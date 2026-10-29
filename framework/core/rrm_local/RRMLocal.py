import os
import signal
import time
import threading
import traceback
import logging
import platform
from typing import Optional

from core.monitoring.MetricsCollector import MetricsCollector, ProcessMetricsCollector
from core.communication.Message import *

import core.Utils as Utils
from core.models.Node import Node
from core.communication.ChannelManagerClient import ChannelManagerClient
from core.communication.ChannelManagerRouter import ChannelManagerRouter

from core.rrm_local.PartitionManager import PartitionManager
from core.rrm_local.MetricsManager import MetricsManager
from core.rrm_local.MessageHandlerLocal import MessageHandlerLocal
from core.rrm_local.AppEnvironmentManager import AppEnvironmentManager
from core.models.ResourceRegistry import LocalResourceRegistry

from Config import NODE_CATALOG_FILE, NODE_INVENTORY_FILE

logger = logging.getLogger(__name__)


class RRMLocal:
    """
    Local Resource and Runtime Manager (RRMLocal).
    
    Manages resources and executes commands on a single node:
    - Receives placement decisions from RRMGlobal
    - Starts and manages application partition processes
    - Collects and reports local performance metrics
    - Handles communication with local partitions and RRMGlobal
    """
    def __init__(
        self,
        port,
        global_ip,
        global_port,
        board_info_file=None,
        node_id: Optional[str] = None,
    ):
        self.__ip = Utils.get_local_ip()
        self.__port = port
        self.__local_node_status = Node((self.__ip, self.__port), None) 
        self.__lock = threading.Lock()
        
        self.__shutdown_requested = False
        self.__global_shutdown = False

        self.__app_port = Utils.get_free_port()

        self.__node_id = node_id
        self.__node_catalog_file = NODE_CATALOG_FILE
        self.__node_inventory_file = NODE_INVENTORY_FILE
        self.__local_resource_registry = LocalResourceRegistry()
        self.__node_inventory_entry = {}
        if self.__node_id:
            loaded = self.__local_resource_registry.load_from_node_inventory_file(self.__node_id, self.__node_inventory_file)
            if not loaded:
                logger.warning("LocalResourceRegistry not initialized from node_inventory (node_id=%s)", self.__node_id)
            self.__node_inventory_entry = Utils.load_node_inventory_entry(self.__node_id, self.__node_inventory_file)
        else:
            logger.info("node_id not provided: LocalResourceRegistry sync disabled")
        
        # Load optional device-specific performance characteristics
        if board_info_file:
            self.__board_info = Utils.load_board_info(board_info_file)
        elif self.__node_id:
            self.__board_info = Utils.load_board_info_from_catalog(
                self.__node_id,
                self.__node_inventory_file,
                self.__node_catalog_file,
            )
        else:
            self.__board_info = {}
        self.__board_info_file = board_info_file
        
        # Get current logging level to propagate to child processes
        # The root logger is always DEBUG, so we need to get the level from the handlers
        root_logger = logging.getLogger()
        current_log_level = logging.INFO  # Default
        if root_logger.handlers:
            # Get level from first handler (console handler)
            current_log_level = root_logger.handlers[0].level

        # Prepare all application environments at RRMLocal startup
        # (moved from PartitionManager runtime path)
        self.__env_manager = AppEnvironmentManager(venv_base_dir=os.path.dirname(__file__))
        self.__env_manager.prepare_all()

        board_architecture = None
        if isinstance(self.__board_info, dict):
            board_architecture = (
                self.__board_info.get("compute", {})
                .get("cpu", {})
                .get("architecture")
            )

        architecture_flag = str(board_architecture or platform.machine())
        os_name = str(platform.system())
        logger.info(
            "Initializing MetricsCollector with architecture_flag=%s, os_name=%s",
            architecture_flag,
            os_name,
        )
        
        # Modular managers for partition lifecycle and metrics collection
        self.__partition_manager = PartitionManager(
            get_local_node_status=lambda: self.__local_node_status,
            get_app_port=lambda: self.__app_port,
            get_lock=lambda: self.__lock,
            log_level=current_log_level,
            env_manager=self.__env_manager,
        )
        
        self.__metrics_manager = MetricsManager(
            metrics_collector=MetricsCollector(
                architecture_flag=architecture_flag,
                os_name=os_name,
            ),
            process_metrics_collector=ProcessMetricsCollector(),
            get_policy=lambda: self.__message_handler.get_policy() if hasattr(self, '_RRMLocal__message_handler') else None,
            get_local_node_status=lambda: self.__local_node_status,
            get_lock=lambda: self.__lock
        )
        
        # Message handler processes commands from RRMGlobal and local partitions
        self.__message_handler = MessageHandlerLocal(
            get_policy=lambda: self.__message_handler.get_policy() if hasattr(self, '_RRMLocal__message_handler') else None,
            get_metrics_manager=lambda: self.__metrics_manager,
            get_partition_manager=lambda: self.__partition_manager,
            get_local_node_status=lambda: self.__local_node_status,
            get_lock=lambda: self.__lock,
            get_channel_manager_rrm=lambda: self.__channelManagerRRM if hasattr(self, '_RRMLocal__channelManagerRRM') else None,
            set_shutdown_flags=self._set_shutdown_flags,
            get_local_resource_registry=lambda: self.__local_resource_registry,
            sync_local_resources_to_global=self._sync_local_resources_to_global,
        )
        
        # Dual communication channels: one to RRMGlobal (client), one for local apps (router)
        # TODO check how to advertise rrm address
        self.__channelManagerRRM = ChannelManagerClient(
            self.__ip, self.__port, global_ip, global_port, 
            self.__message_handler.handler_RRM
        )
        self.__channelManagerRRM.initialize_connection()
        
        # Send board information to RRMGlobal if available
        if self.__board_info and Utils.validate_board_info(self.__board_info):
            self.__channelManagerRRM.send_message(LocalBoardInfo(board_info=self.__board_info))
            logger.info(f"Sent board information: {self.__board_info.get('id', 'unknown')}")
        elif self.__board_info_file:
            logger.warning(f"Board info file provided but invalid: {self.__board_info_file}")

        self._sync_local_resources_to_global()
        
        self.__channelManagerAPP = ChannelManagerRouter(
            self.__ip, self.__app_port, 
            self.__message_handler.handler_clients
        )

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Properly handle SIGCHLD to prevent zombie processes
        def sigchld_handler(signum, frame):
            try:
                while True:
                    try:
                        pid, status = os.waitpid(-1, os.WNOHANG)
                        if pid == 0:
                            break
                    except OSError:
                        break
            except Exception:
                pass
        if platform.system() != "Windows":  # Unix/Linux/macOS
            signal.signal(signal.SIGCHLD, sigchld_handler)

    def _sync_local_resources_to_global(self, update_reason: str = ""):
        """Send local node resources to RRMGlobal after successful connection."""
        if not self.__node_id:
            return

        payload = self.__local_resource_registry.to_sync_payload()
        resources = payload.get("resources")
        if not isinstance(resources, dict):
            logger.warning("Skipping LocalResourcesSync: invalid local resources payload")
            return

        self.__channelManagerRRM.send_message(
            LocalResourcesSync(
                node_id=str(payload.get("node_id") or self.__node_id),
                type_id=str(payload.get("type_id") or ""),
                resources=resources,
                updated_at=float(payload.get("updated_at") or time.time()),
                update_reason=str(update_reason or ""),
            )
        )
        logger.info("Sent LocalResourcesSync for node_id=%s with %d resources", self.__node_id, len(resources))



    def running_loop(self):
        update_period = self.__metrics_manager.get_update_period()
        print_timeout = 10 * update_period
        next_print_timestamp = time.time() + print_timeout
        
        logger.info("Starting main loop...")
        try:
            while not self.__shutdown_requested:
                # Collect and update metrics if policy is set
                self.__metrics_manager.collect_and_update_metrics()
            
                if time.time() >= next_print_timestamp:
                    next_print_timestamp = time.time() + print_timeout
                    self.print_local_node_status()
                
                time.sleep(update_period)
                    
        except Exception as e:
            logger.error(f"Critical error in running loop: {e}")
            logger.error(traceback.format_exc())
        finally:
            logger.info("Exiting main loop...")
            self._cleanup()
    


    def print_local_node_status(self):
        if logger.level > logging.INFO:
            return

        print("=" * 60)
        print("LOCAL NODE STATUS SUMMARY")
        print("=" * 60)
        print(f"snapshot_timestamp_utc: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")
        print("scope: local")

        with self.__lock:
            status = self.__local_node_status.get_status()
            running_partitions = dict(self.__local_node_status.get_running_partitions())

        metrics_mode_for_print = "instant"
        if hasattr(self, '_RRMLocal__message_handler') and self.__message_handler is not None:
            metrics_mode_for_print = self.__message_handler.get_last_capabilities_mode()

        local_node_id = self.__local_resource_registry.get_node_id() or self.__node_id or "unknown"
        local_type_id = self.__local_resource_registry.get_type_id() or "unknown"
        local_resources = self.__local_resource_registry.get_resources_snapshot()
        node_status_value = self.__local_node_status.get_node_status().value.upper()
        endpoint_type = Utils.get_connection_type_for_ip(self.__ip)
        location = {}
        if isinstance(self.__node_inventory_entry, dict):
            location = self.__node_inventory_entry.get("location", {})
        location = Utils.normalize_indoor_location(location)

        print("NODE STATUS ")
        print(f"  Logical Node ID: {local_node_id}")
        print(f"  Node Type ID: {local_type_id}")
        print("  Endpoint:")
        print(f"    IP: {self.__ip}")
        print(f"    Port: {self.__port}")
        print(f"    Type: {endpoint_type}")
        print("  Online: true")
        print(f"  Location: {location if isinstance(location, dict) else {}}")

        print("Status:")
        for key in [
            "cpu_percentage",
            "cpu_frequency",
            "battery_percentage",
            "is_connected_to_power",
            "temperature",
            "memory_used_mb",
            "memory_available_mb",
            "memory_percentage",
            "disk_used_gb",
            "disk_available_gb",
            "power_consumption_w",
            "upload_speed",
            "download_speed",
        ]:
            if key in status:
                print(
                    f"  {Utils.MetricsFormattingUtils.format_runtime_metric(key, status.get(key), default_mode=metrics_mode_for_print)}"
                )
        print(f"  Last Update UTC: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}")

        print("Connected Resources:")
        if local_resources:
            rows = []
            for resource_id, resource_data in local_resources.items():
                if not isinstance(resource_data, dict):
                    continue
                rows.append({
                    "resource_id": str(resource_id),
                    "type": str(resource_data.get("type", "unknown")),
                    "status": str(resource_data.get("status") or "ACTIVE").upper(),
                    "connection_type": str(resource_data.get("interface") or "unknown").lower(),
                })

            if rows:
                rows.sort(key=lambda item: item["resource_id"])
                headers = {
                    "resource_id": "Resource ID",
                    "type": "Type",
                    "status": "Status",
                    "connection_type": "Connection",
                }
                widths = {}
                for key, label in headers.items():
                    widths[key] = max(len(label), *(len(str(row.get(key, ""))) for row in rows))

                header_line = (
                    f"    {headers['resource_id']:<{widths['resource_id']}}  "
                    f"{headers['type']:<{widths['type']}}  "
                    f"{headers['status']:<{widths['status']}}  "
                    f"{headers['connection_type']:<{widths['connection_type']}}"
                )
                separator_line = (
                    f"    {'-' * widths['resource_id']}  "
                    f"{'-' * widths['type']}  "
                    f"{'-' * widths['status']}  "
                    f"{'-' * widths['connection_type']}"
                )
                print(header_line)
                print(separator_line)
                for row in rows:
                    print(
                        f"    {row['resource_id']:<{widths['resource_id']}}  "
                        f"{row['type']:<{widths['type']}}  "
                        f"{row['status']:<{widths['status']}}  "
                        f"{row['connection_type']:<{widths['connection_type']}}"
                    )
            else:
                print("  {}")
        else:
            print("  {}")

        print("Running Partitions:")
        if running_partitions:
            for partition_id, partition in running_partitions.items():
                print("  -")
                print(f"    Partition ID: {partition_id}")
                print(f"    PID: {partition.get_pid()}")
                print(f"    Client ID: {partition.get_clientId()}")
                print("    Status: RUNNING")
                utilization = partition.get_utilization()
                print("    Utilization:")
                if utilization:
                    for metric, value in utilization.items():
                        print(
                            f"      {Utils.MetricsFormattingUtils.format_runtime_metric(metric, value, default_mode=metrics_mode_for_print)}"
                        )
                else:
                    print("      {}")
                print("    Devices Status:")
                devices_status = partition.get_devices_status()
                if devices_status:
                    if isinstance(devices_status, dict):
                        items = sorted(
                            ((str(device_id), str(state)) for device_id, state in devices_status.items()),
                            key=lambda item: item[0],
                        )
                        id_width = max(len("Device ID"), *(len(device_id) for device_id, _ in items))
                        st_width = max(len("State"), *(len(state) for _, state in items))
                        print(f"      {'Device ID':<{id_width}}  {'State':<{st_width}}")
                        print(f"      {'-' * id_width}  {'-' * st_width}")
                        for device_id, state in items:
                            print(f"      {device_id:<{id_width}}  {state:<{st_width}}")
                    else:
                        print(f"      {devices_status}")
                else:
                    print("      {}")
        else:
            print("  []")

        print("=" * 60)




    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
        self.__shutdown_requested = True
    
    def _set_shutdown_flags(self, global_shutdown=False, shutdown_requested=False):
        """Set shutdown flags (called by MessageHandlerLocal)."""
        if global_shutdown:
            self.__global_shutdown = True
        if shutdown_requested:
            self.__shutdown_requested = True

    def _cleanup(self):
        """Cleanup resources before shutdown"""
        logger.info("Performing cleanup...")
        
        # Stop all running partitions using partition manager
        self.__partition_manager.stop_all_partitions()

        if not self.__global_shutdown:
            # Notify the global RRM about the disconnection
            logger.info("Notifying global RRM about disconnection...")
            self.__channelManagerRRM.send_message(LocalShutdown())
        else:
            logger.info("Skipping disconnection notification to global RRM as this is a global shutdown") 

        # Close channel managers
        self.__channelManagerRRM.close()
        logger.info("RRM channel manager closed")

        self.__channelManagerAPP.close()
        logger.info("APP channel manager closed")
       
        logger.info("Cleanup completed")
