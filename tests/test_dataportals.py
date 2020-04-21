import os

import pytest

import archetypal as ar
import pandas as pd

from archetypal import download_bld_window, settings


def test_tabula_available_country(config, scratch_then_cache):
    # First, let's try the API call
    data = {"code_country": "FR"}
    cc_res = ar.dataportal.tabula_api_request(data, table="all-country")

    # Then let's use the user-friendly call. Since it is the second call to the
    # same function, the response should be read from the cache.
    code_country = "FR"
    cc_cache = ar.dataportal.tabula_available_buildings(code_country)


def test_tabula_api_request_valueerror(config, scratch_then_cache):
    # Gives "wrong_string" as table
    data = {"code_country": "FR"}
    with pytest.raises(ValueError):
        cc_res = ar.dataportal.tabula_api_request(data, table="wrong_string")

    # Gives "wrong_string" as country
    data = {"code_country": "wrong_string"}
    with pytest.raises(ValueError):
        cc_res = ar.dataportal.tabula_api_request(data, table="all-country")


def test_tabula_notavailable_country(config, scratch_then_cache):
    pass


def test_tabula_building_sheet(config, scratch_then_cache):
    sheet = ar.tabula_building_details_sheet(code_country="Austria")


def test_tabula_building_sheet_code_building(config, scratch_then_cache):
    # Test with code_building not None
    sheet = ar.tabula_building_details_sheet(
        code_building="AT.MT.AB.02.Gen.ReEx.001.001", code_country="Austria"
    )


def test_tabula_building_sheet_valueerror(config, scratch_then_cache):
    # Test with wrong code_building
    with pytest.raises(ValueError):
        sheet = ar.tabula_building_details_sheet(
            code_building="wrong_string", code_country="Austria"
        )

    # Test with wrong code_buildingsizeclass
    with pytest.raises(ValueError):
        sheet = ar.tabula_building_details_sheet(
            code_buildingsizeclass="wrong_string", code_country="Austria"
        )

    # Test with wrong code_country
    with pytest.raises(ValueError):
        sheet = ar.tabula_building_details_sheet(code_country="wrong_string",)


def test_tabula_system(config, scratch_then_cache):
    res = ar.dataportal.tabula_system(code_country="FR")


def test_tabula_system_valueerror(config, scratch_then_cache):
    # Test with wrong code_boundarycond
    with pytest.raises(ValueError):
        res = ar.dataportal.tabula_system(
            code_country="FR", code_boundarycond="wrong_string"
        )


def test_resolve_codecountry(config, scratch_then_cache):
    # Tests with country string length == 3
    res = ar.dataportal._resolve_codecountry("USA")

    # Tests with country number (integer)
    res = ar.dataportal._resolve_codecountry(533)


def test_openei_api_request(config, scratch_then_cache):
    data = {"code_country": "FR"}
    res = ar.dataportal.openei_api_request(data)


def test_tabula_multiple(config, scratch_then_cache):
    country_code = "FR"
    ab = ar.dataportal.tabula_available_buildings(country_code)
    archetypes = pd.concat(
        ab.apply(
            lambda x: ar.tabula_building_details_sheet(
                code_building=x.code_buildingtype_column1
                + "."
                + x.suffix_building_column1
                + ".001"
            ),
            axis=1,
        ).values.tolist(),
        keys=ab.code_buildingtype_column1 + "." + ab.suffix_building_column1,
    )


@pytest.mark.xfail(
    condition=os.environ.get("NREL_CONSUMER_KEY") is None,
    reason="Must provide an NREL API key as ENV Variable 'NREL_CONSUMER_KEY'",
    strict=True,
)
def test_nrel_api_request(config, scratch_then_cache):
    data = {
        "keyword": "Window",
        "format": "json",
        "f[]": ["fs_a_Overall_U-factor:[3.4 TO 3.6]", 'sm_component_type:"Window"'],
        "oauth_consumer_key": os.environ.get("NREL_CONSUMER_KEY"),
    }

    response = ar.dataportal.nrel_bcl_api_request(data)
    assert response["result"]


@pytest.mark.xfail(
    condition=os.environ.get("NREL_CONSUMER_KEY") is None,
    reason="Must provide an NREL API key as ENV Variable 'NREL_CONSUMER_KEY'",
    strict=True,
)
def test_download_bld_window(config, scratch_then_cache):
    oauth_consumer_key = os.environ.get("NREL_CONSUMER_KEY")

    response = download_bld_window(
        u_factor=3.18,
        shgc=0.49,
        vis_trans=0.53,
        oauth_key=oauth_consumer_key,
        tolerance=0.05,
    )
    assert response


@pytest.mark.xfail(
    condition=os.environ.get("NREL_CONSUMER_KEY") is None,
    reason="Must provide an NREL API key as ENV Variable 'NREL_CONSUMER_KEY'",
    strict=True,
)
def test_download_and_load_bld_window(clean_config):
    """Download window and load its idf file"""
    oauth_consumer_key = os.environ.get("NREL_CONSUMER_KEY")

    response = download_bld_window(
        u_factor=3.18,
        shgc=0.49,
        vis_trans=0.53,
        oauth_key=oauth_consumer_key,
        tolerance=0.05,
    )
    idf = ar.load_idf(response[0], ep_version=settings.ep_version)
    construct = idf.getobject("CONSTRUCTION", "AEDG-SmOffice 1A Window Fixed")
    ws = ar.WindowSetting.from_construction(Name="test_window", Construction=construct)

    assert ws


def test_statcan(config, scratch_then_cache):
    data = dict(type="json", lang="E", dguid="2016A000011124", topic=5, notes=0)
    response = ar.dataportal.stat_can_request(**data)
    print(response)


def test_statcan_error(config, scratch_then_cache):
    # Tests statcan with error in inputs
    data = dict(type="json", lang="E", dguid="wrong_string", topic=5, notes=0)
    response = ar.dataportal.stat_can_request(**data)
    print(response)


def test_statcan_geo(config, scratch_then_cache):
    data = dict(type="json", lang="E", geos="PR", cpt="00")
    response = ar.dataportal.stat_can_geo_request(**data)
    print(response)


def test_statcan_geo_error(config, scratch_then_cache):
    # Tests statcan_geo with error in inputs
    data = dict(type="json", lang="E", geos="wrong_string", cpt="00")
    response = ar.dataportal.stat_can_geo_request(**data)
    print(response)
