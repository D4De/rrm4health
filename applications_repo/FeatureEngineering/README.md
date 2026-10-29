# FeatureEngineering

**Status: AI-assisted framework integration, with a positive functional
validation outcome confirmed by the project maintainer.**

This application acquires RAW IMU samples over Wi-Fi, extracts a 66-value feature
vector from each window and appends the results to CSV files. It integrates the
feature-engineering stage of the source project, not its complete activity
classification and model-training workflow.

## Application source

Original upstream repository:
[Rbarik25/IMU-Activity-Recognition](https://github.com/Rbarik25/IMU-Activity-Recognition/tree/main).

The original project, **IMU-Based Human Activity Recognition using Nicla Vision**,
includes data collection, exploratory analysis, feature extraction, model
training and real-time prediction. The local RRM integration is based on the
feature-extraction logic in `notebooks/02_feature_engineering.ipynb`.

In the source workflow, that notebook processes previously recorded IMU data.
The integrated version replaces file-based input with live Wi-Fi RAW acquisition,
while retaining the feature calculations and ordering. The original Nicla/UDP
acquisition and decision-tree prediction scripts are not the runtime entry
points of this framework application.

## AI-assisted integration

The application was integrated into RRM4Health with AI assistance, using the
descriptor, generated task skeleton, original notebook code and framework
examples/managers. The work included review and corrections.


The implementation is [FeatureEngineering.py](FeatureEngineering.py), with
acquisition support in [WifiAcquisitionMngr.py](../../utilities_library/WifiAcquisitionMngr.py). The task
structure is defined in the
[application descriptor](FeatureEngineering.json):

| Task | Role |
| --- | --- |
| `setup_and_collect` | Acquire six-axis RAW samples from one Wi-Fi IMU and build overlapping windows. |
| `FeatureEngineering` | Calculate the feature vector and append it to the activity-specific CSV file. |

Setup, loop and cleanup methods follow the framework lifecycle. Acquisition
resources belong to the collection task; CSV resources belong to the
feature-extraction task, so the tasks can run in separate partitions.

## Validation status

**Functional validation completed with a positive outcome**, as confirmed by
the project maintainer and recorded in the integration experience report.
This status refers to the integrated feature-extraction application, not only
to successful code generation or syntax checks.

It does not imply that the original project's entire training/classification
pipeline was integrated or that classification accuracy was measured by this
application. No numerical accuracy claim or exhaustive hardware compatibility
matrix is provided here. Repeat the relevant checks after changing firmware,
feature definitions, hardware or dependencies.


## Windowing and feature vector

The implementation uses six channels in this order:
`ax`, `ay`, `az`, `gx`, `gy`, `gz`.

- Window size: **20 samples**.
- Step size: **10 samples**, giving 50% overlap.
- The first six values are the last sample of each channel.
- Each channel then contributes ten statistics: mean, minimum, maximum,
  standard deviation, variance, RMS, peak-to-peak, median, mean absolute
  deviation and signal energy.
- Total: **6 + (6 × 10) = 66 values per window**.

These are application-side features calculated from RAW samples, not the
28-feature packets produced by the firmware's FEATURES mode. The integrated
application explicitly configures the acquisition manager with `raw=True`.

## CSV output

Results are written relative to the application installation:

```text
data/featured/<activity>_features.csv
```

The `activity` parameter selects the output filename. The CSV contains the
66 feature columns; the activity label is not added as a separate column by
the current implementation. The directory is created when needed.

The application appends rows rather than overwriting previous acquisitions.
It writes a header for a new/empty file and checks an existing file's header
before appending. Each row is flushed to disk, and cleanup closes the file.
Dataset, plotting and training files from the original project are not required
for this live extraction path.

## Files, parameters and deployment


Keep the main Python implementation, `utilities_library/WifiAcquisitionMngr.py`,
[requirements.txt](requirements.txt), [LICENSE](LICENSE) and the descriptor.
Example GUI parameter sets are available in [gui_config/](gui_config/).

The descriptor exposes `imuname`, `campaignname`, `samplingfreq`, `activity`,
`wifi_interface`, `wifi_ssid` and `wifi_password`. In this application,
`imuname` is the IMU's IP or MAC address, used both as the manager key and the
connection address. Replace example network credentials and sensor addresses
with the settings of the actual acquisition environment.

The source and descriptor are maintained together. This application is not
installed in the framework in this checkout. See the
[application repository guide](../README.md) for deployment.

