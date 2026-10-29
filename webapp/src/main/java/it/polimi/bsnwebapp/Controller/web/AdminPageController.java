package it.polimi.bsnwebapp.Controller.web;

import java.net.URI;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;

import org.springframework.stereotype.Controller;
import org.springframework.ui.Model;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.servlet.mvc.support.RedirectAttributes;

import it.polimi.bsnwebapp.DTO.request.SensoreCreateRequest;
import it.polimi.bsnwebapp.Config.MqttRuntimeConfig;
import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import it.polimi.bsnwebapp.Model.Enum.StatoCampagna;
import it.polimi.bsnwebapp.Model.Enum.TipoMisura;
import it.polimi.bsnwebapp.Repository.CampagnaRepository;
import it.polimi.bsnwebapp.Service.AppParamJsonService;
import it.polimi.bsnwebapp.Service.ApplicazioneDescrittoreService;
import it.polimi.bsnwebapp.Service.DatabaseConfigService;
import it.polimi.bsnwebapp.Service.MqttRuntimeConfigService;
import it.polimi.bsnwebapp.Service.MqttSseService;
import it.polimi.bsnwebapp.Service.ScriptCatalogService;
import it.polimi.bsnwebapp.Service.SensoreService;
import it.polimi.bsnwebapp.Service.SettingApplicationService;
import lombok.RequiredArgsConstructor;

/**
 * Controller MVC per la pagina di amministrazione.
 * Prepara i dati per la view /admin (script disponibili e sensori) e gestisce upload script e creazione sensori.
 * Le operazioni sono riservate agli utenti con ruolo USER_DEV.
 */

@Controller
@RequiredArgsConstructor
@RequestMapping("/admin")
public class AdminPageController {

    private final ScriptCatalogService scriptCatalogService;
    private final SensoreService sensoreService;
    private final DatabaseConfigService databaseConfigService;
    private final ApplicazioneDescrittoreService applicazioneDescrittoreService;
    private final AppParamJsonService appParamJsonService;
    private final SettingApplicationService settingApplicationService;
    private final MqttRuntimeConfigService mqttRuntimeConfigService;
    private final MqttSseService mqttSseService;
    private final CampagnaRepository campagnaRepository;

    @GetMapping
    public String adminRoot() {
        return "redirect:/admin/scripts";
    }

    @GetMapping("/scripts")
    public String admin(Model model) {
        model.addAttribute("scriptsAvailable", scriptCatalogService.listScripts());
        model.addAttribute("descrittoriDisponibili", applicazioneDescrittoreService.listaDescrittori());
        String selected = settingApplicationService.getValue("selectedAppId");
        model.addAttribute("selectedAppId", selected);

        // prepare parameters for the selected application (if any)
        if (selected != null && !selected.isBlank()) {
            Map<String, Object> params = applicazioneDescrittoreService.getDescrittoreByAppId(selected) != null
                    ? applicazioneDescrittoreService.getDescrittoreByAppId(selected).getParametri()
                    : null;
            // filter out parameters that should not be shown/edited here
            Map<String, Object> filtered = new LinkedHashMap<>();
            if (params != null) {
                for (Map.Entry<String, Object> e : params.entrySet()) {
                    String k = e.getKey();
                    if (k == null) continue;
                    String lower = k.toLowerCase();
                    if (lower.equals("imunames") || lower.equals("campaignname")
                            || lower.equals("samplingfreq") || lower.equals("peripheral_locations"))
                    {
                        continue;
                    }
                    filtered.put(k, e.getValue());
                }
            }
            model.addAttribute("appParameters", filtered);

            AppParamJsonService.AppConfig saved = appParamJsonService.getAppConfig(selected);

            // load persisted values (if any) for these parameters from JSON backend storage
            Map<String, String> currentValues = new HashMap<>();
            for (Map.Entry<String, Object> entry : filtered.entrySet()) {
                String key = entry.getKey();
                String fallback = entry.getValue() == null ? "" : String.valueOf(entry.getValue());
                String fromJson = saved.values.get(key);
                currentValues.put(key, fromJson != null ? fromJson : fallback);
            }
            model.addAttribute("appParamValues", currentValues);
            model.addAttribute("appUserEditableKeys", saved.editableKeys);

        }
        model.addAttribute("activeTab", "scripts");

        return "admin-scripts";
    }

    @GetMapping("/sensori")
    public String adminSensori(Model model) {
        model.addAttribute("sensori", sensoreService.listaSensori());
        model.addAttribute("activeTab", "sensori");
        return "admin-sensori";
    }

    @GetMapping("/database")
    public String adminDatabase(Model model) {
        model.addAttribute("databaseConfigs", databaseConfigService.listAll());
        model.addAttribute("activeTab", "database");
        return "admin-database";
    }

    @GetMapping("/mqtt")
    public String adminMqtt(Model model) {
        MqttRuntimeConfig mqttConfig = mqttRuntimeConfigService.getConfig();
        model.addAttribute("mqttConfig", mqttConfig);
        model.addAttribute("mqttBrokerHost", extractBrokerHost(mqttConfig.broker()));
        model.addAttribute("mqttBrokerPort", extractBrokerPort(mqttConfig.broker()));
        model.addAttribute("mqttConfigPath", mqttRuntimeConfigService.getConfigPath().toString());
        long activeCampaigns = countActiveCampaigns();
        model.addAttribute("mqttLocked", activeCampaigns > 0);
        model.addAttribute("activeCampaignsCount", activeCampaigns);
        model.addAttribute("activeTab", "mqtt");
        return "admin-mqtt";
    }

    @PostMapping("/scripts")
    public String selectApplication(@RequestParam("appId") String appId,
                                     RedirectAttributes redirectAttributes) {
        try {
            if (appId == null || appId.isBlank()) {
                redirectAttributes.addFlashAttribute("scriptUploadError", "Selezionare un'applicazione.");
            } else {
                settingApplicationService.setValue("selectedAppId", appId);
                redirectAttributes.addFlashAttribute("scriptUploadSuccess", "Applicazione selezionata: " + appId);
            }
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("scriptUploadError", e.getMessage());
        }
        return "redirect:/admin/scripts";
    }

    @PostMapping("/sensori")
    public String createSensore(@RequestParam String codice,
                                @RequestParam String nome,
                                @RequestParam String tipo,
                                @RequestParam Protocollo protocolloDefault,
                                @RequestParam(required = false) List<Protocollo> protocolliSupportati,
                                @RequestParam(required = false) List<TipoMisura> misureSupportate,
                                RedirectAttributes redirectAttributes) {
        try {
            SensoreCreateRequest request = new SensoreCreateRequest();
            request.setCodice(codice);
            request.setNome(nome);
            request.setTipo(tipo);
            request.setProtocolloDefault(protocolloDefault);
            request.setProtocolliSupportati(protocolliSupportati == null ? null : Set.copyOf(protocolliSupportati));
            request.setMisureSupportate(misureSupportate == null ? null : Set.copyOf(misureSupportate));
            sensoreService.creaSensore(request);
            redirectAttributes.addFlashAttribute("sensoreSuccess", "Sensore creato con successo.");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("sensoreError", e.getMessage());
        }
        return "redirect:/admin/sensori";
    }

    @PostMapping("/sensori/{id}/elimina")
    public String deleteSensore(@PathVariable Long id,
                                RedirectAttributes redirectAttributes) {
        try {
            sensoreService.eliminaSensore(id);
            redirectAttributes.addFlashAttribute("sensoreSuccess", "Sensore eliminato con successo.");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("sensoreError", e.getMessage());
        }
        return "redirect:/admin/sensori";
    }

    @PostMapping("/database")
    public String createDatabase(@RequestParam String nome,
                                 @RequestParam String host,
                                 @RequestParam String dbName,
                                 RedirectAttributes redirectAttributes) {
        try {
            databaseConfigService.create(nome, host, dbName);
            redirectAttributes.addFlashAttribute("databaseSuccess", "Database aggiunto con successo.");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("databaseError", e.getMessage());
        }
        return "redirect:/admin/database";
    }

    @PostMapping("/database/{id}/elimina")
    public String deleteDatabase(@PathVariable Long id,
                                 RedirectAttributes redirectAttributes) {
        try {
            databaseConfigService.delete(id);
            redirectAttributes.addFlashAttribute("databaseSuccess", "Database eliminato con successo.");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("databaseError", e.getMessage());
        }
        return "redirect:/admin/database";
    }

    @PostMapping("/mqtt")
    public String saveMqttConfig(@RequestParam(value = "enabled", required = false) String enabled,
                                 @RequestParam String brokerHost,
                                 @RequestParam int brokerPort,
                                 @RequestParam String topic,
                                 @RequestParam String clientId,
                                 @RequestParam(required = false) String username,
                                 @RequestParam(required = false) String password,
                                 @RequestParam(defaultValue = "0") int qos,
                                 RedirectAttributes redirectAttributes) {
        try {
            if (hasActiveCampaigns()) {
                redirectAttributes.addFlashAttribute(
                        "mqttError",
                        "Configurazione MQTT non modificabile: sono presenti campagne in avvio o in corso."
                );
                return "redirect:/admin/mqtt";
            }
            String broker = buildTcpBroker(brokerHost, brokerPort);
            MqttRuntimeConfig config = new MqttRuntimeConfig(
                    enabled != null,
                    broker,
                    topic,
                    clientId,
                    username,
                    password,
                    qos
            );
            mqttRuntimeConfigService.saveConfig(config);
            mqttSseService.reloadConfig();
            redirectAttributes.addFlashAttribute("mqttSuccess", "Configurazione MQTT salvata.");
        } catch (Exception e) {
            redirectAttributes.addFlashAttribute("mqttError", e.getMessage());
        }
        return "redirect:/admin/mqtt";
    }

    private String extractBrokerHost(String broker) {
        try {
            String host = URI.create(broker).getHost();
            return host == null || host.isBlank() ? "localhost" : host;
        } catch (IllegalArgumentException e) {
            return "localhost";
        }
    }

    private int extractBrokerPort(String broker) {
        try {
            int port = URI.create(broker).getPort();
            return port > 0 ? port : 1883;
        } catch (IllegalArgumentException e) {
            return 1883;
        }
    }

    private String buildTcpBroker(String brokerHost, int brokerPort) {
        if (brokerHost == null || brokerHost.isBlank()) {
            throw new IllegalArgumentException("Host MQTT obbligatorio");
        }
        if (brokerPort < 1 || brokerPort > 65535) {
            throw new IllegalArgumentException("La porta MQTT deve essere compresa tra 1 e 65535");
        }

        String host = brokerHost.trim();
        if (host.contains("://") || host.contains("/") || host.contains(" ")) {
            throw new IllegalArgumentException("Inserire soltanto l'host o l'indirizzo IP MQTT");
        }
        if (host.contains(":") && !(host.startsWith("[") && host.endsWith("]"))) {
            host = "[" + host + "]";
        }
        return "tcp://" + host + ":" + brokerPort;
    }

    @PostMapping("/scripts/params")
    public String saveAppParameters(@RequestParam("appId") String appId,
                                    @RequestParam(value = "editableKeys", required = false) List<String> editableKeys,
                                    @RequestParam Map<String, String> allParams,
                                    RedirectAttributes redirectAttributes) {
        try {
            if (appId == null || appId.isBlank()) {
                redirectAttributes.addFlashAttribute("scriptUploadError", "App non valida.");
                return "redirect:/admin/scripts";
            }

            List<String> excluded = List.of(
                    "imunames", "campaignname", "samplingfreq",
                    "peripheral_locations", "appid", "editablekeys");
            Map<String, String> values = new LinkedHashMap<>();

            for (Map.Entry<String, String> e : allParams.entrySet()) {
                String key = e.getKey();
                if (key == null) continue;
                if (excluded.contains(key.toLowerCase())) continue;
                String value = e.getValue();
                values.put(key, value == null ? "" : value);
            }

            appParamJsonService.saveAppConfig(appId, values, editableKeys);

            redirectAttributes.addFlashAttribute("scriptUploadSuccess", "Parametri salvati per " + appId);
        } catch (Exception ex) {
            redirectAttributes.addFlashAttribute("scriptUploadError", ex.getMessage());
        }
        return "redirect:/admin/scripts";
    }

    @PostMapping("/scripts/params/reset")
    public String resetAppParameters(@RequestParam("appId") String appId,
                                     RedirectAttributes redirectAttributes) {
        if (appId == null || appId.isBlank()) {
            redirectAttributes.addFlashAttribute("scriptUploadError", "App non valida.");
        } else {
            appParamJsonService.resetAppConfig(appId);
            redirectAttributes.addFlashAttribute("scriptUploadSuccess", "Parametri resettati per " + appId);
        }
        return "redirect:/admin/scripts";
    }

    private boolean hasActiveCampaigns() {
        return campagnaRepository.existsByStatoIn(activeCampaignStates());
    }

    private long countActiveCampaigns() {
        return campagnaRepository.countByStatoIn(activeCampaignStates());
    }

    private List<StatoCampagna> activeCampaignStates() {
        return List.of(StatoCampagna.AVVIO_IN_CORSO, StatoCampagna.IN_CORSO);
    }
}
