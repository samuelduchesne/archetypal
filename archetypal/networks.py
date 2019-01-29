import hashlib
import logging as lg
import os
import time
import uuid

import dhmin
import numpy as np
import pandas as pd
import pyomo.environ
from pyomo.opt import SolverFactory
from shapely.geometry import LineString, Point

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
    file further. It is used over the possibly more compact bzip2 compression
    due to the
    lower runtime.

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
                filename = hash_model(prob.nodes_tmp, prob.edges_tmp, prob.params,
                                      prob.timesteps)
            else:
                filename = prob.name

            cache_path_filename = os.path.join(settings.cache_folder,
                                               os.extsep.join(
                                                   [filename, 'gzip']))
            import gzip
            try:
                import cPickle as pickle
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
                import cPickle as pickle
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
                  model_name=None, override_hash=False):
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
                                  is_connected=is_connected)

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
        ar.plot_dhmin(prob, plot_demand=True, margin=0.2, show=False, save=True,
                      extent='tight', legend=legend)
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