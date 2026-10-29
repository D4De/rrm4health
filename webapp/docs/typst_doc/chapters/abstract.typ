// abstract.typ

= 1. Abstract
#v(0.6em)

/ Overview: Il codice sorgente del progetto è disponibile al seguente link: #link("https://github.com/ArturoMatteoSantarlasci/BSN_WebApp2.0")[BSN_WebApp]. 
  
  Il progetto BSN WebApp è una piattaforma web integrata progettata per la gestione, l'acquisizione e la visualizzazione di dati provenienti da reti di sensori corporei #text(weight: "bold","(Body Sensor Networks - BSN)"). 
L'obiettivo principale del sistema è fornire al personale medico e ai ricercatori uno strumento unificato che permetta sia il monitoraggio in tempo reale dei segnali fisiologici (come accelerometri e giroscopi) sia l'archiviazione efficiente delle serie temporali per analisi successive. \
L'architettura è stata sviluppata per garantire bassa latenza nella trasmissione dei dati e scalabilità nella gestione di volumi elevati di misurazioni inerziali.

Il sistema implementa una rigida separazione dei privilegi distinguendo il ruolo #text(weight: "bold","USER_MED"), dedicato al personale clinico per la gestione dei pazienti e l'avvio delle campagne, dal ruolo #text(weight: "bold","USER_DEV"), riservato agli admin per la configurazione degli script, dei database e la manutenzione dei sensori.

/ Tools: L'infrastruttura tecnologica adotta un approccio moderno basato su microservizi logici e containerizzazione. Il core del backend è sviluppato in #text(fill: rgb("#c33d36"), weight: "bold", "Java") con il framework #text(fill: rgb("#1e950f"), weight: "bold", "Spring Boot"), che gestisce la logica di business e le #text(fill: rgb("#5283A2"), weight: "bold", "API REST"). La comunicazione real-time è garantita dal protocollo #text(weight: "bold", "MQTT") per l'ingestione dei dati dai sensori e dalla tecnologia #text(weight: "bold", "Server-Sent Events (SSE)")  per lo streaming unidirezionale verso il frontend. 
  Inoltre, il broker/server MQTT può persistere i messaggi ricevuti su database; l'infrastruttura consente di configurare anche un salvataggio aggiuntivo su un ulteriore database scelto dall’utente. 
  
  
  La persistenza dei dati segue un modello ibrido (Polyglot Persistence): un database relazionale #text(fill: rgb("#372bbf"), weight: "bold", "MariaDB") gestisce i metadati strutturati, mentre #text(fill: rgb("#372bbf"), weight: "bold", "InfluxDB") è utilizzato specificamente per l'archiviazione ad alte prestazioni delle serie temporali (Time-Series Data). 
  
  Il frontend è realizzato come applicazione web multi-pagina con rendering server-side tramite #text(fill: rgb("#a11791"), weight: "bold", "Thymeleaf") . Si fa uso della libreria #text(fill: rgb("#c26e0f"), weight: "bold", "HTMX") sul lato client per arricchire l’interattività. Per la visualizzazione in tempo reale viene impiegata la libreria #text(fill: rgb("#188b24"), weight: "bold", "Chart.js"). #text(fill: rgb("#c33d36"), weight: "bold", "JavaScript (vanilla)")  per creare script per la gestione della logica UI. Lo stile dell’applicazione sono basati su #text(fill: rgb("#c20fc2"), weight: "bold", "Tailwind CSS") con componenti di #text(fill: rgb("#5283A2"), weight: "bold", "DaisyUI"). 

L’intera documentazione del progetto è stata redatta tramite #text(weight: "bold", "Typst"). \
I componenti del sistema vengono eseguiti come container e orchestrati tramite #text(weight: "bold", "Docker Compose").

La documentazione fornisce sia una panoramica generale, sia un’analisi tecnica approfondita rivolta a sviluppatori e manutentori del progetto.



