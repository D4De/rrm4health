package it.polimi.bsnwebapp.Service;

import it.polimi.bsnwebapp.DTO.response.ImuSseEvent;
import org.junit.jupiter.api.Test;

import java.time.Instant;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertInstanceOf;
import static org.junit.jupiter.api.Assertions.assertNull;

class MqttSseServiceTest {

    private final MqttSseService service = new MqttSseService(null, null);

    @Test
    void parsesApplicationOutputAndPreservesFieldNames() {
        ImuSseEvent event = service.parsePayload(
                "index=4,fB_median_Tot=18.25,Ti_median_Tot=1.2,ts=1782900000.25,c_id=12,cname=12ba",
                "aaac/campaign/breathanalysis"
        );

        assertEquals("application-data", event.type());
        assertEquals(12L, event.campaignId());
        assertEquals("12ba", event.cname());
        assertEquals("aaac/campaign/breathanalysis", event.topic());
        assertEquals(Instant.ofEpochSecond(1782900000L, 250_000_000L), event.receivedAt());
        assertEquals(4L, event.values().get("index"));
        assertEquals(18.25, event.values().get("fB_median_Tot"));
        assertInstanceOf(Double.class, event.values().get("Ti_median_Tot"));
    }

    @Test
    void keepsImuEventsCompatibleAndAssociatesCampaign() {
        ImuSseEvent event = service.parsePayload(
                "ax=1.5,ay=2,az=-3,imuid=abc,ts=1751371200123,c_id=7,cname=7",
                "aaac/campaign/imu"
        );

        assertEquals("imu", event.type());
        assertEquals(7L, event.campaignId());
        assertEquals("ABC", event.imuid());
        assertEquals(1.5, event.values().get("ax"));
        assertEquals(2L, event.values().get("ay"));
    }

    @Test
    void keepsNumericCnameAsLegacyFallback() {
        ImuSseEvent event = service.parsePayload(
                "ax=1,imuid=abc,cname=12",
                "aaac/campaign/imu"
        );

        assertEquals(12L, event.campaignId());
    }

    @Test
    void rejectsNonNumericCnameWithoutCampaignId() {
        ImuSseEvent event = service.parsePayload(
                "index=1,fB_median_Tot=18.25,cname=12ba",
                "aaac/campaign/breathanalysis"
        );

        assertNull(event.campaignId());
    }
}
