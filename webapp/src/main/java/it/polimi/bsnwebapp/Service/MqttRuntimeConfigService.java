package it.polimi.bsnwebapp.Service;

import it.polimi.bsnwebapp.Config.MqttProperties;
import it.polimi.bsnwebapp.Config.MqttRuntimeConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.nio.file.StandardCopyOption;
import java.util.Properties;

/**
 * Gestisce la configurazione MQTT runtime su file .properties.
 * application.properties resta il fallback/bootstrap, mentre questo file e' modificabile da admin o script.
 */
@Service
public class MqttRuntimeConfigService {

    private static final Logger logger = LoggerFactory.getLogger(MqttRuntimeConfigService.class);

    private static final String KEY_ENABLED = "app.mqtt.enabled";
    private static final String KEY_BROKER = "app.mqtt.broker";
    private static final String KEY_TOPIC = "app.mqtt.topic";
    private static final String KEY_CLIENT_ID = "app.mqtt.client-id";
    private static final String KEY_USERNAME = "app.mqtt.username";
    private static final String KEY_PASSWORD = "app.mqtt.password";
    private static final String KEY_QOS = "app.mqtt.qos";

    private final Path configPath;
    private final MqttProperties defaults;

    public MqttRuntimeConfigService(
            MqttProperties defaults,
            @Value("${app.mqtt.config-file:./data/mqtt-runtime.properties}") String configFilePath) {
        this.defaults = defaults;
        this.configPath = Paths.get(configFilePath).toAbsolutePath().normalize();
        initStorage();
    }

    /**
     * Restituisce la configurazione runtime corrente, usando i default di application.properties
     * per eventuali chiavi mancanti o non valide.
     */
    public synchronized MqttRuntimeConfig getConfig() {
        Properties properties = readProperties();
        return new MqttRuntimeConfig(
                parseBoolean(properties.getProperty(KEY_ENABLED), defaults.isEnabled()),
                normalize(properties.getProperty(KEY_BROKER), defaults.getBroker()),
                normalize(properties.getProperty(KEY_TOPIC), defaults.getTopic()),
                normalize(properties.getProperty(KEY_CLIENT_ID), defaults.getClientId()),
                normalize(properties.getProperty(KEY_USERNAME), defaults.getUsername()),
                normalize(properties.getProperty(KEY_PASSWORD), defaults.getPassword()),
                parseQos(properties.getProperty(KEY_QOS), defaults.getQos())
        );
    }

    /**
     * Salva la configurazione runtime in modo atomico: scrive prima un file temporaneo,
     * poi lo sostituisce al file principale.
     */
    public synchronized void saveConfig(MqttRuntimeConfig config) {
        if (config == null) {
            throw new IllegalArgumentException("Configurazione MQTT mancante");
        }
        validate(config);

        Properties properties = new Properties();
        properties.setProperty(KEY_ENABLED, Boolean.toString(config.enabled()));
        properties.setProperty(KEY_BROKER, safe(config.broker()));
        properties.setProperty(KEY_TOPIC, safe(config.topic()));
        properties.setProperty(KEY_CLIENT_ID, safe(config.clientId()));
        properties.setProperty(KEY_USERNAME, safe(config.username()));
        properties.setProperty(KEY_PASSWORD, safe(config.password()));
        properties.setProperty(KEY_QOS, Integer.toString(config.qos()));
        writeProperties(properties);
    }

    public Path getConfigPath() {
        return configPath;
    }

    public synchronized long getLastModifiedMillis() {
        try {
            return Files.exists(configPath) ? Files.getLastModifiedTime(configPath).toMillis() : 0L;
        } catch (IOException e) {
            logger.warn("Impossibile leggere timestamp configurazione MQTT: {}", e.getMessage());
            return 0L;
        }
    }

    private void initStorage() {
        try {
            Path parent = configPath.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            if (!Files.exists(configPath)) {
                saveConfig(defaultConfig());
            }
        } catch (Exception e) {
            throw new IllegalStateException("Impossibile inizializzare configurazione MQTT runtime: " + configPath, e);
        }
    }

    private MqttRuntimeConfig defaultConfig() {
        return new MqttRuntimeConfig(
                defaults.isEnabled(),
                defaults.getBroker(),
                defaults.getTopic(),
                defaults.getClientId(),
                defaults.getUsername(),
                defaults.getPassword(),
                defaults.getQos()
        );
    }

    private Properties readProperties() {
        Properties properties = new Properties();
        if (!Files.exists(configPath)) {
            return properties;
        }
        try (InputStream input = Files.newInputStream(configPath)) {
            properties.load(input);
        } catch (IOException e) {
            logger.warn("Configurazione MQTT runtime non leggibile, uso fallback: {}", e.getMessage());
        }
        return properties;
    }

    private void writeProperties(Properties properties) {
        Path tempPath = configPath.resolveSibling(configPath.getFileName() + ".tmp");
        try (OutputStream output = Files.newOutputStream(tempPath)) {
            properties.store(output, "MQTT runtime configuration");
            Files.move(tempPath, configPath, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
        } catch (IOException atomicMoveError) {
            try {
                Files.move(tempPath, configPath, StandardCopyOption.REPLACE_EXISTING);
            } catch (IOException fallbackMoveError) {
                throw new IllegalStateException("Impossibile scrivere configurazione MQTT runtime: " + configPath, fallbackMoveError);
            }
        }
    }

    private void validate(MqttRuntimeConfig config) {
        if (config.enabled()) {
            if (config.broker() == null || config.broker().isBlank()) {
                throw new IllegalArgumentException("Broker MQTT obbligatorio");
            }
            if (config.topic() == null || config.topic().isBlank()) {
                throw new IllegalArgumentException("Topic MQTT obbligatorio");
            }
            if (config.clientId() == null || config.clientId().isBlank()) {
                throw new IllegalArgumentException("Client ID MQTT obbligatorio");
            }
        }
        if (config.qos() < 0 || config.qos() > 2) {
            throw new IllegalArgumentException("QoS MQTT deve essere 0, 1 o 2");
        }
    }

    private boolean parseBoolean(String value, boolean fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return Boolean.parseBoolean(value.trim());
    }

    private int parseQos(String value, int fallback) {
        if (value == null || value.isBlank()) {
            return fallback;
        }
        try {
            int qos = Integer.parseInt(value.trim());
            return qos >= 0 && qos <= 2 ? qos : fallback;
        } catch (NumberFormatException e) {
            return fallback;
        }
    }

    private String normalize(String value, String fallback) {
        if (value == null) {
            return fallback == null ? "" : fallback;
        }
        return value.trim();
    }

    private String safe(String value) {
        return value == null ? "" : value.trim();
    }
}
