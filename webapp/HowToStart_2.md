# How To Start

Guida per compilare e avviare la WebApp dopo aver scaricato il repository. I comandi sono pensati per Ubuntu/Debian e vanno eseguiti da un terminale.

## Prerequisiti

Per compilare e avviare la WebApp servono:

- Java JDK 21 o superiore;
- Docker Engine e Docker Compose v2;
- connessione Internet al primo build, per scaricare Maven e le dipendenze Java.

Maven non deve essere installato: il repository contiene `mvnw`, il Maven Wrapper. Per installare le dipendenze di sistema su Ubuntu/Debian:

```bash
sudo apt-get update
sudo apt-get install -y openjdk-21-jdk-headless docker.io docker-compose-v2
```

Avvia Docker e abilitalo all'avvio del computer:

```bash
sudo systemctl enable --now docker
```

Per usare Docker senza `sudo`, aggiungi il tuo utente al gruppo `docker`:

```bash
sudo usermod -aG docker "$USER"
```

La modifica al gruppo diventa effettiva dopo logout e login. Fino ad allora puoi anteporre `sudo` ai comandi Docker e Compose.

## Avvio completo con lo script RRM

Questa modalità avvia MariaDB, InfluxDB, Mosquitto, la WebApp e i processi RRM. Lo script `StartSingleNode.sh` deve trovarsi nella cartella principale del repository RRM, insieme alle cartelle `framework` e `install`.

Lo script installa, se mancanti, Java, Python, Git, Docker e Compose. Crea inoltre un ambiente Python e installa i pacchetti usati dall'RRM: `psutil`, `pyzmq` e `jsonschema`. Su Ubuntu/Debian può chiedere la password `sudo` per installare pacchetti di sistema.

Dalla cartella contenente `StartSingleNode.sh` esegui:

```bash
chmod +x StartSingleNode.sh
./StartSingleNode.sh
```

Durante la prima esecuzione scegli la configurazione MQTT e Influx:

1. `Locale`: broker Mosquitto e InfluxDB avviati in Docker sul computer;
2. `DB Cristiana`: servizi remoti preconfigurati nello script;
3. `Manuale`: inserisci host e porta MQTT, filtro topic, host e porta InfluxDB e nome database.

La configurazione MQTT viene scritta in `IoMTApp/data/mqtt-runtime.properties`; quella Influx viene inserita in MariaDB tramite `IoMTApp/setupdata/zz_database_config.sql`. Lo script avvia poi Compose, attende MariaDB, importa i file SQL iniziali e compila la WebApp se non trova già il JAR.

Al termine apri [http://localhost:8080](http://localhost:8080). Per creare il primo account usa `/register`, poi accedi da `/login`.

Comandi utili, sempre dalla cartella dello script:

```bash
./StartSingleNode.sh status
./StartSingleNode.sh logs
./StartSingleNode.sh stop
```

`stop` ferma WebApp e processi RRM avviati dallo script; i container Docker restano avviati. Per fermare anche i container, dalla cartella `IoMTApp` esegui `docker compose stop` (oppure `sudo docker compose stop`). I volumi dei database vengono mantenuti.

Per ricompilare forzatamente la WebApp:

```bash
./StartSingleNode.sh start --rebuild-webapp
```

Per saltare i test Maven durante il build:

```bash
./StartSingleNode.sh start --rebuild-webapp --skip-tests
```

## Avvio manuale della sola WebApp

Questa modalità avvia i servizi dati locali e la WebApp, senza i processi RRM. Apri un terminale nella cartella `IoMTApp`:

```bash
cd IoMTApp
```

Se il repository scaricato è già posizionato dentro `IoMTEcoSystem`, la cartella può chiamarsi `IoMTApp`; verifica la posizione con `pwd` e `ls`.

### 1. Configura MQTT e InfluxDB

Imposta il broker in `data/mqtt-runtime.properties`. Per usare il broker Mosquitto locale avviato dal Compose, i valori principali sono:

```properties
app.mqtt.enabled=true
app.mqtt.broker=tcp://localhost:1883
app.mqtt.topic=aaac/campaign/#
app.mqtt.client-id=bsn-webapp-sse-01
app.mqtt.username=
app.mqtt.password=
app.mqtt.qos=0
```

Il database Influx usato dalle campagne viene selezionato nella tabella `database_config` di MariaDB. Nella configurazione locale iniziale è `localhost:8086` e database `bsn_timeseries`; questi valori sono inseriti da `setupdata/zz_database_config.sql` quando MariaDB inizializza un volume nuovo. I file in `setupdata` vengono eseguiti automaticamente da MariaDB solo alla prima creazione del volume.

Se vuoi che lo script guidato generi queste configurazioni, usa l'avvio completo descritto sopra. Se MariaDB ha già un volume dati, modificare il file SQL non cambia automaticamente le righe già presenti nel database.

### 2. Avvia i database e il broker

```bash
docker compose up -d
```

In caso di permessi Docker non ancora aggiornati, usa:

```bash
sudo docker compose up -d
```

Compose avvia MariaDB sulla porta `3306`, InfluxDB sulla `8086` e Mosquitto sulla `1883`. I dati vengono conservati nei volumi Docker anche dopo il riavvio dei container.

### 3. Compila la WebApp

Per compilare ed eseguire anche i test:

```bash
./mvnw clean package
```

Per saltare i test:

```bash
./mvnw clean package -DskipTests
```

Il JAR viene creato in `target/`. Se il wrapper non è eseguibile:

```bash
chmod +x mvnw
```

### 4. Avvia la WebApp

```bash
java -jar target/bsn-webapp-0.0.1-SNAPSHOT.jar
```

Lascia il terminale aperto e visita [http://localhost:8080](http://localhost:8080). Per creare il primo account vai su `/register`, poi accedi da `/login`. Esegui il comando dalla cartella `IoMTApp`: la WebApp usa alcuni percorsi relativi, tra cui `data/` e `scripts/`.

Per fermare la WebApp premi `Ctrl+C`. Per fermare i container lasciando intatti i database:

```bash
docker compose stop
```

Per riavviarli:

```bash
docker compose start
```

## Compilazione senza avviare i processi

Per verificare solo che le classi Java compilino, dalla cartella `IoMTApp`:

```bash
./mvnw compile
```

Oppure, dalla cartella principale RRM, lo script offre la modalità:

```bash
./StartSingleNode.sh start --compile-only
```

Questa modalità usa comunque lo script completo per installazione, configurazione e avvio dei container prima della compilazione. Se vuoi soltanto compilare la WebApp senza avviare servizi, usa direttamente `./mvnw compile` dentro `IoMTApp`.

## Risoluzione dei problemi

- **`JAVA_HOME` o Java non trovato**: installa un JDK 21+ e controlla `java -version`.
- **`ensurepip is not available` durante l'installazione RRM**: installa il pacchetto `python3-venv` della versione Python presente, ad esempio `sudo apt-get install python3.12-venv`, poi riesegui lo script. Lo script completo prova a installare il pacchetto `venv` automaticamente.
- **Permesso negato su Docker**: usa temporaneamente `sudo docker compose ...`; dopo aver aggiunto l'utente al gruppo Docker fai logout e login.
- **Porta già occupata**: controlla che non siano già in esecuzione MariaDB/MySQL sulla `3306`, InfluxDB sulla `8086`, Mosquitto sulla `1883` o un'altra WebApp sulla `8080`.
- **MariaDB non pronto al primo avvio**: controlla `docker compose logs mariadb`; dopo che il container è diventato healthy puoi rieseguire lo script completo, che riapplica schema e dati iniziali.
- **La pagina si apre ma l'avvio campagne non funziona**: l'avvio manuale della sola WebApp non avvia RRM Global e RRM Local. Per usare le campagne avvia anche RRM tramite `StartSingleNode.sh`.
