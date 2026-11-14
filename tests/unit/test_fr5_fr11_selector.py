from config.settings import SERVERS
from controller.selector import ServerSelector


def test_tc11_numeric_dynamic_selection(telemetry):
    """TC11 FR-5: known normalized metrics with 0.4/0.4/0.2 weights select lowest score."""
    telemetry["srv1"].update(rtt_ms=10, utilization=0.0, active_conns=0)
    telemetry["srv2"].update(rtt_ms=20, utilization=0.0, active_conns=5)
    telemetry["srv3"].update(rtt_ms=30, utilization=1.0, active_conns=10)
    selector = ServerSelector("dynamic")
    assert selector.select_server("c1", telemetry) == SERVERS["srv1"]


def test_tc12_single_healthy_server_selected(telemetry):
    """TC12 FR-5: boundary with exactly one UP server."""
    telemetry["srv1"]["status"] = "DOWN"
    telemetry["srv2"]["status"] = "UP"
    telemetry["srv3"]["status"] = "DOWN"
    assert ServerSelector().select_server("c1", telemetry) == SERVERS["srv2"]


def test_tc13_all_down_current_fallback(telemetry):
    """TC13 FR-5: record current implementation policy for all-down input."""
    for data in telemetry.values():
        data["status"] = "DOWN"
    assert ServerSelector().select_server("c1", telemetry) == SERVERS["srv1"]


def test_tc20_static_client_mapping():
    """TC20 FR-11: configured static baseline maps clients to servers."""
    selector = ServerSelector("static")
    expected = {"c1": "srv1", "c2": "srv2", "c3": "srv3", "c4": "srv1", "c5": "srv2", "c6": "srv3"}
    for client, server in expected.items():
        assert selector.select_server(client, {}) == SERVERS[server]


def test_tc21_dynamic_and_static_mode_instances(telemetry):
    """TC21 FR-11: mode selected at construction affects the next server choice."""
    dynamic = ServerSelector("dynamic")
    static = ServerSelector("static")
    assert dynamic.select_server("c2", telemetry) == SERVERS["srv1"]
    assert static.select_server("c2", telemetry) == SERVERS["srv2"]
