package it.polimi.bsnwebapp.exception;

/**
 * Eccezione applicativa per segnalare conflitto di stato o risorsa duplicata (HTTP 409).
 * Viene sollevata quando il flusso non puo proseguire e il controller deve rispondere con errore.
 * Estende RuntimeException per propagazione senza gestione obbligatoria.
 */

public class ConflictException extends RuntimeException{

    public ConflictException(String message) {
        super(message);
    }
}