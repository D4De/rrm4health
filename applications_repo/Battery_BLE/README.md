# Battery_BLE

Reads battery levels from BLE IMUs, sends a framework GUI notification and
requests its own stop. Acquisition uses the shared `BleAcquisitionMngr`.

## Descriptor and configuration

See the [application descriptor](Battery_BLE.json) for tasks, deployment
configurations and parameters. `imunames` contains BLE device names separated
by `-`; `adapter` selects the Bluetooth adapter, usually `hci0` or `hci1`.

## Installation

This application currently has an installed runtime copy. Source code and the
descriptor are maintained together here; installation copies are synchronized
explicitly. See the [application repository guide](../README.md).
