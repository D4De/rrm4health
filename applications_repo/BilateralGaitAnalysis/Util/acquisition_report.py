"""Per-window acquisition quality report written by the gait application."""

import csv
import logging
from pathlib import Path


logger = logging.getLogger(__name__)


class AcquisitionWindowReporter:
    """Write one acquisition-quality CSV row for every complete window."""

    FIELDS = (
        "window_index",
        "window_size_samples",
        "theoretical_duration_s",
        "actual_duration_s",
        "lost_packets",
        "sampling_frequency_hz",
    )

    def __init__(self, output_path):
        output_directory = Path(output_path).expanduser()
        output_directory.mkdir(parents=True, exist_ok=True)
        self.path = output_directory / "acquisition_windows.csv"
        # A run starts with a clean report: results from different acquisitions
        # must not be silently mixed just because they share an output directory.
        with self.path.open("w", newline="", encoding="utf-8") as csv_file:
            csv.DictWriter(csv_file, fieldnames=self.FIELDS).writeheader()

    def record(self, window):
        """Append metrics for a complete raw acquisition window and return it."""
        size = len(window["data"]["left_sensor"])
        rate = float(window["sampling_rate_hz"])
        row = {
            "window_index": int(window["window_index"]),
            "window_size_samples": size,
            "theoretical_duration_s": size / rate,
            "actual_duration_s": float(window["actual_duration_s"]),
            "lost_packets": int(window.get("lost_packets", 0)),
            "sampling_frequency_hz": rate,
        }
        with self.path.open("a", newline="", encoding="utf-8") as csv_file:
            csv.DictWriter(csv_file, fieldnames=self.FIELDS).writerow(row)
        logger.info(
            "[window=%s] acquisition CSV recorded: samples=%s lost_packets=%s "
            "sampling_rate_hz=%s",
            row["window_index"], row["window_size_samples"],
            row["lost_packets"], row["sampling_frequency_hz"],
        )
        return window
