package it.polimi.bsnwebapp.Service;

import it.polimi.bsnwebapp.DTO.response.ImuSseEvent;
import org.junit.jupiter.api.Test;

import java.time.Instant;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNull;

class InfluxWriteServiceTest {

    private final InfluxWriteService service = new InfluxWriteService(null);

    @Test
    void usesBaseMeasurementForImu() {
        ImuSseEvent event = new ImuSseEvent(
                "imu", "IMU1", "295", 295L,
                Map.of("ax", 1.0), "aaac/campaign/imu", Instant.now()
        );

        assertEquals("campaign_295", service.resolveMeasurement(event, 295L));
    }

    @Test
    void usesCampaignAndCnameForApplicationOutput() {
        ImuSseEvent event = new ImuSseEvent(
                "application-data", null, "295ba", 295L,
                Map.of("index", 1L), "aaac/campaign/breathanalysis", Instant.now()
        );

        assertEquals("campaign_295_295ba", service.resolveMeasurement(event, 295L));
    }

    @Test
    void sanitizesOutputMeasurementName() {
        ImuSseEvent event = new ImuSseEvent(
                "application-data", null, "295 breath/analysis", 295L,
                Map.of("index", 1L), "aaac/campaign/breathanalysis", Instant.now()
        );

        assertEquals("campaign_295_295_breath_analysis", service.resolveMeasurement(event, 295L));
    }

    @Test
    void rejectsApplicationOutputWithoutCname() {
        ImuSseEvent event = new ImuSseEvent(
                "application-data", null, null, 295L,
                Map.of("index", 1L), "aaac/campaign/output", Instant.now()
        );

        assertNull(service.resolveMeasurement(event, 295L));
    }
}
