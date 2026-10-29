# Parametri di input

Questo documento spiega  i parametri presenti nel descrittore
di `BilateralGaitAnalysis`. Per ogni parametro sono indicati il significato, la
modalità in cui viene utilizzato e l'effetto atteso su prestazioni e accuratezza.

L'applicazione analizza esclusivamente il cammino con due IMU montate sui piedi:
una a sinistra e una a destra. I parametri non modificano la configurazione
fisica delle IMU; descrivono come interpretare i dati che arrivano al programma.

## Parametri delle IMU e dell'acquisizione

### `imu_names`

Identificativi/indirizzi delle due IMU, separati da `-`. In modalità Wi-Fi sono
direttamente i MAC address (oppure gli indirizzi IP):

```text
E0:72:A1:21:6A:20-E0:72:A1:21:39:60
```

L'ordine è obbligatorio: prima IMU del piede sinistro, poi IMU del piede destro.
L'applicazione richiede esattamente due identificativi.

Un identificativo errato impedisce la connessione BLE o fa scartare i pacchetti;
non modifica invece il costo computazionale dell'elaborazione. In modalità file
il valore serve come etichetta logica e non seleziona i sensori del dataset:
questi vengono risolti dal loader tramite `subject_id` e `trial_id`.

### `sensor_positions`

Posizioni anatomiche associate alle due IMU. Il valore attualmente supportato è:

```text
left_foot-right_foot
```

Deve avere lo stesso ordine di `imu_names`. È vincolato perché BarthDTW, Herzer e
la ricostruzione delle traiettorie assumono sensori montati sui piedi. Un ordine
invertito scambierebbe i risultati sinistro/destri e renderebbe errate le
metriche bilaterali; non offre alcun vantaggio prestazionale.

### `wifi_interface`, `wifi_ssid`, `wifi_password`, `wifi_port`

Parametri della rete Wi-Fi. L'interfaccia è normalmente:

```text
wlan0
```

`wifi_port` è normalmente `8023`; SSID e password sono necessari solo se viene
gestito automaticamente l'access point. Non cambiano accuratezza o costo.

### `acquisition_mode`

Seleziona la sorgente dati:

- `wifi`: due IMU fisiche, pacchetti grezzi a 100 Hz;
- `file`: trial del dataset SensorPositionComparison2019, a 204,8 Hz nativi.

La pipeline gaitmap successiva è la stessa, ma la sorgente determina frequenza,
latenza e gestione dei pacchetti persi. Il dataset viene riprodotto rispettando i
tempi di registrazione; Wi-Fi procede invece alla velocità reale dei sensori.

### `input_path`

Percorso della radice estratta del dataset, per esempio:

```text
dataset/SensorPositionComparison2019-v1.0.0-beta
```

È obbligatorio in modalità `file` e relativo alla directory dell'applicazione.
In modalità `wifi` resta vuoto. Un percorso errato impedisce il setup, senza
alterare le prestazioni o l'accuratezza.

### `subject_id`

Identificativo del partecipante nel dataset, per esempio `4d91` o `8873`. È
utilizzato solo in modalità `file` per selezionare il soggetto. Cambiare soggetto
non modifica il costo teorico della pipeline, ma può cambiare la qualità dei
segnali, il numero di falcate rilevate e quindi la stabilità delle statistiche.

### `trial_id`

Prova del dataset da analizzare:

```text
slow_10, normal_10, fast_10,
slow_20, normal_20, fast_20, long
```

I suffissi `10` e `20` indicano il percorso nominale in metri, non la durata.
`long` è una prova continua di circa cinque minuti.

Una prova più lunga genera più finestre e più risultati, aumentando il tempo totale
di elaborazione e la dimensione dei file. Aumenta però anche il numero di falcate
disponibili e la robustezza delle statistiche aggregate.

### `campaign_name`

Nome della campagna Wi-Fi, per esempio:

```text
live_gait_campaign
```

Deve corrispondere al campo `cname` inviato dalle IMU ed è comune a entrambi i
dispositivi. Serve a evitare di mescolare pacchetti di acquisizioni diverse. È
obbligatorio in modalità Wi-Fi e non viene usato per selezionare un trial del
dataset.

### `initial_counter`

Valore iniziale del contatore `nth` configurato nella campagna BLE, compreso tra
`0` e `65535`. Normalmente si usa `0`.

Non cambia il carico degli algoritmi. È importante per interpretare correttamente
wrap-around e salti del contatore; un valore incoerente può produrre falsi
pacchetti mancanti o impedire la sincronizzazione delle due IMU.

### `sampling_frequency_hz`

Frequenza di campionamento dichiarata:

- `100` per le IMU BLE;
- `204.8` nelle configurazioni dataset.

In modalità BLE viene inviata alla campagna e usata per convertire campioni in
secondi. In modalità file il loader usa la frequenza nativa del dataset, quindi il
valore configurato è solo descrittivo e non ricampiona i dati.

Una frequenza maggiore conserva meglio gli eventi rapidi del passo ma aumenta il
numero di campioni e il costo computazionale. 100 Hz è il valore operativo minimo
previsto per questa pipeline; 10 Hz non è considerato adeguato per BarthDTW e
Herzer.

## Parametri delle finestre

### `window_duration_s`

Durata teorica di ogni finestra, normalmente `20` secondi. La finestra contiene
circa 2.000 campioni a 100 Hz o 4.096 campioni a 204,8 Hz.

Finestre più lunghe contengono più falcate e riducono il rischio che un singolo
confine interrompa una falcata, ma richiedono più memoria e fanno attendere più a
lungo il primo risultato. Finestre più brevi riducono latenza e memoria, ma
possono non contenere abbastanza falcate per BarthDTW, Herzer e le statistiche.

### `window_overlap_s`

Parte ripetuta tra due finestre consecutive, normalmente `2` secondi. Con una
finestra di 20 secondi, una nuova finestra viene avviata ogni 18 secondi.

Un overlap maggiore aiuta a non perdere falcate ai bordi e rende più stabile la
deduplicazione, ma rielabora più campioni e aumenta il carico. Un overlap nullo è
più economico, ma può perdere o spezzare falcate sui confini. Il valore deve essere
inferiore a `window_duration_s`.

## Preprocessing e algoritmi

### `lowpass_cutoff_hz`

Frequenza di taglio del filtro Butterworth passa-basso applicato nel preprocessing,
normalmente `20` Hz. Frequenze superiori vengono attenuate per ridurre rumore e
componenti non utili.

Il valore deve essere inferiore alla frequenza di Nyquist, cioè metà della
frequenza di campionamento effettiva. Un cutoff più basso riduce il rumore ma può
smussare picchi utili per gli eventi del passo; uno più alto conserva più dettaglio
ma lascia passare più rumore. Il filtro è applicato a ogni finestra e ha un costo
computazionale contenuto rispetto a BarthDTW e alla ricostruzione.

### `barth_max_cost`

Costo massimo accettato da BarthDTW per una corrispondenza tra template e segnale.
Il valore predefinito è `4.0`.

- valore più basso: matching più severo, meno falsi positivi ma rischio di perdere
  falcate reali;
- valore più alto: matching più permissivo, più falcate candidate ma maggiore
  rischio di falsi positivi.

Modifica soprattutto accuratezza e numero di falcate analizzate. Il costo
computazionale può aumentare leggermente se vengono mantenuti più candidati, ma il
parametro non cambia la frequenza o la dimensione delle finestre.

### `lightweight_mode`

Se `false`, vengono eseguite anche ricostruzione delle traiettorie e metriche
spaziali. Se `true`, queste fasi vengono saltate e restano disponibili
segmentazione, eventi e parametri temporali.

La modalità leggera riduce memoria e tempo CPU, risultando adatta al Raspberry Pi
4 o a prove lunghe. In cambio non produce lunghezza del passo, traiettoria,
orientamenti e altre metriche spaziali.

### `minimum_complete_strides`

Numero minimo di falcate complete richiesto dall'aggregatore per considerare
affidabile il risultato di un piede. Il valore predefinito è `3`.

Non forza il rilevamento delle falcate e non cambia direttamente il costo della
pipeline. Stabilisce invece quando una tabella può essere marcata come completa:
un valore maggiore è più prudente ma può lasciare più finestre senza statistiche;
un valore minore produce risultati prima, con maggiore variabilità.

## Output e timeout del framework

### `output_path`

Directory in cui vengono scritti JSON, CSV, risultati finali, il report
`acquisition_windows.csv` e, durante la diagnostica temporanea BLE, i file
`raw_wifi_packets_<imuid>.json`.


## Configurazioni consigliate

Per dataset:

```text
acquisition_mode       = file
sampling_frequency_hz   = 204.8
window_duration_s       = 20
window_overlap_s        = 2
lowpass_cutoff_hz       = 20
lightweight_mode        = false
```

Per IMU reali via Wi-Fi:

```text
acquisition_mode       = wifi
sampling_frequency_hz   = 100
window_duration_s       = 20
window_overlap_s        = 2
lowpass_cutoff_hz       = 20
lightweight_mode        = true   # utile per ridurre il carico sul Raspberry Pi 4
```

I range fisici delle IMU, pari a ±4 g per l'accelerometro e ±2000 °/s per il
giroscopio, non sono parametri di input: sono fissati dal firmware e vengono
decodificati dall'applicazione.
