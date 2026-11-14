import pytest

pytest_plugins = []

@pytest.fixture
def telemetry():
    return {
        "srv1": {"status": "UP", "rtt_ms": 10.0, "utilization": 0.0, "active_conns": 0},
        "srv2": {"status": "UP", "rtt_ms": 40.0, "utilization": 0.0, "active_conns": 0},
        "srv3": {"status": "UP", "rtt_ms": 100.0, "utilization": 0.0, "active_conns": 0},
    }
