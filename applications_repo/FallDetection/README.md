# Fall Detection

**Status: integration and functional validation not completed.**
The work was discontinued because reconstructing and verifying the missing
parts of the source project would have required substantial additional time.
The files in this directory must not be presented as a completed or validated
fall-detection application.

## Application source

Original upstream repository:
[bturbil/fall-detection-system](https://github.com/bturbil/fall-detection-system/tree/main).

This repository was selected as the source for the attempted integration into
RRM4Health. According to the project maintainer's account of the evaluation,
the available upstream material did not provide everything needed to reproduce
the complete processing pipeline: a complete codebase together with all the
required ready-to-use models and processing thresholds.

This describes the material available during the integration attempt, not a
new audit of the current upstream repository. The local files preserve the work
performed so far; their presence does not demonstrate that the original system
has been fully reproduced.

## Integration approach: no AI assistance

**AI was not used for the application implementation or integration work.**
The adaptation was undertaken manually. It should not be grouped with the
AI-assisted integrations of other applications in this repository.

The intended framework pipeline receives on-device feature packets over Wi-Fi,
prepares a feature vector, distinguishes static from dynamic activity and
applies a classifier before persisting the result. Local code includes an
ESP32-C3/MPU6050 acquisition path with 28 features, a `dynamic_sma` threshold
and a model exposing the scikit-learn prediction interface.

These are elements of the partial implementation, not a claim that feature
definitions, model inputs, thresholds and original training conditions have
all been verified against the source project.

## Why the work was not completed

Completing the integration required more than connecting an acquisition manager
to the framework. The missing material would have required additional work to:

- Reconstruct the processing steps not fully supplied by the source project.
- Obtain or reproduce the required trained models and establish their exact
  feature ordering, units and preprocessing contract.
- Recover or determine the processing thresholds and verify their suitability.
- Complete the framework integration and validate the resulting pipeline.

The time needed for that reconstruction exceeded the time allocated to the
activity, so the work was left unfinished. **Neither the integration nor the
functional validation was completed.** No recognition-accuracy or fall-detection
reliability claim is made for this local implementation.

## Material currently preserved


| File or directory | Role |
| --- | --- |
| [FallDetection.py](FallDetection.py) | Framework-facing implementation retained from the unfinished integration. |
| [fall_detection_app.py](fall_detection_app.py) | Additional application code retained with the working material. |
| [WifiAcquisitionMngr.py](../../utilities_library/WifiAcquisitionMngr.py) | Shared Wi-Fi acquisition manager used directly by the application. |
| `mlp_dynamic_only_model.pkl` | Model artifact present locally; not evidence of a complete, validated reproduction of the upstream pipeline. |
| [requirements.txt](requirements.txt) | Dependencies declared for the local implementation. |
| [gui_config/](gui_config/) | Example acquisition and processing parameters, not validated operating recommendations. |
| [test_fall_detection.py](test_fall_detection.py) | Local tests; their presence does not establish completed end-to-end validation. |

The retained preset uses 200 Hz sampling with 300-sample windows and steps.
Treat these values and the stored threshold as working configuration values,
not as confirmed training-compatible or validated settings.

The source and [application descriptor](FallDetection.json) are maintained
together. The application is not installed in the framework in this checkout.
See the [application repository guide](../README.md) for deployment;

Before resuming the work, resolve the missing source/model/threshold information,
document the intended preprocessing contract, finish the integration and run
functional validation. Until then, the status remains **incomplete and not
functionally validated**.
