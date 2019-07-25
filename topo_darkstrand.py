
from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import CPULimitedHost
from mininet.link import TCLink
from mininet.node import Controller, RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel
import itertools
from multiprocessing import Process
import random

class CompleteGraphTopo(Topo):
    def build(self):
        edges = [(0,1), (0,3), (1,25), (1,13), (2,19), (2,6), (3,6), (4,5), (4,7), (5,8), (6,7), (8,9), (9,16), (10,17),
                 (10,11), (11,12), (12,13), (12,15), (14,25), (14,26), (15,16), (16,17), (18,27), (18,22), (19,27),
                 (19,26), (20,21), (20,23), (21,22), (23,24), (24,25)]
        total_node = 28
        for node in range(total_node):
            switch = self.addSwitch('s%s'%(node+1))
            host = self.addHost('h%s'%(node+1))
            self.addLink( host, switch)
        for (sw1, sw2) in edges:
            sw1='s%s'%(sw1+1)
            sw2='s%s'%(sw2+1)
            self.addLink(sw1,sw2)

    def enable_BFD(self,net):
        """
        Bidirectional Forwarding Detection(BFD) is a network protocol used to detect link failure between two forwarding elements.
        """
        switches=net.switches
        for switch in switches:
            self.ofp_version(switch, ['OpenFlow13'])
            intfs=switch.nameToIntf.keys()[1:]
            for intf in intfs:
                switch.cmd('ovs-vsctl set interface "%s" bfd:enable=true'%intf)

    def ofp_version(self,switch, protocols):
        """
        sets openFlow version for each switch from mininet.
        """
        protocols_str = ','.join(protocols)
        command = 'ovs-vsctl set Bridge %s protocols=%s' % (switch, protocols)
        switch.cmd(command.split(' '))

def doiperf(src,dst):
    port,time=5001,5
    dst.cmd('sudo pkill iperf')
    dst.cmd(('iperf -s -p %s -u -D')%(port))

    try:
        output=src.cmd(('iperf -c %s -p %s -u -t %d')%(dst.IP(),port,time))
        print "Thread: %s,%s" % (src,dst)
        print output
    except AssertionError:
       pass


def myiperf(self,line):
    net = self.mn
    trhread = []
    src_list = [19, 21, 22, 23, 24]
    dst_list = [9, 10, 11, 17 ,18]
    for i in range(10):
        src = random.choice(src_list)
        dst = random.choice(dst_list)
        src = 'h%s' % (src)
        dst = 'h%s' % (dst)
        src = net.getNodeByName(src)
        dst = net.getNodeByName(dst)
        p = Process(target=doiperf, args=(src, dst))
        trhread.append(p)
    for t in trhread:
        t.start()
    for t in trhread:
        t.join()

def dopacket_delivery(src,dst):
    port,time,startLoad=5001,5,1
    dst.cmd('sudo pkill iperf')
    dst.cmd(('iperf -s -p %s -u -D')%(port))

    try:
        output=src.cmd(('iperf -c %s -p %s -u -t %d -b %sM')%(dst.IP(),port,time,startLoad))
        print "Thread: %s,%s" % (src,dst)
        print output
    except AssertionError:
       pass


def mypacket_delivery(self,line):
    net = self.mn
    trhread = []
    src_list = [19, 21, 22, 23, 24]
    dst_list = [9, 10, 11, 17 ,18]
    for i in range(10):
        src = random.choice(src_list)
        dst = random.choice(dst_list)
        src = 'h%s' % (src)
        dst = 'h%s' % (dst)
        src = net.getNodeByName(src)
        dst = net.getNodeByName(dst)
        p = Process(target=dopacket_delivery, args=(src, dst))
        trhread.append(p)
    for t in trhread:
        t.start()
    for t in trhread:
        t.join()


def runner():
    topo = CompleteGraphTopo()
    c = RemoteController('c','127.0.0.1',6633)
    net = Mininet( topo=topo,controller=c,waitConnected=True,autoSetMacs=True,autoStaticArp=True)
    
    topo.enable_BFD(net)
    net.start()
    CLI.do_mypacket_delivery = mypacket_delivery
    CLI.do_myiperf = myiperf
    CLI(net)
    net.stop()
if __name__ == '__main__':
    setLogLevel('info')
    runner()
