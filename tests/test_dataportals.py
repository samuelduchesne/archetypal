import os

import pandas as pd
import pytest

from archetypal import IDF, dataportal
from archetypal.dataportal import download_bld_window, tabula_building_details_sheet
from archetypal.template.window_setting import WindowSetting


def test_tabula_available_country(config):
    # First, let's try the API call
    data = {"code_country": "FR"}
    cc_res = dataportal.tabula_api_request(data, table="all-country")
    # Makes sure data is not empty
    assert cc_res["data"]

    # Then let's use the user-friendly call. Since it is the second call to the
    # same function, the response should be read from the cache.
    code_country = "FR"
    cc_cache = dataportal.tabula_available_buildings(code_country)
    # Makes sure result is not empty
    assert list(cc_cache["id"])


def test_tabula_api_request_valueerror(config):
    # Gives "wrong_string" as table
    data = {"code_country": "FR"}
    with pytest.raises(ValueError):
        cc_res = dataportal.tabula_api_request(data, table="wrong_string")
    # Makes sure cc_res not in locals
    assert "cc_res" not in locals()

    # Gives "wrong_string" as country
    data = {"code_country": "wrong_string"}
    with pytest.raises(ValueError):
        cc_res = dataportal.tabula_api_request(data, table="all-country")
    # Makes sure cc_res not in locals
    assert "cc_res" not in locals()


def test_tabula_notavailable_country(config):
    pass


def test_tabula_building_sheet(config):
    sheet = tabula_building_details_sheet(code_country="Austria")

    # Makes sure result is not empty
    assert list(sheet["val"])


def test_tabula_building_sheet_code_building(config):
    # Test with code_building not None
    sheet = tabula_building_details_sheet(
        code_building="AT.MT.AB.02.Gen.ReEx.001.001", code_country="Austria"
    )

    # Makes sure result is not empty
    assert list(sheet["val"])
    # Make sure code_building is right
    assert sheet["val"][0] == "AT.MT.AB.02.Gen.ReEx.001.001"


def test_tabula_building_sheet_valueerror(config):
    # Test with wrong code_building
    with pytest.raises(ValueError):
        sheet = tabula_building_details_sheet(
            code_building="wrong_string", code_country="Austria"
        )
    # Makes sure sheet not in locals
    assert "sheet" not in locals()

    # Test with wrong code_buildingsizeclass
    with pytest.raises(ValueError):
        sheet = tabula_building_details_sheet(
            code_buildingsizeclass="wrong_string", code_country="Austria"
        )
    # Makes sure sheet not in locals
    assert "sheet" not in locals()

    # Test with wrong code_country
    with pytest.raises(ValueError):
        sheet = tabula_building_details_sheet(code_country="wrong_string")
    # Makes sure sheet not in locals
    assert "sheet" not in locals()


def test_tabula_system(config):
    res = dataportal.tabula_system(code_country="FR")

    # Makes sure result is not empty
    assert list(res["data"])
    # Makes sure code_country is right
    assert res["data"][0] == "FR"


def test_tabula_system_valueerror(config):
    # Test with wrong code_boundarycond
    with pytest.raises(ValueError):
        res = dataportal.tabula_system(
            code_country="FR", code_boundarycond="wrong_string"
        )
    # Makes sure res not in locals
    assert "res" not in locals()


def test_resolve_codecountry(config):
    # Tests with country string length == 3
    res = dataportal._resolve_codecountry("USA")
    # Makes sure code_country is right
    assert res == "US"

    # Tests with country number (integer)
    res = dataportal._resolve_codecountry(533)
    # Makes sure code_country is right
    assert res == "AW"


def test_openei_api_request(config):
    data = {"code_country": "FR"}
    res = dataportal.openei_api_request(data)

    # Makes sure result is None (no cache data found)
    assert res is None


def test_nrel_api_cbr_request(config):
    data = {"code_country": "FR"}
    res = dataportal.nrel_api_cbr_request(data)

    # Makes sure result returns an error "API_KEY_MISSING"
    assert res["error"]["code"] == "API_KEY_MISSING"


def test_nrel_api_cbr_request_exception(config):
    # Test with wrong code_country
    data = {"code_country": "wrong_string"}
    res = dataportal.nrel_api_cbr_request(data)

    # Makes sure result returns an error "API_KEY_MISSING"
    assert res["error"]["code"] == "API_KEY_MISSING"


def test_tabula_multiple(config):
    country_code = "FR"
    ab = dataportal.tabula_available_buildings(country_code)
    archetypes = pd.concat(
        ab.apply(
            lambda x: tabula_building_details_sheet(
                code_building=x.code_buildingtype_column1
                + "."
                + x.suffix_building_column1
                + ".001"
            ),
            axis=1,
        ).values.tolist(),
        keys=ab.code_buildingtype_column1 + "." + ab.suffix_building_column1,
    )

    # Makes sure result is not empty
    assert list(archetypes["val"])


@pytest.mark.xfail(
    condition=os.environ.get("NREL_CONSUMER_KEY") is None,
    reason="Must provide an NREL API key as ENV Variable 'NREL_CONSUMER_KEY'",
    strict=True,
)
def test_nrel_api_request(config):
    data = {
        "keyword": "Window",
        "format": "json",
        "f[]": ["fs_a_Overall_U-factor:[3.4 TO 3.6]", 'sm_component_type:"Window"'],
        "oauth_consumer_key": os.environ.get("NREL_CONSUMER_KEY"),
    }

    response = dataportal.nrel_bcl_api_request(data)
    assert response["result"]


@pytest.mark.xfail(
    condition=os.environ.get("NREL_CONSUMER_KEY") is None,
    reason="Must provide an NREL API key as ENV Variable 'NREL_CONSUMER_KEY'",
    strict=True,
)
def test_download_bld_window(config):
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
@pytest.mark.skipif(
    os.environ.get("CI", "False").lower() == "true",
    reason="Skipping this test on CI environment.",
)
def test_download_and_load_bld_window(config):
    """Download window and load its idf file"""
    oauth_consumer_key = os.environ.get("NREL_CONSUMER_KEY")

    response = download_bld_window(
        u_factor=3.18,
        shgc=0.49,
        vis_trans=0.53,
        oauth_key=oauth_consumer_key,
        tolerance=0.05,
    )
    idf = IDF(
        response[0],
        epw="tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
        prep_outputs=False,
    )
    construct = idf.getobject("CONSTRUCTION", "AEDG-SmOffice 1A Window Fixed")
    ws = WindowSetting.from_construction(Name="test_window", Construction=construct)

    assert ws


def test_statcan(config):
    data = dict(type="json", lang="E", dguid="2016A000011124", topic=5, notes=0)
    response = dataportal.stat_can_request(**data)
    print(response)

    # Makes sure result is not empty
    assert response


def test_statcan_error(config):
    # Tests statcan with error in inputs
    data = dict(type="json", lang="E", dguid="wrong_string", topic=5, notes=0)
    response = dataportal.stat_can_request(**data)
    print(response)

    # Makes sure result is None (wrong function input "dguid")
    assert response is None


def test_statcan_geo(config):
    data = dict(type="json", lang="E", geos="PR", cpt="00")
    response = dataportal.stat_can_geo_request(**data)
    print(response)

    # Makes sure result is not empty
    assert response


def test_statcan_geo_error(config):
    # Tests statcan_geo with error in inputs
    data = dict(type="json", lang="E", geos="wrong_string", cpt="00")
    response = dataportal.stat_can_geo_request(**data)
    print(response)

    # Makes sure result is not empty
    assert response
