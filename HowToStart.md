# HowToStart — BreathAnalysis demo with the WebApp and RRM

This guide explains how to run a respiratory-analysis demo with the WebApp,
one RRM Global and one RRM Local on the same Ubuntu/Debian computer.
It assumes that you have already downloaded the `rrm4health` repository.
The WebApp is included in its `webapp/` directory. You need three BLE IMUs with
an accelerometer, gyroscope and
magnetometer, placed on the thorax, abdomen and reference position. Turn them
on before starting the campaign.

In the commands, replace `/path/to/rrm4health` with the directory containing
`framework/` and `webapp/`. The included `webapp/` directory contains
`pom.xml`, `mvnw` and `docker-compose.yml`.
Italian WebApp labels are kept as displayed in the interface, with English
explanations where useful.

## 1. Install prerequisites

Python 3.10+, Java JDK 21+, Docker Engine and Docker Compose v2 are required.
On Ubuntu/Debian, if the packages are available for your distribution:

```bash
sudo apt-get update
sudo apt-get install -y python3 python3-pip python3-venv bluez \
    openjdk-21-jdk-headless docker.io docker-compose-v2
sudo systemctl enable --now docker bluetooth
```

### Alternative packages for Raspberry Pi 4 running Debian Bookworm

If Java 21 or Docker Compose v2 is unavailable from package
sources, use the alternative installation steps below. These commands target
Debian 12 (Bookworm); The Java instructions below are for a 64-bit ARM system.

Install the tools needed to configure the package repositories:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl wget gnupg
```

Install Docker from its Debian repository instead of the distribution's
`docker.io` and `docker-compose-v2` packages:

```bash
sudo install -m 0755 -d /etc/apt/keyrings

sudo curl -fsSL https://download.docker.com/linux/debian/gpg \
    -o /etc/apt/keyrings/docker.asc

sudo chmod a+r /etc/apt/keyrings/docker.asc

sudo tee /etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/debian
Suites: bookworm
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

sudo apt update

sudo apt install -y \
    docker-ce \
    docker-ce-cli \
    containerd.io \
    docker-buildx-plugin \
    docker-compose-plugin
```
Enable Docker and check that it works:

```bash
sudo systemctl enable --now docker
docker --version
docker compose version

sudo docker run hello-world
```
Install Java 21 for ARM64 from the Adoptium repository:

```bash
wget -qO - https://packages.adoptium.net/artifactory/api/gpg/key/public \
    | gpg --dearmor \
    | sudo tee /etc/apt/trusted.gpg.d/adoptium.gpg > /dev/null

echo "deb https://packages.adoptium.net/artifactory/deb bookworm main" \
    | sudo tee /etc/apt/sources.list.d/adoptium.list

sudo apt update
sudo apt install -y temurin-21-jdk
```
### Verify prerequisites

After completing either installation method, check the versions:

```bash
python3 --version
java -version
sudo docker compose version
```

The `mvnw` wrapper downloads Maven; you do not need to install it separately.
The first startup requires Internet access to download Docker images and dependencies.

## 2. Prepare Python for the framework

From the `rrm4health` repository root:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt jsonschema
```

RRM Local prepares the applications' Python environments and installs their
`requirements.txt` files. Wait for this to finish on the first startup.
These environments are separate from `venv` and are located at
`framework/core/rrm_local/venv_<application name>/`.

To install the BreathAnalysis dependencies in the environment you just created,
for example for manual checks:

```bash
python -m pip install -r framework/applications/BreathAnalysis/requirements.txt
```

Activate `venv` in every terminal used to run an RRM.

Installing dependencies only in the launchers' `venv` does not update the
application environments. After adding an application or changing its
`requirements.txt`, restart Local and check the environment-preparation logs.

### Prepare inventories and resources

Before starting the RRMs, make sure the inventories describe your hardware.
WebApp settings and GUI presets do not replace these framework files:

| File relative to the RRM repository root | What to check |
| --- | --- |
| `framework/board_specific_descriptors/node_catalog.json` | Compute-node types and capabilities. |
| `framework/board_specific_descriptors/node_inventory.json` | The actual node, its type reference, location and local resources, including the Bluetooth adapter where applicable. |
| `framework/resources_descriptors/peripheral_catalog.json` | Peripheral types, sensors and supported protocols. |
| `framework/resources_descriptors/peripheral_inventory.json` | The actual IDs, types and locations of the three IMUs. |

1. In `node_inventory.json`, select or create the entry for the computer that
   will run Local. Its key is the **node ID** passed in step 5, not an IP address
   or sensor ID. If you reuse an example node, adapt its board type, location
   and resources to the actual machine; do not declare a Raspberry Pi when
   using a laptop.
2. In the peripheral catalog, check that each IMU type includes an accelerometer,
   gyroscope, magnetometer and the appropriate BLE or Wi-Fi connection. Wi-Fi-only
   ESP32-C3 IMUs without a magnetometer do not satisfy the BreathAnalysis
   descriptor; this demo requires BLE.
3. In the peripheral inventory, check the three IDs you will use in the campaign.
   The type must exist in the catalog. For BLE, `id_ble` must match the actual
   name used by the IMU. Do not declare capabilities absent from the hardware
   just to pass validation.
4. Also check location constraints. The descriptor
   `framework/applications/BreathAnalysis.json` currently requests three exclusive
   IMUs with `gyro`, `acc`, `magn` and `ble`.

Installed application descriptors belong directly in `framework/applications/`,
outside the individual application folders: `BreathAnalysis.json` is next to
`BreathAnalysis/`, not inside it.

The following is an example entry to merge into the existing object in
`peripheral_inventory.json`, without replacing the other entries:

```json
{
  "IMU_A": {
    "id_ble": "IMU_A",
    "EXCL_BY_CONFIGURATION": false,
    "type": "Arduino_Nano_33_BLE",
    "location": {
      "building": "B10"
    }
  }
}
```

`IMU_A` is a placeholder: add three entries using your actual device IDs and
types. The codes later registered in the WebApp and passed in `imunames` must
match the inventory IDs. The framework checks exclusive availability: do not
use the same IMUs in another campaign at the same time.

From the RRM repository root, validate the descriptor after making changes:

```bash
PYTHONPATH=framework python tools/CheckerJSON.py framework/applications/BreathAnalysis.json
```

The output must report `VALID`. This checks the descriptor structure, not
whether physical IMUs are present or runtime resource constraints are satisfied.
Prepare these files before startup. If you edit them while the processes are
running, stop the campaign first, then restart Global and Local before retrying.

## 3. Start the databases, MQTT broker and WebApp

If a host-installed Mosquitto service is already using port `1883`, stop it
before starting Compose to avoid a port conflict:

```bash
sudo systemctl stop mosquitto
```

If you want to use only the containerized broker after future reboots, also run
`sudo systemctl disable mosquitto`.

In the first terminal, from the repository root:

```bash
cd /path/to/rrm4health/webapp
sudo systemctl enable --now docker
systemctl status docker --no-pager
sudo docker compose up -d
sudo docker compose ps
```

Compose starts MariaDB (`3306`), InfluxDB (`8086`) and Mosquitto (`1883`).
Wait until the services are ready before starting the WebApp.
SQL files in `setupdata/` initialize MariaDB only when a new volume is created;
subsequent configuration is managed through the WebApp.

Build and start the WebApp from the same directory:

```bash
chmod +x mvnw
./mvnw clean package
java -jar target/bsn-webapp-0.0.1-SNAPSHOT.jar
```

To build without running tests, use `./mvnw clean package -DskipTests`.
Keep the Java terminal open and visit [http://localhost:8080](http://localhost:8080)
in your browser. If needed, create the first account at `/register`, then sign
in at `/login`.

## 4. Start RRM Global

In a second terminal:

```bash
cd /path/to/rrm4health
source venv/bin/activate
cd framework
python3 LaunchRrmGlobal.py --global_port 41798
```

Leave the process running. Global coordinates application execution.

## 5. Start RRM Local

In a third terminal, after starting Global:

```bash
cd /path/to/rrm4health
source venv/bin/activate
cd framework
python3 LaunchRrmLocal.py --global_ip 127.0.0.1 --global_port 41798 \
    --node_id LOCAL_NODE_ID
```

For the Raspberry Pi 4 configured as `rp1` in `node_inventory.json`, use
`--node_id rp1`. On another machine, use its corresponding inventory key rather
than copying `rp1`. The parameter can be omitted, but local resource
synchronization will then be disabled, as explained below.

Wait for application-environment preparation and check Global's logs for Local's
registration. Local will run BreathAnalysis.

Replace `LOCAL_NODE_ID` with the key selected in `node_inventory.json` during
step 2. `--node_id` enables loading and synchronization of local resources with
Global. Check the logs to confirm that the entry was loaded and
`LocalResourcesSync` was sent. Without this parameter, Local still starts but
disables this synchronization; `--board_info_file` does not replace it.

If Local runs on another machine, replace `127.0.0.1` with Global's reachable
IP address and update the MQTT/database hosts so each service can reach them.
`localhost` always refers to the machine or container making the connection,
not automatically to the Global node.

## 6. WebApp: connect to the framework first

Open the **Framework** tab. In **Connection Management**, enter:

| Field | Value for this demo |
| --- | --- |
| RRM Global IP | `127.0.0.1` |
| Port | `41798` |

Click **Connect** and check the connection status. Complete this step before
maintenance configuration: the WebApp needs to retrieve the application list
and parameters from Global.

## 7. WebApp: configure maintenance settings

Open **Manutenzione** (Maintenance) and configure Script Python, Sensori,
Database and MQTT, in that order. The instructions below refer to the labels
shown in the WebApp.

### Python scripts (Script Python)

In **Manutenzione - Script Python**, select `BreathAnalysis` in
**Seleziona applicazione disponibile** (Select available application), then
click **Seleziona applicazione** (Select application).
Set the parameters and click **Salva parametri** (Save parameters):

| Parameter | Value | Meaning |
| --- | --- | --- |
| `adapter` | `hci0` or `hci1` | Usually `hci0` for internal Bluetooth and `hci1` for an external Bluetooth adapter. Check the detected adapters with `bluetoothctl list`. |
| `method_output` | `DB` | Publish analysis results through MQTT. |
| `path_FILE` | `output/` | File-output directory; this demo uses `DB` instead. |
| `host_DB` | `localhost` | MQTT broker host reachable from Local. |
| `port_DB` | `1883` | MQTT port, not the InfluxDB port. |

You can leave **Modificabile dall'utente** (User-editable) enabled for `adapter`
if you want to select the adapter when configuring the campaign. The other
values can remain fixed.

### Sensors (Sensori)

In **Manutenzione - Sensori**, register each of the three IMUs:

| Field shown in the WebApp | Example / choice |
| --- | --- |
| Codice sensore (Sensor code) | The actual BLE IMU ID, for example `IMUFB9D`; it must be unique. |
| Nome sensore (Sensor name) | Any descriptive name, for example `IMU torace`. |
| Tipo sensore (Sensor type) | The actual board type, for example `Nano 33`. |
| Protocollo di default (Default protocol) | `BLE` |
| Protocolli supportati (Supported protocols) | Select `BLE`. |
| Misure supportate (Supported measurements) | Accelerometer, gyroscope and magnetometer. |

Click **Aggiungi sensore** (Add sensor) for each IMU. The sensor code must match
the ID used by the framework, not an arbitrary descriptive name.
Check it against `peripheral_inventory.json` prepared in step 2: registering
sensors in the WebApp does not replace configuration of the RRM inventories.

### Database

In **Manutenzione - Database**, check whether a local configuration already
exists. If not, fill in the fields and click **Aggiungi database** (Add database):

| Field shown in the WebApp | Value |
| --- | --- |
| Nome (Name) | `Influx locale` |
| Indirizzo host (Host address) | `localhost:8086` |
| Nome database (Database name) | `bsn_timeseries` |

This configuration identifies InfluxDB for storing campaign data. It is separate
from the script's `host_DB`/`port_DB` parameters, which identify MQTT.

### MQTT

In **Manutenzione - MQTT**, turn on **Abilita connessione MQTT** (Enable MQTT
connection) and enter:

| Field shown in the WebApp | Value |
| --- | --- |
| Host/IP MQTT | `localhost` |
| Porta (Port) | `1883` |
| Filtro topic MQTT (MQTT topic filter) | `aaac/campaign/#` |

Click **Salva configurazione MQTT** (Save MQTT configuration). The filter covers
both `aaac/campaign/imu` (acquired samples) and `aaac/campaign/breathanalysis`
(results). The WebApp receives messages from the broker and handles storage in
the database selected for the campaign.

## 8. Start the BreathAnalysis campaign

Return to Home and open the campaign creation/start form:

1. Enter the campaign name and select a patient. If needed, register the patient
   first through the WebApp's patient-management page.
2. Select the `BreathAnalysis` campaign type and click **Configura** (Configure).
3. Set **10 Hz**, **BLE** connectivity and the **Influx locale** database.
   The current respiratory-analysis pipeline processes data at 10 Hz.
4. Select the three IMUs and assign the positions `thorax`, `abdomen` and `reference`.

   **Technical details:** the arguments sent to the application must contain
   the IDs in `imunames`, separated by `-`, and the corresponding positions in
   `peripheral_locations`, in the same order. The code accepts
   `thorax-abdomen-reference`; for example:
   `imunames=IMUFB9D-IMU373B-IMUX7X7` and
   `peripheral_locations=thorax-abdomen-reference`.

5. Check the adapter (`hci0` for internal Bluetooth or `hci1` for an external
   adapter), confirm the settings and click **Avvia Campagna** (Start campaign).

Replace the example IDs with your own device IDs. Position names must be in English.

RAW mode is fixed in the code (`RAW_ACQUISITION = True`) because the pipeline
needs individual samples. The acquisition topic is also fixed:
`aaac/campaign/imu`. The application has no maximum iteration limit; stop the
campaign through the interface.

Check Local's logs for connections to all three IMUs and check campaign status
in the WebApp. The first window takes about 30 seconds (300 samples at 10 Hz);
subsequent results can arrive every 10 seconds (a 100-sample step).
Keep the WebApp, Global and Local terminals open throughout the demo.

## 9. Shutdown and quick checks

Stop the campaign through the WebApp first, then stop Local, Global and the
WebApp with `Ctrl+C` in their respective terminals. To stop the data services too:

```bash
cd /path/to/rrm4health/webapp
sudo docker compose stop
```

Database volumes are preserved. To restart the services, use
`sudo docker compose up -d`.

- **WebApp cannot connect:** check that Global is running on port `41798`.
- **Campaign does not start:** check Local's registration, the three IMU IDs,
  positions and Bluetooth adapter.
- **Resource constraints are not satisfied:** check inventory IDs and types,
  BLE/ACC/GYRO/MAGN capabilities, the `B10` constraint and any IMUs already in use.
- **Local resources are not visible:** check `--node_id`, the corresponding
  `node_inventory.json` entry and synchronization messages in Local's logs.
- **Import or environment error:** check the application virtualenv preparation
  logs; installing the package in the launchers' `venv` alone is not enough.
- **No data:** check the broker at `localhost:1883`, the `aaac/campaign/#` filter
  and the database at `localhost:8086` / `bsn_timeseries`.
- **Data services are not ready:** run `sudo docker compose ps` and
  `sudo docker compose logs mariadb mosquitto influxdb` from the WebApp directory.
- **Port already in use:** check for other running instances of the WebApp
  (`8080`), Global (`41798`), MQTT (`1883`) or databases (`3306`, `8086`).

### Alternative check with the desktop GUI

To use the Python GUI instead of the WebApp to start an application, install
Tk on Ubuntu/Debian and open another terminal:

```bash
sudo apt-get install -y python3-tk
cd /path/to/rrm4health
source venv/bin/activate
python framework/LaunchGui.py
```

Connect to `127.0.0.1:41798`, select the application and fill in its parameters
or load a preset with **Load Configuration**. Use the same inventoried IDs and
positions in the required order. Do not start a second campaign using IMUs
already occupied by the WebApp. Messages sent through `notify_message` appear
as dialogs in the desktop GUI; status updates and data published over MQTT are
separate flows.

## 10. Alternative startup method: single-node script

`StartSingleNode.sh` prepares and starts the data services, the bundled WebApp
from `webapp/`, Global and Local as an alternative to manual startup. Stop any
manually started processes before using the script to avoid port conflicts.

**Current limitation:** the script starts Local without `--node_id` and does
not expose an option to pass it. It therefore does not enable the local
inventory synchronization described in step 5. To test that feature, use the
manual startup in steps 3–5; do not add a second Local alongside the one started
by the script. Peripheral inventories still need to be configured when using
the script with new IMUs that are not already registered.

Start from the repository root:

```bash
cd /path/to/rrm4health
chmod +x StartSingleNode.sh
./StartSingleNode.sh
```

For this demo, choose **Locale** (Local) when prompted for the MQTT and InfluxDB
configuration. The script may request your `sudo` password to install
prerequisites. To force a WebApp rebuild and restart everything:

```bash
./StartSingleNode.sh start --rebuild-webapp
```

Open [http://localhost:8080](http://localhost:8080) and still follow steps 6–8
to connect the framework, configure maintenance settings and start the campaign.

Useful commands from the RRM repository root:

```bash
./StartSingleNode.sh status
./StartSingleNode.sh logs
./StartSingleNode.sh stop
./StartSingleNode.sh start
```

`stop` stops the WebApp and RRMs started by the script. Containers remain
running: stop them with `sudo docker compose stop` from `webapp/`.
`start` starts the WebApp and RRMs if they are not already running.
`status` reports the state of the three processes: WebApp, RRM Local and RRM Global.
