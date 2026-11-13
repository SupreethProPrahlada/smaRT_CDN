"""
Smart CDN - Mininet Topology Definition
Builds the 4-switch, 6-client, 3-server network with traffic shaping.
Owned by Developer 1 (Supreeth Prahalada) - Sprint 1.
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info

import sys
import os

# Add root folder to sys.path so config is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import CLIENT_IPS, CLIENT_MACS, SERVERS, OFP_CONTROLLER_PORT


class SmartCDNTopo(Topo):
    """
    Smart CDN Topology:
    - Ingress Switch s1 connects clients c1..c6
    - Core/Egress Switches:
      - s2 connects srv1 (Primary: 100M / 5ms)
      - s3 connects srv2 (Secondary: 50M / 20ms)
      - s4 connects srv3 (Backup: 10M / 50ms)
    """

    def build(self):
        info("*** Adding OpenFlow 1.3 Switches\n")
        # protocols='OpenFlow13' ensures OVS talks OpenFlow 1.3 to Ryu
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        s2 = self.addSwitch('s2', protocols='OpenFlow13')
        s3 = self.addSwitch('s3', protocols='OpenFlow13')
        s4 = self.addSwitch('s4', protocols='OpenFlow13')

        info("*** Adding Clients (c1 to c6)\n")
        clients = {}
        for c_id, ip in CLIENT_IPS.items():
            mac = CLIENT_MACS[c_id]
            clients[c_id] = self.addHost(c_id, ip=f"{ip}/24", mac=mac)
            # High-speed local access link (100 Mbps, 1 ms)
            self.addLink(clients[c_id], s1, cls=TCLink, bw=100, delay='1ms')

        info("*** Adding Content Servers (srv1 to srv3)\n")
        servers = {}
        # srv1 on s2
        srv1_info = SERVERS['srv1']
        servers['srv1'] = self.addHost('srv1', ip=f"{srv1_info['ip']}/24", mac=srv1_info['mac'])
        self.addLink(servers['srv1'], s2, cls=TCLink, bw=100, delay='1ms')

        # srv2 on s3
        srv2_info = SERVERS['srv2']
        servers['srv2'] = self.addHost('srv2', ip=f"{srv2_info['ip']}/24", mac=srv2_info['mac'])
        self.addLink(servers['srv2'], s3, cls=TCLink, bw=100, delay='1ms')

        # srv3 on s4
        srv3_info = SERVERS['srv3']
        servers['srv3'] = self.addHost('srv3', ip=f"{srv3_info['ip']}/24", mac=srv3_info['mac'])
        self.addLink(servers['srv3'], s4, cls=TCLink, bw=100, delay='1ms')

        info("*** Adding Trunk Links between Switches with Traffic Control\n")
        # Primary link: s1 - s2 (100M, 5ms)
        self.addLink(s1, s2, cls=TCLink, bw=100, delay='5ms')

        # Secondary link: s1 - s3 (50M, 20ms)
        self.addLink(s1, s3, cls=TCLink, bw=50, delay='20ms')

        # Backup link: s1 - s4 (10M, 50ms)
        self.addLink(s1, s4, cls=TCLink, bw=10, delay='50ms')


def run_topology():
    """Start Mininet with SmartCDNTopo and connect to Ryu controller."""
    topo = SmartCDNTopo()
    net = Mininet(
        topo=topo,
        switch=OVSSwitch,
        link=TCLink,
        controller=None,
        autoSetMacs=False,
        autoStaticArp=False
    )
    # Connect to local Ryu controller on port 6653
    c0 = net.addController(
        'c0',
        controller=RemoteController,
        ip='127.0.0.1',
        port=OFP_CONTROLLER_PORT
    )

    info("*** Starting Network\n")
    net.start()

    info("*** Running Mininet CLI (type 'exit' to quit)\n")
    CLI(net)

    info("*** Stopping Network\n")
    net.stop()


topos = {'smart_cdn': (lambda: SmartCDNTopo())}

if __name__ == '__main__':
    setLogLevel('info')
    run_topology()
