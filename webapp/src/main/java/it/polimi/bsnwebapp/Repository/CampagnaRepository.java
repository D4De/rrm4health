package it.polimi.bsnwebapp.Repository;

import it.polimi.bsnwebapp.Model.Entities.Campagna;
import it.polimi.bsnwebapp.Model.Enum.StatoCampagna;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.Collection;
import java.util.List;

/**
 * Repository Spring Data JPA per l'entita Campagna.
 * Espone operazioni CRUD e query derivate dai nomi dei metodi dichiarati.
 * Viene utilizzato dai service per accedere al database MariaDB.
 */

public interface CampagnaRepository extends JpaRepository<Campagna, Long> {
    List<Campagna> findByStato(StatoCampagna stato);
    List<Campagna> findByPersona_Id(Long idPersona);
    List<Campagna> findByUtenteCreatore_Id(Long idUtenteCreatore);
    boolean existsByIdAndUtenteCreatore_Id(Long id, Long idUtenteCreatore);
    boolean existsByStatoIn(Collection<StatoCampagna> stati);
    long countByStatoIn(Collection<StatoCampagna> stati);

    /**
     * Restituisce le campagne da mostrare in home filtrate per stati.
     *
     * La query:
     *      - seleziona le entità Campagna (select c from Campagna)
     *      - esegue un join fetch su c.persona per caricare subito la persona associata
     *      - filtra per stato usando il parametro stati
     *      - ordina per dataInizio in ordine crescente
     *
     * @param stati lista degli stati ammessi per la campagna
     * @return lista di campagne con persona gi\à inizializzata e ordinate per data di inizio
     */
    @Query("""
       select c
       from Campagna c
       join fetch c.persona p
       where c.stato in :stati
       order by c.dataInizio asc
       """)
    List<Campagna> findHomeCampaigns(@Param("stati") List<StatoCampagna> stati);

}
