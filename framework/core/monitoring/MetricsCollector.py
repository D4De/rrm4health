import os
from typing import List
import psutil
import platform
import time
import logging
import math
import threading
from collections import deque
from core.monitoring.MetricFields import MetricField, ProcessMetricField
from Config import METRICS_ERROR_VALUE, METRICS_MAX_CPU_PERCENT, CPU_HIGH_USAGE_THRESHOLD, CPU_MAX_USAGE_THRESHOLD

logger = logging.getLogger(__name__)

WINDOW_MEAN_COMPATIBLE_METRIC_FIELDS = {
    MetricField.NETWORK,
    MetricField.TEMPERATURE,
    MetricField.POWER_CONSUMPTION_W,
}

def get_battery_paths() -> List[str]:
    """
    Get potential battery information paths for different Linux distributions.
    Returns paths in order of likelihood.
    """
    base_paths = [
        '/sys/class/power_supply/BAT0',
        '/sys/class/power_supply/BAT1', 
        '/sys/class/power_supply/battery',
        '/sys/class/power_supply/CMB0',  # Some Chromebooks
        '/sys/class/power_supply/ADP0'   # Some systems
    ]
    
    battery_paths = []
    for base_path in base_paths:
        if os.path.exists(base_path):
            # Check for energy_full first, then charge_full
            for file_name in ['energy_full', 'charge_full', 'energy_now', 'charge_now']:
                full_path = os.path.join(base_path, file_name)
                if os.path.exists(full_path):
                    battery_paths.append(full_path)
    
    return battery_paths


def get_cpu_freq_paths(cpu_num: int = 0) -> List[str]:
    """
    Get potential CPU frequency paths for different Linux distributions.
    """
    paths = [
        f'/sys/devices/system/cpu/cpu{cpu_num}/cpufreq/scaling_cur_freq',
        f'/sys/devices/system/cpu/cpu{cpu_num}/cpufreq/cpuinfo_cur_freq',
        f'/sys/devices/system/cpu/cpu{cpu_num}/cpufreq/scaling_max_freq',
        '/proc/cpuinfo'
    ]
    
    return [path for path in paths if os.path.exists(path)]


def is_connected() -> bool:
    """
    Check if the system is connected to a power source.
    Works even if no battery is present (e.g., desktops or Raspberry Pi).
    """
    battery = psutil.sensors_battery()
    if battery is not None:
        return bool(battery.power_plugged)

    # No battery, check AC adapter presence
    ac_candidates = [
        "/sys/class/power_supply/AC/online",
        "/sys/class/power_supply/ADP0/online",
        "/sys/class/power_supply/ADP1/online"
    ]
    for ac_path in ac_candidates:
        if os.path.exists(ac_path):
            try:
                with open(ac_path, "r") as f:
                    return f.read().strip() == "1"
            except Exception:
                continue

    # Default: if no battery & no AC file → assume it's a powered device (True) otherwise it would not be on
    return True


def get_battery_energy_full() -> float:
    """Get battery energy capacity in mWh. Returns -1.0 if no battery present."""
    if psutil.sensors_battery() is None:
        return METRICS_ERROR_VALUE

    battery_paths = get_battery_paths()
    full_paths = [path for path in battery_paths if path.endswith(('energy_full', 'charge_full'))]
    
    for path in full_paths:
        try:
            with open(path, 'r') as f:
                value = int(f.read().strip())
                # Convert uWh to mWh or uAh to mAh
                return value / 1000
        except (FileNotFoundError, ValueError, PermissionError):
            continue
    
    return METRICS_ERROR_VALUE


class MetricsCollector:
    def __init__(self, architecture_flag: str = None, os_name: str = None):
        self._start_time = time.time()  # Used for calculating uptime
        self._temperature_sensor_cache = None  # Cache for temperature sensor
        self._last_battery_percent = None
        self._last_power_measurement_time = None
        self._battery_energy_full_mwh = get_battery_energy_full()
        self._os_name = (os_name or platform.system()).lower()
        self._architecture_flag = self._normalize_architecture_flag(architecture_flag or platform.machine())
        self._window_cache_samples = deque()
        self._window_cache_lock = threading.Lock()
        self._window_cache_retention_seconds = 300.0
        self._sampler_interval_seconds = 0.5
        self._sampler_stop_event = threading.Event()
        self._sampler_thread = None
        self._validate_field_map()
        self._start_window_sampler()

    def __del__(self):
        self._stop_window_sampler()

    def _validate_field_map(self):
        # Ensure that every MetricField is implemented in the field map
        missing_fields = [field for field in MetricField if field not in self._field_map()]
        if missing_fields:
            raise ValueError(f"The following MetricFields are not implemented in _field_map: {missing_fields}")

    def collect(self,
                fields: set[MetricField],
                mode: str = "instant",
                window_seconds: float = 0.0,
                sample_interval_seconds: float = 0.5) -> dict:
        """
        Collect metrics in one of two modes:
        - instant: single snapshot per metric
        - window: mean aggregation for metrics that support window averaging

        In window mode, fields that do not support mean aggregation are
        returned as instant-only values.

        Returns a dictionary of {field_name: value}
        """
        if not fields:
            return {}

        mode_normalized = str(mode or "instant").strip().lower()
        if mode_normalized == "window":
            return self._collect_window(
                fields=fields,
                window_seconds=window_seconds,
                sample_interval_seconds=sample_interval_seconds,
            )

        if mode_normalized != "instant":
            logger.warning(f"Unknown metrics collection mode '{mode}'. Falling back to instant mode.")

        return self._collect_instant(fields)

    def _collect_instant(self, fields: set[MetricField]) -> dict:
        result = {}

        for field in fields:
            func = self._field_map().get(field)
            if func:
                try:
                    result[field] = func()
                except Exception as e:
                    result[field] = f"Error: {e}"
            else:
                result[field] = "Unsupported field"

        return result

    def _collect_window(self,
                        fields: set[MetricField],
                        window_seconds: float,
                        sample_interval_seconds: float) -> dict:
        window_seconds = float(window_seconds or 0.0)
        sample_interval_seconds = float(sample_interval_seconds or 0.0)

        if window_seconds <= 0:
            logger.warning("Window mode requested with non-positive window_seconds. Falling back to instant mode.")
            return self._collect_instant(fields)

        if sample_interval_seconds <= 0:
            sample_interval_seconds = 0.5

        # Keep cache retention long enough for requested windows.
        self._ensure_window_sampler_config(sample_interval_seconds, window_seconds)

        instant_only_fields = {field for field in fields if field not in WINDOW_MEAN_COMPATIBLE_METRIC_FIELDS}
        window_fields = {field for field in fields if field in WINDOW_MEAN_COMPATIBLE_METRIC_FIELDS}

        result = {}

        # Keep instant-only metrics available even in window mode.
        if instant_only_fields:
            instant_values = self._collect_instant(instant_only_fields)
            for field, value in instant_values.items():
                result[field] = {
                    "mode": "instant_only",
                    "value": value,
                }

        if not window_fields:
            return result

        finished_at = time.time()
        started_at = finished_at - window_seconds
        sample_records = self._get_cached_window_samples(
            fields=window_fields,
            started_at=started_at,
            requested_interval_seconds=sample_interval_seconds,
        )

        if not sample_records:
            # Fallback if cache is still warming up.
            sample_records = [{
                "timestamp": time.time(),
                "values": self._collect_instant(window_fields),
            }]

        for field in window_fields:
            if field == MetricField.NETWORK:
                network_agg = self._aggregate_network_speed(sample_records)
                if network_agg is not None:
                    result[field] = {
                        "mode": "window",
                        "aggregation": "mean",
                        "value": network_agg,
                        "valid_samples": network_agg.get("valid_intervals", 0),
                        "total_samples": max(len(sample_records) - 1, 0),
                        "window_seconds": window_seconds,
                        "sample_interval_seconds": sample_interval_seconds,
                        "started_at": started_at,
                        "finished_at": finished_at,
                    }
                else:
                    result[field] = {
                        "mode": "instant_only",
                        "value": self._get_network_io(),
                    }
                continue

            numeric_values = []
            last_value = METRICS_ERROR_VALUE
            for sample_record in sample_records:
                sample_values = sample_record.get("values", {})
                if field in sample_values:
                    value = sample_values[field]
                    last_value = value
                    if self._is_valid_numeric_metric_value(value):
                        numeric_values.append(float(value))

            if numeric_values:
                mean_value = sum(numeric_values) / len(numeric_values)
                result[field] = {
                    "mode": "window",
                    "aggregation": "mean",
                    "value": round(mean_value, 4),
                    "valid_samples": len(numeric_values),
                    "total_samples": len(sample_records),
                    "window_seconds": window_seconds,
                    "sample_interval_seconds": sample_interval_seconds,
                    "started_at": started_at,
                    "finished_at": finished_at,
                }
            else:
                # Mean cannot be computed from valid numeric values.
                result[field] = {
                    "mode": "instant_only",
                    "value": last_value,
                }

        return result

    def _start_window_sampler(self):
        if self._sampler_thread and self._sampler_thread.is_alive():
            return
        self._sampler_thread = threading.Thread(
            target=self._window_sampler_loop,
            name="metrics-window-sampler",
            daemon=True,
        )
        self._sampler_thread.start()

    def _stop_window_sampler(self):
        self._sampler_stop_event.set()

    def _ensure_window_sampler_config(self, requested_interval_seconds: float, window_seconds: float):
        requested_interval_seconds = float(requested_interval_seconds or 0.5)
        if requested_interval_seconds > 0 and requested_interval_seconds < self._sampler_interval_seconds:
            self._sampler_interval_seconds = requested_interval_seconds

        requested_retention = max(float(window_seconds or 0.0) * 2.0, 300.0)
        if requested_retention > self._window_cache_retention_seconds:
            self._window_cache_retention_seconds = requested_retention

    def _window_sampler_loop(self):
        while not self._sampler_stop_event.is_set():
            sample_timestamp = time.time()
            sample_values = self._collect_instant(WINDOW_MEAN_COMPATIBLE_METRIC_FIELDS)
            with self._window_cache_lock:
                self._window_cache_samples.append({
                    "timestamp": sample_timestamp,
                    "values": sample_values,
                })
                self._prune_window_cache_locked(sample_timestamp)

            self._sampler_stop_event.wait(self._sampler_interval_seconds)

    def _prune_window_cache_locked(self, now: float):
        threshold = now - self._window_cache_retention_seconds
        while self._window_cache_samples and self._window_cache_samples[0]["timestamp"] < threshold:
            self._window_cache_samples.popleft()

    def _get_cached_window_samples(self,
                                   fields: set[MetricField],
                                   started_at: float,
                                   requested_interval_seconds: float) -> List[dict]:
        with self._window_cache_lock:
            selected = [
                sample for sample in self._window_cache_samples
                if sample["timestamp"] >= started_at
            ]

        if not selected:
            return []

        # Downsample cache points to approximate requested sampling interval.
        downsampled = []
        last_kept_timestamp = None
        for sample in selected:
            if last_kept_timestamp is None or (sample["timestamp"] - last_kept_timestamp) >= requested_interval_seconds:
                downsampled.append(sample)
                last_kept_timestamp = sample["timestamp"]

        if not downsampled and selected:
            downsampled = [selected[-1]]

        return [
            {
                "timestamp": sample["timestamp"],
                "values": {
                    field: sample["values"].get(field, METRICS_ERROR_VALUE)
                    for field in fields
                },
            }
            for sample in downsampled
        ]

    def _aggregate_network_speed(self, sample_records: List[dict]):
        if len(sample_records) < 2:
            return None

        upload_speeds = []
        download_speeds = []

        for previous, current in zip(sample_records, sample_records[1:]):
            prev_values = previous.get("values", {})
            curr_values = current.get("values", {})
            prev_network = prev_values.get(MetricField.NETWORK)
            curr_network = curr_values.get(MetricField.NETWORK)

            if not isinstance(prev_network, dict) or not isinstance(curr_network, dict):
                continue

            prev_sent = prev_network.get("bytes_sent")
            prev_recv = prev_network.get("bytes_recv")
            curr_sent = curr_network.get("bytes_sent")
            curr_recv = curr_network.get("bytes_recv")
            dt = float(current.get("timestamp", 0.0)) - float(previous.get("timestamp", 0.0))

            if dt <= 0:
                continue

            if all(isinstance(v, (int, float)) for v in (prev_sent, curr_sent)):
                upload_speeds.append(max((float(curr_sent) - float(prev_sent)) / dt, 0.0))

            if all(isinstance(v, (int, float)) for v in (prev_recv, curr_recv)):
                download_speeds.append(max((float(curr_recv) - float(prev_recv)) / dt, 0.0))

        if not upload_speeds and not download_speeds:
            return None

        upload_mean = (sum(upload_speeds) / len(upload_speeds)) if upload_speeds else 0.0
        download_mean = (sum(download_speeds) / len(download_speeds)) if download_speeds else 0.0

        return {
            "upload_speed": round(upload_mean, 4),
            "download_speed": round(download_mean, 4),
            "unit": "B/s",
            "valid_intervals": min(len(upload_speeds), len(download_speeds)) if upload_speeds and download_speeds else max(len(upload_speeds), len(download_speeds)),
        }

    @staticmethod
    def _is_valid_numeric_metric_value(value) -> bool:
        if isinstance(value, bool):
            return False
        if not isinstance(value, (int, float)):
            return False
        if value == METRICS_ERROR_VALUE:
            return False
        if not math.isfinite(float(value)):
            return False
        return True

    def _field_map(self) -> dict:
        disk_path = self._get_disk_root_path()
        return {
            MetricField.CPU_PERCENTAGE: lambda: min(psutil.cpu_percent(interval=None), METRICS_MAX_CPU_PERCENT),
            MetricField.CPU_FREQUENCY: self._get_cpu_frequency,
            MetricField.MEMORY_PERCENTAGE: lambda: psutil.virtual_memory().percent,
            MetricField.MEMORY_USED_MB: lambda: round((psutil.virtual_memory().total - psutil.virtual_memory().available) / (1024 * 1024), 2),
            MetricField.MEMORY_AVAILABLE_MB: lambda: round(psutil.virtual_memory().available / (1024 * 1024), 2),
            MetricField.DISK_USED: lambda: psutil.disk_usage(disk_path).percent,
            MetricField.DISK_USED_GB: lambda: round(psutil.disk_usage(disk_path).used / (1024 * 1024 * 1024), 2),
            MetricField.DISK_AVAILABLE_GB: lambda: round(psutil.disk_usage(disk_path).free / (1024 * 1024 * 1024), 2),
            MetricField.BATTERY_PERCENTAGE: lambda: psutil.sensors_battery().percent if psutil.sensors_battery() else METRICS_ERROR_VALUE,
            MetricField.NETWORK: self._get_network_io,
            MetricField.TEMPERATURE: self._get_temperature,
            MetricField.POWER_CONSUMPTION_W: self._get_system_power_consumption,
            MetricField.ARCHITECTURE: lambda: self._architecture_flag,
            MetricField.N_CORES: lambda: psutil.cpu_count(logical=False),
            MetricField.MAX_FREQ: self._get_cpu_max_frequency,
            MetricField.UPTIME: lambda: int(time.time() - self._start_time),
            MetricField.MEMORY_TOTAL: lambda: psutil.virtual_memory().total,
            MetricField.DISK_TOTAL: lambda: psutil.disk_usage(disk_path).total,
            MetricField.BATTERY_ENERGY_FULL: get_battery_energy_full,
            MetricField.IS_CONNECTED_TO_POWER: is_connected  
        }

    @staticmethod
    def _normalize_architecture_flag(architecture_value: str) -> str:
        value = str(architecture_value or "").lower()
        if value in ("aarch64", "arm64", "armv8", "armv8l"):
            return "arm64"
        if value in ("armv7l", "armv7", "arm", "armhf"):
            return "arm"
        if value in ("x86_64", "amd64"):
            return "x86_64"
        if value in ("x86", "i386", "i686"):
            return "x86"
        return value or "unknown"

    def _get_disk_root_path(self) -> str:
        if self._os_name.startswith("win"):
            return os.environ.get("SystemDrive", "C:") + "\\"
        return "/"

    @staticmethod
    def _get_cpu_frequency() -> float:
        freq = psutil.cpu_freq()
        return MetricsCollector._normalize_frequency_mhz(freq.current if freq else None)

    @staticmethod
    def _get_cpu_max_frequency() -> float:
        freq = psutil.cpu_freq()
        return MetricsCollector._normalize_frequency_mhz(freq.max if freq else None)

    @staticmethod
    def _normalize_frequency_mhz(value) -> float:
        """Normalize frequency values to MHz.

        Heuristics:
        - values in (0, 20) are assumed GHz and converted to MHz
        - very large values (>100000) are assumed KHz and converted to MHz
        - otherwise values are treated as MHz
        """
        try:
            if value is None:
                return METRICS_ERROR_VALUE
            freq_value = float(value)
            if not math.isfinite(freq_value) or freq_value <= 0:
                return METRICS_ERROR_VALUE
            if freq_value < 20.0:
                freq_value *= 1000.0
            elif freq_value > 100000.0:
                freq_value /= 1000.0
            return round(freq_value, 3)
        except Exception:
            return METRICS_ERROR_VALUE
    
    def _get_temperature(self):
        if self._os_name.startswith("win"):
            return self._get_temperature_windows()
        if self._os_name == "darwin":
            return self._get_temperature_macos()
        return self._get_temperature_linux()

    def _get_temperature_linux(self):
        # Use cached sensor if available
        if self._temperature_sensor_cache is not None:
            try:
                return self._temperature_sensor_cache.current
            except (AttributeError, OSError):
                # Cache invalidated, recalculate
                self._temperature_sensor_cache = None
        
        # Find and cache sensor
        temps = psutil.sensors_temperatures()
        for sensor_group in temps.values():
            if sensor_group:
                self._temperature_sensor_cache = sensor_group[0]
                return sensor_group[0].current

        thermal_zone = "/sys/class/thermal/thermal_zone0/temp"
        if os.path.exists(thermal_zone):
            try:
                with open(thermal_zone, "r", encoding="utf-8") as file_obj:
                    temp_raw = float(file_obj.read().strip())
                return temp_raw / 1000.0
            except Exception:
                pass

        return METRICS_ERROR_VALUE

    def _get_temperature_windows(self):
        try:
            temps = psutil.sensors_temperatures()
            for sensor_group in temps.values():
                if sensor_group:
                    return sensor_group[0].current
        except Exception:
            pass
        return METRICS_ERROR_VALUE

    def _get_temperature_macos(self):
        try:
            temps = psutil.sensors_temperatures()
            for sensor_group in temps.values():
                if sensor_group:
                    return sensor_group[0].current
        except Exception:
            pass
        return METRICS_ERROR_VALUE

    def _get_network_io(self) -> dict:
        io = psutil.net_io_counters()
        return {
            "bytes_sent": io.bytes_sent,
            "bytes_recv": io.bytes_recv
        }

    def _get_system_power_consumption(self) -> float:
        if self._architecture_flag in ("arm64", "arm"):
            return self.get_power_rpi()
        if self._architecture_flag in ("x86_64", "x86"):
            return self.get_power_intel()
        return self._get_generic_power()

    def get_power_rpi(self) -> float:
        return self._get_generic_power()

    def get_power_intel(self) -> float:
        return self._get_generic_power()

    # Explicit aliases requested by architecture-specific design notes.
    def getPowerRPI(self) -> float:
        return self.get_power_rpi()

    def getPowerIntel(self) -> float:
        return self.get_power_intel()

    def _get_generic_power(self) -> float:
        """Estimate system power consumption in Watts from battery discharge trend.

        Priority:
        1) Read direct power telemetry from sysfs if available (power_now/current_now*voltage_now).
        2) Estimate from battery discharge trend.
        3) Fallback to CPU-based estimate to avoid constant 0 on AC/no-battery systems.
        """
        direct_power_w = self._read_sysfs_power_watts()
        if direct_power_w is not None:
            return direct_power_w

        battery = psutil.sensors_battery()
        now = time.time()

        if battery is None:
            return self._estimate_power_from_cpu()

        if battery.power_plugged:
            self._last_battery_percent = battery.percent
            self._last_power_measurement_time = now
            return self._estimate_power_from_cpu()

        if self._battery_energy_full_mwh in (None, METRICS_ERROR_VALUE) or self._battery_energy_full_mwh <= 0:
            return self._estimate_power_from_cpu()

        if self._last_battery_percent is None or self._last_power_measurement_time is None:
            self._last_battery_percent = battery.percent
            self._last_power_measurement_time = now
            return self._estimate_power_from_cpu()

        delta_time_s = now - self._last_power_measurement_time
        if delta_time_s <= 0:
            return self._estimate_power_from_cpu()

        delta_percent = self._last_battery_percent - battery.percent
        self._last_battery_percent = battery.percent
        self._last_power_measurement_time = now

        if delta_percent <= 0:
            return self._estimate_power_from_cpu()

        consumed_mwh = self._battery_energy_full_mwh * (delta_percent / 100.0)
        consumed_wh = consumed_mwh / 1000.0
        hours = delta_time_s / 3600.0
        if hours <= 0:
            return self._estimate_power_from_cpu()

        return max(round(consumed_wh / hours, 3), 0.0)

    def _read_sysfs_power_watts(self):
        """Try to read instantaneous power from Linux power_supply sysfs."""
        power_supply_root = "/sys/class/power_supply"
        if not os.path.isdir(power_supply_root):
            return None

        candidates = [
            "BAT0", "BAT1", "battery", "CMB0",
        ]

        for dev in candidates:
            dev_path = os.path.join(power_supply_root, dev)
            if not os.path.isdir(dev_path):
                continue

            power_now = os.path.join(dev_path, "power_now")
            if os.path.exists(power_now):
                try:
                    # Usually microwatts (uW)
                    with open(power_now, "r", encoding="utf-8") as file_obj:
                        value_uw = float(file_obj.read().strip())
                    value_w = abs(value_uw) / 1_000_000.0
                    if value_w > 0:
                        return round(value_w, 3)
                except Exception:
                    pass

            current_now = os.path.join(dev_path, "current_now")
            voltage_now = os.path.join(dev_path, "voltage_now")
            if os.path.exists(current_now) and os.path.exists(voltage_now):
                try:
                    # Usually current in uA and voltage in uV
                    with open(current_now, "r", encoding="utf-8") as current_obj:
                        curr_ua = float(current_obj.read().strip())
                    with open(voltage_now, "r", encoding="utf-8") as voltage_obj:
                        volt_uv = float(voltage_obj.read().strip())
                    value_w = abs((curr_ua / 1_000_000.0) * (volt_uv / 1_000_000.0))
                    if value_w > 0:
                        return round(value_w, 3)
                except Exception:
                    pass

        return None

    def _estimate_power_from_cpu(self) -> float:
        """Heuristic fallback when direct power telemetry is unavailable."""
        try:
            cpu_percent = float(psutil.cpu_percent(interval=None))
            freq = psutil.cpu_freq()
            freq_ratio = 1.0
            if freq and freq.max and freq.current and freq.max > 0:
                freq_ratio = max(min(float(freq.current) / float(freq.max), 1.0), 0.3)

            # Conservative defaults: keep positive and plausible on laptops/SBC.
            base_w = 3.0
            dynamic_w = 22.0 * (cpu_percent / 100.0) * freq_ratio
            return round(max(base_w + dynamic_w, 0.0), 3)
        except Exception:
            return 0.0


class ProcessMetricsCollector:
    def __init__(self):
        self._start_time = time.time()
        self.__processes = {} 
        self._validate_field_map()
        
        # Initialize energy tracking
        battery = psutil.sensors_battery()
        if battery:
            battery_energy_full = get_battery_energy_full()
            self.__energy_start = (battery.percent / 100.0) * battery_energy_full  # in mWh
        else:
            self.__energy_start = METRICS_ERROR_VALUE  # No battery present

    def _validate_field_map(self):
        missing_fields = [field for field in ProcessMetricField if field not in self._field_map(os.getpid())]
        if missing_fields:
            raise ValueError(f"Missing implementations for: {missing_fields}")

    def collect(self, fields: set[ProcessMetricField], pid) -> dict:
        result = {}
        
        for field in fields:
            func = self._field_map(pid).get(field)
            if func:
                try:
                    value = func()
                    result[field] = value
                except Exception as e:
                    result[field] = METRICS_ERROR_VALUE
            else:
                result[field] = METRICS_ERROR_VALUE
        return result

    def _field_map(self, pid) -> dict:
        if pid not in self.__processes.keys():
            try:
                process = psutil.Process(pid)
                self.__processes[pid] = process
            except psutil.NoSuchProcess:
                logger.warning(f"Process with PID {pid} does not exist")
                return {"error": f"Process with PID {pid} does not exist."}
        process = self.__processes[pid]

        def get_process_core_freq():
            """
            Get frequency that matches htop's display for process CPU frequency.
            Uses multiple sampling methods to get the most accurate reading.
            """
            try:
                cpu_percent = process.cpu_percent(interval=None)
                is_linux = platform.system().lower() == "linux"
                
                # Method 1: Read /proc/cpuinfo
                if is_linux:
                    try:
                        current_core = process.cpu_num()
                        if os.path.exists('/proc/cpuinfo'):
                            with open('/proc/cpuinfo', 'r') as f:
                                content = f.read()
                                cpu_mhz_lines = [line for line in content.split('\n') if 'cpu MHz' in line]
                                if cpu_mhz_lines and current_core < len(cpu_mhz_lines):
                                    freq_mhz = float(cpu_mhz_lines[current_core].split(':')[1].strip())
                                    return freq_mhz
                    except Exception as e:
                        logger.warning(f"Failed to read /proc/cpuinfo: {e}")
                
                # Method 2: Try scaling_cur_freq
                if is_linux:
                    try:
                        current_core = process.cpu_num()
                        freq_paths = get_cpu_freq_paths(current_core)
                        priority_paths = [path for path in freq_paths if 'cur_freq' in path]
                        for freq_path in priority_paths:
                            if os.path.exists(freq_path):
                                try:
                                    with open(freq_path, 'r') as f:
                                        freq_khz = int(f.read().strip())
                                        freq_mhz = freq_khz / 1000.0
                                        return freq_mhz
                                except (ValueError, IOError):
                                    continue
                    except Exception as e:
                        logger.warning(f"Failed to read scaling_cur_freq: {e}")
                
                # Method 3: psutil per-core
                current_core = process.cpu_num()
                freqs = psutil.cpu_freq(percpu=True)
                
                if freqs and current_core < len(freqs) and freqs[current_core].current:
                    current_core_freq = freqs[current_core].current
                    
                    if cpu_percent > CPU_MAX_USAGE_THRESHOLD and freqs[current_core].max:
                        max_freq = freqs[current_core].max
                        return max_freq
                    
                    return current_core_freq
                
                # Method 4: affinity average
                if hasattr(process, 'cpu_affinity'):
                    cpu_affinity = process.cpu_affinity()
                    if freqs and cpu_affinity:
                        accessible_freqs = [freqs[i].current for i in cpu_affinity if i < len(freqs) and freqs[i].current]
                        if accessible_freqs:
                            if cpu_percent > CPU_HIGH_USAGE_THRESHOLD:
                                max_freq = max(accessible_freqs)
                                return max_freq
                            else:
                                avg_freq = sum(accessible_freqs) / len(accessible_freqs)
                                return avg_freq
                
                system_freq = psutil.cpu_freq()
                if system_freq and system_freq.current:
                    return system_freq.current
                    
                return METRICS_ERROR_VALUE
                
            except Exception as e:
                logger.warning(f"Error getting process core frequency for PID {pid}: {e}")
                return METRICS_ERROR_VALUE

        def estimate_process_power():
            """
            Estimate power consumption for a specific process.
            Returns power in Watts, or -1.0 if estimation is not possible.
            If device is connected to power, returns 0.0.
            """
            try:
                # If device is connected to power, power usage estimate should be 0
                if is_connected():
                    return 0.0
                
                if self.__energy_start == METRICS_ERROR_VALUE:
                    return 0.0  # No battery to estimate from
                
                system_cpu_percent = psutil.cpu_percent(interval=0.1)
                process_cpu_percent = process.cpu_percent(interval=None)
                
                if system_cpu_percent <= 0:
                    return 0.0
                
                battery = psutil.sensors_battery()
                if not battery:
                    return 0.0
                
                energy_now = battery.percent * get_battery_energy_full() / 100.0  # in mWh
                
                total_energy_consumed = self.__energy_start - energy_now
                time_elapsed = time.time() - self._start_time
                system_power_estimate = (total_energy_consumed / (time_elapsed / 3600.0)) / 1000.0
                cpu_ratio = min(process_cpu_percent / system_cpu_percent, 1.0)
                return max(system_power_estimate * cpu_ratio, 0.0)
                
            except Exception as e:
                logger.warning(f"Power estimation error for PID {pid}: {e}")
                return 0.0

        return {
            ProcessMetricField.CPU_PERCENTAGE: lambda: min(process.cpu_percent(interval=None), METRICS_MAX_CPU_PERCENT),
            ProcessMetricField.CORE_AVG_FREQUENCY: get_process_core_freq,
            ProcessMetricField.POWER_USAGE_WATTS: lambda: estimate_process_power(),
        }
