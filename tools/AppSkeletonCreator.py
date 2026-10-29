import json
import sys
import os
import argparse

# Support both direct execution and importing this tool as a module.
repository_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if repository_dir not in sys.path:
    sys.path.insert(0, repository_dir)

from tools.CheckerJSON import check_json

OUTPUT_FOLDER = ""

TEMPLATE_CLASS_HEADER = """class {class_name}:
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
    # {{ key: value, ... }}
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
{task_graph_ascii}
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
"""

SETUP_METHODS_HEADER = "    ## Setup methods\n"
LOOP_METHODS_HEADER = "    ## Loop methods\n"
CLEANUP_METHODS_HEADER = "    ## Cleanup methods\n"


def build_ascii_task_graph(tasks):
    from collections import defaultdict, deque

    dependencies = defaultdict(list)  # task -> list of tasks it depends on
    dependents = defaultdict(list)    # task -> list of tasks that depend on it
    task_names = {}

    # Build task relationships with error handling
    for task in tasks:
        if not isinstance(task, dict) or "id" not in task:
            continue
        tid = task["id"]
        task_names[tid] = task.get("name", tid)
        depends_on = task.get("depends_on", [])
        if isinstance(depends_on, list):
            dependencies[tid] = depends_on
            for dep in depends_on:
                dependents[dep].append(tid)

    all_tasks = set(task_names.keys())
    if not all_tasks:
        return "    # No valid task graph found"

    def box(task_id):
        name = task_id  # Use task ID instead of name
        # Ensure minimum width and add padding
        width = max(len(name) + 4, 12)
        return [
            f"┌{'─' * (width - 2)}┐",
            f"│ {name.center(width - 4)} │",
            f"└{'─' * (width - 2)}┘"
        ], width, 3

    def calculate_levels():
        """Calculate the level of each task using topological sorting"""
        levels = {}
        in_degree = {task: len(dependencies[task]) for task in all_tasks}
        queue = deque([task for task in all_tasks if in_degree[task] == 0])
        
        current_level = 0
        
        while queue:
            next_queue = deque()
            
            # Process all tasks at current level
            while queue:
                task = queue.popleft()
                levels[task] = current_level
                
                # Update in-degree for dependent tasks
                for dependent in dependents[task]:
                    in_degree[dependent] -= 1
                    if in_degree[dependent] == 0:
                        next_queue.append(dependent)
            
            queue = next_queue
            current_level += 1
        
        return levels, current_level

    def group_by_levels(levels):
        """Group tasks by their level"""
        max_level = max(levels.values()) if levels else 0
        level_groups = [[] for _ in range(max_level + 1)]
        
        for task, level in levels.items():
            level_groups[level].append(task)
        
        # Sort tasks within each level for consistent output
        for level_tasks in level_groups:
            level_tasks.sort()
        
        return level_groups

    def safe_join_lines(lines_list, spacing=3):
        """Safely join multiple text blocks horizontally with proper spacing"""
        if not lines_list:
            return [], 0
        
        max_height = max(len(lines) for lines in lines_list)
        widths = []
        
        # Normalize heights and calculate widths
        normalized_lines = []
        for lines in lines_list:
            if not lines:
                lines = [" "]
            width = max(len(line) for line in lines) if lines else 1
            widths.append(width)
            
            # Pad to max height
            padded = list(lines)
            while len(padded) < max_height:
                padded.append(' ' * width)
            normalized_lines.append(padded)
        
        # Join horizontally
        result = []
        for i in range(max_height):
            row_parts = []
            for j, lines in enumerate(normalized_lines):
                line = lines[i] if i < len(lines) else ' ' * widths[j]
                # Ensure line is exactly the expected width
                line = line.ljust(widths[j])
                row_parts.append(line)
            result.append((' ' * spacing).join(row_parts))
        
        total_width = sum(widths) + spacing * (len(widths) - 1) if len(widths) > 1 else (widths[0] if widths else 0)
        return result, total_width

    def draw_level(tasks_in_level):
        """Draw all tasks in a level horizontally"""
        if not tasks_in_level:
            return [], 0, []
        
        task_blocks = []
        task_widths = []
        for task in tasks_in_level:
            box_lines, width, _ = box(task)
            task_blocks.append(box_lines)
            task_widths.append(width)
        
        combined_lines, total_width = safe_join_lines(task_blocks)
        return combined_lines, total_width, task_widths

    def get_task_centers(tasks_in_level, task_widths, total_width):
        """Calculate center positions of tasks in a level"""
        centers = {}
        pos = 0
        for i, task in enumerate(tasks_in_level):
            width = task_widths[i] if i < len(task_widths) else 12
            centers[task] = pos + width // 2
            pos += width + 3  # 3 is spacing
        return centers

    def draw_connections(level_groups, levels):
        """Draw connections between levels"""
        if len(level_groups) <= 1:
            return []
        
        all_lines = []
        level_centers = []
        level_widths = []
        
        # Calculate centers for each level
        for level_idx, tasks_in_level in enumerate(level_groups):
            if not tasks_in_level:
                level_centers.append({})
                level_widths.append(0)
                continue
                
            level_lines, total_width, task_widths = draw_level(tasks_in_level)
            centers = get_task_centers(tasks_in_level, task_widths, total_width)
            level_centers.append(centers)
            level_widths.append(total_width)
        
        max_width = max(level_widths) if level_widths else 0
        
        # Draw each level and connections
        for level_idx, tasks_in_level in enumerate(level_groups):
            if not tasks_in_level:
                continue
            
            # Draw tasks in this level
            level_lines, level_width, _ = draw_level(tasks_in_level)
            
            # Center the level
            level_offset = (max_width - level_width) // 2 if max_width > level_width else 0
            for line in level_lines:
                all_lines.append(' ' * level_offset + line)
            
            # Draw connections to next level (except for last level)
            if level_idx < len(level_groups) - 1:
                next_level = level_groups[level_idx + 1]
                if next_level:
                    current_centers = level_centers[level_idx]
                    next_centers = level_centers[level_idx + 1]
                    next_width = level_widths[level_idx + 1]
                    next_offset = (max_width - next_width) // 2 if max_width > next_width else 0
                    
                    # Find connections between current and next level
                    connections = []
                    for next_task in next_level:
                        deps_in_current = [dep for dep in dependencies[next_task] if dep in current_centers]
                        if deps_in_current:
                            # Calculate source positions (adjusted for current level offset)
                            source_positions = [level_offset + current_centers[dep] for dep in deps_in_current]
                            # Calculate target position (adjusted for next level offset)
                            target_position = next_offset + next_centers[next_task]
                            connections.append((source_positions, target_position, next_task))
                    
                    if connections:
                        # Draw connection lines
                        conn_lines = draw_level_connections(connections, max_width)
                        all_lines.extend(conn_lines)
        
        return all_lines

    def draw_level_connections(connections, max_width):
        """Draw connecting lines between two levels"""
        lines = []
        
        # Line 1: Vertical lines down from sources
        line1 = [' '] * max_width
        for source_positions, target_position, _ in connections:
            for pos in source_positions:
                if 0 <= pos < max_width:
                    line1[pos] = '│'
        lines.append(''.join(line1))
        
        # Line 2: Horizontal connections and convergence/divergence
        line2 = [' '] * max_width
        
        # Group connections by source to handle multiple children from same parent
        source_to_targets = {}
        for source_positions, target_position, task in connections:
            for source_pos in source_positions:
                if source_pos not in source_to_targets:
                    source_to_targets[source_pos] = []
                source_to_targets[source_pos].append(target_position)
        
        # Handle each source and its targets
        for source_pos, target_positions in source_to_targets.items():
            if len(target_positions) == 1:
                # Single target - check if target has multiple sources
                target_pos = target_positions[0]
                target_sources = []
                for source_positions, tp, _ in connections:
                    if tp == target_pos:
                        target_sources.extend(source_positions)
                
                if len(target_sources) == 1:
                    # Simple 1-to-1 connection
                    if 0 <= source_pos < max_width:
                        line2[source_pos] = '│'
                    if 0 <= target_pos < max_width:
                        line2[target_pos] = '│'
                else:
                    # Multiple sources converging to one target
                    left_pos = min(target_sources)
                    right_pos = max(target_sources)
                    
                    # Draw horizontal line between all sources
                    for i in range(max(0, left_pos), min(max_width, right_pos + 1)):
                        line2[i] = '─'
                    
                    # Mark sources with cross junctions
                    for pos in target_sources:
                        if 0 <= pos < max_width:
                            line2[pos] = '┼'
                    
                    # Mark target with T-junction
                    if 0 <= target_pos < max_width:
                        line2[target_pos] = '┬'
            
            else:
                # Multiple targets from same source (divergence)
                left_target = min(target_positions)
                right_target = max(target_positions)
                
                # Draw horizontal line between all targets
                for i in range(max(0, left_target), min(max_width, right_target + 1)):
                    line2[i] = '─'
                
                # Mark targets with T-junctions
                for pos in target_positions:
                    if 0 <= pos < max_width:
                        line2[pos] = '┬'
                
                # Connect source to the horizontal line
                if left_target <= source_pos <= right_target:
                    # Source is within the target range
                    if 0 <= source_pos < max_width:
                        line2[source_pos] = '┼'
                else:
                    # Source is outside target range, extend horizontal line
                    extended_left = min(source_pos, left_target)
                    extended_right = max(source_pos, right_target)
                    for i in range(max(0, extended_left), min(max_width, extended_right + 1)):
                        if line2[i] == ' ':
                            line2[i] = '─'
                    
                    # Mark source and target junctions
                    if 0 <= source_pos < max_width:
                        line2[source_pos] = '┼'
                    for pos in target_positions:
                        if 0 <= pos < max_width:
                            line2[pos] = '┬'
        
        lines.append(''.join(line2))
        
        # Line 3: Vertical lines down to targets
        line3 = [' '] * max_width
        for _, target_position, _ in connections:
            if 0 <= target_position < max_width:
                line3[target_position] = '│'
        lines.append(''.join(line3))
        
        return lines

    try:
        # Calculate task levels and group them
        levels, max_levels = calculate_levels()
        level_groups = group_by_levels(levels)
        
        if not levels:
            return "    # No valid task graph structure found"
        
        # Draw the graph level by level with connections
        result_lines = draw_connections(level_groups, levels)
        
        if not result_lines:
            return "    # No valid task graph structure found"

        return "\n".join("    # " + line.rstrip() for line in result_lines)
    
    except Exception as e:
        return f"    # Error generating task graph: {str(e)}"


def generate_class(json_path, output_name=None):
    # Validate the manifest JSON before processing
    is_valid, error_msg = check_json(json_path, verbose=False)
    if not is_valid:
        raise ValueError(f"Invalid manifest file: {error_msg}")
    
    with open(json_path, 'r') as f:
        data = json.load(f)

    class_name = output_name if output_name else data["name"]
    tasks = data["taskgraph"]  # taskgraph is now a direct array
    task_ids = [task["id"] for task in tasks]

    task_graph_ascii = build_ascii_task_graph(tasks)

    output_lines = []
    output_lines.append(TEMPLATE_CLASS_HEADER.format(class_name=class_name, task_graph_ascii=task_graph_ascii))

    output_lines.append(SETUP_METHODS_HEADER)
    output_lines.append("    def setup(self):\n        # Global setup method called before any task-specific setup\n        # Use this to initialize shared resources and instance variables\n        # Return False to signal setup failure, otherwise return True or None\n        pass\n")

    for task in tasks:
        task_id = task["id"]
        output_lines.append(f"    def {task_id}_setup(self):\n        # Setup for task '{task_id}'\n        # Initialize task-specific resources here\n        # Return False to signal setup failure, otherwise return True or None\n        pass\n")

    output_lines.append(LOOP_METHODS_HEADER)
    for task in tasks:
        task_id = task["id"]
        description = task.get("description", f"Task '{task_id}'")
        output_keys = task.get("output", [])
        input_params = task.get("input", [])
        
        # Create method signature with input parameters
        if input_params:
            params_str = ", " + ", ".join(input_params)
        else:
            params_str = ""
        
        # Create the return dictionary structure
        if output_keys:
            return_dict_items = [f'"{key}": None' for key in output_keys]
            return_statement = "        return {" + ", ".join(return_dict_items) + "}"
        else:
            return_statement = "        return {}"
        
        output_lines.append(f"    def {task_id}_loop(self{params_str}):\n        # {description}\n        # Task logic for '{task_id}' goes here\n        # TODO: Implement your logic and populate the return dictionary\n{return_statement}\n")

    output_lines.append(CLEANUP_METHODS_HEADER)
    for task in tasks:
        task_id = task["id"]
        output_lines.append(f"    def {task_id}_cleanup(self):\n        # Cleanup for task '{task_id}'\n        # Release task-specific resources here\n        # Return False to signal cleanup failure, otherwise return True or None\n        pass\n")

    output_lines.append("    def cleanup(self):\n        # Global cleanup method called after all task-specific cleanup\n        # Use this to release shared resources\n        # Return False to signal cleanup failure, otherwise return True or None\n        pass\n")

    return class_name, "\n".join(output_lines)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate Python app class from manifest JSON.")
    parser.add_argument("--manifest_name", help="Path to the manifest JSON file")

    args = parser.parse_args()

    json_filename = args.manifest_name
    
    try:
        output_classname, class_code = generate_class(json_filename)

        output_path = os.path.join(OUTPUT_FOLDER, f"{output_classname}.py")

        with open(output_path, 'w') as f:
            f.write(class_code)

        print(f"Generated class written to {output_path}")
    
    except ValueError as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"ERROR: Unexpected error: {e}")
        sys.exit(1)
