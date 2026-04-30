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
import socket
import subprocess
import sys
import threading
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

ATTACK_DELAY = 20
ATTACK_DURATION = 10

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
    "SELECT COUNT(*) FROM orders WHERE order_date > DATE_SUB(NOW(), INTERVAL 7 DAY)",
    "SELECT * FROM products ORDER BY price ASC LIMIT 20",
    "SELECT * FROM orders WHERE total > 100 ORDER BY total DESC LIMIT 5",
    "SELECT DISTINCT city FROM customers ORDER BY city",
    "SELECT p.name, p.price FROM products p JOIN orders o ON p.id = o.product_id WHERE o.quantity > 2",
    "SELECT * FROM customers WHERE email LIKE '%@gmail.com'",
    "SELECT AVG(total) as avg_order FROM orders",
    "SELECT * FROM products WHERE stock < 10",
    "SELECT c.name, o.total FROM customers c JOIN orders o ON c.id = o.customer_id ORDER BY o.order_date DESC LIMIT 10",
]


def log(host, action, result):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[{ts}] {host}: {action} -> {result}", flush=True)


def rand_url(url):
    """Append a random cache-busting query parameter to a URL."""
    if random.random() < 0.4:
        return f"{url}?t={random.randint(1000, 9999)}"
    return url


def maybe_burst(host, urls, db=True):
    """Occasionally fire 3-8 rapid extra requests to simulate a micro-burst."""
    if random.random() < 0.40:
        count = random.randint(3, 8)
        for _ in range(count):
            if db and random.random() < 0.3:
                db_query(host, random.choice(DB_QUERIES))
            else:
                http_get(host, rand_url(random.choice(urls)), timeout=10)
            time.sleep(random.uniform(0.1, 0.5))


def idle_sleep(min_s, max_s):
    """Sleep for min_s–max_s seconds; 10% chance of a long idle (2–4× longer)."""
    base = random.uniform(min_s, max_s)
    if random.random() < 0.10:
        base *= random.uniform(2, 4)
    time.sleep(base)


def http_get(host, url, timeout=10):
    try:
        req = urllib.request.Request(url, headers={"Connection": "close"})
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


def tcp_noise(host, target_ip, port):
    """Open a short-lived TCP connection to generate a distinct flow record."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(1)
        s.connect((target_ip, port))
        s.send(b"hello")
        s.close()
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Attack patterns
# ---------------------------------------------------------------------------

def http_flood(host, target_ip, target_port, duration):
    """
    Send HTTP flood to target_ip:target_port for duration seconds.
    Sends rapid HTTP GET requests to blend with normal traffic but with abnormal volume.
    """
    log(host, "ATTACK", f"HTTP flood starting to {target_ip}:{target_port} for {duration}s")
    print(f"\n>>> {host} ATTACK STARTED: HTTP flood to {target_ip}:{target_port} <<<\n", file=sys.stderr, flush=True)
    
    url = f"http://{target_ip}:{target_port}/index.html"
    start_time = time.time()
    request_count = 0
    
    try:
        while time.time() - start_time < duration:
            try:
                req = urllib.request.Request(url)
                with urllib.request.urlopen(req, timeout=2) as resp:
                    _ = resp.read()
                    request_count += 1
            except Exception as e:
                # Log but continue flooding on error (timeout, connection reset, etc.)
                pass
    finally:
        pass
    
    elapsed = time.time() - start_time
    log(host, "ATTACK", f"HTTP flood ended ({request_count} requests in {elapsed:.1f}s)")
    print(f"\n>>> {host} ATTACK ENDED: HTTP flood completed <<<\n", file=sys.stderr, flush=True)


def run_attack_in_thread(host, attack_type, target_ip, target_port, attack_delay, attack_duration):
    """Run attack in a background thread after initial delay."""
    time.sleep(attack_delay)
    
    if attack_type == "http_flood":
        http_flood(host, target_ip, target_port, attack_duration)
    else:
        log(host, "ATTACK", f"Unknown attack type: {attack_type}")


def periodic_attacks(host, interval_sec=120, duration_sec=40):
    """Continuously attack every interval_sec for duration_sec (no normal traffic)."""
    next_attack_time = time.time() + interval_sec
    
    while True:
        current_time = time.time()
        
        # Check if it's time to start an attack
        if current_time >= next_attack_time:
            http_flood(host, WEB_SRV, WEB_PORT, duration_sec)
            next_attack_time = time.time() + interval_sec
        
        # Sleep briefly to avoid busy-waiting
        time.sleep(0.5)


# ---------------------------------------------------------------------------
# Traffic profiles — one per host
# ---------------------------------------------------------------------------

def profile_h11(host):
    """Light browser + DB: web/DB queries."""
    urls = [WEB_URLS["index"], WEB_URLS["small"]]
    while True:
        if random.random() < 0.35:
            db_query(host, random.choice(DB_QUERIES))
        else:
            http_get(host, rand_url(random.choice(urls)))
        maybe_burst(host, urls)
        if random.random() < 0.30:
            tcp_noise(host, WEB_SRV, WEB_PORT)
        idle_sleep(0.2, 1.5)


def profile_h12(host):
    """Medium downloader + DB: medium.bin and DB queries, variable 8-25s interval."""
    while True:
        if random.random() < 0.45:
            db_query(host, random.choice(DB_QUERIES))
        else:
            timeout = random.randint(20, 45)
            http_get(host, rand_url(WEB_URLS["medium"]), timeout=timeout)
        if random.random() < 0.1:
            # Occasional quick double-fetch
            http_get(host, rand_url(WEB_URLS["small"]))
        if random.random() < 0.30:
            tcp_noise(host, WEB_SRV, WEB_PORT)
        idle_sleep(0.5, 3.0)


def profile_h13(host):
    """Heavy browser + DB: all web endpoints and DB queries, 0.5-4s interval."""
    urls = list(WEB_URLS.values())
    while True:
        if random.random() < 0.28:
            db_query(host, random.choice(DB_QUERIES))
        else:
            http_get(host, rand_url(random.choice(urls)))
        maybe_burst(host, urls)
        idle_sleep(0.1, 1.5)


def profile_h14(host):
    """Ping both + occasional HTTP/DB: variable ping count and request mix."""
    action_counter = 0
    while True:
        ping_count = random.randint(1, 3)
        ping(host, WEB_SRV, count=ping_count)
        if random.random() < 0.6:
            ping(host, DB_SRV, count=random.randint(1, 2))
        action_counter += 1
        if random.random() < 0.3:
            if random.random() < 0.5:
                http_get(host, rand_url(WEB_URLS["index"]))
            else:
                db_query(host, random.choice(DB_QUERIES))
        if random.random() < 0.30:
            tcp_noise(host, WEB_SRV, WEB_PORT)
        idle_sleep(0.3, 1.5)


def profile_h21(host):
    """DB reader + web: DB queries and HTTP requests."""
    urls = [WEB_URLS["index"], WEB_URLS["small"]]
    while True:
        if random.random() < 0.55:
            db_query(host, random.choice(DB_QUERIES))
        else:
            http_get(host, rand_url(random.choice(urls)))
        maybe_burst(host, urls)
        if random.random() < 0.30:
            tcp_noise(host, DB_SRV, DB_PORT)
        idle_sleep(0.3, 2.0)


def profile_h22(host):
    """Large downloader + DB: large.bin and DB queries, 20-70s interval."""
    while True:
        if random.random() < 0.30:
            db_query(host, random.choice(DB_QUERIES))
        else:
            timeout = random.randint(45, 90)
            # Occasionally download medium instead of large
            url = WEB_URLS["large"] if random.random() < 0.7 else WEB_URLS["medium"]
            http_get(host, rand_url(url), timeout=timeout)
        if random.random() < 0.30:
            tcp_noise(host, WEB_SRV, WEB_PORT)
        idle_sleep(1, 5)


def profile_h23(host):
    """Dual-server: mix web and DB with variable rhythm, 1-5s interval."""
    urls = [WEB_URLS["index"], WEB_URLS["small"], WEB_URLS["medium"]]
    while True:
        r = random.random()
        if r < 0.50:
            db_query(host, random.choice(DB_QUERIES))
        elif r < 0.80:
            http_get(host, rand_url(random.choice(urls)))
        else:
            # Occasionally do both back-to-back
            http_get(host, rand_url(WEB_URLS["index"]))
            time.sleep(random.uniform(0.2, 0.8))
            db_query(host, random.choice(DB_QUERIES))
        idle_sleep(0.2, 1.5)


def profile_h24(host):
    """Bursty browser + DB: variable burst size and pause duration."""
    urls = list(WEB_URLS.values())
    while True:
        burst_size = random.randint(2, 8)
        for _ in range(burst_size):
            if random.random() < 0.35:
                db_query(host, random.choice(DB_QUERIES))
            else:
                http_get(host, rand_url(random.choice(urls)))
            time.sleep(random.uniform(0.1, 1.0))
        if random.random() < 0.30:
            tcp_noise(host, WEB_SRV, WEB_PORT)
        # Variable pause between bursts
        idle_sleep(0.5, 3.0)


def profile_h31(host):
    """Slow steady + DB: small files and DB queries, 5-18s interval."""
    urls = [WEB_URLS["small"], WEB_URLS["index"]]
    while True:
        if random.random() < 0.50:
            db_query(host, random.choice(DB_QUERIES))
        else:
            http_get(host, rand_url(random.choice(urls)))
        if random.random() < 0.08:
            # Rare burst
            for _ in range(random.randint(2, 3)):
                http_get(host, rand_url(WEB_URLS["small"]))
                time.sleep(random.uniform(0.5, 1.5))
        if random.random() < 0.30:
            tcp_noise(host, WEB_SRV, WEB_PORT)
        idle_sleep(0.5, 3.0)


def profile_h32(host):
    """Mixed sizes + DB: random web files and DB queries, variable 2-10s interval."""
    urls = list(WEB_URLS.values())
    while True:
        if random.random() < 0.35:
            db_query(host, random.choice(DB_QUERIES))
        else:
            timeout = random.choice([10, 20, 30, 45])
            http_get(host, rand_url(random.choice(urls)), timeout=timeout)
        maybe_burst(host, [WEB_URLS["index"], WEB_URLS["small"]], db=False)
        idle_sleep(0.3, 2.0)


def profile_h33(host):
    """Multi-ping + mixed: variable ping counts and occasional HTTP/DB."""
    while True:
        ping(host, WEB_SRV, count=random.randint(1, 4))
        if random.random() < 0.7:
            ping(host, DB_SRV, count=random.randint(1, 3))
        if random.random() < 0.35:
            if random.random() < 0.5:
                http_get(host, rand_url(WEB_URLS["index"]))
            else:
                db_query(host, random.choice(DB_QUERIES))
        if random.random() < 0.30:
            tcp_noise(host, WEB_SRV, WEB_PORT)
        idle_sleep(0.3, 2.0)


def profile_h34(host):
    """Bulk transfer + DB: large/medium downloads and DB queries, 15-50s interval."""
    while True:
        if random.random() < 0.35:
            db_query(host, random.choice(DB_QUERIES))
        else:
            if random.random() < 0.6:
                http_get(host, rand_url(WEB_URLS["large"]), timeout=90)
            else:
                http_get(host, rand_url(WEB_URLS["medium"]), timeout=45)
        if random.random() < 0.30:
            tcp_noise(host, WEB_SRV, WEB_PORT)
        idle_sleep(1, 5)


def profile_h15(host):
    """Short-poll client: rapid small HTTP GETs, occasional DB, 0.1-0.5s interval."""
    while True:
        if random.random() < 0.15:
            db_query(host, random.choice(DB_QUERIES))
        else:
            http_get(host, rand_url(WEB_URLS["small"]), timeout=5)
        if random.random() < 0.20:
            http_get(host, rand_url(WEB_URLS["index"]), timeout=5)
        idle_sleep(0.1, 0.5)


def profile_h16(host):
    """Scheduled batch: periodic large download followed by a long idle pause."""
    while True:
        http_get(host, rand_url(WEB_URLS["large"]), timeout=90)
        if random.random() < 0.40:
            db_query(host, random.choice(DB_QUERIES))
        idle_sleep(10, 30)


def profile_h25(host):
    """DB-heavy reader: almost exclusively DB queries at high frequency."""
    while True:
        db_query(host, random.choice(DB_QUERIES))
        if random.random() < 0.10:
            http_get(host, rand_url(WEB_URLS["index"]))
        idle_sleep(0.1, 1.0)


def profile_h26(host):
    """API-like mixed: index/small HTTP with frequent DB, 0.3-2s interval."""
    urls = [WEB_URLS["index"], WEB_URLS["small"]]
    while True:
        r = random.random()
        if r < 0.50:
            db_query(host, random.choice(DB_QUERIES))
        elif r < 0.80:
            http_get(host, rand_url(random.choice(urls)))
        else:
            http_get(host, rand_url(random.choice(urls)))
            time.sleep(random.uniform(0.1, 0.4))
            db_query(host, random.choice(DB_QUERIES))
        if random.random() < 0.20:
            tcp_noise(host, DB_SRV, DB_PORT)
        idle_sleep(0.3, 2.0)


def profile_h35(host):
    """Sequential crawler: fetches all WEB_URLS endpoints in round-robin order."""
    url_keys = list(WEB_URLS.keys())
    idx = 0
    while True:
        key = url_keys[idx % len(url_keys)]
        http_get(host, rand_url(WEB_URLS[key]), timeout=45)
        idx += 1
        if random.random() < 0.25:
            db_query(host, random.choice(DB_QUERIES))
        idle_sleep(0.5, 3.0)


def profile_h36(host):
    """Low-rate monitor: very infrequent activity, ping + rare HTTP, 5-20s idle."""
    while True:
        ping(host, WEB_SRV, count=random.randint(1, 2))
        if random.random() < 0.50:
            ping(host, DB_SRV, count=1)
        if random.random() < 0.20:
            http_get(host, rand_url(WEB_URLS["index"]))
        if random.random() < 0.10:
            db_query(host, random.choice(DB_QUERIES))
        idle_sleep(5, 20)


def run_parallel(profile_func, host, n_threads=3):
    """Run profile_func in n_threads parallel daemon threads to increase flow density."""
    threads = []
    for _ in range(n_threads):
        t = threading.Thread(target=profile_func, args=(host,), daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


PROFILES = {
    "h11": profile_h11,
    "h12": profile_h12,
    "h13": profile_h13,
    "h14": profile_h14,
    "h15": profile_h15,
    "h16": profile_h16,
    "h21": profile_h21,
    "h22": profile_h22,
    "h23": profile_h23,
    "h24": profile_h24,
    "h25": profile_h25,
    "h26": profile_h26,
    "h31": profile_h31,
    "h32": profile_h32,
    "h33": profile_h33,
    "h34": profile_h34,
    "h35": profile_h35,
    "h36": profile_h36,
}


def main():
    parser = argparse.ArgumentParser(description="Host traffic generator")
    parser.add_argument("host", choices=PROFILES.keys(), help="Host name")
    parser.add_argument(
        "--start-delay", type=int, default=0, metavar="MAX",
        help="Sleep a random 0-MAX seconds before starting (for staggering)",
    )
    parser.add_argument(
        "--attack", action="store_true",
        help="Run HTTP flood instead of normal traffic",
    )
    args = parser.parse_args()

    if args.start_delay > 0:
        delay = random.uniform(0, args.start_delay)
        log(args.host, "WAIT", f"starting in {delay:.1f}s")
        time.sleep(delay)

    log(args.host, "START", f"profile={args.host}")

    try:
        if args.attack:
            # Attack-only mode: send periodic attacks every 2 minutes for 40 seconds
            log(args.host, "MODE", "attack-only — sending periodic HTTP floods")
            periodic_attacks(args.host, interval_sec=120, duration_sec=40)
        else:
            # Normal traffic profile with parallel threads for density
            run_parallel(PROFILES[args.host], args.host, n_threads=3)
    except KeyboardInterrupt:
        log(args.host, "STOP", "interrupted")


if __name__ == "__main__":
    main()
