"""
Descriptor schema definitions for the RRM framework.

This module defines the structure, types, and parameters for application descriptors.
This information was previously embedded in the descriptor files but has been extracted
to simplify the manifest format for end users.

This module provides:
- Channel structure definitions and utilities
- Parameter type definitions and utilities
- Schema validation helpers
"""

from typing import Dict, Any, List
from enum import Enum


# ============================================================================
# Channel Structure Definitions
# ============================================================================

class ChannelType(Enum):
    """Supported channel types for inter-partition communication."""
    NETWORK_SOCKET = "network_socket"
    # Add more channel types as needed in the future
    # SHARED_MEMORY = "shared_memory"
    # MESSAGE_QUEUE = "message_queue"


class ChannelStructure:
    """Defines the structure and parameters for communication channels."""
    
    @staticmethod
    def get_default_channel_type() -> str:
        """Get the default channel type."""
        return ChannelType.NETWORK_SOCKET.value
    
    @staticmethod
    def get_channel_template(channel_type: str = None) -> Dict[str, Any]:
        """
        Get the template structure for a channel configuration.
        
        Args:
            channel_type: Type of channel (default: network_socket)
            
        Returns:
            Dictionary with the channel template structure
        """
        if channel_type is None:
            channel_type = ChannelStructure.get_default_channel_type()
        
        if channel_type == ChannelType.NETWORK_SOCKET.value:
            return {
                "type": ChannelType.NETWORK_SOCKET.value,
                "parameters": {
                    "ip_src": "{{IP_SRC}}",
                    "port_src": "{{PORT_SRC}}",
                    "ip_dst": "{{IP_DST}}",
                    "port_dst": "{{PORT_DST}}",
                    "protocol": "tcp"
                }
            }
        else:
            raise ValueError(f"Unsupported channel type: {channel_type}")
    
    @staticmethod
    def create_channel(from_partition: str, to_partition: str, 
                      channel_type: str = None) -> Dict[str, Any]:
        """
        Create a complete channel configuration.
        
        Args:
            from_partition: ID of the source partition
            to_partition: ID of the destination partition
            channel_type: Type of channel (default: network_socket)
            
        Returns:
            Complete channel configuration dictionary
        """
        template = ChannelStructure.get_channel_template(channel_type)
        return {
            "from_partition": from_partition,
            "to_partition": to_partition,
            **template
        }
    
    @staticmethod
    def validate_channel(channel: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate a channel configuration.
        
        Args:
            channel: Channel configuration dictionary
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        required_fields = ["from_partition", "to_partition", "type", "parameters"]
        
        for field in required_fields:
            if field not in channel:
                return False, f"Missing required field: {field}"
        
        channel_type = channel["type"]
        
        if channel_type == ChannelType.NETWORK_SOCKET.value:
            required_params = ["ip_src", "port_src", "ip_dst", "port_dst", "protocol"]
            for param in required_params:
                if param not in channel["parameters"]:
                    return False, f"Missing required parameter for network_socket: {param}"
        else:
            return False, f"Unsupported channel type: {channel_type}"
        
        return True, ""
    
    @staticmethod
    def get_supported_protocols() -> List[str]:
        """Get list of supported network protocols."""
        return ["tcp", "udp"]


# ============================================================================
# Parameter Type Definitions
# ============================================================================

class ParameterType(Enum):
    """Types of parameters used in application execution."""
    GLOBALARG = "globalarg"  # Arguments managed by RRM Global (config_id, partition_id, channels)
    LOCALARG = "localarg"    # Arguments managed by RRM Local (RRM port)
    USERARG = "userarg"      # Arguments provided by the end user


class ParameterDefinition:
    """Defines parameter structures and provides utilities for parameter handling."""
    
    # System-managed parameters that are automatically handled by the framework
    SYSTEM_PARAMETERS = {
        "Ind_conf": {
            "type": ParameterType.GLOBALARG.value,
            "value": "{{CONFIGURATION_ID}}",
            "description": "Configuration index selected by the RRM"
        },
        "Id_part": {
            "type": ParameterType.GLOBALARG.value,
            "value": "{{PARTITION_ID}}",
            "description": "Partition ID within the configuration"
        },
        "channels": {
            "type": ParameterType.GLOBALARG.value,
            "value": "{{CHANNELS_PARAMETERS}}",
            "description": "Channel parameters for inter-partition communication"
        },
        "RRM_port": {
            "type": ParameterType.LOCALARG.value,
            "value": "{{PORT1}}",
            "description": "Port for communicating with the local RRM"
        }
    }
    
    @staticmethod
    def create_parameter(name: str, param_type: str, value: Any = None, 
                        description: str = "") -> Dict[str, Any]:
        """
        Create a parameter definition.
        
        Args:
            name: Parameter name
            param_type: Type of parameter (globalarg, localarg, userarg)
            value: Parameter value or placeholder
            description: Description of the parameter
            
        Returns:
            Parameter definition dictionary
        """
        if param_type not in [pt.value for pt in ParameterType]:
            raise ValueError(f"Invalid parameter type: {param_type}")
        
        param = {
            "type": param_type,
            "value": value if value is not None else f"{{{{{name.upper()}}}}}"
        }
        
        if description:
            param["description"] = description
        
        return param
    
    @staticmethod
    def get_system_parameters() -> Dict[str, Dict[str, Any]]:
        """
        Get all system-managed parameters.
        
        Returns:
            Dictionary of system parameters
        """
        return ParameterDefinition.SYSTEM_PARAMETERS.copy()
    
    @staticmethod
    def merge_parameters(user_params: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """
        Merge user-defined parameters with system parameters.
        
        Args:
            user_params: Dictionary mapping parameter names to their values or definitions
            
        Returns:
            Complete parameter dictionary with both system and user parameters
        """
        # Start with system parameters
        all_params = ParameterDefinition.get_system_parameters()
        
        # Add user parameters
        for name, value in user_params.items():
            if isinstance(value, dict) and "type" in value:
                # Already in the correct format
                all_params[name] = value
            else:
                # Simple value, assume it's a user argument
                all_params[name] = {
                    "type": ParameterType.USERARG.value,
                    "value": value
                }
        
        return all_params
    
    @staticmethod
    def filter_by_type(parameters: Dict[str, Dict[str, Any]], 
                      param_type: ParameterType) -> Dict[str, Any]:
        """
        Filter parameters by type.
        
        Args:
            parameters: Dictionary of all parameters
            param_type: Type to filter by
            
        Returns:
            Dictionary of parameters matching the specified type
        """
        return {
            name: param for name, param in parameters.items()
            if param.get("type") == param_type.value
        }
    
    @staticmethod
    def is_system_parameter(param_name: str) -> bool:
        """
        Check if a parameter is a system-managed parameter.
        
        Args:
            param_name: Name of the parameter
            
        Returns:
            True if the parameter is system-managed, False otherwise
        """
        return param_name in ParameterDefinition.SYSTEM_PARAMETERS
    
    @staticmethod
    def validate_parameter(param: Dict[str, Any]) -> tuple[bool, str]:
        """
        Validate a parameter definition.
        
        Args:
            param: Parameter definition dictionary
            
        Returns:
            Tuple of (is_valid, error_message)
        """
        if "type" not in param:
            return False, "Missing 'type' field in parameter definition"
        
        if param["type"] not in [pt.value for pt in ParameterType]:
            return False, f"Invalid parameter type: {param['type']}"
        
        if "value" not in param:
            return False, "Missing 'value' field in parameter definition"
        
        return True, ""
