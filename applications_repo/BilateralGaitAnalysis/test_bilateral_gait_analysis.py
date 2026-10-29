"""Focused tests for dataset-window acquisition without decoding NilsPod files."""

import csv
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

import pandas as pd
import numpy as np


MODULE_PATH = Path(__file__).with_name("BilateralGaitAnalysis.py")
sys.path.insert(0, str(MODULE_PATH.parent))
SPEC = spec_from_file_location("bilateral_gait_analysis", MODULE_PATH)
MODULE = module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def _opened_source(sample_count=25, sampling_rate_hz=10.0):
    """Build an already-open source with deterministic, synchronized test data."""
    source = MODULE.SensorPositionDatasetFileSource(".", "participant", "trial", 1, 0.2)
    source.sampling_rate_hz = sampling_rate_hz
    frame = pd.DataFrame(
        {column: range(sample_count) for column in MODULE.GAITMAP_SENSOR_COLUMNS}
    )
    source._data = {"left_sensor": frame.copy(), "right_sensor": frame.copy()}
    # Most tests exercise window boundaries, not wall-clock replay. Put the
    # recording epoch far enough in the past so their windows are immediately due.
    source._playback_started_at = time.monotonic() - 10_000.0
    return source


class _FakeBleManager:
    """Minimal FIFO implementing the production manager's get_packet contract."""

    def __init__(self, packets):
        self.packets = list(packets)

    def get_packet(self, block=False, timeout=None):
        return self.packets.pop(0) if self.packets else None


class _FakeFramework:
    def __init__(self, running=True):
        self.running = running

    def is_running(self):
        return self.running

    @staticmethod
    def wait_for_stop():
        raise RuntimeError("framework stopped")


def _ble_packet(imu, counter, raw_acc=1000, raw_gyr=-100):
    """Build one deterministic raw packet in the firmware's hexadecimal format."""
    unsigned_gyr = raw_gyr % 65536
    return {
        "ax": hex(raw_acc), "ay": hex(raw_acc), "az": hex(raw_acc),
        "gx": hex(unsigned_gyr), "gy": hex(unsigned_gyr), "gz": hex(unsigned_gyr),
        "mx": "0x0000", "my": "0x0000", "mz": "0x0000",
        "nth": hex(counter % 65536), "ts": hex(1_700_000_000),
        "imuid": imu, "cname": "268",
    }


def _ble_app(packets, overlap_samples=0):
    """Build the application with the same direct BLE buffers created by setup."""
    app = MODULE.BilateralGaitAnalysis()
    app._acquisition_mode = "ble"
    app._imu_names = ["LEFT", "RIGHT"]
    app._sampling_rate_hz = 2.0
    app._campaign_name = "268"
    app._ble_manager = _FakeBleManager(packets)
    app._ble_pending_packets = {imu: {} for imu in app._imu_names}
    app._ble_last_raw_counter = {imu: None for imu in app._imu_names}
    app._ble_last_unwrapped_counter = {imu: None for imu in app._imu_names}
    app._ble_synchronized_run = []
    app._ble_expected_counter = None
    app._ble_discarded_samples = 0
    app._ble_lost_packets_total = 0
    app._ble_lost_packets_at_window_start = 0
    app._ble_window_samples = 4
    app._ble_overlap_samples = overlap_samples
    app._ble_window_index = 0
    app._ble_next_window_start_sample = 0
    app._ble_window_phase_started_at = None
    app._ble_last_progress_logged = 0
    app._app = _FakeFramework()
    # Acquisition behavior tests do not need filesystem output. The dedicated CSV
    # test below restores the real bound method inside a managed temporary folder.
    app._record_acquisition_window = lambda window: window
    return app


class BleWindowTests(unittest.TestCase):
    def test_hex_conversion_synchronization_and_overlap(self):
        packets = []
        for counter in range(6):
            # Deliberately interleave right then left: output must still be aligned.
            packets.extend([
                _ble_packet("RIGHT", counter),
                _ble_packet("LEFT", counter),
            ])
        app = _ble_app(packets, overlap_samples=2)

        first = app.acquire_imu_window_loop()["raw_imu_window"]
        second = app.acquire_imu_window_loop()["raw_imu_window"]

        self.assertEqual((first["first_nth"], first["last_nth"]), (0, 3))
        self.assertEqual((second["first_nth"], second["last_nth"]), (2, 5))
        self.assertEqual((second["start_sample"], second["end_sample"]), (2, 6))
        self.assertEqual(first["campaign_name"], "268")
        expected_acc = 1000 * 4 / 32768
        expected_gyr = -100 * 2000 / 32768
        self.assertAlmostEqual(first["data"]["left_sensor"].iloc[0].acc_x, expected_acc)
        self.assertAlmostEqual(first["data"]["left_sensor"].iloc[0].gyr_x, expected_gyr)

    def test_counter_wrap_is_continuous(self):
        packets = []
        for counter in (65534, 65535, 0, 1):
            packets.extend([_ble_packet("LEFT", counter), _ble_packet("RIGHT", counter)])
        app = _ble_app(packets)

        window = app.acquire_imu_window_loop()["raw_imu_window"]

        self.assertEqual(window["first_nth"], 65534)
        self.assertEqual(window["last_nth"], 1)

    def test_missing_sample_preserves_previous_synchronized_samples(self):
        packets = []
        for counter in (0, 1, 3, 4, 5, 6):
            packets.extend([_ble_packet("LEFT", counter), _ble_packet("RIGHT", counter)])
        app = _ble_app(packets)

        window = app.acquire_imu_window_loop()["raw_imu_window"]

        self.assertEqual((window["first_nth"], window["last_nth"]), (0, 4))
        self.assertEqual(window["discarded_incomplete_samples"], 1)
        self.assertEqual(window["lost_packets"], 2)

    def test_complete_window_is_written_to_acquisition_csv(self):
        packets = []
        for counter in range(4):
            packets.extend([_ble_packet("LEFT", counter), _ble_packet("RIGHT", counter)])
        app = _ble_app(packets)
        with tempfile.TemporaryDirectory() as output_directory:
            app._output_path = output_directory
            app._initialize_acquisition_csv()
            app._record_acquisition_window = (
                MODULE.BilateralGaitAnalysis._record_acquisition_window.__get__(app)
            )
            app.acquire_imu_window_loop()
            with app._acquisition_csv_path.open(encoding="utf-8") as csv_file:
                rows = list(csv.DictReader(csv_file))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["window_index"], "0")
        self.assertEqual(rows[0]["window_size_samples"], "4")
        self.assertEqual(rows[0]["theoretical_duration_s"], "2.0")
        self.assertGreaterEqual(float(rows[0]["actual_duration_s"]), 0.0)
        self.assertEqual(rows[0]["lost_packets"], "0")
        self.assertEqual(rows[0]["sampling_frequency_hz"], "2.0")

    def test_raw_ble_packets_are_saved_as_valid_json(self):
        app = _ble_app([])
        packet = _ble_packet("LEFT", 7)
        with tempfile.TemporaryDirectory() as output_directory:
            app._output_path = output_directory
            app._initialize_raw_packet_json()
            app._record_raw_ble_packet(packet)
            app._close_raw_packet_json()
            with app._raw_packets_paths["LEFT"].open(encoding="utf-8") as json_file:
                saved = json.load(json_file)
        self.assertEqual(saved, [packet])

    def test_stop_is_observed_even_while_packets_keep_arriving(self):
        packets = []
        for counter in range(4):
            packets.extend([_ble_packet("LEFT", counter), _ble_packet("RIGHT", counter)])
        app = _ble_app(packets)
        app._app = _FakeFramework(running=False)

        with self.assertRaisesRegex(RuntimeError, "framework stopped"):
            app.acquire_imu_window_loop()

        self.assertEqual(len(app._ble_manager.packets), 8)

    def test_malformed_required_channel_is_rejected(self):
        packet = _ble_packet("LEFT", 0)
        del packet["gz"]
        app = _ble_app([packet])

        with self.assertRaisesRegex(ValueError, "missing: gz"):
            app.acquire_imu_window_loop()

    def test_packet_from_another_campaign_is_rejected(self):
        packet = _ble_packet("LEFT", 0)
        packet["cname"] = "269"
        app = _ble_app([packet])

        with self.assertRaisesRegex(ValueError, "campaign '269', expected '268'"):
            app.acquire_imu_window_loop()


class DatasetWindowTests(unittest.TestCase):
    def test_windows_overlap_and_keep_short_final_window(self):
        source = _opened_source()

        first = source.next_window()
        second = source.next_window()
        third = source.next_window()
        exhausted = source.next_window()

        self.assertEqual((first["start_sample"], first["end_sample"]), (0, 10))
        self.assertEqual((second["start_sample"], second["end_sample"]), (8, 18))
        self.assertEqual((third["start_sample"], third["end_sample"]), (16, 25))
        self.assertTrue(third["is_final_window"])
        self.assertIsNone(exhausted)
        self.assertEqual(list(first["data"]), ["left_sensor", "right_sensor"])

    def test_close_prevents_further_reads(self):
        source = _opened_source()
        self.assertTrue(source.close())

        with self.assertRaisesRegex(RuntimeError, "not open"):
            source.next_window()

    def test_realtime_replay_waits_without_advancing_the_file_cursor(self):
        source = _opened_source(sample_count=25, sampling_rate_hz=10.0)
        source._playback_started_at = None

        waiting = source.next_window()

        self.assertIsNone(waiting)
        self.assertEqual(source._next_start_sample, 0)
        # Move the virtual acquisition epoch into the past instead of making the
        # unit test wait one real second for its ten-sample window.
        source._playback_started_at -= 1.1
        available = source.next_window()
        self.assertEqual((available["start_sample"], available["end_sample"]), (0, 10))

    def test_source_distinguishes_temporary_wait_from_true_end_of_file(self):
        source = _opened_source(sample_count=10, sampling_rate_hz=10.0)
        source._playback_started_at = None

        self.assertIsNone(source.next_window())
        self.assertFalse(source.is_exhausted)
        source._playback_started_at -= 1.1
        self.assertIsNotNone(source.next_window())
        self.assertTrue(source.is_exhausted)
        self.assertIsNone(source.next_window())

    def test_acquisition_task_does_not_return_until_a_complete_window_exists(self):
        class DelayedSource:
            is_exhausted = False

            def __init__(self):
                self.calls = 0

            def next_window(self):
                self.calls += 1
                if self.calls < 3:
                    return None
                return {"window_index": 0, "data": {}}

        class RunningFramework:
            @staticmethod
            def is_running():
                return True

        app = MODULE.BilateralGaitAnalysis()
        app._acquisition_mode = "file"
        app._acquisition = DelayedSource()
        app._file_eof_announced = False
        app._app = RunningFramework()
        app._record_acquisition_window = lambda window: window

        result = app.acquire_imu_window_loop()

        self.assertEqual(app._acquisition.calls, 3)
        self.assertEqual(result["raw_imu_window"]["window_index"], 0)

    def test_end_of_dataset_notifies_the_gui_only_once(self):
        class StopRequested(Exception):
            pass

        class ExhaustedSource:
            is_exhausted = True

            @staticmethod
            def next_window():
                return None

        class StoppedFramework:
            def __init__(self):
                self.notifications = []

            def notify_message(self, message, severity="info"):
                self.notifications.append((message, severity))

            @staticmethod
            def wait_for_stop():
                raise StopRequested("test stop")

        app = MODULE.BilateralGaitAnalysis()
        app._acquisition_mode = "file"
        app._acquisition = ExhaustedSource()
        app._file_eof_announced = False
        app._app = StoppedFramework()

        for _ in range(2):
            with self.assertRaises(StopRequested):
                app.acquire_imu_window_loop()

        self.assertEqual(len(app._app.notifications), 1)
        message, severity = app._app.notifications[0]
        self.assertIn("Dataset terminato", message)
        self.assertEqual(severity, "info")


class GlobalCleanupTests(unittest.TestCase):
    def test_all_cleanups_are_safe_when_first_task_setup_failed(self):
        app = MODULE.BilateralGaitAnalysis()
        app.set_framework(
            object(),
            {
                "imu_names": "LEFT-RIGHT",
                "sensor_positions": "left_foot-right_foot",
                "acquisition_mode": "file",
                "input_path": "missing_dataset",
            },
        )
        self.assertTrue(app.setup())

        # This reproduces LifecycleManager's reverse cleanup after acquisition
        # setup fails, before any later task-specific setup has constructed objects.
        self.assertTrue(app.export_gait_result_cleanup())
        self.assertTrue(app.aggregate_gait_results_cleanup())
        self.assertTrue(app.calculate_spatial_parameters_cleanup())
        self.assertTrue(app.reconstruct_stride_trajectories_cleanup())
        self.assertTrue(app.calculate_temporal_parameters_cleanup())
        self.assertTrue(app.detect_gait_events_cleanup())
        self.assertTrue(app.segment_strides_cleanup())
        self.assertTrue(app.preprocess_imu_window_cleanup())
        self.assertTrue(app.acquire_imu_window_cleanup())
        self.assertTrue(app.cleanup())

    def test_cleanup_is_safe_when_task_cleanup_already_released_resources(self):
        app = MODULE.BilateralGaitAnalysis()
        app._ble_manager = None
        app._ble_peripherals_announced = False
        app._acquisition = None
        app._acquisition_mode = "ble"

        self.assertTrue(app.cleanup())

    def test_cleanup_closes_file_source_left_by_partial_setup(self):
        class Source:
            closed = False

            def close(self):
                self.closed = True
                return True

        app = MODULE.BilateralGaitAnalysis()
        app._ble_manager = None
        app._ble_peripherals_announced = False
        app._acquisition_mode = "file"
        app._acquisition = Source()
        source = app._acquisition

        self.assertTrue(app.cleanup())
        self.assertTrue(source.closed)
        self.assertIsNone(app._acquisition)


class TaskLoggingTests(unittest.TestCase):
    def test_logged_phase_reports_start_and_end_with_window_index(self):
        with self.assertLogs(MODULE.logger, level="INFO") as captured:
            result = MODULE.BilateralGaitAnalysis._run_logged_phase(
                "example_task", {"window_index": 7}, lambda: "done"
            )

        self.assertEqual(result, "done")
        messages = "\n".join(captured.output)
        self.assertIn("[window=7] START example_task", messages)
        self.assertIn("[window=7] END example_task", messages)

    def test_export_does_not_log_or_write_an_unchanged_snapshot(self):
        class Exporter:
            called = False

            def export_incremental(self, result):
                self.called = True

        app = MODULE.BilateralGaitAnalysis()
        app._exporter = Exporter()

        self.assertEqual(app.export_gait_result_loop({"updated": False}), {})
        self.assertFalse(app._exporter.called)


class PreprocessingTests(unittest.TestCase):
    @staticmethod
    def _raw_window(sample_count=20):
        frame = pd.DataFrame(
            np.ones((sample_count, len(MODULE.GAITMAP_SENSOR_COLUMNS))),
            columns=MODULE.GAITMAP_SENSOR_COLUMNS,
        )
        return {
            "data": {"left_sensor": frame.copy(), "right_sensor": frame.copy()},
            "sampling_rate_hz": 10.0,
            "window_index": 3,
            "start_sample": 20,
            "end_sample": 40,
        }

    def test_filter_preserves_native_rate_and_sample_count(self):
        preprocessor = MODULE.ImuWindowPreprocessor(2.0)
        result = preprocessor.process(self._raw_window())

        self.assertEqual(result["sampling_rate_hz"], 10.0)
        self.assertEqual(result["source_sampling_rate_hz"], 10.0)
        self.assertEqual(result["source_start_sample"], 20)
        self.assertEqual(result["window_index"], 3)
        self.assertEqual(result["data"]["left_sensor"].shape, (20, 6))
        self.assertEqual(result["data"]["right_sensor"].shape, (20, 6))
        self.assertEqual(result["data"]["left_sensor"].index.name, "sample")
        np.testing.assert_allclose(
            result["data"]["left_sensor"].to_numpy(), 1.0, atol=1e-10
        )

    def test_none_marks_end_of_file(self):
        preprocessor = MODULE.ImuWindowPreprocessor(20.0)
        self.assertIsNone(preprocessor.process(None))

    def test_live_acceleration_is_converted_from_g_to_meters_per_second_squared(self):
        raw = self._raw_window()
        raw["acceleration_unit"] = "g"

        result = MODULE.ImuWindowPreprocessor(2.0).process(raw)

        self.assertEqual(result["acceleration_unit"], "m/s^2")
        np.testing.assert_allclose(
            result["data"]["left_sensor"].iloc[:, :3].to_numpy(),
            9.80665,
            atol=1e-10,
        )
        np.testing.assert_allclose(
            result["data"]["left_sensor"].iloc[:, 3:].to_numpy(),
            1.0,
            atol=1e-10,
        )

    def test_missing_values_are_rejected(self):
        raw = self._raw_window()
        raw["data"]["left_sensor"].iloc[2, 1] = np.nan

        with self.assertRaisesRegex(ValueError, "NaN or infinite"):
            MODULE.ImuWindowPreprocessor(2.0).process(raw)


class HerzerEventDetectorTests(unittest.TestCase):
    def test_empty_stride_window_returns_two_well_formed_sensor_tables(self):
        sensor_frame = pd.DataFrame(
            np.zeros((20, len(MODULE.GAITMAP_SENSOR_COLUMNS))),
            columns=MODULE.GAITMAP_SENSOR_COLUMNS,
        )
        preprocessed = {
            "data": {
                "left_sensor": sensor_frame.copy(),
                "right_sensor": sensor_frame.copy(),
            },
            "sampling_rate_hz": 100.0,
        }
        empty_strides = pd.DataFrame(columns=("start", "end"), dtype=int)
        empty_strides.index = pd.Index([], name="s_id", dtype=int)
        segmented = {
            "stride_list": {
                "left_sensor": empty_strides.copy(),
                "right_sensor": empty_strides.copy(),
            },
            "sampling_rate_hz": 100.0,
            "window_index": 0,
            "window_start_time_s": 0.0,
        }

        detector = MODULE.HerzerGaitEventDetector()
        result = detector.detect(preprocessed, segmented)

        self.assertEqual(
            set(result["min_vel_event_list"]), {"left_sensor", "right_sensor"}
        )
        self.assertTrue(result["min_vel_event_list"]["left_sensor"].empty)
        self.assertEqual(
            tuple(result["min_vel_event_list"]["left_sensor"].columns),
            MODULE.HerzerGaitEventDetector._MIN_VEL_COLUMNS,
        )
        detector.close()


class TemporalParameterTests(unittest.TestCase):
    @staticmethod
    def _event_result():
        # At 100 Hz: pre_ic=0, tc=60 and ic=100 produce a 1.0 s stride,
        # 0.4 s swing and consequently 0.6 s stance.
        events = pd.DataFrame(
            {
                "start": [20.0],
                "end": [120.0],
                "ic": [100.0],
                "tc": [60.0],
                "min_vel": [20.0],
                "pre_ic": [0.0],
            },
            index=pd.Index([7], name="s_id"),
        )
        return {
            "min_vel_event_list": {
                "left_sensor": events.copy(),
                "right_sensor": events.copy(),
            },
            "sampling_rate_hz": 100.0,
            "window_index": 2,
        }

    def test_official_temporal_formulas_and_metadata(self):
        calculator = MODULE.TemporalGaitParameterCalculator()
        result = calculator.calculate(self._event_result())

        left = result["parameters"]["left_sensor"].loc[7]
        self.assertAlmostEqual(left["stride_time"], 1.0)
        self.assertAlmostEqual(left["swing_time"], 0.4)
        self.assertAlmostEqual(left["stance_time"], 0.6)
        self.assertEqual(result["window_index"], 2)
        self.assertEqual(result["sampling_rate_hz"], 100.0)
        calculator.close()

    def test_end_of_file_is_propagated(self):
        calculator = MODULE.TemporalGaitParameterCalculator()
        self.assertIsNone(calculator.calculate(None))
        calculator.close()


class TrajectoryReconstructionTests(unittest.TestCase):
    @staticmethod
    def _inputs():
        frame = pd.DataFrame(
            np.tile([0.0, 0.0, 9.81, 0.0, 0.0, 0.0], (20, 1)),
            columns=MODULE.GAITMAP_SENSOR_COLUMNS,
        )
        empty_events = pd.DataFrame(
            columns=("start", "end", "ic", "tc", "min_vel", "pre_ic"),
            dtype=float,
        )
        empty_events.index = pd.Index([], name="s_id", dtype=int)
        preprocessed = {
            "data": {"left_sensor": frame.copy(), "right_sensor": frame.copy()},
            "sampling_rate_hz": 100.0,
        }
        events = {
            "min_vel_event_list": {
                "left_sensor": empty_events.copy(),
                "right_sensor": empty_events.copy(),
            },
            "sampling_rate_hz": 100.0,
            "window_index": 4,
        }
        return preprocessed, events

    def test_lightweight_mode_skips_all_trajectory_arrays(self):
        preprocessed, events = self._inputs()
        reconstructor = MODULE.StrideTrajectoryReconstructor(lightweight_mode=True)
        result = reconstructor.reconstruct(preprocessed, events)

        self.assertFalse(result["enabled"])
        self.assertIsNone(result["orientation"])
        self.assertIsNone(result["position"])
        self.assertEqual(result["window_index"], 4)

    def test_full_mode_preserves_empty_output_schema(self):
        preprocessed, events = self._inputs()
        reconstructor = MODULE.StrideTrajectoryReconstructor(lightweight_mode=False)
        result = reconstructor.reconstruct(preprocessed, events)

        self.assertTrue(result["enabled"])
        self.assertEqual(
            tuple(result["position"]["left_sensor"].columns),
            ("pos_x", "pos_y", "pos_z"),
        )
        self.assertTrue(result["position"]["left_sensor"].empty)
        reconstructor.close()


class SpatialParameterTests(unittest.TestCase):
    @staticmethod
    def _empty_inputs(enabled):
        events = pd.DataFrame(
            columns=("start", "end", "ic", "tc", "min_vel", "pre_ic"),
            dtype=float,
        )
        events.index = pd.Index([], name="s_id", dtype=int)
        event_result = {
            "min_vel_event_list": {
                "left_sensor": events.copy(),
                "right_sensor": events.copy(),
            },
            "sampling_rate_hz": 100.0,
            "window_index": 5,
        }
        trajectory_result = {
            "enabled": enabled,
            "sampling_rate_hz": 100.0,
        }
        if enabled:
            index = pd.MultiIndex.from_arrays([[], []], names=("s_id", "sample"))
            position = pd.DataFrame(
                columns=("pos_x", "pos_y", "pos_z"), index=index, dtype=float
            )
            orientation = pd.DataFrame(
                columns=("q_x", "q_y", "q_z", "q_w"), index=index, dtype=float
            )
            trajectory_result.update(
                {
                    "position": {
                        "left_sensor": position.copy(),
                        "right_sensor": position.copy(),
                    },
                    "orientation": {
                        "left_sensor": orientation.copy(),
                        "right_sensor": orientation.copy(),
                    },
                }
            )
        return event_result, trajectory_result

    def test_full_mode_returns_all_nine_parameter_columns(self):
        events, trajectories = self._empty_inputs(enabled=True)
        calculator = MODULE.SpatialGaitParameterCalculator(lightweight_mode=False)
        result = calculator.calculate(events, trajectories)

        self.assertTrue(result["enabled"])
        self.assertEqual(len(result["parameters"]["left_sensor"].columns), 9)
        self.assertIn("stride_length", result["parameters"]["left_sensor"])
        self.assertNotIn("velocity", result)
        calculator.close()

    def test_lightweight_mode_skips_spatial_parameters(self):
        events, trajectories = self._empty_inputs(enabled=False)
        calculator = MODULE.SpatialGaitParameterCalculator(lightweight_mode=True)
        result = calculator.calculate(events, trajectories)

        self.assertFalse(result["enabled"])
        self.assertIsNone(result["parameters"])
        self.assertIsNone(result["parameters_pretty"])


class AggregationTests(unittest.TestCase):
    @staticmethod
    def _window(window_index, window_start_s, local_ic_sample, stride_time):
        events = pd.DataFrame(
            {
                "start": [local_ic_sample - 50],
                "end": [local_ic_sample + 50],
                "ic": [local_ic_sample],
                "tc": [local_ic_sample - 40],
                "min_vel": [local_ic_sample - 50],
                "pre_ic": [local_ic_sample - 100],
            },
            index=pd.Index([0], name="s_id"),
        )
        parameters = pd.DataFrame(
            {
                "stride_time": [stride_time],
                "swing_time": [0.4],
                "stance_time": [stride_time - 0.4],
            },
            index=events.index.copy(),
        )
        event_result = {
            "min_vel_event_list": {
                "left_sensor": events.copy(),
                "right_sensor": events.copy(),
            },
            "sampling_rate_hz": 100.0,
            "window_index": window_index,
            "window_start_time_s": window_start_s,
            "window_end_time_s": window_start_s + 10.0,
            "participant": "p1",
            "trial": "normal_10",
        }
        temporal_result = {
            "parameters": {
                "left_sensor": parameters.copy(),
                "right_sensor": parameters.copy(),
            }
        }
        spatial_result = {"enabled": False, "parameters": None}
        return event_result, temporal_result, spatial_result

    def test_duplicate_ic_keeps_observation_farthest_from_window_edge(self):
        aggregator = MODULE.GaitResultAggregator(0.1, 1)
        # Both windows describe absolute IC=9.5 s. In window 0 it is only 0.5 s
        # from the end; in window 1 it is 1.5 s from the start and must replace it.
        first = self._window(0, 0.0, 950, 1.0)
        second = self._window(1, 8.0, 150, 1.1)

        aggregator.update(*first)
        result = aggregator.update(*second)

        self.assertEqual(result["per_sensor"]["left_sensor"]["stride_count"], 1)
        kept = result["per_sensor"]["left_sensor"]["parameters"].iloc[0]
        self.assertEqual(kept["window_index"], 1)
        self.assertAlmostEqual(kept["stride_time"], 1.1)
        self.assertTrue(result["bilateral"]["minimum_complete_strides_met"])


class ResultExportTests(unittest.TestCase):
    @staticmethod
    def _result(updated=True):
        frame = pd.DataFrame(
            {"absolute_ic_time_s": [1.0], "stride_time": [1.1]},
            index=pd.Index([0], name="trial_stride_id"),
        )
        return {
            "updated": updated,
            "participant": "p/1",
            "trial": "normal_10",
            "per_sensor": {
                "left_sensor": {
                    "stride_count": 1,
                    "parameters": frame.copy(),
                    "summary": {"stride_time": {"std": None}},
                },
                "right_sensor": {
                    "stride_count": 1,
                    "parameters": frame.copy(),
                    "summary": {"stride_time": {"std": None}},
                },
            },
            "bilateral": {"total_stride_count": 2},
        }

    def test_incremental_csv_and_final_json_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            exporter = MODULE.GaitResultExporter(directory, "fallback", "trial")
            paths = exporter.export_incremental(self._result())
            final_path = exporter.export_final()

            self.assertEqual(len(paths), 3)
            self.assertTrue(Path(paths["json"]).is_file())
            self.assertTrue(Path(paths["left_sensor_csv"]).is_file())
            self.assertTrue(Path(final_path).is_file())
            self.assertNotIn("/1", Path(paths["json"]).name)
            with Path(paths["json"]).open(encoding="utf-8") as file:
                payload = json.load(file)
            self.assertEqual(payload["bilateral"]["total_stride_count"], 2)
            self.assertEqual(
                payload["per_sensor"]["left_sensor"]["parameters"][0][
                    "trial_stride_id"
                ],
                0,
            )
            exporter.close()

    def test_unchanged_snapshot_does_not_write(self):
        with tempfile.TemporaryDirectory() as directory:
            exporter = MODULE.GaitResultExporter(directory, "p1", "trial")
            self.assertEqual(exporter.export_incremental(self._result(False)), {})
            self.assertEqual(list(Path(directory).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
