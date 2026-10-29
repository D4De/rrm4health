package it.polimi.bsnwebapp.Model.Entities;

import java.time.LocalDateTime;
import java.util.HashSet;
import java.util.Set;

import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import it.polimi.bsnwebapp.Model.Enum.StatoCampagna;
import jakarta.persistence.CascadeType;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.JoinTable;
import jakarta.persistence.Lob;
import jakarta.persistence.ManyToMany;
import jakarta.persistence.ManyToOne;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;
import lombok.ToString;

/**
 * Entity JPA che rappresenta una campagna di acquisizione dati.
 * Mappa la tabella {@code campagna} e include metadati (nome, date, note, stato) e configurazioni
 * (frequenza, durata, scriptFileName, connettivita, dbHost/dbName).
 * Relazioni: Persona e Utente creatore (ManyToOne), TipoCampagna (ManyToMany via {@code campagna_tipo}),
 * Sensore (OneToMany via {@link CampagnaSensore}).
 */

@Entity
@Table(name = "campagna")
@Getter
@Setter
@NoArgsConstructor
public class Campagna {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id_campagna", updatable = false, nullable = false)
    private Long id;

    @Column(name = "nome", nullable = false, length = 150)
    private String nome;

    @Column(name = "data_inizio", nullable = false)
    private LocalDateTime dataInizio;

    @Column(name = "data_fine")
    private LocalDateTime dataFine;

    @Enumerated(EnumType.STRING)
    @Column(name = "stato", nullable = false, length = 30)
    private StatoCampagna stato = StatoCampagna.IN_CORSO;

    @Lob
    @Column(name = "note", columnDefinition = "TEXT")
    private String note;

    @Column(name = "frequenza")
    private Integer frequenza; // es. in Hz

    @Column(name = "durata")
    private Integer durata;    // es. in secondi o minuti

    @Column(name = "script_filename", length = 255)
    private String scriptFileName;

    @Enumerated(EnumType.STRING)
    @Column(name = "connettivita", length = 20)
    private Protocollo connettivita;

    @Column(name = "db_host", length = 255)
    private String dbHost;

    @Column(name = "db_name", length = 255)
    private String dbName;

    //  RELAZIONI MANY-TO-ONE (Foreign Keys)

    /**
     * Persona a cui la campagna è riferita (FK: {@code id_persona}).
     * Con LAZY, quando leggi una Campagna dal DB:
     *  •   JPA non carica subito la Persona.
     * 	•	Al posto di persona mette un “proxy” (un oggetto finto).
     * 	•	Appena fai campagna.getPersona() (in un contesto dove la sessione è aperta), allora fa una query
    */
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "id_persona", nullable = false)
    @ToString.Exclude // Evita crash per loop infinito
    private Persona persona;

    /**
     * Utente che ha creato la campagna (FK: {@code id_utente}).
     */
    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "id_utente_creatore", nullable = false)
    @ToString.Exclude
    private Utente utenteCreatore;

    //  RELAZIONI COMLPESSE

    // 1. Campagna <-> Tipo
    // Non serve entity intermedia perché la tabella di mezzo non ha colonne extra
    // Join table pura: campagna_tipo (solo FK) => ManyToMany
    @ManyToMany(fetch = FetchType.EAGER)  //EAGER perchè ci servono subito i nomi degli script
    @JoinTable(
            name = "campagna_tipo",
            joinColumns = @JoinColumn(name = "id_campagna"),
            inverseJoinColumns = @JoinColumn(name = "id_tipo")
    )
    @ToString.Exclude
    private Set<TipoCampagna> tipi = new HashSet<>();

    // 2. Campagna <-> Sensore
    // Qui serve l'Entity intermedia "CampagnaSensore" perché c'è il campo "attivo"
    // Join table con attributo: campagna_sensore (attivo) => entity intermedia dedicata
    @OneToMany(mappedBy = "campagna", fetch = FetchType.LAZY, cascade = CascadeType.ALL, orphanRemoval = true)
    @ToString.Exclude
    private Set<CampagnaSensore> campagnaSensori = new HashSet<>();

    public Campagna(String nome, LocalDateTime dataInizio, LocalDateTime dataFine,
                    Persona persona, Utente utenteCreatore, StatoCampagna stato, String note) {
        this.nome = nome;
        this.dataInizio = dataInizio;
        this.dataFine = dataFine;
        this.persona = persona;
        this.utenteCreatore = utenteCreatore;
        this.stato = (stato != null) ? stato : StatoCampagna.IN_CORSO; //Default
        this.note = note;
    }
}
