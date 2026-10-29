# 📁 Framework Directory Structure

The Framework folder contains the runtime, application descriptors and deployed
applications. See [HowToStart](../HowToStart.md) for the WebApp demo and
[Application Development Guide](../applications_repo/ApplicationDevelopment.md) for application development.

Unless stated otherwise, run shell commands from the repository root (the
directory containing `framework/`), with the Python environment activated.

```
framework/
│
├── core/                          # Core framework components 
│   ├── communication/             # Message passing and channel management
│   ├── models/                    # Data models and schemas
│   ├── monitoring/                # Performance tracking and metrics
│   ├── rrm_global/                # Global RRM orchestration logic
│   ├── rrm_local/                 # Local RRM node management
│   ├── Utils.py                   # Common utility functions
│   └── logging_config.py          # Centralized logging configuration
│
├── applications/                  # App directories and sibling JSON descriptors
│   ├── BreathAnalysis/
│   ├── BreathAnalysis.json
│   └── ...
│
├── policy/                        # Resource allocation policies
│   ├── Policy.py                  # Base policy interface
│   ├── PolicySymmetricDistribution.py  # Symmetric distribution policy
│   ├── PolicyMaximizeBatteryLife.py    # Battery-aware policy
│   └── PolicyUtils.py             # Policy loading utilities
│
├── board_specific_descriptors/   # Device performance profiles
│   ├── DevicePerformancePerPartition.json  # Profiled performance data
│   ├── node_catalog.json        # Compute-node type definitions
│   └── node_inventory.json      # Logical nodes, locations and local resources
│
├── resources_descriptors/
│   ├── peripheral_catalog.json  # Peripheral type definitions
│   └── peripheral_inventory.json # Peripheral instances and capabilities
│
├── LaunchRrmGlobal.py          # Launch script for RRMGlobal
├── LaunchRrmLocal.py           # Launch script for RRMLocal
├── LaunchCli.py                 # Launch script for CLI interface
├── LaunchGui.py                 # Launch script for GUI interface
│
└──Config.py                      # System-wide configuration constants
```

Descriptor validation and skeleton generation live outside `framework/`, in
[`tools/`](../tools/README.md): `CheckerJSON.py` and `AppSkeletonCreator.py`.
USB inspection is provided by `tools/PrintUsbDevices.py`.

---

## Installation

Use Python 3.10 or newer. See [HowToStart](../HowToStart.md) for system
dependencies, broker/database setup and the complete demo.

**Quick install (from project root):**

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt jsonschema
```

**Individual application dependencies:**

Install the requirements of the application you want to inspect or test manually:

```bash
python -m pip install -r framework/applications/BreathAnalysis/requirements.txt
```

RRM Local prepares isolated application environments at startup, using each
application's `requirements.txt`. They live under
`framework/core/rrm_local/venv_<application name>/`. Installing packages in the
launcher environment alone does not update these application environments.
Restart Local after adding an application or changing its requirements, and
check its environment-preparation logs.

---

## Core Components


### Communication (`core/communication/`)

| File | Description |
|------|-------------|
| `ChannelManagerApp.py` | Manages inter-partition communication channels for running applications |
| `ChannelManagerClient.py` | Implements ZeroMQ client-router pattern client (used by RRMLocal, CLI, GUI) |
| `ChannelManagerRouter.py` | Implements ZeroMQ client-router pattern router (used by RRMGlobal, RRMLocal) |
| `Message.py` | Dataclass definitions for all framework message types |
| `MessageTypes.py` | Enum definitions for message type identifiers |
| `OrchIF.py` | Interface for applications to communicate with RRMLocal |

### 🗂️ Models (`core/models/`)

| File | Description |
|------|-------------|
| `Node.py` | Represents a compute node with its capabilities, status, and running partitions |
| `DescriptorSchema.py` | Parameter definitions and channel schema utilities; manifest validation is in the repository-level `tools/CheckerJSON.py` |

### 📊 Monitoring (`core/monitoring/`)

| File | Description |
|------|-------------|
| `MetricFields.py` | Enum definitions for performance metrics (CPU, memory, battery, network, etc.) |
| `MetricsCollector.py` | Collects and manages runtime performance metrics from nodes |
| `PerformanceTracker.py` | Tracks device performance per partition, computes costs, manages profiles |

### 🌐 RRM Global (`core/rrm_global/`)

| File | Description |
|------|-------------|
| `RRMGlobal.py` | Main orchestrator class coordinating the entire distributed system |
| `NodeManager.py` | Manages connected RRMLocal nodes, their status, and capabilities |
| `ApplicationManager.py` | Manages application lifecycle, placement, and monitoring |
| `MessageHandler.py` | Handles all incoming messages to RRMGlobal from nodes, apps, and UIs |
| `ResourceConstraintManager.py` | Validates task resource requests and resolves linked sensor parameters |
| `LocationManager.py` | Tracks node/peripheral locations and peripheral usage |

### 💻 RRM Local (`core/rrm_local/`)

| File | Description |
|------|-------------|
| `RRMLocal.py` | Local node manager executing commands from RRMGlobal |
| `PartitionManager.py` | Manages locally running application partitions and processes |
| `MetricsManager.py` | Collects and reports local performance metrics to RRMGlobal |
| `MessageHandlerLocal.py` | Handles all incoming messages to RRMLocal |
| `AppEnvironmentManager.py` | Prepares and checks per-application virtual environments at Local startup |

### 🚀 App Starter (`core/rrm_local/app_starter/`)

| File | Description |
|------|-------------|
| `AppStarter.py` | Main application partition executor (entry point for app processes) |
| `LifecycleManager.py` | Manages setup, loop, and cleanup phases of application tasks |
| `TaskGraphManager.py` | Orchestrates task dependencies and execution order |
| `ChannelSetupManager.py` | Configures communication channels between partitions |
| `CodeIntegrityChecker.py` | Performs static AST checks of loop return patterns and producer/consumer consistency before execution |

---

## Policy System (`policy/`)

The framework supports pluggable resource allocation policies:

| Policy | Description |
|--------|-------------|
| `PolicySymmetricDistribution` | Evenly distributes tasks across available nodes |
| `PolicyMaximizeBatteryLife` | Prioritizes nodes with AC power to preserve battery-powered devices |

Custom policies provide matching subclasses of `GlobalPolicyBase` and
`LocalPolicyBase` from `policy/Policy.py`. The global interface includes
`get_required_fields()`, `get_best_placement(graph, manifest)` and
`get_next_update_time(new_utilization, old_utilization)`. The local interface
includes `get_required_fields()`, `update_node_status()` and
`reset_node_status()`. Import both implementations in `PolicyUtils.py`, and
give them the same public `name()` so the Global and Local loaders agree.

---

## Deployment Workflow

Keep every application's source and descriptor together in `applications_repo/`.
Only installed applications have duplicate code under `framework/applications/`
and registered descriptors directly under `framework/applications/`, outside
the individual application folders. See the
[application repository guide](../applications_repo/README.md).

### 1. Create Application Manifest

Create `applications_repo/your_app/your_app.json`. A minimal complete example is
shown below; see [the development tutorial](../applications_repo/ApplicationDevelopment.md) for a
multi-task application. A descriptor defines:

- Tasks and their dependencies
- Executable information
- Deployment configurations
- Resource requirements

**User Parameter Conventions:**

In the `executable.parameters` section, you can define user-configurable parameters with different behaviors in the GUI:

```json
{
  "name": "your_app",
  "taskgraph": [
    {
      "id": "Work",
      "description": "Run one iteration of the application",
      "depends_on": [],
      "input": [],
      "output": []
    }
  ],
  "executable": {
    "path": "applications/your_app/your_app.py",
    "parameters": {
      "param1": "{{Description of what to enter}}",
      "param2": "default_value",
      "param3": ""
    },
    "timeouts": {"setup": 60, "loop": 5, "cleanup": 10}
  },
  "configurations": [
    {
      "id": "config0",
      "partitions": [
        {
          "id": "partitionA",
          "tasks": ["Work"],
          "node": "{{NODE_A}}",
          "required_resources": {
            "ram": 0,
            "disk": 0,
            "network_upload": 0,
            "network_download": 0
          }
        }
      ],
      "channels": []
    }
  ]
}
```

| Format | GUI Behavior | Required | Example |
|--------|--------------|----------|---------|
| `"{{hint text}}"` | Shows gray placeholder hint that disappears on click. User **must** fill this field to start the application. | Yes | `"{{Number of iterations}}"` |
| `"default_value"` | Pre-fills the field with the default value in black text. User can modify or keep it. |  No | `"10"` |
| `""` | Leaves the field empty. User can optionally fill it. |  No | `""` |

`taskgraph` is a root-level list; `executable` and `configurations` are its
siblings. `executable.path` is relative to `framework/`. Read user parameters
from `self._user_args`, and validate/convert them in setup. Framework-managed
parameters such as `Ind_conf`, `Id_part`, `channels` and `RRM_port` must not be
added to `executable.parameters`.

When the GUI user tries to start an application without filling required fields (those with `{{}}`), an error popup will list the missing fields and prevent the start command from being sent.

### 2. Validate Manifest

```bash
PYTHONPATH=framework python tools/CheckerJSON.py applications_repo/your_app/your_app.json
```

Check that the output reports `VALID`;

### 3. Generate Application Template

```bash
mkdir -p applications_repo/your_app
(
    cd applications_repo/your_app
    PYTHONPATH=../../framework python ../../tools/AppSkeletonCreator.py \
        --manifest_name your_app.json
)
```

This creates `your_app.py` with all task methods pre-defined. The creator writes
`<descriptor name>.py` in its working directory and overwrites an existing file
with that name. Generate in a new/scratch directory when revising a descriptor;
do not overwrite an implemented application.

### 4. Implement Application Logic

Fill in the generated template methods:

- `setup()` and `<task_id>_setup()`: Initialize resources.
- `<task_id>_loop()`: Run task logic and return the declared output dictionary.
- `<task_id>_cleanup()` and `cleanup()`: Release resources, including partially
  initialized resources after setup failures.

Keep `set_framework()` unchanged. Pass data between tasks using returned keys
matching the consumer arguments, rather than shared globals or instance state:
partitions may run in different processes. Returning `None` does not automatically
skip downstream tasks. See [Application Development Guide](../applications_repo/ApplicationDevelopment.md) for
manager integration, RAW/FEATURES acquisition and notifications.

### 5. Deploy

```bash
# Check the generated implementation after filling in the methods
python -m py_compile applications_repo/your_app/your_app.py
```

The descriptor and implementation remain together in the application repository.
Put helper modules/resources there and add its `requirements.txt`. To install
this new application, copy its directory into `framework/applications/` and
its descriptor directly into `framework/applications/`, not inside the copied
application folder. Preserve the installed path in
`executable.path`; do not rewrite it to the source repository's location.
Review existing runtime changes before updating an installed application.
Deploy code and assets on every execution node; 

### 6. Run

Start/restart the RRM components after deployment, then use CLI, desktop GUI or
the WebApp to request execution. The generated class is not a standalone script.

### 7. (Optional) Create GUI Configuration Files

For easier application launching via GUI, you can create preset configuration files:

1. **Create a `gui_config` folder** in your application directory:
   ```bash
   mkdir -p applications_repo/your_app/gui_config
   ```

2. **Create JSON configuration files** with preset parameter values:
   ```bash
   touch applications_repo/your_app/gui_config/config1.json
   ```

3. **Define configuration presets** in JSON format:
   ```json
   {
     "name": "Configuration Name",
     "description": "Brief description of what this configuration does",
     "userargs": {
       "param1": "value1",
       "param2": "value2",
       "param3": "value3"
     }
   }
   ```

**Example:** a new preset at
`framework/applications/BreathAnalysis/gui_config/three_imus_demo.json`:

```json
{
  "name": "Three IMUs - local MQTT",
  "description": "Thorax, abdomen and reference sensors with MQTT output",
  "userargs": {
    "imunames": "IMU_A-IMU_B-IMU_C",
    "peripheral_locations": "thorax-abdomen-reference",
    "adapter": "hci0",
    "campaignname": "breath_campaign_001",
    "samplingfreq": "10",
    "method_output": "DB",
    "path_FILE": "output/",
    "host_DB": "localhost",
    "port_DB": "1883"
  }
}
```

Replace the sensor IDs with registered devices in the same order as their
locations. For example BreathAnalysis requires exactly the three roles `thorax`, `abdomen`
and `reference`, with `-` as the separator. `hci0` usually identifies internal
Bluetooth and `hci1` an external adapter; verify with `bluetoothctl list`.
Do not add the removed `initcounter`, `rawquat` or `database_DB` parameters.
RAW acquisition and the topic `aaac/campaign/imu` are fixed in the application.
`host_DB`/`port_DB` identify the MQTT broker (normally `1883`), not the InfluxDB
HTTP endpoint (`8086`). Check sensor capabilities and the descriptor's `B10`
building constraint against your deployment.

**Using configurations in the desktop GUI:**

- Select your application from the dropdown
- If configuration files exist, the "Load Configuration" button becomes enabled
- Click "Load Configuration" to see available presets
- Select a preset and click "Apply" to populate the parameter fields
- Modify values if needed, then click "Start Application"

The WebApp has its own maintenance screens; see [HowToStart](../HowToStart.md).

**Benefits:**

- Save commonly used parameter sets
- Quick switching between different scenarios (e.g., testing vs. production)
- Reduce errors from manual parameter entry
- Share configurations with team members

---

## Configuration (`Config.py`)

System-wide constants:
- Port ranges for RRM and applications
- Performance collection intervals
- Timeouts for application lifecycle phases
- File paths for descriptors and performance data

---

## Launch Scripts

| Script | Purpose |
|--------|---------|
| `LaunchRrmGlobal.py` | Start the global orchestrator |
| `LaunchRrmLocal.py` | Start a local node manager |
| `LaunchCli.py` | Start command-line interface |
| `LaunchGui.py` | Start graphical user interface |

Start the components in separate terminals, keeping them running:

```bash
python framework/LaunchRrmGlobal.py --global_port 41798
```

```bash
python framework/LaunchRrmLocal.py --global_ip 127.0.0.1 --global_port 41798
```

```bash
python framework/LaunchGui.py
```

Connect the desktop GUI to Global at `127.0.0.1:41798` for this local example.
Alternatively use `python framework/LaunchCli.py`, or follow
[HowToStart](../HowToStart.md) to launch and configure the WebApp.
The Global, Local and CLI launchers support `--help`; the desktop GUI configures
its connection inside the window, not through an argparse `--help` interface.

## Node and Peripheral Inventories

The framework's inventories are separate from desktop GUI presets and WebApp
maintenance settings:

- `framework/board_specific_descriptors/node_catalog.json`: compute-node types.
- `framework/board_specific_descriptors/node_inventory.json`: logical nodes,
  their type, location and local resources.
- `framework/resources_descriptors/peripheral_catalog.json`: peripheral types
  and capabilities.
- `framework/resources_descriptors/peripheral_inventory.json`: concrete
  peripherals used to satisfy task `requires` constraints.

When using inventory-backed local resource synchronization, supply the logical
node ID from `node_inventory.json`:

```bash
python framework/LaunchRrmLocal.py --global_ip 127.0.0.1 --global_port 41798 \
    --node_id YOUR_NODE_ID
```

Replace `YOUR_NODE_ID` with the entry for the actual machine; it is not an IP
address or an application ID. Without `--node_id`, Local can still start, but
its local resource-registry synchronization is disabled. `--board_info_file`
can override compute-board information; it does not replace `--node_id` for
resource synchronization.

Task `requires` entries use `ResourceRequest` or `DeviceRequest`, with
`parameter_linked` and `separator` connecting selected resources to application
parameters. Capabilities, exclusive usage and location constraints must match
the inventory. For one device use an empty separator; for several devices use
the separator declared in the descriptor. See
[the resource-request example](../applications_repo/ApplicationDevelopment.md#descriptor-rules).

## Application Notifications and Stop Handling

Use the injected `self._app` interface inside application methods:

```python
self._app.notify_message("Acquisition ready", severity="info")
self._app.notify_peripherals_in_use(["IMU_A"], "ble")
# Later, after disconnecting the peripheral in cleanup:
self._app.notify_peripherals_released(["IMU_A"])
```

`notify_message` sends a user-facing framework notification (`info`, `warning`
or `error`); it does not stop execution or publish an MQTT result. Peripheral
helpers update usage status and do not connect/disconnect the hardware.
Use registered IDs, not custom output aliases. See
[the notification tutorial](../applications_repo/ApplicationDevelopment.md#9-send-notifications-to-the-user-and-report-peripheral-usage)
for placement in task setup/loop/cleanup and avoiding duplicate alerts.

`self._app.stop_application()` requests an intentional stop and raises the
framework's stop exception. `self._app.wait_for_stop()` lets an exhausted finite
source stay idle until STOP instead of repeatedly executing the graph.
Do not swallow the stop exception in broad application error handlers.

Setup, loop and cleanup execute in worker threads controlled by AppStarter.
The descriptor's `loop` timeout is a join budget after STOP or loop termination,
not a maximum campaign duration or a per-window deadline. Keep hardware reads
bounded and check `self._app.is_running()` in long acquisition waits so cleanup
can begin when STOP arrives. Configure setup and cleanup budgets to cover their
actual resource operations.

---

## Auto-start Applications at Global Startup

The framework supports optional automatic application launch when RRMGlobal starts.

### How it works

- The list of applications to start is read from `framework/auto_start_applications.json`.
- Auto-start is enabled only when you launch Global with:

  python framework/LaunchRrmGlobal.py --autostart on

- To disable it explicitly:

  python framework/LaunchRrmGlobal.py --autostart off

### File format: `auto_start_applications.json`

The file must contain a top-level object with an `applications` array.

Example for the `your_app` descriptor created earlier (not a built-in app):

```json
{
  "applications": [
    {
      "app_id": "your_app",
      "args": {
        "param1": "demo",
        "param2": "default_value",
        "param3": ""
      }
    }
  ]
}
```

### Mini guide to edit the file

1. Open `framework/auto_start_applications.json`.
2. Add one object per app inside `applications`.
3. Set `app_id` exactly equal to the descriptor name (without .json) in `framework/applications/`.
4. Fill `args` with the same parameter names defined in `executable.parameters` of that descriptor.
5. Save the file and restart Global with `--autostart on`.

### Common mistakes

- Wrong `app_id` (does not match descriptor filename).
- `args` is not an object (must be `{ ... }`).
- Missing required user parameters for the target descriptor.

### Quick validation tip

If auto-start does not trigger, check Global logs first. Malformed entries and
permanent launch errors are logged; launch attempts that need additional nodes
may be postponed until nodes become available. Supply all required parameters
and deploy the application before enabling its entry.

---

## Logging

Centralized logging configuration in `core/logging_config.py`:
- Configurable log levels: DEBUG, INFO, WARNING, ERROR
- Optional file logging
- Separate loggers for different components

Set log level when launching:
```bash
python framework/LaunchRrmGlobal.py --log_level DEBUG
```

---

## Global Snapshot Detail Levels (Implementation Decision)

To keep global snapshots useful for orchestration while avoiding unnecessary runtime noise, the framework now supports a configurable snapshot detail level.

### Why this was introduced

The global snapshot has two different use cases:

1. **Minimal orchestration view** for architecture + workload mapping.
2. **Runtime-aware view** where node metrics are needed for policy-driven decisions.

For this reason, the global snapshot output is now controlled by a dynamic detail-level mechanism.

### Detail levels

The global snapshot supports three levels:

1. **minimal**
  - Includes only architecture structure, running workload, and mapping.
  - Excludes node runtime summaries and additional diagnostic sections.

2. **policy**
  - Includes only runtime metrics required by the selected policy.
  - This is the default level and keeps output aligned with actual scheduling needs.

3. **full**
  - Includes all available node runtime metrics.

### How to configure

Use the global launcher option:

```bash
python framework/LaunchRrmGlobal.py --snapshot_detail minimal
python framework/LaunchRrmGlobal.py --snapshot_detail policy
python framework/LaunchRrmGlobal.py --snapshot_detail full
```

### What was changed in code

1. **Default configuration constant**
  - Added `GLOBAL_SNAPSHOT_DETAIL_DEFAULT` in `Config.py`.

2. **Global launcher option**
  - Added `--snapshot_detail` argument in `LaunchRrmGlobal.py`.

3. **RRMGlobal wiring**
  - `RRMGlobal` now accepts `snapshot_detail` and passes it to global status printing.

4. **NodeManager logic**
  - Added policy-aware filtering for runtime summary fields.
  - Added level-based output gating (`minimal`, `policy`, `full`).

### Additional behavior linked to logging

The "Device Performance Per Partition" section is printed only in full logging mode (`DEBUG`), not at default `INFO`.

This keeps normal console output compact while preserving deep diagnostics when explicitly requested.

---

## Metrics Collection Modes (Instant vs Window)

Metrics capabilities requested by RRMGlobal now support two collection modes:

1. **instant** (default)
  - Single measurement for each requested metric.

2. **window**
  - Repeated sampling in background over a configurable rolling window.
  - For metrics where averaging is meaningful, RRMLocal returns the **mean**.
  - For metrics where mean is not meaningful (or not computable), RRMLocal returns `instant_only` values.

### Window aggregation policy

In `window` mode, aggregation is intentionally limited to **mean** only.

- Mean-compatible metrics are limited to: `temperature`, `power_consumption_w`, `upload_speed`, and `download_speed`.
- In practice, upload/download are derived from the `network` counters and aggregated as mean speeds in `B/s`.
- Non-mean-compatible metrics (for example architecture/static capacities/network counters/connection-state flags) are returned in `instant_only` mode.


### How to configure from RRMGlobal

Use the global launcher flags:

```bash
python framework/LaunchRrmGlobal.py --metrics_mode instant

python framework/LaunchRrmGlobal.py --metrics_mode window --window_seconds 5 --sample_interval_seconds 0.5
```

Arguments:

- `--metrics_mode`: `instant` (default) or `window`
- `--window_seconds`: window duration in seconds (must be `> 0` to enable effective window mode)
- `--sample_interval_seconds`: sampling interval during window mode (must be `> 0`, default `0.5`)

### Latency note

In `window` mode, capabilities are computed from a rolling cache populated by a background sampler thread.

This means requests do **not** wait for the full `window_seconds` before replying.

The sampler wakes up approximately every `sample_interval_seconds` (or faster if a smaller interval was requested previously) and updates the cache used for aggregation.

The default mode remains `instant`, and `window` should be enabled only when aggregated metrics are explicitly needed.

---

## Metrics Collection by OS and Architecture

The metrics subsystem is structured to support different hardware families and operating systems without changing the orchestrator architecture.

### Current design

Metrics collection is centralized in:

- `core/monitoring/MetricsCollector.py`

The collector is initialized with:

- `architecture_flag` (for example `arm64`, `x86_64`)
- `os_name` (for example Linux, Windows, macOS)

At RRMLocal startup, these values are resolved and passed to the collector. The architecture comes from node profile data when available, with fallback to runtime detection.

### Dispatch logic

The implementation uses explicit dispatch points so each metric can evolve independently by OS/architecture:

1. **Power consumption**
  - Entry point: `_get_system_power_consumption()`.
  - Architecture branch:
    - ARM: `get_power_rpi()` / alias `getPowerRPI()`
    - x86: `get_power_intel()` / alias `getPowerIntel()`
    - fallback: `_get_generic_power()`

2. **Temperature**
  - Entry point: `_get_temperature()`.
  - OS branch:
    - Linux: `_get_temperature_linux()`
    - Windows: `_get_temperature_windows()`
    - macOS: `_get_temperature_macos()`

3. **Disk metrics**
  - Root path is selected by OS (`/` on Unix-like systems, `SystemDrive` on Windows).

4. **Process frequency probing**
  - Linux-specific sources (`/proc`, `cpufreq`) are guarded behind OS checks.
  - Generic `psutil` fallback remains available for portability.

### How to add hardware-specific implementations (without architectural changes)

When adding a new board or CPU family, keep the same external API and modify only collector internals.

Recommended workflow:

1. Add/confirm architecture identifier in node catalog (`compute.cpu.architecture`).
2. Extend architecture normalization mapping in `MetricsCollector` if needed.
3. Implement or refine the dedicated method for the target family:
  - `get_power_rpi()` for Raspberry-like devices
  - `get_power_intel()` for Intel/AMD laptops/desktops
  - add new method (for example `get_power_nvidia_jetson()`) and branch it in `_get_system_power_consumption()`
4. Keep generic fallback methods untouched to preserve compatibility.
5. Validate behavior on each OS with the same RRMLocal and policy flow.

This approach allows improving metric accuracy per platform while keeping message schemas, policy interfaces, and RRMGlobal/RRMLocal integration stable.

---

## Indoor Location Model (Implementation Choices)

To better support indoor deployments, location modeling is now centered on enclosed spaces (building/floor/room) instead of outdoor-style coordinates only.

### Design goals

1. Keep the model simple for operators (`building,floor,room`).
2. Use a single canonical JSON representation.
3. Allow progressive evolution toward richer indoor navigation/semantics.
4. Support partial/uncertain location data with explicit quality metadata.

### Recommended canonical structure

Use a hierarchical indoor object as canonical representation:

- `building`
- `floor`
- `room`
- `zone` (optional)

### Why this model

- It matches common indoor operational needs (where a device is in the building hierarchy).
- It supports missing details (for example only building or floor known).
- It keeps matching logic deterministic and simple across resources and constraints.
- It is compatible with future extension to topological indoor navigation models.

Configuration note:

- Static JSON configurations should contain only semantic location keys (`building`, `floor`, `room`, optional `zone`).
- Confidence/provenance/timestamp values can be computed at runtime by acquisition/fusion modules and are not required in configuration files.

### Acquisition strategy (practical roadmap)

1. **Static baseline (immediate)**
  - Define location in inventory files for fixed nodes/resources.
  - Use as trusted fallback.

2. **Assisted indoor inference (short term)**
  - Wi-Fi mapping: `BSSID/SSID -> building/floor/room`.
  - BLE mapping: `beacon_id -> building/floor/room`.
  - Output includes `source` and `confidence`.

3. **Sensor fusion (mid term)**
  - Combine static + Wi-Fi + BLE (+ optional IMU) with confidence-based rules.
  - Apply timeout/decay for stale dynamic estimates.

4. **Quality governance**
  - If confidence is low or inconsistent, fall back to static inventory location.
  - Always keep provenance (`source`) and freshness (`updated_at`).

### Location Manager (Event-Driven Skeleton)

To support dynamic indoor localization in an event-driven architecture, the framework includes a dedicated global manager:

- `core/rrm_global/LocationManager.py`

Current scope of this component:

1. Maintain location state for nodes and peripherals.
2. Accept runtime updates from RRMLocal components.
3. Track peripheral usage state (`in_use`) to highlight actively used devices.
4. Expose snapshots for orchestration/monitoring.
5. Provide an internal event backlog for downstream processing.

Implemented event types:

- `node_location_updated`
- `node_location_removed`
- `peripheral_location_updated`
- `peripheral_location_removed`
- `peripheral_usage_updated`

Main APIs already available:

- `update_node_location(node_id, location, source=...)`
- `update_peripheral_location(node_id, peripheral_id, location, in_use=..., source=...)`
- `set_peripheral_in_use(node_id, peripheral_id, in_use, source=...)`
- `remove_node(node_id, source=...)`
- `remove_peripheral(node_id, peripheral_id, source=...)`
- `get_snapshot(only_in_use_peripherals=False)`
- `drain_events()`

Integration model (intended flow):

1. RRMLocal detects a location change for its node or for a peripheral in use.
2. RRMLocal sends an update event/message to RRMGlobal.
3. RRMGlobal routes it to `LocationManager`.
4. `LocationManager` normalizes the payload and updates centralized state.
5. Policies/schedulers/monitoring components can consume snapshot data or drained events.

### Brief literature/standards references

- **OGC IndoorGML**: indoor spatial model focused on navigation and topology.
  - https://www.ogc.org/standards/indoorgml/
- **buildingSMART IFC (ISO 16739)**: standard semantic model for built assets/spaces.
  - https://www.buildingsmart.org/standards/bsi-standards/industry-foundation-classes/
- **Indoor positioning systems overview**: practical technology tradeoffs (Wi-Fi, BLE, UWB, IMU, fusion).
  - https://en.wikipedia.org/wiki/Indoor_positioning_system
- **Classic Wi-Fi indoor localization references**:
  - RADAR (Bahl, Padmanabhan, INFOCOM 2000)
  - Horus (Youssef, Agrawala)

### Notes for this framework

- Prefer symbolic indoor hierarchy for allocation constraints; coordinates remain optional metadata.
- For low-cost deployments, prioritize static inventory + Wi-Fi/BLE before high-precision UWB.
- Legacy aliases are handled only at parsing time by normalization utilities; persisted JSON uses only canonical keys.
- `campus` is not mandatory for the indoor model adopted here; if needed later, it can be added as an optional extension field.

---

## Device Profiling

The framework can use pre-profiled performance data:

1. **node_catalog.json / node_inventory.json**: Compute-node types and logical
   node instances in `framework/board_specific_descriptors/`.
2. **DevicePerformancePerPartition.json**: Measured performance per partition per device

These files help the policy make informed placement decisions.

---

## Development Guidelines

### Adding a New Component

1. Place code in appropriate `core/` subdirectory
2. Follow existing import patterns
3. Use centralized logging
4. Update `__init__.py` files for clean imports

### Modifying Policies

1. Implement matching `GlobalPolicyBase` and `LocalPolicyBase` subclasses from
   `policy/Policy.py`, with the same public policy name.
2. Implement the interfaces described in the Policy System section.
3. Import both subclasses in `policy/PolicyUtils.py`; policy names are discovered
   from the imported global subclasses and used by the launchers/interfaces.
4. Restart the RRM components to load the new implementations.


## Troubleshooting

### Common Issues

**Application won't start:**

- Check JSON manifest validation
- Verify application files are in `applications/`
- Check RRMLocal nodes are connected
- Check Local's per-application environment preparation and dependency errors
- Verify `requires` constraints, inventory IDs and exclusive resource availability

**Communication failures:**

- Ensure firewall allows framework ports
- Point Local's `--global_ip` at Global and use the same `--global_port` on both
- Check network connectivity between nodes

---
