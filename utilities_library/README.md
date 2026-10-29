# Shared acquisition and transmission managers


## Managers

| Module | Class | Purpose |
| --- | --- | --- |
| [BleAcquisitionMngr.py](BleAcquisitionMngr.py) | `BleAcquisitionMngr` | BLE acquisition in RAW or FEATURES mode. |
| [WifiAcquisitionMngr.py](WifiAcquisitionMngr.py) | `WifiAcquisitionMngr` | Wi-Fi acquisition in RAW or FEATURES mode. |
| [FileAcquisitionMngr.py](FileAcquisitionMngr.py) | `FileAcquisitionMngr` | Replay files at the configured frequency without physical IMUs. |
| [MqttTransmissionMngr.py](MqttTransmissionMngr.py) | `MqttTransmissionMngr` | Publish already serialized rows through MQTT. |

Import the managers from the shared package:

```python
from utilities_library.BleAcquisitionMngr import BleAcquisitionMngr
from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr
from utilities_library.FileAcquisitionMngr import FileAcquisitionMngr
from utilities_library.MqttTransmissionMngr import MqttTransmissionMngr
```

Deploy `utilities_library/` alongside `framework/` on each execution node.


## Acquisition setup

```python
# Prefer Wi-Fi for high transmission frequencies; BLE can be used at low rates.
ble = BleAcquisitionMngr()
ble.set_imus(["IMU_A", "IMU_B"])
ble.set_id_imus(["thorax", "abdomen"])
ble.set_adapter("hci0")

wifi = WifiAcquisitionMngr()
wifi.set_imus({"IMU_A": "192.168.1.10", "IMU_B": "192.168.1.11"})
wifi.set_id_imus(["thorax", "abdomen"])
wifi.set_access_point("wlan0", "your_ssid", "your_password")

manager = wifi  # Start only the selected transport.
# RAW: individual samples; build processing windows in the application.
manager.set_campaign("demo", 10, raw=True)
# FEATURES alternative: firmware calculates one summary packet per window.
# manager.set_campaign("demo", 10, raw=False, window_size=300, step_size=100)
manager.start_collection()
try:
    manager.wait_connection()
    packet = manager.get_packet(block=True, timeout=0.1)
    if packet is not None and "battery" not in packet:
        print(packet)
finally:
    manager.stop_collection()
```

Split setup, reads and shutdown between the owning task's setup, loop and
cleanup methods in framework applications. Keep waits bounded and compatible
with STOP handling. Battery packets are not measurement windows; check their
presence before accessing measurement fields such as `ts`.

FEATURES uses fewer transmissions than RAW: at 10 Hz, a 300-sample window
first completes after about 30 seconds, followed by a new packet every 10 seconds
with a 100-sample step. Choose transport according to transmission load, not just
the firmware sampling rate.

## Replay from files

```python
manager = FileAcquisitionMngr(input_dir="input", loop_files=True)
manager.set_imus(["IMU_A", "IMU_B"])
manager.set_id_imus(["thorax", "abdomen"])
manager.set_campaign("demo", 10, raw=True)
```

Use the same collection lifecycle as the real managers. Files are named after
custom IDs, for example `thorax.jsonl` and `abdomen.jsonl`. Supported suffixes
are no extension, `.jsonl`, `.json`, `.csv` and `.txt`; see the implementation
for parsing details. If `input_dir` is omitted, the default is `input/` beside
`FileAcquisitionMngr.py` (create it and supply your recordings).

The manager paces records at the specified frequency; it does not calculate
firmware features from RAW input. To replay FEATURES, provide feature records.
`loop_files=False`, the default, stops replaying a device at EOF. Use receive
timeouts so an exhausted file cannot block an application indefinitely.

## MQTT publication

```python
publisher = MqttTransmissionMngr()
publisher.set_db_mqtt("localhost", 1883, "demo/results")
publisher.start_db_mqtt()
try:
    publisher.put_row("campaign=demo,imuid=thorax,mean=1.25")
finally:
    publisher.stop_db_mqtt()
```

`put_row` queues a serialized string; it does not convert a dictionary to CSV.
Use separate `MqttTransmissionMngr` instances for acquired data and processing
results when both streams are required. In a distributed graph, initialize each
publisher in the task that owns it, rather than sharing an instance across
partitions. MQTT transports the data; the downstream ingestion service determines
which database receives it.

## Examples and further documentation

From the repository root:

```bash
python utilities_library/TestWifiAcquisitionMngr.py --help
```


- [ExampleAllMngr.py](ExampleAllMngr.py): task-based acquisition, processing and
  separate MQTT publication of samples and results.
- [TestBleAcquisitionMngr.py](TestBleAcquisitionMngr.py): BLE acquisition example without framework integration.
- [TestWifiAcquisitionMngr.py](TestWifiAcquisitionMngr.py): Wi-Fi acquisition test without framework integration.
- [Application development tutorial](../applications_repo/ApplicationDevelopment.md): descriptors, generated
  methods, task lifecycle and user notifications.
- [Firmware feature guide](AddingImuFeatures.md): feature ordering,
  packet formats and hardware notes.
