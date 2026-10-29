package it.polimi.bsnwebapp.exception;

/**
 * Eccezione applicativa per segnalare errore interno inatteso (HTTP 500).
 * Viene sollevata quando il flusso non puo proseguire e il controller deve rispondere con errore.
 * Estende RuntimeException per propagazione senza gestione obbligatoria.
 */

public class InternalServerErrorException extends RuntimeException{

    public InternalServerErrorException(String message) {
        super(message);
    }
}