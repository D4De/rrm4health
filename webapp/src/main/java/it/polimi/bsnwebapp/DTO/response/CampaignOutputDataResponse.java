package it.polimi.bsnwebapp.DTO.response;

import java.util.List;

/**
 * Dati applicativi prodotti da una campagna e salvati nelle measurement
 * {@code campaign_<id>_<cname>}.
 */
public record CampaignOutputDataResponse(
        Long campaignId,
        List<Series> series
) {
    public record Series(
            String measurement,
            List<String> columns,
            List<List<Object>> values
    ) {
    }
}
