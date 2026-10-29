package it.polimi.bsnwebapp.DTO.response;

/**
 * DTO di risposta per una configurazione database selezionabile.
 * Espone nome, host e nome del database per la UI e per le selezioni campagna.
 */
public record DatabaseConfigResponse(
        Long id,
        String nome,
        String host,
        String dbName
) {
}
