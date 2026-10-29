from flask import Flask, request, jsonify
import numpy as np
import tensorflow as tf
import json
from datetime import datetime, timezone

app = Flask(__name__)


# =================================================
# Load CNN model
# =================================================

MODEL_FILE = "imu_activity_cnn.keras"

model = tf.keras.models.load_model(MODEL_FILE)

print("CNN model loaded successfully!")


# =================================================
# Load normalization values
# =================================================

mean = np.load("imu_mean.npy")
std = np.load("imu_std.npy")

print("Normalization values loaded!")


# =================================================
# Load activity names
# =================================================

with open("activity_names.json", "r") as f:
    activity_names = json.load(f)

print("Activity labels loaded!")


# =================================================
# IMU sample storage
# =================================================

samples = []

WINDOW_SIZE = 100


# =================================================
# Store latest prediction
# =================================================

latest_prediction = {
    "status": "waiting",
    "activity": "Waiting",
    "confidence": 0.0,
    "timestamp": None
}


# =================================================
# Receive IMU data from ESP32
# =================================================

@app.route("/imu", methods=["POST"])
def receive_imu():

    global samples
    global latest_prediction

    try:

        data = request.get_json()

        # -------------------------------------------------
        # Get IMU values
        # -------------------------------------------------

        ax = float(data["ax"])
        ay = float(data["ay"])
        az = float(data["az"])

        gx = float(data["gx"])
        gy = float(data["gy"])
        gz = float(data["gz"])


        # -------------------------------------------------
        # Add sample
        # -------------------------------------------------

        samples.append([
            ax,
            ay,
            az,
            gx,
            gy,
            gz
        ])


        # -------------------------------------------------
        # Print received sample
        # -------------------------------------------------

        print(
            f"Sample {len(samples)}/{WINDOW_SIZE} | "
            f"ax={ax:.0f} "
            f"ay={ay:.0f} "
            f"az={az:.0f} "
            f"gx={gx:.0f} "
            f"gy={gy:.0f} "
            f"gz={gz:.0f}"
        )


        # =================================================
        # When 100 samples are collected
        # =================================================

        if len(samples) >= WINDOW_SIZE:

            # -------------------------------------------------
            # Convert samples to NumPy array
            # -------------------------------------------------

            window = np.array(
                samples[-WINDOW_SIZE:],
                dtype=np.float32
            )

            # Shape:
            # (100, 6)


            # -------------------------------------------------
            # Add batch dimension
            # -------------------------------------------------

            window = np.expand_dims(window, axis=0)

            # Shape:
            # (1, 100, 6)


            # =================================================
            # Normalize using training values
            # =================================================

            window_normalized = (
                window - mean
            ) / (std + 1e-8)


            # =================================================
            # CNN prediction
            # =================================================

            probabilities = (
                model(
                    window_normalized,
                    training=False
                ).numpy()[0]
            )

            prediction = int(
                np.argmax(probabilities)
            )

            confidence = float(
                probabilities[prediction] * 100
            )


            # -------------------------------------------------
            # Get activity name
            # -------------------------------------------------

            activity = activity_names[
                str(prediction)
            ]


            # =================================================
            # Get current UTC timestamp
            # =================================================

            timestamp = datetime.now(
                timezone.utc
            ).isoformat()


            # =================================================
            # Update latest prediction
            # =================================================

            latest_prediction = {
                "status": "prediction",
                "activity": activity,
                "confidence": round(confidence, 2),
                "timestamp": timestamp
            }


            # =================================================
            # Print prediction
            # =================================================

            print()
            print("================================")
            print("       ACTIVITY DETECTED")
            print("================================")
            print(f"Activity   : {activity}")
            print(f"Confidence : {confidence:.2f}%")
            print(f"Timestamp  : {timestamp}")
            print("================================")
            print()


            # -------------------------------------------------
            # Clear samples for next window
            # -------------------------------------------------

            samples.clear()


            # -------------------------------------------------
            # Send prediction response to ESP32
            # -------------------------------------------------

            return jsonify({
                "status": "prediction",
                "activity": activity,
                "confidence": round(confidence, 2),
                "timestamp": timestamp
            })


        # =================================================
        # Still collecting samples
        # =================================================

        return jsonify({
            "status": "collecting",
            "samples": len(samples),
            "window_size": WINDOW_SIZE
        })


    except Exception as e:

        print("ERROR:", e)

        return jsonify({
            "status": "error",
            "message": str(e)
        }), 400


# =================================================
# Latest activity API
# Used by mobile application
# =================================================

@app.route("/latest", methods=["GET"])
def latest():

    response = latest_prediction.copy()

    # Current number of samples
    response["samples"] = len(samples)

    # Total samples required for prediction
    response["window_size"] = WINDOW_SIZE

    return jsonify(response)


# =================================================
# Server health API
# Used by mobile application
# =================================================

@app.route("/health", methods=["GET"])
def health():

    return jsonify({
        "status": "online",
        "model": "1D CNN",
        "activities": 6
    })


# =================================================
# Start server
# =================================================

if __name__ == "__main__":

    print()
    print("==========================================")
    print("        IMU ACTIVITY CNN SERVER")
    print("==========================================")
    print("Model      : 1D CNN")
    print("Activities : 6")
    print("Window     : 100 samples")
    print("Server     : http://10.43.155.161:5000")
    print("==========================================")
    print("Waiting for ESP32...")
    print()

    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
