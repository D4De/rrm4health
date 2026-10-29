package it.polimi.bsnwebapp.DTO.response;

import java.util.List;

/**
 * DTO di risposta per una serie InfluxDB.
 * Espone le colonne e i valori della query per consentire la costruzione dei grafici storici.
 * Il campo measurement indica la misura interrogata (per-campagna) e campaignId identifica la campagna.
 */
public record InfluxSeriesResponse(
        Long campaignId,
        String measurement,
        List<String> columns,
        List<List<Object>> values
) {
}
