import os
import signal
import logging
import threading
from typing import Optional

from core.rrm_local.AppEnvironmentManager import AppEnvironmentManager

logger = logging.getLogger(__name__)


class PartitionManager:
    """Manages partition lifecycle: forking, executing, and terminating partitions."""
    
    def __init__(self, get_local_node_status, get_app_port, get_lock, log_level=logging.INFO, env_manager: Optional[AppEnvironmentManager] = None):
        """
        Initialize the PartitionManager.
        
        Args:
            get_local_node_status: Lambda function that returns the local node status
            get_app_port: Lambda function that returns the app port
            get_lock: Lambda function that returns the threading lock
            log_level: Logging level to propagate to child processes
        """
        self.__get_local_node_status = get_local_node_status
        self.__get_app_port = get_app_port
        self.__get_lock = get_lock
        self.__log_level = log_level
        self.__env_manager = env_manager
        self.__partition_to_check = {}
        self.__partitions_to_check = {}
        self.__pending_partitions_lock = threading.Lock()

        # Directory base del modulo
        self.__base_dir = os.path.dirname(__file__)
        # Directory che contiene AppStarter
        self.__appstarter_dir = os.path.join(self.__base_dir, "app_starter")
    
    def fork_and_exec(self, app_id, param, uniqueId):
        """Fork and execute a partition using AppStarter.py.
        
        Args:
            app_id: Application identifier
            param: Parameters for the partition
            uniqueId: Unique identifier for the partition
        """
        # Build command to execute AppStarter.py with the new parameter format
        string_param = ""
        
        # Extract required parameters
        channels = param["channels"]["value"]
        id_partition = param["Id_part"]["value"]
        ind_conf = param["Ind_conf"]["value"]

        # Add required AppStarter.py arguments
        string_param += f"--Ind_conf {ind_conf} "
        string_param += f"--Id_part {id_partition} "
        string_param += f"--RRM_port {self.__get_app_port()} "
        string_param += f"--App_id {app_id} "
        string_param += f"--App_instance_counter {uniqueId[0][1]} "

        # Add channel parameters
        for channel in [c for c in channels if c["from_partition"] == id_partition or c["to_partition"] == id_partition]:
            string_param += f"--{channel['from_partition']}&{channel['to_partition']}&type {channel['type']} "
            for parameter in channel["parameters"].keys():
                string_param += f"--{channel['from_partition']}&{channel['to_partition']}&{parameter} {channel['parameters'][parameter]} "

        # Add user arguments (excluding system parameters)
        for name_param in param.keys():
            if name_param not in ["channels", "Id_part", "Ind_conf"]:
                string_param += f"--{name_param} {str(param[name_param]['value'])} "
            
        # Remove trailing space
        string_param = string_param.rstrip()
        args_list = string_param.split()

        # ---------------------------------------------------------
        # SELECT THE PYTHON INTERPRETER (venv prepared at RRMLocal startup)
        # ---------------------------------------------------------
        if not self.__env_manager:
            raise RuntimeError("PartitionManager requires an AppEnvironmentManager instance")

        python_exec = self.__env_manager.get_python_exec(app_id)
        if not os.path.exists(python_exec):
            raise FileNotFoundError(
                f"Python interpreter for app '{app_id}' not found at '{python_exec}'. "
                "Ensure RRMLocal prepared environments at startup."
            )

        # Path of AppStarter.py
        # Execute AppStarter.py instead of the application directly
        appstarter_path = [
            python_exec,
            os.path.join(os.path.dirname(__file__), "app_starter", "AppStarter.py")
        ]

        # ---------------------------------------------------------
        # FORK & EXEC
        # ---------------------------------------------------------
        
        # Prevent the child from registering before the parent has stored the
        # exact unique ID -> PID association.
        child_ready_fd, parent_ready_fd = os.pipe()
        try:
            pid = os.fork()  # Create new process
        except Exception:
            os.close(child_ready_fd)
            os.close(parent_ready_fd)
            raise

        if pid == 0:  # Child process
            os.close(parent_ready_fd)
            try:
                os.read(child_ready_fd, 1)
            finally:
                os.close(child_ready_fd)
            # Propagate logging level to child process via environment variable
            os.environ['RRM_LOG_LEVEL'] = str(self.__log_level)
            logger.debug(f"Executing AppStarter: {appstarter_path + args_list}")
            os.execvp(appstarter_path[0], appstarter_path + args_list)
            # If execvp succeeds, the following code will never be executed
            os._exit(1)  # If execvp fails, exit with error
        else:  # Parent process
            os.close(child_ready_fd)
            try:
                with self.__pending_partitions_lock:
                    self.__partition_to_check = (uniqueId, pid)
                    self.__partitions_to_check[uniqueId] = pid
            finally:
                os.write(parent_ready_fd, b"1")
                os.close(parent_ready_fd)
    
    def kill_a_partition(self, partitionID):
        """Terminate a running partition.
        
        Args:
            partitionID: Identifier of the partition to kill
        """
        partitionID = ((partitionID[0][0], partitionID[0][1]), partitionID[1])  # convert to tuple
        
        lock = self.__get_lock()
        local_node_status = self.__get_local_node_status()
        
        if lock is None or local_node_status is None:
            logger.error("Cannot kill partition: lock or local_node_status not initialized")
            return
        
        with lock:
            running_partitions = local_node_status.get_running_partitions()
            if partitionID not in running_partitions:
                logger.warning(f"Partition {partitionID} not found in running partitions")
                return
            pid = running_partitions[partitionID].get_pid()
        
        logger.info(f"Terminating child process with PID: {pid}")
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            logger.warning(f"Process with PID {pid} does not exist (may have already terminated)")
    
    def get_partition_to_check(self):
        """Get the partition currently being checked after fork/exec."""
        with self.__pending_partitions_lock:
            return self.__partition_to_check
    
    def add_running_partition(self, uniqueID, clientId):
        """Add a running partition to the node status.
        
        Args:
            uniqueID: Unique identifier for the partition
            clientId: Client identifier from the channel manager
        """
        with self.__pending_partitions_lock:
            pid = self.__partitions_to_check.pop(uniqueID, None)
            if pid is None and self.__partition_to_check:
                pending_unique_id, pending_pid = self.__partition_to_check
                if pending_unique_id == uniqueID:
                    pid = pending_pid
            if self.__partition_to_check and self.__partition_to_check[0] == uniqueID:
                self.__partition_to_check = {}

        if pid is not None:
            lock = self.__get_lock()
            local_node_status = self.__get_local_node_status()
            
            if lock is None or local_node_status is None:
                logger.error("Cannot add partition: lock or local_node_status not initialized")
                return False
            
            with lock:
                local_node_status.add_running_partition(uniqueID, pid, clientId)
                logger.info(f"Added a new client: {clientId}, {local_node_status.get_running_partitions()[uniqueID]}")
            return True
        else:
            logger.error(
                "Cannot register partition %s: no pending child process matches it",
                uniqueID,
            )
            return False
    
    def remove_running_partition(self, uniqueID):
        """Remove a running partition from the node status.
        
        Args:
            uniqueID: Unique identifier for the partition
        """
        lock = self.__get_lock()
        local_node_status = self.__get_local_node_status()
        
        if lock is None or local_node_status is None:
            logger.error("Cannot remove partition: lock or local_node_status not initialized")
            return
        
        try:
            with lock:
                local_node_status.remove_running_partition(uniqueID)
        except (KeyError, RuntimeError) as e:
            logger.debug(f"Partition {uniqueID} already removed or not found")
    
    def get_unique_id_from_clientId(self, clientId):
        """Get the unique ID for a partition from its client ID.
        
        Args:
            clientId: Client identifier from the channel manager
            
        Returns:
            The unique ID or None if not found
        """
        uniqueID = None
        lock = self.__get_lock()
        local_node_status = self.__get_local_node_status()
        
        if lock is None or local_node_status is None:
            logger.error("Cannot get unique ID: lock or local_node_status not initialized")
            return None
        
        with lock:
            for uID, partition in local_node_status.get_running_partitions().items():
                if partition.get_clientId() == clientId:
                    uniqueID = uID
                    break
        
        logger.debug(f"Unique ID for client {clientId} is {uniqueID}")
        return uniqueID
    
    def stop_all_partitions(self):
        """Stop all running partitions during cleanup."""
        lock = self.__get_lock()
        local_node_status = self.__get_local_node_status()
        
        if lock is None or local_node_status is None:
            logger.error("Cannot stop partitions: lock or local_node_status not initialized")
            return
        
        with lock:
            running_partitions = list(local_node_status.get_running_partitions().keys())
        
        if running_partitions:
            logger.info(f"Stopping {len(running_partitions)} running partitions...")
            for partition_id in running_partitions:
                self.kill_a_partition(partition_id)
