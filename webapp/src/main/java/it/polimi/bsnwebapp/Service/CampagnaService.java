package it.polimi.bsnwebapp.Service;

import java.io.IOException;
import java.time.Duration;
import java.time.LocalDateTime;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

import it.polimi.bsnwebapp.Config.MqttProperties;
import it.polimi.bsnwebapp.Controller.sse.SensoriSseController;
import it.polimi.bsnwebapp.DTO.request.CampagnaCreateRequest;
import it.polimi.bsnwebapp.DTO.response.CampagnaResponse;
import it.polimi.bsnwebapp.Model.Entities.Campagna;
import it.polimi.bsnwebapp.Model.Entities.CampagnaSensore;
import it.polimi.bsnwebapp.Model.Entities.DatabaseConfig;
import it.polimi.bsnwebapp.Model.Entities.Persona;
import it.polimi.bsnwebapp.Model.Entities.Sensore;
import it.polimi.bsnwebapp.Model.Entities.TipoCampagna;
import it.polimi.bsnwebapp.Model.Entities.Utente;
import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import it.polimi.bsnwebapp.Model.Enum.StatoCampagna;
import it.polimi.bsnwebapp.Repository.CampagnaRepository;
import it.polimi.bsnwebapp.Repository.CampagnaSensoreRepository;
import it.polimi.bsnwebapp.Repository.DatabaseConfigRepository;
import it.polimi.bsnwebapp.Repository.PersonaRepository;
import it.polimi.bsnwebapp.Repository.SensoreRepository;
import it.polimi.bsnwebapp.Repository.TipoCampagnaRepository;
import it.polimi.bsnwebapp.Repository.UtenteRepository;

/**
 * Service principale per il ciclo di vita delle campagne.
 * Crea campagne, valida configurazioni, associa sensori e tipi, avvia script Python e aggiorna lo stato.
 * Converte Campagna in CampagnaResponse e gestisce terminazioni e pulizia processi.
 */

@Service
public class CampagnaService {

    @Autowired
    private ApplicazioneDescrittoreService applicazioneDescrittoreService;

    private static final Logger logger = LoggerFactory.getLogger(CampagnaService.class);

    //dice a Spring di cercare un oggetto già pronto (chiamato Bean) nella sua memoria e di "iniettarlo"
    // automaticamente nella tua classe, senza che tu debba fare new Classe()
    @Autowired
    private CampagnaRepository campagnaRepository;

    @Autowired
    private PersonaRepository personaRepository;

    @Autowired
    private UtenteRepository utenteRepository;

    @Autowired
    private TipoCampagnaRepository tipoCampagnaRepository;

    @Autowired
    private SensoreRepository sensoreRepository;

    @Autowired
    private CampagnaSensoreRepository campagnaSensoreRepository;

    @Autowired
    private CampagnaProcessManager processManager;

    @Autowired
    private DatabaseConfigRepository databaseConfigRepository;

    @Autowired
    private MqttProperties mqttProperties;

    @Autowired
    private CampagnaAvvioService campagnaAvvioService;

    @Autowired
    private RrmConnectionService rrmConnectionService;

    @Autowired
    private AppParamJsonService appParamJsonService;

    @Autowired
    private SensoriSseController sensoriSseController;

    // Percorso del folder contenente gli script Python letto da application.properties
    @Value("${app.python.scripts.folder}")
    private String scriptsFolder;

    /**
     * Crea e avvia immediatamente una nuova campagna.
     * Il flusso prevede: validazione input, caricamento entita, creazione campagna,
    * associazione sensori, salvataggio, ricarica relazioni e invio richiesta di avvio
    * applicazione RRM in background. La campagna viene salvata in stato AVVIO_IN_CORSO
    * con dataInizio impostata all'istante della richiesta di avvio.
     *
     * @param request Oggetto con i dati della campagna da creare
     * @return CampagnaResponse con tutti i dettagli della campagna avviata
     * @throws IOException Se l'avvio degli script fallisce
     */
    @Transactional
    public CampagnaResponse creaEAvviaCampagna(CampagnaCreateRequest request) throws IOException {
        logger.info("Creazione e avvio immediato campagna: {}", request.getNome());

        // Validazione dati obbligatori
        if (request.getNome() == null || request.getNome().isBlank()) {
            throw new IllegalArgumentException("Il nome della campagna è obbligatorio");
        }
        if (request.getIdPersona() == null) {
            throw new IllegalArgumentException("È obbligatorio specificare il paziente");
        }
        if (request.getIdUtenteCreatore() == null) {
            throw new IllegalArgumentException("È obbligatorio specificare l'utente creatore");
        }
        if (request.getIdTipoCampagna() == null) {
            throw new IllegalArgumentException("Selezionare un tipo di campagna");
        }
        if (request.getIdSensori() == null || request.getIdSensori().isEmpty()) {
            throw new IllegalArgumentException("Selezionare almeno un sensore");
        }
        Set<Long> sensoriInUso = new java.util.HashSet<>(campagnaSensoreRepository.findIdSensoriInUso());
        List<String> sensoriGiaOccupati = request.getIdSensori().stream()
                .filter(sensoriInUso::contains)
                .map(id -> sensoreRepository.findById(id)
                        .map(Sensore::getCodice)
                        .orElse(String.valueOf(id)))
                .toList();
        if (!sensoriGiaOccupati.isEmpty()) {
            throw new IllegalArgumentException("Sensori già in uso in un'altra campagna: "
                    + String.join(", ", sensoriGiaOccupati));
        }
        Map<Long, String> sensorLocations = request.getSensorLocations() == null
                ? Map.of()
                : request.getSensorLocations();
        boolean hasAnyLocation = request.getIdSensori().stream()
                .map(sensorLocations::get)
                .anyMatch(location -> location != null && !location.isBlank());
        boolean hasAllLocations = request.getIdSensori().stream()
                .map(sensorLocations::get)
                .allMatch(location -> location != null && !location.isBlank());
        if (hasAnyLocation && !hasAllLocations) {
            throw new IllegalArgumentException(
                    "Specificare la location per tutti i sensori selezionati oppure non specificarne nessuna");
        }
        for (Long idSensore : request.getIdSensori()) {
            String location = sensorLocations.get(idSensore);
            if (location != null && location.trim().length() > 255) {
                throw new IllegalArgumentException("La location dei sensori non può superare 255 caratteri");
            }
        }
        if (request.getFrequenza() == null || request.getFrequenza() <= 0) {
            throw new IllegalArgumentException("Specificare una frequenza di campionamento valida");
        }
        if (request.getDurata() != null && request.getDurata() <= 0) {
            throw new IllegalArgumentException("Specificare una durata timer valida");
        }
        if (request.getConnettivita() == null) {
            throw new IllegalArgumentException("Specificare la connettività");
        }
        if (request.getIdDatabase() == null || request.getIdDatabase() <= 0) {
            throw new IllegalArgumentException("Selezionare un database Influx");
        }

        // Recupero entità dal database
        Persona persona = personaRepository.findById(request.getIdPersona())
                .orElseThrow(() -> new IllegalArgumentException("Persona non trovata con ID: " + request.getIdPersona()));

        Utente utente = utenteRepository.findById(request.getIdUtenteCreatore())
                .orElseThrow(() -> new IllegalArgumentException("Utente non trovato con ID: " + request.getIdUtenteCreatore()));

        TipoCampagna tipo = tipoCampagnaRepository.findById(request.getIdTipoCampagna())
                .orElseThrow(() -> new IllegalArgumentException("Tipo campagna non trovato con ID: " + request.getIdTipoCampagna()));
        Set<TipoCampagna> tipi = new java.util.HashSet<>();
        tipi.add(tipo);

        List<Sensore> sensori = request.getIdSensori().stream()
            .map(idSensore -> {
                Sensore sensore = sensoreRepository.findById(idSensore)
                    .orElseThrow(() -> new IllegalArgumentException("Sensore non trovato con ID: " + idSensore));
                if (sensore.isEliminato()) {
                String label = (sensore.getCodice() == null || sensore.getCodice().isBlank())
                    ? String.valueOf(sensore.getId())
                    : sensore.getCodice();
                throw new IllegalArgumentException("Sensore non disponibile (archiviato): " + label);
                }
                return sensore;
            })
            .collect(Collectors.toList());

        List<String> incompatibili = sensori.stream()
                .filter(sensore -> !supportsProtocol(sensore, request.getConnettivita()))
                .map(sensore -> sensore.getCodice() == null ? String.valueOf(sensore.getId()) : sensore.getCodice())
                .collect(Collectors.toList());
        if (!incompatibili.isEmpty()) {
            throw new IllegalArgumentException("Sensori non compatibili con la connettivita selezionata: "
                    + String.join(", ", incompatibili));
        }

        // Creazione entità Campagna
        Campagna campagna = new Campagna();
        campagna.setNome(request.getNome());
        campagna.setNote(request.getNote());
        campagna.setPersona(persona);
        campagna.setUtenteCreatore(utente);
        campagna.setStato(StatoCampagna.AVVIO_IN_CORSO);
        campagna.setTipi(tipi);
        campagna.setDataInizio(LocalDateTime.now());
        campagna.setFrequenza(request.getFrequenza());
        campagna.setDurata(request.getDurata());
        campagna.setConnettivita(request.getConnettivita());
        DatabaseConfig dbConfig = databaseConfigRepository.findById(request.getIdDatabase())
                .orElseThrow(() -> new IllegalArgumentException("Database non trovato"));
        campagna.setDbHost(dbConfig.getHost());
        campagna.setDbName(dbConfig.getDbName());

        String scriptName = request.getScriptFileName();
        if (scriptName == null || scriptName.isBlank()) {
            scriptName = tipo.getScriptFileName();
        }
        if (scriptName == null || scriptName.isBlank()) {
            throw new IllegalArgumentException("Script/Application ID non valido per il tipo selezionato");
        }
        campagna.setScriptFileName(scriptName);

        // Salvataggio campagna per ottenere l'ID
        campagna = campagnaRepository.save(campagna);

        Map<String, String> cleanOverrides = appParamJsonService
            .sanitizeUserOverrides(scriptName, request.getUserAppParams());
        appParamJsonService.saveCampaignOverrides(campagna.getId(), cleanOverrides);

        // Creazione associazioni CampagnaSensore
        for (Sensore sensore : sensori) {
            CampagnaSensore cs = new CampagnaSensore(campagna, sensore, true);
            String location = sensorLocations.get(sensore.getId());
            cs.setLocation(location == null || location.isBlank() ? null : location.trim());
            campagnaSensoreRepository.save(cs);
        }

        // Ricarica la campagna per ottenere tutte le relazioni aggiornate
        campagna = campagnaRepository.findById(campagna.getId())
                .orElseThrow(() -> new IllegalStateException("Impossibile ricaricare la campagna appena creata"));

        scheduleAvvioCampagna(campagna.getId());
        scheduleSensoriRefresh();

        logger.info("Campagna creata. Avvio applicazione in background. ID: {}", campagna.getId());

        return convertToResponse(campagna);
    }

    private void scheduleAvvioCampagna(Long campagnaId) {
        Runnable task = () -> campagnaAvvioService.avviaCampagnaAsync(campagnaId);
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    task.run();
                }
            });
        } else {
            task.run();
        }
    }

    private void scheduleSensoriRefresh() {
        Runnable task = () -> {
            try {
                sensoriSseController.notifyAllClients();
            } catch (Exception e) {
                logger.warn("Notifica SSE sensori fallita", e);
            }
        };
        if (TransactionSynchronizationManager.isSynchronizationActive()) {
            TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
                @Override
                public void afterCommit() {
                    task.run();
                }
            });
        } else {
            task.run();
        }
    }

    /**
     * Converte un'entità Campagna in CampagnaResponse DTO.
     */
    /**
     * Converte una entita Campagna in DTO CampagnaResponse.
     * Mappa i campi base, i dati della persona, dell'utente creatore, i tipi campagna e i sensori associati.
     *
     * @param campagna entita persistita da convertire
     * @return DTO pronto per la serializzazione
     */
    public CampagnaResponse convertToResponse(Campagna campagna) {
        CampagnaResponse response = new CampagnaResponse();
        response.setId(campagna.getId());
        response.setNome(campagna.getNome());
        response.setNote(campagna.getNote());
        response.setStato(campagna.getStato());
        response.setDataInizio(campagna.getDataInizio());
        response.setDataFine(campagna.getDataFine());
        response.setDurataTotale(formatDuration(campagna.getDataInizio(), campagna.getDataFine()));
        response.setFrequenza(campagna.getFrequenza());
        response.setDurata(campagna.getDurata());
        response.setConnettivita(campagna.getConnettivita());
        response.setScriptFileName(campagna.getScriptFileName());
        response.setDbHost(campagna.getDbHost());
        response.setDbName(campagna.getDbName());

        // Informazioni persona
        response.setIdPersona(campagna.getPersona().getId());
        response.setNomePersona(campagna.getPersona().getNome());
        response.setCognomePersona(campagna.getPersona().getCognome());
        response.setNotePersona(campagna.getPersona().getNote());

        // Informazioni utente creatore
        response.setIdUtenteCreatore(campagna.getUtenteCreatore().getId());
        response.setUsernameCreatore(campagna.getUtenteCreatore().getUsername());

        // Tipi campagna
        List<CampagnaResponse.TipoCampagnaInfo> tipiInfo = campagna.getTipi().stream()
                .map(tipo -> new CampagnaResponse.TipoCampagnaInfo(
                        tipo.getId(),
                        tipo.getCodice(),
                        tipo.getDescrizione(),
                        null, // nomeApplicazione - da implementare se necessario
                        tipo.getScriptFileName() // eseguibile
                ))
                .collect(Collectors.toList());
        response.setTipiCampagna(tipiInfo);

        // Sensori
        List<CampagnaResponse.SensoreInfo> sensoriInfo = campagna.getCampagnaSensori().stream()
            .sorted(Comparator
                .comparing((CampagnaSensore cs) -> cs.getSensore().getNome() == null ? "" : cs.getSensore().getNome(), String.CASE_INSENSITIVE_ORDER)
                .thenComparing(cs -> cs.getSensore().getTipo() == null ? "" : cs.getSensore().getTipo(), String.CASE_INSENSITIVE_ORDER)
                .thenComparing(cs -> cs.getSensore().getId()))
                .map(cs -> new CampagnaResponse.SensoreInfo(
                        cs.getSensore().getId(),
                        cs.getSensore().getNome(),
                        cs.getSensore().getTipo(),
                        cs.getSensore().getCodice(),
                        cs.getProtocollo(), // protocollo dalla relazione CampagnaSensore
                        cs.getSensore().getMisureSupportate(),
                        cs.isAttivo(),
                        cs.getLocation()
                ))
                .collect(Collectors.toList());
        response.setSensori(sensoriInfo);

        return response;
    }

    /**
     * Calcola la durata tra due timestamp in formato HH:mm:ss.
     * Ritorna null se uno dei due valori e' assente o se la durata risulta negativa.
     */
    private String formatDuration(LocalDateTime start, LocalDateTime end) {
        if (start == null || end == null) {
            return null;
        }
        long seconds = Duration.between(start, end).getSeconds();
        if (seconds < 0) {
            return null;
        }
        long hours = seconds / 3600;
        long minutes = (seconds % 3600) / 60;
        long secs = seconds % 60;
        return String.format("%02d:%02d:%02d", hours, minutes, secs);
    }

    /**
     * Recupera i dettagli di una campagna specifica.
     * Esegue una query per id e converte l'entita in DTO.
     *
     * @param id ID della campagna
     * @return CampagnaResponse con tutti i dettagli
     */
    public CampagnaResponse getCampagnaById(Long id) {
        logger.info("Recupero dettagli campagna ID: {}", id);
        Campagna campagna = campagnaRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Campagna non trovata con ID: " + id));
        return convertToResponse(campagna);
    }

    /**
     * Recupera tutte le campagne associate a un paziente.
     * Verifica l'esistenza della persona prima di eseguire la query.
     *
     * @param idPersona ID del paziente
     * @return Lista di CampagnaResponse
     */
    public List<CampagnaResponse> getCampagneByPersona(Long idPersona) {
        logger.info("Recupero campagne per paziente ID: {}", idPersona);

        // Verifica che la persona esista
        if (!personaRepository.existsById(idPersona)) {
            throw new IllegalArgumentException("Persona non trovata con ID: " + idPersona);
        }

        List<Campagna> campagne = campagnaRepository.findByPersona_Id(idPersona);
        return campagne.stream()
                .map(this::convertToResponse)
                .collect(Collectors.toList());
    }

    /**
     * Recupera tutte le campagne create da un utente medico.
     * Verifica l'esistenza dell'utente prima di eseguire la query.
     *
     * @param idUtente ID dell'utente medico
     * @return Lista di CampagnaResponse
     */
    public List<CampagnaResponse> getCampagneByUtente(Long idUtente) {
        logger.info("Recupero campagne create dall'utente ID: {}", idUtente);

        // Verifica che l'utente esista
        if (!utenteRepository.existsById(idUtente)) {
            throw new IllegalArgumentException("Utente non trovato con ID: " + idUtente);
        }

        List<Campagna> campagne = campagnaRepository.findByUtenteCreatore_Id(idUtente);
        return campagne.stream()
                .map(this::convertToResponse)
                .collect(Collectors.toList());
    }


    /**
     * Termina forzatamente una campagna in corso.
     * Uccide il processo Python associato e aggiorna il DB.
     *
     * @param id ID della campagna
     * @return L'entità Campagna aggiornata
     */
    @Transactional
    public Campagna terminaCampagna(Long id) {
        logger.info("Richiesta terminazione campagna ID: {}", id);

        Campagna campagna = campagnaRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Campagna non trovata"));

        // 1. Uccidi i processi OS
        terminaProcessiFisici(campagna);

        // 2. Aggiorna DB
        campagna.setStato(StatoCampagna.TERMINATA);
        campagna.setDataFine(LocalDateTime.now());

        Campagna salvata = campagnaRepository.save(campagna);
        scheduleSensoriRefresh();
        return salvata;
    }

    private String extractMqttHost(String broker) {
        if (broker == null) {
            return null;
        }
        String value = broker.trim();
        if (value.isEmpty()) {
            return null;
        }
        int schemeIdx = value.indexOf("://");
        if (schemeIdx >= 0) {
            value = value.substring(schemeIdx + 3);
        }
        int slashIdx = value.indexOf('/');
        if (slashIdx >= 0) {
            value = value.substring(0, slashIdx);
        }
        int colonIdx = value.lastIndexOf(':');
        if (colonIdx > 0) {
            value = value.substring(0, colonIdx);
        }
        return value.isBlank() ? null : value;
    }

    private String resolveMqttPort(String broker) {
        String port = extractMqttPort(broker);
        return port == null ? "1883" : port;
    }

    private String extractMqttPort(String broker) {
        if (broker == null) {
            return null;
        }
        String value = broker.trim();
        if (value.isEmpty()) {
            return null;
        }
        int schemeIdx = value.indexOf("://");
        if (schemeIdx >= 0) {
            value = value.substring(schemeIdx + 3);
        }
        int slashIdx = value.indexOf('/');
        if (slashIdx >= 0) {
            value = value.substring(0, slashIdx);
        }
        int colonIdx = value.lastIndexOf(':');
        if (colonIdx < 0 || colonIdx == value.length() - 1) {
            return null;
        }
        String port = value.substring(colonIdx + 1).trim();
        return port.isEmpty() ? null : port;
    }

    /**
     * Elimina una campagna terminata appartenente all'utente creatore.
     * Blocca l'operazione se la campagna non e' in stato TERMINATA o se l'utente non e' proprietario.
     *
     * @param id ID della campagna
     * @param idUtente ID dell'utente autenticato
     */
    @Transactional
    public void eliminaCampagnaTerminata(Long id, Long idUtente) {
        logger.info("Richiesta eliminazione campagna ID: {} da utente {}", id, idUtente);

        Campagna campagna = campagnaRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Campagna non trovata"));

        if (campagna.getUtenteCreatore() == null || campagna.getUtenteCreatore().getId() == null
                || !campagna.getUtenteCreatore().getId().equals(idUtente)) {
            throw new IllegalArgumentException("Non autorizzato a eliminare questa campagna");
        }

        if (campagna.getStato() != StatoCampagna.TERMINATA
                && campagna.getStato() != StatoCampagna.AVVIO_FALLITO) {
            throw new IllegalStateException("Puoi eliminare solo campagne terminate o con avvio fallito");
        }

        //terminaProcessiFisici(campagna);
        campagnaRepository.delete(campagna);
    }

    /**
     * Termina i processi OS associati alla campagna e pulisce la memoria.
     * Non aggiorna lo stato DB: la persistenza viene gestita dal chiamante.
     */
    private void terminaProcessiFisici(Campagna campagna) {
        if (campagna == null || campagna.getId() == null) {
            return;
        }

        Long id = campagna.getId();
        String appId = campagnaAvvioService.getAppIdPerCampagna(id);
        if (appId == null || appId.isBlank()) {
            throw new IllegalStateException("ID applicazione mancante per la terminazione");
        }

        try {
            System.out.println("Invio stop application per " + appId + " della campagna " + id);
            CompletableFuture<it.polimi.bsnwebapp.communication.Messages.GlobalStopApplicationResponse> future
                = rrmConnectionService.stopApplication(appId);
            it.polimi.bsnwebapp.communication.Messages.GlobalStopApplicationResponse resp
                = future.get(Utils.RRM_STOP_APPLICATION_TIMEOUT_SECONDS, TimeUnit.SECONDS);
            if (!"OK".equals(resp.status)) {
                throw new IllegalStateException("RRM ha risposto con stato non valido: " + resp.status);
            }
            campagnaAvvioService.rimuoviAppIdPerCampagna(id);
        } catch (Exception e) {
            logger.error("Errore durante lo stop applicazione '{}' per campagna {}", appId, id, e);
            throw new IllegalStateException("Errore durante lo stop dell'applicazione RRM", e);
        }

        List<Process> processi = processManager.getProcessi(id);
        int uccisi = 0;

        for (Process p : processi) {
            if (p == null) {
                continue;
            }
            if (p.isAlive()) {
                p.destroy(); // Invia SIGTERM
                uccisi++;
            }
        }

        processManager.pulisciMemoriaCampagna(id);
        logger.info("Terminati {} processi per campagna {}", uccisi, id);
    }

    private String resolveAppId(Campagna campagna) {
        if (campagna == null) {
            return null;
        }
        String appId = campagna.getScriptFileName();
        if (appId != null && !appId.isBlank()) {
            return appId;
        }
        Set<TipoCampagna> tipi = campagna.getTipi();
        if (tipi == null || tipi.isEmpty()) {
            return null;
        }
        if (tipi.size() == 1) {
            TipoCampagna tipo = tipi.iterator().next();
            return tipo.getScriptFileName();
        }
        return tipi.iterator().next().getScriptFileName();
    }

    private boolean supportsProtocol(Sensore sensore, Protocollo protocollo) {
        if (sensore == null || protocollo == null) {
            return false;
        }
        Set<Protocollo> supportati = sensore.getProtocolliSupportati();
        if (supportati != null && !supportati.isEmpty()) {
            return supportati.contains(protocollo);
        }
        return sensore.getProtocollo() != null && sensore.getProtocollo() == protocollo;
    }
}
