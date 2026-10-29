from enum import Enum
import time
import logging
from core.monitoring.MetricFields import MetricField
from policy.Policy import GlobalPolicyBase
from policy.Policy import LocalPolicyBase
from policy.Policy import safe_temperature
import platform
logger = logging.getLogger(__name__)

# Unique ID for the policy
# This is used to identify the policy in the system.
# It should be unique across all policies.
CLASSNAME = "PolicySymmetricDistribution"
class StatusField(str, Enum):
    """
    Enum for status fields used in by the policy, aggregated by the local policy and used by the global policy.
    """
    CPU_PERCENTAGE = "cpu_percentage"
    CPU_FREQUENCY = "cpu_frequency"
    MEMORY_USED_MB = "memory_used_mb"
    MEMORY_AVAILABLE_MB = "memory_available_mb"
    MEMORY_PERCENTAGE = "memory_percentage"
    DISK_USED = "disk_used"
    DISK_USED_GB = "disk_used_gb"
    DISK_AVAILABLE_GB = "disk_available_gb"
    BATTERY_PERCENTAGE = "battery_percentage"
    IS_CONNECTED_TO_POWER = "is_connected_to_power"
    POWER_CONSUMPTION_W = "power_consumption_w"
    DOWNLOAD_SPEED = "download_speed"
    UPLOAD_SPEED = "upload_speed"
    TEMPERATURE = "temperature"

# This is the list of required fields for the symmetric distribution policy.
# It includes the fields that are necessary for the policy to function correctly.
REQUIRED_FIELDS = []
class PolicySymmetricDistributionGlobal(GlobalPolicyBase):
    """    
    A global policy that implements the symmetric distribution strategy.
    It selects the best placement for partitions based on the current number of running partitions on each node.
    """
    @classmethod
    def name(cls):
        return CLASSNAME
    
    def get_required_fields(self):
        return REQUIRED_FIELDS
    
    def get_best_placement(self, graph, manifest):

        number_of_partitions = {
            node.get_nodeId(): node.get_number_of_running_partitions()
            for node in graph.values()
        }
        best_placement = None
        best_placement_cost = float('inf')
        best_config_id = -1

        for i, config in enumerate(manifest):
            temp_num_of_partition = number_of_partitions.copy()

            for partition in config["partitions"]:

                min_client_id = min(
                    temp_num_of_partition,
                    key=lambda cid: temp_num_of_partition[cid]
                )

                partition["node"] = min_client_id
                temp_num_of_partition[min_client_id] += 1 

            cost = self.__cost(temp_num_of_partition)
            if cost < best_placement_cost:
                best_placement = config
                best_placement_cost = cost
                best_config_id = i

        logger.debug(f"Best config index: {best_config_id}")
        return best_placement, best_config_id

    
    def __cost(self, temp_num_of_partition):

        max_partitions = max(temp_num_of_partition.values(), default=0)
        difference = sum(max_partitions - num_partitions for num_partitions in temp_num_of_partition.values())
        
        return difference


    def get_next_update_time(self, new_utilization, old_utilization):
        return 10 # always return 10 seconds for this policy

class PolicySymmetricDistributionLocal(LocalPolicyBase):
    """    A local policy that implements the aggregation logic of this policy.
    It updates the node status with the collected metrics and provides methods to reset the status and update process status.
    """

    def __init__(self):
        super().__init__()
        self.__status = {}
        self.__last_reset_time = time.time()
        self.__count = 0
        self.__last_bytes_sent = 0
        self.__last_bytes_recv = 0
        self.__last_measurement_time = time.time()

    @classmethod
    def name(cls):
        return CLASSNAME
    
    def update_node_status(self, collected_metrics):

        cpu_usage = collected_metrics.get(MetricField.CPU_PERCENTAGE, 0.0)
        cpu_freq = collected_metrics.get(MetricField.CPU_FREQUENCY, 0.0)
        memory_used_mb = collected_metrics.get(MetricField.MEMORY_USED_MB, 0.0)
        memory_available_mb = collected_metrics.get(MetricField.MEMORY_AVAILABLE_MB, 0.0)
        mem = collected_metrics.get(MetricField.MEMORY_PERCENTAGE, 0.0)
        disk_used_gb = collected_metrics.get(MetricField.DISK_USED_GB, 0.0)
        disk_available_gb = collected_metrics.get(MetricField.DISK_AVAILABLE_GB, 0.0)
        battery_percentage = collected_metrics.get(MetricField.BATTERY_PERCENTAGE, 0.0)
        is_connected_to_power = collected_metrics.get(MetricField.IS_CONNECTED_TO_POWER, True)
        power_consumption_w = collected_metrics.get(MetricField.POWER_CONSUMPTION_W, 0.0)
        network = collected_metrics.get(MetricField.NETWORK, {"bytes_sent": 0, "bytes_recv": 0})
        disk_usage = collected_metrics.get(MetricField.DISK_USED, 0.0)
        temperature = safe_temperature(collected_metrics.get(MetricField.TEMPERATURE, None))

        self.__count += 1
        
        # Calculate network speed from delta bytes
        current_time = time.time()
        
        if self.__count == 1:  # First measurement
            self.__last_bytes_sent = network["bytes_sent"]
            self.__last_bytes_recv = network["bytes_recv"]
            self.__last_measurement_time = current_time
            upload_speed = 0.0
            download_speed = 0.0
        else:
            # Calculate speed from byte deltas between measurements
            time_delta = current_time - self.__last_measurement_time
            bytes_sent_delta = network["bytes_sent"] - self.__last_bytes_sent
            bytes_recv_delta = network["bytes_recv"] - self.__last_bytes_recv
            
            upload_speed = bytes_sent_delta / time_delta if time_delta > 0 else 0.0
            download_speed = bytes_recv_delta / time_delta if time_delta > 0 else 0.0
            
            # Update last values for next calculation
            self.__last_bytes_sent = network["bytes_sent"]
            self.__last_bytes_recv = network["bytes_recv"]
            self.__last_measurement_time = current_time
        
        if platform.system() == "Darwin" or platform.system() == "Windows":
            temperature = None
        else:
            temperature = (self.__status.get(StatusField.TEMPERATURE.value, 0) * (self.__count - 1) + temperature) / self.__count
        
        self.__status = {
            StatusField.CPU_PERCENTAGE.value: (self.__status.get(StatusField.CPU_PERCENTAGE.value, 0) * (self.__count - 1) + cpu_usage)/ self.__count,
            StatusField.CPU_FREQUENCY.value: (self.__status.get(StatusField.CPU_FREQUENCY.value, 0) * (self.__count - 1) + cpu_freq) / self.__count,
            StatusField.BATTERY_PERCENTAGE.value: battery_percentage,
            StatusField.IS_CONNECTED_TO_POWER.value: is_connected_to_power,  # Current charging status (not averaged)
            StatusField.POWER_CONSUMPTION_W.value: power_consumption_w,
            #"battery depletion": (self.__status.get("battery depletion", 0) * (self.__count - 1) + (energy_full - psutil.sensors_battery().power_plugged)) / self.__count,
            StatusField.TEMPERATURE.value: temperature,
            StatusField.MEMORY_USED_MB.value: memory_used_mb,
            StatusField.MEMORY_AVAILABLE_MB.value: memory_available_mb,
            StatusField.DISK_USED.value: (self.__status.get(StatusField.DISK_USED.value, 0) * (self.__count - 1) + disk_usage) / self.__count,
            StatusField.DISK_USED_GB.value: disk_used_gb,
            StatusField.DISK_AVAILABLE_GB.value: disk_available_gb,
            StatusField.MEMORY_PERCENTAGE.value: (self.__status.get(StatusField.MEMORY_PERCENTAGE.value, 0) * (self.__count - 1) + mem) / self.__count,
            StatusField.UPLOAD_SPEED.value: (self.__status.get(StatusField.UPLOAD_SPEED.value, 0) * (self.__count - 1) + upload_speed) / self.__count,
            StatusField.DOWNLOAD_SPEED.value: (self.__status.get(StatusField.DOWNLOAD_SPEED.value, 0) * (self.__count - 1) + download_speed) / self.__count,
        }

        copy = self.__status.copy()

        return copy
    
    def reset_node_status(self):
        self.__last_reset_time = time.time()
        self.__count = 0
        self.__status = {}
        self.__last_bytes_sent = 0
        self.__last_bytes_recv = 0
        self.__last_measurement_time = time.time()