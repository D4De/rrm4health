# Sensor Position Comparison

This repository contains data recorded with Nilspods synchronized with Qualisys motion capture data.
 
Inside the data folder are recorded sessions from 14 different test subjects which again contain folders with the recorder IMU and the motion capture data.
Additionally, the meta data of the recorded sessions is included in a json document for each subject respectively.

Inside the qualysis_project folder are the used calibration set ups for the recordings at the Frauenhofer Institut Nuremberg.
Also, the AIM model containing the named marker positions is available.

The complete setup of this experiment set is documented in the `setup_docu` directory.
It contains a detailed description of the performed tests and images to visualize the set up.

**When working with the data, always use the provided data loader library to avoid errors**

## Citation

If you use the dataset please cite TODO

## Measurement Errors

**THIS IS IMPORTANT INFORMATION! READ IT BEFORE WORKING WITH THE DATA!**

1. The cavity sensors for the left foot of the subjects "8d60", "cb3d", and "cdfc" are rotated by 180 deg compared to
the images in the measurement setup.
The function `sensor_position_dataset_helper.get_session_df` applies rotations to fix that on loading the data.
**Use this function or `sensor_position_dataset_helper.get_imu_test` to load the data and everything should be correct** 
2. Subject **6dbe** was measured twice, because one of the insole did not seem to work for the first measurement.
The first measurement is therefore missing one sensor file.
The measurement with the folder name **6dbe_2** is the correct one containing data from all sensors.


## Handle the data

### Download the data

TODO:

#### For MaD-Lab Members

If you are a member of the FAU MaD-Lab and have access to our intranet, you can download the data from our 
[internal git repo](https://mad-srv.informatik.uni-erlangen.de/MadLab/data/sensorpositoncomparison). 

The version published on Zenodo corresponds to the git commit: TODO

The repo uses git-lfs to handle the larger binary files.
Either use the download button in the top right of the repo or clone the data with git as explained below.
To clone the data you need [git](https://git-scm.com/book/en/v2/Getting-Started-Installing-Git) and 
[git-lfs](https://help.github.com/en/articles/installing-git-large-file-storage) installed.

Then you can run:

```
# ssh
git clone git@mad-srv.informatik.uni-erlangen.de:MadLab/data/sensorpositoncomparison.git

# https
git clone https://mad-srv.informatik.uni-erlangen.de/MadLab/data/sensorpositoncomparison.git
```

### Install the helper module

To handle the data, it is recommended to install the helper module, which can be found 
[here](https://github.com/mad-lab-fau/sensor_position_dataset_helper).

```
pip install sensor_position_dataset_helper
```
 
The helper module provides high level function to load and access the data.
See the documentation of the loader package for more information.
You should always use the package when accessing the data to prevent issues.

### Scripts

The `scripts` subfolder contains scripts that were to postprocess the data in this repo.
If you want to rerun this postprocessing, run `poetry install` in the root of the data repository.
This will install all versions of all packages that were used to generate the results.
Then you can run the scripts using: `poetry run python ./scripts/<script-name>.py`.

## Understand the data

The data has the following structure:

```
sensorpositoncomparison
│   README.md
├── scripts  # scripts for all automated steps of the performed data preprocessing
│
├── qualysis_project  # Should be used when manipulating the data in QTM
│   ├── AIM models  # Models for marker autodetection
│   │   Settings.qtmproj
|
├── calibrations # The calibration files of all the used nilspods
|
├── data
|   ├── <subject_id>
|   |   ├── mocap
|   |   |   |   <test_name>.qtm  # Raw qtm file, can be used to reprocess all data
|   |   |   |   <test_name>.c3d  # c3d export of post processed qtm data
|   |   |   |   <test_name>_steps.csv  # Results of automatic step detection on mocap data
|   |   |
|   |   ├── imu
|   |   |   |   NilsPod-<sensor_id>_<record_datetime>.bin  # Raw NilsPod binary file
|   |   |   
|   |   |   meta_data.json  # Subject metadata (see more below)
|   |   |   manual_stride_border.csv  # Manually annotated IMU stride borders 
|   
|   global_meta_data.json  # Global metadata of the dataset (see more below)
|   pyproject.toml  # The required python dependencies to run the scripts
|   poetry.toml  # The frozen python dependencies to reproduce the exact output of the preprocessing
|
```

### Global Metadata

Contains general information about the measurement.
This includes:

- measurement_order: order in which the participants were measured on the measurement day.

### Subject Metadata

Subject specfic metadata.
This includes:

- sensors: map linking sensor-ids to the actual recording positions
- mocap_test_start: Start-times of the individual mocap measurements in **UTC+02** timezone.
    This can be used to find the corresponding sensor data. Note that the sensordata timestamps are in **UTC+00**.
    See [Time Sync](#time-sync) for further details.
- imu_tests: The start and end date and index of all tests in the continuous IMU datastream.
    This can be used to extract the tests synchronised with the mocap data.
- shoe_size: The EU shoe size of the pair of shoes the subject wore during the test

### Post Processing

All Mocap data was manually post processed using the QTM 2019 software.
Goal of the post processing was to maximise the coverage and quality of the marker tracking.
As final step of the procedure a **gap fill with the size of 80 ms** was performed.
The final results was saved in the `.qtm` file (modifiable) and exported as `.c3d` for further processing.
None of the files were cut to preserve the original start and end values and hence the sync with the sensor system.

**Note:** In the C3D format, missing markers are exported as having a position of `[0, 0, 0]`.
These values should be replaced by `NaN`'s in further processing steps.

### Step/Stride Detection

#### IMU

The file `manual_stride_border.csv` for each subject contains the start and stop values of all strides in the dataset.
The strides are annotated manually by visual inspection of the RAW IMU signal.
The values are provided in **IMU samples** since start of the session.
Because all IMU sensors were synchronised, the timestamps can be used for all of them, **if they are loaded and
synchronised together** (use `get_session_df` for this).
Other than the Mocap stride borders, these stride borders also contain strides that were performed in between gait tests.
Therefore, this annotation should be used if it is important that **all** strides of the dataset are annotated.

The start/stop of a stride is labeled at the first minima in the GyrY (lateral axis) signal after the Midstance.
The labeling was done based on the instep sensor.
For initiation strides the first minima before the swing phase is labeled.
Termination strides are not labeled, except another minima occured that indicated a foot lift.
The stride borders can be used equivalently to the output of a DTW analysis based on 
[Barth et al.](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5796275/).

The manual annotation was performed by Nils Roth <nils.roth@fau.de> and Arne Küderle <arne.kuederle@fau.de>.

All strides are exported to csv with the following column headers:

- s_id: A unique s_id for any given subject. The same s_id is used for the mocap strides (see below)
- start: The start of the manual labeled imu stride in samples since start of the recording
- end: The end of the manual labeled imu stride in samples since start of the recording

#### Mocap

For each mocap test a corresponding file named `<test_name>_steps.csv` exists, which contains the results of an 
semi-automated stride detection.
The step detection uses the coordinate based HS and TO detection algorithm developed by 
[Zeni et al.](https://www.sciencedirect.com/science/article/abs/pii/S0966636207001804).
For the algorithms the marker with the labels `R/L_FCC` (heel), `R/L_TOE` (toe), and `L5` (sacrum) were used.

The X-direction (direction of movement) was determined as follows:

- The "hip-plane" is defined as the plane containing the 3 hip marker (`R\L_IAC` and `L5`)
- The sagittal plan is defined as being perpendicular to the hip-plane while cutting the triangle created by the hip 
  markers in half through the `L5` marker.
- The forward direction was defined as the cross product between the sagittal plane normal at each point in time and 
  the upwards direction (`[0, 0, 1]`). The sagittal plane normal was defined in a way that the cross product resulted 
  in the forward and not the backwards direction.

Further a mid-stance/minimal-velocity detection was performed and a "min_vel" event was identified analogous to
[Rampp et al.](https://ieeexplore.ieee.org/document/6949634) based on the combined signal energy of velocity of the heel
and the toe marker.

Before applying the stride segmentation, all invalid marker postions (i.e. when the marker could not be tracked) were 
replaced with `NaN`'s to avoid wrongly detecting minima/maxima in the distances.

To avoid false-positives for the event detection, the manual stride labels of the IMU data (see previous sections) are
used to define regions of interest.
Within each of the manual strides for exactly one IC (HS), TC (TO), and min_vel (MS) is searched.
Strides were removed when the events could not be detected in the correct order (TC, IC, min_vel) or any of the markers
used in the detection (`R\L_IAC`, `L5`, and the `TOE` and `FCC` marker of the foot the stride belongs to) had any NaNs
in the manual label stride.

All valid strides are exported to csv with the following column headers:

- s_id: A unique s_id for any given subject. This s_id corresponds to the s_id in the manual IMU labels
- start: The start of the manual labeled imu stride converted into frames since start of the gait test
- end: The end of the manual labeled imu stride converted into frames since start of the gait test
- foot: foot for which the stride was detected ("left" or "right")
- ic: the position of the initial contact. The value is provided in frames since the start of the gait test.
- tc: the position of the terminal contact. The value is provided in frames since the start of the gait test.
- min_vel: the position of minimal marker velocity withing the search region. The value is provided in frames since the
  start of the gait test.

For further details see `scripts/step_segmentation.py`.


### Time Sync

All sensors and the Qualysis system are fully synchronsied to a sample/frame level.
To use the synchronisation the following steps need to be performed.

The sensors need to be treated as a `SyncedSession` (see 
[NilsPodLib](https://github.com/mad-lab-fau/NilsPodLib) for details) and 
need to be cut to the sync region.
To make sure the synchronisation always works correctly, `sensor_position_dataset_helper.helper.get_session_df` should
always be used to load the data.

The start of each MoCap measurement needs to be linked to a falling edge in the analog signal of the "sync" NilsPod.
This sensor was directly connected to the camera system and recorded a low value whenever the cameras were recording 
(and a high value otherwise).
Using the timestamps from the subject metadata the correct falling edge for each test can be identified in the sensor 
data.

The metadata contains the start timestamp for the mocap system and the start and stop timestamps/sample of the exact
samples in the imu data.
This information can be used to directly extract a specific test from the IMU datastream 
(see `sensor_position_dataset_helper.helper.get_test`).
The imu timestamps in the metadata are generated by `scripts/extract_tests.py`).

To compare the different datastreams, the camerastream needs to be interpolated to the higher sampling rate of the
sensor (100 Hz vs 204.8 Hz).

### Calibrations

The sensors were calibrated using a Ferraris Calibration.
The results of these calibrations are stored in the `calibrations` folder.
The calibrations are automatically applied to the data on loading when using the data loader library.
