import time
import logging
from typing import Optional, Set, Dict, Any
from Config import UPDATE_PERIOD

logger = logging.getLogger(__name__)

class MetricsManager:
    """Manages metrics collection for the local node and its partitions."""
    
    def __init__(self, metrics_collector, process_metrics_collector, get_policy, get_local_node_status, get_lock):
        """
        Initialize the MetricsManager.
        
        Args:
            metrics_collector: MetricsCollector instance for system metrics
            process_metrics_collector: ProcessMetricsCollector instance for process metrics
            get_policy: Lambda function that returns the current policy
            get_local_node_status: Lambda function that returns the local node status
            get_lock: Lambda function that returns the threading lock
        """
        self.__metrics_collector = metrics_collector
        self.__process_metrics_collector = process_metrics_collector
        self.__get_policy = get_policy
        self.__get_local_node_status = get_local_node_status
        self.__get_lock = get_lock
        self.__resources_to_collect = None
        self.__process_resources_to_collect = None
    
    def set_resources_to_collect(self, resources_to_collect, process_resources_to_collect):
        """Set the resources to collect from the system and processes.
        
        Args:
            resources_to_collect: List of system resource names to collect
            process_resources_to_collect: List of process resource names to collect
        """
        self.__resources_to_collect = resources_to_collect
        self.__process_resources_to_collect = process_resources_to_collect
    
    def collect_and_update_metrics(self):
        """Collect metrics and update node status based on policy."""
        policy = self.__get_policy()
        local_node_status = self.__get_local_node_status()
        lock = self.__get_lock()
        
        if policy is None or local_node_status is None or lock is None:
            return
        
        collected_metrics = self.__metrics_collector.collect(self.__resources_to_collect)
        status = policy.update_node_status(collected_metrics)
        
        with lock:
            local_node_status.update_status(status)
            for partitionID, partition in local_node_status.get_running_partitions().items():
                resources = self.__process_metrics_collector.collect(
                    self.__process_resources_to_collect, 
                    partition.get_pid()
                )
                partition.update_utilization(resources)
    
    def collect_capabilities(self,
                             fields_to_collect,
                             mode: str = "instant",
                             window_seconds: float = 0.0,
                             sample_interval_seconds: float = 0.5):
        """Collect capability data for specific fields.
        
        Args:
            fields_to_collect: List of fields to collect
            
        Returns:
            Dictionary of collected data
        """
        if fields_to_collect:
            return self.__metrics_collector.collect(
                fields_to_collect,
                mode=mode,
                window_seconds=window_seconds,
                sample_interval_seconds=sample_interval_seconds,
            )
        else:
            logger.warning("No fields specified for capability request")
            return {}
    
    def get_update_period(self):
        """Get the update period for metrics collection."""
        return UPDATE_PERIOD
