package it.polimi.bsnwebapp.Model.Entities;

import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Entity di associazione tra Campagna e Sensore.
 * Mappa la tabella {@code campagna_sensore} con chiave composta e attributi extra ({@code attivo}, {@code protocollo}).
 * Permette di registrare quali sensori sono attivi in una campagna e quale protocollo usano.
 */

@Entity
@Table(name = "campagna_sensore")
@Getter
@Setter
@NoArgsConstructor
public class CampagnaSensore {

    @EmbeddedId
    private CampagnaSensoreId id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId("campagnaId")
    @JoinColumn(name = "id_campagna", nullable = false)
    private Campagna campagna;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @MapsId("sensoreId")
    @JoinColumn(name = "id_sensore", nullable = false)
    private Sensore sensore;

    @Column(name = "attivo", nullable = false)
    private boolean attivo = true;

    @Enumerated(EnumType.STRING)
    @Column(name = "protocollo", nullable = false)
    private Protocollo protocollo = Protocollo.BLE;

    @Column(name = "location", length = 255)
    private String location;

    public CampagnaSensore(Campagna campagna, Sensore sensore, boolean attivo) {
        this.campagna = campagna;
        this.sensore = sensore;
        this.attivo = attivo;
        this.protocollo = (protocollo != null) ? protocollo : sensore.getProtocollo();
        this.id = new CampagnaSensoreId(campagna.getId(), sensore.getId());
    }
}
