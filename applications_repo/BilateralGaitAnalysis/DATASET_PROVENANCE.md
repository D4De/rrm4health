# SensorPositionComparison2019 provenance

## Source

- Title: Sensor Position Comparison Dataset
- Authors: Arne Küderle, Nils Roth, Jovana Zlatanovic, Markus Zrenner,
  Björn Eskofier, and Felix Kluge
- Zenodo record: <https://zenodo.org/records/5747173>
- DOI: <https://doi.org/10.5281/zenodo.5747173>
- Published version: `v1.0.0-beta`
- License reported by the Zenodo API: CC BY 4.0
- Archive name: `sensorpositoncomparison.zip` (the missing `i` in
  `positon` is part of the upstream filename)
- Expected archive size: `3,676,811,489` bytes
- Expected archive MD5: `2e72d1d7e2352003bf3686dd8da77dd3`
- Local audit date: 2026-08-30

When results derived from the dataset are published, cite the dataset and:

Küderle A, Roth N, Zlatanovic J, Zrenner M, Eskofier B, Kluge F. “The
Placement of Foot-Mounted IMU Sensors Does Affect the Accuracy of Spatial
Parameters during Regular Walking.” PLOS ONE 17(6), 2022, e0269567.
<https://doi.org/10.1371/journal.pone.0269567>

## Local copy

The extracted dataset is stored in the application's dedicated data directory:

```text
dataset/SensorPositionComparison2019-v1.0.0-beta/
```

The complete `dataset/` directory is explicitly excluded by the repository
`.gitignore`. It must not be committed. The upstream directory was renamed
locally to correct the unclear upstream spelling; its contents were not
modified. At audit time it contained 683 files and occupied
5,084,146,606 bytes on disk.

Only the extracted directory was supplied. The original ZIP was not present,
so its MD5 could not be independently verified locally. The structural checks
below passed, but they are not a cryptographic substitute for checking the ZIP.

## Structural audit

The dataset contains 15 subject directories but 14 logical participants.
Participant `6dbe` was recorded twice because the first recording had a faulty
or missing insole stream. The upstream README instructs users to select
`6dbe_2`; therefore application validation and benchmarks must exclude `6dbe`.

Canonical subject directories:

```text
4d91 5047 5237 54a9 6dbe_2 6e2e 80b8 8873 8d60 9b4b c9bb cb3d cdfc e54d
```

For every canonical participant the audit found:

- `meta_data.json`;
- both `l_instep` and `r_instep` sensor identifiers;
- corresponding raw NilsPod `.bin` streams;
- metadata boundaries for the `long` test;
- `mocap/long_steps.csv` with events for both feet.

After excluding `6dbe`, the long trials contain 6,138 reference strides in
total. Their durations range from approximately 303.25 to 312.39 seconds at
the documented IMU sampling frequency of 204.8 Hz.

## Files relevant to this application

For each participant:

- `meta_data.json` maps anatomical positions such as `l_instep` and
  `r_instep` to physical sensor IDs and provides start/stop indices for each
  test;
- `imu/NilsPodX-<sensor-id>_<datetime>.bin` contains a continuous raw stream;
- `manual_stride_border.csv` contains manually annotated IMU stride borders in
  samples since session start;
- `mocap/<test>_steps.csv` contains reference `start`, `end`, `ic`, `tc`, and
  `min_vel` events;
- `mocap/<test>.c3d` and `.qtm` contain motion-capture data;
- `calibrations/<sensor-id>/` contains sensor calibration data.

The application must resolve instep sensor IDs through each participant's
metadata. Sensor IDs must not be hard-coded because different participants used
different physical devices.

## Loading constraints

Raw `.bin` files must not be interpreted as ready-to-use gaitmap input. Loading
must apply the upstream synchronization, calibration, test slicing, unit
conversion, and coordinate transformations. The upstream README explicitly
recommends using its loader rather than reading binaries directly.

The next implementation step must evaluate the maintained `gaitmap-datasets`
loader first. The older `sensor_position_dataset_helper` remains useful for
reproducing the publication but its own repository marks it as deprecated.

## Available trials

The dataset does include short trials; upstream names them by walking speed and
nominal path length instead of using the word `short`:

```text
slow_10    normal_10    fast_10
slow_20    normal_20    fast_20
long
```

The `10` trials are repeated 4 x 10 m walks, the `20` trials are repeated
2 x 20 m walks, and `long` is approximately five minutes. Each trial has its
own motion-capture `.c3d`/`.qtm` files and `<trial>_steps.csv` reference events.
