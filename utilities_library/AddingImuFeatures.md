# Adding New IMU Features

This document explains how to extend the on-device preprocessing pipeline by adding, removing, or modifying features computed from IMU data.

The current preprocessing mode is selected with:

```text
raw = true   -> RAW acquisition
raw = false  -> FEATURES acquisition
```

In FEATURES mode, the firmware samples the IMU locally, stores samples in a sliding window, computes a feature vector, and sends only the resulting features instead of transmitting every raw sample.

The current feature set contains 28 features based on accelerometer and gyroscope data.

---

## 1. Current preprocessing pipeline

The generic processing flow is:

```text
IMU samples
   |
   v
Unit conversion
   |
   v
Optional filtering
   |
   v
Sliding window
   |
   v
Feature extraction
   |
   v
Feature packet
   |
   +--> BLE
   |
   +--> Wi-Fi
```

The window behavior is controlled by:

- `sampling_frequency`
- `window_size`
- `step_size`

For example:

```text
sampling_frequency = 100 Hz
window_size        = 300 samples
step_size          = 100 samples
```

means:

- the first feature vector is generated after approximately 3 seconds;
- the window contains 300 samples;
- 200 samples are retained after each feature extraction;
- 100 new samples are collected before computing the next feature vector;
- a new feature vector is therefore generated approximately every 1 second.

---

## 2. Current feature vector

The current feature order is:

```text
 0  acc_mag_max
 1  acc_mag_mean
 2  acc_mag_std

 3  gyro_mag_max
 4  gyro_mag_mean
 5  gyro_mag_std

 6  ax_mean
 7  ax_max
 8  ax_std

 9  ay_mean
10  ay_max
11  ay_std

12  az_mean
13  az_max
14  az_std

15  gx_mean
16  gx_max
17  gx_std

18  gy_mean
19  gy_max
20  gy_std

21  gz_mean
22  gz_max
23  gz_std

24  tilt
25  dynamic_sma
26  jerk_max
27  jerk_mean
```

The order is important because the firmware and the Python managers must use exactly the same ordering.

---

# 3. Adding a new feature in the firmware

The main function to modify in the firmware is:

```cpp
extractFeatureVector(float* outFeatures)
```

This function contains the calculations performed on the current sliding window.

Each feature is written into the output array using an index:

```cpp
outFeatures[0] = ...;
outFeatures[1] = ...;
...
outFeatures[27] = ...;
```

## Example: adding RMS acceleration magnitude

Suppose a new application requires:

```text
acc_mag_rms
```

First, increase the number of features.

Find:

```cpp
#define FEATURE_COUNT 28
```

and change it to:

```cpp
#define FEATURE_COUNT 29
```

Then compute the new feature inside:

```cpp
extractFeatureVector()
```

For example:

```cpp
double accMagSquaredSum = 0.0;

for (uint16_t i = 0; i < n; i++) {
    float ax = featureAxBuffer[i];
    float ay = featureAyBuffer[i];
    float az = featureAzBuffer[i];

    float accMag = sqrtf(
        ax * ax +
        ay * ay +
        az * az
    );

    accMagSquaredSum += accMag * accMag;
}
```

Then append the feature at the end of the vector:

```cpp
outFeatures[28] =
    sqrtf((float)(accMagSquaredSum / n));
```

Do not reuse an existing index unless the corresponding feature is intentionally being replaced.

---

# 4. Keep feature ordering consistent

The feature index used in the Arduino firmware must match the index used in the Python manager.

For example:

```text
Arduino firmware               Python manager

outFeatures[0]   <---------->  FEATURE_NAMES[0]
outFeatures[1]   <---------->  FEATURE_NAMES[1]
...
outFeatures[27]  <---------->  FEATURE_NAMES[27]
outFeatures[28]  <---------->  FEATURE_NAMES[28]
```

If the new Arduino feature is:

```cpp
outFeatures[28] = accMagRms;
```

the corresponding Python name must be appended as:

```python
"acc_mag_rms",
```

---

# 5. Updating the BLE manager

Open the BLE manager:

```text
utilities_library/BleAcquisitionMngr.py
```

or the corresponding current BLE manager used by the project.

Find:

```python
FEATURE_NAMES = [
    ...
]
```

Add the new feature name in exactly the same position used by the Arduino firmware.

Example:

```python
FEATURE_NAMES = [
    ...
    "jerk_mean",
    "acc_mag_rms",
]
```

The following values are automatically derived from `FEATURE_NAMES`:

```python
FEATURE_COUNT = len(FEATURE_NAMES)
FEATURE_PACKET_LENGTH = FEATURE_COUNT * 4 + 2 + 4
FEATURE_PACKET_FORMAT = "<" + ("f" * FEATURE_COUNT) + "HI"
```

Therefore, these values should not normally be edited manually.

---

# 6. Updating the Wi-Fi manager

Open:

```text
utilities_library/WifiAcquisitionMngr.py
```

Find the same section:

```python
FEATURE_NAMES = [
    ...
]
```

Add or remove feature names so that this list matches the Arduino `outFeatures[]` ordering exactly.

Example:

```python
FEATURE_NAMES = [
    ...
    "jerk_mean",
    "acc_mag_rms",
]
```

As in the BLE manager, the packet size and binary format are derived automatically from the list.

---

# 7. Adding a feature that uses existing ACC/GYRO data

If the new feature uses only:

```text
Ax Ay Az
Gx Gy Gz
```

the required changes are normally limited to:

1. update `FEATURE_COUNT` in the firmware;
2. modify `extractFeatureVector()`;
3. append or insert the corresponding `outFeatures[index]`;
4. update `FEATURE_NAMES` in the BLE manager;
5. update `FEATURE_NAMES` in the Wi-Fi manager.

No acquisition or buffering changes are required.

Examples include:

```text
RMS
range
median
energy
zero-crossing metrics
correlation between axes
skewness
kurtosis
frequency-domain features
```

---

# 8. Adding a feature that requires another sensor

If a new feature requires data that is not currently stored in the preprocessing window, additional changes are required.

For example, a magnetometer-based feature may require:

```text
Mx
My
Mz
```

In that case, the firmware must also be extended in the following areas.

## 8.1 Add buffers

For example:

```cpp
float* featureMxBuffer = NULL;
float* featureMyBuffer = NULL;
float* featureMzBuffer = NULL;
```

## 8.2 Allocate the buffers

Extend:

```cpp
allocateFeatureBuffers()
```

to allocate memory for the new signals.

## 8.3 Free the buffers

Extend:

```cpp
freeFeatureBuffers()
```

to release the additional memory.

## 8.4 Shift the buffers

Extend:

```cpp
shiftFeatureWindow()
```

so that the new sensor signals use the same sliding-window behavior.

## 8.5 Acquire the sensor data

Extend:

```cpp
sampleFeaturesMode()
```

to read the additional sensor.

## 8.6 Compute the feature

Finally, use the new buffer contents inside:

```cpp
extractFeatureVector()
```

and append the new output to:

```cpp
outFeatures[]
```

---

# 9. Hardware-specific notes

## ESP32-C3 Mini

The ESP32-C3 Mini boards used by the new IMU group have a USB-serial
configuration requirement that is easy to miss:

> **Disable USB CDC before uploading the firmware.**

In the Arduino IDE, select:

```text
Tools -> USB CDC On Boot -> Disabled
```

If USB CDC is left enabled, the IMU may work only while the Arduino IDE or the
Serial Monitor is open; it may fail to start or communicate correctly when the
board is powered without the IDE. After disabling USB CDC and uploading the
firmware again, the ESP32-C3 Mini can run standalone, without the Serial
Monitor open.

This board/firmware setting is independent of the selected acquisition mode
(`raw` or `features`) and communication transport (BLE or Wi-Fi).

### Adding a feature on the ESP32-C3 firmware

When adding a feature to the ESP32-C3 Wi-Fi firmware, keep the firmware and
the Python manager synchronized:

1. Update `FEATURE_COUNT` in `esp32_IMU.ino`.
2. Compute the new value in `computeFeatures()` and append it to `outFeatures[]`.
3. Keep the index and order documented in `FEATURE_NAMES` in
   `utilities_library/WifiAcquisitionMngr.py` exactly the same as the order in `outFeatures[]`.
4. Update the packet-size calculation/format if the packet structure is not
   generated automatically from `FEATURE_COUNT`.
5. Recompile and upload the firmware with **USB CDC On Boot disabled**.

The feature vector is transmitted as 32-bit floating-point values. Therefore,
adding one feature increases the FEATURES payload by 4 bytes. Check the
resulting packet size against the Wi-Fi receiver and update any size assertions
or decoding formats on both sides. Do not change the order of existing
features: saved datasets and models depend on stable feature indices.

The feature buffers are allocated using `window_size` for each accelerometer
and gyroscope axis. New features should normally reuse these buffers, rather
than adding a second copy of the complete sample window, to avoid unnecessary
RAM usage on the ESP32-C3. Validate the feature with both a small test window
and the production `window_size`/`step_size` configuration.

## Nano 33 BLE / LSM9DS1

The feature pipeline uses accelerometer and gyroscope values converted to physical units before feature extraction.

The raw acquisition path uses optimized multi-axis reads.

If magnetometer-based features are added, the LSM9DS1 magnetometer can also be included in the preprocessing buffers.

---

## Nano 33 BLE Sense Rev2 / BMI270 + BMM150

The BMI270 accelerometer and gyroscope are sampled together using the optimized:

```cpp
readAccelGyro(...)
```

method.

The current 28-feature set does not use BMM150 magnetometer data, so the magnetometer is not sampled in FEATURES mode.

If magnetometer-based features are required, extend `sampleFeaturesMode()` and the feature buffers as described above.

---

## LSM6DS3 Wi-Fi platform

The LSM6DS3 provides accelerometer and gyroscope data.

The optimized implementation uses:

```cpp
readAccelGyro(...)
```

to obtain ACC and GYRO data with one combined register transaction.

This hardware configuration does not provide a magnetometer, so magnetometer-based features require an additional external sensor.

---

# 10. Feature packet layout

The current FEATURES packet contains:

```text
FEATURE_COUNT x float32
uint16 counter
uint32 timestamp
```

For 28 features:

```text
28 x 4 bytes = 112 bytes
counter      =   2 bytes
timestamp    =   4 bytes
------------------------
total        = 118 bytes
```

If `FEATURE_COUNT` changes, the packet size changes as well.

The Python managers automatically calculate the new expected packet size from `FEATURE_NAMES`.

---

# 11. BLE packet-size consideration

Increasing the number of features also increases the BLE notification payload.

Always verify that the resulting packet size is supported by the negotiated BLE MTU and by the BLE stack used on both sides.

If the feature vector becomes too large for a single BLE notification, the feature packet must be fragmented into multiple BLE notifications and reconstructed in the Python manager.

This limitation does not apply in the same way to the TCP-based Wi-Fi transport, although TCP framing must still use the correct packet length.

---

# 12. Feature units

The preprocessing pipeline operates on values converted to physical units.

Current units are:

```text
Accelerometer:
    g

Gyroscope:
    degrees/second

Tilt:
    degrees
```

Features derived from these values therefore inherit the corresponding units.

When adding new features, document their units whenever they are meaningful.

---

# 13. Recommended procedure for adding a feature

Use the following checklist.

```text
[ ] Decide which sensor signals are required.
[ ] Check whether those signals are already buffered.
[ ] Increase/decrease FEATURE_COUNT in the firmware.
[ ] Implement the computation in extractFeatureVector().
[ ] Add the result to outFeatures[].
[ ] Keep all outFeatures[] indices unique and ordered.
[ ] Update FEATURE_NAMES in the BLE manager.
[ ] Update FEATURE_NAMES in the Wi-Fi manager.
[ ] Check the resulting packet size.
[ ] Recompile the firmware.
[ ] Run RAW/FEATURES acquisition tests.
[ ] Verify counter continuity.
[ ] Verify the numerical values and units of the new feature.
```

---

# 14. Important rule

The firmware defines the actual feature computation.

The Python managers only define the names associated with each feature position.

Therefore:

```text
Firmware outFeatures[] order
            MUST MATCH
Python FEATURE_NAMES order
```

A mismatch will not necessarily generate an error: it may silently associate the wrong name with a feature value.

For this reason, always update both sides together whenever the feature vector changes.
