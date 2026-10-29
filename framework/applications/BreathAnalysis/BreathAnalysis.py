import asyncio
import copy
from functools import partial
import traceback
from bleak import BleakClient, BleakScanner
import paho.mqtt.publish as publish
import paho.mqtt.client as mqtt
import logging
import time
import struct
import sys
import queue
from datetime import datetime
#import for the app logic
from Util.Preprocessing import Preprocessing
from Util.Dimension_Reduction import Dimension_Reduction
from Util.Spectrum_Analysis import Spectrum_Analysis
from Util.Processing import Processing
from Util.Acquisition import Acquisition
import Util.MadgwickQuaternion
import Util.ChangeData
from utilities_library.BleAcquisitionMngr import BleAcquisitionMngr
from utilities_library.MqttTransmissionMngr import MqttTransmissionMngr
import Util.SaveToFile
import json

import pandas as pd
import statistics
import scipy.stats as stats
import threading
import numpy as np
from collections import defaultdict

# Replace with your device name or address
MQTT_BROKER             = "localhost"
MQTT_PORT               = 1883
MQTT_TOPIC_RAW             = "aaac/campaign/imu"
# La pipeline del respiro richiede campioni RAW per calcolare i quaternioni.
RAW_ACQUISITION = True
MQTT_TOPIC_OUTPUT             = "aaac/campaign/breathanalysis"

#Parameters for the output
METHOD_OUTPUT = "FILE"
PATH_FILE = ""

#Parameters IMU5B35-IMU373B-IMUX7X7 20250907 0 10 True

ADAPTER = "hci0"


# expected input parameters
CAMPAIGN_TEMPLATE       = {"name": "", "sampling_frequency": 10, "raw": True, "window_size": 300, "step_size": 100}
BSN_IMUS = ""

preProcessing = Preprocessing()
dimensionReduction = Dimension_Reduction()
spectrumAnalysis = Spectrum_Analysis()
processing = Processing()
acquisition = Acquisition()


window_size = 300  # samples inside the window (Must be >=SgolayWindowPCA). 1 minute = 600 samples 
start = 0  # number of initial samples to skip (samples PER device)
stop = 0   # number of sample at which program execution will stop, 0 will run the txt file to the end
overlapping = 100  # Overlapping between a window and the following. 1=max overlap. MUST BE >= SgolayWindowPCA. The higher the faster -300
SgolayWindowPCA = 31  # original: 31.  MUST BE AN ODD NUMBER
fdev = 10  #frequenza di sampling
# filter thresholds
f_threshold_max = 1
f_threshold_min = 0.05

n_IMU = 3
frequency_channel_data = 10


Thorax = "thorax"
Abdomen = 'abdomen'
Reference = 'reference'

first_iteration = 1
#index_window = 0 


start_time = time.time()
indexes = []
cname = []
Tot_med = []
Tot_Iqr = []
Timestamps = []

class BreathAnalysis:
    # FRAMEWORK EXECUTION FLOW:
    # 1. All setup methods are called in dependency order
    # 2. Loop methods are called in dependency levels (round-robin within each level)
    # 3. Cleanup methods are called in reverse order
    #
    # IMPORTANT: AppStarter performs comprehensive validation before execution:
    # - Method existence validation (all required setup/loop/cleanup methods must exist)
    # - Task dependency topological ordering with cycle detection
    # - Return type consistency (only dict or None allowed in loop methods)
    # - Always same dictionary structure returned inside the same methods
    # - Unique key production validation (no two loop methods can return dictionaries with the same key)
    # - Parameter-production matching (all required parameters must be produced by other tasks)
    #
    # VARIABLE MANAGEMENT:
    # Define instance variables (self.variable_name) in setup methods for persistence.
    #
    # RETURN VALUE REQUIREMENTS:
    # Each loop method MUST return a dictionary (can be empty) with structure:
    # { key: value, ... }
    # - 'key': variable name to be used by dependent methods
    # - 'value': the actual data content
    # - All attributes needed by dependent tasks must be returned with exact matching names
    # - In case of unification (one taskY depends on multiple tasks) the attributes of taskY must be a sub-set of the attributes returned by the above tasks
    #
    # TASK EXECUTION LEVELS:
    # Tasks are organized by dependency levels. Higher levels execute before lower levels.
    # No execution order is guaranteed within the same level (parallel execution possible).
    # For your convenience, here is the task graph you defined in the JSON file:
    #
    #    ┌───────────────────┐
    #    │ setup_and_collect │
    #    └───────────────────┘
    #              │
    #              ││
    #               │
    # ┌──────────────────────────┐
    # │ TASK_READING_AND_PREPARE │
    # └──────────────────────────┘
    #               │
    #              ││
    #              │
    #      ┌───────────────┐
    #      │ PreProcessing │
    #      └───────────────┘
    #              │
    #              ││
    #               │
    #    ┌────────────────────┐
    #    │ DimensionReduction │
    #    └────────────────────┘
    #               │
    #               │
    #               │
    #     ┌──────────────────┐
    #     │ SpectrumAnalysis │
    #     └──────────────────┘
    #               │
    #               │
    #               │
    #        ┌────────────┐
    #        │ Processing │
    #        └────────────┘
    #               │
    #               │
    #               │
    #         ┌──────────┐
    #         │ SaveCSV  │
    #         └──────────┘
    #
    #
    # DO NOT MODIFY: this is needed for the correct functioning of the framework
    def set_framework(self, app, user_args=None):
        self._app = app  # this is the Application instance
        self._user_args = user_args

    # You have access to the following system methods via self._app:
    # - self._app.send_status(status): send device status updates to the RRM
    # - self._app.stop_application(): stop the application and inform the RRM
    #
    # The user_args are passed from by the user when starting the application and can be accessed via self._user_args.        
    
    ## Setup methods

    def setup(self):
        global METHOD_OUTPUT,PATH_FILE,MQTT_BROKER,MQTT_PORT
        # Global setup method called before any task-specific setup
        # Use this to initialize shared resources and instance variables
        # Return False to signal setup failure, otherwise return True or None
        self._imunames = self._user_args.get("imunames",None)
        self._peripheral_locations = self._user_args.get("peripheral_locations", None)
        self._adapter = self._user_args.get("adapter",None)
        self._campaignname = self._user_args.get("campaignname",None)
        self._samplingfreq = self._user_args.get("samplingfreq", None)
        METHOD_OUTPUT = self._user_args.get("method_output", None)
        PATH_FILE = self._user_args.get("path_FILE", None)
        MQTT_BROKER = self._user_args.get("host_DB", "localhost")
        MQTT_PORT = self._user_args.get("port_DB", 1883)
        self.IdDevice_Thorax = ''
        self.IdDevice_Abdomen = ''
        self.IdDevice_Reference = ''
        if MQTT_PORT is not None:
            MQTT_PORT = int(MQTT_PORT)
        
        CAMPAIGN_TEMPLATE["name"] = self._campaignname

        if PATH_FILE is None:
            PATH_FILE = ""
        PATH_FILE = ""
            
        if METHOD_OUTPUT == "FILE":
            print("Saving output in:" + PATH_FILE + CAMPAIGN_TEMPLATE["name"])        
        return True        

    def setup_and_collect_setup(self):
   # Run the asyncio event loop
        try:
            global  BSN_IMUS,PATH_FILE,METHOD_OUTPUT

            if not isinstance(self._imunames, str):
                raise ValueError("Il parametro 'imunames' è obbligatorio")
            if not isinstance(self._peripheral_locations, str):
                raise ValueError("Il parametro 'peripheral_locations' è obbligatorio")

            device_ids = [
                device_id.strip()
                for device_id in self._imunames.split("-")
                if device_id.strip()
            ]
            locations = [
                location.strip().casefold()
                for location in self._peripheral_locations.split("-")
                if location.strip()
            ]

            if len(device_ids) != len(locations):
                raise ValueError(
                    "Il numero di device in 'imunames' deve coincidere con il "
                    "numero di location in 'peripheral_locations'"
                )
            if len(set(device_ids)) != len(device_ids):
                raise ValueError("Sono presenti ID device duplicati")
            if len(set(locations)) != len(locations):
                raise ValueError("Sono presenti location duplicate")

            required_locations = {Thorax, Abdomen, Reference}
            received_locations = set(locations)
            missing_locations = required_locations - received_locations
            unknown_locations = received_locations - required_locations

            if missing_locations or unknown_locations:
                details = []
                if missing_locations:
                    details.append(f"mancanti: {sorted(missing_locations)}")
                if unknown_locations:
                    details.append(f"non riconosciute: {sorted(unknown_locations)}")
                raise ValueError(
                    "Location non valide (" + "; ".join(details) + "). "
                    "Location richieste: " + Thorax + " " + Abdomen + " " + Reference
                )

            device_by_location = dict(zip(locations, device_ids))
            BSN_IMUS = device_ids
            print("IMUs BSN: ", BSN_IMUS)

            CAMPAIGN_TEMPLATE["sampling_frequency"] = int(self._samplingfreq)
            CAMPAIGN_TEMPLATE["raw"] = RAW_ACQUISITION

            self.ble_manager = BleAcquisitionMngr()
            
            self.ble_manager.set_imus(BSN_IMUS)
            
            self.IdDevice_Thorax = device_by_location[Thorax]
            self.IdDevice_Abdomen = device_by_location[Abdomen]
            self.IdDevice_Reference = device_by_location[Reference]
            
            self.ble_manager.set_id_imus(BSN_IMUS)
            self.ble_manager.set_adapter(self._adapter)
            
            self.ble_manager.set_campaign(
                CAMPAIGN_TEMPLATE["name"],
                CAMPAIGN_TEMPLATE["sampling_frequency"],
                raw=CAMPAIGN_TEMPLATE["raw"],
                window_size=CAMPAIGN_TEMPLATE["window_size"],
                step_size=CAMPAIGN_TEMPLATE["step_size"],
            )
            
            if METHOD_OUTPUT == "FILE":
                self.writer_file = Util.SaveToFile.SaveToFile()
                self.writer_file.set_path(PATH_FILE)
                self.writer_file.set_name_file(CAMPAIGN_TEMPLATE["name"])
                
            
            self.db_mqtt_manager = MqttTransmissionMngr()
            self.db_mqtt_manager.set_db_mqtt(MQTT_BROKER,MQTT_PORT,MQTT_TOPIC_RAW)
            self.db_mqtt_manager.start_db_mqtt()
        
            self.packets_splitted_for_id = {
                device_id: [] for device_id in BSN_IMUS
            }
            
            if self._imunames is not None and CAMPAIGN_TEMPLATE["name"] is not None and CAMPAIGN_TEMPLATE["sampling_frequency"] is not None and CAMPAIGN_TEMPLATE["raw"] is not None:
                self.ble_manager.start_collection()
                self.ble_manager.wait_connection()
                print(CAMPAIGN_TEMPLATE)
                self._app.notify_peripherals_in_use(BSN_IMUS, "ble")
            else:
                self._app.stop_application()
                
            
        except Exception as e:
            traceback.print_exc()
            print(f"Setup error: {e}", flush=True)
            ble_manager = getattr(self, "ble_manager", None)
            if ble_manager is not None:
                try:
                    ble_manager.stop_collection()
                except Exception as cleanup_error:
                    print(
                        f"Errore durante l'arresto del BLE manager: {cleanup_error}",
                        flush=True,
                    )
            raise
        
        return True    

    def TASK_READING_AND_PREPARE_setup(self):
        # Setup for task 'TASK_READING_AND_PREPARE'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        self.first_iteration = 1
        self.index_window = 0
        return True

    def PreProcessing_setup(self):
        # Setup for task 'PreProcessing'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        return True

    def DimensionReduction_setup(self):
        # Setup for task 'DimensionReduction'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        return True

    def SpectrumAnalysis_setup(self):
        # Setup for task 'SpectrumAnalysis'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        return True

    def Processing_setup(self):
        # Setup for task 'Processing'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        return True

    def SaveCSV_setup(self):
        # Setup for task 'SaveCSV'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        return True

    ## Loop methods

    def setup_and_collect_loop(self):
        # Task logic for 'setup_and_collect' goes here
        # Example of a raw point: {'time': '2025-05-18T12:58:07.725063Z', 'ax': '0x0000', 'ay': '0x0000', 'az': '0x0000', 'gx': '0x0000',
        # 'gy': '0x0000', 'gz': '0x0000', 'imuid': 'IMU4E5A', 'mx': '0x0000', 'my': '0x0000', 'mz': '0x0000', 'ts': 130679349.0}
        #time.sleep(1/CAMPAIGN_TEMPLATE["sampling_frequency"])
        
        #Check if there are enough data
        ok = all(len(v) >= window_size for v in self.packets_splitted_for_id.values())
        
        while not ok:
            #Extract a point
            packet = self.ble_manager.get_packet(True)
            #print("Get a packet")
            csv_data_d = ",".join(f"{k}={v}" for k, v in packet.items())
            csv_data_d += ",c_id=" + CAMPAIGN_TEMPLATE["name"]
            
            self.db_mqtt_manager.put_row(csv_data_d)
            
            if "battery" in packet.keys():
                print(f"Battery level for IMU {packet['imuid']} received")
                continue
            
            if packet["ts"] is not None:
                self.packets_splitted_for_id[packet["imuid"]] = self.packets_splitted_for_id[packet["imuid"]] + [packet]
                
            #if METHOD_OUTPUT == "DB":
                #publish.single(topic=MQTT_TOPIC_RAW, payload=csv_data_d, hostname=MQTT_BROKER, port=MQTT_PORT)
                #csv_data_d = queue_csv_data.get()
                #packet_csv = dict(item.split("=") for item in csv_data_d.split(","))
                
                #if packet_csv["ts"] is not None:
                    #publish.single(topic=MQTT_TOPIC_RAW, payload=csv_data_d, hostname=MQTT_BROKER, port=MQTT_PORT)
                #loop = asyncio.get_running_loop()
                #pub = partial(publish.single, topic=MQTT_TOPIC_RAW, payload=csv_data_d, hostname=MQTT_BROKER, port=MQTT_PORT)
                #loop.run_in_executor(None, pub)           

            #Check if there are enough data
            ok = all(len(v) >= window_size for v in self.packets_splitted_for_id.values())


        # nuovo dizionario con i primi 300
        
        new_windows_of_data = {k: copy.deepcopy(v[:window_size]) 
                       for k, v in self.packets_splitted_for_id.items()}
        
        for k in self.packets_splitted_for_id.keys():
            self.packets_splitted_for_id[k] = self.packets_splitted_for_id[k][overlapping:]
        
        return {"new_windows_of_data":new_windows_of_data}

    def TASK_READING_AND_PREPARE_loop(self,new_windows_of_data):
        # Task logic for 'TASK_READING_AND_PREPARE' goes here
        time.sleep(0.3)
        if self.first_iteration == 1:
            self.first_iteration = 0
        else:
            self.index_window += overlapping
            
        message = new_windows_of_data
        # Obtain quaternion and Splitting data raw for Id IMU
        ################################################################################################
        data_raw_splitted_for_Id = {}
        quaternions_calculated = {}
        first_timestamp = str(min(int(first_message,16) for first_message in [v[0]["ts"] for v in message.values()]))
        print("FIRST TIMESTAMP:",first_timestamp)     
        
        for nameIMU in message.keys():
                
            q = []
            points_of_a_imu = message[nameIMU]

            with open(nameIMU + ".json", "w", encoding="utf-8") as f:
                json.dump(points_of_a_imu, f, indent=4, ensure_ascii=False)

                
            for i in range(len(points_of_a_imu)):
                ts = str(datetime.fromtimestamp(int(points_of_a_imu[i]['ts'], 16)))

                points_of_a_imu[i] = Util.MadgwickQuaternion.point_transformation(points_of_a_imu[i])
                quat = (Util.MadgwickQuaternion.MadgwickQuaternionUpdate(points_of_a_imu[i]["ax"],points_of_a_imu[i]["ay"],points_of_a_imu[i]["az"],points_of_a_imu[i]["gx"],
                                                                points_of_a_imu[i]["gy"],points_of_a_imu[i]["gz"],points_of_a_imu[i]["mx"],points_of_a_imu[i]["my"],points_of_a_imu[i]["mz"],1/10))
                quat.append(ts)
                q.append(quat)            

            quaternions_calculated[nameIMU] = q
                
        #Convert the arrays in a dataframe
        #...........
            
        data_raw_splitted_for_Id[self.IdDevice_Thorax] = pd.DataFrame(quaternions_calculated[self.IdDevice_Thorax], columns=['1', '2', '3', '4',"time_device"])      
        data_raw_splitted_for_Id[self.IdDevice_Thorax] = data_raw_splitted_for_Id[self.IdDevice_Thorax].reset_index(drop=True)  # reset the indexes order     
                   
        data_raw_splitted_for_Id[self.IdDevice_Abdomen] = pd.DataFrame(quaternions_calculated[self.IdDevice_Abdomen], columns=['1', '2', '3', '4',"time_device"])
        data_raw_splitted_for_Id[self.IdDevice_Abdomen] = data_raw_splitted_for_Id[self.IdDevice_Abdomen].reset_index(drop=True)  # reset the indexes order  

        data_raw_splitted_for_Id[self.IdDevice_Reference] = pd.DataFrame(quaternions_calculated[self.IdDevice_Reference], columns=['1', '2', '3', '4',"time_device"])
        data_raw_splitted_for_Id[self.IdDevice_Reference] = data_raw_splitted_for_Id[self.IdDevice_Reference].reset_index(drop=True)  # reset the indexes order  
            
            
        data_splitted_for_Id = acquisition.refining_a_dictionary_of_raw_data(start,data_raw_splitted_for_Id)

        #Remove quaternions of the pulse ....
        #data_splitted_for_Id.pop(IdDevice_pulse)

        data_splitted_for_Id, final_index = acquisition.cuts_excess_data(data_splitted_for_Id)

        mean_quaternions_splitted_for_ID, quaternions_arrays_splitted_for_ID = acquisition.prepare_other_data_for_the_elaboration(data_splitted_for_Id)

        #Extract the reference quaternions
        data_reference = data_splitted_for_Id.pop(self.IdDevice_Reference)
        mean_quaternions_references = mean_quaternions_splitted_for_ID.pop(self.IdDevice_Reference)
        quaternions_arrays_references = quaternions_arrays_splitted_for_ID.pop(self.IdDevice_Reference)
              
        #################################################################################################           
        
        print("index_window", self.index_window)
        
        return {"quaternions_arrays_splitted_for_ID":quaternions_arrays_splitted_for_ID,"mean_quaternions_splitted_for_ID":mean_quaternions_splitted_for_ID,
                "quaternions_arrays_references":quaternions_arrays_references,"mean_quaternions_references":mean_quaternions_references,"index_window":self.index_window,"first_timestamp":first_timestamp}
        
            

    def PreProcessing_loop(self,quaternions_arrays_splitted_for_ID,mean_quaternions_splitted_for_ID,quaternions_arrays_references,mean_quaternions_references,index_window,first_timestamp):
        # Task logic for 'PreProcessing' goes here
        data_prepocessed_splitted_for_ID = {}
        for IdDevice in quaternions_arrays_splitted_for_ID.keys():
            #print(mean_quaternions_splitted_for_ID[IdDevice])
            data_prepocessed_splitted_for_ID[IdDevice] = preProcessing.change_reference_quaternion(quaternions_arrays_splitted_for_ID[IdDevice],mean_quaternions_splitted_for_ID[IdDevice],0,window_size,quaternions_arrays_references,mean_quaternions_references)

        return {"data_prepocessed_splitted_for_ID":data_prepocessed_splitted_for_ID,"index_window":index_window,"first_timestamp":first_timestamp}

    def DimensionReduction_loop(self,data_prepocessed_splitted_for_ID,index_window,first_timestamp):
        # Task logic for 'DimensionReduction' goes here
        signals_reduced_splitted_for_ID = {}
        
        for IdDevice in data_prepocessed_splitted_for_ID.keys():
            window = data_prepocessed_splitted_for_ID[IdDevice].loc[0:0 + window_size]

            if window.isna().any().any():
                print("NaN trovati nella finestra PCA")
                print(window)
                data_prepocessed_splitted_for_ID = {}
                break
        
        if data_prepocessed_splitted_for_ID != {}:
            for IdDevice in data_prepocessed_splitted_for_ID.keys():
                signals_reduced_splitted_for_ID[IdDevice] = dimensionReduction.dimension_reduction_with_pca2(data_prepocessed_splitted_for_ID[IdDevice],0,window_size)

        return {"signals_reduced_splitted_for_ID":signals_reduced_splitted_for_ID,"index_window":index_window,"first_timestamp":first_timestamp}
    
    def SpectrumAnalysis_loop(self,signals_reduced_splitted_for_ID,index_window,first_timestamp):
        # Task logic for 'SpectrumAnalysis' goes here
        lowThresholds_splitted_for_ID = {}
        f_splitted_for_ID = {}
        pxx_splitted_for_ID = {}
        Signals_Fuse_splitted_for_ID = {}
        
        if signals_reduced_splitted_for_ID != {}:         
            #Add the name of the new signals to use for the Spectrum Analysis
            for IdDevice in signals_reduced_splitted_for_ID.keys():
                spectrumAnalysis.add_new_signal(IdDevice)
                        
            #Spectrum Analysis
            for IdDevice in signals_reduced_splitted_for_ID.keys():
                spectrumAnalysis.apply_savgol_filter(IdDevice,signals_reduced_splitted_for_ID[IdDevice],window_size,overlapping,SgolayWindowPCA)
                f_splitted_for_ID[IdDevice], pxx_splitted_for_ID[IdDevice], lowThresholds_splitted_for_ID[IdDevice] = spectrumAnalysis.find_peaks(IdDevice,index_window,window_size,overlapping,fdev,f_threshold_min)
                Signals_Fuse_splitted_for_ID[IdDevice] = spectrumAnalysis.get_a_fuse(IdDevice) #Signal Fuse contains all signals from individual IMUs with all windows processed so far

            #CHECK if find_peaks has failed => Flat signal
            for IdDevice in lowThresholds_splitted_for_ID.keys():
                
                if lowThresholds_splitted_for_ID[IdDevice] == None:
                    lowThresholds_splitted_for_ID = "None"
                    f_splitted_for_ID = "None"
                    pxx_splitted_for_ID = "None"
                    Signals_Fuse_splitted_for_ID = "None"
                    break
        else:
            lowThresholds_splitted_for_ID = "None"
            f_splitted_for_ID = "None"
            pxx_splitted_for_ID = "None"
            Signals_Fuse_splitted_for_ID = "None"                
                    
        return {"lowThresholds_splitted_for_ID":lowThresholds_splitted_for_ID,"Signals_Fuse_splitted_for_ID":Signals_Fuse_splitted_for_ID,
                "f_splitted_for_ID":f_splitted_for_ID,"pxx_splitted_for_ID":pxx_splitted_for_ID,"index_window":index_window,"first_timestamp":first_timestamp}
        
    def Processing_loop(self,lowThresholds_splitted_for_ID,Signals_Fuse_splitted_for_ID,f_splitted_for_ID,pxx_splitted_for_ID,index_window,first_timestamp):
        # Task logic for 'Processing' goes here
        
        if lowThresholds_splitted_for_ID != "None" and Signals_Fuse_splitted_for_ID != "None" and f_splitted_for_ID != "None" and pxx_splitted_for_ID != "None":
            
            lowThreshold = min(lowThreshold for lowThreshold in lowThresholds_splitted_for_ID.values())  # the low threshold is computed as the minimum between the thoracic and the abdominal one    

            Max_Ind_splitted_for_ID = {}
            Min_Ind_splitted_for_ID = {}
            SmoothSmoothes_splitted_for_ID = {}
                    
            #ABDOMEN MAXIMA AND MINIMA DETECTION Processing
            for IdDevice in lowThresholds_splitted_for_ID.keys():
                        
                if IdDevice == self.IdDevice_Abdomen: #if the signal is the addome
                    Signals_Fuse_splitted_for_ID[IdDevice] = - Signals_Fuse_splitted_for_ID[IdDevice]
                            
                Max_Ind_splitted_for_ID[IdDevice], Min_Ind_splitted_for_ID[IdDevice], SmoothSmoothes_splitted_for_ID[IdDevice] = processing.detect_MAXIMA_MINIMA(Signals_Fuse_splitted_for_ID[IdDevice],f_splitted_for_ID[IdDevice],pxx_splitted_for_ID[IdDevice],lowThreshold,f_threshold_max,f_threshold_min,fdev,index_window,window_size,IdDevice)
                        
                if IdDevice == self.IdDevice_Abdomen: #if the signal is the addome
                    Signals_Fuse_splitted_for_ID[IdDevice] = - Signals_Fuse_splitted_for_ID[IdDevice]
                    
            # TOTAL RESPIRATORY SIGNAL
                    
            Max_Ind_Tot, Min_Ind_Tot  = processing.calculate_total_respiratory_signal(SmoothSmoothes_splitted_for_ID[self.IdDevice_Thorax],SmoothSmoothes_splitted_for_ID[self.IdDevice_Abdomen],fdev,index_window,window_size,overlapping,lowThreshold,f_threshold_max)
        else:
            Max_Ind_Tot, Min_Ind_Tot = np.array([]), np.array([])

            
        return {"Max_Ind_Tot":Max_Ind_Tot,"Min_Ind_Tot":Min_Ind_Tot,"index_window":index_window,"first_timestamp":first_timestamp}

    def SaveCSV_loop(self,Max_Ind_Tot,Min_Ind_Tot,index_window,first_timestamp):
        # Task logic for 'SaveCSV' goes here
        global Tot_med, Tot_Iqr, indexes, Timestamps
        T_Tot, Ti_Tot, Te_Tot, fB_Tot = [], [], [], []

        if Max_Ind_Tot.size != 0 or Min_Ind_Tot.size != 0:                
            for i in range(len(Min_Ind_Tot)):
                te = (Min_Ind_Tot[i] - Max_Ind_Tot[i]) / fdev
                ti = (Max_Ind_Tot[i + 1] - Min_Ind_Tot[i]) / fdev
                Ti_Tot.append(ti)
                Te_Tot.append(te)
                ttot = ti + te
                fb = (1 / ttot) * 60
                T_Tot.append(ttot)
                fB_Tot.append(fb)
            try:
                #MEDIANA
                Tmed_Tot = statistics.median(T_Tot)
                Timed_Tot = statistics.median(Ti_Tot)
                Temed_Tot = statistics.median(Te_Tot)
                fBmed_Tot = statistics.median(fB_Tot)
                #fBspectrum_T = fBspectrum_T * 60
                duty_med_Tot = statistics.median([float(Ti_Tot / T_Tot) for Ti_Tot, T_Tot in zip(Ti_Tot, T_Tot)])
                #INTERQUARTILE
                Tirq_Tot = stats.iqr(T_Tot)
                Tiirq_Tot = stats.iqr(Ti_Tot)
                Teirq_Tot = stats.iqr(Te_Tot)
                fBirq_Tot = stats.iqr(fB_Tot)
                duty_irq_Tot = stats.iqr([float(Ti_Tot / T_Tot) for Ti_Tot, T_Tot in zip(Ti_Tot, T_Tot)])
                Tot_med.append([fBmed_Tot, Timed_Tot, Temed_Tot, duty_med_Tot])
                Tot_Iqr.append([fBirq_Tot, Tiirq_Tot, Teirq_Tot, duty_irq_Tot])
                Timestamps.append(first_timestamp)
                print("fB_median_Tot, Ti_median_Tot, Te_median_Tot, duty_median_Tot\n", [round(i, 2) for i in Tot_med[-1]])
                print("fB_irq_Tot, Ti_irq_Tot, Te_irq_Tot, duty_irq_Tot\n", [round(i, 2) for i in Tot_Iqr[-1]], "\n")
                print("--- Tempo trascorso: %s secondi ---" % round((time.time() - start_time) / 60, 2))
                print("--- Tempo acquisizione:", round(index_window / 600, 2), "secondi ---")
                print("--------------------------------------------------------------------------------------\n")
            except Exception as e:
                print("Errore calcolo parameteri totale:", e)
                Tot_med.append([np.nan, np.nan, np.nan, np.nan])
                Tot_Iqr.append([np.nan, np.nan, np.nan, np.nan])
        else:
            print("Errore calcolo parameteri totale, Segnale non valido")
            Tot_med.append([np.nan, np.nan, np.nan, np.nan])
            Tot_Iqr.append([np.nan, np.nan, np.nan, np.nan])
            fBmed_Tot = "None"
            Timed_Tot = "None"
            Temed_Tot = "None"
            duty_med_Tot = "None"
            fBirq_Tot = "None"
            Tiirq_Tot = "None"
            Teirq_Tot = "None"
            duty_irq_Tot = "None"
            
        indexes.append(index_window)
        cname.append(CAMPAIGN_TEMPLATE["name"])
        
        #If DB is active then save the parameters there
        if METHOD_OUTPUT == "DB":
            csv_data_d = "index=" + str(index_window)
            csv_data_d += (",fB_median_Tot="+ str(fBmed_Tot) + ",Ti_median_Tot="+ str(Timed_Tot)
            +",Te_median_Tot="+ str(Temed_Tot) +",duty_median_Tot="+ str(duty_med_Tot)
            + ",fB_irq_Tot="+str(fBirq_Tot)+",Ti_irq_Tot="+str(Tiirq_Tot)+",Te_irq_Tot="+str(Teirq_Tot)+",duty_irq_Tot="+str(duty_irq_Tot)
            + ",ts=" + str(first_timestamp) + ",cname=" + CAMPAIGN_TEMPLATE["name"] +"ba" + ",c_id=" + CAMPAIGN_TEMPLATE["name"])
            

            publish.single(topic=MQTT_TOPIC_OUTPUT, payload=csv_data_d, hostname=MQTT_BROKER, port=MQTT_PORT)
            print("Publishing on MQTT: ",MQTT_BROKER," port= ",MQTT_PORT," topic= ",MQTT_TOPIC_OUTPUT, " with cname= ",CAMPAIGN_TEMPLATE["name"]+ "_ba")
            print("Payload: ",csv_data_d)
                        
        return {}
    
    ## Cleanup methods

    def setup_and_collect_cleanup(self):
        # Cleanup for task 'setup_and_collect'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        print("Stopping IMUs ....")
        print("Waiting stop acquisition")
        self.ble_manager.stop_collection()
        print("Acquisition stopped")
        self._app.notify_peripherals_released(BSN_IMUS)
        
        
        self.db_mqtt_manager.stop_db_mqtt()
        print("MQTT STOPED")
        return True

    def TASK_READING_AND_PREPARE_cleanup(self):
        # Cleanup for task 'TASK_READING_AND_PREPARE'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        return True

    def PreProcessing_cleanup(self):
        # Cleanup for task 'PreProcessing'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        return True

    def DimensionReduction_cleanup(self):
        # Cleanup for task 'DimensionReduction'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        return True

    def SpectrumAnalysis_cleanup(self):
        # Cleanup for task 'SpectrumAnalysis'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        return True

    def Processing_cleanup(self):
        # Cleanup for task 'Processing'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        return True

    def SaveCSV_cleanup(self):
        
        global Tot_med, Tot_Iqr, indexes, Timestamps, METHOD_OUTPUT,PATH_FILE,MQTT_BROKER,MQTT_PORT
        # Cleanup for task 'SaveCSV'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        dftot = pd.DataFrame(Tot_med, columns=["fB_median_Tot", "Ti_median_Tot", "Te_median_Tot", "duty_median_Tot"])
        #dfa = pd.DataFrame(PCA_A, columns=["fBmedian_Abdomen", "Ti_median_Abdomen", "Te_median_Abdomen", "duty_median_Abdomen"])
        #dft = pd.DataFrame(PCA_T, columns=["fB_median_Thorax", "Ti_median_Thorax", "Te_median_Thorax", "duty_median_Thorax"])
        #dfiqra = pd.DataFrame(SD_A, columns=["fBirq_Thorax", "Tiirq_Thorax", "Teirq_Thorax", "duty_irq_Thorax"])
        #dfiqrt = pd.DataFrame(SD_T, columns=["fBirq_Abd", "Tiirq_Abd", "Teirq_Abd", "duty_irq_Abd"])
        dfiqrtot = pd.DataFrame(Tot_Iqr, columns=["fBirq_Tot", "Tiirq_Tot", "Teirq_Tot", "duty_irq_Tot"])
        tot = pd.concat([dftot, dfiqrtot], axis=1)


        tot['index'] = indexes
        tot = tot.set_index('index')
        
        tot['cname'] = cname
        #tot = tot.set_index('cname')
        
        if METHOD_OUTPUT == "FILE":
            self.writer_file.save_dataframe_to_csv(tot)

            
        print("--- Computing time: %s minutes ---" % round((time.time() - start_time)/60, 2))
        print("END")
        return True

    def cleanup(self):
        # Global cleanup method called after all task-specific cleanup
        # Use this to release shared resources
        # Return False to signal cleanup failure, otherwise return True or None
        return True
