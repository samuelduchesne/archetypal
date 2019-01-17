import pandas as pd
import pytest
from osgeo import gdal
from shapely.geometry import Point

import archetypal as ar
# configure archetypal
from archetypal import project_geom
from archetypal.building import download_bld_window


def test_tabula_available_country(config, scratch_then_cache):
    # First, let's try the API call
    data = {'code_country': 'FR'}
    cc_res = ar.dataportal.tabula_api_request(data, table='all-country')

    # Then let's use the user-friendly call. Since it is the second call to the
    # same function, the response should be read from the cache.
    code_country = 'FR'
    cc_cache = ar.dataportal.tabula_available_buildings(code_country)


def test_tabula_notavailable_country(config, scratch_then_cache):
    pass


def test_tabula_building_sheet(config, scratch_then_cache):
    sheet = ar.tabula_building_details_sheet(code_country='Austria')


def test_tabula_multiple(config, scratch_then_cache):
    country_code = 'FR'
    ab = ar.dataportal.tabula_available_buildings(country_code)
    archetypes = pd.concat(ab.apply(
        lambda x: ar.tabula_building_details_sheet(
            code_building=x.code_buildingtype_column1 + '.' +
                          x.suffix_building_column1 + '.001'),
        axis=1).values.tolist(),
                           keys=ab.code_buildingtype_column1 + '.' +
                                ab.suffix_building_column1)


def test_nrel_api_request(config, scratch_then_cache):
    data = {'keyword': 'Window',
            'format': 'json',
            'f[]': ['fs_a_Overall_U-factor:[3.4 TO 3.6]',
                    'sm_component_type:"Window"'],
            'oauth_consumer_key': 'f2d08b2d6cf7c8abd7d7c580ede79fa4'}

    response = ar.dataportal.nrel_bcl_api_request(data)
    assert response['result']


def test_gis_server_raster_request(config, bbox):
    # Create credentials
    cred = {'username': 'samueld',
            'password': 'sdsd',
            'server': 'comsolator.meca.polymtl.ca',
            'db_name': 'postgis_mtl',
            'schema': 'mns',
            'table_name': 'mnt_2015_1m'}

    vsipath = ar.dataportal.gis_server_raster_request(cred, bbox, srid=2950,
                                                      output_type='memory')
    assert vsipath
    gdal.Unlink(vsipath)


pts = [Point(-73.613112, 45.504631),  # Polytechnique Montréal
       Point(-73.538427, 45.42970)]  # middle of the St-Laurence River


@pytest.fixture(params=pts, ids=['where_there_should_be_data',
                                 'where_there_is_no_data'])
def bbox(request):
    """Parametrizes the creation of bounding boxes"""
    bbox = project_geom(request.param, from_crs={'init': 'epsg:4326'},
                        to_crs={'init': 'epsg:2950'})

    yield bbox.buffer(100)

    del bbox


@pytest.fixture()
def test_gis_server_request(config, scratch_then_cache, bbox):
    """Retrieves tax data for a bbox"""
    # Create credentials
    cred = {'username': 'samueld',
            'password': 'sdsd',
            'server': 'comsolator.meca.polymtl.ca',
            'db_name': 'postgis_mtl',
            'schema': 'donneesouvertesmtl',
            'table_name': 'uniteevaluationfonciere_latest'}

    yield ar.dataportal.gis_server_request(cred, bbox, srid=2950)


@pytest.fixture()
def test_gis_server_osmnx(config, scratch_then_cache):
    """Uses osmnx to create a retreive a geodataframe covering 1km2 around
    the center of dowwntown Montréal"""
    import osmnx as ox
    # using osmnx to retrieve a location & project it to EPSG:2950,
    # the projection of the 'uniteevaluationfonciere_latest' database
    downtown = ox.gdf_from_place('Montreal Downtown')
    downtown = ox.project_gdf(downtown, to_crs={'init': 'EPSG:2950'})

    # create bounding box from the first geometry in downtown geodataframe
    bbox = downtown.iloc[0].geometry.buffer(500)

    # Create credentials
    cred = {'username': 'samueld',
            'password': 'sdsd',
            'server': 'comsolator.meca.polymtl.ca',
            'db_name': 'postgis_mtl',
            'schema': 'donneesouvertesmtl',
            'table_name': 'uniteevaluationfonciere_latest'}

    yield ar.dataportal.gis_server_request(cred, bbox, 'contains', 2950)


def test_download_bld_window(scratch_then_cache):
    oauth_consumer_key = 'f2d08b2d6cf7c8abd7d7c580ede79fa4'

    response = download_bld_window(u_factor=3.18, shgc=0.49, vis_trans=0.53,
                                   oauth_key=oauth_consumer_key, tolerance=0.05)

    assert response


def test_update_height(config, bbox, scratch_then_cache):
    cred_gdf = {'username': 'samueld',
                'password': 'sdsd',
                'server': 'comsolator.meca.polymtl.ca',
                'db_name': 'postgis_mtl',
                'schema': 'donneesouvertesmtl',
                'table_name': 'uniteevaluationfonciere_latest'}

    cred_raster = {'username': 'samueld',
                   'password': 'sdsd',
                   'server': 'comsolator.meca.polymtl.ca',
                   'db_name': 'postgis_mtl',
                   'schema': 'mns',
                   'table_name': 'mnt_2015_1m'}

    gdf = ar.dataportal.gis_server_request(cred_gdf, bbox, srid=2950)
    geotiff = ar.dataportal.gis_server_raster_request(cred_raster, bbox,
                                                      srid=2950,
                                                      output_type='memory')
    if not gdf.empty:
        from rasterstats import zonal_stats
        z_stats = zonal_stats(gdf.copy(), geotiff, stats="mean")
        gdf['raster_height'] = [x['mean'] for x in z_stats]
        assert not gdf['raster_height'].empty
    else:
        assert pytest.raises(Exception)


def test_land_xml(config):
    file = './input_data/landxml/MNT2015_ville_Hampstead.xml'

    return ar.utils.landxml_to_point(file)