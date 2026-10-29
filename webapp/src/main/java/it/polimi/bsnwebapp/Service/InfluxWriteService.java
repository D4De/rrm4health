package it.polimi.bsnwebapp.Service;

import it.polimi.bsnwebapp.DTO.response.ImuSseEvent;
import it.polimi.bsnwebapp.Model.Entities.Campagna;
import it.polimi.bsnwebapp.Repository.CampagnaRepository;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;

/**
 * Service che salva i dati IMU su InfluxDB in base al database selezionato nella campagna.
 * Riceve eventi MQTT gia decodificati, costruisce il line protocol e invia una write HTTP 1.x.
 */
@Service
@RequiredArgsConstructor
public class InfluxWriteService {

    private static final Logger logger = LoggerFactory.getLogger(InfluxWriteService.class);

    private final CampagnaRepository campagnaRepository;
    private final HttpClient httpClient = HttpClient.newHttpClient();

    /**
     * Scrive un evento su InfluxDB usando il DB configurato per la campagna.
     * Se il cname non e' numerico o la campagna non esiste, la scrittura viene ignorata.
     *
     * @param event evento real time decodificato da MQTT
     */
    public void writeEvent(ImuSseEvent event) {
        if (event == null || event.campaignId() == null) {
            return;
        }
        long campaignId = event.campaignId();

        Campagna campagna = campagnaRepository.findById(campaignId).orElse(null);
        if (campagna == null) {
            return;
        }

        String baseUrl = normalizeBaseUrl(campagna.getDbHost());
        String database = normalizeDatabase(campagna.getDbName());
        if (baseUrl.isBlank() || database.isBlank()) {
            logger.warn("Influx write skipped: db non configurato per campagna {}", campaignId);
            return;
        }
        String measurement = resolveMeasurement(event, campaignId);
        if (measurement == null) {
            logger.warn("Influx write skipped: cname mancante per output campagna {}", campaignId);
            return;
        }
        String line = buildLineProtocol(event, measurement);

        if (line == null || line.isBlank()) {
            return;
        }

        try {
            URI uri = URI.create(baseUrl + "/write?db=" + encode(database) + "&precision=ns");
            HttpRequest request = HttpRequest.newBuilder(uri)
                    .POST(HttpRequest.BodyPublishers.ofString(line))
                    .build();
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 300) {
                logger.warn("Influx write failed: status={} body={}", response.statusCode(), response.body());
            }
        } catch (IOException e) {
            logger.warn("Influx write error: {}", e.getMessage());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            logger.warn("Influx write interrupted");
        }
    }

    /**
     * Usa la measurement base per IMU/batteria e una measurement dedicata per ogni output.
     *
     * @param event evento SSE/MQTT
     * @return nome della misura (campaign)
     */
    String resolveMeasurement(ImuSseEvent event, long campaignId) {
        String base = "campaign_" + campaignId;
        if (!"application-data".equals(event.type())) {
            return base;
        }
        if (event.cname() == null || event.cname().isBlank()) {
            return null;
        }
        String safeCname = event.cname().trim().replaceAll("[^A-Za-z0-9_-]+", "_");
        return safeCname.isBlank() ? null : base + "_" + safeCname;
    }

    /**
     * Costruisce il line protocol Influx con tags, campi e timestamp.
     *
     * @param event evento real time
     * @param measurement misura target
     * @return stringa line protocol o null se campi assenti
     */
    private String buildLineProtocol(ImuSseEvent event, String measurement) {
        Map<String, Object> fields = new LinkedHashMap<>();
        if (event.values() != null && !event.values().isEmpty()) {
            if ("application-data".equals(event.type())) {
                fields.put("_field_order", String.join(",", event.values().keySet()));
            }
            fields.putAll(event.values());
        }

        StringBuilder line = new StringBuilder();
        line.append(measurement);

        String tags = buildTags(event);
        if (!tags.isEmpty()) {
            line.append(",").append(tags);
        }

        String fieldSet = buildFieldSet(fields);
        if (fieldSet.isEmpty()) {
            return null;
        }
        line.append(" ").append(fieldSet);

        long timestamp = toNanoTimestamp(event.receivedAt());
        line.append(" ").append(timestamp);
        return line.toString();
    }

    /**
     * Compone i tag standard per il salvataggio (imuid, cname, topic e tipo evento).
     *
     * @param event evento real time
     * @return tag concatenati per line protocol
     */
    private String buildTags(ImuSseEvent event) {
        StringBuilder tags = new StringBuilder();
        appendTag(tags, "imuid", event.imuid());
        appendTag(tags, "cname", event.cname());
        appendTag(tags, "topic", event.topic());
        appendTag(tags, "event_type", event.type());
        return tags.toString();
    }

    /**
     * Aggiunge un tag se il valore e' presente.
     *
     * @param builder accumulatore tag
     * @param key chiave tag
     * @param value valore tag
     */
    private void appendTag(StringBuilder builder, String key, String value) {
        if (value == null || value.isBlank()) {
            return;
        }
        if (!builder.isEmpty()) {
            builder.append(",");
        }
        builder.append(escapeTag(key)).append("=").append(escapeTag(value));
    }

    /**
     * Costruisce la sezione dei campi per il line protocol.
     *
     * @param fields mappa valori grezzi
     * @return stringa campi formattata
     */
    private String buildFieldSet(Map<String, Object> fields) {
        StringBuilder builder = new StringBuilder();
        for (Map.Entry<String, Object> entry : fields.entrySet()) {
            String key = entry.getKey();
            Object value = entry.getValue();
            String fieldValue = formatFieldValue(value);
            if (fieldValue == null) {
                continue;
            }
            if (!builder.isEmpty()) {
                builder.append(",");
            }
            builder.append(escapeFieldKey(key)).append("=").append(fieldValue);
        }
        return builder.toString();
    }

    /**
     * Converte un valore Java in formato field del line protocol.
     *
     * @param value valore grezzo
     * @return stringa formattata o null se non valida
     */
    private String formatFieldValue(Object value) {
        if (value == null) {
            return null;
        }
        if (value instanceof Integer || value instanceof Long || value instanceof Short || value instanceof Byte) {
            return value + "i";
        }
        if (value instanceof Float || value instanceof Double) {
            double v = ((Number) value).doubleValue();
            if (Double.isNaN(v) || Double.isInfinite(v)) {
                return null;
            }
            return Double.toString(v);
        }
        if (value instanceof Boolean) {
            return ((Boolean) value) ? "true" : "false";
        }
        String str = value.toString();
        if (str.isBlank()) {
            return null;
        }
        return "\"" + str.replace("\"", "\\\"") + "\"";
    }

    /**
     * Escapa caratteri speciali nei tag (spazi, virgole, uguali).
     *
     * @param value valore tag
     * @return tag escaped
     */
    private String escapeTag(String value) {
        return value.replace(" ", "\\ ")
                .replace(",", "\\,")
                .replace("=", "\\=");
    }

    /**
     * Escapa caratteri speciali nelle chiavi dei campi.
     *
     * @param value chiave campo
     * @return chiave escaped
     */
    private String escapeFieldKey(String value) {
        return value.replace(" ", "\\ ")
                .replace(",", "\\,");
    }

    /**
     * Converte un Instant in timestamp nanosecondi per Influx.
     *
     * @param instant istante base
     * @return epoch in nanosecondi
     */
    private long toNanoTimestamp(Instant instant) {
        Instant ts = instant == null ? Instant.now() : instant;
        return ts.getEpochSecond() * 1_000_000_000L + ts.getNano();
    }

    /**
     * Normalizza l'URL Influx aggiungendo schema e porta se necessari.
     *
     * @param host valore specifico campagna
     * @return base URL valida o stringa vuota
     */
    private String normalizeBaseUrl(String host) {
        if (host == null || host.isBlank()) {
            return "";
        }
        String value = host.trim();
        if (value.startsWith("http://") || value.startsWith("https://")) {
            return value;
        }
        if (value.contains(":")) {
            return "http://" + value;
        }
        return "http://" + value + ":8086";
    }

    /**
     * Normalizza il nome database della campagna.
     *
     * @param dbName nome database della campagna
     * @return nome database o stringa vuota
     */
    private String normalizeDatabase(String dbName) {
        if (dbName == null || dbName.isBlank()) {
            return "";
        }
        return dbName.trim();
    }

    /**
     * Codifica un parametro URL in UTF-8.
     *
     * @param value testo raw
     * @return testo encoded
     */
    private String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }
}
