"""Online RAW Wi-Fi feature extraction for the RRM application framework.

Feature ordering matches 02_feature_engineering.ipynb: six final channel
samples followed by ten time-domain statistics for each of six channels.
"""

import csv
import logging
from pathlib import Path
import math
import time

import numpy as np

from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr


_LOG = logging.getLogger(__name__)
_CHANNELS = ("ax", "ay", "az", "gx", "gy", "gz")
_STATISTICS = ("mean", "min", "max", "std", "var", "rms", "ptp", "median", "mad", "energy")
# These are algorithm constants taken directly from the supplied notebook.
_WINDOW_SIZE = 20
_STEP_SIZE = 10
# Operational safeguards, not additional application/algorithm parameters.
_CONNECT_TIMEOUT_SECONDS = 50.0
_PACKET_TIMEOUT_SECONDS = 4.0


class FeatureEngineering:
    # DO NOT MODIFY: this is needed for the correct functioning of the framework
    def set_framework(self, app, user_args=None):
        self._app = app  # this is the Application instance
        self._user_args = user_args

    def _parameter(self, name):
        args = self._user_args
        if isinstance(args, dict):
            value = args.get(name)
        else:
            value = getattr(args, name, None) if args is not None else None
        if value is None or not str(value).strip() or str(value).startswith("{{"):
            raise ValueError(f"Required application parameter missing: {name}")
        return str(value).strip()

    # Global setup: do not create Wi-Fi resources on the processing-only partition.
    def setup(self):
        return True

    def setup_and_collect_setup(self):
        self.imu_manager = None
        self._samples = []
        self._acquisition_active = False
        self._window_size = _WINDOW_SIZE
        self._step_size = _STEP_SIZE
        imu = self._parameter("imuname")
        campaign = self._parameter("campaignname")
        interface = self._parameter("wifi_interface")
        ssid = self._parameter("wifi_ssid")
        password = self._parameter("wifi_password")
        sampling_text = self._parameter("samplingfreq")
        try:
            frequency = int(sampling_text)
        except ValueError as exc:
            raise ValueError("samplingfreq must be a positive integer") from exc
        if frequency <= 0:
            raise ValueError("samplingfreq must be greater than zero")

        # The descriptor provides one imuname, not a separate address parameter.
        # A literal IP or MAC can serve as both the manager key and the address.
        self._imu_name = imu
        self.imu_manager = WifiAcquisitionMngr()
        self.imu_manager.set_imus({imu: imu})
        self.imu_manager.set_id_imus([imu])
        self.imu_manager.set_access_point(interface, ssid, password)
        self.imu_manager.set_campaign(campaign, frequency, raw=True)
        try:
            self.imu_manager.start_collection()
            self._acquisition_active = True
            # wait_connection() is unbounded: use the existing manager event to
            # enforce the descriptor's 60-second setup ceiling.
            if not self.imu_manager.ready_connection.wait(_CONNECT_TIMEOUT_SECONDS):
                raise TimeoutError("Timed out connecting to the Wi-Fi IMU")
            self.imu_manager.wait_connection()  # propagates manager worker failures
        except BaseException:
            self.setup_and_collect_cleanup()
            raise
        return True

    def FeatureEngineering_setup(self):
        self._activity = self._parameter("activity")
        self._feature_names = tuple(
            [f"{ch.capitalize()}_last" for ch in _CHANNELS]
            + [f"{ch.capitalize()}_{name}" for ch in _CHANNELS for name in _STATISTICS]
        )
        self._feature_csv = None
        self._feature_writer = None
        # Notebook: ../data/featured/<activity>_features.csv. Anchor to the
        # application installation (not cwd), so partition launches are stable.
        activity_filename = self._activity
        if activity_filename in (".", "..") or any(c in activity_filename for c in ("/", "\\", "\x00")):
            raise ValueError("activity must be a single filename-safe label")
        output_dir = Path(__file__).resolve().parents[0] / "data" / "featured"
        print("output_dir:",output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        self._feature_csv_path = output_dir / f"{activity_filename}_features.csv"
        # Append allows restarts without truncating existing measurements.
        # The original notebook overwrote the CSV; here each online window
        # contributes a new row. Existing headers must match the notebook.
        has_data = self._feature_csv_path.exists() and self._feature_csv_path.stat().st_size > 0
        if has_data:
            with self._feature_csv_path.open("r", newline="", encoding="utf-8") as previous:
                existing_header = next(csv.reader(previous), [])
            if existing_header != list(self._feature_names):
                raise ValueError(f"Existing CSV has incompatible header: {self._feature_csv_path}")
        self._feature_csv = self._feature_csv_path.open("a", newline="", encoding="utf-8")
        self._feature_writer = csv.writer(self._feature_csv)
        if not has_data:
            self._feature_writer.writerow(self._feature_names)
            self._feature_csv.flush()
        return True

    @staticmethod
    def _decode_sample(packet):
        """Decode six 16-bit RAW sensor fields (two's-complement integers).

        No undocumented conversion to g or degrees/s is applied.
        """
        values = []
        for channel in _CHANNELS:
            raw = packet[channel]
            if isinstance(raw, str) and raw.lower().startswith("0x"):
                value = int(raw, 16)
                if value < 0 or value > 0xFFFF:
                    raise ValueError(f"Invalid 16-bit {channel}: {raw}")
                if value >= 0x8000:
                    value -= 0x10000
            else:
                value = float(raw)
            if not math.isfinite(value):
                raise ValueError(f"Non-finite sensor value for {channel}")
            values.append(value)
        return values

    def setup_and_collect_loop(self):
        # A stable dictionary shape is maintained even when no window is ready.
        if self.imu_manager is None or not self._acquisition_active:
            return {"new_window_of_data": None}
        deadline = time.monotonic() + _PACKET_TIMEOUT_SECONDS
        try:
            while len(self._samples) < self._window_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _LOG.warning("Wi-Fi packet timeout: awaiting a complete window")
                    return {"new_window_of_data": None}
                packet = self.imu_manager.get_packet(True, timeout=remaining)
                if packet is None:
                    _LOG.warning("No RAW packet received before timeout")
                    return {"new_window_of_data": None}
                if not isinstance(packet, dict) or packet.get("ts") is None:
                    continue
                if packet.get("imuid") != self._imu_name:
                    continue
                try:
                    sample = self._decode_sample(packet)
                except (KeyError, TypeError, ValueError) as exc:
                    _LOG.warning("Discarded malformed RAW packet: %s", exc)
                    continue
                self._samples.append(sample)

            window = [row.copy() for row in self._samples[:self._window_size]]
            del self._samples[:self._step_size]
            return {"new_window_of_data": window}
        except KeyboardInterrupt:
            _LOG.info("KeyboardInterrupt during Wi-Fi acquisition")
            raise
        except (OSError, RuntimeError, ConnectionError, TimeoutError) as exc:
            _LOG.exception("Wi-Fi acquisition failed: %s", exc)
            # Leave error propagation to the framework and its cleanup lifecycle.
            raise

    def FeatureEngineering_loop(self, new_window_of_data):
        if new_window_of_data is None:
            return {}

        window = np.asarray(new_window_of_data, dtype=float)
        if window.shape != (_WINDOW_SIZE, 6):
            raise ValueError(f"Unexpected RAW window shape: {window.shape}; expected ({_WINDOW_SIZE}, 6)")
        if not np.isfinite(window).all():
            raise ValueError("RAW window contains non-finite samples")

        # Exact statistical operations and ordering from the supplied notebook.
        features = window[-1].tolist()
        for col in range(window.shape[1]):
            x = window[:, col]
            features.extend([
                np.mean(x),
                np.min(x),
                np.max(x),
                np.std(x),
                np.var(x),
                np.sqrt(np.mean(x**2)),
                np.ptp(x),
                np.median(x),
                np.mean(np.abs(x - np.mean(x))),
                np.sum(x**2),
            ])
        feature_vector = [float(x) for x in features]
        self._feature_writer.writerow(feature_vector)
        self._feature_csv.flush()
        return {}

    def setup_and_collect_cleanup(self):
        manager = getattr(self, "imu_manager", None)
        self._acquisition_active = False
        if manager is not None:
            try:
                if getattr(manager, "thread", None) is not None and manager.thread.is_alive():
                    manager.stop_collection()
            except Exception:
                _LOG.exception("Unable to stop Wi-Fi manager cleanly")
                return False
            finally:
                self.imu_manager = None
        self._samples = []
        return True

    def FeatureEngineering_cleanup(self):
        file_handle = getattr(self, "_feature_csv", None)
        try:
            if file_handle is not None and not file_handle.closed:
                file_handle.close()
        finally:
            self._feature_csv = None
            self._feature_writer = None
            self._activity = None
            self._feature_names = ()
        return True

    def cleanup(self):
        return True
