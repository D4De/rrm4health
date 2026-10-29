# ActivityRecognitionCNN

**Status: AI-assisted framework integration, not functionally validated.**
The real-model validation could not be completed because of compatibility
problems between the serialized Keras model, the installed libraries and the
Python version used during testing. This application must not be presented as
a validated activity-recognition implementation.

## Application source

The application is based on **Real-Time IMU Human Activity Recognition (HAR)
Server**, a Python/Flask application that receives six-axis IMU samples through
HTTP, normalizes windows of 100 samples and classifies activities with a 1D CNN.

Original upstream repository:
[Ganamoorthy/imu-activity-server](https://github.com/Ganamoorthy/imu-activity-server).

The supplied original material is preserved locally:

- [imu_server.py](imu_server.py): the original Flask server used as the basis
  for the integration.
- [README originalApp.md](<README originalApp.md>): the original application's
  documentation, including its HTTP endpoints and standalone workflow.
- `imu_activity_cnn.keras`, `imu_mean.npy`, `imu_std.npy` and
  `activity_names.json`: the supplied model, normalization statistics and labels.

The upstream repository above is the source identified by the project maintainer.
The local files preserve the material used for integration. The placeholder
clone URL in the original README is superseded by this source attribution.

## AI-assisted integration into RRM4Health

The integration was carried out with AI assistance.
The process used the application descriptor, a generated class skeleton, the
original script and framework examples/managers as inputs, followed by review
and corrections.

The framework-facing implementation is
[ActivityRecognitionCNN.py](ActivityRecognitionCNN.py). It replaces the original
HTTP acquisition path with the project's Wi-Fi RAW manager and separates the
application into two tasks:

| Task | Role |
| --- | --- |
| `setup_and_collect` | Acquire accelerometer/gyroscope samples from one Wi-Fi IMU and assemble a 100-sample window. |
| `CNNInference` | Load the model and normalization assets, normalize the window, run inference and print the predicted activity and confidence. |

Setup, loop and cleanup methods follow the framework lifecycle. The descriptor
is available in the [application descriptor](ActivityRecognitionCNN.json).
Running `imu_server.py` starts the original standalone application; it is not
the startup procedure for the integrated framework version.

## Why functional validation was not completed

The integration report records the following environment for the unsuccessful
validation attempt:

| Component | Version recorded during testing |
| --- | --- |
| Python in the framework application environment | 3.10 |
| TensorFlow | 2.21.0 |
| Keras in that environment | 3.12.4 |
| Keras used to save the supplied model | 3.13.2 |

The supplied `.keras` archive independently records `keras_version: 3.13.2`
in its `metadata.json`. Model loading failed during deserialization with:

```text
ValueError: Unrecognized keyword arguments passed to Dense:
{'quantization_config': None}
```

The report attributes this failure to the difference between the Keras model
serialization version and the installed runtime. Attempts to install the
required library version were also constrained by the Python version used in
the application environment. Consequently, inference with the real model and
end-to-end functional validation were not completed.

These versions describe the recorded attempt, not a general compatibility
matrix or a working installation recipe. The current `.python-version` and
`requirements.txt` may differ from that environment; changing a version pin
alone does not establish that the application works.

Static checks and tests with simulated components were reported as passed,
but they do not validate model loading, real inference, recognition accuracy
or equivalence with the original application. AI-assisted integration and
functional validation are separate milestones.

## Files required by the integrated application


```python
from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr
```


Keep the following files when preparing a future validation environment:

- `ActivityRecognitionCNN.py` and `utilities_library/WifiAcquisitionMngr.py`.
- `requirements.txt` and the application descriptor.
- `imu_activity_cnn.keras`.
- `imu_mean.npy` and `imu_std.npy`.
- `activity_names.json`.

The assets must be available on the node executing `CNNInference`. GUI presets
in `gui_config/` provide example parameters, not evidence of successful
validation.

The source and [application descriptor](ActivityRecognitionCNN.json) are
maintained together. The application is not installed in the framework in this
checkout. See the [application repository guide](../README.md) for deployment;
installing it does not change the functional-validation status described above.

Before treating this application as operational, establish a compatible
Python/TensorFlow/Keras environment, verify loading of the unmodified model,
compare inference with the original implementation on known inputs, and then
validate acquisition and execution through the framework. Until those checks
are completed, its status remains **not functionally validated**.
