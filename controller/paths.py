from ryu.ofproto import ofproto_v1_3
from config.settings import S1_DETOUR_PORT, S5_S1_PORT, S5_S2_PORT, S2_DETOUR_PORT

DPID_S1 = 1
S1_TRUNK_PORTS = {'srv1': 7, 'srv2': 8, 'srv3': 9}
SERVER_SWITCH_PORTS = {2: {'server_port': 1, 's1_trunk_port': 2}, 3: {'server_port': 1, 's1_trunk_port': 2}, 4: {'server_port': 1, 's1_trunk_port': 2}}

S1_CLIENT_PORTS = {f"c{i}": i for i in range(1, 7)}   # clients are linked to s1 first, in order

# Sprint 4: srv1's two paths. Each lists the (dpid, port) pairs whose link state it depends on.
DPID_S2, DPID_S5 = 2, 5
SRV1_PATHS = {
    'primary': {'s1_port': S1_TRUNK_PORTS['srv1'], 's2_port': SERVER_SWITCH_PORTS[2]['s1_trunk_port'],
                'ports': {(DPID_S1, S1_TRUNK_PORTS['srv1']), (DPID_S2, SERVER_SWITCH_PORTS[2]['s1_trunk_port'])}},
    'detour': {'s1_port': S1_DETOUR_PORT, 's2_port': S2_DETOUR_PORT,
               'ports': {(DPID_S1, S1_DETOUR_PORT), (DPID_S5, S5_S1_PORT), (DPID_S5, S5_S2_PORT), (DPID_S2, S2_DETOUR_PORT)}},
}

def add_flow(datapath, priority, match, actions, idle_timeout=0, flags=0):
    ofproto = datapath.ofproto
    inst = [datapath.ofproto_parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
    datapath.send_msg(datapath.ofproto_parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst, idle_timeout=idle_timeout, flags=flags))

def delete_flows(datapath, match, out_port=None, priority=None):
    """Delete rules matching `match` (strictly, at `priority`, when one is given)."""
    ofproto, parser = datapath.ofproto, datapath.ofproto_parser
    datapath.send_msg(parser.OFPFlowMod(
        datapath=datapath, command=ofproto.OFPFC_DELETE if priority is None else ofproto.OFPFC_DELETE_STRICT,
        priority=priority or 0, out_port=ofproto.OFPP_ANY if out_port is None else out_port,
        out_group=ofproto.OFPG_ANY, match=match))
