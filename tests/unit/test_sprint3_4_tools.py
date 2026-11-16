"""Sprint 3/4 (Developer 2): configuration, congestion generator and HTML route map."""

import json
import time

from config import settings
from scripts import congestion, route_map


def test_tc58_failover_timing_configuration():
    """TC58 FR-4/FR-7: 10 s heartbeat timeout, and client retries outlast it."""
    assert settings.HEARTBEAT_TIMEOUT == 10.0
    assert settings.HEARTBEAT_TIMEOUT > 2 * settings.HEARTBEAT_INTERVAL
    assert settings.CLIENT_MAX_RETRIES * settings.CLIENT_RETRY_DELAY > settings.HEARTBEAT_TIMEOUT


def test_tc59_congestion_generator_command():
    """TC59 FR-12: generator sends constant-rate UDP iperf traffic to the chosen sink."""
    assert congestion.build_command("10.0.0.6", 90, 30) == [
        "iperf", "-c", "10.0.0.6", "-u", "-b", "90M", "-t", "30", "-i", "5"]


def _snapshot(**overrides):
    data = {
        "timestamp": time.time(), "cdn_mode": "dynamic", "srv1_path": "detour",
        "servers": {
            "srv1": {"status": "UP", "rtt_ms": 12.0, "utilization": 0.9, "active_conns": 1},
            "srv2": {"status": "DOWN", "rtt_ms": 40.0, "utilization": 0.0, "active_conns": 0},
            "srv3": {"status": "UP", "rtt_ms": 100.0, "utilization": 0.1, "active_conns": 0},
        },
        "paths": {
            "primary": {"status": "UP", "rtt_ms": 12.0, "utilization": 0.92, "background": 0.9},
            "detour": {"status": "UP", "rtt_ms": 33.0, "utilization": 0.4, "background": 0.0},
        },
        "flows": [{"client": "c1", "server": "srv1", "path": "detour", "rate_mbps": 41.5}],
    }
    data.update(overrides)
    return data


def test_tc60_route_map_shows_paths_servers_and_flows():
    """TC60 HTML route map: active path, link state, a DOWN server and live flows are rendered."""
    page = route_map.render_html(_snapshot())

    assert "<svg" in page and 'http-equiv="refresh"' in page
    assert "srv1 path: <strong>detour</strong>" in page
    assert 'class="link hot"' in page                 # primary at 92%
    assert ">DOWN</text>" in page                      # srv2 label
    assert "<td>c1</td><td>srv1</td><td>detour</td><td>41.5</td>" in page
    assert "Controller data is" not in page


def test_tc61_route_map_flags_stale_data_and_escapes_text(tmp_path):
    """TC61 HTML route map: old or missing controller data is flagged; values are HTML-escaped."""
    page = route_map.render_html(_snapshot(timestamp=time.time() - 60, cdn_mode="<b>x</b>"))
    assert "Controller data is" in page
    assert "<b>x</b>" not in page and "&lt;b&gt;x&lt;/b&gt;" in page

    source, target = tmp_path / "live.json", tmp_path / "map.html"
    source.write_text(json.dumps(_snapshot()))
    route_map.write_once(str(source), str(target))
    assert "Smart CDN Route Map" in target.read_text()
    route_map.write_once(str(tmp_path / "missing.json"), str(target))   # no data yet: still a page
    assert "No active flows" in target.read_text()
