
package it.polimi.bsnwebapp.Repository;

import java.util.List;

import org.springframework.data.jpa.repository.JpaRepository;

import it.polimi.bsnwebapp.Model.Entities.CampagnaSensore;
import it.polimi.bsnwebapp.Model.Entities.CampagnaSensoreId;

/**
 * Repository Spring Data JPA per l'entita CampagnaSensore.
 * Espone operazioni CRUD e query derivate dai nomi dei metodi dichiarati.
 * Viene utilizzato dai service per accedere al database MariaDB.
 */

public interface CampagnaSensoreRepository extends JpaRepository<CampagnaSensore, CampagnaSensoreId> {

        /**
         * Restituisce gli ID dei sensori attivi in campagne in corso (IN_CORSO o AVVIO_IN_CORSO).
         */
        @org.springframework.data.jpa.repository.Query("""
            select distinct cs.sensore.id from CampagnaSensore cs
            where cs.attivo = true and cs.campagna.stato in (it.polimi.bsnwebapp.Model.Enum.StatoCampagna.IN_CORSO, it.polimi.bsnwebapp.Model.Enum.StatoCampagna.AVVIO_IN_CORSO)
        """)
        java.util.List<Long> findIdSensoriInUso();
    List<CampagnaSensore> findByCampagna_Id(Long idCampagna);
    boolean existsBySensore_Id(Long idSensore);
}
