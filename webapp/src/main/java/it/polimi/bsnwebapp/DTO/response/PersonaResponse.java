package it.polimi.bsnwebapp.DTO.response;

import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDate;

/**
 * DTO di risposta per i dettagli anagrafici della persona.
 * Viene serializzato dai controller REST per alimentare la UI o i client esterni.
 * Campi inclusi: id, nome, cognome, dataNascita, note, nomeCompleto.
 */

@Data
@NoArgsConstructor
@AllArgsConstructor
public class PersonaResponse {
    private Long id;
    private String nome;
    private String cognome;
    private LocalDate dataNascita;
    private String note;

    // calcolato per visualizzazione
    private String nomeCompleto;

    public PersonaResponse(Long id, String nome, String cognome, LocalDate dataNascita, String note) {
        this.id = id;
        this.nome = nome;
        this.cognome = cognome;
        this.dataNascita = dataNascita;
        this.note = note;
        this.nomeCompleto = nome + " " + cognome;
    }
}

