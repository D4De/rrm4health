package it.polimi.bsnwebapp.Controller.api;

import java.io.IOException;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import it.polimi.bsnwebapp.DTO.request.QuickApplicationStartRequest;
import it.polimi.bsnwebapp.DTO.response.MessageResponse;
import it.polimi.bsnwebapp.Service.AppParamJsonService;
import it.polimi.bsnwebapp.Service.QuickApplicationService;
import lombok.RequiredArgsConstructor;

@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/apps")
public class AppParamController {

    private final AppParamJsonService appParamJsonService;
    private final QuickApplicationService quickApplicationService;

    @GetMapping("/{appId}/editable-params")
    public ResponseEntity<Map<String, String>> getEditableParams(@PathVariable String appId) {
        return ResponseEntity.ok(appParamJsonService.getEditableParamsForUser(appId));
    }

    @PostMapping("/quick-start")
    public ResponseEntity<?> quickStart(@RequestBody QuickApplicationStartRequest request) {
        try {
            quickApplicationService.startQuickApplication(request);
            return ResponseEntity.ok(new MessageResponse("Applicazione avviata con successo"));
        } catch (IllegalArgumentException | IllegalStateException e) {
            return ResponseEntity
                    .status(HttpStatus.BAD_REQUEST)
                    .body(new MessageResponse("Errore: " + e.getMessage()));
        } catch (IOException e) {
            return ResponseEntity
                    .status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body(new MessageResponse("Errore avvio applicazione: " + e.getMessage()));
        }
    }
}
