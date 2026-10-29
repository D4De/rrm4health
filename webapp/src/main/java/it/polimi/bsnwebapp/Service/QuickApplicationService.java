package it.polimi.bsnwebapp.Service;

import java.io.IOException;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import org.springframework.stereotype.Service;

import it.polimi.bsnwebapp.DTO.request.QuickApplicationStartRequest;
import it.polimi.bsnwebapp.Model.Entities.Sensore;
import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import it.polimi.bsnwebapp.Repository.SensoreRepository;
import it.polimi.bsnwebapp.communication.Messages;
import lombok.RequiredArgsConstructor;

/**
 * Avvia applicazioni rapide RRM che non devono essere salvate come campagne.
 */
@Service
@RequiredArgsConstructor
public class QuickApplicationService {

    private static final String BATTERY_APP_ID = "Battery_BLE";

    private final SensoreRepository sensoreRepository;
    private final RrmConnectionService rrmConnectionService;
    private final AppParamJsonService appParamJsonService;

    public void startQuickApplication(QuickApplicationStartRequest request) throws IOException {
        if (request == null) {
            throw new IllegalArgumentException("Richiesta non valida");
        }

        String appId = request.getAppId() == null ? "" : request.getAppId().trim();
        if (!BATTERY_APP_ID.equalsIgnoreCase(appId)) {
            throw new IllegalArgumentException("Applicazione rapida non supportata: " + appId);
        }
        if (request.getIdSensori() == null || request.getIdSensori().isEmpty()) {
            throw new IllegalArgumentException("Selezionare almeno un sensore");
        }

        List<Sensore> sensori = request.getIdSensori().stream()
                .map(id -> sensoreRepository.findById(id)
                        .orElseThrow(() -> new IllegalArgumentException("Sensore non trovato con ID: " + id)))
                .peek(sensore -> {
                    if (sensore.isEliminato()) {
                        throw new IllegalArgumentException("Sensore non disponibile: " + sensorLabel(sensore));
                    }
                    if (!supportsProtocol(sensore, Protocollo.BLE)) {
                        throw new IllegalArgumentException("Sensore non compatibile con BLE: " + sensorLabel(sensore));
                    }
                })
                .sorted(Comparator.comparing(Sensore::getId))
                .collect(Collectors.toList());

        Map<Long, String> sensorLocations = request.getSensorLocations() == null
                ? Map.of()
                : request.getSensorLocations();
        validateLocations(request.getIdSensori(), sensorLocations);

        Map<String, Object> args = new HashMap<>();
        args.put("connectivity", Protocollo.BLE.name());
        args.put("imunames", sensori.stream()
                .map(Sensore::getCodice)
                .filter(codice -> codice != null && !codice.isBlank())
                .collect(Collectors.joining("-")));
        if (String.valueOf(args.get("imunames")).isBlank()) {
            throw new IllegalArgumentException("Lista sensori vuota: selezionare almeno un sensore valido");
        }

        Map<String, String> appParams = appParamJsonService.getAllAppValues(appId);
        if (!appParams.isEmpty()) {
            args.putAll(appParams);
        }
        Map<String, String> overrides = appParamJsonService.sanitizeUserOverrides(appId, request.getUserAppParams());
        if (!overrides.isEmpty()) {
            args.putAll(overrides);
        }

        boolean hasAllLocations = sensori.stream()
                .map(sensore -> sensorLocations.get(sensore.getId()))
                .allMatch(location -> location != null && !location.isBlank());
        if (hasAllLocations) {
            args.put("peripheral_locations", sensori.stream()
                    .map(sensore -> sensorLocations.get(sensore.getId()).trim())
                    .collect(Collectors.joining("-")));
        }

        CompletableFuture<Messages.GlobalStartApplicationResponse> future = rrmConnectionService.startApplication(appId, args);
        Messages.GlobalStartApplicationResponse response;
        try {
            response = future.get(Utils.RRM_START_APPLICATION_TIMEOUT_SECONDS, TimeUnit.SECONDS);
        } catch (Exception e) {
            throw new IOException("Timeout o errore durante l'avvio dell'applicazione su RRM", e);
        }

        if (response == null || !"OK".equals(response.status)) {
            String status = response == null ? "risposta mancante" : response.status;
            throw new IOException("RRM ha risposto con stato non valido: " + status);
        }
    }

    private void validateLocations(List<Long> sensorIds, Map<Long, String> sensorLocations) {
        boolean hasAnyLocation = sensorIds.stream()
                .map(sensorLocations::get)
                .anyMatch(location -> location != null && !location.isBlank());
        boolean hasAllLocations = sensorIds.stream()
                .map(sensorLocations::get)
                .allMatch(location -> location != null && !location.isBlank());
        if (hasAnyLocation && !hasAllLocations) {
            throw new IllegalArgumentException(
                    "Specificare la location per tutti i sensori selezionati oppure non specificarne nessuna");
        }
        for (Long idSensore : sensorIds) {
            String location = sensorLocations.get(idSensore);
            if (location != null && location.trim().length() > 255) {
                throw new IllegalArgumentException("La location dei sensori non può superare 255 caratteri");
            }
        }
    }

    private boolean supportsProtocol(Sensore sensore, Protocollo protocollo) {
        if (sensore == null || protocollo == null) {
            return false;
        }
        if (sensore.getProtocolliSupportati() != null && !sensore.getProtocolliSupportati().isEmpty()) {
            return sensore.getProtocolliSupportati().contains(protocollo);
        }
        return sensore.getProtocollo() == protocollo;
    }

    private String sensorLabel(Sensore sensore) {
        if (sensore == null) return "sconosciuto";
        if (sensore.getCodice() != null && !sensore.getCodice().isBlank()) return sensore.getCodice();
        return String.valueOf(sensore.getId());
    }
}
