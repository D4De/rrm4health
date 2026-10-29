package it.polimi.bsnwebapp.exception;

/**
 * Eccezione applicativa per segnalare richiesta non valida (HTTP 400).
 * Viene sollevata quando il flusso non puo proseguire e il controller deve rispondere con errore.
 * Estende RuntimeException per propagazione senza gestione obbligatoria.
 */

public class BadRequestException extends RuntimeException{

    public BadRequestException(String message) {
        super(message);
    }
}