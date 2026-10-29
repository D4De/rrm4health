"""TFLite posture classifier shared by the light and heavy execution modes."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np


CLASS_NAMES = ("LYING", "SITTING", "STANDING", "EMPTY")


def _interpreter_class():
    try:
        from tflite_runtime.interpreter import Interpreter
    except ImportError:
        import tensorflow as tf

        Interpreter = tf.lite.Interpreter
    return Interpreter


class TFLitePostureClassifier:
    """Load one MobileNetV2 TFLite model and reuse its interpreter."""

    def __init__(self, model_path, num_threads=4):
        self.model_path = Path(model_path).expanduser().resolve()
        self.num_threads = int(num_threads)
        if self.num_threads < 1:
            raise ValueError("num_threads must be at least 1")
        if not self.model_path.is_file():
            raise FileNotFoundError(f"TFLite model not found: {self.model_path}")

        Interpreter = _interpreter_class()
        self.interpreter = Interpreter(
            model_path=str(self.model_path), num_threads=self.num_threads
        )
        self.interpreter.allocate_tensors()
        inputs = self.interpreter.get_input_details()
        outputs = self.interpreter.get_output_details()
        if len(inputs) != 1 or len(outputs) != 1:
            raise ValueError("The posture model must expose one input and one output")
        self.input = inputs[0]
        self.output = outputs[0]
        if tuple(self.input["shape"]) != (1, 64, 64, 3):
            raise ValueError(f"Unexpected TFLite input shape: {self.input['shape']}")
        if self.input["dtype"] != np.float32 or self.output["dtype"] != np.float32:
            raise ValueError("The selected model must use float32 input and output")

    def classify(self, model_input):
        tensor = np.asarray(model_input, dtype=np.float32)
        started_ns = time.perf_counter_ns()
        self.interpreter.set_tensor(self.input["index"], tensor)
        self.interpreter.invoke()
        probabilities = self.interpreter.get_tensor(self.output["index"])[0]
        inference_ms = (time.perf_counter_ns() - started_ns) / 1_000_000.0
        class_id = int(np.argmax(probabilities))
        return {
            "posture_id": class_id,
            "posture": CLASS_NAMES[class_id],
            "confidence": float(probabilities[class_id]),
            "probabilities": [float(value) for value in probabilities],
            "inference_ms": inference_ms,
        }

    def close(self):
        self.interpreter = None
