package it.polimi.bsnwebapp.Controller.api;

import it.polimi.bsnwebapp.DTO.response.SensoreResponse;
import it.polimi.bsnwebapp.Service.SensoreService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Controller REST per la lettura dei sensori lato medico.
 * Espone una lista dei sensori disponibili senza operazioni di modifica.
 */

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/sensori")
public class SensoreMedController {

    private final SensoreService sensoreService;

    @GetMapping
    public ResponseEntity<List<SensoreResponse>> lista() {
        return ResponseEntity.ok(sensoreService.listaSensori());
    }
}
