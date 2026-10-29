# Allow both direct script execution and package imports from the repository root.
import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[1]))

from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr
import asyncio
import json
import argparse
from datetime import datetime

COUNTER_MAX = 65535


def analyze_packet_loss(packets):
    """
    Analizza il counter 'nth' dei pacchetti e individua eventuali
    pacchetti mancanti.

    Gestisce anche il rollover:
        65534 -> 65535 -> 0 -> 1
    """

    if not packets:
        print("\nNessun pacchetto ricevuto.")
        return

    # Raggruppamento per IMU, utile anche se in futuro
    # vengono testate più IMU contemporaneamente.
    packets_by_imu = {}

    for packet in packets:
        imu_id = packet.get("imuid", "UNKNOWN")
        packets_by_imu.setdefault(imu_id, []).append(packet)

    print("\n" + "=" * 70)
    print("ANALISI PACKET LOSS")
    print("=" * 70)

    for imu_id, imu_packets in packets_by_imu.items():

        counters = []

        for packet in imu_packets:
            nth = packet.get("nth")

            if nth is None:
                continue

            try:
                # WifiAcquisitionMngr restituisce valori del tipo "0x001a"
                if isinstance(nth, str):
                    counter = int(nth, 16)
                else:
                    counter = int(nth)

                counters.append(counter)

            except (ValueError, TypeError):
                print(
                    f"[{imu_id}] Counter nth non valido: {nth}"
                )

        print(f"\nIMU: {imu_id}")
        print(f"Pacchetti ricevuti: {len(imu_packets)}")
        print(f"Counter validi:     {len(counters)}")

        if len(counters) < 2:
            print("Pacchetti insufficienti per analizzare le perdite.")
            continue

        missing_packets = 0
        loss_events = []
        duplicate_packets = 0

        for index in range(1, len(counters)):

            previous = counters[index - 1]
            current = counters[index]

            # Counter atteso tenendo conto del rollover a 16 bit
            expected = (previous + 1) % (COUNTER_MAX + 1)

            if current == expected:
                continue

            # Stesso counter due volte
            if current == previous:
                duplicate_packets += 1

                loss_events.append({
                    "type": "duplicate",
                    "packet_index": index,
                    "previous": previous,
                    "current": current
                })

                continue

            # Numero di pacchetti saltati, considerando rollover
            missing = (
                current - expected
            ) % (COUNTER_MAX + 1)

            missing_packets += missing

            loss_events.append({
                "type": "loss",
                "packet_index": index,
                "previous": previous,
                "expected": expected,
                "current": current,
                "missing": missing
            })

        expected_total = len(counters) + missing_packets

        if expected_total > 0:
            loss_percentage = (
                missing_packets / expected_total
            ) * 100
        else:
            loss_percentage = 0

        print(f"Primo counter:      {counters[0]}")
        print(f"Ultimo counter:     {counters[-1]}")
        print(f"Pacchetti persi:    {missing_packets}")
        print(f"Duplicati:          {duplicate_packets}")
        print(f"Packet loss:        {loss_percentage:.4f}%")

        if not loss_events:
            print("Nessuna perdita rilevata.")
        else:
            print("\nEventi anomali:")

            for event in loss_events:

                if event["type"] == "loss":
                    print(
                        f"  Packet index {event['packet_index']}: "
                        f"{event['previous']} -> {event['current']} "
                        f"(atteso {event['expected']}, "
                        f"persi {event['missing']})"
                    )

                elif event["type"] == "duplicate":
                    print(
                        f"  Packet index {event['packet_index']}: "
                        f"counter duplicato {event['current']}"
                    )

    print("\n" + "=" * 70)


def str_to_bool(value):
    """Converte true/false, 1/0, yes/no in bool."""
    if isinstance(value, bool):
        return value

    value = value.lower()

    if value in ("true", "1", "yes", "y"):
        return True

    if value in ("false", "0", "no", "n"):
        return False

    raise argparse.ArgumentTypeError(
        "Valore booleano non valido. Usa true oppure false."
    )


def split_imu_addresses(values):
    """Separa gli indirizzi IMU usando '-' come separatore tra i MAC."""
    addresses = []

    for value in values:
        parts = [address.strip() for address in value.split("-")]

        if any(not address for address in parts):
            raise argparse.ArgumentTypeError(
                "Lista IMU non valida: usa '-' tra due MAC/IP."
            )

        addresses.extend(parts)

    return addresses


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Test acquisizione IMU via WiFi in modalità RAW o FEATURES."
        )
    )

    parser.add_argument(
        "--imus",
        nargs="+",
        default=["b0:b2:1c:4a:00:38"],
        help=(
            "MAC/IP delle IMU separati da '-'. Esempio: "
            "--imus b0:b2:1c:4a:00:38-e0:72:a1:21:6a:20"
        ),
    )

    parser.add_argument(
        "--wifi-interface",
        default="wlp2s0",
        help="Interfaccia WiFi usata per l'Access Point.",
    )

    parser.add_argument(
        "--ssid",
        default="G5_7411",
        help="SSID dell'Access Point.",
    )

    parser.add_argument(
        "--password",
        default="edna modem",
        help="Password dell'Access Point.",
    )

    parser.add_argument(
        "--campaign",
        default="prova",
        help="Nome della campagna.",
    )

    parser.add_argument(
        "--freq",
        type=int,
        default=100,
        help="Frequenza di campionamento in Hz.",
    )

    parser.add_argument(
        "--raw",
        type=str_to_bool,
        default=True,
        help=(
            "Modalità di acquisizione: "
            "true = RAW, false = FEATURES."
        ),
    )

    parser.add_argument(
        "--window-size",
        type=int,
        default=300,
        help=(
            "Dimensione della finestra in campioni. "
            "Usata in modalità FEATURES."
        ),
    )

    parser.add_argument(
        "--step-size",
        type=int,
        default=100,
        help=(
            "Step della sliding window in campioni. "
            "Usato in modalità FEATURES."
        ),
    )

    parser.add_argument(
        "--packet-timeout",
        type=float,
        default=20.0,
        help="Timeout get_packet() in secondi.",
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "File JSONL di output. Se omesso viene generato "
            "automaticamente con timestamp."
        ),
    )

    args = parser.parse_args()
    args.imus = split_imu_addresses(args.imus)
    return args

"""
python3 example_WIFI.py \
    --imus b0:b2:1c:4a:00:38-e0:72:a1:21:6a:20 \
    --wifi-interface wlp2s0 \
    --ssid G5_7411 \
    --password "edna modem" \
    --campaign prova \
    --freq 100 \
    --raw false \
    --window-size 300 \
    --step-size 100 \
    --packet-timeout 20

python3 example_WIFI.py \
    --imus b0:b2:1c:4a:00:38-e0:72:a1:21:6a:20 \
    --wifi-interface wlp2s0 \
    --ssid G5_7411 \
    --password "edna modem" \
    --campaign prova \
    --freq 100 \
    --raw true \
    --packet-timeout 20

Esp32 C3 1
14:31:29.273 -> [DEVICE] IMU ID: IMU6A20
14:31:29.273 -> [DEVICE] MAC:    E0:72:A1:21:6A:20

Esp32 C3 2
14:31:29.273 -> [DEVICE] IMU ID: IMU3960
14:31:29.273 -> [DEVICE] MAC:    E0:72:A1:21:39:60
"""
def main(args):

    manager = None
    packets = []

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    if args.output:
        filename = args.output
    else:
        mode = "raw" if args.raw else "features"
        filename = f"wifi_{mode}_{timestamp}.jsonl"

    try:
        manager = WifiAcquisitionMngr()

        manager.set_imus(args.imus)

        manager.set_access_point(
            args.wifi_interface,
            args.ssid,
            args.password
        )

        manager.set_campaign(
            args.campaign,
            args.freq,
            raw=args.raw,
            window_size=args.window_size,
            step_size=args.step_size
        )

        print("\nConfigurazione test:")
        print(f"  IMU              : {args.imus}")
        print(f"  WiFi interface   : {args.wifi_interface}")
        print(f"  SSID             : {args.ssid}")
        print(f"  Campaign         : {args.campaign}")
        print(f"  Frequency        : {args.freq} Hz")
        print(f"  Mode             : {'RAW' if args.raw else 'FEATURES'}")

        if not args.raw:
            print(f"  Window size      : {args.window_size} samples")
            print(f"  Step size        : {args.step_size} samples")

        manager.start_collection()
        manager.wait_connection()

        print(f"\nSalvataggio pacchetti in: {filename}\n")

        i = 0

        # buffering=1 -> line buffering:
        # ogni riga viene scritta subito sul file.
        with open(
            filename,
            "w",
            encoding="utf-8",
            buffering=1
        ) as json_file:

            while True:

                pck = manager.get_packet(
                    True,
                    args.packet_timeout
                )

                if pck is None:
                    print(
                        "\nTimeout: nessun pacchetto ricevuto "
                        f"negli ultimi {args.packet_timeout:g} secondi."
                    )
                    break

                print(pck)

                # Conservazione in RAM per l'analisi finale
                packets.append(pck)

                # Scrittura immediata su disco
                json.dump(
                    pck,
                    json_file,
                    ensure_ascii=False
                )

                json_file.write("\n")

                # Forza il flush per minimizzare la perdita
                # di dati in caso di interruzione improvvisa.
                json_file.flush()

                i += 1

                # Test disconnessione opzionale:
                #
                # if i == 50:
                #     manager.force_disconnect()

    except KeyboardInterrupt:
        print("\nStopped by user.")

    except Exception as e:
        print(f"\nInterrupted: {e}")

    finally:

        if manager is not None:
            try:
                manager.stop_collection()
            except Exception as e:
                print(
                    f"Errore durante stop_collection(): {e}"
                )

        print(f"\nTotale pacchetti acquisiti: {len(packets)}")
        print(f"File salvato: {filename}")

        # Analisi finale packet loss
        analyze_packet_loss(packets)


if __name__ == "__main__":
    args = parse_args()
    main(args)
