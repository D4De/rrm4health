package it.polimi.bsnwebapp.Service;

import java.time.LocalDateTime;
import java.util.List;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;

import it.polimi.bsnwebapp.Controller.sse.SensoriSseController;
import it.polimi.bsnwebapp.Model.Entities.Campagna;
import it.polimi.bsnwebapp.Model.Enum.StatoCampagna;
import it.polimi.bsnwebapp.Repository.CampagnaRepository;

/**
 * Job schedulato che verifica la coerenza tra lo stato campagna a DB e i processi attivi.
 * Se una campagna risulta IN_CORSO ma non ha processi vivi, la termina e aggiorna le note.
 * Usa CampagnaProcessManager e CampagnaRepository per il controllo periodico.
 */

@Component
public class CampagnaWatchdog {

    private static final Logger logger = LoggerFactory.getLogger(CampagnaWatchdog.class);

    @Autowired
    private CampagnaRepository campagnaRepository;

    @Autowired
    private CampagnaProcessManager processManager;

    @Autowired
    private SensoriSseController sensoriSseController;

    @Autowired
    private CampagnaService campagnaService;

    /**
     * Esegue il controllo periodico di allineamento stato campagna/processi.
     * Ogni 30 secondi verifica le campagne IN_CORSO nel DB e controlla se esistono processi vivi.
     * Se non ne trova, forza la campagna a TERMINATA, aggiorna le note e pulisce la memoria processi.
     */
    @Scheduled(fixedRate = 30000)
    public void allineaStatoProcessi() {
        logger.debug("Watchdog: Inizio controllo processi...");

        List<Campagna> campagneDichiarateAttive = campagnaRepository.findByStato(StatoCampagna.IN_CORSO);

        for (Campagna campagna : campagneDichiarateAttive) {
            Long id = campagna.getId();

            if (isTimerScaduto(campagna)) {
                logger.warn("Timer scaduto: terminazione automatica campagna {}", id);
                terminaPerScadenzaTimer(campagna);
                continue;
            }

            // 2. Verifichiamo la realtà tramite il Manager: "C'è almeno uno script vivo per questo ID?"
            boolean isAliveInRealLife = processManager.isCampagnaAttiva(id);

            if (!isAliveInRealLife) {
                logger.error("ALLARME DISALLINEAMENTO: La Campagna {} è IN_CORSO su DB, ma non ha processi Python attivi.", id);

                // 3. Azione correttiva: Chiudiamo la campagna
                terminaForzatamente(campagna);

                // Pulizia extra della memoria
                processManager.pulisciMemoriaCampagna(id);
            }
        }
    }

    private boolean isTimerScaduto(Campagna campagna) {
        if (campagna == null) {
            return false;
        }
        Integer durataMinuti = campagna.getDurata();
        if (durataMinuti == null || durataMinuti <= 0) {
            return false;
        }
        LocalDateTime dataInizio = campagna.getDataInizio();
        if (dataInizio == null) {
            return false;
        }
        LocalDateTime scadenza = dataInizio.plusMinutes(durataMinuti.longValue());
        return !LocalDateTime.now().isBefore(scadenza);
    }

    private void terminaPerScadenzaTimer(Campagna campagna) {
        if (campagna == null || campagna.getId() == null) {
            return;
        }

        try {
            campagnaService.terminaCampagna(campagna.getId());
            logger.info("Campagna {} terminata automaticamente per scadenza timer.", campagna.getId());
        } catch (Exception e) {
            logger.error("Errore durante la terminazione automatica per timer della campagna {}", campagna.getId(), e);

            String noteAttuali = campagna.getNote() != null ? campagna.getNote() : "";
            campagna.setNote(noteAttuali + "\n[SYSTEM]: Errore stop automatico per timer: " + e.getMessage());
            campagnaRepository.save(campagna);
        }
    }

    /**
     * Aggiorna lo stato della campagna a TERMINATA e salva la data di fine.
     * Aggiunge una nota di sistema per indicare la chiusura automatica.
     *
     * @param campagna entita da aggiornare
     */
    private void terminaForzatamente(Campagna campagna) {
        try {
            campagna.setStato(StatoCampagna.TERMINATA);
            campagna.setDataFine(LocalDateTime.now());
            String noteAttuali = campagna.getNote() != null ? campagna.getNote() : "";
            campagna.setNote(noteAttuali + "\n[SYSTEM]: Terminata automaticamente dal Watchdog per assenza processi.");

            campagnaRepository.save(campagna);
            sensoriSseController.notifyAllClients();
            logger.info("Campagna {} aggiornata a TERMINATA dal sistema.", campagna.getId());
        } catch (Exception e) {
            logger.error("Errore critico durante il salvataggio della terminazione campagna {}", campagna.getId(), e);
        }
    }
}
