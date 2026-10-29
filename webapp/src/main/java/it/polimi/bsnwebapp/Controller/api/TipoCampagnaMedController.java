package it.polimi.bsnwebapp.Controller.api;

import it.polimi.bsnwebapp.DTO.response.MessageResponse;
import it.polimi.bsnwebapp.DTO.response.TipoCampagnaResponse;
import it.polimi.bsnwebapp.Service.TipoCampagnaService;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Controller REST per la consultazione dei tipi campagna disponibili.
 * Restituisce lista e dettaglio dei tipi definiti a catalogo tramite TipoCampagnaService.
 */

@RestController
@RequestMapping("/api/v1/tipi-campagna")
@RequiredArgsConstructor
public class TipoCampagnaMedController {

    private static final Logger logger = LoggerFactory.getLogger(TipoCampagnaMedController.class);

    private final TipoCampagnaService tipoCampagnaService;

    /**
     * Recupera tutti i tipi di campagna disponibili.
     */
    @GetMapping
    public ResponseEntity<?> getAllTipiCampagna() {
        try {
            logger.info("Richiesta recupero di tutti i tipi di campagna");

            List<TipoCampagnaResponse> tipi = tipoCampagnaService.getAllTipiCampagna();

            return ResponseEntity.ok(tipi);

        } catch (Exception e) {
            logger.error("Errore durante il recupero dei tipi di campagna", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }

    /**
     * Recupera i dettagli di un tipo di campagna specifico.
     */
    @GetMapping("/{id}")
    public ResponseEntity<?> getTipoCampagnaById(@PathVariable Long id) {
        try {
            logger.info("Richiesta dettagli tipo campagna ID: {}", id);

            TipoCampagnaResponse tipo = tipoCampagnaService.getTipoCampagnaById(id);

            return ResponseEntity.ok(tipo);

        } catch (IllegalArgumentException e) {
            logger.error("Tipo campagna non trovato: {}", e.getMessage());
            return ResponseEntity
                    .status(HttpStatus.NOT_FOUND)
                    .body(new MessageResponse("Errore: " + e.getMessage()));

        } catch (Exception e) {
            logger.error("Errore durante il recupero del tipo di campagna", e);
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore interno del server"));
        }
    }
}
