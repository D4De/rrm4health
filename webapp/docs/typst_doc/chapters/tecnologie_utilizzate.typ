= 2. Tecnologie Utilizzate
#v(0.6em)
#set list(indent: 1.5em)

Il progetto BSN WebApp adotta un insieme di tecnologie moderne per la realizzazione
dell’interfaccia utente, della logica applicativa e dell’infrastruttura di supporto.
Di seguito vengono descritte le principali tecnologie utilizzate, organizzate per ambito.

== 2.1 Backend
#v(0.3em)

Il backend dell’applicazione è sviluppato in *Java* utilizzando il framework *Spring Boot* (versione 3.x),
che consente una rapida configurazione e un’architettura modulare basata sul paradigma MVC.

Le principali componenti Spring impiegate sono:
- *Spring MVC*: gestione del routing web e dei controller;
- *Spring Data JPA*: accesso ai dati e persistenza su database relazionale;
- *Spring Security*: autenticazione e autorizzazione degli utenti.

== 2.2 Persistenza dei Dati
#v(0.3em)

La persistenza è suddivisa in due livelli distinti, in base alla natura dei dati gestiti.

- *Database Relazionale*:  
  Viene utilizzato *MariaDB* per l’archiviazione dei dati strutturati e persistenti
  (utenti, sensori, pazienti, campagne, configurazioni).  
  Il database è eseguito all’interno di un container Docker e l’accesso avviene tramite
  *JDBC* utilizzando il driver `mariadb-java-client`.

- *Database Time-Series*:  
  I dati grezzi dei sensori sono memorizzati in *InfluxDB* (versione 1.8), un database
  ottimizzato per serie temporali. Questa soluzione consente query efficienti su
  intervalli temporali ed è particolarmente adatta alla visualizzazione di grafici storici.

---

== 2.3 Comunicazione e Streaming dei Dati
#v(0.3em)

La comunicazione tra sensori e server avviene tramite il protocollo *MQTT*.
Gli script Python pubblicano i dati su un broker MQTT esterno, mentre il backend
si sottoscrive ai topic tramite la libreria *Eclipse Paho MQTT*.

Per la trasmissione dei dati in tempo reale al browser viene utilizzato il meccanismo
di *Server-Sent Events (SSE)*, che permette al server di mantenere una connessione
persistente con il client e inviare aggiornamenti continui.

---

== 2.4 Frontend
#v(0.3em)

L’interfaccia utente è realizzata come applicazione web multi-pagina con rendering
server-side tramite *Thymeleaf*.

Le principali tecnologie frontend utilizzate sono:
- *HTMX*: aggiornamento dinamico di frammenti HTML senza ricaricare l’intera pagina;
- *Chart.js*: visualizzazione dei dati sensoriali tramite grafici interattivi;
- *JavaScript (Vanilla)*: gestione della logica client-side personalizzata;
- *Tailwind CSS* con *DaisyUI*: definizione dello stile grafico e del layout responsivo.

---

== 2.5 Containerizzazione e DevOps
#v(0.3em)

Il progetto include una configurazione *Docker Compose* per l’orchestrazione dei servizi
di supporto (database, servizi esterni).

Il sistema di build è gestito tramite *Maven*, che cura la gestione delle dipendenze
e il ciclo di build dell’applicazione.  
Tra le dipendenze principali si segnalano:
- driver JDBC per MariaDB;
- client Java per InfluxDB;
- libreria Eclipse Paho MQTT;
- supporto a *JSON Web Token (JWT)* per la sicurezza.
