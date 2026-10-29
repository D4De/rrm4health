from __future__ import annotations

import csv
from datetime import datetime, timezone
import logging
from pathlib import Path

from applications_repo.PatientPostureMonitoring.Util.sdt_frame_source import DatasetExhausted, SDTFrameSource
from applications_repo.PatientPostureMonitoring.Util.depth_preprocessing import DepthPreprocessor
from applications_repo.PatientPostureMonitoring.Util.tflite_classifier import TFLitePostureClassifier


logger = logging.getLogger(__name__)


def _parse_bool(value, parameter_name):
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().lower()
    if normalized in {"true", "1", "yes", "on"}:
        return True
    if normalized in {"false", "0", "no", "off"}:
        return False
    raise ValueError(f"{parameter_name} must be true or false, got {value!r}")


class PatientPostureMonitoring:
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
    #  ┌─────────────────────┐
    #  │ acquire_depth_frame │
    #  └─────────────────────┘
    #             │
    #             ││
    #              │
    # ┌────────────────────────┐
    # │ preprocess_depth_frame │
    # └────────────────────────┘
    #              │
    #              │
    #              │
    #    ┌──────────────────┐
    #    │ classify_posture │
    #    └──────────────────┘
    #              │
    #              │
    #              │
    # ┌────────────────────────┐
    # │ publish_posture_result │
    # └────────────────────────┘
    #
    #
    # DO NOT MODIFY: this is needed for the correct functioning of the framework
    def set_framework(self, app, user_args=None):
        self._app = app  # this is the Application instance
        self._user_args = user_args or {}

    # You have access to the following system methods via self._app:
    # - self._app.send_status(status): send device status updates to the RRM
    # - self._app.stop_application(): stop the application and inform the RRM
    #
    # The user_args are passed from by the user when starting the application and can be accessed via self._user_args.

    ## Setup methods

    def setup(self):
        # Global setup method called before any task-specific setup
        # Use this to initialize shared resources and instance variables
        # Return False to signal setup failure, otherwise return True or None
        self._dataset_path = self._user_args.get("dataset_path", "")
        if not str(self._dataset_path).strip():
            raise ValueError("dataset_path is required")
        try:
            self._target_fps = float(self._user_args.get("target_fps", 5))
        except (TypeError, ValueError) as error:
            raise ValueError("target_fps must be numeric") from error
        self._loop_dataset = _parse_bool(
            self._user_args.get("loop_dataset", True), "loop_dataset"
        )
        # These parameters are shared by task setup methods.  In a distributed
        # configuration the framework may initialize publish before classify.
        self._heavy_mode = _parse_bool(
            self._user_args.get("heavy_mode", False), "heavy_mode"
        )
        try:
            self._num_threads = int(self._user_args.get("num_threads", 4))
        except (TypeError, ValueError) as error:
            raise ValueError("num_threads must be an integer") from error
        self._output_path = Path(self._user_args.get("output_path", "output/"))
        self._source = None
        return True

    def acquire_depth_frame_setup(self):
        # Setup for task 'acquire_depth_frame'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        self._source = SDTFrameSource(
            dataset_path=self._dataset_path,
            target_fps=self._target_fps,
            loop_dataset=self._loop_dataset,
        )
        logger.info(
            "SDT virtual Depth source ready: %d frames at %.3f FPS (loop=%s)",
            self._source.frame_count,
            self._target_fps,
            self._loop_dataset,
        )
        return True

    def preprocess_depth_frame_setup(self):
        # Setup for task 'preprocess_depth_frame'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        self._depth_preprocessor = DepthPreprocessor(output_size=64)
        return True

    def classify_posture_setup(self):
        # Setup for task 'classify_posture'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        models_directory = Path(__file__).resolve().parent / "models"
        model_name = (
            "mobilenetv2_depth_float32.tflite"
            if self._heavy_mode
            else "mobilenetv2_depth_dynamic.tflite"
        )
        self._classifier = TFLitePostureClassifier(
            models_directory / model_name,
            num_threads=self._num_threads,
        )
        logger.info(
            "TFLite posture classifier ready: mode=%s, model=%s, threads=%d",
            "heavy" if self._heavy_mode else "light",
            model_name,
            self._num_threads,
        )
        return True

    def publish_posture_result_setup(self):
        # Setup for task 'publish_posture_result'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        self._output_path = self._output_path.expanduser().resolve()
        self._output_path.mkdir(parents=True, exist_ok=True)
        mode = "heavy" if self._heavy_mode else "light"
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        self._results_path = self._output_path / f"posture_{mode}_{timestamp}.csv"
        self._results_file = self._results_path.open(
            "w", newline="", encoding="utf-8"
        )
        self._results_writer = csv.DictWriter(
            self._results_file,
            fieldnames=[
                "timestamp_utc",
                "frame_index",
                "dataset_cycle",
                "reference_label",
                "posture_id",
                "posture",
                "confidence",
                "probability_lying",
                "probability_sitting",
                "probability_standing",
                "probability_empty",
                "inference_ms",
                "heavy_mode",
                "correct",
            ],
        )
        self._results_writer.writeheader()
        self._results_file.flush()
        logger.info("Posture results will be written to %s", self._results_path)
        return True

    ## Loop methods

    def acquire_depth_frame_loop(self):
        # Read the next 16-bit depth frame and its reference label from the SDT dataset
        # Task logic for 'acquire_depth_frame' goes here
        # TODO: Implement your logic and populate the return dictionary
        try:
            frame, frame_index, dataset_cycle, reference_label = self._source.next_frame()
        except DatasetExhausted:
            logger.info("SDT test split completed; requesting application stop")
            self._app.stop_application()
            return {
                "raw_depth_frame": None,
                "frame_index": None,
                "dataset_cycle": None,
                "reference_label": None,
            }
        return {
            "raw_depth_frame": frame,
            "frame_index": frame_index,
            "dataset_cycle": dataset_cycle,
            "reference_label": reference_label,
        }

    def preprocess_depth_frame_loop(self, raw_depth_frame, frame_index, dataset_cycle, reference_label):
        # Normalize valid depth values, resize to 64x64 and replicate the image to three channels
        # Task logic for 'preprocess_depth_frame' goes here
        # TODO: Implement your logic and populate the return dictionary
        if raw_depth_frame is None:
            return {
                "model_input": None,
                "frame_index": frame_index,
                "dataset_cycle": dataset_cycle,
                "reference_label": reference_label,
            }
        return {
            "model_input": self._depth_preprocessor.transform(raw_depth_frame),
            "frame_index": frame_index,
            "dataset_cycle": dataset_cycle,
            "reference_label": reference_label,
        }

    def classify_posture_loop(self, model_input, frame_index, dataset_cycle, reference_label):
        # Run the selected light or heavy TFLite MobileNetV2 model and classify patient posture
        # Task logic for 'classify_posture' goes here
        # TODO: Implement your logic and populate the return dictionary
        if model_input is None:
            return {"posture_result": None}
        posture_result = self._classifier.classify(model_input)
        posture_result.update(
            {
                "frame_index": frame_index,
                "dataset_cycle": dataset_cycle,
                "reference_label": reference_label,
                "heavy_mode": self._heavy_mode,
            }
        )
        return {"posture_result": posture_result}

    def publish_posture_result_loop(self, posture_result):
        # Publish the posture state and persist optional inference and timing metrics
        # Task logic for 'publish_posture_result' goes here
        # TODO: Implement your logic and populate the return dictionary
        if posture_result is None:
            return {}
        probabilities = posture_result["probabilities"]
        reference_label = posture_result["reference_label"]
        self._results_writer.writerow(
            {
                "timestamp_utc": datetime.now(timezone.utc).isoformat(),
                "frame_index": posture_result["frame_index"],
                "dataset_cycle": posture_result["dataset_cycle"],
                "reference_label": reference_label,
                "posture_id": posture_result["posture_id"],
                "posture": posture_result["posture"],
                "confidence": posture_result["confidence"],
                "probability_lying": probabilities[0],
                "probability_sitting": probabilities[1],
                "probability_standing": probabilities[2],
                "probability_empty": probabilities[3],
                "inference_ms": posture_result["inference_ms"],
                "heavy_mode": posture_result["heavy_mode"],
                "correct": int(posture_result["posture_id"] == reference_label),
            }
        )
        self._results_file.flush()

        logger.info(
            "Frame %s: predicted=%s confidence=%.4f reference=%s latency=%.3f ms",
            posture_result["frame_index"],
            posture_result["posture"],
            posture_result["confidence"],
            reference_label,
            posture_result["inference_ms"],
        )
        return {}

    ## Cleanup methods

    def acquire_depth_frame_cleanup(self):
        # Cleanup for task 'acquire_depth_frame'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        self._source = None
        return True

    def preprocess_depth_frame_cleanup(self):
        # Cleanup for task 'preprocess_depth_frame'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        self._depth_preprocessor = None
        return True

    def classify_posture_cleanup(self):
        # Cleanup for task 'classify_posture'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        if getattr(self, "_classifier", None) is not None:
            self._classifier.close()
        self._classifier = None
        return True

    def publish_posture_result_cleanup(self):
        # Cleanup for task 'publish_posture_result'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        results_file = getattr(self, "_results_file", None)
        if results_file is not None and not results_file.closed:
            results_file.flush()
            results_file.close()
        self._results_writer = None
        self._results_file = None
        return True

    def cleanup(self):
        # Global cleanup method called after all task-specific cleanup
        # Use this to release shared resources
        # Return False to signal cleanup failure, otherwise return True or None
        return True
