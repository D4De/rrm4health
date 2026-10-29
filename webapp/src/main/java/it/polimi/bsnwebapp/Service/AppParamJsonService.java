package it.polimi.bsnwebapp.Service;

import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;

import com.fasterxml.jackson.databind.ObjectMapper;

@Service
public class AppParamJsonService {

    private static final Logger logger = LoggerFactory.getLogger(AppParamJsonService.class);

    private final ObjectMapper objectMapper;
    private final Path jsonPath;

    public AppParamJsonService(ObjectMapper objectMapper,
                               @Value("${app.params.json.file:./data/app-params-config.json}") String jsonFilePath) {
        this.objectMapper = objectMapper;
        this.jsonPath = Paths.get(jsonFilePath).toAbsolutePath().normalize();
        initStorage();
    }

    public synchronized AppConfig getAppConfig(String appId) {
        if (appId == null || appId.isBlank()) {
            return new AppConfig();
        }
        RootData root = readRoot();
        AppConfig cfg = root.apps.get(appId);
        if (cfg == null) {
            return new AppConfig();
        }
        if (cfg.values == null) cfg.values = new LinkedHashMap<>();
        if (cfg.editableKeys == null) cfg.editableKeys = new ArrayList<>();
        return cfg;
    }

    public synchronized void saveAppConfig(String appId,
                                           Map<String, String> values,
                                           List<String> editableKeys) {
        if (appId == null || appId.isBlank()) {
            return;
        }
        RootData root = readRoot();
        AppConfig cfg = new AppConfig();
        cfg.values = values == null ? new LinkedHashMap<>() : new LinkedHashMap<>(values);
        cfg.editableKeys = editableKeys == null ? new ArrayList<>() : new ArrayList<>(editableKeys);
        root.apps.put(appId, cfg);
        writeRoot(root);
    }

    public synchronized void resetAppConfig(String appId) {
        if (appId == null || appId.isBlank()) {
            return;
        }
        RootData root = readRoot();
        root.apps.remove(appId);
        writeRoot(root);
    }

    public synchronized Map<String, String> getEditableParamsForUser(String appId) {
        AppConfig cfg = getAppConfig(appId);
        Map<String, String> out = new LinkedHashMap<>();
        for (String key : cfg.editableKeys) {
            if (key == null || key.isBlank()) continue;
            out.put(key, cfg.values.getOrDefault(key, ""));
        }
        return out;
    }

    public synchronized Map<String, String> getAllAppValues(String appId) {
        AppConfig cfg = getAppConfig(appId);
        return new LinkedHashMap<>(cfg.values);
    }

    public synchronized Map<String, String> sanitizeUserOverrides(String appId, Map<String, String> rawOverrides) {
        Map<String, String> clean = new LinkedHashMap<>();
        if (rawOverrides == null || rawOverrides.isEmpty()) {
            return clean;
        }
        AppConfig cfg = getAppConfig(appId);
        List<String> editable = cfg.editableKeys == null ? List.of() : cfg.editableKeys;
        for (Map.Entry<String, String> e : rawOverrides.entrySet()) {
            String key = e.getKey();
            if (key == null || key.isBlank()) continue;
            if (!editable.contains(key)) continue;
            clean.put(key, e.getValue() == null ? "" : e.getValue());
        }
        return clean;
    }

    public synchronized void saveCampaignOverrides(Long campaignId, Map<String, String> overrides) {
        if (campaignId == null) {
            return;
        }
        RootData root = readRoot();
        if (overrides == null || overrides.isEmpty()) {
            root.campaignOverrides.remove(String.valueOf(campaignId));
        } else {
            root.campaignOverrides.put(String.valueOf(campaignId), new LinkedHashMap<>(overrides));
        }
        writeRoot(root);
    }

    public synchronized Map<String, String> consumeCampaignOverrides(Long campaignId) {
        if (campaignId == null) {
            return new LinkedHashMap<>();
        }
        RootData root = readRoot();
        Map<String, String> values = root.campaignOverrides.remove(String.valueOf(campaignId));
        writeRoot(root);
        return values == null ? new LinkedHashMap<>() : values;
    }

    private void initStorage() {
        try {
            Path parent = jsonPath.getParent();
            if (parent != null) {
                Files.createDirectories(parent);
            }
            if (!Files.exists(jsonPath)) {
                writeRoot(new RootData());
            }
        } catch (IOException e) {
            throw new IllegalStateException("Impossibile inizializzare storage JSON parametri app: " + jsonPath, e);
        }
    }

    private RootData readRoot() {
        try {
            if (!Files.exists(jsonPath)) {
                return new RootData();
            }
            RootData root = objectMapper.readValue(jsonPath.toFile(), RootData.class);
            if (root == null) {
                return new RootData();
            }
            if (root.apps == null) root.apps = new LinkedHashMap<>();
            if (root.campaignOverrides == null) root.campaignOverrides = new LinkedHashMap<>();
            return root;
        } catch (Exception e) {
            logger.warn("JSON parametri app non leggibile, uso storage vuoto: {}", e.getMessage());
            return new RootData();
        }
    }

    private void writeRoot(RootData root) {
        try {
            objectMapper.writerWithDefaultPrettyPrinter().writeValue(jsonPath.toFile(), root);
        } catch (IOException e) {
            throw new IllegalStateException("Impossibile scrivere JSON parametri app: " + jsonPath, e);
        }
    }

    public static class RootData {
        public Map<String, AppConfig> apps = new LinkedHashMap<>();
        public Map<String, Map<String, String>> campaignOverrides = new LinkedHashMap<>();
    }

    public static class AppConfig {
        public Map<String, String> values = new LinkedHashMap<>();
        public List<String> editableKeys = new ArrayList<>();
    }
}
