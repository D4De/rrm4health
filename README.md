# rrm4health
Repository for the work on runtime resource management for healthcare applications

All application sources and their descriptors are maintained together in
[applications_repo](applications_repo/README.md). Installed applications retain
separate deployment copies in the framework; its descriptor registry contains
only those installed applications.

Start with [HowToStart](HowToStart.md) for a complete BreathAnalysis demo with
the WebApp, one RRM Global and one RRM Local. For implementation details, see
[framework/README.md](framework/README.md) and the
[application development tutorial](applications_repo/ApplicationDevelopment.md).

Unless explicitly stated otherwise, run commands from the repository root
(the directory containing `framework/`) in a new terminal with the environment
activated. Application dependencies and platform-specific hardware support may
have additional requirements beyond the core launcher environment.

# 📁 Repository Structure

```
project_root/
│
├── framework/              # Core framework implementation
│   ├── core/              # Modular core components
│   ├── applications/      # App directories and sibling JSON  descriptors
│   ├── policy/            # Resource allocation policies
│   ├── Launch*.py         # Launch scripts
│   └── Config.py          # Configuration constants
│
├── old/                   # Legacy code (deprecated)
│
├── applications_repo/     # Application sources and descriptors
├── utilities_library/     # Shared managers and integration examples
├── tools/                 # Descriptor and development tools
├── imu/                   # Board-specific firmware and sensor libraries
├── install/               # Platform installation scripts
└── StartSingleNode.sh      # Alternative single-node startup
```

| Directory | Description |
|--------|-------------|
| `framework` | Core framework system with modular architecture |
| `framework/core` | Modular components: RRM, communication, monitoring, models |
| `framework/applications` | Deployed application directories and sibling JSON descriptors |
| `framework/policy` | Resource allocation policy implementations |
| `old` | Deprecated scripts (no longer maintained) |
| `applications_repo` | Application sources and their descriptors |
| `utilities_library` | Shared managers and integration examples |
| `tools` | Descriptor validation, skeleton generation and USB inspection |
| `imu` | Firmware and sensor libraries |

---

# Installation

## Prerequisites

- **Python 3.10+**
- **pip** package manager

Check your Python version:
```bash
python3 --version
```

## Recommended Installation (via `install/` scripts)

Run the script for your operating system from the repository root.

### Linux

Install python 3.10:

```bash
sudo apt install python3.10-venv
```

```bash
cd install
chmod +x Install.sh
./Install.sh
```

What this script does:
- checks that Python 3.10+ is installed
- creates a virtual environment in `venv/`
- upgrades pip
- installs core dependencies (`psutil`, `pyzmq`, `jsonschema`)

Activate the environment later with:
```bash
source venv/bin/activate
```

### macOS

Install python 3.10:

```bash
brew install python
```

```bash
cd install
chmod +x InstallMac.sh
./InstallMac.sh
```

What this script does:
- checks that `python3` is available
- creates a virtual environment in `venv/`
- upgrades pip
- installs dependencies from `requirements.txt`

Activate the environment later with:
```bash
source venv/bin/activate
```

### Windows (PowerShell)

Install python 3.10 in https://python.org".

Open PowerShell in the repository root and run:

```powershell
cd install
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\InstallWindows.ps1
```

What this script does:
- checks that Python 3.10+ is installed
- creates a virtual environment in `venv\`
- upgrades pip
- installs dependencies from `requirements.txt`

Activate the environment later with:
```powershell
.\venv\Scripts\Activate.ps1
```

## Adding New Applications

When you add a new application with its own `requirements.txt`:

1. Create its source directory under `applications_repo/` and keep the main
   implementation, helpers, `requirements.txt` and matching descriptor together.
2. Validate the source descriptor before installation.
3. Install a reviewed copy of the application and register its descriptor only
   when you want the framework to offer that application.

RRM Local prepares environments for installed applications at startup. Keeping
an application only in the source repository does not install it. See the
[application repository guide](applications_repo/README.md).


---

# Quick Start

## Single Node (for dummies): one command

If you want to install, configure and start everything on a single node (RRM Global + RRM Local + GUI WebApp), run this from the repository root:

```bash
./StartSingleNode.sh
```

The script automatically performs:
- `install/Install.sh` from the root (venv setup + RRM Python dependencies)
- WebApp download from `https://github.com/cbolk/IoMTEcoSystem` if `IoMTApp/` does not exist
- `docker compose up -d` in `IoMTApp/` (MariaDB + InfluxDB)
- Java WebApp build (only if the jar does not already exist)
- WebApp startup (`http://localhost:8080`)
- `LaunchRrmGlobal.py` startup
- `LaunchRrmLocal.py` startup targeting `127.0.0.1`

Useful commands:

```bash
./StartSingleNode.sh status
./StartSingleNode.sh stop
./StartSingleNode.sh logs
./StartSingleNode.sh start --rebuild-webapp
./StartSingleNode.sh start --update-webapp
./StartSingleNode.sh start --skip-system-install
./StartSingleNode.sh start --skip-tests
./StartSingleNode.sh start --compile-only
./StartSingleNode.sh start --fix-webapp-encoding
```

Note: on Debian/Ubuntu Linux, the script also attempts to install missing system tools via `apt` (Docker, Compose, Java, git, python3-venv), enables/starts Docker, checks `docker status/ps`, and then proceeds with app setup (RRM Python venv, RRM dependencies, WebApp clone/update/build). If you want to skip the `apt` step, use `--skip-system-install`.


## Starting the Framework

The framework uses dedicated launch scripts for each component.

### 1. Start the Global RRM (Orchestrator)

```bash
cd framework
python3 LaunchRrmGlobal.py [OPTIONS]
```

**Available options:**
```bash
python3 LaunchRrmGlobal.py [-h] \
    [--global_port GLOBAL_PORT] \
    [--policy_name {PolicySymmetricDistribution,PolicyMaximizeBatteryLife}] \
    [--log_level {DEBUG,INFO,WARNING,ERROR}] \
   [--log_file LOG_FILE] \
   [--snapshot_detail {minimal,policy,full}] \
   [--metrics_mode {instant,window}] \
   [--window_seconds WINDOW_SECONDS] \
   [--sample_interval_seconds SAMPLE_INTERVAL_SECONDS] \
   [--autostart {on,off,true,false,yes,no,1,0}]
```

- `--global_port`: Port for RRMGlobal (default: 41798)
- `--policy_name`: Resource allocation policy (default: PolicySymmetricDistribution)
- `--log_level`: Logging verbosity (default: INFO)
- `--log_file`: Optional log file path
- `--snapshot_detail`: Global snapshot verbosity (default: policy)
- `--metrics_mode`: Capabilities collection mode (default: instant)
- `--window_seconds`: Window size for metrics_mode=window
- `--sample_interval_seconds`: Sampling interval for metrics_mode=window
- `--autostart`: enable/disable automatic startup of applications listed in `framework/auto_start_applications.json` (default: off)

Examples:

```bash
# enable automatic app startup when Global starts
python3 LaunchRrmGlobal.py --autostart on

# disable automatic app startup when Global starts
python3 LaunchRrmGlobal.py --autostart off
```

### 2. Start Local RRM Instances (Nodes)

Run on each node (can be same or different machines):

```bash
cd framework
python3 LaunchRrmLocal.py [OPTIONS]
```

**Available options:**
```bash
python3 LaunchRrmLocal.py [-h] \
    [--global_ip GLOBAL_IP] \
    [--global_port GLOBAL_PORT] \
    [--board_info_file BOARD_INFO_FILE] \
    [--log_level {DEBUG,INFO,WARNING,ERROR}] \
    [--log_file LOG_FILE]
```

- `--global_ip`: IP address of RRMGlobal (default: auto-detected)
- `--global_port`: Port of RRMGlobal (default: 41798)
- `--board_info_file`: Optional JSON file with device-specific performance data
- `--log_level`: Logging verbosity (default: INFO)
- `--log_file`: Optional log file path

⚠️ **Note:** Ensure `--global_port` matches on both Global and Local instances.

### 3. Start User Interface

Choose between CLI or GUI:

**Command-Line Interface (CLI):**
```bash
cd framework
python3 LaunchCli.py
```

The CLI provides a menu:
```
Simple RRM CLI
1. Start App
2. Stop App
3. Get Policy List
4. Change Policy
5. Exit
```

**Graphical User Interface (GUI):**
```bash
cd framework
python3 LaunchGui.py
```

The GUI provides:
- Connect to RRMGlobal by specifying IP and port
- Start/stop applications with user arguments
- View running applications in real-time
- Change resource allocation policies
- **Load preset configurations** for quick application setup (see GUI Configuration Files in the framework README and the application development guide)

---

## Deploying an Application

### From the application repository to the framework

Each directory in `applications_repo/` contains an application and its matching
JSON descriptor. Installed applications retain separate runtime copies.

1. Develop the implementation, helpers, assets and `requirements.txt` together
   with the descriptor in the application's source directory.
2. Validate the source descriptor, for example:

   ```bash
   PYTHONPATH=framework python tools/CheckerJSON.py applications_repo/Battery_BLE/Battery_BLE.json
   ```

   Check that the output reports `VALID`.
3. After stopping any running instance, copy the application directory into
   `framework/applications/` and its descriptor directly into the same directory,
   outside the individual application folders. For example, install the code in
   `framework/applications/BreathAnalysis/` and register it with
   `framework/applications/BreathAnalysis.json`.
   Review local changes before updating a runtime copy.
4. Restart Local to prepare its environment, restart Global and refresh the
   interface's application list.

Do not leave descriptors for uninstalled applications in the runtime registry.
For details and the current installation list, see
[applications_repo/README.md](applications_repo/README.md).

---

## Example Workflow

### Start a test application with CLI

1. **Start RRMGlobal:**
   ```bash
   cd framework
   python3 LaunchRrmGlobal.py
   ```

2. **Start two RRMLocal instances** (in separate terminals):
   ```bash
   python3 LaunchRrmLocal.py
   ```

3. **Start the CLI** (in another terminal):
   ```bash
   python3 LaunchCli.py
   ```

4. **Start an application:**
   ```
   Choose an option: 1
   Enter App ID: template_test
   Enter user arguments (JSON format or press Enter for none): {"NUM_REP": "5"}
   ```

   Success response:
   ```
   [RECEIVED]: {'type': 'Start App Response', 'status': 'OK', 'appID': ['template_test', 1]}
   ```

5. **Check available policies:**
   ```
   Choose an option: 3
   [RECEIVED]: {'type': '[GUI] Policy List Response', 
                'policy_list': ['PolicySymmetricDistribution', 'PolicyMaximizeBatteryLife']}
   ```

6. **Change policy:**
   ```
   Choose an option: 4
   Enter new policy name: PolicyMaximizeBatteryLife
   [RECEIVED]: {'type': '[GUI] Policy Change Response', 'status': 'OK'}
   ```

7. **Stop the application:**
   ```
   Choose an option: 2
   Enter App ID: template_test,1
   [RECEIVED]: {'type': 'Stop App Response', 'status': 'OK'}
   ```

### AppStarter: direct execution for testing only

**Use CLI or GUI to start applications during normal operation.** Direct
invocation of [AppStarter.py](framework/core/rrm_local/app_starter/AppStarter.py)
is for testing/debugging only, not a separately maintained standalone launcher.
It loads an integrated application and runs its partition's setup, loop and
cleanup; normally RRM Local launches it automatically.

For a BreathAnalysis test, prepare the installed application, its Python
environment, three BLE IMUs and MQTT as described in [HowToStart](HowToStart.md).
From the repository root, the direct command has a form like this:

```bash
framework/core/rrm_local/venv_BreathAnalysis/bin/python \
    framework/core/rrm_local/app_starter/AppStarter.py \
    --App_id BreathAnalysis --Ind_conf 0 --Id_part partitionA \
    --App_instance_counter 1 --RRM_port LOCAL_APP_PORT \
    --imunames IMU_A-IMU_B-IMU_C \
    --peripheral_locations thorax-abdomen-reference \
    --adapter hci0 --campaignname breath_test --samplingfreq 10 \
    --method_output DB --path_FILE output/ --host_DB localhost --port_DB 1883
```

Replace the IMU IDs and adapter with your hardware values. Configuration index
`0` contains the single `partitionA`. `LOCAL_APP_PORT` must be Local's actual
internal application port, **not** Global's `41798` or MQTT's `1883`.

⛔ **WARNING:**  This is a low-level command template, not a standalone demo: it requires Local's
communication endpoint and coordinated instance/process tracking. It bypasses
normal scheduling and resource reservation.

⛔ **DO NOTE:** launch it alongside a managed instance using the same IMUs.
For routine startup and shutdown, use CLI or GUI instead.

---

## Documentation

Manager classes have exactly the same names as their files, : `BleAcquisitionMngr`, `WifiAcquisitionMngr`,
`FileAcquisitionMngr` and `MqttTransmissionMngr`. Import them from
`utilities_library`, as shown in the shared-manager guide.

- [Shared Managers](utilities_library/README.md) - Acquisition and MQTT managers used by applications
- [Framework Architecture](framework/README.md) - Detailed component documentation
- [Application Development Guide](applications_repo/ApplicationDevelopment.md) - How to create applications
- [JSON Manifest Tutorial](applications_repo/ApplicationDevelopment.md#3-write-the-descriptor) - Application descriptor format

---

## Key Features

- **Dynamic Resource Management**: Automatic task distribution across heterogeneous nodes
- **Multiple Policies**: Support for different resource allocation strategies
- **Flexible Deployment**: Partition applications across multiple devices
- **Real-time Monitoring**: Track CPU, memory, battery, and network usage
- **Graceful Shutdown**: Clean termination of distributed applications
- **Device Profiling**: Performance characterization for optimal placement

---

## Requirements

See [Installation](#-installation) section above for complete setup instructions.

**Core dependencies:** pyzmq, psutil, numpy  
**Optional (applications):** pandas, scipy, scikit-learn, bleak, paho-mqtt

---
