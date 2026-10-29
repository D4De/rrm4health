package it.polimi.bsnwebapp.DTO.request;

import java.util.List;
import java.util.Map;

import com.fasterxml.jackson.annotation.JsonFormat;

import lombok.Data;

/**
 * Richiesta per avviare una applicazione rapida RRM senza creare una campagna.
 */
@Data
public class QuickApplicationStartRequest {
    private String appId;

    @JsonFormat(with = JsonFormat.Feature.ACCEPT_SINGLE_VALUE_AS_ARRAY)
    private List<Long> idSensori;

    private Map<Long, String> sensorLocations;

    private Map<String, String> userAppParams;
}
