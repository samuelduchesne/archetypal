import collections
import json
import os

import pytest
from path import Path

import archetypal as ar
from archetypal import settings, get_eplus_dirs, IDF
from archetypal.template.schedule import YearSchedulePart
from archetypal.umi_template import UmiTemplateLibrary
from tests.conftest import no_duplicates


class TestUmiTemplate:
    """Test suite for the UmiTemplateLibrary class"""

    def test_template_to_template(self, config):
        """load the json into UmiTemplateLibrary object, then convert back to json and
        compare"""

        file = "tests/input_data/umi_samples/BostonTemplateLibrary_nodup.json"

        a = UmiTemplateLibrary.read_file(file).to_dict()
        b = TestUmiTemplate.read_json(file)
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
        a = UmiTemplateLibrary.read_idf(
            idf_source, wf, name="Mixed_Files", processors=-1
        )

        data_dict = a.to_dict()
        a.to_json()
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
        a = UmiTemplateLibrary.read_idf(idf_source, wf, name="Mixed_Files")
        a.to_json()
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
    def manual_umitemplate_library(self, config, idf):
        """ Creates Umi template from scratch """

        # region Defines materials

        # Opaque materials
        concrete = ar.OpaqueMaterial(
            Name="Concrete", Conductivity=0.5, SpecificHeat=800, Density=1500, idf=idf
        )
        insulation = ar.OpaqueMaterial(
            Name="Insulation", Conductivity=0.04, SpecificHeat=1000, Density=30, idf=idf
        )
        brick = ar.OpaqueMaterial(
            Name="Brick", Conductivity=1, SpecificHeat=900, Density=1900, idf=idf
        )
        plywood = ar.OpaqueMaterial(
            Name="Plywood", Conductivity=0.13, SpecificHeat=800, Density=540, idf=idf
        )
        OpaqueMaterials = [concrete, insulation, brick, plywood]

        # Glazing materials
        glass = ar.GlazingMaterial(
            Name="Glass",
            Density=2500,
            Conductivity=1,
            SolarTransmittance=0.7,
            SolarReflectanceFront=0.5,
            SolarReflectanceBack=0.5,
            VisibleTransmittance=0.7,
            VisibleReflectanceFront=0.5,
            VisibleReflectanceBack=0.5,
            IRTransmittance=0.7,
            IREmissivityFront=0.5,
            IREmissivityBack=0.5,
            idf=idf,
        )
        GlazingMaterials = [glass]

        # Gas materials
        air = ar.GasMaterial(Name="Air", Conductivity=0.02, Density=1.24, idf=idf)
        GasMaterials = [air]
        # endregion

        # region Defines MaterialLayers

        # Opaque MaterialLayers
        concreteLayer = ar.MaterialLayer(concrete, Thickness=0.2)
        insulationLayer = ar.MaterialLayer(insulation, Thickness=0.5)
        brickLayer = ar.MaterialLayer(brick, Thickness=0.1)
        plywoodLayer = ar.MaterialLayer(plywood, Thickness=0.016)

        # Glazing MaterialLayers
        glassLayer = ar.MaterialLayer(glass, Thickness=0.16)

        # Gas MaterialLayers
        airLayer = ar.MaterialLayer(air, Thickness=0.04)

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
        wall_int = ar.OpaqueConstruction(
            Name="wall_int",
            Layers=[plywoodLayer],
            Surface_Type="Partition",
            Outside_Boundary_Condition="Zone",
            IsAdiabatic=True,
            idf=idf,
        )
        wall_ext = ar.OpaqueConstruction(
            Name="wall_ext",
            Layers=[concreteLayer, insulationLayer, brickLayer],
            Surface_Type="Facade",
            Outside_Boundary_Condition="Outdoors",
            idf=idf,
        )
        floor = ar.OpaqueConstruction(
            Name="floor",
            Layers=[concreteLayer, plywoodLayer],
            Surface_Type="Ground",
            Outside_Boundary_Condition="Zone",
            idf=idf,
        )
        roof = ar.OpaqueConstruction(
            Name="roof",
            Layers=[plywoodLayer, insulationLayer, brickLayer],
            Surface_Type="Roof",
            Outside_Boundary_Condition="Outdoors",
            idf=idf,
        )
        OpaqueConstructions = [wall_int, wall_ext, floor, roof]

        # Window construction
        window = ar.WindowConstruction(
            Name="Window", Layers=[glassLayer, airLayer, glassLayer], idf=idf
        )
        WindowConstructions = [window]

        # Structure definition
        mass_ratio = ar.MassRatio(Material=plywood, NormalRatio=1, HighLoadRatio=1)
        struct_definition = ar.StructureInformation(
            Name="Structure", MassRatios=[mass_ratio], idf=idf
        )
        StructureDefinitions = [struct_definition]
        # endregion

        # region Defines schedules

        # Day schedules
        # Always on
        sch_d_on = ar.DaySchedule.from_values(
            Values=[1] * 24, Category="Day", Type="Fraction", Name="AlwaysOn", idf=idf,
        )
        # Always off
        sch_d_off = ar.DaySchedule.from_values(
            Values=[0] * 24, Category="Day", Type="Fraction", Name="AlwaysOff", idf=idf,
        )
        # DHW
        sch_d_dhw = ar.DaySchedule.from_values(
            Values=[0.3] * 24, Category="Day", Type="Fraction", Name="DHW", idf=idf,
        )
        # Internal gains
        sch_d_gains = ar.DaySchedule.from_values(
            Values=[0] * 6 + [0.5, 0.6, 0.7, 0.8, 0.9, 1] + [0.7] * 6 + [0.4] * 6,
            Category="Day",
            Type="Fraction",
            Name="Gains",
            idf=idf,
        )
        DaySchedules = [sch_d_on, sch_d_dhw, sch_d_gains, sch_d_off]

        # Week schedules
        # Always on
        sch_w_on = ar.WeekSchedule(
            Days=[sch_d_on, sch_d_on, sch_d_on, sch_d_on, sch_d_on, sch_d_on, sch_d_on],
            Category="Week",
            Type="Fraction",
            Name="AlwaysOn",
            idf=idf,
        )
        # Always off
        sch_w_off = ar.WeekSchedule(
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
            idf=idf,
        )
        # DHW
        sch_w_dhw = ar.WeekSchedule(
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
            idf=idf,
        )
        # Internal gains
        sch_w_gains = ar.WeekSchedule(
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
            Type="Fractio",
            Name="Gains",
            idf=idf,
        )
        WeekSchedules = [sch_w_on, sch_w_off, sch_w_dhw, sch_w_gains]

        # Year schedules
        # Always on
        dict_on = {
            "Category": "Year",
            "Parts": [
                YearSchedulePart(
                    **{
                        "FromDay": 1,
                        "FromMonth": 1,
                        "ToDay": 31,
                        "ToMonth": 12,
                        "Schedule": sch_w_on,
                    }
                )
            ],
            "Type": "Fraction",
            "Name": "AlwaysOn",
            "idf": idf,
        }
        sch_y_on = ar.YearSchedule.from_parts(**dict_on)
        # Always off
        dict_off = {
            "Category": "Year",
            "Parts": [
                YearSchedulePart(
                    **{
                        "FromDay": 1,
                        "FromMonth": 1,
                        "ToDay": 31,
                        "ToMonth": 12,
                        "Schedule": sch_w_off,
                    }
                )
            ],
            "Type": "Fraction",
            "Name": "AlwaysOff",
            "idf": idf,
        }
        sch_y_off = ar.YearSchedule.from_parts(**dict_off)
        # DHW
        dict_dhw = {
            "Category": "Year",
            "Parts": [
                YearSchedulePart(
                    **{
                        "FromDay": 1,
                        "FromMonth": 1,
                        "ToDay": 31,
                        "ToMonth": 12,
                        "Schedule": sch_w_dhw,
                    }
                )
            ],
            "Type": "Fraction",
            "Name": "DHW",
            "idf": idf,
        }
        sch_y_dhw = ar.YearSchedule.from_parts(**dict_dhw)
        # Internal gains
        dict_gains = {
            "Category": "Year",
            "Parts": [
                YearSchedulePart(
                    **{
                        "FromDay": 1,
                        "FromMonth": 1,
                        "ToDay": 31,
                        "ToMonth": 12,
                        "Schedule": sch_w_gains,
                    }
                )
            ],
            "Type": "Fraction",
            "Name": "Gains",
            "idf": idf,
        }
        sch_y_gains = ar.YearSchedule.from_parts(**dict_gains)
        YearSchedules = [sch_y_on, sch_y_off, sch_y_dhw, sch_y_gains]
        # endregion

        # region Defines Window settings

        window_setting = ar.WindowSetting(
            Name="window_setting_1",
            Construction=window,
            AfnWindowAvailability=sch_y_off,
            ShadingSystemAvailabilitySchedule=sch_y_off,
            ZoneMixingAvailabilitySchedule=sch_y_off,
            idf=idf,
        )
        WindowSettings = [window_setting]
        # endregion

        # region Defines DHW settings

        dhw_setting = ar.DomesticHotWaterSetting(
            Name="dhw_setting_1",
            IsOn=True,
            WaterSchedule=sch_y_dhw,
            FlowRatePerFloorArea=0.03,
            WaterSupplyTemperature=65,
            WaterTemperatureInlet=10,
            idf=idf,
        )
        DomesticHotWaterSettings = [dhw_setting]
        # endregion

        # region Defines ventilation settings

        vent_setting = ar.VentilationSetting(
            Name="vent_setting_1",
            NatVentSchedule=sch_y_off,
            ScheduledVentilationSchedule=sch_y_off,
            idf=idf,
        )
        VentilationSettings = [vent_setting]
        # endregion

        # region Defines zone conditioning setttings

        zone_conditioning = ar.ZoneConditioning(Name="conditioning_setting_1",
                                                HeatingSchedule=sch_y_on,
                                                CoolingSchedule=sch_y_on,
                                                MechVentSchedule=sch_y_off, idf=idf)
        ZoneConditionings = [zone_conditioning]
        # endregion

        # region Defines zone construction sets

        # Perimeter zone
        zone_constr_set_perim = ar.ZoneConstructionSet(
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
            idf=idf,
        )
        # Core zone
        zone_constr_set_core = ar.ZoneConstructionSet(
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
            idf=idf,
        )
        ZoneConstructionSets = [zone_constr_set_perim, zone_constr_set_core]
        # endregion

        # region Defines zone loads

        zone_load = ar.ZoneLoad(
            Name="zone_load_1",
            EquipmentAvailabilitySchedule=sch_y_gains,
            LightsAvailabilitySchedule=sch_y_gains,
            OccupancySchedule=sch_y_gains,
            idf=idf,
        )
        ZoneLoads = [zone_load]
        # endregion

        # region Defines zones

        # Perimeter zone
        perim = ar.ZoneDefinition(
            Name="Perim_zone",
            idf=idf,
            Conditioning=zone_conditioning,
            Constructions=zone_constr_set_perim,
            DomesticHotWater=dhw_setting,
            Loads=zone_load,
            Ventilation=vent_setting,
            Windows=window_setting,
            InternalMassConstruction=wall_int,
        )
        # Core zone
        core = ar.ZoneDefinition(
            Name="Core_zone",
            idf=idf,
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

        building_template = ar.BuildingTemplate(
            Core=core,
            Perimeter=perim,
            Structure=struct_definition,
            Windows=window_setting,
            Name="Building_template_1",
            idf=idf,
        )
        BuildingTemplates = [building_template]
        # endregion

        # region Creates json file (Umi template)

        umi_template = ar.UmiTemplateLibrary(
            name="unnamed",
            BuildingTemplates=BuildingTemplates,
            GasMaterials=GasMaterials,
            GlazingMaterials=GlazingMaterials,
            OpaqueConstructions=OpaqueConstructions,
            OpaqueMaterials=OpaqueMaterials,
            WindowConstructions=WindowConstructions,
            StructureDefinitions=StructureDefinitions,
            DaySchedules=DaySchedules,
            WeekSchedules=WeekSchedules,
            YearSchedules=YearSchedules,
            DomesticHotWaterSettings=DomesticHotWaterSettings,
            VentilationSettings=VentilationSettings,
            WindowSettings=WindowSettings,
            ZoneConditionings=ZoneConditionings,
            ZoneConstructionSets=ZoneConstructionSets,
            ZoneLoads=ZoneLoads,
            Zones=Zones,
        )

        yield umi_template.to_dict()

    def test_manual_template_library(self, manual_umitemplate_library):
        assert no_duplicates(manual_umitemplate_library, attribute="Name")
        assert no_duplicates(manual_umitemplate_library, attribute="$id")

    def test_climatestudio(self, climatestudio):
        template_json = ar.UmiTemplateLibrary(
            name="my_umi_template", BuildingTemplates=[climatestudio]
        ).to_json(all_zones=True)
        print(template_json)

    @pytest.mark.skipif(
        os.environ.get("CI", "False").lower() == "true",
        reason="Skipping this test on CI environment because it needs EnergyPlys 8-7-0",
    )
    def test_sf_cz5a(self, config):
        from path import Path

        settings.log_console = False
        files = Path("tests/input_data/problematic").files("*CZ5A*.idf")
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        template = ar.UmiTemplateLibrary.read_idf(
            name="my_umi_template", idf_files=files, as_version="9-2-0", weather=w
        )
        template.to_json()
        assert no_duplicates(template.to_dict(), attribute="Name")
        assert no_duplicates(template.to_dict(), attribute="$id")

    office = [
        r"tests\input_data\necb\NECB 2011-SmallOffice-NECB HDD "
        r"Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
        r"tests\input_data\necb\NECB 2011-MediumOffice-NECB HDD "
        r"Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
        r"tests\input_data\necb\NECB 2011-LargeOffice-NECB HDD "
        r"Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf",
    ]

    @pytest.mark.skipif(
        os.environ.get("CI", "False").lower() == "true",
        reason="Skipping this test on CI environment",
    )
    @pytest.mark.parametrize("file", office, ids=["small", "medium", "large"])
    def test_necb_serial(self, file, config):
        settings.log_console = True
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        template = ar.UmiTemplateLibrary.read_idf(
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
        template = ar.UmiTemplateLibrary.read_idf(
            name="my_umi_template",
            idf_files=office,
            as_version="9-2-0",
            weather=w,
            processors=-1,
        )
        template.to_json()
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
        template = ar.UmiTemplateLibrary.read_idf(
            name=file.stem,
            idf_files=[file],
            as_version="9-2-0",
            weather=w,
            processors=1,
        )
        template.to_json()
        assert no_duplicates(template.to_dict(), attribute="Name")
        assert no_duplicates(template.to_dict(), attribute="$id")


@pytest.fixture(scope="session")
def climatestudio(config):
    """A building template fixture from a climate studio idf file used in subsequent
    tests"""
    file = "tests/input_data/umi_samples/climatestudio_test.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w, annual=True)

    from archetypal.template import BuildingTemplate

    bt = BuildingTemplate.from_idf(idf)
    yield bt


@pytest.fixture(scope="session")
def sf_cz5a(config):
    """A building template fixture from a climate studio idf file used in subsequent
    tests"""
    file = "tests/input_data/problematic/SF+CZ5A+USA_IL_Chicago-OHare.Intl.AP.725300+oilfurnace+slab+IECC_2012.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w, annual=True)

    from archetypal.template import BuildingTemplate

    bt = BuildingTemplate.from_idf(idf)
    yield bt
