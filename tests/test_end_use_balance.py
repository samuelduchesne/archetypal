from tempfile import TemporaryFile

import pytest
from archetypal import IDF
from archetypal.idfclass.end_use_balance import EndUseBalance


class TestEndUseBalance:
    @pytest.fixture()
    def idf(self):
        idf = IDF.from_example_files(
            "AdultEducationCenter.idf",
            epw="USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
            annual=True,
            design_day=False,
            readvars=False,
        )
        idf = idf.saveas("AdultEducationCenter.idf")
        idf.outputs.add_end_use_balance_components()
        idf.outputs.apply()
        idf.simulate()
        yield idf

    @pytest.fixture()
    def idf_noOA(self):
        idf = IDF.from_example_files(
            "HVACStandAloneERV_Economizer.idf",
            epw="USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw",
            annual=True,
            design_day=False,
            readvars=False,
        )
        idf.outputs.add_load_balance_components()
        idf.outputs.add_end_use_balance_components()
        idf.outputs.add_sensible_heat_gain_summary_components()
        idf.outputs.apply()

        idf.removeidfobjects(list(idf.idfobjects["DESIGNSPECIFICATION:OUTDOORAIR"]))

        idf.simulate()
        yield idf

    def test_from_idf(self, idf):
        """Test initializing with idf model."""
        eu = EndUseBalance.from_sql_file(
            idf.sql_file, outdoor_surfaces_only=True, units="GJ", power_units="W"
        )
        # assert eu
        # assert not eu.component_summary().empty
        # assert not eu.separate_gains_and_losses("opaque_flow", ["Zone_Name"]).empty
        # to_df = eu.to_df(separate_gains_and_losses=False)
        # assert not to_df.empty
        # assert to_df.columns.shape == (10,)  # should have 10 columns
        to_df_sep = eu.to_df(separate_gains_and_losses=True)
        assert not to_df_sep.empty
        # assert to_df_sep.columns.shape == (32,)  # should have 32 columns

    def test_from_idf_noOA(self, idf_noOA):
        """Test initializing with idf model."""
        eu = EndUseBalance.from_sql_file(
            idf_noOA.sql_file, outdoor_surfaces_only=True, units="GJ", power_units="W"
        )
        to_df_sep = eu.to_df(separate_gains_and_losses=True)
        assert not to_df_sep.empty

    def test_to_sankey(self, idf):
        eu = EndUseBalance.from_sql_file(
            idf.sql_file, outdoor_surfaces_only=True, units="GJ", power_units="W"
        )
        with TemporaryFile("w") as f:
            eu.to_sankey(f)
