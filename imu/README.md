# IMU firmware

Firmware and supporting sensor libraries for the IMU boards used by the
framework. This directory contains device-side code; Python acquisition and
transmission managers live in [utilities_library](../utilities_library/README.md).

## Directory structure

```text
imu/
├── README.md
├── esp32C3/
│   └── esp32C3.ino                  # ESP32-C3 + MPU6050, Wi-Fi/TCP
├── nano33/
│   ├── nano33BLE.ino               # Nano 33 BLE / Sense, BLE
│   ├── Arduino_LSM9DS1_AAAC.h
│   ├── LSM9DS1_AAAC.h
│   ├── LSM9DS1_AAAC.cpp
│   └── arduino_secrets.h
├── nano33rev2/
│   ├── nano33rev2.ino            # Nano 33 BLE Sense Rev2, BLE
│   ├── Arduino_BMI270_BMM150_AAAC.h  # Sensor library and bundled drivers
│   ├── BMI270_AAAC.cpp               
│   ├── BoschSensorClass_AAAC.h   
│   ├── library.properties          
│   ├── src          
│   │   └── utilities              
│   │        └── BMI270-Sensor-API/
│   │        └── BMM150-Sensor-API/
│   └── utilities              
│        └── BMI270-Sensor-API/
│        └── BMM150-Sensor-API/
├── nano33IoT/
│   ├── nano33IoT.ino               # Nano 33 IoT, BLE and Wi-Fi code
│   └── Arduino_LSM6DS3/            # Bundled sensor library
└── nRF52840/
    └── IMU_nRF52840/
        ├── README.md              # Nordic project build/programming guide
        ├── IMU_nrf/               # Native firmware, SDK and build projects
        ├── ble2mqtt/              # Companion BLE-to-MQTT code
        ├── docs/
        └── resources/
```

These are board-specific implementations, not interchangeable copies. Match
the firmware to the actual board and sensor, and check its protocol and packet
layout before selecting a Python manager. Do not assume identical capabilities
or sampling limits across all boards.

## Arduino firmware

Use the Arduino IDE with the board support package matching your hardware.
Install the libraries required by the selected sketch's `#include` directives;

- `nano33/`: uses the local LSM9DS1 AAAC sources, `ArduinoBLE` and `TimeLib`.
- `nano33rev2/`: uses the bundled BMI270/BMM150 AAAC library, `ArduinoBLE` and
  `TimeLib`.
- `nano33IoT/`: uses the bundled LSM6DS3 library, `ArduinoBLE`, `TimeLib`,
  `WiFiNINA` and `ArduinoMDNS`, along with board-provided SPI/UDP support.
- `esp32C3/`: uses Arduino, Wire and Wi-Fi headers supplied by the ESP32 board
  package, with MPU6050 access implemented in the sketch.

Make the bundled sensor libraries available to the IDE as Arduino libraries;
preserve their source and directory structure. Arduino may request a sketch
folder matching the `.ino` filename: if necessary, prepare a working copy with
that layout and retain the sketch's companion files.


### ESP32-C3 Mini standalone operation

For the ESP32-C3 Mini IMUs used in this project, set the following **before
compiling and uploading**:

```text
Tools -> USB CDC On Boot -> Disabled
```

With USB CDC enabled, these boards may work only while the IDE or Serial
Monitor is open. After uploading with USB CDC disabled, test standalone power
operation without the Serial Monitor. The sketch's I2C pins and MPU6050 address
must also match the physical wiring.

## WiFi Configuration – SPECIFICANOMI BOARD
Before flashing Arduino boards equipped with WiFi connectivity, the corresponding Arduino projects must be configured with the required network credentials (SSID and password).

- board nano33IoT: open file nano33IoT.ino and modify lines 201 and 202

- board esp32C3: open file esp32C3.ino and modify lines 81 and 82


## Native nRF52840 project

`nRF52840/IMU_nRF52840/IMU_nrf/` is a Nordic SDK project, not an Arduino sketch.
It contains custom firmware in `src/`, SDK configuration in `config/`, bundled
SDK components and a GCC build directory. Follow its
[dedicated manual](nRF52840/IMU_nRF52840/README.md) for the SEGGER Embedded Studio
project, build steps, include paths and SDK configuration.

## RAW, FEATURES and host integration

For firmware implementing both modes, RAW transmits individual samples for
host-side processing; FEATURES computes a sliding-window feature vector on the
IMU and transmits the resulting values. Keep feature count, order, units and
packet layout synchronized with the Python acquisition manager.

For high transmission frequencies, prefer `WifiAcquisitionMngr`; for low
transmission frequencies, `BleAcquisitionMngr` can be used, provided the selected
board and firmware support that transport.

See [AddingImuFeatures.md](../utilities_library/AddingImuFeatures.md) for the
feature pipeline, packet formats and hardware-specific notes, and the
[application development guide](../applications_repo/ApplicationDevelopment.md)
for integrating acquisition into an application.


