package it.polimi.bsnwebapp.Service;

import java.util.Optional;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import it.polimi.bsnwebapp.Model.Entities.SettingApplication;
import it.polimi.bsnwebapp.Repository.SettingApplicationRepository;
import lombok.RequiredArgsConstructor;

/**
 * Service per memorizzare e recuperare coppie chiave/valore di configurazione.
 * Usato ad esempio per mantenere l'applicazione selezionata persistente tra i login.
 */
@Service
@RequiredArgsConstructor
public class SettingApplicationService {

    private final SettingApplicationRepository repository;

    /**
     * Restituisce il valore associato alla chiave, oppure null se non presente.
     */
    @Transactional(readOnly = true)
    public String getValue(String key) {
        return repository.findByKey(key)
                .map(SettingApplication::getValue)
                .orElse(null);
    }

    /**
     * Imposta il valore per la chiave; crea la voce se assente.
     */
    @Transactional
    public void setValue(String key, String value) {
        Optional<SettingApplication> existing = repository.findByKey(key);
        if (existing.isPresent()) {
            SettingApplication s = existing.get();
            s.setValue(value);
            repository.save(s);
        } else {
            repository.save(new SettingApplication(key, value));
        }
    }

    /**
     * Elimina tutte le impostazioni la cui chiave inizia con il prefisso specificato.
     */
    @Transactional
    public void deleteByPrefix(String prefix) {
        if (prefix == null || prefix.isBlank()) return;
        repository.deleteByKeyStartingWith(prefix);
    }

    /**
     * Recupera tutte le coppie chiave/valore in cui la chiave comincia con il
     * prefisso fornito. La chiave restituita nella mappa risultante e la
     * parte di stringa che compare dopo il prefisso; il prefisso stesso viene
     * rimosso.
     *
     * @param prefix prefisso da cercare (es. "app.myApp.")
     * @return mappa paramName -> valore (vuota se non ci sono impostazioni)
     */
    @Transactional(readOnly = true)
    public java.util.Map<String, String> getValuesWithPrefix(String prefix) {
        java.util.Map<String, String> result = new java.util.HashMap<>();
        if (prefix == null || prefix.isBlank()) {
            return result;
        }
        java.util.List<SettingApplication> list = repository.findByKeyStartingWith(prefix);
        for (SettingApplication s : list) {
            String key = s.getKey();
            if (key.startsWith(prefix)) {
                String stripped = key.substring(prefix.length());
                result.put(stripped, s.getValue());
            }
        }
        return result;
    }
}
