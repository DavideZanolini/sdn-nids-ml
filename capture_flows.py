#!/usr/bin/env python3
"""Capture network flows from core-eth0 and core-eth1 using scapy and save features to CSV.

Sniffs packets in real time, aggregates them into flows (by 5-tuple),
and extracts per-flow features for training the autoencoder NIDS.

Usage:
    sudo python3 captures/capture_flows.py [--timeout 300] [--attack]

"""

import argparse
import csv
import os
import re
import signal
import sys
import time
from collections import defaultdict
from datetime import datetime

from scapy.all import IP, TCP, UDP, ICMP, sniff

CAPTURE_DIR = os.path.dirname(os.path.abspath(__file__)) + "/captures"
FLOW_IDLE_TIMEOUT = 30   # seconds without packets → flow is considered idle
MAX_FLOW_DURATION = 15   # seconds of activity → force-export and reset the flow
H11_ATTACKER_IP = "10.0.1.11"  # h11 is the attacker in attack mode


class FlowKey:
    """4-tuple key: (src_ip, dst_ip, dst_port, protocol).

    """
    __slots__ = ("src_ip", "dst_ip", "dst_port", "protocol")

    def __init__(self, src_ip, dst_ip, dst_port, protocol):
        self.src_ip = src_ip
        self.dst_ip = dst_ip
        self.dst_port = dst_port
        self.protocol = protocol

    def __hash__(self):
        return hash((self.src_ip, self.dst_ip, self.dst_port, self.protocol))

    def __eq__(self, other):
        return (self.src_ip == other.src_ip and self.dst_ip == other.dst_ip and
                self.dst_port == other.dst_port and self.protocol == other.protocol)


class FlowRecord:
    __slots__ = ("timestamps", "pkt_sizes", "fwd_bytes", "bwd_bytes",
                 "fwd_pkts", "bwd_pkts", "tcp_flags", "first_src_port",
                 "ip_flags_df", "ip_flags_mf", "ip_flags_rb", "ip_frag_off",
                 "tcp_lengths", "tcp_window_sizes", "udp_lengths", "icmp_types")

    def __init__(self, first_src_port=0):
        self.timestamps = []
        self.pkt_sizes = []
        self.fwd_bytes = 0
        self.bwd_bytes = 0
        self.fwd_pkts = 0
        self.bwd_pkts = 0
        self.tcp_flags = {"SYN": 0, "FIN": 0, "RST": 0, "PSH": 0, "ACK": 0,
                          "CWR": 0, "ECE": 0, "URG": 0, "RES": 0}
        # Metadata only — the src_port of the first packet in this flow
        self.first_src_port = first_src_port
        self.ip_flags_df = 0
        self.ip_flags_mf = 0
        self.ip_flags_rb = 0
        self.ip_frag_off = 0
        self.tcp_lengths = []
        self.tcp_window_sizes = []
        self.udp_lengths = []
        self.icmp_types = []


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


def extract_features(key, rec, label="normal"):
    """Compute feature vector from a completed flow."""
    iats = [rec.timestamps[i] - rec.timestamps[i - 1]
            for i in range(1, len(rec.timestamps))]

    iat_mean = sum(iats) / len(iats) if iats else 0.0

    # Packet sizes
    pkt_size_mean = sum(rec.pkt_sizes) / len(rec.pkt_sizes) if rec.pkt_sizes else 0.0

    return {
        "src_ip": key.src_ip,
        "dst_ip": key.dst_ip,
        "src_port": rec.first_src_port,
        "dst_port": key.dst_port,
        "protocol": key.protocol,
        "iat_mean": round(iat_mean, 6),
        "pkt_size_mean": round(pkt_size_mean, 2),
        "ip_flags_df": rec.ip_flags_df,
        "ip_flags_mf": rec.ip_flags_mf,
        "ip_flags_rb": rec.ip_flags_rb,
        "ip_frag_off": rec.ip_frag_off,
        "tcp_len_mean": round(sum(rec.tcp_lengths) / len(rec.tcp_lengths), 2) if rec.tcp_lengths else 0.0,
        "ack_count": rec.tcp_flags["ACK"],
        "cwr_count": rec.tcp_flags["CWR"],
        "ece_count": rec.tcp_flags["ECE"],
        "fin_count": rec.tcp_flags["FIN"],
        "psh_count": rec.tcp_flags["PSH"],
        "res_count": rec.tcp_flags["RES"],
        "rst_count": rec.tcp_flags["RST"],
        "syn_count": rec.tcp_flags["SYN"],
        "urg_count": rec.tcp_flags["URG"],
        "tcp_win_mean": round(sum(rec.tcp_window_sizes) / len(rec.tcp_window_sizes), 2) if rec.tcp_window_sizes else 0.0,
        "udp_len_mean": round(sum(rec.udp_lengths) / len(rec.udp_lengths), 2) if rec.udp_lengths else 0.0,
        "icmp_type_mean": round(sum(rec.icmp_types) / len(rec.icmp_types), 2) if rec.icmp_types else 0.0,
        "pkt_count": rec.fwd_pkts + rec.bwd_pkts,
        "label": label,
    }


FEATURE_COLUMNS = [
    "src_ip", "dst_ip", "src_port", "dst_port", "protocol",
    "iat_mean", "pkt_size_mean", "ip_flags_df", "ip_flags_mf",
    "ip_flags_rb", "ip_frag_off", "tcp_len_mean", "ack_count",
    "cwr_count", "ece_count", "fin_count", "psh_count", "res_count",
    "rst_count", "syn_count", "urg_count", "tcp_win_mean",
    "udp_len_mean", "icmp_type_mean", "pkt_count", "label",
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

    # Canonical flow key: 4-tuple (src_ip, dst_ip, dst_port, protocol).
    # src_port is excluded so all connections from the same host to the same
    # server port aggregate into one flow.
    key_fwd = FlowKey(src_ip, dst_ip, dst_port, protocol)
    key_bwd = FlowKey(dst_ip, src_ip, src_port, protocol)

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
        flows[key] = FlowRecord(first_src_port=src_port)

    rec = flows[key]
    rec.timestamps.append(ts)
    rec.pkt_sizes.append(pkt_len)

    if is_forward:
        rec.fwd_pkts += 1
        rec.fwd_bytes += pkt_len
    else:
        rec.bwd_pkts += 1
        rec.bwd_bytes += pkt_len

    # IP-level features
    ip_f = int(ip.flags)
    rec.ip_flags_df += (ip_f >> 1) & 1
    rec.ip_flags_mf += ip_f & 1
    rec.ip_flags_rb += (ip_f >> 2) & 1
    rec.ip_frag_off += int(ip.frag)

    if flags is not None:
        if flags & 0x02: rec.tcp_flags["SYN"] += 1
        if flags & 0x01: rec.tcp_flags["FIN"] += 1
        if flags & 0x04: rec.tcp_flags["RST"] += 1
        if flags & 0x08: rec.tcp_flags["PSH"] += 1
        if flags & 0x10: rec.tcp_flags["ACK"] += 1
        if flags & 0x80: rec.tcp_flags["CWR"] += 1
        if flags & 0x40: rec.tcp_flags["ECE"] += 1
        if flags & 0x20: rec.tcp_flags["URG"] += 1
        if int(flags) & 0x100: rec.tcp_flags["RES"] += 1
        tcp_l = pkt[TCP]
        ip_hlen = (ip.ihl or 5) * 4
        tcp_hlen = (tcp_l.dataofs or 5) * 4
        rec.tcp_lengths.append(max(0, len(pkt[IP]) - ip_hlen - tcp_hlen))
        rec.tcp_window_sizes.append(tcp_l.window)
    elif protocol == 17:
        rec.udp_lengths.append(pkt[UDP].len)
    elif protocol == 1:
        rec.icmp_types.append(pkt[ICMP].type)

    pkt_count += 1
    if pkt_count % 500 == 0:
        print(f"  {pkt_count} packets captured, {len(flows)} active flows", flush=True)


def expire_idle_flows(now):
    """Remove flows idle for FLOW_IDLE_TIMEOUT seconds (connection ended)."""
    expired = []
    for key, rec in flows.items():
        if rec.timestamps and now - rec.timestamps[-1] > FLOW_IDLE_TIMEOUT:
            expired.append((key, rec))
    for key, _ in expired:
        del flows[key]
    return expired


def expire_long_flows(now):
    """Force-export flows that have exceeded MAX_FLOW_DURATION, then reset them.
    """
    expired = []
    for key, rec in flows.items():
        if rec.timestamps and now - rec.timestamps[0] > MAX_FLOW_DURATION:
            expired.append((key, rec))
    for key, rec in expired:
        # Export current record, then reset to a fresh one preserving metadata
        flows[key] = FlowRecord(first_src_port=rec.first_src_port)
    return expired


def _append_flows_to_csv(flow_list, filepath, label="normal", attack_mode=False):
    file_exists = os.path.exists(filepath) and os.path.getsize(filepath) > 0
    with open(filepath, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FEATURE_COLUMNS)
        if not file_exists:
            writer.writeheader()
        for key, rec in flow_list:
            # In attack mode, label h11 flows as "malicious"
            if attack_mode and key.src_ip == H11_ATTACKER_IP:
                flow_label = "malicious"
            else:
                flow_label = label
            features = extract_features(key, rec, label=flow_label)
            writer.writerow(features)


def save_flows(flow_list, filepath, label="normal", attack_mode=False):
    """
    Append flow features to capture CSV file.

    Args:
        flow_list: List of (key, record) tuples to save
        filepath: Path to capture CSV file
        label: Default label for non-attacker flows (default: "normal")
        attack_mode: If True, label h11 flows as "malicious", others use default label
    """
    _append_flows_to_csv(flow_list, filepath, label=label, attack_mode=attack_mode)

    # Append only the newly exported flows for real-time inference.
    inference_copy_path = filepath.replace(".csv", "_inference.csv")
    _append_flows_to_csv(flow_list, inference_copy_path, label=label, attack_mode=attack_mode)

def main():
    global running

    parser = argparse.ArgumentParser(description="Capture flows for NIDS training")
    parser.add_argument("--timeout", type=int, default=0,
                        help="Capture duration in seconds")
    parser.add_argument("--label", default="normal", choices=["normal", "attack"],
                        help="Label assigned to non-attacker flows (default: normal)")
    parser.add_argument("--attack", action="store_true",
                        help="Enable attack mode: h11 flows labeled as 'malicious'")
    args = parser.parse_args()

    # Hardcoded interfaces
    iface = "core-eth1"
    
    # Find next incremental capture number
    n = 1
    while os.path.exists(os.path.join(CAPTURE_DIR, f"capture_{n}.csv")):
        n += 1
    out_file = os.path.join(CAPTURE_DIR, f"capture_{n}.csv")

    print(f"=== Flow Capture ===")
    print(f"Interface(s): {iface}")
    print(f"Output:    {out_file}")
    print(f"Label:     {args.label}")
    print(f"Timeout:   {args.timeout}s" if args.timeout else "Timeout:   none")
    print(f"Flow idle timeout: {FLOW_IDLE_TIMEOUT}s, max duration: {MAX_FLOW_DURATION}s")
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
        sniff(iface=iface, prn=process_packet, store=False,
              timeout=5, stop_filter=lambda _: not running)

        # Expire idle and long-duration flows periodically
        now = time.time()
        if now - last_expire >= 10:
            long_expired = expire_long_flows(now)
            idle_expired = expire_idle_flows(now)
            to_save = long_expired + idle_expired
            if to_save:
                save_flows(to_save, out_file, label=args.label, attack_mode=args.attack)
                total_saved += len(to_save)
                print(f"  Saved {len(to_save)} flows ({total_saved} total, "
                      f"{len(long_expired)} windowed, {len(idle_expired)} idle)", flush=True)
            last_expire = now

        # Check capture timeout
        if args.timeout and (now - start_time) >= args.timeout:
            print(f"\nTimeout reached ({args.timeout}s)")
            break

    # Save all remaining active flows
    remaining = list(flows.items())
    if remaining:
        save_flows(remaining, out_file, label=args.label, attack_mode=args.attack)
        total_saved += len(remaining)

    print(f"\n=== Capture complete ===")
    print(f"Total packets: {pkt_count}")
    print(f"Total flows saved: {total_saved}")
    print(f"Capture file: {out_file}")


if __name__ == "__main__":
    main()
