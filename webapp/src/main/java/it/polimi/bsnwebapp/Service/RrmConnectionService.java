package it.polimi.bsnwebapp.Service;

import org.zeromq.ZMQ;
import org.zeromq.ZContext;
import org.zeromq.SocketType;
import org.springframework.context.ApplicationEventPublisher;
import org.springframework.stereotype.Service;
import org.springframework.beans.factory.annotation.Autowired;

import jakarta.annotation.PreDestroy;
import java.util.Map;
import it.polimi.bsnwebapp.communication.MessageType;
import it.polimi.bsnwebapp.communication.Messages;
import it.polimi.bsnwebapp.communication.Message;
import java.util.concurrent.BlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.LinkedBlockingQueue;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.ConcurrentLinkedQueue;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.LinkedHashSet;
import java.util.Set;

/**
 * Service che incapsula il client ZeroMQ verso RRM Global.
 * Replica in Java il comportamento di ChannelManagerClient.py utilizzato dal frontend Python.
 *
 * Fornisce metodi per connettersi/disconnettersi e inviare messaggi, oltre a una callback interna
 * che processa i messaggi ricevuti ("handler").
 */
@Service
public class RrmConnectionService {
    @Autowired
    private it.polimi.bsnwebapp.Service.SettingApplicationService settingApplicationService;

    private ZContext context;
    private ZMQ.Socket socket;
    private ExecutorService executor;
    private volatile boolean running;
    private BlockingQueue<Map<String, Object>> sendQueue;

    private String localIdentity;
    private String rrmUri;

    // Service per persistere i descrittori delle applicazioni nel database
    @Autowired
    private ApplicazioneDescrittoreService applicazioneDescrittoreService;

    @Autowired
    private RrmGuiNotificationMapper guiNotificationMapper;

    @Autowired
    private ApplicationEventPublisher applicationEventPublisher;

    /*
     * Stato mantenuto dal servizio, usato inoltre dal controller per aggiornare la UI.
     */
    private String currentPolicy;
    private java.util.List<String> availablePolicies;
    private java.util.List<Map<String,Object>> availableApplications;
    private java.util.List<Map<String, Object>> availableDescriptors;  // holds name+parameters maps from RRM (only executable parameters, not full manifest)
    private java.util.List<Map<String, Object>> resourcesStatus;
    private Integer resourcesCount;
    private java.util.List<Map<String, Object>> nodesStatus;
    private Integer nodesCount;
    private final AtomicBoolean resourcesStatusRequestInFlight = new AtomicBoolean(false);
    private final AtomicBoolean resourcesStatusReloadRequested = new AtomicBoolean(false);
    private final AtomicBoolean nodesStatusRequestInFlight = new AtomicBoolean(false);
    private final AtomicBoolean nodesStatusReloadRequested = new AtomicBoolean(false);

    // helper for signalling when we have the initial lists after connecting
    private CompletableFuture<Void> initialDataFuture;
    private java.util.concurrent.atomic.AtomicBoolean policiesReceived = new java.util.concurrent.atomic.AtomicBoolean(false);
    private java.util.concurrent.atomic.AtomicBoolean descriptorsReceived = new java.util.concurrent.atomic.AtomicBoolean(false);
    // keep applicationsReceived only if we ever need running apps acknowledgement
    private java.util.concurrent.atomic.AtomicBoolean applicationsReceived = new java.util.concurrent.atomic.AtomicBoolean(false);

    // pending futures for start-application requests keyed by appID
    private final java.util.Map<String, CompletableFuture<Messages.GlobalStartApplicationResponse>> pendingStartFutures = new java.util.concurrent.ConcurrentHashMap<>();
    private final java.util.Map<String, CompletableFuture<Messages.GlobalStopApplicationResponse>> pendingStopFutures = new java.util.concurrent.ConcurrentHashMap<>();
    private final ConcurrentLinkedQueue<Messages.GlobalGuiNotification> pendingGuiNotifications = new ConcurrentLinkedQueue<>();
    private final Set<GuiNotificationSubscriber> guiNotificationSubscribers = new LinkedHashSet<>();
    private final Object guiNotificationLock = new Object();

    @FunctionalInterface
    public interface GuiNotificationSubscriber {
        void send(Messages.GlobalGuiNotification notification) throws Exception;
    }

    // accessor methods for controller
    public String getCurrentPolicy() { return currentPolicy; }
    public java.util.List<String> getAvailablePolicies() { return availablePolicies; }
    public java.util.List<Map<String,Object>> getAvailableApplications() { return availableApplications; }
    public void setCurrentPolicy(String policy) { this.currentPolicy = policy; }
    public void setAvailablePolicies(java.util.List<String> policies) { this.availablePolicies = policies; }
    public void setAvailableApplications(java.util.List<Map<String,Object>> apps) { this.availableApplications = apps; }

    public java.util.List<Map<String,Object>> getAvailableDescriptors() { return availableDescriptors; }
    public void setAvailableDescriptors(java.util.List<Map<String,Object>> descs) { this.availableDescriptors = descs; }
    public java.util.List<Map<String,Object>> getResourcesStatus() { return resourcesStatus; }
    public void setResourcesStatus(java.util.List<Map<String,Object>> resourcesStatus) { this.resourcesStatus = resourcesStatus; }
    public Integer getResourcesCount() { return resourcesCount; }
    public void setResourcesCount(Integer resourcesCount) { this.resourcesCount = resourcesCount; }
    public java.util.List<Map<String,Object>> getNodesStatus() { return nodesStatus; }
    public void setNodesStatus(java.util.List<Map<String,Object>> nodesStatus) { this.nodesStatus = nodesStatus; }
    public Integer getNodesCount() { return nodesCount; }
    public void setNodesCount(Integer nodesCount) { this.nodesCount = nodesCount; }
    public void refreshResourcesStatusFromRrm() {
        if (!running) {
            return;
        }
        if (resourcesStatusRequestInFlight.compareAndSet(false, true)) {
            sendMessage(new Messages.GUIListResourcesStatus());
            return;
        }
        resourcesStatusReloadRequested.set(true);
    }

    public void refreshNodesStatusFromRrm() {
        if (!running) {
            return;
        }
        if (nodesStatusRequestInFlight.compareAndSet(false, true)) {
            sendMessage(new Messages.GUIListNodesStatus());
            return;
        }
        nodesStatusReloadRequested.set(true);
    }

    public void refreshRuntimeStatusFromRrm() {
        refreshResourcesStatusFromRrm();
        refreshNodesStatusFromRrm();
    }

    public Runnable subscribeGuiNotifications(GuiNotificationSubscriber subscriber) {
        synchronized (guiNotificationLock) {
            guiNotificationSubscribers.add(subscriber);

            Messages.GlobalGuiNotification pending;
            while ((pending = pendingGuiNotifications.peek()) != null) {
                try {
                    subscriber.send(pending);
                    pendingGuiNotifications.poll();
                } catch (Exception e) {
                    guiNotificationSubscribers.remove(subscriber);
                    break;
                }
            }
        }

        AtomicBoolean subscribed = new AtomicBoolean(true);
        return () -> {
            if (subscribed.compareAndSet(true, false)) {
                synchronized (guiNotificationLock) {
                    guiNotificationSubscribers.remove(subscriber);
                }
            }
        };
    }

    void publishGuiNotification(Messages.GlobalGuiNotification notification) {
        synchronized (guiNotificationLock) {
            boolean delivered = false;
            var iterator = guiNotificationSubscribers.iterator();
            while (iterator.hasNext()) {
                GuiNotificationSubscriber subscriber = iterator.next();
                try {
                    subscriber.send(notification);
                    delivered = true;
                } catch (Exception e) {
                    iterator.remove();
                }
            }

            if (!delivered) {
                pendingGuiNotifications.offer(notification);
            }
        }
    }

    private void onResourcesStatusResponse(java.util.List<Map<String, Object>> resources, Integer count) {
        resourcesStatus = resources;
        resourcesCount = count;
        resourcesStatusRequestInFlight.set(false);

        if (resourcesStatusReloadRequested.compareAndSet(true, false) && running) {
            if (resourcesStatusRequestInFlight.compareAndSet(false, true)) {
                sendMessage(new Messages.GUIListResourcesStatus());
            }
        }
    }

    private void onNodesStatusResponse(java.util.List<Map<String, Object>> nodes, Integer count) {
        nodesStatus = nodes;
        nodesCount = count;
        nodesStatusRequestInFlight.set(false);

        if (nodesStatusReloadRequested.compareAndSet(true, false) && running) {
            if (nodesStatusRequestInFlight.compareAndSet(false, true)) {
                sendMessage(new Messages.GUIListNodesStatus());
            }
        }
    }

    public RrmConnectionService() {
        this.sendQueue = new LinkedBlockingQueue<>();
    }

    /**
     * Prova a connettersi automaticamente usando la configurazione persistente.
     * Restituisce true se la connessione è stata avviata, false altrimenti.
     */
    public boolean tryAutoConnect() {
        // Se già connesso, non ristabilire la connessione
        if (socket != null && running) {
            System.out.println("[RRM-CONNECTION] Connessione già attiva, skip auto-connect.");
            return true;
        }
        String ip = settingApplicationService != null ? settingApplicationService.getValue("rrm.ip") : null;
        String portStr = settingApplicationService != null ? settingApplicationService.getValue("rrm.port") : null;
        if (ip != null && !ip.isBlank() && portStr != null && !portStr.isBlank()) {
            try {
                int port = Integer.parseInt(portStr);
                initializeConnection(ip, port);
                boolean ready = waitForInitialData(5, TimeUnit.SECONDS);
                if (!ready) {
                    System.out.println("[RRM-CONNECTION] Auto-connect failed: no initial data from RRM Global.");
                    disconnect();
                    return false;
                }
                return true;
            } catch (Exception e) {
                System.out.println("[RRM-CONNECTION] Errore auto-connessione: " + e.getMessage());
            }
        }
        return false;
    }
    

    public void initializeConnection(String localIp, int localPort, String rrmIp, int rrmPort) {
        this.localIdentity = localIp + ":" + localPort;
        this.rrmUri = "tcp://" + rrmIp + ":" + rrmPort;

        // prepare fresh future each time we create a connection
        initialDataFuture = new CompletableFuture<>();
        policiesReceived.set(false);
        descriptorsReceived.set(false);
        applicationsReceived.set(false);

        startSocket();
    }

    /**
     * Convenience variant: decide automaticamente indirizzo e porta locali
     * usati come identity (simile al comportamento Python). La porta è
     * un numero casuale non vincolante, l'IP è quello della prima interfaccia
     * non-loopback.
     */
    public void initializeConnection(String rrmIp, int rrmPort) {
        String localIp = Utils.getLocalIp();
        int localPort = Utils.getFreePort();
        initializeConnection(localIp, localPort, rrmIp, rrmPort);
    }

    private void startSocket() {
        context = new org.zeromq.ZContext();
        socket = context.createSocket(SocketType.DEALER);
        socket.monitor("inproc://rrm-monitor",
        ZMQ.EVENT_CONNECTED
      | ZMQ.EVENT_DISCONNECTED
      | ZMQ.EVENT_CONNECT_RETRIED
      | ZMQ.EVENT_CLOSED);
        ZMQ.Socket monitor = context.createSocket(SocketType.PAIR);
        monitor.connect("inproc://rrm-monitor");
        socket.setReceiveTimeOut(1000);
        socket.setIdentity(localIdentity.getBytes());
        socket.connect(rrmUri);

        running = true;
        System.out.println("[RRM-CONNECTION] RRM connected! Local identity: " + localIdentity + ", RRM URI: " + rrmUri);

        executor = Executors.newFixedThreadPool(3);
        executor.submit(this::receiverLoop);
        System.out.println("[RRM-CONNECTION] RRM receiver loop started.");
        executor.submit(this::senderLoop);
        System.out.println("[RRM-CONNECTION] RRM sender loop started.");
        executor.submit(() -> monitorLoop(monitor));
        System.out.println("[RRM-CONNECTION] RRM monitor loop started.");


        // Registra subito la GUI a RRM Global, così da ricevere la risposta con lo stato attuale e triggerare l'inizializzazione dei dati (policy/app disponibili)
        //Todo: conviene fare un file a parte per i messaggi? magari con un enum per i tipi di messaggio, così eviti errori di battitura
        sendMessage(new Messages.GUIRegister());
        System.out.println("[RRM-CONNECTION] Sent initial GUIRegister message to RRM Global.");
    }

    private void receiverLoop() {
        while (running && !Thread.currentThread().isInterrupted()) {
            try {
                byte[] reply = socket.recv(0);
                if (reply == null) {
                    continue;
                }
                String json = new String(reply);
                System.out.println("[RRM-CONNECTION][DEBUG] Received message map json: " + json);
                Map<String, Object> messageMap = JsonUtils.fromJson(json);
                System.out.println("[RRM-CONNECTION][DEBUG] Received message map: " + messageMap);
                //Se il messaggio ha una chiave "type" con valore "Global.StartApplicationResponse" allora devi prendere il valore di "appID" e se è un arraylist allora devi convertirlo in stringa nel formato "(elem1,elem2)"
                normalizeStartApplicationResponseAppId(messageMap);
                //System.out.println("[RRM-CONNECTION][DEBUG] Received message map: " + messageMap);
                Message message = Messages.fromMap(messageMap);
                if (message != null) {
                    processMessage(message);
                }
            } catch (Exception e) {
                // log error
                e.printStackTrace();
                if (running) {
                    System.out.println("[RRM-CONNECTION] Receiver loop error: marking connection as disconnected.");
                    disconnect();
                }
                break;
            }
        }
    }

    private void normalizeStartApplicationResponseAppId(Map<String, Object> messageMap) {
        String type = String.valueOf(messageMap.get("type"));
        if (!MessageType.GLOBAL_START_APPLICATION_RESPONSE.getValue().equals(type)
                && !MessageType.GLOBAL_STOP_APPLICATION_RESPONSE.getValue().equals(type)) {
            return;
        }
        Object appId = messageMap.get("appID");
        if (!(appId instanceof java.util.ArrayList<?> appIdList)) {
            return;
        }

        StringBuilder normalizedAppId = new StringBuilder("(");
        for (int i = 0; i < appIdList.size(); i++) {
            if (i > 0) {
                normalizedAppId.append(", ");
            }
            String value = String.valueOf(appIdList.get(i));
            if (i == 0) {
                normalizedAppId.append('\'').append(value.replace("'", "\\'"))
                    .append('\'');
            } else {
                normalizedAppId.append(value);
            }
        }
        normalizedAppId.append(')');
        messageMap.put("appID", normalizedAppId.toString());
    }


    private void senderLoop() {
        while (running || !sendQueue.isEmpty()) {
            try {
                Map<String, Object> msg = sendQueue.poll(1, TimeUnit.SECONDS);
                if (msg != null) {
                    String json = JsonUtils.toJson(msg);
                    socket.send(json.getBytes());
                }
            } catch (InterruptedException ie) {
                Thread.currentThread().interrupt();
            } catch (Exception e) {
                e.printStackTrace();
                break;
            }
        }
    }

    private void monitorLoop(ZMQ.Socket monitor) {
        while (running && !Thread.currentThread().isInterrupted()) {
            try {
                ZMQ.Event event = ZMQ.Event.recv(monitor);
                if (event == null) {
                    continue;
                }
                switch (event.getEvent()) {

                case ZMQ.EVENT_CONNECTED:
                    System.out.println("[RRM-MONITOR] Connected");
                    break;

                case ZMQ.EVENT_CONNECT_RETRIED:
                    System.out.println("[RRM-MONITOR] Retrying connection");
                    break;

                case ZMQ.EVENT_DISCONNECTED:
                    System.out.println("[RRM-MONITOR] Disconnected");

                    if (running) {
                        disconnect();
                    }
                    return;

                case ZMQ.EVENT_CLOSED:
                    System.out.println("[RRM-MONITOR] Socket closed");
                    return;
            }
            } catch (Exception e) {
                e.printStackTrace();
                break;
            }
        }
    }

    /**
     * Metodo usato dai controller o altri componenti per inviare un messaggio.
     */
    public void sendMessage(Map<String, Object> message) {
        sendQueue.offer(message);
    }

    /**
     * Overload che accetta direttamente un oggetto Message.
     */
    public void sendMessage(Message msg) {
        if (msg == null) return;
        sendMessage(msg.toMap());
    }

    /**
     * Processa un oggetto Message già convertito.
     */
    private void processMessage(Message msg) {
        MessageType type = msg.getType();
        switch (type) {
            case GLOBAL_REGISTER_RESPONSE -> {
                Messages.GlobalRegisterResponse resp = (Messages.GlobalRegisterResponse) msg;
                System.out.println("Registered with RRM Global: " + resp.status);
                if (resp.current_policy != null) {
                    currentPolicy = resp.current_policy;
                }
                // dopo registrazione chiedi le policy e le applicazioni disponibili
                sendMessage(new Messages.GUIListPolicies());
                sendMessage(new Messages.GUIListApplications());
                sendMessage(new Messages.GUIListAvailableApplications());
            }
            case GLOBAL_LIST_POLICIES_RESPONSE -> {
                Messages.GlobalListPoliciesResponse resp = (Messages.GlobalListPoliciesResponse) msg;
                availablePolicies = resp.policy_list;
                policiesReceived.set(true);
                checkInitialDataReady();
            }
            case GLOBAL_LIST_APPLICATIONS_RESPONSE -> {
                Messages.GlobalListApplicationsResponse resp = (Messages.GlobalListApplicationsResponse) msg;
                availableApplications = resp.applications;
                System.out.println("Received applications from RRM Global: " + availableApplications);
                applicationsReceived.set(true);
                // running app list not required for initial future
            }
            case GLOBAL_LIST_AVAILABLE_APPLICATIONS_RESPONSE -> {
                Messages.GlobalListAvailableApplicationsResponse resp = (Messages.GlobalListAvailableApplicationsResponse) msg;
                availableDescriptors = resp.descriptors;
                // Salva i descrittori nel database per persistenza
                if (applicazioneDescrittoreService != null) {
                    applicazioneDescrittoreService.salvaDescrittori(resp.descriptors);
                }
                descriptorsReceived.set(true);
                checkInitialDataReady();
            }
            case GLOBAL_LIST_RESOURCES_STATUS_RESPONSE -> {
                Messages.GlobalListResourcesStatusResponse resp = (Messages.GlobalListResourcesStatusResponse) msg;
                onResourcesStatusResponse(resp.resources, resp.count);
            }
            case GLOBAL_LIST_NODES_STATUS_RESPONSE -> {
                Messages.GlobalListNodesStatusResponse resp = (Messages.GlobalListNodesStatusResponse) msg;
                onNodesStatusResponse(resp.nodes, resp.count);
            }
            case GLOBAL_GUI_NOTIFICATION -> {
                Messages.GlobalGuiNotification resp = (Messages.GlobalGuiNotification) msg;
                if (isRuntimeStatusUpdateNotification(resp.message)) {
                    refreshRuntimeStatusFromRrm();
                    break;
                }
                publishApplicationSelfStoppedEvent(resp);
                Messages.GlobalGuiNotification mapped = guiNotificationMapper.toWebNotification(resp);
                publishGuiNotification(mapped);
                System.out.println("[RRM-CONNECTION] GUI notification received: severity=" + mapped.severity + ", message=" + mapped.message);
            }
            case GLOBAL_START_APPLICATION_RESPONSE -> {
                Messages.GlobalStartApplicationResponse resp = (Messages.GlobalStartApplicationResponse) msg;
                System.out.println("Start application response for " + resp.appID + ": " + resp.status);
                //Todo:resp.appID è un arrayList con due elementi, per poterlo usare dobbiamo convertirlo in stringa "(appID,counter)"
                CompletableFuture<Messages.GlobalStartApplicationResponse> f = pendingStartFutures.remove(normalizeResponseAppId(resp.appID));
                
                
                if (f != null) {
                    f.complete(resp);
                }
            }
            case GLOBAL_STOP_APPLICATION_RESPONSE -> {
                Messages.GlobalStopApplicationResponse resp = (Messages.GlobalStopApplicationResponse) msg;
                System.out.println("DEBUG:Stop application response for " + resp.appID + ": " + pendingStopFutures);
                CompletableFuture<Messages.GlobalStopApplicationResponse> f = pendingStopFutures.remove(resp.appID);
                if (f != null) {
                    System.out.println("Stopping " + resp.appID + ": " + f);
                    f.complete(resp);
                }
            }
            case GLOBAL_SET_POLICY_RESPONSE -> {
                Messages.GlobalSetPolicyResponse resp = (Messages.GlobalSetPolicyResponse) msg;
                System.out.println("Set policy response: " + resp.status);
                if ("OK".equals(resp.status)) {
                    // optionally request fresh policy list
                    sendMessage(new Messages.GUIListPolicies());
                }
            }
            case GLOBAL_SHUTDOWN -> {
                System.out.println("Received GlobalShutdown message from RRM Global. Disconnecting...");
                disconnect();
            }
            default -> System.out.println("Received unknown message type: " + type);
        }
    }

    public void disconnect() {
        running = false;
        if (socket != null) {
            socket.close();
            socket = null;
        }
        if (context != null) {
            context.close();
            context = null;
        }
        if (executor != null) {
            executor.shutdownNow();
            executor = null;
        }
        resourcesStatus = null;
        resourcesCount = null;
        nodesStatus = null;
        nodesCount = null;
        resourcesStatusRequestInFlight.set(false);
        resourcesStatusReloadRequested.set(false);
        nodesStatusRequestInFlight.set(false);
        nodesStatusReloadRequested.set(false);
        // if we're tearing down before the initial data arrives, cancel the future
        if (initialDataFuture != null && !initialDataFuture.isDone()) {
            initialDataFuture.completeExceptionally(new IllegalStateException("Disconnected before initial data"));
        }
    }

    public boolean isConnectionAlive() {
        return socket != null && running;
    }

    private boolean isRuntimeStatusUpdateNotification(String message) {
        return "UPDATE".equals(message == null ? "" : message.trim());
    }

    /**
     * Returns a future that completes when the first policy/application lists
     * have been received from RRM Global. Useful for the controller to delay
     * reporting "connected" until the service has some data to show.
     *
     * The future is recreated on each call to initializeConnection; if the
     * connection is disconnected before the lists arrive it will complete
     * exceptionally.
     */
    public CompletableFuture<Void> getInitialDataFuture() {
        return initialDataFuture;
    }

    public boolean waitForInitialData(long timeout, TimeUnit unit) {
        CompletableFuture<Void> future = initialDataFuture;
        if (future == null) {
            return false;
        }
        try {
            future.get(timeout, unit);
            return true;
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            return false;
        } catch (java.util.concurrent.TimeoutException | java.util.concurrent.ExecutionException e) {
            return false;
        }
    }

    /**
     * Invia una richiesta di avvio applicazione a RRM Global e restituisce un
     * future che verrà completato quando si riceverà la risposta.
     *
     * @param appId identificatore dell'applicazione
     * @param args  argomenti addizionali da inviare (può essere null)
     * @return future che fornisce la risposta ricevuta dal server
     */
    public CompletableFuture<Messages.GlobalStartApplicationResponse> startApplication(String appId, java.util.Map<String,Object> args) {
        if (appId == null || appId.isBlank()) {
            CompletableFuture<Messages.GlobalStartApplicationResponse> failed = new CompletableFuture<>();
            failed.completeExceptionally(new IllegalArgumentException("appId mancante"));
            return failed;
        }
        Messages.GUIStartApplication request = new Messages.GUIStartApplication(appId, args == null ? Map.of() : args);
        CompletableFuture<Messages.GlobalStartApplicationResponse> future = new CompletableFuture<>();
        pendingStartFutures.put(appId, future);
        sendMessage(request);
        return future;
    }

    /**
     * Invia una richiesta di stop applicazione a RRM Global e restituisce un
     * future che verrà completato quando si riceverà la risposta.
     *
     * @param appId identificatore dell'applicazione
     * @return future che fornisce la risposta ricevuta dal server
     */
    public CompletableFuture<Messages.GlobalStopApplicationResponse> stopApplication(String appId) {
        if (appId == null || appId.isBlank()) {
            CompletableFuture<Messages.GlobalStopApplicationResponse> failed = new CompletableFuture<>();
            failed.completeExceptionally(new IllegalArgumentException("appId mancante"));
            return failed;
        }
        Messages.GUIStopApplication request = new Messages.GUIStopApplication(appId);
        CompletableFuture<Messages.GlobalStopApplicationResponse> future = new CompletableFuture<>();
        pendingStopFutures.put(appId, future);
        sendMessage(request);
        return future;
    }

    // package-private helper used by unit tests to simulate arrival of a response
    void completeStartResponseForTest(String appId, Messages.GlobalStartApplicationResponse resp) {
        CompletableFuture<Messages.GlobalStartApplicationResponse> f = pendingStartFutures.remove(appId);
        if (f != null) {
            f.complete(resp);
        }
    }

    void completeStopResponseForTest(String appId, Messages.GlobalStopApplicationResponse resp) {
        CompletableFuture<Messages.GlobalStopApplicationResponse> f = pendingStopFutures.remove(appId);
        if (f != null) {
            f.complete(resp);
        }
    }

    private String normalizeResponseAppId(String appId) {
        if (appId == null) {
            return null;
        }
        int len = appId.length();
        if (len < 4 || appId.charAt(0) != '(' || appId.charAt(len - 1) != ')') {
            return appId;
        }
        int i = 1;
        while (i < len - 1 && Character.isWhitespace(appId.charAt(i))) {
            i++;
        }
        if (i >= len - 1) {
            return appId;
        }
        char quote = appId.charAt(i);
        if (quote != '\'' && quote != '"') {
            return appId;
        }
        int start = ++i;
        while (i < len - 1) {
            char c = appId.charAt(i);
            if (c == '\\') {
                i += 2;
                continue;
            }
            if (c == quote) {
                return appId.substring(start, i);
            }
            i++;
        }
        return appId;
    }

    private void publishApplicationSelfStoppedEvent(Messages.GlobalGuiNotification notification) {
        if (notification == null || applicationEventPublisher == null) {
            return;
        }
        if (notification.category == null
                || !"app_self_stopped".equalsIgnoreCase(notification.category.trim())) {
            return;
        }

        applicationEventPublisher.publishEvent(new RrmApplicationSelfStoppedEvent(
                normalizeResponseAppId(notification.appID),
                notification.nodeID,
                notification.message));
    }

    private void checkInitialDataReady() {
        // we wait for policy list and descriptor list before completing the future
        if (policiesReceived.get() && descriptorsReceived.get() &&
            initialDataFuture != null && !initialDataFuture.isDone()) {
            initialDataFuture.complete(null);
            System.out.println("[RRM-CONNECTION] RRM connected and initial data ready.");
        }
    }

    @PreDestroy
    public void cleanup() {
        disconnect();
    }
}

// utilità semplice per serializzare/deserializzare JSON usando Jackson
class JsonUtils {
    private static final com.fasterxml.jackson.databind.ObjectMapper mapper = new com.fasterxml.jackson.databind.ObjectMapper();
    static String toJson(Object obj) {
        try { return mapper.writeValueAsString(obj); } catch (Exception e) { throw new RuntimeException(e); }
    }
    @SuppressWarnings("unchecked")
    static Map<String,Object> fromJson(String json) {
        try {
            return mapper.readValue(json, new com.fasterxml.jackson.core.type.TypeReference<Map<String,Object>>(){});
        } catch(Exception e) {
            throw new RuntimeException(e);
        }
    }
}
