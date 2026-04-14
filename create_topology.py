#!/usr/bin/env python3

import os
import subprocess
from comnetsemu.cli import CLI, spawnXtermDocker
from comnetsemu.net import Containernet, VNFManager
from mininet.node import RemoteController, OVSKernelSwitch
from mininet.log import setLogLevel, info
from mininet.link import TCLink

def create_topology():
    # Only used for auto-testing.
    AUTOTEST_MODE = os.environ.get("COMNETSEMU_AUTOTEST_MODE", 0)
    
    # 1. Initialize ComNetsEmu's network
    net = Containernet(controller=RemoteController, switch=OVSKernelSwitch, link=TCLink)
    mgr = VNFManager(net)

    info('*** Adding controller\n')
    c0 = net.addController('c0', controller=RemoteController, ip='127.0.0.1', port=6653)

    info('*** Adding switches\n')
    sa = net.addSwitch('sa', dpid='000000000000000a')
    core = net.addSwitch('core', dpid='000000000000000c')
    sb = net.addSwitch('sb', dpid='000000000000000b')
    sb1 = net.addSwitch('sb1', dpid='00000000000000b1')
    sb2 = net.addSwitch('sb2', dpid='00000000000000b2')
    sb3 = net.addSwitch('sb3', dpid='00000000000000b3')

    info('*** Adding server hosts\n')
    # Subnet 1: 192.168.0.x
    web_srv = net.addDockerHost(
        "web_srv", dimage="web_server", ip='192.168.0.1/24', defaultRoute='via 192.168.0.254',  docker_args={"hostname": "web_srv"}
    )
    db_srv = net.addDockerHost(
        "db_srv", dimage="db_server", ip='192.168.0.2/24', defaultRoute='via 192.168.0.254', docker_args={"hostname": "db_srv"}
    )

    info('*** Adding client hosts (10.0.1.x subnet)\n')
    # Subnet 2: 10.0.1.x
    h11 = net.addHost('h11', ip='10.0.1.11/24', defaultRoute='via 10.0.1.254')
    h12 = net.addHost('h12', ip='10.0.1.12/24', defaultRoute='via 10.0.1.254')
    h13 = net.addHost('h13', ip='10.0.1.13/24', defaultRoute='via 10.0.1.254')
    h14 = net.addHost('h14', ip='10.0.1.14/24', defaultRoute='via 10.0.1.254')

    info('*** Adding client hosts (10.0.2.x subnet)\n')
    # Subnet 3: 10.0.2.x
    h21 = net.addHost('h21', ip='10.0.2.21/24', defaultRoute='via 10.0.2.254')
    h22 = net.addHost('h22', ip='10.0.2.22/24', defaultRoute='via 10.0.2.254')
    h23 = net.addHost('h23', ip='10.0.2.23/24', defaultRoute='via 10.0.2.254')
    h24 = net.addHost('h24', ip='10.0.2.24/24', defaultRoute='via 10.0.2.254')

    info('*** Adding client hosts (10.0.3.x subnet)\n')
    # Subnet 4: 10.0.3.x
    h31 = net.addHost('h31', ip='10.0.3.31/24', defaultRoute='via 10.0.3.254')
    h32 = net.addHost('h32', ip='10.0.3.32/24', defaultRoute='via 10.0.3.254')
    h33 = net.addHost('h33', ip='10.0.3.33/24', defaultRoute='via 10.0.3.254')
    h34 = net.addHost('h34', ip='10.0.3.34/24', defaultRoute='via 10.0.3.254')

    info('*** Creating links\n')
    # Connect servers to switch a
    net.addLink(web_srv, sa)
    net.addLink(db_srv, sa)

    # Connect hosts to switch b1
    net.addLink(h11, sb1)
    net.addLink(h12, sb1)
    net.addLink(h13, sb1)
    net.addLink(h14, sb1)

    # Connect hosts to switch b2
    net.addLink(h21, sb2)
    net.addLink(h22, sb2)
    net.addLink(h23, sb2)
    net.addLink(h24, sb2)

    # Connect hosts to switch b3
    net.addLink(h31, sb3)
    net.addLink(h32, sb3)
    net.addLink(h33, sb3)
    net.addLink(h34, sb3)

    # Inter-switch links
    net.addLink(sa, core)
    net.addLink(core, sb)
    net.addLink(sb, sb1)
    net.addLink(sb, sb2)
    net.addLink(sb, sb3)

    info('*** Starting network\n')
    net.start()

    info('*** Configuring server host routes\n')
    # In ComNetsEmu, DockerHost interfaces sometimes miss the subnet route;
    # explicitly ensure the connected subnet route and default gateway are set.
    for host, iface, subnet, gw in [
        (web_srv, 'web_srv-eth0', '192.168.0.0/24', '192.168.0.254'),
        (db_srv,  'db_srv-eth0',  '192.168.0.0/24', '192.168.0.254'),
    ]:
        host.cmd(f'ip link set {iface} up')
        host.cmd(f'ip route add {subnet} dev {iface} 2>/dev/null || true')
        host.cmd(f'ip route replace default via {gw}')

    info('*** Starting web server on web_srv\n')
    web_server = mgr.addContainer(
        "web_server", "web_srv", "web_server", "python3 /home/web_server.py", docker_args={}
    )
    # Start DB container using its provided start script (don't try to run python)
    db_server = mgr.addContainer(
        "db_server", "db_srv", "db_server", "/start.sh", docker_args={}
    )

    # Assign IP to the switches
    info('*** Configuring switch IPs\n')
    sb1.cmd('ifconfig sb1 10.0.1.254 netmask 255.255.255.0')
    sb2.cmd('ifconfig sb2 10.0.2.254 netmask 255.255.255.0')
    sb3.cmd('ifconfig sb3 10.0.3.254 netmask 255.255.255.0')
    core.cmd('ifconfig core 8.8.8.8 netmask 255.255.255.0')

    if not AUTOTEST_MODE:
        info('*** Running CLI\n')
        CLI(net)

    info('*** Stopping network\n')
    mgr.removeContainer("web_server")
    mgr.removeContainer("db_server")
    net.stop()
    mgr.stop()

if __name__ == '__main__':
    setLogLevel('info')
    create_topology()
