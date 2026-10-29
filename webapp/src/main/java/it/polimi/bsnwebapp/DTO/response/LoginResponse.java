package it.polimi.bsnwebapp.DTO.response;

import it.polimi.bsnwebapp.Model.Enum.RuoloUtente;
import lombok.AllArgsConstructor;
import lombok.Getter;
import lombok.NoArgsConstructor;

/**
 * DTO di risposta per l'esito del login con token JWT e ruolo.
 * Viene serializzato dai controller REST per alimentare la UI o i client esterni.
 * Campi inclusi: userId, username, ruolo, jwtToken, tokenType.
 */

@Getter
@AllArgsConstructor
@NoArgsConstructor
public class LoginResponse {

    private Long userId;
    private String username;
    private RuoloUtente ruolo;

    /**
     * Questo campo contiene il JSON Web Token (JWT) generato dal server dopo un login riuscito.
     * Il JWT è un token di sicurezza che viene utilizzato per autenticare e autorizzare l'utente
     * nelle richieste successive al server. Contiene informazioni sull'utente e sulla sua sessione,
     * ed è firmato digitalmente per garantirne l'integrità. Il client (ad esempio, un'applicazione web o mobile)
     * deve memorizzare questo token e inviarlo in ogni richiesta protetta.
     */
    private String jwtToken;

    /**
     * Questo campo indica il tipo di token di autenticazione.
     * "Bearer" è il tipo più comune e significa che il token deve essere
     * inviato nell'header "Authorization" della richiesta HTTP, preceduto dalla parola "Bearer ".
     * Ad esempio: Authorization: Bearer <jwtToken>.
     * Questo campo è utile per il client per sapere come formattare l'header di autorizzazione.
     */
    private String tokenType = "Bearer";
}