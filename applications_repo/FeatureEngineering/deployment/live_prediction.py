# ============================================
# IMU-Based Human Activity Recognition
# Real-Time Deployment (PC Side)
# ============================================

import socket
import numpy as np
import joblib
import json
from collections import deque

# ============================================
# CONFIGURATION
# ============================================

UDP_IP = "0.0.0.0"     # Listen on all interfaces
UDP_PORT = 5005       # Must match Nicla main.py

WINDOW_SIZE = 20
STEP_SIZE = 10        # 50% overlap

# ============================================
# LOAD TRAINED MODEL
# ============================================

model = joblib.load("activity_model.pkl")
print(" Model loaded successfully")

# ============================================
# LOAD LABEL MAP (OFFLINE, FROM TRAINING)
# ============================================

with open("label_map.json", "r") as f:
    label_map = json.load(f)

# JSON keys are strings → convert to int
label_map = {int(k): v for k, v in label_map.items()}
print(" Label map loaded successfully")

# ============================================
# SOCKET INITIALIZATION
# ============================================

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((UDP_IP, UDP_PORT))

print(" Listening for live IMU data...")

# ============================================
# SLIDING WINDOW BUFFER
# ============================================

buffer = deque(maxlen=WINDOW_SIZE)
sample_count = 0

# ============================================
# FEATURE EXTRACTION FUNCTION
# ============================================

def extract_features(window):
    features = []
    for col in range(window.shape[1]):  # 6 IMU channels
        x = window[:, col]
        features.extend([
            np.mean(x),
            np.min(x),
            np.max(x),
            np.std(x),
            np.var(x),
            np.sqrt(np.mean(x**2)),          # RMS
            np.ptp(x),                       # Peak-to-peak
            np.median(x),
            np.mean(np.abs(x - np.mean(x))), # MAD
            np.sum(x**2)                     # Energy
        ])
    return features

# ============================================
# REAL-TIME PREDICTION LOOP
# ============================================

print(" Live prediction started...\n")

while True:
    data, _ = sock.recvfrom(1024)

    # Expecting: Ax,Ay,Az,Gx,Gy,Gz
    row = [x.strip() for x in data.decode().split(",")]

    if len(row) != 6:
        continue

    try:
        imu_sample = np.array(row, dtype=float)
    except ValueError:
        continue

    buffer.append(imu_sample)
    sample_count += 1

    # Predict when window is full and step condition satisfied
    if len(buffer) == WINDOW_SIZE and sample_count % STEP_SIZE == 0:
        window = np.array(buffer)

        # SAME FEATURE ORDER AS TRAINING
        raw_part = window[-1].tolist()
        feat_part = extract_features(window)
        features = raw_part + feat_part

        # Sanity check
        if len(features) != 66:
            print(" Feature length mismatch:", len(features))
            continue

        features = np.array(features).reshape(1, -1)

        pred = model.predict(features)[0]
        print(" Predicted Activity:", label_map[pred])
