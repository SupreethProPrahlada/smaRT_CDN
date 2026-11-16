from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import (
    CLIENT_IPS, CLIENT_MACS, SERVERS, OFP_CONTROLLER_PORT, DETOUR_LINKS, TRAFFIC_HOST,
    S1_DETOUR_PORT, S5_S1_PORT, S5_S2_PORT, S2_DETOUR_PORT, S2_TRAFFIC_PORT,
)

class SmartCDNTopo(Topo):
    def build(self):
        s1 = self.addSwitch('s1', protocols='OpenFlow13')
        s2 = self.addSwitch('s2', protocols='OpenFlow13')
        s3 = self.addSwitch('s3', protocols='OpenFlow13')
        s4 = self.addSwitch('s4', protocols='OpenFlow13')

        for c_id, ip in CLIENT_IPS.items():
            self.addLink(self.addHost(c_id, ip=f"{ip}/24", mac=CLIENT_MACS[c_id]), s1, cls=TCLink, bw=100, delay='1ms')

        for s_id, s_info in SERVERS.items():
            sw = {'srv1': s2, 'srv2': s3, 'srv3': s4}[s_id]
            self.addLink(self.addHost(s_id, ip=f"{s_info['ip']}/24", mac=s_info['mac']), sw, cls=TCLink, bw=100, delay='1ms')

        self.addLink(s1, s2, cls=TCLink, bw=100, delay='5ms')   # Primary
        self.addLink(s1, s3, cls=TCLink, bw=50, delay='20ms')   # Secondary
        self.addLink(s1, s4, cls=TCLink, bw=10, delay='50ms')   # Backup

        # Sprint 4 (Developer 2): detour switch s5 gives srv1 a second path, s1 -> s5 -> s2.
        s5 = self.addSwitch('s5', protocols='OpenFlow13')
        d1, d2 = DETOUR_LINKS['s1-s5'], DETOUR_LINKS['s5-s2']
        self.addLink(s1, s5, port1=S1_DETOUR_PORT, port2=S5_S1_PORT, cls=TCLink, bw=d1['bw'], delay=f"{d1['delay_ms']}ms")
        self.addLink(s5, s2, port1=S5_S2_PORT, port2=S2_DETOUR_PORT, cls=TCLink, bw=d2['bw'], delay=f"{d2['delay_ms']}ms")
        # Congestion-generator host behind s2: its traffic loads the primary s1-s2 trunk.
        bg = self.addHost(TRAFFIC_HOST['id'], ip=f"{TRAFFIC_HOST['ip']}/24", mac=TRAFFIC_HOST['mac'])
        self.addLink(bg, s2, port2=S2_TRAFFIC_PORT, cls=TCLink, bw=100, delay='1ms')

if __name__ == '__main__':
    setLogLevel('info')
    topo = SmartCDNTopo()
    net = Mininet(topo=topo, switch=OVSSwitch, link=TCLink, controller=None)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=OFP_CONTROLLER_PORT)
    net.start()
    CLI(net)
    net.stop()
