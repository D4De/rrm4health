import socket
import psutil
import json
import os
import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


def get_local_ip():
    try:
        # First try: route-based lookup (usually the right interface)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))   # Google's DNS, just for routing
        ip = s.getsockname()[0]
        s.close()
        return ip

    except Exception as e:
        # Fallback: scan all interfaces
        addrs = psutil.net_if_addrs()
        for iface, iface_addrs in addrs.items():
            for addr in iface_addrs:
                # Added check to exclude 172.x.x.x and 169.254.x.x addresses
                if addr.family == socket.AF_INET and not addr.address.startswith(("127.", "172.", "169.254.")):
                    return addr.address
        logger.error(f"Error getting local IP: {e}")
        return "127.0.0.1"

def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0)) 
        return s.getsockname()[1]


def get_connection_type_for_ip(ip_address: str) -> str:
    """Infer connection type for a local IPv4 address.

    Returns one of: "wifi", "ethernet", "unknown".
    """
    if not ip_address:
        return "unknown"

    try:
        interface_addrs = psutil.net_if_addrs()
    except Exception:
        return "unknown"

    matched_interface = None
    for iface_name, addrs in interface_addrs.items():
        for addr in addrs:
            if addr.family == socket.AF_INET and addr.address == ip_address:
                matched_interface = iface_name.lower()
                break
        if matched_interface is not None:
            break

    if matched_interface is None:
        return "unknown"

    wifi_prefixes = ("wlan", "wl", "wifi", "wlp")
    ethernet_prefixes = ("eth", "en", "eno", "ens", "enp")

    if matched_interface.startswith(wifi_prefixes):
        return "wifi"
    if matched_interface.startswith(ethernet_prefixes):
        return "ethernet"

    # Additional robust fallback based on common substrings.
    if "wlan" in matched_interface or "wifi" in matched_interface:
        return "wifi"
    if "eth" in matched_interface or matched_interface.startswith("en"):
        return "ethernet"

    return "unknown"


def normalize_indoor_location(location_value: Any) -> Any:
    """Normalize location payloads to a canonical indoor schema.

    Supported keys in the current JSON model:
    - building
    - floor
    - room
    - zone
    """
    if not isinstance(location_value, dict):
        return location_value

    current_model_keys = ("building", "floor", "room", "zone")
    return {key: location_value.get(key) for key in current_model_keys if key in location_value}


def load_board_info(file_path: Optional[str] = None) -> Dict[str, Any]:
    """
    Load board information from JSON file.
    
    Args:
        file_path: Path to the JSON file containing board information.
                  If None, returns empty dict.
    
    Returns:
        Dictionary containing board information, or empty dict if file not found/invalid.
    """
    if file_path is None:
        return {}
    
    if not os.path.exists(file_path):
        logger.warning(f"Board info file not found: {file_path}")
        return {}
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            board_info = json.load(f)
        logger.info(f"Loaded board info from: {file_path}")
        return board_info
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading board info from {file_path}: {e}")
        return {}


def validate_board_info(board_info: Dict[str, Any]) -> bool:
    """
    Validate board information structure.
    
    Args:
        board_info: Dictionary containing board information
    
    Returns:
        True if valid, False otherwise
    """
    if not isinstance(board_info, dict):
        return False
    
    # Check for required fields (basic validation)
    required_fields = ["id"]
    for field in required_fields:
        if field not in board_info:
            logger.warning(f"Missing required field in board info: {field}")
            return False
    
    # Optional but recommended fields
    optional_fields = ["description", "max_temp", "max_network_speed"]
    for field in optional_fields:
        if field in board_info:
            if field == "max_temp" or field == "max_network_speed":
                if not isinstance(board_info[field], (int, float)) or board_info[field] <= 0:
                    logger.warning(f"Invalid value for {field}: must be a positive number")
                    return False
            elif field == "description":
                if not isinstance(board_info[field], str) or not board_info[field].strip():
                    logger.warning(f"Invalid value for {field}: must be a non-empty string")
                    return False
    
    return True


def load_board_info_from_catalog(node_id: str, node_inventory_file: str, node_catalog_file: str) -> Dict[str, Any]:
    """Resolve board info by node_id using node inventory + node catalog files."""
    if not node_id:
        logger.warning("Cannot resolve board info: node_id is empty")
        return {}

    if not node_inventory_file or not os.path.exists(node_inventory_file):
        logger.warning(f"Node inventory file not found: {node_inventory_file}")
        return {}

    if not node_catalog_file or not os.path.exists(node_catalog_file):
        logger.warning(f"Node catalog file not found: {node_catalog_file}")
        return {}

    try:
        with open(node_inventory_file, "r", encoding="utf-8") as file_obj:
            node_inventory = json.load(file_obj)
        with open(node_catalog_file, "r", encoding="utf-8") as file_obj:
            node_catalog = json.load(file_obj)
    except (json.JSONDecodeError, IOError) as exc:
        logger.error(f"Error loading node catalog/inventory: {exc}")
        return {}

    if not isinstance(node_inventory, dict) or not isinstance(node_catalog, dict):
        logger.warning("Invalid node catalog/inventory format: expected JSON objects")
        return {}

    node_entry = node_inventory.get(node_id)
    if not isinstance(node_entry, dict):
        logger.warning(f"Node '{node_id}' not found in node inventory")
        return {}

    type_id = node_entry.get("type")
    if not isinstance(type_id, str) or not type_id:
        logger.warning(f"Node '{node_id}' has invalid or missing 'type' in node inventory")
        return {}

    board_info = node_catalog.get(type_id)
    if not isinstance(board_info, dict):
        logger.warning(f"Type '{type_id}' not found in node catalog")
        return {}

    return dict(board_info)


def load_node_inventory_entry(node_id: str, node_inventory_file: str) -> Dict[str, Any]:
    """Return a single node entry from node inventory by logical node_id."""
    if not node_id:
        return {}

    if not node_inventory_file or not os.path.exists(node_inventory_file):
        logger.warning(f"Node inventory file not found: {node_inventory_file}")
        return {}

    try:
        with open(node_inventory_file, "r", encoding="utf-8") as file_obj:
            node_inventory = json.load(file_obj)
    except (json.JSONDecodeError, IOError) as exc:
        logger.error(f"Error loading node inventory: {exc}")
        return {}

    if not isinstance(node_inventory, dict):
        logger.warning("Invalid node inventory format: expected JSON object")
        return {}

    entry = node_inventory.get(node_id)
    if not isinstance(entry, dict):
        return {}

    return dict(entry)


class MetricsFormattingUtils:
    """Shared helpers to format metrics with explicit units and collection mode."""

    WINDOW_COMPATIBLE_METRIC_NAMES = {
        "temperature",
        "power_consumption_w",
        "upload_speed",
        "download_speed",
        "network",
    }

    @staticmethod
    def metric_unit(metric_name: str, value: Any = None) -> str:
        units = {
            "temperature": "C",
            "power_consumption_w": "W",
            "power_usage_estimate": "W",
            "upload_speed": "B/s",
            "download_speed": "B/s",
            "cpu_percentage": "%",
            "memory_percentage": "%",
            "disk_used": "%",
            "memory_used_mb": "MB",
            "memory_available_mb": "MB",
            "disk_used_gb": "GB",
            "disk_available_gb": "GB",
            "battery_percentage": "%",
            "cpu_frequency": "MHz",
            "core_avg_frequency": "MHz",
            "max_freq": "MHz",
            "uptime": "s",
            "memory_total": "bytes",
            "disk_total": "bytes",
            "battery_energy_full": "mWh",
        }

        if metric_name == "network" and isinstance(value, dict):
            return value.get("unit", "B/s")

        return units.get(metric_name, "")

    @staticmethod
    def format_runtime_metric(metric_name: str, value: Any, default_mode: str = "instant") -> str:
        label = metric_name.replace('_', ' ').capitalize()
        normalized_default_mode = str(default_mode or "instant")

        # Only metrics that support window aggregation should ever be labeled as window.
        scalar_mode = (
            normalized_default_mode
            if normalized_default_mode == "window" and metric_name in MetricsFormattingUtils.WINDOW_COMPATIBLE_METRIC_NAMES
            else "instant"
        )

        if isinstance(value, dict):
            mode = str(value.get("mode", scalar_mode))
            metric_value = value.get("value")

            if metric_name == "network" and isinstance(metric_value, dict):
                upload_value = metric_value.get("upload_speed", 0.0)
                download_value = metric_value.get("download_speed", 0.0)
                unit = MetricsFormattingUtils.metric_unit(metric_name, metric_value)
                return (
                    f"{label}: upload={upload_value} {unit}, "
                    f"download={download_value} {unit} ({mode})"
                )

            unit = MetricsFormattingUtils.metric_unit(metric_name, metric_value)
            if unit:
                return f"{label}: {metric_value} {unit} ({mode})"
            return f"{label}: {metric_value} ({mode})"

        unit = MetricsFormattingUtils.metric_unit(metric_name, value)
        if unit:
            return f"{label}: {value} {unit} ({scalar_mode})"
        return f"{label}: {value} ({scalar_mode})"