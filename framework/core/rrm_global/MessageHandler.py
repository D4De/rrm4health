import ast
import logging
import time
import traceback
from typing import Dict, Tuple, Any, List

import policy.PolicyUtils as PolicyUtils
from core.communication.MessageTypes import MessageTypes
from core.communication.Message import *
from core.monitoring.MetricFields import MetricField
from core.models.Node import NodeStatus

logger = logging.getLogger(__name__)


class MessageHandler:
    """Handles routing and processing of messages from nodes and GUIs."""
    
    def __init__(self, node_manager, app_manager, channel_manager, 
                 get_policy_fn, get_performance_tracker_fn, get_required_fields_fn, get_guis_fn,
                 get_capabilities_mode_fn,
                 get_capabilities_window_seconds_fn,
                 get_capabilities_sample_interval_seconds_fn,
                 set_policy_fn=None,
                 upsert_node_resources_fn=None,
                 remove_node_resources_fn=None,
                 get_resource_registry_snapshot_fn=None):
        self.__node_manager = node_manager
        self.__app_manager = app_manager
        self.__channel_manager = channel_manager
        # Use getter functions to always access current values from RRMGlobal
        self.__get_policy = get_policy_fn
        self.__get_performance_tracker = get_performance_tracker_fn
        self.__get_required_fields = get_required_fields_fn
        self.__get_guis = get_guis_fn
        self.__get_capabilities_mode = get_capabilities_mode_fn
        self.__get_capabilities_window_seconds = get_capabilities_window_seconds_fn
        self.__get_capabilities_sample_interval_seconds = get_capabilities_sample_interval_seconds_fn
        self.__set_policy = set_policy_fn  # Callback to set policy in RRMGlobal
        self.__upsert_node_resources = upsert_node_resources_fn
        self.__remove_node_resources = remove_node_resources_fn
        self.__get_resource_registry_snapshot = get_resource_registry_snapshot_fn

    def _notify_guis(self, message: str, severity: str = "info", category: str = "generic",
                     app_id: Any = None, node_id: Any = None) -> None:
        """Broadcast a textual notification to all connected GUIs."""
        if self.__channel_manager is None:
            return

        guis = self.__get_guis() if self.__get_guis else {}
        if not isinstance(guis, dict) or not guis:
            return

        app_id_text = "" if app_id is None else str(app_id)
        node_id_text = "" if node_id is None else str(node_id)

        for gui_client_id in list(guis.keys()):
            try:
                self.__channel_manager.send_message(
                    gui_client_id,
                    GlobalGuiNotification(
                        message=str(message),
                        severity=str(severity or "info").lower(),
                        category=str(category or "generic"),
                        appID=app_id_text,
                        nodeID=node_id_text,
                    ),
                )
            except Exception as exc:
                logger.warning("Failed to notify GUI %s: %s", gui_client_id, exc)
    
    def handle_message(self, clientId: bytes, msg_dict: Dict[str, Any]) -> None:
        """Main message routing handler."""
        client_id_str = clientId.decode('utf-8')  
        ip, port = client_id_str.split(':')  
        node_id = (ip, int(port))

        try:
            msg = message_factory(msg_dict)
        except ValueError as e:
            logger.error(f"Error decoding message: {e}")
            traceback.print_exc()
            return

        # Gui nodes will have source "GUI"
        source: str = getattr(msg, "source", None)

        if source != "GUI":
            self._handle_node_message(clientId, node_id, msg)
        elif source == "GUI":
            self._handle_gui_message(clientId, node_id, msg)
    
    def _handle_node_message(self, clientId: bytes, node_id: Tuple[str, int], msg) -> None:
        """Handle messages from RRM Local nodes."""
        if msg.type == MessageTypes.LOCAL_CONNECT:
            all_metric_fields = [field.value for field in MetricField]
            previous_node_count = len(self.__node_manager.get_client_list())
            client = self.__node_manager.add_client(node_id, clientId)
            logger.info(f"New client connected: {clientId} with Node ID {node_id}")
            if len(self.__node_manager.get_client_list()) != previous_node_count:
                self._notify_guis(
                    message="UPDATE",
                    category="nodes_update",
                    node_id=node_id,
                )
            self.__channel_manager.send_message(clientId, GlobalConnectResponse())
            self.__channel_manager.send_message(clientId,
                                               GlobalRequestCapabilities(
                                                   fields=self.__get_required_fields(),
                                                   mode=self.__get_capabilities_mode(),
                                                   window_seconds=self.__get_capabilities_window_seconds(),
                                                   sample_interval_seconds=self.__get_capabilities_sample_interval_seconds(),
                                               ))
            self.__channel_manager.send_message(clientId, GlobalSetPolicy(
                policy_name=type(self.__get_policy()).name(), 
                resources_to_collect=all_metric_fields,
                process_resources_to_collect=self.__get_performance_tracker().get_required_fields()))

        elif msg.type == MessageTypes.LOCAL_PARTITION_CONFIGURED:
            event_app_id = str(getattr(msg, "appID", "") or "")
            event_partition_id = str(getattr(msg, "partitionID", "") or "")

            # Correlated ack (new RRMLocal): enqueue only if that partition is actually pending startup.
            if event_app_id and event_partition_id:
                if self.__app_manager.is_partition_start_pending(event_app_id, event_partition_id):
                    self.__app_manager.get_partition_configured_queue().put(
                        {
                            "status": "ok",
                            "appID": event_app_id,
                            "partitionID": event_partition_id,
                            "node_id": str(node_id),
                        }
                    )
                    logger.info(
                        "Accepted partition configured event: app=%s partition=%s node=%s",
                        event_app_id,
                        event_partition_id,
                        node_id,
                    )
                else:
                    logger.debug(
                        "Ignoring LOCAL_PARTITION_CONFIGURED for non-pending startup app=%s partition=%s",
                        event_app_id,
                        event_partition_id,
                    )
            # Legacy ack (old RRMLocal): accept only if at least one startup is pending.
            elif self.__app_manager.has_pending_startups():
                self.__app_manager.get_partition_configured_queue().put(True)
            else:
                logger.debug("Ignoring legacy LOCAL_PARTITION_CONFIGURED with no pending startup")
        
        elif msg.type == MessageTypes.LOCAL_STATUS:
            self._handle_status_update(node_id, msg)
        
        elif msg.type == MessageTypes.LOCAL_APPLICATION_DISCONNECTED:
            self._handle_app_disconnected(node_id, msg)
        
        elif msg.type == MessageTypes.LOCAL_CAPABILITIES:
            self._handle_capabilities(clientId, node_id, msg)
        
        elif msg.type == MessageTypes.LOCAL_SHUTDOWN:
            self._handle_node_shutdown(clientId, node_id)
        
        elif msg.type == MessageTypes.LOCAL_BOARD_INFO:
            self._handle_board_info(clientId, node_id, msg)

        elif msg.type == MessageTypes.LOCAL_RESOURCES_SYNC:
            self._handle_resources_sync(clientId, node_id, msg)

        elif msg.type == MessageTypes.LOCAL_GUI_NOTIFICATION:
            self._handle_gui_notification(node_id, msg)
        
        else:
            logger.warning(f"Received unknown message from client {clientId}: {msg}")
    
    def _handle_status_update(self, node_id: Tuple[str, int], msg) -> None:
        """Handle LOCAL_STATUS messages."""
        client = self.__node_manager.get_client(node_id)
        if not client:
            logger.warning(f"Received status from unknown node {node_id}. Ignoring.")
            return
        
        # If node was marked as DISCONNECTED, mark it as responding again
        if client.get_node_status() == NodeStatus.DISCONNECTED:
            logger.info(f"Node {node_id} is responding again. Changing status from DISCONNECTED to READY.")
            self.__node_manager.set_client_node_status(node_id, NodeStatus.READY)
        
        for partition in msg.running_partitions:
            app_id: Tuple[str, int] = partition["id"][0]
            unique_id: Tuple[Tuple[str, int], int] = ((app_id[0], app_id[1]), partition["id"][1])
            if unique_id not in client.get_running_partitions():
                logger.warning(f"Received status for partition {unique_id} from node {node_id} not present in the global RRM.")
                continue
            else:
                client.get_running_partitions()[unique_id].update_utilization(
                    partition.get("utilization", {}))
                client.get_running_partitions()[unique_id].add_devices_status(partition.get("devices_status", {}))

        old_utilization: Dict[str, Any] = client.get_status()
        new_utilization: Dict[str, Any] = msg.status

        next_update_time: float = self.__get_policy().get_next_update_time(new_utilization, old_utilization)

        logger.debug(f"Node {node_id} status updated. Next update in {next_update_time} seconds.")

        self.__node_manager.set_client_next_update_time(node_id, time.time() + next_update_time)
        self.__node_manager.update_client_status(node_id, msg.status)

        self.__get_performance_tracker().update_partition_consumption(msg.running_partitions, client.get_prefix())

    def _handle_gui_notification(self, node_id: Tuple[str, int], msg) -> None:
        """Broadcast a textual notification emitted by an application."""
        print(f"Received GUI notification from node {node_id}: {msg.message}")
        self._notify_guis(
            message=msg.message,
            severity=getattr(msg, "severity", "info"),
            category="application_message",
            app_id=getattr(msg, "appID", ""),
            node_id=node_id,
        )
    
    def _handle_app_disconnected(self, node_id: Tuple[str, int], msg) -> None:
        """Handle LOCAL_APPLICATION_DISCONNECTED messages."""
        app_id = msg.appID[0]
        app_id = (app_id[0], app_id[1])
        partition_id = (app_id, msg.appID[1])
        logger.info(f"Received application disconnected message for app {app_id} from node {node_id}")

        reason = str(getattr(msg, "reason", "") or "")
        phase = str(getattr(msg, "phase", "") or "")
        exception_type = str(getattr(msg, "exception_type", "") or "")
        exception_text = str(getattr(msg, "exception_text", "") or "")
        traceback_text = str(getattr(msg, "traceback_text", "") or "")

        if exception_type or exception_text:
            notification_text = (
                f"Unhandled exception in app {app_id} (partition {partition_id[1]}, phase={phase or 'runtime'}): "
                f"{exception_type or 'Exception'}: {exception_text}"
            )
            self._notify_guis(
                message=notification_text,
                severity="error",
                category="app_uncaught_exception",
                app_id=app_id,
                node_id=node_id,
            )
            logger.error(
                "Uncaught app exception from node %s - app=%s partition=%s phase=%s: %s: %s",
                node_id,
                app_id,
                partition_id[1],
                phase or "runtime",
                exception_type or "Exception",
                exception_text,
            )
            if traceback_text:
                logger.error("Traceback from app crash:\n%s", traceback_text)
        elif reason == "self_stop":
            self._notify_guis(
                message=f"Application {app_id} stopped autonomously on node {node_id}",
                severity="info",
                category="app_self_stopped",
                app_id=app_id,
                node_id=node_id,
            )
        else:
            self._notify_guis(
                message=f"Application {app_id} disconnected on node {node_id}",
                severity="warning",
                category="app_disconnected",
                app_id=app_id,
                node_id=node_id,
            )

        # Signal startup pipeline only for failures during startup phases.
        if (phase or "").lower() in ("setup", "bootstrap") and (exception_type or exception_text):
            pending = self.__app_manager.is_partition_start_pending(str(app_id), str(partition_id[1]))
            if not pending:
                logger.debug(
                    "Ignoring startup-failed event for non-pending startup app=%s partition=%s",
                    app_id,
                    partition_id[1],
                )
                return
            self.__app_manager.get_partition_configured_queue().put(
                {
                    "status": "failed",
                    "appID": str(app_id),
                    "partitionID": str(partition_id[1]),
                    "node_id": str(node_id),
                    "phase": phase,
                    "exception_type": exception_type,
                    "exception_text": exception_text,
                }
            )
        
        if app_id in self.__app_manager.get_running_apps().keys():
            # Remove the app from this node's running apps (to avoid to stop it a second time)
            client = self.__node_manager.get_client(node_id)
            if client:
                client.remove_running_partition(partition_id)
            # Remove the app from the global running apps and stop all the other partitions from other nodes
            self.__app_manager.stop_app(app_id, self.__node_manager.get_all_clients())
            logger.info(f"App {app_id} disconnected.")
            self._notify_guis(
                message="UPDATE",
                category="applications_update",
                app_id=app_id,
                node_id=node_id,
            )
        else:
            logger.warning(f"App {app_id} not found in running apps.")
    
    def _handle_capabilities(self, clientId: bytes, node_id: Tuple[str, int], msg) -> None:
        """Handle LOCAL_CAPABILITIES messages."""
        logger.debug(f"Received capabilities from client {clientId}: {msg}")
        client = self.__node_manager.get_client(node_id)
        if client:
            capabilities: Dict[str, Any] = msg.data
            previous_node_status = client.get_node_status()
            self.__node_manager.set_client_capabilities(node_id, capabilities)
            # Node status is automatically set to READY in set_capabilities method
            logger.info(f"Node {node_id} with prefix {client.get_prefix()} capabilities updated: {capabilities}")
            logger.info(f"Node {node_id} status: {client.get_node_status().value}")
            if previous_node_status == NodeStatus.SETUP and client.get_node_status() == NodeStatus.READY:
                self._notify_guis(
                    message="UPDATE",
                    category="nodes_update",
                    node_id=node_id,
                )
        else:
            logger.warning(f"Received device prefix from unknown node {node_id}")

    def _handle_node_shutdown(self, clientId: bytes, node_id: Tuple[str, int]) -> None:
        """Handle LOCAL_SHUTDOWN messages."""
        logger.info(f"Received shutdown notification from {clientId}. Killing all the apps with partitions on this node.")
        self._notify_guis(
            message=f"Node {node_id} sent shutdown/disconnect notification",
            severity="error",
            category="node_shutdown",
            node_id=node_id,
        )

        if self.__remove_node_resources is not None:
            self.__remove_node_resources(node_id)
        
        self.__node_manager.set_client_node_status(node_id, NodeStatus.DISCONNECTED)
        self.__node_manager.clear_client_id(node_id)  # Clear clientId to avoid sending messages to a dead client
        
        client = self.__node_manager.get_client(node_id)
        if client:
            # Create a list copy since we're modifying during iteration
            for running_partition in list(client.get_running_partitions().keys()):
                self.__app_manager.stop_app(running_partition[0], self.__node_manager.get_all_clients())
        
        # Remove the node from the clients
        if self.__node_manager.remove_client(node_id):
            logger.info(f"Node {node_id} removed from clients.")
            self._notify_guis(
                message="UPDATE",
                category="nodes_update",
                node_id=node_id,
            )
        else:
            logger.warning(f"Node {node_id} not found in clients.")
    
    def _handle_board_info(self, clientId: bytes, node_id: Tuple[str, int], msg) -> None:
        """Handle LOCAL_BOARD_INFO messages."""
        logger.debug(f"Received board info from {clientId}: {msg.board_info}")
        client = self.__node_manager.get_client(node_id)
        if client:
            self.__node_manager.set_client_board_info(node_id, msg.board_info)
            board_id = client.get_board_id()
            logger.info(f"Board info updated for node {node_id} (Board ID: {board_id})")
        else:
            logger.warning(f"Received board info from unknown node {node_id}")

    def _handle_resources_sync(self, clientId: bytes, node_id: Tuple[str, int], msg) -> None:
        """Handle LOCAL_RESOURCES_SYNC messages."""
        if self.__upsert_node_resources is None:
            logger.warning("Received LOCAL_RESOURCES_SYNC but resource registry callback is not configured")
            return

        previous_resources = {}
        if self.__get_resource_registry_snapshot is not None:
            snapshot = self.__get_resource_registry_snapshot()
            if isinstance(snapshot, dict):
                node_entry = snapshot.get(f"{node_id[0]}:{node_id[1]}", {})
                if isinstance(node_entry, dict):
                    previous_resources = node_entry.get("resources", {}) or {}

        payload = {
            "node_id": msg.node_id,
            "type_id": msg.type_id,
            "resources": msg.resources,
            "updated_at": msg.updated_at,
            "update_reason": getattr(msg, "update_reason", ""),
        }
        self.__upsert_node_resources(node_id, payload)
        logger.info(
            "Resources synchronized from node %s (%s): %d resources",
            node_id,
            msg.node_id,
            len(msg.resources or {}),
        )
        if (
            str(getattr(msg, "update_reason", "")).upper() == "DEVICE_STATUS_UPDATE"
            and previous_resources != (msg.resources or {})
        ):
            self._notify_guis(
                message="UPDATE",
                category="used_resources_update",
                node_id=node_id,
            )
    
    def _handle_gui_message(self, clientId: bytes, node_id: Tuple[str, int], msg) -> None:
        """Handle messages from GUI clients."""
        if msg.type == MessageTypes.GUI_START_APPLICATION:
            if not msg.args:
                logger.warning("User arguments are empty. Using default configuration.")
            self.__app_manager.get_app_to_run_queue().put((clientId, msg.appID, msg.args))
        
        elif msg.type == MessageTypes.GUI_STOP_APPLICATION:
            app_id = self._parse_gui_app_id(msg.appID)
            if app_id is None:
                logger.warning(f"Invalid appID received in GUI_STOP_APPLICATION: {msg.appID!r}")
                self.__channel_manager.send_message(
                    clientId,
                    GlobalStopApplicationResponse(appID=str(msg.appID), status="FAILED: invalid appID format"),
                )
                return
            self.__app_manager.get_app_to_stop_queue().put((clientId, app_id))
        
        elif msg.type == MessageTypes.GUI_SET_POLICY:
            self._handle_set_policy(clientId, msg)
        
        elif msg.type == MessageTypes.GUI_LIST_POLICIES:
            policy_list: List[str] = PolicyUtils.get_policy_names()
            self.__channel_manager.send_message(
                clientId,
                GlobalListPoliciesResponse(policy_list=policy_list)
            )
        
        elif msg.type == MessageTypes.GUI_REGISTER:
            self.__get_guis()[clientId] = node_id
            current_policy_name = type(self.__get_policy()).name()
            self.__channel_manager.send_message(clientId, GlobalRegisterResponse(current_policy=current_policy_name))
            logger.info(f"GUI registered: {clientId} at node_id {node_id}")
        
        elif msg.type == MessageTypes.GUI_LIST_AVAILABLE_APPLICATIONS:
            # return parsed descriptors of all available applications
            descriptors = []
            try:
                descriptors = self.__app_manager.list_available_app_descriptors()
            except Exception as e:
                logger.error(f"Error while collecting available application descriptors: {e}")
            self.__channel_manager.send_message(clientId, GlobalListAvailableApplicationsResponse(descriptors=descriptors))
            print("Descriptors sent to GUI:", descriptors)
        elif msg.type == MessageTypes.GUI_LIST_APPLICATIONS:
            applications = []
            for app_id, channels_config in self.__app_manager.get_running_apps().items():
                # Build partition mappings from running partitions on all nodes
                partitions = []
                for node in self.__node_manager.get_all_clients().values():
                    for partition_key in node.get_running_partitions().keys():
                        if partition_key[0] == app_id:  # partition_key is ((app_name, app_counter), partition_name)
                            partition_name = partition_key[1]
                            node_id = node.get_nodeId()  # (ip, port)
                            partitions.append({
                                "partitionID": partition_name,
                                "node_ip": node_id[0],
                                "node_port": node_id[1]
                            })
                
                app_info = {
                    "appID": app_id,
                    "partitions": partitions
                }
                applications.append(app_info)
            self.__channel_manager.send_message(clientId, GlobalListApplicationsResponse(applications=applications))

        elif msg.type == MessageTypes.GUI_LIST_NODES_STATUS:
            nodes_status = []
            clients_snapshot = self.__node_manager.get_client_list()
            for node in clients_snapshot.values():
                node_ip, node_port = node.get_nodeId()
                node_status = node.get_node_status().value if node.get_node_status() is not None else "unknown"
                nodes_status.append(
                    {
                        "node_ip": str(node_ip),
                        "node_port": int(node_port),
                        "node_id": f"{node_ip}:{node_port}",
                        "status": str(node_status).upper(),
                        "online": str(node_status).lower() != NodeStatus.DISCONNECTED.value,
                        "board_id": str(node.get_board_id()),
                    }
                )

            nodes_status.sort(key=lambda item: (item["node_ip"], item["node_port"]))
            self.__channel_manager.send_message(
                clientId,
                GlobalListNodesStatusResponse(
                    nodes=nodes_status,
                    count=len(nodes_status),
                ),
            )

        elif msg.type == MessageTypes.GUI_LIST_RESOURCES_STATUS:
            resources_status = []
            registry_snapshot = self.__get_resource_registry_snapshot() if self.__get_resource_registry_snapshot else {}
            if isinstance(registry_snapshot, dict):
                for _, node_entry in registry_snapshot.items():
                    node_resources = node_entry.get("resources", {}) if isinstance(node_entry, dict) else {}
                    if not isinstance(node_resources, dict):
                        continue
                    for resource_id, resource_data in node_resources.items():
                        if not isinstance(resource_data, dict):
                            continue
                        resources_status.append(
                            {
                                "resource_id": str(resource_id),
                                "type": str(resource_data.get("type", "unknown")),
                                "status": str(resource_data.get("status", "ACTIVE")).upper(),
                                "connection": str(resource_data.get("interface", "unknown")).lower(),
                            }
                        )
            resources_status.sort(key=lambda item: item["resource_id"])
            self.__channel_manager.send_message(
                clientId,
                GlobalListResourcesStatusResponse(
                    resources=resources_status,
                    count=len(resources_status),
                ),
            )
        
        else:
            logger.warning(f"Received unknown message from GUI: {msg}")

    @staticmethod
    def _parse_gui_app_id(raw_app_id: Any) -> Tuple[str, int] | None:
        """Normalize appID from GUI to (app_name, counter) tuple."""
        parsed = raw_app_id

        if isinstance(raw_app_id, str):
            text = raw_app_id.strip()
            if not text:
                return None
            try:
                parsed = ast.literal_eval(text)
            except Exception:
                return None

        if isinstance(parsed, tuple) and len(parsed) == 2:
            name, counter = parsed
            if not isinstance(name, str):
                return None
            try:
                return (name, int(counter))
            except Exception:
                return None

        if isinstance(parsed, list) and len(parsed) == 2:
            name, counter = parsed
            if not isinstance(name, str):
                return None
            try:
                return (name, int(counter))
            except Exception:
                return None

        return None
    
    def _handle_set_policy(self, clientId: bytes, msg) -> None:
        """Handle GUI_SET_POLICY messages."""
        new_policy_name: str = msg.policy_name
        if new_policy_name:
            logger.info(f"Changing policy to {new_policy_name}")
            # Load the new policy
            from policy.PolicyUtils import load_policy_by_name_global
            new_policy = load_policy_by_name_global(new_policy_name)
            
            # Use the set_policy callback to update policy in RRMGlobal
            if self.__set_policy:
                self.__set_policy(new_policy)
            
            self.__channel_manager.send_message(clientId, GlobalSetPolicyResponse())
        else:
            logger.warning("No policy name provided, keeping the current policy.")
