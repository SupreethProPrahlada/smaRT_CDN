"""
Smart CDN - Ryu OpenFlow 1.3 Controller
Handles ARP for VIP (10.0.0.100) and two-way TCP NAT header rewriting (FR-1).
Owned by Developer 1 (Supreeth Prahalada) - Sprint 1.
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp, ether_types

import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import (
    VIP_IP, VIP_MAC, SERVERS, CLIENT_IPS, CLIENT_MACS, CONTENT_PORT
)
from controller.paths import (
    DPID_S1, DPID_S2, DPID_S3, DPID_S4, S1_TRUNK_PORTS, SERVER_SWITCH_PORTS, add_flow
)


class SmartCDNController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SmartCDNController, self).__init__(*args, **kwargs)
        self.server_keys = ['srv1', 'srv2', 'srv3']
        self.rr_index = 0
        self.datapaths = {}
        self.logger.info("=== Smart CDN Controller Initialized (Sprint 1 Baseline) ===")

    def get_next_server(self):
        """Simple round-robin selection for Sprint 1 (Sprint 2 will use 3-factor cost)."""
        srv_key = self.server_keys[self.rr_index % len(self.server_keys)]
        self.rr_index += 1
        return SERVERS[srv_key]

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Install table-miss flow entry on switch connection."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id
        self.datapaths[dpid] = datapath

        self.logger.info(f"Switch s{dpid} connected. Installing Table-Miss rule.")

        # Table-miss rule: send unknown packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        add_flow(datapath, priority=0, match=match, actions=actions)

        # Proactively install bidirectional forwarding on core switches s2, s3, s4
        if dpid in SERVER_SWITCH_PORTS:
            cfg = SERVER_SWITCH_PORTS[dpid]
            srv_port = cfg['server_port']
            trunk_port = cfg['s1_trunk_port']

            # Server to Trunk (s1)
            m1 = parser.OFPMatch(in_port=srv_port)
            a1 = [parser.OFPActionOutput(trunk_port)]
            add_flow(datapath, priority=10, match=m1, actions=a1)

            # Trunk (s1) to Server
            m2 = parser.OFPMatch(in_port=trunk_port)
            a2 = [parser.OFPActionOutput(srv_port)]
            add_flow(datapath, priority=10, match=m2, actions=a2)
            self.logger.info(f"Installed static trunk<->server rules on switch s{dpid}")

    def handle_arp(self, datapath, in_port, pkt_ethernet, pkt_arp):
        """Controller answers ARP queries for VIP and hosts to prevent packet storms (FR-1)."""
        if pkt_arp.opcode != arp.ARP_REQUEST:
            return

        target_ip = pkt_arp.dst_ip
        src_ip = pkt_arp.src_ip
        target_mac = None

        if target_ip == VIP_IP:
            target_mac = VIP_MAC
        elif target_ip in [s['ip'] for s in SERVERS.values()]:
            for s in SERVERS.values():
                if s['ip'] == target_ip:
                    target_mac = s['mac']
                    break
        elif target_ip in CLIENT_IPS.values():
            for c_id, ip in CLIENT_IPS.items():
                if ip == target_ip:
                    target_mac = CLIENT_MACS[c_id]
                    break

        if target_mac is None:
            return

        # Build ARP Reply
        pkt_reply = packet.Packet()
        pkt_reply.add_protocol(ethernet.ethernet(
            ethertype=ether_types.ETH_TYPE_ARP,
            dst=pkt_ethernet.src,
            src=target_mac
        ))
        pkt_reply.add_protocol(arp.arp(
            opcode=arp.ARP_REPLY,
            src_mac=target_mac,
            src_ip=target_ip,
            dst_mac=pkt_arp.src_mac,
            dst_ip=src_ip
        ))
        pkt_reply.serialize()

        # Send packet out through the port where the request arrived
        parser = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(in_port)]
        out = parser.OFPPacketOut(
            datapath=datapath,
            buffer_id=datapath.ofproto.OFP_NO_BUFFER,
            in_port=datapath.ofproto.OFPP_CONTROLLER,
            actions=actions,
            data=pkt_reply.data
        )
        datapath.send_msg(out)
        self.logger.debug(f"[ARP] Replied to {src_ip} -> {target_ip} is at {target_mac}")

    def install_nat_rules(self, datapath, client_port, client_ip, client_mac, server_info):
        """Installs two-way NAT FlowMod rules on ingress switch s1 (FR-1)."""
        parser = datapath.ofproto_parser
        server_id = server_info['id']
        server_ip = server_info['ip']
        server_mac = server_info['mac']
        trunk_port = S1_TRUNK_PORTS[server_id]

        self.logger.info(
            f"[NAT Rule] Client {client_ip} (port {client_port}) <--> Server {server_id} ({server_ip}) via trunk port {trunk_port}"
        )

        # 1. Forward Direction: Client -> VIP:8000 rewritten to Server:8000
        match_fwd = parser.OFPMatch(
            in_port=client_port,
            eth_type=ether_types.ETH_TYPE_IP,
            ip_proto=6, # TCP
            ipv4_src=client_ip,
            ipv4_dst=VIP_IP,
            tcp_dst=CONTENT_PORT
        )
        actions_fwd = [
            parser.OFPActionSetField(ipv4_dst=server_ip),
            parser.OFPActionSetField(eth_dst=server_mac),
            parser.OFPActionOutput(trunk_port)
        ]
        add_flow(datapath, priority=100, match=match_fwd, actions=actions_fwd, idle_timeout=60)

        # 2. Reverse Direction: Server:8000 -> Client rewritten to VIP:8000
        match_rev = parser.OFPMatch(
            in_port=trunk_port,
            eth_type=ether_types.ETH_TYPE_IP,
            ip_proto=6, # TCP
            ipv4_src=server_ip,
            ipv4_dst=client_ip,
            tcp_src=CONTENT_PORT
        )
        actions_rev = [
            parser.OFPActionSetField(ipv4_src=VIP_IP),
            parser.OFPActionSetField(eth_src=VIP_MAC),
            parser.OFPActionOutput(client_port)
        ]
        add_flow(datapath, priority=100, match=match_rev, actions=actions_rev, idle_timeout=60)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Processes incoming packets sent to the controller."""
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        pkt_eth = pkt.get_protocol(ethernet.ethernet)
        if not pkt_eth:
            return

        # 1. Handle ARP
        pkt_arp = pkt.get_protocol(arp.arp)
        if pkt_arp:
            self.handle_arp(datapath, in_port, pkt_eth, pkt_arp)
            return

        # 2. Handle TCP to VIP on switch s1
        pkt_ip = pkt.get_protocol(ipv4.ipv4)
        pkt_tcp = pkt.get_protocol(tcp.tcp)

        if dpid == DPID_S1 and pkt_ip and pkt_tcp:
            if pkt_ip.dst == VIP_IP and pkt_tcp.dst_port == CONTENT_PORT:
                # Select destination server
                selected_server = self.get_next_server()
                self.install_nat_rules(
                    datapath=datapath,
                    client_port=in_port,
                    client_ip=pkt_ip.src,
                    client_mac=pkt_eth.src,
                    server_info=selected_server
                )

                # Send this first packet through the rewritten path
                parser = datapath.ofproto_parser
                trunk_port = S1_TRUNK_PORTS[selected_server['id']]
                actions = [
                    parser.OFPActionSetField(ipv4_dst=selected_server['ip']),
                    parser.OFPActionSetField(eth_dst=selected_server['mac']),
                    parser.OFPActionOutput(trunk_port)
                ]
                out = parser.OFPPacketOut(
                    datapath=datapath,
                    buffer_id=msg.buffer_id,
                    in_port=in_port,
                    actions=actions,
                    data=msg.data if msg.buffer_id == datapath.ofproto.OFP_NO_BUFFER else None
                )
                datapath.send_msg(out)
                return
