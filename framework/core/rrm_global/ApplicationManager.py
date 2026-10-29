import copy
import json
import queue
import threading
import time
import os
import logging
import sys
from typing import Dict, List, Tuple, Any, Optional, Set

from core.models.DescriptorSchema import ChannelStructure, ParameterDefinition, ParameterType
from core.rrm_global.ResourceConstraintManager import ResourceConstraintManager
from Config import FRAMEWORK_DIR, MANIFEST_FOLDER

# Shared development tools live beside framework/, not inside it.
repository_dir = os.path.dirname(FRAMEWORK_DIR)
if repository_dir not in sys.path:
    sys.path.insert(0, repository_dir)

from tools.CheckerJSON import check_json

logger = logging.getLogger(__name__)


class ApplicationManager:
    """Manages application lifecycle: starting, stopping, and tracking running apps."""
    
    def __init__(self, get_channel_manager_fn=None):
        self.__running_apps: Dict[Tuple[str, int], List[Dict[str, Any]]] = {}
        self.__app_to_run = queue.Queue()
        self.__app_to_stop = queue.Queue()
        self.__partition_configured_queue = queue.Queue()  # Queue to receive partition configuration confirmations
        self.__resource_constraint_manager = ResourceConstraintManager()
        self.__used_exclusive_resource_ids: Set[str] = set()
        self.__app_used_resources: Dict[Tuple[str, int], Set[str]] = {}
        self.__app_resource_usage: Dict[Tuple[str, int], Dict[str, str]] = {}
        self.__resource_exclusive_owner: Dict[str, Tuple[str, int]] = {}
        self.__resource_shared_users: Dict[str, Set[Tuple[str, int]]] = {}
        self.__pending_start_partitions: Set[Tuple[str, str]] = set()
        self.__pending_start_lock = threading.Lock()
        # Use getter function to always access current channel_manager from RRMGlobal
        self.__get_channel_manager = get_channel_manager_fn

    def _track_used_resources_for_app(self, app_id: Tuple[str, int], resource_ids: Set[str]) -> Tuple[bool, str]:
        conflict_ids = sorted(resource_ids.intersection(self.__used_exclusive_resource_ids))
        if conflict_ids:
            return False, f"Resources already in use by another app: {conflict_ids}"

        if resource_ids:
            self.__used_exclusive_resource_ids.update(resource_ids)
            self.__app_used_resources[app_id] = set(resource_ids)
            logger.info(f"Tracked used resources for app {app_id}: {sorted(resource_ids)}")
        else:
            self.__app_used_resources[app_id] = set()

        return True, ""

    def _release_resources_for_app(self, app_id: Tuple[str, int]) -> None:
        used_ids = self.__app_used_resources.pop(app_id, set())
        if used_ids:
            self.__used_exclusive_resource_ids.difference_update(used_ids)

        usage = self.__app_resource_usage.pop(app_id, {})
        for resource_id, mode in usage.items():
            if mode == "exclusive":
                current_owner = self.__resource_exclusive_owner.get(resource_id)
                if current_owner == app_id:
                    self.__resource_exclusive_owner.pop(resource_id, None)
            else:
                shared_users = self.__resource_shared_users.get(resource_id)
                if shared_users:
                    shared_users.discard(app_id)
                    if not shared_users:
                        self.__resource_shared_users.pop(resource_id, None)

        if used_ids or usage:
            logger.info(
                "Released resources for app %s: exclusive=%s, usage=%s",
                app_id,
                sorted(used_ids),
                {key: usage[key] for key in sorted(usage.keys())},
            )

    @staticmethod
    def _merge_usage_mode(current_mode: Optional[str], new_mode: str) -> str:
        # Exclusive has higher priority than shared for mixed references.
        if current_mode == "exclusive" or new_mode == "exclusive":
            return "exclusive"
        return "shared"

    def _register_resource_usage_for_app(self, app_id: Tuple[str, int], usage_map: Dict[str, str]) -> None:
        normalized_usage: Dict[str, str] = {}
        for resource_id, mode in (usage_map or {}).items():
            rid = str(resource_id).strip()
            if not rid:
                continue
            normalized_mode = "exclusive" if str(mode).lower() == "exclusive" else "shared"
            normalized_usage[rid] = self._merge_usage_mode(normalized_usage.get(rid), normalized_mode)

        self.__app_resource_usage[app_id] = normalized_usage

        for resource_id, mode in normalized_usage.items():
            if mode == "exclusive":
                self.__resource_exclusive_owner[resource_id] = app_id
                self.__resource_shared_users.pop(resource_id, None)
            else:
                shared_users = self.__resource_shared_users.setdefault(resource_id, set())
                shared_users.add(app_id)

    def _format_precheck_error(self, app_id: str, code: str, details: List[str]) -> str:
        compact_details = [str(d).strip() for d in details if str(d).strip()]
        if not compact_details:
            compact_details = ["Unknown pre-check failure."]

        numbered = "\n".join(f"  {idx + 1}) {msg}" for idx, msg in enumerate(compact_details))
        return (
            f"PRECHECK_FAILED[{code}] app='{app_id}' details={len(compact_details)}\n"
            f"{numbered}"
        )
    
    def get_running_apps(self) -> Dict[Tuple[str, int], List[Dict[str, Any]]]:
        """Get the dictionary of running applications."""
        return self.__running_apps
    
    def get_app_to_run_queue(self) -> queue.Queue:
        """Get the queue of apps to run."""
        return self.__app_to_run
    
    def get_app_to_stop_queue(self) -> queue.Queue:
        """Get the queue of apps to stop."""
        return self.__app_to_stop
    
    def get_partition_configured_queue(self) -> queue.Queue:
        """Get the queue for partition configuration confirmations."""
        return self.__partition_configured_queue

    def _clear_partition_configured_queue(self) -> int:
        """Drop stale startup events left by previous app lifecycles."""
        dropped = 0
        while True:
            try:
                self.__partition_configured_queue.get_nowait()
                dropped += 1
            except queue.Empty:
                break
        return dropped

    def _mark_partition_start_pending(self, app_id: str, partition_id: str) -> None:
        with self.__pending_start_lock:
            self.__pending_start_partitions.add((str(app_id), str(partition_id)))

    def _unmark_partition_start_pending(self, app_id: str, partition_id: str) -> None:
        with self.__pending_start_lock:
            self.__pending_start_partitions.discard((str(app_id), str(partition_id)))

    def _clear_pending_starts_for_app(self, app_id: Tuple[str, int]) -> None:
        app_key = str(app_id)
        with self.__pending_start_lock:
            to_remove = [item for item in self.__pending_start_partitions if item[0] == app_key]
            for item in to_remove:
                self.__pending_start_partitions.discard(item)

    def is_partition_start_pending(self, app_id: str, partition_id: str) -> bool:
        with self.__pending_start_lock:
            return (str(app_id), str(partition_id)) in self.__pending_start_partitions

    def has_pending_startups(self) -> bool:
        with self.__pending_start_lock:
            return bool(self.__pending_start_partitions)

    def get_resource_instances_status(self) -> Dict[str, Any]:
        """Return resource instances split by free/used with occupancy state flags."""
        instances = self.__resource_constraint_manager.get_resource_instances_snapshot()

        used_resources: List[Dict[str, Any]] = []
        free_resources: List[Dict[str, Any]] = []

        for resource_id in sorted(instances.keys()):
            instance = instances.get(resource_id, {})
            item = {
                "resource_id": resource_id,
                "type": instance.get("type", "unknown"),
                "location": instance.get("location", {}),
            }

            if resource_id in self.__resource_exclusive_owner:
                owner = self.__resource_exclusive_owner[resource_id]
                used_resources.append({
                    **item,
                    "reservation_mode": "exclusive",
                    "state_flag": "busy-in-exclusive-mode",
                    "used_by_app": str(owner),
                })
            elif resource_id in self.__resource_shared_users and self.__resource_shared_users[resource_id]:
                owners = sorted(self.__resource_shared_users[resource_id], key=lambda app: str(app))
                used_resources.append({
                    **item,
                    "reservation_mode": "shared",
                    "state_flag": "used-in-shared-mode",
                    "used_by_app": [str(owner) for owner in owners],
                })
            else:
                free_resources.append({
                    **item,
                    "reservation_mode": "none",
                    "state_flag": "idle",
                })

        return {
            "free": free_resources,
            "used": used_resources,
        }

    def list_available_app_descriptors(self) -> List[Dict[str, Any]]:
        """Return a list of executable parameter sets for all applications.

        Previously the method returned the full manifest for each descriptor.  To reduce
        payload size and only send what the GUI/CLI needs, we now return a map with the
        application id and the ``executable``→``parameters`` section of the manifest.

        Skips files that cannot be parsed and ignores the special
        ``DevicePerformancePerPartition.json`` file.
        """
        apps: List[Dict[str, Any]] = []
        try:
            for fname in os.listdir(MANIFEST_FOLDER):
                if not fname.endswith(".json") or fname == "DevicePerformancePerPartition.json":
                    continue
                path = os.path.join(MANIFEST_FOLDER, fname)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    # extract executable parameters (default to empty dict)
                    exec_conf = data.get("executable", {})
                    params = exec_conf.get("parameters", {})
                    apps.append({
                        "appID": os.path.splitext(fname)[0],
                        "parameters": params
                    })
                except Exception as e:
                    logger.warning(f"Unable to load descriptor '{fname}': {e}")
        except Exception as e:
            logger.error(f"Error listing available descriptors: {e}")
        return apps
    
    def start_app(self, appId: str, user_args: Dict[str, Any], clients: Dict[Tuple[str, int], Any],
                  get_policy_fn, get_performance_tracker_fn,
                  startup_wait_lock=None) -> Optional[Tuple[str, int]]:
        """
        Start an application with the given ID and user arguments.
        
        Returns:
            - Tuple (appId, app_counter) on success
            - Tuple ("ERROR", error_message) on validation/placement failure
            - None on timeout/runtime failure
        """
        self.__resource_constraint_manager.reload()
        # Validate the manifest file before loading
        manifest_path = MANIFEST_FOLDER + appId + ".json"
        is_valid, error_msg = check_json(manifest_path, verbose=False)
        if not is_valid:
            error_message = f"Invalid manifest file for app '{appId}': {error_msg}"
            logger.error(f"Validation Error: {error_message}")
            return ("ERROR", error_message)
        
        # Read file Json manifest
        with open(manifest_path, "r", encoding="utf-8") as file:
            data = json.load(file)    

        constraint_result = None
        user_set_linked_params = []
        resources_to_reserve: Set[str] = set()
        resources_usage_map: Dict[str, str] = {}

        # Validate task resource constraints before placement/start
        try:
            linked_params = self.__resource_constraint_manager.get_constraint_linked_parameters(data)
            user_set_linked_params = [
                param_name for param_name in linked_params
                if (param_name in user_args) and (user_args.get(param_name) is not None) and (str(user_args.get(param_name)).strip() != "")
            ]

            has_user_set_linked_params = len(user_set_linked_params) > 0

            if has_user_set_linked_params:
                used_exclusive_ids = set(self.__used_exclusive_resource_ids)
                validation_errors = []
                for param_name in user_set_linked_params:
                    ok, err = self.__resource_constraint_manager.validate_linked_parameter_value(
                        data,
                        param_name,
                        user_args.get(param_name),
                        used_exclusive_ids,
                    )
                    if not ok:
                        validation_errors.append(err)

                if validation_errors:
                    error_message = self._format_precheck_error(
                        appId,
                        "USER_LINKED_PARAMS",
                        validation_errors,
                    )
                    logger.error(error_message)
                    return ("ERROR", error_message)

                for param_name in user_set_linked_params:
                    resources_to_reserve.update(
                        self.__resource_constraint_manager.collect_exclusive_instances_for_linked_parameter(
                            data,
                            param_name,
                            user_args.get(param_name),
                        )
                    )

                for task in data.get("taskgraph", []):
                    requires = task.get("requires", [])
                    if not isinstance(requires, list):
                        continue
                    for req in requires:
                        parameter_linked = req.get("parameter_linked")
                        if parameter_linked not in user_set_linked_params:
                            continue
                        selected_instances = self.__resource_constraint_manager._parse_linked_value_to_ids(
                            user_args.get(parameter_linked),
                            req.get("separator", ""),
                        )
                        effective_exclusive_instances = self.__resource_constraint_manager.get_effective_exclusive_instances(
                            req,
                            selected_instances,
                        )
                        for instance_id in selected_instances:
                            mode = "exclusive" if instance_id in effective_exclusive_instances else "shared"
                            current_mode = resources_usage_map.get(instance_id)
                            resources_usage_map[instance_id] = self._merge_usage_mode(current_mode, mode)
            else:
                constraint_result = self.__resource_constraint_manager.validate_manifest_constraints(
                    data,
                    pre_used_exclusive_ids=self.__used_exclusive_resource_ids,
                )
                if not constraint_result.get("valid", False):
                    constraint_errors = constraint_result.get("errors", [])
                    error_message = self._format_precheck_error(
                        appId,
                        "AUTO_RESOLVE",
                        constraint_errors,
                    )
                    logger.error(error_message)
                    return ("ERROR", error_message)

                resources_to_reserve.update(
                    allocation_instance
                    for allocation in constraint_result.get("allocations", [])
                    for allocation_instance in allocation.get("exclusive_instances", [])
                )

                for allocation in constraint_result.get("allocations", []):
                    exclusive_instances = set(allocation.get("exclusive_instances", []))
                    for instance_id in allocation.get("selected_instances", []):
                        mode = "exclusive" if instance_id in exclusive_instances else "shared"
                        current_mode = resources_usage_map.get(instance_id)
                        resources_usage_map[instance_id] = self._merge_usage_mode(current_mode, mode)

                # Use parameters resolved by ResourceConstraintManager unless explicitly set by user
                resolved_parameters = constraint_result.get("resolved_parameters", {})
                if resolved_parameters:
                    merged_user_args = dict(resolved_parameters)
                    if user_args:
                        merged_user_args.update(user_args)
                    user_args = merged_user_args
                    logger.info(f"Resolved constraint-linked parameters for app {appId}: {resolved_parameters}")
        except Exception as e:
            error_message = self._format_precheck_error(
                appId,
                "INTERNAL_EXCEPTION",
                [str(e)],
            )
            logger.error(error_message)
            return ("ERROR", error_message)

        config_data = data["configurations"]
        
        # Extract setup timeout from the manifest executable configuration
        executable_config = data["executable"]
        timeouts = executable_config.get("timeouts", {})
        setup_timeout = timeouts.get("setup", 60) + 5  # Default to 60 seconds if not specified. + 5 seconds buffer for communication overhead
        logger.info(f"Using setup timeout: {setup_timeout} seconds for app {appId}")
        
        clients_copy = {}
        # Check if all required nodes are ready
        # Optimized: only copy necessary data instead of deep copying entire node
        for node in clients.values():
            if node.is_ready():
                # Create a shallow copy and explicitly copy mutable attributes
                import copy as copy_module
                node_copy = copy_module.copy(node)
                # Only deep copy the mutable collections that will be modified
                node_copy._Node__available_ports = node.get_available_ports().copy()
                clients_copy[node.get_nodeId()] = node_copy
            else:
                logger.error(f"Node {node.get_nodeId()} is not ready (status: {node.get_node_status().value})")

        # Check if we have any ready nodes available
        if not clients_copy:
            error_msg = "No devices available. All nodes are either disconnected or not ready."
            logger.error(error_msg)
            return ("ERROR", error_msg)

        try:
            config_data, configId = get_policy_fn().get_best_placement(clients_copy, config_data)
        except Exception as e:
            error_msg = f"Failed to find suitable placement for application: {str(e)}"
            logger.error(error_msg)
            return ("ERROR", error_msg)

        app_id_counter = 0
        alreadyUsed = True
        while alreadyUsed:
            alreadyUsed = False
            for j in self.__running_apps.keys():
                if j[0] == appId and j[1] == app_id_counter:
                    alreadyUsed = True
                    app_id_counter += 1
                    break
        logger.info(f"Starting app {appId} with app_id_counter {app_id_counter}")
        appId_tuple = (appId, app_id_counter)

        track_ok, track_err = self._track_used_resources_for_app(appId_tuple, resources_to_reserve)
        if not track_ok:
            error_message = f"Resource constraints not satisfied for app '{appId}': {track_err}"
            logger.error(error_message)
            return ("ERROR", error_message)

        self._register_resource_usage_for_app(appId_tuple, resources_usage_map)

        dropped_events = self._clear_partition_configured_queue()
        if dropped_events:
            logger.debug("Cleared %d stale startup event(s) before starting app %s", dropped_events, appId_tuple)

        # Create channels with proper structure using ChannelStructure
        channels_config = []
        for channel_basic in config_data["channels"]:
            # Create full channel structure with default type
            channel = ChannelStructure.create_channel(
                channel_basic["from_partition"],
                channel_basic["to_partition"]
            )
            channels_config.append(channel)
        
        # Populate the channels config with the IP and port of the clients
        for channel in channels_config:
            for partition in config_data["partitions"]:
                if channel["from_partition"] == partition["id"]:
                    ip_src, port_src = partition["node"]
                if channel["to_partition"] == partition["id"]:
                    ip_dst, port_dst = partition["node"]
            channel["parameters"]["ip_src"] = ip_src
            channel["parameters"]["port_src"] = str(clients_copy[(ip_src, port_src)].pop_next_available_port())

            # Remove the port from all the node with the same ip
            for client in clients_copy.values():
                if client.get_nodeId()[0] == ip_src:
                   client.remove_port(channel["parameters"]["port_src"])
            
            channel["parameters"]["ip_dst"] = ip_dst
            channel["parameters"]["port_dst"] = str(clients_copy[(ip_dst, port_dst)].pop_next_available_port())

            # Remove the port from all the node with the same ip
            for client in clients_copy.values():
                if client.get_nodeId()[0] == ip_dst:
                   client.remove_port(channel["parameters"]["port_dst"])

        try:
            for partition in config_data["partitions"]:
                Id = partition["id"]
                uniqueId = (appId_tuple, Id)
                expected_app = str(appId_tuple)
                expected_partition = str(Id)
                channels_for_a_partition = []
                
                # Obtain parameters of the channels
                for channel in channels_config:
                    if channel["from_partition"] == Id or channel["to_partition"] == Id:
                        channels_for_a_partition.append(channel)

                # Build parameters using ParameterDefinition with user-provided values from executable config
                user_params = data["executable"]["parameters"].copy()
                param = ParameterDefinition.merge_parameters(user_params)
                
                # Set system-managed parameters
                param["Ind_conf"]["value"] = str(configId)
                param["Id_part"]["value"] = Id
                param["channels"]["value"] = channels_for_a_partition
                
                # Remove localarg parameters (managed by RRM Local)
                keys_to_remove = []
                for key, value in param.items():
                    if value.get("type") == ParameterType.LOCALARG.value:
                        keys_to_remove.append(key)
                for key in keys_to_remove:
                    del param[key]

                # Apply user-provided arguments
                for key, value in user_args.items():
                    if key in param:
                        param[key]["value"] = value
                        logger.info(f"User argument {key} set to {value} for partition {Id} of app {appId_tuple}")
                    else:
                        logger.warning(f"User argument {key} not found in the application parameters. It will be ignored")

                logger.info(f"Starting partition {Id} of app {appId_tuple} on node {partition['node']}")
                from core.communication.Message import GlobalStartPartition
                if self.__get_channel_manager is None:
                    raise RuntimeError("Channel manager not initialized")
                self._mark_partition_start_pending(expected_app, expected_partition)
                self.__get_channel_manager().send_message(clients[partition["node"]].get_clientId(),
                                            GlobalStartPartition(uniqueID=uniqueId, app_id=appId, param=param))

                # Do not hold the node registry lock while waiting. Otherwise a
                # Local.Status received just before Local.PartitionConfigured can
                # block the sole network reader on that same lock, leaving the ACK
                # queued until this timeout expires.
                wait_lock_released = False
                try:
                    if startup_wait_lock is not None:
                        startup_wait_lock.release()
                        wait_lock_released = True

                    wait_start = time.time()
                    while True:
                        remaining = setup_timeout - (time.time() - wait_start)
                        if remaining <= 0:
                            self._unmark_partition_start_pending(expected_app, expected_partition)
                            raise RuntimeError(f"Timeout ({setup_timeout}s) starting partition {Id} of app {appId_tuple} on node {partition['node']}")

                        try:
                            startup_event = self.__partition_configured_queue.get(timeout=remaining)
                        except queue.Empty:
                            self._unmark_partition_start_pending(expected_app, expected_partition)
                            raise RuntimeError(f"Timeout ({setup_timeout}s) starting partition {Id} of app {appId_tuple} on node {partition['node']}")

                        if startup_event is True:
                            # Backward-compatible ack from older RRMLocal versions.
                            self._unmark_partition_start_pending(expected_app, expected_partition)
                            break

                        if not isinstance(startup_event, dict):
                            logger.debug("Ignoring unknown startup queue event: %r", startup_event)
                            continue

                        event_app = str(startup_event.get("appID") or "")
                        event_partition = str(startup_event.get("partitionID") or "")
                        if event_app and event_app != expected_app:
                            logger.debug("Ignoring startup event for another app: %s", event_app)
                            continue
                        if event_partition and event_partition != expected_partition:
                            logger.debug("Ignoring startup event for another partition: %s", event_partition)
                            continue

                        status = str(startup_event.get("status") or "").lower()
                        if status == "ok":
                            self._unmark_partition_start_pending(expected_app, expected_partition)
                            break
                        if status == "failed":
                            phase = str(startup_event.get("phase") or "runtime")
                            exc_type = str(startup_event.get("exception_type") or "Exception")
                            exc_text = str(startup_event.get("exception_text") or "")
                            self._unmark_partition_start_pending(expected_app, expected_partition)
                            raise RuntimeError(
                                f"Partition {Id} of app {appId_tuple} failed during {phase}: {exc_type}: {exc_text}"
                            )

                        logger.debug("Ignoring startup event with unknown status: %r", startup_event)
                finally:
                    if wait_lock_released:
                        startup_wait_lock.acquire()
                
                logger.info(f"Successfully started partition {Id} of app {appId_tuple} on node {partition['node']}")
                clients_copy[partition["node"]].add_running_partition((appId_tuple, Id))
                # TODO check if we can avoid using a deepcopy of the clients nodes
        except RuntimeError as exc:
            logger.error(f"Failed starting partition {Id} of app {appId_tuple} on node {partition['node']}: {exc}")
            self._clear_pending_starts_for_app(appId_tuple)
            
            # Mark node as disconnected only for startup timeout failures.
            from core.models.Node import NodeStatus
            if partition["node"] in clients and "Timeout (" in str(exc):
                clients[partition["node"]].set_node_status(NodeStatus.DISCONNECTED)
            
            # Rollback: stop any partitions that were already started for this app
            for node in clients_copy.values():
                logger.debug(f"Checking node {node.get_nodeId()} for running partitions of app {appId_tuple}")
                logger.debug(f"Running partitions: {node.get_running_partitions()}")
                
                # Check if this node has any running partitions for the current app
                partitions_to_stop = None
                for partition_key in node.get_running_partitions().keys():
                    # partition_key is a tuple like ((appId, app_counter), partition_id)
                    if partition_key[0] == appId_tuple:
                        from core.communication.Message import GlobalStopPartition
                        if self.__get_channel_manager is None:
                            raise RuntimeError("Channel manager not initialized")
                        self.__get_channel_manager().send_message(
                            node.get_clientId(),
                            GlobalStopPartition(partitionId=partition_key)
                        )
                        partitions_to_stop = partition_key
                        break
                if partitions_to_stop is not None:
                    node.remove_running_partition(partitions_to_stop)
            self._release_resources_for_app(appId_tuple)
            return None
        
        # Update clients with modified copies
        for node in clients_copy.values():
            clients[node.get_nodeId()] = node
        
        self.__running_apps[appId_tuple] = channels_config
        return appId_tuple

    def stop_app(self, AppId: Tuple[str, int], clients: Dict[Tuple[str, int], Any]) -> None:
        """Stop a running application and free its resources."""
        AppId = (AppId[0], AppId[1])  # Ensure it's a proper tuple
        if AppId not in self.__running_apps:
            logger.warning(f"App {AppId} is not running, cannot stop it")
            self._release_resources_for_app(AppId)
            return
        
        if self.__get_channel_manager is None:
            logger.warning("Channel manager not initialized, cannot send stop messages")
            # Still proceed to clean up local state
        
        for node in clients.values():
            for partition in list(node.get_running_partitions().keys()):
                if partition[0] == AppId:
                    if node.get_clientId() is not None and self.__get_channel_manager is not None:
                        from core.communication.Message import GlobalStopPartition
                        self.__get_channel_manager().send_message(
                            node.get_clientId(),
                            GlobalStopPartition(partitionId=partition)
                        )
                    node.remove_running_partition(partition)

        channel: List[Dict[str, Any]] = self.__running_apps.pop(AppId)

        ip_to_clients = {}
        for client in clients.values():
            ip = client.get_nodeId()[0]
            if ip not in ip_to_clients:
                ip_to_clients[ip] = []
            ip_to_clients[ip].append(client)
        
        for ch in channel:
            ip_src = ch["parameters"]["ip_src"]
            port_src = int(ch["parameters"]["port_src"])
            ip_dst = ch["parameters"]["ip_dst"]
            port_dst = int(ch["parameters"]["port_dst"])

            # Restore port for source IP - O(1) lookup
            for client in ip_to_clients.get(ip_src, []):
                client.free_port(port_src)
            
            # Restore port for destination IP - O(1) lookup
            for client in ip_to_clients.get(ip_dst, []):
                client.free_port(port_dst)

        self._release_resources_for_app(AppId)
