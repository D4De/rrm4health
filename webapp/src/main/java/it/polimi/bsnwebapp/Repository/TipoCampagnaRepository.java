package it.polimi.bsnwebapp.Repository;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import it.polimi.bsnwebapp.Model.Entities.TipoCampagna;

/**
 * Repository Spring Data JPA per l'entita TipoCampagna.
 * Espone operazioni CRUD e query derivate dai nomi dei metodi dichiarati.
 * Viene utilizzato dai service per accedere al database MariaDB.
 */

public interface TipoCampagnaRepository extends JpaRepository<TipoCampagna, Long> {
    /**
     * Ricerca un TipoCampagna per codice.
     * @param codice il codice da cercare
     * @return Optional contenente il TipoCampagna se trovato
     */
    Optional<TipoCampagna> findByCodice(String codice);
}
