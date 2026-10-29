# Allow both direct script execution and package imports from the repository root.
import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utilities_library.BleAcquisitionMngr import BleAcquisitionMngr
import asyncio
import sys
from utilities_library.MqttTransmissionMngr import MqttTransmissionMngr


MQTT_BROKER = "131.175.120.117"
MQTT_PORT = 1883
MQTT_TOPIC = "aaac/campaign/imu"

COUNTER_MODULO = 65536


def parse_bool(value):
    value = str(value).strip().lower()
    if value in ("true", "1", "yes", "y"):
        return True
    if value in ("false", "0", "no", "n"):
        return False
    raise ValueError("raw must be True or False")


def parse_counter(value):
    if isinstance(value, int):
        return value
    return int(str(value), 0)


class PacketLossTracker:
    def __init__(self, imu_names):
        self.stats = {
            imu: {
                "received": 0,
                "lost": 0,
                "last_nth": None,
                "first_nth": None,
                "sequence_resets_or_reorders": 0,
            }
            for imu in imu_names
        }

    def update(self, packet):
        if "nth" not in packet:
            return

        imu = packet.get("imuid", "UNKNOWN")
        if imu not in self.stats:
            self.stats[imu] = {
                "received": 0,
                "lost": 0,
                "last_nth": None,
                "first_nth": None,
                "sequence_resets_or_reorders": 0,
            }

        nth = parse_counter(packet["nth"]) % COUNTER_MODULO
        st = self.stats[imu]
        st["received"] += 1

        if st["first_nth"] is None:
            st["first_nth"] = nth

            # Every new campaign starts from counter 0.
            if nth < COUNTER_MODULO // 2:
                st["lost"] += nth
                if nth > 0:
                    print(
                        f"[LOSS][{imu}] Missing {nth} initial packet(s): "
                        f"first received nth={nth}"
                    )

            st["last_nth"] = nth
            return

        expected = (st["last_nth"] + 1) % COUNTER_MODULO

        if nth == expected:
            st["last_nth"] = nth
            return

        forward_gap = (nth - expected) % COUNTER_MODULO

        if forward_gap < COUNTER_MODULO // 2:
            st["lost"] += forward_gap
            print(
                f"[LOSS][{imu}] expected nth={expected}, "
                f"received nth={nth} -> LOST {forward_gap}"
            )
        else:
            st["sequence_resets_or_reorders"] += 1
            print(
                f"[LOSS][{imu}] counter reset/reorder: "
                f"last={st['last_nth']}, received={nth}"
            )

        st["last_nth"] = nth

    def print_summary(self):
        print("\n================ PACKET LOSS SUMMARY ================")

        total_received = 0
        total_lost = 0

        for imu, st in self.stats.items():
            received = st["received"]
            lost = st["lost"]
            expected = received + lost
            pct = (lost / expected * 100.0) if expected else 0.0

            total_received += received
            total_lost += lost

            print(f"\nIMU: {imu}")
            print(f"  Received packets : {received}")
            print(f"  Lost packets     : {lost}")
            print(f"  Expected total   : {expected}")
            print(f"  Packet loss      : {pct:.3f} %")
            print(f"  First nth        : {st['first_nth']}")
            print(f"  Last nth         : {st['last_nth']}")
            print(
                f"  Resets/reorders  : "
                f"{st['sequence_resets_or_reorders']}"
            )

        total_expected = total_received + total_lost
        total_pct = (
            total_lost / total_expected * 100.0
            if total_expected else 0.0
        )

        print("\n---------------- TOTAL ----------------")
        print(f"Received packets : {total_received}")
        print(f"Lost packets     : {total_lost}")
        print(f"Expected total   : {total_expected}")
        print(f"Packet loss      : {total_pct:.3f} %")
        print("=====================================================\n")



"""{
    "acc_mag_max": ...,
    "acc_mag_mean": ...,
    "acc_mag_std": ...,

    ...

    "dynamic_sma": ...,
    "jerk_max": ...,
    "jerk_mean": ...,

    "nth": 3,
    "ts": 1789400000,
    "imuid": "IMU5B35",
    "cname": "campaign01",
    "mode": "features"
}"""
async def main():
    ble_manager = None
    db_mqtt_manager = None
    loss_tracker = None

    try:
        # RAW:
        # python3 Test_Reconnect_features.py IMU5B35 campaign01 10 True
        #
        # FEATURES:
        # python3 Test_Reconnect_features.py IMU5B35 campaign01 100 False 300 100
        BSN_IMUS = sys.argv[1].split("-")
        name = sys.argv[2]
        sampling_frequency = int(sys.argv[3])
        raw = parse_bool(sys.argv[4])

        window_size = int(sys.argv[5]) if len(sys.argv) > 5 else 300
        step_size = int(sys.argv[6]) if len(sys.argv) > 6 else 100

        print(
            f"Campaign mode: {'RAW' if raw else 'FEATURES'} | "
            f"freq={sampling_frequency} Hz | "
            f"window={window_size} | step={step_size}"
        )

        ble_manager = BleAcquisitionMngr()
        db_mqtt_manager = MqttTransmissionMngr()
        loss_tracker = PacketLossTracker(BSN_IMUS)

        ble_manager.set_imus(BSN_IMUS)
        ble_manager.set_adapter("hci0")

        ble_manager.set_campaign(
            name,
            sampling_frequency,
            raw=raw,
            window_size=window_size,
            step_size=step_size
        )

        db_mqtt_manager.set_db_mqtt(
            MQTT_BROKER,
            MQTT_PORT,
            MQTT_TOPIC
        )
        db_mqtt_manager.start_db_mqtt()

        ble_manager.start_collection()
        ble_manager.wait_connection()

        while True:
            pck = ble_manager.get_packet(True, 20)
            if pck is None:
                break

            print(pck)
            loss_tracker.update(pck)

            csv_data_d = ",".join(
                f"{k}={v}" for k, v in pck.items()
            )
            #db_mqtt_manager.put_row(csv_data_d)

    except KeyboardInterrupt:
        print("Stopped by user.")

    except Exception as e:
        print(f"Interrupted: {e}")

    finally:
        if loss_tracker is not None:
            loss_tracker.print_summary()

        if ble_manager is not None:
            try:
                ble_manager.stop_collection()
            except Exception as e:
                print(f"Error while stopping BLE collection: {e}")

        if db_mqtt_manager is not None:
            try:
                db_mqtt_manager.stop_db_mqtt()
            except Exception as e:
                print(f"Error while stopping MQTT: {e}")


if __name__ == "__main__":
    asyncio.run(main())
