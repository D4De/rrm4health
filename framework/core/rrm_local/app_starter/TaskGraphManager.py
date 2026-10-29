from collections import defaultdict


class TaskGraphManager:
    """Manages task graph topology, dependencies, and input/output mappings."""
    
    def __init__(self, tasks, all_tasks, app_logic):
        """
        Initialize the TaskGraphManager.
        
        Args:
            tasks: List of task IDs to execute in this partition
            all_tasks: List of all task definitions from manifest
            app_logic: Application logic object to validate methods
        """
        self.__tasks = tasks
        self.__all_tasks = all_tasks
        self.__app_logic = app_logic
        self.__task_map = {task["id"]: task for task in all_tasks}
        
        # Order tasks by dependencies
        self.__tasks_level = self._topological_levels(tasks, all_tasks)
        
        # Compute method names for each phase
        self.__setup_tasks = []
        self.__loop_tasks = []
        self.__cleanup_tasks = []
        
        self._validate_and_compute_methods()
        
        # Compute I/O mappings
        self.__input_values = set()
        self.__output_values = {}
        self._compute_io_mappings()
    
    def get_tasks_level(self):
        """Get the topologically sorted task levels."""
        return self.__tasks_level
    
    def get_setup_tasks(self):
        """Get the list of setup task method names."""
        return self.__setup_tasks
    
    def get_loop_tasks(self):
        """Get the list of loop task method names (by level)."""
        return self.__loop_tasks
    
    def get_cleanup_tasks(self):
        """Get the list of cleanup task method names."""
        return self.__cleanup_tasks
    
    def get_input_values(self):
        """Get the set of input values needed from other partitions."""
        return self.__input_values
    
    def get_output_values(self):
        """Get the dictionary mapping output keys to destination partitions."""
        return self.__output_values
    
    def update_output_mappings(self, current_config, out_channel):
        """Update output value mappings with actual channel destinations.
        
        Args:
            current_config: Current configuration dictionary
            out_channel: List of output channel configurations
        """
        if out_channel is None:
            return
        
        # Build task I/O map for lookups
        task_ios = {t["id"]: {
            "inputs": set(t.get("input", []) or []),
            "outputs": set(t.get("output", []) or [])
        } for t in self.__all_tasks}
        
        for channel in out_channel:
            # Update output values with the channel's destination partition
            for partition in current_config["partitions"]:
                if partition["id"] == channel["to_partition"]:
                    # Gather all inputs required by destination partition tasks
                    dest_required = set()
                    for dest_tid in partition["tasks"]:
                        dest_required.update(task_ios.get(dest_tid, {}).get("inputs", set()))
                    # Map only outputs that are needed by destination
                    for data in dest_required:
                        if data in self.__output_values:
                            self.__output_values[data] = channel["to_partition"]
    
    def _validate_and_compute_methods(self):
        """Validate method existence and compute method names."""
        # Check for global setup and cleanup methods
        if not hasattr(self.__app_logic, "setup"):
            raise RuntimeError("Missing method: setup")
        
        if not hasattr(self.__app_logic, "cleanup"):
            raise RuntimeError("Missing method: cleanup")

        # Check for task-specific methods
        for task_level in self.__tasks_level:
            loop_tasks = []
            for task in task_level:
                method = task + "_setup"
                if not hasattr(self.__app_logic, method):
                    raise RuntimeError(f"Missing method: {method}")
                self.__setup_tasks.append(method)

                method = task + "_loop"
                if not hasattr(self.__app_logic, method):
                    raise RuntimeError(f"Missing method: {method}")
                loop_tasks.append(method)

                method = task + "_cleanup"
                if not hasattr(self.__app_logic, method):
                    raise RuntimeError(f"Missing method: {method}")
                self.__cleanup_tasks.append(method)

            self.__loop_tasks.append(loop_tasks)
    
    def _compute_io_mappings(self):
        """Compute input and output value mappings for this partition."""
        # Build task I/O map from manifest
        task_ios = {t["id"]: {
            "inputs": set(t.get("input", []) or []),
            "outputs": set(t.get("output", []) or [])
        } for t in self.__all_tasks}
        
        # Get partition task IDs in execution order (flattened from levels)
        partition_task_ids = [t.replace("_loop", "") for level in self.__loop_tasks for t in level]
        
        # Track what has been produced so far as we walk through tasks in order
        produced_so_far = set()
        external_inputs = set()
        
        # Walk through tasks in dependency order (using __tasks_level)
        for level in self.__tasks_level:
            for tid in level:
                # Get inputs needed by this task
                task_inputs = task_ios.get(tid, {}).get("inputs", set())
                # Any input needed that hasn't been produced yet must be external
                for inp in task_inputs:
                    if inp not in produced_so_far:
                        external_inputs.add(inp)
                # Add outputs produced by this task
                task_outputs = task_ios.get(tid, {}).get("outputs", set())
                produced_so_far.update(task_outputs)
        
        # These are the inputs that must come from external sources
        self.__input_values = external_inputs

        # Find outputs that are needed by tasks outside this partition
        partition_outputs = set()
        for task in self.__all_tasks:
            task_id = task["id"]
            # If this task is NOT in our partition
            if task_id not in partition_task_ids:
                # Check if it depends on any task in our partition
                for depends_on in task.get("depends_on", []):
                    if depends_on in partition_task_ids:
                        # This external task needs inputs from our partition
                        partition_outputs.update(task_ios.get(task_id, {}).get("inputs", set()))
        
        # Get all outputs produced by tasks in this partition
        produced_outputs = set()
        for tid in partition_task_ids:
            produced_outputs.update(task_ios.get(tid, {}).get("outputs", set()))
        
        # Only keep outputs that are both produced by us AND needed by external tasks
        partition_outputs = produced_outputs.intersection(partition_outputs)
        
        # Prepare mapping output_key -> destination partition (filled later by update_output_mappings)
        self.__output_values = {key: None for key in partition_outputs}
    
    def _topological_levels(self, task_ids_to_order, all_tasks):
        """
        Organize tasks into dependency levels using topological sorting.
        
        Args:
            task_ids_to_order: List of task IDs to order
            all_tasks: List of all task definitions
            
        Returns:
            List of lists, where each inner list contains tasks that can run in parallel
        """
        task_map = {task["id"]: task for task in all_tasks}

        # Validate input
        missing = [tid for tid in task_ids_to_order if tid not in task_map]
        if missing:
            raise ValueError(f"Task IDs not found in manifest: {missing}")

        # Build in-degree and graph
        graph = defaultdict(list)
        in_degree = defaultdict(int)

        for tid in task_ids_to_order:
            in_degree[tid] = 0  # initialize

        for tid in task_ids_to_order:
            for dep in task_map[tid].get("depends_on", []):
                if dep in task_ids_to_order:
                    graph[dep].append(tid)
                    in_degree[tid] += 1

        # Build levels
        levels = []
        current_level = [tid for tid in task_ids_to_order if in_degree[tid] == 0]

        visited = set()
        while current_level:
            levels.append(current_level[:])  # Make a copy of the current level
            next_level = []

            for tid in current_level:
                visited.add(tid)
                for neighbor in graph[tid]:
                    in_degree[neighbor] -= 1
                    if in_degree[neighbor] == 0:
                        next_level.append(neighbor)

            current_level = next_level

        if len(visited) != len(task_ids_to_order):
            raise RuntimeError("Cycle detected in task dependencies")

        return levels
