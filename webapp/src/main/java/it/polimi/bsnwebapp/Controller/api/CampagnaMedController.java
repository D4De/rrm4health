package it.polimi.bsnwebapp.Controller.api;

import java.io.IOException;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.http.HttpStatus;
import org.springframework.http.ContentDisposition;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

import it.polimi.bsnwebapp.DTO.request.CampagnaCreateRequest;
import it.polimi.bsnwebapp.DTO.response.CampaignOutputDataResponse;
import it.polimi.bsnwebapp.DTO.response.CampagnaResponse;
import it.polimi.bsnwebapp.DTO.response.InfluxSeriesResponse;
import it.polimi.bsnwebapp.DTO.response.MessageResponse;
import it.polimi.bsnwebapp.Model.Entities.DatabaseConfig;
import it.polimi.bsnwebapp.Model.Entities.Utente;
import it.polimi.bsnwebapp.Repository.DatabaseConfigRepository;
import it.polimi.bsnwebapp.Service.CampagnaService;
import it.polimi.bsnwebapp.Service.CampaignOutputExportService;
import it.polimi.bsnwebapp.Service.InfluxQueryService;

/**
 * Controller REST per la gestione delle campagne.
 * Offre endpoint per creare/avviare campagne, consultare dettagli, terminare ed eliminare campagne.
 * Le risposte sono CampagnaResponse e MessageResponse con gestione errori applicativa.
 */

@RestController
@RequestMapping("/api/v1/campagne")
public class CampagnaMedController {

    private static final Logger logger = LoggerFactory.getLogger(CampagnaMedController.class);

    @Autowired
    private CampagnaService campagnaService;

    @Autowired
    private InfluxQueryService influxQueryService;

    @Autowired
    private CampaignOutputExportService campaignOutputExportService;

    @Autowired
    private DatabaseConfigRepository databaseConfigRepository;

    /**
     * Recupera tutte le campagne create dall'utente medico autenticato.
     * GET /api/campagne
     *
     * @param utente Utente autenticato (iniettato automaticamente da Spring Security)
     * @return Lista delle campagne create dall'utente
     */
    @GetMapping
    public ResponseEntity<?> getMieCampagne(@AuthenticationPrincipal Utente utente) {
        try {
            logger.info("Richiesta campagne dell'utente loggato ID: {}", utente.getId());

            List<CampagnaResponse> campagne = campagnaService.getCampagneByUtente(utente.getId());

            return ResponseEntity.ok(campagne);

        } catch (Exception e) {
            logger.error("Errore durante il recupero delle campagne dell'utente", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Recupera i dettagli di una campagna specifica.
     * GET /api/campagne/{id}
     *
     * @param id ID della campagna
     * @return Dettagli completi della campagna
     */
    @GetMapping("/{id}")
    public ResponseEntity<?> getCampagnaById(@PathVariable Long id) {
        try {
            logger.info("Richiesta dettagli campagna ID: {}", id);

            CampagnaResponse campagna = campagnaService.getCampagnaById(id);

            return ResponseEntity.ok(campagna);

        } catch (IllegalArgumentException e) {
            logger.error("Campagna non trovata: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.NOT_FOUND)
                    .body(new MessageResponse("Errore: " + e.getMessage()));

        } catch (Exception e) {
            logger.error("Errore durante il recupero della campagna", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Recupera tutte le campagne associate a un paziente specifico.
     * GET /api/campagne/paziente/{idPersona}
     *
     * @param idPersona ID del paziente
     * @return Lista delle campagne del paziente
     */
    @GetMapping("/paziente/{idPersona}")
    public ResponseEntity<?> getCampagneByPaziente(@PathVariable Long idPersona) {
        try {
            logger.info("Richiesta campagne per paziente ID: {}", idPersona);

            List<CampagnaResponse> campagne = campagnaService.getCampagneByPersona(idPersona);

            return ResponseEntity.ok(campagne);

        } catch (IllegalArgumentException e) {
            logger.error("Errore: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.NOT_FOUND)
                    .body(new MessageResponse("Errore: " + e.getMessage()));

        } catch (Exception e) {
            logger.error("Errore durante il recupero delle campagne del paziente", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Crea e avvia immediatamente una nuova campagna.
     * POST /api/campagne/avvia-subito
     *
     * @param request Dati della campagna da creare e avviare
     * @param utente Utente autenticato (iniettato automaticamente)
     * @return CampagnaResponse con i dettagli della campagna avviata
     */
    @PostMapping("/avvia-subito")
    public ResponseEntity<?> creaEAvviaCampagna(
            @RequestBody CampagnaCreateRequest request,
            @AuthenticationPrincipal Utente utente) {
        try {
            logger.info("Richiesta creazione e avvio immediato campagna: {} da utente ID: {}",
                    request.getNome(), utente.getId());

            // Imposta automaticamente l'ID dell'utente creatore
            request.setIdUtenteCreatore(utente.getId());

            CampagnaResponse response = campagnaService.creaEAvviaCampagna(request);

            return ResponseEntity
                    .status(HttpStatus.CREATED)
                    .body(response);

        } catch (IllegalArgumentException | IllegalStateException e) {
            logger.error("Errore validazione dati: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.BAD_REQUEST)
                    .body(new MessageResponse("Errore: " + e.getMessage()));

        } catch (IOException e) {
            logger.error("Errore durante l'avvio dell'applicazione RRM: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore avvio applicazione: " + e.getMessage()));

        } catch (Exception e) {
            logger.error("Errore inatteso durante la creazione/avvio della campagna", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Termina una campagna in corso.
     */
    @PostMapping("/{id}/termina")
    public ResponseEntity<?> terminaCampagna(@PathVariable Long id) {
        try {
            logger.info("Richiesta terminazione campagna ID: {}", id);

            campagnaService.terminaCampagna(id);

            return ResponseEntity
                    .ok(new MessageResponse("Campagna terminata con successo"));

        } catch (IllegalArgumentException e) {
            logger.error("Errore: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.BAD_REQUEST)
                    .body(new MessageResponse("Errore: " + e.getMessage()));

        } catch (Exception e) {
            logger.error("Errore inatteso durante la terminazione della campagna", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Elimina una campagna terminata dell'utente autenticato.
     */
    @PostMapping("/{id}/elimina")
    public ResponseEntity<?> eliminaCampagna(@PathVariable Long id,
                                             @AuthenticationPrincipal Utente utente) {
        try {
            campagnaService.eliminaCampagnaTerminata(id, utente.getId());
            return ResponseEntity.ok(new MessageResponse("Campagna eliminata con successo"));
        } catch (IllegalArgumentException | IllegalStateException e) {
            logger.error("Errore eliminazione campagna: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.BAD_REQUEST)
                    .body(new MessageResponse("Errore: " + e.getMessage()));
        } catch (Exception e) {
            logger.error("Errore inatteso durante l'eliminazione della campagna", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    // Riavvio campagna rimosso: una campagna non può essere riavviata dopo la terminazione.

    /**
     * Recupera i dati storici di una campagna da InfluxDB.
     * La query usa una misura per-campagna (campaign_id) e puo essere limitata per sensore o numero di punti.
     *
     * @param id ID della campagna
     * @param measurement misura Influx (default: campaign)
     * @param imuid filtro opzionale per uno o piu sensori separati da virgola
     * @param limit numero massimo di punti (default 1000)
     * @param dbId database opzionale da cui leggere (se diverso dal default MQTT)
     * @return serie Influx con colonne e valori pronti per i grafici
     */
    @GetMapping("/{id}/dati")
    public ResponseEntity<?> getCampagnaDati(
            @PathVariable Long id,
            @RequestParam(defaultValue = "campaign") String measurement,
            @RequestParam(required = false) String imuid,
            @RequestParam(defaultValue = "1000") Integer limit,
            @RequestParam(required = false) Long fromSeconds,
            @RequestParam(required = false) Long dbId) {
        try {
            String overrideHost = null;
            String overrideDb = null;
            if (dbId != null && dbId > 0) {
                DatabaseConfig dbConfig = databaseConfigRepository.findById(dbId)
                        .orElseThrow(() -> new IllegalArgumentException("Database non trovato"));
                overrideHost = dbConfig.getHost();
                overrideDb = dbConfig.getDbName();
            }
            InfluxSeriesResponse response = influxQueryService.queryCampaignData(
                    id,
                    measurement,
                    imuid,
                    limit,
                    fromSeconds,
                    overrideHost,
                    overrideDb
            );
            return ResponseEntity.ok(response);
        } catch (IllegalArgumentException e) {
            logger.error("Errore validazione dati Influx: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.BAD_REQUEST)
                    .body(new MessageResponse("Errore: " + e.getMessage()));
        } catch (Exception e) {
            logger.error("Errore durante la lettura dati Influx", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Recupera gli output applicativi dalle measurement campaign_<id>_<cname>.
     */
    @GetMapping("/{id}/output/dati")
    public ResponseEntity<?> getCampaignOutputData(
            @PathVariable Long id,
            @RequestParam(defaultValue = "1000") Integer limit) {
        try {
            CampaignOutputDataResponse response =
                    influxQueryService.queryCampaignOutputData(id, limit);
            return ResponseEntity.ok(response);
        } catch (IllegalArgumentException e) {
            logger.error("Errore validazione output Influx: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.BAD_REQUEST)
                    .body(new MessageResponse("Errore: " + e.getMessage()));
        } catch (Exception e) {
            logger.error("Errore durante la lettura degli output Influx", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Esporta gli output applicativi della campagna in uno ZIP contenente un CSV per topic.
     */
    @GetMapping("/{id}/output/export")
    public ResponseEntity<?> exportCampaignOutputs(
            @PathVariable Long id,
            @AuthenticationPrincipal Utente utente) {
        try {
            CampaignOutputExportService.ExportArchive archive =
                    campaignOutputExportService.exportApplicationOutputs(id, utente);
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.parseMediaType("application/zip"));
            headers.setContentDisposition(ContentDisposition.attachment()
                    .filename(archive.fileName(), java.nio.charset.StandardCharsets.UTF_8)
                    .build());
            headers.setContentLength(archive.content().length);
            return new ResponseEntity<>(archive.content(), headers, HttpStatus.OK);
        } catch (AccessDeniedException e) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(new MessageResponse(e.getMessage()));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                    .body(new MessageResponse(e.getMessage()));
        } catch (IllegalStateException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new MessageResponse(e.getMessage()));
        } catch (Exception e) {
            logger.error("Errore durante l'esportazione degli output della campagna {}", id, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore durante l'esportazione degli output"));
        }
    }

    /**
     * Esporta i dati IMU della campagna in un CSV.
     */
    @GetMapping("/{id}/imu/export")
    public ResponseEntity<?> exportCampaignImuData(
            @PathVariable Long id,
            @AuthenticationPrincipal Utente utente) {
        try {
            CampaignOutputExportService.ExportFile file =
                    campaignOutputExportService.exportImuData(id, utente);
            HttpHeaders headers = new HttpHeaders();
            headers.setContentType(MediaType.parseMediaType("text/csv; charset=UTF-8"));
            headers.setContentDisposition(ContentDisposition.attachment()
                    .filename(file.fileName(), java.nio.charset.StandardCharsets.UTF_8)
                    .build());
            headers.setContentLength(file.content().length);
            return new ResponseEntity<>(file.content(), headers, HttpStatus.OK);
        } catch (AccessDeniedException e) {
            return ResponseEntity.status(HttpStatus.FORBIDDEN)
                    .body(new MessageResponse(e.getMessage()));
        } catch (IllegalArgumentException e) {
            return ResponseEntity.status(HttpStatus.BAD_REQUEST)
                    .body(new MessageResponse("Errore: " + e.getMessage()));
        } catch (IllegalStateException e) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND)
                    .body(new MessageResponse(e.getMessage()));
        } catch (Exception e) {
            logger.error("Errore durante l'esportazione dei dati IMU della campagna {}", id, e);
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore durante l'esportazione dei dati IMU"));
        }
    }
}
