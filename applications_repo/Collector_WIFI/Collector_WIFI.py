from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr
from utilities_library.MqttTransmissionMngr import MqttTransmissionMngr


class Collector_WIFI:
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
    # - self._app.send_status(status): send device status updates to the RRM
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
        self._ssid = self._user_args.get("ssid",None)
        self._password = self._user_args.get("password",None)
        self._campaignname = self._user_args.get("campaignname",None)
        self._samplingfreq = self._user_args.get("samplingfreq", None)
        self._rawquats = self._user_args.get("rawquat", None)
        self._mqtt_broker = self._user_args.get("host_DB", None)
        self._mqtt_port = self._user_args.get("port_DB", None)
        self._mqtt_topic_raw = self._user_args.get("database_DB", None)
        

    def setup_and_collect_setup(self):
        # Setup for task 'setup_and_collect'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        self.manager = WifiAcquisitionMngr()
        
        if self._imunames is not None:
            BSN_IMUS = [imu.strip() for imu in self._imunames.split("-") if imu.strip()]
            self.manager.set_imus({imu: imu for imu in BSN_IMUS})
            print("IMUs BSN: ", BSN_IMUS)

        self.manager.set_access_point(self._adapter, self._ssid, self._password)
        
        raw = self._rawquats if isinstance(self._rawquats, bool) else str(self._rawquats).strip().lower() == "true"
        self.manager.set_campaign(
            self._campaignname,
            int(self._samplingfreq),
            raw=raw,
            window_size=300,
            step_size=100,
        )

        self.db_mqtt_manager = MqttTransmissionMngr()
        self.db_mqtt_manager.set_db_mqtt(self._mqtt_broker, int(self._mqtt_port), self._mqtt_topic_raw)
        self.db_mqtt_manager.start_db_mqtt()          
        
        self.manager.start_collection()
        self.manager.wait_connection()

    ## Loop methods

    def setup_and_collect_loop(self):
        # Setup and connect all the imus
        # Task logic for 'setup_and_collect' goes here
        i = 0;    
        while(True):
            pck = self.manager.get_packet(True,20)
            if pck is None:
                break
            
            csv_data_d = ",".join(f"{k}={v}" for k, v in pck.items())
            
            self.db_mqtt_manager.put_row(csv_data_d)
            print(pck)
            i += 1
        return {}

    ## Cleanup methods

    def setup_and_collect_cleanup(self):
        # Cleanup for task 'setup_and_collect'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        self.manager.stop_collection()
        self.db_mqtt_manager.stop_db_mqtt()
        return True

    def cleanup(self):
        # Global cleanup method called after all task-specific cleanup
        # Use this to release shared resources
        # Return False to signal cleanup failure, otherwise return True or None
        return True
