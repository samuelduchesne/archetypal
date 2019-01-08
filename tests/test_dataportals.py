import pandas as pd

import archetypal as ar

# configure archetypal
ar.config(log_console=True, log_file=True, use_cache=True,
          data_folder='.temp/data', logs_folder='.temp/logs',
          imgs_folder='.temp/imgs', cache_folder='.temp/cache',
          umitemplate='../data/BostonTemplateLibrary.json')


def test_tabula_available_country(cleanup):
    # First, let's try the API call
    data = {'code_country': 'FR'}
    cc_res = ar.dataportal.tabula_api_request(data, table='all-country')

    # Then let's use the user-friendly call. Since it is the second call to the
    # same function, the response should be read from the cache.
    code_country = 'FR'
    cc_cache = ar.dataportal.tabula_available_buildings(code_country)


def test_tabula_notavailable_country(cleanup):
    pass


def test_tabula_building_sheet(cleanup):
    sheet = ar.tabula_building_details_sheet(code_country='Austria')


def test_tabula_multiple():
    country_code = 'FR'
    ab = ar.dataportal.tabula_available_buildings(country_code)
    archetypes = pd.concat(ab.apply(
        lambda x: ar.tabula_building_details_sheet(
            code_building=x.code_buildingtype_column1 + '.' +
                          x.suffix_building_column1 + '.001'),
        axis=1).values.tolist(),
                           keys=ab.code_buildingtype_column1 + '.' +
                                ab.suffix_building_column1)
