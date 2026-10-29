#!/usr/bin/env python3
import argparse
import asyncio
import json
import random
import signal
import time
import sys
from bleak import BleakClient, BleakScanner
import paho.mqtt.publish as publish
from typing import List

# Replace with your device name or address
# DB Cristiana: 131.175.120.117
MQTT_BROKER = "localhost"
MQTT_PORT   = 1883
MQTT_TOPIC  = "aaac/campaign/imu"

SENSOR_PACKET_TEMPLATE  = ["ax", "ay", "az", "gx", "gy", "gz", "mx", "my", "mz", "nth", "ts", "imuid", "cname"]


def parse_imu_list(raw: str) -> List[str]:
    # Accetta formati tipo:
    # "IMU1-IMU2-IMU3" oppure "IMU1,IMU2,IMU3" oppure mix
    print(raw)
    parts = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts.extend([p.strip() for p in chunk.split("-") if p.strip()])
    if not parts:
        raise ValueError("Lista IMU vuota o non valida.")
    return parts


def rand_sensor_value() -> float:
    # Puoi cambiare range e distribuzione a piacere
    return round(random.uniform(-10.0, 10.0), 6)


def build_payload(nth: int, cname: str, imus: List[str]) -> dict:
    ts = time.time()  # timestamp in secondi (float)
    payload = {
        "ax": rand_sensor_value(),
        "ay": rand_sensor_value(),
        "az": rand_sensor_value(),
        "gx": rand_sensor_value(),
        "gy": rand_sensor_value(),
        "gz": rand_sensor_value(),
        "mx": rand_sensor_value(),
        "my": rand_sensor_value(),
        "mz": rand_sensor_value(),
        "nth": nth,
        "ts": ts,
        "imuid": random.choice(imus),
        "cname": cname,
    }
    # Se vuoi assicurarti l'ordine "template", puoi serializzare usando list/tuple,
    # ma in JSON l'ordine non è semanticamente importante.
    return payload


async def publisher(stop_event: asyncio.Event, imus: List[str], cname: str, nth_start: int) -> None:
    nth = nth_start
    reconnect_delay_s = 2.0

    period_s = 0.1  # 10 msg/s

    while not stop_event.is_set():
        try:
            next_tick = time.monotonic()
            while not stop_event.is_set():
                payload = build_payload(nth, cname, imus)
                # formato: ax:...,ay:...,...
                result = ",".join(f"{k}:{payload[k]}" for k in SENSOR_PACKET_TEMPLATE)
                # publish.single è bloccante -> eseguilo in thread
                await asyncio.to_thread(
                    publish.single,
                    topic=MQTT_TOPIC,
                    payload=result,
                    hostname=MQTT_BROKER,
                    port=MQTT_PORT,
                )
                print(payload, result)
                nth += 1
                next_tick += period_s
                sleep_for = next_tick - time.monotonic()
                if sleep_for > 0:
                    await asyncio.sleep(sleep_for)
                else:
                    next_tick = time.monotonic()

        except Exception as e:
            if not stop_event.is_set():
                print(f"[MQTT] Errore: {e}. Riprovo tra {reconnect_delay_s:.1f}s...")
                await asyncio.sleep(reconnect_delay_s)


def install_signal_handlers(stop_event: asyncio.Event) -> None:
    loop = asyncio.get_running_loop()

    def _ask_exit() -> None:
        stop_event.set()

    # SIGTERM richiesto
    try:
        loop.add_signal_handler(signal.SIGTERM, _ask_exit)
    except NotImplementedError:
        # Windows: SIGTERM handler potrebbe non essere supportato così
        signal.signal(signal.SIGTERM, lambda *_: _ask_exit())

    # Utile anche Ctrl+C
    try:
        loop.add_signal_handler(signal.SIGINT, _ask_exit)
    except NotImplementedError:
        signal.signal(signal.SIGINT, lambda *_: _ask_exit())


async def main() -> int:
    imus = parse_imu_list(sys.argv[1])
    cname = sys.argv[2]
    nth_start = int(sys.argv[3])

    stop_event = asyncio.Event()
    install_signal_handlers(stop_event)

    print(f"[START] broker={MQTT_BROKER}:{MQTT_PORT} topic={MQTT_TOPIC}")
    print(f"[START] cname={cname} nth_start={nth_start} imus={imus}")
    print("[INFO] Invio 10 msg/s. Termina con SIGTERM (o Ctrl+C).")

    task = asyncio.create_task(publisher(stop_event, imus, cname, nth_start))

    await stop_event.wait()
    print("[STOP] SIGTERM ricevuto: chiusura in corso...")

    # Aspetta che il task finisca (publisher esce al prossimo ciclo)
    await task
    print("[STOP] Terminato.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
