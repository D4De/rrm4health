package it.polimi.bsnwebapp.Repository;

import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

import it.polimi.bsnwebapp.Model.Entities.SettingApplication;

public interface SettingApplicationRepository extends JpaRepository<SettingApplication, Long> {
    Optional<SettingApplication> findByKey(String key);

    /**
     * Recupera tutte le impostazioni la cui chiave comincia con il prefisso dato.
     */
    java.util.List<SettingApplication> findByKeyStartingWith(String prefix);

    /**
     * Elimina tutte le impostazioni con chiave che comincia per prefisso.
     */
    void deleteByKeyStartingWith(String prefix);
}
