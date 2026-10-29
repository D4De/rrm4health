"""Dataset-backed IMU window source for bilateral gait analysis."""

import logging
from pathlib import Path
import time

import pandas as pd

from .gait_constants import DATASET_SENSOR_MAP, GAITMAP_SENSOR_COLUMNS

logger = logging.getLogger(__name__)

class SensorPositionDatasetFileSource:
    """Load one real dataset trial and expose it as overlapping IMU windows.

    Valid values for SensorPositionComparison2019
    ------------------------------------------------
    The reduced dataset bundled with this application contains these participants::

        4d91, 5237, 8873, cb3d

    The original upstream dataset contains additional participants, but they were
    deliberately omitted to keep the application package reasonably small. If the
    complete archive is restored, the official loader can expose them again.

    ``trial`` must be one of::

        slow_10, normal_10, fast_10,
        slow_20, normal_20, fast_20,
        long

    The suffixes ``10`` and ``20`` refer to walking-path length in metres, not to
    trial duration in seconds. The short trials contain repeated walks at slow,
    normal or fast speed. ``long`` is continuous walking for about five minutes.

    Ready-to-use short-trial example::

        source = SensorPositionDatasetFileSource(
            dataset_path="dataset/SensorPositionComparison2019-v1.0.0-beta",
            participant="4d91",
            trial="normal_10",
            window_duration_s=20,
            window_overlap_s=2,
        ).open()

    Ready-to-use long-trial example using the same participant::

        source = SensorPositionDatasetFileSource(
            dataset_path="dataset/SensorPositionComparison2019-v1.0.0-beta",
            participant="4d91",
            trial="long",
            window_duration_s=20,
            window_overlap_s=2,
        ).open()

    ``4d91`` is used only as a valid reproducible example; it is not a preferred
    or medically representative participant. Any identifier in the list above can
    be selected. When the application is started through its descriptor, the same
    values go into ``input_path``, ``subject_id`` and ``trial_id`` respectively.

    Args:
        dataset_path: Root of the extracted SensorPositionComparison2019 archive.
            It is the directory containing ``data/``, ``calibrations/`` and the
            upstream ``README.md``.
        participant: Participant directory to select, for example ``"4d91"``.
            The invalid first recording ``"6dbe"`` is deliberately rejected by
            the official loader; the valid replacement is ``"6dbe_2"``.
        trial: Test to select, such as ``"normal_10"`` or ``"long"``.
        window_duration_s: Requested length of every analysis window in seconds.
        window_overlap_s: Amount repeated between consecutive windows. Repetition
            is needed so strides crossing a boundary can later be recovered.
        File windows always become available according to the dataset's original
        204.8 Hz timing. Timing never changes or resamples the recorded data.

    The official ``gaitmap-datasets`` loader performs the difficult operations:
    decoding the NilsPod binary streams, synchronising devices, applying their
    calibrations, slicing the selected test and rotating sensors into a common
    gaitmap-compatible coordinate system. This class only selects the two instep
    sensors and divides the resulting trial into windows.

    ``next_window`` returns a dictionary, not a bare DataFrame. Besides the two
    signals it reports sample/time boundaries and whether this is the final window;
    downstream tasks can therefore deduplicate strides in overlap regions without
    guessing where a window came from.
    """

    sampling_rate_hz = 204.8

    def __init__(
        self,
        dataset_path,
        participant,
        trial,
        window_duration_s,
        window_overlap_s,
    ):
        self.dataset_path = Path(dataset_path).expanduser().resolve()
        self.participant = str(participant).strip()
        self.trial = str(trial).strip()
        self.window_duration_s = float(window_duration_s)
        self.window_overlap_s = float(window_overlap_s)
        self._data = None
        self._next_start_sample = 0
        self._window_index = 0
        self._playback_started_at = None
        self._window_phase_started_at = None

    def open(self):
        """Decode and retain the selected trial.

        Returns:
            The source object itself. Returning ``self`` makes setup convenient and
            mirrors the convention used by file-like Python objects.

        Raises:
            FileNotFoundError: If ``dataset_path`` is not an extracted dataset.
            RuntimeError: If the optional official loader is not installed.
            ValueError: If participant/trial do not exist, either instep sensor is
                absent, columns are unexpected, or the trial has no samples.
        """
        required_entries = (self.dataset_path / "data", self.dataset_path / "calibrations")
        if not all(entry.is_dir() for entry in required_entries):
            raise FileNotFoundError(
                f"{self.dataset_path} is not a SensorPositionComparison2019 root: "
                "expected the data/ and calibrations/ directories."
            )

        try:
            from gaitmap_datasets.sensor_position_comparison_2019 import (
                SensorPositionComparison2019Mocap,
            )
        except ImportError as error:
            raise RuntimeError(
                "File mode for the NilsPod dataset requires gaitmap-datasets. "
                "Install Framework/applications/BilateralGaitAnalysis/requirements.txt."
            ) from error

        dataset = SensorPositionComparison2019Mocap(
            data_folder=self.dataset_path,
            # Alignment is essential: raw units were mounted at different
            # orientations. True converts them to the dataset's common foot frame.
            align_data=True,
            # Disk caching is intentionally left disabled. A cached complete session
            # is large and would be undesirable on a Raspberry Pi SD card.
        )

        available = dataset.index
        matching = available[
            (available["participant"] == self.participant)
            & (available["test"] == self.trial)
        ]
        if matching.empty:
            participant_trials = available.loc[
                available["participant"] == self.participant, "test"
            ].tolist()
            if participant_trials:
                detail = f"available trials: {', '.join(participant_trials)}"
            else:
                participants = ", ".join(sorted(available["participant"].unique()))
                detail = f"available participants: {participants}"
            raise ValueError(
                f"Unknown dataset selection {self.participant!r}/{self.trial!r}; {detail}."
            )

        # A one-row tpcp subset is required before accessing `.data`; otherwise the
        # dataset cannot know which participant/test should be decoded.
        trial_data = dataset.get_subset(
            participant=self.participant, test=self.trial
        )[0].data

        selected = {}
        for output_name, dataset_name in DATASET_SENSOR_MAP.items():
            if dataset_name not in trial_data.columns.get_level_values(0):
                raise ValueError(f"Dataset trial is missing required sensor {dataset_name!r}.")
            sensor_data = trial_data[dataset_name].loc[:, GAITMAP_SENSOR_COLUMNS].copy()
            if sensor_data.isna().any().any():
                raise ValueError(f"Sensor {dataset_name!r} contains missing samples.")
            # Window-local indexes are created in next_window. Here RangeIndex keeps
            # exact sample positions and avoids floating-point time comparisons.
            selected[output_name] = sensor_data.reset_index(drop=True)

        lengths = {len(frame) for frame in selected.values()}
        if lengths == {0}:
            raise ValueError("The selected dataset trial contains no IMU samples.")
        if len(lengths) != 1:
            raise ValueError("The left and right dataset streams are not synchronized.")

        self._data = selected
        self._next_start_sample = 0
        self._window_index = 0
        self._playback_started_at = None
        self._window_phase_started_at = None
        return self

    @property
    def total_samples(self):
        """Return the number of synchronized samples in the selected trial."""
        self._require_open()
        return len(self._data["left_sensor"])

    @property
    def is_exhausted(self):
        """Return ``True`` only after the complete finite trial was emitted."""
        self._require_open()
        return self._next_start_sample >= self.total_samples

    def next_window(self):
        """Return the next overlapping window or ``None`` when unavailable.

        Returns:
            ``None`` after EOF and while the next recorded interval has not yet
            elapsed on the always-active replay clock. Inspect
            :attr:`is_exhausted` to distinguish these two cases. Otherwise a
            dictionary with:

            - ``data``: ``left_sensor`` and ``right_sensor`` DataFrames. Each has
              the six gaitmap columns and a zero-based, window-local sample index;
            - ``sampling_rate_hz``: ``204.8`` for this dataset;
            - ``window_index``: monotonically increasing integer starting at zero;
            - ``start_sample``/``end_sample``: half-open absolute interval in the
              trial, so the included samples are ``start <= sample < end``;
            - ``start_time_s``/``end_time_s``: the same boundaries in seconds;
            - ``is_final_window``: true when the window reaches the trial end.

        A final window shorter than ``window_duration_s`` is returned instead of
        discarded. Later analysis can decide whether it contains enough complete
        strides to be useful.
        """
        self._require_open()
        if self._next_start_sample >= self.total_samples:
            return None

        window_samples = max(1, round(self.window_duration_s * self.sampling_rate_hz))
        overlap_samples = round(self.window_overlap_s * self.sampling_rate_hz)
        step_samples = window_samples - overlap_samples
        start = self._next_start_sample
        end = min(start + window_samples, self.total_samples)
        if self._window_phase_started_at is None:
            self._window_phase_started_at = time.perf_counter()
            logger.info(
                "[window=%s] START acquire_imu_window source=file samples=%s:%s",
                self._window_index,
                start,
                end,
            )

        # File playback always follows the original acquisition clock. The first
        # complete 20-second window is available after 20 seconds; with 2 seconds
        # of overlap, later windows become available every 18 seconds. A short
        # sleep prevents busy waiting. The acquisition task calls this method in an
        # internal loop, so this temporary None never reaches downstream tasks.
        if self._playback_started_at is None:
            self._playback_started_at = time.monotonic()
        available_at = self._playback_started_at + end / self.sampling_rate_hz
        remaining_s = available_at - time.monotonic()
        if remaining_s > 0:
            time.sleep(min(0.1, remaining_s))
            return None

        window_data = {
            sensor: frame.iloc[start:end].reset_index(drop=True)
            for sensor, frame in self._data.items()
        }
        actual_duration_s = time.perf_counter() - self._window_phase_started_at
        result = {
            "data": window_data,
            "sampling_rate_hz": self.sampling_rate_hz,
            "window_index": self._window_index,
            "start_sample": start,
            "end_sample": end,
            "start_time_s": start / self.sampling_rate_hz,
            "end_time_s": end / self.sampling_rate_hz,
            "is_final_window": end == self.total_samples,
            "participant": self.participant,
            "trial": self.trial,
            "actual_duration_s": actual_duration_s,
        }
        # Once a window reaches EOF there must not be a second, almost completely
        # overlapping tail window. Without this branch, advancing by `step_samples`
        # can leave the cursor just before EOF and emit a useless one-sample window.
        self._next_start_sample = (
            self.total_samples if result["is_final_window"] else start + step_samples
        )
        self._window_index += 1
        logger.info(
            "[window=%s] END acquire_imu_window source=file duration_s=%.3f",
            result["window_index"],
            actual_duration_s,
        )
        self._window_phase_started_at = None
        return result

    def close(self):
        """Release references to the decoded trial and return ``True``."""
        self._data = None
        return True

    def _require_open(self):
        """Raise a clear lifecycle error when reading before ``open``."""
        if self._data is None:
            raise RuntimeError("The dataset source is not open.")


