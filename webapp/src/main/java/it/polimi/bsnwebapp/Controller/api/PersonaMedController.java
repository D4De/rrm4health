package it.polimi.bsnwebapp.Controller.api;

import it.polimi.bsnwebapp.DTO.request.PersonaCreateRequest;
import it.polimi.bsnwebapp.DTO.response.MessageResponse;
import it.polimi.bsnwebapp.DTO.response.PersonaResponse;
import it.polimi.bsnwebapp.Service.PersonaService;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Controller REST per la gestione delle persone (pazienti).
 * Permette listing, dettaglio e creazione di persone tramite PersonaService.
 * Ritorna PersonaResponse e messaggi di errore coerenti con lo stato HTTP.
 */

@RestController
@RequestMapping("/api/v1/persone")
@RequiredArgsConstructor
public class PersonaMedController {

    private static final Logger logger = LoggerFactory.getLogger(PersonaMedController.class);

    private final PersonaService personaService;

    /**
     * Recupera tutte le persone (pazienti) disponibili.
     * GET /api/v1/persone
     *
     * @return Lista di tutte le persone
     */
    @GetMapping
    public ResponseEntity<?> getAllPersone() {
        try {
            logger.info("Richiesta recupero di tutte le persone");

            List<PersonaResponse> persone = personaService.getAllPersone();

            return ResponseEntity.ok(persone);

        } catch (Exception e) {
            logger.error("Errore durante il recupero delle persone", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Recupera i dettagli di una persona specifica.
     * GET /api/v1/persone/{id}
     *
     * @param id ID della persona
     * @return Dettagli completi della persona
     */
    @GetMapping("/{id}")
    public ResponseEntity<?> getPersonaById(@PathVariable Long id) {
        try {
            logger.info("Richiesta dettagli persona ID: {}", id);

            PersonaResponse persona = personaService.getPersonaById(id);

            return ResponseEntity.ok(persona);

        } catch (IllegalArgumentException e) {
            logger.error("Persona non trovata: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.NOT_FOUND)
                    .body(new MessageResponse("Errore: " + e.getMessage()));

        } catch (Exception e) {
            logger.error("Errore durante il recupero della persona", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Crea una nuova persona (paziente).
     */
    @PostMapping
    public ResponseEntity<?> createPersona(@RequestBody PersonaCreateRequest request) {
        try {
            logger.info("Richiesta creazione nuovo paziente: {} {}", request.getNome(), request.getCognome());

            PersonaResponse persona = personaService.createPersona(request);

            return ResponseEntity
                    .status(HttpStatus.CREATED)
                    .body(persona);

        } catch (IllegalArgumentException e) {
            logger.error("Errore validazione dati: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.BAD_REQUEST)
                    .body(new MessageResponse("Errore: " + e.getMessage()));

        } catch (Exception e) {
            logger.error("Errore durante la creazione della persona", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }
}
