package it.polimi.bsnwebapp.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import it.polimi.bsnwebapp.Model.Entities.Campagna;
import it.polimi.bsnwebapp.Model.Entities.Utente;
import it.polimi.bsnwebapp.Model.Enum.RuoloUtente;
import it.polimi.bsnwebapp.Repository.CampagnaRepository;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.stereotype.Service;

import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.math.BigInteger;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.zip.ZipEntry;
import java.util.zip.ZipOutputStream;

/**
 * Esporta in CSV gli output applicativi salvati nella measurement Influx della campagna.
 * Ogni topic viene scritto in un file separato all'interno di un archivio ZIP.
 */
@Service
public class CampaignOutputExportService {

    private static final String IMU_TOPIC = "aaac/campaign/imu";
    private static final String FIELD_ORDER_COLUMN = "_field_order";
    private static final Set<String> METADATA_COLUMNS =
            Set.of("time", "topic", "c_id", "cname", "imuid", "event_type", FIELD_ORDER_COLUMN);
    private static final Set<String> IMU_METADATA_COLUMNS =
            Set.of("time", "topic", "c_id", "cname", "event_type", FIELD_ORDER_COLUMN);
    private static final List<String> IMU_PREFERRED_COLUMNS =
            List.of("imuid", "ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz");

    private final ObjectMapper objectMapper;
    private final CampagnaRepository campagnaRepository;
    private final HttpClient httpClient;

    public CampaignOutputExportService(ObjectMapper objectMapper, CampagnaRepository campagnaRepository) {
        this.objectMapper = objectMapper;
        this.campagnaRepository = campagnaRepository;
        this.httpClient = HttpClient.newHttpClient();
    }

    public ExportArchive exportApplicationOutputs(Long campaignId, Utente requester) throws IOException {
        Campagna campagna = loadAuthorizedCampaign(campaignId, requester);

        String measurementPattern = "^campaign_" + campaignId + "_.+$";
        String query = "SELECT * FROM /" + measurementPattern + "/ ORDER BY time ASC";
        URI uri = buildQueryUri(
                normalizeBaseUrl(campagna.getDbHost()),
                normalizeDatabase(campagna.getDbName()),
                query
        );

        HttpResponse<String> response = sendInfluxQuery(uri);
        return buildArchiveFromResponse(campaignId, response.body());
    }

    public ExportFile exportImuData(Long campaignId, Utente requester) throws IOException {
        Campagna campagna = loadAuthorizedCampaign(campaignId, requester);

        String measurement = "campaign_" + campaignId;
        String query = "SELECT * FROM \"" + measurement + "\" ORDER BY time ASC";
        URI uri = buildQueryUri(
                normalizeBaseUrl(campagna.getDbHost()),
                normalizeDatabase(campagna.getDbName()),
                query
        );

        HttpResponse<String> response = sendInfluxQuery(uri);
        return buildImuCsvFromResponse(campaignId, response.body());
    }

    private Campagna loadAuthorizedCampaign(Long campaignId, Utente requester) {
        if (campaignId == null || requester == null || requester.getId() == null) {
            throw new IllegalArgumentException("Campagna o utente non valido");
        }

        Campagna campagna = campagnaRepository.findById(campaignId)
                .orElseThrow(() -> new IllegalArgumentException("Campagna non trovata"));
        if (requester.getRuolo() != RuoloUtente.USER_DEV
                && !campagnaRepository.existsByIdAndUtenteCreatore_Id(campaignId, requester.getId())) {
            throw new AccessDeniedException("Non autorizzato a esportare questa campagna");
        }
        return campagna;
    }

    private HttpResponse<String> sendInfluxQuery(URI uri) throws IOException {
        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        try {
            HttpResponse<String> response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
            if (response.statusCode() >= 300) {
                throw new IOException("InfluxDB status " + response.statusCode());
            }
            return response;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("Esportazione InfluxDB interrotta", e);
        }
    }

    ExportArchive buildArchiveFromResponse(Long campaignId, String responseBody) throws IOException {
        Map<String, TopicRows> topics = parseTopics(responseBody);
        if (topics.isEmpty()) {
            throw new IllegalStateException("Nessun output applicativo disponibile per questa campagna");
        }

        ByteArrayOutputStream output = new ByteArrayOutputStream();
        Map<String, Integer> usedNames = new LinkedHashMap<>();
        try (ZipOutputStream zip = new ZipOutputStream(output, StandardCharsets.UTF_8)) {
            for (Map.Entry<String, TopicRows> entry : topics.entrySet()) {
                String baseName = topicFileName(entry.getKey());
                int occurrence = usedNames.merge(baseName, 1, Integer::sum);
                String fileName = occurrence == 1
                        ? baseName + ".csv"
                        : baseName + "_" + occurrence + ".csv";

                zip.putNextEntry(new ZipEntry(fileName));
                zip.write(buildCsv(entry.getValue()).getBytes(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
        }

        return new ExportArchive(
                output.toByteArray(),
                "campagna_" + campaignId + "_output.zip",
                topics.size()
        );
    }

    ExportFile buildImuCsvFromResponse(Long campaignId, String responseBody) throws IOException {
        TopicRows imuRows = parseImuRows(responseBody);
        if (imuRows.rows.isEmpty()) {
            throw new IllegalStateException("Nessun dato IMU disponibile per questa campagna");
        }

        return new ExportFile(
                buildCsv(imuRows).getBytes(StandardCharsets.UTF_8),
                "campagna_" + campaignId + "_imu.csv"
        );
    }

    private Map<String, TopicRows> parseTopics(String responseBody) throws IOException {
        JsonNode root = objectMapper.readTree(responseBody);
        JsonNode result = root.path("results").path(0);
        if (result.hasNonNull("error")) {
            throw new IOException("Errore InfluxDB: " + result.path("error").asText());
        }

        Map<String, TopicRows> topics = new LinkedHashMap<>();
        JsonNode seriesNodes = result.path("series");
        if (!seriesNodes.isArray()) {
            return topics;
        }

        for (JsonNode series : seriesNodes) {
            List<String> columns = new ArrayList<>();
            for (JsonNode column : series.path("columns")) {
                columns.add(column.asText());
            }
            int topicIndex = columns.indexOf("topic");
            int timeIndex = columns.indexOf("time");
            if (topicIndex < 0 || timeIndex < 0) {
                continue;
            }

            for (JsonNode valueRow : series.path("values")) {
                String topic = textAt(valueRow, topicIndex);
                if (topic == null || topic.isBlank() || IMU_TOPIC.equals(topic)) {
                    continue;
                }

                TopicRows topicRows = topics.computeIfAbsent(topic, ignored -> new TopicRows());
                int fieldOrderIndex = columns.indexOf(FIELD_ORDER_COLUMN);
                if (fieldOrderIndex >= 0) {
                    topicRows.addPreferredColumns(textAt(valueRow, fieldOrderIndex));
                }
                Map<String, Object> fields = new LinkedHashMap<>();
                for (int i = 0; i < columns.size(); i++) {
                    String column = columns.get(i);
                    if (METADATA_COLUMNS.contains(column) || i >= valueRow.size()) {
                        continue;
                    }
                    JsonNode cell = valueRow.get(i);
                    if (cell == null || cell.isNull()) {
                        continue;
                    }
                    topicRows.columns.add(column);
                    fields.put(column, toJavaValue(cell));
                }
                if (!fields.isEmpty()) {
                    topicRows.rows.add(new OutputRow(timestampAt(valueRow, timeIndex), fields));
                }
            }
        }
        topics.entrySet().removeIf(entry -> entry.getValue().rows.isEmpty());
        return topics;
    }

    private TopicRows parseImuRows(String responseBody) throws IOException {
        JsonNode root = objectMapper.readTree(responseBody);
        JsonNode result = root.path("results").path(0);
        if (result.hasNonNull("error")) {
            throw new IOException("Errore InfluxDB: " + result.path("error").asText());
        }

        TopicRows imuRows = new TopicRows();
        imuRows.preferredColumns.addAll(IMU_PREFERRED_COLUMNS);
        JsonNode seriesNodes = result.path("series");
        if (!seriesNodes.isArray()) {
            return imuRows;
        }

        for (JsonNode series : seriesNodes) {
            List<String> columns = new ArrayList<>();
            for (JsonNode column : series.path("columns")) {
                columns.add(column.asText());
            }
            int timeIndex = columns.indexOf("time");
            if (timeIndex < 0) {
                continue;
            }

            for (JsonNode valueRow : series.path("values")) {
                if (!isImuRow(columns, valueRow)) {
                    continue;
                }

                Map<String, Object> fields = new LinkedHashMap<>();
                for (int i = 0; i < columns.size(); i++) {
                    String column = columns.get(i);
                    if (IMU_METADATA_COLUMNS.contains(column) || i >= valueRow.size()) {
                        continue;
                    }
                    JsonNode cell = valueRow.get(i);
                    if (cell == null || cell.isNull()) {
                        continue;
                    }
                    imuRows.columns.add(column);
                    fields.put(column, toJavaValue(cell));
                }
                if (!fields.isEmpty()) {
                    imuRows.rows.add(new OutputRow(timestampAt(valueRow, timeIndex), fields));
                }
            }
        }
        return imuRows;
    }

    private boolean isImuRow(List<String> columns, JsonNode row) {
        String eventType = textAt(row, columns.indexOf("event_type"));
        if ("imu".equalsIgnoreCase(eventType)) {
            return true;
        }

        String topic = textAt(row, columns.indexOf("topic"));
        if (IMU_TOPIC.equals(topic)) {
            return true;
        }

        return textAt(row, columns.indexOf("imuid")) != null
                && (hasValue(row, columns.indexOf("ax"))
                || hasValue(row, columns.indexOf("gx"))
                || hasValue(row, columns.indexOf("mx")));
    }

    private boolean hasValue(JsonNode row, int index) {
        return index >= 0 && index < row.size() && row.get(index) != null && !row.get(index).isNull();
    }

    private String buildCsv(TopicRows topicRows) {
        List<String> columns = topicRows.orderedColumns();
        StringBuilder csv = new StringBuilder("\uFEFF");
        csv.append("timestamp");
        for (String column : columns) {
            csv.append(',').append(csvCell(column));
        }
        csv.append("\r\n");

        for (OutputRow row : topicRows.rows) {
            csv.append(csvCell(row.timestamp));
            for (String column : columns) {
                csv.append(',').append(csvCell(row.fields.get(column)));
            }
            csv.append("\r\n");
        }
        return csv.toString();
    }

    private String csvCell(Object value) {
        if (value == null) {
            return "";
        }
        String text = String.valueOf(value);
        if (text.contains(",") || text.contains("\"") || text.contains("\n") || text.contains("\r")) {
            return "\"" + text.replace("\"", "\"\"") + "\"";
        }
        return text;
    }

    private Object toJavaValue(JsonNode node) {
        if (node.isFloatingPointNumber()) {
            return node.doubleValue();
        }
        if (node.isIntegralNumber()) {
            return node.longValue();
        }
        if (node.isBoolean()) {
            return node.booleanValue();
        }
        return node.asText();
    }

    private String textAt(JsonNode row, int index) {
        if (index < 0 || index >= row.size()) {
            return null;
        }
        JsonNode value = row.get(index);
        return value == null || value.isNull() ? null : value.asText();
    }

    private String timestampAt(JsonNode row, int index) {
        if (index < 0 || index >= row.size()) {
            return null;
        }
        JsonNode value = row.get(index);
        if (value == null || value.isNull() || !value.isIntegralNumber()) {
            return value == null || value.isNull() ? null : value.asText();
        }
        try {
            BigInteger nanos = value.bigIntegerValue();
            if (nanos.abs().compareTo(new BigInteger("100000000000000000")) < 0) {
                // Recupera i timestamp in secondi che le versioni precedenti avevano salvato come millisecondi.
                nanos = nanos.multiply(BigInteger.valueOf(1000));
            }
            BigInteger[] parts = nanos.divideAndRemainder(BigInteger.valueOf(1_000_000_000L));
            return Instant.ofEpochSecond(parts[0].longValueExact(), parts[1].longValue()).toString();
        } catch (RuntimeException e) {
            return value.asText();
        }
    }

    private String topicFileName(String topic) {
        int separator = topic.lastIndexOf('/');
        String suffix = separator >= 0 ? topic.substring(separator + 1) : topic;
        String safe = suffix.replaceAll("[^A-Za-z0-9._-]+", "_");
        return safe.isBlank() ? "output" : safe;
    }

    private URI buildQueryUri(String baseUrl, String database, String query) {
        String base = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        return URI.create(base + "/query?db=" + encode(database)
                + "&epoch=ns&q=" + encode(query));
    }

    private String normalizeBaseUrl(String host) {
        if (host == null || host.isBlank()) {
            throw new IllegalArgumentException("Indirizzo Influx non configurato");
        }
        String value = host.trim();
        if (value.startsWith("http://") || value.startsWith("https://")) {
            return value;
        }
        return value.contains(":") ? "http://" + value : "http://" + value + ":8086";
    }

    private String normalizeDatabase(String database) {
        if (database == null || database.isBlank()) {
            throw new IllegalArgumentException("Nome database Influx non configurato");
        }
        return database.trim();
    }

    private String encode(String value) {
        return URLEncoder.encode(value, StandardCharsets.UTF_8);
    }

    public record ExportArchive(byte[] content, String fileName, int topicCount) {
    }

    public record ExportFile(byte[] content, String fileName) {
    }

    private record OutputRow(String timestamp, Map<String, Object> fields) {
    }

    private static final class TopicRows {
        private final Set<String> columns = new LinkedHashSet<>();
        private final Set<String> preferredColumns = new LinkedHashSet<>();
        private final List<OutputRow> rows = new ArrayList<>();

        private void addPreferredColumns(String fieldOrder) {
            if (fieldOrder == null || fieldOrder.isBlank()) {
                return;
            }
            for (String field : fieldOrder.split(",")) {
                String value = field.trim();
                if (!value.isEmpty() && !METADATA_COLUMNS.contains(value)) {
                    preferredColumns.add(value);
                }
            }
        }

        private List<String> orderedColumns() {
            LinkedHashSet<String> ordered = new LinkedHashSet<>();
            for (String preferred : preferredColumns) {
                if (columns.contains(preferred)) {
                    ordered.add(preferred);
                }
            }
            ordered.addAll(columns);
            return new ArrayList<>(ordered);
        }
    }
}
