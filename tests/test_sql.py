"""Test the SQL class."""

import itertools

import pytest

from archetypal import IDF
from archetypal.idfclass.sql import Sql

# ref: https://bigladdersoftware.com/epx/docs/9-4/output-details-and-examples/eplusout-mdd.html#meter-variables-idf-format
metered_ressource_types = (
    "Electricity",
    "Gas",
    "DistrictCooling",
    "DistrictHeating",
)

end_use_category_types = (
    "InteriorLights",
    "ExteriorLights",
    "InteriorEquipment",
    "ExteriorEquipment",
    "Fans",
    "Pumps",
    "Heating",
    "Cooling",
    "HeatRecovery",
    "Humidifier",
    "HeatRejection",
    "Cogeneration",
    "Refrigeration",
    "WaterSystems",
    "Miscellaneous",
)
all_meters = list(itertools.product(end_use_category_types, metered_ressource_types))
all_meter_names = [f"{a}:{b}" for a, b in all_meters]


@pytest.fixture(scope="session")
def sql():
    idf = IDF.from_example_files(
        "RefBldgMediumOfficeNew2004_Chicago.idf",
        "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
    ).simulate()

    yield Sql(idf.sql_file)


@pytest.mark.parametrize(
    "variable_or_meter",
    (all_meter_names[0], [all_meter_names[0]], all_meter_names),
    ids=("str", "one", "multiple"),
)
def test_collect_meters(variable_or_meter, sql):
    """Test collecting outputs by name."""
    # environment_type=1 (Design Day) because data is only available for that period.
    df = sql.timeseries_by_name(
        variable_or_meter, reporting_frequency="Hourly", environment_type=1
    )

    assert not df.empty


def test_available_datapoints(sql):
    """Test getting available datapoints in the sql_file"""
    dps = sql.available_outputs

    assert dps


def test_collect_variables(sql):
    """Test collection variables."""
    variable_or_meter = ("Zone Mean Air Temperature",)

    df = sql.timeseries_by_name(
        variable_or_meter, reporting_frequency="Hourly", environment_type=1
    )

    assert df.shape == (48, 18)


def test_collect_variables_raise(sql):
    """Raise error if reporting frequency not supported."""
    variable_or_meter = ("Zone Mean Air Temperature",)

    with pytest.raises(AssertionError):
        sql.timeseries_by_name(variable_or_meter, reporting_frequency="all")


def test_zone_info(sql):
    """Test getting the zone info table."""
    df = sql.zone_info

    assert not df.empty


def test_environment_periods(sql):
    """Test getting the environment_period"""
    df = sql.environment_periods
    assert not df.empty


def test_tabular_data(sql):
    """Test getting tabular data by name"""
    df = sql.tabular_data_by_name("AnnualBuildingUtilityPerformanceSummary", "End Uses")
    assert df.shape == (16, 6)


def test_html_report(sql):
    """Test getting the full html report."""
    df = sql.full_html_report()
    assert df is not None


def test_tabular_data_keys(sql):
    """Test getting tabular data keys."""
    keys = sql.tabular_data_keys
    assert keys[0] == (
        "AnnualBuildingUtilityPerformanceSummary",
        "Site and Source Energy",
        "Entire Facility",
    )


def test_outputs(sql):
    """Test getting an output from the Outputs property"""
    output = sql.outputs["Heating__Electricity_Hourly"]

    assert output is sql.outputs.Heating__Electricity_Hourly
    assert output.reporting_frequency == "Hourly"
    assert output.output_name == "Heating:Electricity"
