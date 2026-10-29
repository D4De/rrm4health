package it.polimi.bsnwebapp.Controller.sse;

import java.io.IOException;
import java.util.List;
import java.util.concurrent.CopyOnWriteArrayList;

import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import it.polimi.bsnwebapp.DTO.response.SensoreResponse;
import it.polimi.bsnwebapp.Service.SensoreService;
import lombok.RequiredArgsConstructor;

/**
 * SSE controller per notificare cambiamenti nella lista sensori disponibili.
 */
@RestController
@RequiredArgsConstructor
public class SensoriSseController {
    private final SensoreService sensoreService;
    private final List<SseEmitter> emitters = new CopyOnWriteArrayList<>();

    @GetMapping(path = "/sse/sensori", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter sensoriStream() {
        SseEmitter emitter = new SseEmitter(0L); // nessun timeout
        emitters.add(emitter);
        emitter.onCompletion(() -> emitters.remove(emitter));
        emitter.onTimeout(() -> emitters.remove(emitter));
        // invia subito la lista attuale
        try {
            emitter.send(sensoreService.listaSensoriDisponibili(), MediaType.APPLICATION_JSON);
        } catch (IOException ignored) {}
        return emitter;
    }

    /**
     * Notifica tutti i client SSE con la nuova lista sensori.
     */
    public void notifyAllClients() {
        List<SensoreResponse> lista = sensoreService.listaSensoriDisponibili();
        for (SseEmitter emitter : emitters) {
            try {
                emitter.send(lista, MediaType.APPLICATION_JSON);
            } catch (IOException e) {
                emitter.complete();
                emitters.remove(emitter);
            }
        }
    }
}
