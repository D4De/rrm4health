package it.polimi.bsnwebapp.Model.Entities;

import java.util.HashSet;
import java.util.Set;

import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import it.polimi.bsnwebapp.Model.Enum.TipoMisura;
import jakarta.persistence.CascadeType;
import jakarta.persistence.CollectionTable;
import jakarta.persistence.Column;
import jakarta.persistence.ElementCollection;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.FetchType;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.JoinColumn;
import jakarta.persistence.OneToMany;
import jakarta.persistence.Table;
import lombok.EqualsAndHashCode;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Entity JPA che rappresenta un sensore fisico utilizzato nelle campagne.
 * Identificato da codice univoco e da un nome logico.
 * Contiene tipo, protocollo di default, lista protocolli supportati e misure disponibili.
 * La relazione con le campagne e' gestita tramite {@link CampagnaSensore}.
 */

@Entity
@Table(name = "sensore")
@Getter
@Setter
@NoArgsConstructor
@EqualsAndHashCode
public class Sensore {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id_sensore", updatable = false, nullable = false)
    private Long id;

    @Column(name = "nome", nullable = false, length = 100)
    private String nome;

    @Column(name = "tipo", nullable = false, length = 50)
    private String tipo;

    @Enumerated(EnumType.STRING)
    @Column(name = "protocollo", nullable = false)
    private Protocollo protocollo;

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(
            name = "sensore_protocollo",
            joinColumns = @JoinColumn(name = "id_sensore")
    )
    @Enumerated(EnumType.STRING)
    @EqualsAndHashCode.Exclude
    @Column(name = "protocollo", nullable = false)
    private Set<Protocollo> protocolliSupportati = new HashSet<>();

    @ElementCollection(fetch = FetchType.EAGER)
    @CollectionTable(
            name = "sensore_misura",
            joinColumns = @JoinColumn(name = "id_sensore")
    )
    @Enumerated(EnumType.STRING)
    @Column(name = "misura", nullable = false)
    @EqualsAndHashCode.Exclude
    private Set<TipoMisura> misureSupportate = new HashSet<>();

    @Column(name = "codice", nullable = false, unique = true, length = 50)
    private String codice;

    @Column(name = "eliminato", nullable = false)
    private boolean eliminato = false;

    // relazione con campagna_sensore (join con attributo "attivo")
    @EqualsAndHashCode.Exclude
    @OneToMany(mappedBy = "sensore", fetch = FetchType.LAZY, cascade = CascadeType.ALL, orphanRemoval = true)
    private Set<CampagnaSensore> campagnaSensori = new HashSet<>();

    public Sensore(String nome, String tipo, Protocollo protocollo) {
        this.nome = nome;
        this.tipo = tipo;
        this.protocollo = protocollo;
    }
}
