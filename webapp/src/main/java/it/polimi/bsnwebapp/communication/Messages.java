package it.polimi.bsnwebapp.communication;

import java.util.List;
import java.util.Map;

/**
 * Raggruppa tutte le classi concrete dei messaggi usati dalla GUI <-> RRM
 * e fornisce una factory per costruirli dalle mappe ricevute.
 */
public class Messages {

    public static record GUIListPolicies() implements Message {
        @Override public MessageType getType() { return MessageType.GUI_LIST_POLICIES; }
        @Override public Map<String,Object> toMap() { return Map.of("type", getType().getValue()); }
    }

    public static record GUIListApplications() implements Message {
        @Override public MessageType getType() { return MessageType.GUI_LIST_APPLICATIONS; }
        @Override public Map<String,Object> toMap() { return Map.of("type", getType().getValue()); }
    }

    /**
     * Ask RRM for the list of available application descriptors (manifests).
     */
    public static record GUIListAvailableApplications() implements Message {
        @Override public MessageType getType() { return MessageType.GUI_LIST_AVAILABLE_APPLICATIONS; }
        @Override public Map<String,Object> toMap() { return Map.of("type", getType().getValue()); }
    }

    /**
     * Ask RRM for the list of resources and their runtime status.
     */
    public static record GUIListResourcesStatus(String source) implements Message {
        public GUIListResourcesStatus() { this("GUI"); }
        @Override public MessageType getType() { return MessageType.GUI_LIST_RESOURCES_STATUS; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "source", source);
        }
    }

    /**
     * Ask RRM for the list of nodes and their runtime status.
     */
    public static record GUIListNodesStatus(String source) implements Message {
        public GUIListNodesStatus() { this("GUI"); }
        @Override public MessageType getType() { return MessageType.GUI_LIST_NODES_STATUS; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "source", source);
        }
    }

    // --- GUI -> RRM messages that include payloads ---
    public static record GUIRegister(String source) implements Message {
        public GUIRegister() { this("GUI"); }
        @Override public MessageType getType() { return MessageType.GUI_REGISTER; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "source", source);
        }
    }

    public static record GUIStartApplication(String appID, Map<String,Object> args, String source) implements Message {
        public GUIStartApplication(String appID, Map<String,Object> args) {
            this(appID, args == null ? Map.of() : args, "GUI");
        }
        @Override public MessageType getType() { return MessageType.GUI_START_APPLICATION; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "appID", appID,
                          "args", args,
                          "source", source);
        }
    }

    public static record GUIStopApplication(String appID, String source) implements Message {
        public GUIStopApplication(String appID) { this(appID, "GUI"); }
        @Override public MessageType getType() { return MessageType.GUI_STOP_APPLICATION; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "appID", appID,
                          "source", source);
        }
    }

    public static record GUISetPolicy(String policy_name, String source) implements Message {
        public GUISetPolicy(String policy_name) { this(policy_name, "GUI"); }
        @Override public MessageType getType() { return MessageType.GUI_SET_POLICY; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "policy_name", policy_name,
                          "source", source);
        }
    }

    // --- responses from RRMGlobal ---
    public static class GlobalRegisterResponse implements Message {
        public String status;
        public String current_policy;
        public GlobalRegisterResponse() {}
        public GlobalRegisterResponse(String status, String current_policy) {
            this.status = status; this.current_policy = current_policy;
        }
        @Override public MessageType getType() { return MessageType.GLOBAL_REGISTER_RESPONSE; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "status", status,
                          "current_policy", current_policy);
        }
    }

    public static class GlobalListPoliciesResponse implements Message {
        public List<String> policy_list;
        public GlobalListPoliciesResponse() {}
        public GlobalListPoliciesResponse(List<String> policy_list) { this.policy_list = policy_list; }
        @Override public MessageType getType() { return MessageType.GLOBAL_LIST_POLICIES_RESPONSE; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(), "policy_list", policy_list);
        }
    }

    public static class GlobalListApplicationsResponse implements Message {
        public List<Map<String,Object>> applications;
        public GlobalListApplicationsResponse() {}
        public GlobalListApplicationsResponse(List<Map<String,Object>> apps) { this.applications = apps; }
        @Override public MessageType getType() { return MessageType.GLOBAL_LIST_APPLICATIONS_RESPONSE; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(), "applications", applications);
        }
    }

    /**
     * Response containing the available descriptors (each entry is a map with
     * "appID" and "manifest" keys mirroring the Python implementation).
     */
    public static class GlobalListAvailableApplicationsResponse implements Message {
        public List<Map<String,Object>> descriptors;
        public GlobalListAvailableApplicationsResponse() {}
        public GlobalListAvailableApplicationsResponse(List<Map<String,Object>> list) { this.descriptors = list; }
        @Override public MessageType getType() { return MessageType.GLOBAL_LIST_AVAILABLE_APPLICATIONS_RESPONSE; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(), "descriptors", descriptors);
        }
    }

    /**
     * Response containing resources currently known by RRM and their status.
     */
    public static class GlobalListResourcesStatusResponse implements Message {
        public List<Map<String,Object>> resources;
        public Integer count;
        public GlobalListResourcesStatusResponse() {}
        public GlobalListResourcesStatusResponse(List<Map<String,Object>> resources, Integer count) {
            this.resources = resources;
            this.count = count;
        }
        @Override public MessageType getType() { return MessageType.GLOBAL_LIST_RESOURCES_STATUS_RESPONSE; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "resources", resources,
                          "count", count);
        }
    }

    /**
     * Response containing nodes currently known by RRM and their status.
     */
    public static class GlobalListNodesStatusResponse implements Message {
        public List<Map<String,Object>> nodes;
        public Integer count;
        public GlobalListNodesStatusResponse() {}
        public GlobalListNodesStatusResponse(List<Map<String,Object>> nodes, Integer count) {
            this.nodes = nodes;
            this.count = count;
        }
        @Override public MessageType getType() { return MessageType.GLOBAL_LIST_NODES_STATUS_RESPONSE; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "nodes", nodes,
                          "count", count);
        }
    }

    /**
     * Asynchronous notification sent by the framework to connected GUIs.
     */
    public static class GlobalGuiNotification implements Message {
        public String message;
        public String severity;
        public String category;
        public String appID;
        public String nodeID;

        public GlobalGuiNotification() {}

        public GlobalGuiNotification(String message, String severity, String category, String appID, String nodeID) {
            this.message = message;
            this.severity = severity;
            this.category = category;
            this.appID = appID;
            this.nodeID = nodeID;
        }

        @Override public MessageType getType() { return MessageType.GLOBAL_GUI_NOTIFICATION; }
        @Override public Map<String,Object> toMap() {
            return Map.of(
                "type", getType().getValue(),
                "message", message == null ? "" : message,
                "severity", severity == null ? "info" : severity,
                "category", category == null ? "generic" : category,
                "appID", appID == null ? "" : appID,
                "nodeID", nodeID == null ? "" : nodeID
            );
        }
    }

    public static class GlobalStartApplicationResponse implements Message {
        public String appID;
        public String status;
        public GlobalStartApplicationResponse() {}
        public GlobalStartApplicationResponse(String appID, String status) {
            this.appID = appID;
            this.status = status;
        }
        @Override public MessageType getType() { return MessageType.GLOBAL_START_APPLICATION_RESPONSE; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "appID", appID,
                          "status", status);
        }
    }

    public static class GlobalStopApplicationResponse implements Message {
        public String appID;
        public String status;
        public GlobalStopApplicationResponse() {}
        public GlobalStopApplicationResponse(String appID, String status) {
            this.appID = appID;
            this.status = status;
        }
        @Override public MessageType getType() { return MessageType.GLOBAL_STOP_APPLICATION_RESPONSE; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "appID", appID,
                          "status", status);
        }
    }

    public static class GlobalSetPolicyResponse implements Message {
        public String status;
        public GlobalSetPolicyResponse() {}
        public GlobalSetPolicyResponse(String status) { this.status = status; }
        @Override public MessageType getType() { return MessageType.GLOBAL_SET_POLICY_RESPONSE; }
        @Override public Map<String,Object> toMap() {
            return Map.of("type", getType().getValue(),
                          "status", status);
        }
    }

    public static class GlobalShutdown implements Message {
        @Override public MessageType getType() { return MessageType.GLOBAL_SHUTDOWN; }
        @Override public Map<String,Object> toMap() { return Map.of("type", getType().getValue()); }
    }

    // add more classes as needed

    /**
     * Trasforma una mappa JSON in un oggetto Message concreto.
     * Restituisce null se il tipo non è riconosciuto.
     */
    @SuppressWarnings("unchecked")
    public static Message fromMap(Map<String,Object> m) {
        if (m == null) return null;
        Object t = m.get("type");
        if (t == null) return null;
        MessageType mt = MessageType.fromString(t.toString());
        if (mt == null) return null;
        switch(mt) {
            /* --- requests coming from GUI --- */
            case GUI_REGISTER -> {
                String source = (String) m.get("source");
                return new GUIRegister(source != null ? source : "GUI");
            }
            case GUI_START_APPLICATION -> {
                String appID = (String) m.get("appID");
                Map<String,Object> args = (Map<String,Object>) m.get("args");
                String source = (String) m.get("source");
                return new GUIStartApplication(appID, args, source != null ? source : "GUI");
            }
            case GUI_STOP_APPLICATION -> {
                String appID = (String) m.get("appID");
                String source = (String) m.get("source");
                return new GUIStopApplication(appID, source != null ? source : "GUI");
            }
            case GUI_SET_POLICY -> {
                String policy = (String) m.get("policy_name");
                String source = (String) m.get("source");
                return new GUISetPolicy(policy, source != null ? source : "GUI");
            }
            case GUI_LIST_AVAILABLE_APPLICATIONS -> {
                return new GUIListAvailableApplications();
            }
            case GUI_LIST_RESOURCES_STATUS -> {
                String source = (String) m.get("source");
                return new GUIListResourcesStatus(source != null ? source : "GUI");
            }
            case GUI_LIST_NODES_STATUS -> {
                String source = (String) m.get("source");
                return new GUIListNodesStatus(source != null ? source : "GUI");
            }

            /* --- responses from RRMGlobal --- */
            case GLOBAL_REGISTER_RESPONSE -> {
                String status = (String) m.get("status");
                String cp = (String) m.get("current_policy");
                return new GlobalRegisterResponse(status, cp);
            }
            case GLOBAL_START_APPLICATION_RESPONSE -> {
                String appID = (String) m.get("appID");
                String status = (String) m.get("status");
                return new GlobalStartApplicationResponse(appID, status);
            }
            case GLOBAL_STOP_APPLICATION_RESPONSE -> {
                String appID = (String) m.get("appID");
                String status = (String) m.get("status");
                return new GlobalStopApplicationResponse(appID, status);
            }
            case GLOBAL_LIST_POLICIES_RESPONSE -> {
                List<String> list = (List<String>) m.get("policy_list");
                return new GlobalListPoliciesResponse(list);
            }
            case GLOBAL_SET_POLICY_RESPONSE -> {
                String status = (String) m.get("status");
                return new GlobalSetPolicyResponse(status);
            }
            case GLOBAL_LIST_APPLICATIONS_RESPONSE -> {
                List<Map<String,Object>> list = (List<Map<String,Object>>) m.get("applications");
                return new GlobalListApplicationsResponse(list);
            }
            case GLOBAL_LIST_AVAILABLE_APPLICATIONS_RESPONSE -> {
                List<Map<String,Object>> list = (List<Map<String,Object>>) m.get("descriptors");
                return new GlobalListAvailableApplicationsResponse(list);
            }
            case GLOBAL_LIST_RESOURCES_STATUS_RESPONSE -> {
                List<Map<String,Object>> resources = (List<Map<String,Object>>) m.get("resources");
                Integer count = null;
                Object rawCount = m.get("count");
                if (rawCount instanceof Number n) {
                    count = n.intValue();
                }
                return new GlobalListResourcesStatusResponse(resources, count);
            }
            case GLOBAL_LIST_NODES_STATUS_RESPONSE -> {
                List<Map<String,Object>> nodes = (List<Map<String,Object>>) m.get("nodes");
                Integer count = null;
                Object rawCount = m.get("count");
                if (rawCount instanceof Number n) {
                    count = n.intValue();
                }
                return new GlobalListNodesStatusResponse(nodes, count);
            }
            case GLOBAL_GUI_NOTIFICATION -> {
                String message = (String) m.get("message");
                String severity = (String) m.get("severity");
                String category = (String) m.get("category");
                String appID = (String) m.get("appID");
                String nodeID = (String) m.get("nodeID");
                return new GlobalGuiNotification(
                    message == null ? "" : message,
                    severity == null ? "info" : severity,
                    category == null ? "generic" : category,
                    appID == null ? "" : appID,
                    nodeID == null ? "" : nodeID
                );
            }
            case GLOBAL_SHUTDOWN -> { return new GlobalShutdown(); }
            default -> { return null; }
        }
    }
}
