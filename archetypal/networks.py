import hashlib
import os
import time

import networkx as nx
from shapely.geometry import LineString, Point
import numpy as np

from archetypal import project_geom, settings, log


def clean_paralleledges_and_selfloops(G):
    # copy nodes into new graph
    G2 = G.copy()

    # copy edges to new graph, including parallel edges
    if G2.is_multigraph:
        for u, v, key, data in G.edges(keys=True, data=True):
            if key != 0:
                # Fix the issue
                parallel_line = data['geometry']
                line1, line2, point = cut(parallel_line,
                                          distance=parallel_line.length/2)
                v2 = point._geom  # creates a unique id for the Point
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
                    G2.remove_edge(u, v, key)
                    G2.add_edges_from([(u, v2, 0, {'geometry': line1,
                                                   'length': line1.length,
                                                   'from': from1,
                                                   'to': v2}),
                                       (v2, v, 0, {'geometry': line2,
                                                   'length': line2.length,
                                                   'from': v2,
                                                   'to': to2})])
            else:
                G2.add_edge(u, v, key)
    return G2


def cut(line, distance):
    """Cuts a line in two at a distance from its starting point"""
    if distance <= 0.0 or distance >= line.length:
        return LineString(line), None, None
    coords = list(line.coords)
    for i, p in enumerate(coords):
        pd = line.project(Point(p))
        if pd == distance:
            return LineString(coords[:i+1]),\
                   LineString(coords[i:]), Point(p)
        if pd > distance:
            cp = line.interpolate(distance)
            return LineString(coords[:i] + [(cp.x, cp.y)]),\
                   LineString([(cp.x, cp.y)] + coords[i:]), cp


def save_model_to_cache(prob):
    """Pickle is the standard Python way of serializing and de-serializing
    Python objects. By using it, saving any object, in case of this function a
    Pyomo ConcreteModel, becomes a twoliner. GZip is a standard Python
    compression library that is used to transparently compress the pickle
    file further. It is used over the possibly more compact bzip2 compression
    due to the
    lower runtime.

    Args:
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

            # hash the model (to make a unique filename)
            filename = hash_model(prob.vertices, prob.edges, prob.params,
                                  prob.timesteps)

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


def load_model_from_cache(nodes, edges, params, timesteps):
    if settings.use_cache:
        cache_filename = hash_model(nodes, edges, params, timesteps)
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
            log('Retreived problem "{name}"from cache'.format(name=prob.name))
            return prob


def hash_model(nodes, edges, params, timesteps):
    hasher = hashlib.md5()

    hasher.update(nodes.__str__().encode('utf-8'))
    hasher.update(edges.__str__().encode('utf-8'))
    hasher.update(params.__str__().encode('utf-8'))
    # hasher.update(timesteps.__str__().encode('utf-8'))

    return hasher.hexdigest()