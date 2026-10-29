# BilateralGaitAnalysis

**Status: AI-assisted framework integration, with a positive functional
validation outcome confirmed by the project maintainer.**

The application performs continuous gait analysis using exactly two IMUs,
mounted on the left and right foot. It is an implemented RRM4Health application,
not an empty skeleton.

## Application sources

This application is not a direct port of a single standalone script. Its
framework-facing code adapts algorithms and examples from the gaitmap ecosystem:

- [gaitmap official examples](https://gaitmap.readthedocs.io/en/stable/auto_examples/):
  the basis for BarthDtw stride segmentation, Herzer event detection, temporal
  parameter calculation, stride-level trajectory reconstruction and spatial
  parameter calculation.
- [gaitmap-datasets](https://github.com/mad-lab-fau/gaitmap-datasets): the loader
  used for decoding, calibration, synchronization and trial selection during
  dataset replay.
- [Sensor Position Comparison Dataset](https://zenodo.org/records/5747173),
  DOI `10.5281/zenodo.5747173`: the SensorPositionComparison2019 dataset used
  by the file-acquisition mode.

The original algorithm and dataset authors retain their respective attribution;
the local application adds the RRM task lifecycle, acquisition adapters,
windowing, cross-window aggregation and result export. See
[REFERENCES.md](REFERENCES.md) for the detailed algorithm/publication references
and [DATASET_PROVENANCE.md](DATASET_PROVENANCE.md) for the dataset's source,
integrity audit and loading constraints.

## AI-assisted integration

The application was implemented and integrated into RRM4Health with AI
assistance. The integration adapts the source algorithms to the descriptor's
tasks, dependencies and input/output contracts, with task-specific setup, loop
and cleanup methods.

The framework-facing implementation is
[BilateralGaitAnalysis.py](BilateralGaitAnalysis.py), supported by the modules
in `Util/`. AI assistance concerns the local implementation and framework
adaptation; it does not imply authorship of the upstream algorithms or replace
functional validation.

## Validation status

**Functional validation completed with a positive outcome**.

## Processing pipeline

1. synchronized file replay or live Wi-Fi RAW acquisition;
2. overlapping windows (20 s with 2 s overlap by default);
3. gaitmap foot-frame preprocessing;
4. `BarthDtw` stride segmentation at the native input frequency;
5. `HerzerEventDetection`;
6. `TemporalParameterCalculation`;
7. optional stride-level trajectory reconstruction and
   `SpatialParameterCalculation`;
8. cross-window deduplication and final aggregation after framework shutdown.

`lightweight_mode=true` skips trajectory reconstruction and spatial
parameters while preserving temporal analysis. The user, rather than a fixed
trial timer, decides when to stop the application.

## Code structure

`BilateralGaitAnalysis.py` is the framework-facing orchestrator: it defines the
task lifecycle, selects file or Wi-Fi acquisition and connects task inputs and
outputs. Reusable logic lives in `Util/`, following the same organisation used by
the other applications:

- `dataset_source.py`: SensorPositionComparison2019 file windows;
- `gait_pipeline.py`: filtering, gaitmap algorithms, aggregation and export;
- `acquisition_report.py`: per-window acquisition-quality CSV;
- `config.py`: shared parsing of framework parameters;
- `gait_constants.py`: common sensor names and runtime setup.

[`WifiAcquisitionMngr`](../../utilities_library/WifiAcquisitionMngr.py) is the shared
Wi-Fi manager in `utilities_library`, independent of the gait-specific pipeline.


```python
from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr
```

## Acquisition modes

- `file`: replay SensorPositionComparison2019 through the official dataset loader.
- `wifi`: acquire two synchronized foot IMUs using the framework Wi-Fi RAW manager.

The former `memory` mode is intentionally not part of this application.

## Dataset replay

The file-acquisition task is implemented for SensorPositionComparison2019.
Set `input_path` to the extracted dataset root, `subject_id` to one of its
participants and `trial_id` to one of `slow_10`, `normal_10`, `fast_10`,
`slow_20`, `normal_20`, `fast_20`, or `long`.

The official `gaitmap-datasets` loader decodes and calibrates the NilsPod files,
synchronises the devices, extracts the requested test and aligns their coordinate
systems. The application then retains only `l_instep` and `r_instep` and returns
overlapping windows named `left_sensor` and `right_sensor`.

The same acquisition task can alternatively collect two physical foot IMUs over
Wi-Fi at 100 Hz using RAW packets. All subsequent gaitmap, aggregation and export tasks are implemented.

File replay always follows recording time. A window becomes available only when
its recorded end time has elapsed: a 20-second first window therefore takes 20
seconds, and subsequent windows with 2-second overlap arrive every 18 seconds. The
acquisition task remains active throughout this wait; downstream tasks run only
after a complete window exists. Samples remain at their native 204.8 Hz.

For every completed dataset or Wi-Fi window, the application appends one row to
`acquisition_windows.csv` inside the configured `output_path`. The file reports
the window index, size in samples, theoretical duration, actual wall-clock
acquisition duration, sampling frequency and the number of Wi-Fi packets lost during
that window. Packet loss is derived separately for each physical IMU from forward
gaps in its `nth` counter; dataset windows have zero lost packets.

During the temporary Wi-Fi diagnostic capture, the raw packets are also written to
one JSON array per configured IMU, named `raw_wifi_packets_<imuid>.json`. These files
are written before decoding and therefore include packets later ignored by the
gait pipeline.

Every active task logs `START`, `END`, window index and processing duration. Null
iterations used while waiting for a real-time file window do not generate phase
logs, preventing repeated messages.

## Preprocessing

The preprocessing task checks synchronized finite two-foot signals and currently
applies a fourth-order zero-phase Butterworth low-pass filter. It preserves the
native acquisition frequency: dataset files remain at 204.8 Hz and Wi-Fi signals
remain at the physical IMU rate of 100 Hz. Acceleration remains in m/s²
and angular velocity in degree/s, as required by gaitmap.

The external 20 Hz low-pass is an application design choice, not a mandatory
gaitmap preparation step. Its effect on gait metrics depends on the input and
configuration. In particular, `HerzerEventDetection`
already applies its own configurable low-pass internally for IC detection.

## Stride segmentation

Stride segmentation is implemented with gaitmap's `BarthDtw`, using its original
template and the descriptor's `barth_max_cost` (4.0 by default). Each window is
converted from gaitmap sensor frame to foot body frame before segmentation. Template
resampling is enabled, so only the reference template is adapted to the native
window rate; the dataset remains at 204.8 Hz and Wi-Fi data remains at 100 Hz.

The task returns both window-local sample borders for the following Herzer task and
absolute trial times for later removal of duplicate strides in overlap regions.

## Gait-event detection

`HerzerEventDetection` is implemented with its official default parameters. It
receives body-frame data, the local Barth stride borders and the native sampling
rate. The task preserves both official results: the event annotations on the
original Barth borders and the minimal-velocity-aligned stride list required by
trajectory and temporal-parameter calculation. Empty/quiet sensor windows produce
well-formed empty tables.

## Temporal parameters

`TemporalParameterCalculation(expected_stride_type="min_vel")` is implemented on
Herzer's minimal-velocity stride lists. It returns per-stride `stride_time`,
`swing_time` and `stance_time`, all in seconds, plus gaitmap's pretty tables with
units in their labels. Trial-level summaries, cadence, bilateral asymmetry and
overlap deduplication remain responsibilities of the later aggregator.

## Stride trajectories

Full mode reconstructs each Herzer min-velocity stride independently with
`StrideLevelTrajectory` and its official defaults: `SimpleGyroIntegration` plus
`ForwardBackwardIntegration`. It returns quaternion orientation and position in
metres. Gaitmap calculates velocity internally while integrating position, but the
application does not copy or expose it because no downstream task consumes it.
These trajectories are relative to each stride and require only accelerometer and
gyroscope data.

When `lightweight_mode=true`, reconstruction is skipped and the task returns an
explicit disabled envelope. Temporal analysis remains active in both modes.

## Spatial parameters

Full mode calculates all nine official `SpatialParameterCalculation` outputs:
stride length, gait velocity, arc length, IC angle, TC angle, turning angle,
maximum orientation change, maximum sensor lift and maximum lateral excursion.
The per-sample sole-angle diagnostic is intentionally not copied. Lightweight mode
returns an explicit disabled result while temporal parameters remain available.

## Cross-window aggregation

The aggregator converts Herzer IC samples to absolute trial time and treats
same-foot ICs within 100 ms as duplicate observations from overlapping windows.
It retains the observation farthest from a window edge, combines temporal and
optional spatial parameters, and reports cumulative per-foot tables plus count,
mean, sample standard deviation, median, minimum and maximum. The result also says
whether each foot reached `minimum_complete_strides`.

## Result export

Each updated aggregate atomically overwrites `<participant>_<trial>_latest.json`
and one CSV per foot in `output_path`. JSON contains metadata, bilateral counts,
summaries and all stride rows; CSV contains the machine-friendly combined parameter
table. During framework cleanup a separate `<participant>_<trial>_final.json` is
written. Unchanged EOF iterations do not trigger additional SD-card writes.

Filtering is performed independently on each overlapping window. The overlap
provides a boundary region that the later result aggregator will discard while
deduplicating strides, avoiding the use of filter-edge samples in final metrics.

## External provenance

- gaitmap core 2.6.0: MIT.
- gaitmap_mad 2.6.0 (`BarthDtw`): AGPL-3.0.
- Dataset used by file replay: SensorPositionComparison2019,
  DOI `10.5281/zenodo.5747173`.

The compatibility of AGPL-3.0 with the framework's distribution model must be
confirmed before the application is distributed.

The local validation dataset has been structurally audited. Its source,
license, integrity metadata, participant exclusions, and loading constraints
are recorded in `DATASET_PROVENANCE.md`.

Local datasets are kept separately from application code under `dataset/`.
That directory is ignored by Git and currently contains the extracted
`SensorPositionComparison2019-v1.0.0-beta` dataset.

## Repository location and deployment

The source and [application descriptor](BilateralGaitAnalysis.json) are
maintained together. The application is not installed in the framework in this
checkout. See the [application repository guide](../README.md) for deployment.d
