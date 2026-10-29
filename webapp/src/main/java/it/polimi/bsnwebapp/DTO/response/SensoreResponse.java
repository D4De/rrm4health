package it.polimi.bsnwebapp.DTO.response;

import java.util.Set;

import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import it.polimi.bsnwebapp.Model.Enum.TipoMisura;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * DTO di risposta per i dettagli di un sensore registrato.
 * Viene serializzato dai controller REST per alimentare la UI o i client esterni.
 * Campi inclusi: id, codice, nome, tipo, protocolloDefault, protocolliSupportati, misureSupportate.
 */

@Getter
@NoArgsConstructor
public class SensoreResponse {
    private Long id;
    private String codice;
    private String nome;
    private String tipo;
    private Protocollo protocolloDefault;
    private Set<Protocollo> protocolliSupportati;
    private Set<TipoMisura> misureSupportate;
    private boolean occupato;

    public SensoreResponse(Long id, String codice, String nome, String tipo, Protocollo protocolloDefault, Set<Protocollo> protocolliSupportati, Set<TipoMisura> misureSupportate, boolean occupato) {
        this.id = id;
        this.codice = codice;
        this.nome = nome;
        this.tipo = tipo;
        this.protocolloDefault = protocolloDefault;
        this.protocolliSupportati = protocolliSupportati;
        this.misureSupportate = misureSupportate;
        this.occupato = occupato;
    }

    // Costruttore lombok AllArgsConstructor NON copre il nuovo campo, quindi lo aggiungo manualmente
}
