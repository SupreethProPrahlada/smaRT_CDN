import struct
import time
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration


def _controller():
    pytest.importorskip("ryu")
    import controller.cdn_controller as controller_module
    from controller.cdn_controller import SmartCDNController
    from controller.selector import ServerSelector

    controller = object.__new__(SmartCDNController)
    controller.datapaths = {}
    controller.selector = ServerSelector(cdn_mode="dynamic")
    controller.server_telemetry = {
        "srv1": {"status": "UP", "rtt_ms": 10.0, "utilization": 0.0, "active_conns": 0, "capacity": 100},
        "srv2": {"status": "UP", "rtt_ms": 40.0, "utilization": 0.0, "active_conns": 0, "capacity": 50},
        "srv3": {"status": "UP", "rtt_ms": 100.0, "utilization": 0.0, "active_conns": 0, "capacity": 10},
    }
    controller.port_stats_history = {}
    return controller_module, controller


def _event(data, datapath_id=1, in_port=7):
    return SimpleNamespace(msg=SimpleNamespace(
        data=data,
        datapath=SimpleNamespace(id=datapath_id),
        match={"in_port": in_port},
    ))


def _probe_packet(ethertype, payload):
    from ryu.lib.packet import ethernet, packet

    pkt = packet.Packet()
    pkt.add_protocol(ethernet.ethernet(
        dst="ff:ff:ff:ff:ff:ff", src="00:00:00:00:01:00", ethertype=ethertype
    ))
    pkt.add_protocol(payload)
    pkt.serialize()
    return pkt.data


def test_tc04_probe_ema_uses_half_old_and_half_new_value(monkeypatch):
    """TC04 FR-2: incoming probe RTT is smoothed with alpha 0.5."""
    controller_module, controller = _controller()
    now = time.time()
    monkeypatch.setattr(controller_module.time, "time", lambda: now)
    payload = struct.pack("!d8s", now - 0.020, b"srv1    ")

    controller.packet_in_handler(_event(_probe_packet(0x88B5, payload)))

    assert controller.server_telemetry["srv1"]["rtt_ms"] == pytest.approx(15.0, abs=1.0)


def test_tc05_malformed_probe_does_not_change_known_measurement():
    """TC05 FR-2: short probe payload is ignored without changing telemetry."""
    _, controller = _controller()
    original = controller.server_telemetry["srv1"]["rtt_ms"]

    controller.packet_in_handler(_event(_probe_packet(0x88B5, b"short")))

    assert controller.server_telemetry["srv1"]["rtt_ms"] == original


def test_tc06_port_stats_convert_to_clamped_utilization(monkeypatch):
    """TC06 FR-3: zero and ordinary byte deltas produce correct bounded utilization."""
    controller_module, controller = _controller()
    current_time = [100.0]
    monkeypatch.setattr(controller_module.time, "time", lambda: current_time[0])
    stat = SimpleNamespace(port_no=7, tx_bytes=0, rx_bytes=0)
    event = SimpleNamespace(msg=SimpleNamespace(datapath=SimpleNamespace(id=1), body=[stat]))

    controller.port_stats_reply_handler(event)
    current_time[0] = 101.0
    controller.port_stats_reply_handler(event)
    assert controller.server_telemetry["srv1"]["utilization"] == 0.0

    stat.tx_bytes = 6_250_000
    current_time[0] = 102.0
    controller.port_stats_reply_handler(event)

    assert controller.server_telemetry["srv1"]["utilization"] == 0.5


def test_tc07_port_stats_saturate_above_capacity(monkeypatch):
    """TC07 FR-3: measured throughput above link capacity is capped at 100%."""
    controller_module, controller = _controller()
    monkeypatch.setattr(controller_module.time, "time", lambda: 101.0)
    controller.port_stats_history[(1, 7)] = (0, 100.0)
    stat = SimpleNamespace(port_no=7, tx_bytes=25_000_000, rx_bytes=0)
    event = SimpleNamespace(msg=SimpleNamespace(datapath=SimpleNamespace(id=1), body=[stat]))

    controller.port_stats_reply_handler(event)

    assert controller.server_telemetry["srv1"]["utilization"] == 1.0


def _heartbeat_packet(src_ip, text):
    from ryu.lib.packet import ethernet, ipv4, packet, udp

    pkt = packet.Packet()
    pkt.add_protocol(ethernet.ethernet(
        dst="00:00:00:00:01:00", src="00:00:00:00:00:11", ethertype=0x0800
    ))
    pkt.add_protocol(ipv4.ipv4(src=src_ip, dst="10.0.0.254", proto=17))
    pkt.add_protocol(udp.udp(src_port=45000, dst_port=9000))
    pkt.add_protocol(text.encode())
    pkt.serialize()
    return pkt.data


def test_tc09_valid_heartbeat_updates_known_server_load():
    """TC09 FR-4: valid heartbeat updates the known server's load and UP state."""
    _, controller = _controller()

    controller.packet_in_handler(_event(_heartbeat_packet("10.0.0.11", "STATUS srv1 4 123.0\n")))

    assert controller.server_telemetry["srv1"]["active_conns"] == 4
    assert controller.server_telemetry["srv1"]["status"] == "UP"


def test_tc10_malformed_and_unknown_heartbeats_are_ignored():
    """TC10 FR-4: malformed, unknown, or unauthorized heartbeat datagrams are ignored."""
    _, controller = _controller()

    controller.packet_in_handler(_event(_heartbeat_packet("10.0.0.11", "STATUS srv1 bad 123.0\n")))
    controller.packet_in_handler(_event(_heartbeat_packet("10.0.0.11", "STATUS unknown 4 123.0\n")))
    controller.packet_in_handler(_event(_heartbeat_packet("10.0.0.99", "STATUS srv1 9 123.0\n")))

    assert controller.server_telemetry["srv1"]["active_conns"] == 0
    assert "unknown" not in controller.server_telemetry
