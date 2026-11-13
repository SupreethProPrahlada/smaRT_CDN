"""
Smart CDN - Ryu SDN Controller (Sprint 2 Complete System)
Features:
- FR-1: Virtual IP ARP (10.0.0.100) & Two-Way OpenFlow NAT
- FR-2: Real-time Ping Latency Probing (EtherType 0x88B5) + EMA (alpha=0.5)
- FR-3: Switch Port Statistics & Link Utilization Monitoring
- FR-4: Server Heartbeat & Active Load Tracker on Port 9000
- FR-5 & FR-11: 3-Factor Cost Selection Algorithm & Static Baseline Mode
- FR-8: Live State Export (results/live_routes.json) & 5-Second Status Log
Owned by Developer 1 (Supreeth Prahalada) - Sprint 2.
"""

from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet, ethernet, arp, ipv4, tcp, udp, ether_types
from ryu.lib import hub

import sys
import os
import json
import time
import struct

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import (
    VIP_IP, VIP_MAC, SERVERS, CLIENT_IPS, CLIENT_MACS, CONTENT_PORT,
    HB_LISTEN_IP, HB_PORT, PROBE_ETHERTYPE, PROBE_INTERVAL, EMA_ALPHA,
    STATS_INTERVAL, LOG_INTERVAL, DEFAULT_CDN_MODE, LIVE_ROUTES_JSON
)
from controller.paths import (
    DPID_S1, DPID_S2, DPID_S3, DPID_S4, S1_TRUNK_PORTS, SERVER_SWITCH_PORTS, add_flow
)
from controller.selector import ServerSelector


class SmartCDNController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SmartCDNController, self).__init__(*args, **kwargs)
        self.datapaths = {}
        self.selector = ServerSelector(cdn_mode=DEFAULT_CDN_MODE)

        # Telemetry State Store (FR-2, FR-3, FR-4)
        self.server_telemetry = {
            'srv1': {'status': 'UP', 'rtt_ms': 10.0, 'utilization': 0.0, 'active_conns': 0, 'last_seen': time.time(), 'capacity': 100},
            'srv2': {'status': 'UP', 'rtt_ms': 40.0, 'utilization': 0.0, 'active_conns': 0, 'last_seen': time.time(), 'capacity': 50},
            'srv3': {'status': 'UP', 'rtt_ms': 100.0, 'utilization': 0.0, 'active_conns': 0, 'last_seen': time.time(), 'capacity': 10},
        }

        # Port statistics tracking for delta calculation (FR-3)
        # key: (dpid, port_no) -> (tx_bytes, rx_bytes, timestamp)
        self.port_stats_history = {}

        # Timers
        self.last_log_time = time.time()

        # Start non-blocking periodic monitoring threads
        self.monitor_thread = hub.spawn(self._monitor_loop)
        self.probe_thread = hub.spawn(self._probe_loop)

        self.logger.info("=== Smart CDN Controller Initialized (Sprint 2 Telemetry & Selection Active) ===")

    # ==========================================
    # Switch Handshake & Static Flow Rules
    # ==========================================
    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        dpid = datapath.id
        self.datapaths[dpid] = datapath
        parser = datapath.ofproto_parser
        ofproto = datapath.ofproto

        self.logger.info(f"Switch s{dpid} connected. Installing baseline rules.")

        # 1. Table-miss rule
        match_miss = parser.OFPMatch()
        actions_miss = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        add_flow(datapath, priority=0, match=match_miss, actions=actions_miss)

        # 2. Probe loopback on core switches (s2, s3, s4) for FR-2
        if dpid in SERVER_SWITCH_PORTS:
            cfg = SERVER_SWITCH_PORTS[dpid]
            trunk_port = cfg['s1_trunk_port']
            server_port = cfg['server_port']

            # Return latency probes immediately to s1 trunk
            match_probe = parser.OFPMatch(eth_type=PROBE_ETHERTYPE)
            actions_probe = [parser.OFPActionOutput(trunk_port)]
            add_flow(datapath, priority=200, match=match_probe, actions=actions_probe)

            # Bidirectional forwarding between s1 trunk and local server
            m1 = parser.OFPMatch(in_port=server_port)
            a1 = [parser.OFPActionOutput(trunk_port)]
            add_flow(datapath, priority=10, match=m1, actions=a1)

            m2 = parser.OFPMatch(in_port=trunk_port)
            a2 = [parser.OFPActionOutput(server_port)]
            add_flow(datapath, priority=10, match=m2, actions=a2)

        # 3. Direct probe return to controller on s1
        if dpid == DPID_S1:
            match_probe_s1 = parser.OFPMatch(eth_type=PROBE_ETHERTYPE)
            actions_probe_s1 = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
            add_flow(datapath, priority=200, match=match_probe_s1, actions=actions_probe_s1)

    # ==========================================
    # FR-2: Active Latency Probing Loop
    # ==========================================
    def _probe_loop(self):
        """Sends raw Ethernet probe frames (EtherType 0x88B5) every 1.0s (FR-2)."""
        hub.sleep(2.0)
        while True:
            if DPID_S1 in self.datapaths:
                dp = self.datapaths[DPID_S1]
                parser = dp.ofproto_parser
                now = time.time()

                for srv_id, trunk_port in S1_TRUNK_PORTS.items():
                    # Payload: timestamp (double) + server_id (8 bytes)
                    payload = struct.pack('!d8s', now, srv_id.ljust(8).encode('ascii'))
                    pkt = packet.Packet()
                    pkt.add_protocol(ethernet.ethernet(
                        ethertype=PROBE_ETHERTYPE,
                        dst='ff:ff:ff:ff:ff:ff',
                        src=VIP_MAC
                    ))
                    pkt.add_protocol(payload)
                    pkt.serialize()

                    actions = [parser.OFPActionOutput(trunk_port)]
                    out = parser.OFPPacketOut(
                        datapath=dp,
                        buffer_id=dp.ofproto.OFP_NO_BUFFER,
                        in_port=dp.ofproto.OFPP_CONTROLLER,
                        actions=actions,
                        data=pkt.data
                    )
                    dp.send_msg(out)

            hub.sleep(PROBE_INTERVAL)

    def handle_probe_reply(self, data):
        """Calculates RTT and applies EMA smoothing (FR-2)."""
        try:
            # Ethernet header is 14 bytes
            payload = data[14:]
            t_sent, srv_bytes = struct.unpack('!d8s', payload[:16])
            srv_id = srv_bytes.decode('ascii').strip()

            if srv_id in self.server_telemetry:
                rtt_ms = (time.time() - t_sent) * 1000.0
                curr_ema = self.server_telemetry[srv_id]['rtt_ms']
                # EMA: smoothed = alpha * new + (1 - alpha) * old
                smoothed = (EMA_ALPHA * rtt_ms) + ((1.0 - EMA_ALPHA) * curr_ema)
                self.server_telemetry[srv_id]['rtt_ms'] = round(smoothed, 2)
        except Exception:
            pass

    # ==========================================
    # FR-3: Port Statistics Polling Loop
    # ==========================================
    def _monitor_loop(self):
        """Periodically requests port stats and exports live JSON telemetry."""
        while True:
            for dp in list(self.datapaths.values()):
                parser = dp.ofproto_parser
                req = parser.OFPPortStatsRequest(dp, 0, dp.ofproto.OFPP_ANY)
                dp.send_msg(req)

            # Export telemetry to results/live_routes.json (FR-8)
            self.export_live_routes()

            # 5-second controller log (FR-8)
            if time.time() - self.last_log_time >= LOG_INTERVAL:
                self.log_controller_status()
                self.last_log_time = time.time()

            hub.sleep(STATS_INTERVAL)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Computes throughput and link utilization percentage on trunk ports (FR-3)."""
        dpid = ev.msg.datapath.id
        now = time.time()

        if dpid == DPID_S1:
            for stat in ev.msg.body:
                port_no = stat.port_no
                for srv_id, trunk_port in S1_TRUNK_PORTS.items():
                    if port_no == trunk_port:
                        key = (dpid, port_no)
                        tx_bytes = stat.tx_bytes + stat.rx_bytes

                        if key in self.port_stats_history:
                            prev_bytes, prev_time = self.port_stats_history[key]
                            dt = now - prev_time
                            if dt > 0.1:
                                delta_bytes = tx_bytes - prev_bytes
                                mbps = (delta_bytes * 8.0) / (dt * 1_000_000.0)
                                capacity = self.server_telemetry[srv_id]['capacity']
                                util = min(1.0, max(0.0, mbps / capacity))
                                self.server_telemetry[srv_id]['utilization'] = round(util, 3)

                        self.port_stats_history[key] = (tx_bytes, now)

    # ==========================================
    # FR-4: Heartbeat Processing (Port 9000)
    # ==========================================
    def handle_heartbeat_packet(self, payload):
        """Parses STATUS <id> <active_conns> <timestamp> (FR-4)."""
        try:
            text = payload.decode('utf-8', errors='ignore').strip()
            parts = text.split()
            if len(parts) >= 3 and parts[0] == "STATUS":
                srv_id = parts[1]
                active_conns = int(parts[2])
                if srv_id in self.server_telemetry:
                    self.server_telemetry[srv_id]['active_conns'] = active_conns
                    self.server_telemetry[srv_id]['last_seen'] = time.time()
                    self.server_telemetry[srv_id]['status'] = 'UP'
        except Exception:
            pass

    # ==========================================
    # Packet In Routing & NAT
    # ==========================================
    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        pkt_eth = pkt.get_protocol(ethernet.ethernet)
        if not pkt_eth:
            return

        # 1. Handle latency probe packet returns (FR-2)
        if pkt_eth.ethertype == PROBE_ETHERTYPE:
            self.handle_probe_reply(msg.data)
            return

        # 2. Handle ARP (FR-1)
        pkt_arp = pkt.get_protocol(arp.arp)
        if pkt_arp:
            self.handle_arp(datapath, in_port, pkt_eth, pkt_arp)
            return

        # 3. Handle UDP Heartbeat on Port 9000 (FR-4)
        pkt_ip = pkt.get_protocol(ipv4.ipv4)
        pkt_udp = pkt.get_protocol(udp.udp)
        if pkt_ip and pkt_udp and pkt_udp.dst_port == HB_PORT:
            # Extract UDP payload
            udp_payload = msg.data[14 + (pkt_ip.header_length * 4) + 8:]
            self.handle_heartbeat_packet(udp_payload)
            return

        # 4. Handle TCP SYN to VIP:8000 -> Smart Server Selection (FR-5)
        pkt_tcp = pkt.get_protocol(tcp.tcp)
        if dpid == DPID_S1 and pkt_ip and pkt_tcp:
            if pkt_ip.dst == VIP_IP and pkt_tcp.dst_port == CONTENT_PORT:
                # Identify client ID
                client_id = "c1"
                for cid, cip in CLIENT_IPS.items():
                    if cip == pkt_ip.src:
                        client_id = cid
                        break

                # 3-Factor Smart Selection
                selected_server = self.selector.select_server(
                    client_id=client_id,
                    server_telemetry=self.server_telemetry
                )

                self.install_nat_rules(
                    datapath=datapath,
                    client_port=in_port,
                    client_ip=pkt_ip.src,
                    client_mac=pkt_eth.src,
                    server_info=selected_server
                )

                # Send packet out
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

    def handle_arp(self, datapath, in_port, pkt_ethernet, pkt_arp):
        if pkt_arp.opcode != arp.ARP_REQUEST:
            return

        target_ip = pkt_arp.dst_ip
        target_mac = None

        if target_ip == VIP_IP:
            target_mac = VIP_MAC
        elif target_ip == HB_LISTEN_IP:
            target_mac = "00:00:00:00:02:54"
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
            dst_ip=pkt_arp.src_ip
        ))
        pkt_reply.serialize()

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

    def install_nat_rules(self, datapath, client_port, client_ip, client_mac, server_info):
        parser = datapath.ofproto_parser
        server_id = server_info['id']
        server_ip = server_info['ip']
        server_mac = server_info['mac']
        trunk_port = S1_TRUNK_PORTS[server_id]

        self.logger.info(
            f"[Route Decision] Mode={self.selector.cdn_mode} | Client {client_ip} -> Server {server_id} ({server_ip}) | RTT={self.server_telemetry[server_id]['rtt_ms']}ms Util={self.server_telemetry[server_id]['utilization']*100:.1f}% Conns={self.server_telemetry[server_id]['active_conns']}"
        )

        # Forward rule
        m_fwd = parser.OFPMatch(
            in_port=client_port,
            eth_type=ether_types.ETH_TYPE_IP,
            ip_proto=6,
            ipv4_src=client_ip,
            ipv4_dst=VIP_IP,
            tcp_dst=CONTENT_PORT
        )
        a_fwd = [
            parser.OFPActionSetField(ipv4_dst=server_ip),
            parser.OFPActionSetField(eth_dst=server_mac),
            parser.OFPActionOutput(trunk_port)
        ]
        add_flow(datapath, priority=100, match=m_fwd, actions=a_fwd, idle_timeout=60)

        # Reverse rule
        m_rev = parser.OFPMatch(
            in_port=trunk_port,
            eth_type=ether_types.ETH_TYPE_IP,
            ip_proto=6,
            ipv4_src=server_ip,
            ipv4_dst=client_ip,
            tcp_src=CONTENT_PORT
        )
        a_rev = [
            parser.OFPActionSetField(ipv4_src=VIP_IP),
            parser.OFPActionSetField(eth_src=VIP_MAC),
            parser.OFPActionOutput(client_port)
        ]
        add_flow(datapath, priority=100, match=m_rev, actions=a_rev, idle_timeout=60)

    # ==========================================
    # FR-8: Live State Export & Status Log
    # ==========================================
    def export_live_routes(self):
        """Exports state to results/live_routes.json in < 50ms (FR-8, NFR-5)."""
        try:
            os.makedirs(os.path.dirname(LIVE_ROUTES_JSON), exist_ok=True)
            snapshot = {
                'timestamp': time.time(),
                'cdn_mode': self.selector.cdn_mode,
                'servers': self.server_telemetry
            }
            with open(LIVE_ROUTES_JSON, 'w') as f:
                json.dump(snapshot, f, indent=2)
        except Exception:
            pass

    def log_controller_status(self):
        """Prints 5-second summary table to console (FR-8)."""
        self.logger.info("-------------------- Smart CDN State (5s Log) --------------------")
        self.logger.info(f"Mode: {self.selector.cdn_mode.upper()}")
        for s_id, data in self.server_telemetry.items():
            self.logger.info(
                f"  [{s_id}] Status: {data['status']:4s} | RTT: {data['rtt_ms']:6.2f} ms | Util: {data['utilization']*100:5.1f}% | Conns: {data['active_conns']:2d}"
            )
        self.logger.info("-----------------------------------------------------------------")
