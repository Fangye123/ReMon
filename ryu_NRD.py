from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import arp,ipv4, lldp
from ryu.lib import hub
from ryu.lib import mac
import copy,itertools
from ryu.topology import event, switches
from ryu.topology.api import get_switch, get_link
import networkx as nx
import time
import operator

time_to_collect=10
class SimpleSwitch13(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super(SimpleSwitch13, self).__init__(*args, **kwargs)
        self.net = nx.DiGraph()
        self.all_pair_shortest_path = {}
        self.per_C = 0
        self.time_col = {}
        self.monitoring_list = []
        self.weight = {}
        self.dp_list = {}
        self.group_id = 0
        self.eth_type = None
        self.priority = 100

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        self.dp_list[datapath.id] = datapath

        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER,ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, 0, match, actions)

    def add_flow(self, dp, p, match, actions, idle_timeout=0, hard_timeout=0,table=0):
        ofproto = dp.ofproto
        parser = dp.ofproto_parser

        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS,
                                             actions)]

        mod = parser.OFPFlowMod(datapath=dp, priority=p,
                                idle_timeout=idle_timeout,
                                hard_timeout=hard_timeout,
                                match=match, instructions=inst,table_id=table)
        dp.send_msg(mod)

    def get_shortestPath(self, edges, src, dst):
        path = nx.shortest_path(self.net, src, dst)
        edges_used = self.pairwise(path)
        edges_remain = set(edges) - set(edges_used)
        edges_remain = list(edges_remain)
        newgraph = nx.DiGraph()
        newgraph.add_edges_from(edges_remain)
        path2 = nx.shortest_path(newgraph, src, dst)  # compute second shortest path
        return path, path2

    def pairwise(self, l):  # compute pairwise by given a path list
        result = []
        for i in range(len(l)):
            start = l[i]
            end = l[i + 1]
            result.append((start, end))
            if end == l[-1]:
                break
        return result

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
                    path, path2 = self.get_shortestPath(edges, src, dst)
                    anchor_node = []
                    for sw in path:
                        if len(list(set(nx.all_neighbors(self.net, sw)))) > 2:
                            anchor_node.append(sw)
                    self.all_pair_shortest_path[pair] = [path, path2, anchor_node]
            except:
                pass

    events = [event.EventSwitchEnter,event.EventSwitchLeave,event.EventPortAdd,event.EventLinkAdd]
    
    @set_ev_cls(events)
    def get_topology(self, ev):
        self.net=nx.DiGraph()
        links = copy.copy(get_link(self, None))
        edges_list=[]  # extra list item for constructing nx graph
        if len(links)>0:
            for link in links:
                src = link.src
                dst = link.dst
                edges_list.append((src.dpid,dst.dpid,{'port':src.port_no}))
 
            self.net.add_edges_from(edges_list)  
            self.getall_pair_shortest_path()
            self.WAS()

    def WAS(self):
        start_time = time.time()
        paths = self.all_pair_shortest_path.values()
        for path in paths:
            for sw in path[0]:
                try:
                    self.weight[sw] = self.weight[sw] + 1
                except:
                    self.weight[sw] = 1
        self.monitoring_list = []
        for path in paths:
            path = path[0]
            spath = set(path)
            ss = set(self.monitoring_list)
            if (spath & ss):
                pass
            else:
                self.monitoring_list.append(path[-1])
        print self.monitoring_list
        print "Total ", len(self.monitoring_list), " switches"
        print "WAS computation time:", (time.time() - start_time) * 1000

    @set_ev_cls(event.EventLinkDelete,MAIN_DISPATCHER)
    def link_fail_handler(self,ev):
        link=ev.link
        if "DOWN" not in str(link.src):
            return
        h1=link.src.dpid
        h2=link.dst.dpid
        self.AAR(h1,h2)

    def AAR(self,h1,h2):
        count=0
        count_flow=0
        start_time=time.time()
        net=nx.DiGraph()
        print "----------------------------------"
        print "Failure link:(",h1,",",h2,")"

        links = copy.copy(get_link(self, None))
        edges_list=[]  # extra list item for constructing nx graph
        if len(links)>0:
            for link in links:
                src = link.src
                dst = link.dst
                edges_list.append((src.dpid,dst.dpid,{'port':src.port_no}))
        net.add_edges_from(edges_list)

        for key in self.all_pair_shortest_path.keys():
            path = self.all_pair_shortest_path[key][0]
            back_path = self.all_pair_shortest_path[key][1]
            anchor_nodes = self.all_pair_shortest_path[key][2]
            src, dst = key
            
            if h1 in path and h2 in path:
                count_flow=count_flow+1
                index=path.index(h1)
                index2=path.index(h2)
                if index != index2-1 and index != index2+1:
                    continue
                print "Original path:",path
                if index2<index:
                    index=index2
                new_path=None
                while index!=-1:
                    if path[index] in anchor_nodes:
                        count+=1
                        try:
                            new_path=nx.shortest_path(net,path[index],path[-1])
                            for sw in path[:index]:
                                if sw in new_path:
                                    continue
                            break
                        except:
                            log="do nothing"
                    index=index-1
                old_path=path[:index]
                if new_path==None:
                    try:
                        count+=1
                        new_path=nx.shortest_path(net,path[0],path[-1])
                        old_path=[]
                    except:
                        print "no alternative path found"
                        continue
                print "change to:",old_path,"+",new_path

                path=old_path
                path.extend(new_path)

                if path == back_path:
                    print 'new path is already existed in backup path'
                else:
                    # update monitoring list
                    spath=set(path)
                    ss=set(self.monitoring_list)
                    if (spath & ss):
                        pass
                    else:
                        self.monitoring_list.append(path[-1])
                    # update anchor nodes
                    anchor_nodes = []
                    for sw in path:
                        if len(list(set(nx.all_neighbors(net, sw)))) > 2:
                            anchor_nodes.append(sw)
                    self.all_pair_shortest_path[key][0] = path
                    self.all_pair_shortest_path[key][2] = anchor_nodes

                    # add new flow entry for anchor node
                    datapath = self.dp_list[new_path[0]]
                    out_port = self.net[new_path[0]][new_path[1]]['port']
                    ofp_parser = datapath.ofproto_parser
                    actions = [ofp_parser.OFPActionOutput(out_port)]
                    src, dst = key
                    src = "10.0.0.%s" % (str(src))
                    dst = "10.0.0.%s" % (str(dst))
                    match = ofp_parser.OFPMatch(eth_type=self.eth_type, ipv4_dst=dst, ipv4_src=src)
                    self.add_flow(datapath, self.priority, match, actions, table=0)
                    self.priority = self.priority+1

        print "Compute time:", (time.time()-start_time)*1000, "ms"
        print "Number of computation:",count
        print "Number of flow change:",count_flow
        print "-----------------------------------\n"
        print self.monitoring_list
        print "Total ", len(self.monitoring_list), " switches"

    def create_flow_primary(self, datapath, flow_info, src_port, out_port1, out_port2):
        ofp_parser = datapath.ofproto_parser
        ofp = datapath.ofproto
        self.group_id += 1
        if out_port2:
            actions = [ofp_parser.OFPActionGroup(self.group_id)]
            match = ofp_parser.OFPMatch(eth_src="00:00:00:00:00:00", in_port=src_port, eth_type=flow_info[0],
                                        ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
            actions1 = [ofp_parser.OFPActionOutput(out_port1)]
            actions2 = [ofp_parser.OFPActionOutput(out_port2),
                        ofp_parser.OFPActionSetField(eth_src="00:00:00:00:00:00")]
            actions3 = [ofp_parser.OFPActionOutput(ofp.OFPP_IN_PORT),
                        ofp_parser.OFPActionSetField(eth_src="11:11:11:11:11:11")]
            weight = 0
            buckets = [ofp_parser.OFPBucket(weight, out_port1, ofp.OFPG_ANY, actions1),
                       ofp_parser.OFPBucket(weight, out_port2, ofp.OFPG_ANY, actions2),
                       ofp_parser.OFPBucket(weight, src_port, ofp.OFPG_ANY, actions3)]
            req = ofp_parser.OFPGroupMod(datapath, ofp.OFPGC_ADD, ofp.OFPGT_FF, self.group_id, buckets)
            datapath.send_msg(req)
            self.add_flow(datapath, 1, match, actions, table=0)

        else:
            actions = [ofp_parser.OFPActionGroup(self.group_id)]
            match = ofp_parser.OFPMatch(eth_src="00:00:00:00:00:00", in_port=src_port, eth_type=flow_info[0],
                                        ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
            actions1 = [ofp_parser.OFPActionOutput(out_port1),
                        ofp_parser.OFPActionSetField(eth_src="00:00:00:00:00:00")]
            actions2 = [ofp_parser.OFPActionOutput(ofp.OFPP_IN_PORT),
                        ofp_parser.OFPActionSetField(eth_src="11:11:11:11:11:11")]
            weight = 0
            buckets = [ofp_parser.OFPBucket(weight, out_port1, ofp.OFPG_ANY, actions1),
                       ofp_parser.OFPBucket(weight, src_port, ofp.OFPG_ANY, actions2)]
            req = ofp_parser.OFPGroupMod(datapath, ofp.OFPGC_ADD, ofp.OFPGT_FF, self.group_id, buckets)
            datapath.send_msg(req)
            self.add_flow(datapath, 1, match, actions, table=0)

    def create_flow_crankback(self, datapath, flow_info, src_port, out_port1, out_port2):
        ofp_parser = datapath.ofproto_parser
        ofp = datapath.ofproto
        if out_port2:
            self.group_id += 1
            actions3 = [ofp_parser.OFPActionGroup(self.group_id)]
            match = ofp_parser.OFPMatch(eth_src="11:11:11:11:11:11", in_port=src_port, eth_type=flow_info[0],
                                        ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
            actions1 = [ofp_parser.OFPActionOutput(out_port2),
                        ofp_parser.OFPActionSetField(eth_src="00:00:00:00:00:00")]
            actions2 = [ofp_parser.OFPActionOutput(ofp.OFPP_IN_PORT),
                        ofp_parser.OFPActionSetField(eth_src="11:11:11:11:11:11")]
            weight = 0
            buckets = [ofp_parser.OFPBucket(weight, out_port2, ofp.OFPG_ANY, actions1),
                       ofp_parser.OFPBucket(weight, src_port, ofp.OFPG_ANY, actions2)]
            req = ofp_parser.OFPGroupMod(datapath, ofp.OFPGC_ADD, ofp.OFPGT_FF, self.group_id, buckets)
            datapath.send_msg(req)
            self.add_flow(datapath, 100, match, actions3, table=0)
        else:
            match = ofp_parser.OFPMatch(eth_src="11:11:11:11:11:11", in_port=src_port, eth_type=flow_info[0],
                                        ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
            actions2 = [ofp_parser.OFPActionOutput(out_port1)]
            self.add_flow(datapath, 100, match, actions2, table=0)

        return

    def shortest_forwarding(self, msg, eth_type, ip_src, ip_dst):
        flow_info = (eth_type, ip_src, ip_dst)

        src_sw = msg.datapath.id
        dst_sw = int(ip_dst.split('.')[3])
        if src_sw == dst_sw:
            return

        path, backup_path, anchors= self.all_pair_shortest_path[(src_sw, dst_sw)]
        print path, backup_path
        if path[0] != int(ip_src.split('.')[3]):
            curr_sw = path[0]
            datapath = self.dp_list[curr_sw]
            in_port = msg.match['in_port']
            next_sw_in_path = path[path.index(curr_sw) + 1]
            next_sw_in_backuppath = backup_path[backup_path.index(curr_sw) + 1]
            out_port1 = self.net[curr_sw][next_sw_in_path]['port']
            out_port2 = self.net[curr_sw][next_sw_in_backuppath]['port']
            if out_port2 != in_port and out_port1 != in_port:
                self.create_flow_primary(datapath, flow_info, in_port, out_port1, out_port2)
                self.create_flow_crankback(datapath, flow_info, out_port1, in_port, out_port2)
                self.create_flow_crankback(datapath, flow_info, out_port2, in_port, False)
            else:
                if out_port1 == in_port:
                    self.create_flow_primary(datapath, flow_info, in_port, out_port2, False)
                    self.create_flow_crankback(datapath, flow_info, in_port, out_port2, False)
                    self.create_flow_crankback(datapath, flow_info, out_port2, in_port, False)
                if out_port2 == in_port:
                    self.create_flow_primary(datapath, flow_info, in_port, out_port1, False)
                    self.create_flow_crankback(datapath, flow_info, in_port, out_port1, False)
                    self.create_flow_crankback(datapath, flow_info, out_port1, in_port, False)

        prev_path, prev_backup_path = path, backup_path
        curr_sw = path[1]

        # for normal switch
        while curr_sw != dst_sw:
            datapath = self.dp_list[curr_sw]
            path, backup_path, anchors= self.all_pair_shortest_path[(curr_sw, dst_sw)]
            prev_sw = prev_path[prev_path.index(curr_sw) - 1]
            in_port = self.net[curr_sw][prev_sw]['port']

            next_sw_in_path = path[path.index(curr_sw) + 1]
            next_sw_in_backuppath = backup_path[backup_path.index(curr_sw) + 1]
            out_port1 = self.net[curr_sw][next_sw_in_path]['port']
            out_port2 = self.net[curr_sw][next_sw_in_backuppath]['port']
            if out_port2 != in_port and out_port1 != in_port:
                self.create_flow_primary(datapath, flow_info, in_port, out_port1, out_port2)
                self.create_flow_crankback(datapath, flow_info, out_port1, in_port, out_port2)
                self.create_flow_crankback(datapath, flow_info, out_port2, in_port, False)
            else:
                if out_port1 == in_port:
                    self.create_flow_primary(datapath, flow_info, in_port, out_port2, False)
                    self.create_flow_crankback(datapath, flow_info, in_port, out_port2, False)
                    self.create_flow_crankback(datapath, flow_info, out_port2, in_port, False)
                if out_port2 == in_port:
                    self.create_flow_primary(datapath, flow_info, in_port, out_port1, False)
                    self.create_flow_crankback(datapath, flow_info, in_port, out_port1, False)
                    self.create_flow_crankback(datapath, flow_info, out_port1, in_port, False)
            curr_sw = next_sw_in_path
            prev_path, prev_backup_path = path, backup_path

        # for dst switch
        datapath = self.dp_list[curr_sw]
        parser = datapath.ofproto_parser
        prev_sw = prev_path[prev_path.index(curr_sw) - 1]
        in_port = self.net[curr_sw][prev_sw]['port']
        actions = [parser.OFPActionOutput(1)]
        match = parser.OFPMatch(in_port=in_port, eth_type=flow_info[0], ipv4_src=flow_info[1],
                                ipv4_dst=flow_info[2])
        self.add_flow(datapath, 1, match, actions, table=0)

        # for src switch
        path, backup_path, anchors= self.all_pair_shortest_path[(src_sw, dst_sw)]
        curr_sw = src_sw
        datapath = self.dp_list[curr_sw]
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        next_sw_in_path = path[path.index(curr_sw) + 1]
        next_sw_in_backuppath = backup_path[backup_path.index(curr_sw) + 1]
        out_port1 = self.net[curr_sw][next_sw_in_path]['port']
        out_port2 = self.net[curr_sw][next_sw_in_backuppath]['port']
        in_port = msg.match['in_port']
        if out_port2 != in_port and out_port1 != in_port:
            # primary rule
            self.group_id += 1
            match = parser.OFPMatch(in_port=in_port, eth_type=flow_info[0],
                                    ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
            actions = [parser.OFPActionGroup(self.group_id)]
            actions1 = [parser.OFPActionOutput(out_port1),
                        parser.OFPActionSetField(eth_src="00:00:00:00:00:00")]
            actions2 = [parser.OFPActionOutput(out_port2),
                        parser.OFPActionSetField(eth_src="11:11:11:11:11:11")]
            buckets = [parser.OFPBucket(0, out_port1, ofproto.OFPG_ANY, actions1),
                       parser.OFPBucket(0, out_port2, ofproto.OFPG_ANY, actions2)]
            req = parser.OFPGroupMod(datapath, ofproto.OFPGC_ADD, ofproto.OFPGT_FF, self.group_id, buckets)
            datapath.send_msg(req)
            self.add_flow(datapath, 1, match, actions, table=0)

            # crankback rule
            match = parser.OFPMatch(eth_src="11:11:11:11:11:11", in_port=out_port1, eth_type=flow_info[0],
                                    ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
            actions2 = [parser.OFPActionOutput(out_port2), parser.OFPActionSetField(eth_src="00:00:00:00:00:00")]
            self.add_flow(datapath, 100, match, actions2, table=0)
        else:
            match = parser.OFPMatch(in_port=in_port, eth_type=flow_info[0],
                                    ipv4_src=flow_info[1], ipv4_dst=flow_info[2])
            actions = [parser.OFPActionOutput(out_port1),
                       parser.OFPActionSetField(eth_src="00:00:00:00:00:00")]
            self.add_flow(datapath, 1, match, actions, table=0)

        out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id, data=msg.data,
                                                   in_port=in_port, actions=actions)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def _packet_in_handler(self, ev):
        """
        """
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']
        pkt = packet.Packet(msg.data)
        ip_pkt = pkt.get_protocol(ipv4.ipv4)
        lldp_pkt = pkt.get_protocol(lldp.lldp)

        if isinstance(lldp_pkt, lldp.lldp):
            return
                
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
        out = datapath.ofproto_parser.OFPPacketOut(datapath=datapath, buffer_id=buffer_id,data=msg_data, in_port=src_port, actions=actions)
        return out

    def send_packet_out(self, datapath, buffer_id, src_port, dst_port, data):
        out = self._build_packet_out(datapath, buffer_id,src_port, dst_port, data)
        if out:
            datapath.send_msg(out)
