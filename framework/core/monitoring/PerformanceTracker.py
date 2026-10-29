import json

from core.monitoring.MetricFields import ProcessMetricField
from Config import  MODIFIED_DEVICE_PERFORMANCE_COST, NEW_DEVICE_COST, NEW_PARTITION_COST, NEW_APP_COST, DIFFERENT_FREQUENCY_SCALER, DIFFERENT_CORES_SCALER, DIFFERENT_ARCHITECTURE_COST, CHANGES_THRESHOLD

class PerformanceTracker:
    def __init__(self, file_path):
        self.__file_path = file_path
        self.__device_performance_per_partition = json.load(open(file_path, "r", encoding="utf-8"))
        self.__device_performance_changes = 0  # Counter for device performance changes
        self.__required_fields = [ProcessMetricField.CPU_PERCENTAGE, ProcessMetricField.CORE_AVG_FREQUENCY, ProcessMetricField.POWER_USAGE_WATTS]

    def get_required_fields(self):
        """
        Returns the set of fields required for performance tracking.
        This can be extended to include more fields as needed.
        """
        return self.__required_fields
    
    def update_partition_consumption(self, status, node_prefix):

        for partition in status:
            app_id = partition["id"][0][0]
            partition_id = partition["id"][1]

            # Ensure structure is initialized
            if app_id not in self.__device_performance_per_partition.keys():
                self.__device_performance_per_partition[app_id] = {}
                self.__device_performance_per_partition[app_id][partition_id] = {}
                self.__device_performance_changes += NEW_APP_COST
            elif partition_id not in self.__device_performance_per_partition[app_id].keys():
                self.__device_performance_per_partition[app_id][partition_id] = {}
                self.__device_performance_changes += NEW_PARTITION_COST

            utilization = partition.get("utilization", {})
            performance = self.__device_performance_per_partition[app_id][partition_id]

            if node_prefix not in performance:
                performance[node_prefix] = utilization
                self.__device_performance_changes += NEW_DEVICE_COST
            else:
                old = performance[node_prefix]
                reliability = 0.8

                # Weighted average for each metric
                updated = {}
                for k in utilization:
                    old_val = old.get(k, 0)
                    new_val = utilization.get(k, 0)

                    # Only update if both values are valid (not -1.0)
                    if old_val != -1.0 and new_val != -1.0:
                        updated[k] = old_val * reliability + new_val * (1 - reliability)
                        self.__device_performance_changes += abs(new_val - old_val) * MODIFIED_DEVICE_PERFORMANCE_COST
                    elif new_val != -1.0:
                        # First valid measurement
                        updated[k] = new_val
                        self.__device_performance_changes += NEW_DEVICE_COST
                    else:
                        # Keep old value if new measurement is invalid
                        updated[k] = old_val

                performance[node_prefix] = updated
                
    def get_closest_performance(self, app_id, partition_id, node_prefix):
        partition_to_run = self.__device_performance_per_partition.get(app_id, {}).get(partition_id, {})

        if node_prefix in partition_to_run:
            return partition_to_run[node_prefix]
        else:
            architecture, n_cores, power_state, max_freq = node_prefix.split("_")
            min_diff = float('inf')
            closest_performance = None
            for prefix, performance in partition_to_run.items():
                cost = 0
                # We always pick device with the same power state if available (device charging use 0 battery)
                if prefix.startswith(f"{architecture}_{n_cores}_") and prefix.endswith(f"_{power_state}"):
                    _,_,freq,_ = prefix.split("_")
                    cost = abs(float(freq) - float(max_freq)) * DIFFERENT_FREQUENCY_SCALER
                elif prefix.startswith(f"{architecture}_") and prefix.endswith(f"_{power_state}"):
                    _, n_cores_prefix, freq,_ = prefix.split("_")
                    cost = abs(int(n_cores_prefix) - int(n_cores)) * DIFFERENT_CORES_SCALER + abs(float(freq) - float(max_freq)) * DIFFERENT_FREQUENCY_SCALER
                else:
                    cost = DIFFERENT_ARCHITECTURE_COST  # High cost for non-matching architectures
                if cost < min_diff:
                    min_diff = cost
                    closest_performance = performance
            return closest_performance
    
    def get_device_performance_per_partition(self):
        return self.__device_performance_per_partition
    
    def need_to_write(self):
        return self.__device_performance_changes > CHANGES_THRESHOLD
    
    def write_changes_to_file(self):
        with open(self.__file_path, "w", encoding="utf-8") as f:
            json.dump(self.__device_performance_per_partition, f, indent=4)
        self.__device_performance_changes = 0