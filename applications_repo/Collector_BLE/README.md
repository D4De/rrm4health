# Collector_BLE

Collects IMU packets through the shared `BleAcquisitionMngr` and publishes
serialized rows through `MqttTransmissionMngr`.

## Descriptor and configuration

See the [application descriptor](Collector_BLE.json) for tasks, deployment
configurations and parameters. Configure the actual IMU IDs, Bluetooth adapter,
campaign, acquisition settings and MQTT destination before starting collection.

## Installation

This application currently has an installed runtime copy. Source code and the
descriptor are maintained together here; installation copies are synchronized
explicitly. See the [application repository guide](../README.md).
