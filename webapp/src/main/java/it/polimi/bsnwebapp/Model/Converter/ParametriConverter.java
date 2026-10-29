package it.polimi.bsnwebapp.Model.Converter;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import jakarta.persistence.AttributeConverter;
import jakarta.persistence.Converter;
import java.util.Map;

/**
 * Converter JPA per serializzare/deserializzare Map<String, Object> in JSON (VARCHAR/TEXT nel DB).
 * Utilizzato dall'Entity ApplicazioneDescrittore per persistere i parametri variabili.
 */
@Converter
public class ParametriConverter implements AttributeConverter<Map<String, Object>, String> {

    private static final ObjectMapper mapper = new ObjectMapper();

    /**
     * Converte una Map in stringa JSON per il salvataggio nel database.
     */
    @Override
    public String convertToDatabaseColumn(Map<String, Object> attribute) {
        if (attribute == null) return null;
        try {
            return mapper.writeValueAsString(attribute);
        } catch (Exception e) {
            throw new RuntimeException("Errore nella serializzazione dei parametri a JSON", e);
        }
    }

    /**
     * Converte una stringa JSON da database in Map per l'uso in applicazione.
     */
    @Override
    public Map<String, Object> convertToEntityAttribute(String dbData) {
        if (dbData == null) return null;
        try {
            return mapper.readValue(dbData, new TypeReference<Map<String, Object>>() {});
        } catch (Exception e) {
            throw new RuntimeException("Errore nella deserializzazione dei parametri da JSON", e);
        }
    }
}
