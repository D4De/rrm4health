from enum import Enum

class MessageTypes(str, Enum):
    # GUI -> RRMGlobal
    GUI_REGISTER = "GUI.Register"
    GUI_START_APPLICATION = "GUI.StartApplication"
    GUI_STOP_APPLICATION = "GUI.StopApplication"
    GUI_LIST_POLICIES = "GUI.ListPolicies"
    GUI_SET_POLICY = "GUI.SetPolicy"
    GUI_LIST_APPLICATIONS = "GUI.ListApplications"
    GUI_LIST_NODES_STATUS = "GUI.ListNodesStatus"
    GUI_LIST_RESOURCES_STATUS = "GUI.ListResourcesStatus"
    # new message to list all available application descriptors (not just running apps)
    GUI_LIST_AVAILABLE_APPLICATIONS = "GUI.ListAvailableApplications"

    # RRMGlobal -> GUI

    # RRMGlobal -> GUI
    GLOBAL_REGISTER_RESPONSE = "Global.RegisterResponse"
    GLOBAL_START_APPLICATION_RESPONSE = "Global.StartApplicationResponse"
    GLOBAL_STOP_APPLICATION_RESPONSE = "Global.StopApplicationResponse"
    GLOBAL_LIST_POLICIES_RESPONSE = "Global.ListPoliciesResponse"
    GLOBAL_SET_POLICY_RESPONSE = "Global.SetPolicyResponse"
    GLOBAL_LIST_APPLICATIONS_RESPONSE = "Global.ListApplicationsResponse"
    GLOBAL_LIST_NODES_STATUS_RESPONSE = "Global.ListNodesStatusResponse"
    GLOBAL_LIST_RESOURCES_STATUS_RESPONSE = "Global.ListResourcesStatusResponse"
    # response containing the list of descriptors (name + manifest)
    GLOBAL_LIST_AVAILABLE_APPLICATIONS_RESPONSE = "Global.ListAvailableApplicationsResponse"
    GLOBAL_GUI_NOTIFICATION = "Global.GuiNotification"
    GLOBAL_SHUTDOWN = "Global.Shutdown"

    # RRMLocal -> RRMGlobal
    LOCAL_CONNECT = "Local.Connect"
    LOCAL_CAPABILITIES = "Local.Capabilities"
    LOCAL_STATUS = "Local.Status"
    LOCAL_APPLICATION_DISCONNECTED = "Local.ApplicationDisconnected"
    LOCAL_PARTITION_CONFIGURED = "Local.PartitionConfigured"
    LOCAL_SHUTDOWN = "Local.Shutdown"
    LOCAL_BOARD_INFO = "Local.BoardInfo"
    LOCAL_RESOURCES_SYNC = "Local.ResourcesSync"
    LOCAL_GUI_NOTIFICATION = "Local.GuiNotification"

    # RRMGlobal -> RRMLocal
    GLOBAL_CONNECT_RESPONSE = "Global.ConnectResponse"
    GLOBAL_REQUEST_CAPABILITIES = "Global.RequestCapabilities"
    GLOBAL_REQUEST_STATUS = "Global.RequestStatus"
    GLOBAL_UPDATE_DEVICE_PERFORMANCE = "Global.UpdateDevicePerformance"
    GLOBAL_START_PARTITION = "Global.StartPartition"
    GLOBAL_STOP_PARTITION = "Global.StopPartition"
    GLOBAL_SET_POLICY = "Global.SetPolicy"
