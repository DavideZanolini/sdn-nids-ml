#!/usr/bin/env python3
"""
Traffic generator for SDN-NIDS-ML hosts.

Each host runs a unique traffic profile against the servers in the topology.
Usage from Mininet CLI:
    mininet> h11 python3 main/hosts/traffic_gen.py h11 &
    mininet> source main/hosts/start_traffic.sh
"""

import argparse
import random
import subprocess
import sys
import time
import urllib.request
from datetime import datetime

try:
    import pymysql
except ImportError:
    pymysql = None

WEB_SRV = "192.168.0.1"
WEB_PORT = 8000
DB_SRV = "192.168.0.2"
DB_PORT = 3306

WEB_URLS = {
    "index": f"http://{WEB_SRV}:{WEB_PORT}/index.html",
    "small": f"http://{WEB_SRV}:{WEB_PORT}/test.txt",
    "medium": f"http://{WEB_SRV}:{WEB_PORT}/medium.bin",
    "large": f"http://{WEB_SRV}:{WEB_PORT}/large.bin",
}

DB_QUERIES = [
    "SELECT * FROM customers",
    "SELECT * FROM products WHERE price > 50",
    "SELECT * FROM orders ORDER BY order_date DESC LIMIT 10",
    "SELECT c.name, COUNT(o.id) as order_count FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.id",
    "SELECT p.name, SUM(o.quantity) as total_sold FROM products p JOIN orders o ON p.id = o.product_id GROUP BY p.id ORDER BY total_sold DESC",
    "SELECT * FROM products WHERE category = 'Electronics'",
    "SELECT c.name, SUM(o.total) as total_spent FROM customers c JOIN orders o ON c.id = o.customer_id GROUP BY c.id ORDER BY total_spent DESC LIMIT 5",
    "SELECT * FROM customers WHERE city = 'New York'",
]


def log(host, action, result):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {host}: {action} -> {result}", flush=True)


def http_get(host, url, timeout=10):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            _ = resp.read()
            log(host, f"GET {url}", f"{resp.status}")
    except Exception as e:
        log(host, f"GET {url}", f"ERR: {e}")


def ping(host, target, count=1):
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", "2", target],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            rtt = "ok"
            for line in result.stdout.splitlines():
                if "avg" in line:
                    rtt = line.split("=")[-1].strip()
                    break
            log(host, f"PING {target}", rtt)
        else:
            log(host, f"PING {target}", "timeout")
    except Exception as e:
        log(host, f"PING {target}", f"ERR: {e}")


def db_query(host, query):
    """Execute a single query against the DB server."""
    if pymysql is None:
        log(host, "DB", "ERR: pymysql not installed")
        return
    try:
        conn = pymysql.connect(
            host=DB_SRV, port=DB_PORT,
            user="root", password="root", database="shop",
            connect_timeout=5, read_timeout=5,
        )
        with conn.cursor() as cur:
            cur.execute(query)
            rows = cur.fetchall()
            log(host, f"DB query", f"{len(rows)} rows")
        conn.close()
    except Exception as e:
        log(host, "DB query", f"ERR: {e}")


# ---------------------------------------------------------------------------
# Traffic profiles — one per host
# ---------------------------------------------------------------------------

def profile_h11(host):
    """Light browser: index.html and test.txt, 2-5s interval."""
    urls = [WEB_URLS["index"], WEB_URLS["small"]]
    while True:
        http_get(host, random.choice(urls))
        time.sleep(random.uniform(2, 5))


def profile_h12(host):
    """Medium downloader: medium.bin, 10-20s interval."""
    while True:
        http_get(host, WEB_URLS["medium"], timeout=30)
        time.sleep(random.uniform(10, 20))


def profile_h13(host):
    """Heavy browser: all web endpoints, 1-3s interval."""
    urls = list(WEB_URLS.values())
    while True:
        http_get(host, random.choice(urls))
        time.sleep(random.uniform(1, 3))


def profile_h14(host):
    """Ping + occasional HTTP: ping every 3-5s, HTTP every ~15s."""
    counter = 0
    while True:
        ping(host, WEB_SRV)
        counter += 1
        if counter % 4 == 0:
            http_get(host, WEB_URLS["index"])
        time.sleep(random.uniform(3, 5))


def profile_h21(host):
    """DB reader: random queries, 3-6s interval."""
    while True:
        db_query(host, random.choice(DB_QUERIES))
        time.sleep(random.uniform(3, 6))


def profile_h22(host):
    """Large downloader: large.bin, 30-60s interval."""
    while True:
        http_get(host, WEB_URLS["large"], timeout=60)
        time.sleep(random.uniform(30, 60))


def profile_h23(host):
    """Dual-server: alternate between web_srv and db_srv, 2-4s."""
    idx = 0
    while True:
        if idx % 2 == 0:
            http_get(host, WEB_URLS["index"])
        else:
            db_query(host, random.choice(DB_QUERIES))
        idx += 1
        time.sleep(random.uniform(2, 4))


def profile_h24(host):
    """Bursty browser: burst of 5 rapid requests then long pause."""
    urls = list(WEB_URLS.values())
    while True:
        for _ in range(5):
            http_get(host, random.choice(urls))
            time.sleep(random.uniform(0.3, 0.8))
        time.sleep(random.uniform(10, 20))


def profile_h31(host):
    """Slow steady: test.txt, 8-15s interval."""
    while True:
        http_get(host, WEB_URLS["small"])
        time.sleep(random.uniform(8, 15))


def profile_h32(host):
    """Mixed sizes: random web files, 3-8s interval."""
    urls = list(WEB_URLS.values())
    while True:
        http_get(host, random.choice(urls), timeout=30)
        time.sleep(random.uniform(3, 8))


def profile_h33(host):
    """Multi-ping + mixed: ping both servers, occasional HTTP or DB query."""
    counter = 0
    while True:
        ping(host, WEB_SRV)
        ping(host, DB_SRV)
        counter += 1
        if counter % 3 == 0:
            if random.random() < 0.5:
                http_get(host, WEB_URLS["index"])
            else:
                db_query(host, random.choice(DB_QUERIES))
        time.sleep(random.uniform(3, 5))


def profile_h34(host):
    """Bulk transfer: large.bin, 20-40s interval."""
    while True:
        http_get(host, WEB_URLS["large"], timeout=60)
        time.sleep(random.uniform(20, 40))


PROFILES = {
    "h11": profile_h11,
    "h12": profile_h12,
    "h13": profile_h13,
    "h14": profile_h14,
    "h21": profile_h21,
    "h22": profile_h22,
    "h23": profile_h23,
    "h24": profile_h24,
    "h31": profile_h31,
    "h32": profile_h32,
    "h33": profile_h33,
    "h34": profile_h34,
}


def main():
    parser = argparse.ArgumentParser(description="Host traffic generator")
    parser.add_argument("host", choices=PROFILES.keys(), help="Host name")
    parser.add_argument(
        "--start-delay", type=int, default=0, metavar="MAX",
        help="Sleep a random 0-MAX seconds before starting (for staggering)",
    )
    args = parser.parse_args()

    if args.start_delay > 0:
        delay = random.uniform(0, args.start_delay)
        log(args.host, "WAIT", f"starting in {delay:.1f}s")
        time.sleep(delay)

    log(args.host, "START", f"profile={args.host}")
    try:
        PROFILES[args.host](args.host)
    except KeyboardInterrupt:
        log(args.host, "STOP", "interrupted")


if __name__ == "__main__":
    main()
