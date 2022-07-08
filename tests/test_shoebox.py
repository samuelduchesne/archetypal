import pandas as pd
import pytest
from archetypal import UmiTemplateLibrary

from archetypal.idfclass.shoeboxer import ShoeBox
from archetypal.idfclass.shoeboxer.hvac_templates import HVACTemplates
from archetypal.template import BuildingTemplate

CWEC_EPW = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
DDY_FILE = "tests/input_data/umi_samples/CAN_PQ_Montreal.Intl.AP.716270_CWEC.ddy"

lib = UmiTemplateLibrary.open(
    "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
)


class TestShoebox:
    @pytest.fixture()
    def template(self):
        yield UmiTemplateLibrary.open(
            "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        )

    @pytest.fixture()
    def building_template(self, template):
        yield next(iter(template.BuildingTemplates))

    @pytest.mark.parametrize(
        "building_template,hvac_template",
        list(
            pd.MultiIndex.from_product(
                [lib.BuildingTemplates, list(HVACTemplates)]
            ).values
        ),
    )
    def test_from_template(self, building_template: BuildingTemplate, hvac_template):
        name = "_".join([building_template.Name, hvac_template])
        sb = ShoeBox.from_template(
            building_template,
            system=hvac_template,
            ddy_file=DDY_FILE,
            name=name,
        )
        assert len(sb.idfobjects["ZONE"]) == 2

        # sb.saveas(name)
        # sb.outputs.add_dxf().apply()
        sb.simulate(
            epw=CWEC_EPW,
            expandobjects=True,
            design_day=False,
            annual=True,
            keep_data_err=True,
        )

        # sb.view_model()
        # sb.meters.OutputMeter.Heating__EnergyTransfer.values().plot2d()

    def test_from_template_zone_dict(self, building_template, template):
        name = "test_zones.idf"
        sb = ShoeBox.from_template(
            building_template,
            ddy_file=DDY_FILE,
            epw=CWEC_EPW,
            zones_data=[
                {
                    "name": "",
                    "coordinates": [
                        (20, 0),
                        (20, 10),
                        (10, 10),
                        (10, 20),
                        (0, 20),
                        (0, 0),
                    ],
                    "height": 4 * 3,
                    "num_stories": 3,
                    "zoning": "core/perim",
                    "perim_depth": 3,
                }
            ],
            name=name,
        )
        # assert there are 15 zones
        assert len(sb.idfobjects["ZONE"]) == 21
        # sb.view_model()
