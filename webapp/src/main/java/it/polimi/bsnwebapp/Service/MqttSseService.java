package it.polimi.bsnwebapp.Service;

import it.polimi.bsnwebapp.Config.MqttRuntimeConfig;
import it.polimi.bsnwebapp.DTO.response.ImuSseEvent;
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;
import lombok.RequiredArgsConstructor;
import org.eclipse.paho.client.mqttv3.IMqttDeliveryToken;
import org.eclipse.paho.client.mqttv3.MqttCallbackExtended;
import org.eclipse.paho.client.mqttv3.MqttClient;
import org.eclipse.paho.client.mqttv3.MqttConnectOptions;
import org.eclipse.paho.client.mqttv3.MqttException;
import org.eclipse.paho.client.mqttv3.MqttMessage;
import org.eclipse.paho.client.mqttv3.persist.MemoryPersistence;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import java.io.IOException;
import java.math.BigDecimal;
import java.nio.charset.StandardCharsets;
import java.time.Instant;
import java.util.Arrays;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CopyOnWriteArrayList;
import java.util.stream.Collectors;

/**
 * Service che collega MQTT, SSE e scrittura Influx per il real time.
 * Si connette al broker configurato, sottoscrive il topic, decodifica i payload e li trasforma in ImuSseEvent.
 * Gli eventi vengono inviati ai client SSE e scritti su InfluxDB in base al database scelto dalla campagna.
 */

@Service

//È un’annotazione di Lombok che ti genera automaticamente un costruttore che prende come parametri tutti i campi final
@RequiredArgsConstructor
public class MqttSseService implements MqttCallbackExtended {
    private static final Logger logger = LoggerFactory.getLogger(MqttSseService.class);

    private final MqttRuntimeConfigService mqttRuntimeConfigService;
    private final InfluxWriteService influxWriteService;


    //serve a leggere un valore di configurazione da application.properties e iniettarlo in quel campo.
    //:0 di default se non viene trovato
    @Value("${app.sse.timeout-ms:0}")
    private long sseTimeoutMs;  //serve per chiudere automaticamente connessioni sse rimaste aperte dopo timeout

    private final List<SseClient> clients = new CopyOnWriteArrayList<>();  //CopyOnWriteArrayList è thread-safe
    private MqttClient client;
    private volatile MqttRuntimeConfig currentConfig;

    /**
     * Inizializza il servizio MQTT alla partenza dell'applicazione.
     * Se la proprieta app.mqtt.enabled e' false, il servizio resta inattivo.
     * In caso contrario crea il client, si connette al broker e sottoscrive il topic.
     */
    @PostConstruct
    public void start() {
        currentConfig = mqttRuntimeConfigService.getConfig();
        if (!currentConfig.enabled()) {
            logger.info("MQTT disabled. SSE will be available but no data will be streamed.");
            return;
        }
        connectAndSubscribe(currentConfig);
    }

    /**
     * Chiude la connessione MQTT prima dello shutdown dell'applicazione.
     * Serve a rilasciare risorse e chiudere il client in modo pulito.
     */
    @PreDestroy
    public void stop() {
        disconnectCurrentClient();
    }

    /**
     * Ricarica la configurazione runtime dal file e riconnette il client MQTT.
     * Il chiamante deve verificare eventuali vincoli di dominio, ad esempio campagne attive.
     */
    public synchronized void reloadConfig() {
        MqttRuntimeConfig nextConfig = mqttRuntimeConfigService.getConfig();
        disconnectCurrentClient();
        currentConfig = nextConfig;
        if (!nextConfig.enabled()) {
            logger.info("MQTT runtime config reloaded: MQTT disabled.");
            return;
        }
        connectAndSubscribe(nextConfig);
        logger.info("MQTT runtime config reloaded.");
    }

    /**
     * Crea un emitter SSE con filtri opzionali su imuid e cname.
     * I client vengono memorizzati in una lista thread-safe e rimossi su completion/timeout/error.
     *
     * @param imuidParam lista di imuid separati da virgola per filtrare i sensori
     * @param cnameParam nome campagna per filtrare i messaggi
     * @return emitter SSE gia pronto per lo streaming
     */
    public SseEmitter createEmitter(String imuidParam, String cnameParam, Long campaignId) {
        long timeout = sseTimeoutMs > 0 ? sseTimeoutMs : 0L;
        SseEmitter emitter = new SseEmitter(timeout);
        SseClient clientEntry = new SseClient(
                emitter,
                normalizeImuids(imuidParam),
                normalizeFilter(cnameParam),
                campaignId
        );
        clients.add(clientEntry);

        emitter.onCompletion(() -> clients.remove(clientEntry));
        emitter.onTimeout(() -> clients.remove(clientEntry));
        emitter.onError(ex -> clients.remove(clientEntry));
        return emitter;
    }

    /**
     * Callback eseguita quando la connessione MQTT e' completa.
     * In caso di riconnessione, effettua nuovamente la subscribe ai topic.
     */
    @Override
    public void connectComplete(boolean reconnect, String serverURI) {
        if (reconnect) {
            subscribe(currentConfig);
            logger.info("MQTT reconnected to {}", serverURI);
        }
    }

    /**
     * Callback invocata quando la connessione MQTT si interrompe.
     * Non interrompe gli SSE, ma registra l'evento per diagnostica.
     */
    @Override
    public void connectionLost(Throwable cause) {
        logger.warn("MQTT connection lost: {}", cause == null ? "unknown" : cause.getMessage());
    }

    /**
     * Callback invocata alla ricezione di un messaggio MQTT.
     * Decodifica il payload, crea un ImuSseEvent e lo inoltra ai client SSE compatibili.
     */
    @Override
    public void messageArrived(String topic, MqttMessage message) {
        String payload = new String(message.getPayload(), StandardCharsets.UTF_8);
        ImuSseEvent event = parsePayload(payload, topic); //parsing messaggio
        if (event == null) {
            return;
        }
        influxWriteService.writeEvent(event);
        broadcast(event);
    }

    /**
     * Callback di completamento publish (non usata in modalita consumer).
     */
    @Override
    public void deliveryComplete(IMqttDeliveryToken token) {
        // No-op (consumer only)
    }

    /**
     * Crea il client MQTT e avvia la connessione con le opzioni configurate.
     * Imposta la callback e sottoscrive il topic di interesse.
     */
    private void connectAndSubscribe(MqttRuntimeConfig config) {
        if (config == null || !config.enabled()) {
            return;
        }
        try {
            client = new MqttClient(config.broker(), config.clientId(), new MemoryPersistence());
            client.setCallback(this);

            MqttConnectOptions options = new MqttConnectOptions();
            options.setAutomaticReconnect(true);
            options.setCleanSession(true);

            if (config.username() != null && !config.username().isBlank()) {
                options.setUserName(config.username());
            }
            if (config.password() != null && !config.password().isBlank()) {
                options.setPassword(config.password().toCharArray());
            }

            client.connect(options);
            subscribe(config);
            logger.info("MQTT connected to {} topic={}", config.broker(), config.topic());
        } catch (MqttException e) {
            logger.error("MQTT connection error: {}", e.getMessage());
        }
    }

    private void disconnectCurrentClient() {
        if (client == null) {
            return;
        }
        try {
            if (client.isConnected()) {
                client.disconnect();
            }
            client.close();
        } catch (MqttException e) {
            logger.warn("MQTT disconnect error: {}", e.getMessage());
        } finally {
            client = null;
        }
    }

    /**
     * Sottoscrive il topic MQTT configurato con il QoS definito.
     * Se il client non e' connesso, l'operazione viene ignorata.
     */
    private void subscribe(MqttRuntimeConfig config) {
        if (client == null || !client.isConnected()) {
            return;
        }
        if (config == null || !config.enabled()) {
            return;
        }
        try {
            client.subscribe(config.topic(), config.qos());
        } catch (MqttException e) {
            logger.error("MQTT subscribe error: {}", e.getMessage());
        }
    }

    /**
     * Invia l'evento SSE a tutti i client attivi rispettando i filtri impostati.
     * I client che falliscono l'invio vengono rimossi per evitare leak di risorse.
     */
    private void broadcast(ImuSseEvent event) {
        List<SseClient> toRemove = new ArrayList<>();
        for (SseClient clientEntry : clients) {
            if (!matches(clientEntry, event)) {
                continue;
            }
            try {
                clientEntry.emitter.send(SseEmitter.event().name(event.type()).data(event));
            } catch (IOException e) {
                toRemove.add(clientEntry);
            }
        }
        if (!toRemove.isEmpty()) {
            clients.removeAll(toRemove);
        }
    }

    /**
     * Verifica se un evento soddisfa i filtri di un client SSE.
     * Gli output applicativi richiedono sempre l'id campagna; per i vecchi pacchetti
     * IMU senza cname resta disponibile il filtro per codice sensore.
     */
    private boolean matches(SseClient clientEntry, ImuSseEvent event) {
        if (clientEntry.campaignId != null) {
            if (event.campaignId() != null && !clientEntry.campaignId.equals(event.campaignId())) {
                return false;
            }
            if (event.campaignId() == null && "application-data".equals(event.type())) {
                return false;
            }
        }
        if (clientEntry.imuids != null && !"application-data".equals(event.type())) {
            if (event.imuid() == null || !clientEntry.imuids.contains(event.imuid().toUpperCase())) {
                return false;
            }
        }
        if (clientEntry.cname != null) {
            if (event.cname() == null || !clientEntry.cname.equalsIgnoreCase(event.cname())) {
                return false;
            }
        }
        return true;
    }

    /**
     * Decide quale parser usare in base al formato del payload.
     * Supporta key/value con '=' o ':' e formato posizionale a 12 token.
     *
     * @param payload stringa ricevuta da MQTT
     * @param topic topic di provenienza
     * @return ImuSseEvent oppure null se il payload non e' valido
     */
    ImuSseEvent parsePayload(String payload, String topic) {
        if (payload == null || payload.isBlank()) {
            return null;
        }

        if (payload.contains("=") || payload.contains(":")) {
            return parseKeyValuePayload(payload, topic);
        }
        return parsePositionalPayload(payload, topic);
    }

    /**
     * Parser per payload key/value (es. ax=..., ay=..., ts=...).
     * Normalizza le chiavi (imuid, counter) e converte i valori numerici.
     */
    private ImuSseEvent parseKeyValuePayload(String payload, String topic) {
        Map<String, Object> values = new LinkedHashMap<>();
        String imuid = null;
        String cname = null;
        Long campaignId = null;
        Instant timestamp = Instant.now();

        for (String part : payload.split(",")) {
            String trimmed = part.trim();
            if (trimmed.isEmpty()) {
                continue;
            }

            String[] kv;
            if (trimmed.contains("=")) {
                kv = trimmed.split("=", 2);
            } else if (trimmed.contains(":")) {
                kv = trimmed.split(":", 2);
            } else {
                continue;
            }

            String rawKey = kv[0].trim();
            String key = rawKey.toLowerCase();
            String value = kv[1].trim();

            if (key.isEmpty()) {
                continue;
            }
            if (key.equals("imiid")) {
                key = "imuid";
            }
            if (key.equals("nth")) {
                key = "counter";
            }

            if (key.equals("imuid")) {
                imuid = value.toUpperCase();
                continue;
            }
            if (key.equals("cname")) {
                cname = value;
                continue;
            }
            if (key.equals("c_id")) {
                campaignId = parseCampaignId(value);
                continue;
            }
            if (key.equals("ts")) {
                Instant parsedTimestamp = parseTimestamp(value);
                if (parsedTimestamp != null) {
                    timestamp = parsedTimestamp;
                }
                continue;
            }

            Object parsed = parseValue(key, value);
            values.put(isSensorField(key) ? key : rawKey, parsed);
        }

        if (values.isEmpty()) {
            return null;
        }
        if (campaignId == null) {
            campaignId = parseCampaignId(cname);
        }
        String type = resolveType(values);
        return new ImuSseEvent(type, imuid, cname, campaignId, values, topic, timestamp);
    }

    /**
     * Parser per payload posizionale a 12 token.
     * Supporta anche il formato a 13 token dove il primo e' un timestamp extra da scartare.
     */
    private ImuSseEvent parsePositionalPayload(String payload, String topic) {
        String[] tokens = payload.trim().split("\\s+");
        if (tokens.length == 13) {
            tokens = Arrays.copyOfRange(tokens, 1, 13);
        }
        if (tokens.length != 12) {
            return null;
        }

        Map<String, Object> values = new LinkedHashMap<>();
        String imuid = null;
        Instant timestamp = Instant.now();
        String[] fields = {"ax", "ay", "az", "counter", "gx", "gy", "gz", "imuid", "mx", "my", "mz", "ts"};

        for (int i = 0; i < fields.length; i++) {
            String key = fields[i];
            String value = tokens[i];
            if (key.equals("imuid")) {
                imuid = value.toUpperCase();
                continue;
            }
            if (key.equals("ts")) {
                Instant parsedTimestamp = parseTimestamp(value);
                if (parsedTimestamp != null) {
                    timestamp = parsedTimestamp;
                }
                continue;
            }
            Object parsed = parseValue(key, value);
            values.put(key, parsed);
        }

        String type = resolveType(values);
        return new ImuSseEvent(type, imuid, null, null, values, topic, timestamp);
    }

    /**
     * Converte una stringa in valore numerico quando possibile.
     * Gestisce interi esadecimali signed 16-bit e float con punto decimale.
     */
    private Object parseValue(String key, String value) {
        try {
            if (key.equals("counter")) {
                Number parsed = parseNumber(value);
                return parsed == null ? value : parsed.longValue();
            }
            Number parsed = parseNumber(value);
            if (parsed != null) {
                return parsed;
            }
            if ("true".equalsIgnoreCase(value) || "false".equalsIgnoreCase(value)) {
                return Boolean.parseBoolean(value);
            }
        } catch (NumberFormatException e) {
            return value;
        }
        return value;
    }

    /**
     * Interpreta timestamp Unix in secondi, millisecondi, microsecondi o nanosecondi.
     */
    private Instant parseTimestamp(String value) {
        if (value == null) {
            return null;
        }
        String v = value.trim();
        if (v.isEmpty()) {
            return null;
        }
        try {
            BigDecimal raw = new BigDecimal(v);
            BigDecimal absolute = raw.abs();
            BigDecimal unitsPerSecond;
            if (absolute.compareTo(new BigDecimal("100000000000")) < 0) {
                unitsPerSecond = BigDecimal.ONE;
            } else if (absolute.compareTo(new BigDecimal("100000000000000")) < 0) {
                unitsPerSecond = new BigDecimal("1000");
            } else if (absolute.compareTo(new BigDecimal("100000000000000000")) < 0) {
                unitsPerSecond = new BigDecimal("1000000");
            } else {
                unitsPerSecond = new BigDecimal("1000000000");
            }

            BigDecimal[] parts = raw.divideAndRemainder(unitsPerSecond);
            long seconds = parts[0].longValueExact();
            long nanos = parts[1]
                    .multiply(new BigDecimal("1000000000"))
                    .divide(unitsPerSecond)
                    .longValue();
            if (nanos < 0) {
                seconds--;
                nanos += 1_000_000_000L;
            }
            return Instant.ofEpochSecond(seconds, nanos);
        } catch (RuntimeException e) {
            logger.warn("Failed to parse timestamp: {}", value);
            return null;
        }
    }

    /**
     * Parser numerico generico con supporto a:
     * - esadecimale signed 16-bit (0xXXXX)
     * - float con punto
     * - interi base 10
     */
    private Number parseNumber(String value) {
        if (value == null) {
            return null;
        }
        String v = value.trim();
        if (v.isEmpty()) {
            return null;
        }
        if (v.startsWith("0x") || v.startsWith("0X")) {
            int raw = Integer.parseInt(v.substring(2), 16);
            if (raw >= 0x8000) {
                raw -= 0x10000;
            }
            return raw;
        }
        if (v.endsWith(".")) {
            v = v.substring(0, v.length() - 1);
        }
        try {
            return Long.parseLong(v);
        } catch (NumberFormatException ignored) {
            return Double.parseDouble(v);
        }
    }

    /**
     * Converte c_id, o il cname numerico legacy, nell'identificativo della campagna.
     */
    private Long parseCampaignId(String cname) {
        if (cname == null || cname.isBlank()) {
            return null;
        }
        try {
            return Long.parseLong(cname.trim());
        } catch (NumberFormatException e) {
            return null;
        }
    }

    private boolean isSensorField(String key) {
        return switch (key) {
            case "ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz", "battery", "counter" -> true;
            default -> false;
        };
    }

    /**
     * Determina il tipo di evento in base ai campi presenti.
     * Se rileva assi IMU ritorna "imu", se presente battery ritorna "battery".
     */
    private String resolveType(Map<String, Object> values) {
        boolean hasImu = values.containsKey("ax")
                || values.containsKey("ay")
                || values.containsKey("az")
                || values.containsKey("gx")
                || values.containsKey("gy")
                || values.containsKey("gz")
                || values.containsKey("mx")
                || values.containsKey("my")
                || values.containsKey("mz");
        if (hasImu) {
            return "imu";
        }
        if (values.containsKey("battery")) {
            return "battery";
        }
        return "application-data";
    }

    /**
     * Normalizza il parametro imuid in un Set di codici maiuscoli.
     * Restituisce null se il filtro non e' presente.
     */
    private Set<String> normalizeImuids(String imuidParam) {
        if (imuidParam == null || imuidParam.isBlank()) {
            return null;
        }
        return List.of(imuidParam.split(",")).stream()
                .map(String::trim)
                .filter(val -> !val.isEmpty())
                .map(String::toUpperCase)
                .collect(Collectors.toSet());
    }

    /**
     * Normalizza un filtro testuale opzionale rimuovendo spazi.
     */
    private String normalizeFilter(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.trim();
    }

    private record SseClient(SseEmitter emitter, Set<String> imuids, String cname, Long campaignId) {
    }
}
