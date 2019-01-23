import os
import random
import logging as lg
import shutil

import osmnx as ox
import dhmin
import numpy as np
import pyomo.environ
from archetypal import save_model_to_cache, load_model_from_cache
from pyomo.opt import SolverFactory
from shapely.geometry import Polygon
import networkx as nx
import archetypal as ar


def test_dhmin(ox_config):

    if os.path.isdir('./.temp/imgs'):
        shutil.rmtree('./.temp/imgs')

    bbox = Polygon(((-73.580147, 45.509472), (-73.551007, 45.509472),
                    (-73.551007, 45.488723), (-73.580147, 45.488723),
                    (-73.580147, 45.509472)))
    bbox = ar.project_geom(bbox, from_crs={'init': 'epsg:4326'},
                           to_crs={'init': 'epsg:2950'})
    bbox = bbox.buffer(-1050)
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
    nx.is_connected(G)
    # symmetry yet. We will create it with dhmin

    ec = ['b' if key == 0 else 'r' for u, v, key in G.edges(keys=True)]
    ox.plot_graph(G, node_color='w', node_edgecolor='k', node_size=20,
                  node_zorder=3, edge_color=ec, edge_linewidth=2)
    G2 = ar.clean_paralleledges_and_selfloops(G)
    ec = ['b' if key == 0 else 'r' for u, v, key in G2.edges(keys=True)]
    ox.plot_graph(G2, node_color='w', node_edgecolor='k', node_size=20,
                  save=True, node_zorder=3, edge_color=ec, edge_linewidth=2,
                  annotate=True)

    # Drop parallel edges and selfloops
    # paralel = [(u, v) for u, v, key in G2.edges(keys=True) if key != 0]
    # [G2.remove_edge(*key) for key in paralel]
    self_loops = [(u, v) for u, v in G2.selfloop_edges()]
    ec = ['r' if (u, v) in self_loops else 'b' for u, v, key in G2.edges(
        keys=True)]
    ec = ["#"+''.join([random.choice('0123456789ABCDEF') for j in range(6)])
             for i in G2.edges]
    nc = ['r' if node > 9999999999 else 'b' for node in G2.nodes]
    ox.plot_graph(G2, node_color=nc, node_edgecolor='k', node_size=20,
                  save=True, node_zorder=3, edge_color=ec, edge_linewidth=2,
                  annotate=True, filename='fixed_nodes')

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
    seed = 2
    rdstate = np.random.RandomState(seed=seed)
    plants = nodes.sample(n=5, random_state=rdstate).index
    nodes.loc[plants, 'init'] = 1
    nodes.loc[plants, 'c_heatvar'] = 0.035
    nodes.loc[plants, 'c_heatfix'] = 0
    nodes.loc[plants, 'capacity'] = 500

    edges['pipe_exist'] = 0
    edges['must_build'] = 0
    edges['peak'] = edges.apply(lambda x: randon_peak(rdstate), axis=1)
    edges['cnct_quota'] = 1
    edges['cap_max'] = 1000

    # create provblem
    params = {'r_heat': 0.07}
    timesteps = [(1600, .8), (1040, .5)]

    # create fake duration, scaling factor with same as timstep (could be
    # customized)
    edge_profiles = edges.apply(lambda x: timesteps, axis=1)

    # try to load problem from cache
    cached_model = load_model_from_cache(nodes, edges, params, timesteps)
    if not cached_model:
        prob = dhmin.create_model(nodes, edges, params,
                                  timesteps, edge_profiles, 'test',
                                  is_connected=False)

        # Choose the solver
        optim = SolverFactory('gurobi')

        # Create readable output file
        outputfile = os.path.join(ar.settings.data_folder, 'rundh.lp')
        if not os.path.isdir(ar.settings.data_folder):
            os.makedirs(ar.settings.data_folder)
        prob.write(outputfile, io_options={'symbolic_solver_labels': True})

        # get logger to writer solver log to logger
        logger = lg.getLogger(ar.settings.log_name).handlers[0].baseFilename

        # solve and load results back into the model
        result = optim.solve(prob, tee=True, logfile=logger)
        prob.solutions.load_from(result)

        # save the model to cache
        save_model_to_cache(prob)
    else:
        prob = cached_model
    # plot results
    ar.plot_dhmin(prob, plot_demand=True, margin=0.2, show=False, save=True,
                  extent='tight', legend=True)


def randon_peak(seed=None):
    """Creates random positive numbers; 2x more in the positive"""
    if not seed:
        seed = np.random.RandomState(seed=seed)
    num = seed.randint(-250, 250)
    return num if num > 50 else 0


def random_color():
    rgbl=[0.1, 0, 0]
    random.shuffle(rgbl)
    return tuple(rgbl)
