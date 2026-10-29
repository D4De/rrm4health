import copy
import json
import logging
import os
import time
from threading import Lock
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)


class LocalResourceRegistry:
    """Registry locale delle risorse fisicamente collegate al nodo RRMLocal."""

    def __init__(self) -> None:
        self.__node_id: Optional[str] = None
        self.__type_id: Optional[str] = None
        self.__resources: Dict[str, Dict[str, Any]] = {}

    def load_from_node_inventory_file(self, node_id: str, node_inventory_file: str) -> bool:
        """Load node-local resources from node_inventory.json for the specified node_id."""
        if not node_id:
            logger.warning("Cannot load local resources: node_id is empty")
            return False

        if not node_inventory_file or not os.path.exists(node_inventory_file):
            logger.warning("Cannot load local resources: node_inventory_file not found (%s)", node_inventory_file)
            return False

        try:
            with open(node_inventory_file, "r", encoding="utf-8") as file_obj:
                data = json.load(file_obj)
        except Exception as exc:
            logger.error("Error reading node_inventory file %s: %s", node_inventory_file, exc)
            return False

        if not isinstance(data, dict):
            logger.error("Invalid node_inventory format in %s: expected JSON object", node_inventory_file)
            return False

        target_node = data.get(node_id)

        if not target_node:
            logger.warning("Node '%s' not found in node_inventory file %s", node_id, node_inventory_file)
            return False

        if not isinstance(target_node, dict):
            logger.error("Invalid node entry for '%s' in %s: expected object", node_id, node_inventory_file)
            return False

        resources = target_node.get("resources", {})
        if not isinstance(resources, dict):
            logger.error("Invalid resources format for node '%s': expected object", node_id)
            return False

        self.__node_id = node_id
        self.__type_id = str(target_node.get("type", "")) if target_node.get("type") is not None else None
        self.__resources = copy.deepcopy(resources)

        logger.info(
            "Loaded %d local resources for node_id=%s from %s",
            len(self.__resources),
            self.__node_id,
            node_inventory_file,
        )
        return True

    def load_from_node_magazzino_file(self, node_id: str, node_magazzino_file: str) -> bool:
        """Backward-compatibility shim for old method name."""
        return self.load_from_node_inventory_file(node_id, node_magazzino_file)

    def load_from_board_nodes_file(self, node_id: str, board_nodes_file: str) -> bool:
        """Backward-compatibility shim for very old method name."""
        return self.load_from_node_inventory_file(node_id, board_nodes_file)

    def get_node_id(self) -> Optional[str]:
        return self.__node_id

    def get_type_id(self) -> Optional[str]:
        return self.__type_id

    def get_resources_snapshot(self) -> Dict[str, Dict[str, Any]]:
        return copy.deepcopy(self.__resources)

    def get_resource(self, resource_id: str) -> Dict[str, Any]:
        if not resource_id:
            return {}
        value = self.__resources.get(resource_id)
        return copy.deepcopy(value) if isinstance(value, dict) else {}

    def add_or_update_resource(self, resource_id: str, resource_data: Dict[str, Any]) -> None:
        if not resource_id:
            return
        current = self.__resources.get(resource_id)
        merged = dict(current) if isinstance(current, dict) else {}
        if isinstance(resource_data, dict):
            merged.update(resource_data)
        self.__resources[resource_id] = merged

    def remove_resource(self, resource_id: str) -> None:
        if not resource_id:
            return
        self.__resources.pop(resource_id, None)

    def to_sync_payload(self) -> Dict[str, Any]:
        return {
            "node_id": self.__node_id,
            "type_id": self.__type_id,
            "resources": self.get_resources_snapshot(),
            "updated_at": time.time(),
        }


class GlobalResourceRegistry:
    """Registry globale delle risorse note su tutti i nodi connessi."""

    def __init__(self) -> None:
        self.__registry_by_node: Dict[str, Dict[str, Any]] = {}
        self.__lock = Lock()

    @staticmethod
    def _normalize_node_key(node_key: Any) -> str:
        if isinstance(node_key, tuple) and len(node_key) == 2:
            return f"{node_key[0]}:{node_key[1]}"
        return str(node_key)

    def upsert_node_resources(self, node_key: Any, payload: Dict[str, Any]) -> None:
        normalized_key = self._normalize_node_key(node_key)
        record = {
            "node_key": normalized_key,
            "node_id": payload.get("node_id"),
            "type_id": payload.get("type_id"),
            "resources": copy.deepcopy(payload.get("resources", {})),
            "updated_at": payload.get("updated_at", time.time()),
        }
        with self.__lock:
            self.__registry_by_node[normalized_key] = record

    def remove_node(self, node_key: Any) -> None:
        normalized_key = self._normalize_node_key(node_key)
        with self.__lock:
            self.__registry_by_node.pop(normalized_key, None)

    def get_snapshot(self) -> Dict[str, Dict[str, Any]]:
        with self.__lock:
            return copy.deepcopy(self.__registry_by_node)

    def get_flat_resources_snapshot(self) -> Dict[str, Dict[str, Any]]:
        """Flatten resources as instance_id -> resource_data enriched with node metadata."""
        flat: Dict[str, Dict[str, Any]] = {}
        with self.__lock:
            for node_key, node_data in self.__registry_by_node.items():
                node_id = node_data.get("node_id")
                type_id = node_data.get("type_id")
                for resource_instance_id, resource in (node_data.get("resources") or {}).items():
                    item = copy.deepcopy(resource) if isinstance(resource, dict) else {"value": resource}
                    item["instance_id"] = resource_instance_id
                    item["node_key"] = node_key
                    item["node_id"] = node_id
                    item["node_type_id"] = type_id
                    flat[f"{node_key}/{resource_instance_id}"] = item
        return flat
