import logging

import pandas as pd
import pytest
from archetypal import UmiTemplateLibrary

from archetypal.idfclass.shoeboxer import ShoeBox
from archetypal.idfclass.shoeboxer.hvac_templates import HVACTemplates
from archetypal.template import BuildingTemplate

logging.getLogger(__name__)

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
        name = "_".join([building_template.Name, hvac_template.name])
        sb = ShoeBox.from_template(
            building_template,
            system=hvac_template.name,
            ddy_file="tests/input_data/umi_samples/CAN_PQ_Montreal.Intl.AP.716270_CWEC.ddy",
            name=name,
        )
        assert len(sb.idfobjects["ZONE"]) == 2

        sb.saveas(name)
        sb.outputs.add_dxf().apply()
        sb.simulate(
            epw="tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
            expandobjects=True,
            design_day=False,
            annual=True,
            keep_data_err=True,
        )

        sb.view_model()
        # sb.meters.OutputMeter.Heating__DistrictHeating.values().plot2d()

    def test_from_template_zone_dict(self, building_template, template):
        name = "test_zones.idf"
        sb = ShoeBox.from_template(
            building_template,
            ddy_file="tests/CAN_PQ_Montreal.Intl.AP.716270_CWEC.ddy",
            zones_data=[
                {
                    "name": "",
                    "coordinates": [(10, 0), (10, 10), (0, 10), (0, 0)],
                    "height": 4,
                    "num_stories": 3,
                    "zoning": "core/perim",
                    "perim_depth": 3,
                }
            ],
            name=name,
        )
        # assert there are 15 zones
        assert len(sb.idfobjects["ZONE"]) == 15
