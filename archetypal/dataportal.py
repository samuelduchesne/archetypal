import hashlib
import io
import json
import logging as lg
import os
import re
import time

import geopandas as gpd
import pandas as pd
import pycountry as pycountry
import requests
from sqlalchemy import create_engine

from archetypal import log, settings, make_str

# scipy and sklearn are optional dependencies for faster nearest node search
try:
    from osgeo import gdal
except ImportError as e:
    gdal = None


def tabula_available_buildings(code_country='France'):
    """Returns all available building types for a specific country.

    Args:
        code_country:

    Returns:

    """
    # Check code country
    if code_country.upper() not in ['AT', 'BA', 'BE', 'BG', 'CY', 'CZ', 'DE',
                                    'DK', 'ES', 'FR', 'GB', 'GR', 'HU', 'IE',
                                    'IT', 'NL', 'NO', 'PL', 'RS', 'SE', 'SI']:
        code_country = pycountry.countries.get(name=code_country)
        if code_country is not None:
            code_country = code_country.alpha_2
        else:
            raise ValueError('Country name {} is invalid'.format(code_country))
    data = {'code_country': code_country}
    json_response = tabula_api_request(data, table='all-country')

    # load data
    df = pd.DataFrame(json_response)
    df = df.data.apply(pd.Series)
    return df


def tabula_api_request(data, table='detail'):
    """Send a request to the TABULA API via HTTP GET and return the JSON
    response.

    Args:
        data (dict): dictionnary of query attributes.
            with table='all-country', data expects 'code_country'.
            with table='detail', data expects 'buildingtype', 'suffix', and
            'variant'.
        table (str): the server-table to query. 'detail' or 'all-country'
    Returns:

    """
    # Prepare URL
    if table == 'all-country':
        codehex = str(
            int(hashlib.md5(data['code_country'].encode('utf-8')).hexdigest(),
                16))[0:13]
        url_base = ('http://webtool.building-typology.eu/data/matrix/building'
                    '/{0}/p/0/o/0/l/10/dc/{1}')
        prepared_url = url_base.format(data['code_country'], codehex)

    elif table == 'detail':
        buildingtype = '.'.join(s for s in data['buildingtype'])
        suffix = '.'.join(s for s in data['suffix'])
        bldname = buildingtype + '.' + suffix
        hexint = hashlib.md5(bldname.encode('utf-8')).hexdigest()[0:13]
        url_base = ('http://webtool.building-typology.eu/data/adv/building'
                    '/detail/{0}/bv/{1}/dc/{2}')
        prepared_url = url_base.format(bldname, data['variant'], hexint)

    else:
        raise ValueError('server-table name "{}" invalid'.format(table))

    # First, try to get the cached resonse from file
    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json
    else:
        # if this URL is not already in the cache, request it
        response = requests.get(prepared_url)
        if response.status_code == 200:
            response_json = response.json()
            if 'remark' in response_json:
                log('Server remark: "{}"'.format(response_json['remark'],
                                                 level=lg.WARNING))
            elif not response_json['success']:
                raise ValueError('The query "{}" returned no results'.format(
                    prepared_url), lg.WARNING)
            save_to_cache(prepared_url, response_json)
            return response_json
        else:
            # Handle some server errors
            pass


def tabula_building_details_sheet(code_building=None, code_country='FR',
                                  code_typologyregion='N',
                                  code_buildingsizeclass='SFH',
                                  code_construcionyearclass=1,
                                  code_additional_parameter='Gen',
                                  code_type='ReEx',
                                  code_num=1, code_variantnumber=1):
    """

    Args:
        code_building (str) : Whole building code e.g.:
            "AT.MT.AB.02.Gen.ReEx.001.001"
             |  |  |  |   |   |    |   |__code_variantnumber
             |  |  |  |   |   |    |______code_num
             |  |  |  |   |   |___________code_type
             |  |  |  |   |_______________code_additional_parameter
             |  |  |  |___________________code_construcionyearclass
             |  |  |______________________code_buildingsizeclass
             |  |_________________________code_typologyregion
             |____________________________code_country
        code_country (str): Country name or International Country Code (ISO
            3166-1-alpha-2 code). Input as 'France' will work equally as 'FR'.
        code_typologyregion (str): N for national; otherwise specific codes
            representing regions in a given country
        code_buildingsizeclass (str): 4 standardized classes: 'SFH':
        Single-family house, 'TH': Terraced house, 'MFH': multi-family house,
            'AB': Apartment block
        code_construcionyearclass (int or str): allocation of time bands to
            classes. Defined nationally (according to significant changes in
            construction technologies, building codes or available statistical
            data
        code_additional_parameter (str): 1 unique category. Defines the generic
            (or basic) typology matrix so that each residential building of a
            given country can be assigned to one generic type. A further
            segmentation in subtypes is  possible and can be indicated by a
            specific code. Whereas the generic types must comprise the whole
            building stock the total of subtypes must be comprehensive. e.g.
            'HR' (highrises), 'TFrame' (timber frame), 'Semi' (semi-detached)
        code_type: “ReEx” is a code for “real example” and “SyAv” for
            “Synthetical Average”
        code_num: TODO: What is this paramter?
        code_variantnumber: the energy performance level 1, 2 and 3. 1: minimum
            requirements, 2: improved and 3: ambitious or NZEB standard (assumed
            or announced level of Nearly Zero-Energy Buildings)

    Returns:
        pandas.DataFrame: The DataFrame from the

    """
    # Parse builsing_code
    if code_building is not None:
        try:
            code_country, code_typologyregion, code_buildingsizeclass, \
            code_construcionyearclass, \
            code_additional_parameter, code_type, code_num, \
            code_variantnumber = code_building.split('.')
        except ValueError:
            msg = (
                'the query "{}" is missing a parameter. Make sure the '
                '"code_building" has the form: '
                'AT.MT.AB.02.Gen.ReEx.001.001').format(code_building)
            log(msg, lg.ERROR)
            raise ValueError(msg)

    # Check code country
    if code_country.upper() not in ['AT', 'BA', 'BE', 'BG', 'CY', 'CZ', 'DE',
                                    'DK', 'ES', 'FR', 'GB', 'GR', 'HU', 'IE',
                                    'IT', 'NL', 'NO', 'PL', 'RS', 'SE', 'SI']:
        code_country = pycountry.countries.get(name=code_country)
        if code_country is not None:
            # if country is valid, return ISO 3166-1-alpha-2 code
            code_country = code_country.alpha_2
        else:
            raise ValueError('Country name {} is invalid'.format(code_country))

    # Check code_buildingsizeclass
    if code_buildingsizeclass.upper() not in ['SFH', 'TH', 'MFH', 'AB']:
        raise ValueError(
            'specified code_buildingsizeclass "{}" not supported. Available '
            'values are "SFH", "TH", '
            '"MFH" or "AB"')
    # Check numericals
    if not isinstance(code_construcionyearclass, str):
        code_construcionyearclass = str(code_construcionyearclass).zfill(2)

    if not isinstance(code_num, str):
        code_num = str(code_num).zfill(3)

    if not isinstance(code_variantnumber, str):
        code_variantnumber = str(code_variantnumber).zfill(3)

    # prepare data
    data = {'buildingtype': [code_country, code_typologyregion,
                             code_buildingsizeclass, code_construcionyearclass,
                             code_additional_parameter],
            'suffix': [code_type, code_num],
            'variant': code_variantnumber}
    json_response = tabula_api_request(data, table='detail')

    if json_response is not None:
        log('')
        # load data
        df = pd.DataFrame(json_response)
        df = df.data.apply(pd.Series)

        # remove html tags from labels
        df.label = df.label.str.replace('<[^<]+?>', ' ')
        return df
    else:
        raise ValueError('No data found in TABULA matrix with query:"{}"\nRun '
                         'archetypal.dataportal.tabula_available_buildings() '
                         'with country code "{}" to get list of possible '
                         'building types'
                         ''.format('.'.join(s for s in data['buildingtype']),
                                   code_country))


def tabula_system(code_country, code_boundarycond='SUH', code_variantnumber=1):
    """

    Args:
        code_country:
        code_boundarycond:
        code_variantnumber:

    Returns:

    """
    # Check code country
    if code_country.upper() not in ['AT', 'BA', 'BE', 'BG', 'CY', 'CZ', 'DE',
                                    'DK', 'ES', 'FR', 'GB', 'GR', 'HU', 'IE',
                                    'IT', 'NL', 'NO', 'PL', 'RS', 'SE', 'SI']:
        code_country = pycountry.countries.get(name=code_country)
        if code_country is not None:
            # if country is valid, return ISO 3166-1-alpha-2 code
            code_country = code_country.alpha_2
        else:
            raise ValueError('Country name {} is invalid')

    # Check code_buildingsizeclass
    if code_boundarycond.upper() not in ['SUH', 'MUH']:
        raise ValueError(
            'specified code_boundarycond "{}" not valid. Available values are '
            '"SUH" (Single Unit Houses) '
            'and "MUH" (Multi-unit Houses)')

    # Check code variant number
    if not isinstance(code_variantnumber, str):
        code_variantnumber = str(code_variantnumber).zfill(2)

    # prepare data
    data = {'systype': [code_country, code_boundarycond, code_variantnumber]}
    json_response = tabula_system_request(data)

    if json_response is not None:
        log('')
        # load data
        df = pd.DataFrame(json_response)
        return df.data.to_frame()
    else:
        raise ValueError('No data found in TABULA matrix with query:"{}"\nRun '
                         'archetypal.dataportal.tabula_available_buildings() '
                         'with country code "{}" to get list of possible '
                         'building types'
                         ''.format('.'.join(s for s in data['systype']),
                                   code_country))


def tabula_system_request(data):
    """

    Args:
        data (dict): prepared data for html query

    Returns:

    Examples:
        'http://webtool.building-typology.eu/data/matrix/system/detail/IT.SUH
        .01/dc/1546889637169'

    """
    system = '.'.join(s for s in data['systype'])
    hexint = hashlib.md5(system.encode('utf-8')).hexdigest()[0:13]

    log('quering system type {}'.format(system))
    prepared_url = 'http://webtool.building-typology.eu/data/matrix/system' \
                   '/detail/{0}/dc/{1}'.format(
        system, hexint)

    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json

    else:
        # if this URL is not already in the cache, pause, then request it
        response = requests.get(prepared_url)

        try:
            response_json = response.json()
            if 'remark' in response_json:
                log('Server remark: "{}"'.format(response_json['remark'],
                                                 level=lg.WARNING))
            save_to_cache(prepared_url, response_json)
        except Exception:
            # Handle some server errors
            pass
        else:
            return response_json


def get_from_cache(url):
    """

    Args:
        url:

    Returns:

    """
    # if the tool is configured to use the cache
    if settings.use_cache:
        # determine the filename by hashing the url
        filename = hashlib.md5(url.encode('utf-8')).hexdigest()

        cache_path_filename = os.path.join(settings.cache_folder,
                                           os.extsep.join([filename, 'json']))
        # open the cache file for this url hash if it already exists, otherwise
        # return None
        if os.path.isfile(cache_path_filename):
            with io.open(cache_path_filename, encoding='utf-8') as cache_file:
                response_json = json.load(cache_file)
            log('Retrieved response from cache file "{}" for URL "{}"'.format(
                cache_path_filename, url))
            return response_json


def save_to_cache(url, response_json):
    """

    Args:
        url:
        response_json:

    Returns:

    """
    if settings.use_cache:
        if response_json is None:
            log('Saved nothing to cache because response_json is None')
        else:
            # create the folder on the disk if it doesn't already exist
            if not os.path.exists(settings.cache_folder):
                os.makedirs(settings.cache_folder)

            # hash the url (to make filename shorter than the often extremely
            # long url)
            filename = hashlib.md5(url.encode('utf-8')).hexdigest()
            cache_path_filename = os.path.join(settings.cache_folder,
                                               os.extsep.join(
                                                   [filename, 'json']))
            # dump to json, and save to file
            json_str = make_str(json.dumps(response_json))
            with io.open(cache_path_filename, 'w',
                         encoding='utf-8') as cache_file:
                cache_file.write(json_str)

            log('Saved response to cache file "{}"'.format(cache_path_filename))


def openei_api_request(data, pause_duration=None, timeout=180,
                       error_pause_duration=None):
    """

    Args:
        data (dict or OrderedDict): key-value pairs of parameters to post to
            the API
        pause_duration:
        timeout (int): how long to pause in seconds before requests, if None,
            will query API status endpoint to find when next slot is available
        error_pause_duration (int): the timeout interval for the requests
            library

    Returns:
        dict
    """
    # define the Overpass API URL, then construct a GET-style URL as a string to
    # hash to look up/save to cache
    url = ' https://openei.org/services/api/content_assist/recommend'
    prepared_url = requests.Request('GET', url, params=data).prepare().url
    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json


# def openei_dataset_request(data):
#     'COMMERCIAL_LOAD_DATA_E_PLUS_OUTPUT'
#     'https://openei.org/datasets/files/961/pub/{}
#     'USA_AR_Batesville'
#     'AWOS'
#     '723448'
#     'RefBldgMediumOfficeNew2004'
#     '/{}.{}.{}_TMY3/{}_v1.3_7.1_3A_USA_GA_ATLANTA\
#         .csv'


def nrel_api_cbr_request(data):
    # define the Overpass API URL, then construct a GET-style URL as a string to
    # hash to look up/save to cache
    url = 'https://developer.nrel.gov/api/commercial-building-resources/v1' \
          '/resources.json'
    prepared_url = requests.Request('GET', url, params=data).prepare().url
    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json

    else:
        start_time = time.time()
        log('Getting from {}, "{}"'.format(url, data))
        response = requests.get(prepared_url)
        # if this URL is not already in the cache, pause, then request it
        # get the response size and the domain, log result
        size_kb = len(response.content) / 1000.
        domain = re.findall(r'//(?s)(.*?)/', url)[0]
        log('Downloaded {:,.1f}KB from {}'
            ' in {:,.2f} seconds'.format(size_kb, domain,
                                         time.time() - start_time))

        try:
            response_json = response.json()
            if 'remark' in response_json:
                log('Server remark: "{}"'.format(response_json['remark'],
                                                 level=lg.WARNING))
            save_to_cache(prepared_url, response_json)
        except Exception:
            # deal with response satus_code here
            log(
                'Server at {} returned status code {} and no JSON data.'.format(
                    domain,
                    response.status_code),
                level=lg.ERROR)
        else:
            return response_json


def nrel_bcl_api_request(data):
    """Send a request to the Building Component Library API via HTTP GET and
    return the JSON response.

    Args:
        data (dict or OrderedDict): key-value pairs of parameters to post to
            the API

    Returns:
        dict
    """
    try:
        kformat = data.pop('format')  # json or xml
        keyword = data.pop('keyword')
    except KeyError:
        url = 'https://bcl.nrel.gov/api/search/'
    else:
        url = 'https://bcl.nrel.gov/api/search/{}.{}'.format(keyword, kformat)
    prepared_url = requests.Request('GET', url, params=data).prepare().url
    print(prepared_url)
    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json

    else:
        start_time = time.time()
        log('Getting from {}, "{}"'.format(url, data))
        response = requests.get(prepared_url)
        # if this URL is not already in the cache, pause, then request it
        # get the response size and the domain, log result
        size_kb = len(response.content) / 1000.
        domain = re.findall(r'//(?s)(.*?)/', url)[0]
        log('Downloaded {:,.1f}KB from {}'
            ' in {:,.2f} seconds'.format(size_kb, domain,
                                         time.time() - start_time))

        try:
            response_json = response.json()
            if 'remark' in response_json:
                log('Server remark: "{}"'.format(response_json['remark'],
                                                 level=lg.WARNING))
            save_to_cache(prepared_url, response_json)
        except Exception:
            # deal with response satus_code here
            log(
                'Server at {} returned status code {} and no JSON data.'.format(
                    domain,
                    response.status_code),
                level=lg.ERROR)
            return response.content
        else:
            return response_json


def gis_server_raster_request(creds, bbox=None, how='intersects', srid=None,
                              output_type='Raster'):
    """

    Args:
        output_type:
        creds:
        bbox:
        how:
        srid:

    Returns:
        numpy.array

    Info:
        https://gis.stackexchange.com/questions/130139/downloading-raster
        -data-into-python-from-postgis-using-psycopg2
    """
    if gdal is None:
        raise ImportError('The osgeo package must be installed to use this '
                          'optional feature. recommended to use conda '
                          '*install gdal instead* of pip')

    username = creds.pop('username')
    password = creds.pop('password')
    server = creds.pop('server')
    db_name = creds.pop('db_name')
    tb_schema = creds.pop('schema')
    table_name = creds.pop('table_name')
    # create the engine string
    engine_str = 'postgresql://{}:{}@{}/{}'.format(username, password, server,
                                                   db_name)
    # instanciate the server engine
    engine = create_engine(engine_str)

    xmin, ymin, xmax, ymax = bbox.bounds

    if how.lower() == 'intersects':
        how = '&&'
    elif how.lower() == 'contains':
        how = '@'
    else:
        raise NameError('there is no spatial operator named {}. choose from '
                        '"intersets" or "contains"')

    # prepare the sql query
    sql = "SELECT ST_AsGDALRaster(ST_Union(rast), 'GTiff') As rast_gdal " \
          "FROM {schema}.{table_name} " \
          "WHERE " \
          "rast " \
          "{how} " \
          "ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax}, {my_srid})".format(
        schema=tb_schema,
        table_name=table_name,
        xmin=xmin,
        ymin=ymin,
        xmax=xmax,
        ymax=ymax,
        my_srid=srid,
        how=how)

    # Todo: seek raster data from cache instead of from gis server
    # # try to get results from cache
    # cached_response = get_from_cache(sql)
    #
    # if cached_response is not None:
    #     # found this request in the cache, just return it instead of making a
    #     # new sql call. We need to load id usin json.loads though.
    #     return gpd.GeoDataFrame.from_features(cached_response)

    # Use a virtual memory file, which is named like this
    vsipath = '/vsimem/from_postgis'

    # Download raster data into Python as GeoTIFF, and make a virtual file
    # for GDAL
    result = engine.execute(sql)

    try:
        gdal.FileFromMemBuffer(vsipath, bytes(result.fetchone()[0]))

        # Read first band of raster with GDAL
        ds = gdal.Open(vsipath)
        band = ds.GetRasterBand(1)
        arr = band.ReadAsArray()

    except Exception:
        # Close and clean up virtual memory file
        gdal.Unlink(vsipath)
        raise
    else:
        if output_type == 'Raster':
            gdal.Unlink(vsipath)
            return ds
        elif output_type == 'memory':
            return vsipath
        elif output_type == 'array':
            gdal.Unlink(vsipath)
            return arr


def gis_server_request(creds, bbox=None, how='intersects', srid=None):
    """Send a request to the GIS server via postgis SQL query and return the
    GeoDataFrame response.

    Args:
        creds (dict): credentials to connect with the database. Pass a dict
        containing the 'username', 'password', 'server', 'db_name',
        'tb_schema', 'engine_str
        bbox (shapely.geometry): Any shapely geometry that has bounds.
        how (str): the spatial operator to use. 'intersects' gets more rows
            while 'contains' gets fewer rows.
        srid (int): SRID. If no SRID is specified the unknown spatial
            reference system is assumed.

    Returns:
        geopandas.GeoDataFrame

    Info:
        * Originaly from <https://gis.stackexchange.com/questions/83387
        /performing-bounding-box-query-in-postgis>
    """
    username = creds.pop('username')
    password = creds.pop('password')
    server = creds.pop('server')
    db_name = creds.pop('db_name')
    tb_schema = creds.pop('schema')
    table_name = creds.pop('table_name')
    # create the engine string
    engine_str = 'postgresql://{}:{}@{}/{}'.format(username, password, server,
                                                   db_name)
    # instanciate the server engine
    engine = create_engine(engine_str)

    xmin, ymin, xmax, ymax = bbox.bounds

    if how.lower() == 'intersects':
        how = '&&'
    elif how.lower() == 'contains':
        how = '@'
    else:
        raise NameError('there is no spatial operator named {}. choose from '
                        '"intersets" or "contains"')

    sql = 'SELECT * FROM {schema}.{table_name} ' \
          'WHERE ' \
          'geom ' \
          '{how} ' \
          'ST_MakeEnvelope({xmin}, {ymin}, {xmax}, {ymax}, {my_srid})'.format(
        schema=tb_schema,
        table_name=table_name,
        xmin=xmin,
        ymin=ymin,
        xmax=xmax,
        ymax=ymax,
        my_srid=srid,
        how=how)
    cached_response_geojson = get_from_cache(sql)

    if cached_response_geojson is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call. We need to load id usin json.loads though.
        return gpd.GeoDataFrame.from_features(cached_response_geojson)

    else:
        start_time = time.time()
        log('Getting from from {}:{}.{}, "{}"'.format(server, tb_schema,
                                                      table_name, sql))
        gdf = gpd.read_postgis(sql, con=engine, geom_col='geom',
                               crs={'init': 'epsg:{srid}'.format(srid=srid)})
        size_kb = gdf.memory_usage(deep=True).sum() / 1000
        len_gdf = len(gdf)
        log('Downloaded {:,.1f} KB or {} entries from {}:{}.{} in '
            '{:,.2f} seconds'.format(size_kb, len_gdf, server, tb_schema,
                                     table_name, time.time() - start_time))
        if not gdf.empty:
            gdf_json = gdf.to_json()
            save_to_cache(sql, json.loads(gdf_json))  # must load the json
            # because because the save_to_cache handles to conversion
            # Todo: for some reason, rasterio does not like the gdf as is. so
            #  the workaournd is to spit out the json back into a new
            #  GeoDataFrame. Why?
            return gpd.GeoDataFrame.from_features(json.loads(gdf_json))
        else:
            log('No entries found. Check your parameters such as '
                'the bbox coordinates and the CRS', lg.ERROR)
            return gpd.GeoDataFrame([])  # return empty GeoDataFrame


def stat_can_request(data):
    prepared_url = 'https://www12.statcan.gc.ca/rest/census-recensement' \
                   '/CPR2016.{type}?lang={lang}&dguid={dguid}&topic=' \
                   '{topic}&notes={notes}'.format(
        type=data.get('type', 'json'),
        lang=data.get('land', 'E'),
        dguid=data.get('dguid', '2016A000011124'),
        topic=data.get('topic', 1),
        notes=data.get('notes', 0))

    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json

    else:
        # if this URL is not already in the cache, request it
        start_time = time.time()
        log('Getting from {}, "{}"'.format(prepared_url, data))
        response = requests.get(prepared_url)
        # if this URL is not already in the cache, pause, then request it
        # get the response size and the domain, log result
        size_kb = len(response.content) / 1000.
        domain = re.findall(r'//(?s)(.*?)/', prepared_url)[0]
        log('Downloaded {:,.1f}KB from {}'
            ' in {:,.2f} seconds'.format(size_kb, domain,
                                         time.time() - start_time))

        try:
            response_json = response.json()
            if 'remark' in response_json:
                log('Server remark: "{}"'.format(response_json['remark'],
                                                 level=lg.WARNING))
            save_to_cache(prepared_url, response_json)

        except Exception:
            # There seems to be a double backlash in the response. We try
            # removing it here.
            try:
                response = response.content.decode('UTF-8').replace('//',
                                                                    '')
                response_json = json.loads(response)
            except Exception:
                log(
                    'Server at {} returned status code {} and no JSON '
                    'data.'.format(
                        domain,
                        response.status_code),
                    level=lg.ERROR)
            else:
                save_to_cache(prepared_url, response_json)
                return response_json
            # deal with response satus_code here
            log('Server at {} returned status code {} and no JSON '
                'data.'.format(
                    domain, response.status_code), level=lg.ERROR)
        else:
            return response_json


def stat_can_geo_request(data):
    prepared_url = 'https://www12.statcan.gc.ca/rest/census-recensement' \
                   '/CR2016Geo.{type}?lang={lang}&geos={geos}&cpt={cpt}'.format(
        type=data.get('type', 'json'),
        lang=data.get('land', 'E'),
        geos=data.get('geos', 'PR'),
        cpt=data.get('cpt', '00'))

    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json

    else:
        # if this URL is not already in the cache, request it
        start_time = time.time()
        log('Getting from {}, "{}"'.format(prepared_url, data))
        response = requests.get(prepared_url)
        # if this URL is not already in the cache, pause, then request it
        # get the response size and the domain, log result
        size_kb = len(response.content) / 1000.
        domain = re.findall(r'//(?s)(.*?)/', prepared_url)[0]
        log('Downloaded {:,.1f}KB from {}'
            ' in {:,.2f} seconds'.format(size_kb, domain,
                                         time.time() - start_time))

        try:
            response_json = response.json()
            if 'remark' in response_json:
                log('Server remark: "{}"'.format(response_json['remark'],
                                                 level=lg.WARNING))
            save_to_cache(prepared_url, response_json)

        except Exception:
            # There seems to be a double backlash in the response. We try
            # removing it here.
            try:
                response = response.content.decode('UTF-8').replace('//',
                                                                    '')
                response_json = json.loads(response)
            except Exception:
                log(
                    'Server at {} returned status code {} and no JSON '
                    'data.'.format(
                        domain,
                        response.status_code),
                    level=lg.ERROR)
            else:
                save_to_cache(prepared_url, response_json)
                return response_json
            # deal with response satus_code here
            log('Server at {} returned status code {} and no JSON '
                'data.'.format(
                    domain, response.status_code), level=lg.ERROR)
        else:
            return response_json
