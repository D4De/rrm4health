package it.polimi.bsnwebapp.Service;

import java.util.regex.Matcher;
import java.util.regex.Pattern;

import org.springframework.stereotype.Component;

import it.polimi.bsnwebapp.communication.Messages;

/**
 * Traduce i messaggi GUI notification grezzi provenienti da RRM
 * in un payload user-friendly per la Web App.
 */
@Component
public class RrmGuiNotificationMapper {

    private static final Pattern PRECHECK_FAILED_PATTERN = Pattern.compile(
        "PRECHECK_FAILED\\[(?<code>[^\\]]+)]\\s+app='(?<appId>[^']+)'",
        Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern USER_LINKED_PARAMS_DETAILS_PATTERN = Pattern.compile(
        "expected\\s+(?<expected>\\d+)\\s+resources,\\s+got\\s+(?<got>\\d+)\\s+from\\s+parameter\\s+'imunames'",
        Pattern.CASE_INSENSITIVE);
    private static final Pattern USER_LINKED_PARAMS_UNKNOWN_RESOURCE_PATTERN = Pattern.compile(
        "references\\s+unknown\\s+resource\\s+'(?<resource>[^']+)'",
        Pattern.CASE_INSENSITIVE);
    private static final Pattern AUTO_START_TIMEOUT_RUNTIME_PATTERN = Pattern.compile(
        "Auto-start\\s+timeout/runtime\\s+failure\\s+for\\s+app\\s+'(?<appId>[^']+)'",
        Pattern.CASE_INSENSITIVE);
    private static final Pattern APPLICATION_START_TIMEOUT_RUNTIME_PATTERN = Pattern.compile(
        "Application\\s+start\\s+timeout/runtime\\s+failure\\s+for\\s+'(?<appId>[^']+)'",
        Pattern.CASE_INSENSITIVE);
    private static final Pattern APPLICATION_START_FAILED_PATTERN = Pattern.compile(
        "Application\\s+start\\s+failed\\s+for\\s+'(?<appId>[^']+)'\\s*:\\s*(?<reason>.+)",
        Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern INVALID_MANIFEST_SEPARATOR_PATTERN = Pattern.compile(
        "Invalid\\s+manifest\\s+file\\s+for\\s+app\\s+'(?<appId>[^']+)'\\s*:\\s*"
            + "Logical\\s+constraint\\s+error\\s+in\\s+.*?"
            + "Task\\s+'(?<task>[^']+)'\\s+has\\s+ResourceRequest\\s+at\\s+(?<request>\\S+)\\s+"
            + "with\\s+count=(?<count>\\d+),\\s+so\\s+separator\\s+must\\s+be\\s+an\\s+empty\\s+string",
        Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern RRM_GLOBAL_CRITICAL_ERROR_PATTERN = Pattern.compile(
        "Critical\\s+error\\s+in\\s+RRM\\s+Global\\s+loop:",
        Pattern.CASE_INSENSITIVE);
    private static final Pattern NODE_SHUTDOWN_DISCONNECT_PATTERN = Pattern.compile(
        "Node\\s+(?<nodeId>.+?)\\s+sent\\s+shutdown/disconnect\\s+notification",
        Pattern.CASE_INSENSITIVE);
    private static final Pattern APPLICATION_STOPPED_AUTONOMOUSLY_ON_NODE_PATTERN = Pattern.compile(
        "Application\\s+(?<appId>.+?)\\s+stopped\\s+autonomously\\s+on\\s+node\\s+(?<nodeId>.+)",
        Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern APPLICATION_DISCONNECTED_ON_NODE_PATTERN = Pattern.compile(
        "Application\\s+(?<appId>.+?)\\s+disconnected\\s+on\\s+node\\s+(?<nodeId>.+)",
        Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern TUPLE_FIRST_VALUE_PATTERN = Pattern.compile(
        "^\\(?\\s*['\"]?(?<value>[^,'\")]+)['\"]?\\s*,.*\\)?$");

    public Messages.GlobalGuiNotification toWebNotification(Messages.GlobalGuiNotification raw) {
        if (raw == null) {
            return new Messages.GlobalGuiNotification(
                "Notifica RRM senza contenuto.",
                "info",
                "generic",
                "",
                ""
            );
        }

        String severity = normalizeSeverity(raw.severity);
        String message = mapMessage(raw.message, raw.appID);
        String category = normalizeCategory(raw.category);

        return new Messages.GlobalGuiNotification(
            message,
            severity,
            category,
            raw.appID == null ? "" : raw.appID,
            raw.nodeID == null ? "" : raw.nodeID
        );
    }

    private String normalizeSeverity(String severity) {
        String value = severity == null ? "info" : severity.trim().toLowerCase();
        if ("error".equals(value) || "warning".equals(value) || "info".equals(value)) {
            return value;
        }
        return "info";
    }

    private String normalizeCategory(String category) {
        if (category == null || category.isBlank()) {
            return "generic";
        }
        return category;
    }

    private String mapMessage(String rawMessage, String fallbackAppId) {
        if (rawMessage == null || rawMessage.isBlank()) {
            return "Notifica RRM senza contenuto.";
        }

        String normalized = rawMessage.trim();
        String precheckMessage = mapPrecheckMessage(normalized, fallbackAppId);
        if (precheckMessage != null) {
            return precheckMessage;
        }

        String autoStartMessage = mapAutoStartTimeoutRuntimeMessage(normalized);
        if (autoStartMessage != null) {
            return autoStartMessage;
        }

        String applicationStartFailedMessage = mapApplicationStartFailedMessage(normalized);
        if (applicationStartFailedMessage != null) {
            return applicationStartFailedMessage;
        }

        String applicationStartMessage = mapApplicationStartTimeoutRuntimeMessage(normalized);
        if (applicationStartMessage != null) {
            return applicationStartMessage;
        }

        String rrmCriticalMessage = mapRrmGlobalCriticalErrorMessage(normalized);
        if (rrmCriticalMessage != null) {
            return rrmCriticalMessage;
        }

        String nodeShutdownMessage = mapNodeShutdownDisconnectMessage(normalized);
        if (nodeShutdownMessage != null) {
            return nodeShutdownMessage;
        }

        String applicationStoppedAutonomouslyMessage = mapApplicationStoppedAutonomouslyOnNodeMessage(normalized);
        if (applicationStoppedAutonomouslyMessage != null) {
            return applicationStoppedAutonomouslyMessage;
        }

        String applicationDisconnectedMessage = mapApplicationDisconnectedOnNodeMessage(normalized);
        if (applicationDisconnectedMessage != null) {
            return applicationDisconnectedMessage;
        }

        return normalized;
    }

    private String mapAutoStartTimeoutRuntimeMessage(String message) {
        Matcher matcher = AUTO_START_TIMEOUT_RUNTIME_PATTERN.matcher(message);
        if (!matcher.find()) {
            return null;
        }

        String appId = matcher.group("appId");
        if (appId == null || appId.isBlank()) {
            appId = "sconosciuta";
        }

        return "L'applicazione " + appId + " non e partita automaticamente a causa di timeout/errore runtime.";
    }

    private String mapApplicationStartTimeoutRuntimeMessage(String message) {
        Matcher matcher = APPLICATION_START_TIMEOUT_RUNTIME_PATTERN.matcher(message);
        if (!matcher.find()) {
            return null;
        }

        String appId = matcher.group("appId");
        if (appId == null || appId.isBlank()) {
            appId = "sconosciuta";
        }

        return "Applicazione " + appId + " non partita per timeout/errore runtime!";
    }

    private String mapApplicationStartFailedMessage(String message) {
        Matcher matcher = APPLICATION_START_FAILED_PATTERN.matcher(message);
        if (!matcher.find()) {
            return null;
        }

        String appId = matcher.group("appId");
        if (appId == null || appId.isBlank()) {
            appId = "sconosciuta";
        }

        String reason = matcher.group("reason");
        if (reason != null) {
            Matcher invalidManifestMatcher = INVALID_MANIFEST_SEPARATOR_PATTERN.matcher(reason);
            if (invalidManifestMatcher.find()) {
                String task = invalidManifestMatcher.group("task");
                String request = invalidManifestMatcher.group("request");
                String count = invalidManifestMatcher.group("count");
                return "Avvio Fallito: manifest non valido per " + appId
                    + ". Nel task " + task + " la richiesta " + request
                    + " ha count=" + count + ". Separator non settato correttamente.";
            }
        }

        return "Avvio Fallito: applicazione " + appId + " non partita.";
    }

    private String mapRrmGlobalCriticalErrorMessage(String message) {
        Matcher matcher = RRM_GLOBAL_CRITICAL_ERROR_PATTERN.matcher(message);
        if (!matcher.find()) {
            return null;
        }
        return "Errore nell'RRM Global, sistema offline!";
    }

    private String mapNodeShutdownDisconnectMessage(String message) {
        Matcher matcher = NODE_SHUTDOWN_DISCONNECT_PATTERN.matcher(message);
        if (!matcher.find()) {
            return null;
        }
        return "Un nodo locale si e disconesso!";
    }

    private String mapApplicationStoppedAutonomouslyOnNodeMessage(String message) {
        Matcher matcher = APPLICATION_STOPPED_AUTONOMOUSLY_ON_NODE_PATTERN.matcher(message);
        if (!matcher.find()) {
            return null;
        }

        String appId = cleanNotificationEntity(matcher.group("appId"));
        if (appId == null || appId.isBlank()) {
            appId = "sconosciuta";
        }

        return "Applicazione " + appId + " chiusa autonomamente!";
    }

    private String mapApplicationDisconnectedOnNodeMessage(String message) {
        Matcher matcher = APPLICATION_DISCONNECTED_ON_NODE_PATTERN.matcher(message);
        if (!matcher.find()) {
            return null;
        }

        String appId = cleanNotificationEntity(matcher.group("appId"));
        if (appId == null || appId.isBlank()) {
            appId = "sconosciuta";
        }

        return "Applicazione " + appId + " chiusa!";
    }

    private String cleanNotificationEntity(String value) {
        if (value == null) {
            return null;
        }

        String cleaned = value.trim();
        while ((cleaned.startsWith("\"") && !cleaned.endsWith("\""))
                || (cleaned.startsWith("'") && !cleaned.endsWith("'"))) {
            cleaned = cleaned.substring(1).trim();
        }
        if ((cleaned.startsWith("\"") && cleaned.endsWith("\""))
                || (cleaned.startsWith("'") && cleaned.endsWith("'"))) {
            cleaned = cleaned.substring(1, cleaned.length() - 1).trim();
        }

        Matcher tupleMatcher = TUPLE_FIRST_VALUE_PATTERN.matcher(cleaned);
        if (tupleMatcher.matches()) {
            return tupleMatcher.group("value").trim();
        }
        return cleaned;
    }

    private String mapPrecheckMessage(String status, String fallbackAppId) {
        Matcher precheckMatcher = PRECHECK_FAILED_PATTERN.matcher(status);
        if (!precheckMatcher.find()) {
            return null;
        }

        String code = precheckMatcher.group("code");
        if (code == null || !"USER_LINKED_PARAMS".equalsIgnoreCase(code.trim())) {
            return null;
        }

        Matcher detailsMatcher = USER_LINKED_PARAMS_DETAILS_PATTERN.matcher(status);
        if (detailsMatcher.find()) {
            String expected = detailsMatcher.group("expected");
            String got = detailsMatcher.group("got");
            String appId = precheckMatcher.group("appId");
            if (appId == null || appId.isBlank()) {
                appId = fallbackAppId;
            }
            if (appId == null || appId.isBlank()) {
                appId = "sconosciuta";
            }
            return "Avvio Fallito: L'applicazione " + appId + " richiede " + expected
                + " sensori ma ne sono stati selezionati " + got + ".";
        }

        Matcher unknownResourceMatcher = USER_LINKED_PARAMS_UNKNOWN_RESOURCE_PATTERN.matcher(status);
        if (unknownResourceMatcher.find()) {
            String resource = unknownResourceMatcher.group("resource");
            if (resource != null && !resource.isBlank()) {
                return "Avvio Fallito: Sensore " + resource + " non riconosciuto.";
            }
        }

        return null;
    }

    public boolean matchesNodeShutdownDisconnectNotification(String rawMessage) {
        if (rawMessage == null || rawMessage.isBlank()) {
            return false;
        }
        return NODE_SHUTDOWN_DISCONNECT_PATTERN.matcher(rawMessage.trim()).find();
    }
}
