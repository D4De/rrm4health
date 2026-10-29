package it.polimi.bsnwebapp.Service;

import static org.junit.jupiter.api.Assertions.assertEquals;

import org.junit.jupiter.api.Test;

import it.polimi.bsnwebapp.communication.Messages;

class RrmGuiNotificationMapperTest {

    private final RrmGuiNotificationMapper mapper = new RrmGuiNotificationMapper();

    @Test
    void mapsApplicationDisconnectedNotificationWithTupleIds() {
        Messages.GlobalGuiNotification mapped = mapper.toWebNotification(
                new Messages.GlobalGuiNotification(
                        "Application \"('Collector_BLE', 0) disconnected on node ('10.79.3.195', 47575)\"",
                        "warning",
                        "runtime",
                        "",
                        ""));

        assertEquals("Applicazione Collector_BLE chiusa!", mapped.message);
        assertEquals("warning", mapped.severity);
        assertEquals("runtime", mapped.category);
    }

    @Test
    void mapsApplicationStoppedAutonomouslyNotification() {
        Messages.GlobalGuiNotification mapped = mapper.toWebNotification(
                new Messages.GlobalGuiNotification(
                        "Application Collector_BLE stopped autonomously on node ('10.79.3.195', 47575)",
                        "info",
                        "app_self_stopped",
                        "Collector_BLE",
                        "('10.79.3.195', 47575)"));

        assertEquals("Applicazione Collector_BLE chiusa autonomamente!", mapped.message);
        assertEquals("info", mapped.severity);
        assertEquals("app_self_stopped", mapped.category);
    }

    @Test
    void mapsApplicationStartFailedForInvalidManifestSeparator() {
        Messages.GlobalGuiNotification mapped = mapper.toWebNotification(
                new Messages.GlobalGuiNotification(
                        "Application start failed for 'Collector_BLE': Invalid manifest file for app 'Collector_BLE': "
                                + "Logical constraint error in /home/cysko7927/rrm4health/rrm4health/Framework/descriptors/Collector_BLE.json: "
                                + "Task 'setup_and_collect' has ResourceRequest at requires[0] with count=1, "
                                + "so separator must be an empty string. Suggested fix: set separator to ''.",
                        "error",
                        "runtime",
                        "",
                        ""));

        assertEquals("Avvio Fallito: manifest non valido per Collector_BLE. "
                + "Nel task setup_and_collect la richiesta requires[0] ha count=1. "
                + "Separator non settato correttamente.",
                mapped.message);
        assertEquals("error", mapped.severity);
        assertEquals("runtime", mapped.category);
    }
}
