#!/usr/bin/env python3
"""
Capture network flows from core-eth1 using scapy and save features to CSV.

Sniffs packets in real time, aggregates them into flows (by 5-tuple),
and extracts per-flow features for training the autoencoder NIDS.

Usage:
    sudo python3 captures/capture_flows.py [--iface core-eth1] [--timeout 300]

Press Ctrl+C to stop early. Flows are saved on exit.
"""

import argparse
import csv
import os
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime

from scapy.all import IP, TCP, UDP, ICMP, sniff

CAPTURE_DIR = os.path.dirname(os.path.abspath(__file__))
FLOW_IDLE_TIMEOUT = 30  # seconds without packets → flow is expired


class FlowKey:
    __slots__ = ("src_ip", "dst_ip", "src_port", "dst_port", "protocol")

    def __init__(self, src_ip, dst_ip, src_port, dst_port, protocol):
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.src_port = src_port
        self.dst_port = dst_port
        self.protocol = protocol

    def __hash__(self):
        return hash((self.src_ip, self.dst_ip, self.src_port, self.dst_port, self.protocol))

    def __eq__(self, other):
        return (self.src_ip == other.src_ip and self.dst_ip == other.dst_ip and
                self.src_port == other.src_port and self.dst_port == other.dst_port and
                self.protocol == other.protocol)


class FlowRecord:
    __slots__ = ("timestamps", "pkt_sizes", "fwd_bytes", "bwd_bytes",
                 "fwd_pkts", "bwd_pkts", "tcp_flags")

    def __init__(self):
        self.timestamps = []
        self.pkt_sizes = []
        self.fwd_bytes = 0
        self.bwd_bytes = 0
        self.fwd_pkts = 0
        self.bwd_pkts = 0
        self.tcp_flags = {"SYN": 0, "FIN": 0, "RST": 0, "PSH": 0, "ACK": 0}


# Active flows: FlowKey → FlowRecord
flows = {}
# Track which direction is "forward" (first packet seen)
flow_initiators = {}
# Global packet counter
pkt_count = 0
running = True


def _safe_std(values):
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
    return variance ** 0.5


def extract_features(key, rec):
    """Compute feature vector from a completed flow."""
    if len(rec.timestamps) < 2:
        duration = 0.0
    else:
        duration = rec.timestamps[-1] - rec.timestamps[0]

    total_pkts = rec.fwd_pkts + rec.bwd_pkts
    total_bytes = rec.fwd_bytes + rec.bwd_bytes

    # Inter-arrival times
    iats = [rec.timestamps[i] - rec.timestamps[i - 1]
            for i in range(1, len(rec.timestamps))]

    iat_mean = sum(iats) / len(iats) if iats else 0.0
    iat_std = _safe_std(iats) if iats else 0.0
    iat_min = min(iats) if iats else 0.0
    iat_max = max(iats) if iats else 0.0

    # Packet sizes
    pkt_size_mean = sum(rec.pkt_sizes) / len(rec.pkt_sizes) if rec.pkt_sizes else 0.0
    pkt_size_std = _safe_std(rec.pkt_sizes) if rec.pkt_sizes else 0.0
    pkt_size_min = min(rec.pkt_sizes) if rec.pkt_sizes else 0
    pkt_size_max = max(rec.pkt_sizes) if rec.pkt_sizes else 0

    # Rates
    if duration > 0:
        pkt_rate = total_pkts / duration
        byte_rate = total_bytes / duration
    else:
        pkt_rate = 0.0
        byte_rate = 0.0

    return {
        "src_ip": key.src_ip,
        "dst_ip": key.dst_ip,
        "src_port": key.src_port,
        "dst_port": key.dst_port,
        "protocol": key.protocol,
        "duration": round(duration, 6),
        "fwd_pkts": rec.fwd_pkts,
        "bwd_pkts": rec.bwd_pkts,
        "fwd_bytes": rec.fwd_bytes,
        "bwd_bytes": rec.bwd_bytes,
        "pkt_size_mean": round(pkt_size_mean, 2),
        "pkt_size_std": round(pkt_size_std, 2),
        "pkt_size_min": pkt_size_min,
        "pkt_size_max": pkt_size_max,
        "iat_mean": round(iat_mean, 6),
        "iat_std": round(iat_std, 6),
        "iat_min": round(iat_min, 6),
        "iat_max": round(iat_max, 6),
        "pkt_rate": round(pkt_rate, 2),
        "byte_rate": round(byte_rate, 2),
        "syn_count": rec.tcp_flags["SYN"],
        "fin_count": rec.tcp_flags["FIN"],
        "rst_count": rec.tcp_flags["RST"],
        "psh_count": rec.tcp_flags["PSH"],
        "ack_count": rec.tcp_flags["ACK"],
    }


FEATURE_COLUMNS = [
    "src_ip", "dst_ip", "src_port", "dst_port", "protocol",
    "duration", "fwd_pkts", "bwd_pkts", "fwd_bytes", "bwd_bytes",
    "pkt_size_mean", "pkt_size_std", "pkt_size_min", "pkt_size_max",
    "iat_mean", "iat_std", "iat_min", "iat_max",
    "pkt_rate", "byte_rate",
    "syn_count", "fin_count", "rst_count", "psh_count", "ack_count",
]


def process_packet(pkt):
    global pkt_count
    if not pkt.haslayer(IP):
        return

    ip = pkt[IP]
    src_ip = ip.src
    dst_ip = ip.dst
    pkt_len = len(pkt)
    ts = float(pkt.time)

    # Skip transit-network traffic (switch-to-switch)
    if src_ip.startswith("10.10.") or dst_ip.startswith("10.10."):
        return

    # Determine protocol and ports
    if pkt.haslayer(TCP):
        protocol = 6
        src_port = pkt[TCP].sport
        dst_port = pkt[TCP].dport
        flags = pkt[TCP].flags
    elif pkt.haslayer(UDP):
        protocol = 17
        src_port = pkt[UDP].sport
        dst_port = pkt[UDP].dport
        flags = None
    elif pkt.haslayer(ICMP):
        protocol = 1
        src_port = 0
        dst_port = 0
        flags = None
    else:
        return

    # Canonical flow key: initiator is always "forward"
    key_fwd = FlowKey(src_ip, dst_ip, src_port, dst_port, protocol)
    key_bwd = FlowKey(dst_ip, src_ip, dst_port, src_port, protocol)

    if key_fwd in flows:
        key = key_fwd
        is_forward = True
    elif key_bwd in flows:
        key = key_bwd
        is_forward = False
    else:
        # New flow — first packet defines forward direction
        key = key_fwd
        is_forward = True
        flows[key] = FlowRecord()

    rec = flows[key]
    rec.timestamps.append(ts)
    rec.pkt_sizes.append(pkt_len)

    if is_forward:
        rec.fwd_pkts += 1
        rec.fwd_bytes += pkt_len
    else:
        rec.bwd_pkts += 1
        rec.bwd_bytes += pkt_len

    if flags is not None:
        if flags & 0x02:
            rec.tcp_flags["SYN"] += 1
        if flags & 0x01:
            rec.tcp_flags["FIN"] += 1
        if flags & 0x04:
            rec.tcp_flags["RST"] += 1
        if flags & 0x08:
            rec.tcp_flags["PSH"] += 1
        if flags & 0x10:
            rec.tcp_flags["ACK"] += 1

    pkt_count += 1
    if pkt_count % 500 == 0:
        print(f"  {pkt_count} packets captured, {len(flows)} active flows", flush=True)


def expire_idle_flows(now):
    """Remove flows that have been idle for FLOW_IDLE_TIMEOUT seconds."""
    expired = []
    for key, rec in flows.items():
        if now - rec.timestamps[-1] > FLOW_IDLE_TIMEOUT:
            expired.append((key, rec))
    for key, _ in expired:
        del flows[key]
    return expired


def save_flows(flow_list, filepath):
    """Append flow features to CSV file."""
    file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
    with open(filepath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for key, rec in flow_list:
            features = extract_features(key, rec)
            writer.writerow(features)


def main():
    global running

    parser = argparse.ArgumentParser(description="Capture flows for NIDS training")
    parser.add_argument("--iface", default="core-eth0,core-eth1",
                        help="Interface(s) to sniff on (comma-separated)")
    parser.add_argument("--timeout", type=int, default=0,
                        help="Capture duration in seconds (0 = until Ctrl+C)")
    parser.add_argument("--output", default=None,
                        help="Output CSV filename (default: flows_YYYYMMDD_HHMMSS.csv)")
    args = parser.parse_args()

    if args.output:
        out_file = os.path.join(CAPTURE_DIR, args.output)
    else:
        # Find next incremental capture number
        n = 1
        while os.path.exists(os.path.join(CAPTURE_DIR, f"capture_{n}.csv")):
            n += 1
        out_file = os.path.join(CAPTURE_DIR, f"capture_{n}.csv")

    # Parse interface argument into a string or list for scapy.sniff
    iface_arg = args.iface
    if "," in iface_arg:
        iface = [i.strip() for i in iface_arg.split(",") if i.strip()]
    else:
        iface = iface_arg

    print(f"=== Flow Capture ===")
    print(f"Interface(s): {iface}")
    print(f"Output:    {out_file}")
    print(f"Timeout:   {args.timeout}s" if args.timeout else "Timeout:   none (Ctrl+C to stop)")
    print(f"Flow idle timeout: {FLOW_IDLE_TIMEOUT}s")
    print()

    def stop(sig, frame):
        global running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    start_time = time.time()
    last_expire = start_time
    total_saved = 0

    print("Sniffing...", flush=True)

    while running:
        # Sniff in short bursts so we can check timeouts
        sniff(iface=args.iface, prn=process_packet, store=False,
              timeout=5, stop_filter=lambda _: not running)

        # Expire idle flows periodically
        now = time.time()
        if now - last_expire >= 10:
            expired = expire_idle_flows(now)
            if expired:
                save_flows(expired, out_file)
                total_saved += len(expired)
                print(f"  Saved {len(expired)} expired flows ({total_saved} total)", flush=True)
            last_expire = now

        # Check capture timeout
        if args.timeout and (now - start_time) >= args.timeout:
            print(f"\nTimeout reached ({args.timeout}s)")
            break

    # Save all remaining active flows
    remaining = list(flows.items())
    if remaining:
        save_flows(remaining, out_file)
        total_saved += len(remaining)

    print(f"\n=== Capture complete ===")
    print(f"Total packets: {pkt_count}")
    print(f"Total flows saved: {total_saved}")
    print(f"Output: {out_file}")


if __name__ == "__main__":
    main()
