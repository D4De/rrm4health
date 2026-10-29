package it.polimi.bsnwebapp.Model.Entities;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

import java.time.LocalDate;

/**
 * Entity JPA che rappresenta una persona (paziente).
 * Contiene dati anagrafici e note; e' referenziata dalle campagne tramite foreign key.
 * Mappa la tabella persona con un id auto-generato.
 */

@Entity
@Table(name = "persona")
@Getter
@Setter
@NoArgsConstructor
public class Persona {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id_persona", updatable = false, nullable = false)
    private Long id;

    @Column(name = "nome", nullable = false, length = 100)
    private String nome;

    @Column(name = "cognome", nullable = false, length = 100)
    private String cognome;

    @Column(name = "data_nascita")
    private LocalDate dataNascita;

    /**
     * Note testuali (potenzialmente lunghe).
     * <p>
     * {@link Lob} mappa il campo su un tipo adatto a testi di grandi dimensioni (es. TEXT).
     * </p>
     */
    @Lob
    @Column(name = "note", columnDefinition = "TEXT")
    private String note;

    public Persona(String nome, String cognome, LocalDate dataNascita, String note) {
        this.nome = nome;
        this.cognome = cognome;
        this.dataNascita = dataNascita;
        this.note = note;
    }
}
