"""Tests for the SDT virtual Depth source and acquisition task."""

import unittest

import numpy as np

from applications_repo.PatientPostureMonitoring.PatientPostureMonitoring import PatientPostureMonitoring
from applications_repo.PatientPostureMonitoring.Util.sdt_frame_source import DatasetExhausted, SDTFrameSource


DATASET = "/home/cysko7927/SDT_dataset"


class FakeFrameworkApplication:
    def __init__(self):
        self.stop_requested = False

    def stop_application(self):
        self.stop_requested = True


class SDTFrameSourceTest(unittest.TestCase):
    def test_first_frame_has_expected_type_shape_and_label(self):
        source = SDTFrameSource(DATASET, target_fps=0, loop_dataset=False)
        frame, index, cycle, label = source.next_frame()
        self.assertEqual(index, 0)
        self.assertEqual(label, 0)
        self.assertEqual(cycle, 0)
        self.assertEqual(frame.shape, (480, 640))
        self.assertEqual(frame.dtype, np.uint16)
        self.assertEqual(source.frame_count, 8000)

    def test_loop_restarts_at_zero(self):
        source = SDTFrameSource(DATASET, target_fps=0, loop_dataset=True)
        source._index = source.frame_count
        _, index, cycle, label = source.next_frame()
        self.assertEqual(index, 0)
        self.assertEqual(label, 0)
        self.assertEqual(cycle, 1)
        self.assertEqual(source.completed_cycles, 1)

    def test_non_looping_source_reports_exhaustion(self):
        source = SDTFrameSource(DATASET, target_fps=0, loop_dataset=False)
        source._index = source.frame_count
        with self.assertRaises(DatasetExhausted):
            source.next_frame()

    def test_application_acquisition_task(self):
        framework = FakeFrameworkApplication()
        application = PatientPostureMonitoring()
        application.set_framework(
            framework,
            {"dataset_path": DATASET, "target_fps": "0", "loop_dataset": "false"},
        )
        self.assertTrue(application.setup())
        self.assertTrue(application.acquire_depth_frame_setup())
        result = application.acquire_depth_frame_loop()
        self.assertEqual(
            set(result),
            {"raw_depth_frame", "frame_index", "dataset_cycle", "reference_label"},
        )
        self.assertEqual(result["frame_index"], 0)
        self.assertFalse(framework.stop_requested)


if __name__ == "__main__":
    unittest.main()
