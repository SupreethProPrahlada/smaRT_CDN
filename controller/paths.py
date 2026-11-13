"""
Smart CDN - Path & Flow Routing Helpers
OpenFlow 1.3 FlowMod utilities and switch topology mapping.
Owned by Developer 1 (Supreeth Prahalada) - Sprint 1.
"""

from ryu.ofproto import ofproto_v1_3

# Switch DPIDs in Mininet
DPID_S1 = 1  # Ingress Aggregation Switch
DPID_S2 = 2  # Primary Path Switch (srv1)
DPID_S3 = 3  # Secondary Path Switch (srv2)
DPID_S4 = 4  # Backup Path Switch (srv3)

# Switch Port Definitions
# s1 ports: 1-6 connect c1-c6; 7->s2, 8->s3, 9->s4
S1_TRUNK_PORTS = {
    'srv1': 7,  # Trunk to s2 (Primary)
    'srv2': 8,  # Trunk to s3 (Secondary)
    'srv3': 9,  # Trunk to s4 (Backup)
}

# Core switches (s2, s3, s4) ports:
# Port 1 connects the attached server, Port 2 connects trunk link to s1
SERVER_SWITCH_PORTS = {
    DPID_S2: {'server_port': 1, 's1_trunk_port': 2},
    DPID_S3: {'server_port': 1, 's1_trunk_port': 2},
    DPID_S4: {'server_port': 1, 's1_trunk_port': 2},
}


def add_flow(datapath, priority, match, actions, buffer_id=None, idle_timeout=0, hard_timeout=0):
    """Installs an OpenFlow 1.3 flow rule into the switch flow table."""
    ofproto = datapath.ofproto
    parser = datapath.ofproto_parser

    inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
    if buffer_id:
        mod = parser.OFPFlowMod(
            datapath=datapath,
            buffer_id=buffer_id,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
    else:
        mod = parser.OFPFlowMod(
            datapath=datapath,
            priority=priority,
            match=match,
            instructions=inst,
            idle_timeout=idle_timeout,
            hard_timeout=hard_timeout
        )
    datapath.send_msg(mod)
