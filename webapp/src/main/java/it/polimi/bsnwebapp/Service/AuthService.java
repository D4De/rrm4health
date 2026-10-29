package it.polimi.bsnwebapp.Service;

import it.polimi.bsnwebapp.Model.Entities.Utente;
import it.polimi.bsnwebapp.Model.Enum.RuoloUtente;
import it.polimi.bsnwebapp.Repository.UtenteRepository;
import it.polimi.bsnwebapp.DTO.request.LoginRequest;
import it.polimi.bsnwebapp.DTO.response.LoginResponse;
import it.polimi.bsnwebapp.DTO.request.RegisterRequest;
import it.polimi.bsnwebapp.Security.utils.JwtUtils;
import it.polimi.bsnwebapp.exception.BadRequestException;
import it.polimi.bsnwebapp.exception.ConflictException;
import it.polimi.bsnwebapp.exception.InternalServerErrorException;
import lombok.NonNull;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpHeaders;
import org.springframework.security.authentication.AuthenticationManager;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.stereotype.Service;

import java.util.List;
import java.util.Optional;

/**
 * Service per registrazione e login utenti.
 * Valida i dati in input, verifica duplicati, salva l'utente con password cifrata e genera JWT.
 * In caso di errore solleva eccezioni applicative mappate dai controller.
 */

@Service
@RequiredArgsConstructor
public class AuthService {

    private final UtenteRepository utenteRepository;
    private final PasswordEncoder passwordEncoder;
    private final JwtUtils jwtUtils;
    private final AuthenticationManager authenticationManager;

    /**
     * Metodo per registrare un utente sul database.
     * @param request DTO con i dati per la registrazione.
     * @throws RuntimeException possibile eccezione causata dal client.
     */
    public void registrazioneUtente(@NonNull RegisterRequest request) throws RuntimeException {

        // Normalizzo lo username e assegno a delle variabili i dati della richiesta
        //.trim serve per rimuovere gli spazi bianchi iniziali e finali
        //.toLowerCase serve per convertire tutti i caratteri della strinfa in minuscolo
        final String username = request.getUsername().trim().toLowerCase();
        final String password = request.getPassword();
        final RuoloUtente ruolo = request.getRuolo();

        //Controlla se esiste già un utente con questo username sul DB.
        Optional<Utente> userAlreadyRegistered = utenteRepository.findByUsername(username);
        if (userAlreadyRegistered.isPresent()) {
            throw new ConflictException("Username già registrato");
        }

        //controllo che tutti i campi non siano vuoti
        checkUserData(List.of(username, password));

        //Costruisco l'oggetto e lo salvo sul DB
        Utente utente = new Utente(username, passwordEncoder.encode(password), ruolo);
        utenteRepository.save(utente);

        // Controlla se l'utente è presente sul database, se sì la registrazione è andata a buon fine. Altrimenti, lancia eccezione.
        Optional<Utente> userRegistered = utenteRepository.findByUsername(username);
        if (userRegistered.isEmpty()) {
            throw new InternalServerErrorException("Errore durante la registrazione");
        }
    }

    /**
     * Metodo per il login. Dopo aver eseguito i controlli viene generato un JWT per l'utente loggato.
     * @param request DTO con i dati per il login.
     * @return DTO con i dati dell'utente.
     */
    public LoginResponse login(@NonNull LoginRequest request) {

        // Normalizzo lo username
        final String username = request.getUsername().trim().toLowerCase();
        final String password = request.getPassword();

        // Controllo che i campi non siano vuoti
        checkUserData(List.of(username, password));

        // Autentica l'utente con le credenziali fornite.
        authenticationManager.authenticate(
                new UsernamePasswordAuthenticationToken(username, password));

        // Recupera l'utente dal database.
        Utente user = utenteRepository.findByUsername(username)
                .orElseThrow(() -> new BadRequestException("Credenziali non valide"));

        // Ritorna il DTO con i dati dell'utente e il token JWT.
        return new LoginResponse(
                user.getId(),
                user.getUsername(),
                user.getRuolo(),
                "Accesso effettuato con successo",
                jwtUtils.generateToken(user)
        );
    }

    /**
     * Crea un oggetto {@link HttpHeaders} e aggiunge il token, così da mandarlo al client.
     * @param jwt Stringa con il token.
     * @return L'oggetto {@link HttpHeaders} con il token al suo interno.
     */
    public HttpHeaders putJwtInHttpHeaders(String jwt) {
        HttpHeaders headers = new HttpHeaders();
        headers.add(HttpHeaders.AUTHORIZATION, "Bearer " + jwt);
        return headers;
    }

    /**
     * Controlla se tutti i campi sono stati compilati.
     * @param dataList Lista di stringhe da controllare.
     * @throws RuntimeException Eccezione causata da un campo vuoto.
     */
    private void checkUserData(@NonNull List<String> dataList) throws RuntimeException {
        for (String data : dataList) {
            if (data == null || data.isBlank()) {
                throw new BadRequestException("Dati mancanti");
            }
        }
    }
}