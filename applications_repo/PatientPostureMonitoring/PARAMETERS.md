# Parametri dell'applicazione

L'applicazione legge frame Depth dello split `test` SDT e assegna una delle
quattro classi `LYING`, `SITTING`, `STANDING` ed `EMPTY`. I parametri sono
stringhe nel descrittore, ma vengono convertiti al tipo corretto durante il
setup.

| Parametro | Significato | Impatto su CPU e tempi | Impatto sull'accuratezza |
|---|---|---|---|
| `dataset_path` | Percorso della directory SDT estratta, contenente `test/`. | Non modifica il costo dell'inferenza; un disco lento può aumentare il tempo di acquisizione. | Nessuno, se il dataset è quello previsto. Un dataset diverso rende il risultato non confrontabile. |
| `heavy_mode` | Se `false` usa il modello TFLite dynamic-range (leggero); se `true` usa il modello Float32. | `true` richiede più memoria e generalmente più CPU; la latenza aumenta rispetto alla modalità leggera. | Non esegue nuovo training: entrambi i modelli derivano dallo stesso addestramento. Float32 può conservare meglio la precisione numerica, ma non garantisce un aumento dell'accuratezza. |
| `num_threads` | Numero di thread assegnati all'interprete TFLite. | Aumentarlo può ridurre la latenza e aumentare l'utilizzo dei core, ma oltre i core disponibili (4 su Raspberry Pi 4B) può creare contesa e consumi inutili. | Nessun impatto previsto sul modello o sulle predizioni. |
| `target_fps` | Frequenza con cui la sorgente virtuale restituisce i frame. `0` disabilita l'attesa. | Valore più alto = più lavoro al secondo, fino al limite reale di CPU/disco. Con `0` si esegue al massimo della velocità. | Non cambia la predizione del singolo frame. Un valore troppo basso può però perdere transizioni rapide in una telecamera reale. |
| `loop_dataset` | Se `true`, ricomincia dal primo frame dopo la fine dello split; se `false`, termina quando il dataset è esaurito. | Il loop consente un'esecuzione continua; non cambia il costo per frame. | Nessuno sulla singola predizione. Il campo `dataset_cycle` distingue i cicli nel CSV. |
| `output_path` | Directory in cui salvare il CSV dei risultati. | La scrittura e il `flush` a ogni frame introducono un piccolo costo I/O; non influisce sulla rete neurale. | Nessuno. |

## Indicazioni pratiche

### Uso normale su Raspberry Pi 4B

```json
{
  "heavy_mode": "true",
  "num_threads": "4",
  "target_fps": "10",
  "loop_dataset": "true"
}
```

Dieci FPS sono un compromesso credibile per un monitoraggio posturale: la scena
non cambia rapidamente come in un'applicazione sportiva e non è necessario
elaborare ogni frame prodotto dalla telecamera.

### Modalità leggera

Impostare `heavy_mode=false`. È indicata quando la priorità è mantenere bassa la
latency e lasciare risorse ad altri servizi del Raspberry.

### Modalità pesante o prova di carico

Impostare `heavy_mode=true`, `num_threads=4` e, per un benchmark, `target_fps=0`.
In questa situazione l'applicazione non simula più una frequenza di telecamera:
elabora i frame appena possibile e misura il limite della piattaforma.

## Accuratezza e parametri temporali

L'accuratezza dipende soprattutto da modello, preprocessing e somiglianza tra
telecamera reale e SDT. Cambiare `target_fps`, `num_threads`, `loop_dataset` o
`output_path` non migliora il modello. Questi parametri controllano il modo in
cui il modello viene eseguito.

In un sistema reale è opportuno scegliere il massimo `target_fps` che il
Raspberry riesce a sostenere senza accumulare ritardo. Se l'inferenza impiega
più del tempo disponibile per frame, la frequenza effettiva sarà inferiore a
quella configurata.

## Configurazione distribuita

Il descrittore offre anche `config1`, che esegue acquisizione e pubblicazione in
una partizione e preprocessing e classificazione in un'altra. Questa scelta può
spostare il carico CPU tra due nodi, ma non modifica l'accuratezza: la stessa
immagine e lo stesso modello producono la predizione.
