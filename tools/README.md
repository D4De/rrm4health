# Development tools

Utilities for validating application descriptors and generating the Python
application skeleton. These tools support development; 

## Directory structure

```text
tools/
├── README.md
├── CheckerJSON.py            # Descriptor schema and consistency checks
├── AppSkeletonCreator.py     # Python skeleton generator
├── Prompt.txt                # Prompt for AI-assisted application integration
└── PrintUsbDevices.py        # Script to print Device path,VendorID, ProductID,Product name and Bus of the USB devices
```

`__pycache__/`, when present, is a generated Python cache, not source code.

## Validate a descriptor

Use the project's Python environment. The validator requires `jsonschema` in
addition to the core dependencies. From the repository root:

```bash
python3 -m pip install -r requirements.txt
python3 -m pip install jsonschema
PYTHONPATH=framework python3 tools/CheckerJSON.py applications_repo/Battery_BLE/Battery_BLE.json
```

`PYTHONPATH=framework` makes the framework's `core` package available to the
tools. The checker accepts a positional descriptor path and checks the schema
and consistency constraints, including references to tasks and partitions.
Look for `VALID` in its output: the current command-line wrapper does not set
a failing exit status when validation returns an error. 

## Generate an application skeleton

First create your application's descriptor, for example
`applications_repo/MyApplication/MyApplication.json`. Then run:

```bash
cd applications_repo/MyApplication
PYTHONPATH=../../framework python3 ../../tools/AppSkeletonCreator.py \
    --manifest_name MyApplication.json
```

The creator validates the descriptor and writes `<name>.py` in the **current
working directory**, using the descriptor's `name`. It generates the framework
hook, global setup/cleanup methods, task setup/loop/cleanup methods and a task
graph comment. Implement the actual processing and resource management yourself.

**An existing output file is overwritten.** Generate only for a new application,
or use a scratch directory when comparing an updated descriptor with existing
code.

## AI-assisted integration

[Prompt.txt](Prompt.txt) provides instructions for adapting a monolithic script
to the generated task structure. Supply your descriptor, generated skeleton,
original script and the current shared-manager examples and implementations.
This prompt has been tested with ChatGPT Sol mid thinking effort and also with Claude free version.


## Related documentation

- [Application development guide](../applications_repo/ApplicationDevelopment.md)
- [Application repository and installation](../applications_repo/README.md)
- [Shared acquisition and transmission managers](../utilities_library/README.md)
- [Startup tutorial](../HowToStart.md)
