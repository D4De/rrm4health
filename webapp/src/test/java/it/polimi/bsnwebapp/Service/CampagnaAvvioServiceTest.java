package it.polimi.bsnwebapp.Service;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.LocalDateTime;
import java.util.Map;
import java.util.Optional;

import org.junit.jupiter.api.Test;
import org.springframework.test.util.ReflectionTestUtils;

import it.polimi.bsnwebapp.Controller.sse.SensoriSseController;
import it.polimi.bsnwebapp.Model.Entities.Campagna;
import it.polimi.bsnwebapp.Model.Enum.StatoCampagna;
import it.polimi.bsnwebapp.Repository.CampagnaRepository;

class CampagnaAvvioServiceTest {

    @Test
    @SuppressWarnings("unchecked")
    void selfStoppedApplicationTerminatesAssociatedCampaign() {
        CampagnaRepository campagnaRepository = mock(CampagnaRepository.class);
        CampagnaProcessManager processManager = mock(CampagnaProcessManager.class);
        SensoriSseController sensoriSseController = mock(SensoriSseController.class);
        CampagnaAvvioService service = new CampagnaAvvioService();

        ReflectionTestUtils.setField(service, "campagnaRepository", campagnaRepository);
        ReflectionTestUtils.setField(service, "processManager", processManager);
        ReflectionTestUtils.setField(service, "sensoriSseController", sensoriSseController);

        Map<Long, String> campagnaAppMap = (Map<Long, String>) ReflectionTestUtils
                .getField(service, "campagnaAppMap");
        campagnaAppMap.put(42L, "('Collector_BLE', 0)");

        Campagna campagna = new Campagna();
        campagna.setId(42L);
        campagna.setNome("Test");
        campagna.setDataInizio(LocalDateTime.now().minusMinutes(5));
        campagna.setStato(StatoCampagna.IN_CORSO);

        when(campagnaRepository.findById(42L)).thenReturn(Optional.of(campagna));
        when(campagnaRepository.save(any(Campagna.class))).thenAnswer(invocation -> invocation.getArgument(0));

        service.terminaCampagnaPerChiusuraAutonoma(new RrmApplicationSelfStoppedEvent(
                "Collector_BLE",
                "('10.79.3.195', 47575)",
                "Application Collector_BLE stopped autonomously on node ('10.79.3.195', 47575)"));

        assertEquals(StatoCampagna.TERMINATA, campagna.getStato());
        assertNotNull(campagna.getDataFine());
        assertTrue(campagna.getNote().contains("applicazione Collector_BLE chiusa autonomamente"));
        assertTrue(campagnaAppMap.isEmpty());
        verify(campagnaRepository).save(campagna);
        verify(processManager).pulisciMemoriaCampagna(42L);
        verify(sensoriSseController).notifyAllClients();
    }
}
