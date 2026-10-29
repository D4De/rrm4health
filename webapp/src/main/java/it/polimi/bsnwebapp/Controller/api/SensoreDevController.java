package it.polimi.bsnwebapp.Controller.api;

import it.polimi.bsnwebapp.DTO.request.SensoreCreateRequest;
import it.polimi.bsnwebapp.DTO.response.SensoreResponse;
import it.polimi.bsnwebapp.Service.SensoreService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;

/**
 * Controller REST per la gestione sensori lato amministrazione (USER_DEV).
 * Consente creazione e listing dei sensori con validazione tramite SensoreService.
 * Espone endpoint sotto /api/v1/dev/sensori.
 */

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/dev/sensori")
public class SensoreDevController {

    private final SensoreService sensoreService;

    @PostMapping
    public ResponseEntity<SensoreResponse> crea(@Valid @RequestBody SensoreCreateRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(sensoreService.creaSensore(request));
    }

    @GetMapping
    public ResponseEntity<List<SensoreResponse>> lista() {
        return ResponseEntity.ok(sensoreService.listaSensori());
    }
}
