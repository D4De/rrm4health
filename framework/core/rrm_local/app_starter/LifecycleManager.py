import inspect
import logging
import queue
import threading
import time
import traceback
from typing import Iterable, List

logger = logging.getLogger(__name__)


class RunningStoppedException(Exception):
    """Exception raised when the running state is stopped."""
    pass


class LifecycleManager:
    """Manages application lifecycle: setup, loop, and cleanup phases."""
    
    def __init__(self, app_logic, get_task_graph_manager, get_channel_setup_manager,
                 get_rrm_interface, running_event, app_id="", partition_id=""):
        """
        Initialize the LifecycleManager.
        
        Args:
            app_logic: Application logic object
            get_task_graph_manager: Lambda function that returns TaskGraphManager
            get_channel_setup_manager: Lambda function that returns ChannelSetupManager
            get_rrm_interface: Lambda function that returns RRM interface
            running_event: Threading event to control application running state
        """
        self.__app_logic = app_logic
        self.__get_task_graph_manager = get_task_graph_manager
        self.__get_channel_setup_manager = get_channel_setup_manager
        self.__get_rrm_interface = get_rrm_interface
        self.__running = running_event
        self.__app_id = str(app_id or "")
        self.__partition_id = str(partition_id or "")
        self.__last_uncaught_exception = None
        self.__shutdown_reason = ""

    def record_uncaught_exception(self, exception: Exception, phase: str, traceback_text: str = ""):
        """Store uncaught exception details to be sent with DISCONNECT_PART.

        The first uncaught exception is preserved as root cause; later exceptions
        (e.g., during cleanup) are logged but do not overwrite it.
        """
        if self.__last_uncaught_exception is not None:
            logger.warning(
                "Additional uncaught exception in phase '%s' ignored to preserve original crash cause",
                phase,
            )
            return

        exc_type = type(exception).__name__
        exc_text = str(exception)
        tb_text = traceback_text or traceback.format_exc()

        self.__last_uncaught_exception = {
            "app_id": self.__app_id,
            "partition_id": self.__partition_id,
            "phase": str(phase or "runtime"),
            "exception_type": exc_type,
            "exception_text": exc_text,
            "traceback": tb_text,
        }

    def get_last_uncaught_exception(self):
        return self.__last_uncaught_exception

    def get_disconnect_info(self):
        """Return exception details or the reason for a clean self-stop."""
        if self.__last_uncaught_exception is not None:
            return self.__last_uncaught_exception
        if self.__shutdown_reason:
            return {
                "app_id": self.__app_id,
                "partition_id": self.__partition_id,
                "reason": self.__shutdown_reason,
            }
        return None
    
    def run_setup(self):
        """Run setup tasks in order."""
        task_graph_manager = self.__get_task_graph_manager()
        if task_graph_manager is None:
            raise RuntimeError("TaskGraphManager not initialized")
        
        # Run global setup first
        if hasattr(self.__app_logic, "setup"):
            logger.info("Running global setup")
            result = self.__app_logic.setup()
            if result is False:
                raise RuntimeError("Global setup failed for the application")
        
        # Run task-specific setup methods
        for task in task_graph_manager.get_setup_tasks():
            logger.info(f"Running setup for task: {task}")
            result = getattr(self.__app_logic, task)()
            if result is False:
                raise RuntimeError(f"Setup failed for the application, failing task: {task}")
    
    def run_loop(self):
        """Run the main application loop."""
        task_graph_manager = self.__get_task_graph_manager()
        channel_setup_manager = self.__get_channel_setup_manager()
        
        if task_graph_manager is None or channel_setup_manager is None:
            raise RuntimeError("Managers not initialized")
        
        logger.info("Starting application loop")
        
        input_values = task_graph_manager.get_input_values()
        output_values = task_graph_manager.get_output_values()
        loop_tasks = task_graph_manager.get_loop_tasks()
        channel_manager = channel_setup_manager.get_channel_manager()
        in_channel = channel_setup_manager.get_in_channel()
        out_channel = channel_setup_manager.get_out_channel()
        
        if in_channel:
            # Initialize queues for each input required by the tasks in the first level
            received_data_needed_for_first_level = {}
            for input_name in input_values:
                if input_name not in received_data_needed_for_first_level:
                    received_data_needed_for_first_level[input_name] = queue.Queue()
        
        try:
            while self.__running.is_set():
                if in_channel:
                    # Wait until we have all required data for this iteration
                    while any(q.empty() for q in received_data_needed_for_first_level.values()):
                        msg = channel_manager.recv(running=self.__running)
                        logger.debug(f"Received message: {msg}")
                        if not msg:
                            raise RunningStoppedException("Running stopped, no message received")
                        for input_name, data in msg.items():
                            # We only add the data required by this partition, the other is discarded
                            if input_name in input_values:
                                received_data_needed_for_first_level[input_name].put(data)

                    input_data = {}
                    for input_name, q in received_data_needed_for_first_level.items():
                        input_data[input_name] = q.get()
                else:
                    input_data = {}

                current_input = input_data
                # Accumulate all outputs needed for outgoing partitions
                accumulated_outputs = {}
                for val in output_values.values():
                    if val is not None:
                        accumulated_outputs.setdefault(val, {})

                for level_tasks in loop_tasks:
                    level_output = {}

                    for task_name in level_tasks:
                        method = getattr(self.__app_logic, task_name)
                        sig = inspect.signature(method)
                        params = [name for name in sig.parameters if name != 'self']

                        # Extract only the inputs needed for this task
                        args = {}

                        for param in params:
                            if param in current_input:
                                args[param] = current_input[param]
                            elif param in input_data:
                                # If the parameter is not in current_input, check if it was received from the channel
                                args[param] = input_data[param]
                        logger.info(f"Running task '{task_name}', with args: {args.keys()}")
                        result = method(**args)

                        # Merge output from all tasks at this level
                        if isinstance(result, dict):
                            # If something is returned, merge it
                            level_output.update(result)
                            
                            # Accumulate outputs that are needed by outgoing partitions
                            for output_key, output_value in result.items():
                                if output_key in output_values.keys():
                                    dest = output_values[output_key]
                                    if dest is not None:
                                        accumulated_outputs.setdefault(dest, {})
                                        accumulated_outputs[dest].update({output_key: output_value})

                    # Keep every value produced during this iteration. A task can
                    # depend on outputs from multiple, non-adjacent DAG levels; if
                    # we replaced the mapping here, only the immediately preceding
                    # level remained available and valid task graphs failed with
                    # missing method arguments.
                    current_input.update(level_output)

                # Send accumulated outputs instead of just the last level's output
                if out_channel and accumulated_outputs:
                    logger.debug(f"Sending accumulated outputs: {accumulated_outputs}")
                    for key, value in accumulated_outputs.items():
                        if value:
                            channel_manager.send(key, value)
        except RunningStoppedException:
            pass
        except Exception as e:
            logger.error(f"Exception in loop runner: {e}")
            tb_text = traceback.format_exc()
            logger.error(tb_text)
            self.record_uncaught_exception(e, phase="loop", traceback_text=tb_text)
            self.__running.clear()
    
    def run_cleanup(self, original_cwd=None):
        """Run cleanup tasks in reverse order.
        
        Args:
            original_cwd: Original working directory to restore
        """
        task_graph_manager = self.__get_task_graph_manager()
        if task_graph_manager is None:
            raise RuntimeError("TaskGraphManager not initialized")
        
        try:
            # Run task-specific cleanup methods first
            for task in reversed(task_graph_manager.get_cleanup_tasks()):
                logger.info(f"Running cleanup for task: {task}")
                result = getattr(self.__app_logic, task)()
                if result is False:
                    raise RuntimeError(f"Cleanup failed for the application, failing task: {task}")
            
            # Run global cleanup last
            if hasattr(self.__app_logic, "cleanup"):
                logger.info("Running global cleanup")
                result = self.__app_logic.cleanup()
                if result is False:
                    raise RuntimeError("Global cleanup failed for the application")
        finally:
            # Restore the original working directory
            if original_cwd is not None:
                import os
                os.chdir(original_cwd)
    
    def send_status(self, status):
        """Send status updates to the RRM.

        Accepted compact payloads:
        - {"in_use": [{"id": "IMUX", "connection_type": "ble"}]}
        - {"released": ["IMUX"]} or {"released": [{"id": "IMUX"}]}
        """
        rrm_interface = self.__get_rrm_interface()
        if rrm_interface is None:
            logger.warning("RRM interface not initialized")
            return
        
        if status is None:
            logger.warning("Invalid status format: None")
            return

        rrm_msg = {"action": "DEVICE_STATUS_UPDATE", "value": status}
        rrm_interface.send_message(rrm_msg)

    def notify_message(self, message, severity: str = "info"):
        """Send a textual notification to the connected GUIs."""
        rrm_interface = self.__get_rrm_interface()
        if rrm_interface is None:
            logger.warning("RRM interface not initialized")
            return

        message_text = str(message or "").strip()
        if not message_text:
            logger.warning("notify_message requires a non-empty message")
            return

        rrm_interface.send_message({
            "action": "GUI_NOTIFICATION",
            "message": message_text,
            "severity": str(severity or "info").strip().lower(),
        })

    @staticmethod
    def _normalize_ids(peripheral_ids) -> List[str]:
        if peripheral_ids is None:
            return []
        if isinstance(peripheral_ids, str):
            ids = [peripheral_ids]
        elif isinstance(peripheral_ids, Iterable):
            ids = list(peripheral_ids)
        else:
            ids = [peripheral_ids]
        return [str(pid).strip() for pid in ids if str(pid).strip()]

    def notify_peripherals_in_use(self, peripheral_ids, connection_type: str):
        ids = self._normalize_ids(peripheral_ids)
        ctype = str(connection_type or "").strip().lower()
        if not ids or not ctype:
            logger.warning("notify_peripherals_in_use requires non-empty IDs and connection_type")
            return
        self.send_status({
            "in_use": [{"id": pid, "connection_type": ctype} for pid in ids]
        })

    def notify_peripherals_released(self, peripheral_ids):
        ids = self._normalize_ids(peripheral_ids)
        if not ids:
            return
        self.send_status({"released": ids})
    
    def stop_application(self):
        """Stop the application loop."""
        logger.info("Stopping application loop")
        self.__shutdown_reason = "self_stop"
        self.__running.clear()
        raise RunningStoppedException("Signal received, stopping application")
