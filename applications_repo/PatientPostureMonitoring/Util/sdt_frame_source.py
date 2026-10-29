"""Sequential virtual Depth-camera source backed by the SDT real test split."""

from __future__ import annotations

import time
from pathlib import Path

import numpy as np
from PIL import Image


CLASS_NAMES = ("LYING", "SITTING", "STANDING", "EMPTY")


class DatasetExhausted(Exception):
    """Raised when a non-looping SDT source reaches its last frame."""


class SDTFrameSource:
    """Replay SDT Depth frames at a configurable camera-like frame rate."""

    def __init__(self, dataset_path, target_fps=5.0, loop_dataset=True):
        self.dataset_root = Path(dataset_path).expanduser().resolve()
        self.test_directory = self.dataset_root / "test"
        self.target_fps = float(target_fps)
        self.loop_dataset = bool(loop_dataset)
        if self.target_fps < 0:
            raise ValueError("target_fps must be greater than or equal to zero")
        self._period = 1.0 / self.target_fps if self.target_fps > 0 else 0.0
        self._labels = self._load_and_validate_dataset()
        self._index = 0
        self._next_deadline = None
        self.completed_cycles = 0

    @property
    def frame_count(self):
        return len(self._labels)

    @property
    def next_index(self):
        return self._index

    def _load_and_validate_dataset(self):
        labels_path = self.test_directory / "labels.txt"
        if not self.test_directory.is_dir():
            raise FileNotFoundError(f"SDT test directory not found: {self.test_directory}")
        if not labels_path.is_file():
            raise FileNotFoundError(f"SDT label file not found: {labels_path}")

        labels = []
        with labels_path.open(encoding="utf-8") as handle:
            for line_number, line in enumerate(handle, start=1):
                fields = line.strip().split(",")
                if len(fields) != 5:
                    raise ValueError(f"{labels_path}:{line_number}: expected 5 fields")
                try:
                    label = int(fields[0])
                except ValueError as error:
                    raise ValueError(
                        f"{labels_path}:{line_number}: invalid class {fields[0]!r}"
                    ) from error
                if label not in range(len(CLASS_NAMES)):
                    raise ValueError(f"{labels_path}:{line_number}: invalid class {label}")
                labels.append(label)
        if not labels:
            raise ValueError(f"SDT label file is empty: {labels_path}")

        missing = [
            self.test_directory / f"image_d_{index}.png"
            for index in range(len(labels))
            if not (self.test_directory / f"image_d_{index}.png").is_file()
        ]
        if missing:
            raise FileNotFoundError(
                f"Missing {len(missing)} SDT Depth frames; first missing file: {missing[0]}"
            )
        return tuple(labels)

    def _pace(self):
        if self._period == 0.0:
            return
        now = time.monotonic()
        if self._next_deadline is None:
            self._next_deadline = now
        delay = self._next_deadline - now
        if delay > 0:
            time.sleep(delay)
            now = time.monotonic()
        self._next_deadline += self._period
        if self._next_deadline < now - self._period:
            self._next_deadline = now + self._period

    def _read_depth(self, index):
        path = self.test_directory / f"image_d_{index}.png"
        with Image.open(path) as image:
            frame = np.asarray(image)
        if frame.shape != (480, 640):
            raise ValueError(f"Unexpected SDT frame shape {frame.shape} in {path}")
        if frame.ndim != 2 or np.any(frame < 0) or np.any(frame > 65535):
            raise ValueError(f"Invalid 16-bit grayscale SDT frame: {path}")
        return frame.astype(np.uint16, copy=False)

    def next_frame(self):
        """Return ``(depth_uint16, index, cycle, label)`` or raise DatasetExhausted."""
        if self._index >= self.frame_count:
            if not self.loop_dataset:
                raise DatasetExhausted("SDT test split completed")
            self._index = 0
            self.completed_cycles += 1
            self._next_deadline = None

        self._pace()
        index = self._index
        frame = self._read_depth(index)
        label = self._labels[index]
        self._index += 1
        return frame, index, self.completed_cycles, label
