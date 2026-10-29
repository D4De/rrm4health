# Riferimenti del progetto PatientPostureMonitoring

Questo documento raccoglie le fonti consultate e il codice utilizzato come base
per l'implementazione. Distingue le fonti effettivamente confluite nella versione
attuale dalle alternative analizzate e poi escluse.

## Dataset e documentazione

### SDT Dataset

- **SDT – Simultaneously-collected multimodal lying pose dataset**, Zenodo
  record [4124309](https://zenodo.org/records/4124309).
- Il README distribuito con il dataset è la fonte per struttura delle directory,
  split `train`/`validation`/`test`, coppie Depth/Thermal, formato dei frame e
  codifica delle quattro classi.
- La versione dell'applicazione usa il solo split reale `test` della componente
  Depth, riproducendolo come sorgente di una telecamera virtuale.

## Articoli e letteratura

- **TinyM²Net-V3 / Medical human pose recognition paper**, versione consultata:
  [arXiv:2405.12353v1](https://arxiv.org/abs/2405.12353) (PDF locale:
  `/home/cysko7927/Scaricati/2405.12353v1.pdf`).
  Sono stati presi come riferimento l'uso di input 64×64, il ramo Depth con
  MobileNetV2, il ramo Thermal con VGG16, la classificazione a quattro stati,
  l'uso di pesi ImageNet e il protocollo sperimentale multimodale. Il paper è
  stato usato come riferimento metodologico; il modello multimodale non è
  incluso nell'applicazione corrente.

## Documentazione tecnica

- [Keras MobileNetV2](https://keras.io/api/applications/mobilenet/#mobilenetv2-function):
  architettura, pesi ImageNet e sostituzione della testa con quattro neuroni.
- [TensorFlow Lite](https://www.tensorflow.org/lite/guide): conversione del
  modello Keras, interprete e distribuzione su hardware edge.
- [TFLite Python runtime](https://www.tensorflow.org/lite/guide/python): runtime
  leggero usato su Raspberry Pi (`tflite-runtime`).
- [TensorFlow Lite performance](https://www.tensorflow.org/lite/performance/best_practices):
  scelta del numero di thread e confronto tra modello Float32 e modello con
  ottimizzazione dynamic-range.
- [Pillow](https://pillow.readthedocs.io/): caricamento dei frame PNG a 16 bit.

## Codice usato come base

### Componenti runtime dell'applicazione

- `Util/sdt_frame_source.py`: loader sequenziale dello split SDT reale, pacing a
  FPS configurabile e gestione del riavvio del dataset.
- `Util/depth_preprocessing.py`: normalizzazione Depth, ridimensionamento
  bilineare a 64×64 e replica sui tre canali richiesti da MobileNetV2.
- `Util/tflite_classifier.py`: selezione dell'interprete (`tflite-runtime` con
  fallback TensorFlow), caricamento del modello e classificazione delle quattro
  classi.

## Scelte risultanti

La versione operativa è quindi una pipeline **Depth-only**:

`frame Depth SDT → normalizzazione/resize 64×64 → MobileNetV2 →
LYING/SITTING/STANDING/EMPTY → CSV`

`heavy_mode=false` usa il modello TFLite dynamic-range; `heavy_mode=true` usa il
modello TFLite Float32.