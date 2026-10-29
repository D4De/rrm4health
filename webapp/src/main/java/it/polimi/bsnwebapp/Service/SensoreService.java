
package it.polimi.bsnwebapp.Service;

import java.util.EnumSet;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import it.polimi.bsnwebapp.DTO.request.SensoreCreateRequest;
import it.polimi.bsnwebapp.DTO.response.SensoreResponse;
import it.polimi.bsnwebapp.Model.Entities.Sensore;
import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import it.polimi.bsnwebapp.Model.Enum.TipoMisura;
import it.polimi.bsnwebapp.Repository.CampagnaSensoreRepository;
import it.polimi.bsnwebapp.Repository.SensoreRepository;
import it.polimi.bsnwebapp.exception.BadRequestException;
import it.polimi.bsnwebapp.exception.ConflictException;
import lombok.RequiredArgsConstructor;

/**
 * Service per la gestione dei sensori.
 * Normalizza il codice (maiuscolo), verifica unicita, imposta protocolli supportati e salva su DB.
 * Espone anche la lista sensori e la conversione in SensoreResponse.
 */

@Service
@RequiredArgsConstructor
public class SensoreService {

    /**
     * Restituisce solo i sensori disponibili (non in uso in campagne attive).
     */
    @Transactional(readOnly = true)
    public List<SensoreResponse> listaSensoriDisponibili() {
        List<Long> inUso = campagnaSensoreRepository.findIdSensoriInUso();
        return sensoreRepository.findAllByEliminatoFalse().stream()
                .map(s -> toResponse(s, inUso.contains(s.getId())))
                .toList();
    }

    private final SensoreRepository sensoreRepository;
    private final CampagnaSensoreRepository campagnaSensoreRepository;

    private static final int MAX_CODICE_LEN = 50;
    private static final int MAX_NOME_LEN = 100;
    private static final int MAX_TIPO_LEN = 50;

    /**
    * Crea un nuovo sensore applicando le regole di normalizzazione.
    * Il codice viene forzato in maiuscolo.
     * Verifica duplicati e completa i protocolli supportati con quello di default.
     *
     * @param request dati del sensore da creare
     * @return sensore creato in formato DTO
     */
    @Transactional
    public SensoreResponse creaSensore(SensoreCreateRequest request) {
        String codice = normalizeCodice(request.getCodice());
        String nome = normalizeNome(request.getNome());
        String tipo = normalizeTipo(request.getTipo());

        Sensore existing = sensoreRepository.findByCodice(codice).orElse(null);
        if (existing != null && !existing.isEliminato()) {
            throw new ConflictException("Codice sensore già presente");
        }

        Protocollo def = request.getProtocolloDefault();
        if (def == null) throw new BadRequestException("Protocollo di default mancante");

        Set<Protocollo> supportati = (request.getProtocolliSupportati() == null)
                ? new HashSet<>()
                : new HashSet<>(request.getProtocolliSupportati());

        if (supportati.isEmpty()) supportati.add(def);
        if (!supportati.contains(def)) supportati.add(def);

        Sensore s = (existing != null) ? existing : new Sensore();
        s.setCodice(codice);
        s.setNome(nome);
        s.setTipo(tipo);
        s.setProtocollo(def);
        s.setProtocolliSupportati(supportati);
        s.setEliminato(false);
        Set<TipoMisura> misureRaw = request.getMisureSupportate();
        Set<TipoMisura> misure;
        if (misureRaw == null) {
            misure = EnumSet.allOf(TipoMisura.class);
        } else if (misureRaw.isEmpty()) {
            throw new BadRequestException("Selezionare almeno una misura supportata");
        } else {
            misure = EnumSet.copyOf(misureRaw);
        }
        s.setMisureSupportate(misure);

        Sensore saved = sensoreRepository.save(s);
        return toResponse(saved);
    }

    /**
     * Restituisce l'elenco dei sensori registrati.
     *
     * @return lista di sensori in formato DTO
     */
    @Transactional(readOnly = true)
    public List<SensoreResponse> listaSensori() {
        return sensoreRepository.findAllByEliminatoFalse().stream().map(this::toResponse).toList();
    }

    /**
     * Elimina (archivia) un sensore.
     *
     * Se il sensore e' gia stato usato in campagne, non viene rimosso fisicamente
     * dal DB per preservare lo storico: viene invece marcato come {@code eliminato}
     * e non comparira' piu' tra i sensori selezionabili.
     *
     * @param id ID del sensore
     */
    @Transactional
    public void eliminaSensore(Long id) {
        if (id == null) {
            throw new BadRequestException("ID sensore mancante");
        }
        Sensore sensore = sensoreRepository.findById(id)
                .orElseThrow(() -> new BadRequestException("Sensore non trovato"));

        if (campagnaSensoreRepository.existsBySensore_Id(id)) {
            sensore.setEliminato(true);
            sensoreRepository.save(sensore);
            return;
        }

        sensoreRepository.delete(sensore);
    }

    /**
    * Normalizza il codice sensore.
    * Richiede una stringa non vuota e la converte in maiuscolo.
     *
     * @param codice codice inserito dall'utente
     * @return codice normalizzato
     */
    private String normalizeCodice(String codice) {
        if (codice == null) throw new BadRequestException("Codice mancante");
        String c = codice.trim().toUpperCase();
        if (c.isEmpty()) throw new BadRequestException("Codice mancante");
        if (c.length() > MAX_CODICE_LEN) {
            throw new BadRequestException("Il codice non puo superare " + MAX_CODICE_LEN + " caratteri");
        }
        return c;
    }

    private String normalizeNome(String nome) {
        if (nome == null) throw new BadRequestException("Nome mancante");
        String value = nome.trim();
        if (value.isEmpty()) throw new BadRequestException("Nome mancante");
        if (value.length() > MAX_NOME_LEN) {
            throw new BadRequestException("Il nome non puo superare " + MAX_NOME_LEN + " caratteri");
        }
        return value;
    }

    private String normalizeTipo(String tipo) {
        if (tipo == null) throw new BadRequestException("Tipo mancante");
        String value = tipo.trim();
        if (value.isEmpty()) throw new BadRequestException("Tipo mancante");
        if (value.length() > MAX_TIPO_LEN) {
            throw new BadRequestException("Il tipo non puo superare " + MAX_TIPO_LEN + " caratteri");
        }
        return value;
    }

    /**
     * Converte l'entita Sensore in DTO.
     *
     * @param s entita sensore persistita
     * @return DTO con i dati principali del sensore
     */
    private SensoreResponse toResponse(Sensore s) {
        return toResponse(s, false);
    }

    private SensoreResponse toResponse(Sensore s, boolean occupato) {
        return new SensoreResponse(
                s.getId(),
                s.getCodice(),
                s.getNome(),
                s.getTipo(),
                s.getProtocollo(),
                s.getProtocolliSupportati(),
                s.getMisureSupportate(),
                occupato
        );
    }
}
