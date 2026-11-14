"""
Smart CDN - System Configuration and Constants
Aligns with IEEE 830 SRS Specification (Appendix A: Data Dictionary).
Owned by Developer 1 (Supreeth Prahalada) - Sprint 0 Baseline.
"""

from typing import Dict, Any

VIP_IP = "10.0.0.100"
VIP_MAC = "00:00:00:00:01:00"
SUBNET_MASK = "255.255.255.0"
IP_PREFIX = "10.0.0.0/24"

CLIENT_IPS = {f"c{i}": f"10.0.0.{i}" for i in range(1, 7)}
CLIENT_MACS = {f"c{i}": f"00:00:00:00:00:0{i}" for i in range(1, 7)}

SERVERS = {
    "srv1": {"id": "srv1", "ip": "10.0.0.11", "mac": "00:00:00:00:00:11", "switch": "s2", "capacity_mbps": 100, "delay_ms": 5},
    "srv2": {"id": "srv2", "ip": "10.0.0.12", "mac": "00:00:00:00:00:12", "switch": "s3", "capacity_mbps": 50, "delay_ms": 20},
    "srv3": {"id": "srv3", "ip": "10.0.0.13", "mac": "00:00:00:00:00:13", "switch": "s4", "capacity_mbps": 10, "delay_ms": 50},
}

OFP_CONTROLLER_PORT = 6653
CONTENT_PORT = 8000
HB_PORT = 9000
HB_LISTEN_IP = "10.0.0.254"

PROBE_ETHERTYPE = 0x88B5
PROBE_INTERVAL = 1.0
EMA_ALPHA = 0.5
STATS_INTERVAL = 1.0

HEARTBEAT_INTERVAL = 2.0
CHUNK_SIZE = 65536
CONTENT_DIR = "/tmp/cdn_content"
CLIENT_DOWNLOAD_DIR = "/tmp/client_downloads"

SELECTION_WEIGHTS = {"latency": 0.40, "utilization": 0.40, "load": 0.20}
DEFAULT_CDN_MODE = "dynamic"
STATIC_MAPPING = {"c1": "srv1", "c4": "srv1", "c2": "srv2", "c5": "srv2", "c3": "srv3", "c6": "srv3"}

LOG_INTERVAL = 5.0
LIVE_ROUTES_JSON = "results/live_routes.json"
CLIENT_TRANSFERS_CSV = "results/data/client-transfers.csv"

# Compatibility aliases
VIP = VIP_IP
SERVER_POOL = SERVERS
CONTROLLER_PORT = CONTENT_PORT
TELEMETRY_PORT = HB_PORT
ETHERTYPE_PROBE = PROBE_ETHERTYPE
PROBE_INTERVAL_SEC = PROBE_INTERVAL
STATS_INTERVAL_SEC = STATS_INTERVAL
CLIENT_CSV = CLIENT_TRANSFERS_CSV
SWITCH_PORTS = {'srv1': 1, 'srv2': 2, 'srv3': 3}
TRUNK_CAPACITY = {'s1-s2': 100_000_000, 's1-s3': 50_000_000, 's1-s4': 10_000_000}
