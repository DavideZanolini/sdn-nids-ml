#!/bin/bash
# run_experiment.sh — Orchestrate the full experiment
#
# Run this from a SEPARATE terminal AFTER the topology is up
# (create_topology.py running in another terminal with the Ryu controller).
#
# Usage: sudo bash run_experiment.sh [--attack]
#
# Press Ctrl+C to stop everything.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRAFFIC_SCRIPT="$SCRIPT_DIR/hosts/traffic_gen.py"
CAPTURE_SCRIPT="$SCRIPT_DIR/capture_flows.py"
HOSTS="h11 h12 h13 h14 h15 h16 h21 h22 h23 h24 h25 h26 h31 h32 h33 h34 h35 h36"
START_DELAY=3
ATTACK_MODE=false

# Parse arguments
if [[ "$1" == "--attack" ]]; then
    ATTACK_MODE=true
fi

if [ "$EUID" -ne 0 ]; then
    echo "ERROR: This script must be run as root (sudo)"
    exit 1
fi

# --- Cleanup handler ---
TRAFFIC_PIDS=()
CAPTURE_PID=""

cleanup() {
    echo ""
    echo "=== Stopping experiment ==="
    for p in "${TRAFFIC_PIDS[@]}"; do
        kill "$p" 2>/dev/null || true
    done
    if [ -n "$CAPTURE_PID" ]; then
        kill "$CAPTURE_PID" 2>/dev/null || true
    fi
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

# --- Step 3: Start flow capture ---
echo ""
echo "=== Step 2: Starting flow capture ==="
CAPTURE_ARGS="--label normal"
CAPTURE_DURATION=1800  # Default to no 30 minutes timeout
if [ "$ATTACK_MODE" = true ]; then
    CAPTURE_ARGS="$CAPTURE_ARGS --attack"
    echo "  Attack mode enabled: h11 flows will be labeled as 'malicious'"
fi

# Check if a duration argument is provided
if [[ "$2" =~ ^[0-9]+$ ]]; then
    CAPTURE_DURATION=$2
    CAPTURE_ARGS="$CAPTURE_ARGS --timeout $CAPTURE_DURATION"
    echo "  Capture duration set to $CAPTURE_DURATION seconds"
fi

sudo python3 "$CAPTURE_SCRIPT" $CAPTURE_ARGS &
CAPTURE_PID=$!
echo "  Flow capture started (PID: $CAPTURE_PID)"
sleep 2
# --- Step 4: Traffic generators ---
echo ""
echo "=== Step 3: Starting traffic generators ==="
for host in $HOSTS; do
    pid=$(pgrep -f "mininet:${host}$" 2>/dev/null | head -1) || true
    if [ -z "$pid" ]; then
        echo "  WARNING: $host not found, skipping"
        continue
    fi
    
    echo "  $host started (random delay 0-${START_DELAY}s)"

    # Pass --attack only to h11, and only if in attack mode
    if [ "$ATTACK_MODE" = true ] && [ "$host" = "h11" ]; then
        mnexec -a "$pid" python3 "$TRAFFIC_SCRIPT" "$host" --start-delay "$START_DELAY" --attack > /dev/null 2>&1 &
    else
        mnexec -a "$pid" python3 "$TRAFFIC_SCRIPT" "$host" --start-delay "$START_DELAY" > /dev/null 2>&1 &
    fi
    TRAFFIC_PIDS+=($!)
done

echo ""
echo "=== Experiment running === "
echo ""
wait
