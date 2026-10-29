package it.polimi.bsnwebapp.communication;

import java.util.Map;

/**
 * Interfaccia base per ogni messaggio.
 * Fornisce conversione in mappa per serializzazione e recupero del tipo.
 */
public interface Message {
    MessageType getType();
    Map<String,Object> toMap();
}
