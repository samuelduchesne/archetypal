import pytest

from archetypal import IDF
from archetypal.idfclass import Outputs


class TestOutput:
    @pytest.fixture()
    def idf(self):
        yield IDF(prep_outputs=False)

    def test_output_init(self, idf):
        """Test initialization of the Output class."""

        outputs = Outputs(idf)
        str(outputs)  # test the string representation of the object

        assert len(outputs.other_outputs) == 2
        assert len(outputs.output_variables) == 0
        assert len(outputs.output_meters) == 0

        outputs.add_umi_template_outputs()
        assert len(outputs.output_variables) > 1
        assert len(outputs.output_meters) > 1
        assert outputs.reporting_frequency == "Hourly"
        assert outputs.include_sqlite
        assert outputs.include_html

    def test_output_properties(self, idf):
        """Test changing properties of Outputs."""
        outputs = Outputs(idf)

        outputs.output_variables = ["Air System Outdoor Air Minimum Flow Fraction"]
        assert outputs.output_variables == (
            "Air System Outdoor Air Minimum Flow Fraction",
        )
        outputs.reporting_frequency = "daily"  # lower case
        assert outputs.reporting_frequency == "Daily"  # should be upper case
        outputs.unit_conversion = "InchPound"
        assert outputs.unit_conversion == "InchPound"
        outputs.include_sqlite = False
        assert not outputs.include_sqlite
        outputs.include_html = True
        assert outputs.include_html

        with pytest.raises(AssertionError):
            outputs.output_variables = (
                "Zone Ideal Loads Supply Air Total Cooling Energy"
            )
        with pytest.raises(AssertionError):
            outputs.reporting_frequency = "annually"
        with pytest.raises(AssertionError):
            outputs.other_outputs = "ComponentSizingSummary"
        with pytest.raises(AssertionError):
            outputs.unit_conversion = "IP"

    def test_add_basics(self, idf):
        """Test the Output add_basics method"""
        outputs = Outputs(idf).add_basics()
        assert len(outputs.output_variables) == 0
        assert len(outputs.output_meters) == 0
        assert len(outputs.other_outputs) == 6
