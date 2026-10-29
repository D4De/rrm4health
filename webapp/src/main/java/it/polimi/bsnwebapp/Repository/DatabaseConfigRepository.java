package it.polimi.bsnwebapp.Repository;

import it.polimi.bsnwebapp.Model.Entities.DatabaseConfig;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * Repository Spring Data JPA per la gestione delle configurazioni database.
 * Fornisce CRUD e verifiche di unicita su nome e coppia host/dbName.
 */
public interface DatabaseConfigRepository extends JpaRepository<DatabaseConfig, Long> {
    boolean existsByNomeIgnoreCase(String nome);
    boolean existsByHostIgnoreCaseAndDbNameIgnoreCase(String host, String dbName);
}
