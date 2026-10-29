# Allow both direct script execution and package imports from the repository root.
import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

import copy
import math

from utilities_library.BleAcquisitionMngr import BleAcquisitionMngr
from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr
from utilities_library.MqttTransmissionMngr import MqttTransmissionMngr


window_size = 300
overlapping = 100

# Scegliere il collegamento da usare: "wifi" oppure "ble".
# Per frequenze di trasmissione elevate e' meglio usare il manager WiFi;
# per frequenze basse si puo' usare il manager BLE.
TRANSPORT = "wifi"

# Scegliere il tipo di dati: "raw" oppure "features".
# RAW invia tutti i singoli campioni e quindi genera piu' traffico.
# FEATURES calcola i valori riassuntivi sulla IMU e invia un pacchetto per finestra.
ACQUISITION_MODE = "features"

# Parametri comuni ai manager WiFi e BLE.
CAMPAIGN_NAME = "campaign01"
SAMPLING_FREQUENCY = 10
FEATURE_WINDOW_SIZE = 300
FEATURE_STEP_SIZE = 100

# Nomi trasmessi dalle IMU e nomi che l'applicazione usera' nei pacchetti.
IMU_NAMES = ["IMUX", "IMUY", "IMUZ"]
IMU_IDS = ["device1", "device2", "device3"]

# In WiFi ogni IMU va associata al proprio indirizzo IP oppure MAC.
WIFI_IMUS = {
    "IMUX": "192.168.1.10",
    "IMUY": "192.168.1.11",
    "IMUZ": "192.168.1.12",
}
WIFI_INTERFACE = "wlan0"
WIFI_SSID = "nome_rete"
WIFI_PASSWORD = "password_rete"

# Database/topic per l'output del processing. E' volutamente separato dal
# database che riceve i pacchetti grezzi o le feature appena acquisite.
OUTPUT_MQTT_BROKER = "XXX.XXX.XXX.XXX"
OUTPUT_MQTT_PORT = 1883
OUTPUT_MQTT_TOPIC = "topic/breathanalysis"

RAW_MQTT_BROKER = "XXX.XXX.XXX.XXX"
RAW_MQTT_PORT = 1883
RAW_MQTT_TOPIC = "topic/imu"

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

        # Global setup method called before any task-specific setup
        # Use this to initialize shared resources and instance variables
        # Return False to signal setup failure, otherwise return True or None

        # + Enter additional input parameters for your application based on what you described in the JSON.
             
        return True        

    def setup_and_collect_setup(self):
        raw = ACQUISITION_MODE == "raw"
        if ACQUISITION_MODE not in ("raw", "features"):
            raise ValueError("ACQUISITION_MODE deve essere 'raw' o 'features'")

        # Per frequenze di trasmissione elevate e' meglio usare il manager WiFi;
        # per frequenze basse si puo' usare il manager BLE.
        if TRANSPORT == "wifi":
            self.imu_manager = WifiAcquisitionMngr()
            self.imu_manager.set_imus(WIFI_IMUS)
            self.imu_manager.set_id_imus(IMU_IDS)
            self.imu_manager.set_access_point(
                WIFI_INTERFACE,
                WIFI_SSID,
                WIFI_PASSWORD,
            )
        elif TRANSPORT == "ble":
            self.imu_manager = (
                BleAcquisitionMngr()
            )
            self.imu_manager.set_imus(IMU_NAMES)
            self.imu_manager.set_id_imus(IMU_IDS)
            self.imu_manager.set_adapter("hci0")
        else:
            raise ValueError("TRANSPORT deve essere 'wifi' o 'ble'")

        # Esempio RAW: impostare ACQUISITION_MODE = "raw".
        # raw=True fa arrivare un pacchetto per ogni campione acquisito.
        # window_size e step_size non vengono usati in questa modalita'.
        # Chiamata equivalente:
        # self.imu_manager.set_campaign("campaign01", 10, raw=True)
        #
        # Esempio FEATURES: impostare ACQUISITION_MODE = "features".
        # raw=False fa arrivare un pacchetto di feature per ogni finestra.
        # window_size indica i campioni della finestra; step_size di quanti
        # campioni avanza la finestra successiva.
        # Chiamata equivalente:
        # self.imu_manager.set_campaign(
        #     "campaign01", 10, raw=False, window_size=300, step_size=100
        # )
        self.imu_manager.set_campaign(
            CAMPAIGN_NAME,
            SAMPLING_FREQUENCY,
            raw=raw,
            window_size=FEATURE_WINDOW_SIZE,
            step_size=FEATURE_STEP_SIZE,
        )

        self.db_mqtt_manager = MqttTransmissionMngr()
        self.db_mqtt_manager.set_db_mqtt(RAW_MQTT_BROKER,RAW_MQTT_PORT,RAW_MQTT_TOPIC)
        self.db_mqtt_manager.start_db_mqtt()

        # Seconda istanza MQTT: pubblica solo i risultati prodotti dal task
        # Processing, senza mescolarli ai dati di acquisizione.
        self.db_mqtt_output_manager = MqttTransmissionMngr()
        self.db_mqtt_output_manager.set_db_mqtt(
            OUTPUT_MQTT_BROKER,
            OUTPUT_MQTT_PORT,
            OUTPUT_MQTT_TOPIC,
        )
        self.db_mqtt_output_manager.start_db_mqtt()

        self.imu_manager.start_collection()
        self.imu_manager.wait_connection()

        self.packets_splitted_for_id = {imu_id: [] for imu_id in IMU_IDS}
        return True

    def Processing_setup(self):
        # Setup for task 'Processing'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        return True

    def Save_setup(self):
        # Setup for task 'SaveCSV'
        # Initialize task-specific resources here
        # Return False to signal setup failure, otherwise return True or None
        return True

    ## Loop methods

    def setup_and_collect_loop(self):
        # Task logic for 'setup_and_collect' goes here
        #Example of a point: {'time': '2025-05-18T12:58:07.725063Z', 'ax': '0x0000', 'ay': '0x0000', 'az': '0x0000', 'counter': 0.0, 'gx': '0x0000', 
        # 'gy': '0x0000', 'gz': '0x0000', 'imuid': 'IMU4E5A', 'mx': '0x0000', 'my': '0x0000', 'mz': '0x0000', 'ts': 130679349.0}
        #time.sleep(1/CAMPAIGN_TEMPLATE["sampling_frequency"])
        
        # In RAW costruiamo qui una finestra di campioni.
        # In FEATURES ogni pacchetto ricevuto e' gia' il riassunto di una
        # finestra calcolata dalla IMU, quindi ne basta uno per dispositivo.
        packets_needed = window_size if ACQUISITION_MODE == "raw" else 1
        ok = all(
            len(values) >= packets_needed
            for values in self.packets_splitted_for_id.values()
        )
        
        while not ok:
            #Extract a point
            packet = self.imu_manager.get_packet(True)
            if packet is None:
                continue

            csv_data_d = ",".join(f"{k}={v}" for k, v in packet.items())

            self.db_mqtt_manager.put_row(csv_data_d)
            #print("Get a packet")

    
            if "battery" in packet:
                print(f"Battery level for IMU {packet['imuid']} received")
                continue
            
            if packet["ts"] is not None: #If the packet is empty discard it
                self.packets_splitted_for_id[packet["imuid"]] = self.packets_splitted_for_id[packet["imuid"]] + [packet]
       

            #Check if there are enough data
            ok = all(
                len(values) >= packets_needed
                for values in self.packets_splitted_for_id.values()
            )


        # RAW restituisce una finestra di campioni; FEATURES una lista con il
        # singolo pacchetto di feature, mantenendo uguale la struttura dati.
        new_windows_of_data = {k: copy.deepcopy(v[:packets_needed])
                       for k, v in self.packets_splitted_for_id.items()}

        consumed_packets = overlapping if ACQUISITION_MODE == "raw" else 1
        for k in self.packets_splitted_for_id.keys():
            self.packets_splitted_for_id[k] = (
                self.packets_splitted_for_id[k][consumed_packets:]
            )
        
        return {"new_windows_of_data":new_windows_of_data}
            
    def Processing_loop(self,new_windows_of_data):
        # Task logic for 'Processing' goes here

        # Elaboration input -> output. Qui usiamo un'elaborazione semplice e
        # sostituibile: per ogni IMU calcoliamo la media dei campi numerici
        # presenti nella finestra (RAW o FEATURES).
        output = {}
        ignored_fields = {"imuid", "mode", "cname", "ts", "nth"}

        for imu_id, packets in new_windows_of_data.items():
            numeric_fields = {}
            for packet in packets:
                for field, value in packet.items():
                    if field in ignored_fields:
                        continue
                    try:
                        if isinstance(value, str) and value.lower().startswith("0x"):
                            number = int(value, 16)
                        else:
                            number = float(value)
                        if math.isfinite(number):
                            numeric_fields.setdefault(field, []).append(number)
                    except (TypeError, ValueError):
                        # I campi testuali non fanno parte dell'elaborazione.
                        continue

            output[imu_id] = {
                "sample_count": len(packets),
                **{
                    f"{field}_mean": sum(values) / len(values)
                    for field, values in numeric_fields.items()
                    if values
                },
            }

        return {"out": output}

    def Save_loop(self,out):
        # Task logic for 'SaveCSV' goes here

        # Convertiamo ogni risultato in una riga CSV key=value e lo
        # pubblichiamo sul secondo database MQTT, come nell'app BreathAnalysis.
        for imu_id, values in out.items():
            csv_data = ",".join(
                [
                    f"imuid={imu_id}",
                    f"cname={CAMPAIGN_NAME}",
                    f"mode={ACQUISITION_MODE}",
                    *[f"{key}={value}" for key, value in values.items()],
                ]
            )
            self.db_mqtt_output_manager.put_row(csv_data)
        
        return {}
    
    ## Cleanup methods

    def setup_and_collect_cleanup(self):
        # Cleanup for task 'setup_and_collect'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        print("Stopping IMUs ....")
        # Start BLE collection in background thread
        print("Waiting stop acquisition")
        self.imu_manager.stop_collection()
        print("Acquisition stopped")
        
        self.db_mqtt_manager.stop_db_mqtt()
        self.db_mqtt_output_manager.stop_db_mqtt()
        return True


    def Processing_cleanup(self):
        # Cleanup for task 'Processing'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        return True

    def Save_cleanup(self):
        # Cleanup for task 'Save'
        # Release task-specific resources here
        # Return False to signal cleanup failure, otherwise return True or None
        return True

    def cleanup(self):
        # Global cleanup method called after all task-specific cleanup
        # Use this to release shared resources
        # Return False to signal cleanup failure, otherwise return True or None
        return True
