package it.polimi.bsnwebapp.Service;

import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

import org.springframework.stereotype.Component;

/**
 * Gestisce i processi Python avviati per ogni campagna.
 * Mantiene una mappa in memoria campagnaId -> lista di Process e fornisce verifica di attivita.
 * Usato da CampagnaService per registrare processi e da CampagnaWatchdog per il controllo stato.
 */

@Component
public class CampagnaProcessManager {

    // Mappa Thread-Safe: ID_Campagna -> Lista di Processi OS
    private final Map<Long, List<Process>> processiAttivi = new ConcurrentHashMap<>();

    /**
     * Registra un processo OS associato a una campagna.
     * La mappa interna e' thread-safe e mantiene la lista completa dei processi attivi per campagna.
     *
     * @param campagnaId id della campagna
     * @param processo processo OS avviato da CampagnaService
     */
    public void registraProcesso(Long campagnaId, Process processo) {
        // computeIfAbsent crea una nuova ArrayList se non esiste ancora per quell'ID
        processiAttivi.computeIfAbsent(campagnaId, k -> new ArrayList<>()).add(processo);
    }

    /**
     * Restituisce la lista dei processi associati a una campagna.
     * Se non ci sono processi registrati, ritorna una lista vuota.
     *
     * @param campagnaId id della campagna
     * @return lista dei processi registrati
     */
    public List<Process> getProcessi(Long campagnaId) {
        return processiAttivi.getOrDefault(campagnaId, new ArrayList<>());
    }

    /**
     * Pulisce la mappa dei processi per una campagna.
     * Non termina i processi sul sistema operativo: serve solo a rimuovere il riferimento in memoria.
     *
     * @param campagnaId id della campagna da rimuovere
     */
    public void pulisciMemoriaCampagna(Long campagnaId) {
        processiAttivi.remove(campagnaId);
    }

    /**
     * Verifica se la campagna ha almeno un processo vivo nel sistema operativo.
     * Serve al watchdog per allineare lo stato DB con lo stato reale dei processi.
     *
     * @param campagnaId id della campagna
     * @return true se almeno un processo risulta ancora attivo
     */
    public boolean isCampagnaAttiva(Long campagnaId) {
        List<Process> lista = processiAttivi.get(campagnaId);
        if (lista == null || lista.isEmpty()) {
            return false;
        }
        // Ritorna true se ALMENO UNO dei processi nella lista è ancora vivo
        // oppure se abbiamo un placeholder (null) usato per campagne RRM
        return lista.stream().anyMatch(p -> p == null || p.isAlive());
    }
}
