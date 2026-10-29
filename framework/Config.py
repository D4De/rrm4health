# Channel Manager Ports
import os

# Get the Framework directory path
FRAMEWORK_DIR = os.path.dirname(os.path.abspath(__file__))

START_PORT_CHANNELS = 38866
END_PORT_CHANNELS = 39680

# Performance Tracker
MODIFIED_DEVICE_PERFORMANCE_COST = 1
NEW_DEVICE_COST = 5
NEW_PARTITION_COST = 10
NEW_APP_COST = 100

DIFFERENT_FREQUENCY_SCALER = 1
DIFFERENT_CORES_SCALER = 10
DIFFERENT_ARCHITECTURE_COST = 1000

CHANGES_THRESHOLD = 200 

# File Paths and Identifiers
DEVICE_PERFORMANCES_PER_PARTITION_FILE = os.path.join(FRAMEWORK_DIR, "board_specific_descriptors", "DevicePerformancePerPartition.json")
NODE_CATALOG_FILE = os.path.join(FRAMEWORK_DIR, "board_specific_descriptors", "node_catalog.json")
NODE_INVENTORY_FILE = os.path.join(FRAMEWORK_DIR, "board_specific_descriptors", "node_inventory.json")
AUTO_START_APPLICATIONS_FILE = os.path.join(FRAMEWORK_DIR, "auto_start_applications.json")
APPLICATION_INFO_FILE = "_application_info_.json"
DEFAULT_APP_ID = "test1"

# RRM Global Configuration

MANIFEST_FOLDER = os.path.join(FRAMEWORK_DIR, "applications") + os.sep
UPDATE_PERIOD = 1 # seconds
GLOBAL_SNAPSHOT_DETAIL_DEFAULT = "policy"  # one of: minimal, policy, full

# ZMQ Configuration
ZMQ_POLL_TIMEOUT = 1000  # milliseconds
ZMQ_RECV_SLEEP = 0.1  # seconds for busy wait fallback
ZMQ_LINGER_TIMEOUT = 0  # milliseconds to wait for pending messages on close
ZMQ_SEND_TIMEOUT = 1000  # milliseconds for send operations
ZMQ_RECV_TIMEOUT = 1000  # milliseconds for receive operations

# Logging Configuration
LOG_LEVEL = "INFO"  # DEBUG, INFO, WARNING, ERROR, CRITICAL

# Timeout Configuration (seconds)
DEFAULT_SETUP_TIMEOUT = 60
DEFAULT_LOOP_TIMEOUT = 60
DEFAULT_CLEANUP_TIMEOUT = 60
THREAD_JOIN_TIMEOUT = 2.0
STATUS_UPDATE_INTERVAL = 10  # seconds between status updates

# Queue Configuration
QUEUE_GET_TIMEOUT = 1  # seconds
QUEUE_POLL_TIMEOUT = 0.1  # seconds

# Metrics Configuration
METRICS_ERROR_VALUE = -1.0  # Default value for metrics errors
METRICS_MAX_CPU_PERCENT = 100.0  # Maximum CPU percentage

# Power Configuration
CPU_HIGH_USAGE_THRESHOLD = 80.0  # Percentage
CPU_MAX_USAGE_THRESHOLD = 90.0  # Percentage

