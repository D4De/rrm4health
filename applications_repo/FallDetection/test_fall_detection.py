"""Unit tests for the framework FallDetection task pipeline."""

import json
import tempfile
import unittest
from pathlib import Path

import numpy as np

from applications_repo.FallDetection.FallDetection import FEATURE_NAMES, FallDetection, G_TO_MS2


class FakeFrameworkApplication:
    def __init__(self):
        self.in_use = []
        self.released = []
        self.stop_requested = False

    def notify_peripherals_in_use(self, identifiers, connection_type):
        self.in_use.append((list(identifiers), connection_type))

    def notify_peripherals_released(self, identifiers):
        self.released.extend(identifiers)

    def stop_application(self):
        self.stop_requested = True


class FakeModel:
    classes_ = np.asarray([0, 1, 5, 6])
    n_features_in_ = len(FEATURE_NAMES)

    def predict(self, vector):
        assert vector.shape == (1, len(FEATURE_NAMES))
        return np.asarray([5])

    def predict_proba(self, vector):
        return np.asarray([[0.05, 0.05, 0.85, 0.05]])


class FakeManager:
    def __init__(self):
        self.calls = []
        self.packet = feature_packet(0.1)

    def set_imus(self, value):
        self.calls.append(("set_imus", value))

    def set_access_point(self, *value):
        self.calls.append(("set_access_point", value))

    def set_campaign(self, *value, **options):
        self.calls.append(("set_campaign", value, options))

    def start_collection(self):
        self.calls.append(("start_collection",))

    def wait_connection(self):
        self.calls.append(("wait_connection",))

    def get_packet(self, block, timeout):
        self.calls.append(("get_packet", block, timeout))
        return self.packet

    def stop_collection(self):
        self.calls.append(("stop_collection",))


def feature_packet(dynamic_sma):
    packet = {name: 1.0 for name in FEATURE_NAMES}
    packet.update(
        {
            "dynamic_sma": dynamic_sma,
            "imuid": "b0:b2:1c:4a:00:38",
            "cname": "fall_detection",
            "nth": 7,
            "ts": 1234,
        }
    )
    return packet


class FallDetectionTest(unittest.TestCase):
    def make_application(self, output_path):
        application = FallDetection()
        application.set_framework(
            FakeFrameworkApplication(),
            {
                "imu_names": "b0:b2:1c:4a:00:38",
                "ssid": "test-network",
                "output_path": str(output_path),
            },
        )
        self.assertTrue(application.setup())
        application._model = FakeModel()
        return application

    def test_acquisition_task_configures_features_mode_and_releases_imu(self):
        with tempfile.TemporaryDirectory() as directory:
            application = self.make_application(directory)
            application.manager_factory = FakeManager
            self.assertTrue(application.acquire_feature_packet_setup())
            manager = application._manager
            packet = application.acquire_feature_packet_loop()["feature_packet"]
            self.assertTrue(application.acquire_feature_packet_cleanup())

        campaign_call = next(call for call in manager.calls if call[0] == "set_campaign")
        self.assertEqual(campaign_call[1], ("fall_detection", 200))
        self.assertEqual(
            campaign_call[2],
            {"raw": False, "window_size": 300, "step_size": 300},
        )
        self.assertEqual(packet["nth"], 7)
        self.assertEqual(application._app.in_use[0][1], "wifi")
        self.assertEqual(application._app.released, ["b0:b2:1c:4a:00:38"])

    def test_preparation_converts_only_acceleration_features(self):
        with tempfile.TemporaryDirectory() as directory:
            application = self.make_application(directory)
            prepared = application.prepare_feature_vector_loop(
                feature_packet(0.01)
            )["prepared_packet"]

        self.assertAlmostEqual(prepared["features"]["ax_mean"], G_TO_MS2)
        self.assertAlmostEqual(prepared["features"]["dynamic_sma"], 0.01 * G_TO_MS2)
        self.assertEqual(prepared["features"]["gx_mean"], 1.0)
        self.assertEqual(prepared["features"]["tilt"], 1.0)
        self.assertEqual(prepared["metadata"]["nth"], 7)

    def test_static_packet_bypasses_model(self):
        with tempfile.TemporaryDirectory() as directory:
            application = self.make_application(directory)
            prepared = application.prepare_feature_vector_loop(
                feature_packet(0.01)
            )["prepared_packet"]
            result = application.classify_fall_risk_loop(prepared)[
                "detection_result"
            ]

        self.assertEqual(result["branch"], "static")
        self.assertEqual(result["label"], "static (standing/sitting/lying)")
        self.assertNotIn("model_class", result)
        self.assertNotIn("confidence", result)

    def test_dynamic_packet_is_classified_and_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            application = self.make_application(directory)
            prepared = application.prepare_feature_vector_loop(
                feature_packet(0.1)
            )["prepared_packet"]
            result = application.classify_fall_risk_loop(prepared)[
                "detection_result"
            ]
            self.assertTrue(application.persist_detection_setup())
            output_path = application._results_path
            application.persist_detection_loop(result)
            application.persist_detection_cleanup()
            persisted = json.loads(output_path.read_text(encoding="utf-8"))

        self.assertEqual(result["branch"], "dynamic")
        self.assertEqual(result["label"], "fall")
        self.assertEqual(result["model_class"], 5)
        self.assertAlmostEqual(result["confidence"], 0.85)
        self.assertEqual(persisted["label"], "fall")

    def test_missing_feature_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            application = self.make_application(directory)
            packet = feature_packet(0.1)
            del packet["jerk_mean"]
            with self.assertRaisesRegex(ValueError, "jerk_mean"):
                application.prepare_feature_vector_loop(packet)


if __name__ == "__main__":
    unittest.main()
