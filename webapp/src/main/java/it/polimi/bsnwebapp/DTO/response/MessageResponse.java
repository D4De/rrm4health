package it.polimi.bsnwebapp.DTO.response;

import lombok.AllArgsConstructor;
import lombok.Getter;

/**
 * DTO di risposta per un messaggio testuale semplice verso il client.
 * Viene serializzato dai controller REST per alimentare la UI o i client esterni.
 * Campi inclusi: message.
 */

@Getter
@AllArgsConstructor
public class MessageResponse {

    private String message;
}