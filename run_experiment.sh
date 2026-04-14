#!/bin/bash
# run_experiment.sh — Orchestrate the full experiment
#
# Run this from a SEPARATE terminal AFTER the topology is up
# (create_topology.py running in another terminal with the Ryu controller).
#
# Usage: sudo bash run_experiment.sh [--sync]
#
# Options:
#   --sync   Start all traffic generators at t=0 (no random delay)
#
# Steps:
#   1. Configure routing via Ryu REST API
#   2. Launch traffic generators on all hosts (each with random 0-30s delay)
#
# Press Ctrl+C to stop everything.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRAFFIC_SCRIPT="$SCRIPT_DIR/hosts/traffic_gen.py"
HOSTS="h11 h12 h13 h14 h21 h22 h23 h24 h31 h32 h33 h34"
START_DELAY=30

if [[ "$1" == "--sync" ]]; then
    START_DELAY=0
fi

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)"
    exit 1
fi

# --- Cleanup handler ---
TRAFFIC_PIDS=()

cleanup() {
    echo ""
    echo "=== Stopping experiment ==="
    for p in "${TRAFFIC_PIDS[@]}"; do
        kill "$p" 2>/dev/null || true
    done
    exit 0
}
trap cleanup INT TERM

# --- Step 1: Dependencies ---
pip install -q pymysql 2>/dev/null

# --- Step 2: Routing ---
echo "=== Step 1: Setting up routing ==="
bash "$SCRIPT_DIR/setup_routing.sh"
echo ""
echo "Routing configured."

# --- Step 2: Traffic generators ---
echo ""
echo "=== Step 2: Starting traffic generators ==="
for host in $HOSTS; do
    pid=$(pgrep -f "mininet:${host}$" 2>/dev/null | head -1) || true
    if [ -z "$pid" ]; then
        echo "  WARNING: $host not found, skipping"
        continue
    fi
    mnexec -a "$pid" python3 "$TRAFFIC_SCRIPT" "$host" --start-delay "$START_DELAY" \
        > /dev/null 2>&1 &
    TRAFFIC_PIDS+=($!)
    if [ "$START_DELAY" -eq 0 ]; then
        echo "  $host started (no delay)"
    else
        echo "  $host started (random delay 0-${START_DELAY}s)"
    fi
done

echo ""
echo "=== Experiment running ==="
echo "Press Ctrl+C to stop"

wait
