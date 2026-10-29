# BreathAnalysis

Online respiratory-analysis pipeline using three BLE IMUs assigned to `thorax`,
`abdomen` and `reference`. Acquisition uses `BleAcquisitionMngr`; acquired
samples are published with `MqttTransmissionMngr` and the processing tasks
produce the respiratory-analysis results.

## Descriptor and configuration

See the [application descriptor](BreathAnalysis.json) for the task graph,
deployment configurations and parameters. Device IDs in `imunames` and roles in
`peripheral_locations` use `-` as a separator and must be in the same order.
The processing pipeline uses 10 Hz, 300-sample windows and a 100-sample step.
RAW acquisition and the acquisition topic `aaac/campaign/imu` are fixed in code.

`host_DB` and `port_DB` identify the MQTT broker, not the InfluxDB HTTP endpoint.
Use the [demo tutorial](../../HowToStart.md) for WebApp configuration and startup.

## Installation

This application currently has an installed runtime copy. Source code and the
descriptor are maintained together here; installation copies are synchronized
explicitly. See the [application repository guide](../README.md).
