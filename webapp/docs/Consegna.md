Definizione e sviluppo di una applicazione web fruibile anche da dispositivi mobili per la gestione di campagne di collezione dati di Body Sensor Network (BSN) che rilevano i parametri vitali tramite dispositivi wearable.

## funzionalità

Il progetto ha come obiettivo quello di supportare le seguenti fasi di campagne sperimentali:
1. pianificazione della campagna, specificandone gli aspetti rilevanti:
	+ identificativo della campagna
	+ data e inizio
	+ persona
	+ tipo di campagna
	+ caratteristiche del campionamento (frequenza, durata, ...)
	+ sensori utilizzati (selezione tra quelli esistenti)
	+ comunicazione dati
		+ ble
		+ ant
	+ salvataggio dati
		+ locale
		+ db
	+ informazioni relative a salvataggio dei dati collezionati
2. esecuzione di una campagna
	+ avvio dell'applicazione che 
		+ abilita i sensori selezionati facendoli comunicare con il dispositivo che acquisisce i valori campionati
		+ fornisce i parametri per l'acquisizione
	+ visualizzazione in tempo reale dei dati acquisiti (se possibile)
	+ termine dell'applicazione (al termine della campagna)
3. esecuzione di programmi di analisi dati (non fanno parte dell'applicazione)
	+ selezione da una libreria di programmi disponibili del tipo di elaborazione che si desidera utilizzare
	+ selezione dei dati presenti da analizzare
	+ specifica di dove salvare i risultati se necessario
4. visualizzazione
	+ dati acquisiti
	+ dati in fase di acquisizione
	+ risultati di elaborazione
5. manutenzione (inserimento/eliminazione/aggiornamento) delle informazioni presenti
	+ sensori 
	+ campagne
	+ programmi disponibili per l'analisi
	+ dati presenti in altri repository (per esempio su una SD su cui sono stati salvati direttamente dai sensori)

### dettagli
tipi di campagna (scelta multipla):
+ respiro
+ battito cardiaco
+ attività motoria
+ benessere

informazioni sulle applicazioni:
+ nome
+ eseguibile
+ versione
+ caratteristiche

tipo di comunicazione
+ ant
+ ble

### modi di funzionamento
La modalità principale di fruizione dell'applicazione consiste nel supportare la persona che deve eseguire campagne di raccolta dati, anche contemporanee. Per cui deve essere immediato poter:
1. predisporre il kit per avviare una campagna, inserendo le informazioni necessarie (dati della campagna e selezione/associazione dei sensori da utilizzarsi)
2. avviare l'accoppiamento dei sensori relativi ad una BSN
3. avviare la raccolta dati
4. terminare la raccolta dati

Inoltre, deve essere possibile:
- dopo aver avviato la raccolta dati (fase 3) è possibile che si desideri avviare un'altra campagna, mentre la precedente è ancora in esecuzione
- mentre una o più campagne sono in esecuzione, visualizzare i dati che vengono raccolti (selezionando la campagna di interesse tra quante in esecuzione)
## dati
I dati da gestire sono di una duplice natura:
+ sequenze temporali (tipicamente quelli acquisiti dai sensori)
+ dati strutturati (quelli relativi agli elementi che fanno parte del sistema)
Per questo motivo si può pensare di avere a disposizione due diversi "database", uno relazionale (per esempio mariadb) e uno time-series (per esempio influxdb). Di fatto la parte relazionale è piuttosto contenuta per cui è anche possibile pensare di utilizzare utilizzare solo un database time-series.

## interfaccia
L'interfaccia utente deve prevedere un accesso leggermente differenziato in base al tipo di utente:
+ user-med: utente finale del sistema, interessato alle funzionalità 1-4
+ user-dev: utente esperto del sistema
+ admin: forse corrisponde a user-dev

### tecnologia
La soluzione tecnica adottata per la realizzazione della web app deve essere tale da privilegiare:
- semplicità di interazione
- possibilità di visualizzare sequenze temporali, anche dinamicamente (per la visualizzazione concorrente dei dati collezionati)
- facile manutenzione (funzionalità 5) dei dati presenti nel sistema

Poichè si tratta di un sistema prototipale che vedrà senz'altro degli ulteriori sviluppi, la soluzione presentata dovrà essere:
- facilmente manutenibile
- facilmente estendibile
- scalabile

### note
- Privilegierei uno sviluppo con docker per permettere di avere l'installazione di tutti i pacchetti necessari per spostare l'istanza su qualsiasi macchina. 
- Probabilmente verrà eseguito su un Raspberry Pi.
- Il software di comunicazione con i sensori e le applicazioni sono realizzate in ***python***

