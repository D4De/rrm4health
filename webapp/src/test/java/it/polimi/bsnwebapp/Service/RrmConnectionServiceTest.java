package it.polimi.bsnwebapp.Service;

import java.util.Map;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import it.polimi.bsnwebapp.communication.Messages;

class RrmConnectionServiceTest {

    private RrmConnectionService service;

    @BeforeEach
    void setup() {
        service = new RrmConnectionService();
    }

    @Test
    void startApplicationReturnsFutureAndCompletesWhenResponseArrives() throws Exception {
        String appId = "testApp";
        Map<String,Object> args = Map.of("foo", "bar");

        CompletableFuture<Messages.GlobalStartApplicationResponse> future = service.startApplication(appId, args);
        assertNotNull(future, "Future should never be null");
        assertFalse(future.isDone(), "Future should not be completed immediately");

        // simulate response from RRM
        Messages.GlobalStartApplicationResponse resp = new Messages.GlobalStartApplicationResponse(appId, "OK");
        service.completeStartResponseForTest(appId, resp);

        Messages.GlobalStartApplicationResponse result = future.get(1, TimeUnit.SECONDS);
        assertEquals("OK", result.status);
        assertEquals(appId, result.appID);
    }

    @Test
    void startApplicationWithEmptyAppIdCompletesExceptionally() throws Exception {
        CompletableFuture<Messages.GlobalStartApplicationResponse> future = service.startApplication("", null);
        assertTrue(future.isCompletedExceptionally());
        // getting the result should wrap the IAE inside ExecutionException
        ExecutionException execEx = assertThrows(ExecutionException.class,
                () -> future.get(1, TimeUnit.SECONDS));
        assertTrue(execEx.getCause() instanceof IllegalArgumentException);
    }

    @Test
    void stopApplicationReturnsFutureAndCompletesWhenResponseArrives() throws Exception {
        String appId = "testApp";

        CompletableFuture<Messages.GlobalStopApplicationResponse> future = service.stopApplication(appId);
        assertNotNull(future, "Future should never be null");
        assertFalse(future.isDone(), "Future should not be completed immediately");

        // simulate response from RRM
        Messages.GlobalStopApplicationResponse resp = new Messages.GlobalStopApplicationResponse(appId, "OK");
        service.completeStopResponseForTest(appId, resp);

        Messages.GlobalStopApplicationResponse result = future.get(1, TimeUnit.SECONDS);
        assertEquals("OK", result.status);
        assertEquals(appId, result.appID);
    }

    @Test
    void stopApplicationWithEmptyAppIdCompletesExceptionally() throws Exception {
        CompletableFuture<Messages.GlobalStopApplicationResponse> future = service.stopApplication(" ");
        assertTrue(future.isCompletedExceptionally());
        ExecutionException execEx = assertThrows(ExecutionException.class,
                () -> future.get(1, TimeUnit.SECONDS));
        assertTrue(execEx.getCause() instanceof IllegalArgumentException);
    }

    @Test
    void guiNotificationIsDeliveredToEverySubscriber() {
        AtomicInteger firstSubscriberCalls = new AtomicInteger();
        AtomicInteger secondSubscriberCalls = new AtomicInteger();
        service.subscribeGuiNotifications(notification -> firstSubscriberCalls.incrementAndGet());
        service.subscribeGuiNotifications(notification -> secondSubscriberCalls.incrementAndGet());

        service.publishGuiNotification(new Messages.GlobalGuiNotification(
                "Test", "info", "generic", null, null));

        assertEquals(1, firstSubscriberCalls.get());
        assertEquals(1, secondSubscriberCalls.get());
    }

    @Test
    void guiNotificationWaitsForSubscriberWhenPageIsReloading() {
        AtomicInteger subscriberCalls = new AtomicInteger();
        service.publishGuiNotification(new Messages.GlobalGuiNotification(
                "Test", "info", "generic", null, null));

        service.subscribeGuiNotifications(notification -> subscriberCalls.incrementAndGet());

        assertEquals(1, subscriberCalls.get());
    }
}
