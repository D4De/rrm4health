import copy
import logging
import threading
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

import core.Utils as Utils

logger = logging.getLogger(__name__)


class LocationEventType(str, Enum):
    NODE_LOCATION_UPDATED = "node_location_updated"
    NODE_LOCATION_REMOVED = "node_location_removed"
    PERIPHERAL_LOCATION_UPDATED = "peripheral_location_updated"
    PERIPHERAL_LOCATION_REMOVED = "peripheral_location_removed"
    PERIPHERAL_USAGE_UPDATED = "peripheral_usage_updated"


@dataclass(frozen=True)
class LocationEvent:
    event_type: LocationEventType
    node_id: str
    peripheral_id: Optional[str] = None
    location: Optional[Dict[str, Any]] = None
    in_use: Optional[bool] = None
    source: str = "local_update"
    updated_at: float = 0.0


class LocationManager:
    """Event-driven location state manager for nodes and peripherals.

    This class is intentionally lightweight and provides only the skeleton needed
    to integrate dynamic location updates from RRMLocal into RRMGlobal.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._node_locations: Dict[str, Dict[str, Any]] = {}
        self._peripheral_locations: Dict[str, Dict[str, Dict[str, Any]]] = {}
        self._event_backlog: List[LocationEvent] = []
        self._subscribers: List[Callable[[LocationEvent], None]] = []

    def subscribe(self, callback: Callable[[LocationEvent], None]) -> None:
        with self._lock:
            self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[LocationEvent], None]) -> None:
        with self._lock:
            self._subscribers = [cb for cb in self._subscribers if cb is not callback]

    def update_node_location(self, node_id: str, location: Dict[str, Any], source: str = "local_update") -> None:
        if not node_id:
            return

        normalized = self._normalize_location(location)
        event = LocationEvent(
            event_type=LocationEventType.NODE_LOCATION_UPDATED,
            node_id=node_id,
            location=normalized,
            source=source,
            updated_at=time.time(),
        )

        with self._lock:
            self._node_locations[node_id] = normalized
            self._event_backlog.append(event)
            subscribers = list(self._subscribers)

        self._notify_subscribers(subscribers, event)

    def update_peripheral_location(
        self,
        node_id: str,
        peripheral_id: str,
        location: Dict[str, Any],
        in_use: Optional[bool] = None,
        source: str = "local_update",
    ) -> None:
        if not node_id or not peripheral_id:
            return

        normalized = self._normalize_location(location)
        event = LocationEvent(
            event_type=LocationEventType.PERIPHERAL_LOCATION_UPDATED,
            node_id=node_id,
            peripheral_id=peripheral_id,
            location=normalized,
            in_use=in_use,
            source=source,
            updated_at=time.time(),
        )

        with self._lock:
            node_peripherals = self._peripheral_locations.setdefault(node_id, {})
            payload = node_peripherals.setdefault(peripheral_id, {})
            payload["location"] = normalized
            if in_use is not None:
                payload["in_use"] = bool(in_use)
            payload["updated_at"] = event.updated_at
            payload["source"] = source

            self._event_backlog.append(event)
            subscribers = list(self._subscribers)

        self._notify_subscribers(subscribers, event)

    def set_peripheral_in_use(self, node_id: str, peripheral_id: str, in_use: bool, source: str = "local_usage") -> None:
        if not node_id or not peripheral_id:
            return

        event = LocationEvent(
            event_type=LocationEventType.PERIPHERAL_USAGE_UPDATED,
            node_id=node_id,
            peripheral_id=peripheral_id,
            in_use=bool(in_use),
            source=source,
            updated_at=time.time(),
        )

        with self._lock:
            node_peripherals = self._peripheral_locations.setdefault(node_id, {})
            payload = node_peripherals.setdefault(peripheral_id, {})
            payload["in_use"] = bool(in_use)
            payload["updated_at"] = event.updated_at
            payload["source"] = source

            self._event_backlog.append(event)
            subscribers = list(self._subscribers)

        self._notify_subscribers(subscribers, event)

    def remove_node(self, node_id: str, source: str = "system") -> None:
        if not node_id:
            return

        event = LocationEvent(
            event_type=LocationEventType.NODE_LOCATION_REMOVED,
            node_id=node_id,
            source=source,
            updated_at=time.time(),
        )

        with self._lock:
            self._node_locations.pop(node_id, None)
            self._peripheral_locations.pop(node_id, None)
            self._event_backlog.append(event)
            subscribers = list(self._subscribers)

        self._notify_subscribers(subscribers, event)

    def remove_peripheral(self, node_id: str, peripheral_id: str, source: str = "system") -> None:
        if not node_id or not peripheral_id:
            return

        event = LocationEvent(
            event_type=LocationEventType.PERIPHERAL_LOCATION_REMOVED,
            node_id=node_id,
            peripheral_id=peripheral_id,
            source=source,
            updated_at=time.time(),
        )

        with self._lock:
            node_peripherals = self._peripheral_locations.get(node_id, {})
            node_peripherals.pop(peripheral_id, None)
            if not node_peripherals:
                self._peripheral_locations.pop(node_id, None)

            self._event_backlog.append(event)
            subscribers = list(self._subscribers)

        self._notify_subscribers(subscribers, event)

    def get_node_location(self, node_id: str) -> Dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._node_locations.get(node_id, {}))

    def get_peripheral_location(self, node_id: str, peripheral_id: str) -> Dict[str, Any]:
        with self._lock:
            node_peripherals = self._peripheral_locations.get(node_id, {})
            payload = node_peripherals.get(peripheral_id, {})
            return copy.deepcopy(payload.get("location", {}))

    def get_snapshot(self, only_in_use_peripherals: bool = False) -> Dict[str, Any]:
        with self._lock:
            node_locations = copy.deepcopy(self._node_locations)
            peripheral_locations = copy.deepcopy(self._peripheral_locations)

        if not only_in_use_peripherals:
            return {
                "nodes": node_locations,
                "peripherals": peripheral_locations,
            }

        filtered_peripherals: Dict[str, Dict[str, Dict[str, Any]]] = {}
        for node_id, per_node in peripheral_locations.items():
            selected = {
                periph_id: payload
                for periph_id, payload in per_node.items()
                if bool(payload.get("in_use", False))
            }
            if selected:
                filtered_peripherals[node_id] = selected

        return {
            "nodes": node_locations,
            "peripherals": filtered_peripherals,
        }

    def drain_events(self) -> List[LocationEvent]:
        with self._lock:
            events = list(self._event_backlog)
            self._event_backlog.clear()
            return events

    @staticmethod
    def _normalize_location(location: Dict[str, Any]) -> Dict[str, Any]:
        normalized = Utils.normalize_indoor_location(location)
        return normalized if isinstance(normalized, dict) else {}

    @staticmethod
    def _notify_subscribers(subscribers: List[Callable[[LocationEvent], None]], event: LocationEvent) -> None:
        for callback in subscribers:
            try:
                callback(event)
            except Exception as exc:
                logger.error("Error in location event subscriber: %s", exc)
