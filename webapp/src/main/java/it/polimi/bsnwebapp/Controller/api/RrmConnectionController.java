package it.polimi.bsnwebapp.Controller.api;

import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Enumeration;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;
import java.util.stream.Collectors;

import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.servlet.mvc.method.annotation.SseEmitter;

import it.polimi.bsnwebapp.DTO.request.ConnectionRequest;
import it.polimi.bsnwebapp.DTO.response.SensoreResponse;
import it.polimi.bsnwebapp.Service.RrmConnectionService;
import it.polimi.bsnwebapp.communication.Messages;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor; // use jakarta annotation
/**
 * Controller REST per la gestione della connessione a RRM Global.
 * Gestisce l'inoltro delle richieste di connessione e disconnessione tramite ZeroMQ.
 * Espone endpoint sotto /api/v1/rrm/connection.
 */
@RestController
@RequiredArgsConstructor
@RequestMapping("/api/v1/rrm/connection")
public class RrmConnectionController {

    private final RrmConnectionService connectionService;
    private final it.polimi.bsnwebapp.Service.SettingApplicationService settingApplicationService;
    private final it.polimi.bsnwebapp.Service.SensoreService sensoreService;

    /**
     * Ottiene l'indirizzo IP privato del client sulla rete locale.
     * Se il client è in loopback, rileva l'IP privato della macchina server.
     * 
     * @param request servlet request
     * @return ResponseEntity con IP privato in JSON
     */
    @GetMapping("/local-ip")
    public ResponseEntity<LocalIpResponse> getLocalIP(HttpServletRequest request) {
        String remoteAddr = request.getRemoteAddr();
        
        // Controlla X-Forwarded-For (proxies)
        String forwardedFor = request.getHeader("X-Forwarded-For");
        if (forwardedFor != null && !forwardedFor.isEmpty()) {
            remoteAddr = forwardedFor.split(",")[0].trim();
        }
        
        // Controlla X-Real-IP (nginx, etc.)
        String realIp = request.getHeader("X-Real-IP");
        if (realIp != null && !realIp.isEmpty()) {
            remoteAddr = realIp;
        }
        
        // Se siamo in loopback (localhost), rileva l'IP privato della macchina
        if (remoteAddr.equals("::1") || remoteAddr.equals("0:0:0:0:0:0:0:1") || 
            remoteAddr.equals("127.0.0.1") || remoteAddr.startsWith("127.")) {
            remoteAddr = getPrivateNetworkIP();
        }
        
        return ResponseEntity.ok(new LocalIpResponse(remoteAddr));
    }


    /**
     * Effettua la connessione a RRM Global all'indirizzo e porta specificati.
     * 
     * @param request DTO contente ip e porta
     * @return ResponseEntity con messaggio di successo
     */
    @PostMapping("/connect")
    public ResponseEntity<String> connect(@Valid @RequestBody ConnectionRequest request) {
        try {
            connectionService.initializeConnection(request.getIp(), request.getPort());
            // wait for the initial lists to arrive (short timeout so UI isn't blocked forever)
            boolean ready = connectionService.waitForInitialData(5, java.util.concurrent.TimeUnit.SECONDS);
            if (!ready) {
                connectionService.disconnect();
                return ResponseEntity.status(HttpStatus.GATEWAY_TIMEOUT)
                        .body("Timeout durante la connessione a RRM Global (nessuna risposta)");
            }

            // Salva la configurazione in modo persistente
            settingApplicationService.setValue("rrm.ip", request.getIp());
            settingApplicationService.setValue("rrm.port", String.valueOf(request.getPort()));

            String message = String.format("Connessione avviata verso %s:%d", request.getIp(), request.getPort());
            return ResponseEntity.ok(message);
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Errore di connessione: " + e.getMessage());
        }
        /**
         * Endpoint per recuperare la configurazione RRM persistente
         */
    }

    @GetMapping("/config")
    public ResponseEntity<Map<String, Object>> getRrmConfig() {
        String ip = settingApplicationService.getValue("rrm.ip");
        String port = settingApplicationService.getValue("rrm.port");
        return ResponseEntity.ok(Map.of("ip", ip, "port", port));
    }
    /**
     * Chiude la connessione a RRM Global.
     * 
     * @return ResponseEntity con messaggio di successo
     */
    @PostMapping("/disconnect")
    public ResponseEntity<String> disconnect() {
        // nota: il service disconnette anche se ci sono handler registrati
        try {
            connectionService.disconnect();
            return ResponseEntity.ok("Connessione chiusa");
        } catch (Exception e) {
            return ResponseEntity.status(HttpStatus.INTERNAL_SERVER_ERROR)
                    .body("Errore durante la disconnessione: " + e.getMessage());
        }
    }

    /**
     * Richiede la lista delle policy a RRM Global e restituisce il valore
     * attualmente memorizzato (potrebbe essere precedente se la risposta non è ancora arrivata).
     */
    @GetMapping("/policies")
    public ResponseEntity<Map<String,Object>> policies() {
        // Trigger a fresh request to RRM Global
        connectionService.sendMessage(new it.polimi.bsnwebapp.communication.Messages.GUIListPolicies());
        java.util.List<String> list = connectionService.getAvailablePolicies();
        Map<String,Object> response = Map.of(
            "current", connectionService.getCurrentPolicy(),
            "available", list == null ? java.util.List.of() : list
        );
        return ResponseEntity.ok(response);
    }

    /**
     * Richiede la lista delle applicazioni a RRM Global e restituisce il valore memorizzato.
     */
    @GetMapping("/applications")
    public ResponseEntity<java.util.List<Map<String,Object>>> applications() {
        connectionService.sendMessage(new it.polimi.bsnwebapp.communication.Messages.GUIListApplications());
        java.util.List<Map<String,Object>> list = connectionService.getAvailableApplications();
        return ResponseEntity.ok(list == null ? java.util.List.of() : list);
    }

    /**
     * Richiede la lista dei descrittori delle applicazioni a RRM Global e
     * restituisce il valore memorizzato. note: entries contain only the executable parameters
     * section (sufficient for UI argument forms) rather than whole manifest objects.
     */
    @GetMapping("/applications/descriptors")
    public ResponseEntity<java.util.List<Map<String,Object>>> applicationDescriptors() {
        connectionService.sendMessage(new it.polimi.bsnwebapp.communication.Messages.GUIListAvailableApplications());
        java.util.List<Map<String,Object>> list = connectionService.getAvailableDescriptors();
        return ResponseEntity.ok(list == null ? java.util.List.of() : list);
    }

    /**
     * Richiede lo stato risorse a RRM Global e restituisce i dati filtrati.
     */
    @GetMapping("/resources-status")
    public ResponseEntity<Map<String,Object>> resourcesStatus() {
        return ResponseEntity.ok(filteredResourcesPayload());
    }

    /**
     * Restituisce solo le risorse RRM il cui resource_id corrisponde al codice sensore DB.
     */
    @GetMapping("/resources-status/filtered")
    public ResponseEntity<Map<String, Object>> filteredResourcesStatus() {
        return ResponseEntity.ok(filteredResourcesPayload());
    }

    /**
     * Restituisce solo i nodi online ricevuti da RRM.
     */
    @GetMapping("/nodes-status/online")
    public ResponseEntity<Map<String, Object>> onlineNodesStatus() {
        return ResponseEntity.ok(onlineNodesPayload());
    }

    /**
     * Stream SSE per aggiornare in tempo reale lo stato risorse filtrato.
     */
    @GetMapping(value = "/resources-status/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter resourcesStatusEvents() {
        SseEmitter emitter = new SseEmitter(0L);
        ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();

        scheduler.scheduleAtFixedRate(() -> {
            try {
                Map<String, Object> payload = filteredResourcesPayload();
                emitter.send(SseEmitter.event()
                    .name("resources-status")
                    .data(payload));
            } catch (java.io.IOException | IllegalStateException ignored) {
                scheduler.shutdownNow();
                emitter.complete();
            } catch (Exception e) {
                scheduler.shutdownNow();
                emitter.completeWithError(e);
            }
        }, 0, 1, TimeUnit.SECONDS);

        emitter.onCompletion(scheduler::shutdownNow);
        emitter.onTimeout(scheduler::shutdownNow);
        emitter.onError(throwable -> scheduler.shutdownNow());

        return emitter;
    }

    /**
     * Stream SSE per aggiornare in tempo reale lo stato nodi online.
     */
    @GetMapping(value = "/nodes-status/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter nodesStatusEvents() {
        SseEmitter emitter = new SseEmitter(0L);
        ScheduledExecutorService scheduler = Executors.newSingleThreadScheduledExecutor();

        scheduler.scheduleAtFixedRate(() -> {
            try {
                Map<String, Object> payload = onlineNodesPayload();
                emitter.send(SseEmitter.event()
                    .name("nodes-status")
                    .data(payload));
            } catch (java.io.IOException | IllegalStateException ignored) {
                scheduler.shutdownNow();
                emitter.complete();
            } catch (Exception e) {
                scheduler.shutdownNow();
                emitter.completeWithError(e);
            }
        }, 0, 1, TimeUnit.SECONDS);

        emitter.onCompletion(scheduler::shutdownNow);
        emitter.onTimeout(scheduler::shutdownNow);
        emitter.onError(throwable -> scheduler.shutdownNow());

        return emitter;
    }

    /**
     * Stream SSE delle notifiche asincrone inviate dall'RRM alle GUI.
     */
    @GetMapping(value = "/gui-notifications/events", produces = MediaType.TEXT_EVENT_STREAM_VALUE)
    public SseEmitter guiNotificationsEvents() {
        SseEmitter emitter = new SseEmitter(0L);
        Runnable unsubscribe = connectionService.subscribeGuiNotifications(notification ->
            emitter.send(SseEmitter.event()
                .name("gui-notification")
                .data(notification.toMap()))
        );

        emitter.onCompletion(unsubscribe);
        emitter.onTimeout(unsubscribe);
        emitter.onError(throwable -> unsubscribe.run());

        return emitter;
    }

    private Map<String, Object> filteredResourcesPayload() {
        boolean connected = connectionService.isConnectionAlive();
        List<Map<String, Object>> rawResources = connectionService.getResourcesStatus();
        Integer totalFromRrmValue = connectionService.getResourcesCount();
        int totalFromRrm = totalFromRrmValue != null
            ? totalFromRrmValue
            : (rawResources == null ? 0 : rawResources.size());

        Set<String> sensorCodes = sensoreService.listaSensori().stream()
            .map(SensoreResponse::getCodice)
            .filter(code -> code != null && !code.isBlank())
            .map(code -> code.trim().toUpperCase())
            .collect(Collectors.toSet());

        List<Map<String, Object>> filtered = (rawResources == null ? List.<Map<String, Object>>of() : rawResources)
            .stream()
            .filter(resource -> {
                Object rawId = resource.get("resource_id");
                if (rawId == null) {
                    return false;
                }
                String resourceId = rawId.toString().trim().toUpperCase();
                return sensorCodes.contains(resourceId);
            })
            .toList();

        return Map.of(
            "connected", connected,
            "resources", filtered,
            "count", filtered.size(),
            "countTotal", totalFromRrm
        );
    }

    private Map<String, Object> onlineNodesPayload() {
        boolean connected = connectionService.isConnectionAlive();
        List<Map<String, Object>> rawNodes = connectionService.getNodesStatus();
        Integer totalFromRrmValue = connectionService.getNodesCount();
        int totalFromRrm = totalFromRrmValue != null
            ? totalFromRrmValue
            : (rawNodes == null ? 0 : rawNodes.size());

        List<Map<String, Object>> online = (rawNodes == null ? List.<Map<String, Object>>of() : rawNodes)
            .stream()
            .filter(this::isNodeOnline)
            .toList();

        return Map.of(
            "connected", connected,
            "nodes", online,
            "count", online.size(),
            "countTotal", totalFromRrm
        );
    }

    private boolean isNodeOnline(Map<String, Object> node) {
        Object rawOnline = node.get("online");
        if (rawOnline instanceof Boolean onlineValue) {
            return onlineValue;
        }
        if (rawOnline != null) {
            String onlineText = rawOnline.toString().trim().toLowerCase();
            if ("true".equals(onlineText)) {
                return true;
            }
            if ("false".equals(onlineText)) {
                return false;
            }
        }

        Object rawStatus = node.get("status");
        if (rawStatus == null) {
            return false;
        }
        String status = rawStatus.toString().trim().toUpperCase();
        return !"DISCONNECTED".equals(status) && !"OFFLINE".equals(status);
    }

    /**
     * Rileva l'indirizzo IP privato della macchina server sulla rete locale.
     * Preferisce 192.168.x.x, poi 10.x.x.x, evita 172.x.x.x (Docker).
     * 
     * @return IP privato (es. 192.168.x.x, 10.x.x.x) o "127.0.0.1" se non trovato
     */
    private String getPrivateNetworkIP() {
        String fallbackIP = null;
        
        try {
            Enumeration<NetworkInterface> interfaces = NetworkInterface.getNetworkInterfaces();
            while (interfaces.hasMoreElements()) {
                NetworkInterface networkInterface = interfaces.nextElement();
                if (networkInterface.isLoopback() || !networkInterface.isUp()) {
                    continue;
                }
                
                Enumeration<InetAddress> addresses = networkInterface.getInetAddresses();
                while (addresses.hasMoreElements()) {
                    InetAddress addr = addresses.nextElement();
                    
                    // Salta IPv6 e link-local addresses
                    if (addr.getAddress().length != 4 || addr.isLinkLocalAddress()) {
                        continue;
                    }
                    
                    String ip = addr.getHostAddress();
                    
                    // Preferisci 192.168.x.x (rete locale comune)
                    if (ip.startsWith("192.168.")) {
                        return ip;
                    }
                    
                    // Fallback: 10.x.x.x
                    if (ip.startsWith("10.") && fallbackIP == null) {
                        fallbackIP = ip;
                    }
                    
                    // Evita 172.x.x.x perché tipicamente Docker
                }
            }
        } catch (Exception e) 
        {
            // Se c'è un errore, ritorna localhost
        }
        
        // Ritorna il fallback se non ha trovato 192.168.x.x
        if (fallbackIP != null) {
            return fallbackIP;
        }
        
        return "127.0.0.1";
    }
    /**
     * DTO per la risposta dell'indirizzo IP locale
     */
    public record LocalIpResponse(String ip) {}
}
