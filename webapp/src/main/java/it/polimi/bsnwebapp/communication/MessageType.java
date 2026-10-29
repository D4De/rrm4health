package it.polimi.bsnwebapp.communication;

import java.util.HashMap;
import java.util.Map;

/**
 * Enumerazione delle stringhe di tipo messaggio utilizzate tra GUI e RRM.
 * Corrisponde a MessageTypes.py.
 */
public enum MessageType {
    // GUI -> RRMGlobal
    GUI_REGISTER("GUI.Register"),
    GUI_START_APPLICATION("GUI.StartApplication"),
    GUI_STOP_APPLICATION("GUI.StopApplication"),
    GUI_LIST_POLICIES("GUI.ListPolicies"),
    GUI_SET_POLICY("GUI.SetPolicy"),
    GUI_LIST_APPLICATIONS("GUI.ListApplications"),
    GUI_LIST_AVAILABLE_APPLICATIONS("GUI.ListAvailableApplications"),
    GUI_LIST_RESOURCES_STATUS("GUI.ListResourcesStatus"),
    GUI_LIST_NODES_STATUS("GUI.ListNodesStatus"),

    // RRMGlobal -> GUI
    GLOBAL_REGISTER_RESPONSE("Global.RegisterResponse"),
    GLOBAL_START_APPLICATION_RESPONSE("Global.StartApplicationResponse"),
    GLOBAL_STOP_APPLICATION_RESPONSE("Global.StopApplicationResponse"),
    GLOBAL_LIST_POLICIES_RESPONSE("Global.ListPoliciesResponse"),
    GLOBAL_SET_POLICY_RESPONSE("Global.SetPolicyResponse"),
    GLOBAL_LIST_APPLICATIONS_RESPONSE("Global.ListApplicationsResponse"),
    GLOBAL_LIST_AVAILABLE_APPLICATIONS_RESPONSE("Global.ListAvailableApplicationsResponse"),
    GLOBAL_LIST_RESOURCES_STATUS_RESPONSE("Global.ListResourcesStatusResponse"),
    GLOBAL_LIST_NODES_STATUS_RESPONSE("Global.ListNodesStatusResponse"),
    GLOBAL_GUI_NOTIFICATION("Global.GuiNotification"),
    GLOBAL_SHUTDOWN("Global.Shutdown");

    private final String value;
    private static final Map<String, MessageType> LOOKUP = new HashMap<>();

    static {
        for (MessageType mt : MessageType.values()) {
            LOOKUP.put(mt.value, mt);
        }
    }

    MessageType(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }

    public static MessageType fromString(String s) {
        return LOOKUP.get(s);
    }
}
