package it.polimi.bsnwebapp.Service;

import java.io.IOException;
import java.time.LocalDateTime;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.event.EventListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import it.polimi.bsnwebapp.Controller.sse.SensoriSseController;
import it.polimi.bsnwebapp.Model.Entities.Campagna;
import it.polimi.bsnwebapp.Model.Entities.CampagnaSensore;
import it.polimi.bsnwebapp.Model.Entities.TipoCampagna;
import it.polimi.bsnwebapp.Model.Enum.StatoCampagna;
import it.polimi.bsnwebapp.Repository.CampagnaRepository;
import it.polimi.bsnwebapp.Repository.CampagnaSensoreRepository;

/**
 * Service dedicato all'avvio asincrono delle campagne con transazione attiva.
 * Garantisce una sessione Hibernate valida durante la costruzione degli argomenti.
 */

@Service
public class CampagnaAvvioService {

    private static final Logger logger = LoggerFactory.getLogger(CampagnaAvvioService.class);
    private static final Pattern PRECHECK_FAILED_PATTERN = Pattern.compile(
        "PRECHECK_FAILED\\[(?<code>[^\\]]+)]\\s+app='(?<appId>[^']+)'",
        Pattern.CASE_INSENSITIVE | Pattern.DOTALL);
    private static final Pattern USER_LINKED_PARAMS_DETAILS_PATTERN = Pattern.compile(
        "expected\\s+(?<expected>\\d+)\\s+resources,\\s+got\\s+(?<got>\\d+)\\s+from\\s+parameter\\s+'imunames'",
        Pattern.CASE_INSENSITIVE);
    private static final Pattern USER_LINKED_PARAMS_UNKNOWN_RESOURCE_PATTERN = Pattern.compile(
        "references\\s+unknown\\s+resource\\s+'(?<resource>[^']+)'",
        Pattern.CASE_INSENSITIVE);
    //mappa campagnaId -> appId per tenere traccia delle associazioni e poterle stoppare correttamente in caso di stop manuale o watchdog
    private final Map<Long, String> campagnaAppMap = new ConcurrentHashMap<>();

    @Autowired
    private CampagnaRepository campagnaRepository;

    @Autowired
    private CampagnaSensoreRepository campagnaSensoreRepository;

    @Autowired
    private CampagnaProcessManager processManager;

    @Autowired
    private RrmConnectionService rrmConnectionService;

    @Autowired
    private AppParamJsonService appParamJsonService;

    @Autowired
    private SensoriSseController sensoriSseController;

    @Async("applicationTaskExecutor")
    @Transactional
    public void avviaCampagnaAsync(Long campagnaId) {
        try {
            Campagna campagna = campagnaRepository.findById(campagnaId)
                    .orElseThrow(() -> new IllegalStateException("Campagna non trovata con ID: " + campagnaId));

            if (campagna.getStato() != StatoCampagna.AVVIO_IN_CORSO) {
                logger.info("Avvio saltato: campagna {} in stato {}", campagnaId, campagna.getStato());
                return;
            }

            avviaProcessiCampagna(campagna);
            aggiornaStatoDopoAvvio(campagnaId);
        } catch (Exception e) {
            logger.error("Errore durante l'avvio asincrono campagna {}", campagnaId, e);
            aggiornaStatoAvvioFallito(campagnaId, e);
        }
    }

    /**
     * Richiede l'avvio dell'applicazione corrispondente alla campagna tramite RRM Global.
     * Invece di eseguire uno script Python locale costruisce una mappa di argomenti
     * (inclusi sensori e parametri salvati su SettingApplication) e invia il
     * messaggio {@code GUI_START_APPLICATION} usando {@link RrmConnectionService}.
     * Il metodo attende la risposta {@code GLOBAL_START_APPLICATION_RESPONSE} e,
     * in caso di successo, segna internamente la campagna come attiva (tramite
    * {@link CampagnaProcessManager}) per evitare avvii duplicati. Se la conferma
    * non arriva entro il timeout configurato o lo stato non è "OK" viene lanciata un'eccezione.
     *
     * @param campagna entita campagna gia salvata con id valorizzato
     * @throws IOException se l'avvio tramite RRM fallisce o scade il timeout
     */
    private void avviaProcessiCampagna(Campagna campagna) throws IOException {
        if (campagna == null || campagna.getId() == null) {
            throw new IllegalArgumentException("Campagna non valida");
        }
        Long id = campagna.getId();

        if (processManager.isCampagnaAttiva(id)) {
            throw new IllegalStateException("Impossibile avviare: campagna già registrata come attiva.");
        }

        Set<TipoCampagna> tipi = campagna.getTipi();
        if (tipi == null || tipi.isEmpty()) {
            throw new IllegalStateException("La campagna non ha nessun Tipo associato (nessuna applicazione da lanciare).");
        }
        if (tipi.size() != 1) {
            throw new IllegalStateException("La campagna deve avere un solo tipo/appID associato.");
        }

        TipoCampagna tipo = tipi.iterator().next();
        String appId = campagna.getScriptFileName();
        if (appId == null || appId.isBlank()) {
            appId = tipo.getScriptFileName();
        }
        if (appId == null || appId.isBlank()) {
            throw new IllegalStateException("ID applicazione mancante per il tipo selezionato.");
        }

        try {
            logger.info("Richiesta avvio applicazione '{}' per campagna {} (Tipo: {})", appId, id, tipo.getCodice());

            Map<String, Object> args = new HashMap<>();

            List<CampagnaSensore> sensoriAttivi = campagnaSensoreRepository.findByCampagna_Id(id).stream()
                    .filter(CampagnaSensore::isAttivo)
                    .filter(cs -> cs.getSensore().getCodice() != null
                            && !cs.getSensore().getCodice().isBlank())
                    .sorted((left, right) -> left.getSensore().getId()
                            .compareTo(right.getSensore().getId()))
                    .collect(Collectors.toList());
            String sensoriDash = sensoriAttivi.stream()
                    .map(cs -> cs.getSensore().getCodice())
                    .collect(Collectors.joining("-"));
            if (sensoriDash.isBlank()) {
                throw new IllegalStateException("Lista sensori vuota: selezionare almeno un sensore valido");
            }
            args.put("imunames", sensoriDash);
            String peripheralLocations = sensoriAttivi.stream()
                    .map(CampagnaSensore::getLocation)
                    .map(location -> location == null ? "" : location)
                    .collect(Collectors.joining("-"));
            boolean hasAllPeripheralLocations = !sensoriAttivi.isEmpty()
                    && sensoriAttivi.stream()
                            .map(CampagnaSensore::getLocation)
                            .allMatch(location -> location != null && !location.isBlank());

            if (campagna.getFrequenza() != null) {
                args.put("samplingfreq", campagna.getFrequenza());
            }
            if (campagna.getConnettivita() != null) {
                args.put("connectivity", campagna.getConnettivita().name());
            }
            if (campagna.getId() != null) {
                args.put("campaignname", String.valueOf(id));
            }

            Map<String, String> appParams = appParamJsonService.getAllAppValues(appId);
            if (!appParams.isEmpty()) {
                args.putAll(appParams);
            }

            Map<String, String> campaignOverrides = appParamJsonService.consumeCampaignOverrides(id);
            if (!campaignOverrides.isEmpty()) {
                args.putAll(campaignOverrides);
            }
            // Parametro opzionale gestito dalla campagna: viene inviato solo se tutte le location sono presenti.
            args.remove("peripheral_locations");
            if (hasAllPeripheralLocations) {
                args.put("peripheral_locations", peripheralLocations);
            }

            logger.info("Avvio applicazione - AppID: {}, Args: {}", appId, args);
            CompletableFuture<it.polimi.bsnwebapp.communication.Messages.GlobalStartApplicationResponse> future
                    = rrmConnectionService.startApplication(appId, args);

            it.polimi.bsnwebapp.communication.Messages.GlobalStartApplicationResponse resp;
            try {
                resp = future.get(Utils.RRM_START_APPLICATION_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            } catch (Exception e) {
                throw new IOException("Timeout o errore durante l'avvio dell'applicazione su RRM", e);
            }

            String nonOkMessage = buildPrecheckUserMessage(resp.status, appId);
            if (nonOkMessage != null) {
                logger.warn("Avvio applicazione fallito con messaggio precheck: {}", nonOkMessage);
                throw new IOException(nonOkMessage);
            }

            if (!"OK".equals(resp.status)) {
                throw new IOException("RRM ha risposto con stato non valido: " + resp.status);
            }

            processManager.registraProcesso(id, null);

            //Salva assocciazione campagna-appID e l'appID della resp per poi stopparla correttamente
            campagnaAppMap.put(id, resp.appID);
        } catch (Exception e) {
            logger.error("Errore durante l'avvio applicazione RRM", e);
            processManager.pulisciMemoriaCampagna(id);
            throw e instanceof IOException ? (IOException) e : new IOException(e);
        }
    }

    private void aggiornaStatoDopoAvvio(Long campagnaId) {
        campagnaRepository.findById(campagnaId).ifPresent(campagna -> {
            if (campagna.getStato() != StatoCampagna.AVVIO_IN_CORSO) {
                processManager.pulisciMemoriaCampagna(campagnaId);
                logger.warn("Avvio completato ma campagna {} in stato {}. Pulizia memoria processi.",
                        campagnaId, campagna.getStato());
                return;
            }
            campagna.setStato(StatoCampagna.IN_CORSO);
            campagna.setDataInizio(LocalDateTime.now());
            campagnaRepository.save(campagna);
        });
    }

    private void aggiornaStatoAvvioFallito(Long campagnaId, Exception e) {
        campagnaRepository.findById(campagnaId).ifPresent(campagna -> {
            if (campagna.getStato() != StatoCampagna.AVVIO_IN_CORSO) {
                return;
            }
            campagna.setStato(StatoCampagna.AVVIO_FALLITO);
            String reason = (e.getMessage() == null || e.getMessage().isBlank())
                    ? "Errore sconosciuto"
                    : e.getMessage();
            campagna.setNote(appendSystemNote(campagna.getNote(), "Avvio fallito: " + reason));
            campagnaRepository.save(campagna);
            sensoriSseController.notifyAllClients();
        });
    }

    private String appendSystemNote(String note, String message) {
        String base = note == null ? "" : note;
        String separator = base.isBlank() ? "" : "\n";
        return base + separator + "[SYSTEM]: " + message;
    }

    private String buildPrecheckUserMessage(String status, String fallbackAppId) {
        if (status == null || status.isBlank()) {
            return null;
        }

        String normalizedStatus = status.trim();
        Matcher precheckMatcher = PRECHECK_FAILED_PATTERN.matcher(normalizedStatus);
        if (!precheckMatcher.find()) {
            return null;
        }

        String code = precheckMatcher.group("code");
        if (code == null || !"USER_LINKED_PARAMS".equalsIgnoreCase(code.trim())) {
            return null;
        }

        Matcher detailsMatcher = USER_LINKED_PARAMS_DETAILS_PATTERN.matcher(normalizedStatus);
        if (!detailsMatcher.find()) {
            Matcher unknownResourceMatcher = USER_LINKED_PARAMS_UNKNOWN_RESOURCE_PATTERN.matcher(normalizedStatus);
            if (unknownResourceMatcher.find()) {
                String resource = unknownResourceMatcher.group("resource");
                if (resource != null && !resource.isBlank()) {
                    return "Avvio Fallito: Sensore " + resource + " non riconosciuto.";
                }
            }
            return null;
        }

        String expected = detailsMatcher.group("expected");
        String got = detailsMatcher.group("got");
        String appId = precheckMatcher.group("appId");
        if (appId == null || appId.isBlank()) {
            appId = fallbackAppId;
        }
        if (appId == null || appId.isBlank()) {
            appId = "sconosciuta";
        }

        return "Avvio Fallito: L'applicazione " + appId + " richiede " + expected
                + " sensori ma ne sono stati selezionati " + got + ".";
    }

    // Metodo di utilità per recuperare l'appID associato a una campagna, usato dal watchdog per stoppare correttamente in caso di disallineamento
    public String getAppIdPerCampagna(Long campagnaId) {
        return campagnaAppMap.get(campagnaId);  
    }

    //Remove associazione campagna-appID, usato in caso di stop manuale o disallineamento watchdog
    public void rimuoviAppIdPerCampagna(Long campagnaId) {
        campagnaAppMap.remove(campagnaId); 
    }

    @EventListener
    @Transactional
    public void terminaCampagnaPerChiusuraAutonoma(RrmApplicationSelfStoppedEvent event) {
        if (event == null || event.appId() == null || event.appId().isBlank()) {
            return;
        }

        Long campagnaId = findCampagnaIdByAppId(event.appId());
        if (campagnaId == null) {
            logger.warn("Chiusura autonoma RRM ricevuta per app '{}' ma nessuna campagna associata trovata.",
                    event.appId());
            return;
        }

        campagnaRepository.findById(campagnaId).ifPresent(campagna -> {
            if (campagna.getStato() != StatoCampagna.IN_CORSO
                    && campagna.getStato() != StatoCampagna.AVVIO_IN_CORSO) {
                processManager.pulisciMemoriaCampagna(campagnaId);
                rimuoviAppIdPerCampagna(campagnaId);
                return;
            }

            campagna.setStato(StatoCampagna.TERMINATA);
            campagna.setDataFine(LocalDateTime.now());
            String nodeInfo = event.nodeId() == null || event.nodeId().isBlank()
                    ? ""
                    : " sul nodo " + event.nodeId();
            campagna.setNote(appendSystemNote(campagna.getNote(),
                    "Terminata automaticamente: applicazione " + event.appId()
                            + " chiusa autonomamente" + nodeInfo + "."));
            campagnaRepository.save(campagna);
            processManager.pulisciMemoriaCampagna(campagnaId);
            rimuoviAppIdPerCampagna(campagnaId);
            sensoriSseController.notifyAllClients();
            logger.info("Campagna {} terminata per chiusura autonoma dell'app '{}'.",
                    campagnaId, event.appId());
        });
    }

    private Long findCampagnaIdByAppId(String appId) {
        String normalizedAppId = normalizeAppId(appId);
        if (normalizedAppId == null || normalizedAppId.isBlank()) {
            return null;
        }

        return campagnaAppMap.entrySet().stream()
                .filter(entry -> normalizedAppId.equals(normalizeAppId(entry.getValue())))
                .map(Map.Entry::getKey)
                .findFirst()
                .orElse(null);
    }

    private String normalizeAppId(String appId) {
        if (appId == null) {
            return null;
        }
        String value = appId.trim();
        int len = value.length();
        if (len < 4 || value.charAt(0) != '(' || value.charAt(len - 1) != ')') {
            return value;
        }
        int i = 1;
        while (i < len - 1 && Character.isWhitespace(value.charAt(i))) {
            i++;
        }
        if (i >= len - 1) {
            return value;
        }
        char quote = value.charAt(i);
        if (quote != '\'' && quote != '"') {
            return value;
        }
        int start = ++i;
        while (i < len - 1) {
            char c = value.charAt(i);
            if (c == '\\') {
                i += 2;
                continue;
            }
            if (c == quote) {
                return value.substring(start, i);
            }
            i++;
        }
        return value;
    }
}
