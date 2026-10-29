import asyncio
import threading
import queue
import time
import socket
import traceback
import os
import ipaddress
import struct

# =========================
# PARAMETERS
# =========================

NUM_SENSORS = 3
NUM_READINGS_PER_SENSOR = 3
NUM_READINGS = NUM_SENSORS * NUM_READINGS_PER_SENSOR

SENSOR_PRECISION = 2
COUNTER_PRECISION = 2
TIMESTAMP_SIZE = 4

RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY = 2.0
CONNECT_TIMEOUT = 5.0
IMU_PORT_DEFAULT = 8023
IDLE_TIMEOUT_DEFAULT = 5.0

SENSOR_PACKET_LENGTH = (
    SENSOR_PRECISION * NUM_READINGS
    + COUNTER_PRECISION
    + TIMESTAMP_SIZE
)

SENSOR_PACKET_TEMPLATE = [
    "ax", "ay", "az",
    "gx", "gy", "gz",
    "mx", "my", "mz",
    "nth", "ts"
]

SENSOR_PACKET_DICT = {k: 0 for k in SENSOR_PACKET_TEMPLATE}

# =========================
# FEATURES MODE
# =========================
# IMPORTANT:
# Keep only this array synchronized with outFeatures[] in the firmware.
# If features are added/removed, change FEATURE_NAMES (and the firmware)
# keeping exactly the same order. Packet size/format are derived automatically.
FEATURE_NAMES = [
    "acc_mag_max", "acc_mag_mean", "acc_mag_std",
    "gyro_mag_max", "gyro_mag_mean", "gyro_mag_std",
    "ax_mean", "ax_max", "ax_std",
    "ay_mean", "ay_max", "ay_std",
    "az_mean", "az_max", "az_std",
    "gx_mean", "gx_max", "gx_std",
    "gy_mean", "gy_max", "gy_std",
    "gz_mean", "gz_max", "gz_std",
    "tilt", "dynamic_sma", "jerk_max", "jerk_mean",
]

FEATURE_COUNT = len(FEATURE_NAMES)
FEATURE_PACKET_LENGTH = FEATURE_COUNT * 4 + COUNTER_PRECISION + TIMESTAMP_SIZE
FEATURE_PACKET_FORMAT = "<" + ("f" * FEATURE_COUNT) + "HI"

LINE_END = "\n"
CMD_PING = "PING"
CMD_CONFIG_PREFIX = "CONFIG:"
CMD_TIMESTAMP_PREFIX = "TIMESTAMP:"
CMD_ACTIVITY_PREFIX = "ACTIVITY:"
CMD_BOOT_ID = "BOOT_ID"
CMD_BATTERY = "BATTERY"
RESP_BATTERY_PREFIX = "BATTERY:"
RESP_OK_CONFIG = "OK:CONFIG"
RESP_ERR_CONFIG = "ERR:CONFIG"
RESP_ACK_OK = "ACK_OK"
RESP_ACK_KO = "ACK_KO"

# =========================
# WIFI MANAGER
# =========================

class WifiAcquisitionMngr:

    def __init__(self):
        self.IMUS = {}               # name -> ip/mac
        self.IMUS_ID_CUSTOM = {}
        self.imu_port = IMU_PORT_DEFAULT
        self.dhcp_leases_path = "/var/lib/NetworkManager/dnsmasq-wlp2s0.leases"
        self.arp_table_path = "/proc/net/arp"
        self.mac_lookup_timeout = 30
        self.recv_timeout = 1.0
        self.reconnect_attempts = RECONNECT_ATTEMPTS
        self.reconnect_delay = RECONNECT_DELAY
        self.connect_timeout = CONNECT_TIMEOUT
        self.idle_timeout = IDLE_TIMEOUT_DEFAULT


        self.CAMPAIGN = {
            "name": "",
            "sampling_frequency": 10,
            "raw": True,
            "window_size": 300,
            "step_size": 100
        }

        self.sockets = {}            # name -> socket
        self.packet_queue = queue.Queue()

        self.stop_event = threading.Event()
        self.ready_connection = threading.Event()

        self.loop = None
        self.thread = None
        self._thread_exception = None
        self._thread_exception_traceback = None
        self._thread_exception_reported = False
        self._thread_exception_lock = threading.Lock()

        self.sensor_reading_payload = {}
        self.imu_addresses = {}
        self.stopping_by_user = False
        self.session_boot_id = {}
        self._ap_started = False

    # =========================
    # USER SETTERS
    # =========================

    def set_imus(self, imu_dict):
        """
        imu_dict = {
            "IMU1": "192.168.1.10" or "AA:BB:CC:DD:EE:FF",
            "IMU2": "192.168.1.11" or "11:22:33:44:55:66"
        }
        """
        self.IMUS = imu_dict

    def set_id_imus(self, custom_ids):
        """
        ["device1", "device2", ...]
        """
        if isinstance(self.IMUS, dict):
            imus = list(self.IMUS.keys())
        else:
            imus = list(self.IMUS)

        for imu, cid in zip(imus, custom_ids):
            self.IMUS_ID_CUSTOM[imu] = cid

    def set_campaign(self, name, freq, raw=True, window_size=300, step_size=100):
        """
        raw=True  -> RAW acquisition.
        raw=False -> FEATURES acquisition.

        window_size and step_size are expressed in samples and are used only
        by FEATURES mode. The packet counter always starts from 0 in firmware.
        """
        freq = int(freq)
        window_size = int(window_size)
        step_size = int(step_size)

        if not isinstance(raw, bool):
            raise TypeError("raw must be True or False")
        if freq <= 0:
            raise ValueError("sampling frequency must be > 0")
        if window_size <= 0:
            raise ValueError("window_size must be > 0")
        if step_size <= 0 or step_size > window_size:
            raise ValueError("step_size must be > 0 and <= window_size")

        self.CAMPAIGN.update({
            "name": name,
            "sampling_frequency": freq,
            "raw": raw,
            "window_size": window_size,
            "step_size": step_size
        })
        
    def set_access_point(self,wifi_interface,ap_ssid,ap_password):
        self.wifi_interface = wifi_interface #"wlan0"
        self.ap_ssid = ap_ssid
        self.ap_password = ap_password

    def set_dhcp_leases_path(self, path):
        self.dhcp_leases_path = path

    def set_mac_lookup_timeout(self, timeout_seconds):
        self.mac_lookup_timeout = timeout_seconds

    def set_recv_timeout(self, timeout_seconds):
        self.recv_timeout = timeout_seconds

    def set_reconnect_options(self, attempts=None, delay_seconds=None, connect_timeout=None):
        if attempts is not None:
            self.reconnect_attempts = attempts
        if delay_seconds is not None:
            self.reconnect_delay = delay_seconds
        if connect_timeout is not None:
            self.connect_timeout = connect_timeout

    def set_idle_timeout(self, timeout_seconds):
        self.idle_timeout = timeout_seconds

    # =========================
    # PUBLIC API
    # =========================

    def start_collection(self):
        self.stop_event.clear()
        self.ready_connection.clear()
        self.stopping_by_user = False
        with self._thread_exception_lock:
            self._thread_exception = None
            self._thread_exception_traceback = None
            self._thread_exception_reported = False
        self.thread = threading.Thread(target=self._run_loop)
        self.thread.daemon = True
        self.thread.start()

    def wait_connection(self):
        self.ready_connection.wait()
        self._raise_thread_exception_if_any()

    def stop_collection(self):
        self.stop_event.set()
        self.stopping_by_user = True
        if self.loop and self.loop.is_running():
            print("If: Start Stop all imus:")
            fut = asyncio.run_coroutine_threadsafe(self._stop_all(), self.loop)
            fut.result()
        else:
            print("Else:Start Stop all imus:")
            asyncio.run(self._stop_all())  
        #print("Closing loop")
        #self.loop.close()  
        if self.thread:
            self.thread.join()

    def force_disconnect(self, imu_ids=None, remove_from_map=False):
        def do_close():
            if imu_ids is None:
                ids = list(self.sockets.keys())
            elif isinstance(imu_ids, (list, tuple, set)):
                ids = list(imu_ids)
            else:
                ids = [imu_ids]

            for imu_id in ids:
                sock = self.sockets.get(imu_id)
                if sock:
                    try:
                        sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    try:
                        sock.close()
                    except OSError:
                        pass
                    print(f"[manual] socket closed for {imu_id}")

                if remove_from_map:
                    self.sockets.pop(imu_id, None)

        if self.loop and self.loop.is_running():
            self.loop.call_soon_threadsafe(do_close)
        else:
            do_close()

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
        """Preserve the first WiFi worker failure for the application thread."""
        with self._thread_exception_lock:
            if self._thread_exception is None:
                self._thread_exception = exception
                self._thread_exception_traceback = exception.__traceback__
        self.ready_connection.set()

    def _raise_thread_exception_if_any(self):
        """Re-raise a WiFi worker failure once in the framework-managed thread."""
        with self._thread_exception_lock:
            if self._thread_exception is None or self._thread_exception_reported:
                return
            exception = self._thread_exception
            exception_traceback = self._thread_exception_traceback
            self._thread_exception_reported = True

        raise exception.with_traceback(exception_traceback)

    def get_battery_levels(self):
        """
        Connect to every configured WiFi IMU, request BATTERY, disconnect,
        and return {imu_name: percentage | None | "IMU non trovata"}.

        This mirrors the public helper exposed by BleAcquisitionMngr and is intended
        to be used while a collection is not running.
        """
        if not self.IMUS:
            return {}

        if self.loop is not None and self.loop.is_running():
            if threading.current_thread() is self.thread:
                raise RuntimeError(
                    "get_battery_levels() cannot be called from the WiFi worker thread"
                )
            future = asyncio.run_coroutine_threadsafe(
                self._get_battery_levels_async(), self.loop
            )
            return future.result()

        return asyncio.run(self._get_battery_levels_async())

    # =========================
    # THREAD / LOOP
    # =========================

    def _run_loop(self):
        self.loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self.loop)
        try:
            self.loop.run_until_complete(self._main())
            print("Closing")
        except KeyboardInterrupt:
            print("WIFI collection stopped by user.")
        except Exception as e:
            print(f"WIFI collection error: {e}")
            traceback.print_exc()
            self._record_thread_exception(e)
        finally:
            if not self.ready_connection.is_set() and not self.stopping_by_user:
                self._record_thread_exception(
                    RuntimeError("WiFi worker stopped before the connection was ready")
                )
            self.loop.close()

    def _iter_imus(self):
        if isinstance(self.IMUS, dict):
            return list(self.IMUS.items())
        return [(imu, imu) for imu in self.IMUS]

    def _normalize_mac(self, mac):
        return mac.strip().lower().replace("-", ":")

    def _is_mac_address(self, value):
        if not isinstance(value, str):
            return False
        mac = self._normalize_mac(value)
        parts = mac.split(":")
        if len(parts) != 6:
            return False
        for part in parts:
            if len(part) != 2:
                return False
            if not all(c in "0123456789abcdef" for c in part):
                return False
        return True

    def _get_dhcp_leases_by_mac(self):
        if not os.path.exists(self.dhcp_leases_path):
            return {}

        leases = {}

        with open(self.dhcp_leases_path) as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 3:
                    mac = self._normalize_mac(parts[1])
                    ip = parts[2]
                    leases[mac] = ip

        return leases

    def _get_arp_table_by_mac(self):
        if not os.path.exists(self.arp_table_path):
            return {}

        entries = {}
        iface_filter = getattr(self, "wifi_interface", None)

        with open(self.arp_table_path) as f:
            next(f, None)
            for line in f:
                parts = line.split()
                if len(parts) >= 4:
                    ip = parts[0]
                    mac = self._normalize_mac(parts[3])
                    if iface_filter and len(parts) >= 6 and parts[5] != iface_filter:
                        continue
                    if mac != "00:00:00:00:00:00":
                        entries[mac] = ip

        return entries

    async def _get_local_ipv4_networks(self):
        networks = []
        iface_filter = getattr(self, "wifi_interface", None)

        try:
            proc = await asyncio.create_subprocess_exec(
                "ip",
                "-o",
                "-4",
                "addr",
                "show",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0 and stdout:
                for line in stdout.decode(errors="ignore").splitlines():
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    ifname = parts[1]
                    if ifname == "lo":
                        continue
                    if iface_filter and ifname != iface_filter:
                        continue

                    cidr = parts[3]
                    if "/" not in cidr:
                        continue
                    try:
                        iface = ipaddress.ip_interface(cidr)
                    except ValueError:
                        continue

                    if iface.ip.is_loopback or iface.ip.is_link_local:
                        continue

                    net = iface.network
                    # Evita scansioni troppo grandi (es. /16): degrada a /24 attorno all'IP locale.
                    if net.num_addresses - 2 > 2048:
                        net = ipaddress.ip_network(f"{iface.ip}/24", strict=False)

                    if net not in networks:
                        networks.append(net)
        except FileNotFoundError:
            pass
        except Exception:
            pass

        if networks:
            return networks

        # Fallback: deduci l'IP locale dalla route di default e assumi /24.
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            local_ip = s.getsockname()[0]
            s.close()
            return [ipaddress.ip_interface(f"{local_ip}/24").network]
        except Exception:
            return []

    async def _prime_arp_cache(self, networks, port=None, per_host_timeout=0.25, concurrency=128):
        if not networks:
            return

        loop = asyncio.get_running_loop()
        sem = asyncio.Semaphore(concurrency)
        port = self.imu_port if port is None else port

        async def touch(ip_str):
            async with sem:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.setblocking(False)
                try:
                    await asyncio.wait_for(loop.sock_connect(s, (ip_str, port)), timeout=per_host_timeout)
                except Exception:
                    pass
                finally:
                    try:
                        s.close()
                    except Exception:
                        pass

        tasks = []
        max_hosts_total = 4096
        touched = 0
        for net in networks:
            for ip in net.hosts():
                tasks.append(asyncio.create_task(touch(str(ip))))
                touched += 1
                if touched >= max_hosts_total:
                    break
            if touched >= max_hosts_total:
                break

        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _resolve_mac_to_ip(self, mac, timeout=None):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + (timeout or self.mac_lookup_timeout)
        mac = self._normalize_mac(mac)

        def lookup_now():
            leases = self._get_dhcp_leases_by_mac()
            if mac in leases:
                return leases[mac]
            arp = self._get_arp_table_by_mac()
            if mac in arp:
                return arp[mac]
            return None

        ip = lookup_now()
        if ip:
            return ip

        networks = await self._get_local_ipv4_networks()
        last_probe = -1e9
        probe_interval = 5.0

        while True:
            ip = lookup_now()
            if ip:
                return ip

            now = loop.time()
            if now >= deadline:
                raise TimeoutError(f"Timeout resolving MAC {mac}")

            if networks and (now - last_probe) >= probe_interval:
                remaining = max(0.0, deadline - now)
                per_host_timeout = min(0.35, max(0.08, remaining / 20.0))
                await self._prime_arp_cache(networks, per_host_timeout=per_host_timeout)
                last_probe = loop.time()
                await asyncio.sleep(0.2)
            else:
                await asyncio.sleep(1)

    async def _resolve_imu_address(self, imu_id, address):
        if self._is_mac_address(address):
            return await self._resolve_mac_to_ip(address)
        return address

    def _get_imu_address(self, imu_id):
        if imu_id in self.imu_addresses:
            return self.imu_addresses[imu_id]
        if isinstance(self.IMUS, dict):
            return self.IMUS.get(imu_id, imu_id)
        return imu_id

    async def _connect_socket(self, ip, port):
        loop = asyncio.get_running_loop()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.setblocking(False)
        await asyncio.wait_for(loop.sock_connect(s, (ip, port)), timeout=self.connect_timeout)
        return s

    async def _connect_single_imu(self, imu_id, address):
        ip = await self._resolve_imu_address(imu_id, address)
        s = await self._connect_socket(ip, self.imu_port)
        return s, ip

    async def _get_battery_levels_async(self):
        battery_levels = {imu_id: None for imu_id, _ in self._iter_imus()}

        async def read_one(imu_id, address):
            sock = None
            try:
                sock, ip = await self._connect_single_imu(imu_id, address)
                await self._send_line(sock, CMD_BATTERY)
                line = await self._read_line(sock, timeout=2.0)

                if line is None or not line.startswith(RESP_BATTERY_PREFIX):
                    raise RuntimeError(
                        f"[{imu_id}] invalid battery response: {line!r}"
                    )

                value = line[len(RESP_BATTERY_PREFIX):].strip()
                if value.upper() == "NA":
                    level = None
                else:
                    level = int(value)
                    if not 0 <= level <= 100:
                        raise ValueError(
                            f"[{imu_id}] invalid battery level: {level}"
                        )

                print(f"Battery level of {imu_id}: {level if level is not None else 'N/A'}")
                return imu_id, level
            except (TimeoutError, ConnectionError, OSError) as e:
                print(f"[{imu_id}] battery read failed: {e}")
                return imu_id, "IMU non trovata"
            finally:
                if sock is not None:
                    try:
                        sock.close()
                    except OSError:
                        pass

        tasks = [
            asyncio.create_task(read_one(imu_id, address))
            for imu_id, address in self._iter_imus()
        ]
        if tasks:
            for imu_id, level in await asyncio.gather(*tasks):
                battery_levels[imu_id] = level

        return battery_levels

    async def _reconfigure_after_reconnect(self, imu_id, sock):
        await self._send_line(sock, self._build_timestamp_line(int(time.time())))
        await self._send_line(sock, self._build_config_line())
        await self._wait_for_config_ack(imu_id, sock)
        await self._send_line(sock, f"{CMD_ACTIVITY_PREFIX}START")

    async def _attempt_reconnect(self, imu_id):
        address = self._get_imu_address(imu_id)
        print(f"[{imu_id}] reconnect starting (address={address})")

        for attempt in range(self.reconnect_attempts):
            if self.stop_event.is_set() or self.stopping_by_user:
                return False

            sock = None
            try:
                print(f"[{imu_id}] reconnect attempt {attempt + 1}/{self.reconnect_attempts}")
                sock, ip = await self._connect_single_imu(imu_id, address)
                self.sockets[imu_id] = sock
                self.sensor_reading_payload[imu_id] = SENSOR_PACKET_DICT.copy()

                boot_id = await self._fetch_boot_id(sock, timeout=2.0)
                prev_boot_id = self.session_boot_id.get(imu_id)

                if boot_id is None:
                    print(f"[{imu_id}] boot_id unavailable; skip reconfigure")
                elif prev_boot_id is None or boot_id != prev_boot_id:
                    self.session_boot_id[imu_id] = boot_id
                    print(f"[{imu_id}] boot_id changed -> reconfigure")
                    await self._reconfigure_after_reconnect(imu_id, sock)
                else:
                    print(f"[{imu_id}] boot_id unchanged -> resume")

                print(f"[{imu_id}] Reconnected @ {ip}:{self.imu_port}")
                return True
            except Exception as e:
                if sock:
                    sock.close()
                print(
                    f"[{imu_id}] Reconnect failed ({attempt + 1}/{self.reconnect_attempts}): {e}"
                )
                await asyncio.sleep(self.reconnect_delay)

            print(f"[{imu_id}] reconnect attempts exhausted")
        return False

    def _format_line(self, line):
        if not line.endswith(LINE_END):
            line = f"{line}{LINE_END}"
        return line.encode("ascii")

    async def _send_line(self, sock, line):
        await asyncio.get_running_loop().sock_sendall(sock, self._format_line(line))

    async def _read_line(self, sock, timeout=2.0):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        buffer = bytearray()

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None

            chunk = await asyncio.wait_for(loop.sock_recv(sock, 1), timeout=remaining)
            if not chunk:
                return None
            buffer.extend(chunk)
            if chunk == b"\n":
                break

        return buffer.decode("ascii", errors="ignore").strip()

    async def _fetch_boot_id(self, sock, timeout=2.0):
        await self._send_line(sock, CMD_BOOT_ID)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            remaining = deadline - loop.time()

            if remaining <= 0:
                return None

            try:
                line = await self._read_line(sock, timeout=remaining)
            except asyncio.TimeoutError:
                print("[DEBUG] BOOT_ID timeout")
                return None

            if line is None:
                return None

            line = line.strip()

            if line.isdigit():
                return int(line)

    def _build_timestamp_line(self, timestamp):
        return f"{CMD_TIMESTAMP_PREFIX}{timestamp}"

    def _build_config_line(self):
        sampling_frequency = self.CAMPAIGN["sampling_frequency"]
        raw_value = "true" if self.CAMPAIGN["raw"] else "false"
        window_size = self.CAMPAIGN["window_size"]
        step_size = self.CAMPAIGN["step_size"]

        return (
            f"{CMD_CONFIG_PREFIX}"
            f"sampling_frequency={sampling_frequency},"
            f"raw={raw_value},"
            f"window_size={window_size},"
            f"step_size={step_size}"
        )

    async def _wait_for_config_ack(self, imu_id, sock, timeout=5.0):
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout

        while True:
            remaining = deadline - loop.time()
            if remaining <= 0:
                raise TimeoutError(f"[{imu_id}] timeout waiting ACK_OK")

            line = await self._read_line(sock, timeout=remaining)
            if line is None:
                raise TimeoutError(f"[{imu_id}] connection closed while waiting ACK_OK")

            if line == RESP_OK_CONFIG:
                continue
            if line == RESP_ACK_OK:
                return
            if line in (RESP_ACK_KO, RESP_ERR_CONFIG):
                raise RuntimeError(f"[{imu_id}] config failed: {line}")
    
    async def ping_imus(self, message=CMD_PING, timeout=2):
        """
        Invia un ping a tutte le IMU connesse e stampa la risposta.
        """

        loop = asyncio.get_running_loop()

        for imu_id, sock in self.sockets.items():
            try:
                if isinstance(message, bytes):
                    await loop.sock_sendall(sock, message)
                    data = await asyncio.wait_for(
                        loop.sock_recv(sock, 1024),
                        timeout=timeout
                    )
                    response = data.decode(errors="ignore").strip()
                else:
                    await self._send_line(sock, message)
                    response = await self._read_line(sock, timeout=timeout)

                if response is None:
                    print(f"[{imu_id}] timeout risposta ping")
                else:
                    print(f"[{imu_id}] risposta ping: {response}")

            except asyncio.TimeoutError:
                print(f"[{imu_id}] timeout risposta ping")

            except Exception as e:
                print(f"[{imu_id}] errore ping: {e}")


    async def _main(self):
        try:
            result = await self._connect_all()
            if not result:
                missing = [
                    imu_id
                    for imu_id, _ in self._iter_imus()
                    if imu_id not in self.sockets
                ]
                raise RuntimeError(
                    "Required WiFi IMUs not found: " + ", ".join(missing)
                )

            self.ready_connection.set()

            await self._send_timestamp_all()
            result = await self._send_config_all()
            if not result:
                raise RuntimeError("WiFi IMU configuration failed")

            await self._start_all()
            print("ALL IMUs started")
            await self._collect_all()
        finally:
            print("Closing main_process.")
            await self._disconnect_imus()
            self.stopping_by_user = False

    async def _disconnect_imus(self):
        for imu_id, s in list(self.sockets.items()):
            try:
                s.close()
            finally:
                print("Disconnected imu:", imu_id)
                self.sockets.pop(imu_id, None)
        self.stop_event.set()  
        
    # =========================
    # WIFI LOGIC
    # =========================

    async def _connect_all(self):
        self.sockets = {}
        self.sensor_reading_payload = {}
        self.imu_addresses = {}

        #await self._start_wifi_ap()

        await asyncio.sleep(1)

        for imu_id, address in self._iter_imus():
            self.imu_addresses[imu_id] = address

            connected = False
            for attempt in range(self.reconnect_attempts):
                s = None
                try:
                    s, ip = await self._connect_single_imu(imu_id, address)
                    print(f"[DEBUG] imu_id={imu_id}")
                    print(f"[DEBUG] MAC/address={address}")
                    print(f"[DEBUG] resolved IP={ip}")
                    print(f"[DEBUG] peer={s.getpeername()}")
                    connected = True
                    break
                except Exception as e:
                    if s:
                        s.close()
                    print(
                        f"[{imu_id}] connessione fallita, retry {attempt+1}/{self.reconnect_attempts}: {e}"
                    )
                    await asyncio.sleep(0.5)

            if not connected:
                print(f"Impossibile connettersi a {imu_id}")
                return False

            self.sockets[imu_id] = s
            self.sensor_reading_payload[imu_id] = SENSOR_PACKET_DICT.copy()

            print(f"[DEBUG] requesting BOOT_ID from {imu_id} at {ip}")
            boot_id = await self._fetch_boot_id(s, timeout=2.0)
            if boot_id is not None:
                self.session_boot_id[imu_id] = boot_id
                print(f"[{imu_id}] boot_id={boot_id}")
            else:
                print(f"[{imu_id}] boot_id unavailable")

            print(f"Connected to {imu_id} @ {ip}:{self.imu_port}")

        print("Tutte le IMU connesse")
        return True


    async def _start_wifi_ap(self):
        """
        Avvia un Access Point Wi-Fi usando NetworkManager (nmcli)
        """
        cmd = [
            "nmcli", "device", "wifi", "hotspot",
            "ifname", self.wifi_interface,
            "ssid", self.ap_ssid,
            "password", self.ap_password
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )

        await process.wait()

        if process.returncode != 0:
            raise RuntimeError(f"Errore avvio AP: {process.returncode}")

        print("Access Point Wi-Fi avviato")
        self._ap_started = True

    async def _stop_wifi_ap(self):
        """
        Disattiva l'Access Point Wi-Fi creato con NetworkManager.
        """

        # Metodo 1 (robusto): disattiva la connessione attiva sull'interfaccia
        cmd = [
            "nmcli", "device", "disconnect", self.wifi_interface
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL
        )

        await process.wait()

        if process.returncode != 0:
            raise RuntimeError(f"Errore arresto AP")

        print("Access Point Wi-Fi arrestato")
        self._ap_started = False

    def _get_dhcp_clients(self):
        """
        Ritorna dict: {hostname: ip} leggendo i lease DHCP di NetworkManager
        """
        if not os.path.exists(self.dhcp_leases_path):
            return {}

        clients = {}

        with open(self.dhcp_leases_path) as f:
            for line in f:
                parts = line.split()
                if len(parts) >= 4:
                    ip = parts[2]
                    hostname = parts[3]
                    if hostname != "*":
                        clients[hostname] = ip

        return clients



    async def _wait_for_all_hostnames(self, timeout=30):
        expected_ids = set(self.IMUS.keys() if isinstance(self.IMUS, dict) else self.IMUS)

        start = asyncio.get_running_loop().time()

        while True:
            clients = self._get_dhcp_clients()
            connected_ids = set(clients.keys())
            
            print("Trovati:", connected_ids)
            
            if expected_ids.issubset(connected_ids):
                return clients

            if asyncio.get_running_loop().time() - start > timeout:
                missing = expected_ids - connected_ids
                raise TimeoutError(f"IMU mancanti: {missing}")

            await asyncio.sleep(1)


    async def _send_config_all(self):
        for imu, s in self.sockets.items():
            try:
                await self._send_line(s, self._build_config_line())
                await self._wait_for_config_ack(imu, s)
            except Exception as e:
                print(f"Failed configuration to {imu}: {e}")
                return False
        return True

    async def _send_timestamp_all(self):
        timestamp = int(time.time())
        line = self._build_timestamp_line(timestamp)
        for s in self.sockets.values():
            await self._send_line(s, line)

    async def _start_all(self):
        for s in self.sockets.values():
            await self._send_line(s, f"{CMD_ACTIVITY_PREFIX}START")

    async def _stop_all(self):
        for imu_id, s in list(self.sockets.items()):
            try:
                await self._send_line(s, f"{CMD_ACTIVITY_PREFIX}STOP")
            except (ConnectionError, OSError) as e:
                print(f"[{imu_id}] STOP send failed: {e}")
            finally:
                try:
                    s.close()
                except OSError:
                    pass
                print("Disconnected imu:", imu_id)
        self.stop_event.set()
        if self._ap_started:
            await self._stop_wifi_ap()
        print("Clearing sockets")
        self.sockets.clear()

    async def _stop_all_test(self):
        for imu_id in self.IMUS:
            loop = asyncio.get_running_loop()
            s = self.sockets[imu_id] 
            await self._send_line(s, f"{CMD_ACTIVITY_PREFIX}STOP")
            s.close()
            print("Disconnected imu:",imu_id)
        self.stop_event.set()
        if self._ap_started:
            await self._stop_wifi_ap()

    async def _collect_all(self):
        tasks = [asyncio.create_task(self._collect_device(imu_id)) for imu_id, _ in self._iter_imus()]
        print("Started collecting")
        await asyncio.gather(*tasks)
        print("Finish collecting")

    async def _collect_device(self, imu):
        loop = asyncio.get_running_loop()
        buffer = bytearray()
        last_packet_time = loop.time()

        while not self.stop_event.is_set():
            sock = self.sockets.get(imu)
            if sock is None:
                if self.stopping_by_user:
                    break
                print(f"[{imu}] socket missing; attempting reconnect")
                if not await self._attempt_reconnect(imu):
                    self.stop_event.set()
                    break
                buffer.clear()
                continue

            packet_length = (
                SENSOR_PACKET_LENGTH
                if self.CAMPAIGN["raw"]
                else FEATURE_PACKET_LENGTH
            )

            try:
                chunk = await asyncio.wait_for(
                    loop.sock_recv(sock, packet_length),
                    timeout=self.recv_timeout,
                )
            except asyncio.TimeoutError:
                if self.idle_timeout is not None:
                    idle_for = loop.time() - last_packet_time
                    if idle_for >= self.idle_timeout:
                        if self.stopping_by_user:
                            break
                        print(
                            f"[{imu}] idle {idle_for:.1f}s; attempting reconnect"
                        )
                        if not await self._attempt_reconnect(imu):
                            self.stop_event.set()
                            break
                        buffer.clear()
                        last_packet_time = loop.time()
                continue
            except (ConnectionResetError, OSError) as e:
                if self.stopping_by_user:
                    break
                print(f"[{imu}] recv error ({e}); attempting reconnect")
                if not await self._attempt_reconnect(imu):
                    self.stop_event.set()
                    break
                buffer.clear()
                continue
            if not chunk:
                if self.stopping_by_user:
                    break
                print(f"[{imu}] recv returned empty; attempting reconnect")
                if not await self._attempt_reconnect(imu):
                    self.stop_event.set()
                    break
                buffer.clear()
                last_packet_time = loop.time()
                continue
            buffer.extend(chunk)
            last_packet_time = loop.time()

            while len(buffer) >= packet_length:
                packet = bytes(buffer[:packet_length])
                del buffer[:packet_length]

                if self.CAMPAIGN["raw"]:
                    self._parse_packet(imu, packet)
                else:
                    self._parse_feature_packet(imu, packet)
        
        print("Closing collect_device")

    # =========================
    # PACKET PARSER
    # =========================

    def _parse_packet(self, imu, data):
        rs = self.sensor_reading_payload[imu]

        offset = 0
        for k in SENSOR_PACKET_TEMPLATE[:-2]:
            rs[k] = int.from_bytes(data[offset:offset+2], "little")
            offset += 2

        rs["nth"] = int.from_bytes(data[offset:offset+2], "little")
        offset += 2

        rs["ts"] = int.from_bytes(data[offset:offset+4], "little")

        packet = {k: f"0x{rs[k]:04x}" for k in SENSOR_PACKET_TEMPLATE}
        packet["imuid"] = imu
        #packet["imuid"] = self.IMUS_ID_CUSTOM.get(imu, imu)
        packet["cname"] = self.CAMPAIGN["name"]

        self.packet_queue.put(packet)


    def _parse_feature_packet(self, imu, data):
        """
        Parse one FEATURES packet:
          FEATURE_COUNT float32 + uint16 counter + uint32 timestamp.

        This parser is generic with respect to the number of features:
        FEATURE_NAMES is the only manager-side feature list to update.
        """
        if len(data) != FEATURE_PACKET_LENGTH:
            raise ValueError(
                f"Invalid FEATURES packet length: {len(data)} "
                f"(expected {FEATURE_PACKET_LENGTH})"
            )

        values = struct.unpack(FEATURE_PACKET_FORMAT, data)

        packet = {
            name: value
            for name, value in zip(
                FEATURE_NAMES,
                values[:FEATURE_COUNT]
            )
        }

        packet["nth"] = values[FEATURE_COUNT]
        packet["ts"] = values[FEATURE_COUNT + 1]
        packet["imuid"] = imu
        packet["cname"] = self.CAMPAIGN["name"]

        self.packet_queue.put(packet)

# =========================
# END OF FILE
# =========================
