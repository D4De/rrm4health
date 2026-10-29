"""Depth preprocessing matching the TensorFlow pipeline used during training."""

from __future__ import annotations

import numpy as np


class DepthPreprocessor:
    """Convert one SDT uint16 Depth frame into a MobileNetV2 input batch."""

    def __init__(self, output_size=64):
        self.output_size = int(output_size)
        if self.output_size < 1:
            raise ValueError("output_size must be positive")
        self._resize_cache = {}

    def _resize_coordinates(self, height, width):
        key = (height, width)
        cached = self._resize_cache.get(key)
        if cached is not None:
            return cached

        # TensorFlow tf.image.resize uses half-pixel centres for bilinear resize.
        y = (np.arange(self.output_size) + 0.5) * height / self.output_size - 0.5
        x = (np.arange(self.output_size) + 0.5) * width / self.output_size - 0.5
        y = np.clip(y, 0, height - 1)
        x = np.clip(x, 0, width - 1)
        y0 = np.floor(y).astype(np.intp)
        x0 = np.floor(x).astype(np.intp)
        y1 = np.minimum(y0 + 1, height - 1)
        x1 = np.minimum(x0 + 1, width - 1)
        wy = (y - y0).astype(np.float32)[:, None]
        wx = (x - x0).astype(np.float32)[None, :]
        cached = (y0, x0, y1, x1, wy, wx)
        self._resize_cache[key] = cached
        return cached

    def _resize_bilinear(self, image):
        height, width = image.shape
        y0, x0, y1, x1, wy, wx = self._resize_coordinates(height, width)
        return (
            image[y0[:, None], x0[None, :]] * (1.0 - wy) * (1.0 - wx)
            + image[y0[:, None], x1[None, :]] * (1.0 - wy) * wx
            + image[y1[:, None], x0[None, :]] * wy * (1.0 - wx)
            + image[y1[:, None], x1[None, :]] * wy * wx
        ).astype(np.float32, copy=False)

    def transform(self, depth_frame):
        """Return a float32 array with shape ``(1, 64, 64, 3)`` and range 0..1."""
        depth = np.asarray(depth_frame, dtype=np.float32)
        if depth.ndim != 2:
            raise ValueError(f"Expected a two-dimensional Depth frame, got {depth.shape}")

        valid = depth > 0.0
        normalized = np.zeros_like(depth, dtype=np.float32)
        if np.any(valid):
            valid_values = depth[valid]
            minimum = np.min(valid_values)
            scale = max(float(np.max(valid_values) - minimum), 1.0)
            normalized[valid] = (depth[valid] - minimum) / scale

        resized = np.clip(self._resize_bilinear(normalized), 0.0, 1.0)
        three_channels = np.repeat(resized[..., None], repeats=3, axis=-1)
        return three_channels[None, ...].astype(np.float32, copy=False)
