from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.integration


class FakeParser:
    def OFPMatch(self, **fields):
        return fields

    def OFPActionOutput(self, port, **kwargs):
        return ("output", port, kwargs)

    def OFPActionSetField(self, **fields):
        return ("set_field", fields)

    def OFPInstructionActions(self, instruction_type, actions):
        return SimpleNamespace(instruction_type=instruction_type, actions=actions)

    def OFPFlowMod(self, **fields):
        return SimpleNamespace(**fields)

    def OFPPacketOut(self, **fields):
        return SimpleNamespace(**fields)


class FakeDatapath:
    def __init__(self):
        self.id = 1
        self.ofproto = SimpleNamespace(
            OFP_NO_BUFFER=0xFFFFFFFF,
            OFPP_CONTROLLER=0xFFFFFFFD,
            OFPCML_NO_BUFFER=0xFFFF,
            OFPIT_APPLY_ACTIONS=4,
        )
        self.ofproto_parser = FakeParser()
        self.messages = []

    def send_msg(self, message):
        self.messages.append(message)


def _controller():
    pytest.importorskip("ryu")
    from controller.cdn_controller import SmartCDNController
    from controller.selector import ServerSelector

    controller = object.__new__(SmartCDNController)
    controller.selector = ServerSelector("dynamic")
    controller.server_telemetry = {
        "srv1": {"status": "UP", "rtt_ms": 10.0, "utilization": 0.0, "active_conns": 0},
        "srv2": {"status": "UP", "rtt_ms": 40.0, "utilization": 0.0, "active_conns": 0},
        "srv3": {"status": "UP", "rtt_ms": 100.0, "utilization": 0.0, "active_conns": 0},
    }
    controller.logger = SimpleNamespace(info=lambda *args, **kwargs: None)
    return controller


def _event(data, datapath):
    return SimpleNamespace(msg=SimpleNamespace(
        data=data,
        datapath=datapath,
        match={"in_port": 1},
        buffer_id=datapath.ofproto.OFP_NO_BUFFER,
    ))


def _arp_request(dst_ip):
    from ryu.lib.packet import arp, ethernet, packet

    pkt = packet.Packet()
    pkt.add_protocol(ethernet.ethernet(
        dst="ff:ff:ff:ff:ff:ff", src="00:00:00:00:00:01", ethertype=0x0806
    ))
    pkt.add_protocol(arp.arp(
        opcode=arp.ARP_REQUEST,
        src_mac="00:00:00:00:00:01",
        src_ip="10.0.0.1",
        dst_mac="00:00:00:00:00:00",
        dst_ip=dst_ip,
    ))
    pkt.serialize()
    return pkt.data


def test_tc02_vip_arp_and_bidirectional_nat_rules():
    """TC02 FR-1: VIP ARP reply and TCP packet-in install both NAT directions."""
    controller = _controller()
    from ryu.lib.packet import arp, ethernet, ipv4, packet, tcp

    dp = FakeDatapath()
    controller.packet_in_handler(_event(_arp_request("10.0.0.100"), dp))
    arp_out = dp.messages[-1]
    arp_reply = packet.Packet(arp_out.data)
    assert arp_reply.get_protocol(arp.arp).opcode == arp.ARP_REPLY
    assert arp_reply.get_protocol(arp.arp).src_ip == "10.0.0.100"
    assert arp_reply.get_protocol(arp.arp).src_mac == "00:00:00:00:01:00"

    request = packet.Packet()
    request.add_protocol(ethernet.ethernet(
        dst="00:00:00:00:01:00", src="00:00:00:00:00:01", ethertype=0x0800
    ))
    request.add_protocol(ipv4.ipv4(src="10.0.0.1", dst="10.0.0.100", proto=6))
    request.add_protocol(tcp.tcp(src_port=40000, dst_port=8000))
    request.serialize()
    controller.packet_in_handler(_event(request.data, dp))

    flows = [message for message in dp.messages if hasattr(message, "instructions")]
    assert len(flows) == 2
    assert flows[0].idle_timeout == flows[1].idle_timeout == 60
    assert flows[0].match["ipv4_dst"] == "10.0.0.100"
    assert flows[1].match["ipv4_src"] == "10.0.0.11"
    forward_actions = flows[0].instructions[0].actions
    reverse_actions = flows[1].instructions[0].actions
    assert ("set_field", {"ipv4_dst": "10.0.0.11"}) in forward_actions
    assert ("set_field", {"ipv4_src": "10.0.0.100"}) in reverse_actions


def test_tc03_unrelated_arp_target_gets_no_controller_reply():
    """TC03 FR-1: controller does not claim an unrelated IP address via ARP."""
    controller = _controller()
    dp = FakeDatapath()

    controller.packet_in_handler(_event(_arp_request("10.0.0.250"), dp))

    assert dp.messages == []
