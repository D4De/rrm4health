"""Framework-native fall detection from WiFi IMU feature packets."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np

from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr


logger = logging.getLogger(__name__)

FEATURE_NAMES = (
    "acc_mag_max", "acc_mag_mean", "acc_mag_std",
    "gyro_mag_max", "gyro_mag_mean", "gyro_mag_std",
    "ax_mean", "ax_max", "ax_std",
    "ay_mean", "ay_max", "ay_std",
    "az_mean", "az_max", "az_std",
    "gx_mean", "gx_max", "gx_std",
    "gy_mean", "gy_max", "gy_std",
    "gz_mean", "gz_max", "gz_std",
    "tilt", "dynamic_sma", "jerk_max", "jerk_mean",
)

ACCELERATION_FEATURES = frozenset(
    {
        "acc_mag_max", "acc_mag_mean", "acc_mag_std",
        "ax_mean", "ax_max", "ax_std",
        "ay_mean", "ay_max", "ay_std",
        "az_mean", "az_max", "az_std",
        "dynamic_sma", "jerk_max", "jerk_mean",
    }
)

CLASS_LABELS = {
    0: "walking",
    1: "running",
    5: "fall",
    6: "fast walking",
}

G_TO_MS2 = 9.80665
DEFAULT_STATIC_SMA_THRESHOLD = 0.325226


def _positive_int(value, name):
    try:
        parsed = int(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be an integer") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def _positive_float(value, name):
    try:
        parsed = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{name} must be numeric") from error
    if parsed <= 0:
        raise ValueError(f"{name} must be greater than zero")
    return parsed


def _parse_imu_names(value):
    if isinstance(value, dict):
        result = dict(value)
    elif isinstance(value, (list, tuple)):
        result = [str(item).strip() for item in value if str(item).strip()]
    else:
        result = [item.strip() for item in str(value or "").split("-") if item.strip()]
    if not result:
        raise ValueError("imu_names must contain at least one MAC address or IP")
    return result


class FallDetection:
    """Split acquisition, preparation, inference and export into framework tasks."""

    manager_factory = WifiAcquisitionMngr

    def set_framework(self, app, user_args=None):
        self._app = app
        self._user_args = user_args or {}

    def setup(self):
        self._imu_names = _parse_imu_names(self._user_args.get("imu_names"))
        self._wifi_interface = str(
            self._user_args.get("wifi_interface", "wlp2s0")
        ).strip()
        self._ssid = str(self._user_args.get("ssid", "")).strip()
        self._password = str(self._user_args.get("password", ""))
        self._campaign_name = str(
            self._user_args.get("campaign_name", "fall_detection")
        ).strip()
        if not self._wifi_interface or not self._ssid or not self._campaign_name:
            raise ValueError("wifi_interface, ssid and campaign_name cannot be empty")

        self._sampling_frequency_hz = _positive_int(
            self._user_args.get("sampling_frequency_hz", 200),
            "sampling_frequency_hz",
        )
        self._window_size = _positive_int(
            self._user_args.get("window_size", 300), "window_size"
        )
        self._step_size = _positive_int(
            self._user_args.get("step_size", 300), "step_size"
        )
        if self._step_size > self._window_size:
            raise ValueError("step_size must be less than or equal to window_size")

        self._packet_timeout_s = _positive_float(
            self._user_args.get("packet_timeout_s", 20), "packet_timeout_s"
        )
        try:
            self._static_sma_threshold = float(
                self._user_args.get(
                    "static_sma_threshold", DEFAULT_STATIC_SMA_THRESHOLD
                )
            )
        except (TypeError, ValueError) as error:
            raise ValueError("static_sma_threshold must be numeric") from error
        if self._static_sma_threshold < 0:
            raise ValueError("static_sma_threshold cannot be negative")

        app_directory = Path(__file__).resolve().parent
        model_path = Path(
            self._user_args.get("model_path", "mlp_dynamic_only_model.pkl")
        ).expanduser()
        self._model_path = (
            model_path if model_path.is_absolute() else app_directory / model_path
        )
        self._output_path = Path(
            self._user_args.get("output_path", "output/")
        ).expanduser()

        self._manager = None
        self._model = None
        self._results_file = None
        self._peripherals_announced = False
        return True

    def acquire_feature_packet_setup(self):
        self._manager = self.manager_factory()
        self._manager.set_imus(self._imu_names)
        self._manager.set_access_point(
            self._wifi_interface, self._ssid, self._password
        )
        self._manager.set_campaign(
            self._campaign_name,
            self._sampling_frequency_hz,
            raw=False,
            window_size=self._window_size,
            step_size=self._step_size,
        )
        self._manager.start_collection()
        self._manager.wait_connection()
        if hasattr(self._app, "notify_peripherals_in_use"):
            self._app.notify_peripherals_in_use(self._imu_names, "wifi")
            self._peripherals_announced = True
        logger.info(
            "WiFi FEATURES acquisition ready: %d Hz, window=%d, step=%d",
            self._sampling_frequency_hz,
            self._window_size,
            self._step_size,
        )
        return True

    def prepare_feature_vector_setup(self):
        return True

    def classify_fall_risk_setup(self):
        if not self._model_path.is_file():
            raise FileNotFoundError(f"Fall-detection model not found: {self._model_path}")
        self._model = joblib.load(self._model_path)
        if not hasattr(self._model, "predict"):
            raise TypeError("The fall-detection model does not expose predict()")
        expected_features = getattr(self._model, "n_features_in_", len(FEATURE_NAMES))
        if int(expected_features) != len(FEATURE_NAMES):
            raise ValueError(
                f"Model expects {expected_features} features; {len(FEATURE_NAMES)} are required"
            )
        return True

    def persist_detection_setup(self):
        self._output_path = self._output_path.resolve()
        self._output_path.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._results_path = self._output_path / f"fall_detection_{timestamp}.jsonl"
        self._results_file = self._results_path.open(
            "w", encoding="utf-8", buffering=1
        )
        logger.info("Fall detections will be written to %s", self._results_path)
        return True

    def acquire_feature_packet_loop(self):
        packet = self._manager.get_packet(True, self._packet_timeout_s)
        if packet is None:
            logger.warning(
                "No FEATURES packet received for %.3f seconds; stopping",
                self._packet_timeout_s,
            )
            self._app.stop_application()
        return {"feature_packet": packet}

    def prepare_feature_vector_loop(self, feature_packet):
        if not isinstance(feature_packet, dict):
            raise TypeError("The WiFi manager returned a non-dictionary packet")
        missing = [name for name in FEATURE_NAMES if name not in feature_packet]
        if missing:
            raise ValueError("FEATURES packet is missing: " + ", ".join(missing))

        converted = {
            name: float(feature_packet[name])
            * (G_TO_MS2 if name in ACCELERATION_FEATURES else 1.0)
            for name in FEATURE_NAMES
        }
        prepared_packet = {
            "features": converted,
            "metadata": {
                "imuid": feature_packet.get("imuid", "UNKNOWN"),
                "campaign": feature_packet.get("cname", self._campaign_name),
                "nth": feature_packet.get("nth"),
                "ts": feature_packet.get("ts"),
            },
        }
        return {"prepared_packet": prepared_packet}

    def classify_fall_risk_loop(self, prepared_packet):
        features = prepared_packet["features"]
        dynamic_sma = features["dynamic_sma"]
        model_class = None
        confidence = None
        probabilities = None

        if dynamic_sma <= self._static_sma_threshold:
            label = "static (standing/sitting/lying)"
            branch = "static"
        else:
            branch = "dynamic"
            vector = np.asarray(
                [[features[name] for name in FEATURE_NAMES]], dtype=np.float64
            )
            model_class = int(self._model.predict(vector)[0])
            label = CLASS_LABELS.get(
                model_class, f"unknown_dynamic_class_{model_class}"
            )
            if hasattr(self._model, "predict_proba"):
                raw_probabilities = self._model.predict_proba(vector)[0]
                classes = getattr(
                    self._model, "classes_", range(len(raw_probabilities))
                )
                probabilities = {
                    CLASS_LABELS.get(int(class_id), str(int(class_id))): float(
                        probability
                    )
                    for class_id, probability in zip(classes, raw_probabilities)
                }
                confidence = float(np.max(raw_probabilities))

        detection_result = dict(prepared_packet["metadata"])
        detection_result.update(
            {
                "label": label,
                "branch": branch,
                "dynamic_sma": float(dynamic_sma),
            }
        )
        if model_class is not None:
            detection_result["model_class"] = model_class
        if confidence is not None:
            detection_result["confidence"] = confidence
        if probabilities is not None:
            detection_result["probabilities"] = probabilities
        return {"detection_result": detection_result}

    def persist_detection_loop(self, detection_result):
        json.dump(detection_result, self._results_file, ensure_ascii=False)
        self._results_file.write("\n")
        self._results_file.flush()
        logger.info(
            "[%s] nth=%s ts=%s SMA=%.6f -> %s%s",
            detection_result["imuid"],
            detection_result["nth"],
            detection_result["ts"],
            detection_result["dynamic_sma"],
            detection_result["label"],
            ""
            if "confidence" not in detection_result
            else f" (confidence={detection_result['confidence']:.3f})",
        )
        return {}

    def acquire_feature_packet_cleanup(self):
        try:
            if self._manager is not None:
                self._manager.stop_collection()
        finally:
            self._manager = None
            if self._peripherals_announced and hasattr(
                self._app, "notify_peripherals_released"
            ):
                self._app.notify_peripherals_released(self._imu_names)
                self._peripherals_announced = False
        return True

    def prepare_feature_vector_cleanup(self):
        return True

    def classify_fall_risk_cleanup(self):
        self._model = None
        return True

    def persist_detection_cleanup(self):
        if self._results_file is not None and not self._results_file.closed:
            self._results_file.flush()
            self._results_file.close()
        self._results_file = None
        return True

    def cleanup(self):
        return True
