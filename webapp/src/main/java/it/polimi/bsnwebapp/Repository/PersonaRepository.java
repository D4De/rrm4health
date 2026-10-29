package it.polimi.bsnwebapp.Repository;

import it.polimi.bsnwebapp.Model.Entities.Persona;
import org.springframework.data.jpa.repository.JpaRepository;

/**
 * Repository Spring Data JPA per l'entita Persona.
 * Espone operazioni CRUD e query derivate dai nomi dei metodi dichiarati.
 * Viene utilizzato dai service per accedere al database MariaDB.
 */

public interface PersonaRepository extends JpaRepository<Persona, Long> {
}
