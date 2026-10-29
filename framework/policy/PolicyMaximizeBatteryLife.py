from enum import Enum
from itertools import permutations
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
CLASSNAME = "PolicyMaximizeBatteryLife"
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

# This is the list of required fields for the maximize battery life policy.
# It includes the fields that are necessary for the policy to function correctly.
REQUIRED_FIELDS = [
    MetricField.CPU_PERCENTAGE,
    MetricField.MEMORY_PERCENTAGE,
    MetricField.BATTERY_PERCENTAGE,
    MetricField.IS_CONNECTED_TO_POWER,
    MetricField.TEMPERATURE,
    MetricField.NETWORK
]
class PolicyMaximizeBatteryLifeGlobal(GlobalPolicyBase):
    """
    This policy aims to maximize the battery life of the system by minimizing the imbalance 
    in expected battery status after running the partitions.
    
    The policy also enforces node limits including:
    - Maximum temperature (from board info)
    - Maximum network speed (from board info)  
    - CPU usage limits (100%)
    - Memory usage limits (100%)
    - Battery depletion limits (>= 0%)
    """
    @classmethod
    def name(cls):
        return CLASSNAME
    
    def __init__(self):
        super().__init__()
         # next_update_time 
        self.__MIN_UPDATE_PERIOD = 1  # seconds
        self.__MAX_UPDATE_PERIOD = 10  # seconds
        self.__slope = 0.1
        self.__last_update_time = time.time()

    def get_required_fields(self):
        return REQUIRED_FIELDS
    
    def get_best_placement(self, graph, manifest):
        # TODO test this policy
        # We choose the configuration and placement that minimizes the battery cost.
        # The battery cost is defined as the imbalance in expected battery status after running the partitions. (After a period?? after all the app)
        # For now we enumerate all the configurations that do not exceed over the limits and return the one with the lowest cost.
        # This works with the assumption that apps are started sequentially with enough time between starts so that the node status can be update before the next start.
        nodes_status = {node.get_nodeId(): node.get_status() for node in graph.values()}
        
        best_placement_cost = float('inf')
        best_placement = None
        best_config_id = None
        
        for i, config in enumerate(manifest):
            for perm in permutations(nodes_status.keys(), len(config["partitions"])):
                valid = True
                nodes_copy = nodes_status.copy()
                
                for j, partition in enumerate(config["partitions"]):
                    required_resources = partition.get("required_resources", {}) # Dictionary containing the required resources for this partition
                    if not required_resources:
                        raise ValueError("Manifest does not contain required_resources field.")
                    logger.debug(f"required_resources: {required_resources}")
                    node_id = perm[j]
                    node = graph[node_id]
                    partition_id = partition["id"]
                    
                    logger.debug(f"Checking placement of partition {partition_id} on node {node_id}")
                    logger.debug(f"Node status: {nodes_copy[node_id]}")
                    
                    required_res = required_resources
                    current_status = nodes_status[node_id]
                    
                    # Check resource limits and board info constraints
                    if not self._check_node_limits(node, current_status, required_res):
                        valid = False
                        break
                    
                    # Update the node status with the expected status after running the partition
                    nodes_copy[node_id] = {
                        "battery": current_status.get("battery", 100) - required_res.get("battery", 0),
                        "is_connected_to_power": current_status.get("is_connected_to_power", False),
                        "cpu": current_status.get("cpu", 0) + required_res.get("cpu", 0),
                        "temp": current_status.get("temp", 0) + required_res.get("temp", 0),
                        "network": current_status.get("network", 0) + required_res.get("network", 0),
                        "memory": current_status.get("memory", 0) + required_res.get("memory", 0)
                    }

                if valid:
                    cost = self.__cost(nodes_copy, perm, config["partitions"])

                    if cost < best_placement_cost:
                        best_placement = perm
                        best_placement_cost = cost
                        best_config_id = i
        
        # compile the best placement configuration
        if best_placement_cost == float('inf'):
            raise ValueError("No valid placement found in the manifest.")
        best_config = manifest[best_config_id]
        for j, partition in enumerate(best_config["partitions"]):
            partition["node"] = best_placement[j]
        return best_config, best_config_id
    
    def _check_node_limits(self, node, current_status, required_resources):
        """
        Check if placing a partition on a node would respect all node limits,
        including board info constraints like max temperature and max network speed.
        Also considers charging status for battery conservation.
        
        Args:
            node: Node object containing board info and other node data
            current_status: Current resource utilization of the node
            required_resources: Required resources for the partition to be placed
            
        Returns:
            bool: True if placement is valid, False if it violates any limits
        """
        try:
            # Validate inputs
            if not node or not isinstance(current_status, dict) or not isinstance(required_resources, dict):
                logger.warning("Invalid input parameters for node limit check")
                return False
            
            # Check charging status - if not charging and battery is low, be more conservative
            is_charging = current_status.get("is_connected_to_power", False)
            current_battery = current_status.get("battery", 100)
            required_battery = required_resources.get("battery", 0)
            
            # If device is connected to power, battery usage is 0 (no depletion)
            actual_battery_usage = 0 if is_charging else required_battery
            projected_battery = current_battery - actual_battery_usage
            
            # If not charging and battery is low, apply stricter limits
            if not is_charging and current_battery < 30:  # Low battery threshold
                if required_battery > 5:  # High battery usage partition
                    logger.info(f"Battery conservation: rejecting high-usage partition on low battery node {node.get_nodeId()}: "
                          f"battery {current_battery}%, not charging, requires {required_battery}%")
                    return False
            
            # Check temperature limits from board info
            max_temp = node.get_max_temp()
            if max_temp > 0:  # Only check if max_temp is set in board info
                current_temp = current_status.get("temp", 0)
                required_temp = required_resources.get("temp", 0)
                projected_temp = current_temp + required_temp
                
                if projected_temp > max_temp:
                    logger.warning(f"Temperature limit exceeded for node {node.get_nodeId()}: "
                          f"projected {projected_temp}°C > max {max_temp}°C")
                    return False
            
            # Check network speed limits from board info
            max_network_speed = node.get_max_network_speed()
            if max_network_speed > 0:  # Only check if max_network_speed is set in board info
                current_network = current_status.get("network", 0)
                required_network = required_resources.get("network", 0)
                projected_network = current_network + required_network
                
                if projected_network > max_network_speed:
                    logger.warning(f"Network speed limit exceeded for node {node.get_nodeId()}: "
                          f"projected {projected_network} Mbps > max {max_network_speed} Mbps")
                    return False
            
            # Check other resource limits (you can extend this for CPU, memory, etc.)
            # For now, we'll check basic resource bounds
            
            # Check battery - ensure it doesn't go below 0
            if projected_battery < 0:
                logger.warning(f"Battery would be depleted for node {node.get_nodeId()}: "
                      f"projected {projected_battery}% < 0%")
                return False
            
            # Check CPU usage doesn't exceed 100%
            current_cpu = current_status.get("cpu", 0)
            required_cpu = required_resources.get("cpu", 0)
            projected_cpu = current_cpu + required_cpu
            
            if projected_cpu > 100:
                logger.warning(f"CPU limit exceeded for node {node.get_nodeId()}: "
                      f"projected {projected_cpu}% > 100%")
                return False
            
            # Check memory usage doesn't exceed 100%
            current_memory = current_status.get("memory", 0)
            required_memory = required_resources.get("memory", 0)
            projected_memory = current_memory + required_memory
            
            if projected_memory > 100:
                logger.warning(f"Memory limit exceeded for node {node.get_nodeId()}: "
                      f"projected {projected_memory}% > 100%")
                return False
            
            return True
            
        except Exception as e:
            logger.error(f"Error checking node limits for {node.get_nodeId() if node else 'unknown'}: {e}")
            return False
    
    def __cost(self, nodes_status, perm, partitions):
        # Calculate the cost as the sum of the imbalance in battery status after running the partitions.
        # Also consider charging status - heavily favor charging nodes
        
        max_battery = max(status.get("battery", 0) for status in nodes_status.values())
        battery_imbalance = sum(max_battery - status.get("battery", 0) for status in nodes_status.values())
        
        # Add charging status penalty - penalize heavily for using non-charging nodes
        charging_penalty = 0
        for node_id, status in nodes_status.items():
            is_charging = status.get("is_connected_to_power", False)
            if not is_charging:
                # Heavy penalty for non-charging nodes to prioritize charging nodes
                charging_penalty += 50  # Large penalty value
                
                # Additional penalty based on battery level - lower battery = higher penalty
                battery_level = status.get("battery", 100)
                if battery_level < 50:
                    charging_penalty += (50 - battery_level) * 2  # Escalating penalty for low battery
        
        total_cost = battery_imbalance + charging_penalty
        return total_cost

    def get_next_update_time(self, new_utilization, old_utilization):
        battery_depletion = (old_utilization.get("battery", 0) - new_utilization.get("battery", 0))
        battery_depletion_rate = battery_depletion / (time.time() - self.__last_update_time)

        self.__last_update_time = time.time()
        # If battery is depleting fast, check more often; if slow, check less often
        if battery_depletion_rate > 0:
            next_update_time = max(self.__MIN_UPDATE_PERIOD, min(self.__MAX_UPDATE_PERIOD, self.__slope / battery_depletion_rate))
        else:
            next_update_time = self.__MAX_UPDATE_PERIOD
       
        return next_update_time
class PolicyMaximizeBatteryLifeLocal(LocalPolicyBase):

    def __init__(self):
        super().__init__()
        self.__status = {}
        self.__process_status = {}
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
            
            # Debug logging
            logger.debug(f"Network - Time delta: {time_delta:.3f}s, Sent delta: {bytes_sent_delta}, Recv delta: {bytes_recv_delta}")
            
            upload_speed = bytes_sent_delta / time_delta if time_delta > 0 else 0.0
            download_speed = bytes_recv_delta / time_delta if time_delta > 0 else 0.0
            
            logger.debug(f"Network - Upload speed: {upload_speed:.1f} B/s, Download speed: {download_speed:.1f} B/s")
            
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