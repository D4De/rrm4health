package it.polimi.bsnwebapp.Model.Entities;

import jakarta.persistence.*;
import lombok.Getter;
import lombok.NoArgsConstructor;
import lombok.Setter;

/**
 * Entity JPA che rappresenta un tipo di campagna (dizionario).
 * Mappa la tabella {@code tipo_campagna} con codice, descrizione e script associato.
 * E' collegata alle campagne via {@code campagna_tipo} ed e' usata per selezionare lo script da avviare.
 */

@Entity
@Table(name = "tipo_campagna")
@Getter
@Setter
@NoArgsConstructor
public class TipoCampagna {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    @Column(name = "id_tipo", updatable = false, nullable = false)
    private Long id;

    @Column(name = "codice", nullable = false, unique = true, length = 30)
    private String codice;    //es: IMU, ECG...

    @Column(name = "descrizione", nullable = false, length = 100)
    private String descrizione;

    @Column(name = "script_filename", nullable = false)
    private String scriptFileName;  //es: respiro.py


    public TipoCampagna(String codice, String descrizione) {
        this.codice = codice;
        this.descrizione = descrizione;
        this.scriptFileName = scriptFileName;
    }
}
