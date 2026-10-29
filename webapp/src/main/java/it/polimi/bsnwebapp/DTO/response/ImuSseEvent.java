package it.polimi.bsnwebapp.DTO.response;

import java.time.Instant;
import java.util.Map;

/**
 * Record di risposta per eventi SSE derivati da messaggi MQTT.
 * Contiene tipo evento, imuid, cname, mappa valori decodificata, topic e timestamp di ricezione.
 * Usato da MqttSseService per inviare dati real time al frontend.
 */

public record ImuSseEvent(
        String type,
        String imuid,
        String cname,
        Long campaignId,
        Map<String, Object> values,
        String topic,
        Instant receivedAt
) {
}
