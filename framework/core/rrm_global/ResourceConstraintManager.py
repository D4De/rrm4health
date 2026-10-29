import json
import os
from typing import Any, Dict, List, Optional, Set, Tuple

import core.Utils as Utils
from Config import FRAMEWORK_DIR


class ResourceConstraintManager:
    """Validates task-level resource constraints against resource descriptors.

    The manager evaluates the `requires` field in an application manifest and checks
    if the currently available resource instances can satisfy all requests.

    Supported request types:
    - ResourceRequest
    - DeviceRequest

    It can also produce parameter values resolved from selected resources using
    `parameter_linked` + `separator`.
    """

    def __init__(
        self,
        resources_catalog_path: Optional[str] = None,
        resource_instances_path: Optional[str] = None,
    ):
        descriptors_dir = os.path.join(FRAMEWORK_DIR, "resources_descriptors")
        self._resources_catalog_path = resources_catalog_path or os.path.join(descriptors_dir, "peripheral_catalog.json")
        self._resource_instances_path = resource_instances_path or os.path.join(descriptors_dir, "peripheral_inventory.json")

        self._resource_catalog: Dict[str, Dict[str, Any]] = {}
        self._resource_instances: Dict[str, Dict[str, Any]] = {}

    def reload(self) -> None:
        """Reload resources catalog and resource instances from disk."""
        self._resource_catalog = self._load_json_object(self._resources_catalog_path)
        self._resource_instances = self._load_json_object(self._resource_instances_path)

    def get_resource_instances_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Return a shallow copy of known resource instances."""
        if not self._resource_catalog or not self._resource_instances:
            self.reload()
        return dict(self._resource_instances)

    def validate_manifest_constraints(
        self,
        manifest: Dict[str, Any],
        pre_used_exclusive_ids: Optional[Set[str]] = None,
    ) -> Dict[str, Any]:
        """Validate all `requires` constraints in the provided manifest.

        Returns a structured dictionary with:
        - valid: bool
        - errors: list[str]
        - allocations: list[dict]
        - resolved_parameters: dict[str, str]
        """
        if not self._resource_catalog or not self._resource_instances:
            self.reload()

        taskgraph = manifest.get("taskgraph", [])
        if not isinstance(taskgraph, list):
            return {
                "valid": False,
                "errors": ["Manifest field 'taskgraph' is not a valid list."],
                "allocations": [],
                "resolved_parameters": {},
            }

        errors: List[str] = []
        allocations: List[Dict[str, Any]] = []
        resolved_parameters: Dict[str, str] = {}

        allocated_exclusive_ids: Set[str] = set(pre_used_exclusive_ids or set())

        for task in taskgraph:
            task_id = task.get("id", "<unknown_task>")
            requires = task.get("requires", [])

            if not requires:
                continue

            if not isinstance(requires, list):
                errors.append(f"Task '{task_id}' has invalid 'requires' field (must be a list).")
                continue

            for req_idx, request in enumerate(requires):
                req_type = request.get("type")
                if req_type == "ResourceRequest":
                    ok, req_error, req_allocation = self._resolve_resource_request(
                        task_id,
                        req_idx,
                        request,
                        allocated_exclusive_ids,
                    )
                elif req_type == "DeviceRequest":
                    ok, req_error, req_allocation = self._resolve_device_request(
                        task_id,
                        req_idx,
                        request,
                        allocated_exclusive_ids,
                    )
                else:
                    ok = False
                    req_error = f"Task '{task_id}' requires[{req_idx}] has unsupported type '{req_type}'."
                    req_allocation = None

                if not ok:
                    errors.append(req_error)
                    continue

                allocations.append(req_allocation)
                parameter_linked = req_allocation.get("parameter_linked")
                if parameter_linked:
                    resolved_parameters[parameter_linked] = req_allocation.get("linked_value", "")

        return {
            "valid": len(errors) == 0,
            "errors": errors,
            "allocations": allocations,
            "resolved_parameters": resolved_parameters,
        }

    def get_constraint_linked_parameters(self, manifest: Dict[str, Any]) -> Set[str]:
        """Return all unique parameter_linked names used by manifest constraints."""
        linked: Set[str] = set()
        for task in manifest.get("taskgraph", []):
            requires = task.get("requires", [])
            if not isinstance(requires, list):
                continue
            for request in requires:
                parameter_name = request.get("parameter_linked")
                if isinstance(parameter_name, str) and parameter_name:
                    linked.add(parameter_name)
        return linked

    def validate_linked_parameter_value(
        self,
        manifest: Dict[str, Any],
        parameter_name: str,
        parameter_value: Any,
        used_exclusive_ids: Optional[Set[str]] = None,
    ) -> Tuple[bool, str]:
        """Validate one user-provided linked parameter against all related requests.

        This method performs only matching/validation and never resolves/fixes values.
        """
        if not self._resource_catalog or not self._resource_instances:
            self.reload()

        used_exclusive_ids = used_exclusive_ids if used_exclusive_ids is not None else set()

        related_requests: List[Tuple[str, int, Dict[str, Any]]] = []
        for task in manifest.get("taskgraph", []):
            task_id = task.get("id", "<unknown_task>")
            requires = task.get("requires", [])
            if not isinstance(requires, list):
                continue
            for req_idx, req in enumerate(requires):
                if req.get("parameter_linked") == parameter_name:
                    related_requests.append((task_id, req_idx, req))

        if not related_requests:
            return False, f"No requires entry found for parameter_linked '{parameter_name}'."

        for task_id, req_idx, req in related_requests:
            selected_instances = self._parse_linked_value_to_ids(parameter_value, req.get("separator", ""))
            req_type = req.get("type")

            if req_type == "ResourceRequest":
                ok, err = self.match_resource_request_selection(
                    task_id,
                    req_idx,
                    req,
                    selected_instances,
                    used_exclusive_ids,
                )
            elif req_type == "DeviceRequest":
                ok, err = self.match_device_request_selection(
                    task_id,
                    req_idx,
                    req,
                    selected_instances,
                    used_exclusive_ids,
                )
            else:
                return False, f"Task '{task_id}' requires[{req_idx}] has unsupported type '{req_type}'."

            if not ok:
                return False, err

        return True, ""

    def collect_exclusive_instances_for_linked_parameter(
        self,
        manifest: Dict[str, Any],
        parameter_name: str,
        parameter_value: Any,
    ) -> Set[str]:
        """Collect exclusive instance IDs referenced by one linked parameter value."""
        exclusive_ids: Set[str] = set()
        for task in manifest.get("taskgraph", []):
            requires = task.get("requires", [])
            if not isinstance(requires, list):
                continue

            for req in requires:
                if req.get("parameter_linked") != parameter_name:
                    continue

                selected = self._parse_linked_value_to_ids(parameter_value, req.get("separator", ""))
                exclusive_ids.update(self._get_effective_exclusive_instances(req, selected))

        return exclusive_ids

    def get_effective_exclusive_instances(
        self,
        request: Dict[str, Any],
        selected_instances: List[str],
    ) -> Set[str]:
        """Return selected instances that are effectively exclusive for this request."""
        return self._get_effective_exclusive_instances(request, selected_instances)

    def match_resource_request_selection(
        self,
        task_id: str,
        req_idx: int,
        request: Dict[str, Any],
        selected_instances: List[str],
        allocated_exclusive_ids: Optional[Set[str]] = None,
    ) -> Tuple[bool, str]:
        """Public matcher for ResourceRequest against user-selected instances."""
        allocated_exclusive_ids = allocated_exclusive_ids if allocated_exclusive_ids is not None else set()

        features = request.get("features", {})
        count = request.get("count", 0)
        request_exclusive = bool(request.get("exclusive", False))
        parameter_linked = request.get("parameter_linked", "")

        if len(selected_instances) != count:
            return (
                False,
                (
                    f"Task '{task_id}' requires[{req_idx}] ResourceRequest mismatch: "
                    f"expected {count} resources, got {len(selected_instances)} from parameter '{parameter_linked}'."
                ),
            )

        if len(set(selected_instances)) != len(selected_instances):
            return (
                False,
                f"Task '{task_id}' requires[{req_idx}] ResourceRequest contains duplicated selected resources.",
            )

        effective_exclusive_instances = self._get_effective_exclusive_instances(request, selected_instances)

        for instance_id in selected_instances:
            if instance_id not in self._resource_instances:
                return (
                    False,
                    f"Task '{task_id}' requires[{req_idx}] ResourceRequest references unknown resource '{instance_id}'.",
                )

            instance = self._resource_instances[instance_id]
            status = str(instance.get("status", "available")).lower()
            if status != "available":
                return (
                    False,
                    f"Task '{task_id}' requires[{req_idx}] ResourceRequest resource '{instance_id}' is not available.",
                )

            if self._is_effective_exclusive(request_exclusive, instance_id) and instance_id in allocated_exclusive_ids:
                return (
                    False,
                    f"Task '{task_id}' requires[{req_idx}] ResourceRequest conflicts on exclusive resource '{instance_id}'.",
                )

            if not self._instance_matches_features(instance, features):
                return (
                    False,
                    (
                        f"Task '{task_id}' requires[{req_idx}] ResourceRequest resource '{instance_id}' "
                        f"does not satisfy required features."
                    ),
                )

        allocated_exclusive_ids.update(effective_exclusive_instances)

        return True, ""

    def match_device_request_selection(
        self,
        task_id: str,
        req_idx: int,
        request: Dict[str, Any],
        selected_instances: List[str],
        allocated_exclusive_ids: Optional[Set[str]] = None,
    ) -> Tuple[bool, str]:
        """Public matcher for DeviceRequest against user-selected instances."""
        allocated_exclusive_ids = allocated_exclusive_ids if allocated_exclusive_ids is not None else set()

        required_device_ids = request.get("device_id", [])
        request_exclusive = bool(request.get("exclusive", False))
        parameter_linked = request.get("parameter_linked", "")

        if len(selected_instances) != len(required_device_ids):
            return (
                False,
                (
                    f"Task '{task_id}' requires[{req_idx}] DeviceRequest mismatch: expected {len(required_device_ids)} "
                    f"resource(s), got {len(selected_instances)} from parameter '{parameter_linked}'."
                ),
            )

        if set(selected_instances) != set(required_device_ids):
            return (
                False,
                (
                    f"Task '{task_id}' requires[{req_idx}] DeviceRequest mismatch: selected resources {selected_instances} "
                    f"do not match required device_id list {required_device_ids}."
                ),
            )

        for instance_id in selected_instances:
            if instance_id not in self._resource_instances:
                return (
                    False,
                    f"Task '{task_id}' requires[{req_idx}] DeviceRequest references unknown resource '{instance_id}'.",
                )

            instance = self._resource_instances[instance_id]
            status = str(instance.get("status", "available")).lower()
            if status != "available":
                return (
                    False,
                    f"Task '{task_id}' requires[{req_idx}] DeviceRequest resource '{instance_id}' is not available.",
                )

            if self._is_effective_exclusive(request_exclusive, instance_id) and instance_id in allocated_exclusive_ids:
                return (
                    False,
                    f"Task '{task_id}' requires[{req_idx}] DeviceRequest conflicts on exclusive resource '{instance_id}'.",
                )

        allocated_exclusive_ids.update(self._get_effective_exclusive_instances(request, selected_instances))

        return True, ""

    def _resolve_resource_request(
        self,
        task_id: str,
        req_idx: int,
        request: Dict[str, Any],
        allocated_exclusive_ids: Set[str],
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        features = request.get("features", {})
        count = request.get("count", 0)
        request_exclusive = bool(request.get("exclusive", False))
        parameter_linked = request.get("parameter_linked", "")
        separator = request.get("separator", "")

        candidates: List[str] = []
        for instance_id in sorted(self._resource_instances.keys()):
            if self._is_effective_exclusive(request_exclusive, instance_id) and instance_id in allocated_exclusive_ids:
                continue

            instance = self._resource_instances[instance_id]
            if self._instance_matches_features(instance, features):
                candidates.append(instance_id)

        if len(candidates) < count:
            return (
                False,
                (
                    f"Task '{task_id}' requires[{req_idx}] ResourceRequest not satisfiable: "
                    f"required count={count}, available matches={len(candidates)}."
                ),
                None,
            )

        selected = candidates[:count]
        effective_exclusive_instances = self._get_effective_exclusive_instances(request, selected)
        allocated_exclusive_ids.update(effective_exclusive_instances)

        linked_value = separator.join(selected) if separator else (selected[0] if selected else "")

        return (
            True,
            "",
            {
                "task_id": task_id,
                "request_index": req_idx,
                "type": "ResourceRequest",
                "parameter_linked": parameter_linked,
                "separator": separator,
                "selected_instances": selected,
                "linked_value": linked_value,
                "exclusive": bool(effective_exclusive_instances),
                "exclusive_instances": sorted(effective_exclusive_instances),
            },
        )

    def _resolve_device_request(
        self,
        task_id: str,
        req_idx: int,
        request: Dict[str, Any],
        allocated_exclusive_ids: Set[str],
    ) -> Tuple[bool, str, Optional[Dict[str, Any]]]:
        device_ids = request.get("device_id", [])
        request_exclusive = bool(request.get("exclusive", False))
        parameter_linked = request.get("parameter_linked", "")
        separator = request.get("separator", "")

        missing = [device_id for device_id in device_ids if device_id not in self._resource_instances]
        if missing:
            return (
                False,
                f"Task '{task_id}' requires[{req_idx}] DeviceRequest has unknown device_id values: {missing}.",
                None,
            )

        effective_exclusive_instances = self._get_effective_exclusive_instances(request, device_ids)
        already_used = [device_id for device_id in device_ids if device_id in effective_exclusive_instances and device_id in allocated_exclusive_ids]
        if already_used:
            return (
                False,
                f"Task '{task_id}' requires[{req_idx}] DeviceRequest conflicts on exclusive devices: {already_used}.",
                None,
            )
        allocated_exclusive_ids.update(effective_exclusive_instances)

        linked_value = separator.join(device_ids) if separator else (device_ids[0] if device_ids else "")

        return (
            True,
            "",
            {
                "task_id": task_id,
                "request_index": req_idx,
                "type": "DeviceRequest",
                "parameter_linked": parameter_linked,
                "separator": separator,
                "selected_instances": device_ids,
                "linked_value": linked_value,
                "exclusive": bool(effective_exclusive_instances),
                "exclusive_instances": sorted(effective_exclusive_instances),
            },
        )

    def _get_effective_exclusive_instances(self, request: Dict[str, Any], instance_ids: List[str]) -> Set[str]:
        request_exclusive = bool(request.get("exclusive", False))
        return {
            instance_id
            for instance_id in instance_ids
            if self._is_effective_exclusive(request_exclusive, instance_id)
        }

    def _is_effective_exclusive(self, request_exclusive: bool, instance_id: str) -> bool:
        return request_exclusive or self._is_exclusive_by_policy(instance_id)

    def _is_exclusive_by_policy(self, instance_id: str) -> bool:
        instance = self._resource_instances.get(instance_id, {})
        device_type = instance.get("type")
        type_definition = self._resource_catalog.get(device_type, {}) if device_type else {}

        excl_by_design = bool(type_definition.get("EXCL_BY_DESIGN", False))
        if excl_by_design:
            return True

        return bool(instance.get("EXCL_BY_CONFIGURATION", False))

    @staticmethod
    def _parse_linked_value_to_ids(raw_value: Any, separator: str) -> List[str]:
        if isinstance(raw_value, list):
            return [str(item).strip() for item in raw_value if str(item).strip()]

        value = str(raw_value).strip()
        if value == "":
            return []

        if separator == "":
            return [value]

        return [chunk.strip() for chunk in value.split(separator) if chunk.strip()]

    def _instance_matches_features(self, instance: Dict[str, Any], required_features: Dict[str, Any]) -> bool:
        if not required_features:
            return True

        device_type = instance.get("type")
        type_definition = self._resource_catalog.get(device_type, {})

        #Features can be defined at the instance level or at the type level.
        #Features type level
        sensors = type_definition.get("sensors", {})
        connections = type_definition.get("connections", {})
        if not connections:
            connections = type_definition.get("connection", {})
        power = type_definition.get("power", {})
        
        #Features instance level
        location = instance.get("location", {})

        for feature_name, feature_requirements in required_features.items():
            if feature_name == "location":
                if not isinstance(location, dict):
                    return False
                normalized_required_location = Utils.normalize_indoor_location(feature_requirements)
                normalized_available_location = Utils.normalize_indoor_location(location)
                if not self._is_subset_dict(normalized_required_location, normalized_available_location):
                    return False
                continue

            if feature_name == "ble":
                if "bluetooth" not in connections and "ble" not in connections:
                    return False
                continue

            if feature_name == "bluetooth":
                if "bluetooth" not in connections and "ble" not in connections:
                    return False
                continue

            if feature_name in sensors:
                if not self._is_subset_dict(feature_requirements, sensors.get(feature_name, {})):
                    return False
                continue

            if feature_name in connections:
                if not self._is_subset_dict(feature_requirements, connections.get(feature_name, {})):
                    return False
                continue

            if feature_name in power:
                if not self._is_subset_dict(feature_requirements, power.get(feature_name, {})):
                    return False
                continue

            return False

        return True

    @staticmethod
    def _is_subset_dict(required: Any, available: Any) -> bool:
        if required is None:
            return True

        if isinstance(required, dict):
            if not isinstance(available, dict):
                return False
            for key, required_value in required.items():
                if key not in available:
                    return False
                if not ResourceConstraintManager._is_subset_dict(required_value, available[key]):
                    return False
            return True

        if isinstance(required, list):
            if not isinstance(available, list):
                return False
            return all(item in available for item in required)

        if isinstance(required, (int, float)) and isinstance(available, (int, float)):
            return float(required) == float(available)

        return str(required) == str(available)

    @staticmethod
    def _load_json_object(path: str) -> Dict[str, Any]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Resource descriptor file not found: {path}")

        with open(path, "r", encoding="utf-8") as file_obj:
            data = json.load(file_obj)

        if not isinstance(data, dict):
            raise ValueError(f"Resource descriptor file must contain a JSON object: {path}")

        return data
