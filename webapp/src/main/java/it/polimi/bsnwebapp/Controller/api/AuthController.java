package it.polimi.bsnwebapp.Controller.api;

import it.polimi.bsnwebapp.DTO.request.LoginRequest;
import it.polimi.bsnwebapp.DTO.request.RegisterRequest;
import it.polimi.bsnwebapp.DTO.response.LoginResponse;
import it.polimi.bsnwebapp.DTO.response.MessageResponse;
import it.polimi.bsnwebapp.Service.AuthService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

/**
 * Controller REST per autenticazione e registrazione utenti.
 * Espone gli endpoint /api/v1/auth/register e /api/v1/auth/login e delega ad AuthService.
 * In caso di login restituisce il JWT sia nel body sia nell'header Authorization.
 */

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/auth")
public class AuthController {

    private final AuthService authService;

    /**
     * Endpoint per la registrazione di un nuovo Utente.
     * Chiama il servizio di autenticazione per registrare l'utente nel sistema.
     * @param request DTO con i dati per la registrazione.
     * @return Messaggio di avvenuta registrazione.
     */
    @PostMapping("/register")
    public ResponseEntity<MessageResponse> registrazioneUtente(@Valid @RequestBody RegisterRequest request) {

        authService.registrazioneUtente(request);

        // Restituisce una risposta di successo con lo stato HTTP 201 Created
        return ResponseEntity
                .status(HttpStatus.CREATED)
                .body(new MessageResponse("Registrazione effettuata con successo"));
    }

    /**
     * Endpoint per il login.
     * Chiama il servizio di autenticazione per autenticare l'utente e ottenere un token JWT.
     * @param request DTO con i dati per il login.
     * @return DTO con l'utente autenticato e un messaggio di avvenuta autenticazione.
     * Nell'header la stringa jwt.
     */
    @PostMapping("/login")
    public ResponseEntity<LoginResponse> login(@Valid @RequestBody LoginRequest request) {
        // Chiama il servizio di autenticazione per autenticare l'utente
        final LoginResponse response = authService.login(request);

        // Restituisce una risposta di successo con lo stato HTTP 200 OK e l'header JWT
        return ResponseEntity
                .status(HttpStatus.OK)
                .headers(authService.putJwtInHttpHeaders(response.getJwtToken()))
                .body(response);
    }
}




