import argparse
import importlib.util
import json
import logging
import os
import signal
import sys
import threading
import time
import traceback

# Add the Framework directory to sys.path for imports
framework_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
if framework_dir not in sys.path:
    sys.path.insert(0, framework_dir)

# Applications share managers from the repository-level utilities_library package.
# AppStarter is launched from a partition directory, not necessarily the repo root.
repository_dir = os.path.dirname(framework_dir)
if repository_dir not in sys.path:
    sys.path.insert(0, repository_dir)

# Import and configure logging before creating logger
from core.logging_config import setup_logging

# Get logging level from environment variable (set by parent process)
# Default to INFO if not set
log_level = int(os.environ.get('RRM_LOG_LEVEL', str(logging.INFO)))
setup_logging(level=log_level)

logger = logging.getLogger(__name__)

# Import framework communication modules
import core.communication.OrchIF as OrchIF

# Import managers
from core.rrm_local.app_starter.TaskGraphManager import TaskGraphManager
from core.rrm_local.app_starter.ChannelSetupManager import ChannelSetupManager
from core.rrm_local.app_starter.LifecycleManager import LifecycleManager, RunningStoppedException
from core.rrm_local.app_starter.CodeIntegrityChecker import check_code_integrity, InconsistentReturnException


running = threading.Event()
running.set() 

# Paths relative to Framework directory
FOLDER_APP_DESCRIPTORS = os.path.join(framework_dir, "applications")
FOLDER_APP = os.path.join(framework_dir, "applications")

# Default timeouts (used if not specified in JSON)
DEFAULT_SETUP_TIMEOUT = 60  # seconds
DEFAULT_LOOP_TIMEOUT = 60   # seconds  
DEFAULT_CLEANUP_TIMEOUT = 60 # seconds


class TimeoutException(Exception):
    """Exception raised when a timeout occurs."""
    pass


def load_class_from_file(class_name, app_folder):
    """
    Load application class dynamically from Python file.
    
    This enables the framework to instantiate application partitions without
    hardcoding imports. The application class is loaded from the applications/
    directory based on the app name specified in the manifest.
    
    Args:
        class_name: Name of the class to load (also the app name)
        app_folder: Path to the application's folder
    
    Returns:
        The loaded class
    """
    # The main executable file has the same name as the app
    filename = f"{class_name}.py"
    path = os.path.join(app_folder, filename)
    module_name = class_name
    
    # Add the application's folder to sys.path temporarily to resolve relative imports
    abs_folder_path = os.path.abspath(app_folder)
    if abs_folder_path not in sys.path:
        sys.path.insert(0, abs_folder_path)
        path_added = True
    else:
        path_added = False
    
    try:
        spec = importlib.util.spec_from_file_location(module_name, path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return getattr(module, class_name)
    except Exception as e:
        raise RuntimeError(f"Failed to load {class_name} from {path}") from e
    finally:
        # Remove the path if we added it
        if path_added:
            sys.path.remove(abs_folder_path)


def _get_root_exception(exception):
    """Return the original exception from an explicit/implicit exception chain."""
    root_exception = exception
    visited = set()

    while id(root_exception) not in visited:
        visited.add(id(root_exception))
        next_exception = root_exception.__cause__
        if next_exception is None and not root_exception.__suppress_context__:
            next_exception = root_exception.__context__
        if next_exception is None:
            break
        root_exception = next_exception

    return root_exception


def notify_bootstrap_exception(
    exception,
    app_id,
    partition_id,
    rrm_port,
    traceback_text,
    app_instance_counter=0,
):
    """Report failures occurring before ``Application`` can create its RRM interface.

    Dynamic imports and application construction happen before the normal lifecycle
    notification machinery is available.  A short-lived interface is therefore
    registered so that RRMLocal can associate the failure with the pending child,
    then the standard DISCONNECT_PART message is sent.
    """
    root_exception = _get_root_exception(exception)
    disconnect_info = {
        "app_id": str(app_id or ""),
        "partition_id": str(partition_id or ""),
        "phase": "bootstrap",
        "exception_type": type(root_exception).__name__,
        "exception_text": str(root_exception),
        "traceback": traceback_text or "",
    }

    rrm_interface = None
    try:
        rrm_interface = OrchIF.OrchIF(rrm_port)
        # REGISTER_PART must precede DISCONNECT_PART so RRMLocal can map the
        # DEALER identity to the partition currently being started.
        rrm_interface.connect({
            "app_id": str(app_id or ""),
            "app_counter": int(app_instance_counter),
            "partition_id": str(partition_id or ""),
        })
        rrm_interface.disconnect(disconnect_info=disconnect_info)
        return True
    except Exception as notify_exc:
        logger.error("Failed to notify RRM about bootstrap exception: %s", notify_exc)
        if rrm_interface is not None:
            try:
                rrm_interface.disconnect(send_disconnect=False)
            except Exception:
                logger.debug("Failed to close bootstrap RRM interface", exc_info=True)
        return False



def handler_sigterm(signum, frame):
    """Handle SIGTERM and SIGINT signals."""
    global running
    logger.info("Signal received, setting running to False")
    running.clear()


signal.signal(signal.SIGTERM, handler_sigterm)
signal.signal(signal.SIGINT, handler_sigterm)


class Application:
    def __init__(self, app_logic_obj, Id_partition, RRM_port, tasks, all_tasks, App_id, 
                 in_channel, out_channel, current_config, user_args=None, timeouts=None,
                 App_instance_counter=0):
        try:
            logger.debug(f"all_tasks: {all_tasks}")
            logger.debug(f"current_config: {current_config}")
            
            # Initialize timeouts from configuration or use defaults
            if timeouts:
                self.__setup_timeout = timeouts.get("setup", DEFAULT_SETUP_TIMEOUT)
                self.__loop_timeout = timeouts.get("loop", DEFAULT_LOOP_TIMEOUT)
                self.__cleanup_timeout = timeouts.get("cleanup", DEFAULT_CLEANUP_TIMEOUT)
            else:
                self.__setup_timeout = DEFAULT_SETUP_TIMEOUT
                self.__loop_timeout = DEFAULT_LOOP_TIMEOUT
                self.__cleanup_timeout = DEFAULT_CLEANUP_TIMEOUT
                
            logger.info(f"Using timeouts - Setup: {self.__setup_timeout}s, Loop: {self.__loop_timeout}s, Cleanup: {self.__cleanup_timeout}s")
            
            # Change to the specific application's directory
            self._original_cwd = os.getcwd()
            app_directory = os.path.join(FOLDER_APP, App_id)
            os.chdir(os.path.abspath(app_directory))
            
            # Initialize application logic
            self._app_logic = app_logic_obj
            self._app_logic.set_framework(self, user_args)
            
            # Create managers
            self.__task_graph_manager = TaskGraphManager(tasks, all_tasks, self._app_logic)
            self.__channel_setup_manager = ChannelSetupManager(in_channel, out_channel)
            
            # Setup RRM interface
            self.__rrm_Virtual_interface = OrchIF.OrchIF(RRM_port)
            self.__rrm_Virtual_interface.connect({
                "app_id": str(App_id),
                "app_counter": int(App_instance_counter),
                "partition_id": str(Id_partition),
            })
            self.__rrm_Virtual_interface.start()
            
            # Create lifecycle manager with lambda getters
            self.__lifecycle_manager = LifecycleManager(
                app_logic=self._app_logic,
                get_task_graph_manager=lambda: self.__task_graph_manager,
                get_channel_setup_manager=lambda: self.__channel_setup_manager,
                get_rrm_interface=lambda: self.__rrm_Virtual_interface,
                running_event=running,
                app_id=App_id,
                partition_id=Id_partition,
            )

            self.__setup_exception = None
            self.__cleanup_exception = None
            self.__uncaught_exception_reported = False
            self.__disconnect_notified = False

            def _notify_disconnect_if_needed():
                if self.__disconnect_notified:
                    return
                if self.__rrm_Virtual_interface is None or self.__lifecycle_manager is None:
                    return
                disconnect_info = self.__lifecycle_manager.get_disconnect_info()
                try:
                    self.__rrm_Virtual_interface.notify_disconnect_part(disconnect_info=disconnect_info)
                    self.__disconnect_notified = True
                except Exception as notify_exc:
                    logger.error("Failed to send immediate disconnect notification: %s", notify_exc)
            
            # Update output mappings based on channels
            self.__task_graph_manager.update_output_mappings(current_config, out_channel)
            
            logger.info(f"Tasks level: {self.__task_graph_manager.get_tasks_level()}")
            logger.info(f"Setup tasks: {self.__task_graph_manager.get_setup_tasks()}")
            logger.info(f"Loop tasks: {self.__task_graph_manager.get_loop_tasks()}")
            logger.info(f"Cleanup tasks: {self.__task_graph_manager.get_cleanup_tasks()}")
            logger.info(f"Inputs not produced by the partition: {self.__task_graph_manager.get_input_values()}")
            logger.info(f"Outputs produced by the partition: {self.__task_graph_manager.get_output_values()}")
            logger.info(f"Channels in: {self.__channel_setup_manager.get_in_channel()}")
            logger.info(f"Channels out: {self.__channel_setup_manager.get_out_channel()}")
            logger.info(f"Updated output values: {self.__task_graph_manager.get_output_values()}")
            
            # Run setup phase
            def _setup_runner():
                try:
                    self.__lifecycle_manager.run_setup()
                except RunningStoppedException:
                    # A self-stop requested during setup is a clean shutdown,
                    # not an uncaught application exception.
                    pass
                except Exception as exc:
                    self.__setup_exception = exc
                    tb = traceback.format_exc()
                    logger.error("Uncaught exception during setup phase: %s", exc)
                    logger.error(tb)
                    self.__lifecycle_manager.record_uncaught_exception(
                        exc,
                        phase="setup",
                        traceback_text=tb,
                    )
                    self.__uncaught_exception_reported = True
                    _notify_disconnect_if_needed()
                    running.clear()

            self.setup_thread = threading.Thread(target=_setup_runner, daemon=True)
            self.setup_thread.start()
            
            # Wait for setup to complete
            setup_start_time = time.time()
            while self.setup_thread.is_alive():
                if not running.is_set():
                    logger.info("Setup interrupted by stop signal")
                    raise RunningStoppedException("Setup stopped by signal")
                elapsed = time.time() - setup_start_time
                if elapsed >= self.__setup_timeout:
                    raise TimeoutException(f"Setup tasks did not complete within {self.__setup_timeout} seconds")
                self.setup_thread.join(timeout=1)

            if self.__setup_exception is not None:
                raise RuntimeError("Setup phase failed due to an uncaught application exception") from self.__setup_exception
            
            # Notify RRM that configuration is complete
            logger.info(
                "Setup completed; sending ADVERT_OK_CONFIGURATION for partition %s",
                Id_partition,
            )
            confirmation_sent = self.__rrm_Virtual_interface.advert_OK_configuration(Id_partition)
            if not confirmation_sent:
                raise RuntimeError(
                    f"Failed to send ADVERT_OK_CONFIGURATION for partition {Id_partition}"
                )
            logger.info(
                "ADVERT_OK_CONFIGURATION sent for partition %s; starting loop",
                Id_partition,
            )
            
            # Start main loop
            self.__loop_thread = threading.Thread(target=self.__lifecycle_manager.run_loop, daemon=True)
            self.__loop_thread.start()
            while running.is_set() and self.__loop_thread.is_alive():
                time.sleep(1)
            self.__loop_thread.join(timeout=self.__loop_timeout)
            if self.__loop_thread.is_alive():
                raise TimeoutException(f"Loop tasks did not complete within {self.__loop_timeout} seconds")
        
        except TimeoutException as e:
            logger.error(f"Timeout occurred: {e}")
        except RunningStoppedException:
            pass
        except Exception as e:
            logger.error(f"Exception occurred: {e}")
            tb = traceback.format_exc()
            logger.error(tb)
            if (
                hasattr(self, "_Application__lifecycle_manager")
                and self.__lifecycle_manager is not None
                and not getattr(self, "_Application__uncaught_exception_reported", False)
            ):
                self.__lifecycle_manager.record_uncaught_exception(
                    e,
                    phase="bootstrap",
                    traceback_text=tb,
                )
                self.__uncaught_exception_reported = True
            _notify_disconnect_if_needed()

        # Cleanup phase
        try:
            def _cleanup_runner():
                try:
                    self.__lifecycle_manager.run_cleanup(self._original_cwd)
                except RunningStoppedException:
                    # Preserve a previously recorded clean self-stop reason.
                    pass
                except Exception as exc:
                    self.__cleanup_exception = exc
                    tb = traceback.format_exc()
                    logger.error("Uncaught exception during cleanup phase: %s", exc)
                    logger.error(tb)
                    self.__lifecycle_manager.record_uncaught_exception(
                        exc,
                        phase="cleanup",
                        traceback_text=tb,
                    )
                    self.__uncaught_exception_reported = True

            self.cleanup_thread = threading.Thread(target=_cleanup_runner, daemon=True)
            self.cleanup_thread.start()
            self.cleanup_thread.join(timeout=self.__cleanup_timeout)
            if self.cleanup_thread.is_alive():
                raise TimeoutException(f"Cleanup tasks did not complete within {self.__cleanup_timeout} seconds")
            if self.__cleanup_exception is not None:
                raise RuntimeError("Cleanup phase failed due to an uncaught application exception") from self.__cleanup_exception
        except TimeoutException as e:
            logger.error(f"Timeout occurred during cleanup: {e}")
        except Exception as e:
            logger.error(f"Exception occurred during cleanup: {e}")
        finally:
            # Close managers
            self.__channel_setup_manager.close()
            
            logger.info("Closing RRM connection")
            try:
                disconnect_info = None
                if self.__lifecycle_manager is not None:
                    disconnect_info = self.__lifecycle_manager.get_disconnect_info()
                self.__rrm_Virtual_interface.disconnect(
                    disconnect_info=disconnect_info,
                    send_disconnect=not self.__disconnect_notified,
                )
            except Exception as e:
                logger.error(f"Error disconnecting from RRM: {e}")
            
            logger.info("Application stopped successfully")
            running.clear()
            
            # Give threads a chance to exit gracefully
            time.sleep(0.5)
            
            # Force kill if needed
            for t in threading.enumerate():
                if t is not threading.current_thread() and not t.daemon and t.is_alive():
                    logger.warning(f"Thread {t.name} still alive, forcing exit")
                    os._exit(1)
            logger.warning("Forcefully stopping process...")
    
    def stop_application(self):
        """Stop the application loop."""
        self.__lifecycle_manager.stop_application()
    
    def send_status(self, status):
        """Send status updates to the RRM."""
        self.__lifecycle_manager.send_status(status)

    def wait_for_stop(self, poll_interval_s=0.1):
        """Block an exhausted finite source until the framework receives STOP.

        This keeps a completed file-based application alive without busy-looping
        through its task graph. The message-handler/signal thread clears the shared
        running event; this method then raises ``RunningStoppedException`` so the
        lifecycle loop exits immediately and starts cleanup.
        """
        interval = max(0.01, float(poll_interval_s))
        while running.is_set():
            time.sleep(interval)
        raise RunningStoppedException("Framework stop received while source was idle")

    def is_running(self):
        """Return whether the framework still permits the application to run."""
        return running.is_set()

    def notify_message(self, message, severity="info"):
        """Send a textual notification to the connected GUIs."""
        self.__lifecycle_manager.notify_message(message, severity)

    def notify_peripherals_in_use(self, peripheral_ids, connection_type):
        """Notify RRMLocal about peripherals currently in use.

        Args:
            peripheral_ids: Single ID or iterable of IDs
            connection_type: Communication type (e.g., ble, wifi)
        """
        self.__lifecycle_manager.notify_peripherals_in_use(peripheral_ids, connection_type)

    def notify_peripherals_released(self, peripheral_ids):
        """Notify RRMLocal about peripherals no longer in use.

        Args:
            peripheral_ids: Single ID or iterable of IDs
        """
        self.__lifecycle_manager.notify_peripherals_released(peripheral_ids)


if __name__ == '__main__':
    print("#######################################################")
    print("Starting the application")

    # Parsing all the arguments and passing them to the class
    parser = argparse.ArgumentParser(description="Management of known and unknown parameters")
    
    parser.add_argument('--Ind_conf', type=int, required=True, help='Configuration Index')
    parser.add_argument('--Id_part', type=str, required=True, help='Partition ID')
    parser.add_argument('--RRM_port', type=int, required=True, help='Port for communicating with the local RRM')
    parser.add_argument('--App_id', type=str, required=True, help='Application ID')
    parser.add_argument('--App_instance_counter', type=int, default=0, help='Application instance counter')
    
    args, unknown_args_channel = parser.parse_known_args()

    ## Get known args
    Id_partition = args.Id_part
    Id_configuration = int(args.Ind_conf)
    RRM_port = int(args.RRM_port)
    App_id = args.App_id
    App_instance_counter = int(args.App_instance_counter)

    with open(os.path.join(FOLDER_APP_DESCRIPTORS, f"{args.App_id}.json"), "r", encoding="utf-8") as file:
        manifest_json = json.load(file)

    user_args = {}
    channel_args = {}

    # Use new manifest structure where executable is at top level
    exec_params = manifest_json["executable"]["parameters"]

    # Iterate through unknown args divide userargs from channel args
    # In the new structure, all parameters in exec_params are user parameters
    # System parameters are automatically managed by the framework
    i = 0
    while i < len(unknown_args_channel):
        if unknown_args_channel[i].startswith('--'):
            key = unknown_args_channel[i].lstrip('-')
            
            # Check if next element exists and is not another option
            if (i + 1 < len(unknown_args_channel) and 
                not unknown_args_channel[i + 1].startswith('--')):
                value = unknown_args_channel[i + 1]
                i += 2  # Skip both the key and value
            else:
                value = None  # No value provided for this argument
                i += 1  # Skip only the key

            # If the parameter is defined in exec_params, it's a user arg
            # Otherwise, it's a channel arg
            if key in exec_params:
                user_args[key] = value
            else:
                channel_args[key] = value
        else:
            i += 1  # Skip non-option arguments


    channels_src = manifest_json["configurations"][Id_configuration]["channels"]
    in_channels = []

    # Channel parameters from argc
    for channel in [c for c in channels_src if c["to_partition"] == Id_partition]:
        channel_key = f"{channel['from_partition']}&{channel['to_partition']}&type"
        if channel_args.get(channel_key) == "network_socket":
            base_key = f"{channel['from_partition']}&{channel['to_partition']}"
            try:
                # Ensure parameters dict exists
                if "parameters" not in channel:
                    channel["parameters"] = {}
                
                channel["parameters"]["ip_src"] = channel_args[f"{base_key}&ip_src"]
                channel["parameters"]["port_src"] = channel_args[f"{base_key}&port_src"]
                channel["parameters"]["ip_dst"] = channel_args[f"{base_key}&ip_dst"]
                channel["parameters"]["port_dst"] = channel_args[f"{base_key}&port_dst"]
                channel["parameters"]["protocol"] = channel_args[f"{base_key}&protocol"]
                in_channels.append(channel)
            except KeyError as e:
                logger.error(f"Missing required channel parameter: {e}")
                sys.exit(1)
            
    out_channels = []
    for channel in [c for c in channels_src if c["from_partition"] == Id_partition]:
        channel_key = f"{channel['from_partition']}&{channel['to_partition']}&type"
        if channel_args.get(channel_key) == "network_socket":
            base_key = f"{channel['from_partition']}&{channel['to_partition']}"
            try:
                # Ensure parameters dict exists
                if "parameters" not in channel:
                    channel["parameters"] = {}
                
                channel["parameters"]["ip_src"] = channel_args[f"{base_key}&ip_src"]
                channel["parameters"]["port_src"] = channel_args[f"{base_key}&port_src"]
                channel["parameters"]["ip_dst"] = channel_args[f"{base_key}&ip_dst"]
                channel["parameters"]["port_dst"] = channel_args[f"{base_key}&port_dst"]
                channel["parameters"]["protocol"] = channel_args[f"{base_key}&protocol"]
                out_channels.append(channel)
            except KeyError as e:
                logger.error(f"Missing required channel parameter: {e}")
                sys.exit(1)

    logger.debug(f"Input channels: {in_channels}")
    logger.debug(f"Output channels: {out_channels}")

    all_tasks = manifest_json["taskgraph"]

    tasks = [p for p in manifest_json["configurations"][Id_configuration]["partitions"] if p["id"] == Id_partition][0]["tasks"]

    # Perform comprehensive integrity check on all loop methods
    logger.info("Performing code integrity check...")
    startup_failed = False
    try:
        # Extract task IDs from the taskgraph - now taskgraph is an array of task objects
        task_ids = [task["id"] for task in all_tasks] if isinstance(all_tasks, list) else [task["id"] for task in all_tasks.values()]
        check_code_integrity(
            file_path=os.path.join(FOLDER_APP, App_id, f"{App_id}.py"), 
            task_names=task_ids,
            all_tasks=all_tasks
        )
        logger.info("Code integrity check passed successfully")
    except InconsistentReturnException as e:
        logger.error(f"Code integrity check failed: {e}")
        sys.exit(1)

    # Get the current configuration and channels for better output determination
    current_config = manifest_json["configurations"][Id_configuration]

    try:
        # Use executable.path from manifest instead of assuming naming pattern
        executable_path = manifest_json["executable"]["path"]
        
        # Handle both relative (from Framework root) and absolute paths
        if os.path.isabs(executable_path):
            abs_executable_path = executable_path
        else:
            abs_executable_path = os.path.join(framework_dir, executable_path)
        
        # Extract directory and filename
        app_folder = os.path.dirname(abs_executable_path)
        executable_filename = os.path.basename(abs_executable_path)
        
        # Extract class name from filename (remove .py extension)
        if executable_filename.endswith('.py'):
            class_name = executable_filename[:-3]
        else:
            class_name = executable_filename
        
        logger.info(f"Loading application class '{class_name}' from {abs_executable_path}")
        
        if not os.path.exists(abs_executable_path):
            raise FileNotFoundError(f"Executable file not found: {abs_executable_path}")
        
        AppLogicClass = load_class_from_file(class_name=class_name, app_folder=app_folder)
        app_logic_instance = AppLogicClass()

        # Extract timeouts from manifest executable configuration
        executable_config = manifest_json["executable"]
        timeouts = executable_config.get("timeouts", {})

        application = Application(
            app_logic_obj=app_logic_instance, 
            Id_partition=Id_partition, 
            RRM_port=RRM_port, 
            tasks=tasks, 
            all_tasks=all_tasks, 
            App_id=App_id, 
            in_channel=in_channels, 
            out_channel=out_channels, 
            user_args=user_args, 
            current_config=current_config,
            timeouts=timeouts,
            App_instance_counter=App_instance_counter,
        )
    except Exception as e:
        startup_failed = True
        tb = traceback.format_exc()
        logger.error(f"Failed to start application: {e}")
        logger.error(tb)
        notify_bootstrap_exception(
            exception=e,
            app_id=App_id,
            partition_id=Id_partition,
            rrm_port=RRM_port,
            traceback_text=tb,
            app_instance_counter=App_instance_counter,
        )
    finally:
        if startup_failed:
            print(f"Application {App_id} closed after startup failure")
        else:
            print(f"Application {App_id} closed successfully")
        print("#######################################################")

    if startup_failed:
        sys.exit(1)
