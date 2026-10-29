# Application repository

This is the source repository for the framework's applications. Every application
directory contains its implementation, requirements, supporting files and a
JSON descriptor with the same application name.

The runtime installation is separate: installed applications retain a duplicate
under `framework/applications/<App>/`, with their registered descriptors at
`framework/applications/<App>.json`, outside the individual application folders.
Unlike the source layout here, runtime discovery reads JSON files directly from
`framework/applications/`, not from its subdirectories.
Applications kept only here must not have descriptors
in that runtime registry, otherwise the user interfaces would offer applications
whose runtime implementation is not installed.

## Applications

We are currently working on integrating several applications from the literature into our framework. The applications are available in this folder and listed in the table below, which summarizes their current implementation and integration status. Specifically, the second column indicates whether our implementation of each application has been validated, while the last column indicates whether the application has been integrated into the framework and is therefore ready to use.
For further details on each application's provenance, integration approach, and validation limitations, please refer to its corresponding README file.

| Application | Validated | Available in the framework |
| --- | --- | --- |
| [Battery_BLE](Battery_BLE/README.md) | Yes | Yes |
| [BreathAnalysis](BreathAnalysis/README.md) | Yes | Yes |
| [Collector_BLE](Collector_BLE/README.md) | Yes | Yes |
| [Collector_WIFI](Collector_WIFI/README.md) | Yes | Yes |
| [ActivityRecognitionCNN](ActivityRecognitionCNN/README.md) | No | No |
| [BilateralGaitAnalysis](BilateralGaitAnalysis/README.md) | Yes | No |
| [FallDetection](FallDetection/README.md) | No | No |
| [FeatureEngineering](FeatureEngineering/README.md) | Yes| No |
| [PatientPostureMonitoring](PatientPostureMonitoring/README.md) | No | No |

## Develop and validate

Keep source changes and the descriptor together in the application directory.
The descriptor's `executable.path` remains relative to the framework installation,
so it can be copied into the runtime registry unchanged. Do not replace it with
an absolute development-machine path.

From the repository root, validate a descriptor before installation, for example
(the POSIX command below makes the framework's `core` package importable):

```bash
PYTHONPATH=framework python tools/CheckerJSON.py applications_repo/Battery_BLE/Battery_BLE.json
```

Check that the output reports `VALID`; structural validation does not establish
hardware availability or functional correctness.

Applications import shared managers from `utilities_library/`. Preserve the
application's algorithm modules, assets and requirements, and provide datasets
separately where necessary. Generated caches, logs and output are not source
files to synchronize.

## Install or update an application

On every execution node, after stopping any running instance of that application:

1. Copy the application's directory to `framework/applications/`, preserving its
   name and internal structure. Review existing local changes before updating a
   runtime copy; do not overwrite them blindly.
2. Copy its JSON descriptor directly to `framework/applications/`, outside the
   application's own directory (for example, `framework/applications/BreathAnalysis.json`).
   Only register it after
   the implementation and required assets are installed.
3. Restart RRM Local to prepare/check the application's dedicated environment.
4. Restart RRM Global and refresh the launch interface's application list so it
   reflects the installed descriptors.

The installed application and registered descriptor are deployment copies, not
symlinks. Editing the source repository does not update them automatically.
When updating, synchronize the code and descriptor as one reviewed change.

## Uninstall an application

Stop it first, remove its runtime descriptor and runtime application copy, then
restart the RRM components and refresh the interface. Retain the complete source
and descriptor here so the application can be installed again later.

See the [framework guide](../framework/README.md),
[development tutorial](ApplicationDevelopment.md) and
[shared manager guide](../utilities_library/README.md) for further details.
