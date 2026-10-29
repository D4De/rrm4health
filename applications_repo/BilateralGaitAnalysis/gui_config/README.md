# BilateralGaitAnalysis GUI configurations

The framework starts this application with `BilateralGaitAnalysis/` as its current
working directory. Therefore `input_path` and `output_path` are relative to the
application directory, for example `dataset/SensorPositionComparison2019-v1.0.0-beta`
and `output/4d91_normal_10_full/`.
File acquisition always uses the dataset's native 204.8 Hz sampling frequency.
For clarity, every dataset configuration therefore reports
`sampling_frequency_hz: "204.8"`, although the file reader obtains the effective
frequency from the dataset itself. The BLE configuration keeps the physical IMU
frequency of 100 Hz.

File acquisition always reproduces recording time: the first 20-second window is
emitted after 20 seconds and subsequent windows are emitted every
`window_duration_s - window_overlap_s` seconds. The acquisition task waits for a
complete window, so downstream tasks are not executed during that interval. BLE
acquisition follows the same rule using packets received from the physical IMUs.

In `ble_two_real_imus.json`, replace `imu_names` with the two real MAC addresses.
The order is mandatory: left-foot IMU first and right-foot IMU second. Also
choose suitable values for `subject_id`, `trial_id`, and `campaign_name`. The
`campaign_name` value becomes the common `cname` of packets from both IMUs.

The physical IMUs operate at fixed ranges of ±4 g and ±2000 °/s. These values are
not GUI parameters because the application cannot reconfigure the hardware.
