#!/usr/bin/env python3
"""
smaRT_CDN Live Terminal Dashboard (Sprint 2)
Reads results/live_routes.json and displays a real-time ASCII telemetry dashboard.
"""

import os
import sys
import time
import json
from datetime import datetime

ROUTES_FILE = "results/live_routes.json"

def make_meter(val: float, max_val: float, length: int = 10) -> str:
    ratio = min(max(val / max_val, 0.0), 1.0)
    filled = int(round(ratio * length))
    return f"[{'#' * filled}{'-' * (length - filled)}]"

def render_dashboard():
    while True:
        # Clear screen
        os.system('clear' if os.name == 'posix' else 'cls')

        if not os.path.exists(ROUTES_FILE):
            print("==================================================================")
            print("                smaRT_CDN LIVE MONITOR (Sprint 2)                 ")
            print("==================================================================")
            print(f"Waiting for controller telemetry at: {ROUTES_FILE} ...")
            print("Ensure Ryu controller is running: ryu-manager controller/cdn_controller.py")
            time.sleep(1)
            continue

        try:
            with open(ROUTES_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except Exception:
            time.sleep(0.5)
            continue

        mode = data.get('cdn_mode', 'dynamic').upper()
        profile = data.get('profile', 'balanced').upper()
        desc = data.get('profile_desc', 'Standard Balanced')
        weights = data.get('weights', {'latency': 0.4, 'utilization': 0.4, 'load': 0.2})
        servers = data.get('servers', {})
        t_str = datetime.fromtimestamp(data.get('timestamp', time.time())).strftime('%Y-%m-%d %H:%M:%S')

        print("==================================================================")
        print("                smaRT_CDN LIVE MONITOR (Sprint 2)                 ")
        print("==================================================================")
        print(f"  Time: {t_str}   |   Mode: {mode}")
        print(f"  Policy Profile: {profile} ({desc})")
        print(f"  Weights: Latency={weights['latency']*100:.0f}%, Util={weights['utilization']*100:.0f}%, Load={weights['load']*100:.0f}%")
        print("------------------------------------------------------------------")
        print(f" {'SERVER':<6} {'IP':<11} {'STATUS':<9} {'RTT (ms)':<17} {'UTILIZATION':<14} {'CONNS':<6}")
        print("------------------------------------------------------------------")

        for srv_id, s in sorted(servers.items()):
            ip = s.get('ip', '10.0.0.x')
            status = s.get('status', 'HEALTHY')
            rtt = s.get('rtt_ms', 0.0)
            util = s.get('utilization', 0.0) * 100.0
            conns = s.get('active_conns', 0)

            rtt_meter = f"{make_meter(rtt, 100.0, 8)} {rtt:4.1f}"
            util_meter = f"{make_meter(util, 100.0, 6)} {util:4.1f}%"

            print(f" {srv_id:<6} {ip:<11} {status:<9} {rtt_meter:<17} {util_meter:<14} {conns:<6}")

        print("------------------------------------------------------------------")
        print(" Press Ctrl+C to exit. (Auto-refreshes every 1.0s)                 ")
        print("==================================================================")

        time.sleep(1)

if __name__ == '__main__':
    try:
        render_dashboard()
    except KeyboardInterrupt:
        print("\nMonitor stopped.")
        sys.exit(0)
