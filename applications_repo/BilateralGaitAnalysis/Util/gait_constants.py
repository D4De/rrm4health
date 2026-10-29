"""Shared constants and optional-runtime preparation for gait analysis."""

import os
from pathlib import Path
import tempfile


GAITMAP_SENSOR_COLUMNS = (
    "acc_x", "acc_y", "acc_z", "gyr_x", "gyr_y", "gyr_z",
)
DATASET_SENSOR_MAP = {
    "left_sensor": "l_instep",
    "right_sensor": "r_instep",
}


def prepare_numba_cache():
    """Configure a writable Numba cache for gaitmap's JIT-compiled code."""
    cache_dir = Path(tempfile.gettempdir()) / "rrm4health_numba_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("NUMBA_CACHE_DIR", str(cache_dir))
    return cache_dir
