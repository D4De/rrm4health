package it.polimi.bsnwebapp.Config;

/**
 * Configurazione MQTT runtime salvata su file esterno.
 * Usa gli stessi campi di app.mqtt.* per poter essere modificata anche da script.
 */
public record MqttRuntimeConfig(
        boolean enabled,
        String broker,
        String topic,
        String clientId,
        String username,
        String password,
        int qos
) {
}
