"""Acquisition manager backed by files instead of physical IMUs.

The public methods intentionally mirror the Wi-Fi/BLE managers used by the
examples.  By default input files are read from ``utilities_library/input`` and are
named after the configured IMU id (for example ``device1.jsonl``).

Each non-empty line can be a JSON object.  CSV files may contain a header; a
plain comma-separated line is also accepted and is mapped to the usual raw
packet fields.
"""

from __future__ import annotations

import csv
import json
import queue
import threading
import time
from pathlib import Path


RAW_FIELDS = (
    "ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz", "nth", "ts"
)
SUPPORTED_SUFFIXES = ("", ".jsonl", ".json", ".csv", ".txt")


class FileAcquisitionMngr:
    """Replay IMU files at the configured sampling frequency."""

    def __init__(self, input_dir=None, loop_files=False):
        self.input_dir = Path(input_dir) if input_dir else Path(__file__).parent / "input"
        self.loop_files = bool(loop_files)

        self.IMUS = []
        self.IMUS_ID_CUSTOM = {}
        self.CAMPAIGN = {
            "name": "",
            "sampling_frequency": 10,
            "raw": True,
            "window_size": 300,
            "step_size": 100,
        }

        self.packet_queue = queue.Queue()
        self.stop_event = threading.Event()
        self.ready_connection = threading.Event()
        self.thread = None
        self._thread_exception = None
        self._thread_exception_reported = False
        self._exception_lock = threading.Lock()

    # ------------------------------------------------------------------
    # Configuration API (compatible with the real managers)

    def set_imus(self, imus):
        """Set IMU names, or a Wi-Fi-style ``{name: address}`` mapping."""
        self.IMUS = list(imus.keys()) if isinstance(imus, dict) else list(imus)

    def set_id_imus(self, ids):
        """Map each configured IMU name to the id used in output/file names."""
        if len(ids) != len(self.IMUS):
            raise ValueError("the number of IMU ids must match the number of IMUs")
        self.IMUS_ID_CUSTOM = dict(zip(self.IMUS, ids))

    def set_campaign(self, name, freq, raw=True, window_size=300, step_size=100):
        freq = int(freq)
        if freq <= 0:
            raise ValueError("sampling frequency must be > 0")
        if not isinstance(raw, bool):
            raise TypeError("raw must be a bool")
        window_size = int(window_size)
        step_size = int(step_size)
        if window_size <= 0 or step_size <= 0 or step_size > window_size:
            raise ValueError("step_size must be > 0 and <= window_size")
        self.CAMPAIGN.update(
            name=name,
            sampling_frequency=freq,
            raw=raw,
            window_size=window_size,
            step_size=step_size,
        )

    def set_access_point(self, *_args, **_kwargs):
        """No-op compatibility method for code shared with WifiAcquisitionMngr."""

    def set_adapter(self, *_args, **_kwargs):
        """No-op compatibility method for code shared with BleAcquisitionMngr."""

    # ------------------------------------------------------------------
    # Collection API

    def start_collection(self):
        if not self.IMUS:
            raise ValueError("configure at least one IMU with set_imus()")
        self.stop_event.clear()
        self.ready_connection.clear()
        with self._exception_lock:
            self._thread_exception = None
            self._thread_exception_reported = False
        self.thread = threading.Thread(target=self._run, name="fake-imu", daemon=True)
        self.thread.start()

    def wait_connection(self):
        self.ready_connection.wait()
        self._raise_thread_exception_if_any()

    def stop_collection(self):
        self.stop_event.set()
        if self.thread and self.thread is not threading.current_thread():
            self.thread.join()

    def force_disconnect(self, *_args, **_kwargs):
        self.stop_collection()

    def get_packet(self, block=False, timeout=None):
        self._raise_thread_exception_if_any()
        try:
            packet = self.packet_queue.get(block=block, timeout=timeout if block else None)
        except queue.Empty:
            self._raise_thread_exception_if_any()
            return None
        self._raise_thread_exception_if_any()
        return packet

    def get_battery_levels(self):
        """Return unknown battery values, as no real hardware is connected."""
        return {self.IMUS_ID_CUSTOM.get(imu, imu): None for imu in self.IMUS}

    # ------------------------------------------------------------------

    def _raise_thread_exception_if_any(self):
        with self._exception_lock:
            if self._thread_exception is None or self._thread_exception_reported:
                return
            exception = self._thread_exception
            self._thread_exception_reported = True
        raise exception

    def _record_exception(self, exception):
        with self._exception_lock:
            if self._thread_exception is None:
                self._thread_exception = exception
        self.ready_connection.set()

    def _find_file(self, imu_name):
        file_id = self.IMUS_ID_CUSTOM.get(imu_name, imu_name)
        for suffix in SUPPORTED_SUFFIXES:
            candidate = self.input_dir / f"{file_id}{suffix}"
            if candidate.is_file():
                return candidate
        raise FileNotFoundError(
            f"no input file found for IMU '{file_id}' in {self.input_dir}"
        )

    @staticmethod
    def _parse_file(path):
        if path.suffix.lower() == ".json":
            content = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(content, dict):
                content = content.get("packets", [content])
            if not isinstance(content, list):
                raise ValueError(f"JSON input must contain an object or list: {path}")
            return [dict(packet) for packet in content if isinstance(packet, dict)]

        if path.suffix.lower() == ".csv":
            with path.open(newline="", encoding="utf-8") as stream:
                rows = list(csv.DictReader(stream))
            if rows:
                return [dict(row) for row in rows]

        packets = []
        with path.open(encoding="utf-8") as stream:
            for line in stream:
                line = line.strip()
                if not line:
                    continue
                try:
                    packet = json.loads(line)
                except json.JSONDecodeError:
                    values = [value.strip() for value in line.split(",")]
                    packet = dict(zip(RAW_FIELDS, values))
                if not isinstance(packet, dict):
                    raise ValueError(f"each input line must be an object: {path}")
                packets.append(packet)
        return packets

    def _run(self):
        try:
            sources = {}
            for imu in self.IMUS:
                path = self._find_file(imu)
                sources[imu] = self._parse_file(path)
                if not sources[imu]:
                    raise ValueError(f"input file is empty: {path}")

            self.ready_connection.set()
            period = 1.0 / self.CAMPAIGN["sampling_frequency"]
            positions = {imu: 0 for imu in self.IMUS}
            next_due = {imu: time.monotonic() for imu in self.IMUS}

            while not self.stop_event.is_set():
                active_imus = list(positions)
                if not active_imus:
                    break
                imu = min(active_imus, key=lambda item: next_due[item])
                delay = next_due[imu] - time.monotonic()
                if delay > 0:
                    self.stop_event.wait(delay)
                    continue

                packet = dict(sources[imu][positions[imu]])
                packet.setdefault("nth", positions[imu])
                packet.setdefault("ts", time.time())
                packet["imuid"] = self.IMUS_ID_CUSTOM.get(imu, imu)
                packet.setdefault("mode", "raw" if self.CAMPAIGN["raw"] else "features")
                packet.setdefault("cname", self.CAMPAIGN["name"])
                self.packet_queue.put(packet)
                positions[imu] += 1
                if positions[imu] >= len(sources[imu]):
                    if self.loop_files:
                        positions[imu] = 0
                    else:
                        del positions[imu]
                        del next_due[imu]
                        if not positions:
                            break
                        continue
                next_due[imu] += period
        except Exception as exception:  # surfaced by wait_connection/get_packet
            self._record_exception(exception)
        finally:
            self.ready_connection.set()
