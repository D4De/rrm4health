package it.polimi.bsnwebapp.DTO.request;

import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;


/**
 * DTO di richiesta per l'autenticazione utente.
 * Viene popolato dal payload JSON dei controller REST e passato ai service per la validazione.
 * Contiene i campi: username, password.
 */

@Getter
@AllArgsConstructor
@NoArgsConstructor
public class LoginRequest {
    private String username;
    private String password;
}
