package it.polimi.bsnwebapp.Service;

public record RrmApplicationSelfStoppedEvent(String appId, String nodeId, String message) {
}
