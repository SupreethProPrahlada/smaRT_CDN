from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp, ether_types
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import VIP_IP, VIP_MAC, SERVERS, CLIENT_IPS, CLIENT_MACS, CONTENT_PORT
from controller.paths import DPID_S1, S1_TRUNK_PORTS, SERVER_SWITCH_PORTS, add_flow

class SmartCDNController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}
        self.rr_index = 0
        self.server_keys = ['srv1', 'srv2', 'srv3']

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp, dpid = ev.msg.datapath, ev.msg.datapath.id
        self.datapaths[dpid] = dp
        parser, ofproto = dp.ofproto_parser, dp.ofproto
        add_flow(dp, priority=0, match=parser.OFPMatch(), actions=[parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)])

        if dpid in SERVER_SWITCH_PORTS:
            cfg = SERVER_SWITCH_PORTS[dpid]
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=cfg['server_port']), actions=[parser.OFPActionOutput(cfg['s1_trunk_port'])])
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=cfg['s1_trunk_port']), actions=[parser.OFPActionOutput(cfg['server_port'])])

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp, dpid, in_port = msg.datapath, msg.datapath.id, msg.match['in_port']
        pkt = packet.Packet(msg.data)
        pkt_eth = pkt.get_protocol(ethernet.ethernet)
        if not pkt_eth: return

        pkt_arp = pkt.get_protocol(arp.arp)
        if pkt_arp and pkt_arp.opcode == arp.ARP_REQUEST:
            t_ip, t_mac = pkt_arp.dst_ip, None
            if t_ip == VIP_IP: t_mac = VIP_MAC
            elif t_ip in [s['ip'] for s in SERVERS.values()]: t_mac = next(s['mac'] for s in SERVERS.values() if s['ip'] == t_ip)
            elif t_ip in CLIENT_IPS.values(): t_mac = next(mac for cid, mac in CLIENT_MACS.items() if CLIENT_IPS[cid] == t_ip)
            if t_mac:
                r = packet.Packet()
                r.add_protocol(ethernet.ethernet(ethertype=ether_types.ETH_TYPE_ARP, dst=pkt_eth.src, src=t_mac))
                r.add_protocol(arp.arp(opcode=arp.ARP_REPLY, src_mac=t_mac, src_ip=t_ip, dst_mac=pkt_arp.src_mac, dst_ip=pkt_arp.src_ip))
                r.serialize()
                dp.send_msg(dp.ofproto_parser.OFPPacketOut(datapath=dp, buffer_id=dp.ofproto.OFP_NO_BUFFER, in_port=dp.ofproto.OFPP_CONTROLLER, actions=[dp.ofproto_parser.OFPActionOutput(in_port)], data=r.data))
            return

        pkt_ip, pkt_tcp = pkt.get_protocol(ipv4.ipv4), pkt.get_protocol(tcp.tcp)
        if dpid == DPID_S1 and pkt_ip and pkt_tcp and pkt_ip.dst == VIP_IP and pkt_tcp.dst_port == CONTENT_PORT:
            srv = SERVERS[self.server_keys[self.rr_index % 3]]
            self.rr_index += 1
            trunk = S1_TRUNK_PORTS[srv['id']]
            parser = dp.ofproto_parser

            add_flow(dp, priority=100, match=parser.OFPMatch(in_port=in_port, eth_type=0x0800, ip_proto=6, ipv4_src=pkt_ip.src, ipv4_dst=VIP_IP, tcp_dst=CONTENT_PORT), actions=[parser.OFPActionSetField(ipv4_dst=srv['ip']), parser.OFPActionSetField(eth_dst=srv['mac']), parser.OFPActionOutput(trunk)], idle_timeout=60)
            add_flow(dp, priority=100, match=parser.OFPMatch(in_port=trunk, eth_type=0x0800, ip_proto=6, ipv4_src=srv['ip'], ipv4_dst=pkt_ip.src, tcp_src=CONTENT_PORT), actions=[parser.OFPActionSetField(ipv4_src=VIP_IP), parser.OFPActionSetField(eth_src=VIP_MAC), parser.OFPActionOutput(in_port)], idle_timeout=60)
            dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port, actions=[parser.OFPActionSetField(ipv4_dst=srv['ip']), parser.OFPActionSetField(eth_dst=srv['mac']), parser.OFPActionOutput(trunk)], data=msg.data if msg.buffer_id == dp.ofproto.OFP_NO_BUFFER else None))
