#!/usr/bin/env python3
"""
smaRT_CDN Live Telemetry NOC Dashboard (Sprint 2)
Real-time monitoring with ANSI colors, Unicode meters, and live metrics.
"""

import os
import sys
import time
import json
import csv
from datetime import datetime

ROUTES_FILE = "results/live_routes.json"
CSV_FILE = "results/data/client-transfers.csv"

SERVER_META = {
    'srv1': {'ip': '10.0.0.11', 'link': 'Primary (100M / 5ms)',  'role': 'Edge Replica 1'},
    'srv2': {'ip': '10.0.0.12', 'link': 'Secondary (50M / 20ms)', 'role': 'Edge Replica 2'},
    'srv3': {'ip': '10.0.0.13', 'link': 'Backup (10M / 50ms)',    'role': 'Edge Replica 3'},
}

GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
CYAN = "\033[96m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"

def safe_float(val, default=0.0):
    try:
        return float(val)
    except (ValueError, TypeError):
        return default

def color_bar(val: float, max_val: float, length: int = 12, is_latency: bool = True) -> str:
    ratio = min(max(val / max_val, 0.0), 1.0)
    filled = int(round(ratio * length))
    empty = length - filled

    if is_latency:
        color = GREEN if ratio <= 0.25 else (YELLOW if ratio <= 0.60 else RED)
    else:
        color = GREEN if ratio <= 0.50 else (YELLOW if ratio <= 0.80 else RED)

    return f"{color}{'█' * filled}{DIM}{'░' * empty}{RESET}"

def get_recent_transfers():
    if not os.path.exists(CSV_FILE):
        return []
    try:
        with open(CSV_FILE, 'r', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
            return rows[-3:]
    except Exception:
        return []

def render_dashboard():
    while True:
        os.system('clear' if os.name == 'posix' else 'cls')

        if not os.path.exists(ROUTES_FILE):
            print(f"{YELLOW}Waiting for Ryu telemetry at {ROUTES_FILE} ...{RESET}")
            time.sleep(1)
            continue

        try:
            with open(ROUTES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            time.sleep(0.5)
            continue

        mode = data.get('cdn_mode', 'dynamic').upper()
        servers = data.get('servers', {})
        t_str = datetime.fromtimestamp(data.get('timestamp', time.time())).strftime('%H:%M:%S')

        best_srv = 'srv1'
        lowest_rtt = 999.0
        for sid, sdata in servers.items():
            rtt = sdata.get('rtt_ms', 999.0)
            if rtt < lowest_rtt:
                lowest_rtt = rtt
                best_srv = sid

        print(f"{BOLD}{CYAN}==============================================================================={RESET}")
        print(f"{BOLD}{CYAN}             smaRT_CDN TELEMETRY & NETWORK OPERATIONS CENTER (NOC)             {RESET}")
        print(f"{BOLD}{CYAN}==============================================================================={RESET}")
        print(f" {BOLD}System Time:{RESET} {t_str}   |   {BOLD}Mode:{RESET} {GREEN if mode == 'DYNAMIC' else YELLOW}{mode}{RESET}   |   {BOLD}Lowest RTT Replica:{RESET} {GREEN}{best_srv.upper()} ({lowest_rtt:.1f} ms){RESET}")
        print("-------------------------------------------------------------------------------")
        print(f" {BOLD}{'SERVER':<7} {'IP ADDRESS':<13} {'STATUS':<9} {'RTT LATENCY':<24} {'UTILIZATION':<17} {'TRUNK LINK'}{RESET}")
        print("-------------------------------------------------------------------------------")

        for srv_id in ['srv1', 'srv2', 'srv3']:
            s = servers.get(srv_id, {})
            meta = SERVER_META.get(srv_id, {})
            ip = meta.get('ip', '10.0.0.1x')
            link = meta.get('link', '')
            status_raw = s.get('status', 'UP')
            status = f"{GREEN}ONLINE{RESET} " if status_raw in ['UP', 'HEALTHY'] else f"{RED}OFFLINE{RESET}"
            
            rtt = safe_float(s.get('rtt_ms', 50.0))
            util = safe_float(s.get('utilization', 0.0)) * 100.0

            rtt_bar = f"{color_bar(rtt, 100.0, 10, True)} {rtt:5.1f} ms"
            util_bar = f"{color_bar(util, 100.0, 8, False)} {util:4.1f}%"

            marker = f"{GREEN}▶{RESET}" if srv_id == best_srv else " "
            print(f"{marker}{srv_id:<6} {ip:<13} {status:<18} {rtt_bar:<33} {util_bar:<26} {DIM}{link}{RESET}")

        print("-------------------------------------------------------------------------------")
        print(f"{BOLD} Recent Verified Downloads (from {CSV_FILE}):{RESET}")
        transfers = get_recent_transfers()
        if transfers:
            for t in transfers:
                c_id = t.get('client_id', 'client')
                size_bytes = safe_float(t.get('size_bytes') or t.get('bytes_received') or t.get('bytes') or 10485760)
                size_mb = size_bytes / (1024 * 1024)
                mbps = safe_float(t.get('throughput_mbps') or t.get('mbps') or 0.0)
                dur = safe_float(t.get('duration_s') or t.get('duration_sec') or t.get('duration') or 0.0)
                print(f"   • {c_id:<10} | Payload: {size_mb:4.1f} MB | Time: {dur:4.2f}s | Speed: {BOLD}{mbps:5.2f} Mbps{RESET} | {GREEN}Logged Transfer{RESET}")
        else:
            print(f"   {DIM}No transfers logged yet.{RESET}")

        print("-------------------------------------------------------------------------------")
        print(f" {DIM}Press Ctrl+C to exit. Updates live every 1.0s.{RESET}")
        print(f"{BOLD}{CYAN}==============================================================================={RESET}")

        time.sleep(1)

if __name__ == '__main__':
    try:
        render_dashboard()
    except KeyboardInterrupt:
        print("\nNOC Monitor stopped.")
        sys.exit(0)
