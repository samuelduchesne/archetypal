import os

import archetypal as ar
import pandas as pd
import pytest

from path import Path

from archetypal import EnergySeries, get_eplus_dirs, settings

import numpy as np


@pytest.fixture(
    scope="module",
    params=[
        get_eplus_dirs(settings.ep_version) / "ExampleFiles" / "5ZoneNightVent1.idf",
        get_eplus_dirs(settings.ep_version)
        / "ExampleFiles"
        / "BasicsFiles"
        / "AdultEducationCenter.idf",
    ],
)
def energy_series(config, request):
    from archetypal import ReportData

    outputs = {
        "ep_object": "Output:Variable".upper(),
        "kwargs": {
            "Key_Value": "OCCUPY-1",
            "Variable_Name": "Schedule Value",
            "Reporting_Frequency": "Hourly",
        },
    }
    wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    sql = ar.run_eplus(
        request.param,
        weather_file=wf,
        output_report="sql_file",
        prep_outputs=[outputs],
        annual=True,
        expandobjects=True,
    )
    report = ReportData.from_sqlite(
        sql,
        table_name=("Heating:Electricity", "Heating:Gas", "Heating:DistrictHeating"),
    )

    hl = EnergySeries.from_sqlite(
        report,
        name="Heating",
        normalize=False,
        sort_values=False,
        concurrent_sort=False,
        to_units="kWh",
    )

    yield hl


@pytest.fixture(
    params=(["Water Heater Tank Temperature", "WaterSystems:EnergyTransfer"])
)
def rd(request):
    from archetypal import ReportData

    file = Path("tests/input_data/trnsys/HeatPumpWaterHeater.sqlite")

    rd = ReportData.from_sqlite(file, table_name=request.param)
    assert not rd.empty
    yield rd


def test_EnergySeries(rd):
    import matplotlib.pyplot as plt
    from archetypal import EnergySeries

    es = EnergySeries.from_sqlite(rd)
    es.plot()
    plt.show()
    print(es)


@pytest.mark.parametrize("kind", ["polygon", "surface", "contour"])
def test_plot_3d(energy_series, kind):
    hl = energy_series.copy()
    hl.plot3d(
        save=True,
        axis_off=False,
        kind=kind,
        cmap="Reds",
        fig_width=4,
        fig_height=4,
        edgecolors="grey",
        linewidths=0.01,
    )


@pytest.mark.xfail(
    "TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
    reason="Skipping this test on Travis CI.",
)
def test_plot_2d(energy_series):
    hl = energy_series.copy()
    hl.plot2d(
        save=True,
        axis_off=False,
        cmap="Reds",
        subplots=False,
        fig_width=6,
        fig_height=2,
        edgecolors="k",
        linewidths=0.5,
        filename=hl.name + "_heatmap",
    )


@pytest.fixture(scope="module")
def from_csv(config):
    file = "tests/input_data/test_profile.csv"
    df = pd.read_csv(file, index_col=[0], names=["Heat"])
    ep = ar.EnergySeries(
        df.Heat,
        units="BTU/hour",
        frequency="1H",
        to_units="kW",
        sort_values=False,
        use_timeindex=True,
    )
    # ep = ep.unit_conversion(to_units='kW')
    yield ep


@pytest.mark.xfail(
    "TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
    reason="Skipping this test on Travis CI.",
)
def test_discretize(from_csv):
    epc = from_csv.copy()
    res = epc.discretize_tsam()
    res.plot()
    ar.plt.show()


def test_discretize_tsam(from_csv):
    ep = from_csv.copy()
    ldc_disc = ep.discretize_tsam(noTypicalPeriods=10)

    ldc_disc.plot2d(subplots=False)
