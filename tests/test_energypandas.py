import pytest
from pandas import date_range, read_csv
from numpy.testing import assert_almost_equal

from archetypal import IDF, settings, EnergyDataFrame, EnergySeries


@pytest.fixture()
def edf():
    frame = EnergyDataFrame({"Temp": range(0, 10)}, units="C", extrameta="this")
    yield frame

    # check that the name is passed to the slice
    assert frame["Temp"].name == "Temp"

    # check that the metadata is passed to the slice
    assert frame.extrameta == "this"


@pytest.fixture()
def es():
    datetimeindex = date_range(
        freq="H",
        start="{}-01-01".format("2018"),
        periods=10,
    )
    series = EnergySeries(
        range(0, 10), index=datetimeindex, name="Temp", units="C", extrameta="this"
    )
    yield series

    # check that the name is passed to the slice
    assert series.name == "Temp"

    # check that the metadata is passed to the slice
    assert series.extrameta == "this"


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
    def test_units(self, es):
        """tests unit conversion"""
        assert es.to_units(to_units="degF").units == settings.unit_registry.degF
        assert type(es.to_units(to_units="degF")) == EnergySeries

        # inplace
        es.to_units(to_units="degF", inplace=True)
        assert es.units == settings.unit_registry.degF
        assert type(es) == EnergySeries

    def test_normalize(self, es):
        """Tests normalization"""
        assert es.normalize().sum().sum() == 5
        assert type(es.normalize()) == EnergySeries
        es.normalize(inplace=True)

        # inplace
        assert es.sum().sum() == 5
        assert type(es) == EnergySeries

    def test_to_frame(self, es):
        # check that a slice returns an EnergySeries
        assert type(es.to_frame(name="Temp")) == EnergyDataFrame

    def test_repr(self, es):
        # check that a slice returns an EnergySeries
        print(es.__repr__())

    def test_monthly(self, es):
        assert es.monthly.extrameta == "this"
        print(es.monthly)

    def test_from_csv(self):
        file = "tests/input_data/test_profile.csv"
        df = read_csv(file, index_col=[0], names=["Heat"])
        ep = EnergySeries.with_timeindex(
            df.Heat,
            units="BTU/hour",
            frequency="1H",
        )
        assert ep.units == settings.unit_registry.parse_expression("BTU/hour").units

    def test_from_report_data(self, rd_es):
        assert_almost_equal(rd_es.sum(), 2.1187133811706036, decimal=3)
        assert rd_es.units == settings.unit_registry.m3

    def test_expanddim(self, es):
        """Tests when result has one higher dimension as the original"""
        # to_frame should return an EnergyDataFrame
        assert type(es.to_frame()) == EnergyDataFrame

        # Units of expandeddim frame should be same as EnergySeries
        assert es.to_frame().units == es.units

        # Meta of expandeddim frame should be same as EnergySeries
        assert es.to_frame().extrameta == es.extrameta

    @pytest.mark.parametrize("kind", ["polygon", "surface", "contour"])
    def test_plot_3d(self, rd_es, kind):
        fig, ax = rd_es.plot3d(
            save=False,
            show=False,
            axis_off=False,
            kind=kind,
            cmap="Reds",
            fig_width=4,
            fig_height=4,
            edgecolors="grey",
            linewidths=0.01,
        )

    def test_plot_2d(self, rd_es):
        fig, ax = rd_es.plot2d(
            save=False,
            show=False,
            axis_off=False,
            cmap="Reds",
            subplots=False,
            fig_width=6,
            fig_height=2,
            edgecolors="k",
            linewidths=0.5,
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
    def test_units(self, edf):
        """tests unit conversion"""
        assert edf.to_units(to_units="degF").units == settings.unit_registry.degF
        assert type(edf.to_units(to_units="degF")) == EnergyDataFrame

        # inplace
        edf.to_units(to_units="degF", inplace=True)
        assert edf.units == settings.unit_registry.degF
        assert type(edf) == EnergyDataFrame

    def test_normalize(self, edf):
        """Tests normalization"""
        assert edf.normalize().sum().sum() == 5
        assert type(edf.normalize()) == EnergyDataFrame
        edf.normalize(inplace=True)

        # inplace
        assert edf.sum().sum() == 5
        assert type(edf) == EnergyDataFrame

    def test_slice(self, edf):
        # check that a slice returns an EnergySeries
        assert type(edf[["Temp"]]) == EnergyDataFrame
        assert type(edf["Temp"]) == EnergySeries

        # check that the name is passed to the slice
        assert edf[["Temp"]].name is None  # only EnergySeries have name
        assert edf["Temp"].name == "Temp"

        # check that the metadata is passed to the slice
        assert edf[["Temp"]].extrameta == "this"
        assert edf["Temp"].extrameta == "this"

        # check that the slice keeps the units
        assert edf.units == edf["Temp"].units

    def test_from_report_data(self, rd_edf):
        assert_almost_equal(rd_edf.sum().sum(), 398258.8688595464, decimal=3)
        assert rd_edf.units == settings.unit_registry.C

    def test_discretize(self, rd_edf):
        rd_edf = rd_edf.discretize_tsam(noTypicalPeriods=1)
        assert hasattr(rd_edf, "agg")
        rd_edf.discretize_tsam(noTypicalPeriods=1, inplace=True)
        assert hasattr(rd_edf, "agg")
        # check that the type is maintained
        assert type(rd_edf) == EnergyDataFrame
