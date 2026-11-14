import json
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration


def test_tc17_json_export_contains_current_mode_and_servers(monkeypatch, tmp_path):
    """TC17 FR-8: live export is valid JSON with mode and server telemetry."""
    pytest.importorskip("ryu")
    import controller.cdn_controller as controller_module
    from controller.cdn_controller import SmartCDNController
    from controller.selector import ServerSelector

    controller = object.__new__(SmartCDNController)
    controller.selector = ServerSelector(cdn_mode="dynamic")
    controller.server_telemetry = {
        "srv1": {"status": "UP", "rtt_ms": 10.0, "utilization": 0.25, "active_conns": 2}
    }
    out_path = tmp_path / "live_routes.json"
    monkeypatch.setattr(controller_module, "LIVE_ROUTES_JSON", str(out_path))

    controller.export_live_routes()

    payload = json.loads(out_path.read_text(encoding="utf-8"))
    assert payload["cdn_mode"] == "dynamic"
    assert payload["servers"]["srv1"]["active_conns"] == 2
    assert isinstance(payload["timestamp"], (int, float))


def test_tc39_controller_status_log_contains_telemetry():
    """TC39 FR-8: five-second status logger renders mode and live server metrics."""
    pytest.importorskip("ryu")
    from controller.cdn_controller import SmartCDNController
    from controller.selector import ServerSelector

    messages = []
    controller = object.__new__(SmartCDNController)
    controller.logger = SimpleNamespace(info=messages.append)
    controller.selector = ServerSelector("dynamic")
    controller.server_telemetry = {
        "srv1": {"status": "UP", "rtt_ms": 12.5, "utilization": 0.25, "active_conns": 3}
    }

    controller.log_controller_status()

    assert any("DYNAMIC" in message for message in messages)
    assert any("12.50 ms" in message and "25.0%" in message and "Conns: 3" in message for message in messages)
