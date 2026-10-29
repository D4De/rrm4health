package it.polimi.bsnwebapp.Service;

import java.util.List;
import java.util.Map;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import it.polimi.bsnwebapp.Model.Entities.ApplicazioneDescrittore;
import it.polimi.bsnwebapp.Model.Entities.TipoCampagna;
import it.polimi.bsnwebapp.Repository.ApplicazioneDescrittoreRepository;
import it.polimi.bsnwebapp.Repository.TipoCampagnaRepository;
import lombok.RequiredArgsConstructor;

/**
 * Service per la gestione dei descrittori delle applicazioni disponibili in RRM Global.
 * Fornisce metodi per salvare, aggiornare e recuperare descrittori di applicazioni.
 * Viene utilizzato da RrmConnectionService per persistere i dati ricevuti dal server RRM.
 */
@Service
@RequiredArgsConstructor
public class ApplicazioneDescrittoreService {

    private final ApplicazioneDescrittoreRepository repository;
    private final TipoCampagnaRepository tipoCampagnaRepository;

    /**
     * Salva o aggiorna una lista di descrittori di applicazioni nel database.
     * Ogni descrittore è rappresentato come una mappa con i parametri dell'applicazione.
     * Se un descrittore con lo stesso appID esiste già, viene aggiornato; altrimenti viene creato.
     * Estrae automaticamente la mappa "parameters" dal descrittore ricevuto.
     * Contemporaneamente, aggiunge una riga nella tabella TipoCampagna con codice e script_filename
     * impostati all'appID.
     *
     * @param descriptors lista di mappe contenente i descrittori ricevuti da RRM Global
     */
    @Transactional
    public void salvaDescrittori(List<Map<String, Object>> descriptors) {
        if (descriptors == null || descriptors.isEmpty()) {
            return;
        }
        // 1. Salva/aggiorna descrittori e tipi campagna
        for (Map<String, Object> desc : descriptors) {
            String appId = (String) desc.get("appID");
            if (appId == null || appId.isBlank()) {
                System.out.println("[APPLICAZIONE-DESCRITTORE] Skipping descrittore senza appID");
                continue;
            }

            Object paramsObj = desc.get("parameters");
            Map<String, Object> parametri = (paramsObj instanceof Map) ? (Map<String, Object>) paramsObj : desc;

            ApplicazioneDescrittore existing = repository.findByAppId(appId).orElse(null);

            if (existing != null) {
                existing.setParametri(parametri);
                repository.save(existing);
                System.out.println("[APPLICAZIONE-DESCRITTORE] Descrittore aggiornato: " + appId);
            } else {
                ApplicazioneDescrittore newDesc = new ApplicazioneDescrittore(appId, parametri);
                repository.save(newDesc);
                System.out.println("[APPLICAZIONE-DESCRITTORE] Descrittore salvato: " + appId);
            }

            salvaTipoCampagnaPerDescrittore(appId);
        }

        // 2. Sincronizza TipoCampagna: elimina quelli non presenti nei descrittori
        List<String> appIds = descriptors.stream()
                .map(d -> (String) d.get("appID"))
                .filter(id -> id != null && !id.isBlank())
                .toList();

        List<TipoCampagna> tuttiTipi = tipoCampagnaRepository.findAll();
        for (TipoCampagna tipo : tuttiTipi) {
            if (!appIds.contains(tipo.getCodice())) {
                tipoCampagnaRepository.delete(tipo);
                System.out.println("[TIPO-CAMPAGNA] Eliminato tipo campagna non più presente: " + tipo.getCodice());
            }
        }

        // 3. Sincronizza ApplicazioneDescrittore: elimina quelli non più presenti nei descrittori ricevuti
        List<ApplicazioneDescrittore> tuttiDescrittori = repository.findAll();
        for (ApplicazioneDescrittore descr : tuttiDescrittori) {
            if (!appIds.contains(descr.getAppId())) {
                repository.delete(descr);
                System.out.println("[APPLICAZIONE-DESCRITTORE] Eliminato descrittore non più presente: " + descr.getAppId());
            }
        }

        System.out.println("[APPLICAZIONE-DESCRITTORE] Salvataggio descrittori completato. Totale: " + descriptors.size());
    }

    /**
     * Salva o verifica l'esistenza di una riga in TipoCampagna per il dato appID.
     * Se non esiste, ne crea una nuova con codice = appID, script_filename = appID, descrizione = "Applicazione " + appID.
     *
     * @param appId identificativo dell'applicazione
     */
    private void salvaTipoCampagnaPerDescrittore(String appId) {
        // Verifica se esiste già
        if (tipoCampagnaRepository.findByCodice(appId).isEmpty()) {
            TipoCampagna tipoCampagna = new TipoCampagna();
            tipoCampagna.setCodice(appId);
            tipoCampagna.setScriptFileName(appId);
            tipoCampagna.setDescrizione("Applicazione " + appId);
            tipoCampagnaRepository.save(tipoCampagna);
            System.out.println("[TIPO-CAMPAGNA] Tipo campagna creato per appID: " + appId);
        } else {
            System.out.println("[TIPO-CAMPAGNA] Tipo campagna già esistente per appID: " + appId);
        }
    }

    /**
     * Recupera tutti i descrittori salvati nel database.
     *
     * @return lista di descrittori
     */
    @Transactional(readOnly = true)
    public List<ApplicazioneDescrittore> listaDescrittori() {
        return repository.findAll();
    }

    /**
     * Recupera un descrittore specifico tramite appID.
     *
     * @param appId identificativo univoco dell'applicazione
     * @return descrittore se trovato, null altrimenti
     */
    @Transactional(readOnly = true)
    public ApplicazioneDescrittore getDescrittoreByAppId(String appId) {
        return repository.findByAppId(appId).orElse(null);
    }

    /**
     * Verifica l'esistenza di un descrittore con il dato appID.
     */
    @Transactional(readOnly = true)
    public boolean existsByAppId(String appId) {
        if (appId == null) {
            return false;
        }
        return repository.existsByAppId(appId);
    }

    /**
     * Elimina un descrittore dal database.
     *
     * @param id ID del descrittore
     */
    @Transactional
    public void eliminaDescrittore(Long id) {
        if (id == null) {
            throw new IllegalArgumentException("ID descrittore mancante");
        }
        repository.deleteById(id);
        System.out.println("[APPLICAZIONE-DESCRITTORE] Descrittore eliminato: " + id);
    }

    /**
     * Elimina tutti i descrittori dal database.
     * Utile per resetting della cache locale quando si riconnette a RRM Global.
     */
    @Transactional
    public void eliminaTuttiDescrittori() {
        long count = repository.count();
        repository.deleteAll();
        System.out.println("[APPLICAZIONE-DESCRITTORE] Eliminati " + count + " descrittori");
    }
}
