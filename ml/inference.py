#!/usr/bin/env python3
"""
Real-time anomaly detection inference script.
Fetches capture_1_inference.csv every 5 seconds, analyzes new flows,
and detects malicious flows using the trained autoencoder model.
"""

import os
import time
import numpy as np
import pandas as pd
import tensorflow as tf
import joblib

# Paths
CAPTURE_FILE = "../captures/capture_2_inference.csv"
MODEL_PATH = "autoencoder_model.h5"
THRESHOLD_PATH = "anomaly_threshold.txt"
SCALER_PATH = "scaler.pkl"
POLL_INTERVAL = 5  # seconds

# Load the trained model
if not os.path.exists(MODEL_PATH):
    raise FileNotFoundError(f"Model file not found: {MODEL_PATH}")
try:
    model = tf.keras.models.load_model(MODEL_PATH, safe_mode=False)
except TypeError:
    # Fallback for newer TensorFlow versions that don't have safe_mode parameter
    model = tf.keras.saving.load_model(MODEL_PATH)
print("Model loaded successfully.")

# Load the anomaly threshold
if not os.path.exists(THRESHOLD_PATH):
    raise FileNotFoundError(f"Threshold file not found: {THRESHOLD_PATH}")
with open(THRESHOLD_PATH, "r") as f:
    anomaly_threshold = float(f.read().strip())
print(f"Anomaly threshold loaded: {anomaly_threshold}")

# Load the scaler
if not os.path.exists(SCALER_PATH):
    raise FileNotFoundError(f"Scaler file not found: {SCALER_PATH}")
scaler = joblib.load(SCALER_PATH)
print("Scaler loaded successfully.")

# Statistics
stats = {
    "total_flows_analyzed": 0,
    "malicious_flows": 0,
    "normal_flows": 0,
    "malicious_ips": {},  # ip -> count
    "malicious_ports": {},  # port -> count
    "started_at": time.time(),
}

print(f"\nMonitoring {CAPTURE_FILE} for anomalies...")
print("=" * 10)

try:
    while True:
        if not os.path.exists(CAPTURE_FILE):
            print(f"Waiting for {CAPTURE_FILE}...")
            time.sleep(POLL_INTERVAL)
            continue

        # Load the flow data
        df = pd.read_csv(CAPTURE_FILE)
        if df.empty:
            time.sleep(POLL_INTERVAL)
            continue

        print(f"\nFound {len(df)} flow(s) to analyze...")

        # Prepare feature columns (drop non-feature columns)
        DROP_COLS = ["n", "src_ip", "dst_ip", "src_port", "dst_port", "protocol", "label"]
        X = df.drop(columns=DROP_COLS, errors="ignore").values.astype("float32")
        X = scaler.transform(X)

        # Perform inference
        reconstructed = model.predict(X, verbose=0)
        reconstruction_error = np.mean(np.square(X - reconstructed), axis=1)

        # Detect anomalies
        anomalies = reconstruction_error > anomaly_threshold

        # Process results
        for idx, (flow_idx, flow_row) in enumerate(df.iterrows()):
            src_ip = flow_row["src_ip"]
            dst_ip = flow_row["dst_ip"]
            src_port = int(flow_row["src_port"])
            dst_port = int(flow_row["dst_port"])
            error = reconstruction_error[idx]

            # Mark as analyzed
            stats["total_flows_analyzed"] += 1

            if anomalies[idx]:
                stats["malicious_flows"] += 1
                stats["malicious_ips"][src_ip] = stats["malicious_ips"].get(src_ip, 0) + 1
                stats["malicious_ports"][src_port] = stats["malicious_ports"].get(src_port, 0) + 1
                
                print(f"\n[MALICIOUS]")
                print(f"  Source: {src_ip}:{src_port}")
                print(f"  Destination: {dst_ip}:{dst_port}")
                print(f"  Reconstruction Error: {error:.6f}")
                print(f"  Threshold: {anomaly_threshold:.6f}")
            else:
                stats["normal_flows"] += 1

        # Remove all data from the CSV file
        df.iloc[0:0].to_csv(CAPTURE_FILE, index=False)

        time.sleep(POLL_INTERVAL)

except KeyboardInterrupt:
    print("\n" + "=" * 10)
    print("\nStopping inference...")

# Print final statistics
elapsed = time.time() - stats["started_at"]
total = stats["total_flows_analyzed"]
malicious_rate = (stats["malicious_flows"] / total * 100) if total else 0.0
normal_rate = (stats["normal_flows"] / total * 100) if total else 0.0
flows_per_second = (total / elapsed) if elapsed else 0.0

print("\n" + "=" * 72)
print("INFERENCE STATISTICS SUMMARY")
print("=" * 72)
print(f"{'Runtime':<28}: {elapsed:,.1f}s")
print(f"{'Total flows analyzed':<28}: {total:,}")
print(f"{'Normal flows':<28}: {stats['normal_flows']:,} ({normal_rate:.2f}%)")
print(f"{'Malicious flows detected':<28}: {stats['malicious_flows']:,} ({malicious_rate:.2f}%)")
print(f"{'Average throughput':<28}: {flows_per_second:.2f} flows/s")

if stats["malicious_ips"]:
    print("\nTop malicious source IPs")
    print("-" * 72)
    print(f"{'Source IP':<40} {'Flows':>10} {'Share':>10}")
    print("-" * 72)
    for ip, count in sorted(stats["malicious_ips"].items(), key=lambda x: x[1], reverse=True)[:10]:
        share = count / stats["malicious_flows"] * 100
        print(f"{ip:<40} {count:>10,} {share:>9.2f}%")

print("=" * 72)
