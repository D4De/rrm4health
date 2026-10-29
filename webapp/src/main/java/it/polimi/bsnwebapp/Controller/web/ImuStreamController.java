package it.polimi.bsnwebapp.Controller.web;

import it.polimi.bsnwebapp.Service.MqttSseService;
import lombok.RequiredArgsConstructor;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

/**
 * Controller REST per lo streaming SSE dei dati IMU.
 * Espone /sse/imu e crea un SseEmitter filtrando opzionalmente per imuid o cname.
 * La sorgente dati e' MqttSseService che riceve i messaggi MQTT in tempo reale.
 */

@RestController
@RequiredArgsConstructor
@RequestMapping("/sse")
public class ImuStreamController {

    private final MqttSseService mqttSseService;

    /**
     * Endpoint SSE per lo streaming dei dati IMU.
     * Consente filtri opzionali su imuid (lista separata da virgola) e cname (nome campagna).
     *
     * @param imuid codici sensore da filtrare
     * @param cname nome campagna da filtrare
     * @return emitter SSE connesso al broker MQTT
     */
    @GetMapping(path = "/imu", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter streamImu(
            @RequestParam(value = "imuid", required = false) String imuid,
            @RequestParam(value = "cname", required = false) String cname,
            @RequestParam(value = "campaignId", required = false) Long campaignId
    ) {
        return mqttSseService.createEmitter(imuid, cname, campaignId);
    }
}
