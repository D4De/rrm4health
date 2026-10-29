#!/usr/bin/env python3
"""
Fall-detection runtime using the current WiFi IMU manager.

Pipeline
--------
ESP32-C3 + MPU6050
    -> FEATURES packet (28 features)
    -> convert accelerometer-derived features from g-based units to m/s^2-based units
    -> static/dynamic gate using dynamic_sma
    -> if static:
           "static (standing/sitting/lying)"
       else:
           sklearn Pipeline from mlp_dynamic_only_model.pkl
           -> walking / running / fall / fast walking

Important
---------
The model file must be the one produced by train_dynamic_model.py, i.e. a
joblib-saved sklearn Pipeline containing:
    StandardScaler + MLPClassifier

Expected dynamic class mapping:
    0 -> walking
    1 -> running
    5 -> fall
    6 -> fast walking

Recommended acquisition configuration:
    sampling_frequency = 200 Hz
    raw = False
    window_size = 300
    step_size = 300

This yields independent 1.5 s windows, matching the training script.
"""

import argparse
import json
from datetime import datetime

import joblib
import numpy as np

import sys as _sys
from pathlib import Path as _Path

if __package__ in (None, ""):
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))

from utilities_library.WifiAcquisitionMngr import WifiAcquisitionMngr


# =============================================================================
# FEATURE ORDER
# =============================================================================

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

CLASS_LABELS = {
    0: "walking",
    1: "running",
    5: "fall",
    6: "fast walking",
}

# Candidate threshold obtained from the SisFall low-motion analysis.
# IMPORTANT: this threshold is defined in the same acceleration scale used
# during training, after g -> m/s^2 conversion of the accelerometer-derived
# features.
STATIC_SMA_THRESHOLD = 0.325226

G_TO_MS2 = 9.80665

# Features that scale linearly with acceleration.
# The firmware currently computes them from acceleration in g, while the
# training pipeline uses the SisFall scale corresponding to m/s^2.
ACCELERATION_FEATURES = {
    "acc_mag_max",
    "acc_mag_mean",
    "acc_mag_std",

    "ax_mean",
    "ax_max",
    "ax_std",

    "ay_mean",
    "ay_max",
    "ay_std",

    "az_mean",
    "az_max",
    "az_std",

    "dynamic_sma",
    "jerk_max",
    "jerk_mean",
}


# =============================================================================
# UTILITIES
# =============================================================================

def str_to_bool(value):
    if isinstance(value, bool):
        return value

    value = value.lower()

    if value in ("true", "1", "yes", "y"):
        return True

    if value in ("false", "0", "no", "n"):
        return False

    raise argparse.ArgumentTypeError(
        "Invalid boolean value. Use true or false."
    )


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Fall-detection runtime using ESP32-C3 + MPU6050 FEATURES packets."
        )
    )

    parser.add_argument(
        "--model",
        default="mlp_dynamic_only_model.pkl",
        help="Path to the trained sklearn/joblib model.",
    )

    parser.add_argument(
        "--imus",
        nargs="+",
        default=["b0:b2:1c:4a:00:38"],
        help="List of IMU MAC/IP addresses.",
    )

    parser.add_argument(
        "--wifi-interface",
        default="wlp2s0",
        help="WiFi interface used by the access point.",
    )

    parser.add_argument(
        "--ssid",
        default="G5_7411",
        help="WiFi access-point SSID.",
    )

    parser.add_argument(
        "--password",
        default="edna modem",
        help="WiFi access-point password.",
    )

    parser.add_argument(
        "--campaign",
        default="fall_detection",
        help="Campaign name.",
    )

    parser.add_argument(
        "--freq",
        type=int,
        default=200,
        help="IMU sampling frequency in Hz.",
    )

    parser.add_argument(
        "--window-size",
        type=int,
        default=300,
        help="Feature window size in samples.",
    )

    parser.add_argument(
        "--step-size",
        type=int,
        default=300,
        help="Feature window step in samples.",
    )

    parser.add_argument(
        "--packet-timeout",
        type=float,
        default=20.0,
        help="Timeout while waiting for a FEATURES packet.",
    )

    parser.add_argument(
        "--static-threshold",
        type=float,
        default=STATIC_SMA_THRESHOLD,
        help="dynamic_sma threshold for static/dynamic gating.",
    )

    parser.add_argument(
        "--output",
        default=None,
        help=(
            "Optional JSONL output file. If omitted, a timestamped filename "
            "is generated."
        ),
    )

    return parser.parse_args()


def convert_packet_to_training_units(packet):
    """
    Convert only accelerometer-derived features.

    Firmware side:
        acceleration-related features are computed from g.

    Training side:
        the SisFall preprocessing operates on an acceleration scale
        corresponding to m/s^2.

    Gyroscope features and tilt are NOT converted.
    """
    converted = dict(packet)

    for name in ACCELERATION_FEATURES:
        if name in converted:
            converted[name] = float(converted[name]) * G_TO_MS2

    return converted


def build_model_vector(packet):
    """
    Return the 28-feature vector in exactly the training order.
    """
    missing = [
        name
        for name in FEATURE_NAMES
        if name not in packet
    ]

    if missing:
        raise KeyError(
            "Missing feature(s) in packet: "
            + ", ".join(missing)
        )

    return np.array(
        [float(packet[name]) for name in FEATURE_NAMES],
        dtype=np.float64,
    ).reshape(1, -1)


def classify_packet(packet, model, static_threshold):
    """
    Classify one FEATURES packet.

    Returns:
        dict with label, branch, dynamic_sma, and optionally model class.
    """
    converted = convert_packet_to_training_units(packet)

    dynamic_sma = float(converted["dynamic_sma"])

    if dynamic_sma <= static_threshold:
        return {
            "label": "static (standing/sitting/lying)",
            "branch": "static",
            "dynamic_sma": dynamic_sma,
            "model_class": None,
        }

    vector = build_model_vector(converted)

    prediction = int(model.predict(vector)[0])

    label = CLASS_LABELS.get(
        prediction,
        f"unknown_dynamic_class_{prediction}",
    )

    result = {
        "label": label,
        "branch": "dynamic",
        "dynamic_sma": dynamic_sma,
        "model_class": prediction,
    }

    # Keep confidence/probabilities when the sklearn model supports them.
    if hasattr(model, "predict_proba"):
        probabilities = model.predict_proba(vector)[0]

        classes = model.classes_

        result["probabilities"] = {
            CLASS_LABELS.get(int(cls), str(int(cls))): float(prob)
            for cls, prob in zip(classes, probabilities)
        }

        result["confidence"] = float(np.max(probabilities))

    return result


# =============================================================================
# MAIN
# =============================================================================

def main(args):
    print("=" * 72)
    print("FALL DETECTION APPLICATION")
    print("=" * 72)

    print(f"Loading model: {args.model}")
    model = joblib.load(args.model)

    print("Model loaded successfully.")
    print(f"Static SMA threshold: {args.static_threshold:.6f}")
    print(f"Sampling frequency:   {args.freq} Hz")
    print(f"Window size:          {args.window_size} samples")
    print(f"Step size:            {args.step_size} samples")

    if args.freq > 0:
        print(
            f"Window duration:      "
            f"{args.window_size / args.freq:.3f} s"
        )

    if args.step_size == args.window_size:
        print("Window overlap:       0%")
    else:
        overlap = (
            1.0 - (args.step_size / args.window_size)
        ) * 100.0

        print(f"Window overlap:       {overlap:.2f}%")

    print("=" * 72)

    manager = None
    output_file = None

    if args.output:
        filename = args.output
    else:
        timestamp = datetime.now().strftime(
            "%Y%m%d_%H%M%S"
        )
        filename = (
            f"fall_detection_{timestamp}.jsonl"
        )

    try:
        manager = WifiAcquisitionMngr()

        manager.set_imus(args.imus)

        manager.set_access_point(
            args.wifi_interface,
            args.ssid,
            args.password,
        )

        # FEATURES mode only.
        manager.set_campaign(
            args.campaign,
            args.freq,
            raw=False,
            window_size=args.window_size,
            step_size=args.step_size,
        )

        manager.start_collection()
        manager.wait_connection()

        print()
        print("Acquisition started.")
        print(f"Saving detections to: {filename}")
        print()

        output_file = open(
            filename,
            "w",
            encoding="utf-8",
            buffering=1,
        )

        while True:
            packet = manager.get_packet(
                True,
                args.packet_timeout,
            )

            if packet is None:
                print(
                    f"No FEATURES packet received for "
                    f"{args.packet_timeout:g} seconds."
                )
                break

            result = classify_packet(
                packet,
                model,
                args.static_threshold,
            )

            record = {
                "imuid": packet.get(
                    "imuid",
                    "UNKNOWN",
                ),
                "campaign": packet.get(
                    "cname",
                    args.campaign,
                ),
                "nth": packet.get("nth"),
                "ts": packet.get("ts"),
                "label": result["label"],
                "branch": result["branch"],
                "dynamic_sma": result[
                    "dynamic_sma"
                ],
            }

            if result["model_class"] is not None:
                record["model_class"] = result[
                    "model_class"
                ]

            if "confidence" in result:
                record["confidence"] = result[
                    "confidence"
                ]

            if "probabilities" in result:
                record["probabilities"] = result[
                    "probabilities"
                ]

            # Console output
            print(
                f"[{record['imuid']}] "
                f"nth={record['nth']} "
                f"ts={record['ts']} "
                f"SMA={record['dynamic_sma']:.6f} "
                f"-> {record['label']}",
                end="",
            )

            if "confidence" in record:
                print(
                    f" "
                    f"(confidence="
                    f"{record['confidence']:.3f})"
                )
            else:
                print()

            # Save one detection per JSON line.
            json.dump(
                record,
                output_file,
                ensure_ascii=False,
            )
            output_file.write("\n")
            output_file.flush()

    except KeyboardInterrupt:
        print("\nStopped by user.")

    except Exception as exc:
        print(f"\nApplication interrupted: {exc}")
        raise

    finally:
        if output_file is not None:
            output_file.close()

        if manager is not None:
            try:
                manager.stop_collection()
            except Exception as exc:
                print(
                    f"Error during stop_collection(): "
                    f"{exc}"
                )

        print("Application terminated.")


if __name__ == "__main__":
    main(parse_args())
