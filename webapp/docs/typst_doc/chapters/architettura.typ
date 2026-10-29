= 3. Organizzazione del Codice
#v(0.6em)
#set list(indent: 1.5em)

L’organizzazione interna del codice segue il paradigma *Model–View–Controller (MVC)*
e una chiara separazione in strati, al fine di garantire modularità, manutenibilità
e una netta distinzione delle responsabilità.

---

== 3.1 Controller Layer
#v(0.3em)

Il package *Controller* contiene i controller Spring responsabili della gestione
delle richieste HTTP in ingresso.

Nel progetto sono presenti:
- *Controller MVC* (annotati con `@Controller`), che restituiscono viste
  renderizzate tramite *Thymeleaf*;
- *Controller REST* (annotati con `@RestController`), che espongono API JSON
  utilizzate per funzionalità dinamiche basate su *AJAX/HTMX* o per servizi dati.

I nomi dei controller riflettono chiaramente il loro ambito funzionale:
- `HomePageController` gestisce la homepage e le pagine generali;
- `AuthController` si occupa delle operazioni di autenticazione e registrazione;
- controller come `CampagnaMedController` e `PersonaMedController` gestiscono
  le funzionalità dedicate all’utente medico;
- `SensoreDevController` espone operazioni sui sensori per l’utente sviluppatore.

È inoltre presente un `ImuStreamController`, dedicato allo streaming dei dati
dei sensori tramite *Server-Sent Events (SSE)*.  
IMU (*Inertial Measurement Unit*) indica l’insieme di dati trasmessi in tempo reale.

---

== 3.2 Service Layer
#v(0.3em)

Il package *Service* incapsula la logica di business dell’applicazione, coordinando
le operazioni complesse e transazionali e fungendo da livello intermedio tra
controller e persistenza.

Alcuni servizi rilevanti sono:
- `CampagnaService`, che gestisce l’avvio e la terminazione delle campagne di monitoraggio;
- `MqttSseService`, che si connette al broker MQTT e inoltra i dati in ingresso
  sia verso InfluxDB (tramite `InfluxWriteService`) sia verso i client SSE;
- `InfluxQueryService`, che fornisce metodi per interrogare i dati storici
  delle campagne concluse;
- `AuthService`, responsabile della validazione e registrazione degli utenti;
- `PersonaService`, `SensoreService`, `TipoCampagnaService`, che incapsulano
  la logica CRUD delle rispettive entità.
-  `CampagnaWatchdog`: job schedulato che verifica la coerenza tra lo stato campagna a DB e i processi attivi. Se una campagna risulta IN_CORSO ma non ha processi vivi, la termina e aggiorna le note.

---

== 3.3 Persistence Layer (Repository)
#v(0.3em)

Il layer di persistenza è gestito tramite *Spring Data JPA* nel package *Repository*.
Per ciascuna entità principale è presente un’interfaccia repository dedicata
(ad esempio `UtenteRepository`, `PersonaRepository`, `CampagnaRepository`,
`SensoreRepository`).

Queste interfacce estendono `JpaRepository` e vengono implementate automaticamente da Spring al runtime, consentendo operazioni CRUD e query personalizzate senza scrivere manualmente il codice di accesso al database.

---

== 3.4 Model e DTO
#v(0.3em)

Il package *Model* contiene le entità JPA che rappresentano il modello dati
dell’applicazione e mappano le tabelle del database relazionale.

Accanto alle entità, il package *DTO* include oggetti di trasferimento dati
utilizzati per:
- inviare informazioni aggregate al frontend;
- disaccoppiare il modello di persistenza dalle API esposte;
- ottimizzare il payload delle risposte HTTP.

---

== 3.5 Configurazione e Sicurezza
#v(0.3em)

La configurazione di alto livello è gestita nei package *Config* e *Security*.
In particolare:
- `SecurityConfig` configura *Spring Security*, inclusi filtri JWT,
  autorizzazioni sulle rotte e gestione delle sessioni;
- eventuali configurazioni custom (ad esempio client MQTT) sono definite
  nel package *Config*.

I parametri applicativi (credenziali DB, URL del broker MQTT, configurazione
InfluxDB) sono caricati tramite `application.properties` oppure memorizzati
nel database e gestiti tramite interfaccia amministrativa.
