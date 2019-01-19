import networkx as nx
from shapely.geometry import LineString, Point
import numpy as np

from archetypal import project_geom


def clean_paralleledges_and_selfloops(G):
    # copy nodes into new graph
    G2 = G.copy()

    # copy edges to new graph, including parallel edges
    if G2.is_multigraph:
        for u, v, key, data in G.edges(keys=True, data=True):
            if key != 0:
                # Fix the issue
                parallel_line = data['geometry']
                line1, line2, point = cut(parallel_line, parallel_line.length/2)
                v2 = point._geom  # creates a unique id for the Point
                if G2.has_edge(u, v, key):
                    # create node associated with new point
                    x, y = point.coords[0]
                    lon, lat = project_geom(point, from_crs=G2.graph['crs'],
                                            to_crs={'init':
                                                        'epsg:4326'}).coords[0]
                    G2.add_nodes_from([v2], geometry=point, highway=np.NaN,
                                      lat=lat, lon=lon, osmid=v2, x=x, y=y)
                    # remove that edge and replace with two edged
                    G2.remove_edge(u, v, key)
                    G2.add_edges_from([(u, v2, {'geometry': line1}),
                                       (v2, v, {'geometry': line2})])
            else:
                G2.add_edge(u, v, key)

    # update graph attribute dict, and return graph
    G2.graph.update(G.graph)
    return G2


def cut(line, distance):
    """Cuts a line in two at a distance from its starting point"""
    if distance <= 0.0 or distance >= line.length:
        return LineString(line), _, _
    coords = list(line.coords)
    for i, p in enumerate(coords):
        pd = line.project(Point(p))
        if pd == distance:
            return LineString(coords[:i+1]),\
                   LineString(coords[i:]), Point(p)
        if pd > distance:
            cp = line.interpolate(distance)
            return LineString(coords[:i] + [(cp.x, cp.y)]),\
                   LineString([(cp.x, cp.y)] + coords[i:]), Point(p)