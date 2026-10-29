package it.polimi.bsnwebapp.DTO.response;

import it.polimi.bsnwebapp.Model.Enum.Protocollo;
import it.polimi.bsnwebapp.Model.Enum.StatoCampagna;
import it.polimi.bsnwebapp.Model.Enum.TipoMisura;
import lombok.AllArgsConstructor;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;
import java.util.List;
import java.util.Set;

/**
 * DTO di risposta che aggrega tutti i dati di una campagna.
 * Include informazioni su campagna, persona, utente creatore, configurazione esecuzione e associazioni.
 * Contiene anche liste di TipiCampagnaInfo e SensoreInfo per la UI.
 */

@Data
@NoArgsConstructor
@AllArgsConstructor
public class CampagnaResponse {
    private Long id;
    private String nome;
    private String note;
    private StatoCampagna stato;
    private LocalDateTime dataInizio;
    private LocalDateTime dataFine;
    private String durataTotale;
    private Integer frequenza;
    private Integer durata;
    private Protocollo connettivita;
    private String scriptFileName;
    private String dbHost;
    private String dbName;

    // Informazioni sulla persona
    private Long idPersona;
    private String nomePersona;
    private String cognomePersona;
    private String notePersona;

    // Informazioni sull'utente creatore
    private Long idUtenteCreatore;
    private String usernameCreatore;

    // Tipi di campagna associati e sensori associati
    private List<TipoCampagnaInfo> tipiCampagna;
    private List<SensoreInfo> sensori;

    /**
     * DTO interno per i dettagli del tipo campagna associato.
     * Riporta id, codice, descrizione e informazioni sullo script selezionabile dalla UI.
     * Viene popolato in CampagnaService durante la conversione della campagna.
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class TipoCampagnaInfo {
        private Long id;
        private String codice;
        private String descrizione;
        private String nomeApplicazione;
        private String eseguibile;
    }

    /**
     * DTO interno per le informazioni di un sensore associato alla campagna.
     * Include attributi anagrafici, protocolli e misure supportate, oltre al flag attivo.
     * Deriva da CampagnaSensore e Sensore per comporre la vista di monitoraggio.
     */
    @Data
    @NoArgsConstructor
    @AllArgsConstructor
    public static class SensoreInfo {
        private Long id;
        private String nome;
        private String tipo;  //es: XIAO, ...
        private String codice;  //MAC ADDRESS
        private Protocollo protocollo;
        private Set<TipoMisura> misureSupportate;
        private boolean attivo;  //non presente nel DB, serve per mostrare la spunta selezionato.
        private String location;
    }
}
