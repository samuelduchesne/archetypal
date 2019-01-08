import hashlib
import io
import json
import logging as lg
import os

import pandas as pd
import pycountry as pycountry
import requests

from archetypal import log, settings, make_str


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
            given
            country can be assigned to one generic type. A further
            segmentation in
            subtypes is  possible and can be indicated by a specific code.
            Whereas
            the generic types must comprise the whole building stock the
            total of
            subtypes must be comprehensive. e.g. 'HR' (highrises), 'TFrame' (
            timber
            frame), 'Semi' (semi-detached)
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
