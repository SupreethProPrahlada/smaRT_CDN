"""
Smart CDN - System Configuration and Constants
Aligns with IEEE 830 SRS Specification (Appendix A: Data Dictionary).
Owned by Developer 1 (Supreeth Prahalada) - Sprint 0 Baseline.
"""

from typing import Dict, Any

# 1. Virtual IP & Addressing (FR-1)
VIP_IP: str = "10.0.0.100"
VIP_MAC: str = "00:00:00:00:01:00"
SUBNET_MASK: str = "255.255.255.0"
IP_PREFIX: str = "10.0.0.0/24"

# 2. Clients Configuration (c1 - c6)
CLIENT_IPS: Dict[str, str] = {
    f"c{i}": f"10.0.0.{i}" for i in range(1, 7)
}
CLIENT_MACS: Dict[str, str] = {
    f"c{i}": f"00:00:00:00:00:0{i}" for i in range(1, 7)
}

# 3. Backend Servers Configuration (srv1 - srv3)
SERVERS: Dict[str, Dict[str, Any]] = {
    "srv1": {
        "id": "srv1",
        "ip": "10.0.0.11",
        "mac": "00:00:00:00:00:11",
        "switch": "s2",
        "trunk": "s1-s2",
        "capacity_mbps": 100,
        "base_delay_ms": 5,
    },
    "srv2": {
        "id": "srv2",
        "ip": "10.0.0.12",
        "mac": "00:00:00:00:00:12",
        "switch": "s3",
        "trunk": "s1-s3",
        "capacity_mbps": 50,
        "base_delay_ms": 20,
    },
    "srv3": {
        "id": "srv3",
        "ip": "10.0.0.13",
        "mac": "00:00:00:00:00:13",
        "switch": "s4",
        "trunk": "s1-s4",
        "capacity_mbps": 10,
        "base_delay_ms": 50,
    },
}

SERVER_BY_IP: Dict[str, Dict[str, Any]] = {
    srv["ip"]: srv for srv in SERVERS.values()
}

# 4. Ports & Protocols
OFP_CONTROLLER_PORT: int = 6653
CONTENT_PORT: int = 8000
HB_PORT: int = 9000
HB_LISTEN_IP: str = "10.0.0.254"

# 5. Telemetry & Monitoring Parameters (FR-2, FR-3, NFR-3)
PROBE_ETHERTYPE: int = 0x88B5           # Custom EtherType for ping telemetry frames
PROBE_INTERVAL: float = 1.0             # Latency probe frequency (1.0 Hz)
EMA_ALPHA: float = 0.5                  # Exponential Moving Average factor
STATS_INTERVAL: float = 1.0             # Port statistics query interval

# 6. Heartbeat & Crash Detection (FR-4, NFR-2)
HEARTBEAT_INTERVAL: float = 2.0         # Server heartbeat frequency in seconds
HEARTBEAT_TIMEOUT: float = 10.0         # Dead server threshold in seconds
MAX_RETRIES: int = 12                   # Maximum client retry attempts

# 7. Content Streaming & Integrity (FR-7)
CHUNK_SIZE: int = 65536                 # 64 KB binary streaming chunk size
CONTENT_DIR: str = "/tmp/cdn_content"
CLIENT_DOWNLOAD_DIR: str = "/tmp/client_downloads"

# 8. Server Selection & Routing (FR-5, FR-11)
SELECTION_WEIGHTS = {
    "latency": 0.40,                    # 40% Weight for latency
    "utilization": 0.40,                # 40% Weight for bandwidth utilization
    "load": 0.20,                       # 20% Weight for server active connections
}

DEFAULT_CDN_MODE: str = "dynamic"       # "dynamic" or "static"

STATIC_MAPPING = {
    "c1": "srv1", "c4": "srv1",
    "c2": "srv2", "c5": "srv2",
    "c3": "srv3", "c6": "srv3",
}

SHIFT_RTT: float = 0.050                # 50 ms latency increase triggers detour switch s5

# 9. Logging & Result Artifacts (FR-8, NFR-5)
LOG_INTERVAL: float = 5.0               # Controller state logging interval
LIVE_ROUTES_JSON: str = "results/live_routes.json"
CLIENT_TRANSFERS_CSV: str = "results/data/client-transfers.csv"
EXPERIMENTS_CSV: str = "results/data/experiments.csv"
