package it.polimi.bsnwebapp.Service;

import com.fasterxml.jackson.databind.ObjectMapper;
import it.polimi.bsnwebapp.DTO.response.CampaignOutputDataResponse;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class InfluxQueryServiceTest {

    @Test
    void parsesAllMeasurementsMatchingTheCampaignOutputQuery() throws Exception {
        InfluxQueryService service = new InfluxQueryService(
                new ObjectMapper(),
                null
        );
        String response = """
                {
                  "results": [{
                    "series": [
                      {
                        "name": "campaign_42_random_a",
                        "columns": ["time", "_field_order", "index"],
                        "values": [["2026-07-06T10:00:00Z", "index", 1]]
                      },
                      {
                        "name": "campaign_42_random_b",
                        "columns": ["time", "score"],
                        "values": [["2026-07-06T10:01:00Z", 2.5]]
                      }
                    ]
                  }]
                }
                """;

        CampaignOutputDataResponse result = service.parseOutputResponse(42L, response);

        assertEquals(42L, result.campaignId());
        assertEquals(2, result.series().size());
        assertEquals("campaign_42_random_a", result.series().get(0).measurement());
        assertEquals(1L, result.series().get(0).values().get(0).get(2));
        assertEquals(2.5, result.series().get(1).values().get(0).get(1));
    }
}
