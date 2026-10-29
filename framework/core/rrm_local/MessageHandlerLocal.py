import json
import logging
from typing import Any, Dict, List, Tuple

import policy.PolicyUtils as PolicyUtils
from core.communication.MessageTypes import MessageTypes
from core.communication.Message import *

from Config import DEVICE_PERFORMANCES_PER_PARTITION_FILE

logger = logging.getLogger(__name__)


class MessageHandlerLocal:
    """Handles incoming messages from RRM Global and application clients."""
    
    def __init__(self, get_policy, get_metrics_manager, get_partition_manager, 
                 get_local_node_status, get_lock, get_channel_manager_rrm,
                 set_shutdown_flags=None,
                 get_local_resource_registry=None,
                 sync_local_resources_to_global=None):
        """
        Initialize the MessageHandlerLocal.
        
        Args:
            get_policy: Lambda function that returns the current policy
            get_metrics_manager: Lambda function that returns the metrics manager
            get_partition_manager: Lambda function that returns the partition manager
            get_local_node_status: Lambda function that returns the local node status
            get_lock: Lambda function that returns the threading lock
            get_channel_manager_rrm: Lambda function that returns the RRM channel manager
            set_shutdown_flags: Optional callback to set shutdown flags in RRMLocal
        """
        self.__get_policy = get_policy
        self.__get_metrics_manager = get_metrics_manager
        self.__get_partition_manager = get_partition_manager
        self.__get_local_node_status = get_local_node_status
        self.__get_lock = get_lock
        self.__get_channel_manager_rrm = get_channel_manager_rrm
        self.__set_shutdown_flags = set_shutdown_flags
        self.__get_local_resource_registry = get_local_resource_registry
        self.__sync_local_resources_to_global = sync_local_resources_to_global
        self.__policy = None  # Local reference to avoid repeated lambda calls
        self.__resource_users_by_partition = {}
        self.__resource_partition_users = {}
        self.__base_resource_ids = set()
        self.__last_capabilities_mode = "instant"

    def get_last_capabilities_mode(self) -> str:
        """Return the last metrics mode requested by RRMGlobal for capabilities."""
        return self.__last_capabilities_mode
    
    def set_policy(self, policy):
        """Set the policy reference (called by RRMLocal when policy changes)."""
        self.__policy = policy
    
    def handler_RRM(self, msg_dict):
        """Handle messages from RRM Global.
        
        Args:
            msg_dict: Dictionary representation of the message
        """
        try:
            msg = message_factory(msg_dict)
        except ValueError as e:
            logger.error(f"Error decoding message: {e}")
            return

        if msg.type == MessageTypes.GLOBAL_START_PARTITION:
            self._handle_start_partition(msg)
        elif msg.type == MessageTypes.GLOBAL_STOP_PARTITION:
            self._handle_stop_partition(msg)
        elif msg.type == MessageTypes.GLOBAL_REQUEST_CAPABILITIES:
            self._handle_request_capabilities(msg)
        elif msg.type == MessageTypes.GLOBAL_REQUEST_STATUS:
            self._handle_request_status(msg)
        elif msg.type == MessageTypes.GLOBAL_SET_POLICY:
            self._handle_set_policy(msg)
        elif msg.type == MessageTypes.GLOBAL_UPDATE_DEVICE_PERFORMANCE:
            self._handle_update_device_performance(msg)
        elif msg.type == MessageTypes.GLOBAL_SHUTDOWN:
            self._handle_shutdown(msg)
    
    def handler_clients(self, clientId, msg):
        """Handle messages from application clients.
        
        Args:
            clientId: Identifier of the client sending the message
            msg: Message dictionary
        """
        action = msg.get("action")
        
        if action == "REGISTER_PART":
            self._handle_register_partition(clientId, msg)
        elif action == "ADVERT_OK_CONFIGURATION":
            self._handle_advert_ok_configuration(clientId, msg)
        elif action == "DISCONNECT_PART":
            self._handle_disconnect_partition(clientId, msg)
        elif action == "DEVICE_STATUS_UPDATE":
            self._handle_device_status_update(clientId, msg)
        elif action == "GUI_NOTIFICATION":
            self._handle_gui_notification(clientId, msg)
    
    def _handle_start_partition(self, msg):
        """Handle GLOBAL_START_PARTITION message."""
        partitionID = ((msg.uniqueID[0][0], msg.uniqueID[0][1]), msg.uniqueID[1])  # convert to tuple
        app_id = msg.app_id  # Use app_id from the message
        
        partition_manager = self.__get_partition_manager()
        if partition_manager is None:
            logger.error("Cannot start partition: partition_manager not initialized")
            return
        
        partition_manager.fork_and_exec(app_id, msg.param, partitionID)
    
    def _handle_stop_partition(self, msg):
        """Handle GLOBAL_STOP_PARTITION message."""
        partition_manager = self.__get_partition_manager()
        if partition_manager is None:
            logger.error("Cannot stop partition: partition_manager not initialized")
            return

        partition_id = None
        try:
            partition_id = ((msg.partitionId[0][0], msg.partitionId[0][1]), msg.partitionId[1])
        except Exception:
            partition_id = None

        # Do not release/remove resources here: the app can still emit runtime
        # DEVICE_STATUS_UPDATE released notifications during graceful shutdown.
        # Final cleanup is performed on DISCONNECT_PART.
        partition_manager.kill_a_partition(msg.partitionId)
    
    def _handle_request_capabilities(self, msg):
        """Handle GLOBAL_REQUEST_CAPABILITIES message."""
        fields_to_collect = msg.fields
        mode = getattr(msg, "mode", "instant")
        window_seconds = getattr(msg, "window_seconds", 0.0)
        sample_interval_seconds = getattr(msg, "sample_interval_seconds", 0.5)
        self.__last_capabilities_mode = str(mode or "instant").strip().lower()
        
        metrics_manager = self.__get_metrics_manager()
        channel_manager_rrm = self.__get_channel_manager_rrm()
        
        if metrics_manager is None or channel_manager_rrm is None:
            logger.error("Cannot handle capabilities request: managers not initialized")
            return
        
        collected_data = metrics_manager.collect_capabilities(
            fields_to_collect,
            mode=self.__last_capabilities_mode,
            window_seconds=window_seconds,
            sample_interval_seconds=sample_interval_seconds,
        )
        channel_manager_rrm.send_message(LocalCapabilities(data=collected_data))
    
    def _handle_request_status(self, msg):
        """Handle GLOBAL_REQUEST_STATUS message."""
        local_node_status = self.__get_local_node_status()
        lock = self.__get_lock()
        channel_manager_rrm = self.__get_channel_manager_rrm()
        policy = self.__get_policy()
        
        if local_node_status is None or lock is None or channel_manager_rrm is None:
            logger.error("Cannot handle status request: components not initialized")
            return
        
        with lock:
            status = local_node_status.get_status()
            running_partitions = local_node_status.get_running_partitions()
            running_partitions_data = []
            for partition_id, partition in running_partitions.items():
                running_partitions_data.append({
                    "id": partition_id,
                    "utilization": partition.get_utilization(),
                    "devices_status": partition.get_devices_status()
                })
                partition.reset_utilization()  # Reset utilization after sending status
        
        msg = LocalStatus(status=status, running_partitions=running_partitions_data)
        channel_manager_rrm.send_message(msg)
        
        if policy is not None:
            policy.reset_node_status()
    
    def _handle_set_policy(self, msg):
        """Handle GLOBAL_SET_POLICY message."""
        new_policy_name = msg.policy_name
        resources_to_collect = msg.resources_to_collect
        process_resources_to_collect = msg.process_resources_to_collect
        
        metrics_manager = self.__get_metrics_manager()
        if metrics_manager is None:
            logger.error("Cannot set policy: metrics_manager not initialized")
            return
        
        self.__policy = PolicyUtils.load_policy_by_name_local(new_policy_name)
        metrics_manager.set_resources_to_collect(resources_to_collect, process_resources_to_collect)
        
        logger.info(f"Changing policy to {new_policy_name} with resources {resources_to_collect} and process resources {process_resources_to_collect}")
    
    def _handle_update_device_performance(self, msg):
        """Handle GLOBAL_UPDATE_DEVICE_PERFORMANCE message."""
        data = msg.data
        if data:
            try:
                with open(DEVICE_PERFORMANCES_PER_PARTITION_FILE, 'w') as f:
                    json.dump(data, f, indent=2)
                logger.info("Device performance file updated successfully")
            except Exception as e:
                logger.error(f"Error updating device performance file: {e}")
    
    def _handle_shutdown(self, msg):
        """Handle GLOBAL_SHUTDOWN message."""
        logger.info("Shutdown signal received. Initiating graceful shutdown...")
        # Use callback to set shutdown flags in RRMLocal
        if self.__set_shutdown_flags is not None:
            self.__set_shutdown_flags(global_shutdown=True, shutdown_requested=True)
    
    def _handle_register_partition(self, clientId, msg):
        """Handle REGISTER_PART message from client."""
        partition_manager = self.__get_partition_manager()
        if partition_manager is None:
            logger.error("Cannot register partition: partition_manager not initialized")
            return
        
        registration = msg.get("h_constraints") if isinstance(msg, dict) else None
        if not isinstance(registration, dict):
            registration = {}

        app_id = str(registration.get("app_id") or "")
        partition_id = str(registration.get("partition_id") or "")
        app_counter = registration.get("app_counter")

        if app_id and partition_id and app_counter is not None:
            try:
                uniqueID = ((app_id, int(app_counter)), partition_id)
            except (TypeError, ValueError):
                logger.error("Invalid partition registration payload: %r", registration)
                return
        else:
            # Backward compatibility with application starters that do not yet
            # include their identity in REGISTER_PART.
            partition_to_check = partition_manager.get_partition_to_check()
            if not partition_to_check:
                logger.error("Cannot associate legacy REGISTER_PART from %s", clientId)
                return
            uniqueID = partition_to_check[0]

        partition_manager.add_running_partition(uniqueID, clientId)
    
    def _handle_advert_ok_configuration(self, clientId, msg):
        """Handle ADVERT_OK_CONFIGURATION message from client."""
        Id_partition = msg["h_constraints"]["Id_partition"]
        partition_manager = self.__get_partition_manager()
        channel_manager_rrm = self.__get_channel_manager_rrm()
        
        if partition_manager is None or channel_manager_rrm is None:
            logger.error("Cannot advertise configuration: channel_manager_rrm not initialized")
            return

        unique_id = partition_manager.get_unique_id_from_clientId(clientId)
        if unique_id is None:
            registration = msg.get("h_constraints") if isinstance(msg, dict) else None
            if not isinstance(registration, dict):
                registration = {}
            app_id_value = str(registration.get("app_id") or "")
            app_counter = registration.get("app_counter")
            if app_id_value and app_counter is not None:
                try:
                    unique_id = (
                        (app_id_value, int(app_counter)),
                        str(registration.get("partition_id") or Id_partition),
                    )
                except (TypeError, ValueError):
                    unique_id = None
            if unique_id is not None:
                # Recover even if the earlier REGISTER_PART was missed: the
                # self-identifying confirmation can complete local registration.
                if not partition_manager.add_running_partition(unique_id, clientId):
                    unique_id = None
            if unique_id is None:
                logger.error(
                    "Cannot forward ADVERT_OK_CONFIGURATION for partition %s: unknown application client %s",
                    Id_partition,
                    clientId,
                )
                return

        app_id = str(unique_id[0])
        partition_id = str(unique_id[1])

        sent = channel_manager_rrm.send_message(
            LocalPartitionConfigured(
                appID=app_id,
                partitionID=partition_id,
            ),
            wait=True,
        )
        if not sent:
            raise RuntimeError(
                f"Failed to forward partition configured event for {app_id}/{partition_id}"
            )
        logger.info(
            "Forwarded partition configured event to RRMGlobal: app=%s partition=%s",
            app_id,
            partition_id,
        )
    
    def _handle_disconnect_partition(self, clientId, msg):
        """Handle DISCONNECT_PART message from client."""
        partition_manager = self.__get_partition_manager()
        channel_manager_rrm = self.__get_channel_manager_rrm()
        
        if partition_manager is None or channel_manager_rrm is None:
            logger.error("Cannot handle disconnect: managers not initialized")
            return
        
        uniqueID = partition_manager.get_unique_id_from_clientId(clientId)
        self._release_partition_resources(uniqueID)
        partition_manager.remove_running_partition(uniqueID)

        h_constraints = msg.get("h_constraints") if isinstance(msg, dict) else None
        if not isinstance(h_constraints, dict):
            h_constraints = {}

        channel_manager_rrm.send_message(
            LocalApplicationDisconnected(
                appID=uniqueID,
                reason=str(h_constraints.get("reason") or ""),
                phase=str(h_constraints.get("phase") or ""),
                exception_type=str(h_constraints.get("exception_type") or ""),
                exception_text=str(h_constraints.get("exception_text") or ""),
                traceback_text=str(h_constraints.get("traceback") or ""),
            )
        )
        
        logger.info(f"Partition {uniqueID} disconnected")
    
    def _handle_device_status_update(self, clientId, msg):
        """Handle DEVICE_STATUS_UPDATE message from client."""
        device_status = msg.get("value")
        if device_status is None:
            logger.warning("No device status provided in the message")
            return
        
        partition_manager = self.__get_partition_manager()
        local_node_status = self.__get_local_node_status()
        lock = self.__get_lock()
        
        if partition_manager is None or local_node_status is None or lock is None:
            logger.error("Cannot update device status: components not initialized")
            return
        
        uniqueID = partition_manager.get_unique_id_from_clientId(clientId)
        if uniqueID is None:
            logger.warning(f"Cannot update device status: unknown clientId {clientId}")
            return

        usage_entries, update_mode = self._normalize_device_usage_entries(device_status)
        if not usage_entries and not self._is_explicit_empty_snapshot(device_status):
            logger.warning(f"Ignoring malformed DEVICE_STATUS_UPDATE payload: {device_status}")
            return

        partition_devices_status = {
            entry["resource_id"]: ("ACTIVE" if entry["in_use"] else "INACTIVE")
            for entry in usage_entries
        }

        with lock:
            running_partitions = local_node_status.get_running_partitions()
            partition = running_partitions.get(uniqueID)
            if partition is None:
                logger.info(f"Ignoring DEVICE_STATUS_UPDATE for non-running partition {uniqueID}: {device_status}")
                return

            partition.add_devices_status(partition_devices_status)

            self._ensure_base_resource_ids_initialized()
            local_registry = self.__get_local_resource_registry() if self.__get_local_resource_registry else None
            if local_registry is not None:
                self._apply_device_usage_updates(uniqueID, usage_entries, local_registry, update_mode)
        
        logger.info(f"Received device status update: {device_status}")
        self._sync_resources_if_available(update_reason="DEVICE_STATUS_UPDATE")

    def _handle_gui_notification(self, clientId, msg):
        """Forward an application message to RRMGlobal."""
        partition_manager = self.__get_partition_manager()
        channel_manager_rrm = self.__get_channel_manager_rrm()
        if partition_manager is None or channel_manager_rrm is None:
            logger.error("Cannot forward GUI notification: managers not initialized")
            return

        unique_id = partition_manager.get_unique_id_from_clientId(clientId)
        if unique_id is None:
            logger.warning("Ignoring GUI notification from unknown clientId %s", clientId)
            return

        message_text = str(msg.get("message") or "").strip()
        if not message_text:
            logger.warning("Ignoring empty GUI notification from partition %s", unique_id)
            return

        channel_manager_rrm.send_message(
            LocalGuiNotification(
                message=message_text,
                severity=str(msg.get("severity") or "info").strip().lower(),
                appID=unique_id[0],
                partitionID=str(unique_id[1]),
            )
        )

    def _normalize_device_usage_entries(self, payload: Any) -> Tuple[List[Dict[str, Any]], str]:
        entries: List[Dict[str, Any]] = []

        # Accepted format:
        # {"in_use": [{"id": "IMUX", "connection_type": "ble"}, ...]}
        # {"released": [{"id": "IMUX", "connection_type": "ble"}, ...]}
        if isinstance(payload, dict):
            in_use = payload.get("in_use")
            if isinstance(in_use, (list, tuple, set)):
                for item in in_use:
                    if not isinstance(item, dict):
                        continue
                    rid = str(item.get("id") or item.get("resource_id") or "").strip()
                    connection_type = str(item.get("connection_type") or "").strip().lower()
                    if not rid or not connection_type:
                        continue
                    entries.append(
                        {
                            "resource_id": rid,
                            "in_use": True,
                            "type": self._infer_resource_type(rid, item.get("type")),
                            "connection_type": connection_type,
                            "status": "ACTIVE",
                        }
                    )
                return entries, "snapshot"

            released = payload.get("released")
            if isinstance(released, (list, tuple, set)):
                for item in released:
                    if isinstance(item, dict):
                        rid = str(item.get("id") or item.get("resource_id") or "").strip()
                        connection_type = str(item.get("connection_type") or "").strip().lower() or "ble"
                    else:
                        rid = str(item).strip()
                        connection_type = "ble"
                    if not rid:
                        continue
                    entries.append(
                        {
                            "resource_id": rid,
                            "in_use": False,
                            "type": self._infer_resource_type(rid, item.get("type") if isinstance(item, dict) else None),
                            "connection_type": connection_type,
                            "status": "INACTIVE",
                        }
                    )
                return entries, "delta"

        return [], "delta"

    def _is_explicit_empty_snapshot(self, payload: Any) -> bool:
        if isinstance(payload, dict):
            value = payload.get("in_use")
            if isinstance(value, (list, tuple, set)) and len(value) == 0:
                return True
        return False

    def _infer_resource_type(self, resource_id: str, explicit_type: Any) -> str:
        if explicit_type is not None:
            return str(explicit_type)
        if resource_id.upper().startswith("IMU"):
            return "Arduino_33_BLE"
        return "UnknownPeripheral"

    def _partition_key(self, unique_id: Any) -> str:
        return str(unique_id)

    def _ensure_base_resource_ids_initialized(self) -> None:
        if self.__base_resource_ids:
            return
        if not self.__get_local_resource_registry:
            return
        local_registry = self.__get_local_resource_registry()
        if local_registry is None:
            return
        self.__base_resource_ids = set(local_registry.get_resources_snapshot().keys())

    def _apply_device_usage_updates(self, unique_id: Any, usage_entries: List[Dict[str, Any]], local_registry, update_mode: str) -> None:
        pkey = self._partition_key(unique_id)
        previous = self.__resource_users_by_partition.get(pkey, set())
        current = set(previous)

        if update_mode == "snapshot":
            current = {entry["resource_id"] for entry in usage_entries if bool(entry.get("in_use"))}

            for resource_id in previous.difference(current):
                users = self.__resource_partition_users.get(resource_id)
                if users:
                    users.discard(pkey)
                    if not users:
                        self.__resource_partition_users.pop(resource_id, None)
                        merged = local_registry.get_resource(resource_id)
                        if merged:
                            merged["status"] = "INACTIVE"
                            local_registry.add_or_update_resource(resource_id, merged)

        for entry in usage_entries:
            resource_id = entry["resource_id"]
            in_use = bool(entry["in_use"])

            if in_use:
                current.add(resource_id)
                users = self.__resource_partition_users.setdefault(resource_id, set())
                users.add(pkey)

                merged = local_registry.get_resource(resource_id)
                merged.update({
                    "type": entry.get("type") or merged.get("type") or "UnknownPeripheral",
                    "interface": entry.get("connection_type") or merged.get("interface") or "ble",
                    "status": entry.get("status") or "ACTIVE",
                })
                local_registry.add_or_update_resource(resource_id, merged)
            else:
                users = self.__resource_partition_users.get(resource_id)
                if users:
                    users.discard(pkey)
                    if not users:
                        self.__resource_partition_users.pop(resource_id, None)
                merged = local_registry.get_resource(resource_id)
                # Do not recreate dynamic resources after final removal: if missing and non-base,
                # a late "released" update should be ignored.
                if not merged and resource_id not in self.__base_resource_ids:
                    continue
                merged.update({
                    "type": entry.get("type") or merged.get("type") or "UnknownPeripheral",
                    "interface": entry.get("connection_type") or merged.get("interface") or "ble",
                    "status": "INACTIVE",
                })
                local_registry.add_or_update_resource(resource_id, merged)

        self.__resource_users_by_partition[pkey] = current

    def _release_partition_resources(self, unique_id: Any) -> None:
        if unique_id is None:
            return
        if not self.__get_local_resource_registry:
            return
        local_registry = self.__get_local_resource_registry()
        if local_registry is None:
            return

        pkey = self._partition_key(unique_id)
        resources = self.__resource_users_by_partition.pop(pkey, set())
        if not resources:
            return

        self._ensure_base_resource_ids_initialized()
        for resource_id in resources:
            users = self.__resource_partition_users.get(resource_id)
            if users:
                users.discard(pkey)
                if not users:
                    self.__resource_partition_users.pop(resource_id, None)
                else:
                    continue

            if resource_id not in self.__base_resource_ids:
                local_registry.remove_resource(resource_id)

        self._sync_resources_if_available()

    def _sync_resources_if_available(self, update_reason: str = "") -> None:
        if self.__sync_local_resources_to_global is None:
            return
        try:
            self.__sync_local_resources_to_global(update_reason=update_reason)
        except Exception as exc:
            logger.error(f"Error while syncing local resources to global: {exc}")
    
    def get_policy(self):
        """Get the current policy (used by RRMLocal)."""
        return self.__policy
