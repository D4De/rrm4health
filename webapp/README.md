<div align="center">
  <img src="docs/typst_doc/assets/sensor-icon.svg" alt="BSN WebApp Icon" width="120" />
  <h1>CAMPAIGN:Clinical Application Manager for Patient Acquisition and Intelligent Monitoring</h1>
  <p>
    Piattaforma web per gestione, acquisizione e visualizzazione di dati da Body Sensor Networks (BSN),
    con monitoraggio real-time e archiviazione efficiente di serie temporali.
  </p>
  
</div>

---

## Overview

**BSN WebApp** è una piattaforma web integrata pensata per:
- **monitorare in tempo reale** segnali provenienti da sensori corporei (es. IMU: accelerometri e giroscopi);
- **archiviare serie temporali** per analisi successive;
- offrire un’interfaccia unificata per **personale medico** e **amministratori/tecnici**.

L’architettura è progettata per garantire **bassa latenza** e **scalabilità** nella gestione di grandi volumi di misurazioni inerziali.

❗![ATTENZIONE](https://img.shields.io/badge/ATTENZIONE-red):
Ad oggi la WebApp è configurata solo per funzionare tramite server/broker MQTT.

---

## Funzionalità principali

- **Real-time monitoring** con streaming dei dati verso il frontend
- **Gestione campagne** e organizzazione delle acquisizioni
- **Gestione pazienti / soggetti** 
- **Gestione sensori** e manutenzione/configurazione
- **Persistenza ibrida (Polyglot Persistence)**:
  - **MariaDB** per metadati strutturati
  - **InfluxDB** per serie temporali ad alte prestazioni
- Possibilità che il broker/server MQTT **persisti** i messaggi su database e/o che sia configurabile un **salvataggio aggiuntivo** su un ulteriore database scelto dall’utente


## Ruoli e permessi

Il sistema implementa una separazione rigida dei privilegi tramite ruoli:

- **USER_MED**  
  Per personale clinico/ricercatori: gestione pazienti/soggetti e avvio/gestione campagne.

- **USER_DEV**  
  Per admin/tecnici: configurazione script e database, manutenzione sensori e componenti infrastrutturali.



## Tech Stack

- **Java / Spring Boot**
- **MQTT** (ingestion)
- **SSE** (streaming real-time verso UI)
- **MariaDB** (relazionale)
- **InfluxDB** (time-series)
- **Thymeleaf**, **HTMX**, **Chart.js**
- **Tailwind CSS**, **DaisyUI**
- **Docker Compose**
- **Typst** (documentazione)

---

