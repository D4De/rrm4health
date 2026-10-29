# Collector_WIFI

Collects IMU packets through the shared `WifiAcquisitionMngr` and publishes
serialized rows through `MqttTransmissionMngr`. Prefer Wi-Fi for high
transmission frequencies; BLE can be used for lower transmission rates.

## Descriptor and configuration

See the [application descriptor](Collector_WIFI.json) for tasks, deployment
configurations and parameters. Configure the actual IMU addresses, Wi-Fi
interface/network, campaign, acquisition settings and MQTT destination before
starting collection.

## Installation

This application currently has an installed runtime copy. Source code and the
descriptor are maintained together here; installation copies are synchronized
explicitly. See the [application repository guide](../README.md).
