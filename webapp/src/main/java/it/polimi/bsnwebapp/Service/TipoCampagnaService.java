package it.polimi.bsnwebapp.Service;

import it.polimi.bsnwebapp.DTO.response.TipoCampagnaResponse;
import it.polimi.bsnwebapp.Model.Entities.TipoCampagna;
import it.polimi.bsnwebapp.Repository.TipoCampagnaRepository;
import lombok.RequiredArgsConstructor;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.stream.Collectors;

/**
 * Service per la gestione dei tipi campagna.
 * Recupera elenco e dettaglio dei tipi disponibili e li converte in TipoCampagnaResponse.
 * Usato dai controller per popolare le viste e le API.
 */

@Service
@RequiredArgsConstructor
public class TipoCampagnaService {

    private static final Logger logger = LoggerFactory.getLogger(TipoCampagnaService.class);

    private final TipoCampagnaRepository tipoCampagnaRepository;

    /**
     * Recupera tutti i tipi di campagna disponibili.
     *
     * @return Lista di TipoCampagnaResponse
     */
    @Transactional(readOnly = true)
    public List<TipoCampagnaResponse> getAllTipiCampagna() {
        logger.info("Recupero di tutti i tipi di campagna");
        List<TipoCampagna> tipi = tipoCampagnaRepository.findAll();
        return tipi.stream()
                .map(this::convertToResponse)
                .collect(Collectors.toList());
    }

    /**
     * Recupera i dettagli di un tipo di campagna specifico.
     *
     * @param id ID del tipo di campagna
     * @return TipoCampagnaResponse
     */
    @Transactional(readOnly = true)
    public TipoCampagnaResponse getTipoCampagnaById(Long id) {
        logger.info("Recupero dettagli tipo campagna ID: {}", id);
        TipoCampagna tipo = tipoCampagnaRepository.findById(id)
                .orElseThrow(() -> new IllegalArgumentException("Tipo campagna non trovato con ID: " + id));
        return convertToResponse(tipo);
    }

    /**
     * Converte un'entità TipoCampagna in TipoCampagnaResponse DTO.
     */
    private TipoCampagnaResponse convertToResponse(TipoCampagna tipo) {
        return new TipoCampagnaResponse(
                tipo.getId(),
                tipo.getCodice(),
                tipo.getDescrizione(),
                tipo.getScriptFileName()
        );
    }
}

