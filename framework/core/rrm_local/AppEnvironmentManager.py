import hashlib
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass
from typing import List, Optional, Set, Tuple

from Config import FRAMEWORK_DIR

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppEnvInfo:
    app_id: str
    venv_dir: str
    python_exec: str
    requirements_file: Optional[str]


class AppEnvironmentManager:
    """Prepare and validate per-application virtualenvs.

    Design goal:
    - Do the heavy work once at RRMLocal startup (scan + create venv + install requirements).
    - Keep PartitionManager lightweight (just uses the already-prepared interpreter).
    """

    def __init__(self, venv_base_dir: str, applications_dir: Optional[str] = None):
        self._venv_base_dir = venv_base_dir
        self._applications_dir = applications_dir or os.path.join(FRAMEWORK_DIR, "applications")

    def _app_dir(self, app_id: str) -> str:
        return os.path.join(self._applications_dir, app_id)

    def _venv_dir(self, app_id: str) -> str:
        return os.path.join(self._venv_base_dir, f"venv_{app_id}")

    def get_python_exec(self, app_id: str) -> str:
        return os.path.join(self._venv_dir(app_id), "bin", "python3")

    def discover_app_ids(self) -> List[str]:
        if not os.path.isdir(self._applications_dir):
            logger.warning(f"Applications directory not found: {self._applications_dir}")
            return []

        app_ids: List[str] = []
        for name in sorted(os.listdir(self._applications_dir)):
            app_path = os.path.join(self._applications_dir, name)
            if os.path.isdir(app_path) and not name.startswith("__"):
                app_ids.append(name)
        return app_ids

    def _requirements_file(self, app_id: str) -> Optional[str]:
        req = os.path.join(self._app_dir(app_id), "requirements.txt")
        return req if os.path.exists(req) else None

    def _requirements_hash_path(self, app_id: str) -> str:
        return os.path.join(self._venv_dir(app_id), ".rrm_requirements.sha256")

    def _parse_requirement_names(self, requirements_file: str) -> Tuple[List[str], bool]:
        """Extract package names from a requirements.txt (best-effort).

        Returns:
            (names, has_complex_entries)

        We treat VCS/URL/constraint/include lines as "complex".
        """
        names: List[str] = []
        has_complex = False

        with open(requirements_file, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#"):
                    continue

                # Includes / constraints / options are complex
                if line.startswith(("-r ", "--requirement ", "-c ", "--constraint ")):
                    has_complex = True
                    continue
                if line.startswith(("-e ", "--editable ", "--find-links ", "--index-url ", "--extra-index-url ")):
                    has_complex = True
                    continue

                # URLs/VCS lines
                if "://" in line or line.startswith(("git+", "hg+", "svn+", "bzr+")):
                    has_complex = True
                    continue

                # Basic PEP 508-ish extraction: take the distribution name prefix
                # Stop at first special char used in specifiers/extras.
                stop_chars = set("<>=!~[ ")
                pkg = ""
                for ch in line:
                    if ch in stop_chars:
                        break
                    pkg += ch
                pkg = pkg.strip()
                if pkg:
                    names.append(pkg)
                else:
                    has_complex = True

        # de-dup while preserving order
        seen = set()
        unique: List[str] = []
        for n in names:
            key = n.lower()
            if key not in seen:
                seen.add(key)
                unique.append(n)
        return unique, has_complex

    def _pip_list_installed_names(self, python_exec: str) -> Set[str]:
        """Return installed distribution names (lowercased) in the venv.

        Uses a single `pip list --format=json` call (faster than N x `pip show`).
        """
        result = subprocess.run(
            [
                python_exec,
                "-m",
                "pip",
                "list",
                "--format=json",
                "--disable-pip-version-check",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        if result.returncode != 0:
            raise subprocess.CalledProcessError(result.returncode, result.args, result.stdout, result.stderr)

        try:
            payload = json.loads(result.stdout or "[]")
        except json.JSONDecodeError:
            logger.debug(f"pip list returned non-JSON output: {result.stdout!r}")
            payload = []

        names: Set[str] = set()
        for item in payload:
            name = (item.get("name") or "").strip().lower()
            if name:
                names.add(name)
        return names

    def _compute_sha256(self, file_path: str) -> str:
        h = hashlib.sha256()
        with open(file_path, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                h.update(chunk)
        return h.hexdigest()

    def _read_text_if_exists(self, path: str) -> Optional[str]:
        try:
            with open(path, "r", encoding="utf-8") as f:
                return f.read().strip()
        except FileNotFoundError:
            return None

    def _write_text(self, path: str, content: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

    def ensure_env_for_app(self, app_id: str) -> AppEnvInfo:
        """Ensure the venv exists and (if requirements.txt exists) it is satisfied.

        Strategy for existing venvs:
        - If requirements hash didn't change since last successful install, skip pip.
        - Otherwise run `pip install -r` to reconcile packages.

        This matches the current behavior of PartitionManager (pip install -r),
        but moves it to RRMLocal startup.
        """
        venv_dir = self._venv_dir(app_id)
        python_exec = self.get_python_exec(app_id)
        requirements_file = self._requirements_file(app_id)

        created = False
        if not os.path.exists(python_exec):
            logger.info(f"Creating virtualenv for app '{app_id}'...")
            subprocess.run([sys.executable, "-m", "venv", venv_dir], check=True)
            created = True

        if requirements_file:
            desired_hash = self._compute_sha256(requirements_file)
            hash_path = self._requirements_hash_path(app_id)
            current_hash = self._read_text_if_exists(hash_path)

            requirements_changed = (current_hash != desired_hash)
            needs_install = created or requirements_changed

            # If requirements didn't change, still verify packages are present (fast offline check)
            if not needs_install:
                names, has_complex = self._parse_requirement_names(requirements_file)
                if has_complex:
                    # Can't reliably check; fall back to pip install -r (idempotent)
                    logger.info(
                        f"Complex requirements detected for app '{app_id}'. "
                        "Running pip install to validate environment..."
                    )
                    needs_install = True
                else:
                    installed = self._pip_list_installed_names(python_exec)
                    missing = [n for n in names if n.strip().lower() not in installed]
                    if missing:
                        logger.info(
                            f"App '{app_id}' missing {len(missing)} package(s) ({', '.join(missing[:5])}" +
                            ("..." if len(missing) > 5 else "") +
                            "), installing requirements..."
                        )
                        needs_install = True
                    else:
                        logger.debug(f"Requirements already satisfied for app '{app_id}' (packages present).")

            if needs_install:
                logger.info(f"Installing/updating requirements for app '{app_id}'...")
                subprocess.run(
                    [
                        python_exec,
                        "-m",
                        "pip",
                        "install",
                        "--disable-pip-version-check",
                        "-r",
                        requirements_file,
                    ],
                    check=True,
                )
                self._write_text(hash_path, desired_hash)
        else:
            logger.debug(f"No requirements.txt for app '{app_id}', skipping pip install.")

        return AppEnvInfo(
            app_id=app_id,
            venv_dir=venv_dir,
            python_exec=python_exec,
            requirements_file=requirements_file,
        )

    def prepare_all(self) -> List[AppEnvInfo]:
        """Scan all apps under Framework/applications and ensure envs."""
        infos: List[AppEnvInfo] = []
        app_ids = self.discover_app_ids()
        if not app_ids:
            logger.info("No applications found to prepare environments for.")
            return infos

        logger.info(f"Preparing environments for {len(app_ids)} application(s)...")
        for app_id in app_ids:
            try:
                infos.append(self.ensure_env_for_app(app_id))
            except subprocess.CalledProcessError as e:
                logger.error(f"Failed preparing environment for app '{app_id}': {e}")
                raise
        logger.info("Application environment preparation completed.")
        return infos
