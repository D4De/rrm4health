"""CNN activity recognition using one Wi-Fi IMU and the RRM task framework."""
import json
import logging
import math
import time
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr

LOGGER = logging.getLogger(__name__)
WINDOW_SIZE = 100
CHANNELS = ("ax", "ay", "az", "gx", "gy", "gz")
# Preserve the legacy server's non-overlapping window semantics.
# Source: imu_server(2).py (samples.clear() after each inference).

class ActivityRecognitionCNN:
    # FRAMEWORK EXECUTION FLOW:
    # 1. All setup methods are called in dependency order
    # 2. Loop methods are called in dependency levels (round-robin within each level)
    # 3. Cleanup methods are called in reverse order
    #
    # IMPORTANT: AppStarter performs comprehensive validation before execution:
    # - Method existence validation (all required setup/loop/cleanup methods must exist)
    # - Task dependency topological ordering with cycle detection
    # - Return type consistency (only dict or None allowed in loop methods)
    # - Always same dictionary structure returned inside the same methods
    # - Unique key production validation (keys can be reused across branches, but multiple tasks returning the same key cannot directly converge into the same consuming task)
    # - Parameter-production matching (all required parameters must be produced by other tasks)
    #
    # VARIABLE MANAGEMENT:
    # Define instance variables (self.variable_name) in setup methods for persistence.
    #
    # RETURN VALUE REQUIREMENTS:
    # Each loop method MUST return a dictionary (can be empty) with structure:
    # { key: value, ... }
    # - 'key': variable name to be used by dependent methods
    # - 'value': the actual data content
    # - All attributes needed by dependent tasks must be returned with exact matching names
    # - In case of unification (one taskY depends on multiple tasks) the attributes of taskY must be a sub-set of the attributes returned by the above tasks
    #
    # TASK EXECUTION LEVELS:
    # Tasks are organized by dependency levels. Higher levels execute before lower levels.
    # No execution order is guaranteed within the same level (parallel execution possible).
    # For your convenience, here is the task graph you defined in the JSON file:
    #
    # ┌───────────────────┐
    # │ setup_and_collect │
    # └───────────────────┘
    #           │
    #           │
    #           │
    #   ┌──────────────┐
    #   │ CNNInference │
    #   └──────────────┘
    #
    #
    # DO NOT MODIFY: this is needed for the correct functioning of the framework
    def set_framework(self, app, user_args=None):
        self._app = app  # this is the Application instance
        self._user_args = user_args

    # You have access to the following system methods via self._app:
    # - self._app.send_status(status): send device status updates to the RRM
    # - self._app.stop_application(): stop the application and inform the RRM
    #
    # The user_args are passed from by the user when starting the application and can be accessed via self._user_args.

    ## Setup methods

    def setup(self):
        # Common to both partitions: do not initialize Wi-Fi or TensorFlow here.
        # Each partition may run in a separate process/node.
        if not isinstance(self._user_args, dict):
            raise ValueError("user_args must be a dictionary")
        return True

    def setup_and_collect_setup(self):
        # Persistent acquisition state only on the collection partition.
        self.imu_manager = None
        self.samples = deque()
        self._collection_started = False
        args = self._user_args
        required = ("imuname", "imuaddress", "campaignname", "samplingfreq",
                    "wifi_interface", "wifi_ssid", "wifi_password")
        for key in required:
            value = args.get(key)
            if not isinstance(value, (str, int, float)) or not str(value).strip() or str(value).startswith("{{"):
                raise ValueError(f"Missing/invalid parameter: {key}")
        self.imu_name = str(args["imuname"]).strip()
        self.imu_address = str(args["imuaddress"]).strip()
        self.campaign_name = str(args["campaignname"]).strip()
        try:
            frequency = int(args["samplingfreq"])
            if float(args["samplingfreq"]) != frequency or frequency <= 0:
                raise ValueError
        except (TypeError, ValueError) as exc:
            raise ValueError("samplingfreq must be a positive integer") from exc
        self.sampling_frequency = frequency

        try:
            self.imu_manager = WifiAcquisitionMngr()
            self.imu_manager.set_imus({self.imu_name: self.imu_address})
            self.imu_manager.set_id_imus([self.imu_name])
            self.imu_manager.set_access_point(
                str(args["wifi_interface"]), str(args["wifi_ssid"]),
                str(args["wifi_password"])
            )
            self.imu_manager.set_campaign(self.campaign_name, self.sampling_frequency, raw=True)
            # Do not call wait_connection() here: its public API is unbounded,
            # and the framework declares a finite setup timeout.
            self.imu_manager.start_collection()
            self._collection_started = True
            return True
        except BaseException:
            self.setup_and_collect_cleanup()
            raise

    def CNNInference_setup(self):
        # Model assets are local to the inference partition, not the Wi-Fi partition.
        self.model = None
        self.mean = None
        self.std = None
        self.activity_names = None
        base = Path(__file__).resolve().parent
        model_file = base / "imu_activity_cnn.keras"
        mean_file = base / "imu_mean.npy"
        std_file = base / "imu_std.npy"
        labels_file = base / "activity_names.json"
        for asset in (model_file, mean_file, std_file, labels_file):
            if not asset.is_file():
                raise FileNotFoundError(f"Missing CNN artifact: {asset}")
        # Lazy import avoids requiring TensorFlow on a node running only acquisition.
        import tensorflow as tf
        self.model = tf.keras.models.load_model(str(model_file))
        self.mean = np.load(mean_file, allow_pickle=False)
        self.std = np.load(std_file, allow_pickle=False)
        with labels_file.open("r", encoding="utf-8") as source:
            self.activity_names = json.load(source)
        if not isinstance(self.activity_names, (dict, list)):
            raise ValueError("activity_names.json must contain a dict or list")
        if self.mean.ndim > 3 or self.std.ndim > 3:
            raise ValueError("Invalid normalizer dimensionality")
        # Validate that the normalizer broadcasts exactly to (1, 100, 6).
        for key, value in (("mean", self.mean), ("std", self.std)):
            try:
                shape = np.broadcast_shapes((1, WINDOW_SIZE, len(CHANNELS)), value.shape)
            except ValueError as exc:
                raise ValueError(f"{key} is incompatible with CNN input") from exc
            if shape != (1, WINDOW_SIZE, len(CHANNELS)):
                raise ValueError(f"{key} changes CNN input shape: {shape}")
            if not np.all(np.isfinite(value)):
                raise ValueError(f"{key} contains non-finite values")
        return True

    ## Loop methods

    @staticmethod
    def _decode_sensor(value):
        # Wi-Fi manager encodes 16-bit readings as unsigned 0x.... strings.
        # Keep values as produced by the manager; scaling/signedness is a
        # training/preprocessing contract that has NOT been provided.
        number = int(value, 16) if isinstance(value, str) and value.lower().startswith("0x") else float(value)
        if not math.isfinite(number):
            raise ValueError("Non-finite IMU reading")
        return float(number)

    def setup_and_collect_loop(self):
        # Fixed dict keys, even when 100 samples are not yet available.
        if self.imu_manager is None or not self._collection_started:
            return {"imu_window": None}
        # Loop budget below the descriptor's 5-second watchdog.
        deadline = time.monotonic() + 3.0
        try:
            while len(self.samples) < WINDOW_SIZE:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return {"imu_window": None}
                packet = self.imu_manager.get_packet(True, timeout=min(0.25, remaining))
                if packet is None:
                    continue
                if not isinstance(packet, dict) or packet.get("imuid") != self.imu_name:
                    continue
                if packet.get("ts") is None:
                    continue
                try:
                    row = [self._decode_sensor(packet[name]) for name in CHANNELS]
                except (KeyError, TypeError, ValueError, OverflowError) as exc:
                    LOGGER.warning("Discarding malformed Wi-Fi packet: %s", exc)
                    continue
                self.samples.append(row)
            window = list(self.samples)
            self.samples.clear()  # same non-overlapping policy as Flask original
            return {"imu_window": window}  # JSON-serializable across nodes
        except KeyboardInterrupt:
            self._app.stop_application()
            return {"imu_window": None}
        except Exception:
            LOGGER.exception("Wi-Fi RAW acquisition failed")
            self._app.stop_application()
            return {"imu_window": None}

    def CNNInference_loop(self, imu_window):
        if imu_window is None:
            return {}
        try:
            window = np.asarray(imu_window, dtype=np.float32)
            if window.shape != (WINDOW_SIZE, len(CHANNELS)) or not np.all(np.isfinite(window)):
                raise ValueError(f"Invalid IMU window shape/values: {window.shape}")
            batched = np.expand_dims(window, axis=0)
            normalized = (batched - self.mean) / (self.std + 1e-8)
            probabilities = np.asarray(self.model(normalized, training=False).numpy()[0])
            if probabilities.ndim != 1 or probabilities.size == 0 or not np.all(np.isfinite(probabilities)):
                raise ValueError("CNN returned invalid probabilities")
            index = int(np.argmax(probabilities))
            name = (self.activity_names[str(index)] if isinstance(self.activity_names, dict)
                    else self.activity_names[index])
            confidence = float(probabilities[index] * 100)
            prediction = {
                "status": "prediction",
                "activity": name,
                "confidence": round(confidence, 2),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            print("\n================================")
            print("       ACTIVITY DETECTED")
            print("================================")
            print(f"Activity   : {prediction['activity']}")
            print(f"Confidence : {prediction['confidence']:.2f}%")
            print(f"Timestamp  : {prediction['timestamp']}")
            print("================================\n")
            return {}
        except KeyboardInterrupt:
            self._app.stop_application()
            return {}
        except Exception:
            LOGGER.exception("CNN inference failed")
            self._app.stop_application()
            return {}

    ## Cleanup methods

    def setup_and_collect_cleanup(self):
        manager = getattr(self, "imu_manager", None)
        if manager is not None:
            try:
                # Manager owns its socket, asynchronous loop and worker thread.
                # Its stop_collection() performs STOP + disconnect + join.
                if getattr(self, "_collection_started", False):
                    manager.stop_collection()
            except Exception:
                LOGGER.exception("Error stopping Wi-Fi manager")
                return False
            finally:
                self._collection_started = False
                self.imu_manager = None
        if hasattr(self, "samples"):
            self.samples.clear()
        return True

    def CNNInference_cleanup(self):
        self.model = None
        self.mean = None
        self.std = None
        self.activity_names = None
        return True

    def cleanup(self):
        # No shared external resources are allocated by global setup.
        return True
