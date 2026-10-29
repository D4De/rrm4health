import time

from utilities_library.BleAcquisitionMngr import BleAcquisitionMngr
class Battery_BLE:
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
        
        self.manager.set_id_imus(self._imu_ids)
                
        
        self._app.notify_peripherals_in_use(self._imu_ids, "ble")
        
        self._batteries = {}
        

    ## Loop methods

    @staticmethod
    def _format_battery_notification(battery_levels):
        """Build a compact, user-facing battery status message."""
        if not battery_levels:
            return "Livelli batteria:\n• Nessuna IMU configurata"

        formatted_levels = []
        for imu_name, battery_level in battery_levels.items():
            if battery_level is None:
                display_value = "lettura non disponibile"
            elif isinstance(battery_level, (int, float)) and not isinstance(battery_level, bool):
                display_value = f"{battery_level}%"
            else:
                display_value = str(battery_level)

            formatted_levels.append(f"• {imu_name}: {display_value}")

        return "Livelli batteria:\n" + "\n".join(formatted_levels)

    def setup_and_collect_loop(self):
        # Setup and connect all the imus
        # Task logic for 'setup_and_collect' goes here
        battery_levels = self.manager.get_battery_levels()

        print(battery_levels)

        self._app.notify_message(
            self._format_battery_notification(battery_levels)
        )

        self._app.stop_application()
        return {}

    ## Cleanup methods

    def setup_and_collect_cleanup(self):
        # Cleanup for task 'setup_and_collect'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        self._app.notify_peripherals_released(self._imu_ids)
        self.manager.stop_collection()
        return True

    def cleanup(self):
        # Global cleanup method called after all task-specific cleanup
        # Use this to release shared resources
        # Return False to signal cleanup failure, otherwise return True or None
        return True
