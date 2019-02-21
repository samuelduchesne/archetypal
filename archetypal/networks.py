import hashlib
import logging as lg
import os
import time
import uuid

import dhmin
import networkx as nx
import numpy as np
import osmnx as ox
import pandas as pd
import geopandas as gpd
import pyomo.environ
from pyomo.opt import SolverFactory
from shapely.geometry import Point, LineString

import archetypal as ar
from archetypal import project_geom, settings, log


def clean_paralleledges_and_selfloops(G):
    """Cuts any parallel edges in two, creating a new point in between"""
    # copy nodes into new graph
    star_time = time.time()
    G2 = G.copy()
    self_loops = [(u, v) for u, v in G2.selfloop_edges()]
    # copy edges to new graph, including parallel edges
    if G2.is_multigraph:
        count = 0
        for u, v, key, data in G.edges(keys=True, data=True):
            if key != 0 or (u, v) in self_loops:
                count += 1
                # Fix the issue
                parallel_line = data['geometry']
                line1, line2, point = cut(parallel_line,
                                          distance=parallel_line.length / 2)
                v2 = int(str(uuid.uuid1().int)[0:11])  # creates a unique id
                # for the Point
                if G2.has_edge(u, v, key):
                    # create node associated with new point
                    x, y = point.coords[0]
                    lon, lat = project_geom(point, from_crs=G2.graph['crs'],
                                            to_latlon=True).coords[0]
                    G2.add_nodes_from([v2], highway=np.NaN,
                                      lat=lat, lon=lon, osmid=v2, x=x, y=y)
                    # keep way direction
                    from1 = G2.edges[u, v, key]['from']
                    to2 = G2.edges[u, v, key]['to']
                    # remove that edge and replace with two edged
                    G2.remove_edge(u, v, key=key)
                    G2.add_edges_from([(u, v2, 0, {'geometry': line1,
                                                   'length': line1.length,
                                                   'from': from1,
                                                   'to': v2}),
                                       (v2, v, 0, {'geometry': line2,
                                                   'length': line2.length,
                                                   'from': v2,
                                                   'to': to2})])
            else:
                G2.add_edge(u, v, key=key, data=data)
        log('Identified {} parallel or self-loop edges to cut in {:,.2f} '
            'seconds'.format(count, time.time() - star_time))

    return G2


def cut(line, distance):
    """Cuts a line in two at a distance from its starting point"""
    if distance <= 0.0 or distance >= line.length:
        return LineString(line), None, None
    coords = list(line.coords)
    for i, p in enumerate(coords):
        pd = line.project(Point(p))
        if pd == distance:
            return LineString(coords[:i + 1]), \
                   LineString(coords[i:]), Point(p)
        if pd > distance:
            cp = line.interpolate(distance)
            return LineString(coords[:i] + [(cp.x, cp.y)]), \
                   LineString([(cp.x, cp.y)] + coords[i:]), cp


def save_model_to_cache(prob, override_hash=False):
    """Pickle is the standard Python way of serializing and de-serializing
    Python objects. By using it, saving any object, in case of this function a
    Pyomo ConcreteModel, becomes a twoliner. GZip is a standard Python
    compression library that is used to transparently compress the pickle
    file further.

    Args:
        override_hash:
        prob (pyomo.ConcreteModel): the model

    Returns:

    """
    if settings.use_cache:
        if prob is None:
            log('Saved nothing to cache because model is None')
        else:

            # create the folder on the disk if it doesn't already exist
            if not os.path.exists(settings.cache_folder):
                os.makedirs(settings.cache_folder)
            if not override_hash:
                # hash the model (to make a unique filename)
                filename = hash_model(prob.nodes_tmp, prob.edges_tmp,
                                      prob.params,
                                      prob.timesteps)
            else:
                filename = prob.name

            cache_path_filename = os.path.join(settings.cache_folder,
                                               os.extsep.join(
                                                   [filename, 'gzip']))
            import gzip
            try:
                import cloudpickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            with gzip.GzipFile(cache_path_filename, 'wb') as file_handle:
                pickle.dump(prob, file_handle)
            log('Saved pickle to file in {:,.2f} seconds'.format(
                time.time() - start_time))


def load_model_from_cache(nodes, edges, params, timesteps, override_hash=False,
                          model_name='DHMIN'):
    if settings.use_cache:
        if not override_hash:
            cache_filename = hash_model(nodes, edges, params, timesteps)
        else:
            cache_filename = model_name
        cache_fullpath_filename = os.path.join(settings.cache_folder,
                                               os.extsep.join([
                                                   cache_filename, 'gzip']))
        if os.path.isfile(cache_fullpath_filename):
            import gzip
            try:
                import cloudpickle as pickle
            except ImportError:
                import pickle
            with gzip.GzipFile(cache_fullpath_filename, 'r') as file_handle:
                prob = pickle.load(file_handle)
            log('Retreived model "{name}" from cache'.format(name=prob.name))
            return prob


def hash_model(nodes, edges, params, timesteps):
    """Hashes the MIP model inputs"""
    hasher = hashlib.md5()

    hasher.update(nodes.values.__str__().encode('utf-8'))
    hasher.update(edges.values.__str__().encode('utf-8'))
    hasher.update(str(params).encode('utf-8'))
    # hasher.update(timesteps.__str__().encode('utf-8'))

    return hasher.hexdigest()


def solve_network(edges, nodes, params, timesteps, edge_profiles,
                  plot_results=True, is_connected=True, time_limit=None,
                  solver='glpk', mip_gap=0.01, force_solve=False, legend=True,
                  model_name=None, override_hash=False,
                  use_availability=True, **kwargs):
    """Prepares and solves a Mixed-Integer Programming problem from a set of
    edges and nodes with demand and supply techno-economic properties.

    Args:
        edges:
        nodes:
        params:
        timesteps:
        edge_profiles:
        plot_results:
        is_connected:
        time_limit:
        solver:
        mip_gap:
        force_solve:
        legend:

    Returns:

    """
    # try to load problem from cache
    cached_model = load_model_from_cache(nodes, edges, params, timesteps,
                                         override_hash=override_hash,
                                         model_name=model_name)
    if not cached_model:
        # create the model
        prob = dhmin.create_model(nodes, edges, params,
                                  timesteps, edge_profiles, name=model_name,
                                  is_connected=is_connected,
                                  use_availability=use_availability)

        # Choose the solver
        optim = SolverFactory(solver)

        # Create readable output file
        outputfile = os.path.join(ar.settings.data_folder, 'rundh.lp')
        if not os.path.isdir(ar.settings.data_folder):
            os.makedirs(ar.settings.data_folder)
        prob.write(outputfile, io_options={'symbolic_solver_labels': True})

        # get logger to writer solver log to logger
        logger = lg.getLogger(ar.settings.log_name).handlers[0].baseFilename

        # solve and load results back into the model
        # optim.options['TimeLimit'] = time_limit
        if time_limit is not None:
            optim.options["TimeLimit"] = time_limit
        if mip_gap is not None:
            optim.options["MIPGap"] = mip_gap
        result = optim.solve(prob, tee=True, logfile=logger,
                             load_solutions=False)
        prob.solutions.load_from(result)

        # save the model to cache
        save_model_to_cache(prob, override_hash=True)
    else:
        prob = cached_model
        if force_solve:
            # Choose the solver
            optim = SolverFactory(solver)
            # get logger to writer solver log to logger
            logger = lg.getLogger(ar.settings.log_name).handlers[0].baseFilename
            result = optim.solve(prob, tee=True, logfile=logger,
                                 load_solutions=False)
            prob.solutions.load_from(result)
    # plot results
    if plot_results:
        show = kwargs.get('show', False)
        bbox = kwargs.get('bbox', None)
        ar.plot_dhmin(prob, bbox=bbox, plot_demand=True, margin=0.2,
                      show=show, save=True, extent='tight', legend=legend)
    return prob


def add_edge_profiles(G, edge_data):
    for u, v, data in G.edges(keys=False, data=True):
        try:
            data['profiles'] = edge_data.loc[(u, v)]
        except KeyError:
            raise KeyError('No edge_data for edge ({u}, {v})'.format(u=u, v=v))
        else:
            pass

    return G


def stats(model):
    """Calculate basic kpis and topological stats for a model

    Args:
        model (pyomo.ConcreteModel):

    Returns:
        pandas.Series: Series of model measures:
            - tech_parameters = techno-economic paramters used for the
                simulation
            - total_network_length = total network lenght
            - network_cost = network cost
            - heat_gen_cost = heat generation cost
            - heat_sell_revenue = heat sell revenue
            - net_profits = profits : network_cost + heat_gen_cost -
                heat_sell_revenue
            - installed_power = combined installed capacity of network
            - linear_heat_density = linear heat density
    """
    # built pipes length
    built_edges = dhmin.get_entity(model, 'x')
    total_network_length = model.edges.loc[built_edges.x == 1].geometry. \
        unary_union.length

    # Network cost
    costs = dhmin.get_entity(model, 'costs').to_dict()['costs']
    network_cost = costs['network']
    heat_gen_cost = costs['heat']
    heat_sell_revenue = costs['revenue']
    net_profits = network_cost + heat_gen_cost + heat_sell_revenue
    pmax = dhmin.get_entity(model, 'Pmax')
    sfactor = dhmin.get_entity(model, 'scaling_factor')
    sfactor_join_on_pmax = sfactor.join(pmax, on=['vertex', 'vertex_'])
    duration = dhmin.get_entity(model, 'dt')
    duration_join_on_sfactor_join_on_pmax = sfactor_join_on_pmax.join(
        duration, on='timesteps')
    pin = dhmin.get_entity(model, 'Pin')
    pot = dhmin.get_entity(model, 'Pot')
    linear_heat_density = (pin.Pin - pot.Pot).sum() / total_network_length
    installed_power = dhmin.get_entity(model,
                                       'Q').loc[(slice(None), 'Pmax'),
                                                'Q'].sum()
    tech_parameters = model.tech_parameters._data

    stats = {'tech_parameters': tech_parameters,
             'total_network_length': total_network_length,
             'network_cost': network_cost,
             'heat_gen_cost': heat_gen_cost,
             'heat_sell_revenue': heat_sell_revenue,
             'net_profits': net_profits,
             'installed_power': installed_power,
             'linear_heat_density': linear_heat_density}

    return pd.Series(stats)


def graph_from_shp(file, name=None, simplify=True, strict=True, crs=None,
                   custom_filter=None):
    """creates a MultiDiGraph from a shapefile.

    With simplify=True, it implements :func:`osmnx.simplify_graph`

    Args:
        file (str): shapefile of directory of multiple shapefiles
        name (str, optional): name of graph
        simplify (bool): If True, simplify a graph's topology by removing all
            nodes that are not intersections or dead-ends.
        strict (bool): if False, allow nodes to be end points even if they fail
            all other rules but have edges with different ids
        crs (dict): specify the crs of the shapefile eg. dict(init='epsg:2950')
        custom_filter (tuple): filter the attributes of the shapefile. Pass a
            tuple of ('column_name', equal_to_value). Todo: Implement != diff
    Returns:
        networkx.MultiDiGraph
    """
    if not name:
        name = os.path.basename(file)
    # create graph from shapefile
    if custom_filter:
        # load GeoDataFrame and apply filter
        gdf = gpd.read_file(file)
        gdf = gdf[gdf[custom_filter[0]]==custom_filter[1]]

        import tempfile
        with tempfile.TemporaryDirectory() as tempdir:
            with ar.cd(tempdir):
                gdf.to_file('temp')
                G = nx.read_shp('temp/temp.shp', simplify=False)
    else:
        G = nx.read_shp(file, simplify=False)

    # create multidigraph from digraph (since osmnx deals with multidigraphs)
    # give it a name and the default crs
    G = nx.MultiDiGraph(G, name=name, crs=settings.default_crs)

    # set osmid edge attribute. Uses a dict of {(u, v, key): id}
    nx.set_edge_attributes(G, {(edge[0], edge[1], edge[2]): edge[3]['osmid']
    if 'osmid' in edge[3] else i for
                               i, edge in
                               enumerate(G.edges(keys=True, data=True))},
                           'osmid')
    # set length attribute.
    nx.set_edge_attributes(G, {(edge[0], edge[1], edge[2]): float(edge[3][
        'length']) if edge[3]['length'] is not None else None
    if 'length' in edge[3] else None for
                               i, edge in
                               enumerate(G.edges(keys=True, data=True))},
                           'length')
    # Set x, y node attributes
    nx.set_node_attributes(G, {node: node[0] for node in G.nodes}, 'x')
    nx.set_node_attributes(G, {node: node[1] for node in G.nodes}, 'y')

    if crs:
        G.graph['crs'] = crs

    if simplify:
        G = ox.simplify_graph(G, strict=strict)

    return G


def split_union(gdfs):
    """splits and unionizes a list of GeoDataFrames"""
    if not isinstance(gdfs, list):
        gdfs = list(gdfs)

    import itertools
    from shapely.ops import split, linemerge
    gdf_segments = []

    # with a list of GeoDataFrame, we use permutations to split all
    # combinations of each GeoDataFrame
    for first, second in itertools.permutations(gdfs, 2):
        split_line = split(first.unary_union,
                           second.unary_union)

        # transform Geometry Collection to GeoDataFrame
        segments = [feature for feature in split_line]
        gdf_segments.append(
            gpd.GeoDataFrame(list(range(len(segments))), geometry=segments))
    df = pd.concat(gdf_segments)
    gdf_segments = gpd.GeoDataFrame(df, crs=dict(init='epsg:2950'),
                                    geometry=df.geometry)
    gdf_segments.columns = ['index', 'geometry']
    return gdf_segments