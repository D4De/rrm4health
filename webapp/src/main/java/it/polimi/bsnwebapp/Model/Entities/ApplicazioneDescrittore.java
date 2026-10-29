package it.polimi.bsnwebapp.Model.Entities;

import java.util.Map;

import it.polimi.bsnwebapp.Model.Converter.ParametriConverter;
import jakarta.persistence.Column;
import jakarta.persistence.Convert;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.PrePersist;
import jakarta.persistence.PreUpdate;
import jakarta.persistence.Table;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Entity JPA che rappresenta il descrittore di un'applicazione disponibile in RRM Global.
 * Ogni descrittore contiene l'identificativo univoco dell'applicazione (appID) e una mappa
 * di parametri eseguibili ricevuta dal server RRM.
 * I parametri vengono serializzati/deserializzati automaticamente da ParametriConverter.
 */
@Entity
@Table(name = "applicazione_descrittore")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
public class ApplicazioneDescrittore {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id", updatable = false, nullable = false)
    private Long id;

    @Column(name = "app_id", nullable = false, unique = true, length = 255)
    private String appId;

    @Column(name = "parametri", columnDefinition = "LONGTEXT")
    @Convert(converter = ParametriConverter.class)
    private Map<String, Object> parametri;

    /**
     * Timestamp di ultima sincronizzazione con RRM Global.
     * Utile per capire quando i dati sono stati aggiornati.
     */
    @Column(name = "last_updated", nullable = false, columnDefinition = "TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP")
    private java.time.LocalDateTime lastUpdated;

    @PrePersist
    protected void onCreate() {
        lastUpdated = java.time.LocalDateTime.now();
    }

    @PreUpdate
    protected void onUpdate() {
        lastUpdated = java.time.LocalDateTime.now();
    }

    public ApplicazioneDescrittore(String appId, Map<String, Object> parametri) {
        this.appId = appId;
        this.parametri = parametri;
    }
}
