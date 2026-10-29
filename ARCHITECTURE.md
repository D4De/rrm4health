# RRM4Health Framework Architecture

This document describes the architectural design and organization of the RRM4Health (Runtime Resource Manager for Healthcare) framework.

## Overview

RRM4Health is a distributed runtime resource management system designed for healthcare applications. It enables dynamic partitioning and deployment of applications across heterogeneous compute nodes (laptops, single-board computers, cloud instances) based on configurable resource allocation policies.

### Key Capabilities

- **Dynamic Application Partitioning**: Split applications into tasks that can run on different nodes
- **Policy-Based Resource Allocation**: Pluggable policies for optimizing different objectives (battery life, performance, load distribution)
- **Heterogeneous Device Support**: x86_64, ARM (Raspberry Pi), server instances
- **Real-Time Monitoring**: Track CPU, memory, battery, network, disk usage
- **Graceful Lifecycle Management**: Clean startup, execution, and shutdown of distributed applications

---

## System Architecture

### High-Level View

```
┌─────────────────────────────────────────────────────────────┐
│                     User Interfaces                         │
│                   (CLI / GUI Clients)                       │
└────────────────────┬────────────────────────────────────────┘
                     │
                     │ ZeroMQ Messages
                     ▼
┌─────────────────────────────────────────────────────────────┐
│                     RRMGlobal                               │
│  ┌─────────────┐  ┌──────────────┐  ┌──────────────────┐   │
│  │   Node      │  │ Application  │  │   Message        │   │
│  │  Manager    │  │   Manager    │  │   Handler        │   │
│  └─────────────┘  └──────────────┘  └──────────────────┘   │
│  ┌─────────────────────────────────────────────────────┐   │
│  │         Performance Tracker & Policy                │   │
│  └─────────────────────────────────────────────────────┘   │
└──────────────────┬────────────────────────────┬────────────┘
                   │                            |
                   │                            |
                   │                            |
                   ▼                            ▼ 
        ┌────────────────────┐       ┌────────────────────┐
        │    RRMLocal        │       │    RRMLocal        │  (Multiple nodes)
        │  ┌──────────────┐  │       │  ┌──────────────┐  │
        │  │  Partition   │  │       │  │  Partition   │  │
        │  │  Manager     │  │       │  │  Manager     │  │
        │  └──────────────┘  │       │  └──────────────┘  │
        │  ┌──────────────┐  │       │  ┌──────────────┐  │
        │  │   Metrics    │  │       │  │   Metrics    │  │
        │  │   Manager    │  │       │  │   Manager    │  │
        │  └──────────────┘  │       │  └──────────────┘  │
        └─────────┬──────────┘       └─────────┬──────────┘
                  │                            │
                  ▼                            ▼
        ┌───────────────────┐        ┌───────────────────┐
        │  App Partitions   │        │  App Partitions   │
        │  (Processes)      │        │  (Processes)      │
        └───────────────────┘        └───────────────────┘
```

### Component Interaction

1. **User** interacts via CLI/GUI
2. **RRMGlobal** receives start app request
3. **ApplicationManager** parses manifest, selects configuration
4. **Policy** determines optimal node placement
5. **NodeManager** tracks available nodes and capabilities
6. **RRMGlobal** sends start partition commands to selected **RRMLocal** instances
7. **RRMLocal** starts application partition process via **PartitionManager**
8. **AppStarter** runs within partition process, executing tasks
9. **MetricsManager** collects performance data, reports to **RRMGlobal**
10. **PerformanceTracker** aggregates metrics for policy decisions

---

## Directory Structure

```
framework/
├── core/                           # Modular core components
│   ├── communication/              # Message passing infrastructure
│   │   ├── ChannelManagerApp.py   # Inter-partition communication
│   │   ├── ChannelManagerClient.py # ZeroMQ client (RRMLocal→RRMGlobal)
│   │   ├── ChannelManagerRouter.py # ZeroMQ router (RRMGlobal, RRMLocal)
│   │   ├── Message.py              # Message dataclasses
│   │   ├── MessageTypes.py         # Message type enums
│   │   └── OrchIF.py               # Application→RRMLocal interface
│   │
│   ├── models/                     # Data models
│   │   ├── Node.py                 # Node representation with capabilities
│   │   └── DescriptorSchema.py    # JSON manifest validation schemas
│   │
│   ├── monitoring/                 # Performance tracking
│   │   ├── MetricFields.py         # Metric type enums
│   │   ├── MetricsCollector.py    # Runtime metric collection
│   │   └── PerformanceTracker.py  # Performance profiling per partition
│   │
│   ├── rrm_global/                 # Global orchestration
│   │   ├── RRMGlobal.py            # Main orchestrator
│   │   ├── NodeManager.py          # Manages connected nodes
│   │   ├── ApplicationManager.py  # Manages application lifecycle
│   │   └── MessageHandler.py       # Processes incoming messages
│   │
│   ├── rrm_local/                  # Local node management
│   │   ├── RRMLocal.py             # Local node manager
│   │   ├── PartitionManager.py    # Manages local partitions
│   │   ├── MetricsManager.py      # Collects local metrics
│   │   ├── MessageHandlerLocal.py # Processes local messages
│   │   └── app_starter/            # Application execution engine
│   │       ├── AppStarter.py       # Main partition executor
│   │       ├── LifecycleManager.py # Setup/loop/cleanup phases
│   │       ├── TaskGraphManager.py # Task dependency orchestration
│   │       ├── ChannelSetupManager.py # Inter-partition channels
│   │       └── CodeIntegrityChecker.py # Runtime validation
│   │
│   ├── Utils.py                    # Common utility functions
│   └── logging_config.py           # Centralized logging
│
├── policy/                         # Resource allocation policies
│   ├── Policy.py                   # Base policy interface
│   ├── PolicySymmetricDistribution.py  # Even distribution
│   ├── PolicyMaximizeBatteryLife.py    # Battery-aware placement
│   └── PolicyUtils.py              # Policy loading utilities
│
├── applications/                   # App directories and sibling JSON descriptors
│
├── board_specific_descriptors/    # Device performance profiles
├── LaunchRrmGlobal.py           # RRMGlobal launcher
├── LaunchRrmLocal.py            # RRMLocal launcher
├── LaunchCli.py                  # CLI launcher
├── LaunchGui.py                  # GUI launcher
└── Config.py                       # System-wide constants
```

Development tools live in the repository-level `tools/` directory:
`CheckerJSON.py`, `AppSkeletonCreator.py`, `PrintUsbDevices.py` and `Prompt.txt`.

---

## Core Modules

### Communication Module (`core/communication/`)

Handles all message passing using ZeroMQ patterns.

**ChannelManagerRouter**: Implements router socket pattern
- Used by RRMGlobal to communicate with multiple RRMLocal instances
- Used by RRMLocal to communicate with local application partitions
- Receives messages from multiple clients, routes responses

**ChannelManagerClient**: Implements client socket pattern
- Used by RRMLocal to communicate with RRMGlobal
- Used by CLI/GUI to communicate with RRMGlobal
- Maintains single connection to router

**ChannelManagerApp**: Manages inter-partition communication
- Created by AppStarter for each running partition
- Sends/receives data between partitions (task outputs/inputs)
- Supports TCP socket channels

**Message**: Dataclass definitions for all message types
- Type-safe message construction
- Clear message contracts between components

**OrchIF**: Application interface to RRMLocal
- Applications use this to:
  - Stop execution (`stop_application()`)
  - Report device status (`send_status()`)
  - Communicate with framework

### Models Module (`core/models/`)

Data structures representing framework entities.

**Node**: Represents a compute node
- Stores capabilities (CPU, memory, battery, architecture)
- Tracks running partitions
- Maintains resource utilization metrics
- Used by both RRMGlobal (remote nodes) and RRMLocal (local node)

**DescriptorSchema**: JSON schema validation
- Validates application manifests
- Checks task dependencies
- Ensures configuration consistency

### Monitoring Module (`core/monitoring/`)

Performance tracking and profiling.

**MetricsCollector**: Collects runtime metrics
- CPU usage and frequency
- Memory utilization
- Battery level and power state
- Network throughput
- Disk usage

**ProcessMetricsCollector**: Per-process metrics
- CPU usage per partition process
- Memory usage per partition process
- Used for partition-level profiling

**PerformanceTracker**: Manages performance profiles
- Stores device performance per partition type
- Computes placement costs based on profiled data
- Updates profiles as new measurements arrive
- Persists to `DevicePerformancePerPartition.json`

### RRM Global Module (`core/rrm_global/`)

Global orchestration layer.

**RRMGlobal**: Main orchestrator
- Coordinates the entire distributed system
- Runs main event loop
- Delegates to specialized managers
- Handles graceful shutdown

**NodeManager**: Manages connected nodes
- Tracks node status (READY, BUSY, NOT_RESPONDING)
- Stores node capabilities and metrics
- Sends policy updates to nodes
- Detects unresponsive nodes

**ApplicationManager**: Manages application lifecycle
- Loads and validates manifests
- Selects deployment configuration using policy
- Tracks running applications
- Coordinates application start/stop across nodes
- Queues app start/stop requests

**MessageHandler**: Processes all incoming messages
- Routes messages to appropriate handlers
- Delegates to NodeManager/ApplicationManager
- Handles GUI connections and responses
- Coordinates policy changes

### RRM Local Module (`core/rrm_local/`)

Node-level execution layer.

**RRMLocal**: Local node manager
- Receives commands from RRMGlobal
- Manages local resources
- Runs main event loop
- Handles graceful shutdown
- Reports node status

**PartitionManager**: Manages application partitions
- Starts partition processes
- Tracks PIDs and client IDs
- Stops partitions cleanly
- Reaps zombie processes

**MetricsManager**: Collects local metrics
- Periodic metric collection
- Aggregates metrics from MetricsCollector
- Sends updates to RRMGlobal
- Collects per-partition process metrics

**MessageHandlerLocal**: Processes local messages
- Handles RRMGlobal commands (start/stop partition, policy change)
- Handles application messages (status updates)
- Updates local node status
- Delegates to PartitionManager/MetricsManager

**AppStarter** (`app_starter/`): Application execution engine
- Entry point for partition processes
- Loads application class dynamically
- Manages task lifecycle (setup, loop, cleanup)
- Enforces timeouts
- Validates task return types
- Handles inter-partition channels

**LifecycleManager**: Executes task phases
- Runs setup methods in dependency order
- Executes loop methods iteratively
- Runs cleanup methods in reverse order
- Enforces timeouts with signal handlers
- Propagates task outputs to dependent tasks

**TaskGraphManager**: Orchestrates task dependencies
- Computes dependency levels
- Determines execution order
- Validates task graph consistency

**ChannelSetupManager**: Configures partition channels
- Creates inter-partition communication channels
- Manages send/receive queues

**CodeIntegrityChecker**: Runtime validation
- Checks task return types match expected outputs
- Validates all required outputs are produced
- Catches inconsistencies during execution

---

## Policy System

Policies determine how applications are partitioned and placed across nodes.

### Policy Interface

All policies extend `Policy.py` and implement:
- `get_required_fields()`: Metrics needed for decisions
- `choose_configuration()`: Select deployment configuration
- `update_period()`: How often to collect metrics

### Built-in Policies

**PolicySymmetricDistribution**: Even load distribution
- Spreads partitions evenly across available nodes
- Minimizes maximum node load
- Good for general-purpose workloads

**PolicyMaximizeBatteryLife**: Battery-aware placement
- Prefers nodes connected to AC power
- Avoids battery-powered devices when possible
- Extends battery life of mobile nodes

### Adding Custom Policies

1. Create new policy class in `policy/` extending `Policy`
2. Implement required methods
3. Register in `PolicyUtils` by including the new policy file
4. Policy becomes available in CLI/GUI

---

## Application Lifecycle

### 1. Manifest Definition

Application defined in JSON with:
- Tasks and dependencies
- Executable information
- Deployment configurations
- Resource requirements

### 2. Deployment Request

User requests app start via CLI/GUI → RRMGlobal

### 3. Configuration Selection

1. ApplicationManager loads manifest
2. Policy evaluates each configuration
3. Best configuration selected based on:
   - Node availability
   - Resource requirements
   - Performance profiles
   - Policy objectives

### 4. Partition Placement

1. RRMGlobal sends `GlobalStartPartition` to selected RRMLocal instances
2. Each RRMLocal starts partition process
3. PartitionManager spawns AppStarter subprocess

### 5. Partition Execution

AppStarter in each partition:
1. Loads application class
2. Sets up inter-partition channels
3. Executes setup methods
4. Runs main loop iteratively:
   - Execute tasks in dependency order
   - Pass outputs between tasks and partitions
5. Executes cleanup methods
6. Reports completion/failure

### 6. Monitoring

During execution:
- MetricsManager collects node metrics
- PartitionManager tracks process metrics
- Metrics sent to RRMGlobal periodically
- PerformanceTracker updates profiles

### 7. Termination

Application stops when:
- Application calls `stop_application()`
- User requests stop via CLI/GUI
- Error/exception occurs

Cleanup sequence:
1. Stop signal sent to all partitions
2. Cleanup methods executed
3. Processes terminated
4. Resources released

---

## Communication Patterns

### Message Flow Examples

**Starting an Application:**
```
GUI → RRMGlobal: GuiStartApplication
RRMGlobal → Policy: choose_configuration()
RRMGlobal → RRMLocal₁: GlobalStartPartition
RRMGlobal → RRMLocal₂: GlobalStartPartition
RRMLocal₁ → Partition₁: (fork/exec AppStarter)
RRMLocal₂ → Partition₂: (fork/exec AppStarter)
RRMGlobal → GUI: GlobalStartApplicationResponse
```

**Periodic Monitoring:**
```
RRMLocal → MetricsCollector: collect_metrics()
RRMLocal → RRMGlobal: LocalPerformanceUpdate
RRMGlobal → PerformanceTracker: update_metrics()
```

**Inter-Partition Communication:**
```
Partition₁ → ChannelManagerApp: send(data)
ChannelManagerApp → (network socket) → ChannelManagerApp
ChannelManagerApp → Partition₂: receive(data)
```

**Policy Change:**
```
GUI → RRMGlobal: GuiChangePolicy
RRMGlobal → RRMLocal₁: GlobalSetPolicy
RRMGlobal → RRMLocal₂: GlobalSetPolicy
RRMLocal → MetricsManager: update_required_fields()
RRMGlobal → GUI: GuiChangePolicyResponse
```

---

## Concurrency and Thread Safety

### Threading Model

**RRMGlobal:**
- Main thread: Event loop, policy decisions, application management
- ChannelManager threads: Message sending/receiving
- Lock protects: `__clients` (NodeManager), `__running_apps` (ApplicationManager)

**RRMLocal:**
- Main thread: Event loop, metric collection
- ChannelManager threads: Message sending/receiving (2 managers)
- Lock protects: `__local_node_status`, partition list

**AppStarter (per partition):**
- Main thread: Task execution (setup, loop, cleanup)
- ChannelManager threads: Inter-partition communication
- Signal handlers: Timeout enforcement


---

## Error Handling and Resilience

### Graceful Degradation

- **Node failure**: Detected by periodic status checks, node marked NOT_RESPONDING
- **Partition failure**: Partition terminated, resources released, error reported
- **Timeout**: Setup/loop/cleanup timeouts enforced, process killed if exceeded
- **Invalid manifest**: Validation errors reported before deployment
- **Communication failure**: ZeroMQ handles reconnection, queues buffer messages

### Logging

Centralized logging configuration:
- Configurable levels: DEBUG, INFO, WARNING, ERROR
- Optional file output
- Component-specific loggers
- Consistent format across modules

---

## Testing and Development

### Development Mode

Use debug logging to trace execution:
```bash
python3 LaunchRrmGlobal.py --log_level DEBUG --log_file global.log
python3 LaunchRrmLocal.py --log_level DEBUG --log_file local.log
```

### Local Testing

Run entire system on one machine:
```bash
# Terminal 1
python3 LaunchRrmGlobal.py

# Terminal 2
python3 LaunchRrmLocal.py

# Terminal 3
python3 LaunchRrmLocal.py

# Terminal 4
python3 LaunchCli.py
```

### Distributed Testing

Run across multiple machines:
1. Start RRMGlobal on one machine
2. Start RRMLocal on each node with `--global_ip <global_ip>`
3. Start CLI/GUI on any machine with access to RRMGlobal

---
