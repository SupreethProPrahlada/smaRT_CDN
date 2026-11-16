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
    STATS_INTERVAL, LOG_INTERVAL, DEFAULT_CDN_MODE, LIVE_ROUTES_JSON,
    HEARTBEAT_TIMEOUT, TRAFFIC_HOST, DETOUR_LINKS, PATH_PROBE_TIMEOUT, CONGESTION_SHIFT,
    S5_S1_PORT, S5_S2_PORT, S2_DETOUR_PORT, S2_TRAFFIC_PORT,
)
from controller.paths import (
    DPID_S1, DPID_S2, DPID_S5, S1_TRUNK_PORTS, SERVER_SWITCH_PORTS, S1_CLIENT_PORTS, SRV1_PATHS,
    add_flow, delete_flows,
)
from controller.selector import ServerSelector

DETOUR_PROBE_ID = 'srv1d'     # probe tag for srv1's detour path through s5
PATH_CAPACITY = {'primary': SERVERS['srv1']['capacity_mbps'], 'detour': DETOUR_LINKS['s1-s5']['bw']}

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
        self._init_failover_state()
        hub.spawn(self._monitor_loop)
        hub.spawn(self._probe_loop)

    def _init_failover_state(self):
        # Sprint 3: a server silent for HEARTBEAT_TIMEOUT is DOWN (servers get one timeout to start).
        self.last_heartbeat = {s: time.time() for s in self.server_telemetry}
        # Sprint 4: state of srv1's two paths, the path new srv1 flows use, and live flows.
        self.paths = {name: {'status': 'DOWN', 'rtt_ms': None, 'utilization': 0.0, 'background': 0.0,
                             'last_probe': 0.0, 'ports_down': set()} for name in SRV1_PATHS}
        self.srv1_path = 'primary'
        self.flows = {}   # client IP -> {client, client_ip, server, in_port, path, rate_mbps, bytes, stamp}

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        dp = ev.msg.datapath
        dpid = dp.id
        self.datapaths[dpid] = dp
        parser, ofproto = dp.ofproto_parser, dp.ofproto
        # A (re)connecting switch reports later link changes itself; forget old ones.
        for p in self.paths.values():
            p['ports_down'] = {key for key in p['ports_down'] if key[0] != dpid}

        add_flow(dp, priority=0, match=parser.OFPMatch(), actions=[parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)])

        if dpid in SERVER_SWITCH_PORTS:
            cfg = SERVER_SWITCH_PORTS[dpid]
            add_flow(dp, priority=200, match=parser.OFPMatch(eth_type=PROBE_ETHERTYPE), actions=[parser.OFPActionOutput(ofproto.OFPP_IN_PORT)])
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=cfg['server_port']), actions=[parser.OFPActionOutput(cfg['s1_trunk_port'])])
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=cfg['s1_trunk_port']), actions=[parser.OFPActionOutput(cfg['server_port'])])

        if dpid == DPID_S2:
            server_port = SERVER_SWITCH_PORTS[DPID_S2]['server_port']
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=S2_DETOUR_PORT), actions=[parser.OFPActionOutput(server_port)])
            # Match bg's MAC, not its IP, so ARP replies for bg reach it too (not srv1).
            add_flow(dp, priority=20, match=parser.OFPMatch(eth_dst=TRAFFIC_HOST['mac']), actions=[parser.OFPActionOutput(S2_TRAFFIC_PORT)])
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=S2_TRAFFIC_PORT), actions=[parser.OFPActionOutput(SRV1_PATHS['primary']['s2_port'])])
            self._set_srv1_egress(self.srv1_path)

        if dpid == DPID_S5:
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=S5_S1_PORT), actions=[parser.OFPActionOutput(S5_S2_PORT)])
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=S5_S2_PORT), actions=[parser.OFPActionOutput(S5_S1_PORT)])

        if dpid == DPID_S1:
            add_flow(dp, priority=200, match=parser.OFPMatch(eth_type=PROBE_ETHERTYPE), actions=[parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)])
            # Plain IP routes so congestion-generator traffic (bg <-> clients) is delivered.
            for c_id, c_ip in CLIENT_IPS.items():
                add_flow(dp, priority=5, match=parser.OFPMatch(eth_type=0x0800, ipv4_dst=c_ip), actions=[parser.OFPActionOutput(S1_CLIENT_PORTS[c_id])])
            add_flow(dp, priority=5, match=parser.OFPMatch(eth_type=0x0800, ipv4_dst=TRAFFIC_HOST['ip']), actions=[parser.OFPActionOutput(SRV1_PATHS['primary']['s1_port'])])

    def _probe_loop(self):
        hub.sleep(2.0)
        targets = list(S1_TRUNK_PORTS.items()) + [(DETOUR_PROBE_ID, SRV1_PATHS['detour']['s1_port'])]
        while True:
            if DPID_S1 in self.datapaths:
                dp = self.datapaths[DPID_S1]
                parser = dp.ofproto_parser
                now = time.time()
                for srv_id, trunk in targets:
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
            if DPID_S1 in self.datapaths:
                dp = self.datapaths[DPID_S1]
                dp.send_msg(dp.ofproto_parser.OFPFlowStatsRequest(dp, match=dp.ofproto_parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_src=CONTENT_PORT)))
            self.evaluate()
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
            trunks = dict(S1_TRUNK_PORTS, **{DETOUR_PROBE_ID: SRV1_PATHS['detour']['s1_port']})
            for stat in ev.msg.body:
                for srv_id, trunk in trunks.items():
                    if stat.port_no == trunk:
                        key = (dpid, stat.port_no)
                        tot_bytes = stat.tx_bytes + stat.rx_bytes
                        if key in self.port_stats_history:
                            pb, pt = self.port_stats_history[key]
                            dt = now - pt
                            if dt > 0.1:
                                mbps = ((tot_bytes - pb) * 8.0) / (dt * 1_000_000.0)
                                if srv_id == DETOUR_PROBE_ID:
                                    self._update_path_load('detour', mbps)
                                else:
                                    self.server_telemetry[srv_id]['utilization'] = round(min(1.0, max(0.0, mbps / self.server_telemetry[srv_id]['capacity'])), 3)
                                    if srv_id == 'srv1':
                                        self._update_path_load('primary', mbps)
                        self.port_stats_history[key] = (tot_bytes, now)

    def _update_path_load(self, name, mbps):
        """Utilization of a srv1 path, and the share used by traffic other than our CDN flows (FR-6)."""
        cap = PATH_CAPACITY[name]
        on_path = [f for f in self.flows.values() if f['server'] == 'srv1' and f['path'] == name]
        self.paths[name]['utilization'] = round(min(1.0, max(0.0, mbps / cap)), 3)
        # A new flow's rate is known only after two flow-stats samples; until then its
        # traffic would look like someone else's, so keep the previous estimate.
        if all(f['rate_mbps'] is not None for f in on_path):
            ours = sum(f['rate_mbps'] for f in on_path)
            self.paths[name]['background'] = round(min(1.0, max(0.0, (mbps - ours) / cap)), 3)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        """Rate of each CDN flow, from the byte count of its s1 reverse (server -> client) rule."""
        now = time.time()
        for stat in ev.msg.body:
            flow = self.flows.get(stat.match.get('ipv4_dst'))
            if flow is None or stat.match.get('ipv4_src') != SERVERS[flow['server']]['ip']:
                continue
            if flow['bytes'] is not None and stat.byte_count >= flow['bytes'] and now > flow['stamp']:
                flow['rate_mbps'] = (stat.byte_count - flow['bytes']) * 8.0 / ((now - flow['stamp']) * 1_000_000.0)
            flow['bytes'], flow['stamp'] = stat.byte_count, now

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        dp, desc, ofproto = msg.datapath, msg.desc, msg.datapath.ofproto
        key = (dp.id, desc.port_no)
        down = bool(msg.reason == ofproto.OFPPR_DELETE or desc.state & ofproto.OFPPS_LINK_DOWN or desc.config & ofproto.OFPPC_PORT_DOWN)
        for name, cfg in SRV1_PATHS.items():
            if key in cfg['ports']:
                self.logger.info(f"[Path] Port s{dp.id}:{desc.port_no} on srv1 {name} path is {'DOWN' if down else 'UP'}")
                (self.paths[name]['ports_down'].add if down else self.paths[name]['ports_down'].discard)(key)
        self.evaluate()

    def evaluate(self):
        """Apply health changes: server failover (FR-4) and srv1 path choice (FR-6, FR-9, FR-10)."""
        now = time.time()
        for s_id, d in self.server_telemetry.items():
            silent = now - self.last_heartbeat[s_id]
            if d['status'] == 'UP' and silent > HEARTBEAT_TIMEOUT:
                d['status'] = 'DOWN'
                self.logger.info(f"[Failover] {s_id} DOWN: no heartbeat for {silent:.1f}s; flushing its flows")
                self.flush_server(s_id)

        for name, p in self.paths.items():
            up = not p['ports_down'] and now - p['last_probe'] < PATH_PROBE_TIMEOUT
            if up != (p['status'] == 'UP'):
                p['status'] = 'UP' if up else 'DOWN'
                self.logger.info(f"[Path] srv1 {name} path {p['status']}")

        primary, detour = self.paths['primary'], self.paths['detour']
        congested = (detour['status'] == 'UP'
                     and primary['background'] - detour['background'] >= CONGESTION_SHIFT)
        if primary['status'] == 'UP' and not congested:
            want, reason = 'primary', 'primary path healthy'
        elif detour['status'] == 'UP':
            want = 'detour'
            reason = (f"primary congested: other traffic {primary['background']*100:.0f}% vs {detour['background']*100:.0f}%"
                      if primary['status'] == 'UP' else 'primary path DOWN')
        else:
            want, reason = 'primary', 'no working srv1 path'
        changed = want != self.srv1_path
        if changed:
            self.logger.info(f"[Path] srv1 traffic now via {want} ({reason})")
            self.srv1_path = want
            self._set_srv1_egress(want)
        if self.paths[want]['status'] != 'UP':
            return
        staying = 0
        for flow in [f for f in self.flows.values() if f['server'] == 'srv1' and f['path'] != want]:
            # Live flows leave a failed or congested primary, and any path that is DOWN;
            # on recovery they stay on the detour rather than being reordered mid-transfer.
            if want == 'detour' or self.paths[flow['path']]['status'] != 'UP':
                self._move_flow(flow, want, reason if want == 'detour' else f"srv1 {flow['path']} path DOWN")
            else:
                staying += 1
        if changed and staying:
            self.logger.info(f"[Path] {staying} live srv1 flow(s) stay on the detour; new flows use the primary")

    def _set_srv1_egress(self, path):
        """Send srv1's own traffic (heartbeats, unmatched replies) out of the chosen s2 path port."""
        dp = self.datapaths.get(DPID_S2)
        if dp is not None:
            parser = dp.ofproto_parser
            add_flow(dp, priority=10, match=parser.OFPMatch(in_port=SERVER_SWITCH_PORTS[DPID_S2]['server_port']),
                     actions=[parser.OFPActionOutput(SRV1_PATHS[path]['s2_port'])])

    def _s1_port(self, flow):
        return SRV1_PATHS[flow['path']]['s1_port'] if flow['path'] else S1_TRUNK_PORTS[flow['server']]

    def _install_nat(self, flow, dp=None):
        """Bidirectional VIP NAT on s1 for one client, plus srv1's detour reply rule on s2."""
        dp = dp or self.datapaths[DPID_S1]
        parser, ofproto = dp.ofproto_parser, dp.ofproto
        srv, port, client_ip = SERVERS[flow['server']], self._s1_port(flow), flow['client_ip']
        add_flow(dp, priority=100, match=parser.OFPMatch(in_port=flow['in_port'], eth_type=0x0800, ip_proto=6, ipv4_src=client_ip, ipv4_dst=VIP_IP, tcp_dst=CONTENT_PORT), actions=[parser.OFPActionSetField(ipv4_dst=srv['ip']), parser.OFPActionSetField(eth_dst=srv['mac']), parser.OFPActionOutput(port)], idle_timeout=60, flags=ofproto.OFPFF_SEND_FLOW_REM)
        add_flow(dp, priority=100, match=parser.OFPMatch(in_port=port, eth_type=0x0800, ip_proto=6, ipv4_src=srv['ip'], ipv4_dst=client_ip, tcp_src=CONTENT_PORT), actions=[parser.OFPActionSetField(ipv4_src=VIP_IP), parser.OFPActionSetField(eth_src=VIP_MAC), parser.OFPActionOutput(flow['in_port'])], idle_timeout=60)
        s2 = self.datapaths.get(DPID_S2)
        if s2 is not None and flow['server'] == 'srv1':
            match = s2.ofproto_parser.OFPMatch(eth_type=0x0800, ipv4_src=srv['ip'], ipv4_dst=client_ip)
            if flow['path'] == 'detour':
                add_flow(s2, priority=100, match=match, actions=[s2.ofproto_parser.OFPActionOutput(S2_DETOUR_PORT)], idle_timeout=60)
            else:
                delete_flows(s2, match, priority=100)

    def _move_flow(self, flow, path, reason):
        """Shift a live srv1 connection to another path; the TCP endpoints stay the same."""
        dp = self.datapaths[DPID_S1]
        old_port = self._s1_port(flow)
        old = flow['path']
        flow['path'] = path
        self._install_nat(flow)
        srv_ip = SERVERS[flow['server']]['ip']
        delete_flows(dp, dp.ofproto_parser.OFPMatch(in_port=old_port, eth_type=0x0800, ip_proto=6, ipv4_src=srv_ip, ipv4_dst=flow['client_ip'], tcp_src=CONTENT_PORT), priority=100)
        self.logger.info(f"[Path] Moved {flow['client']} ({flow['client_ip']}) from srv1 {old} to {path} ({reason})")

    def flush_server(self, s_id):
        """FR-4: delete a failed server's NAT rules so its clients are steered again on reconnect."""
        srv = SERVERS[s_id]
        dp = self.datapaths.get(DPID_S1)
        if dp is not None:
            parser = dp.ofproto_parser
            ports = [S1_TRUNK_PORTS[s_id]] + ([SRV1_PATHS['detour']['s1_port']] if s_id == 'srv1' else [])
            for port in ports:
                delete_flows(dp, parser.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_dst=VIP_IP, tcp_dst=CONTENT_PORT), out_port=port)
            delete_flows(dp, parser.OFPMatch(eth_type=0x0800, ip_proto=6, ipv4_src=srv['ip'], tcp_src=CONTENT_PORT))
        s2 = self.datapaths.get(DPID_S2)
        if s2 is not None and s_id == 'srv1':
            delete_flows(s2, s2.ofproto_parser.OFPMatch(eth_type=0x0800, ipv4_src=srv['ip']))
        for client_ip in [ip for ip, f in self.flows.items() if f['server'] == s_id]:
            del self.flows[client_ip]

    @set_ev_cls(ofp_event.EventOFPFlowRemoved, MAIN_DISPATCHER)
    def flow_removed_handler(self, ev):
        msg = ev.msg
        if msg.reason == msg.datapath.ofproto.OFPRR_IDLE_TIMEOUT and msg.match.get('ipv4_dst') == VIP_IP:
            self.flows.pop(msg.match.get('ipv4_src'), None)

    def selection_telemetry(self):
        """Server telemetry as the selector should see it: srv1 measured on the path it would use."""
        tel = {s: dict(d) for s, d in self.server_telemetry.items()}
        p = self.paths[self.srv1_path]
        if p['rtt_ms'] is not None and p['status'] == 'UP':
            tel['srv1']['rtt_ms'], tel['srv1']['utilization'] = p['rtt_ms'], p['utilization']
        return tel

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
                rtt = (time.time() - t_sent) * 1000.0
                if s_id in self.server_telemetry:
                    old = self.server_telemetry[s_id]['rtt_ms']
                    self.server_telemetry[s_id]['rtt_ms'] = round((EMA_ALPHA * rtt) + ((1.0 - EMA_ALPHA) * old), 2)
                path = 'primary' if s_id == 'srv1' else 'detour' if s_id == DETOUR_PROBE_ID else None
                if path:
                    p = self.paths[path]
                    p['rtt_ms'] = round(rtt if p['rtt_ms'] is None else (EMA_ALPHA * rtt) + ((1.0 - EMA_ALPHA) * p['rtt_ms']), 2)
                    p['last_probe'] = time.time()
            except Exception: pass
            return

        pkt_arp = pkt.get_protocol(arp.arp)
        if pkt_arp and pkt_arp.opcode == arp.ARP_REQUEST:
            t_ip, t_mac = pkt_arp.dst_ip, None
            if t_ip == VIP_IP: t_mac = VIP_MAC
            elif t_ip == HB_LISTEN_IP: t_mac = "00:00:00:00:02:54"
            elif t_ip == TRAFFIC_HOST['ip']: t_mac = TRAFFIC_HOST['mac']
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
                if (
                    len(p) >= 3
                    and p[0] == "STATUS"
                    and p[1] in self.server_telemetry
                    and SERVERS.get(p[1], {}).get('ip') == pkt_ip.src
                ):
                    self.server_telemetry[p[1]]['active_conns'] = int(p[2])
                    self.last_heartbeat[p[1]] = time.time()
                    if self.server_telemetry[p[1]]['status'] != 'UP':
                        self.logger.info(f"[Failover] {p[1]} UP: heartbeat received again")
                    self.server_telemetry[p[1]]['status'] = 'UP'
            except Exception: pass
            return

        pkt_tcp = pkt.get_protocol(tcp.tcp)
        if dpid == DPID_S1 and pkt_ip and pkt_tcp and pkt_ip.dst == VIP_IP and pkt_tcp.dst_port == CONTENT_PORT:
            cid = next((k for k, v in CLIENT_IPS.items() if v == pkt_ip.src), "c1")
            srv = self.selector.select_server(cid, self.selection_telemetry())
            flow = {'client': cid, 'client_ip': pkt_ip.src, 'server': srv['id'], 'in_port': in_port,
                    'path': self.srv1_path if srv['id'] == 'srv1' else None, 'rate_mbps': None, 'bytes': None, 'stamp': 0.0}
            self.flows[pkt_ip.src] = flow
            port = self._s1_port(flow)
            parser = dp.ofproto_parser
            via = f" via {flow['path']}" if flow['path'] else ""
            self.logger.info(f"[Route Decision] Mode={self.selector.cdn_mode} | Client {pkt_ip.src} -> {srv['id']}{via} (RTT={self.server_telemetry[srv['id']]['rtt_ms']}ms Util={self.server_telemetry[srv['id']]['utilization']*100:.1f}%)")

            self._install_nat(flow, dp)

            dp.send_msg(parser.OFPPacketOut(datapath=dp, buffer_id=msg.buffer_id, in_port=in_port, actions=[parser.OFPActionSetField(ipv4_dst=srv['ip']), parser.OFPActionSetField(eth_dst=srv['mac']), parser.OFPActionOutput(port)], data=msg.data if msg.buffer_id == dp.ofproto.OFP_NO_BUFFER else None))

    def export_live_routes(self):
        tmp_path = f"{LIVE_ROUTES_JSON}.tmp"
        try:
            os.makedirs(os.path.dirname(LIVE_ROUTES_JSON), exist_ok=True)
            paths = {name: {k: v for k, v in p.items() if k in ('status', 'rtt_ms', 'utilization', 'background')}
                     for name, p in self.paths.items()}
            flows = [{'client': f['client'], 'server': f['server'], 'path': f['path'] or 'trunk',
                      'rate_mbps': round(f['rate_mbps'] or 0.0, 2)} for f in self.flows.values()]
            with open(tmp_path, 'w', encoding='utf-8') as f:
                json.dump({'timestamp': time.time(), 'cdn_mode': self.selector.cdn_mode, 'servers': self.server_telemetry,
                           'srv1_path': self.srv1_path, 'paths': paths, 'flows': flows}, f, indent=2)
            os.replace(tmp_path, LIVE_ROUTES_JSON)
        except Exception as exc:
            self.logger.warning(f"[Export] Failed to write {LIVE_ROUTES_JSON}: {exc}")

    def log_controller_status(self):
        self.logger.info("-------------------- Smart CDN State (5s Log) --------------------")
        self.logger.info(f"Mode: {self.selector.cdn_mode.upper()}")
        for s, d in self.server_telemetry.items():
            self.logger.info(f"  [{s}] Status: {d['status']} | RTT: {d['rtt_ms']:6.2f} ms | Util: {d['utilization']*100:5.1f}% | Conns: {d['active_conns']}")
        for name, p in self.paths.items():
            rtt = '   -  ' if p['rtt_ms'] is None else f"{p['rtt_ms']:6.2f}"
            mark = '*' if name == self.srv1_path else ' '
            self.logger.info(f" {mark}[srv1 {name}] Status: {p['status']} | RTT: {rtt} ms | Util: {p['utilization']*100:5.1f}% | Other traffic: {p['background']*100:5.1f}%")
        self.logger.info("-----------------------------------------------------------------")
