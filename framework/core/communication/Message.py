from dataclasses import dataclass, asdict, field
from typing import Any, Dict, List, Tuple
from core.communication.MessageTypes import MessageTypes

@dataclass
class Message:
    type: MessageTypes

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

# GUI -> RRMGlobal
@dataclass
class GUIRegister(Message):
    type: MessageTypes = field(default=MessageTypes.GUI_REGISTER, init=False)
    source: str = "GUI"

@dataclass
class GUIStartApplication(Message):
    appID: str
    args: Dict[str, Any] = field(default_factory=dict) 
    type: MessageTypes = field(default=MessageTypes.GUI_START_APPLICATION, init=False)
    source: str = "GUI"

@dataclass
class GUIStopApplication(Message):
    appID: str
    type: MessageTypes = field(default=MessageTypes.GUI_STOP_APPLICATION, init=False)
    source: str = "GUI"

@dataclass
class GUIListPolicies(Message):
    type: MessageTypes = field(default=MessageTypes.GUI_LIST_POLICIES, init=False)
    source: str = "GUI"

@dataclass
class GUISetPolicy(Message):
    policy_name: str
    type: MessageTypes = field(default=MessageTypes.GUI_SET_POLICY, init=False)
    source: str = "GUI"

@dataclass
class GUIListApplications(Message):
    type: MessageTypes = field(default=MessageTypes.GUI_LIST_APPLICATIONS, init=False)
    source: str = "GUI"

@dataclass
class GUIListNodesStatus(Message):
    type: MessageTypes = field(default=MessageTypes.GUI_LIST_NODES_STATUS, init=False)
    source: str = "GUI"

@dataclass
class GUIListResourcesStatus(Message):
    type: MessageTypes = field(default=MessageTypes.GUI_LIST_RESOURCES_STATUS, init=False)
    source: str = "GUI"

@dataclass
class GUIListAvailableApplications(Message):
    """Request the list of all applications defined in the descriptors folder."""
    type: MessageTypes = field(default=MessageTypes.GUI_LIST_AVAILABLE_APPLICATIONS, init=False)
    source: str = "GUI"

# RRMGlobal -> GUI
@dataclass
class GlobalRegisterResponse(Message):
    status: str = "OK"
    current_policy: str = ""
    type: MessageTypes = field(default=MessageTypes.GLOBAL_REGISTER_RESPONSE, init=False)

@dataclass
class GlobalStartApplicationResponse(Message):
    appID: str
    status: str = "OK"
    type: MessageTypes = field(default=MessageTypes.GLOBAL_START_APPLICATION_RESPONSE, init=False)

@dataclass
class GlobalStopApplicationResponse(Message):
    appID: str
    status: str = "OK"
    type: MessageTypes = field(default=MessageTypes.GLOBAL_STOP_APPLICATION_RESPONSE, init=False)

@dataclass
class GlobalListPoliciesResponse(Message):
    policy_list: List[str]
    type: MessageTypes = field(default=MessageTypes.GLOBAL_LIST_POLICIES_RESPONSE, init=False)

@dataclass
class GlobalSetPolicyResponse(Message):
    status: str = "OK"
    type: MessageTypes = field(default=MessageTypes.GLOBAL_SET_POLICY_RESPONSE, init=False)

@dataclass
class GlobalListApplicationsResponse(Message):
    applications: List[Dict[str, Any]]
    type: MessageTypes = field(default=MessageTypes.GLOBAL_LIST_APPLICATIONS_RESPONSE, init=False)

@dataclass
class GlobalListNodesStatusResponse(Message):
    nodes: List[Dict[str, Any]]
    count: int = 0
    type: MessageTypes = field(default=MessageTypes.GLOBAL_LIST_NODES_STATUS_RESPONSE, init=False)

@dataclass
class GlobalListResourcesStatusResponse(Message):
    resources: List[Dict[str, Any]]
    count: int = 0
    type: MessageTypes = field(default=MessageTypes.GLOBAL_LIST_RESOURCES_STATUS_RESPONSE, init=False)

@dataclass
class GlobalListAvailableApplicationsResponse(Message):
    """Response carried back to GUI with the parsed manifests of available apps."""
    descriptors: List[Dict[str, Any]]
    type: MessageTypes = field(default=MessageTypes.GLOBAL_LIST_AVAILABLE_APPLICATIONS_RESPONSE, init=False)

@dataclass
class GlobalGuiNotification(Message):
    """Asynchronous notification sent by the framework to connected GUIs."""
    message: str
    severity: str = "info"
    category: str = "generic"
    appID: str = ""
    nodeID: str = ""
    type: MessageTypes = field(default=MessageTypes.GLOBAL_GUI_NOTIFICATION, init=False)

# RRMLocal -> RRMGlobal
@dataclass
class LocalConnect(Message):
    board_info: Dict[str, Any] = field(default_factory=dict)
    type: MessageTypes = field(default=MessageTypes.LOCAL_CONNECT, init=False)

@dataclass
class LocalCapabilities(Message):
    data: Dict[str, Any]
    type: MessageTypes = field(default=MessageTypes.LOCAL_CAPABILITIES, init=False)

@dataclass
class LocalStatus(Message):
    status: Dict[str, Any]
    running_partitions: List[Dict[str, Any]]
    type: MessageTypes = field(default=MessageTypes.LOCAL_STATUS, init=False)

@dataclass
class LocalApplicationDisconnected(Message):
    appID: Tuple[str, int]
    reason: str = ""
    phase: str = ""
    exception_type: str = ""
    exception_text: str = ""
    traceback_text: str = ""
    type: MessageTypes = field(default=MessageTypes.LOCAL_APPLICATION_DISCONNECTED, init=False)

@dataclass
class LocalPartitionConfigured(Message):
    appID: str = ""
    partitionID: str = ""
    type: MessageTypes = field(default=MessageTypes.LOCAL_PARTITION_CONFIGURED, init=False)

@dataclass
class LocalShutdown(Message):
    type: MessageTypes = field(default=MessageTypes.LOCAL_SHUTDOWN, init=False)

@dataclass
class LocalBoardInfo(Message):
    board_info: Dict[str, Any]
    type: MessageTypes = field(default=MessageTypes.LOCAL_BOARD_INFO, init=False)

@dataclass
class LocalResourcesSync(Message):
    node_id: str
    type_id: str
    resources: Dict[str, Any]
    updated_at: float
    update_reason: str = ""
    type: MessageTypes = field(default=MessageTypes.LOCAL_RESOURCES_SYNC, init=False)

@dataclass
class LocalGuiNotification(Message):
    message: str
    severity: str = "info"
    appID: Any = ""
    partitionID: str = ""
    type: MessageTypes = field(default=MessageTypes.LOCAL_GUI_NOTIFICATION, init=False)

# RRMGlobal -> RRMLocal
@dataclass
class GlobalConnectResponse(Message):
    type: MessageTypes = field(default=MessageTypes.GLOBAL_CONNECT_RESPONSE, init=False)

@dataclass
class GlobalRequestCapabilities(Message):
    fields: List[str]
    mode: str = "instant"
    window_seconds: float = 0.0
    sample_interval_seconds: float = 0.5
    type: MessageTypes = field(default=MessageTypes.GLOBAL_REQUEST_CAPABILITIES, init=False)

@dataclass
class GlobalRequestStatus(Message):
    type: MessageTypes = field(default=MessageTypes.GLOBAL_REQUEST_STATUS, init=False)

@dataclass
class GlobalUpdateDevicePerformance(Message):
    data: Dict[str, Any]
    type: MessageTypes = field(default=MessageTypes.GLOBAL_UPDATE_DEVICE_PERFORMANCE, init=False)

@dataclass
class GlobalStartPartition(Message):
    uniqueID: Tuple[Tuple[str, int], str]
    app_id: str
    param: Dict[str, Any]
    type: MessageTypes = field(default=MessageTypes.GLOBAL_START_PARTITION, init=False)

@dataclass
class GlobalStopPartition(Message):
    partitionId: Tuple[Tuple[str, int], str]
    type: MessageTypes = field(default=MessageTypes.GLOBAL_STOP_PARTITION, init=False)

@dataclass
class GlobalSetPolicy(Message):
    policy_name: str
    resources_to_collect: List[str]
    process_resources_to_collect: List[str]
    type: MessageTypes = field(default=MessageTypes.GLOBAL_SET_POLICY, init=False)

@dataclass
class GlobalShutdown(Message):
    type: MessageTypes = field(default=MessageTypes.GLOBAL_SHUTDOWN, init=False)
    
_message_classes: Dict[MessageTypes, type[Message]] = {}

# Dynamically populate _message_classes and ensure completeness
for name, cls in list(globals().items()):
    if isinstance(cls, type) and issubclass(cls, Message) and hasattr(cls, 'type') and cls is not Message:
        _message_classes[cls.type] = cls

# Check for completeness
for msg_type in MessageTypes:
    if msg_type not in _message_classes:
        raise RuntimeError(f"Missing dataclass definition for MessageType: {msg_type.value}")

def message_factory(data: Dict[str, Any]) -> Message:
    message_type_str = data.pop("type", None)
    if not message_type_str:
        raise ValueError("Message data does not contain a 'type' field.")

    try:
        message_type = MessageTypes(message_type_str)
    except ValueError:
        raise ValueError(f"Unknown message type: {message_type_str}")

    message_class = _message_classes.get(message_type)
    if not message_class:
        # This case should ideally be caught by the completeness check at import time
        raise ValueError(f"No message class found for type: {message_type.value}")

    return message_class(**data)
