from ryu.ofproto import ofproto_v1_3

DPID_S1 = 1
S1_TRUNK_PORTS = {'srv1': 7, 'srv2': 8, 'srv3': 9}
SERVER_SWITCH_PORTS = {2: {'server_port': 1, 's1_trunk_port': 2}, 3: {'server_port': 1, 's1_trunk_port': 2}, 4: {'server_port': 1, 's1_trunk_port': 2}}

def add_flow(datapath, priority, match, actions, idle_timeout=0):
    ofproto = datapath.ofproto
    inst = [datapath.ofproto_parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
    datapath.send_msg(datapath.ofproto_parser.OFPFlowMod(datapath=datapath, priority=priority, match=match, instructions=inst, idle_timeout=idle_timeout))
