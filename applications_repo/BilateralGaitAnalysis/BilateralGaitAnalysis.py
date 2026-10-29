"""Framework task orchestrator for bilateral gait analysis."""

from __future__ import annotations

import logging
import json
from pathlib import Path
import re
import time

import pandas as pd

from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr
from applications_repo.BilateralGaitAnalysis.Util.config import (
    as_bool as _as_bool,
    non_negative_float as _non_negative_float,
    non_negative_int as _non_negative_int,
    positive_float as _positive_float,
    positive_int as _positive_int,
    split_parameter as _split_parameter,
)
from applications_repo.BilateralGaitAnalysis.Util.acquisition_report import AcquisitionWindowReporter
from applications_repo.BilateralGaitAnalysis.Util.dataset_source import SensorPositionDatasetFileSource
from applications_repo.BilateralGaitAnalysis.Util.gait_constants import GAITMAP_SENSOR_COLUMNS
from applications_repo.BilateralGaitAnalysis.Util.gait_pipeline import (
    BarthDtwStrideSegmenter,
    GaitResultAggregator,
    GaitResultExporter,
    HerzerGaitEventDetector,
    ImuWindowPreprocessor,
    SpatialGaitParameterCalculator,
    StrideTrajectoryReconstructor,
    TemporalGaitParameterCalculator,
)


logger = logging.getLogger(__name__)

BLE_ACCELEROMETER_RANGE_G = 4.0
BLE_GYROSCOPE_RANGE_DPS = 2000.0

class BilateralGaitAnalysis:
    """Coordinate gait analysis from one IMU on each foot.

    Planned full pipeline:
        acquisition -> preprocessing -> BarthDtw -> Herzer event detection ->
        temporal parameters -> stride trajectories -> spatial parameters -> export.

    The framework invokes every ``*_setup`` method once, the ``*_loop`` methods
    repeatedly while the application is active, and the ``*_cleanup`` methods when
    an external stop request terminates the application.
    """

    def set_framework(self, app, user_args=None):
        """Store references supplied by the framework.

        Args:
            app: Running framework ``Application`` instance. It will later provide
                lifecycle operations such as peripheral notification and shutdown.
            user_args: Mapping containing the descriptor parameters selected by the
                user. Values normally arrive as strings.

        Returns:
            Nothing. The references are retained for ``setup`` and all task methods.
        """
        self._app = app
        self._user_args = user_args or {}

    @staticmethod
    def _ble_unsigned_value(value, field, bits):
        """Decode one hexadecimal BLE field as an unsigned integer.

        Args:
            value: A packet value such as ``"0xfa22"``. Integer values are also
                accepted to make deterministic tests and diagnostics convenient.
            field: Field name included in a possible validation exception.
            bits: Storage width: 16 for sensor channels/``nth`` and 32 for ``ts``.

        Returns:
            An integer between zero and ``2**bits - 1`` (both included).

        Raises:
            ValueError: If the value is not an integer or does not fit in ``bits``.
        """
        try:
            parsed = int(value, 0) if isinstance(value, str) else int(value)
        except (TypeError, ValueError) as error:
            raise ValueError(
                f"BLE field {field!r} is not a valid integer: {value!r}."
            ) from error
        if not 0 <= parsed < 2**bits:
            raise ValueError(f"BLE field {field!r} does not fit in {bits} bits.")
        return parsed

    @classmethod
    def _ble_signed_16(cls, value, field):
        """Return the signed -32768..32767 value encoded by a 16-bit BLE field."""
        unsigned = cls._ble_unsigned_value(value, field, 16)
        return unsigned - 65536 if unsigned >= 32768 else unsigned

    def _decode_ble_packet(self, packet):
        """Validate and scale one raw packet received from the local BLE manager.

        Args:
            packet: Dictionary produced by ``WifiAcquisitionMngr``. A data
                packet must contain ``ax``, ``ay``, ``az``, ``gx``, ``gy``, ``gz``,
                ``nth``, ``ts``, ``imuid`` and ``cname``. Magnetometer fields are
                optional because they are not used by this application.

        Returns:
            ``None`` for battery packets or packets from unrelated devices.
            Otherwise returns ``(imu_id, nth, six_values, ts)``. The three
            accelerations are expressed in g and the three angular rates in
            degrees/second. Preprocessing later converts g to m/s² for gaitmap.

        The fixed conversion deliberately reproduces the already-established code:

        ``acc = signed_raw * (4.0 / 32768.0)``
        ``gyr = signed_raw * (2000.0 / 32768.0)``

        Magnetometer values are ignored because the chosen gaitmap algorithms use
        accelerometer and gyroscope only.
        """
        if not isinstance(packet, dict):
            raise ValueError("The BLE manager returned a non-dictionary packet.")
        imu_id = str(packet.get("imuid", ""))
        if imu_id not in self._ble_pending_packets or "battery" in packet:
            return None

        required_fields = (
            "ax", "ay", "az", "gx", "gy", "gz", "nth", "ts", "cname"
        )
        missing = [field for field in required_fields if field not in packet]
        if missing:
            raise ValueError(
                f"BLE packet from {imu_id!r} is missing: {', '.join(missing)}."
            )

        # `cname` identifies the acquisition campaign, not an individual IMU.
        # Consequently every packet from both feet must carry the single campaign
        # name passed to WifiAcquisitionMngr during setup. A mismatch would mean that data
        # from two different sessions are being mixed in the same gait window.
        packet_campaign = str(packet["cname"])
        if packet_campaign != self._campaign_name:
            raise ValueError(
                f"BLE packet from {imu_id!r} belongs to campaign "
                f"{packet_campaign!r}, expected {self._campaign_name!r}."
            )

        raw_values = [
            self._ble_signed_16(packet[field], field)
            for field in ("ax", "ay", "az", "gx", "gy", "gz")
        ]
        values = [
            value * (BLE_ACCELEROMETER_RANGE_G / 32768.0)
            for value in raw_values[:3]
        ] + [
            value * (BLE_GYROSCOPE_RANGE_DPS / 32768.0)
            for value in raw_values[3:]
        ]
        return (
            imu_id,
            self._ble_unsigned_value(packet["nth"], "nth", 16),
            values,
            self._ble_unsigned_value(packet["ts"], "ts", 32),
        )

    def _unwrap_ble_counter(self, imu_id, raw_counter):
        """Convert wrapping ``nth`` into a monotonically increasing sample number.

        Returns:
            The unwrapped counter. ``None`` means that the packet is a duplicate or
            an old out-of-order packet and must not enter the analysis window.
        """
        previous_raw = self._ble_last_raw_counter[imu_id]
        if previous_raw is None:
            unwrapped = raw_counter
        else:
            delta = (raw_counter - previous_raw) % 65536
            if delta == 0 or delta >= 32768:
                return None
            # `nth` increases once per packet on each physical IMU. Therefore a
            # forward jump of N means that N-1 packets from this specific IMU did
            # not reach the application. Summing both devices gives the actual
            # packet-loss count, which is distinct from skipped synchronized time
            # instants (one instant can contain two missing packets).
            self._ble_lost_packets_total += delta - 1
            unwrapped = self._ble_last_unwrapped_counter[imu_id] + delta
        self._ble_last_raw_counter[imu_id] = raw_counter
        self._ble_last_unwrapped_counter[imu_id] = unwrapped
        return unwrapped

    def _consume_synchronized_ble_samples(self):
        """Move consecutive counters present for both feet into the active window.

        The per-device dictionaries allow notifications to arrive in either order.
        If both devices have advanced beyond an absent counter, at least one packet
        was lost. In that case acquisition skips to the next counter actually shared
        by both feet, but preserves the synchronized samples already collected.
        Requiring 20 completely lossless BLE seconds would otherwise allow one
        occasional radio loss to reset the entire window forever.

        Returns:
            Nothing. The method updates the acquisition buffers in place.
        """
        left_imu, right_imu = self._imu_names
        if self._ble_expected_counter is None:
            common = (
                self._ble_pending_packets[left_imu].keys()
                & self._ble_pending_packets[right_imu].keys()
            )
            if not common:
                return
            self._ble_expected_counter = min(common)

        while all(
            self._ble_expected_counter in self._ble_pending_packets[imu_id]
            for imu_id in self._imu_names
        ):
            counter = self._ble_expected_counter
            self._ble_synchronized_run.append(
                (
                    counter,
                    self._ble_pending_packets[left_imu].pop(counter),
                    self._ble_pending_packets[right_imu].pop(counter),
                )
            )
            self._ble_expected_counter += 1

        both_advanced = all(
            self._ble_pending_packets[imu_id]
            and max(self._ble_pending_packets[imu_id]) > self._ble_expected_counter
            for imu_id in self._imu_names
        )
        if both_advanced:
            common = (
                self._ble_pending_packets[left_imu].keys()
                & self._ble_pending_packets[right_imu].keys()
            )
            later_common = [
                counter for counter in common
                if counter > self._ble_expected_counter
            ]
            if later_common:
                next_counter = min(later_common)
                self._ble_discarded_samples += (
                    next_counter - self._ble_expected_counter
                )
                logger.warning(
                    "BLE synchronization gap: skipping counters %s:%s while "
                    "preserving %s already synchronized samples.",
                    self._ble_expected_counter,
                    next_counter,
                    len(self._ble_synchronized_run),
                )
                for imu_id in self._imu_names:
                    pending = self._ble_pending_packets[imu_id]
                    for stale_counter in [
                        counter for counter in pending if counter < next_counter
                    ]:
                        pending.pop(stale_counter, None)
                self._ble_expected_counter = next_counter
                self._consume_synchronized_ble_samples()

    def _build_ble_window(self):
        """Build one gait-analysis input dictionary from synchronized BLE samples.

        Returns:
            A dictionary with two six-column DataFrames, timing/counter metadata and
            ``acceleration_unit='g'``. The latter tells preprocessing to perform the
            final g-to-m/s² conversion required by gaitmap. Overlap samples remain
            buffered and will be repeated in the following window.
        """
        emitted = self._ble_synchronized_run[: self._ble_window_samples]
        start_sample = self._ble_next_window_start_sample
        end_sample = start_sample + self._ble_window_samples
        actual_duration_s = time.perf_counter() - self._ble_window_phase_started_at
        result = {
            "data": {
                "left_sensor": pd.DataFrame(
                    [sample[1][0] for sample in emitted],
                    columns=GAITMAP_SENSOR_COLUMNS,
                ),
                "right_sensor": pd.DataFrame(
                    [sample[2][0] for sample in emitted],
                    columns=GAITMAP_SENSOR_COLUMNS,
                ),
            },
            "sampling_rate_hz": self._sampling_rate_hz,
            "acceleration_unit": "g",
            "gyroscope_unit": "deg/s",
            "window_index": self._ble_window_index,
            "start_sample": start_sample,
            "end_sample": end_sample,
            "start_time_s": start_sample / self._sampling_rate_hz,
            "end_time_s": end_sample / self._sampling_rate_hz,
            "is_final_window": False,
            "first_nth": emitted[0][0] % 65536,
            "last_nth": emitted[-1][0] % 65536,
            "firmware_timestamps": {
                "left_sensor": [sample[1][1] for sample in emitted],
                "right_sensor": [sample[2][1] for sample in emitted],
            },
            # A window has exactly one campaign name, common to both IMUs. Packet
            # decoding has already rejected any value different from this one.
            "campaign_name": self._campaign_name,
            "discarded_incomplete_samples": self._ble_discarded_samples,
            "lost_packets": (
                self._ble_lost_packets_total
                - self._ble_lost_packets_at_window_start
            ),
            "actual_duration_s": actual_duration_s,
        }
        self._ble_lost_packets_at_window_start = self._ble_lost_packets_total
        step_samples = self._ble_window_samples - self._ble_overlap_samples
        self._ble_synchronized_run = self._ble_synchronized_run[step_samples:]
        self._ble_next_window_start_sample += step_samples
        self._ble_window_index += 1
        self._ble_last_progress_logged = len(self._ble_synchronized_run)
        logger.info(
            "[window=%s] END acquire_imu_window source=ble duration_s=%.3f",
            result["window_index"],
            actual_duration_s,
        )
        self._ble_window_phase_started_at = None
        return result

    def _initialize_acquisition_csv(self):
        """Create the acquisition report used by all completed windows."""
        self._acquisition_reporter = AcquisitionWindowReporter(self._output_path)
        self._acquisition_csv_path = self._acquisition_reporter.path

    def _record_acquisition_window(self, window):
        """Append acquisition-quality information for one complete window.

        Args:
            window: Complete raw-window dictionary produced by the dataset source
                or BLE acquisition. ``lost_packets`` is zero for an immutable
                dataset and is calculated from per-IMU ``nth`` gaps for BLE.

        Returns:
            The same ``window`` object, allowing the caller to record and return it
            without altering the framework's existing data contract.
        """
        return self._acquisition_reporter.record(window)

    def _initialize_raw_packet_json(self):
        """Open one temporary diagnostic JSON stream for each configured IMU."""
        raw_path = Path(self._output_path).expanduser()
        raw_path.mkdir(parents=True, exist_ok=True)
        self._raw_packets_files = {}
        self._raw_packets_paths = {}
        self._raw_packet_first = {}
        for imu_id in self._imu_names:
            safe_imu_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(imu_id))
            path = raw_path / f"raw_wifi_packets_{safe_imu_id}.json"
            file = path.open("w", encoding="utf-8")
            file.write("[\n")
            self._raw_packets_files[imu_id] = file
            self._raw_packets_paths[imu_id] = path
            self._raw_packet_first[imu_id] = True

    def _record_raw_ble_packet(self, packet):
        """Write one unmodified manager packet before application decoding."""
        files = getattr(self, "_raw_packets_files", {})
        if not files:
            return
        imu_id = str(packet.get("imuid", "")) if isinstance(packet, dict) else ""
        raw_file = files.get(imu_id)
        if raw_file is None:
            logger.warning("Raw BLE packet has unknown IMU id %r; packet not saved", imu_id)
            return
        if not self._raw_packet_first[imu_id]:
            raw_file.write(",\n")
        json.dump(packet, raw_file, ensure_ascii=False)
        raw_file.flush()
        self._raw_packet_first[imu_id] = False

    def _close_raw_packet_json(self):
        """Close the temporary raw-packet JSON array safely and idempotently."""
        files = getattr(self, "_raw_packets_files", {})
        if not files:
            return
        for imu_id, raw_file in list(files.items()):
            try:
                raw_file.write("\n]\n")
                raw_file.flush()
            finally:
                raw_file.close()
        self._raw_packets_files = {}

    @staticmethod
    def _run_logged_phase(task_name, phase_input, operation):
        """Execute one processing phase and log its start, end, or failure.

        Args:
            task_name: Descriptor task identifier shown in the log message.
            phase_input: Primary input envelope. A ``None`` value represents file
                exhaustion or a real-time replay window that is not ready yet.
            operation: Zero-argument callable performing the actual phase.

        Returns:
            Exactly the value returned by ``operation``. When ``phase_input`` is
            ``None``, the operation still runs to preserve normal propagation but
            no START/END messages are emitted, avoiding log spam during waits.

        Raises:
            Any exception raised by ``operation`` after logging a FAILED message
            containing the task name, window index and elapsed processing time.
        """
        if phase_input is None:
            return operation()
        window_index = (
            phase_input.get("window_index", "unknown")
            if isinstance(phase_input, dict)
            else "unknown"
        )
        started_at = time.perf_counter()
        logger.info("[window=%s] START %s", window_index, task_name)
        try:
            result = operation()
        except Exception:
            logger.exception(
                "[window=%s] FAILED %s duration_s=%.3f",
                window_index,
                task_name,
                time.perf_counter() - started_at,
            )
            raise
        logger.info(
            "[window=%s] END %s duration_s=%.3f",
            window_index,
            task_name,
            time.perf_counter() - started_at,
        )
        return result

    def setup(self):
        """Validate configuration shared by all tasks.

        The bilateral analysis has a stricter hardware contract than the former TUG
        application: exactly two IMUs are required, ordered left foot then right
        foot. This is checked here rather than encoded as a JSON array constraint.

        Returns:
            ``True`` when the configuration is valid.

        Raises:
            ValueError: If the IMU count, acquisition mode, window geometry,
                sampling frequency, or anatomical positions are invalid.
        """
        self._imu_names = _split_parameter(self._user_args.get("imu_names", ""))
        if len(self._imu_names) != 2:
            raise ValueError(
                "BilateralGaitAnalysis requires exactly two IMUs in 'imu_names': "
                "left foot first and right foot second."
            )

        positions = _split_parameter(
            self._user_args.get("sensor_positions", "left_foot-right_foot")
        )
        if positions != ["left_foot", "right_foot"]:
            raise ValueError(
                "sensor_positions must be 'left_foot-right_foot' and must follow "
                "the same order as imu_names."
            )
        self._sensor_positions = dict(zip(self._imu_names, positions))

        self._acquisition_mode = str(
            self._user_args.get("acquisition_mode", "wifi")
        ).strip().lower()
        if self._acquisition_mode not in {"wifi", "file"}:
            raise ValueError("acquisition_mode must be either 'wifi' or 'file'.")

        self._sampling_rate_hz = _positive_float(
            self._user_args.get("sampling_frequency_hz", 100),
            "sampling_frequency_hz",
        )
        self._lowpass_cutoff_hz = _positive_float(
            self._user_args.get("lowpass_cutoff_hz", 20),
            "lowpass_cutoff_hz",
        )
        if self._lowpass_cutoff_hz >= self._sampling_rate_hz / 2:
            raise ValueError(
                "lowpass_cutoff_hz must be below half of sampling_frequency_hz."
            )
        self._window_duration_s = _positive_float(
            self._user_args.get("window_duration_s", 20), "window_duration_s"
        )
        self._window_overlap_s = _non_negative_float(
            self._user_args.get("window_overlap_s", 2), "window_overlap_s"
        )
        if self._window_overlap_s >= self._window_duration_s:
            raise ValueError("window_overlap_s must be smaller than window_duration_s.")
        self._lightweight_mode = _as_bool(
            self._user_args.get("lightweight_mode", False)
        )
        # `barth_max_cost` is not a choice from a fixed enumeration. This
        # application accepts every finite real number greater than zero; 4.0 is
        # the official BarthDtw default. It is the largest normalized DTW cost that
        # a candidate may have and still be accepted as a stride:
        #
        #   smaller value -> stricter matching, fewer false positives, but more
        #                    real/pathological strides can be missed;
        #   larger value  -> more permissive matching and more detected strides,
        #                    but also a greater risk of false positives.
        #
        # Values such as 3.0, 3.5, 4.0, 4.5 and 5.0 are useful tuning candidates,
        # not the only allowed values. Gaitmap itself also accepts `None` to omit
        # the threshold, but the descriptor deliberately does not expose that mode
        # because it can admit unsuitable matches and complicates validation.
        self._barth_max_cost = _positive_float(
            self._user_args.get("barth_max_cost", 4.0), "barth_max_cost"
        )
        self._minimum_complete_strides = _positive_int(
            self._user_args.get("minimum_complete_strides", 3),
            "minimum_complete_strides",
        )
        self._input_path = str(self._user_args.get("input_path", ""))
        if self._acquisition_mode == "file" and not self._input_path.strip():
            raise ValueError("input_path is required when acquisition_mode is 'file'.")

        self._wifi_interface = str(self._user_args.get("wifi_interface", "wlan0"))
        self._wifi_ssid = str(self._user_args.get("wifi_ssid", ""))
        self._wifi_password = str(self._user_args.get("wifi_password", ""))
        self._wifi_port = _positive_int(self._user_args.get("wifi_port", 8023), "wifi_port")
        self._subject_id = str(self._user_args.get("subject_id", "unknown_subject"))
        self._trial_id = str(self._user_args.get("trial_id", "gait_trial"))
        # The campaign name is written by the BLE manager into every packet as
        # `cname`. It identifies the acquisition session, while `trial_id` labels
        # the exported gait result. They may be equal but have distinct purposes.
        self._campaign_name = str(
            self._user_args.get("campaign_name", self._trial_id)
        ).strip()
        if self._acquisition_mode == "wifi" and not self._campaign_name:
            raise ValueError("campaign_name cannot be empty in Wi-Fi mode.")
        self._initial_counter = _non_negative_int(
            self._user_args.get("initial_counter", 0), "initial_counter"
        )
        if self._initial_counter > 65535:
            raise ValueError("initial_counter must be between 0 and 65535.")
        self._output_path = str(self._user_args.get("output_path", "output/"))
        # Allocate every task resource name before the first task-specific setup.
        # LifecycleManager runs all cleanup methods even when an early setup task
        # raises an exception. Initializing these attributes to None makes those
        # cleanup methods safe: each one can distinguish "resource never created"
        # from a live object that must actually be closed.
        self._acquisition = None
        self._ble_manager = None
        self._ble_peripherals_announced = False
        self._preprocessor = None
        self._stride_segmenter = None
        self._event_detector = None
        self._temporal_calculator = None
        self._trajectory_reconstructor = None
        self._spatial_calculator = None
        self._result_aggregator = None
        self._exporter = None
        self._acquisition_reporter = None
        self._acquisition_csv_path = None
        self._raw_packets_paths = {}
        self._raw_packets_files = {}
        self._raw_packet_first = {}
        self._file_eof_announced = False
        return True

    # ------------------------------------------------------------------
    # Setup methods: allocate task-specific objects once.
    # ------------------------------------------------------------------

    def acquire_imu_window_setup(self):
        """Open the dataset source or connect both physical BLE IMUs.

        Returns:
            ``True`` after acquisition resources have been prepared.

        In file mode ``input_path`` must point to the extracted dataset root,
        ``subject_id`` selects a participant and ``trial_id`` selects one test.
        The dataset's real 204.8 Hz rate overrides the live-device configuration.
        In Wi-Fi mode the shared manager starts a raw campaign at the configured
        frequency (normally 100 Hz), waits for both connections, and then reports
        the peripheral reservation to the framework.
        """
        if self._acquisition_mode == "file":
            self._acquisition = SensorPositionDatasetFileSource(
                dataset_path=self._input_path,
                participant=self._subject_id,
                trial=self._trial_id,
                window_duration_s=self._window_duration_s,
                window_overlap_s=self._window_overlap_s,
            ).open()
        else:
            # Wi-Fi manager receives the stable IMU identifiers plus their IP/MAC
            # addresses. RAW is mandatory because gaitmap needs every sample.
            self._ble_manager = WifiAcquisitionMngr()
            # Same initialization contract used by Examples/example_WIFI.py:
            # an ordered list of MAC/IP addresses is accepted directly.
            self._ble_manager.set_imus(self._imu_names)
            self._ble_manager.imu_port = self._wifi_port
            self._ble_manager.set_access_point(
                self._wifi_interface, self._wifi_ssid, self._wifi_password
            )
            self._ble_manager.set_campaign(
                self._campaign_name,
                int(self._sampling_rate_hz),
                # This application deliberately always requests RAW samples.
                # The feature-capable manager still supports FEATURES for other
                # applications, but gaitmap requires the complete time series.
                raw=True,
                # These two fields are ignored by the firmware in RAW mode.
                # Keep the same defaults used by example_WIFI.py rather than
                # sending the application's 20-second gait window (2000/1800).
                window_size=300,
                step_size=100,
            )
            self._initialize_raw_packet_json()
            self._ble_manager.start_collection()
            self._ble_manager.wait_connection()
            self._app.notify_peripherals_in_use(self._imu_names, "wifi")
            self._ble_peripherals_announced = True
            # As in BreathAnalysis, packets are split by device inside the task.
            # Here dictionaries indexed by `nth` are used because gait analysis
            # additionally requires exact left/right sample synchronization.
            self._ble_pending_packets = {imu_id: {} for imu_id in self._imu_names}
            self._ble_last_raw_counter = {imu_id: None for imu_id in self._imu_names}
            self._ble_last_unwrapped_counter = {
                imu_id: None for imu_id in self._imu_names
            }
            self._ble_synchronized_run = []
            self._ble_expected_counter = None
            self._ble_discarded_samples = 0
            self._ble_lost_packets_total = 0
            self._ble_lost_packets_at_window_start = 0
            self._ble_window_samples = round(
                self._window_duration_s * self._sampling_rate_hz
            )
            self._ble_overlap_samples = round(
                self._window_overlap_s * self._sampling_rate_hz
            )
            self._ble_window_index = 0
            self._ble_next_window_start_sample = 0
            self._ble_window_phase_started_at = None
            self._ble_last_progress_logged = 0
            self._acquisition = self._ble_manager
        self._initialize_acquisition_csv()
        return True

    def preprocess_imu_window_setup(self):
        """Create the reusable native-frequency filtering configuration.

        Returns:
            ``True`` after an :class:`ImuWindowPreprocessor` has been created.

        The filter coefficients are calculated for the frequency carried by each
        input window: 204.8 Hz for dataset files and 100 Hz for the future BLE
        source. Preprocessing deliberately preserves that frequency.
        """
        self._preprocessor = ImuWindowPreprocessor(
            lowpass_cutoff_hz=self._lowpass_cutoff_hz,
        )
        return True

    def segment_strides_setup(self):
        """Create BarthDTW once so its template and JIT code can be reused.

        Returns:
            ``True`` after constructing :class:`BarthDtwStrideSegmenter` with the
            descriptor's ``barth_max_cost``. Lightweight mode does not replace
            stride segmentation; it skips expensive spatial reconstruction later.
        """
        self._stride_segmenter = BarthDtwStrideSegmenter(
            max_cost=self._barth_max_cost
        )
        return True

    def detect_gait_events_setup(self):
        """Create the Herzer detector once and return ``True``."""
        self._event_detector = HerzerGaitEventDetector()
        return True

    def calculate_temporal_parameters_setup(self):
        """Create the min-velocity temporal calculator and return ``True``."""
        self._temporal_calculator = TemporalGaitParameterCalculator()
        return True

    def reconstruct_stride_trajectories_setup(self):
        """Prepare full reconstruction or the explicit lightweight bypass."""
        self._trajectory_reconstructor = StrideTrajectoryReconstructor(
            lightweight_mode=self._lightweight_mode
        )
        return True

    def calculate_spatial_parameters_setup(self):
        """Prepare all spatial metrics or the lightweight bypass."""
        self._spatial_calculator = SpatialGaitParameterCalculator(
            lightweight_mode=self._lightweight_mode
        )
        return True

    def aggregate_gait_results_setup(self):
        """Prepare trial-wide deduplication and statistics state."""
        self._result_aggregator = GaitResultAggregator(
            deduplication_tolerance_s=0.1,
            minimum_complete_strides=self._minimum_complete_strides,
        )
        return True

    def export_gait_result_setup(self):
        """Create the output directory and atomic result exporter."""
        self._exporter = GaitResultExporter(
            output_path=self._output_path,
            subject_id=self._subject_id,
            trial_id=self._trial_id,
        )
        return True

    # ------------------------------------------------------------------
    # Loop methods: placeholders preserving the framework data contracts.
    # ------------------------------------------------------------------

    def acquire_imu_window_loop(self):
        """Return the next synchronized two-foot window.

        Returns:
            A mapping with ``raw_imu_window``. In file mode its value is the
            documented window dictionary returned by the active source. Both file
            and BLE modes remain inside this method until a complete synchronized
            window is ready. Temporary ``None`` values produced by the replay clock
            are consumed here and never enter the downstream pipeline.

        Reaching the end of a replay file does not request framework shutdown. This
        preserves the lifecycle rule that termination belongs to the user/framework.
        """
        if self._acquisition_mode == "file":
            # Remain inside the acquisition task until one complete recorded
            # window is available. Temporary None values are internal clock ticks,
            # not pipeline data, and must never trigger preprocessing or analysis.
            while True:
                window = self._acquisition.next_window()
                if window is not None:
                    return {
                        "raw_imu_window": self._record_acquisition_window(window)
                    }
                if self._acquisition.is_exhausted:
                    if not self._file_eof_announced:
                        # Notify the GUI exactly once. The application deliberately
                        # remains alive after this message: only the framework/user
                        # owns termination, while this task waits below for STOP.
                        self._app.notify_message(
                            "Dataset terminato: tutte le finestre disponibili sono "
                            "state elaborate. L'applicazione è in attesa del comando "
                            "di arresto.",
                            severity="info",
                        )
                        logger.info(
                            "Dataset exhausted; waiting for external framework STOP "
                            "without executing further taskgraph iterations."
                        )
                        self._file_eof_announced = True
                    self._app.wait_for_stop()
                if not self._app.is_running():
                    self._app.wait_for_stop()

        # This is the same core pattern used by BreathAnalysis: repeatedly obtain a
        # packet from WifiAcquisitionMngr and split it according to `imuid` until a window is
        # ready. `get_packet` uses a short timeout so the STOP state can be checked
        # even if one IMU stops transmitting. No incomplete value is propagated to
        # preprocessing: the task remains here until the full window is available.
        if self._ble_window_phase_started_at is None:
            self._ble_window_phase_started_at = time.perf_counter()
            logger.info(
                "[window=%s] START acquire_imu_window source=ble",
                self._ble_window_index,
            )
        while len(self._ble_synchronized_run) < self._ble_window_samples:
            # Check STOP on every iteration, including when the BLE queue is never
            # empty. Previously STOP was observed only after get_packet() timed out,
            # so a continuous sensor stream could keep this task alive forever.
            if not self._app.is_running():
                self._app.wait_for_stop()
            packet = self._ble_manager.get_packet(
                block=True, timeout=0.25
            )
            if packet is None:
                if not self._app.is_running():
                    self._app.wait_for_stop()
                continue
            self._record_raw_ble_packet(packet)
            decoded = self._decode_ble_packet(packet)
            if decoded is None:
                continue
            imu_id, raw_counter, values, timestamp = decoded
            counter = self._unwrap_ble_counter(imu_id, raw_counter)
            if counter is None:
                continue
            self._ble_pending_packets[imu_id][counter] = (
                values,
                timestamp,
            )
            self._consume_synchronized_ble_samples()
            synchronized_count = len(self._ble_synchronized_run)
            progress_interval = max(1, round(5 * self._sampling_rate_hz))
            if synchronized_count - self._ble_last_progress_logged >= progress_interval:
                logger.info(
                    "[window=%s] acquire_imu_window progress=%s/%s synchronized "
                    "samples discarded_missing=%s",
                    self._ble_window_index,
                    synchronized_count,
                    self._ble_window_samples,
                    self._ble_discarded_samples,
                )
                self._ble_last_progress_logged = synchronized_count

        window = self._build_ble_window()
        return {"raw_imu_window": self._record_acquisition_window(window)}

    def preprocess_imu_window_loop(self, raw_imu_window):
        """Validate and filter one synchronized window at its native frequency.

        Args:
            raw_imu_window: Complete window emitted by
                ``acquire_imu_window_loop``. Acquisition never emits ``None``.

        Returns:
            A one-key framework result mapping containing the two gaitmap-ready
            DataFrames and processing metadata documented by
            :meth:`ImuWindowPreprocessor.process`.
        """
        processed = self._run_logged_phase(
            "preprocess_imu_window",
            raw_imu_window,
            lambda: self._preprocessor.process(raw_imu_window),
        )
        return {"preprocessed_imu_window": processed}

    def segment_strides_loop(self, preprocessed_imu_window):
        """Detect per-foot stride borders in one native-frequency window.

        Args:
            preprocessed_imu_window: Output value from the preprocessing task.

        Returns:
            A framework mapping whose ``segmented_stride_list`` value is the Barth
            result envelope documented by :meth:`BarthDtwStrideSegmenter.segment`.
        """
        segmented = self._run_logged_phase(
            "segment_strides",
            preprocessed_imu_window,
            lambda: self._stride_segmenter.segment(preprocessed_imu_window),
        )
        return {"segmented_stride_list": segmented}

    def detect_gait_events_loop(
        self, preprocessed_imu_window, segmented_stride_list
    ):
        """Detect gait events inside the Barth-segmented strides.

        Args:
            preprocessed_imu_window: Filtered native-frequency signal envelope.
            segmented_stride_list: Barth result envelope for the same window.

        Returns:
            A framework mapping containing the two official Herzer event-list
            representations documented by :class:`HerzerGaitEventDetector`.
        """
        events = self._run_logged_phase(
            "detect_gait_events",
            segmented_stride_list,
            lambda: self._event_detector.detect(
                preprocessed_imu_window, segmented_stride_list
            ),
        )
        return {"gait_event_list": events}

    def calculate_temporal_parameters_loop(self, gait_event_list):
        """Calculate temporal parameters for each valid Herzer stride.

        Args:
            gait_event_list: Herzer result envelope for the current window.

        Returns:
            A framework mapping whose ``temporal_parameters`` value contains the
            per-foot gaitmap result tables and copied window metadata.
        """
        parameters = self._run_logged_phase(
            "calculate_temporal_parameters",
            gait_event_list,
            lambda: self._temporal_calculator.calculate(gait_event_list),
        )
        return {"temporal_parameters": parameters}

    def reconstruct_stride_trajectories_loop(
        self, preprocessed_imu_window, gait_event_list
    ):
        """Reconstruct per-stride orientation, velocity and position.

        Args:
            preprocessed_imu_window: Native-frequency sensor-frame IMU envelope.
            gait_event_list: Herzer result envelope for the same window.

        Returns:
            A framework mapping containing the trajectory envelope, or its explicit
            lightweight-mode representation.
        """
        trajectories = self._run_logged_phase(
            "reconstruct_stride_trajectories",
            gait_event_list,
            lambda: self._trajectory_reconstructor.reconstruct(
                preprocessed_imu_window, gait_event_list
            ),
        )
        return {"stride_trajectories": trajectories}

    def calculate_spatial_parameters_loop(
        self, gait_event_list, stride_trajectories
    ):
        """Calculate nine spatial metrics for every reconstructed stride.

        Args:
            gait_event_list: Herzer result envelope for the current window.
            stride_trajectories: Full or lightweight trajectory envelope.

        Returns:
            A framework mapping containing the spatial parameter envelope.
        """
        parameters = self._run_logged_phase(
            "calculate_spatial_parameters",
            gait_event_list,
            lambda: self._spatial_calculator.calculate(
                gait_event_list, stride_trajectories
            ),
        )
        return {"spatial_parameters": parameters}

    def aggregate_gait_results_loop(
        self, gait_event_list, temporal_parameters, spatial_parameters
    ):
        """Deduplicate overlap strides and return cumulative trial statistics."""
        result = self._run_logged_phase(
            "aggregate_gait_results",
            gait_event_list,
            lambda: self._result_aggregator.update(
                gait_event_list, temporal_parameters, spatial_parameters
            ),
        )
        return {"gait_result": result}

    def export_gait_result_loop(self, gait_result):
        """Persist changed cumulative results without stopping the application.

        The task graph declares no output because paths are an implementation
        detail, but the exporter retains them for diagnostics and cleanup.
        """
        if gait_result is None or not gait_result.get("updated", False):
            return {}
        self._run_logged_phase(
            "export_gait_result",
            gait_result,
            lambda: self._exporter.export_incremental(gait_result),
        )
        return {}

    # ------------------------------------------------------------------
    # Cleanup methods: release resources after the framework receives STOP.
    # ------------------------------------------------------------------

    def acquire_imu_window_cleanup(self):
        """Stop BLE collection, release its reservation, or close file replay."""
        try:
            if self._acquisition_mode == "file" and self._acquisition is not None:
                self._acquisition.close()
            if self._ble_manager is not None:
                self._ble_manager.stop_collection()
                self._ble_manager = None
            if self._ble_peripherals_announced:
                self._app.notify_peripherals_released(self._imu_names)
                self._ble_peripherals_announced = False
        finally:
            self._close_raw_packet_json()
        return True

    def preprocess_imu_window_cleanup(self):
        """Release the stateless preprocessor and return ``True``."""
        self._preprocessor = None
        return True

    def segment_strides_cleanup(self):
        """Release the BarthDTW instance and return ``True``."""
        if self._stride_segmenter is not None:
            self._stride_segmenter.close()
        self._stride_segmenter = None
        return True

    def detect_gait_events_cleanup(self):
        """Release the Herzer detector and return ``True``."""
        if self._event_detector is not None:
            self._event_detector.close()
        self._event_detector = None
        return True

    def calculate_temporal_parameters_cleanup(self):
        """Release the temporal calculator and return ``True``."""
        if self._temporal_calculator is not None:
            self._temporal_calculator.close()
        self._temporal_calculator = None
        return True

    def reconstruct_stride_trajectories_cleanup(self):
        """Release the trajectory reconstructor and return ``True``."""
        if self._trajectory_reconstructor is not None:
            self._trajectory_reconstructor.close()
        self._trajectory_reconstructor = None
        return True

    def calculate_spatial_parameters_cleanup(self):
        """Release the spatial calculator and return ``True``."""
        if self._spatial_calculator is not None:
            self._spatial_calculator.close()
        self._spatial_calculator = None
        return True

    def aggregate_gait_results_cleanup(self):
        """Release cumulative aggregation state and return ``True``."""
        if self._result_aggregator is not None:
            self._result_aggregator.close()
        self._result_aggregator = None
        return True

    def export_gait_result_cleanup(self):
        """Write the final JSON, release exporter state and return ``True``."""
        if self._exporter is not None:
            self._exporter.export_final()
            self._exporter.close()
        self._exporter = None
        return True

    def cleanup(self):
        """Perform the final application-wide cleanup required by the framework.

        The framework normally invokes every task-specific ``*_cleanup`` method
        first and this global method last. Consequently, during a normal shutdown
        the BLE manager has already been stopped and the peripheral reservation has
        already been released by :meth:`acquire_imu_window_cleanup`.

        This method also acts as a safety net for a partially completed setup. For
        example, if BLE setup fails after starting the manager but before all task
        setup methods finish, the corresponding task cleanup might not have run.
        The guarded checks below release only resources that are still present, so
        calling ``cleanup`` after the normal cleanup sequence is safe and does not
        stop or release the same resource twice.

        Returns:
            ``True`` when no application-wide resource remains allocated. The
            framework interprets this value as successful global cleanup.
        """
        ble_manager = getattr(self, "_ble_manager", None)
        try:
            if ble_manager is not None:
                ble_manager.stop_collection()
        finally:
            self._close_raw_packet_json()
            self._ble_manager = None
            if getattr(self, "_ble_peripherals_announced", False):
                self._app.notify_peripherals_released(self._imu_names)
                self._ble_peripherals_announced = False

        acquisition = getattr(self, "_acquisition", None)
        if (
            getattr(self, "_acquisition_mode", None) == "file"
            and acquisition is not None
        ):
            acquisition.close()
        self._acquisition = None
        return True
