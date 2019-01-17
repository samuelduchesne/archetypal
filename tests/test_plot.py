import pytest

import archetypal as ar
from archetypal import project_geom


@pytest.mark.parametrize('plot_graph', [True, False], ids=['with_graph',
                                                           'no_graph'])
def test_plot_map(config, test_gis_server_osmnx, plot_graph):
    gdf = test_gis_server_osmnx
    # gdf.code_utilisation = gdf.code_utilisation.apply(pd.to_numeric)
    ar.plot_map(gdf, column='libelle_utilisation', categorical=True,
                plot_graph=plot_graph,
                equal_aspect=True, crs={'init': 'epsg:2950'},
                annotate=False, legend=True, scheme='Quantiles', margin=0,
                save=True, show=True)


def test_density(config):
    """plots the densitypu data from the GIS server"""
    from shapely.geometry import Polygon
    # We query the buffer (a polygon itself)
    cred = {'username': 'samueld',
            'password': 'sdsd',
            'server': 'comsolator.meca.polymtl.ca',
            'db_name': 'postgis_mtl',
            'schema': 'donneesouvertesmtl',
            'table_name': 'densitepu'}
    bbox = Polygon(((-73.580147, 45.509472), (-73.551007, 45.509472),
                    (-73.551007, 45.488723), (-73.580147, 45.488723),
                    (-73.580147, 45.509472)))
    # bbox = project_geom(bbox, from_crs={'init': 'epsg:4326'},
    #                     to_crs={'init': 'epsg:2950'})
    west, south, east, north = bbox.bounds
    densitepu = ar.dataportal.gis_server_request(cred, bbox, 'intersects', 4326)
    ar.plot_map(densitepu, column='indice', cmap='Oranges', bbox=(north,
                                                                  south,
                                                                  east,
                                                                  west),
                axis_off=False,
                legend=True, margin=0, plot_graph=False,
                crs={'init': 'epsg:4326'})



