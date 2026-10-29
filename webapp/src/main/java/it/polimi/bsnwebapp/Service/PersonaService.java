package it.polimi.bsnwebapp.Service;

import it.polimi.bsnwebapp.DTO.request.PersonaCreateRequest;
import it.polimi.bsnwebapp.DTO.response.PersonaResponse;
import it.polimi.bsnwebapp.Model.Entities.Persona;
import it.polimi.bsnwebapp.Repository.PersonaRepository;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

/**
 * Service per la gestione delle persone (pazienti).
 * Fornisce listing, dettaglio e creazione con validazione dei campi obbligatori.
 * Converte le entita Persona in PersonaResponse per i controller.
 */

@Service
@RequiredArgsConstructor
public class PersonaService {

    private static final Logger logger = LoggerFactory.getLogger(PersonaService.class);

    private final PersonaRepository personaRepository;

    /**
     * Recupera tutte le persone (pazienti) disponibili.
     *
     * @return Lista di PersonaResponse
     */
    @Transactional(readOnly = true)
    public List<PersonaResponse> getAllPersone() {
        List<Persona> persone = personaRepository.findAll();
        return persone.stream()
                .map(this::convertToResponse)
                .collect(Collectors.toList());
    }

    /**
     * Crea una nuova persona (paziente).
     *
     * @param request Dati della persona da creare
     * @return PersonaResponse con i dati della persona creata
     */
    @Transactional
    public PersonaResponse createPersona(PersonaCreateRequest request) {
        logger.info("Creazione nuovo paziente: {} {}", request.getNome(), request.getCognome());

        // Validazione
        if (request.getNome() == null || request.getNome().isBlank()) {
            throw new IllegalArgumentException("Il nome è obbligatorio");
        }
        if (request.getCognome() == null || request.getCognome().isBlank()) {
            throw new IllegalArgumentException("Il cognome è obbligatorio");
        }

        // Creazione entità
        Persona persona = new Persona(
                request.getNome().trim(),
                request.getCognome().trim(),
                request.getDataNascita(),
                request.getNote()
        );

        // Salvataggio
        persona = personaRepository.save(persona);
        logger.info("Paziente creato con ID: {}", persona.getId());

        return convertToResponse(persona);
    }

    /**
     * Recupera i dettagli di una persona specifica.
     *
     * @param id ID della persona
     * @return PersonaResponse
     */
    @Transactional(readOnly = true)
    public PersonaResponse getPersonaById(Long id) {
        logger.info("Recupero dettagli persona ID: {}", id);
        Persona persona = personaRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Persona non trovata con ID: " + id));
        return convertToResponse(persona);
    }

    /**
     * Converte un'entità Persona in PersonaResponse DTO.
     */
    private PersonaResponse convertToResponse(Persona persona) {
        return new PersonaResponse(
                persona.getId(),
                persona.getNome(),
                persona.getCognome(),
                persona.getDataNascita(),
                persona.getNote()
        );
    }
}
