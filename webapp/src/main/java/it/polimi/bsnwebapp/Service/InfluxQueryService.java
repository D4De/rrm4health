package it.polimi.bsnwebapp.Service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import it.polimi.bsnwebapp.DTO.response.CampaignOutputDataResponse;
import it.polimi.bsnwebapp.DTO.response.InfluxSeriesResponse;
import it.polimi.bsnwebapp.Model.Entities.Campagna;
import it.polimi.bsnwebapp.Repository.CampagnaRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.net.URI;
import java.net.URLEncoder;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.regex.Pattern;

/**
 * Service per interrogare InfluxDB 1.x tramite HTTP.
 * Costruisce query per campagna (measurement per campagna) e restituisce colonne/valori in formato compatibile con i grafici.
 * L'URL e il database sono letti dalla campagna o da un database scelto esplicitamente.
 */
@Service
@RequiredArgsConstructor
public class InfluxQueryService {

    private static final Pattern SAFE_NAME = Pattern.compile("^[A-Za-z0-9_]+$");
    private static final int DEFAULT_LIMIT = 1000;
    private static final int MAX_LIMIT = 5000;

    private final ObjectMapper objectMapper;
    private final CampagnaRepository campagnaRepository;
    private final HttpClient httpClient = HttpClient.newHttpClient();

    /**
     * Esegue una query su InfluxDB per la campagna e opzionalmente per imuid.
     *
     * @param campaignId id campagna usato per comporre la misura Influx
     * @param measurement misura base da interrogare (es. campaign)
     * @param imuidCsv filtro facoltativo (es. XEXA,IMU1)
     * @param limit numero massimo di punti da restituire
     * @param dbHostOverride override opzionale host Influx
     * @param dbNameOverride override opzionale nome database
     * @return serie Influx con colonne e valori
     * @throws IOException se la richiesta HTTP fallisce o la risposta non e' valida
     */
    public InfluxSeriesResponse queryCampaignData(
            Long campaignId,
            String measurement,
            String imuidCsv,
            Integer limit,
            Long fromSeconds,
            String dbHostOverride,
            String dbNameOverride
    ) throws IOException {
        if (campaignId == null) {
            throw new IllegalArgumentException("Campagna non valida");
        }

        Campagna campagna = campagnaRepository.findById(campaignId)
                .orElseThrow(() -> new IllegalArgumentException("Campagna non trovata"));

        String safeMeasurement = resolveMeasurementForCampaign(measurement, campaignId);
        int safeLimit = normalizeLimit(limit);
        List<String> imuids = normalizeImuids(imuidCsv);
        Long safeFromSeconds = normalizeFromSeconds(fromSeconds);

        Instant startTime = null;
        if (safeFromSeconds != null && campagna.getDataInizio() != null) {
            startTime = campagna.getDataInizio()
                    .atZone(ZoneId.systemDefault())
                    .toInstant()
                    .plusSeconds(safeFromSeconds);
        }

        String query = buildQuery(safeMeasurement, imuids, safeLimit, startTime);
        String baseUrl = normalizeBaseUrl(resolveHost(dbHostOverride, campagna));
        String database = normalizeDatabase(resolveDatabase(dbNameOverride, campagna));
        URI uri = buildQueryUri(baseUrl, database, query);

        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("Richiesta InfluxDB interrotta", e);
        }

        if (response.statusCode() >= 300) {
            throw new IOException("InfluxDB status " + response.statusCode());
        }

        return parseResponse(campaignId, safeMeasurement, response.body());
    }

    /**
     * Recupera gli output applicativi della campagna. Il suffisso della measurement
     * deriva dal cname pubblicato dall'applicazione e non è noto in anticipo, quindi
     * vengono interrogate tutte le measurement {@code campaign_<id>_<cname>}.
     */
    public CampaignOutputDataResponse queryCampaignOutputData(Long campaignId, Integer limit) throws IOException {
        if (campaignId == null) {
            throw new IllegalArgumentException("Campagna non valida");
        }

        Campagna campagna = campagnaRepository.findById(campaignId)
                .orElseThrow(() -> new IllegalArgumentException("Campagna non trovata"));

        int safeLimit = normalizeLimit(limit);
        String measurementPattern = "^campaign_" + campaignId + "_.+$";
        String query = "SELECT * FROM /" + measurementPattern + "/ ORDER BY time DESC LIMIT " + safeLimit;
        URI uri = buildQueryUri(
                normalizeBaseUrl(campagna.getDbHost()),
                normalizeDatabase(campagna.getDbName()),
                query
        );

        HttpRequest request = HttpRequest.newBuilder(uri).GET().build();
        HttpResponse<String> response;
        try {
            response = httpClient.send(request, HttpResponse.BodyHandlers.ofString());
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IOException("Richiesta InfluxDB interrotta", e);
        }

        if (response.statusCode() >= 300) {
            throw new IOException("InfluxDB status " + response.statusCode());
        }

        return parseOutputResponse(campaignId, response.body());
    }

    private String resolveMeasurementForCampaign(String measurement, Long campaignId) {
        String base = normalizeMeasurement(measurement);
        if (campaignId == null) {
            return base;
        }
        String suffix = "_" + campaignId;
        if (base.endsWith(suffix)) {
            return base;
        }
        return base + suffix;
    }

    private String normalizeMeasurement(String measurement) {
        String value = (measurement == null || measurement.isBlank()) ? "campaign" : measurement.trim();
        if (!SAFE_NAME.matcher(value).matches()) {
            throw new IllegalArgumentException("Misura Influx non valida");
        }
        return value;
    }

    /**
     * Normalizza il limite di punti richiesti garantendo un range sicuro.
     *
     * @param limit valore richiesto dal client
     * @return limite coerente con i vincoli di servizio
     */
    private int normalizeLimit(Integer limit) {
        if (limit == null || limit <= 0) {
            return DEFAULT_LIMIT;
        }
        return Math.min(limit, MAX_LIMIT);
    }

    /**
     * Converte la lista CSV di sensori in una lista pulita e valida.
     * Filtra valori vuoti e non conformi al pattern consentito.
     *
     * @param imuidCsv lista separata da virgola (es. XEXA,IMU1)
     * @return lista validata di codici sensore
     */
    private List<String> normalizeImuids(String imuidCsv) {
        List<String> result = new ArrayList<>();
        if (imuidCsv == null || imuidCsv.isBlank()) {
            return result;
        }
        for (String raw : imuidCsv.split(",")) {
            String value = raw.trim().toUpperCase(Locale.ROOT);
            if (!value.isEmpty() && SAFE_NAME.matcher(value).matches()) {
                result.add(value);
            }
        }
        return result;
    }

    /**
     * Normalizza l'offset temporale in secondi per lo slider.
     *
     * @param fromSeconds secondi dall'avvio campagna
     * @return valore non negativo o null se assente
     */
    private Long normalizeFromSeconds(Long fromSeconds) {
        if (fromSeconds == null) {
            return null;
        }
        return Math.max(0L, fromSeconds);
    }

    /**
     * Costruisce la query InfluxQL per campagna con filtri e ordinamento.
     * Se fromSeconds e' presente, la query ordina in ASC per mantenere la sequenza temporale.
     *
     * @param measurement misura Influx
     * @param imuids lista sensori da filtrare
     * @param limit massimo punti
     * @param startTime istante di inizio da cui leggere
     * @return query InfluxQL pronta per l'HTTP API
     */
    private String buildQuery(String measurement, List<String> imuids, int limit, Instant startTime) {
        StringBuilder builder = new StringBuilder();
        builder.append("SELECT * FROM ").append(measurement);

        boolean hasWhere = false;
        if (startTime != null) {
            builder.append(" WHERE time >= '").append(startTime).append("'");
            hasWhere = true;
        }

        if (!imuids.isEmpty()) {
            builder.append(hasWhere ? " AND " : " WHERE ");
            builder.append("imuid =~ /^(?:");
            for (int i = 0; i < imuids.size(); i++) {
                if (i > 0) builder.append("|");
                builder.append(imuids.get(i));
            }
            builder.append(")$/");
        }

        if (startTime != null) {
            builder.append(" ORDER BY time ASC LIMIT ").append(limit);
        } else {
            builder.append(" ORDER BY time DESC LIMIT ").append(limit);
        }
        return builder.toString();
    }

    /**
     * Costruisce la URL finale per l'endpoint /query di InfluxDB 1.x.
     *
     * @param baseUrl base URL Influx
     * @param database nome database
     * @param query query InfluxQL
     * @return URI completa con parametri
     */
    private URI buildQueryUri(String baseUrl, String database, String query) {
        String base = baseUrl.endsWith("/") ? baseUrl.substring(0, baseUrl.length() - 1) : baseUrl;
        StringBuilder builder = new StringBuilder(base).append("/query?db=")
                .append(encode(database))
                .append("&q=")
                .append(encode(query));

        return URI.create(builder.toString());
    }

    /**
     * Normalizza l'host Influx, aggiungendo schema e porta se mancanti.
     */
    private String normalizeBaseUrl(String host) {
        String value = host == null ? "" : host.trim();
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Indirizzo Influx non configurato");
        }
        if (value.startsWith("http://") || value.startsWith("https://")) {
            return value;
        }
        if (value.contains(":")) {
            return "http://" + value;
        }
        return "http://" + value + ":8086";
    }

    /**
     * Normalizza il nome database.
     */
    private String normalizeDatabase(String dbName) {
        String value = dbName == null ? "" : dbName.trim();
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("Nome database Influx non configurato");
        }
        return value;
    }

    private String resolveHost(String overrideHost, Campagna campagna) {
        if (overrideHost != null && !overrideHost.isBlank()) {
            return overrideHost;
        }
        return campagna.getDbHost();
    }

    private String resolveDatabase(String overrideDatabase, Campagna campagna) {
        if (overrideDatabase != null && !overrideDatabase.isBlank()) {
            return overrideDatabase;
        }
        return campagna.getDbName();
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

    /**
     * Converte la risposta JSON di Influx in un DTO con colonne e valori.
     *
     * @param campaignId id campagna
     * @param measurement misura richiesta
     * @param body risposta JSON
     * @return serie pronta per i grafici
     * @throws IOException se il JSON non e' valido
     */
    private InfluxSeriesResponse parseResponse(Long campaignId, String measurement, String body) throws IOException {
        JsonNode root = objectMapper.readTree(body);
        JsonNode seriesNode = root.path("results").path(0).path("series");
        if (!seriesNode.isArray() || seriesNode.isEmpty()) {
            return new InfluxSeriesResponse(campaignId, measurement, List.of(), List.of());
        }

        JsonNode series = seriesNode.get(0);
        List<String> columns = new ArrayList<>();
        for (JsonNode col : series.path("columns")) {
            columns.add(col.asText());
        }

        List<List<Object>> values = new ArrayList<>();
        for (JsonNode row : series.path("values")) {
            List<Object> rowValues = new ArrayList<>();
            for (JsonNode cell : row) {
                rowValues.add(toJavaValue(cell));
            }
            values.add(rowValues);
        }

        return new InfluxSeriesResponse(campaignId, measurement, columns, values);
    }

    CampaignOutputDataResponse parseOutputResponse(Long campaignId, String body) throws IOException {
        JsonNode result = objectMapper.readTree(body).path("results").path(0);
        if (result.hasNonNull("error")) {
            throw new IOException("Errore InfluxDB: " + result.path("error").asText());
        }

        List<CampaignOutputDataResponse.Series> outputSeries = new ArrayList<>();
        JsonNode seriesNodes = result.path("series");
        if (!seriesNodes.isArray()) {
            return new CampaignOutputDataResponse(campaignId, outputSeries);
        }

        for (JsonNode seriesNode : seriesNodes) {
            List<String> columns = new ArrayList<>();
            for (JsonNode column : seriesNode.path("columns")) {
                columns.add(column.asText());
            }

            List<List<Object>> values = new ArrayList<>();
            for (JsonNode row : seriesNode.path("values")) {
                List<Object> rowValues = new ArrayList<>();
                for (JsonNode cell : row) {
                    rowValues.add(toJavaValue(cell));
                }
                values.add(rowValues);
            }

            outputSeries.add(new CampaignOutputDataResponse.Series(
                    seriesNode.path("name").asText(),
                    columns,
                    values
            ));
        }
        return new CampaignOutputDataResponse(campaignId, outputSeries);
    }

    /**
     * Converte un JsonNode in un tipo Java semplice.
     *
     * @param node nodo JSON
     * @return valore scalare o stringa
     */
    private Object toJavaValue(JsonNode node) {
        if (node == null || node.isNull()) {
            return null;
        }
        if (node.isNumber()) {
            if (node.isFloatingPointNumber()) {
                return node.doubleValue();
            }
            return node.longValue();
        }
        if (node.isBoolean()) {
            return node.booleanValue();
        }
        return node.asText();
    }
}
