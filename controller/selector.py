"""
Smart CDN - Server Selection Engine (Sprint 2)
Computes dynamic scores using a 3-Factor Cost Algorithm:
  Score = w_rtt * Norm(RTT) + w_util * Norm(Util) + w_load * Norm(ActiveConns)

Supports Dynamic Policy Profiles via CDN_PROFILE:
  - 'balanced'   : 40% Latency, 40% Utilization, 20% Load (Default)
  - 'gaming'     : 80% Latency, 10% Utilization, 10% Load (Low-latency focus)
  - 'bulk_video' : 20% Latency, 70% Utilization, 10% Load (High-throughput focus)

Supports Static Baseline Fallback via CDN_MODE=static.
"""

import os
from typing import Dict, Any, Tuple

CDN_PROFILES = {
    'balanced':   {'w_rtt': 0.40, 'w_util': 0.40, 'w_load': 0.20, 'desc': 'Standard CDN Balanced Profile'},
    'gaming':     {'w_rtt': 0.80, 'w_util': 0.10, 'w_load': 0.10, 'desc': 'Ultra-Low Latency Gaming Profile'},
    'bulk_video': {'w_rtt': 0.20, 'w_util': 0.70, 'w_load': 0.10, 'desc': 'High-Bandwidth Bulk Video Streaming'},
}

class ServerSelector:
    def __init__(self):
        self.cdn_mode = os.environ.get('CDN_MODE', 'dynamic').lower()
        self.profile_name = os.environ.get('CDN_PROFILE', 'balanced').lower()
        
        # Load profile or default to balanced
        profile = CDN_PROFILES.get(self.profile_name, CDN_PROFILES['balanced'])
        self.w_rtt = profile['w_rtt']
        self.w_util = profile['w_util']
        self.w_load = profile['w_load']
        self.profile_desc = profile['desc']

    def normalize_rtt(self, rtt_ms: float) -> float:
        # Scale between 0ms (0.0) and 100ms (1.0)
        return min(max(rtt_ms / 100.0, 0.0), 1.0)

    def normalize_util(self, util: float) -> float:
        # Utilization is already 0.0 - 1.0
        return min(max(util, 0.0), 1.0)

    def normalize_load(self, active_conns: int) -> float:
        # Scale between 0 (0.0) and 20 conns (1.0)
        return min(max(active_conns / 20.0, 0.0), 1.0)

    def score_server(self, srv_id: str, telemetry: Dict[str, Any]) -> Tuple[float, Dict[str, float]]:
        rtt_norm = self.normalize_rtt(telemetry.get('rtt_ms', 50.0))
        util_norm = self.normalize_util(telemetry.get('utilization', 0.0))
        load_norm = self.normalize_load(telemetry.get('active_conns', 0))

        score = (self.w_rtt * rtt_norm) + (self.w_util * util_norm) + (self.w_load * load_norm)
        details = {
            'rtt_norm': rtt_norm,
            'util_norm': util_norm,
            'load_norm': load_norm,
            'final_score': score
        }
        return score, details

    def select_best_server(self, client_id: str, server_telemetry: Dict[str, Dict[str, Any]]) -> str:
        # Static baseline mode comparison (FR-15)
        if self.cdn_mode == 'static':
            static_map = {'c1': 'srv1', 'c2': 'srv2', 'c3': 'srv3'}
            return static_map.get(client_id, 'srv1')

        # Dynamic mode: find healthy server with lowest 3-factor score
        best_srv = 'srv1'
        best_score = float('inf')

        for srv_id, metrics in server_telemetry.items():
            if metrics.get('status') == 'DEAD':
                continue
            score, _ = self.score_server(srv_id, metrics)
            if score < best_score:
                best_score = score
                best_srv = srv_id

        return best_srv
