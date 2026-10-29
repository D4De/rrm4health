# Fonti e riferimenti di BilateralGaitAnalysis

Questo documento raccoglie le fonti usate per progettare l'applicazione e indica
per ogni task quale materiale è stato usato come base. Le fonti non implicano che
l'applicazione sia una copia integrale degli esempi: il codice locale è un adapter
originale che converte i dati nel contratto del framework RRM4Health, gestisce le
finestre e collega i task `setup`/`loop`/`cleanup`.

## Sintesi per task

| Task/modulo | Base di riferimento | Uso nel codice locale |
|---|---|---|
| `acquire_imu_window` (dataset) | `SensorPositionComparison2019` e loader `gaitmap-datasets` | Selezione dei due sensori `l_instep`/`r_instep`, finestre sovrapposte e replay temporizzato in [`Util/dataset_source.py`](Util/dataset_source.py). |
| `acquire_imu_window` (Wi-Fi) | [`utilities_library/WifiAcquisitionMngr.py`](../../utilities_library/WifiAcquisitionMngr.py) e relativo contratto `WifiAcquisitionMngr` | Riutilizzo del manager generico senza modificarlo; decoding, conversione dei range fissi, sincronizzazione tramite `nth` e finestre sono logica specifica di Gait in [`BilateralGaitAnalysis.py`](BilateralGaitAnalysis.py). |
| `preprocess_imu_window` | Convenzioni di input gaitmap e coordinate foot/body frame | Controllo delle colonne, conversione delle unità e filtro Butterworth in [`Util/gait_pipeline.py`](Util/gait_pipeline.py). Il filtro esterno è una scelta applicativa. |
| `segment_strides` | Esempio ufficiale **BarthDtw stride segmentation** | Conversione a foot body frame, istanziazione `BarthDtw`, segmentazione dei due piedi e metadati locali/assoluti. |
| `detect_gait_events` | Esempio ufficiale **Herzer event detection** | Chiamata a `HerzerEventDetection`, mantenimento di `annotated_original_event_list_` e `min_vel_event_list_`. |
| `calculate_temporal_parameters` | Esempio ufficiale **Temporal parameters calculation** | `TemporalParameterCalculation(expected_stride_type="min_vel")` e tabelle per piede. |
| `reconstruct_stride_trajectories` | Esempio ufficiale **Stride Level Trajectory reconstruction** | `StrideLevelTrajectory` con `SimpleGyroIntegration` e `ForwardBackwardIntegration`; modalità lightweight locale. |
| `calculate_spatial_parameters` | Esempio ufficiale **Spatial parameters calculation** | `SpatialParameterCalculation` applicato a eventi, traiettorie, posizione e orientamento. |

## Documentazione software

### Gaitmap

- [Gaitmap documentation – examples gallery](https://gaitmap.readthedocs.io/en/stable/auto_examples/)
- [BarthDtw stride segmentation](https://gaitmap.readthedocs.io/en/v2.6.0/auto_examples/stride_segmentation/barth_dtw_stride_segmentation.html)
- [BarthDtw API reference](https://gaitmap.readthedocs.io/en/v2.6.0/modules/generated/stride_segmentation/gaitmap.stride_segmentation.BarthDtw.html)
- [Herzer event detection](https://gaitmap.readthedocs.io/en/stable/auto_examples/event_detection/herzer_event_detection.html)
- [HerzerEventDetection API reference](https://gaitmap.readthedocs.io/en/stable/modules/generated/event_detection/gaitmap.event_detection.HerzerEventDetection.html)
- [Temporal parameters calculation](https://gaitmap.readthedocs.io/en/latest/auto_examples/parameters/temporal_parameters.html)
- [Spatial parameters calculation](https://gaitmap.readthedocs.io/en/v2.5.1/auto_examples/parameters/spatial_parameters.html)
- [TemporalParameterCalculation API reference](https://gaitmap.readthedocs.io/en/v2.6.0/modules/generated/parameters/gaitmap.parameters.TemporalParameterCalculation.html)
- [Gaitmap API reference](https://gaitmap.readthedocs.io/en/latest/modules/index.html)
- [Gaitmap example data and documented sampling rates](https://gaitmap.readthedocs.io/en/v2.6.0/modules/generated/example_data/gaitmap.example_data.get_healthy_example_imu_data.html)
- [Gaitmap-datasets repository](https://github.com/mad-lab-fau/gaitmap-datasets)

Gli esempi gaitmap usano tipicamente segnali da IMU montate sui piedi, dati già
allineati al gaitmap sensor/foot-body frame e frequenze come 102,4 o 204,8 Hz.
Per questo l'applicazione usa due IMU sugli instep e conserva la frequenza nativa
del dataset o quella fisica Wi-Fi.

## Articoli scientifici

### Ecosistema software

- Küderle, A. et al. (2024), *Gaitmap—An Open Ecosystem for IMU-Based Human
  Gait Analysis and Algorithm Benchmarking*. IEEE Open Journal of Engineering in
  Medicine and Biology, 5, 163–172.
  [DOI: 10.1109/OJEMB.2024.3356791](https://doi.org/10.1109/OJEMB.2024.3356791)
  [PubMed](https://pubmed.ncbi.nlm.nih.gov/38487091/)

  È il riferimento generale per l'uso dell'ecosistema gaitmap con IMU indossate
  ai piedi, dataset standardizzati e benchmark degli algoritmi.

### Segmentazione e parametri inerziali

- Barth, J. et al. (2013), *Subsequence dynamic time warping as a method for
  robust step segmentation using gyroscope signals of daily life activities*.
  Proceedings of the IEEE EMBC.
  [DOI: 10.1109/EMBC.2013.6611104](https://doi.org/10.1109/EMBC.2013.6611104)

- Rampp, A. et al. (2015), *Inertial Sensor-Based Stride Parameter Calculation
  From Gait Sequences in Geriatric Patients*. IEEE Transactions on Biomedical
  Engineering, 62(4), 1089–1097.
  [DOI: 10.1109/TBME.2014.2368211](https://doi.org/10.1109/TBME.2014.2368211)

- Figueiredo, J. et al. (2018), *Gait Event Detection in Controlled and Real-Life
  Situations: Repeated Measures From Healthy Subjects*. IEEE TNSRE, 26(10),
  1945–1956.
  [DOI: 10.1109/TNSRE.2018.2868094](https://doi.org/10.1109/TNSRE.2018.2868094)

- Herzer, L. (2021), bachelor thesis and work underlying gaitmap's
  `HerzerEventDetection`. The gaitmap API documents this origin and the
  differences between the original thesis implementation and the maintained
  implementation.
  [FAU profile](https://www.mad.tf.fau.de/person/liv-herzer-2/)

### Parametri spaziali

- Kanzler, C. M. et al. (2015), *Inertial sensor based and shoe size independent
  gait analysis including heel and toe clearance estimation*. IEEE EMBC.

- Rampp, A. et al. (2015), articolo già indicato sopra, usato come riferimento
  per i parametri temporali e spaziali da sequenze inerziali.

## Dataset e pubblicazioni collegate

- Küderle, A. et al., *Sensor Position Comparison Dataset*.
  [Zenodo record](https://zenodo.org/records/5747173),
  [DOI: 10.5281/zenodo.5747173](https://doi.org/10.5281/zenodo.5747173).

- Küderle, A., Roth, N., Zlatanovic, J., Zrenner, M., Eskofier, B. e Kluge, F.
  (2022), *The Placement of Foot-Mounted IMU Sensors Does Affect the Accuracy of
  Spatial Parameters during Regular Walking*. PLOS ONE 17(6), e0269567.
  [DOI: 10.1371/journal.pone.0269567](https://doi.org/10.1371/journal.pone.0269567)

Il dataset locale e l'audit della sua struttura sono descritti in
[`DATASET_PROVENANCE.md`](DATASET_PROVENANCE.md). La copia locale non è la fonte
del loader: i file binari NilsPod devono essere decodificati, calibrati,
sincronizzati e orientati dal loader ufficiale.


Queste parti sono riferimenti architetturali del repository; la logica gaitmap
specifica è stata scritta adattando le API ufficiali documentate sopra.
