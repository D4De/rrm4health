package it.polimi.bsnwebapp.Repository;

import it.polimi.bsnwebapp.Model.Entities.Utente;
import it.polimi.bsnwebapp.Model.Enum.RuoloUtente;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.Optional;

/**
 * Repository Spring Data JPA per l'entita Utente.
 * Espone operazioni CRUD e query derivate dai nomi dei metodi dichiarati.
 * Viene utilizzato dai service per accedere al database MariaDB.
 */

public interface UtenteRepository extends JpaRepository<Utente, Long> {

    Optional<Utente> findByUsername(String username);

    //evita doppioni in registrazione
    boolean existsByUsername(String username);

    Optional<Utente> findByRuolo(RuoloUtente ruolo);
}
