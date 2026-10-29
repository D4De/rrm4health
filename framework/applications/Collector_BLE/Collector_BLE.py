import time

from utilities_library.BleAcquisitionMngr import BleAcquisitionMngr
from utilities_library.MqttTransmissionMngr import MqttTransmissionMngr
class Collector_BLE:
    # FRAMEWORK EXECUTION FLOW:
    # 1. All setup methods are called in dependency order
    # 2. Loop methods are called in dependency levels (round-robin within each level)
    # 3. Cleanup methods are called in reverse order
    #
    # IMPORTANT: AppStarter performs comprehensive validation before execution:
    # - Method existence validation (all required setup/loop/cleanup methods must exist)
    # - Task dependency topological ordering with cycle detection
    # - Return type consistency (only dict or None allowed in loop methods)
    # - Always same dictionary structure returned inside the same methods
    # - Unique key production validation (keys can be reused across branches, but multiple tasks returning the same key cannot directly converge into the same consuming task)
    # - Parameter-production matching (all required parameters must be produced by other tasks)
    #
    # VARIABLE MANAGEMENT:
    # Define instance variables (self.variable_name) in setup methods for persistence.
    #
    # RETURN VALUE REQUIREMENTS:
    # Each loop method MUST return a dictionary (can be empty) with structure:
    # { key: value, ... }
    # - 'key': variable name to be used by dependent methods
    # - 'value': the actual data content
    # - All attributes needed by dependent tasks must be returned with exact matching names
    # - In case of unification (one taskY depends on multiple tasks) the attributes of taskY must be a sub-set of the attributes returned by the above tasks
    #
    # TASK EXECUTION LEVELS:
    # Tasks are organized by dependency levels. Higher levels execute before lower levels.
    # No execution order is guaranteed within the same level (parallel execution possible).
    # For your convenience, here is the task graph you defined in the JSON file:
    #
    # No valid task graph structure found
    #
    #
    # DO NOT MODIFY: this is needed for the correct functioning of the framework
    def set_framework(self, app, user_args=None):
        self._app = app  # this is the Application instance
        self._user_args = user_args

    # You have access to the following system methods via self._app:
    # - self._app.notify_peripherals_in_use(ids, connection_type): mark peripherals as in use
    # - self._app.notify_peripherals_released(ids): mark peripherals as released
    # - self._app.send_status(status): low-level status API (advanced usage)
    # - self._app.stop_application(): stop the application and inform the RRM
    #
    # The user_args are passed from by the user when starting the application and can be accessed via self._user_args.

    ## Setup methods

    def setup(self):
        # Global setup method called before any task-specific setup
        # Use this to initialize shared resources and instance variables
        # Return False to signal setup failure, otherwise return True or None
        self._imunames = self._user_args.get("imunames",None)
        self._adapter = self._user_args.get("adapter",None)
        self._campaignname = self._user_args.get("campaignname",None)
        self._samplingfreq = self._user_args.get("samplingfreq", None)
        self._rawquats = self._user_args.get("rawquat", None)
        self._mqtt_broker = self._user_args.get("MQTT_SERVER", None)
        self._mqtt_port = self._user_args.get("MQTT_PORT", None)
        self._mqtt_topic_raw = self._user_args.get("MQTT_MSG", None)

    def setup_and_collect_setup(self):
        # Setup for task 'setup_and_collect'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        self.manager = BleAcquisitionMngr()
        
        self._imu_ids = []
        if self._imunames is not None:
            self._imu_ids = [imu_id for imu_id in self._imunames.split("-") if imu_id]
            self.manager.set_imus(self._imu_ids)
            print("IMUs BSN: ", self._imu_ids)

        self.manager.set_adapter(self._adapter)
        
        raw = self._rawquats if isinstance(self._rawquats, bool) else str(self._rawquats).strip().lower() == "true"
        self.manager.set_campaign(
            self._campaignname,
            int(self._samplingfreq),
            raw=raw,
            window_size=300,
            step_size=100,
        )
        self.manager.set_id_imus(self._imu_ids)
        
        self.db_mqtt_manager = MqttTransmissionMngr()
        self.db_mqtt_manager.set_db_mqtt(self._mqtt_broker, int(self._mqtt_port), self._mqtt_topic_raw)
        self.db_mqtt_manager.start_db_mqtt()           
        
        self.manager.start_collection()
        self.manager.wait_connection()
        
        self._app.notify_peripherals_in_use(self._imu_ids, "ble")

    ## Loop methods

    def setup_and_collect_loop(self):
        # Setup and connect all the imus
        # Task logic for 'setup_and_collect' goes here
        while(True):
            pck = self.manager.get_packet(True,20)
            
            if pck is None:
                break
            
            csv_data_d = ",".join(f"{k}={v}" for k, v in pck.items())
            csv_data_d += ",c_id=" + self._campaignname
            self.db_mqtt_manager.put_row(csv_data_d)
            #print(pck)
        return {}

    ## Cleanup methods

    def setup_and_collect_cleanup(self):
        # Cleanup for task 'setup_and_collect'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        self._app.notify_peripherals_released(self._imu_ids)
        self.manager.stop_collection()
        self.db_mqtt_manager.stop_db_mqtt()
        return True

    def cleanup(self):
        # Global cleanup method called after all task-specific cleanup
        # Use this to release shared resources
        # Return False to signal cleanup failure, otherwise return True or None
        return True
