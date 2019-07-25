from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import arp, ipv4
from ryu.lib import hub
from ryu.lib import mac
import copy, itertools
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
import networkx as nx
import time
import operator

time_to_collect = 10


class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.net = nx.DiGraph()
        self.all_pair_shortest_path = {}
        self.per_C = 0
        self.time_col = {}
        self.weight = {}
        self.dp_list = {}
        self.eth_type = None

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.dp_list[datapath.id] = datapath

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, dp, p, match, actions, idle_timeout=0, hard_timeout=0, table=0):
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]

        mod = parser.OFPFlowMod(datapath=dp, priority=p,
                                idle_timeout=idle_timeout,
                                hard_timeout=hard_timeout,
                                match=match, instructions=inst, table_id=table)
        dp.send_msg(mod)

    def getall_pair_shortest_path(self):
        self.all_pair_shortest_path = {}
        edges = self.net.edges()
        edges = set(edges)
        edges = list(edges)
        nodes = self.net.nodes
        nodes = set(nodes)
        nodes = list(nodes)
        pairs = set(itertools.product(nodes, nodes))

        for pair in pairs:
            src, dst = pair
            try:
                if src != dst:
                    self.all_pair_shortest_path[pair]=nx.shortest_path(self.net,src,dst)
            except:
                pass

    events = [event.EventSwitchEnter,event.EventSwitchLeave,event.EventPortAdd,event.EventLinkAdd,event.EventLinkDelete]

    @set_ev_cls(events)
    def get_topology(self, ev):
        self.net = nx.DiGraph()
        links = copy.copy(get_link(self, None))
        edges_list = []  # extra list item for constructing nx graph
        if len(links) > 0:
            for link in links:
                src = link.src
                dst = link.dst
                edges_list.append((src.dpid, dst.dpid, {'port': src.port_no}))

            self.net.add_edges_from(edges_list)
            self.getall_pair_shortest_path()
            self.WAS()


    def WAS(self):
        start_time=time.time()
        paths=self.all_pair_shortest_path.values()
        for path in paths:
            for sw in path:
                try:
                    self.weight[sw]=self.weight[sw]+1
                except:
                    self.weight[sw]=1
        s=[]
        for path in paths:
            spath=set(path)
            ss=set(s)
            if (spath & ss):
                pass
            else:
                s.append(path[-1])

        print s
        print "Total ",len(s)," switches"
        print "WAS computation time:",(time.time()-start_time)*1000

    def build_flow(self, datapath, priority, flow_info, src_port, dst_port):
        parser = datapath.ofproto_parser
        actions = [parser.OFPActionOutput(dst_port)]

        match = parser.OFPMatch(
            in_port=src_port, eth_type=flow_info[0],
            ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
        self.add_flow(datapath, priority, match, actions, table=0)

    def shortest_forwarding(self, msg, eth_type, ip_src, ip_dst):
        datapath = msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        in_port = msg.match['in_port']
        flow_info = (eth_type, ip_src, ip_dst, in_port)
        back_info = (flow_info[0], flow_info[2], flow_info[1])

        src_sw = int(ip_src.split('.')[3])
        dst_sw = int(ip_dst.split('.')[3])
        curr_sw = datapath.id

        if curr_sw != dst_sw:
            path = self.all_pair_shortest_path[(curr_sw, dst_sw)]
            print path
            next_sw = path[path.index(curr_sw) + 1]
            out_port = self.net[curr_sw][next_sw]['port']
            src_port, dst_port = in_port, out_port
            self.build_flow(datapath, 1, flow_info, src_port, dst_port)
            self.build_flow(datapath, 1, back_info, dst_port, src_port)
            self.send_packet_out(datapath, msg.buffer_id, src_port, dst_port, msg.data)
        else:
            out_port = 1
            src_port, dst_port = in_port, out_port
            self.build_flow(datapath, 1, flow_info, src_port, dst_port)
            self.build_flow(datapath, 1, back_info, dst_port, src_port)
            self.send_packet_out(datapath, msg.buffer_id, src_port, dst_port, msg.data)

        return

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """
        """
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)

        if isinstance(ip_pkt, ipv4.ipv4):
            if ip_pkt.src == '0.0.0.0':
                return
            if len(pkt.get_protocols(ethernet.ethernet)):
                eth_type = pkt.get_protocols(ethernet.ethernet)[0].ethertype
                self.eth_type = eth_type
                self.shortest_forwarding(msg, eth_type, ip_pkt.src, ip_pkt.dst)

    def _build_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        actions = []
        if dst_port:
            actions.append(datapath.ofproto_parser.OFPActionOutput(dst_port))

        msg_data = None
        if buffer_id == datapath.ofproto.OFP_NO_BUFFER:
            if data is None:
                return None
            msg_data = data
        out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath, buffer_id=buffer_id, data=msg_data,
                                                   in_port=src_port, actions=actions)
        return out

    def send_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        out = self._build_packet_out(datapath, buffer_id, src_port, dst_port, data)
        if out:
            datapath.send_msg(out)
