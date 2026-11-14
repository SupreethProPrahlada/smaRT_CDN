from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp, udp, ether_types
from ryu.lib import hub
import sys, os, json, time, struct

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import (
    VIP_IP, VIP_MAC, SERVERS, CLIENT_IPS, CLIENT_MACS, CONTENT_PORT,
    HB_LISTEN_IP, HB_PORT, PROBE_ETHERTYPE, PROBE_INTERVAL, EMA_ALPHA,
    STATS_INTERVAL, LOG_INTERVAL, DEFAULT_CDN_MODE, LIVE_ROUTES_JSON
)
from controller.paths import DPID_S1, S1_TRUNK_PORTS, SERVER_SWITCH_PORTS, add_flow
from controller.selector import ServerSelector

class SmartCDNController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}
        self.selector = ServerSelector(cdn_mode=DEFAULT_CDN_MODE)
        self.server_telemetry = {
            'srv1': {'status': 'UP', 'rtt_ms': 10.0, 'utilization': 0.0, 'active_conns': 0, 'capacity': 100},
            'srv2': {'status': 'UP', 'rtt_ms': 40.0, 'utilization': 0.0, 'active_conns': 0, 'capacity': 50},
            'srv3': {'status': 'UP', 'rtt_ms': 100.0, 'utilization': 0.0, 'active_conns': 0, 'capacity': 10},
        }
        self.port_stats_history = {}
        self.last_log_time = time.time()
        hub.spawn(self._monitor_loop)
        hub.spawn(self._probe_loop)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        self.datapaths[dpid] = dp
        parser, ofproto = dp.ofproto_parser, dp.ofproto

        add_flow(dp, priority=0, match=parser.OFPMatch(), actions=[parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)])

        if dpid in SERVER_SWITCH_PORTS:
            cfg = SERVER_SWITCH_PORTS[dpid]
            add_flow(dp, priority=200, match=parser.OFPMatch(eth_type=PROBE_ETHERTYPE), actions=[parser.OFPActionOutput(cfg['s1_trunk_port'])])
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=cfg['server_port']), actions=[parser.OFPActionOutput(cfg['s1_trunk_port'])])
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=cfg['s1_trunk_port']), actions=[parser.OFPActionOutput(cfg['server_port'])])

        if dpid == DPID_S1:
            add_flow(dp, priority=200, match=parser.OFPMatch(eth_type=PROBE_ETHERTYPE), actions=[parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)])

    def _probe_loop(self):
        hub.sleep(2.0)
        while True:
            if DPID_S1 in self.datapaths:
                dp = self.datapaths[DPID_S1]
                parser = dp.ofproto_parser
                now = time.time()
                for srv_id, trunk in S1_TRUNK_PORTS.items():
                    payload = struct.pack('!d8s', now, srv_id.ljust(8).encode('ascii'))
                    pkt = packet.Packet()
                    pkt.add_protocol(ethernet.ethernet(ethertype=PROBE_ETHERTYPE, dst='ff:ff:ff:ff:ff:ff', src=VIP_MAC))
                    pkt.add_protocol(payload)
                    pkt.serialize()
                    dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=dp.ofproto.OFP_NO_BUFFER, in_port=dp.ofproto.OFPP_CONTROLLER, actions=[parser.OFPActionOutput(trunk)], data=pkt.data))
            hub.sleep(PROBE_INTERVAL)

    def _monitor_loop(self):
        while True:
            for dp in list(self.datapaths.values()):
                dp.send_msg(dp.ofproto_parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY))
            self.export_live_routes()
            if time.time() - self.last_log_time >= LOG_INTERVAL:
                self.log_controller_status()
                self.last_log_time = time.time()
            hub.sleep(STATS_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        dpid = ev.msg.datapath.id
        now = time.time()
        if dpid == DPID_S1:
            for stat in ev.msg.body:
                for srv_id, trunk in S1_TRUNK_PORTS.items():
                    if stat.port_no == trunk:
                        key = (dpid, stat.port_no)
                        tot_bytes = stat.tx_bytes + stat.rx_bytes
                        if key in self.port_stats_history:
                            pb, pt = self.port_stats_history[key]
                            dt = now - pt
                            if dt > 0.1:
                                mbps = ((tot_bytes - pb) * 8.0) / (dt * 1_000_000.0)
                                self.server_telemetry[srv_id]['utilization'] = round(min(1.0, max(0.0, mbps / self.server_telemetry[srv_id]['capacity'])), 3)
                        self.port_stats_history[key] = (tot_bytes, now)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp, dpid, in_port = msg.datapath, msg.datapath.id, msg.match['in_port']
        pkt = packet.Packet(msg.data)
        pkt_eth = pkt.get_protocol(ethernet.ethernet)
        if not pkt_eth: return

        if pkt_eth.ethertype == PROBE_ETHERTYPE:
            try:
                t_sent, s_b = struct.unpack('!d8s', msg.data[14:30])
                s_id = s_b.decode().strip()
                if s_id in self.server_telemetry:
                    rtt = (time.time() - t_sent) * 1000.0
                    old = self.server_telemetry[s_id]['rtt_ms']
                    self.server_telemetry[s_id]['rtt_ms'] = round((EMA_ALPHA * rtt) + ((1.0 - EMA_ALPHA) * old), 2)
            except Exception: pass
            return

        pkt_arp = pkt.get_protocol(arp.arp)
        if pkt_arp and pkt_arp.opcode == arp.ARP_REQUEST:
            t_ip, t_mac = pkt_arp.dst_ip, None
            if t_ip == VIP_IP: t_mac = VIP_MAC
            elif t_ip == HB_LISTEN_IP: t_mac = "00:00:00:00:02:54"
            elif t_ip in [s['ip'] for s in SERVERS.values()]: t_mac = next(s['mac'] for s in SERVERS.values() if s['ip'] == t_ip)
            elif t_ip in CLIENT_IPS.values(): t_mac = next(mac for cid, mac in CLIENT_MACS.items() if CLIENT_IPS[cid] == t_ip)
            if t_mac:
                r = packet.Packet()
                r.add_protocol(ethernet.ethernet(ethertype=ether_types.ETH_TYPE_ARP, dst=pkt_eth.src, src=t_mac))
                r.add_protocol(arp.arp(opcode=arp.ARP_REPLY, src_mac=t_mac, src_ip=t_ip, dst_mac=pkt_arp.src_mac, dst_ip=pkt_arp.src_ip))
                r.serialize()
                dp.send_msg(dp.ofproto_parser.OFPPacketOut(datapath=dp, buffer_id=dp.ofproto.OFP_NO_BUFFER, in_port=dp.ofproto.OFPP_CONTROLLER, actions=[dp.ofproto_parser.OFPActionOutput(in_port)], data=r.data))
            return

        pkt_ip, pkt_udp = pkt.get_protocol(ipv4.ipv4), pkt.get_protocol(udp.udp)
        if pkt_ip and pkt_udp and pkt_udp.dst_port == HB_PORT:
            try:
                p = msg.data[14 + pkt_ip.header_length*4 + 8:].decode(errors='ignore').strip().split()
                if len(p) >= 3 and p[0] == "STATUS" and p[1] in self.server_telemetry:
                    self.server_telemetry[p[1]]['active_conns'] = int(p[2])
                    self.server_telemetry[p[1]]['status'] = 'UP'
            except Exception: pass
            return

        pkt_tcp = pkt.get_protocol(tcp.tcp)
        if dpid == DPID_S1 and pkt_ip and pkt_tcp and pkt_ip.dst == VIP_IP and pkt_tcp.dst_port == CONTENT_PORT:
            cid = next((k for k, v in CLIENT_IPS.items() if v == pkt_ip.src), "c1")
            srv = self.selector.select_server(cid, self.server_telemetry)
            trunk = S1_TRUNK_PORTS[srv['id']]
            parser = dp.ofproto_parser
            self.logger.info(f"[Route Decision] Mode={self.selector.cdn_mode} | Client {pkt_ip.src} -> {srv['id']} (RTT={self.server_telemetry[srv['id']]['rtt_ms']}ms Util={self.server_telemetry[srv['id']]['utilization']*100:.1f}%)")

            add_flow(dp, priority=100, match=parser.OFPMatch(in_port=in_port, eth_type=0x0800, ip_proto=6, ipv4_src=pkt_ip.src, ipv4_dst=VIP_IP, tcp_dst=CONTENT_PORT), actions=[parser.OFPActionSetField(ipv4_dst=srv['ip']), parser.OFPActionSetField(eth_dst=srv['mac']), parser.OFPActionOutput(trunk)], idle_timeout=60)
            add_flow(dp, priority=100, match=parser.OFPMatch(in_port=trunk, eth_type=0x0800, ip_proto=6, ipv4_src=srv['ip'], ipv4_dst=pkt_ip.src, tcp_src=CONTENT_PORT), actions=[parser.OFPActionSetField(ipv4_src=VIP_IP), parser.OFPActionSetField(eth_src=VIP_MAC), parser.OFPActionOutput(in_port)], idle_timeout=60)

            dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port, actions=[parser.OFPActionSetField(ipv4_dst=srv['ip']), parser.OFPActionSetField(eth_dst=srv['mac']), parser.OFPActionOutput(trunk)], data=msg.data if msg.buffer_id == dp.ofproto.OFP_NO_BUFFER else None))

    def export_live_routes(self):
        try:
            os.makedirs(os.path.dirname(LIVE_ROUTES_JSON), exist_ok=True)
            with open(LIVE_ROUTES_JSON, 'w') as f:
                json.dump({'timestamp': time.time(), 'cdn_mode': self.selector.cdn_mode, 'servers': self.server_telemetry}, f, indent=2)
        except Exception: pass

    def log_controller_status(self):
        self.logger.info("-------------------- Smart CDN State (5s Log) --------------------")
        self.logger.info(f"Mode: {self.selector.cdn_mode.upper()}")
        for s, d in self.server_telemetry.items():
            self.logger.info(f"  [{s}] Status: {d['status']} | RTT: {d['rtt_ms']:6.2f} ms | Util: {d['utilization']*100:5.1f}% | Conns: {d['active_conns']}")
        self.logger.info("-----------------------------------------------------------------")
