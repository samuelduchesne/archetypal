import pytest
from energy_pandas import EnergyDataFrame, EnergySeries
from numpy.testing import assert_almost_equal
from pandas import read_csv

from archetypal import IDF, settings


@pytest.fixture(scope="module")
def idf(config):
    idfname = "tests/input_data/umi_samples/B_Off_0.idf"
    epw = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    _idf = IDF(idfname, epw)
    yield _idf
    _idf.save()


@pytest.fixture(scope="class")
def rd_es(idf):
    try:
        yield idf.meters.OutputMeter.WaterSystems__MainsWater.values()
    except Exception:
        yield idf.simulate().meters.OutputMeter.WaterSystems__MainsWater.values()


@pytest.fixture(scope="class")
def rd_edf(idf):
    try:
        yield idf.variables.OutputVariable.Zone_Air_Temperature.values()
    except Exception:
        yield idf.simulate().variables.OutputVariable.Zone_Air_Temperature.values()


class TestEnergySeries:
    def test_from_csv(self):
        file = "tests/input_data/test_profile.csv"
        df = read_csv(file, index_col=[0], names=["Heat"])
        ep = EnergySeries.with_timeindex(df.Heat, frequency="1H", units="BTU/hour")
        assert ep.units == settings.unit_registry.parse_expression("BTU/hour").units

    def test_from_report_data(self, rd_es):
        assert_almost_equal(rd_es.sum(), 2.1187133811706036, decimal=3)
        assert rd_es.units == settings.unit_registry.m3

    @pytest.mark.parametrize("kind", ["polygon", "surface", "contour"])
    def test_plot_3d(self, rd_es, kind):
        fig, ax = rd_es.plot3d(
            save=False,
            show=True,
            axis_off=False,
            kind=kind,
            cmap="Reds",
            figsize=(4, 4),
            edgecolors="grey",
            linewidths=0.01,
        )

    def test_plot_2d(self, rd_es):
        fig, ax = rd_es.plot2d(
            axis_off=False,
            cmap="Reds",
            figsize=(2, 6),
            show=True,
            save=False,
            filename=rd_es.name + "_heatmap",
        )

    def test_discretize(self, rd_es):
        res = rd_es.discretize_tsam(noTypicalPeriods=1)
        assert_almost_equal(res.sum(), 2.118713381170598, decimal=3)
        rd_es.discretize_tsam(noTypicalPeriods=1, inplace=True)
        assert_almost_equal(res.sum(), 2.118713381170598, decimal=3)
        # check that the type is maintained
        assert type(rd_es) == EnergySeries


class TestEnergyDataFrame:
    def test_from_report_data(self, rd_edf):
        assert_almost_equal(rd_edf.sum().sum(), 397714.38260559476, decimal=3)
        assert rd_edf.units["CORE"] == settings.unit_registry.C

    def test_discretize(self, rd_edf):
        rd_edf = rd_edf.discretize_tsam(noTypicalPeriods=1)
        assert hasattr(rd_edf, "agg")
        rd_edf.discretize_tsam(noTypicalPeriods=1, inplace=True)
        assert hasattr(rd_edf, "agg")
        # check that the type is maintained
        assert type(rd_edf) == EnergyDataFrame

    def test_plot_2d(self, rd_edf):
        fig, ax = rd_edf.plot2d(
            axis_off=False,
            cmap="Reds",
            figsize=(4, 6),
            show=True,
            save=False,
            extent="tight",
        )
