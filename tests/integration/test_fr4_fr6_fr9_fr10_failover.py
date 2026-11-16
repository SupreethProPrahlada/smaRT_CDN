"""Sprint 3/4 (Developer 2): server failover and srv1 path migration in the controller.

Uses Ryu's real OpenFlow 1.3 parser with datapaths that record what the
controller sends, so the rules checked here are the ones a switch would get.
"""

import time
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration


class RecordingDatapath:
    def __init__(self, dpid):
        from ryu.ofproto import ofproto_v1_3, ofproto_v1_3_parser

        self.id = dpid
        self.ofproto = ofproto_v1_3
        self.ofproto_parser = ofproto_v1_3_parser
        self.messages = []

    def send_msg(self, message):
        self.messages.append(message)

    def flow_mods(self, command=None):
        mods = [m for m in self.messages if type(m).__name__ == "OFPFlowMod"]
        return [m for m in mods if command is None or m.command == command]


def _controller():
    pytest.importorskip("ryu")
    from controller.cdn_controller import SmartCDNController
    from controller.selector import ServerSelector

    controller = object.__new__(SmartCDNController)
    controller.logs = []
    controller.logger = SimpleNamespace(info=controller.logs.append, warning=controller.logs.append)
    controller.selector = ServerSelector("dynamic")
    controller.server_telemetry = {
        "srv1": {"status": "UP", "rtt_ms": 10.0, "utilization": 0.0, "active_conns": 0, "capacity": 100},
        "srv2": {"status": "UP", "rtt_ms": 40.0, "utilization": 0.0, "active_conns": 0, "capacity": 50},
        "srv3": {"status": "UP", "rtt_ms": 100.0, "utilization": 0.0, "active_conns": 0, "capacity": 10},
    }
    controller.port_stats_history = {}
    controller.datapaths = {dpid: RecordingDatapath(dpid) for dpid in (1, 2, 5)}
    controller._init_failover_state()
    for p in controller.paths.values():          # both srv1 paths healthy
        p.update(status="UP", rtt_ms=12.0, last_probe=time.time())
    controller.paths["detour"]["rtt_ms"] = 32.0
    return controller


def _flow(controller, client="c1", server="srv1", path="primary"):
    ip = f"10.0.0.{client[1:]}"
    flow = {"client": client, "client_ip": ip, "server": server, "in_port": int(client[1:]),
            "path": path if server == "srv1" else None, "rate_mbps": 0.0, "bytes": None, "stamp": 0.0}
    controller.flows[ip] = flow
    return flow


def _outputs(mod):
    return [a.port for inst in mod.instructions for a in inst.actions if type(a).__name__ == "OFPActionOutput"]


def _heartbeat(controller, src_ip, text):
    from ryu.lib.packet import ethernet, ipv4, packet, udp

    pkt = packet.Packet()
    pkt.add_protocol(ethernet.ethernet(dst="00:00:00:00:02:54", src="00:00:00:00:00:11", ethertype=0x0800))
    pkt.add_protocol(ipv4.ipv4(src=src_ip, dst="10.0.0.254", proto=17))
    pkt.add_protocol(udp.udp(src_port=45000, dst_port=9000))
    pkt.add_protocol(text.encode())
    pkt.serialize()
    controller.packet_in_handler(SimpleNamespace(msg=SimpleNamespace(
        data=pkt.data, datapath=controller.datapaths[1], match={"in_port": 7})))


def test_tc50_silent_server_goes_down_and_flows_are_flushed():
    """TC50 FR-4: after 10 s without heartbeats a server is DOWN and its s1 NAT rules are deleted."""
    controller = _controller()
    _flow(controller, "c2", "srv2")
    controller.last_heartbeat["srv2"] = time.time() - 11

    controller.evaluate()

    s1 = controller.datapaths[1]
    assert controller.server_telemetry["srv2"]["status"] == "DOWN"
    assert controller.flows == {}
    deletes = s1.flow_mods(s1.ofproto.OFPFC_DELETE)
    assert any(m.out_port == 8 for m in deletes)                       # forward rules to srv2's trunk
    assert any(m.match.get("ipv4_src") == "10.0.0.12" for m in deletes)  # reverse rules from srv2
    assert any("srv2 DOWN" in line for line in controller.logs)


def test_tc51_heartbeat_brings_server_back_up():
    """TC51 FR-4: the next valid heartbeat from a DOWN server marks it UP again."""
    controller = _controller()
    controller.server_telemetry["srv1"]["status"] = "DOWN"

    _heartbeat(controller, "10.0.0.11", "STATUS srv1 0 1.0\n")

    assert controller.server_telemetry["srv1"]["status"] == "UP"


def test_tc52_spoofed_heartbeat_does_not_keep_a_dead_server_alive():
    """TC52 FR-4: a heartbeat for srv1 from another address does not reset its timeout."""
    controller = _controller()
    controller.last_heartbeat["srv1"] = time.time() - 11

    _heartbeat(controller, "10.0.0.99", "STATUS srv1 0 1.0\n")
    controller.evaluate()

    assert controller.server_telemetry["srv1"]["status"] == "DOWN"


def test_tc53_primary_link_down_moves_live_flow_to_detour():
    """TC53 FR-9: a port-status DOWN on s1-s2 moves srv1 flows to s5 and re-points s2."""
    controller = _controller()
    _flow(controller, "c1")
    s1, s2 = controller.datapaths[1], controller.datapaths[2]
    desc = SimpleNamespace(port_no=7, state=s1.ofproto.OFPPS_LINK_DOWN, config=0)

    controller.port_status_handler(SimpleNamespace(msg=SimpleNamespace(
        datapath=s1, desc=desc, reason=s1.ofproto.OFPPR_MODIFY)))

    assert controller.srv1_path == "detour"
    assert controller.flows["10.0.0.1"]["path"] == "detour"
    forward = [m for m in s1.flow_mods(s1.ofproto.OFPFC_ADD) if m.match.get("ipv4_dst") == "10.0.0.100"]
    assert _outputs(forward[-1]) == [10]                                   # s1 -> s5
    s2_rules = s2.flow_mods(s2.ofproto.OFPFC_ADD)
    assert any(m.match.get("ipv4_dst") == "10.0.0.1" and _outputs(m) == [3] for m in s2_rules)
    assert any(m.match.get("in_port") == 1 and _outputs(m) == [3] for m in s2_rules)  # srv1 egress


def test_tc54_other_traffic_on_primary_moves_flows_to_detour():
    """TC54 FR-6: other traffic filling >= 50% more of the primary than the detour moves srv1 flows."""
    controller = _controller()
    _flow(controller, "c1")
    controller.paths["primary"]["background"] = 0.9

    controller.evaluate()

    assert controller.srv1_path == "detour"
    assert controller.flows["10.0.0.1"]["path"] == "detour"
    assert any("primary congested" in line for line in controller.logs)


def test_tc55_a_flows_own_traffic_is_not_congestion():
    """TC55 FR-6: a busy primary carrying only our own CDN flow is not treated as congested."""
    controller = _controller()
    flow = _flow(controller, "c1")
    flow["rate_mbps"] = 95.0

    controller._update_path_load("primary", 97.0)
    controller.evaluate()

    assert controller.paths["primary"]["utilization"] == 0.97
    assert controller.paths["primary"]["background"] < 0.05
    assert controller.srv1_path == "primary"


def test_tc62_unmeasured_new_flow_is_not_mistaken_for_congestion():
    """TC62 FR-6: before a new flow's rate is measured, its traffic does not count as congestion."""
    controller = _controller()
    flow = _flow(controller, "c1")
    flow["rate_mbps"] = None                     # first flow-stats sample not taken yet

    controller._update_path_load("primary", 90.0)
    controller.evaluate()

    assert controller.paths["primary"]["background"] == 0.0
    assert controller.srv1_path == "primary" and flow["path"] == "primary"


def test_tc56_recovered_primary_takes_new_flows():
    """TC56 FR-10: once the primary is healthy again new srv1 flows use it; live detour flows stay."""
    controller = _controller()
    controller.srv1_path = "detour"
    _flow(controller, "c1", path="detour")

    controller.evaluate()

    assert controller.srv1_path == "primary"
    assert controller.flows["10.0.0.1"]["path"] == "detour"
    s2_rules = controller.datapaths[2].flow_mods(controller.datapaths[2].ofproto.OFPFC_ADD)
    assert any(m.match.get("in_port") == 1 and _outputs(m) == [2] for m in s2_rules)


def test_tc63_flows_leave_a_failed_detour():
    """TC63 FR-9: flows left on the detour after recovery move back if the detour itself fails."""
    controller = _controller()
    flow = _flow(controller, "c1", path="detour")      # srv1_path is already 'primary'
    controller.paths["detour"]["ports_down"].add((5, 1))

    controller.evaluate()

    assert controller.paths["detour"]["status"] == "DOWN"
    assert flow["path"] == "primary"
    s1 = controller.datapaths[1]
    forward = [m for m in s1.flow_mods(s1.ofproto.OFPFC_ADD) if m.match.get("ipv4_dst") == "10.0.0.100"]
    assert _outputs(forward[-1]) == [7]


def test_tc57_detour_probe_measures_its_own_path():
    """TC57 FR-2/issue 4: a returning detour probe updates the detour RTT and keeps it UP."""
    import struct
    from ryu.lib.packet import ethernet, packet

    controller = _controller()
    controller.paths["detour"].update(rtt_ms=None, last_probe=0.0)
    pkt = packet.Packet()
    pkt.add_protocol(ethernet.ethernet(dst="ff:ff:ff:ff:ff:ff", src="00:00:00:00:01:00", ethertype=0x88B5))
    pkt.add_protocol(struct.pack("!d8s", time.time() - 0.030, b"srv1d   "))
    pkt.serialize()

    controller.packet_in_handler(SimpleNamespace(msg=SimpleNamespace(
        data=pkt.data, datapath=controller.datapaths[1], match={"in_port": 10})))

    assert 25 < controller.paths["detour"]["rtt_ms"] < 60
    assert time.time() - controller.paths["detour"]["last_probe"] < 1
    assert controller.server_telemetry["srv1"]["rtt_ms"] == 10.0          # primary RTT untouched
