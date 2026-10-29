package it.polimi.bsnwebapp.Repository;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import it.polimi.bsnwebapp.Model.Entities.ApplicazioneDescrittore;

/**
 * Repository Spring Data JPA per l'entita ApplicazioneDescrittore.
 * Espone operazioni CRUD e query derivate per accedere ai descrittori
 * delle applicazioni disponibili in RRM Global, persistiti nel database.
 */
public interface ApplicazioneDescrittoreRepository extends JpaRepository<ApplicazioneDescrittore, Long> {
    Optional<ApplicazioneDescrittore> findByAppId(String appId);
    boolean existsByAppId(String appId);
}
