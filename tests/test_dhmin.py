import random

import numpy as np
import osmnx as ox
import pytest
from shapely.geometry import Polygon

import archetypal as ar
from archetypal import solve_network


@pytest.mark.parametrize('seed', [1, 2])
def test_dhmin(ox_config, seed):
    # Create a bounding in lat,lon coordinates
    bbox = Polygon(((-73.580147, 45.509472), (-73.551007, 45.509472),
                    (-73.551007, 45.488723), (-73.580147, 45.488723),
                    (-73.580147, 45.509472)))
    # Project the geometry to EPSG:2950
    bbox = ar.project_geom(bbox, from_crs={'init': 'epsg:4326'},
                           to_crs={'init': 'epsg:2950'})
    # Change the size of the zone if necessary by creating a buffer. Negative
    # values will produce a smaller polygon.
    bbox = bbox.buffer(-1000)

    # Project back to EPSG:2950
    bbox = ar.project_geom(bbox, from_crs={'init': 'epsg:2950'},
                           to_crs={'init': 'epsg:4326'})
    # get the bounding box bounds
    west, south, east, north = bbox.bounds

    # Create a graph from a bounding box bounds.
    G = ox.graph_from_bbox(north, south, east, west, simplify=False,
                           truncate_by_edge=False, retain_all=False,
                           network_type='bike', clean_periphery=True)

    # Simplify network
    G = ox.simplify_graph(G, strict=True)

    # Project to graph to EPSG:2950
    G = ox.project_graph(G, to_crs={'init': 'epsg:2950'})

    # Reproject the bounding box to lat,lon since ploting functions need
    # lat/lon coordinates
    bbox = ar.project_geom(bbox, to_crs={'init': 'epsg:2950'},
                           from_crs={'init': 'epsg:4326'})
    west, south, east, north = bbox.bounds

    G = ox.get_undirected(G)  # Get the undirected graph since we don't want
    # symmetry yet. We will create it with dhmin

    # Fix parallel and self-loop edges
    G2 = ar.clean_paralleledges_and_selfloops(G)

    random.seed(seed)
    ec = ["#" + ''.join([random.choice('0123456789ABCDEF') for j in range(6)])
          for i in G2.edges]
    nc = ['r' if node > 9999999999 else 'b' for node in G2.nodes]
    ox.plot_graph(G2, bbox=(north, south, east, west), node_color=nc,
                  node_edgecolor='k', node_size=20, save=True, node_zorder=3,
                  edge_color=ec, edge_linewidth=2, annotate=False,
                  margin=0.2, filename='test_{}_fixed_nodes'.format(seed))
    edges = ox.graph_to_gdfs(G2, nodes=False)
    edges.set_index(['u', 'v'], inplace=True)
    rdstate = np.random.RandomState(seed=seed)
    profiles = edges.apply(lambda x: {type_str:
                                          ar.create_fake_profile(
                                              y1={'A': random.uniform(0, 10)},
                                              normalize=False,
                                              profile_type=type_str,
                                              sorted=False, units='kWh/m2')
                                      for type_str in
                                      random_type(size=random.randint(1,
                                                                      5))},
                           axis=1)
    profiles = profiles.apply(ar.EnergyProfile, frequency='1H', units='kWh/m2',
                              is_sorted=True, concurrent_sort=True)
    ar.add_edge_profiles(G2, edge_data=profiles)

    nodes, edges = ox.graph_to_gdfs(G2, node_geometry=True,
                                    fill_edge_geometry=True)
    edges.set_index(['u', 'v'], inplace=True)
    edges.index.names = ['Vertex1', 'Vertex2']

    # Sort index to keep randomess pseudo
    nodes = nodes.sort_index()
    edges = edges.sort_index()
    # init, c_heatvar, c_heatfix
    nodes['init'] = 0
    nodes['c_heatvar'] = 0
    nodes['c_heatfix'] = 0
    nodes['capacity'] = 0

    # let's create 5 random plants and give them properties
    plants = nodes.sample(n=5, random_state=rdstate).index
    nodes.loc[plants, 'init'] = 1
    nodes.loc[plants, 'c_heatvar'] = 0.035
    nodes.loc[plants, 'c_heatfix'] = 0
    nodes.loc[plants, 'capacity'] = 5000

    edges['pipe_exist'] = 0
    edges['must_build'] = 0
    edges['peak'] = edges.apply(
        lambda x: sum(profile.p_max if isinstance(profile, ar.EnergyProfile)
                      else 0
                      for profile in
                      x.profiles),
        axis=1)
    edges['cnct_quota'] = 1
    edges['cap_max'] = 1000

    # create provblem
    params = {'c_rev': 0.07}
    timesteps = [(1600, .8), (1040, .5), (6120, .1)]

    # create fake duration, scaling factor with same as timstep (could be
    # customized)
    edge_profiles = edges.apply(lambda x: timesteps, axis=1)

    prob = solve_network(edges, nodes, params, timesteps, edge_profiles,
                         is_connected=False, time_limit=120,
                         use_availability=False,
                         solver='gurobi', legend=False, plot_results=True,
                         model_name='test_{}'.format(seed), override_hash=False)


def random_peak(random_state=None):
    """Creates random positive numbers; 2x more in the positive"""
    if random_state is None:
        random_state = np.random.RandomState(seed=1)
    num = random_state.randint(-250, 250)
    return num if num > 50 else 0


def random_type(random_state=None, size=1):
    if random_state is None:
        random_state = np.random.RandomState(seed=1)
    type = random_state.choice(['medium_office', 'large_office', 'small_office',
                                'small_hotel', 'large_hotel', 'res_highrise'],
                               size=size)
    return type


def random_color():
    rgbl = [0.1, 0, 0]
    random.shuffle(rgbl)
    return tuple(rgbl)
