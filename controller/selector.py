"""
Smart CDN - 3-Factor Server Selection Algorithm
Computes composite route costs and selects the optimal content server (FR-5, FR-11).
Score = (0.4 * Latency) + (0.4 * Utilization) + (0.2 * Server Load)
Owned by Developer 1 (Supreeth Prahalada) - Sprint 2.
"""

from typing import Dict, Any, Optional
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import SELECTION_WEIGHTS, STATIC_MAPPING, SERVERS


class ServerSelector:
    def __init__(self, cdn_mode: str = "dynamic"):
        self.cdn_mode = cdn_mode
        self.weights = SELECTION_WEIGHTS

    def set_mode(self, mode: str):
        """Switch between 'dynamic' (smart 3-factor) and 'static' (fixed baseline)."""
        if mode in ["dynamic", "static"]:
            self.cdn_mode = mode

    def select_server(
        self,
        client_id: str,
        server_telemetry: Dict[str, Dict[str, Any]]
    ) -> Optional[Dict[str, Any]]:
        """
        Selects best server for a client request.
        server_telemetry schema:
        {
            'srv1': {'status': 'UP', 'rtt_ms': 5.2, 'utilization': 0.10, 'active_conns': 1},
            ...
        }
        """
        # 1. Static Mode (FR-11): Fixed client-to-server mapping
        if self.cdn_mode == "static":
            target_srv = STATIC_MAPPING.get(client_id, "srv1")
            return SERVERS[target_srv]

        # 2. Dynamic Mode (FR-5): 3-Factor Composite Cost
        # Filter only healthy (UP) servers
        available = {
            s_id: data for s_id, data in server_telemetry.items()
            if data.get('status', 'UP') == 'UP'
        }

        if not available:
            # Fallback to srv1 if all down or no telemetry yet
            return SERVERS['srv1']

        if len(available) == 1:
            s_id = list(available.keys())[0]
            return SERVERS[s_id]

        # Extract metric values for normalization
        rtts = [data.get('rtt_ms', 50.0) for data in available.values()]
        conns = [data.get('active_conns', 0) for data in available.values()]

        min_rtt, max_rtt = min(rtts), max(rtts)
        min_conn, max_conn = min(conns), max(conns)

        eps = 1e-6
        best_server_id = None
        lowest_score = float('inf')
        scores = {}

        for s_id, data in available.items():
            rtt = data.get('rtt_ms', 50.0)
            util = data.get('utilization', 0.0)  # already 0.0 to 1.0
            conn = data.get('active_conns', 0)

            # Normalization (0.0 to 1.0)
            norm_latency = (rtt - min_rtt) / ((max_rtt - min_rtt) + eps) if max_rtt > min_rtt else 0.0
            norm_util = min(1.0, max(0.0, util))
            norm_load = (conn - min_conn) / ((max_conn - min_conn) + eps) if max_conn > min_conn else 0.0

            # 3-Factor Composite Score:
            # Score = (0.4 * Latency) + (0.4 * Utilization) + (0.2 * Server Load)
            score = (
                self.weights['latency'] * norm_latency +
                self.weights['utilization'] * norm_util +
                self.weights['load'] * norm_load
            )
            scores[s_id] = score

            if score < lowest_score:
                lowest_score = score
                best_server_id = s_id

        return SERVERS[best_server_id]
