import os
import random

import dhmin as dh
import osmnx as ox
import pyomo.environ
from pyomo.opt import SolverFactory
from shapely.geometry import Polygon
import networkx as nx
import archetypal as ar


def test_dhmin(ox_config):
    bbox = Polygon(((-73.580147, 45.509472), (-73.551007, 45.509472),
                    (-73.551007, 45.488723), (-73.580147, 45.488723),
                    (-73.580147, 45.509472)))
    bbox = ar.project_geom(bbox, from_crs={'init': 'epsg:4326'},
                           to_crs={'init': 'epsg:2950'})
    bbox = bbox.buffer(-1000)
    bbox = ar.project_geom(bbox, to_crs={'init': 'epsg:4326'},
                           from_crs={'init': 'epsg:2950'})
    west, south, east, north = bbox.bounds
    G = ox.graph_from_bbox(north, south, east, west, simplify=False,
                           truncate_by_edge=False, retain_all=False,
                           network_type='bike', clean_periphery=True)
    # simplify network with strict mode turned off
    G = ox.simplify_graph(G, strict=True)
    G = ox.project_graph(G, to_crs={'init': 'epsg:2950'})

    # G2 = nx.disjoint_union(G, nx.reverse(G))

    G = ox.get_undirected(G)  # Get the undirected graph since we don't want
    # symmetry yet. We will create it with dhmin

    ec = ['b' if key == 0 else 'r' for u, v, key in G.edges(keys=True)]
    ox.plot_graph(G, node_color='w', node_edgecolor='k', node_size=20,
                  node_zorder=3, edge_color=ec, edge_linewidth=2)
    G2 = ar.clean_paralleledges_and_selfloops(G)
    ec = ['b' if key == 0 else 'r' for u, v, key in G2.edges(keys=True)]
    ox.plot_graph(G2, node_color='w', node_edgecolor='k', node_size=20,
                  node_zorder=3, edge_color=ec, edge_linewidth=2)

    # Drop parallel edges and selfloops
    # paralel = [(u, v) for u, v, key in G2.edges(keys=True) if key != 0]
    # [G2.remove_edge(*key) for key in paralel]
    self_loops = [(u, v) for u, v in G2.selfloop_edges()]
    ec = ['r' if (u, v) in self_loops else 'b' for u, v, key in G2.edges(
        keys=True)]
    ox.plot_graph(G2, node_color='w', node_edgecolor='k', node_size=20,
                  node_zorder=3, edge_color=ec, edge_linewidth=2)

    nodes, edges = ox.graph_to_gdfs(G2, node_geometry=True,
                                    fill_edge_geometry=True)
    edges.set_index(['u', 'v'], inplace=True)
    edges.index.names = ['Vertex1', 'Vertex2']

    # init, c_heatvar, c_heatfix
    nodes['init'] = 0
    nodes['c_heatvar'] = 0
    nodes['c_heatfix'] = 0
    nodes['capacity'] = 0

    ox.plot_graph(G2, annotate=True, show=True)

    # let's create 5 random plants and give them properties
    plants = nodes.sample(n=5).index
    nodes.loc[plants, 'init'] = 1
    nodes.loc[plants, 'c_heatvar'] = 0.035
    nodes.loc[plants, 'c_heatfix'] = 0
    nodes.loc[plants, 'capacity'] = 300

    # let's pretend edges have these values
    num = random.randint(-250, 250)  # random peak demand
    edges['pipe_exist'] = 0
    edges['must_build'] = 0
    edges['peak'] = edges.apply(lambda x: randon_peak(), axis=1)
    edges['cnct_quota'] = 1
    edges['cap_max'] = 1000

    # create provblem
    params = {'r_heat': 0.07}
    timesteps = [(1600, .8), (1040, .5), (1800, 0.2)]
    prob = dh.create_model(nodes, edges, params, timesteps)

    optim = SolverFactory('gurobi')
    outputfile = os.path.join(ar.settings.data_folder, 'rundh.lp')
    if not os.path.isdir(ar.settings.data_folder):
        os.makedirs(ar.settings.data_folder)
    prob.write(outputfile, io_options={'symbolic_solver_labels': True})
    result = optim.solve(prob, tee=True)
    prob.solutions.load_from(result)
    ar.plot_dhmin(prob)


def randon_peak():
    """Creates random positive numbers; 2x more in the positive"""
    num = random.randint(-250, 250)
    return num if num > 0 else 0