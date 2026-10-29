import logging
from core.monitoring.MetricFields import ProcessMetricField
from enum import Enum
from typing import Dict, Any

from Config import START_PORT_CHANNELS, END_PORT_CHANNELS

logger = logging.getLogger(__name__)

class NodeStatus(Enum):
    """Enumeration for node status states"""
    SETUP = "setup"  # Node connected but capabilities not yet received
    READY = "ready"  # Node ready, capabilities received, apps can be started
    DISCONNECTED = "disconnected"  # Node disconnected or timeout occurred

class Node:
    """Class to manage the node
    All nodes have a Node class 
    RRM* contains a list of nodes with their characteristics
    """
    def __init__(self, nodeId, clientId):
        self.__nodeId = nodeId  # Add nodeId attribute
        self.__ip = nodeId[0]
        self.__port = int(nodeId[1])
        self.__clientId = clientId # zmq reference to the client
        self.__running_partition = {} # (AppID,UniqueId,partitionID) -> partition config for global pid for local
        self.__available_ports = list(range(START_PORT_CHANNELS, END_PORT_CHANNELS))
        self.__status = {}
        self.__next_update_time = 0
        self.__capabilities = {}  # Node capabilities, e.g., CPU, RAM
        self.__my_prefix = None  # Prefix based on the capabilities of the node, used to access DevicePerformancePerPartition.json
        self.__node_status = NodeStatus.SETUP  # Initialize as SETUP until capabilities are received
        self.__board_info = {}  # Board information from JSON file
        self.__board_info_initialized = False  # Track if board info was provided
        # node status

    def get_capabilities(self):
        return self.__capabilities
    
    def set_capabilities(self, capabilities):
        """Set the capabilities of the node"""
        self.__capabilities = capabilities
        # Recompute the prefix based on the new capabilities
        if 'architecture' in capabilities and 'n_cores' in capabilities and 'max_freq' in capabilities:
            # Start status as plugged, will be updated when status is received
            self.__my_prefix = f"{capabilities['architecture']}_{capabilities['n_cores']}_{capabilities['max_freq']}_plugged"
            logger.info(f"Capabilities set: {self.__capabilities}, Prefix: {self.__my_prefix}")
            # Set node status to READY when capabilities are received
            self.__node_status = NodeStatus.READY

    def get_prefix(self):
        return self.__my_prefix
    
    def get_node_status(self):
        """Get the current status of the node"""
        return self.__node_status
    
    def set_node_status(self, status: NodeStatus):
        """Set the status of the node"""
        if self.__node_status != status:
            logger.info(f"Node {self.__nodeId} status changing from {self.__node_status.value} to {status.value}")
        self.__node_status = status
    
    def is_ready(self):
        """Check if the node is ready to run applications"""
        return self.__node_status == NodeStatus.READY
    
    def get_nodeId(self):
        return self.__nodeId  # Return the nodeId attribute
    def get_ip(self):
        return self.__ip
    def get_port(self):
        return self.__port
    def get_clientId(self):
        return self.__clientId
    def set_clientId(self, clientId):
        """Set the clientId of the node"""
        self.__clientId = clientId
    def get_number_of_running_partitions(self):
        return len(self.__running_partition)
    def get_running_partitions(self):
        return self.__running_partition
    def pop_next_available_port(self):
        if not self.__available_ports:
            raise RuntimeError("No ports available")
        port = self.__available_ports.pop(0)
        return port
    def free_port(self, port):
        port = int(port)
        if port not in self.__available_ports:
            self.__available_ports.append(port)
    def remove_port(self, port):
        port = int(port)
        if port in self.__available_ports:
            self.__available_ports.remove(port)
    def set_available_ports(self, ports):
        """Set the available ports for the node"""
        self.__available_ports = ports.copy()
    def get_available_ports(self):
        if not self.__available_ports:
            raise RuntimeError("No ports available")
        return self.__available_ports
    def add_running_partition(self, partitionID, pid = 0, clientId = 0):
        if partitionID in self.__running_partition:
            raise RuntimeError("Partition already running")
        self.__running_partition[partitionID] = Partition(pid,clientId)
    def remove_running_partition(self, partitionID):
        if partitionID not in self.__running_partition:
            raise RuntimeError("Partition not running")
        self.__running_partition.pop(partitionID)
    def get_status(self):
        return self.__status
    def update_status(self, status):
        old_power_status = self.__status.get('is_connected_to_power', None)
        new_power_status = status.get('is_connected_to_power', None)
        
        self.__status = status
        
        # If power status changed, update the prefix
        if old_power_status != new_power_status and self.__my_prefix and new_power_status is not None:
            power_suffix = "powered" if new_power_status else "battery"
            self.__my_prefix = f"{self.__capabilities['architecture']}_{self.__capabilities['n_cores']}_{self.__capabilities['max_freq']}_{power_suffix}"
    def get_next_update_time(self):
        return self.__next_update_time
    def set_next_update_time(self, next_update_time):
        self.__next_update_time = next_update_time

    def get_available_ports(self):
        return self.__available_ports
    
    def set_board_info(self, board_info: Dict[str, Any]):
        """Set board information for this node"""
        self.__board_info = board_info if board_info else {}
        self.__board_info_initialized = bool(board_info)
    
    def get_board_info(self) -> Dict[str, Any]:
        """Get board information for this node (returns reference, do not modify)"""
        return self.__board_info
    
    def has_board_info(self) -> bool:
        """Check if board information was initialized for this node"""
        return self.__board_info_initialized
    
    def get_board_id(self) -> str:
        """Get board ID if available"""
        return self.__board_info.get('id', f"node_{self.__ip}_{self.__port}")
    
    def get_max_temp(self) -> float:
        """Get maximum temperature limit for this board, returns -1 if not set"""
        return self.__board_info.get('max_temp', -1)
    
    def get_max_network_speed(self) -> float:
        """Get maximum network speed for this board in Mbps, returns -1 if not set"""
        return self.__board_info.get('max_network_speed', -1)

class Partition:

    def __init__(self, pid, clientId):
        self.__pid = pid
        self.__clientId = clientId
        self.__utilization = {}
        self.__devices_status = {}
        self.__counter = 0 

    def update_utilization(self, metrics):
        cpu = metrics.get(ProcessMetricField.CPU_PERCENTAGE, -1.0)
        battery = metrics.get(ProcessMetricField.POWER_USAGE_WATTS, -1.0)

        self.__utilization["cpu_percentage"] =  (self.__utilization.get("cpu_percentage",0) * self.__counter + cpu) / (self.__counter + 1)
        self.__utilization["core_avg_frequency"] = metrics.get(ProcessMetricField.CORE_AVG_FREQUENCY, -1.0)
        self.__utilization["power_usage_estimate"] = battery

        self.__counter += 1

    def reset_utilization(self):
        self.__utilization = {}
        self.__counter = 0

    def add_devices_status(self, device_status):
        self.__devices_status = device_status

    def get_devices_status(self):
        return self.__devices_status

    def get_utilization(self):
        return self.__utilization
    
    def get_pid(self):
        return self.__pid
    
    def get_clientId(self):
        return self.__clientId
