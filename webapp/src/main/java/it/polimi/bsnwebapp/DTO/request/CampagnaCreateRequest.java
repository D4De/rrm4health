package it.polimi.bsnwebapp.DTO.request;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonFormat;

import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import lombok.Data;

/**
 * DTO di richiesta per la creazione e l'avvio di una campagna.
 * Viene popolato dal payload JSON dei controller REST e passato ai service per la validazione.
 * Contiene i campi: nome, note, idPersona, idUtenteCreatore, idTipoCampagna, scriptFileName, frequenza,
 * connettivita, idDatabase, idSensori.
 */

@Data
public class CampagnaCreateRequest {
    private String nome;
    private String note;

    private Long idPersona;

    private Long idUtenteCreatore;

    // script da eseguire
    private Long idTipoCampagna;

    private String scriptFileName;

    private Integer frequenza;

    private Integer durata;

    private Protocollo connettivita;

    private Long idDatabase;

    // sensori da usare
    @JsonFormat(with = JsonFormat.Feature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
    private List<Long> idSensori;

    // location assegnata a ciascun sensore per questa specifica campagna
    private Map<Long, String> sensorLocations;

    private Map<String, String> userAppParams;
}
