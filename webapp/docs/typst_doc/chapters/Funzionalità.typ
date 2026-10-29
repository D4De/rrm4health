= 5. Funzionalità
#v(0.5em)

#let accent = rgb("#049045")
#let title_color = rgb("#0075af")
#set list(indent: 1.5em)
#set enum(indent: 1.5em)

Le funzionalità della piattaforma sono suddivise in base al ruolo assegnato all'utente:
- #text(fill: accent, weight: "bold")[MED]: *Profilo Medico*, focalizzato sulla gestione clinica, dei pazienti e dell'acquisizione dati.
- #text(fill: accent, weight: "bold")[DEV]: *Profilo Tecnico*, con accesso completo alle configurazioni di sistema, sensori e script.

== 5.1 Autenticazione e Accesso

Il sistema garantisce un accesso sicuro e profilato.

- *Registrazione Utente*: Creazione di un nuovo account selezionando il ruolo appropriato (#text(fill: accent)[MED] o #text(fill: accent)[DEV]).
- *Login/Logout*: Accesso tramite credenziali e terminazione sicura della sessione.

---

== 5.2 Gestione Campagne

Questa sezione rappresenta il *core* dell'applicazione, permettendo di configurare, avviare e monitorare le sessioni di acquisizione dati.

#text(fill:title_color, weight: "bold")[Creazione Nuova Campagna]
\ Il wizard di creazione guida l'utente attraverso i seguenti passaggi:
+ *Selezione Persona*: Scelta del soggetto dall'anagrafica o creazione rapida di una *nuova persona*.
+ *Tipo di Campagna*: Selezione dello script di acquisizione (protocollo medico o test).
+ *Sensori*: Associazione dei sensori necessari per la misurazione.
+ *Database Aggiuntivo* (Opzionale): Configurazione di un database Time-Series esterno per la ridondanza dei dati (il salvataggio sul DB principale è sempre garantito).

#text(fill:title_color, weight: "bold")[Ciclo di Vita e Monitoraggio]
\ Gli stati principali di una campagna sono evidenziati nell'interfaccia:
- *Avvio*: Inizio dell'esecuzione dello script Python sottostante.
- *Monitoraggio Live*: Visualizzazione in tempo reale dei dati streaming (grafici e valori).
- *Terminazione*: Chiusura formale della sessione e salvataggio definitivo.

#text(fill:title_color, weight: "bold")[Consultazione]
- *Campagne Attive*: Vista dedicata alle sessioni attualmente in corso.
- *Storico Campagne*: Archivio filtrabile per *stato*, *paziente* o *data*, per analizzare le attività passate.

---

== 5.3 Manutenzione e Configurazione (DEV)

Funzionalità avanzate per la gestione dell'infrastruttura IoT e dati.

#text(fill:title_color, weight: "bold")[Gestione Sensori]
- *Creazione*: Inserimento di nuovi dispositivi nel sistema.
- *Lista*: Elenco completo dei sensori configurati.
- *Eliminazione*: Rimozione sicura (inibita se il sensore è legato a campagne storiche).

#text(fill:title_color, weight: "bold")[Database Time-Series]
- *Configurazione*: Definizione dei parametri di connessione (Host, Porta, Nome DB).
- *Rimozione*: Gestione delle configurazioni.

#text(fill:title_color, weight: "bold")[Script e Tipi Campagna]
\ Consultazione e upload dei tipi di campagna (script Python). Gli script sono fisicamente residenti nella cartella `bsn/script/` e modificabili direttamente se necessario.

---

== 5.4 Link video funzionalità

- Registrazione, login, manutenzione: #link("https://youtu.be/dj0Kbz2UFww")[BSN_WebApp_1]
- Avvio campagna, aggiunta paziente, monitoraggio tempo reale: #link("https://youtu.be/5qhYEGd0big")[BSN_WebApp_2]
- Terminazione campagna, visualizzazione dati storici: #link("https://youtu.be/-6otoIjSrsc")[BSN_WebApp_3]

