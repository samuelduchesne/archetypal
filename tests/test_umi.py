import collections
import json
import os

import pytest
from path import Path

from archetypal import IDF, settings
from archetypal.eplus_interface.version import get_eplus_dirs
from archetypal.template.building_template import BuildingTemplate
from archetypal.template.conditioning import ZoneConditioning
from archetypal.template.dhw import DomesticHotWaterSetting
from archetypal.template.load import ZoneLoad
from archetypal.template.materials.gas_layer import GasLayer
from archetypal.template.materials.gas_material import GasMaterial
from archetypal.template.materials.glazing_material import GlazingMaterial
from archetypal.template.materials.material_layer import MaterialLayer
from archetypal.template.materials.opaque_material import OpaqueMaterial
from archetypal.template.constructions.opaque_construction import OpaqueConstruction
from archetypal.template.schedule import (
    DaySchedule,
    WeekSchedule,
    YearSchedule,
    YearSchedulePart,
)
from archetypal.template.structure import MassRatio, StructureInformation
from archetypal.template.ventilation import VentilationSetting
from archetypal.template.constructions.window_construction import WindowConstruction
from archetypal.template.window_setting import WindowSetting
from archetypal.template.zone_construction_set import ZoneConstructionSet
from archetypal.template.zonedefinition import ZoneDefinition
from archetypal.umi_template import UmiTemplateLibrary, no_duplicates


class TestUmiTemplate:
    """Test suite for the UmiTemplateLibrary class"""

    def test_template_to_template(self):
        """load the json into UmiTemplateLibrary object, then convert back to json and
        compare"""

        file = "tests/input_data/umi_samples/BostonTemplateLibrary_nodup.json"

        a = UmiTemplateLibrary.open(file).to_dict()
        b = TestUmiTemplate.read_json(file)

        for key in b:
            # Sort the list elements by their Name because .to_dict() sorts by Name
            b[key] = sorted(b[key], key=lambda x: x.get("Name"))
        assert json.loads(json.dumps(a)) == json.loads(json.dumps(b))

    def test_umitemplate(self, config):
        """Test creating UmiTemplateLibrary from 2 IDF files"""
        idf_source = [
            "tests/input_data/necb/NECB 2011-FullServiceRestaurant-NECB HDD Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
            get_eplus_dirs(settings.ep_version)
            / "ExampleFiles"
            / "VentilationSimpleTest.idf",
        ]
        wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        a = UmiTemplateLibrary.from_idf_files(
            idf_source, wf, name="Mixed_Files", processors=-1
        )

        data_dict = a.to_dict()
        a.to_dict()
        assert no_duplicates(data_dict)

    @pytest.mark.skipif(
        os.environ.get("CI", "False").lower() == "true",
        reason="not necessary to test this on CI",
    )
    def test_umi_samples(self, config):
        idf_source = [
            "tests/input_data/umi_samples/B_Off_0.idf",
            "tests/input_data/umi_samples/B_Ret_0.idf",
            "tests/input_data/umi_samples/B_Res_0_Masonry.idf",
            "tests/input_data/umi_samples/B_Res_0_WoodFrame.idf",
        ]
        wf = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        a = UmiTemplateLibrary.from_idf_files(idf_source, wf, name="Mixed_Files")
        a.to_dict()
        data_dict = a.to_dict()
        assert no_duplicates(data_dict)

    @staticmethod
    def read_json(file):
        with open(file, "r") as f:
            a = json.load(f, object_pairs_hook=collections.OrderedDict)
            data_dict = collections.OrderedDict(
                {
                    "GasMaterials": [],
                    "GlazingMaterials": [],
                    "OpaqueMaterials": [],
                    "OpaqueConstructions": [],
                    "WindowConstructions": [],
                    "StructureDefinitions": [],
                    "DaySchedules": [],
                    "WeekSchedules": [],
                    "YearSchedules": [],
                    "DomesticHotWaterSettings": [],
                    "VentilationSettings": [],
                    "ZoneConditionings": [],
                    "ZoneConstructionSets": [],
                    "ZoneLoads": [],
                    "Zones": [],
                    "WindowSettings": [],
                    "BuildingTemplates": [],
                }
            )
            data_dict.update(a)
            for key in data_dict:
                # Sort the list elements by $id
                data_dict[key] = sorted(
                    data_dict[key], key=lambda x: int(x.get("$id", 0))
                )
            return data_dict

    @pytest.fixture()
    def idf(self):
        yield IDF(prep_outputs=False)

    @pytest.fixture()
    def manual_umitemplate_library(self, config):
        """ Creates Umi template from scratch """

        # region Defines materials

        # Opaque materials
        concrete = OpaqueMaterial(
            Name="Concrete",
            Conductivity=0.5,
            SpecificHeat=800,
            Density=1500,
        )
        insulation = OpaqueMaterial(
            Name="Insulation",
            Conductivity=0.04,
            SpecificHeat=1000,
            Density=30,
        )
        brick = OpaqueMaterial(
            Name="Brick",
            Conductivity=1,
            SpecificHeat=900,
            Density=1900,
        )
        plywood = OpaqueMaterial(
            Name="Plywood",
            Conductivity=0.13,
            SpecificHeat=800,
            Density=540,
        )
        OpaqueMaterials = [concrete, insulation, brick, plywood]

        # Glazing materials
        glass = GlazingMaterial(
            Name="Glass",
            Density=2500,
            Conductivity=1,
            SolarTransmittance=0.7,
            SolarReflectanceFront=0.5,
            SolarReflectanceBack=0.5,
            VisibleTransmittance=0.7,
            VisibleReflectanceFront=0.3,
            VisibleReflectanceBack=0.3,
            IRTransmittance=0.7,
            IREmissivityFront=0.5,
            IREmissivityBack=0.5,
        )
        GlazingMaterials = [glass]

        # Gas materials
        air = GasMaterial(Name="Air", Conductivity=0.02, Density=1.24)
        GasMaterials = [air]
        # endregion

        # region Defines MaterialLayers

        # Opaque MaterialLayers
        concreteLayer = MaterialLayer(concrete, Thickness=0.2)
        insulationLayer = MaterialLayer(insulation, Thickness=0.5)
        brickLayer = MaterialLayer(brick, Thickness=0.1)
        plywoodLayer = MaterialLayer(plywood, Thickness=0.016)

        # Glazing MaterialLayers
        glassLayer = MaterialLayer(glass, Thickness=0.16)

        # Gas MaterialLayers
        airLayer = GasLayer(air, Thickness=0.04)

        MaterialLayers = [
            concreteLayer,
            insulationLayer,
            brickLayer,
            plywoodLayer,
            glassLayer,
            airLayer,
        ]
        # endregion

        # region Defines constructions

        # Opaque constructions
        wall_int = OpaqueConstruction(
            Name="wall_int",
            Layers=[plywoodLayer],
        )
        wall_ext = OpaqueConstruction(
            Name="wall_ext",
            Layers=[concreteLayer, insulationLayer, brickLayer],
        )
        floor = OpaqueConstruction(
            Name="floor",
            Layers=[concreteLayer, plywoodLayer],
        )
        roof = OpaqueConstruction(
            Name="roof",
            Layers=[plywoodLayer, insulationLayer, brickLayer],
        )
        OpaqueConstructions = [wall_int, wall_ext, floor, roof]

        # Window construction
        window = WindowConstruction(
            Layers=[glassLayer, airLayer, glassLayer], Name="Window"
        )
        WindowConstructions = [window]

        # Structure definition
        mass_ratio = MassRatio(Material=plywood, NormalRatio=1, HighLoadRatio=1)
        struct_definition = StructureInformation(
            MassRatios=[mass_ratio], Name="Structure"
        )
        StructureDefinitions = [struct_definition]
        # endregion

        # region Defines schedules

        # Day schedules
        # Always on
        sch_d_on = DaySchedule.from_values(
            Name="AlwaysOn", Values=[1] * 24, Type="Fraction", Category="Day"
        )
        # Always off
        sch_d_off = DaySchedule.from_values(
            Name="AlwaysOff", Values=[0] * 24, Type="Fraction", Category="Day"
        )
        # DHW
        sch_d_dhw = DaySchedule.from_values(
            Name="DHW", Values=[0.3] * 24, Type="Fraction", Category="Day"
        )
        # Internal gains
        sch_d_gains = DaySchedule.from_values(
            Name="Gains",
            Values=[0] * 6 + [0.5, 0.6, 0.7, 0.8, 0.9, 1] + [0.7] * 6 + [0.4] * 6,
            Type="Fraction",
            Category="Day",
        )
        DaySchedules = [sch_d_on, sch_d_dhw, sch_d_gains, sch_d_off]

        # Week schedules
        # Always on
        sch_w_on = WeekSchedule(
            Days=[sch_d_on, sch_d_on, sch_d_on, sch_d_on, sch_d_on, sch_d_on, sch_d_on],
            Category="Week",
            Type="Fraction",
            Name="AlwaysOn",
        )
        # Always off
        sch_w_off = WeekSchedule(
            Days=[
                sch_d_off,
                sch_d_off,
                sch_d_off,
                sch_d_off,
                sch_d_off,
                sch_d_off,
                sch_d_off,
            ],
            Category="Week",
            Type="Fraction",
            Name="AlwaysOff",
        )
        # DHW
        sch_w_dhw = WeekSchedule(
            Days=[
                sch_d_dhw,
                sch_d_dhw,
                sch_d_dhw,
                sch_d_dhw,
                sch_d_dhw,
                sch_d_dhw,
                sch_d_dhw,
            ],
            Category="Week",
            Type="Fraction",
            Name="DHW",
        )
        # Internal gains
        sch_w_gains = WeekSchedule(
            Days=[
                sch_d_gains,
                sch_d_gains,
                sch_d_gains,
                sch_d_gains,
                sch_d_gains,
                sch_d_gains,
                sch_d_gains,
            ],
            Category="Week",
            Type="Fraction",
            Name="Gains",
        )
        WeekSchedules = [sch_w_on, sch_w_off, sch_w_dhw, sch_w_gains]

        # Year schedules
        # Always on
        dict_on = {
            "$id": 1,
            "Category": "Year",
            "Parts": [
                {
                    "FromDay": 1,
                    "FromMonth": 1,
                    "ToDay": 31,
                    "ToMonth": 12,
                    "Schedule": sch_w_on.to_ref(),
                }
            ],
            "Type": "Fraction",
            "Name": "AlwaysOn",
        }
        sch_y_on = YearSchedule.from_dict(dict_on, {a.id: a for a in WeekSchedules})
        # Always off
        dict_off = {
            "$id": 2,
            "Category": "Year",
            "Parts": [
                {
                    "FromDay": 1,
                    "FromMonth": 1,
                    "ToDay": 31,
                    "ToMonth": 12,
                    "Schedule": sch_w_off.to_ref(),
                }
            ],
            "Type": "Fraction",
            "Name": "AlwaysOff",
        }
        sch_y_off = YearSchedule.from_dict(dict_off, {a.id: a for a in WeekSchedules})
        # DHW
        dict_dhw = {
            "$id": 3,
            "Category": "Year",
            "Parts": [
                {
                    "FromDay": 1,
                    "FromMonth": 1,
                    "ToDay": 31,
                    "ToMonth": 12,
                    "Schedule": sch_w_dhw.to_ref(),
                }
            ],
            "Type": "Fraction",
            "Name": "DHW",
        }
        sch_y_dhw = YearSchedule.from_dict(dict_dhw, {a.id: a for a in WeekSchedules})
        # Internal gains
        dict_gains = {
            "$id": 4,
            "Category": "Year",
            "Parts": [
                {
                    "FromDay": 1,
                    "FromMonth": 1,
                    "ToDay": 31,
                    "ToMonth": 12,
                    "Schedule": sch_w_gains.to_ref(),
                }
            ],
            "Type": "Fraction",
            "Name": "Gains",
        }
        sch_y_gains = YearSchedule.from_dict(
            dict_gains, {a.id: a for a in WeekSchedules}
        )
        YearSchedules = [sch_y_on, sch_y_off, sch_y_dhw, sch_y_gains]
        # endregion

        # region Defines Window settings

        window_setting = WindowSetting(
            Name="window_setting_1",
            Construction=window,
            AfnWindowAvailability=sch_y_off,
            ShadingSystemAvailabilitySchedule=sch_y_off,
            ZoneMixingAvailabilitySchedule=sch_y_off,
        )
        WindowSettings = [window_setting]
        # endregion

        # region Defines DHW settings

        dhw_setting = DomesticHotWaterSetting(
            WaterSchedule=sch_y_dhw,
            IsOn=True,
            FlowRatePerFloorArea=0.03,
            WaterSupplyTemperature=65,
            WaterTemperatureInlet=10,
            area=1,
            Name="dhw_setting_1",
        )
        DomesticHotWaterSettings = [dhw_setting]
        # endregion

        # region Defines ventilation settings

        vent_setting = VentilationSetting(
            NatVentSchedule=sch_y_off,
            ScheduledVentilationSchedule=sch_y_off,
            Name="vent_setting_1",
        )
        VentilationSettings = [vent_setting]
        # endregion

        # region Defines zone conditioning setttings

        zone_conditioning = ZoneConditioning(
            Name="conditioning_setting_1",
            HeatingSchedule=sch_y_on,
            CoolingSchedule=sch_y_on,
            MechVentSchedule=sch_y_off,
        )
        ZoneConditionings = [zone_conditioning]
        # endregion

        # region Defines zone construction sets

        # Perimeter zone
        zone_constr_set_perim = ZoneConstructionSet(
            Name="constr_set_perim",
            Zone_Names=None,
            Slab=floor,
            IsSlabAdiabatic=False,
            Roof=roof,
            IsRoofAdiabatic=False,
            Partition=wall_int,
            IsPartitionAdiabatic=False,
            Ground=floor,
            IsGroundAdiabatic=False,
            Facade=wall_ext,
            IsFacadeAdiabatic=False,
        )
        # Core zone
        zone_constr_set_core = ZoneConstructionSet(
            Name="constr_set_core",
            Zone_Names=None,
            Slab=floor,
            IsSlabAdiabatic=False,
            Roof=roof,
            IsRoofAdiabatic=False,
            Partition=wall_int,
            IsPartitionAdiabatic=True,
            Ground=floor,
            IsGroundAdiabatic=False,
            Facade=wall_ext,
            IsFacadeAdiabatic=False,
        )
        ZoneConstructionSets = [zone_constr_set_perim, zone_constr_set_core]
        # endregion

        # region Defines zone loads

        zone_load = ZoneLoad(
            EquipmentAvailabilitySchedule=sch_y_gains,
            LightsAvailabilitySchedule=sch_y_gains,
            OccupancySchedule=sch_y_gains,
            Name="zone_load_1",
        )
        ZoneLoads = [zone_load]
        # endregion

        # region Defines zones

        # Perimeter zone
        perim = ZoneDefinition(
            Name="Perim_zone",
            Conditioning=zone_conditioning,
            Constructions=zone_constr_set_perim,
            DomesticHotWater=dhw_setting,
            Loads=zone_load,
            Ventilation=vent_setting,
            Windows=window_setting,
            InternalMassConstruction=wall_int,
        )
        # Core zone
        core = ZoneDefinition(
            Name="Core_zone",
            Conditioning=zone_conditioning,
            Constructions=zone_constr_set_core,
            DomesticHotWater=dhw_setting,
            Loads=zone_load,
            Ventilation=vent_setting,
            Windows=window_setting,
            InternalMassConstruction=wall_int,
        )
        Zones = [perim, core]
        # endregion

        # region Defines building template

        building_template = BuildingTemplate(
            Core=core,
            Perimeter=perim,
            Structure=struct_definition,
            Windows=window_setting,
            Name="Building_template_1",
        )
        BuildingTemplates = [building_template]
        # endregion

        # region Creates json file (Umi template)

        umi_template = UmiTemplateLibrary(
            name="unnamed",
            BuildingTemplates=BuildingTemplates,
            GasMaterials=GasMaterials,
            GlazingMaterials=GlazingMaterials,
            OpaqueConstructions=OpaqueConstructions,
            OpaqueMaterials=OpaqueMaterials,
            WindowConstructions=WindowConstructions,
            StructureInformations=StructureDefinitions,
            DaySchedules=DaySchedules,
            WeekSchedules=WeekSchedules,
            YearSchedules=YearSchedules,
            DomesticHotWaterSettings=DomesticHotWaterSettings,
            VentilationSettings=VentilationSettings,
            WindowSettings=WindowSettings,
            ZoneConditionings=ZoneConditionings,
            ZoneConstructionSets=ZoneConstructionSets,
            ZoneLoads=ZoneLoads,
            ZoneDefinitions=Zones,
        )

        yield umi_template.to_dict()

    def test_manual_template_library(self, manual_umitemplate_library):
        assert no_duplicates(manual_umitemplate_library, attribute="Name")
        assert no_duplicates(manual_umitemplate_library, attribute="$id")

    def test_climatestudio(self, climatestudio):
        template_json = UmiTemplateLibrary(
            name="my_umi_template", BuildingTemplates=[climatestudio]
        ).to_json()
        print(template_json)

    @pytest.mark.skipif(
        os.environ.get("CI", "False").lower() == "true",
        reason="Skipping this test on CI environment",
    )
    @pytest.mark.parametrize(
        "file",
        (
            "tests/input_data/necb/NECB 2011-SmallOffice-NECB HDD Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
            "tests/input_data/necb/NECB 2011-MediumOffice-NECB HDD Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
            "tests/input_data/necb/NECB 2011-LargeOffice-NECB HDD Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
        ),
        ids=("small", "medium", "large"),
    )
    def test_necb_serial(self, file, config):
        settings.log_console = True
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        template = UmiTemplateLibrary.from_idf_files(
            name="my_umi_template",
            idf_files=[file],
            as_version="9-2-0",
            weather=w,
            processors=1,
        )
        assert no_duplicates(template.to_dict(), attribute="Name")
        assert no_duplicates(template.to_dict(), attribute="$id")

    @pytest.mark.skipif(
        os.environ.get("CI", "False").lower() == "true",
        reason="Skipping this test on CI environment",
    )
    def test_necb_parallel(self, config):
        settings.log_console = True
        office = [
            "tests/input_data/necb/NECB 2011-SmallOffice-NECB HDD "
            "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
            "tests/input_data/necb/NECB 2011-MediumOffice-NECB HDD "
            "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
            "tests/input_data/necb/NECB 2011-LargeOffice-NECB HDD "
            "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
        ]
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        template = UmiTemplateLibrary.from_idf_files(
            name="my_umi_template",
            idf_files=office,
            as_version="9-2-0",
            weather=w,
            processors=-1,
        )
        template.to_dict()
        assert no_duplicates(template.to_dict(), attribute="Name")
        assert no_duplicates(template.to_dict(), attribute="$id")

    office = [
        "tests/input_data/necb/NECB 2011-SmallOffice-NECB HDD "
        "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
        "tests/input_data/necb/NECB 2011-MediumOffice-NECB HDD "
        "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
        "tests/input_data/necb/NECB 2011-LargeOffice-NECB HDD "
        "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
    ]

    @pytest.mark.skipif(
        os.environ.get("CI", "False").lower() == "true",
        reason="Skipping this test on CI environment",
    )
    @pytest.mark.parametrize(
        "file", Path("tests/input_data/problematic").files("*CZ5A*.idf")
    )
    def test_cz5a_serial(self, file, config):
        settings.log_console = True
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        template = UmiTemplateLibrary.from_idf_files(
            name=file.stem,
            idf_files=[file],
            as_version="9-2-0",
            weather=w,
            processors=1,
        )
        assert no_duplicates(template.to_dict(), attribute="Name")
        assert no_duplicates(template.to_dict(), attribute="$id")


@pytest.fixture(scope="session")
def climatestudio(config):
    """A building template fixture from a climate studio idf file used in subsequent
    tests"""
    file = "tests/input_data/umi_samples/climatestudio_test.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w, annual=True)
    if idf.sim_info is None:
        idf.simulate()

    bt = BuildingTemplate.from_idf(idf)
    yield bt


@pytest.fixture(scope="session")
def sf_cz5a(config):
    """A building template fixture from a climate studio idf file used in subsequent
    tests"""
    file = "tests/input_data/problematic/SF+CZ5A+USA_IL_Chicago-OHare.Intl.AP.725300+oilfurnace+slab+IECC_2012.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w, annual=True)

    bt = BuildingTemplate.from_idf(idf)
    yield bt
