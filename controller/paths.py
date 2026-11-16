from ryu.ofproto import ofproto_v1_3

DPID_S1 = 1
DPID_S2 = 2
DPID_S5 = 5
S1_TRUNK_PORTS = {'srv1': 7, 'srv2': 8, 'srv3': 9}
S1_DETOUR_PORT = 10
S1_LOADSRC_PORT = 11
S5_S1_PORT = 1
S5_S2_PORT = 2
S2_S5_PORT = 3
SERVER_SWITCH_PORTS = {2: {'server_port': 1, 's1_trunk_port': 2}, 3: {'server_port': 1, 's1_trunk_port': 2}, 4: {'server_port': 1, 's1_trunk_port': 2}}


def should_use_detour(rtt_ms, baseline_rtt_ms, direct_link_up, threshold_ms=50.0):
    return not direct_link_up or rtt_ms - baseline_rtt_ms >= threshold_ms

def add_flow(datapath, priority, match, actions, idle_timeout=0):
    ofproto = datapath.ofproto
    inst = [datapath.ofproto_parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
    datapath.send_msg(datapath.ofproto_parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst, idle_timeout=idle_timeout))


def delete_flow(datapath, match):
    """Delete every flow matching ``match`` on ``datapath`` (FR-6/FR-9/FR-10)."""
    ofproto = datapath.ofproto
    datapath.send_msg(datapath.ofproto_parser.OFPFlowMod(
        datapath=datapath,
        command=ofproto.OFPFC_DELETE,
        out_port=ofproto.OFPP_ANY,
        out_group=ofproto.OFPG_ANY,
        match=match,
        instructions=[],
    ))
