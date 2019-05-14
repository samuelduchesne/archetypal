import archetypal as ar
import pandas as pd

from archetypal import download_bld_window


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


def test_download_bld_window(scratch_then_cache):
    oauth_consumer_key = 'f2d08b2d6cf7c8abd7d7c580ede79fa4'

    response = download_bld_window(u_factor=3.18, shgc=0.49, vis_trans=0.53,
                                   oauth_key=oauth_consumer_key, tolerance=0.05)

    assert response


def test_statcan(config):
    data = dict(type='json', lang='E', dguid='2016A000011124', topic=5, notes=0)

    response = ar.dataportal.stat_can_request(data)
    print(response)


def test_statcan_geo(config):
    data = dict(type='json', lang='E', geos='PR', cpt='00')

    response = ar.dataportal.stat_can_geo_request(data)
    print(response)
