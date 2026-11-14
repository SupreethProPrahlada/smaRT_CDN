from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel
import sys, os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from config.settings import CLIENT_IPS, CLIENT_MACS, SERVERS, OFP_CONTROLLER_PORT

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

if __name__ == '__main__':
    setLogLevel('info')
    topo = SmartCDNTopo()
    net = Mininet(topo=topo, switch=OVSSwitch, link=TCLink, controller=None)
    net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=OFP_CONTROLLER_PORT)
    net.start()
    CLI(net)
    net.stop()
