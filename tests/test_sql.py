import itertools

import pytest

from archetypal import IDF
from archetypal.idfclass.sql import collect_output_by_name

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


@pytest.fixture()
def sql_file():
    idf = IDF.from_example_files(
        "RefBldgMediumOfficeNew2004_Chicago.idf",
        "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
    ).simulate()

    yield idf.sql_file


@pytest.mark.parametrize(
    "variable_or_meter",
    (all_meter_names[0], [all_meter_names[0]], all_meter_names),
    ids=("str", "one", "multiple"),
)
def test_collect_meters(variable_or_meter, sql_file):
    """Test collecting outputs by name."""

    df = collect_output_by_name(
        sql_file, variable_or_meter, reporting_frequency="Hourly"
    )

    assert not df.empty
