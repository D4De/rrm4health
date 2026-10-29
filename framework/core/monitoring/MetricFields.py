from enum import Enum

class MetricField(str, Enum):
    CPU_PERCENTAGE = "cpu_percentage"
    CPU_FREQUENCY = "cpu_frequency"
    MEMORY_PERCENTAGE = "memory_percentage"
    MEMORY_USED_MB = "memory_used_mb"
    MEMORY_AVAILABLE_MB = "memory_available_mb"
    DISK_USED = "disk_used"
    DISK_USED_GB = "disk_used_gb"
    DISK_AVAILABLE_GB = "disk_available_gb"
    BATTERY_PERCENTAGE = "battery_percentage"
    NETWORK = "network"
    TEMPERATURE = "temperature"
    POWER_CONSUMPTION_W = "power_consumption_w"
    ARCHITECTURE = "architecture"
    N_CORES = "n_cores"
    MAX_FREQ = "max_freq"
    UPTIME = "uptime"
    MEMORY_TOTAL = "memory_total"
    DISK_TOTAL = "disk_total"
    BATTERY_ENERGY_FULL = "battery_energy_full"
    IS_CONNECTED_TO_POWER = "is_connected_to_power"

class ProcessMetricField(str, Enum):
    CPU_PERCENTAGE = "cpu_percentage"
    CORE_AVG_FREQUENCY = "core_avg_frequency"
    POWER_USAGE_WATTS = "power_usage_estimate" 