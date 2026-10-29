package it.polimi.bsnwebapp.Service;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.nio.charset.StandardCharsets;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.zip.ZipEntry;
import java.util.zip.ZipInputStream;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

class CampaignOutputExportServiceTest {

    private final CampaignOutputExportService service =
            new CampaignOutputExportService(new ObjectMapper(), null);

    @Test
    void createsOneCsvForEachApplicationTopic() throws Exception {
        String influxResponse = """
                {
                  "results": [{
                    "series": [{
                      "name": "campaign_12",
                      "columns": ["time", "_field_order", "cname", "fB_median_Tot", "index", "result", "score", "topic"],
                      "values": [
                        [1782900000000000000, "index,fB_median_Tot", "12", 18.25, 4, null, null, "aaac/campaign/breathanalysis"],
                        ["2026-07-01T10:00:01Z", "score,result", "12", null, null, "regolare", 0.9, "aaac/campaign/posture"],
                        [1782900005000000, "index,fB_median_Tot", "12", 19.0, 5, null, null, "aaac/campaign/breathanalysis"],
                        ["2026-07-01T10:00:03Z", null, "12", null, null, null, null, "aaac/campaign/imu"]
                      ]
                    }]
                  }]
                }
                """;

        CampaignOutputExportService.ExportArchive archive =
                service.buildArchiveFromResponse(12L, influxResponse);
        Map<String, String> files = unzip(archive.content());

        assertEquals("campagna_12_output.zip", archive.fileName());
        assertEquals(2, archive.topicCount());
        assertEquals(2, files.size());
        assertTrue(files.get("breathanalysis.csv")
                .contains("timestamp,index,fB_median_Tot"));
        assertTrue(files.get("breathanalysis.csv")
                .contains("2026-07-01T"));
        assertTrue(files.get("posture.csv")
                .contains("timestamp,score,result"));
        assertTrue(files.get("posture.csv")
                .contains("2026-07-01T10:00:01Z,0.9,regolare"));
    }

    @Test
    void reportsWhenNoApplicationOutputExists() {
        String emptyResponse = """
                {"results":[{}]}
                """;

        assertThrows(
                IllegalStateException.class,
                () -> service.buildArchiveFromResponse(9L, emptyResponse)
        );
    }

    @Test
    void createsCsvForImuDataOnly() throws Exception {
        String influxResponse = """
                {
                  "results": [{
                    "series": [{
                      "name": "campaign_12",
                      "columns": ["time", "ax", "ay", "battery", "event_type", "imuid", "topic", "fB_median_Tot"],
                      "values": [
                        [1782900000000000000, 1.1, 2.2, null, "imu", "IMU1", "aaac/campaign/imu", null],
                        [1782900001000000000, null, null, 87, "battery", "IMU1", null, null],
                        [1782900002000000000, null, null, null, "application-data", null, "aaac/campaign/breathanalysis", 18.5],
                        [1782900003000000000, 3.3, 4.4, null, null, "IMU2", "aaac/campaign/imu", null]
                      ]
                    }]
                  }]
                }
                """;

        CampaignOutputExportService.ExportFile file =
                service.buildImuCsvFromResponse(12L, influxResponse);
        String csv = new String(file.content(), StandardCharsets.UTF_8);

        assertEquals("campagna_12_imu.csv", file.fileName());
        assertTrue(csv.contains("timestamp,imuid,ax,ay"));
        assertTrue(csv.contains("IMU1,1.1,2.2"));
        assertTrue(csv.contains("IMU2,3.3,4.4"));
        assertTrue(!csv.contains("87"));
        assertTrue(!csv.contains("18.5"));
    }

    @Test
    void reportsWhenNoImuDataExists() {
        String emptyResponse = """
                {"results":[{}]}
                """;

        assertThrows(
                IllegalStateException.class,
                () -> service.buildImuCsvFromResponse(9L, emptyResponse)
        );
    }

    private Map<String, String> unzip(byte[] content) throws Exception {
        Map<String, String> files = new LinkedHashMap<>();
        try (ZipInputStream zip = new ZipInputStream(
                new ByteArrayInputStream(content),
                StandardCharsets.UTF_8)) {
            ZipEntry entry;
            while ((entry = zip.getNextEntry()) != null) {
                ByteArrayOutputStream output = new ByteArrayOutputStream();
                zip.transferTo(output);
                files.put(entry.getName(), output.toString(StandardCharsets.UTF_8));
                zip.closeEntry();
            }
        }
        return files;
    }
}
