import pandas as pd
import pytest
from archetypal import UmiTemplateLibrary

from archetypal.idfclass.shoeboxer import ShoeBox
from archetypal.idfclass.shoeboxer.hvac_templates import (
    HVACTemplates,
    VAVWithBoilersAndChillers,
)
from archetypal.idfclass.shoeboxer.topology import (
    Triangle,
    Rectangle,
    Trapezoid,
    L_Shape,
    T_Shape,
    CrossShape,
    U_Shape,
    H_Shape,
    TopologyBase,
)

TOPOLOGIES = [
    Triangle(),
    Rectangle(),
    Trapezoid(),
    L_Shape(),
    T_Shape(),
    CrossShape(),
    U_Shape(),
    H_Shape(),
]
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
                [lib.BuildingTemplates[0:1], list(HVACTemplates)]
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
            design_day=True,
            annual=False,
            keep_data_err=True,
        )

        # sb.view_model()
        # sb.meters.OutputMeter.Heating__EnergyTransfer.values().plot2d()

    @pytest.mark.parametrize("topology", TOPOLOGIES)
    def test_from_template_zone_dict(
        self, building_template, template, topology: TopologyBase
    ):
        name = "test_zones.idf"
        sb = ShoeBox.from_template(
            building_template,
            system="PTHP",
            ddy_file=DDY_FILE,
            epw=CWEC_EPW,
            zones_data=[
                {
                    "name": "",
                    "coordinates": topology.coords,
                    "height": 4 * 3,
                    "num_stories": 3,
                    "zoning": "core/perim",
                    "perim_depth": 3,
                }
            ],
            name=name,
        )
        # assert there are 15 zones
        # assert len(sb.idfobjects["ZONE"]) == 21
        # sb.view_model()
        sb.saveas(f"idf_{topology.__class__.__name__}.idf")


class TestTopology:
    def test_triangle(self):
        t = Triangle()
        print(t.coords)

    @pytest.mark.parametrize("topology, height", zip(TOPOLOGIES, range(3, 20)))
    def test_form_factor(self, topology: TopologyBase, height):
        perim = topology.shapely_polygon.length
        footprint_area = topology.shapely_polygon.area
        envelope_area = perim * height + footprint_area
        heated_floor_area = footprint_area * (height / topology.floor_to_floor)
        heat_loss_form_factor = envelope_area / heated_floor_area
        print(heat_loss_form_factor)


class TestHVACTemplateValidation:
    @pytest.fixture(scope="class")
    def building_template(self):
        building_template, *_ = UmiTemplateLibrary.open(
            r"C:\Users\samuel.letellier-duc\Downloads\dynamic_template_lib_wHtgClgSch.json"
        ).BuildingTemplates
        yield building_template

    @pytest.fixture(scope="class", params=tuple(HVACTemplates.keys()))
    def template(self, request):
        yield request.param

    @pytest.fixture(scope="class")
    def generate_model(self, building_template, template):

        topology = Rectangle(floor_to_floor="3 m")

        name = "test_zones.idf"
        nb_floors = 3
        sb = ShoeBox.from_template(
            building_template,
            system=template,
            ddy_file=DDY_FILE,
            epw=CWEC_EPW,
            zones_data=[
                {
                    "name": "",
                    "coordinates": topology.coords,
                    "height": nb_floors * topology.floor_to_floor,
                    "num_stories": nb_floors,
                    "zoning": "core/perim",
                    "perim_depth": topology.perimeter_zone_depth,
                }
            ],
            name=name,
        )
        yield sb

    @pytest.fixture(scope="class")
    def simulated_model(self, generate_model):
        yield generate_model.simulate(design_day=True)

    def test_write_run(self, generate_model, template):
        generate_model.saveas(f"{template}.idf")
        pd.DataFrame(
            {
                "local_seed_model": [f"{template}.idf"],
                "local_epw": [generate_model.epw],
                "template": [template],
            }
        ).to_csv("hvac_template_parametric.csv", mode="a", header=False, index=False)

    def test_view_model(self, generate_model):
        generate_model.view_model()

    def test_open_htm(self, simulated_model):
        simulated_model.open_htm()

    def test_design_day(self, simulated_model):
        from archetypal.idfclass.sql import Sql

        sql = Sql(simulated_model.sql_file)
        sql.timeseries_by_name("Baseboard:EnergyTransfer")
