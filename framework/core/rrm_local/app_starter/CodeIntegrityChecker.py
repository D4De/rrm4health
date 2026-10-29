import ast


class InconsistentReturnException(Exception):
    """Exception raised when task methods have inconsistent return patterns."""
    pass


def check_code_integrity(file_path, task_names, all_tasks=None):
    """
    Comprehensive integrity check for task loop methods.
    
    Validates the following:
    1. All *_loop methods only return dicts or None (no inconsistent return types).
    2. All return statements in a single function return dicts with the same keys.
    3. No two *_loop functions return the same key if they directly converge into the same node.
    4. The set of values produced matches the set of parameters required across all *_loop functions.
    
    Args:
        file_path: Path to the Python file to check
        task_names: List of task names (without _loop suffix)
        all_tasks: Optional list of all task definitions for dependency checking
        
    Returns:
        Dictionary mapping function names to their return keys
        
    Raises:
        InconsistentReturnException: If any integrity check fails
    """
    method_names_to_check = [task + '_loop' for task in task_names]

    with open(file_path, "r", encoding="utf-8") as f:
        tree = ast.parse(f.read())

    result = {}  # function_name -> list of return dict keys
    function_parameters = {}  # function_name -> list of parameter names
    key_to_function = {}  # key -> function that returns it

    class Checker(ast.NodeVisitor):
        def visit_FunctionDef(self, node):
            if method_names_to_check and node.name not in method_names_to_check:
                return

            # Extract function parameters (excluding 'self')
            params = [arg.arg for arg in node.args.args if arg.arg != 'self']
            function_parameters[node.name] = params

            dict_returns = []

            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return):
                    val = stmt.value
                    if isinstance(val, ast.Dict):
                        keys = []
                        for key in val.keys:
                            if isinstance(key, ast.Str):
                                keys.append(key.s)
                            elif isinstance(key, ast.Constant):  # Python 3.8+
                                keys.append(key.value)
                        dict_returns.append(keys)
                    elif val is not None:
                        raise InconsistentReturnException(
                            f"Function '{node.name}' must only return dicts or nothing."
                        )

            if dict_returns:
                first = dict_returns[0]
                for r in dict_returns[1:]:
                    if r != first:
                        raise InconsistentReturnException(
                            f"Inconsistent return keys in function '{node.name}': {dict_returns}"
                        )
                result[node.name] = first
            else:
                result[node.name] = []  # Ensure all checked methods are recorded

    # First pass: collect function return keys and parameters
    Checker().visit(tree)

    # Second pass: check for duplicate keys across functions only if they converge into the same node
    if all_tasks:
        # Build task dependency map
        task_map = {task["id"]: task for task in all_tasks}
        
        # For each key, find all tasks that could potentially consume it
        key_to_functions = {}  # key -> list of functions that return it
        for function_name, keys in result.items():
            task_name = function_name.replace('_loop', '')
            for key in keys:
                if key not in key_to_functions:
                    key_to_functions[key] = []
                key_to_functions[key].append(task_name)
        
        # Check if duplicate keys converge directly into the same consuming task (one level below)
        for key, producing_tasks in key_to_functions.items():
            if len(producing_tasks) > 1:
                # Find all tasks that directly depend on any of the producing tasks
                direct_consumers = set()
                
                for task_name in task_names:
                    task_info = task_map.get(task_name, {})
                    dependencies = task_info.get("depends_on", [])
                    
                    # Check if this task directly depends on any of the producing tasks
                    for dep in dependencies:
                        if dep in producing_tasks:
                            direct_consumers.add(task_name)
                
                # If there are direct consumers, check if the same key would be consumed
                if direct_consumers:
                    for consumer in direct_consumers:
                        consumer_method = consumer + '_loop'
                        if consumer_method in function_parameters:
                            consumer_params = function_parameters[consumer_method]
                            if key in consumer_params:
                                # Count how many of the producing tasks this consumer directly depends on
                                consumer_dependencies = task_map.get(consumer, {}).get("depends_on", [])
                                conflicting_producers = [task for task in producing_tasks if task in consumer_dependencies]
                                
                                if len(conflicting_producers) > 1:
                                    # This key converges directly into the same consumer task - this is a problem
                                    raise InconsistentReturnException(
                                        f"Key '{key}' is returned by multiple functions that directly converge into task '{consumer}': {conflicting_producers}"
                                    )
    else:
        # Fallback to original behavior if all_tasks is not provided
        key_to_function = {}
        for function_name, keys in result.items():
            for key in keys:
                if key in key_to_function:
                    raise InconsistentReturnException(
                        f"Key '{key}' is returned by multiple functions: "
                        f"'{key_to_function[key]}' and '{function_name}'"
                    )
                key_to_function[key] = function_name

    # Third pass: ensure required params match produced keys
    all_required_params = set()
    all_produced_values = set()

    for function_name in method_names_to_check:
        if function_name in function_parameters:
            all_required_params.update(function_parameters[function_name])
        if function_name in result:
            all_produced_values.update(result[function_name])

    if all_required_params != all_produced_values:
        missing_productions = all_required_params - all_produced_values
        extra_productions = all_produced_values - all_required_params

        error_msg = "Mismatch between required parameters and produced values:"
        if missing_productions:
            error_msg += f"\n  Required but not produced: {sorted(missing_productions)}"
        if extra_productions:
            error_msg += f"\n  Produced but not required: {sorted(extra_productions)}"

        raise InconsistentReturnException(error_msg)

    return result
