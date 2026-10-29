"""Reusable gaitmap processing, aggregation and export components."""

import json
import logging
import os
from pathlib import Path
import re
import tempfile

import numpy as np
import pandas as pd
from scipy.signal import butter, sosfiltfilt

from .gait_constants import DATASET_SENSOR_MAP, GAITMAP_SENSOR_COLUMNS, prepare_numba_cache

logger = logging.getLogger(__name__)

_prepare_numba_cache = prepare_numba_cache

class ImuWindowPreprocessor:
    """Validate and filter one synchronized two-foot window at its native rate.

    Args:
        lowpass_cutoff_hz: Cutoff of a fourth-order zero-phase Butterworth filter.
            Frequencies above this value are attenuated. A value of 20 Hz is an
            application-level noise-reduction choice, not a requirement imposed by
            gaitmap. It must be validated against the final gait metrics.

    Input contract:
        ``process`` accepts the dictionary returned by the acquisition task. Its
        ``data`` entry must contain synchronized ``left_sensor`` and
        ``right_sensor`` DataFrames with the six columns in
        :data:`GAITMAP_SENSOR_COLUMNS`. Dataset acceleration is already in m/s².
        Live BLE acceleration is in g and is explicitly marked by the acquisition
        task; preprocessing converts it to gaitmap's required m/s². Angular velocity
        is expressed in degree/s in both scenarios.

    Output contract:
        ``process`` returns a new dictionary; it never mutates the acquisition
        window. ``data`` contains filtered DataFrames and ``sampling_rate_hz`` is
        unchanged. File trials therefore remain at 204.8 Hz, while future BLE data
        from the physical IMUs remains at 100 Hz. These are two independent input
        scenarios and are not converted into one another.
    """

    def __init__(self, lowpass_cutoff_hz):
        self.lowpass_cutoff_hz = float(lowpass_cutoff_hz)

    def process(self, raw_window):
        """Preprocess one window and return its gaitmap-ready representation.

        Args:
            raw_window: Acquisition dictionary, or ``None`` after file exhaustion.

        Returns:
            ``None`` if the input is ``None``. Otherwise returns a dictionary with
            the same trial/window metadata and filtered two-foot signals. The
            number of samples and the sampling frequency do not change.

        Raises:
            TypeError: If the window or sensor signals have the wrong container.
            ValueError: If rates, cutoff, sensor names, columns, lengths or numeric
                samples violate the preprocessing contract.
        """
        if raw_window is None:
            return None
        if not isinstance(raw_window, dict):
            raise TypeError("raw_imu_window must be a dictionary or None.")

        try:
            source_rate_hz = float(raw_window["sampling_rate_hz"])
            raw_data = raw_window["data"]
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "raw_imu_window must contain numeric sampling_rate_hz and data."
            ) from error
        if source_rate_hz <= 0:
            raise ValueError("Input sampling_rate_hz must be greater than zero.")
        if not 0 < self.lowpass_cutoff_hz < source_rate_hz / 2:
            raise ValueError(
                "lowpass_cutoff_hz must be greater than zero and below the input "
                f"Nyquist frequency ({source_rate_hz / 2:g} Hz)."
            )
        if not isinstance(raw_data, dict):
            raise TypeError("raw_imu_window['data'] must be a sensor dictionary.")

        required_sensors = set(DATASET_SENSOR_MAP)
        if set(raw_data) != required_sensors:
            raise ValueError(
                "The window must contain exactly left_sensor and right_sensor."
            )

        validated = {}
        for sensor_name in ("left_sensor", "right_sensor"):
            frame = raw_data[sensor_name]
            if not isinstance(frame, pd.DataFrame):
                raise TypeError(f"{sensor_name} must be a pandas DataFrame.")
            if tuple(frame.columns) != GAITMAP_SENSOR_COLUMNS:
                raise ValueError(
                    f"{sensor_name} columns must be {GAITMAP_SENSOR_COLUMNS!r}."
                )
            # Conversion catches object/string columns early. Infinite values are
            # rejected together with NaN because gaitmap requires complete signals.
            values = frame.to_numpy(dtype=float, copy=True)
            if not np.isfinite(values).all():
                raise ValueError(f"{sensor_name} contains NaN or infinite values.")
            # Live acquisition follows the same conversion already used by the
            # respiratory application: raw_acc * (4 g / 32768). Gaitmap expects
            # acceleration in m/s², therefore only BLE windows marked as ``g`` are
            # converted here. Dataset windows already arrive in m/s² and are left
            # unchanged. Gyroscope values are °/s in both scenarios.
            if raw_window.get("acceleration_unit", "m/s^2") == "g":
                values[:, :3] *= 9.80665
            validated[sensor_name] = values

        lengths = {len(values) for values in validated.values()}
        if len(lengths) != 1:
            raise ValueError("Left and right windows must have the same sample count.")
        input_samples = lengths.pop()
        if input_samples == 0:
            raise ValueError("An IMU window cannot be empty.")

        # `sosfiltfilt` applies the filter forward and backward. Consequently it
        # introduces no phase shift, which is essential because a phase delay would
        # move the IC/TC gait events that Herzer will detect later.
        sos = butter(
            4,
            self.lowpass_cutoff_hz,
            btype="lowpass",
            fs=source_rate_hz,
            output="sos",
        )
        # SciPy's default padding for an order-four SOS filter is 15 samples. Report
        # a domain-specific error instead of exposing its cryptic internal message.
        minimum_filter_samples = 16
        if input_samples < minimum_filter_samples:
            raise ValueError(
                f"The window has {input_samples} samples; at least "
                f"{minimum_filter_samples} are required for zero-phase filtering."
            )

        processed_data = {}
        for sensor_name, values in validated.items():
            processed = sosfiltfilt(sos, values, axis=0)
            processed_data[sensor_name] = pd.DataFrame(
                processed,
                columns=GAITMAP_SENSOR_COLUMNS,
                index=pd.RangeIndex(len(processed), name="sample"),
            )

        result = dict(raw_window)
        result.update(
            {
                "data": processed_data,
                "sampling_rate_hz": source_rate_hz,
                "source_sampling_rate_hz": source_rate_hz,
                "source_start_sample": raw_window.get("start_sample"),
                "source_end_sample": raw_window.get("end_sample"),
                "acceleration_unit": "m/s^2",
                "gyroscope_unit": "deg/s",
                "filter_type": "butterworth_zero_phase",
                "filter_order": 4,
                "lowpass_cutoff_hz": self.lowpass_cutoff_hz,
            }
        )
        return result


class BarthDtwStrideSegmenter:
    """Detect left and right stride borders inside a preprocessed window.

    Args:
        max_cost: Maximum normalized DTW cost accepted as a stride. The official
            ``BarthDtw`` default is 4.0. Lower values reject more candidates; higher
            values accept less template-like movements and may increase false
            positives.

    Input contract:
        ``segment`` receives the dictionary produced by
        :class:`ImuWindowPreprocessor`. Its ``data`` is still in gaitmap's sensor
        frame with ``acc_x/.../gyr_z`` columns and carries its native frequency.

    Output contract:
        The returned envelope contains a local ``stride_list`` for direct use by
        Herzer event detection and ``absolute_stride_intervals_s`` for later
        cross-window deduplication. Local ``start`` and ``end`` are sample indexes
        relative to the current window and follow gaitmap's half-open convention
        ``[start, end)``.

    Source:
        This adapter follows the official gaitmap "BarthDtw stride segmentation"
        example: convert sensor-frame data to the foot body frame, instantiate
        ``BarthDtw`` with the original template, and call ``segment`` with the real
        sampling frequency. Framework metadata and absolute-time conversion are
        application-specific additions.
    """

    def __init__(self, max_cost=4.0):
        # Numba compiles the cost-critical helpers used by gaitmap. In constrained
        # deployments its normal user cache might be unavailable; an explicit
        # temporary cache keeps JIT acceleration enabled without persistent SD-card
        # writes. The variable must be defined before importing gaitmap/Numba.
        _prepare_numba_cache()

        try:
            from gaitmap.stride_segmentation import BarthDtw
        except ImportError as error:
            raise RuntimeError(
                "Stride segmentation requires gaitmap and gaitmap_mad 2.6.0. "
                "Install this application's requirements.txt."
            ) from error

        self.max_cost = float(max_cost)
        if not np.isfinite(self.max_cost) or self.max_cost <= 0:
            raise ValueError("barth_max_cost must be a finite number greater than zero.")

        # `resample_template=True` adapts only the stored reference template to the
        # window frequency. It does not resample the acquired IMU signal. Therefore
        # file data stays at 204.8 Hz and BLE data stays at 100 Hz.
        self._algorithm = BarthDtw(
            max_cost=self.max_cost,
            resample_template=True,
        )

    def segment(self, preprocessed_window):
        """Run BarthDTW on both feet and return local and absolute stride borders.

        Args:
            preprocessed_window: Preprocessing envelope, or ``None`` when file
                acquisition is exhausted.

        Returns:
            ``None`` for a ``None`` input. Otherwise a dictionary containing:

            - ``stride_list``: dictionary of gaitmap DataFrames, one per foot;
            - ``absolute_stride_intervals_s``: equivalent start/end times measured
              from the beginning of the complete trial;
            - native ``sampling_rate_hz`` and copied window/trial identifiers.

            A valid processed window can return empty DataFrames when no movement
            matches the template below ``max_cost``; this is not an exception.

        Raises:
            ValueError: If required data, frequency or window time is missing.
        """
        if preprocessed_window is None:
            return None
        try:
            sensor_frame_data = preprocessed_window["data"]
            sampling_rate_hz = float(preprocessed_window["sampling_rate_hz"])
            window_start_time_s = float(preprocessed_window["start_time_s"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "preprocessed_imu_window must contain data, sampling_rate_hz and "
                "start_time_s."
            ) from error
        if sampling_rate_hz <= 0:
            raise ValueError("sampling_rate_hz must be greater than zero.")

        from gaitmap.utils.coordinate_conversion import convert_to_fbf

        # Barth's original template describes the medio-lateral gyroscope axis in
        # the foot body frame. This conversion also mirrors the right foot so the
        # same template and rules can be applied consistently to both sides.
        body_frame_data = convert_to_fbf(
            sensor_frame_data,
            left_like="left_",
            right_like="right_",
        )
        self._algorithm.segment(
            data=body_frame_data,
            sampling_rate_hz=sampling_rate_hz,
        )

        # Copy result tables because gaitmap stores them on the reusable algorithm
        # instance and replaces those attributes on the next window.
        local_stride_lists = {
            sensor: strides.copy()
            for sensor, strides in self._algorithm.stride_list_.items()
        }
        absolute_intervals = {}
        for sensor, strides in local_stride_lists.items():
            intervals = strides[["start", "end"]].astype(float).copy()
            intervals["start"] = (
                intervals["start"] / sampling_rate_hz + window_start_time_s
            )
            intervals["end"] = (
                intervals["end"] / sampling_rate_hz + window_start_time_s
            )
            intervals = intervals.rename(
                columns={"start": "start_time_s", "end": "end_time_s"}
            )
            absolute_intervals[sensor] = intervals

        return {
            "stride_list": local_stride_lists,
            "absolute_stride_intervals_s": absolute_intervals,
            "sampling_rate_hz": sampling_rate_hz,
            "window_index": preprocessed_window.get("window_index"),
            "window_start_time_s": window_start_time_s,
            "is_final_window": preprocessed_window.get("is_final_window", False),
            "participant": preprocessed_window.get("participant"),
            "trial": preprocessed_window.get("trial"),
        }

    def close(self):
        """Release the gaitmap algorithm instance and return ``True``."""
        self._algorithm = None
        return True


class HerzerGaitEventDetector:
    """Detect IC, TC and minimal-velocity events inside Barth-segmented strides.

    The implementation follows the official gaitmap Herzer example. Sensor-frame
    IMU data is converted to the foot body frame, then ``HerzerEventDetection`` is
    called with the local Barth stride borders and the window's native sampling
    rate. Default Herzer parameters are deliberately retained, including its own
    first-order 4 Hz low-pass filter used only for IC detection.

    Two official outputs are preserved:

    - ``annotated_original_event_list`` keeps the original Barth start/end borders
      and adds ``ic``, ``tc`` and ``min_vel``;
    - ``min_vel_event_list`` shifts stride borders to consecutive minimal-velocity
      events and adds ``pre_ic``. This is the representation required by gaitmap's
      stride-level trajectory reconstruction and temporal parameter calculation.

    Event values remain local sample indexes relative to the current window. They
    are not converted to absolute time here; that belongs to the later aggregator,
    which also removes duplicate events from overlapping windows.
    """

    _ANNOTATED_COLUMNS = ("start", "end", "ic", "tc", "min_vel")
    _MIN_VEL_COLUMNS = ("start", "end", "ic", "tc", "min_vel", "pre_ic")

    def __init__(self):
        # Herzer can be constructed independently from Barth in distributed task
        # configurations, so it must not rely on another task preparing Numba first.
        _prepare_numba_cache()
        try:
            from gaitmap.event_detection import HerzerEventDetection
        except ImportError as error:
            raise RuntimeError(
                "Gait-event detection requires gaitmap 2.6.0. Install this "
                "application's requirements.txt."
            ) from error

        # No parameters are overridden: the defaults shown in the official example
        # are the reproducible starting point and can be tuned only after validation.
        self._algorithm = HerzerEventDetection()

    @staticmethod
    def _empty_event_list(columns):
        """Return a typed, gaitmap-shaped empty event table for a quiet sensor."""
        frame = pd.DataFrame(columns=columns, dtype=float)
        frame.index = pd.Index([], name="s_id", dtype=int)
        return frame

    def detect(self, preprocessed_window, segmented_stride_result):
        """Detect events and return both official Herzer event-list variants.

        Args:
            preprocessed_window: Envelope produced by ``ImuWindowPreprocessor``.
                It supplies sensor-frame signals and the native sampling frequency.
            segmented_stride_result: Envelope produced by
                ``BarthDtwStrideSegmenter``. Its ``stride_list`` entries contain
                window-local, half-open start/end sample borders.

        Returns:
            ``None`` when either upstream value is ``None``. Otherwise a dictionary
            containing ``annotated_original_event_list``, ``min_vel_event_list``,
            sampling rate and copied window/trial metadata. Sensors without any
            Barth candidates receive empty DataFrames instead of causing an error.

        Raises:
            ValueError: If the two envelopes are malformed, disagree on sampling
                frequency, or do not describe exactly the same two sensors.
        """
        if preprocessed_window is None or segmented_stride_result is None:
            return None
        try:
            sensor_frame_data = preprocessed_window["data"]
            sampling_rate_hz = float(preprocessed_window["sampling_rate_hz"])
            stride_lists = segmented_stride_result["stride_list"]
            segmented_rate_hz = float(segmented_stride_result["sampling_rate_hz"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "Herzer inputs must contain data, stride_list and sampling rates."
            ) from error
        if sampling_rate_hz <= 0 or not np.isclose(
            sampling_rate_hz, segmented_rate_hz
        ):
            raise ValueError(
                "Preprocessed data and segmented strides must have the same "
                "positive sampling frequency."
            )
        expected_sensors = {"left_sensor", "right_sensor"}
        if set(sensor_frame_data) != expected_sensors or set(stride_lists) != expected_sensors:
            raise ValueError(
                "Herzer requires matching left_sensor and right_sensor inputs."
            )

        from gaitmap.utils.coordinate_conversion import convert_to_fbf

        body_frame_data = convert_to_fbf(
            sensor_frame_data,
            left_like="left_",
            right_like="right_",
        )

        # Herzer expects at least one stride. Excluding empty sensors before calling
        # gaitmap makes final/quiet windows a normal empty result, not an exception.
        active_stride_lists = {
            sensor: strides
            for sensor, strides in stride_lists.items()
            if not strides.empty
        }
        annotated = {
            sensor: self._empty_event_list(self._ANNOTATED_COLUMNS)
            for sensor in expected_sensors
        }
        min_vel = {
            sensor: self._empty_event_list(self._MIN_VEL_COLUMNS)
            for sensor in expected_sensors
        }
        if active_stride_lists:
            active_data = {
                sensor: body_frame_data[sensor] for sensor in active_stride_lists
            }
            self._algorithm.detect(
                data=active_data,
                stride_list=active_stride_lists,
                sampling_rate_hz=sampling_rate_hz,
            )
            annotated.update(
                {
                    sensor: events.copy()
                    for sensor, events in self._algorithm.annotated_original_event_list_.items()
                }
            )
            min_vel.update(
                {
                    sensor: events.copy()
                    for sensor, events in self._algorithm.min_vel_event_list_.items()
                }
            )

        return {
            "annotated_original_event_list": annotated,
            "min_vel_event_list": min_vel,
            "sampling_rate_hz": sampling_rate_hz,
            "window_index": segmented_stride_result.get("window_index"),
            "window_start_time_s": segmented_stride_result.get(
                "window_start_time_s"
            ),
            "window_end_time_s": preprocessed_window.get("end_time_s"),
            "is_final_window": segmented_stride_result.get(
                "is_final_window", False
            ),
            "participant": segmented_stride_result.get("participant"),
            "trial": segmented_stride_result.get("trial"),
        }

    def close(self):
        """Release the Herzer algorithm instance and return ``True``."""
        self._algorithm = None
        return True


class TemporalGaitParameterCalculator:
    """Calculate official gaitmap temporal metrics for every min-velocity stride.

    The input must be Herzer's ``min_vel_event_list`` representation. For each
    retained stride gaitmap calculates exactly three parameters:

    - ``stride_time``: time from ``pre_ic`` to ``ic``;
    - ``swing_time``: time from ``tc`` to ``ic``;
    - ``stance_time``: ``stride_time - swing_time``.

    All three results are expressed in seconds. The calculation divides sample
    differences by the native sampling frequency carried by the event envelope, so
    it works unchanged with 204.8 Hz dataset files and future 100 Hz BLE windows.
    This task does not calculate trial averages, cadence, asymmetry or absolute
    times; those operations belong to the later cross-window aggregator.
    """

    _REQUIRED_EVENT_COLUMNS = {"start", "end", "ic", "tc", "min_vel", "pre_ic"}

    def __init__(self):
        _prepare_numba_cache()
        try:
            from gaitmap.parameters import TemporalParameterCalculation
        except ImportError as error:
            raise RuntimeError(
                "Temporal gait parameters require gaitmap 2.6.0. Install this "
                "application's requirements.txt."
            ) from error

        # Herzer returns min_vel strides, so declare the type explicitly even though
        # it is also gaitmap's default. This protects the formulas from an accidental
        # future change to IC-to-IC input without a corresponding code review.
        self._algorithm = TemporalParameterCalculation(expected_stride_type="min_vel")

    def calculate(self, gait_event_result):
        """Calculate stride, swing and stance times for one two-foot window.

        Args:
            gait_event_result: Envelope returned by
                :class:`HerzerGaitEventDetector`, or ``None`` at end-of-file.

        Returns:
            ``None`` for a ``None`` input. Otherwise a dictionary containing:

            - ``parameters``: per-foot DataFrames with machine-friendly columns
              ``stride_time``, ``swing_time`` and ``stance_time`` in seconds;
            - ``parameters_pretty``: the same values with units in column labels;
            - native sampling frequency and copied window/trial metadata.

            Empty event lists produce empty parameter tables with the same schema.

        Raises:
            ValueError: If frequency, sensors, event columns or values are invalid.
        """
        if gait_event_result is None:
            return None
        try:
            event_lists = gait_event_result["min_vel_event_list"]
            sampling_rate_hz = float(gait_event_result["sampling_rate_hz"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "gait_event_list must contain min_vel_event_list and a numeric "
                "sampling_rate_hz."
            ) from error
        if not np.isfinite(sampling_rate_hz) or sampling_rate_hz <= 0:
            raise ValueError("sampling_rate_hz must be a finite positive number.")
        if not isinstance(event_lists, dict) or set(event_lists) != {
            "left_sensor",
            "right_sensor",
        }:
            raise ValueError(
                "Temporal calculation requires left_sensor and right_sensor events."
            )

        validated_events = {}
        for sensor in ("left_sensor", "right_sensor"):
            events = event_lists[sensor]
            if not isinstance(events, pd.DataFrame):
                raise ValueError(f"{sensor} event list must be a pandas DataFrame.")
            missing = self._REQUIRED_EVENT_COLUMNS.difference(events.columns)
            if missing:
                raise ValueError(
                    f"{sensor} event list is missing columns: {sorted(missing)}."
                )
            numeric_events = events.loc[:, list(self._REQUIRED_EVENT_COLUMNS)].apply(
                pd.to_numeric, errors="coerce"
            )
            if not numeric_events.empty and not np.isfinite(
                numeric_events.to_numpy(dtype=float)
            ).all():
                raise ValueError(f"{sensor} event list contains invalid values.")
            # Preserve the official column order and any extra gaitmap columns while
            # ensuring the algorithm receives a private copy it may safely process.
            validated_events[sensor] = events.copy()

        self._algorithm.calculate(
            stride_event_list=validated_events,
            sampling_rate_hz=sampling_rate_hz,
        )
        parameters = {
            sensor: values.copy()
            for sensor, values in self._algorithm.parameters_.items()
        }
        parameters_pretty = {
            sensor: values.copy()
            for sensor, values in self._algorithm.parameters_pretty_.items()
        }

        return {
            "parameters": parameters,
            "parameters_pretty": parameters_pretty,
            "sampling_rate_hz": sampling_rate_hz,
            "window_index": gait_event_result.get("window_index"),
            "window_start_time_s": gait_event_result.get("window_start_time_s"),
            "is_final_window": gait_event_result.get("is_final_window", False),
            "participant": gait_event_result.get("participant"),
            "trial": gait_event_result.get("trial"),
        }

    def close(self):
        """Release the gaitmap calculator and return ``True``."""
        self._algorithm = None
        return True


class StrideTrajectoryReconstructor:
    """Reconstruct orientation and position independently per stride.

    Full mode uses gaitmap's official default ``StrideLevelTrajectory`` pipeline:
    ``SimpleGyroIntegration`` estimates orientation and
    ``ForwardBackwardIntegration`` estimates velocity and position. Each Herzer
    stride begins at a minimal-velocity event, allowing gaitmap to initialize its
    orientation from gravity and its position/velocity from zero.

    No magnetometer is required by these default methods. Orientation is integrated
    only over one stride, while forward/backward integration reduces accumulated
    velocity drift under the assumption that the foot is stationary at both stride
    boundaries. Gaitmap necessarily calculates velocity internally while integrating
    position, but this wrapper does not copy or expose it because the following
    spatial calculation does not consume it. Results are relative to each individual
    stride, not a continuous global walking path.

    In lightweight mode calculation is skipped completely. The task still returns
    a metadata envelope with ``enabled=False`` so the downstream spatial task can
    distinguish an intentional skip from missing or malformed data.
    """

    def __init__(self, lightweight_mode=False):
        self.lightweight_mode = bool(lightweight_mode)
        self._algorithm = None
        if not self.lightweight_mode:
            _prepare_numba_cache()
            try:
                from gaitmap.trajectory_reconstruction import StrideLevelTrajectory
            except ImportError as error:
                raise RuntimeError(
                    "Stride trajectory reconstruction requires gaitmap 2.6.0. "
                    "Install this application's requirements.txt."
                ) from error

            # Keeping the constructor defaults makes this implementation directly
            # comparable with the official stride-level and MaD pipeline examples.
            self._algorithm = StrideLevelTrajectory()

    def reconstruct(self, preprocessed_window, gait_event_result):
        """Estimate per-stride trajectories or return a disabled-mode envelope.

        Args:
            preprocessed_window: Native-frequency sensor-frame IMU envelope.
            gait_event_result: Herzer envelope containing ``min_vel_event_list``.

        Returns:
            ``None`` if either upstream input is ``None``. Otherwise returns a
            dictionary with ``enabled`` and copied window metadata. In full mode it
            additionally contains:

            - ``orientation``: quaternion columns ``q_x, q_y, q_z, q_w``;
            - ``position``: ``pos_x, pos_y, pos_z`` in metres.

            Each per-foot result uses a ``(s_id, sample)`` MultiIndex. A stride with
            N input samples has N+1 trajectory samples because gaitmap includes the
            initial state. Empty event lists produce well-formed empty tables.

        Raises:
            ValueError: If data and events disagree on sensors or native frequency.
        """
        if preprocessed_window is None or gait_event_result is None:
            return None
        try:
            data = preprocessed_window["data"]
            data_rate_hz = float(preprocessed_window["sampling_rate_hz"])
            event_lists = gait_event_result["min_vel_event_list"]
            event_rate_hz = float(gait_event_result["sampling_rate_hz"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "Trajectory inputs must contain data, min_vel_event_list and "
                "sampling rates."
            ) from error

        expected_sensors = {"left_sensor", "right_sensor"}
        if set(data) != expected_sensors or set(event_lists) != expected_sensors:
            raise ValueError(
                "Trajectory reconstruction requires matching left_sensor and "
                "right_sensor inputs."
            )
        if (
            not np.isfinite(data_rate_hz)
            or data_rate_hz <= 0
            or not np.isclose(data_rate_hz, event_rate_hz)
        ):
            raise ValueError(
                "Trajectory data and events must have the same positive native "
                "sampling frequency."
            )

        result = {
            "enabled": not self.lightweight_mode,
            "sampling_rate_hz": data_rate_hz,
            "window_index": gait_event_result.get("window_index"),
            "window_start_time_s": gait_event_result.get("window_start_time_s"),
            "is_final_window": gait_event_result.get("is_final_window", False),
            "participant": gait_event_result.get("participant"),
            "trial": gait_event_result.get("trial"),
        }
        if self.lightweight_mode:
            result.update({"orientation": None, "position": None})
            return result

        # StrideLevelTrajectory expects the gaitmap sensor frame used by the loader,
        # not the mirrored foot body frame required by Barth and Herzer.
        self._algorithm.estimate(
            data={sensor: frame.copy() for sensor, frame in data.items()},
            stride_event_list={
                sensor: events.copy() for sensor, events in event_lists.items()
            },
            sampling_rate_hz=data_rate_hz,
        )
        orientation = {
            sensor: values.copy()
            for sensor, values in self._algorithm.orientation_.items()
        }
        position = {
            sensor: values.copy()
            for sensor, values in self._algorithm.position_.items()
        }
        for result_name, per_sensor in (
            ("orientation", orientation),
            ("position", position),
        ):
            for sensor, values in per_sensor.items():
                if not values.empty and not np.isfinite(
                    values.to_numpy(dtype=float)
                ).all():
                    raise ValueError(
                        f"Reconstructed {result_name} for {sensor} contains "
                        "NaN or infinite values."
                    )

        result.update(
            {
                "orientation": orientation,
                "position": position,
            }
        )
        return result

    def close(self):
        """Release trajectory methods and their last results, then return ``True``."""
        self._algorithm = None
        return True


class SpatialGaitParameterCalculator:
    """Calculate gaitmap's spatial metrics from events and stride trajectories.

    Full mode uses ``SpatialParameterCalculation(expected_stride_type="min_vel")``
    with ``calculate_only=None``, meaning all nine official parameters are produced:
    stride length, gait velocity, arc length, IC and TC angles, turning angle,
    maximum orientation change, maximum sensor lift and maximum lateral excursion.

    The calculator needs Herzer events plus position and orientation. Velocity is
    intentionally absent because gaitmap does not require it for this step. In
    lightweight mode trajectory reconstruction was skipped, so this class returns
    an explicit disabled result without running any spatial calculations.
    """

    def __init__(self, lightweight_mode=False):
        self.lightweight_mode = bool(lightweight_mode)
        self._algorithm = None
        if not self.lightweight_mode:
            _prepare_numba_cache()
            try:
                from gaitmap.parameters import SpatialParameterCalculation
            except ImportError as error:
                raise RuntimeError(
                    "Spatial gait parameters require gaitmap 2.6.0. Install this "
                    "application's requirements.txt."
                ) from error
            self._algorithm = SpatialParameterCalculation(
                calculate_only=None,
                expected_stride_type="min_vel",
            )

    def calculate(self, gait_event_result, trajectory_result):
        """Return all per-stride spatial parameters or a lightweight bypass.

        Args:
            gait_event_result: Herzer envelope with ``min_vel_event_list``.
            trajectory_result: Envelope from
                :class:`StrideTrajectoryReconstructor`, containing position and
                orientation in full mode.

        Returns:
            ``None`` if either upstream input is ``None``. Otherwise returns an
            envelope with ``enabled`` and window metadata. Full mode adds:

            - ``parameters``: machine-friendly per-foot parameter DataFrames;
            - ``parameters_pretty``: the same values with names and units intended
              for presentation.

            The internal ``sole_angle_course_`` diagnostic is not copied because
            no downstream task needs the complete per-sample angle course.

        Raises:
            ValueError: If events and trajectories are missing, inconsistent or
                contain non-finite calculated parameter values.
        """
        if gait_event_result is None or trajectory_result is None:
            return None
        try:
            event_lists = gait_event_result["min_vel_event_list"]
            event_rate_hz = float(gait_event_result["sampling_rate_hz"])
            trajectory_rate_hz = float(trajectory_result["sampling_rate_hz"])
            trajectory_enabled = bool(trajectory_result["enabled"])
        except (KeyError, TypeError, ValueError) as error:
            raise ValueError(
                "Spatial inputs must contain events, enabled state and sampling "
                "rates."
            ) from error

        if (
            not np.isfinite(event_rate_hz)
            or event_rate_hz <= 0
            or not np.isclose(event_rate_hz, trajectory_rate_hz)
        ):
            raise ValueError(
                "Spatial events and trajectories must have the same positive "
                "native sampling frequency."
            )
        if set(event_lists) != {"left_sensor", "right_sensor"}:
            raise ValueError(
                "Spatial calculation requires left_sensor and right_sensor events."
            )

        result = {
            "enabled": not self.lightweight_mode,
            "sampling_rate_hz": event_rate_hz,
            "window_index": gait_event_result.get("window_index"),
            "window_start_time_s": gait_event_result.get("window_start_time_s"),
            "is_final_window": gait_event_result.get("is_final_window", False),
            "participant": gait_event_result.get("participant"),
            "trial": gait_event_result.get("trial"),
        }
        if self.lightweight_mode:
            if trajectory_enabled:
                raise ValueError(
                    "Lightweight spatial mode received an enabled trajectory result."
                )
            result.update({"parameters": None, "parameters_pretty": None})
            return result
        if not trajectory_enabled:
            raise ValueError("Full spatial mode requires reconstructed trajectories.")

        try:
            positions = trajectory_result["position"]
            orientations = trajectory_result["orientation"]
        except KeyError as error:
            raise ValueError(
                "Full spatial mode requires position and orientation trajectories."
            ) from error
        expected_sensors = {"left_sensor", "right_sensor"}
        if set(positions) != expected_sensors or set(orientations) != expected_sensors:
            raise ValueError(
                "Position and orientation must contain both foot sensors."
            )

        self._algorithm.calculate(
            stride_event_list={
                sensor: events.copy() for sensor, events in event_lists.items()
            },
            positions={sensor: values.copy() for sensor, values in positions.items()},
            orientations={
                sensor: values.copy() for sensor, values in orientations.items()
            },
            sampling_rate_hz=event_rate_hz,
        )
        parameters = {
            sensor: values.copy()
            for sensor, values in self._algorithm.parameters_.items()
        }
        parameters_pretty = {
            sensor: values.copy()
            for sensor, values in self._algorithm.parameters_pretty_.items()
        }
        for sensor, values in parameters.items():
            if not values.empty and not np.isfinite(
                values.to_numpy(dtype=float)
            ).all():
                raise ValueError(
                    f"Spatial parameters for {sensor} contain NaN or infinite values."
                )

        result.update(
            {
                "parameters": parameters,
                "parameters_pretty": parameters_pretty,
            }
        )
        return result

    def close(self):
        """Release the spatial calculator and return ``True``."""
        self._algorithm = None
        return True


class GaitResultAggregator:
    """Deduplicate overlapping windows and maintain trial-wide gait statistics.

    Duplicate identity is based on absolute IC time. Two same-foot strides whose
    IC values differ by at most ``deduplication_tolerance_s`` are treated as the
    same physical stride. If both windows contain it, the observation with the IC
    farthest from either window edge is retained because filtering and event
    detection are less reliable at window boundaries.

    The class stores one combined temporal/spatial row per unique stride. It does
    not invent new clinical metrics: summaries contain count, mean, sample standard
    deviation, median, minimum and maximum of the official gaitmap parameters.
    """

    def __init__(self, deduplication_tolerance_s=0.1, minimum_complete_strides=3):
        self.deduplication_tolerance_s = float(deduplication_tolerance_s)
        self.minimum_complete_strides = int(minimum_complete_strides)
        if not np.isfinite(self.deduplication_tolerance_s) or not (
            0 < self.deduplication_tolerance_s < 0.5
        ):
            raise ValueError("Deduplication tolerance must be between 0 and 0.5 s.")
        if self.minimum_complete_strides <= 0:
            raise ValueError("minimum_complete_strides must be greater than zero.")
        self._records = {"left_sensor": [], "right_sensor": []}
        self._participant = None
        self._trial = None
        self._last_window_index = None

    @staticmethod
    def _summary(frame):
        """Return JSON-friendly descriptive statistics for numeric metric columns."""
        summary = {}
        excluded = {"absolute_ic_time_s", "window_edge_margin_s", "window_index"}
        for column in frame.columns:
            if column in excluded:
                continue
            values = pd.to_numeric(frame[column], errors="coerce").dropna()
            if values.empty:
                continue
            std = values.std(ddof=1)
            summary[column] = {
                "count": int(values.count()),
                "mean": float(values.mean()),
                "std": None if pd.isna(std) else float(std),
                "median": float(values.median()),
                "min": float(values.min()),
                "max": float(values.max()),
            }
        return summary

    def _snapshot(self, updated):
        """Build a safe cumulative snapshot without exposing mutable state."""
        per_sensor = {}
        counts = {}
        for sensor, records in self._records.items():
            ordered = sorted(records, key=lambda record: record["absolute_ic_time_s"])
            frame = pd.DataFrame(ordered)
            if not frame.empty:
                frame.index = pd.RangeIndex(len(frame), name="trial_stride_id")
            counts[sensor] = len(frame)
            per_sensor[sensor] = {
                "stride_count": len(frame),
                "parameters": frame,
                "summary": self._summary(frame),
            }
        minimum_met = all(
            count >= self.minimum_complete_strides for count in counts.values()
        )
        return {
            "updated": updated,
            "window_index": self._last_window_index,
            "participant": self._participant,
            "trial": self._trial,
            "per_sensor": per_sensor,
            "bilateral": {
                "left_stride_count": counts["left_sensor"],
                "right_stride_count": counts["right_sensor"],
                "total_stride_count": sum(counts.values()),
                "minimum_complete_strides_per_foot": self.minimum_complete_strides,
                "minimum_complete_strides_met": minimum_met,
            },
        }

    def update(self, gait_event_result, temporal_result, spatial_result):
        """Merge one window and return the complete deduplicated trial snapshot.

        Args:
            gait_event_result: Herzer envelope providing local IC samples.
            temporal_result: Per-stride temporal parameter envelope.
            spatial_result: Full or lightweight spatial parameter envelope.

        Returns:
            A cumulative snapshot. If upstream values are ``None`` at file EOF, the
            previous snapshot is returned with ``updated=False``.
        """
        if gait_event_result is None or temporal_result is None or spatial_result is None:
            return self._snapshot(updated=False)
        sampling_rate_hz = float(gait_event_result["sampling_rate_hz"])
        window_start_s = float(gait_event_result["window_start_time_s"])
        window_end_s = float(gait_event_result["window_end_time_s"])
        window_index = gait_event_result.get("window_index")
        self._last_window_index = window_index
        self._participant = gait_event_result.get("participant")
        self._trial = gait_event_result.get("trial")
        temporal_tables = temporal_result["parameters"]
        spatial_tables = spatial_result.get("parameters")

        for sensor in ("left_sensor", "right_sensor"):
            events = gait_event_result["min_vel_event_list"][sensor]
            for stride_id, event in events.iterrows():
                if stride_id not in temporal_tables[sensor].index:
                    continue
                absolute_ic = window_start_s + float(event["ic"]) / sampling_rate_hz
                local_ic_s = float(event["ic"]) / sampling_rate_hz
                window_duration_s = window_end_s - window_start_s
                edge_margin = min(
                    local_ic_s, max(0.0, window_duration_s - local_ic_s)
                )
                record = {
                    "absolute_ic_time_s": absolute_ic,
                    "window_edge_margin_s": edge_margin,
                    "window_index": window_index,
                    **temporal_tables[sensor].loc[stride_id].to_dict(),
                }
                if spatial_tables is not None and stride_id in spatial_tables[sensor].index:
                    record.update(spatial_tables[sensor].loc[stride_id].to_dict())

                duplicates = [
                    index
                    for index, existing in enumerate(self._records[sensor])
                    if abs(existing["absolute_ic_time_s"] - absolute_ic)
                    <= self.deduplication_tolerance_s
                ]
                if not duplicates:
                    self._records[sensor].append(record)
                else:
                    index = duplicates[0]
                    if edge_margin > self._records[sensor][index]["window_edge_margin_s"]:
                        self._records[sensor][index] = record
        return self._snapshot(updated=True)

    def close(self):
        """Release cumulative records and return ``True``."""
        self._records = {"left_sensor": [], "right_sensor": []}
        return True


class GaitResultExporter:
    """Persist cumulative gait results as atomic JSON and per-foot CSV files.

    Args:
        output_path: Destination directory. It is created during initialization.
        subject_id: Fallback identifier used before a file result supplies its real
            participant identifier.
        trial_id: Fallback trial identifier used in output filenames.

    Incremental exports overwrite ``*_latest.json`` and the two per-foot CSV files
    only when the aggregator reports ``updated=True``. Cleanup writes a separate
    ``*_final.json`` from the most recent snapshot. Each file is first written in
    the destination directory and then atomically replaced with ``os.replace``;
    therefore power loss cannot expose a partially written destination file.
    """

    def __init__(self, output_path, subject_id, trial_id):
        self.output_path = Path(output_path).expanduser().resolve()
        self.output_path.mkdir(parents=True, exist_ok=True)
        self.subject_id = str(subject_id)
        self.trial_id = str(trial_id)
        self._last_result = None
        self._last_paths = {}

    @staticmethod
    def _safe_filename_token(value):
        """Return a portable filename token without allowing path traversal."""
        token = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value).strip())
        token = token.strip("._")
        return token or "unknown"

    @classmethod
    def _json_safe(cls, value):
        """Recursively convert pandas/NumPy objects into strict JSON values."""
        if isinstance(value, pd.DataFrame):
            # Reset the index so trial_stride_id is preserved in the JSON records.
            return cls._json_safe(value.reset_index().to_dict(orient="records"))
        if isinstance(value, pd.Series):
            return cls._json_safe(value.to_dict())
        if isinstance(value, dict):
            return {str(key): cls._json_safe(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [cls._json_safe(item) for item in value]
        if isinstance(value, np.generic):
            value = value.item()
        if isinstance(value, float) and not np.isfinite(value):
            return None
        if value is None or isinstance(value, (str, int, float, bool)):
            return value
        return str(value)

    @staticmethod
    def _atomic_text_write(path, text):
        """Atomically replace ``path`` with UTF-8 ``text``."""
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            temporary.write_text(text, encoding="utf-8")
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    @staticmethod
    def _atomic_csv_write(path, frame):
        """Atomically replace ``path`` with a pandas DataFrame encoded as CSV."""
        temporary = path.with_name(f".{path.name}.tmp")
        try:
            frame.to_csv(temporary, index=True)
            os.replace(temporary, path)
        finally:
            if temporary.exists():
                temporary.unlink()

    def _base_name(self, result):
        """Build a deterministic participant/trial basename for one snapshot."""
        participant = result.get("participant") or self.subject_id
        trial = result.get("trial") or self.trial_id
        return (
            f"{self._safe_filename_token(participant)}_"
            f"{self._safe_filename_token(trial)}"
        )

    def export_incremental(self, gait_result):
        """Write the latest snapshot and return the paths that were updated.

        Args:
            gait_result: Cumulative dictionary returned by
                :class:`GaitResultAggregator`.

        Returns:
            An empty dictionary for ``None`` or unchanged results. For an updated
            result, returns ``json``, ``left_sensor_csv`` and ``right_sensor_csv``
            as absolute path strings.
        """
        if gait_result is None or not gait_result.get("updated", False):
            return {}
        self._last_result = gait_result
        base = self._base_name(gait_result)
        json_path = self.output_path / f"{base}_latest.json"
        json_payload = json.dumps(
            self._json_safe(gait_result),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        self._atomic_text_write(json_path, json_payload + "\n")

        paths = {"json": str(json_path)}
        for sensor in ("left_sensor", "right_sensor"):
            csv_path = self.output_path / f"{base}_{sensor}.csv"
            frame = gait_result["per_sensor"][sensor]["parameters"]
            self._atomic_csv_write(csv_path, frame)
            paths[f"{sensor}_csv"] = str(csv_path)
        self._last_paths = paths
        return dict(paths)

    def export_final(self):
        """Write and return the final JSON path, or ``None`` if no data arrived."""
        if self._last_result is None:
            return None
        base = self._base_name(self._last_result)
        final_path = self.output_path / f"{base}_final.json"
        final_result = dict(self._last_result)
        # `updated` describes an incremental loop iteration and has no meaning in
        # the immutable final artifact.
        final_result["updated"] = False
        payload = json.dumps(
            self._json_safe(final_result),
            ensure_ascii=False,
            allow_nan=False,
            indent=2,
            sort_keys=True,
        )
        self._atomic_text_write(final_path, payload + "\n")
        return str(final_path)

    def close(self):
        """Release the retained snapshot after final export and return ``True``."""
        self._last_result = None
        return True


