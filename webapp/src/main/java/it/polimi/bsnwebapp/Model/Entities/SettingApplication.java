package it.polimi.bsnwebapp.Model.Entities;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Entity JPA per chiavi di configurazione generiche salvate nel database.
 * Usata per memorizzare opzioni persistenti come l'applicazione selezionata.
 */
@Entity
@Table(name = "setting")
@Getter
@Setter
@NoArgsConstructor
public class SettingApplication {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "key_name", nullable = false, unique = true, length = 100)
    private String key;

    @Column(name = "value", columnDefinition = "TEXT")
    private String value;

    public SettingApplication(String key, String value) {
        this.key = key;
        this.value = value;
    }
}
