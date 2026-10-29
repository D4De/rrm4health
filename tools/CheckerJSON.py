import json
import sys
import os
from jsonschema import validate, ValidationError

# Support direct execution from any working directory.
framework_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'framework'))
if framework_dir not in sys.path:
    sys.path.insert(0, framework_dir)

from core.models.DescriptorSchema import ParameterDefinition

# --- SCHEMA ---
# Updated schema for the simplified descriptor structure
schema = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "taskgraph": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "description": {"type": "string"},
                    "depends_on": {"type": "array", "items": {"type": "string"}},
                    "input": {"type": "array", "items": {"type": "string"}},
                    "output": {"type": "array", "items": {"type": "string"}},
                    "parameters": {"type": "object"},
                    "required_resources": {"type": "object"},
                    "requires": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "oneOf": [
                                {
                                    "properties": {
                                        "type": {"const": "ResourceRequest"},
                                        "count": {"type": "integer", "minimum": 1},
                                        "exclusive": {"type": "boolean"},
                                        "parameter_linked": {"type": "string", "minLength": 1},
                                        "separator": {"type": "string"},
                                        "features": {"type": "object", "minProperties": 1}
                                    },
                                    "required": ["type", "count", "exclusive", "parameter_linked", "separator", "features"],
                                    "additionalProperties": False
                                },
                                {
                                    "properties": {
                                        "type": {"const": "DeviceRequest"},
                                        "exclusive": {"type": "boolean"},
                                        "parameter_linked": {"type": "string", "minLength": 1},
                                        "separator": {"type": "string"},
                                        "device_id": {
                                            "type": "array",
                                            "items": {"type": "string", "minLength": 1},
                                            "minItems": 1
                                        }
                                    },
                                    "required": ["type", "exclusive", "parameter_linked", "separator", "device_id"],
                                    "additionalProperties": False
                                }
                            ]
                        }
                    }
                },
                "required": ["id", "depends_on", "output"]
            }
        },
        "executable": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "parameters": {"type": "object"},
                "timeouts": {
                    "type": "object",
                    "properties": {
                        "setup": {"type": "integer", "minimum": 1},
                        "loop": {"type": "integer", "minimum": 1},
                        "cleanup": {"type": "integer", "minimum": 1}
                    },
                    "additionalProperties": False
                }
            },
            "required": ["path", "parameters", "timeouts"]
        },
        "configurations": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string"},
                    "partitions": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "tasks": {"type": "array", "items": {"type": "string"}},
                                "node": {"type": "string"},
                                "required_resources": {
                                    "type": "object",
                                    "properties": {
                                        "ram": {"type": "integer"},
                                        "disk": {"type": "integer"},
                                        "network_upload": {"type": "integer"},
                                        "network_download": {"type": "integer"}
                                    },
                                    "required": ["ram", "disk", "network_upload", "network_download"]
                                }
                            },
                            "required": ["id", "tasks", "node", "required_resources"]
                        }
                    },
                    "channels": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "from_partition": {"type": "string"},
                                "to_partition": {"type": "string"}
                            },
                            "required": ["from_partition", "to_partition"]
                        }
                    }
                },
                "required": ["id", "partitions", "channels"]
            }
        }
    },
    "required": ["name", "taskgraph", "executable", "configurations"]
}

# --- VALIDATORE ---
def check_json(filepath: str, verbose: bool = True):
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Validazione schema base
        validate(instance=data, schema=schema)

        # --- Raccolta task IDs ---
        task_ids = [task["id"] for task in data["taskgraph"]]

        # --- Unicità task.id ---
        duplicates = {tid for tid in task_ids if task_ids.count(tid) > 1}
        if duplicates:
            raise ValueError(f"Task IDs duplicati trovati: {', '.join(duplicates)}")

        # --- Unicità configuration.id ---
        config_ids = [cfg["id"] for cfg in data["configurations"]]
        duplicates = {cid for cid in config_ids if config_ids.count(cid) > 1}
        if duplicates:
            raise ValueError(f"Configuration IDs duplicati trovati: {', '.join(duplicates)}")

        # --- Controlli per ogni configurazione ---
        for cfg in data["configurations"]:
            # Unicità partition.id
            partition_ids = [p["id"] for p in cfg["partitions"]]
            duplicates = {pid for pid in partition_ids if partition_ids.count(pid) > 1}
            if duplicates:
                raise ValueError(f"Partition IDs duplicati in configurazione '{cfg['id']}': {', '.join(duplicates)}")

            # Unicità canali (from -> to)
            channel_pairs = [(ch["from_partition"], ch["to_partition"]) for ch in cfg["channels"]]
            duplicates = {f"{src}->{dst}" for (src, dst) in channel_pairs if channel_pairs.count((src, dst)) > 1}
            if duplicates:
                raise ValueError(f"Channel duplicati in configurazione '{cfg['id']}': {', '.join(duplicates)}")

            # Controllo che i canali si riferiscano a partizioni valide
            for ch in cfg["channels"]:
                if ch["from_partition"] not in partition_ids:
                    raise ValueError(
                        f"Nella configurazione '{cfg['id']}' il canale ha 'from_partition'='{ch['from_partition']}' "
                        f"che non esiste."
                    )
                if ch["to_partition"] not in partition_ids:
                    raise ValueError(
                        f"Nella configurazione '{cfg['id']}' il canale ha 'to_partition'='{ch['to_partition']}' "
                        f"che non esiste."
                    )

            # Controllo che le partizioni usino solo tasks validi
            for part in cfg["partitions"]:
                for t in part["tasks"]:
                    if t not in task_ids:
                        raise ValueError(
                            f"Nella configurazione '{cfg['id']}', la partizione '{part['id']}' usa il task '{t}' "
                            f"che non esiste."
                        )

        # --- Controllo che tutti i depends_on puntino a tasks esistenti ---
        for task in data["taskgraph"]:
            for dep in task["depends_on"]:
                if dep not in task_ids:
                    raise ValueError(f"Il task '{task['id']}' dipende da '{dep}', che non esiste.")

        # --- Controllo custom sui parameters ---
        # Parameters are now merged with system parameters in the core
        # We verify that user parameters don't override system parameter names improperly
        params = data["executable"]["parameters"]
        system_params = ParameterDefinition.get_system_parameters()
        
        for pname in params.keys():
            if pname in system_params:
                raise ValueError(
                    f"Parameter '{pname}' is a system-managed parameter and should not be defined in the descriptor. "
                    f"System parameters are automatically handled by the framework."
                )

        executable_param_names = set(params.keys())
        for task in data["taskgraph"]:
            for idx, req in enumerate(task.get("requires", [])):
                req_type = req.get("type")
                if req_type not in {"ResourceRequest", "DeviceRequest"}:
                    raise ValueError(
                        f"Task '{task['id']}' has invalid requires[{idx}].type='{req_type}'. "
                        f"Allowed values are ResourceRequest and DeviceRequest."
                    )

                linked_param = req.get("parameter_linked")
                if linked_param not in executable_param_names:
                    raise ValueError(
                        f"Task '{task['id']}' has requires[{idx}] with parameter_linked='{linked_param}', "
                        f"but this parameter is not defined in executable.parameters."
                    )

                if req_type == "ResourceRequest":
                    if not isinstance(req.get("features"), dict) or not req.get("features"):
                        raise ValueError(
                            f"Task '{task['id']}' has ResourceRequest at requires[{idx}] without valid non-empty features."
                        )

                    count = req.get("count")
                    separator = req.get("separator")
                    if count == 1 and separator != "":
                        raise ValueError(
                            f"Task '{task['id']}' has ResourceRequest at requires[{idx}] with count=1, "
                            f"so separator must be an empty string. Suggested fix: set separator to ''."
                        )
                    if count > 1 and separator == "":
                        raise ValueError(
                            f"Task '{task['id']}' has ResourceRequest at requires[{idx}] with count={count}, "
                            f"so separator must be a non-empty string. Suggested fix: set separator to '-' (or ',')."
                        )

                if req_type == "DeviceRequest":
                    device_ids = req.get("device_id")
                    if not isinstance(device_ids, list) or len(device_ids) == 0:
                        raise ValueError(
                            f"Task '{task['id']}' has DeviceRequest at requires[{idx}] without valid non-empty device_id list."
                        )

                    separator = req.get("separator")
                    if len(device_ids) == 1 and separator != "":
                        raise ValueError(
                            f"Task '{task['id']}' has DeviceRequest at requires[{idx}] with a single device_id, "
                            f"so separator must be an empty string. Suggested fix: set separator to ''."
                        )
                    if len(device_ids) > 1 and separator == "":
                        raise ValueError(
                            f"Task '{task['id']}' has DeviceRequest at requires[{idx}] with multiple device_id values, "
                            f"so separator must be a non-empty string. Suggested fix: set separator to '-' (or ',')."
                        )

        if verbose:
            print(f"VALID: {filepath} is valid and respects all constraints.")
        return (True, None)

    except json.JSONDecodeError as e:
        error_msg = f"JSON syntax error in {filepath}: {e}"
        if verbose:
            print(f"ERROR: {error_msg}")
        return (False, error_msg)
    except ValidationError as e:
        error_msg = f"Schema error in {filepath}: {e.message}"
        if verbose:
            print(f"ERROR: {error_msg}")
        return (False, error_msg)
    except ValueError as e:
        error_msg = f"Logical constraint error in {filepath}: {e}"
        if verbose:
            print(f"ERROR: {error_msg}")
        return (False, error_msg)
    except Exception as e:
        error_msg = f"Unexpected error in {filepath}: {e}"
        if verbose:
            print(f"ERROR: {error_msg}")
        return (False, error_msg)

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Uso: python checker.py file.json")
    else:
        check_json(sys.argv[1])
