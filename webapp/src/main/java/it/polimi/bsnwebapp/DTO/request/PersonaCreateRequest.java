package it.polimi.bsnwebapp.DTO.request;

import lombok.Data;
import java.time.LocalDate;

/**
 * DTO di richiesta per la creazione o aggiornamento di una persona.
 * Viene popolato dal payload JSON dei controller REST e passato ai service per la validazione.
 * Contiene i campi: nome, cognome, dataNascita, note.
 */

@Data
public class PersonaCreateRequest {
    private String nome;
    private String cognome;
    private LocalDate dataNascita;
    private String note;
}

