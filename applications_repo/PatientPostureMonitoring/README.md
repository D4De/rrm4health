# Patient Posture Monitoring

**Status: manually integrated into RRM4Health; adequate functional validation
and testing were not completed because the required cameras were unavailable.**

The local implementation replays Depth frames from the SDT dataset and is
designed to classify each frame as `LYING`, `SITTING`, `STANDING` or `EMPTY`.
Dataset replay is not a substitute for validating acquisition and classification
with real cameras. This application must not be presented as a fully tested
camera-based patient-monitoring system.

## Sources and inspiration

The application was developed by taking inspiration from several applications
and examples found online, rather than porting a single upstream application.
The framework-facing code combines those ideas into a local Depth-processing
pipeline with explicit setup, loop and cleanup methods.

The sources retained in the project are documented in
[REFERENCES.md](REFERENCES.md), including:

- The SDT dataset and its documentation, used for the recorded Depth frames,
  dataset layout and class labels.
- The medical pose-recognition literature listed there, used as methodological
  inspiration rather than as a complete implementation copied into this project.
- MobileNetV2, TensorFlow Lite and image-processing documentation used to design
  preprocessing and inference on edge hardware.

 The implementation should therefore be attributed as a local
adaptation inspired by multiple sources, not as a validated reproduction of
one particular online application. The current version is Depth-only; it does
not implement the complete multimodal Depth/Thermal system discussed in the
methodological references.

## Manual integration

The application was integrated manually, not through the AI-assisted integration
workflow used for some other applications in this repository.

The implementation is
[PatientPostureMonitoring.py](PatientPostureMonitoring.py), with the following
task structure:

| Task | Role |
| --- | --- |
| `acquire_depth_frame` | Read a recorded Depth frame and reference label from the SDT test split. |
| `preprocess_depth_frame` | Normalize Depth values, resize to 64×64 and prepare three-channel model input. |
| `classify_posture` | Run the selected TFLite model and assemble the classification result. |
| `publish_posture_result` | Write the posture result and optional inference/timing information to CSV. |

Reusable components are kept in [Util/sdt_frame_source.py](Util/sdt_frame_source.py),
[Util/depth_preprocessing.py](Util/depth_preprocessing.py) and
[Util/tflite_classifier.py](Util/tflite_classifier.py).

## Validation status and limitations

**The application was not adequately tested or functionally validated.**
The required cameras were not available during development, preventing proper
testing of the intended real-camera acquisition and monitoring scenario.

The recorded SDT frames provide a virtual-camera input for development, but
cannot establish compatibility with an actual camera, its Depth format,
calibration, placement or acquisition timing. The current acquisition component
is a dataset replay source, not a demonstrated live-camera driver.

The presence of TFLite models, example GUI configurations and
[dataset-source tests](test_sdt_frame_source.py) does not establish completed
end-to-end validation. No recognition-accuracy claim or real-camera reliability
claim is made here. This documentation update does not constitute a new test run.

Before treating the application as operational, provide the intended cameras,
implement or verify their acquisition adapter, check the preprocessing/model
input contract, and test the complete pipeline in the intended environment.

## Inference modes

- `heavy_mode=false`: dynamically optimized TFLite model;
- `heavy_mode=true`: unquantized Float32 TFLite model.

Both modes require inputs produced by the same 64×64 Depth preprocessing.
These are implementation options, not independently validated camera setups.

## Dependencies

```bash
python3 -m pip install -r applications_repo/PatientPostureMonitoring/requirements.txt
```

Run this command from the repository root for manual dependency preparation.
The implementation uses the lightweight `tflite-runtime`; full TensorFlow is
not required when that runtime is available. The TensorFlow import in the
classifier is retained as a fallback for development environments where
TensorFlow is already installed. 

## Descriptor parameters

For a detailed explanation of every parameter and its intended performance
and accuracy impact, see [PARAMETERS.md](PARAMETERS.md).

- `dataset_path`: root of the extracted SDT dataset containing `test/`;
- `heavy_mode`: selects the dynamic or Float32 model;
- `num_threads`: number of CPU threads assigned to the TFLite interpreter;
- `target_fps`: virtual-camera replay rate; zero disables pacing;
- `loop_dataset`: restarts from frame zero after the final test frame;
- `output_path`: directory for per-frame CSV results.

Treat configuration guidance as development information, not as measured
real-camera performance guarantees.

## Repository location and deployment

The source and [application descriptor](PatientPostureMonitoring.json) are
maintained together. The application is not installed in the framework in this
checkout. See the [application repository guide](../README.md) for deployment.

