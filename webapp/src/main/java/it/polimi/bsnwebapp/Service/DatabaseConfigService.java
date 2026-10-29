package it.polimi.bsnwebapp.Service;

import it.polimi.bsnwebapp.DTO.response.DatabaseConfigResponse;
import it.polimi.bsnwebapp.Model.Entities.DatabaseConfig;
import it.polimi.bsnwebapp.Repository.DatabaseConfigRepository;
import it.polimi.bsnwebapp.exception.BadRequestException;
import it.polimi.bsnwebapp.exception.ConflictException;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;

/**
 * Service per la gestione delle configurazioni database inserite dall'admin.
 * Consente la creazione e il listing delle configurazioni disponibili.
 */
@Service
@RequiredArgsConstructor
public class DatabaseConfigService {

    private final DatabaseConfigRepository databaseConfigRepository;

    /**
     * Restituisce tutte le configurazioni database disponibili.
     *
     * @return lista di configurazioni in formato DTO
     */
    @Transactional(readOnly = true)
    public List<DatabaseConfigResponse> listAll() {
        return databaseConfigRepository.findAll().stream().map(this::toResponse).toList();
    }

    /**
     * Crea una nuova configurazione database con controlli di validazione e unicita.
     *
     * @param nome nome descrittivo della configurazione
     * @param host indirizzo host (IP o dominio)
     * @param dbName nome del database
     * @return configurazione creata in formato DTO
     */
    @Transactional
    public DatabaseConfigResponse create(String nome, String host, String dbName) {
        String cleanNome = normalizeRequired(nome, "Nome database mancante");
        String cleanHost = normalizeRequired(host, "Indirizzo database mancante");
        String cleanDbName = normalizeRequired(dbName, "Nome database mancante");

        if (databaseConfigRepository.existsByNomeIgnoreCase(cleanNome)) {
            throw new ConflictException("Nome database già presente");
        }
        if (databaseConfigRepository.existsByHostIgnoreCaseAndDbNameIgnoreCase(cleanHost, cleanDbName)) {
            throw new ConflictException("Database già presente per questo indirizzo");
        }

        DatabaseConfig config = new DatabaseConfig(cleanNome, cleanHost, cleanDbName);
        return toResponse(databaseConfigRepository.save(config));
    }

    /**
     * Elimina una configurazione database.
     *
     * @param id ID della configurazione
     */
    @Transactional
    public void delete(Long id) {
        if (id == null) {
            throw new BadRequestException("ID database mancante");
        }
        DatabaseConfig config = databaseConfigRepository.findById(id)
                .orElseThrow(() -> new BadRequestException("Database non trovato"));
        databaseConfigRepository.delete(config);
    }

    /**
     * Normalizza un campo obbligatorio (trim) e valida che non sia vuoto.
     */
    private String normalizeRequired(String value, String errorMessage) {
        if (value == null || value.isBlank()) {
            throw new BadRequestException(errorMessage);
        }
        return value.trim();
    }

    /**
     * Converte una configurazione database in DTO.
     */
    private DatabaseConfigResponse toResponse(DatabaseConfig config) {
        return new DatabaseConfigResponse(
                config.getId(),
                config.getNome(),
                config.getHost(),
                config.getDbName()
        );
    }
}
