package it.polimi.bsnwebapp.Repository;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import it.polimi.bsnwebapp.Model.Entities.Sensore;

/**
 * Repository Spring Data JPA per l'entita Sensore.
 * Espone operazioni CRUD e query derivate dai nomi dei metodi dichiarati.
 * Viene utilizzato dai service per accedere al database MariaDB.
 */

public interface SensoreRepository extends JpaRepository<Sensore, Long> {
    boolean existsByCodice(String codice);

    Optional<Sensore> findByCodice(String codice);

    List<Sensore> findAllByEliminatoFalse();
}
