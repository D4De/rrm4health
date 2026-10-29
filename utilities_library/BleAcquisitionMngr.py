import asyncio
import threading
import queue
import time
import traceback
from bleak import BleakClient, BleakScanner
import struct
import paho.mqtt.client as mqtt

# Campaign API: set_campaign(name, freq, raw=True/False, window_size=300, step_size=100)
## BLE RELATED SETTINGS
# UUID of the characteristic sending notifications (from Arduino sketch)
ACK_UUID				=   "555A0002-0010-467A-9538-01F0652C74E8"
TIMESTAMP_CHAR_UUID  	=   "555A0002-0034-467A-9538-01F0652C74E8"
ACTIVITY_UUID	   		=   "555A0002-0040-467A-9538-01F0652C74E8"  # start and stop
RAWSENSOR_UUID	  		=   "555A0002-0030-467A-9538-01F0652C74E8"
FEATURES_UUID           =   "555A0002-0032-467A-9538-01F0652C74E8"
BATTERY_LEVEL_UID		=	"00002A19-0000-1000-8000-00805F9B34FB" # "2A19"

#For reading boot_id
BOOT_ID_UUID            =   "555A0002-0099-467A-9538-01F0652C74E8"

STOP_CAMPAIGN	   		=  	0xF
CAMPAIGN_RAW            =   0x00
CAMPAIGN_FEATURES       =   0x01
START_CAMPAIGN	  		=  	0x0
CAMPAIGN_UUID	   		=   "555A0002-0035-467A-9538-01F0652C74E8"
MAX_WAIT                = 3


## SENSOR SPECIFIC SETTINGS
NUM_SENSORS             = 3
NUM_READINGS_PER_SENSOR = 3
NUM_READINGS            = NUM_SENSORS * NUM_READINGS_PER_SENSOR
SENSOR_PRECISION        = 2 # bytes
COUNTER_PRECISION       = 2 # bytes 0 - 65535
TIMESTAMP_SIZE          = 4
SENSOR_PACKET_LENGTH    = SENSOR_PRECISION * NUM_READINGS + COUNTER_PRECISION + TIMESTAMP_SIZE 
SENSOR_PACKET_TEMPLATE  = ["ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz", "nth", "ts"]
SENSOR_PACKET_DICT      = {"ax": 0x0000, "ay": 0x0000, "az": 0x0000, 
                           "gx": 0x0000, "gy": 0x0000, "gz": 0x0000, 
                           "mx": 0x0000, "my": 0x0000, "mz": 0x0000, 
                           "nth": 0x0000, "ts": 0x00000000}

# ---------------------------------------------------------------------------
# FEATURES CONFIGURATION
#
# IMPORTANT FOR ADDING/REMOVING FEATURES:
# The order of this list MUST be exactly the same as the order used by the
# Arduino firmware in extractFeatureVector(), i.e.:
#
#     outFeatures[0]  <-> FEATURE_NAMES[0]
#     outFeatures[1]  <-> FEATURE_NAMES[1]
#     ...
#
# If the firmware feature set changes, this is the ONLY feature-specific
# section of the manager that must be updated:
#
#   1. Add/remove the corresponding name in FEATURE_NAMES.
#   2. Keep the names in exactly the same order as outFeatures[] on Arduino.
#
# FEATURE_COUNT, FEATURE_PACKET_LENGTH and FEATURE_PACKET_FORMAT are derived
# automatically from this list, so they must NOT be edited manually.
# ---------------------------------------------------------------------------
FEATURE_NAMES = [
    "acc_mag_max",
    "acc_mag_mean",
    "acc_mag_std",
    "gyro_mag_max",
    "gyro_mag_mean",
    "gyro_mag_std",
    "ax_mean",
    "ax_max",
    "ax_std",
    "ay_mean",
    "ay_max",
    "ay_std",
    "az_mean",
    "az_max",
    "az_std",
    "gx_mean",
    "gx_max",
    "gx_std",
    "gy_mean",
    "gy_max",
    "gy_std",
    "gz_mean",
    "gz_max",
    "gz_std",
    "tilt",
    "dynamic_sma",
    "jerk_max",
    "jerk_mean",
]
FEATURE_COUNT = len(FEATURE_NAMES)
FEATURE_PACKET_LENGTH = FEATURE_COUNT * 4 + 2 + 4  # 118 bytes with 28 float32 features
FEATURE_PACKET_FORMAT = "<" + ("f" * FEATURE_COUNT) + "HI"

## RECONNECTION PARAMETERS
RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY = 3
CONNECT_TIMEOUT = 10


class BleAcquisitionMngr:
    def __init__(self):
        # User parameters (set via setters)
        self.BSN_IMUS = []
        self.CAMPAIGN = {
            "name": "",
            "sampling_frequency": 10,
            "raw": True,
            "window_size": 300,
            "step_size": 100
        }

        # BLE internal state
        self.connected_clients = {}
        self.session_boot_id = {}
        self.connected_imus = {}
        self.available_imus = set()
        self.ready_imus = set()
        self.startALL = True
        self.sensor_reading_payload  = {}
        self.sensor_battery_payload  = {}

        # Generic BLE reassembly buffers.
        #
        # BLE notifications are transport fragments: depending on the ATT MTU
        # and on the peripheral implementation, one application packet may
        # arrive in one notification or in several notifications.
        #
        # Keep one independent byte stream for every IMU and acquisition mode.
        self.fragment_buffers = {
            "raw": {},
            "features": {}
        }

        self._adapter= "hci0"
        self.stopping_by_user = False

        # Asyncio loop & thread
        self.loop = None
        self.ble_thread = None
        self._thread_exception = None
        self._thread_exception_traceback = None
        self._thread_exception_reported = False
        self._thread_exception_lock = threading.Lock()

        # Data output queue
        self.packet_queue = queue.Queue()

        # Stop event for BLE collection
        self.stop_event = threading.Event()
        self.ready_connection = threading.Event()


    # ------------------------------
    # USER SETTERS
    # ------------------------------

    def set_imus(self, imu_list):
        """Lista dei nomi IMU ["IMUX","IMUY","IMUZ"]"""
        self.BSN_IMUS = imu_list

    def set_id_imus(self,id_imu_list):
        """Lista dei nomi custom IMU, example: ["device1","device2","device3"]"""
        self.IMUS_ID_CUSTOM = {}
        
        for i in range(len(id_imu_list)):
            self.IMUS_ID_CUSTOM[self.BSN_IMUS[i]] = id_imu_list[i]
    
    def set_campaign(
        self,
        name,
        freq,
        raw=True,
        window_size=300,
        step_size=100
    ):
        """
        Configure a campaign.

        raw=True  -> RAW mode
        raw=False -> FEATURES mode

        QUAT mode is intentionally not selectable from this manager.
        """
        freq = int(freq)
        window_size = int(window_size)
        step_size = int(step_size)

        if not 1 <= freq <= 255:
            raise ValueError("freq must be in [1, 255] Hz")

        if not isinstance(raw, bool):
            raise TypeError("raw must be a bool")

        if not 1 <= window_size <= 65535:
            raise ValueError("window_size must be in [1, 65535]")

        if not 1 <= step_size <= window_size:
            raise ValueError(
                "step_size must be > 0 and <= window_size"
            )

        self.CAMPAIGN["name"] = name
        self.CAMPAIGN["sampling_frequency"] = freq
        self.CAMPAIGN["raw"] = raw
        self.CAMPAIGN["window_size"] = window_size
        self.CAMPAIGN["step_size"] = step_size
    
    def set_adapter(self,adapter_name):
        self._adapter = adapter_name
    # ------------------------------
    # PUBLIC METHODS
    # ------------------------------

    def start_collection(self):
        """Avvia il thread BLE + asyncio loop"""
        self.stop_event.clear()
        self.ready_connection.clear()

        # Never inherit incomplete transport fragments from a previous run.
        self.fragment_buffers["raw"].clear()
        self.fragment_buffers["features"].clear()
        with self._thread_exception_lock:
            self._thread_exception = None
            self._thread_exception_traceback = None
            self._thread_exception_reported = False
        self.ble_thread = threading.Thread(target=self._run_loop_thread)
        self.ble_thread.daemon = True
        self.ble_thread.start()

    def get_battery_levels(self) -> dict[str, int | str | None]:
        """
        Connette tutte le IMU configurate in BSN_IMUS, legge il livello
        batteria, disconnette i dispositivi e restituisce:

            {
                "IMU5B35": 82,
                "IMU373B": 76,
                "IMUX7X7": None
            }

        "IMU non trovata" indica che il dispositivo non è stato rilevato.
        None indica un valore batteria assente/non valido. Le eccezioni BLE
        vengono propagate al chiamante.
        """

        if not self.BSN_IMUS:
            return {}

        # Se il manager ha già un loop BLE attivo, esegui la coroutine lì.
        if self.loop is not None and self.loop.is_running():
            if threading.current_thread() is self.ble_thread:
                raise RuntimeError(
                    "get_battery_levels() non può essere chiamato "
                    "dal thread BLE stesso."
                )

            future = asyncio.run_coroutine_threadsafe(
                self._get_battery_levels_async(),
                self.loop
            )
            return future.result()

        # Caso normale: il manager non sta eseguendo una raccolta.
        return asyncio.run(self._get_battery_levels_async())
    # Give some time for BLE connection to establish
    def wait_connection(self):
        self.ready_connection.wait()
        self._raise_thread_exception_if_any()
        
        
    def stop_collection(self):
        """Stop deve essere thread-safe"""
        self.stopping_by_user = True
        #self.stop_event.set()
        if self.loop and self.loop.is_running():
            print("If: Start Stop all imus:")
            fut = asyncio.run_coroutine_threadsafe(self._stop_imus_and_disconnect(), self.loop)
            fut.result()
        else:
            print("Else:Start Stop all imus:")
            asyncio.run(self._stop_imus_and_disconnect())            
        if self.ble_thread:
            self.ble_thread.join()

    def get_packet(self, block=False, timeout=None):
        self._raise_thread_exception_if_any()

        if not block:
            try:
                return self.packet_queue.get_nowait()
            except queue.Empty:
                self._raise_thread_exception_if_any()
                return None

        deadline = None if timeout is None else time.monotonic() + timeout

        while True:
            self._raise_thread_exception_if_any()

            wait_timeout = 0.25
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    self._raise_thread_exception_if_any()
                    return None
                wait_timeout = min(wait_timeout, remaining)

            try:
                return self.packet_queue.get(timeout=wait_timeout)
            except queue.Empty:
                self._raise_thread_exception_if_any()
                if deadline is not None and time.monotonic() >= deadline:
                    return None

    def _record_thread_exception(self, exception):
        """Preserve the first BLE worker failure for the application thread."""
        with self._thread_exception_lock:
            if self._thread_exception is None:
                self._thread_exception = exception
                self._thread_exception_traceback = exception.__traceback__
        # Also release setup if the worker failed before connecting.
        self.ready_connection.set()

    def _raise_thread_exception_if_any(self):
        """Re-raise a BLE worker failure once in the framework-managed thread."""
        with self._thread_exception_lock:
            if self._thread_exception is None or self._thread_exception_reported:
                return
            exception = self._thread_exception
            exception_traceback = self._thread_exception_traceback
            self._thread_exception_reported = True

        raise exception.with_traceback(exception_traceback)

    # ------------------------------
    # THREAD ENTRYPOINT
    # ------------------------------

    def _run_loop_thread(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main())
        except KeyboardInterrupt:
            print("BLE collection stopped by user.")
        except Exception as e:
            print(f"BLE collection error: {e}")
            traceback.print_exc()
            self._record_thread_exception(e)
        finally:
            if not self.ready_connection.is_set() and not self.stopping_by_user:
                self._record_thread_exception(
                    RuntimeError("BLE worker stopped before the connection was ready")
                )
            self.loop.close()
            
    # ------------------------------
    # BLE LOGIC (ASYNC)
    # ------------------------------

    async def _main(self):
        try:
            result = await self._connect_all()
            if not result:
                connected_names = {
                    names[0]
                    for names in self.connected_imus.values()
                    if names
                }
                missing_imus = [
                    imu_name
                    for imu_name in self.BSN_IMUS
                    if imu_name not in connected_names
                ]
                raise RuntimeError(
                    "Required IMUs not found: " + ", ".join(missing_imus)
                )

            self.ready_connection.set()

            result = await self._configure_all()
            if result:
                await self._start_all()

                if self.startALL:
                    print("ALL IMUs started")
                    await self._collect_all()
        finally:
            print("Closing main_process.")
            await self._disconnect_imus()
            self.stopping_by_user = False

    async def _get_battery_levels_async(self) -> dict[str, int | str | None]:
        """
        Cerca tutte le IMU configurate, legge in parallelo il livello
        batteria e disconnette sempre ogni client aperto.
        """

        battery_levels: dict[str, int | str | None] = {
            imu_name: None
            for imu_name in self.BSN_IMUS
        }

        target_names = set(self.BSN_IMUS)
        discovered_devices = {}

        for attempt in range(MAX_WAIT + 1):
            print(
                f"Battery scan {attempt + 1}/{MAX_WAIT + 1}: "
                f"searching for {sorted(target_names)}"
            )

            devices = await BleakScanner.discover(
                timeout=5.0,
                adapter=self._adapter
            )

            for device in devices:
                if (
                    device.name
                    and device.name in target_names
                    and device.name not in discovered_devices
                ):
                    discovered_devices[device.name] = device

            if len(discovered_devices) == len(target_names):
                break

            missing = target_names - set(discovered_devices)

            if attempt < MAX_WAIT:
                print(
                    "Waiting before another battery scan. "
                    f"Missing IMUs: {sorted(missing)}"
                )
                await asyncio.sleep(2)

        tasks = [
            asyncio.create_task(
                self._read_device_battery(
                    imu_name,
                    discovered_devices[imu_name]
                )
            )
            for imu_name in self.BSN_IMUS
            if imu_name in discovered_devices
        ]

        if tasks:
            results = await asyncio.gather(*tasks)

            for result in results:
                imu_name, battery_level = result
                battery_levels[imu_name] = battery_level

        missing = target_names - set(discovered_devices)

        for imu_name in sorted(missing):
            print(f"IMU {imu_name} not found during battery scan")
            battery_levels[imu_name] = "IMU non trovata"

        return battery_levels

    async def _read_device_battery(
        self,
        imu_name,
        device
    ) -> tuple[str, int | None]:
        """
        Connette una singola IMU, legge la caratteristica Battery Level
        e la disconnette nel blocco finally.
        """

        client = BleakClient(
            device,
            adapter=self._adapter
        )

        battery_level = None

        try:
            print(
                f"Connecting to {imu_name} "
                f"for battery reading..."
            )

            await client.connect(timeout=CONNECT_TIMEOUT)

            if not client.is_connected:
                print(f"Connection to {imu_name} failed")
                return imu_name, None

            battery_data = await client.read_gatt_char(
                BATTERY_LEVEL_UID
            )

            if not battery_data:
                print(
                    f"Empty battery value received from {imu_name}"
                )
                return imu_name, None

            battery_level = int(battery_data[0])

            if not 0 <= battery_level <= 100:
                print(
                    f"Invalid battery level from {imu_name}: "
                    f"{battery_level}"
                )
                return imu_name, None

            print(
                f"Battery level of {imu_name}: "
                f"{battery_level}%"
            )

            return imu_name, battery_level

        finally:
            if client.is_connected:
                await client.disconnect()
                print(
                    f"Disconnected from {imu_name} "
                    "after battery reading"
                )
    # ------------------------------
    async def _disconnect_imus(self):
        for imu_addr, client in list(self.connected_clients.items()):
            imu_names = self.connected_imus.get(imu_addr, [imu_addr])
            try:
                if client.is_connected:
                    await client.disconnect()
                print("Disconnected from ", imu_names)
            finally:
                self.connected_clients.pop(imu_addr, None)
                self.connected_imus.pop(imu_addr, None)
        self.stop_event.set()
        
    async def _connect_all(self):
        print("Scanning for IMUs ", self.BSN_IMUS)
    ## waits for all imus to show up and be available
        num_imus = len(self.BSN_IMUS)
        num_imus_ok = 0
        tot_waiting = 0 
        while num_imus > num_imus_ok:
            print("BleakScanner.discover start")
            devices = await BleakScanner.discover(timeout=5.0,adapter=self._adapter)
            print("BleakScanner.discover finish")  
            for dev in devices:
                if dev.name and dev.name in self.BSN_IMUS and not dev.name in self.connected_imus:
                    print(f"Found {dev.name}:", end=" ")
                    self.available_imus.add(dev.address)
                    client = BleakClient(dev.address,adapter=self._adapter)
                    try:
                        print("trying to connect")
                        await client.connect(timeout=CONNECT_TIMEOUT)
                        if client.is_connected:
                            print(f"Connected to {dev.name}")
                            self.connected_clients[dev.address] = client
                            num_imus_ok += 1
                            self.connected_imus[dev.address] = [dev.name]
                            for service in client.services:
                                print("Service:", service.uuid)
                                for char in service.characteristics:
                                    print("  Characteristic:", char.uuid)
                        else:
                            print(f"Impossible to connect to {dev.name}")
                    except Exception as e:
                        print(f"connect_all: Failed to connect to {dev.name}: {e}")
            if tot_waiting < MAX_WAIT and num_imus_ok < num_imus: 
                tot_waiting += 1
                #wait a moment
                print(f"Waiting 2 sec before retrying for the {num_imus - num_imus_ok} IMU(s)")
                await asyncio.sleep(2)
            elif num_imus_ok < num_imus:
                print(f"Missing {num_imus - num_imus_ok} IMUs. Retry later. Exiting")
                return False
        print("All expected IMUs are alive")
        return True

    # ------------------------------

    async def _configure_all(self):
        num_imus_ok = 0
        for imu_addr, client in self.connected_clients.items():
            try:
                # moved later
                # await client.start_notify(RAWSENSOR_UUID, notification_handler(client))
                # print("Subscribed to ", RAWSENSOR_UUID, " for IMU ", connected_imus[imu_addr])
                boot_id_bytes = await client.read_gatt_char(BOOT_ID_UUID)
                boot_id = int.from_bytes(boot_id_bytes, byteorder="little")

                print(f"IMU: {self.connected_imus[imu_addr]} with boot_id=",boot_id)
                self.session_boot_id[imu_addr] = boot_id
                
                await self._send_timestamp(client)
                print("Timestamp")
                await self._send_campaign_params(client)
                print("Configuration")
                response = await client.read_gatt_char(ACK_UUID)
                if response:
                    print("ACK received")
                    self.ready_imus.add(imu_addr)
                    num_imus_ok += 1
            except Exception as e:
                print(f"Failed connecting to {self.connected_imus[imu_addr]}: {e}")
        result = (num_imus_ok == len(self.BSN_IMUS))
        return result

    async def _send_timestamp(self, client):
        timestamp = int(time.time())
        value = struct.pack(">i", timestamp) 
        print("timestamp", TIMESTAMP_CHAR_UUID, value)
        await client.write_gatt_char(TIMESTAMP_CHAR_UUID, value)
        print(f"Sent timestamp: {timestamp}")

    async def _send_campaign_params(self, client):
        fr = self.CAMPAIGN["sampling_frequency"]
        window_size = self.CAMPAIGN["window_size"]
        step_size = self.CAMPAIGN["step_size"]

        # Public mapping is intentionally fixed:
        # raw=True  -> RAW
        # raw=False -> FEATURES
        campaign_mode = (
            CAMPAIGN_RAW
            if self.CAMPAIGN["raw"]
            else CAMPAIGN_FEATURES
        )

        # 6-byte payload, little-endian:
        # freq(1), mode(1), window_size(2), step_size(2)
        data = struct.pack(
            "<BBHH",
            fr,
            campaign_mode,
            window_size,
            step_size
        )

        print("configuration", CAMPAIGN_UUID, data)
        await client.write_gatt_char(CAMPAIGN_UUID, data)
        print(
            f"Sent campaign parameters: {self.CAMPAIGN} "
            f"(mode={'RAW' if self.CAMPAIGN['raw'] else 'FEATURES'})"
        )

    # ------------------------------
    async def _send_start_to_imu(self,client, imu_addr):
        data = bytearray([START_CAMPAIGN])
        try:
            await client.write_gatt_char(ACTIVITY_UUID, data)
            print(f"Sent START to {self.connected_imus[imu_addr]} ({imu_addr})")
        except Exception as e:
            print(f"Failed to send START to {self.connected_imus[imu_addr]} ({imu_addr}): {e}")
    
    async def _start_all(self):
        ## send start to all, as in parallel as possible, it is anyhow sequential
        tasks = [asyncio.create_task(self._send_start_to_imu(client, imu_addr)) for imu_addr, client in self.connected_clients.items()]
        await asyncio.gather(*tasks)

    async def _stop_all(self):
        print("Start creating Task")
        tasks = [asyncio.create_task(self._send_stop_to_imu(client, imu_addr)) for imu_addr, client in self.connected_clients.items()]
        print("Finish creating Task")
        print("Start await")
        await asyncio.gather(*tasks)
        print("Stop await")
        self.stop_event.set()

    async def _send_stop_to_imu(self,client, imu_addr):
        data = bytearray([STOP_CAMPAIGN])
        try:
            await client.write_gatt_char(ACTIVITY_UUID, data)
            print(f"Sent STOP to {self.connected_imus[imu_addr]} ({imu_addr})")
            startALL = False
        except Exception as e:
            print(f"Failed to send STOP to {self.connected_imus[imu_addr]} ({imu_addr}): {e}")
            
    async def _stop_imus_and_disconnect(self):
        print("connected_clients:",self.connected_clients.items(),flush=True)
        for imu_addr, client in self.connected_clients.items():
            try:
                if client.is_connected:
                    print(f"Stopping notifications for {imu_addr}...",flush=True)         
                    await self._send_stop_to_imu(client,imu_addr)
                    print("Stopped", self.connected_imus[imu_addr],flush=True)
                    await client.disconnect()
                    print(f"Disconnected {imu_addr}")                  
                    self.ready_imus.remove(imu_addr)	                
            except Exception as e:
                print(f"Error stopping {imu_addr}: {e}",flush=True)
        self.stop_event.set()
        self.connected_clients.clear()
        self.fragment_buffers["raw"].clear()
        self.fragment_buffers["features"].clear()

    # ------------------------------

    async def _collect_all(self):
        try:
            print("[collect_data_from_all_imus] ", len(self.connected_clients), " IMUs connected", self.connected_clients.items())
            tasks = [asyncio.create_task(self._collect_device(client, imu_addr)) for imu_addr, client in self.connected_clients.items()]
            await asyncio.gather(*tasks)
        except Exception:
            print("Problem during data collection")
            raise


    async def _collect_device(self, client, imu_addr):
        
        imu = self.connected_imus[imu_addr][0]
        self.sensor_reading_payload[imu] = SENSOR_PACKET_DICT.copy()

        while not self.stop_event.is_set() and  not self.stopping_by_user:
            try:
                print(f"[collect_device] Starting notifications for {imu}")

                # A new notification stream (also after reconnect) starts from
                # a clean application-packet boundary. Discard any incomplete
                # fragment left by the previous BLE connection.
                active_mode = "raw" if self.CAMPAIGN["raw"] else "features"
                self._reset_fragment_buffer(imu, active_mode)

                if self.CAMPAIGN["raw"]:
                    await client.start_notify(
                        RAWSENSOR_UUID,
                        self.notification_handler(client)
                    )
                else:
                    await client.start_notify(
                        FEATURES_UUID,
                        self.notification_handler_features(client)
                    )

                try:
                    await client.start_notify(BATTERY_LEVEL_UID, self.notification_handler_battery(client))
                except:
                    print(f"{imu} has no battery characteristic")

                # Rimani in ascolto finché connesso
                while client.is_connected and not self.stop_event.is_set():
                    await asyncio.sleep(1)

                if not client.is_connected:
                    raise Exception("Device disconnected")

            except Exception as e:
                print(f"[{imu}] Disconnected: {e}")

                #Reconnection attempts should only be made if the user did not request the stop and therefore the disconnections.
                if not self.stopping_by_user:
                    success = await self._attempt_reconnect(client, imu_addr)

                    if not success:
                        print(f"[{imu}] Reconnect failed permanently.")
                        self.stop_event.set()
                        raise RuntimeError(
                            f"Unable to reconnect {imu} after "
                            f"{RECONNECT_ATTEMPTS} attempts"
                        )
                    else:
                        client = self.connected_clients[imu_addr]

    async def _attempt_reconnect(self, client, imu_addr):
        imu = self.connected_imus[imu_addr][0]
        last_exception = None

        for attempt in range(RECONNECT_ATTEMPTS):
            try:
                print(f"[{imu}] Reconnect attempt {attempt+1}/{RECONNECT_ATTEMPTS}")

                await asyncio.sleep(RECONNECT_DELAY)

                client_new = BleakClient(imu_addr, adapter=self._adapter)
                await client_new.connect(timeout=CONNECT_TIMEOUT)
                
                # wait until services is populated
                #while not client_new.services:
                    #await asyncio.sleep(0.1)
            
                        
                self.connected_clients[imu_addr] =  client_new
                if self.connected_clients[imu_addr]:
                    print(f"[{imu}] Reconnected successfully")

                    # Ri-configuriamo solo START (timestamp e config già settati)
                    #await self._send_start_to_imu(client, imu_addr)
                    
                    #Checking probable reboot
                    print("Checking probable reboot:")

                    boot_id_bytes = await client_new.read_gatt_char(BOOT_ID_UUID)
                    new_boot_id = int.from_bytes(boot_id_bytes, byteorder="little")
                    print(f"IMU: {self.connected_imus[imu_addr]} with boot_id=",new_boot_id)
                    

                    if new_boot_id != self.session_boot_id[imu_addr]:
                        print(f"{imu_addr} reboot detected. Resending configuration")
                        self.session_boot_id[imu_addr] = new_boot_id
                        
                        await self._send_timestamp(client_new)
                        print("Timestamp")
                        await self._send_campaign_params(client_new)
                        print("Configuration")
                        response = await client_new.read_gatt_char(ACK_UUID)
                        if response:
                            print("ACK received")
                            data = bytearray([START_CAMPAIGN])
                            await client_new.write_gatt_char(ACTIVITY_UUID, data)
                            print(f"Sent START to {self.connected_imus[imu_addr]} ({imu_addr})")

                    return True

            except Exception as e:
                last_exception = e
                print(f"[{imu}] Reconnect attempt failed: {e}")

        error = RuntimeError(
            f"Unable to reconnect {imu} after {RECONNECT_ATTEMPTS} attempts"
        )
        if last_exception is not None:
            raise error from last_exception
        raise error

    # ------------------------------
    # NOTIFICATION PARSER
    # ------------------------------
    def _reset_fragment_buffer(self, imu, mode=None):
        """
        Reset buffered BLE transport fragments for one IMU.

        mode=None clears both RAW and FEATURES buffers.
        """
        if mode is None:
            for buffers in self.fragment_buffers.values():
                buffers.pop(imu, None)
            return

        if mode not in self.fragment_buffers:
            raise ValueError(f"Unknown BLE fragment mode: {mode}")

        self.fragment_buffers[mode][imu] = bytearray()

    def _append_ble_fragment(self, imu, mode, data, packet_length):
        """
        Append one BLE notification to the per-IMU byte stream and return all
        complete application packets currently available.

        Notification size is intentionally irrelevant. Examples:
          RAW (24 B):       24, 20+4, 8+8+8, ...
          FEATURES (118 B): 118, 29+29+29+29+2, 50+50+18, ...

        This solves BLE transport fragmentation. It cannot by itself recover
        packet alignment after a lost notification because the application
        protocol currently has no explicit framing header.
        """
        if mode not in self.fragment_buffers:
            raise ValueError(f"Unknown BLE fragment mode: {mode}")

        if packet_length <= 0:
            raise ValueError("packet_length must be > 0")

        buffer = self.fragment_buffers[mode].setdefault(
            imu,
            bytearray()
        )

        buffer.extend(bytes(data))

        complete_packets = []

        while len(buffer) >= packet_length:
            complete_packets.append(
                bytes(buffer[:packet_length])
            )
            del buffer[:packet_length]

        return complete_packets

    def _decode_raw_packet(self, imu, data):
        """Decode one complete RAW application packet."""
        if len(data) != SENSOR_PACKET_LENGTH:
            raise ValueError(
                f"invalid RAW packet length: {len(data)}, "
                f"expected {SENSOR_PACKET_LENGTH}"
            )

        rs_payload = self.sensor_reading_payload.setdefault(
            imu,
            SENSOR_PACKET_DICT.copy()
        )

        offset = 0

        for key in SENSOR_PACKET_TEMPLATE[:NUM_READINGS]:
            rs_payload[key] = int.from_bytes(
                data[offset:offset + SENSOR_PRECISION],
                byteorder="little",
                signed=False
            )
            offset += SENSOR_PRECISION

        rs_payload["nth"] = int.from_bytes(
            data[offset:offset + COUNTER_PRECISION],
            byteorder="little",
            signed=False
        )
        offset += COUNTER_PRECISION

        rs_payload["ts"] = int.from_bytes(
            data[offset:offset + TIMESTAMP_SIZE],
            byteorder="little",
            signed=False
        )

        # Preserve the public RAW output format used by the existing manager.
        packet = {
            key: f"0x{rs_payload[key]:04x}"
            for key in SENSOR_PACKET_TEMPLATE
        }
        packet["imuid"] = imu
        packet["cname"] = self.CAMPAIGN["name"]

        self.packet_queue.put(packet)

    def _decode_feature_packet(self, imu, data):
        """Decode one complete FEATURES application packet."""
        if len(data) != FEATURE_PACKET_LENGTH:
            raise ValueError(
                f"invalid FEATURES packet length: {len(data)}, "
                f"expected {FEATURE_PACKET_LENGTH}"
            )

        values = struct.unpack(
            FEATURE_PACKET_FORMAT,
            bytes(data)
        )

        feature_values = values[:FEATURE_COUNT]
        nth = values[FEATURE_COUNT]
        ts = values[FEATURE_COUNT + 1]

        packet = {
            name: value
            for name, value in zip(
                FEATURE_NAMES,
                feature_values
            )
        }

        packet["nth"] = nth
        packet["ts"] = ts
        packet["imuid"] = imu
        packet["cname"] = self.CAMPAIGN["name"]
        packet["mode"] = "features"

        self.packet_queue.put(packet)

    def notification_handler(self, client):
        """
        RAW callback with generic stream reassembly.
        """
        def notification_payload_handler(sender, data):
            imu = self.connected_imus[client.address][0]

            try:
                packets = self._append_ble_fragment(
                    imu,
                    "raw",
                    data,
                    SENSOR_PACKET_LENGTH
                )

                for packet_data in packets:
                    self._decode_raw_packet(
                        imu,
                        packet_data
                    )

            except Exception as e:
                print(
                    f"notification_payload_handler ({imu}): "
                    f"{e} | fragment_len={len(data)}"
                )
                self._reset_fragment_buffer(imu, "raw")

        return notification_payload_handler

    def notification_handler_features(self, client):
        """
        FEATURES callback with generic stream reassembly.
        """
        def notification_features_handler(sender, data):
            imu = self.connected_imus[client.address][0]

            try:
                packets = self._append_ble_fragment(
                    imu,
                    "features",
                    data,
                    FEATURE_PACKET_LENGTH
                )

                for packet_data in packets:
                    self._decode_feature_packet(
                        imu,
                        packet_data
                    )

            except Exception as e:
                print(
                    f"notification_features_handler ({imu}): "
                    f"{e} | fragment_len={len(data)}"
                )
                self._reset_fragment_buffer(imu, "features")

        return notification_features_handler

    #battery ... do I need a separate one?
    def notification_handler_battery(self,client):
        def notification_battery_handler(sender, data):
            try:
                imus = self.connected_imus[client.address]
                imu = imus[0]
                batval = data[0]
                # global variable updated at every reading
                batteryLevel_hex = hex(batval)
                csv_data = "battery=" + batteryLevel_hex
                self.sensor_battery_payload[imu] = batval
                csv_data += "," + "imuid=" + imu
                csv_data += "," + "cname=" + self.CAMPAIGN["name"]	 
                print(f"Trying to send battery {csv_data}")
                #publish.single(topic=MQTT_TOPIC, payload=csv_data, hostname=MQTT_BROKER, port=MQTT_PORT)
                print(f"{csv_data}")
                packet = dict(item.split("=") for item in csv_data.split(","))

                #packet["imuid"] = self.IMUS_ID_CUSTOM[packet["imuid"]]

                self.packet_queue.put(packet)
            except Exception as e:
                imu = self.connected_imus[client.address][0]
                print(f"notification_battery_handler ({imu}): {e} | {data}")
        return notification_battery_handler
