import threading
import time
import logging
import json
from typing import Dict, Tuple, Any

import core.Utils as Utils
from core.models.Node import Node, NodeStatus
from Config import STATUS_UPDATE_INTERVAL, NODE_INVENTORY_FILE

logger = logging.getLogger(__name__)

class NodeManager:
    """Manages connected nodes/clients and their state."""
    
    def __init__(self, get_channel_manager_fn=None):
        self.__clients: Dict[Tuple[str, int], Node] = {}
        self.__clients_lock = threading.Lock()
        # Use getter function to always access current channel_manager from RRMGlobal
        self.__get_channel_manager = get_channel_manager_fn
    
    def get_lock(self):
        """Get the clients lock for external synchronization."""
        return self.__clients_lock
    
    def add_client(self, node_id: Tuple[str, int], client_id: bytes) -> Node:
        """Add a new client node and return the created node."""
        with self.__clients_lock:
            client = Node(node_id, client_id)
            # If the client is on the same node of another client we update the available ports
            for other_client in self.__clients.values():
                if other_client.get_nodeId()[0] == node_id[0]:
                    # Update the available ports for the new client
                    client.set_available_ports(other_client.get_available_ports())
                    break
            self.__clients[node_id] = client
            return client
    
    def remove_client(self, node_id: Tuple[str, int]) -> bool:
        """Remove a client from the manager. Returns True if removed, False if not found."""
        with self.__clients_lock:
            if node_id in self.__clients:
                del self.__clients[node_id]
                return True
            return False
    
    def get_client(self, node_id: Tuple[str, int]) -> Node:
        """Get a client by node_id. Returns None if not found."""
        with self.__clients_lock:
            return self.__clients.get(node_id)
    
    def get_all_clients(self) -> Dict[Tuple[str, int], Node]:
        """Get a reference to all clients (use with lock in calling code)."""
        return self.__clients
    
    def get_client_list(self) -> Dict[Tuple[str, int], Node]:
        """Get a copy of the clients dictionary."""
        with self.__clients_lock:
            return self.__clients.copy()
    
    def update_client_status(self, node_id: Tuple[str, int], status: Dict[str, Any]) -> None:
        """Update the status of a client node."""
        with self.__clients_lock:
            if node_id in self.__clients:
                self.__clients[node_id].update_status(status)
    
    def set_client_node_status(self, node_id: Tuple[str, int], node_status: NodeStatus) -> None:
        """Set the NodeStatus of a client."""
        with self.__clients_lock:
            if node_id in self.__clients:
                self.__clients[node_id].set_node_status(node_status)
    
    def set_client_capabilities(self, node_id: Tuple[str, int], capabilities: Dict[str, Any]) -> None:
        """Set capabilities for a client node."""
        with self.__clients_lock:
            if node_id in self.__clients:
                self.__clients[node_id].set_capabilities(capabilities)
    
    def set_client_board_info(self, node_id: Tuple[str, int], board_info: Dict[str, Any]) -> None:
        """Set board info for a client node."""
        with self.__clients_lock:
            if node_id in self.__clients:
                self.__clients[node_id].set_board_info(board_info)
    
    def set_client_next_update_time(self, node_id: Tuple[str, int], next_time: float) -> None:
        """Set the next update time for a client node."""
        with self.__clients_lock:
            if node_id in self.__clients:
                self.__clients[node_id].set_next_update_time(next_time)
    
    def clear_client_id(self, node_id: Tuple[str, int]) -> None:
        """Clear the clientId for a node (when disconnecting)."""
        with self.__clients_lock:
            if node_id in self.__clients:
                self.__clients[node_id].set_clientId(None)
    
    def get_board_info_summary(self) -> Dict[str, Any]:
        """Get summary of board information for all nodes."""
        board_summary = {}
        with self.__clients_lock:
            for node_id, node in self.__clients.items():
                if node.has_board_info():
                    board_summary[node_id] = {
                        'board_id': node.get_board_id(),
                        'board_info': node.get_board_info(),
                        'node_status': node.get_node_status().value,
                        'initialized': True
                    }
                else:
                    board_summary[node_id] = {
                        'board_id': node.get_board_id(),
                        'board_info': {},
                        'node_status': node.get_node_status().value,
                        'initialized': False
                    }
        return board_summary
    
    def check_clients_ready_for_updates(self) -> None:
        """Check all clients and send update requests if needed."""
        if self.__get_channel_manager is None:
            logger.warning("Channel manager not initialized, skipping client updates")
            return
            
        with self.__clients_lock:
            for client in self.__clients.values():
                if time.time() >= client.get_next_update_time():
                    from core.communication.Message import GlobalRequestStatus
                    self.__get_channel_manager().send_message(client.get_clientId(), GlobalRequestStatus())
                    client.set_next_update_time(time.time() + STATUS_UPDATE_INTERVAL)

    @staticmethod
    def _policy_required_metric_names(policy) -> set:
        names = set()
        try:
            required_fields = policy.get_required_fields() if policy else []
        except Exception:
            required_fields = []

        for field in required_fields or []:
            value = getattr(field, "value", field)
            names.add(str(value))

        # Network is collected as bytes deltas and exposed in status as upload/download speeds.
        if "network" in names:
            names.add("upload_speed")
            names.add("download_speed")

        return names

    @staticmethod
    def _runtime_summary_for_level(status: Dict[str, Any], snapshot_detail: str, policy) -> Dict[str, Any]:
        if not isinstance(status, dict):
            return {}

        if snapshot_detail == "minimal":
            return {}

        if snapshot_detail == "full":
            return dict(status)

        # policy mode
        required_names = NodeManager._policy_required_metric_names(policy)
        return {
            key: value
            for key, value in status.items()
            if key in required_names
        }

    def print_global_node_status(self, running_apps: Dict[Tuple[str, int], Any], 
                                policy, guis: Dict[bytes, Tuple[str, int]], 
                                performance_tracker,
                                node_resources_registry: Dict[str, Any] = None,
                                resource_instances_status: Dict[str, Any] = None,
                                global_endpoint: Tuple[str, int] = None,
                                snapshot_detail: str = "policy",
                                metrics_mode: str = "instant",
                                metrics_window_seconds: float = 0.0,
                                metrics_sample_interval_seconds: float = 0.5) -> None:
        """Print the status of all nodes and running applications."""
        if logger.level > logging.INFO:
            return

        inventory_data = {}
        try:
            with open(NODE_INVENTORY_FILE, "r", encoding="utf-8") as file_obj:
                loaded = json.load(file_obj)
            if isinstance(loaded, dict):
                inventory_data = loaded
        except Exception:
            inventory_data = {}

        print("=" * 60)
        print("GLOBAL NODE STATUS SUMMARY")
        print("=" * 60)
        print(f"  Snapshot Detail Level: {snapshot_detail}")
        print(f"  Metrics Collection Mode: {metrics_mode}")
        if str(metrics_mode).lower() == "window":
            print(f"  Metrics Window Seconds: {metrics_window_seconds}")
            print(f"  Metrics Sample Interval Seconds: {metrics_sample_interval_seconds}")
        print(f"  Snapshot Timestamp UTC: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")

        global_ip = "unknown"
        global_port = "unknown"
        if isinstance(global_endpoint, tuple) and len(global_endpoint) == 2:
            global_ip, global_port = global_endpoint
        endpoint_type = Utils.get_connection_type_for_ip(global_ip)

        with self.__clients_lock:
            nodes_total = len(self.__clients)
            nodes_ready = sum(1 for node in self.__clients.values() if node.get_node_status() == NodeStatus.READY)
            nodes_disconnected = sum(1 for node in self.__clients.values() if node.get_node_status() == NodeStatus.DISCONNECTED)

        print("RRM_GLOBAL:")
        print("  Endpoint:")
        print(f"    IP: {global_ip}")
        print(f"    Port: {global_port}")
        print(f"    Type: {endpoint_type}")
        print("  Status: READY")
        print(f"  Nodes Total: {nodes_total}")
        print(f"  Nodes Ready: {nodes_ready}")
        print(f"  Nodes Disconnected: {nodes_disconnected}")
        print("Nodes:")

        with self.__clients_lock:
            for node in self.__clients.values():
                node_id = node.get_nodeId()
                node_status = node.get_node_status()
                status = node.get_status()
                partitions = node.get_running_partitions()
                board_info = node.get_board_info()

                print(f"\n Node ID: {node_id}")
                print(f"   Node Status: {node_status.value.upper()}")

                node_key = f"{node_id[0]}:{node_id[1]}"
                node_resource_entry = (node_resources_registry or {}).get(node_key, {})
                logical_node_id = node_resource_entry.get("node_id", "unknown")
                type_id = node_resource_entry.get("type_id", "unknown")
                connected_resources = node_resource_entry.get("resources", {})

                inventory_entry = inventory_data.get(logical_node_id, {}) if isinstance(inventory_data, dict) else {}
                location = inventory_entry.get("location", {}) if isinstance(inventory_entry, dict) else {}
                location = Utils.normalize_indoor_location(location)

                connected_resources_list = []
                if isinstance(connected_resources, dict) and connected_resources:
                    for resource_id, resource_data in connected_resources.items():
                        resource_type = resource_data.get("type", "unknown") if isinstance(resource_data, dict) else "unknown"
                        resource_status = (
                            str(resource_data.get("status") or "ACTIVE").upper()
                            if isinstance(resource_data, dict)
                            else "ACTIVE"
                        )
                        resource_connection = (
                            str(resource_data.get("interface") or "unknown").lower()
                            if isinstance(resource_data, dict)
                            else "unknown"
                        )
                        connected_resources_list.append({
                            "resource_id": resource_id,
                            "type": resource_type,
                            "status": resource_status,
                            "connection_type": resource_connection,
                        })

                print("  -")
                print(f"    Logical Node ID: {logical_node_id}")
                print(f"    Node Type ID: {type_id}")
                print("    Endpoint:")
                print(f"      IP: {node_id[0]}")
                print(f"      Port: {node_id[1]}")
                print(f"      Type: {Utils.get_connection_type_for_ip(node_id[0])}")
                print(f"    Node Status: {node_status.value.upper()}")
                print(f"    Online: {str(node_status != NodeStatus.DISCONNECTED).lower()}")
                print(f"    Location: {location if isinstance(location, dict) else {}}")
                print("    Resources:")
                print(f"      Connected Count: {len(connected_resources_list)}")
                print("      Connected Resources:")
                if connected_resources_list:
                    connected_resources_list.sort(key=lambda item: item["resource_id"])
                    headers = {
                        "resource_id": "Resource ID",
                        "type": "Type",
                        "status": "Status",
                        "connection_type": "Connection",
                    }
                    widths = {}
                    for key, label in headers.items():
                        widths[key] = max(len(label), *(len(str(item.get(key, ""))) for item in connected_resources_list))

                    header_line = (
                        f"        {headers['resource_id']:<{widths['resource_id']}}  "
                        f"{headers['type']:<{widths['type']}}  "
                        f"{headers['status']:<{widths['status']}}  "
                        f"{headers['connection_type']:<{widths['connection_type']}}"
                    )
                    separator_line = (
                        f"        {'-' * widths['resource_id']}  "
                        f"{'-' * widths['type']}  "
                        f"{'-' * widths['status']}  "
                        f"{'-' * widths['connection_type']}"
                    )
                    print(header_line)
                    print(separator_line)
                    for item in connected_resources_list:
                        print(
                            f"        {item['resource_id']:<{widths['resource_id']}}  "
                            f"{item['type']:<{widths['type']}}  "
                            f"{item['status']:<{widths['status']}}  "
                            f"{item['connection_type']:<{widths['connection_type']}}"
                        )
                else:
                    print("        []")
                runtime_summary = self._runtime_summary_for_level(status, snapshot_detail, policy)
                if runtime_summary:
                    print("    Runtime Summary:")
                    for key, value in runtime_summary.items():
                        print(f"      {Utils.MetricsFormattingUtils.format_runtime_metric(key, value, default_mode=metrics_mode)}")
                    print(f"      Last Update UTC: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
                print("    Running Partitions:")
                if partitions:
                    for part_id, part in partitions.items():
                        print(f"      - {part_id}")
                else:
                    print("      []")

        app_partition_map: Dict[Any, list] = {}
        with self.__clients_lock:
            for node in self.__clients.values():
                node_key = node.get_nodeId()
                node_resource_entry = (node_resources_registry or {}).get(f"{node_key[0]}:{node_key[1]}", {})
                logical_node_id = node_resource_entry.get("node_id", f"{node_key[0]}:{node_key[1]}")
                for part_id in node.get_running_partitions().keys():
                    if isinstance(part_id, tuple) and len(part_id) == 2 and isinstance(part_id[0], tuple):
                        app_key = part_id[0]
                        task_id = part_id[1]
                        app_partition_map.setdefault(app_key, []).append({
                            "task_id": task_id,
                            "assigned_node": logical_node_id,
                        })

        print("Workload:")
        print("  Running Apps:")
        if running_apps:
            for app_id, app_data in running_apps.items():
                partitions_data = app_partition_map.get(app_id, [])
                print("    -")
                print(f"      App ID: {app_id}")
                print("      status: RUNNING")
                print("      partitions:")
                if partitions_data:
                    normalized_partitions = [
                        {
                            "task_id": str(item.get("task_id", "unknown")),
                            "assigned_node": str(item.get("assigned_node", "unknown")),
                        }
                        for item in partitions_data
                    ]
                    normalized_partitions.sort(key=lambda item: (item["task_id"], item["assigned_node"]))
                    task_width = max(len("Task"), *(len(item["task_id"]) for item in normalized_partitions))
                    node_width = max(len("Assigned Node"), *(len(item["assigned_node"]) for item in normalized_partitions))
                    print(f"        {'Task':<{task_width}}  {'Assigned Node':<{node_width}}")
                    print(f"        {'-' * task_width}  {'-' * node_width}")
                    for item in normalized_partitions:
                        print(f"        {item['task_id']:<{task_width}}  {item['assigned_node']:<{node_width}}")
                else:
                    print("        []")
                print(f"      channels_config: {app_data}")
        else:
            print("    []")
        
        if snapshot_detail != "minimal":
            print("\n Policy: " + (policy.__class__.__name__ if policy else "None"))

            print("\n Registered GUIs:")
            if guis:
                for gui_id, (ip, port) in guis.items():
                    print(f"   GUI ID: {gui_id} at {ip}:{port}")
            else:
                print("  (No GUIs registered)")

        print("\nResource Registry Status:")
        free_resources = []
        used_resources = []
        if isinstance(resource_instances_status, dict):
            free_resources = resource_instances_status.get("free", []) or []
            used_resources = resource_instances_status.get("used", []) or []

        print(f"  Free Resources ({len(free_resources)}):")
        if free_resources:
            rows = [
                {
                    "resource_id": str(item.get("resource_id", "unknown")),
                    "type": str(item.get("type", "unknown")),
                    "state_flag": str(item.get("state_flag", "idle")),
                }
                for item in free_resources
            ]
            rows.sort(key=lambda row: row["resource_id"])
            id_width = max(len("Resource ID"), *(len(row["resource_id"]) for row in rows))
            type_width = max(len("Type"), *(len(row["type"]) for row in rows))
            state_width = max(len("State"), *(len(row["state_flag"]) for row in rows))
            print(f"    {'Resource ID':<{id_width}}  {'Type':<{type_width}}  {'State':<{state_width}}")
            print(f"    {'-' * id_width}  {'-' * type_width}  {'-' * state_width}")
            for row in rows:
                print(f"    {row['resource_id']:<{id_width}}  {row['type']:<{type_width}}  {row['state_flag']:<{state_width}}")
        else:
            print("    []")

        print(f"  Used Resources ({len(used_resources)}):")
        if used_resources:
            rows = []
            for item in used_resources:
                owner = item.get("used_by_app", "unknown")
                if isinstance(owner, list):
                    owner = ", ".join(str(entry) for entry in owner)
                rows.append(
                    {
                        "resource_id": str(item.get("resource_id", "unknown")),
                        "type": str(item.get("type", "unknown")),
                        "mode": str(item.get("reservation_mode", "unknown")),
                        "state_flag": str(item.get("state_flag", "unknown")),
                        "used_by": str(owner),
                    }
                )
            rows.sort(key=lambda row: row["resource_id"])
            id_width = max(len("Resource ID"), *(len(row["resource_id"]) for row in rows))
            type_width = max(len("Type"), *(len(row["type"]) for row in rows))
            mode_width = max(len("Mode"), *(len(row["mode"]) for row in rows))
            state_width = max(len("State"), *(len(row["state_flag"]) for row in rows))
            by_width = max(len("Used By"), *(len(row["used_by"]) for row in rows))
            print(
                f"    {'Resource ID':<{id_width}}  {'Type':<{type_width}}  {'Mode':<{mode_width}}  "
                f"{'State':<{state_width}}  {'Used By':<{by_width}}"
            )
            print(
                f"    {'-' * id_width}  {'-' * type_width}  {'-' * mode_width}  "
                f"{'-' * state_width}  {'-' * by_width}"
            )
            for row in rows:
                print(
                    f"    {row['resource_id']:<{id_width}}  {row['type']:<{type_width}}  {row['mode']:<{mode_width}}  "
                    f"{row['state_flag']:<{state_width}}  {row['used_by']:<{by_width}}"
                )
        else:
            print("    []")

        print("=" * 60)

        # Detailed per-partition device performance is shown only in full logging mode.
        # Root logger is configured at DEBUG, so use handler levels to reflect runtime verbosity.
        root_logger = logging.getLogger()
        debug_output_enabled = any(
            handler.level <= logging.DEBUG
            for handler in root_logger.handlers
        )
        if debug_output_enabled and snapshot_detail != "minimal":
            print(" Device Performance Per Partition:")
            device_performance = performance_tracker.get_device_performance_per_partition()
            for app_id, partitions in list(device_performance.items()):
                print(f"  App ID: {app_id}")
                for partition_id, devices in list(partitions.items()):
                    print(f"    Partition ID: {partition_id}")
                    for device_prefix, performance in list(devices.items()):
                        print(f"       Device Prefix: {device_prefix}")
                        for metric, value in list(performance.items()):
                            print(f"        - {Utils.MetricsFormattingUtils.format_runtime_metric(metric, value, default_mode=metrics_mode)}")

        print("=" * 60)
