import logging
import signal
import time
import json
from typing import Dict, Tuple

import policy.PolicyUtils as PolicyUtils

logger = logging.getLogger(__name__)
from core.monitoring.PerformanceTracker import PerformanceTracker
from core.monitoring.MetricFields import MetricField
from core.communication.Message import *

import core.Utils as Utils
from core.communication.ChannelManagerRouter import ChannelManagerRouter

from Config import (
    DEVICE_PERFORMANCES_PER_PARTITION_FILE,
    UPDATE_PERIOD,
    GLOBAL_SNAPSHOT_DETAIL_DEFAULT,
    AUTO_START_APPLICATIONS_FILE,
)

from core.rrm_global.NodeManager import NodeManager
from core.rrm_global.ApplicationManager import ApplicationManager
from core.rrm_global.MessageHandler import MessageHandler
from core.models.ResourceRegistry import GlobalResourceRegistry

RRM_GLOBAL_IP = Utils.get_local_ip()
RRM_GLOBAL_PORT = 41798  # Default port for the global RRM


class RRMGlobal:
    """
    Global Resource and Runtime Manager (RRMGlobal).
    
    Orchestrates the distributed system by:
    - Managing connected RRMLocal nodes and their capabilities
    - Deciding application placement based on resource allocation policies
    - Monitoring system-wide performance and status
    - Coordinating communication between nodes, applications, and UIs
    """
    def __init__(self,
                 port,
                 policy_name,
                 snapshot_detail: str = GLOBAL_SNAPSHOT_DETAIL_DEFAULT,
                 auto_start_enabled: bool = False,
                 capabilities_mode: str = "instant",
                 capabilities_window_seconds: float = 0.0,
                 capabilities_sample_interval_seconds: float = 0.5):
        self.__ip = Utils.get_local_ip()
        self.__port = port
        self.__snapshot_detail = snapshot_detail if snapshot_detail in ("minimal", "policy", "full") else GLOBAL_SNAPSHOT_DETAIL_DEFAULT
        self.__capabilities_mode = str(capabilities_mode or "instant").strip().lower()
        if self.__capabilities_mode not in ("instant", "window"):
            logger.warning(f"Unknown capabilities mode '{capabilities_mode}'. Falling back to 'instant'.")
            self.__capabilities_mode = "instant"

        self.__capabilities_window_seconds = float(capabilities_window_seconds or 0.0)
        if self.__capabilities_mode == "window" and self.__capabilities_window_seconds <= 0:
            logger.warning("Window mode requested with non-positive window_seconds. Falling back to 'instant'.")
            self.__capabilities_mode = "instant"
            self.__capabilities_window_seconds = 0.0

        self.__capabilities_sample_interval_seconds = float(capabilities_sample_interval_seconds or 0.0)
        if self.__capabilities_sample_interval_seconds <= 0:
            self.__capabilities_sample_interval_seconds = 0.5
        
        self.__GUIs: Dict[bytes, Tuple[str, int]] = {}

        # Load policy and performance tracking
        self.__policy = PolicyUtils.load_policy_by_name_global(policy_name)
        self.__performance_tracker = PerformanceTracker(DEVICE_PERFORMANCES_PER_PARTITION_FILE)
        
        self.__required_fields = ["architecture", "n_cores", "max_freq", "battery_energy_full", "memory_total", "disk_total"]
        self.__resource_registry = GlobalResourceRegistry()
        self.__auto_start_enabled = bool(auto_start_enabled)
        self.__auto_start_queue = self._load_auto_start_applications() if self.__auto_start_enabled else []
        self.__next_auto_start_attempt_ts = 0.0
        
        # Initialize managers (modular design for separation of concerns)
        self.__node_manager = NodeManager()
        self.__app_manager = ApplicationManager()
        
        # Message handler coordinates all incoming communications
        # Uses getter functions to avoid circular dependencies during initialization
        self.__message_handler = MessageHandler(
            self.__node_manager,
            self.__app_manager,
            None,  # channel_manager will be set after creation
            lambda: self.__policy,
            lambda: self.__performance_tracker,
            lambda: self.__required_fields,
            lambda: self.__GUIs,
            lambda: self.__capabilities_mode,
            lambda: self.__capabilities_window_seconds,
            lambda: self.__capabilities_sample_interval_seconds,
            self.set_policy,
            self.__resource_registry.upsert_node_resources,
            self.__resource_registry.remove_node,
            self.__resource_registry.get_snapshot,
        )
        
        # Communication layer using ZeroMQ router pattern
        self.__channelManager = ChannelManagerRouter(self.__ip, self.__port, self.__message_handler.handle_message)
        self.__message_handler._MessageHandler__channel_manager = self.__channelManager
        
        # Complete circular dependencies by injecting channel manager
        self.__node_manager._NodeManager__get_channel_manager = lambda: self.__channelManager
        self.__app_manager._ApplicationManager__get_channel_manager = lambda: self.__channelManager
        
        self.__shutdown_requested = False

        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _load_auto_start_applications(self):
        """Load startup applications from external JSON configuration file."""
        entries = []

        try:
            with open(AUTO_START_APPLICATIONS_FILE, "r", encoding="utf-8") as file_obj:
                payload = json.load(file_obj)
        except FileNotFoundError:
            logger.info("Auto-start file not found: %s. Startup auto-launch disabled.", AUTO_START_APPLICATIONS_FILE)
            return entries
        except Exception as exc:
            logger.error("Failed to load auto-start file %s: %s", AUTO_START_APPLICATIONS_FILE, exc)
            return entries

        if not isinstance(payload, dict):
            logger.error("Invalid auto-start file format in %s: expected JSON object.", AUTO_START_APPLICATIONS_FILE)
            return entries

        apps = payload.get("applications", [])
        if not isinstance(apps, list):
            logger.error("Invalid auto-start format in %s: 'applications' must be a list.", AUTO_START_APPLICATIONS_FILE)
            return entries

        for item in apps:
            if not isinstance(item, dict):
                logger.warning("Skipping invalid auto-start entry (expected object): %r", item)
                continue

            app_id = str(item.get("app_id") or item.get("appID") or "").strip()
            if not app_id:
                logger.warning("Skipping auto-start entry without app_id/appID: %r", item)
                continue

            args = item.get("args", {})
            if not isinstance(args, dict):
                logger.warning("Auto-start args for app '%s' must be an object. Using empty args.", app_id)
                args = {}

            entries.append({"app_id": app_id, "args": args})

        if entries:
            logger.info("Loaded %d startup application(s) from %s", len(entries), AUTO_START_APPLICATIONS_FILE)

        return entries

    def _handle_auto_start(self):
        """Try launching startup applications after at least one node is connected."""
        if not self.__auto_start_enabled:
            return

        if not self.__auto_start_queue:
            return

        now = time.time()
        if now < self.__next_auto_start_attempt_ts:
            return

        node_lock = self.__node_manager.get_lock()
        with node_lock:
            clients = self.__node_manager.get_all_clients()
            connected_nodes = len(clients)
            if connected_nodes == 0:
                self.__next_auto_start_attempt_ts = now + UPDATE_PERIOD
                return

            pending = self.__auto_start_queue[0]
            app_id = pending["app_id"]
            user_args = pending["args"]

            logger.info("Auto-start: trying to launch '%s' (connected_nodes=%d)", app_id, connected_nodes)
            result_app_id = self.__app_manager.start_app(
                app_id,
                user_args,
                clients,
                lambda: self.__policy,
                lambda: self.__performance_tracker,
                startup_wait_lock=node_lock,
            )

        if isinstance(result_app_id, tuple) and len(result_app_id) >= 1 and result_app_id[0] == "ERROR":
            error_message = str(result_app_id[1]) if len(result_app_id) > 1 else "unknown error"
            if "No devices available" in error_message:
                logger.info("Auto-start postponed for '%s': %s", app_id, error_message)
                self.__next_auto_start_attempt_ts = now + UPDATE_PERIOD
                return

            logger.error("Auto-start failed permanently for '%s': %s", app_id, error_message)
            self._notify_all_guis(
                message=f"Auto-start failed for app '{app_id}': {error_message}",
                severity="error",
                category="autostart_failed",
                app_id=app_id,
            )
            self.__auto_start_queue.pop(0)
            self.__next_auto_start_attempt_ts = now + UPDATE_PERIOD
            return

        if result_app_id is None:
            logger.error("Auto-start failed for '%s' due to runtime/timeout. Skipping this entry.", app_id)
            self._notify_all_guis(
                message=f"Auto-start timeout/runtime failure for app '{app_id}'",
                severity="error",
                category="autostart_timeout",
                app_id=app_id,
            )
            self.__auto_start_queue.pop(0)
            self.__next_auto_start_attempt_ts = now + UPDATE_PERIOD
            return

        logger.info("Auto-start launched '%s' as %s", app_id, result_app_id)
        self.__auto_start_queue.pop(0)
        self.__next_auto_start_attempt_ts = now + UPDATE_PERIOD


      
    def get_client_list(self):
        return self.__node_manager.get_client_list()
        
    def get_running_apps(self):
        return self.__app_manager.get_running_apps()
    
    def get_board_info_summary(self):
        """Get summary of board information for all nodes."""
        return self.__node_manager.get_board_info_summary()

    def get_resource_registry_summary(self):
        """Get global snapshot of synchronized node resources."""
        return self.__resource_registry.get_snapshot()

    def _notify_all_guis(self, message: str, severity: str = "info", category: str = "generic",
                         app_id=None, node_id=None) -> None:
        """Broadcast textual notifications to all connected GUIs."""
        app_id_text = "" if app_id is None else str(app_id)
        node_id_text = "" if node_id is None else str(node_id)

        for gui_client_id in list(self.__GUIs.keys()):
            try:
                self.__channelManager.send_message(
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
    
    def set_policy(self, policy):
        """Set a new policy and update it across all nodes."""
        self.__policy = policy
        all_metric_fields = [field.value for field in MetricField]
        # Update the policy in all clients
        with self.__node_manager.get_lock():
            for node in self.__node_manager.get_all_clients().values():
                self.__channelManager.send_message(node.get_clientId(), GlobalSetPolicy(
                    policy_name=type(self.__policy).name(), 
                    resources_to_collect=all_metric_fields,
                    process_resources_to_collect=self.__performance_tracker.get_required_fields()))
    
    def running_loop(self):
        print_timeout_period = 10 * UPDATE_PERIOD
        next_print_timestamp = print_timeout_period + time.time()
        
        logger.info("Starting main loop...")
        try:
            while not self.__shutdown_requested:
                time.sleep(UPDATE_PERIOD)

                self._handle_auto_start()

                app_to_run_queue = self.__app_manager.get_app_to_run_queue()
                if not app_to_run_queue.empty():
                    clientId, appId, user_args = app_to_run_queue.get()
                    node_lock = self.__node_manager.get_lock()
                    with node_lock:
                        clients = self.__node_manager.get_all_clients()
                        result_appId = self.__app_manager.start_app(
                            appId, user_args, clients, 
                            lambda: self.__policy,
                            lambda: self.__performance_tracker,
                            startup_wait_lock=node_lock,
                        )
                    app_to_run_queue.task_done() 
                    if result_appId is not None:
                        # Check if it's an error response
                        if isinstance(result_appId, tuple) and result_appId[0] == "ERROR":
                            # Send error response to GUI
                            error_message = result_appId[1]
                            self._notify_all_guis(
                                message=f"Application start failed for '{appId}': {error_message}",
                                severity="error",
                                category="app_start_failed",
                                app_id=appId,
                            )
                            self.__channelManager.send_message(clientId, GlobalStartApplicationResponse(appID=appId, status=f"FAILED: {error_message}"))
                        else:
                            # Send success response
                            # TODO change this so that it does not retry forever
                            self.__channelManager.send_message(clientId, GlobalStartApplicationResponse(appID=str(result_appId)))
                    else:
                        # App failed to start
                        logger.error(f"Failed to start app {appId}")
                        self._notify_all_guis(
                            message=f"Application start timeout/runtime failure for '{appId}'",
                            severity="error",
                            category="app_start_timeout",
                            app_id=appId,
                        )
                        self.__channelManager.send_message(clientId, GlobalStartApplicationResponse(appID=appId, status=f"FAILED: did not start in time"))

                app_to_stop_queue = self.__app_manager.get_app_to_stop_queue()
                if not app_to_stop_queue.empty():
                    clientId, appId = app_to_stop_queue.get()
                    print(f"Stopping app {appId} for client {clientId}")
                    with self.__node_manager.get_lock():
                        clients = self.__node_manager.get_all_clients()
                        print(f"Clients at stop time: {clients}")
                        self.__app_manager.stop_app(appId, clients)
                    app_to_stop_queue.task_done()
                    self.__channelManager.send_message(clientId, GlobalStopApplicationResponse(appID=appId))

                time.sleep(UPDATE_PERIOD)

                self.__node_manager.check_clients_ready_for_updates()

                if time.time() >= next_print_timestamp:
                    next_print_timestamp = print_timeout_period + time.time()
                    self.__node_manager.print_global_node_status(
                        self.__app_manager.get_running_apps(),
                        self.__policy,
                        self.__GUIs,
                        self.__performance_tracker,
                        self.__resource_registry.get_snapshot(),
                        self.__app_manager.get_resource_instances_status(),
                        (self.__ip, self.__port),
                        self.__snapshot_detail,
                        self.__capabilities_mode,
                        self.__capabilities_window_seconds,
                        self.__capabilities_sample_interval_seconds,
                    )

                # Check if the file with device performance per partition needs to be written and sent to the other nodes
                if self.__performance_tracker.need_to_write():
                    self.__performance_tracker.write_changes_to_file()
                    msg = GlobalUpdateDevicePerformance(data=self.__performance_tracker.get_device_performance_per_partition())
                    with self.__node_manager.get_lock():
                        for client in self.__node_manager.get_all_clients().values():
                            if client.get_ip() != self.__ip:
                                # Send the updated file to all the clients on different machines
                                self.__channelManager.send_message(client.get_clientId(),msg) 
                                #TODO see if we can send just the changes instead of the whole file
                    
        except Exception as e:
            logger.error(f"Critical error in running loop: {e}")
            self._notify_all_guis(
                message=f"Critical error in RRM Global loop: {e}",
                severity="error",
                category="global_runtime_exception",
            )
            import traceback
            traceback.print_exc()
        finally:
            logger.info("Exiting main loop...")
            self._cleanup()
        
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals gracefully"""
        logger.info(f"Received signal {signum}. Initiating graceful shutdown...")
        self.__shutdown_requested = True

    def _cleanup(self):
        """Cleanup resources before shutdown"""
        logger.info("Performing cleanup...")

        # Write final performance tracker data
        if self.__performance_tracker:
            self.__performance_tracker.write_changes_to_file()
            logger.info("Performance tracker data saved")
            
        with self.__node_manager.get_lock():
            for client_id, client in self.__node_manager.get_all_clients().items():
                logger.info(f"Stopping client {client_id}")
                self.__channelManager.send_message(client.get_clientId(), GlobalShutdown())

        for client_id, gui in self.__GUIs.items():
            logger.info(f"Stopping GUI {gui}")
            self.__channelManager.send_message(client_id, GlobalShutdown())
            
        # Close channel manager
        self.__channelManager.close()
        logger.info("Channel manager closed")

        logger.info("Cleanup completed")
