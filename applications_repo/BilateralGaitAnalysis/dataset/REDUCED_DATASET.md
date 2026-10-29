# Reduced SensorPositionComparison2019 dataset

This application includes a reduced copy of
`SensorPositionComparison2019-v1.0.0-beta` containing participants `4d91`,
`5237`, `cb3d`, and `8873`.

For each participant, the complete synchronized NilsPod IMU session and
`meta_data.json` are retained. The complete calibration directory is also kept.
Motion-capture files, manual stride labels, Qualisys project data, setup images,
development scripts, packaging files, and all other participants were removed
because `BilateralGaitAnalysis` does not access them.

The original dataset can be downloaded again from:
https://zenodo.org/records/5747173
