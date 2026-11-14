"""
Smart CDN - OpenFlow 1.3 Ryu Controller (Sprints 1 & 2)
- Ingress switch s1 L4 bidirectional Anycast VIP NAT (10.0.0.100:8000)
- Active EtherType 0x88B5 RTT latency probing with EMA smoothing (alpha=0.5)
- OpenFlow port stats polling for trunk link utilization
- UDP status telemetry listener on port 9000
- 3-Factor Cost Selection with Dynamic Policy Profiles (gaming, bulk_video, balanced)
- OpenFlow TCAM flow aging with idle_timeout=15s
- Atomic live telemetry export to results/live_routes.json
"""

import json
import os
import time
import socket
from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3, ether
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp
from ryu.lib import hub

from config.settings import (
    VIP, VIP_MAC, SERVER_POOL, SWITCH_PORTS,
    TRUNK_CAPACITY, CONTROLLER_PORT, TELEMETRY_PORT,
    ETHERTYPE_PROBE, PROBE_INTERVAL_SEC, STATS_INTERVAL_SEC,
    RESULTS_DIR, LIVE_ROUTES_JSON
)
from controller.selector import ServerSelector

class SmartCDNController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SmartCDNController, self).__init__(*args, **kwargs)
        self.selector = ServerSelector()
        self.datapaths = {}

        # Telemetry State
        self.server_telemetry = {
            srv_id: {
                'ip': info['ip'],
                'mac': info['mac'],
                'trunk_port': info['trunk_port'],
                'status': 'HEALTHY',
                'rtt_ms': 10.0 if srv_id == 'srv1' else (40.0 if srv_id == 'srv2' else 100.0),
                'utilization': 0.0,
                'active_conns': 0,
                'last_seen': time.time(),
                'bytes_prev': 0,
                'time_prev': time.time()
            }
            for srv_id, info in SERVER_POOL.items()
        }

        # Probe Sequence tracking
        self.probe_seq = 0
        self.probe_times = {}

        # Start background green threads
        self.probe_thread = hub.spawn(self.probe_loop)
        self.stats_thread = hub.spawn(self.port_stats_loop)
        self.udp_thread = hub.spawn(self.udp_telemetry_loop)
        self.status_thread = hub.spawn(self.status_console_loop)

        self.logger.info(f"=== smaRT_CDN Controller Initialized ===")
        self.logger.info(f"Mode: {self.selector.cdn_mode.upper()} | Profile: {self.selector.profile_name.upper()} ({self.selector.profile_desc})")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        dpid = datapath.id
        self.datapaths[dpid] = datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Table-miss flow entry: send unknown packets to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions, idle_timeout=0)
        self.logger.info(f"[Switch s{dpid}] Connected & table-miss flow installed")

    def add_flow(self, datapath, priority, match, actions, idle_timeout=15, hard_timeout=0, buffer_id=None):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(
                datapath=datapath, buffer_id=buffer_id, priority=priority,
                match=match, instructions=inst,
                idle_timeout=idle_timeout, hard_timeout=hard_timeout
            )
        else:
            mod = parser.OFPFlowMod(
                datapath=datapath, priority=priority, match=match,
                instructions=inst, idle_timeout=idle_timeout, hard_timeout=hard_timeout
            )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        dp = msg.datapath
        dpid = dp.id
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        # 1. Custom Probe Frame (EtherType 0x88B5) Response
        if eth.ethertype == ETHERTYPE_PROBE:
            self.handle_probe_reply(pkt)
            return

        # 2. Ingress Switch s1 Routing & NAT
        if dpid == 1:
            # Handle ARP for Anycast VIP (10.0.0.100)
            arp_pkt = pkt.get_protocol(arp.arp)
            if arp_pkt and arp_pkt.dst_ip == VIP:
                self.handle_vip_arp(dp, in_port, eth, arp_pkt)
                return

            # Handle TCP Traffic destined to VIP (10.0.0.100:8000)
            ip_pkt = pkt.get_protocol(ipv4.ipv4)
            tcp_pkt = pkt.get_protocol(tcp.tcp)
            if ip_pkt and tcp_pkt and ip_pkt.dst == VIP and tcp_pkt.dst_port == CONTROLLER_PORT:
                self.install_vip_nat_rules(dp, in_port, ip_pkt, tcp_pkt, msg)
                return

        # Default L2 flood for unhandled discovery traffic
        parser = dp.ofproto_parser
        actions = [parser.OFPActionOutput(dp.ofproto.OFPP_FLOOD)]
        data = msg.data if msg.buffer_id == dp.ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port, actions=actions, data=data)
        dp.send_msg(out)

    def handle_vip_arp(self, dp, in_port, eth, arp_pkt):
        parser = dp.ofproto_parser
        reply = packet.Packet()
        reply.add_protocol(ethernet.ethernet(ethertype=ether.ETH_TYPE_ARP, dst=eth.src, src=VIP_MAC))
        reply.add_protocol(arp.arp(
            opcode=arp.ARP_REPLY, src_mac=VIP_MAC, src_ip=VIP,
            dst_mac=arp_pkt.src_mac, dst_ip=arp_pkt.src_ip
        ))
        reply.serialize()
        actions = [parser.OFPActionOutput(in_port)]
        out = parser.OFPPacketOut(datapath=dp, buffer_id=dp.ofproto.OFP_NO_BUFFER, in_port=dp.ofproto.OFPP_CONTROLLER, actions=actions, data=reply.data)
        dp.send_msg(out)

    def install_vip_nat_rules(self, dp, in_port, ip_pkt, tcp_pkt, msg):
        client_ip = ip_pkt.src
        client_mac = msg.match.get('eth_src', '00:00:00:00:00:01')
        client_port = tcp_pkt.src_port

        # Resolve client ID (e.g. 10.0.0.1 -> c1)
        last_octet = client_ip.split('.')[-1]
        client_id = f"c{last_octet}"

        # Choose best server using selector
        srv_id = self.selector.select_best_server(client_id, self.server_telemetry)
        srv = SERVER_POOL[srv_id]
        trunk = srv['trunk_port']

        self.logger.info(f"[Route Decision] Client {client_id} ({client_ip}:{client_port}) -> {srv_id} ({srv['ip']}:8000) via port {trunk}")

        parser = dp.ofproto_parser
        ofproto = dp.ofproto

        # Forward Flow: Client -> VIP translated to Server IP/MAC (idle_timeout=15s)
        match_fwd = parser.OFPMatch(
            in_port=in_port, eth_type=0x0800, ip_proto=6,
            ipv4_src=client_ip, ipv4_dst=VIP,
            tcp_src=client_port, tcp_dst=CONTROLLER_PORT
        )
        actions_fwd = [
            parser.OFPActionSetField(ipv4_dst=srv['ip']),
            parser.OFPActionSetField(eth_dst=srv['mac']),
            parser.OFPActionOutput(trunk)
        ]
        self.add_flow(dp, 100, match_fwd, actions_fwd, idle_timeout=15, hard_timeout=60)

        # Reverse Flow: Server -> Client translated to VIP IP/MAC (idle_timeout=15s)
        match_rev = parser.OFPMatch(
            in_port=trunk, eth_type=0x0800, ip_proto=6,
            ipv4_src=srv['ip'], ipv4_dst=client_ip,
            tcp_src=CONTROLLER_PORT, tcp_dst=client_port
        )
        actions_rev = [
            parser.OFPActionSetField(ipv4_src=VIP),
            parser.OFPActionSetField(eth_src=VIP_MAC),
            parser.OFPActionOutput(in_port)
        ]
        self.add_flow(dp, 100, match_rev, actions_rev, idle_timeout=15, hard_timeout=60)

        # Forward current packet out
        actions_out = [
            parser.OFPActionSetField(ipv4_dst=srv['ip']),
            parser.OFPActionSetField(eth_dst=srv['mac']),
            parser.OFPActionOutput(trunk)
        ]
        data = msg.data if msg.buffer_id == ofproto.OFP_NO_BUFFER else None
        out = parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port, actions=actions_out, data=data)
        dp.send_msg(out)

    def probe_loop(self):
        while True:
            dp = self.datapaths.get(1)
            if dp:
                parser = dp.ofproto_parser
                for srv_id, info in SERVER_POOL.items():
                    self.probe_seq += 1
                    seq = self.probe_seq
                    self.probe_times[seq] = (srv_id, time.time())

                    pkt = packet.Packet()
                    pkt.add_protocol(ethernet.ethernet(
                        ethertype=ETHERTYPE_PROBE,
                        src=VIP_MAC,
                        dst=info['mac']
                    ))
                    payload = f"PROBE:{seq}:{srv_id}".encode()
                    pkt.data = payload
                    pkt.serialize()

                    actions = [parser.OFPActionOutput(info['trunk_port'])]
                    out = parser.OFPPacketOut(
                        datapath=dp, buffer_id=dp.ofproto.OFP_NO_BUFFER,
                        in_port=dp.ofproto.OFPP_CONTROLLER, actions=actions, data=pkt.data
                    )
                    dp.send_msg(out)
            hub.sleep(PROBE_INTERVAL_SEC)

    def handle_probe_reply(self, pkt):
        raw_data = pkt.protocols[-1]
        if isinstance(raw_data, bytes):
            try:
                parts = raw_data.decode().split(':')
                if parts[0] in ['PROBE', 'REPLY']:
                    seq = int(parts[1])
                    if seq in self.probe_times:
                        srv_id, send_t = self.probe_times.pop(seq)
                        rtt = (time.time() - send_t) * 1000.0
                        prev_rtt = self.server_telemetry[srv_id]['rtt_ms']
                        self.server_telemetry[srv_id]['rtt_ms'] = (0.5 * prev_rtt) + (0.5 * rtt)
            except Exception:
                pass

    def port_stats_loop(self):
        while True:
            dp = self.datapaths.get(1)
            if dp:
                parser = dp.ofproto_parser
                req = parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY)
                dp.send_msg(req)
            hub.sleep(STATS_INTERVAL_SEC)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        if ev.msg.datapath.id != 1:
            return
        now = time.time()
        for stat in ev.msg.body:
            port_no = stat.port_no
            for srv_id, info in SERVER_POOL.items():
                if info['trunk_port'] == port_no:
                    t_entry = self.server_telemetry[srv_id]
                    dt = now - t_entry['time_prev']
                    db = stat.tx_bytes - t_entry['bytes_prev']
                    if dt > 0 and t_entry['bytes_prev'] > 0:
                        bps = (db * 8.0) / dt
                        capacity_bps = TRUNK_CAPACITY.get(f"s1-s{info['trunk_port']+1}", 100_000_000)
                        t_entry['utilization'] = min(bps / capacity_bps, 1.0)
                    t_entry['bytes_prev'] = stat.tx_bytes
                    t_entry['time_prev'] = now

    def udp_telemetry_loop(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(('0.0.0.0', TELEMETRY_PORT))
        sock.setblocking(False)
        while True:
            try:
                data, _ = sock.recvfrom(1024)
                parts = data.decode().strip().split()
                if len(parts) >= 4 and parts[0] == 'STATUS':
                    srv_id = parts[1]
                    conns = int(parts[2])
                    if srv_id in self.server_telemetry:
                        self.server_telemetry[srv_id]['active_conns'] = conns
                        self.server_telemetry[srv_id]['last_seen'] = time.time()
            except BlockingIOError:
                pass
            except Exception:
                pass
            hub.sleep(0.5)

    def export_live_routes(self):
        try:
            os.makedirs(os.path.dirname(LIVE_ROUTES_JSON), exist_ok=True)
            temp_path = LIVE_ROUTES_JSON + '.tmp'
            snapshot = {
                'timestamp': time.time(),
                'cdn_mode': self.selector.cdn_mode,
                'profile': self.selector.profile_name,
                'profile_desc': self.selector.profile_desc,
                'weights': {
                    'latency': self.selector.w_rtt,
                    'utilization': self.selector.w_util,
                    'load': self.selector.w_load
                },
                'servers': self.server_telemetry
            }
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot, f, indent=2)
            os.replace(temp_path, LIVE_ROUTES_JSON)
        except Exception:
            pass

    def status_console_loop(self):
        while True:
            hub.sleep(5)
            self.export_live_routes()
            self.logger.info("-------------------- Smart CDN Status (5s Log) --------------------")
            self.logger.info(f"Mode: {self.selector.cdn_mode.upper()} | Profile: {self.selector.profile_name.upper()} ({self.selector.profile_desc})")
            for s, d in self.server_telemetry.items():
                self.logger.info(f"[{s}] Status: {d['status']} | RTT: {d['rtt_ms']:.2f} ms | Util: {d['utilization']*100:5.1f}% | Conns: {d['active_conns']}")
            self.logger.info("-------------------------------------------------------------------")
