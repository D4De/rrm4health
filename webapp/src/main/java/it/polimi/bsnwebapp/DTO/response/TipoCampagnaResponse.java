package it.polimi.bsnwebapp.DTO.response;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

/**
 * DTO di risposta per la descrizione di un tipo campagna disponibile.
 * Viene serializzato dai controller REST per alimentare la UI o i client esterni.
 * Campi inclusi: id, codice, descrizione, scriptFileName.
 */

@Data
@NoArgsConstructor
@AllArgsConstructor
public class TipoCampagnaResponse {
    private Long id;
    private String codice;
    private String descrizione;
    private String scriptFileName;
}

