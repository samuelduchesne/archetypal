################################################################################
# Module: dataportal.py
# Description: Various functions to acquire building archetype data using
#              available APIs
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import hashlib
import io
import json
import logging as lg
import os
import re
import time
import zipfile

import pandas as pd
import pycountry as pycountry
import requests

from archetypal import settings
from archetypal.utils import log


def tabula_available_buildings(country_name="France"):
    """Returns all available building types for a specific country.

    Args:
        country_name (str): The name of the country. pycountry is used to
            resolve country names. Therefore, a country code (e.g. "FRA") can be
            passed as well.
    """
    # Check code country
    code_country = _resolve_codecountry(country_name)
    data = {"code_country": code_country}
    json_response = tabula_api_request(data, table="all-country")

    # load data
    df = pd.DataFrame(json_response)
    df = df.data.apply(pd.Series)
    return df


def tabula_api_request(data, table="detail"):
    """Send a request to the TABULA API via HTTP GET and return the JSON
    response.

    Args:
        data (dict): dictionnary of query attributes. with table='all-country',
            data expects 'code_country'. with table='detail', data expects
            'buildingtype', 'suffix', and 'variant'.
        table (str): the server-table to query. 'detail' or 'all-country'
    """
    # Prepare URL
    if table == "all-country":
        codehex = str(
            int(hashlib.md5(data["code_country"].encode("utf-8")).hexdigest(), 16)
        )[0:13]
        url_base = (
            "http://webtool.building-typology.eu/data/matrix/building"
            "/{0}/p/0/o/0/l/10/dc/{1}"
        )
        prepared_url = url_base.format(data["code_country"], codehex)

    elif table == "detail":
        buildingtype = ".".join(s for s in data["buildingtype"])
        suffix = ".".join(s for s in data["suffix"])
        bldname = buildingtype + "." + suffix
        hexint = hashlib.md5(bldname.encode("utf-8")).hexdigest()[0:13]
        url_base = (
            "http://webtool.building-typology.eu/data/adv/building"
            "/detail/{0}/bv/{1}/dc/{2}"
        )
        prepared_url = url_base.format(bldname, data["variant"], hexint)

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
            if "remark" in response_json:
                log(
                    'Server remark: "{}"'.format(
                        response_json["remark"], level=lg.WARNING
                    )
                )
            elif not response_json["success"]:
                raise ValueError(
                    'The query "{}" returned no results'.format(prepared_url),
                    lg.WARNING,
                )
            save_to_cache(prepared_url, response_json)
            return response_json
        else:
            # Handle some server errors
            pass


def tabula_building_details_sheet(
    code_building=None,
    code_country="FR",
    code_typologyregion="N",
    code_buildingsizeclass="SFH",
    code_construcionyearclass=1,
    code_additional_parameter="Gen",
    code_type="ReEx",
    code_num=1,
    code_variantnumber=1,
):
    """How to format ``code_building``. Format the :attr:`code_building` string
    as such:

    Args:
        code_building (str): The building code string.

            ::

                Whole building code e.g.:

                AT.MT.AB.02.Gen.ReEx.001.001"
                 |  |  |  |   |   |   |   |___code_variantnumber
                 |  |  |  |   |   |   |_______code_num
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
        code_construcionyearclass (int or str): allocation of time bands to
            classes. Defined nationally (according to significant changes in
            construction technologies, building codes or available statistical
            data
        code_additional_parameter (str): 1 unique category. Defines the generic
            (or basic) typology matrix so that each residential building of a
            given country can be assigned to one generic type. A further
            segmentation in subtypes is possible and can be indicated by a
            specific code. Whereas the generic types must comprise the whole
            building stock the total of subtypes must be comprehensive. e.g.
            'HR' (highrises), 'TFrame' (timber frame), 'Semi' (semi-detached)
        code_type: “ReEx” is a code for “real example” and “SyAv” for
            “Synthetical Average”
        code_num: TODO: What is this parameter?
        code_variantnumber: the energy performance level 1, 2 and 3. 1: minimum
            requirements, 2: improved and 3: ambitious or NZEB standard (assumed
            or announced level of Nearly Zero-Energy Buildings)

    Returns:
        pandas.DataFrame: The DataFrame from the
    """
    # Parse builsing_code
    if code_building is not None:
        try:
            (
                code_country,
                code_typologyregion,
                code_buildingsizeclass,
                code_construcionyearclass,
                code_additional_parameter,
                code_type,
                code_num,
                code_variantnumber,
            ) = code_building.split(".")
        except ValueError:
            msg = (
                'the query "{}" is missing a parameter. Make sure the '
                '"code_building" has the form: '
                "AT.MT.AB.02.Gen.ReEx.001.001"
            ).format(code_building)
            log(msg, lg.ERROR)
            raise ValueError(msg)

    # Check code country
    code_country = _resolve_codecountry(code_country)

    # Check code_buildingsizeclass
    if code_buildingsizeclass.upper() not in ["SFH", "TH", "MFH", "AB"]:
        raise ValueError(
            'specified code_buildingsizeclass "{}" not supported. Available '
            'values are "SFH", "TH", '
            '"MFH" or "AB"'
        )
    # Check numericals
    if not isinstance(code_construcionyearclass, str):
        code_construcionyearclass = str(code_construcionyearclass).zfill(2)

    if not isinstance(code_num, str):
        code_num = str(code_num).zfill(3)

    if not isinstance(code_variantnumber, str):
        code_variantnumber = str(code_variantnumber).zfill(3)

    # prepare data
    data = {
        "buildingtype": [
            code_country,
            code_typologyregion,
            code_buildingsizeclass,
            code_construcionyearclass,
            code_additional_parameter,
        ],
        "suffix": [code_type, code_num],
        "variant": code_variantnumber,
    }
    json_response = tabula_api_request(data, table="detail")

    if json_response is not None:
        log("")
        # load data
        df = pd.DataFrame(json_response)
        df = df.data.apply(pd.Series)

        # remove html tags from labels
        df.label = df.label.str.replace("<[^<]+?>", " ")
        return df
    else:
        raise ValueError(
            'No data found in TABULA matrix with query:"{}"\nRun '
            "archetypal.dataportal.tabula_available_buildings() "
            'with country code "{}" to get list of possible '
            "building types"
            "".format(".".join(s for s in data["buildingtype"]), code_country)
        )


def tabula_system(code_country, code_boundarycond="SUH", code_variantnumber=1):
    """Return system level information from TABULA archetypes.

    Args:
        code_country (str): the alpha-2 code of the country. eg. "FR"
        code_boundarycond (str): choices are "SUH" and "MUH".
        code_variantnumber (int):

    """
    # Check code country
    code_country = _resolve_codecountry(code_country)

    # Check code_buildingsizeclass
    if code_boundarycond.upper() not in ["SUH", "MUH"]:
        raise ValueError(
            'specified code_boundarycond "{}" not valid. Available values are '
            '"SUH" (Single Unit Houses) '
            'and "MUH" (Multi-unit Houses)'
        )

    # Check code variant number
    if not isinstance(code_variantnumber, str):
        code_variantnumber = str(code_variantnumber).zfill(2)

    # prepare data
    data = {"systype": [code_country, code_boundarycond, code_variantnumber]}
    json_response = tabula_system_request(data)

    if json_response is not None:
        log("")
        # load data
        df = pd.DataFrame(json_response)
        return df.data.to_frame()
    else:
        raise ValueError(
            'No data found in TABULA matrix with query:"{}"\nRun '
            "archetypal.dataportal.tabula_available_buildings() "
            'with country code "{}" to get list of possible '
            "building types"
            "".format(".".join(s for s in data["systype"]), code_country)
        )


def tabula_system_request(data):
    """Returns:

    Examples:
        'http://webtool.building-typology.eu/data/matrix/system/detail/IT.SUH.01/dc/1546889637169'

    Args:
        data (dict): prepared data for html query
    """
    system = ".".join(s for s in data["systype"])
    hexint = hashlib.md5(system.encode("utf-8")).hexdigest()[0:13]

    log("quering system type {}".format(system))
    prepared_url = (
        "http://webtool.building-typology.eu/data/matrix/system"
        "/detail/{0}/dc/{1}".format(system, hexint)
    )

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
            if "remark" in response_json:
                log(
                    'Server remark: "{}"'.format(
                        response_json["remark"], level=lg.WARNING
                    )
                )
            save_to_cache(prepared_url, response_json)
        except Exception:
            # Handle some server errors
            pass
        else:
            return response_json


def _resolve_codecountry(code_country):
    """check country name against pycountry and return alpha_2 code

    Args:
        code_country:
    """
    if isinstance(code_country, int):
        code_country = pycountry.countries.get(numeric=str(code_country))
    elif len(code_country) == 2:
        code_country = pycountry.countries.get(alpha_2=code_country)
    elif len(code_country) == 3:
        code_country = pycountry.countries.get(alpha_3=code_country)
    else:
        code_country = pycountry.countries.get(name=code_country)

    if code_country is not None:
        # if country is valid, return ISO 3166-1-alpha-2 code
        code_country = code_country.alpha_2
    else:
        raise ValueError("Country name {} is invalid".format(code_country))
    return code_country


def get_from_cache(url):
    """
    Args:
        url:
    """
    # if the tool is configured to use the cache
    if settings.use_cache:
        # determine the filename by hashing the url
        filename = hashlib.md5(str(url).encode("utf-8")).hexdigest()

        cache_path_filename = os.path.join(
            settings.cache_folder, os.extsep.join([filename, "json"])
        )
        # open the cache file for this url hash if it already exists, otherwise
        # return None
        if os.path.isfile(cache_path_filename):
            with io.open(cache_path_filename, encoding="utf-8") as cache_file:
                response_json = json.load(cache_file)
            log(
                'Retrieved response from cache file "{}" for URL "{}"'.format(
                    cache_path_filename, str(url)
                )
            )
            return response_json


def save_to_cache(url, response_json):
    """
    Args:
        url:
        response_json:
    """
    if settings.use_cache:
        if response_json is None:
            log("Saved nothing to cache because response_json is None")
        else:
            # create the folder on the disk if it doesn't already exist
            if not os.path.exists(settings.cache_folder):
                os.makedirs(settings.cache_folder)

            # hash the url (to make filename shorter than the often extremely
            # long url)
            filename = hashlib.md5(str(url).encode("utf-8")).hexdigest()
            cache_path_filename = os.path.join(
                settings.cache_folder, os.extsep.join([filename, "json"])
            )
            # dump to json, and save to file
            json_str = json.dumps(response_json)
            with io.open(cache_path_filename, "w", encoding="utf-8") as cache_file:
                cache_file.write(json_str)

            log('Saved response to cache file "{}"'.format(cache_path_filename))


def openei_api_request(
    data,
):
    """Query the OpenEI.org API.

    Args:
        data (dict or OrderedDict): key-value pairs of parameters to post to the
            API.

    Returns:
        dict: the json response
    """
    # define the Overpass API URL, then construct a GET-style URL as a string to
    # hash to look up/save to cache
    url = " https://openei.org/services/api/content_assist/recommend"
    prepared_url = requests.Request("GET", url, params=data).prepare().url
    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json


def nrel_api_cbr_request(data):
    """Query the NREL Commercial Building Resource Database

    Examples:
        >>> from archetypal import dataportal
        >>> dataportal.nrel_api_cbr_request({'s': 'Commercial'
        >>> 'Reference', 'api_key': 'oGZdX1nhars1cTJYTm7M9T12T1ZOvikX9pH0Zudq'})

    Args:
        data: a dict of

    Returns:
        dict: the json response

    Hint:
        For a detailed description of data arguments, visit
        `Commercial Building Resource API <https://developer.nrel.gov/docs/buildings
        /commercial-building-resource-database-v1/resources/>`_
    """
    # define the Overpass API URL, then construct a GET-style URL as a string to
    # hash to look up/save to cache
    url = (
        "https://developer.nrel.gov/api/commercial-building-resources/v1"
        "/resources.json"
    )
    prepared_url = requests.Request("GET", url, params=data).prepare().url
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
        size_kb = len(response.content) / 1000.0
        domain = re.findall(r"//(?s)(.*?)/", url)[0]
        log(
            "Downloaded {:,.1f}KB from {}"
            " in {:,.2f} seconds".format(size_kb, domain, time.time() - start_time)
        )

        try:
            response_json = response.json()
            if "remark" in response_json:
                log(
                    'Server remark: "{}"'.format(
                        response_json["remark"], level=lg.WARNING
                    )
                )
            elif "error" in response_json:
                log(
                    "Server at {} returned status code {} meaning {}.".format(
                        domain, response.status_code, response_json["error"]["code"]
                    ),
                    level=lg.ERROR,
                )
            else:
                pass
            save_to_cache(prepared_url, response_json)
        except Exception:
            # deal with response satus_code here
            log(
                "Server at {} returned status code {} and no JSON data.".format(
                    domain, response.status_code
                ),
                level=lg.ERROR,
            )
        else:
            return response_json


def nrel_bcl_api_request(data):
    """Send a request to the Building Component Library API via HTTP GET and
    return the JSON response.

    Args:
        data (dict or OrderedDict): key-value pairs of parameters to post to the
            API

    Returns:
        dict: the json response
    """
    try:
        kformat = data.pop("format")  # json or xml
        keyword = data.pop("keyword")
    except KeyError:
        url = "https://bcl.nrel.gov/api/search/"
    else:
        url = "https://bcl.nrel.gov/api/search/{}.{}".format(keyword, kformat)
    prepared_url = requests.Request("GET", url, params=data).prepare().url
    log(prepared_url)
    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json

    else:
        start_time = time.time()
        log('Getting from {}, "{}"'.format(url, data))
        response = requests.get(prepared_url)

        # check if an error has occurred
        response.raise_for_status()

        # if this URL is not already in the cache, pause, then request it
        # get the response size and the domain, log result
        size_kb = len(response.content) / 1000.0
        domain = re.findall(r"//(?s)(.*?)/", url)[0]
        log(
            "Downloaded {:,.1f}KB from {}"
            " in {:,.2f} seconds".format(size_kb, domain, time.time() - start_time)
        )

        # Since raise_for_status has not raised any error, we can check the response
        # json safely
        response_json = response.json()
        if "remark" in response_json:
            log('Server remark: "{}"'.format(response_json["remark"], level=lg.WARNING))
        save_to_cache(prepared_url, response_json)
        return response_json


def stat_can_request(type, lang="E", dguid="2016A000011124", topic=0, notes=0, stat=0):
    """Send a request to the StatCan API via HTTP GET and return the JSON
    response.

    Args:
        type (str): "json" or "xml". json = json response format and xml = xml
            response format.
        lang (str): "E" or "F". E = English and F = French.
        dguid (str): Dissemination Geography Unique Identifier - DGUID. It is an
            alphanumeric code, composed of four components. It varies from 10 to
            21 characters in length. The first 9 characters are fixed in
            composition and length. Vintage (4) + Type (1) + Schema (4) +
            Geographic Unique Identifier (1-12). To find dguid, use any GEO_UID
            ( i.e., DGUID) returned by the 2016 Census geography web data
            service. For more information on the DGUID definition and structure,
            please refer to the `Dissemination Geography Unique Identifier,
            Definition and Structure
            <https://www150.statcan.gc.ca/n1/pub/92f0138m/92f0138m2019001-eng.htm>`_ ,
            Statistics Canada catalogue no. 92F0138M-2019001.
        topic (str): Integer 0-14 (default=0) where: 1. All topics 2. Aboriginal
            peoples 3. Education 4. Ethnic origin 5. Families, households and
            marital status 6. Housing 7. Immigration and citizenship 8. Income
            9. Journey to work 10. Labour 11. Language 12. Language of work 13.
            Mobility 14. Population 15. Visible minority.
        notes (int): 0 or 1. 0 = do not include footnotes. 1 = include
            footnotes.
        stat (int): 0 or 1. 0 = counts. 1 = rates.
    """
    prepared_url = (
        "https://www12.statcan.gc.ca/rest/census-recensement"
        "/CPR2016.{type}?lang={lang}&dguid={dguid}&topic="
        "{topic}&notes={notes}&stat={stat}".format(
            type=type, lang=lang, dguid=dguid, topic=topic, notes=notes, stat=stat
        )
    )

    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json

    else:
        # if this URL is not already in the cache, request it
        start_time = time.time()
        log("Getting from {}".format(prepared_url))
        response = requests.get(prepared_url)
        # if this URL is not already in the cache, pause, then request it
        # get the response size and the domain, log result
        size_kb = len(response.content) / 1000.0
        domain = re.findall(r"//(?s)(.*?)/", prepared_url)[0]
        log(
            "Downloaded {:,.1f}KB from {}"
            " in {:,.2f} seconds".format(size_kb, domain, time.time() - start_time)
        )

        try:
            response_json = response.json()
            if "remark" in response_json:
                log(
                    'Server remark: "{}"'.format(
                        response_json["remark"], level=lg.WARNING
                    )
                )
            save_to_cache(prepared_url, response_json)

        except Exception:
            # There seems to be a double backlash in the response. We try
            # removing it here.
            try:
                response_str = response.content.decode("UTF-8").replace("//", "")
                response_json = json.loads(response_str)
            except Exception:
                pass
            else:
                save_to_cache(prepared_url, response_json)
                return response_json
            # deal with response status_code here
            log(
                "Server at {} returned status code {} and no JSON "
                "data.".format(domain, response.status_code),
                level=lg.ERROR,
            )
        else:
            return response_json


def stat_can_geo_request(type="json", lang="E", geos="PR", cpt="00"):
    """
    Args:
        type (str): "json" or "xml". json = json response format and xml = xml
            response format.
        lang (str): "E" or "F". where: E = English F = French.
        geos (str): one geographic level code (default = PR). where: CD = Census
            divisions CMACA = Census metropolitan areas and census
            agglomerations CSD = Census subdivisions (municipalities) CT =
            Census tracts DA = Dissemination areas DPL = Designated places ER =
            Economic regions FED = Federal electoral districts (2013
            Representation Order) FSA = Forward sortation areas HR = Health
            regions (including LHINs and PHUs) POPCNTR = Population centres PR =
            Canada, provinces and territories.
        cpt (str): one province or territory code (default = 00). where: 00 =
            All provinces and territories 10 = Newfoundland and Labrador 11 =
            Prince Edward Island 12 = Nova Scotia 13 = New Brunswick 24 = Quebec
            35 = Ontario 46 = Manitoba 47 = Saskatchewan 48 = Alberta 59 =
            British Columbia 60 = Yukon 61 = Northwest Territories 62 = Nunavut.
    """
    prepared_url = (
        "https://www12.statcan.gc.ca/rest/census-recensement"
        "/CR2016Geo.{type}?lang={lang}&geos={geos}&cpt={cpt}".format(
            type=type, lang=lang, geos=geos, cpt=cpt
        )
    )

    cached_response_json = get_from_cache(prepared_url)

    if cached_response_json is not None:
        # found this request in the cache, just return it instead of making a
        # new HTTP call
        return cached_response_json

    else:
        # if this URL is not already in the cache, request it
        start_time = time.time()
        log("Getting from {}".format(prepared_url))
        response = requests.get(prepared_url)
        # if this URL is not already in the cache, pause, then request it
        # get the response size and the domain, log result
        size_kb = len(response.content) / 1000.0
        domain = re.findall(r"//(?s)(.*?)/", prepared_url)[0]
        log(
            "Downloaded {:,.1f}KB from {}"
            " in {:,.2f} seconds".format(size_kb, domain, time.time() - start_time)
        )

        try:
            response_json = response.json()
            if "remark" in response_json:
                log(
                    'Server remark: "{}"'.format(
                        response_json["remark"], level=lg.WARNING
                    )
                )
            save_to_cache(prepared_url, response_json)

        except Exception:
            # There seems to be a double backlash in the response. We try
            # removing it here.
            try:
                response_str = response.content.decode("UTF-8").replace("//", "")
                response_json = json.loads(response_str)
            except Exception as e:
                log(
                    f"Error {e}\n"
                    f"Server at {domain} returned status code {response.status_code} "
                    f"and no JSON data.",
                    level=lg.ERROR,
                )
                return {}
            else:
                save_to_cache(prepared_url, response_json)
                return response_json
        else:
            return response_json


def download_bld_window(
    u_factor,
    shgc,
    vis_trans,
    oauth_key,
    tolerance=0.05,
    extension="idf",
    output_folder=None,
):
    """Find window constructions corresponding to a combination of a u_factor,
    shgc and visible transmittance and download their idf file to disk. it is
    necessary to have an authentication key (see Info below).

    .. _Building_Component_Library: https://bcl.nrel.gov/user/register

    Args:
        u_factor (float or tuple): The center of glass u-factor. Pass a range of
            values by passing a tuple (from, to). If a tuple is passed,
            *tolerance* is ignored.
        shgc (float or tuple): The Solar Heat Gain Coefficient. Pass a range of
            values by passing a tuple (from, to). If a tuple is passed,
            *tolerance* is ignored.
        vis_trans (float or tuple): The Visible Transmittance. Pass a range of
            values by passing a tuple (from, to). If a tuple is passed,
            *tolerance* is ignored.
        oauth_key (str): the Building_Component_Library_ authentication key.
        tolerance (float): relative tolerance for the input values. Default is
            0.05 (5%).
        extension (str): specify the extension of the file to download.
            (default: 'idf')
        output_folder (str, optional): specify folder to save response data to.
            Defaults to settings.data_folder.

    Returns:
        (list of archetypal.IDF): a list of IDF files containing window objects
            matching the parameters.

    Note:
        An authentication key from NREL is required to download building
        components. Register at Building_Component_Library_
    """
    # check if one or multiple values
    if isinstance(u_factor, tuple):
        u_factor_dict = "[{} TO {}]".format(u_factor[0], u_factor[1])
    else:
        # apply tolerance
        u_factor_dict = "[{} TO {}]".format(
            u_factor * (1 - tolerance), u_factor * (1 + tolerance)
        )
    if isinstance(shgc, tuple):
        shgc_dict = "[{} TO {}]".format(shgc[0], shgc[1])
    else:
        # apply tolerance
        shgc_dict = "[{} TO {}]".format(shgc * (1 - tolerance), shgc * (1 + tolerance))
    if isinstance(vis_trans, tuple):
        vis_trans_dict = "[{} TO {}]".format(vis_trans[0], vis_trans[1])
    else:
        # apply tolerance
        vis_trans_dict = "[{} TO {}]".format(
            vis_trans * (1 - tolerance), vis_trans * (1 + tolerance)
        )

    data = {
        "keyword": "Window",
        "format": "json",
        "f[]": [
            "fs_a_Overall_U-factor:{}".format(u_factor_dict),
            "fs_a_VLT:{}".format(vis_trans_dict),
            "fs_a_SHGC:{}".format(shgc_dict),
            'sm_component_type:"Window"',
        ],
        "oauth_consumer_key": oauth_key,
    }
    response = nrel_bcl_api_request(data)

    if response:
        log(
            "found {} possible window component(s) matching "
            "the range {}".format(len(response["result"]), str(data["f[]"]))
        )

        # download components
        uids = []
        for component in response["result"]:
            uids.append(component["component"]["uid"])
        url = "https://bcl.nrel.gov/api/component/download?uids={}".format(
            "," "".join(uids)
        )
        # actual download with get()
        d_response = requests.get(url)

        if d_response.ok:
            # loop through files and extract the ones that match the extension
            # parameter
            results = []
            if output_folder is None:
                output_folder = settings.data_folder
            with zipfile.ZipFile(io.BytesIO(d_response.content)) as z:
                for info in z.infolist():
                    if info.filename.endswith(extension):
                        z.extract(info, path=output_folder)
                        results.append(
                            os.path.join(settings.data_folder, info.filename)
                        )
            return results
        else:
            return response["result"]
    else:
        raise ValueError(
            "Could not download window from NREL Building Components "
            "Library. An error occurred with the nrel_api_request"
        )
