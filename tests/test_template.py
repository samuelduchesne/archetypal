import itertools
from copy import copy

import numpy as np
import pytest
from eppy.bunch_subclass import EpBunch

from archetypal import IDF, settings
from archetypal.eplus_interface.version import get_eplus_dirs
from archetypal.simple_glazing import calc_simple_glazing
from archetypal.template.building_template import BuildingTemplate
from archetypal.template.conditioning import ZoneConditioning, EconomizerTypes
from archetypal.template.dhw import DomesticHotWaterSetting
from archetypal.template.load import DimmingTypes, ZoneLoad
from archetypal.template.materials.gas_layer import GasLayer
from archetypal.template.materials.gas_material import GasMaterial
from archetypal.template.materials.glazing_material import GlazingMaterial
from archetypal.template.materials.material_layer import MaterialLayer
from archetypal.template.materials.nomass_material import NoMassMaterial
from archetypal.template.materials.opaque_material import OpaqueMaterial
from archetypal.template.constructions.opaque_construction import OpaqueConstruction
from archetypal.template.constructions.base_construction import (
    ConstructionBase,
    LayeredConstruction,
)
from archetypal.template.schedule import (
    DaySchedule,
    UmiSchedule,
    WeekSchedule,
    YearSchedule,
    YearSchedulePart,
)
from archetypal.template.structure import MassRatio, StructureInformation
from archetypal.template.umi_base import UniqueName
from archetypal.template.ventilation import VentilationSetting
from archetypal.template.constructions.window_construction import WindowConstruction
from archetypal.template.window_setting import WindowSetting
from archetypal.template.zone_construction_set import ZoneConstructionSet
from archetypal.template.zonedefinition import ZoneDefinition
from archetypal.template.constructions.internal_mass import InternalMass
from archetypal.utils import reduce


@pytest.fixture(scope="class")
def small_idf(small_idf_obj):
    """An IDF model"""
    if small_idf_obj.sim_info is None:
        idf.simulate()
    yield small_idf_obj


@pytest.fixture(scope="class")
def small_idf_copy(config):
    """An IDF model

    Args:
        config:
    """
    file = "tests/input_data/umi_samples/B_Off_0.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w)
    yield idf


@pytest.fixture(scope="class")
def small_idf_obj(config):
    """An IDF model. Yields just the idf object."""
    file = "tests/input_data/umi_samples/B_Off_0.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w)
    yield idf


@pytest.fixture(scope="module")
def other_idf(config):
    """Another IDF object with a different signature.

    Args:
        config:
    """
    file = "tests/input_data/umi_samples/B_Res_0_Masonry.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w)
    yield idf


@pytest.fixture(scope="class")
def other_idf_object(config):
    """Another IDF object (same as other_idf). Yields just the idf object

    Args:
        config:
    """
    file = "tests/input_data/umi_samples/B_Res_0_Masonry.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w)
    if idf.sim_info is None:
        idf.simulate()
    yield idf


@pytest.fixture(scope="module")
def other_idf_object_copy(config):
    """Another IDF object with a different signature.

    Args:
        config:
    """
    file = "tests/input_data/umi_samples/B_Res_0_Masonry.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w)
    if idf.sim_info is None:
        idf.simulate()
    yield idf


@pytest.fixture(scope="module")
def small_office(config):
    file = (
        "tests/input_data/necb/NECB 2011-SmallOffice-NECB HDD "
        "Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf"
    )
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF(file, epw=w)
    yield idf


@pytest.fixture(scope="module")
def idf():
    yield IDF(prep_outputs=False)


@pytest.fixture(scope="class", params=["RefBldgWarehouseNew2004_Chicago.idf"])
def warehouse(config, request):
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF.from_example_files(request.param, epw=w, annual=True)
    if idf.sim_info is None:
        idf.simulate()
    yield idf


core_name = "core"
perim_name = "perim"


class TestUnique:
    """Series of tests for the :class:`Unique` class"""

    # todo: Implement tests for Unique class
    pass


class TestUmiBase:
    """Series of tests for the :class:`UmiBase` class"""

    # todo: Implement tests for UmiBase class
    pass


class TestMaterialLayer:
    """Series of tests for the :class:`MaterialLayer` class"""

    @pytest.fixture()
    def mat_a(self, idf):
        yield OpaqueMaterial(Conductivity=0.1, SpecificHeat=4180, Name="mat_a", idf=idf)

    def test_init_material_layer(self, mat_a):
        """Test constructor."""
        mat_layer = MaterialLayer(mat_a, 0.1)

        mat_layer_dup = mat_layer.duplicate()

        assert mat_layer.Material == mat_layer_dup.Material == mat_a
        assert mat_layer.Thickness == mat_layer_dup.Thickness == 0.1


class TestConstructionBase:
    """Series of tests for the :class:`ConstructionBase` class"""

    def test_init_construction_base(self):
        """Test constructor."""
        construction_base = ConstructionBase("base", 0, 0, 0, 0, 0)
        construction_base_dup = construction_base.duplicate()

        assert construction_base == construction_base_dup
        assert (
            construction_base.AssemblyCarbon
            == construction_base_dup.AssemblyCarbon
            == 0
        )
        assert construction_base.id != construction_base_dup.id


class TestLayeredConstruction:
    """Series of tests for the :class:`LayeredConstruction` class"""

    @pytest.fixture()
    def mat_a(self):
        yield OpaqueMaterial(Conductivity=0.1, SpecificHeat=4180, Name="mat_a")

    def test_init_layerd_construction(self, mat_a):
        """Test constructor."""

        layers = [MaterialLayer(mat_a, 0.1), MaterialLayer(mat_a, 0.1)]

        layered_construction = LayeredConstruction(
            Layers=layers, Name="layered_construction"
        )

        layered_construction_dup = layered_construction.duplicate()

        assert layered_construction == layered_construction_dup


class TestMassRatio:
    """Series of tests for the :class:`MassRatio` class"""

    @pytest.fixture()
    def structure_material(self):
        yield OpaqueMaterial(
            Name="Steel General",
            Conductivity=45.3,
            SpecificHeat=500,
            SolarAbsorptance=0.4,
            ThermalEmittance=0.9,
            VisibleAbsorptance=0.4,
            Roughness="Rough",
            Cost=0,
            Density=7830,
            MoistureDiffusionResistance=50,
            EmbodiedCarbon=1.37,
            EmbodiedEnergy=20.1,
            TransportCarbon=0.067,
            TransportDistance=500,
            TransportEnergy=0.94,
            SubstitutionRatePattern=[1],
            SubstitutionTimestep=100,
            DataSource="BostonTemplateLibrary.json",
        )

    def test_init_mass_ratio(self, structure_material):
        """Test constructor."""
        from archetypal.template.structure import MassRatio

        mass_ratio = MassRatio(600, structure_material, 300)
        mass_ratio_dup = mass_ratio.duplicate()

        assert mass_ratio == mass_ratio_dup
        assert mass_ratio is not mass_ratio_dup
        assert mass_ratio.HighLoadRatio == mass_ratio_dup.HighLoadRatio == 600

    def test_generic_mass_ratio(self):
        from archetypal.template.structure import MassRatio

        mass_ratio = MassRatio.generic()
        assert mass_ratio.Material.Name == "Steel General"


class TestYearScheduleParts:
    """Series of tests for the :class:`YearSchedulePart` class"""

    # todo: Implement tests for YearSchedulePart class
    pass


class TestDaySchedule:
    """Series of tests for the :class:`DaySchedule` class"""

    def test_init_day_schedule(self):
        """Test constructor."""
        from archetypal.template.schedule import DaySchedule

        day_schedule = DaySchedule("day_1", [0] * 24)
        day_schedule_dup = day_schedule.duplicate()

        assert day_schedule.Name == day_schedule_dup.Name == "day_1"
        assert (day_schedule.all_values == day_schedule_dup.all_values).all()

    def test_from_values(self):
        """test the `from_values` constructor."""
        from archetypal.template.schedule import DaySchedule

        values = np.array(range(0, 24))
        kwargs = {
            "Category": "Day",
            "Type": "Fraction",
            "Name": "hourlyAllOn",
            "Values": values,
        }
        sched = DaySchedule.from_values(**kwargs)
        assert len(sched.all_values) == 24.0
        assert repr(sched)

    def test_daySchedule_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""

        day_schedule = DaySchedule("A", [0] * 24, Type="Fraction")
        day_dict = day_schedule.to_dict()
        day_schedule_dup = DaySchedule.from_dict(day_dict)
        assert day_schedule == day_schedule_dup

    @pytest.fixture(scope="class")
    def schedules_idf(self):
        yield IDF("tests/input_data/schedules/schedules.idf")

    @pytest.fixture()
    def schedule_day_interval(self, schedules_idf):
        yield schedules_idf.idfobjects["SCHEDULE:DAY:INTERVAL"]

    @pytest.fixture()
    def schedule_day_hourly(self, schedules_idf):
        yield schedules_idf.idfobjects["SCHEDULE:DAY:HOURLY"]

    @pytest.fixture()
    def schedule_day_list(self, schedules_idf):
        yield schedules_idf.idfobjects["SCHEDULE:DAY:LIST"]

    @pytest.fixture()
    def all_schedule_days(
        self, schedule_day_interval, schedule_day_hourly, schedule_day_list
    ):
        yield itertools.chain(schedule_day_list, schedule_day_hourly, schedule_day_list)

    def test_from_epbunch(self, all_schedule_days):
        """test the `from_epbunch` constructor."""

        for epbunch in all_schedule_days:
            sched = DaySchedule.from_epbunch(epbunch)
            sched_dup = sched.duplicate()
            assert len(sched.all_values) == len(sched_dup.all_values) == 24
            assert repr(sched)


class TestWeekSchedule:
    """Series of tests for the :class:`WeekSchedule` class"""

    @pytest.fixture()
    def schedule_week_daily(self, schedules_idf):
        yield schedules_idf.idfobjects["SCHEDULE:WEEK:DAILY"]

    @pytest.fixture()
    def schedule_week_compact(self, schedules_idf):
        yield schedules_idf.idfobjects["SCHEDULE:WEEK:COMPACT"]

    @pytest.fixture()
    def sch_d_on(self):
        """Creates 2 DaySchedules: 1 always ON."""
        yield DaySchedule.from_values(
            Name="AlwaysOn", Values=[1] * 24, Type="Fraction", Category="Day"
        )

    @pytest.fixture()
    def sch_d_off(self):
        """Creates DaySchedules: 1 always OFF."""
        yield DaySchedule.from_values(
            Name="AlwaysOff", Values=[0] * 24, Type="Fraction", Category="Day"
        )

    def test_init(self, sch_d_on, sch_d_off):
        """Creates WeekSchedule from DaySchedule."""

        # List of 7 dict with id of DaySchedule, representing the 7 days of the week
        days = [sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on]
        # Creates WeekSchedule from list of DaySchedule
        a = WeekSchedule(
            Days=days,
            Category="Week",
            Type="Fraction",
            Name="OnOff_1",
        )

    @pytest.fixture(scope="class")
    def schedules_idf(self):
        yield IDF("tests/input_data/schedules/schedules.idf")

    def test_from_epbunch_daily(self, schedule_week_daily):
        for epbunch in schedule_week_daily:
            assert WeekSchedule.from_epbunch(epbunch)

    @pytest.mark.skip("Not yet implemented for Schedule:Week:Compact.")
    def test_from_epbunch_compact(self, schedule_week_compact):
        for epbunch in schedule_week_compact:
            assert WeekSchedule.from_epbunch(epbunch)

    def test_from_dict(self, sch_d_on, sch_d_off):
        days = [sch_d_on, sch_d_off]
        # Dict of a WeekSchedule (like it would be written in json file)
        dict_w_on = {
            "$id": "1",
            "Category": "Week",
            "Days": [
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_on.id},
                {"$ref": sch_d_off.id},
                {"$ref": sch_d_on.id},
            ],
            "Type": "Fraction",
            "Name": "OnOff_2",
        }
        # Creates WeekSchedule from dict (from json)
        a = WeekSchedule.from_dict(
            dict_w_on, day_schedules={a.id: a for a in days}, allow_duplicates=True
        )
        b = a.duplicate()
        # Makes sure WeekSchedules created with 2 methods have the same values
        # And different ids
        assert np.array_equal(a.all_values, b.all_values)
        assert a.id != b.id

    def test_from_to_dict(self, sch_d_on, sch_d_off):
        """Make dict with `to_dict` and load again with `from_dict`."""
        # List of 7 dict with id of DaySchedule, representing the 7 days of the week
        days = [sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on]
        # Creates WeekSchedule from list of DaySchedule
        a = WeekSchedule(
            Days=days,
            Category="Week",
            Type="Fraction",
            Name="OnOff_1",
        )

        week_schedule_dict = a.to_dict()

        b = WeekSchedule.from_dict(
            week_schedule_dict, day_schedules={a.id: a for a in days}
        )
        assert a == b
        assert a is not b


class TestYearSchedule:
    """Series of tests for the :class:`YearSchedule` class"""

    def test_yearSchedule(self):
        """Creates YearSchedule from a dictionary."""
        # Creates 2 DaySchedules : 1 always ON and 1 always OFF
        sch_d_on = DaySchedule.from_values(
            Name="AlwaysOn", Values=[1] * 24, Type="Fraction", Category="Day"
        )
        sch_d_off = DaySchedule.from_values(
            Name="AlwaysOff", Values=[0] * 24, Type="Fraction", Category="Day"
        )

        # List of 7 dict with id of DaySchedule, representing the 7 days of the week
        days = [sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on]
        # Creates WeekSchedule from list of DaySchedule
        sch_w_on_off = WeekSchedule(
            Days=days,
            Category="Week",
            Type="Fraction",
            Name="OnOff",
        )

        # Dict of a YearSchedule (like it would be written in json file)
        dict_year = {
            "$id": "1",
            "Category": "Year",
            "Parts": [
                {
                    "FromDay": 1,
                    "FromMonth": 1,
                    "ToDay": 31,
                    "ToMonth": 12,
                    "Schedule": {"$ref": sch_w_on_off.id},
                }
            ],
            "Type": "Fraction",
            "Name": "OnOff",
        }
        # Creates YearSchedule from dict (from json)
        a = YearSchedule.from_dict(
            dict_year,
            week_schedules={a.id: a for a in [sch_w_on_off]},
            allow_duplicates=True,
        )

        # Makes sure YearSchedule has the same values as concatenate WeekSchedule
        assert a.all_values == pytest.approx(np.resize(sch_w_on_off.all_values, 8760))

    def test_year_schedule_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""
        sch_d_on = DaySchedule.from_values(
            Name="AlwaysOn", Values=[1] * 24, Type="Fraction", Category="Day"
        )
        sch_d_off = DaySchedule.from_values(
            Name="AlwaysOff", Values=[0] * 24, Type="Fraction", Category="Day"
        )

        # List of 7 dict with id of DaySchedule, representing the 7 days of the week
        days = [sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on]
        # Creates WeekSchedule from list of DaySchedule
        sch_w_on_off = WeekSchedule(
            Days=days,
            Category="Week",
            Type="Fraction",
            Name="OnOff",
        )

        parts = [YearSchedulePart(1, 1, 31, 12, sch_w_on_off)]

        sch_year = YearSchedule(Name="OnOff", Parts=parts)

        sch_dict = sch_year.to_dict()

        sch_year_dup = YearSchedule.from_dict(
            sch_dict, week_schedules={a.id: a for a in [sch_w_on_off]}
        )

        assert sch_year == sch_year_dup


class TestWindowType:
    """Series of tests for the :class:`YearSchedulePart` class"""

    # todo: Implement tests for WindowType class

    pass


class TestOpaqueMaterial:
    """Series of tests for the :class:`OpaqueMaterial` class"""

    @pytest.fixture()
    def mat_a(self):
        yield OpaqueMaterial(Conductivity=0.1, SpecificHeat=4180, Name="mat_a")

    @pytest.fixture()
    def mat_b(self):
        yield OpaqueMaterial(Conductivity=0.2, SpecificHeat=4180, Name="mat_b")

    @pytest.fixture()
    def idf(self):
        file = "tests/input_data/umi_samples/B_Off_0.idf"
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        yield IDF(file, epw=w)

    def test_add_materials(self, mat_a, mat_b):
        """Test __add__()."""
        mat_c = mat_a + mat_b
        assert mat_c
        assert mat_c.Conductivity == pytest.approx(0.150)
        assert mat_a.id != mat_b.id != mat_c.id

        mat_d = mat_c + mat_a
        assert mat_d != mat_a != mat_c

    def test_iadd_materials(self):
        """test __iadd__()."""
        mat_a = OpaqueMaterial(Conductivity=0.1, SpecificHeat=4180, Name="mat_ia")
        id_ = mat_a.id  # storing mat_a's id.

        mat_b = OpaqueMaterial(Conductivity=0.2, SpecificHeat=4180, Name="mat_ib")
        mat_a += mat_b
        assert mat_a
        assert mat_a.Conductivity == pytest.approx(0.150)
        assert mat_a.id == id_  # id should not change
        assert mat_a.id != mat_b.id

    def test_from_to_dict(self):
        """Get OpaqueMaterial, convert to json, load back and compare."""
        data = {
            "$id": "10",
            "MoistureDiffusionResistance": 50.0,
            "Roughness": "Rough",
            "SolarAbsorptance": 0.6,
            "SpecificHeat": 1200.0,
            "ThermalEmittance": 0.85,
            "VisibleAbsorptance": 0.6,
            "Conductivity": 0.14,
            "Cost": 0.0,
            "Density": 650.0,
            "EmbodiedCarbon": 0.45,
            "EmbodiedEnergy": 7.4,
            "SubstitutionRatePattern": [0.5, 1.0],
            "SubstitutionTimestep": 20.0,
            "TransportCarbon": 0.067,
            "TransportDistance": 500.0,
            "TransportEnergy": 0.94,
            "Category": "Uncategorized",
            "Comments": None,
            "DataSource": "default",
            "Name": "B_Wood_Floor",
        }
        opaque_mat = OpaqueMaterial.from_dict(data)
        opaque_mat_data = opaque_mat.to_dict()
        opaque_mat_dup = OpaqueMaterial.from_dict(opaque_mat_data)
        assert opaque_mat == opaque_mat_dup

    def test_hash_eq_opaq_mat(self):
        """Test equality and hashing of :class:`TestOpaqueMaterial`."""

        data = {
            "$id": "MATERIAL 1",
            "Name": "A2 - 4 IN DENSE FACE BRICK",
            "Roughness": "Rough",
            "Thickness": 0.1014984,
            "Conductivity": 1.245296,
            "Density": 2082.4,
            "SpecificHeat": 920.48,
            "ThermalEmittance": 0.9,
            "SolarAbsorptance": 0.93,
            "VisibleAbsorptance": 0.93,
        }
        om = OpaqueMaterial.from_dict(data)
        om_2 = om.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert om == om_2
        assert hash(om) == hash(om_2)
        assert om is not om_2

        # hash is used to find object in lookup table
        om_list = [om]
        assert om in om_list
        assert om_2 in om_list  # This is weird but expected

        om_list.append(om_2)
        assert om_2 in om_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(om_list)) == 1

        # dict behavior
        om_dict = {om: "this_idf", om_2: "same_idf"}
        assert len(om_dict) == 1

        om_2.Name = "some other name"
        # even if name changes, they should be equal
        assert om_2 == om

        om_dict = {om: "this_idf", om_2: "same_idf"}
        assert om in om_dict
        assert len(om_dict) == 2

        # if an attribute changed, equality is lost
        om_2.Cost = 69
        assert om != om_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(om_list)) == 2

        # 2 OpaqueMaterial from different idf should have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same characteristics (Thickness, Roughness, etc.)
        om_3 = om.duplicate()
        om_3.DataSource = "Other IDF"
        assert hash(om) == hash(om_3)
        assert id(om) != id(om_3)
        assert om is not om_3
        assert om == om_3

    def test_material_new(self):
        gypsum = OpaqueMaterial(
            Name="GP01 GYPSUM",
            Conductivity=0.16,
            SpecificHeat=1090,
            Density=800,
            Roughness="Smooth",
            SolarAbsorptance=0.7,
            ThermalEmittance=0.9,
            VisibleAbsorptance=0.5,
            DataSource="ASHRAE 90.1-2007",
            MoistureDiffusionResistance=8.3,
        )
        gypsum_duplicate = gypsum.duplicate()

        assert gypsum.Name == gypsum_duplicate.Name == "GP01 GYPSUM"
        assert gypsum.Conductivity == gypsum_duplicate.Conductivity == 0.16
        assert gypsum.SpecificHeat == gypsum_duplicate.SpecificHeat == 1090
        assert gypsum.Density == gypsum_duplicate.Density == 800
        assert gypsum.Roughness == gypsum_duplicate.Roughness == "Smooth"
        assert gypsum.SolarAbsorptance == gypsum_duplicate.SolarAbsorptance == 0.7
        assert gypsum.ThermalEmittance == gypsum_duplicate.ThermalEmittance == 0.9
        assert gypsum.VisibleAbsorptance == gypsum_duplicate.VisibleAbsorptance == 0.5
        assert (
            gypsum.MoistureDiffusionResistance
            == gypsum_duplicate.MoistureDiffusionResistance
            == 8.3
        )

    @pytest.fixture()
    def materials_idf(self):
        """An IDF object with different material definitions."""
        file = "tests/input_data/materials.idf"
        yield IDF(file, prep_outputs=False)

    def test_from_epbunch(self, materials_idf):

        for epbunch in itertools.chain(
            materials_idf.idfobjects["MATERIAL"],
            materials_idf.idfobjects["MATERIAL:NOMASS"],
            materials_idf.idfobjects["MATERIAL:AIRGAP"],
        ):
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(epbunch)
            opaqMat_json = opaqMat_epBunch.to_dict()
            assert OpaqueMaterial.from_dict(opaqMat_json) == opaqMat_epBunch


class TestNoMassMaterial:
    """NoMassMaterial tests."""

    def test_init_nomass_material(self):
        no_mass = NoMassMaterial(
            Name="R13LAYER",
            RValue=2.290965,
            ThermalEmittance=0.9,
            SolarAbsorptance=0.75,
            VisibleAbsorptance=0.75,
        )
        no_mass_dup = no_mass.duplicate()

        assert no_mass == no_mass_dup

    def test_from_dict_to_dict(self):

        data = {
            "$id": "140532076832464",
            "Name": "R13LAYER",
            "MoistureDiffusionResistance": 50.0,
            "Roughness": "Rough",
            "SolarAbsorptance": 0.75,
            "ThermalEmittance": 0.9,
            "VisibleAbsorptance": 0.75,
            "RValue": 2.29,
            "Cost": 0.0,
            "EmbodiedCarbon": 0.0,
            "EmbodiedEnergy": 0.0,
            "SubstitutionRatePattern": [1.0],
            "SubstitutionTimestep": 100.0,
            "TransportCarbon": 0.0,
            "TransportDistance": 0.0,
            "TransportEnergy": 0.0,
            "Category": "Uncategorized",
            "Comments": None,
            "DataSource": None,
        }
        no_mass = NoMassMaterial.from_dict(data)
        to_data = dict(no_mass.to_dict())
        to_data.pop("$id")
        assert to_data == data

    def test_to_epbunch(self, idf):
        """Test to_epbunch."""
        no_mass = NoMassMaterial(
            Name="R13LAYER",
            RValue=2.290965,
            ThermalEmittance=0.9,
            SolarAbsorptance=0.75,
            VisibleAbsorptance=0.75,
        )
        epbunch = no_mass.to_epbunch(idf)
        assert idf.getobject("MATERIAL:NOMASS", epbunch.Name)

    def test_add(self):
        no_mass = NoMassMaterial(
            Name="R13LAYER",
            RValue=2.290965,
            ThermalEmittance=0.9,
            SolarAbsorptance=0.75,
            VisibleAbsorptance=0.75,
        )
        no_mass_dup = no_mass.duplicate()

        no_mass_addition = no_mass + no_mass_dup
        assert no_mass_addition


class TestGlazingMaterial:
    """Series of tests for the :class:`GlazingMaterial` class"""

    def test_simple_glazing_material(self):
        name = "A Glass Material"
        glass = GlazingMaterial(
            Name=name,
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
        assert glass.Name == name

    def test_add_glazing_material(self):
        """test __add__() for OpaqueMaterial."""
        sg_a = calc_simple_glazing(0.763, 2.716, 0.812)
        sg_b = calc_simple_glazing(0.578, 2.413, 0.706)
        mat_a = GlazingMaterial(Name="mat_a", **sg_a)
        mat_b = GlazingMaterial(Name="mat_b", **sg_b)

        mat_c = mat_a + mat_b

        assert mat_c
        assert mat_a.id != mat_b.id != mat_c.id

    def test_iadd_glazing_material(self):
        """test __iadd__() for OpaqueMaterial."""
        sg_a = calc_simple_glazing(0.763, 2.716, 0.812)
        sg_b = calc_simple_glazing(0.578, 2.413, 0.706)
        mat_a = GlazingMaterial(Name="mat_ia", **sg_a)
        mat_b = GlazingMaterial(Name="mat_ib", **sg_b)

        id_ = mat_a.id  # storing mat_a's id.

        mat_a += mat_b

        assert mat_a
        assert mat_a.id == id_  # id should not change
        assert mat_a.id != mat_b.id

    # todo: Implement from_to_dict test for GlazingMaterial class

    def test_hash_eq_glaz_mat(self):
        """Test equality and hashing of :class:`OpaqueConstruction`."""
        from copy import copy

        sg_a = calc_simple_glazing(0.763, 2.716, 0.812)
        mat_a = GlazingMaterial(Name="mat_ia", **sg_a)
        mat_b = copy(mat_a)

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert mat_a == mat_b
        assert hash(mat_a) == hash(mat_b)
        assert mat_a is not mat_b

        # hash is used to find object in lookup table
        glm_list = [mat_a]
        assert mat_a in glm_list
        assert mat_b in glm_list  # This is weird but expected

        glm_list.append(mat_b)
        assert mat_b in glm_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(glm_list)) == 1

        # dict behavior
        glm_dict = {mat_a: "this_idf", mat_b: "same_idf"}
        assert len(glm_dict) == 1

        mat_b.Name = "some other name"
        # even if name changes, they should be equal
        assert mat_b == mat_a

        glm_dict = {mat_a: "this_idf", mat_b: "same_idf"}
        assert mat_a in glm_dict
        assert len(glm_dict) == 2

        # if an attribute changed, equality is lost
        mat_b.Cost = 69
        assert mat_a != mat_b

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(glm_list)) == 2

        # 2 GasMaterial from same json should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same layers (Material and Thickness)
        mat_3 = copy(mat_a)
        mat_3.Name = "other name"
        assert hash(mat_a) != hash(mat_3)
        assert id(mat_a) != id(mat_3)
        assert mat_a is not mat_3
        assert mat_a == mat_3


class TestGasMaterial:
    """Series of tests for the GasMaterial class"""

    def test_gas_material(self):
        from archetypal.template.materials.gas_material import GasMaterial

        air = GasMaterial(Name="Air", Conductivity=0.02, Density=1.24)

        assert air.Conductivity == 0.02
        assert air.Density == 1.24

    def test_gas_material_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""
        from archetypal.template.materials.gas_material import GasMaterial

        air = GasMaterial(Name="Air", Conductivity=0.02, Density=1.24)

        air_dict = air.to_dict()

        air_dup = GasMaterial.from_dict(air_dict)

        assert air == air_dup

    def test_hash_eq_gas_mat(self):
        """Test equality and hashing of :class:`OpaqueConstruction`."""
        import json

        from archetypal.template.materials.gas_material import GasMaterial

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)
        gasMat_json = [
            GasMaterial.from_dict(store, allow_duplicates=True)
            for store in datastore["GasMaterials"]
        ]
        gm = gasMat_json[0]
        gm_2 = gm.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert gm == gm_2
        assert hash(gm) == hash(gm_2)
        assert gm is not gm_2

        # hash is used to find object in lookup table
        gm_list = [gm]
        assert gm in gm_list
        assert gm_2 in gm_list  # This is weird but expected

        gm_list.append(gm_2)
        assert gm_2 in gm_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(gm_list)) == 1

        # dict behavior
        gm_dict = {gm: "this_idf", gm_2: "same_idf"}
        assert len(gm_dict) == 1

        gm_2.Name = "some other name"
        # even if name changes, they should be equal
        assert gm_2 == gm

        gm_dict = {gm: "this_idf", gm_2: "same_idf"}
        assert gm in gm_dict
        assert len(gm_dict) == 2

        # if an attribute changed, equality is lost
        gm_2.Cost = 69
        assert gm != gm_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(gm_list)) == 2

        # 2 GasMaterial from same json should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same layers (Material and Thickness)
        gm_3 = gm.duplicate()
        gm_3.Name = "other name"
        assert hash(gm) != hash(gm_3)
        assert id(gm) != id(gm_3)
        assert gm is not gm_3
        assert gm == gm_3


class TestOpaqueConstruction:
    """Series of tests for the :class:`OpaqueConstruction` class."""

    @pytest.fixture()
    def mat_a(self):
        """A :class:Material fixture."""
        mat_a = OpaqueMaterial(
            Conductivity=1.4, SpecificHeat=840, Density=2240, Name="Concrete"
        )
        yield mat_a

    @pytest.fixture()
    def mat_b(self):
        """A :class:Material fixture."""
        mat_b = OpaqueMaterial(
            Conductivity=0.12, SpecificHeat=1210, Density=540, Name="Plywood"
        )

        yield mat_b

    @pytest.fixture()
    def construction_a(self, mat_a, mat_b):
        """A :class:Construction fixture."""
        thickness = 0.10
        layers = [
            MaterialLayer(mat_a, thickness),
            MaterialLayer(mat_b, thickness),
        ]
        oc_a = OpaqueConstruction(Layers=layers, Name="oc_a")

        yield oc_a

    @pytest.fixture()
    def face_brick(self):
        """A :class:Material fixture."""
        face_brick = OpaqueMaterial(
            Conductivity=1.20,
            Density=1900,
            SpecificHeat=850,
            Name="Face Brick",
        )
        yield face_brick

    @pytest.fixture()
    def thermal_insulation(self):
        """A :class:Material fixture."""
        thermal_insulation = OpaqueMaterial(
            Conductivity=0.041,
            Density=40,
            SpecificHeat=850,
            Name="Thermal insulation",
        )
        yield thermal_insulation

    @pytest.fixture()
    def hollow_concrete_block(self):
        """A :class:Material fixture."""
        hollow_concrete_block = OpaqueMaterial(
            Conductivity=0.85,
            Density=2000,
            SpecificHeat=920,
            Name="Hollow concrete block",
        )
        yield hollow_concrete_block

    @pytest.fixture()
    def plaster(self):
        """A :class:Material fixture."""
        plaster = OpaqueMaterial(
            Conductivity=1.39, Density=2000, SpecificHeat=1085, Name="Plaster"
        )
        yield plaster

    @pytest.fixture()
    def concrete_layer(self):
        """A :class:Material fixture."""
        concrete = OpaqueMaterial(
            Conductivity=1.70,
            Density=2300,
            SpecificHeat=920,
            Name="Concrete layer",
        )
        yield concrete

    @pytest.fixture()
    def facebrick_and_concrete(
        self, face_brick, thermal_insulation, hollow_concrete_block, plaster
    ):
        """A :class:Construction based on the `Facebrick–concrete wall` from: On
        the thermal time constant of structural walls. Applied Thermal
        Engineering, 24(5–6), 743–757.
        https://doi.org/10.1016/j.applthermaleng.2003.10.015
        """
        layers = [
            MaterialLayer(face_brick, 0.1),
            MaterialLayer(thermal_insulation, 0.04),
            MaterialLayer(hollow_concrete_block, 0.2),
            MaterialLayer(plaster, 0.02),
        ]
        oc_a = OpaqueConstruction(Layers=layers, Name="Facebrick–concrete wall")

        yield oc_a

    @pytest.fixture()
    def insulated_concrete_wall(
        self, face_brick, thermal_insulation, concrete_layer, plaster
    ):
        """A :class:Construction based on the `Facebrick–concrete wall` from: On
        the thermal time constant of structural walls. Applied Thermal
        Engineering, 24(5–6), 743–757.
        https://doi.org/10.1016/j.applthermaleng.2003.10.015
        """
        layers = [
            MaterialLayer(plaster, 0.02),
            MaterialLayer(concrete_layer, 0.20),
            MaterialLayer(thermal_insulation, 0.04),
            MaterialLayer(plaster, 0.02),
        ]
        oc_a = OpaqueConstruction(Layers=layers, Name="Insulated Concrete Wall")

        yield oc_a

    @pytest.fixture()
    def construction_b(self, mat_a):
        """A :class:Construction fixture."""
        thickness = 0.30
        layers = [MaterialLayer(mat_a, thickness)]
        oc_b = OpaqueConstruction(Layers=layers, Name="oc_b")

        yield oc_b

    def test_change_r_value(self, facebrick_and_concrete):
        """Test setting r_value on a construction."""
        new_r_value = facebrick_and_concrete.r_value * 2  # lets double the r_value

        before_thickness = facebrick_and_concrete.total_thickness

        facebrick_and_concrete.r_value = new_r_value

        after_thickness = facebrick_and_concrete.total_thickness

        assert facebrick_and_concrete.r_value == pytest.approx(new_r_value)
        assert before_thickness < after_thickness

    def test_change_r_value_one_layer_construction(self, construction_b):
        """Test setting r_value on a construction with only one layer."""
        new_r_value = construction_b.r_value * 2

        before_thickness = construction_b.total_thickness

        construction_b.r_value = new_r_value

        after_thickness = construction_b.total_thickness

        assert construction_b.r_value == new_r_value
        assert after_thickness == 2 * before_thickness

    def test_change_r_value_not_physical(self, facebrick_and_concrete):
        """Test r_value that results in unrealistic assembly."""
        with pytest.raises(ValueError):
            facebrick_and_concrete.r_value = 0.1

    def test_thermal_properties(self, construction_a):
        """test r_value and u_value properties."""
        assert 1 / construction_a.r_value == construction_a.u_value

    def test_add_opaque_construction(self, construction_a, construction_b):
        """Test __add__() for OpaqueConstruction."""
        oc_c = OpaqueConstruction.combine(
            construction_a, construction_b, method="constant_ufactor"
        )
        assert oc_c
        desired = 3.237
        assert oc_c.u_value == pytest.approx(desired, 1e-3)

    def test_iadd_opaque_construction(self, construction_a, construction_b):
        """Test __iadd__() for OpaqueConstruction

        Args:
            construction_a:
            construction_b:
        """
        id_ = construction_a.id
        construction_a += construction_b

        assert construction_a
        assert construction_a.id == id_  # id should not change
        assert construction_a.id != construction_b.id

    def test_opaqueConstruction_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""

        mat_a = OpaqueMaterial(Conductivity=100, SpecificHeat=4180, Name="mat_a")
        mat_b = OpaqueMaterial(Conductivity=0.2, SpecificHeat=4180, Name="mat_b")
        thickness = 0.10
        layers = [MaterialLayer(mat_a, thickness), MaterialLayer(mat_b, thickness)]

        construction = OpaqueConstruction(Name="Construction", Layers=layers)
        construction_dict = construction.to_dict()

        construction_from_dict = OpaqueConstruction.from_dict(
            construction_dict,
            materials={mat_a.id: mat_a, mat_b.id: mat_b},
            allow_duplicates=True,
        )
        assert construction == construction_from_dict

    def test_hash_eq_opaq_constr(self, construction_a, construction_b):
        """Test equality and hashing of :class:`OpaqueConstruction`"""

        oc_2 = construction_a.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert construction_a == oc_2
        assert hash(construction_a) == hash(oc_2)
        assert construction_a is not oc_2

        # hash is used to find object in lookup table
        oc_list = [construction_a]
        assert construction_a in oc_list
        assert oc_2 in oc_list  # This is weird but expected

        oc_list.append(oc_2)
        assert oc_2 in oc_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(oc_list)) == 1

        # dict behavior
        oc_dict = {construction_a: "this_idf", oc_2: "same_idf"}
        assert len(oc_dict) == 1

        oc_2.Name = "some other name"
        # even if name changes, they should be equal
        assert oc_2 == construction_a

        oc_dict = {construction_a: "this_idf", oc_2: "same_idf"}
        assert construction_a in oc_dict
        assert len(oc_dict) == 2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(oc_list)) == 2

        # 2 OpaqueConstruction from different idf should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same layers (Material and Thickness)
        assert construction_a is not construction_b
        assert construction_a != construction_b
        assert hash(construction_a) != hash(construction_b)

    def test_real_word_construction(
        self, facebrick_and_concrete, insulated_concrete_wall
    ):
        """This test is based on wall constructions, materials and results from:
        Tsilingiris, P. T. (2004). On the thermal time constant of structural
        walls. Applied Thermal Engineering, 24(5–6), 743–757.
        https://doi.org/10.1016/j.applthermaleng.2003.10.015

        Args:
            facebrick_and_concrete:
            insulated_concrete_wall:
        """
        assert facebrick_and_concrete.u_factor == pytest.approx(0.6740, 0.01)
        assert (
            facebrick_and_concrete.equivalent_heat_capacity_per_unit_volume
            == pytest.approx(1595166.7, 0.01)
        )
        assert facebrick_and_concrete.heat_capacity_per_unit_wall_area == pytest.approx(
            574260.0, 0.1
        )

        assert insulated_concrete_wall.u_factor == pytest.approx(0.7710, 0.01)
        assert (
            insulated_concrete_wall.equivalent_heat_capacity_per_unit_volume
            == pytest.approx(1826285.7, 0.01)
        )

        combined_mat = facebrick_and_concrete.combine(
            insulated_concrete_wall, method="constant_ufactor"
        )
        facebrick_and_concrete.area = 2
        combined_2xmat = facebrick_and_concrete + insulated_concrete_wall
        assert combined_mat.specific_heat > combined_2xmat.specific_heat

    def test_generic(self):
        """Test generic constructors."""
        generic = OpaqueConstruction.generic()
        generic_dup = generic.duplicate()

        assert generic == generic_dup
        assert generic is not generic_dup

        generic_internalmass = OpaqueConstruction.generic_internalmass()
        generic_internalmass_dup = generic_internalmass.duplicate()

        assert generic_internalmass == generic_internalmass_dup
        assert generic_internalmass is not generic_internalmass_dup

    def test_from_epbunch(self, small_idf_obj):
        """Test OpaqueConstruction.from_epbunch()."""

        internal_mass = small_idf_obj.idfobjects["INTERNALMASS"][0]
        oc_im = OpaqueConstruction.from_epbunch(internal_mass)

        assert oc_im.Name == "PerimInternalMass"

        surface = small_idf_obj.idfobjects["CONSTRUCTION"][0]
        oc_surface = OpaqueConstruction.from_epbunch(surface)

        assert oc_surface.Name == "B_Off_Thm_0"

        # should raise error if wrong type.
        with pytest.raises(AssertionError):
            surface = small_idf_obj.idfobjects["BUILDINGSURFACE:DETAILED"][0]
            OpaqueConstruction.from_epbunch(surface)


class TestWindowConstruction:
    """Series of tests for the :class:`WindowConstruction` class"""

    @pytest.fixture()
    def air(self):
        yield GasMaterial(Name="Air")

    @pytest.fixture()
    def b_glass_clear_3(self):
        yield GlazingMaterial(
            Name="B_Glass_Clear_3",
            Density=2500,
            Conductivity=1,
            SolarTransmittance=0.770675,
            SolarReflectanceFront=0.07,
            SolarReflectanceBack=0.07,
            VisibleTransmittance=0.8836,
            VisibleReflectanceFront=0.0804,
            VisibleReflectanceBack=0.0804,
            IRTransmittance=0,
            IREmissivityFront=0.84,
            IREmissivityBack=0.84,
            DirtFactor=1,
        )

    def test_window_construction_init(self, air, b_glass_clear_3):
        """Test constructor."""
        gap = GasLayer(air, 0.0127)
        clear_glass = MaterialLayer(b_glass_clear_3, 0.005715)
        layers = [
            clear_glass,
            gap,
            clear_glass,
            gap,
            clear_glass,
        ]
        window = WindowConstruction(Layers=layers, Name="Triple Clear Window")
        window_dup = window.duplicate()

        assert window == window_dup
        assert window.u_factor == pytest.approx(1.757, rel=1e-2)

    def test_window_construction_errors(self, air, b_glass_clear_3):
        gap = GasLayer(air, 0.0127)
        clear_glass = MaterialLayer(b_glass_clear_3, 0.005715)
        layers = [
            clear_glass,
            gap,
            clear_glass,
            gap,
        ]
        with pytest.raises(AssertionError):
            WindowConstruction(Layers=layers, Name="Triple Clear Window")

        layers = [gap, clear_glass, gap, clear_glass]
        with pytest.raises(AssertionError):
            WindowConstruction(Layers=layers, Name="Triple Clear Window")

    def test_window_construction_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""

        gas_materials = [
            GasMaterial.from_dict(
                {
                    "$id": "1",
                    "Category": "Gases",
                    "Type": "AIR",
                    "Conductivity": 0.0,
                    "Cost": 0.0,
                    "Density": 0.0,
                    "EmbodiedCarbon": 0.0,
                    "EmbodiedEnergy": 0.0,
                    "SubstitutionRatePattern": [],
                    "SubstitutionTimestep": 0.0,
                    "TransportCarbon": 0.0,
                    "TransportDistance": 0.0,
                    "TransportEnergy": 0.0,
                    "Comments": None,
                    "DataSource": None,
                    "Name": "AIR",
                }
            )
        ]

        glazing_materials = [
            GlazingMaterial.from_dict(data)
            for data in [
                {
                    "$id": "6",
                    "DirtFactor": 1.0,
                    "IREmissivityBack": 0.84,
                    "IREmissivityFront": 0.84,
                    "IRTransmittance": 0.01,
                    "SolarReflectanceBack": 0.07,
                    "SolarReflectanceFront": 0.07,
                    "SolarTransmittance": 0.83,
                    "VisibleReflectanceBack": 0.08,
                    "VisibleReflectanceFront": 0.08,
                    "VisibleTransmittance": 0.89,
                    "Conductivity": 0.9,
                    "Cost": 0.0,
                    "Density": 2500.0,
                    "EmbodiedCarbon": 10.1,
                    "EmbodiedEnergy": 191.8,
                    "SubstitutionRatePattern": [0.2],
                    "SubstitutionTimestep": 50.0,
                    "TransportCarbon": 0.067,
                    "TransportDistance": 500.0,
                    "TransportEnergy": 0.94,
                    "Category": "Uncategorized",
                    "Comments": None,
                    "DataSource": "default",
                    "Name": "B_Glass_Clear_4",
                },
                {
                    "$id": "7",
                    "DirtFactor": 1.0,
                    "IREmissivityBack": 0.84,
                    "IREmissivityFront": 0.84,
                    "IRTransmittance": 0.01,
                    "SolarReflectanceBack": 0.07,
                    "SolarReflectanceFront": 0.07,
                    "SolarTransmittance": 0.83,
                    "VisibleReflectanceBack": 0.08,
                    "VisibleReflectanceFront": 0.08,
                    "VisibleTransmittance": 0.89,
                    "Conductivity": 0.9,
                    "Cost": 0.0,
                    "Density": 2500.0,
                    "EmbodiedCarbon": 5.06,
                    "EmbodiedEnergy": 96.1,
                    "SubstitutionRatePattern": [0.2],
                    "SubstitutionTimestep": 50.0,
                    "TransportCarbon": 0.067,
                    "TransportDistance": 500.0,
                    "TransportEnergy": 0.94,
                    "Category": "Uncategorized",
                    "Comments": None,
                    "DataSource": "default",
                    "Name": "B_Glass_Clear_3",
                },
                {
                    "$id": "8",
                    "DirtFactor": 1.0,
                    "IREmissivityBack": 0.84,
                    "IREmissivityFront": 0.84,
                    "IRTransmittance": 0.01,
                    "SolarReflectanceBack": 0.43,
                    "SolarReflectanceFront": 0.27,
                    "SolarTransmittance": 0.11,
                    "VisibleReflectanceBack": 0.35,
                    "VisibleReflectanceFront": 0.31,
                    "VisibleTransmittance": 0.14,
                    "Conductivity": 0.9,
                    "Cost": 0.0,
                    "Density": 2500.0,
                    "EmbodiedCarbon": 5.06,
                    "EmbodiedEnergy": 96.1,
                    "SubstitutionRatePattern": [0.2],
                    "SubstitutionTimestep": 50.0,
                    "TransportCarbon": 0.067,
                    "TransportDistance": 500.0,
                    "TransportEnergy": 0.94,
                    "Category": "Uncategorized",
                    "Comments": None,
                    "DataSource": "default",
                    "Name": "B_Glass_Clear_3_Ref_H",
                },
                {
                    "$id": "9",
                    "DirtFactor": 1.0,
                    "IREmissivityBack": 0.84,
                    "IREmissivityFront": 0.84,
                    "IRTransmittance": 0.01,
                    "SolarReflectanceBack": 0.22,
                    "SolarReflectanceFront": 0.19,
                    "SolarTransmittance": 0.63,
                    "VisibleReflectanceBack": 0.08,
                    "VisibleReflectanceFront": 0.06,
                    "VisibleTransmittance": 0.85,
                    "Conductivity": 0.9,
                    "Cost": 0.0,
                    "Density": 2500.0,
                    "EmbodiedCarbon": 5.06,
                    "EmbodiedEnergy": 96.1,
                    "SubstitutionRatePattern": [0.2],
                    "SubstitutionTimestep": 50.0,
                    "TransportCarbon": 0.067,
                    "TransportDistance": 500.0,
                    "TransportEnergy": 0.94,
                    "Category": "Uncategorized",
                    "Comments": None,
                    "DataSource": "default",
                    "Name": "B_Glass_Clear_3_LoE_1",
                },
            ]
        ]

        window = WindowConstruction.from_dict(
            {
                "$id": "57",
                "Layers": [
                    {"Material": {"$ref": "7"}, "Thickness": 0.003},
                    {"Material": {"$ref": "1"}, "Thickness": 0.006},
                    {"Material": {"$ref": "7"}, "Thickness": 0.003},
                ],
                "AssemblyCarbon": 0.0,
                "AssemblyCost": 0.0,
                "AssemblyEnergy": 0.0,
                "DisassemblyCarbon": 0.0,
                "DisassemblyEnergy": 0.0,
                "Category": "Double",
                "Comments": "default",
                "DataSource": "default",
                "Name": "B_Dbl_Air_Cl",
            },
            materials={a.id: a for a in (gas_materials + glazing_materials)},
            allow_duplicates=True,
        )
        window_dup = window.duplicate()
        assert window == window_dup
        assert window.id == "57"

    def test_add_and_iadd(self, air, b_glass_clear_3):
        gap = GasLayer(air, 0.0127)
        clear_glass = MaterialLayer(b_glass_clear_3, 0.005715)
        triple = WindowConstruction(
            Layers=[
                clear_glass,
                gap,
                clear_glass,
                gap,
                clear_glass,
            ],
            Name="Triple Clear Window",
        )
        double = WindowConstruction(
            Layers=[
                clear_glass,
                gap,
                clear_glass,
            ],
            Name="Triple Clear Window",
        )

        combined = triple + double

        assert combined

    def test_shgc(self, b_glass_clear_3):
        vision_lite = GlazingMaterial(
            Name="Vision-Lite Diamant",
            Density=2500,
            Conductivity=1,
            SolarTransmittance=0.881,
            SolarReflectanceFront=0.101,
            SolarReflectanceBack=0.101,
            VisibleTransmittance=0.973,
            VisibleReflectanceFront=0.014,
            VisibleReflectanceBack=0.014,
            IRTransmittance=0,
            IREmissivityFront=0.868,
            IREmissivityBack=0.868,
            DirtFactor=1,
        )
        planitherm = GlazingMaterial(
            Name="Planitherm One II",
            Density=2500,
            Conductivity=1,
            SolarTransmittance=0.478,
            SolarReflectanceFront=0.443,
            SolarReflectanceBack=0.382,
            VisibleTransmittance=0.783,
            VisibleReflectanceFront=0.167,
            VisibleReflectanceBack=0.175,
            IRTransmittance=0,
            IREmissivityFront=0.013,
            IREmissivityBack=0.837,
            DirtFactor=1,
        )
        argon = GasMaterial("ARGON")
        triple = WindowConstruction(
            Layers=[
                MaterialLayer(vision_lite, 0.004),
                GasLayer(argon, 0.012),
                MaterialLayer(planitherm, 0.004),
            ],
            Name="Triple Clear Window",
        )
        print("u_factor is ", triple.u_factor)

        # assert temperature profile winter conditions. Values taken from WINDOW
        # software.
        temperature, r_values = triple.temperature_profile(
            outside_temperature=-18, inside_temperature=21, wind_speed=5.5
        )
        assert [-18, -16.3, -16.1, 13.6, 13.8, 21.0] == pytest.approx(temperature, 1e-1)
        print(temperature, r_values)

        shgc = triple.shgc("summer")
        _, temperature = triple.heat_balance("summer")
        print("shgc:", shgc)
        assert [32, 32.9, 32.9, 31.9, 31.8, 24.0] == pytest.approx(temperature, 1e-1)

        print(temperature, r_values)  # m2-K/W

        print("q_no_sun", (32 - 24) / sum(r_values))
        print("q_sun", triple.solar_transmittance * 783)

    def test_from_simple_glazing(self):
        """Test from shgc and u-value."""
        window = WindowConstruction.from_shgc("Window 1", 0.763, 2.716, 0.812)

        assert window.u_factor == pytest.approx(2.716, 1e-1)
        assert window.visible_transmittance == 0.812


class TestStructureInformation:
    """Series of tests for the :class:`StructureInformation` class"""

    @pytest.fixture()
    def structure(self):
        """Test initializing StructureInformation."""

        structure_information = StructureInformation(
            MassRatios=[MassRatio(600, OpaqueMaterial.generic(), 300)], Name="structure"
        )
        yield structure_information
        assert structure_information.Name == "structure"

    def test_structure_from_to_dict(self, structure):
        """Make dict with `to_dict` and load again with `from_dict`."""

        materials = [a.Material for a in structure.MassRatios]

        structure_dict = structure.to_dict()
        structure_dub = StructureInformation.from_dict(
            structure_dict,
            materials={a.id: a for a in materials},
        )
        assert structure == structure_dub

    def test_hash_eq_struc_def(self, structure):
        """Test equality and hashing of :class:`OpaqueConstruction`."""

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        sd_2 = structure.duplicate()
        assert structure == sd_2
        assert hash(structure) == hash(sd_2)
        assert structure is not sd_2

        # hash is used to find object in lookup table
        sd_list = [structure]
        assert structure in sd_list
        assert sd_2 in sd_list  # This is weird but expected

        sd_list.append(sd_2)
        assert sd_2 in sd_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(sd_list)) == 1

        # dict behavior
        sd_dict = {structure: "this_idf", sd_2: "same_idf"}
        assert len(sd_dict) == 1

        sd_2.Name = "some other name"
        # even if name changes, they should be equal
        assert sd_2 == structure

        sd_dict = {structure: "this_idf", sd_2: "same_idf"}
        assert structure in sd_dict
        assert len(sd_dict) == 2

        # if an attribute changed, equality is lost
        sd_2.AssemblyCost = 69
        assert structure != sd_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(sd_list)) == 2

        # 2 GasMaterial from same json should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same layers (Material and Thickness)
        sd_3 = structure.duplicate()
        sd_3.Name = "other name"
        assert hash(structure) != hash(sd_3)
        assert id(structure) != id(sd_3)
        assert structure is not sd_3
        assert structure == sd_3


class TestUmiSchedule:
    """Tests for :class:`UmiSchedule` class"""

    # todo: Implement from_to_dict for UmiSchedule class

    def test_constant_umischedule(self):
        """"""

        const = UmiSchedule.constant_schedule()
        assert const.__class__.__name__ == "UmiSchedule"
        assert const.Name == "AlwaysOn"

    def test_schedule_develop(self, config, small_idf):
        """
        Args:
            config:
            small_idf:
        """

        idf = small_idf
        # clear_cache()
        sched = UmiSchedule(Name="B_Off_Y_Occ", idf=idf)
        assert sched.to_ref()

    def test_hash_eq_umi_sched(self, small_idf, other_idf):
        """Test equality and hashing of :class:`ZoneLoad`"""

        ep_bunch = small_idf.getobject("SCHEDULE:YEAR", "B_Off_Y_Occ")
        sched = UmiSchedule.from_epbunch(epbunch=ep_bunch)
        sched_2 = sched.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert sched == sched_2
        assert hash(sched) == hash(sched_2)
        assert sched is not sched_2

        # hash is used to find object in lookup table
        sched_list = [sched]
        assert sched in sched_list
        assert sched_2 in sched_list  # This is weird but expected

        sched_list.append(sched_2)
        assert sched_2 in sched_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(sched_list)) == 1

        # dict behavior
        sched_dict = {sched: "this_idf", sched_2: "same_idf"}
        assert len(sched_dict) == 1

        sched_2.Name = "some other name"
        # even if name changes, they should be equal
        assert sched_2 == sched

        sched_dict = {sched: "this_idf", sched_2: "same_idf"}
        assert sched in sched_dict
        assert len(sched_dict) == 2

        # if an attribute changed, equality is lost
        sched_2.strict = True
        assert sched != sched_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(sched_list)) == 2

        # 2 UmiSchedule from different small_idf should have the same hash,
        # not be the same object, yet be equal if they have the same values
        sched_3 = UmiSchedule.from_epbunch(
            ep_bunch, allow_duplicates=True, DataSource="Other Name"
        )
        assert sched is not sched_3
        assert sched == sched_3
        assert hash(sched) == hash(sched_3)
        assert id(sched) != id(sched_3)

    def test_combine(self):
        import numpy as np

        from archetypal.utils import reduce

        sch1 = UmiSchedule(
            Name="Equipment_10kw", Values=np.ones(24), quantity=10, Type="Fraction"
        )
        sch2 = UmiSchedule(
            Name="Equipment_20kw", Values=np.ones(24) / 2, quantity=20, Type="Fraction"
        )
        sch3 = UmiSchedule(
            Name="Equipment_30kw", Values=np.ones(24) / 3, quantity=30, Type="Fraction"
        )
        sch4 = reduce(UmiSchedule.combine, (sch1, sch2, sch3))
        assert sch4


class TestZoneConstructionSet:
    """Combines different :class:`ZoneConstructionSet` tests."""

    @pytest.fixture()
    def core_set(self):
        yield ZoneConstructionSet(
            Name="Core Construction Set", Partition=OpaqueConstruction.generic()
        )

    @pytest.fixture()
    def perim_set(self):
        yield ZoneConstructionSet(
            Name="Perimeter Construction Set", Partition=OpaqueConstruction.generic()
        )

    def test_add_zoneconstructionset(self, core_set, perim_set):
        """Test __add__() for ZoneConstructionSet."""

        z_new = core_set + perim_set
        assert z_new == core_set == perim_set

    def test_iadd_zoneconstructionset(self, core_set, perim_set):
        """Test __iadd__() for ZoneConstructionSet."""
        id_ = core_set.id
        core_set += perim_set

        assert core_set
        assert core_set.id == id_  # id should not change
        assert core_set.id != perim_set.id

    def test_zoneConstructionSet_init(self):
        """Test constructor."""
        construction_set = ZoneConstructionSet(Name="A construction set")
        construction_set_dup = construction_set.duplicate()

        assert construction_set == construction_set_dup
        assert (
            construction_set.Name == construction_set_dup.Name == "A construction set"
        )

    def test_zone_construction_set_from_zone(self, warehouse):
        """Test from zone epbunch"""
        zone = warehouse.getobject("ZONE", "Office")
        z = ZoneDefinition.from_epbunch(ep_bunch=zone)
        constrSet_ = ZoneConstructionSet.from_zone(z)

    def test_zoneConstructionSet_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""
        construction = OpaqueConstruction.generic()
        data = {
            "$id": "168",
            "Facade": construction.to_ref(),
            "Ground": construction.to_ref(),
            "Partition": construction.to_ref(),
            "Roof": construction.to_ref(),
            "Slab": construction.to_ref(),
            "IsFacadeAdiabatic": False,
            "IsGroundAdiabatic": False,
            "IsPartitionAdiabatic": False,
            "IsRoofAdiabatic": False,
            "IsSlabAdiabatic": False,
            "Category": "Office Spaces",
            "Comments": None,
            "DataSource": "MIT_SDL",
            "Name": "B_Off_0 constructions",
        }

        construction_set = ZoneConstructionSet.from_dict(
            data, opaque_constructions={a.id: a for a in [construction]}
        )
        construction_set_data = construction_set.to_dict()

        construction_set_dup = ZoneConstructionSet.from_dict(
            construction_set_data,
            opaque_constructions={a.id: a for a in [construction]},
        )
        assert construction_set == construction_set_dup


class TestZoneLoad:
    """Combines different :class:`ZoneLoad` tests"""

    @pytest.fixture(scope="class")
    def fiveZoneEndUses(self, config):
        """"""
        epw = (
            get_eplus_dirs(settings.ep_version)
            / "WeatherData"
            / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
        )
        idf = IDF.from_example_files(
            "5ZoneAirCooled_AirBoundaries_Daylighting.idf", epw=epw
        )
        if idf.sim_info is None:
            idf.simulate()
        yield idf

    def test_zoneLoad_init(self):
        """Test constructor."""
        zone_load = ZoneLoad(
            LightsAvailabilitySchedule=UmiSchedule.constant_schedule(Name="AlwaysOn"),
            OccupancySchedule=UmiSchedule.constant_schedule(Name="AlwaysOn"),
            Name="Zone 1 Loads",
        )
        zone_load_dup = zone_load.duplicate()
        assert zone_load == zone_load_dup
        assert zone_load.Name == zone_load_dup.Name

    def test_zoneLoad_from_zone(self, warehouse):
        """"""
        idf = warehouse
        zone = idf.getobject("ZONE", "Office")
        z = ZoneDefinition.from_epbunch(ep_bunch=zone)
        zone_loads = ZoneLoad.from_zone(z, zone)

        assert zone_loads.DimmingType == DimmingTypes.Off
        assert zone_loads.EquipmentPowerDensity == pytest.approx(8.07, 1e-2)
        assert zone_loads.IlluminanceTarget == pytest.approx(500, 1e-2)
        assert zone_loads.IsEquipmentOn
        assert zone_loads.IsPeopleOn
        assert zone_loads.LightingPowerDensity == pytest.approx(11.84, 1e-2)
        assert zone_loads.PeopleDensity == pytest.approx(0.021, 1e-2)

    def test_zoneLoad_from_zone_mixedparams(self, fiveZoneEndUses):
        """"""
        idf = fiveZoneEndUses
        zone_ep = idf.getobject("ZONE", "SPACE1-1")
        z = ZoneDefinition.from_epbunch(ep_bunch=zone_ep)
        zone_loads = ZoneLoad.from_zone(z, zone_ep)

        assert zone_loads.DimmingType == DimmingTypes.Stepped
        assert zone_loads.EquipmentPowerDensity == pytest.approx(10.649, 1e-2)
        assert zone_loads.IlluminanceTarget == 400
        assert zone_loads.IsEquipmentOn
        assert zone_loads.IsPeopleOn
        assert zone_loads.LightingPowerDensity == pytest.approx(15.974, 1e-2)
        assert zone_loads.PeopleDensity == pytest.approx(0.111, 1e-2)

    def test_zoneLoad_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""
        schedules = [
            UmiSchedule.constant_schedule(id="147"),
            UmiSchedule.constant_schedule(id="146"),
            UmiSchedule.constant_schedule(id="145"),
        ]
        data = {
            "$id": "172",
            "DimmingType": 1,
            "EquipmentAvailabilitySchedule": {"$ref": "147"},
            "EquipmentPowerDensity": 8.0,
            "IlluminanceTarget": 500.0,
            "LightingPowerDensity": 12.0,
            "LightsAvailabilitySchedule": {"$ref": "146"},
            "OccupancySchedule": {"$ref": "145"},
            "IsEquipmentOn": True,
            "IsLightingOn": True,
            "IsPeopleOn": True,
            "PeopleDensity": 0.055,
            "Category": "Office Spaces",
            "Comments": None,
            "DataSource": "MIT_SDL",
            "Name": "B_Off_0 loads",
        }
        zone_load = ZoneLoad.from_dict(copy(data), {a.id: a for a in schedules})
        data_dup = dict(zone_load.to_dict())
        assert zone_load.id == "172"
        assert data == data_dup

    @pytest.fixture()
    def zl(self):
        yield ZoneLoad(
            EquipmentPowerDensity=10,
            EquipmentAvailabilitySchedule=UmiSchedule.random(
                Name="Random Equipment " "Schedule"
            ),
            LightsAvailabilitySchedule=UmiSchedule.constant_schedule(Name="AlwaysOn"),
            OccupancySchedule=UmiSchedule.constant_schedule(Name="AlwaysOn"),
            area=50,
            Name="Zone 1 Loads",
        )

    def test_hash_eq_zone_load(self, zl):
        """Test equality and hashing of :class:`ZoneLoad`."""
        zl_2 = zl.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert zl == zl_2
        assert hash(zl) == hash(zl_2)
        assert zl is not zl_2

        # hash is used to find object in lookup table
        zl_list = [zl]
        assert zl in zl_list
        assert zl_2 in zl_list  # This is weird but expected

        zl_list.append(zl_2)
        assert zl_2 in zl_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(zl_list)) == 1

        # dict behavior
        zl_dict = {zl: "this_idf", zl_2: "same_idf"}
        assert len(zl_dict) == 1

        zl_2.Name = "some other name"
        # even if name changes, they should be equal
        assert zl_2 == zl

        zl_dict = {zl: "this_idf", zl_2: "same_idf"}
        assert zl in zl_dict
        assert len(zl_dict) == 2

        # if an attribute changed, equality is lost
        zl_2.IsEquipmentOn = False
        assert zl != zl_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(zl_list)) == 2

        # 2 ZoneLoad from different idf should not have the same hash even if they
        # have the same name, not be the same object, yet be equal if they have the
        # same values (EquipmentPowerDensity, LightingPowerDensity, etc.)
        zl_3 = zl.duplicate()
        zl_3.DataSource = "Other"
        assert hash(zl) != hash(zl_3)
        assert id(zl) != id(zl_3)
        assert zl is not zl_3
        assert zl == zl_3

    def test_zone_add(self, zl):
        zl_2: ZoneLoad = zl.duplicate()
        zl_2.EquipmentPowerDensity = None
        zl_2.EquipmentAvailabilitySchedule = None

        zl_combined = ZoneLoad.combine(zl, zl_2, weights=[zl.area, zl_2.area])

        # zl_combined = zl + zl_2
        assert zl_combined.EquipmentPowerDensity == 10
        assert zl_combined.area == 100


class TestZoneConditioning:
    """Combines different :class:`ZoneConditioning` tests"""

    @pytest.fixture(
        scope="class",
        params=[
            "RefMedOffVAVAllDefVRP.idf",
            "AirflowNetwork_MultiZone_SmallOffice_HeatRecoveryHXSL.idf",
            "AirflowNetwork_MultiZone_SmallOffice_CoilHXAssistedDX.idf",
        ],
    )
    def zoneConditioningtests(self, config, request):
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = IDF.from_example_files(
            request.param, epw=w, annual=False, design_day=True
        )
        copy = IDF.from_example_files(
            request.param, epw=w, annual=False, design_day=True
        )
        if idf.sim_info is None:
            idf.simulate()
        if copy.sim_info is None:
            copy.simulate()
        yield (
            idf,
            request.param,
            copy,  # yield a copy
        )

    def test_zone_conditioning_init(self):
        """Test constructor."""
        cond = ZoneConditioning(Name="A Name")
        cond_dup = cond.duplicate()

        assert (
            cond.EconomizerType
            == cond_dup.EconomizerType
            == EconomizerTypes.NoEconomizer
        )

    def test_from_zone(self, config, zoneConditioningtests):
        """"""

        idf, idf_name, _ = zoneConditioningtests
        if idf_name == "RefMedOffVAVAllDefVRP.idf":
            zone_ep = idf.getobject("ZONE", "Core_mid")
            z = ZoneDefinition.from_epbunch(ep_bunch=zone_ep)
            cond_ = ZoneConditioning.from_zone(z, zone_ep)
        if idf_name == "AirflowNetwork_MultiZone_SmallOffice_HeatRecoveryHXSL.idf":
            zone_ep = idf.getobject("ZONE", "West Zone")
            z = ZoneDefinition.from_epbunch(ep_bunch=zone_ep)
            cond_HX = ZoneConditioning.from_zone(z, zone_ep)
        if idf_name == "AirflowNetwork_MultiZone_SmallOffice_CoilHXAssistedDX.idf":
            zone_ep = idf.getobject("ZONE", "East Zone")
            z = ZoneDefinition.from_epbunch(ep_bunch=zone_ep)
            cond_HX_eco = ZoneConditioning.from_zone(z, zone_ep)

    def test_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""
        schedule = UmiSchedule.constant_schedule(id="150")
        data = {
            "$id": "165",
            "CoolingSchedule": schedule.to_ref(),
            "CoolingCoeffOfPerf": 3.0,
            "CoolingSetpoint": 24.0,
            "CoolingLimitType": 0,
            "CoolingFuelType": 1,
            "EconomizerType": 0,
            "HeatingCoeffOfPerf": 0.9,
            "HeatingLimitType": 0,
            "HeatingFuelType": 2,
            "HeatingSchedule": schedule.to_ref(),
            "HeatingSetpoint": 20.0,
            "HeatRecoveryEfficiencyLatent": 0.65,
            "HeatRecoveryEfficiencySensible": 0.7,
            "HeatRecoveryType": 0,
            "IsCoolingOn": True,
            "IsHeatingOn": True,
            "IsMechVentOn": True,
            "MaxCoolFlow": 100.0,
            "MaxCoolingCapacity": 100.0,
            "MaxHeatFlow": 100.0,
            "MaxHeatingCapacity": 100.0,
            "MechVentSchedule": schedule.to_ref(),
            "MinFreshAirPerArea": 0.0003,
            "MinFreshAirPerPerson": 0.0025,
            "Category": "Office Spaces",
            "Comments": None,
            "DataSource": "MIT_SDL",
            "Name": "B_Off_0 Conditioning",
        }

        cond = ZoneConditioning.from_dict(
            copy(data), schedules={a.id: a for a in [schedule]}
        )

        cond_dict = cond.to_dict()

        cond_dup = ZoneConditioning.from_dict(
            cond_dict, schedules={a.id: a for a in [schedule]}
        )

        assert cond == cond_dup
        assert cond is not cond_dup
        assert cond.Name == cond_dup.Name == "B_Off_0 Conditioning"

    def test_hash_eq_zone_cond(self):
        """Test equality and hashing of :class:`ZoneConditioning`."""

        zc = ZoneConditioning(Name="Conditioning 1")
        zc_2 = zc.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert zc == zc_2
        assert hash(zc) == hash(zc_2)
        assert zc is not zc_2

        # hash is used to find object in lookup table
        zc_list = [zc]
        assert zc in zc_list
        assert zc_2 in zc_list  # This is weird but expected

        zc_list.append(zc_2)
        assert zc_2 in zc_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(zc_list)) == 1

        # dict behavior
        zc_dict = {zc: "this_idf", zc_2: "same_idf"}
        assert len(zc_dict) == 1

        zc_2.Name = "some other name"
        # even if name changes, they should be equal
        assert zc_2 == zc

        zc_dict = {zc: "this_idf", zc_2: "same_idf"}
        assert zc in zc_dict
        assert len(zc_dict) == 2

        # if an attribute changed, equality is lost
        zc_2.IsCoolingOn = True
        assert zc != zc_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(zc_list)) == 2

        # 2 ZoneConditioning from different idf should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same values (CoolingSetpoint, HeatingSetpoint, etc.)
        zc_3 = zc.duplicate()
        zc_3.DataSource = "Other IDF"
        assert hash(zc) != hash(zc_3)
        assert id(zc) != id(zc_3)
        assert zc is not zc_3
        assert zc == zc_3


class TestVentilationSetting:
    """Combines different :class:`VentilationSetting` tests"""

    @pytest.fixture(
        scope="class",
        params=["VentilationSimpleTest.idf", "RefBldgWarehouseNew2004_Chicago.idf"],
    )
    def ventilatontests(self, config, request):
        """Create test cases with different ventilation definitions."""

        eplusdir = get_eplus_dirs(settings.ep_version)
        w = eplusdir / "WeatherData" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
        idf = IDF.from_example_files(request.param, epw=w, annual=True)
        if idf.sim_info is None:
            idf.simulate()
        copy = IDF.from_example_files(request.param, epw=w, annual=True)
        if copy.sim_info is None:
            copy.simulate()
        yield idf, request.param, copy  # passes a copy as well

    def test_ventilation_init(self):
        """Test __init__ constructor."""
        schedule = UmiSchedule.constant_schedule()

        vent = VentilationSetting(
            NatVentSchedule=schedule,
            ScheduledVentilationSchedule=schedule,
            Name="Ventilation 1",
        )
        vent_dup = vent.duplicate()

        assert vent == vent_dup
        assert vent is not vent_dup
        assert vent.Name == vent_dup.Name == "Ventilation 1"

    def test_naturalVentilation_from_zone(self, ventilatontests):
        """Test from_zone constructor."""
        idf, idf_name, _ = ventilatontests
        if idf_name == "VentilationSimpleTest.idf":
            zone_ep = idf.getobject("ZONE", "ZONE 1")
            z = ZoneDefinition.from_epbunch(ep_bunch=zone_ep, construct_parents=False)
            natVent = VentilationSetting.from_zone(z, zone_ep)
        if idf_name == "VentilationSimpleTest.idf":
            zone_ep = idf.getobject("ZONE", "ZONE 2")
            z = ZoneDefinition.from_epbunch(ep_bunch=zone_ep, construct_parents=False)
            schedVent = VentilationSetting.from_zone(z, zone_ep)
        if idf_name == "RefBldgWarehouseNew2004_Chicago.idf":
            zone_ep = idf.getobject("ZONE", "Office")
            z = ZoneDefinition.from_epbunch(ep_bunch=zone_ep, construct_parents=False)
            infiltVent = VentilationSetting.from_zone(z, zone_ep)

    def test_ventilationSetting_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""
        schedule = UmiSchedule.constant_schedule(id="151")
        data = {
            "$id": "162",
            "Afn": False,
            "IsBuoyancyOn": True,
            "Infiltration": 0.35,
            "IsInfiltrationOn": True,
            "IsNatVentOn": False,
            "IsScheduledVentilationOn": False,
            "NatVentMaxRelHumidity": 80.0,
            "NatVentMaxOutdoorAirTemp": 26.0,
            "NatVentMinOutdoorAirTemp": 20.0,
            "NatVentSchedule": {"$ref": schedule.id},
            "NatVentZoneTempSetpoint": 22.0,
            "ScheduledVentilationAch": 0.6,
            "ScheduledVentilationSchedule": {"$ref": schedule.id},
            "ScheduledVentilationSetpoint": 22.0,
            "IsWindOn": False,
            "Category": "Office Spaces",
            "Comments": None,
            "DataSource": "MIT_SDL",
            "Name": "Ventilation 1",
        }
        vent = VentilationSetting.from_dict(
            data, schedules={a.id: a for a in [schedule]}
        )
        vent_dict = vent.to_dict()

        vent_dup = VentilationSetting.from_dict(
            vent_dict, schedules={a.id: a for a in [schedule]}
        )

        assert vent == vent_dup
        assert vent is not vent_dup
        assert vent.Name == vent_dup.Name == "Ventilation 1"

    def test_hash_eq_vent_settings(self):
        """Test equality and hashing of :class:`DomesticHotWaterSetting`."""

        schedule = UmiSchedule.constant_schedule()
        vent = VentilationSetting(
            NatVentSchedule=schedule,
            ScheduledVentilationSchedule=schedule,
            Name="Ventilation 1",
        )
        vent_2 = vent.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert vent == vent_2
        assert hash(vent) == hash(vent_2)
        assert vent is not vent_2

        # hash is used to find object in lookup table
        vent_list = [vent]
        assert vent in vent_list
        assert vent_2 in vent_list  # This is weird but expected

        vent_list.append(vent_2)
        assert vent_2 in vent_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(vent_list)) == 1

        # dict behavior
        vent_dict = {vent: "this_idf", vent_2: "same_idf"}
        assert len(vent_dict) == 1

        vent_2.Name = "some other name"
        # even if name changes, they should be equal
        assert vent_2 == vent

        vent_dict = {vent: "this_idf", vent_2: "same_idf"}
        assert vent in vent_dict
        assert len(vent_dict) == 2

        # if an attribute changed, equality is lost
        vent_2.Afn = True
        assert vent != vent_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(vent_list)) == 2

        # 2 VentilationSettings from different idf should not have the same hash if they
        # have same names, not be the same object, yet be equal if they have the
        # same values (Infiltration, IsWindOn, etc.)
        vent_3 = vent.duplicate()
        vent_3.DataSource = "Other IDF"
        assert hash(vent) != hash(vent_3)
        assert id(vent) != id(vent_3)
        assert vent is not vent_3
        assert vent == vent_3

    def test_combine(self):
        """Test combining two objects."""
        always_on = UmiSchedule.constant_schedule()
        always_half = UmiSchedule.constant_schedule(0.5, Name="AlwaysHalf")
        random = UmiSchedule.random()
        vent_1 = VentilationSetting(
            Infiltration=0.1,
            NatVentSchedule=always_on,
            ScheduledVentilationAch=1,
            ScheduledVentilationSchedule=random,
            IsScheduledVentilationOn=True,
            area=50,
            volume=150,
            Name="Ventilation 1",
        )
        vent_2 = VentilationSetting(
            Infiltration=0.2,
            NatVentSchedule=always_on,
            ScheduledVentilationAch=2,
            ScheduledVentilationSchedule=always_half,
            IsScheduledVentilationOn=True,
            area=50,
            volume=150,
            Name="Ventilation 2",
        )

        vent_3 = vent_1 + vent_2

        assert vent_3.area == vent_1.area + vent_2.area
        assert vent_3.volume == vent_1.volume + vent_2.volume
        assert vent_3.Infiltration == pytest.approx((0.1 + 0.2) / 2)
        annual_air_volume = (
            vent_1.ScheduledVentilationSchedule.all_values
            * vent_1.ScheduledVentilationAch
            * vent_1.volume
        ).sum() + (
            vent_2.ScheduledVentilationSchedule.all_values
            * vent_2.ScheduledVentilationAch
            * vent_2.volume
        ).sum()
        combined_annual_air_volume = (
            vent_3.ScheduledVentilationSchedule.all_values
            * vent_3.ScheduledVentilationAch
            * vent_3.volume
        ).sum()
        assert combined_annual_air_volume == pytest.approx(annual_air_volume)

    def test_combine_with_none(self):
        """Test combining two objects."""
        always_on = UmiSchedule.constant_schedule()
        always_half = UmiSchedule.constant_schedule(0.5, Name="AlwaysHalf")
        vent_1 = VentilationSetting(
            Infiltration=0,
            NatVentSchedule=always_on,
            ScheduledVentilationAch=0,
            ScheduledVentilationSchedule=None,
            IsScheduledVentilationOn=False,
            area=50,
            volume=150,
            Name="Ventilation 1",
        )
        vent_2 = VentilationSetting(
            Infiltration=0.2,
            NatVentSchedule=always_on,
            ScheduledVentilationAch=2,
            ScheduledVentilationSchedule=always_half,
            IsScheduledVentilationOn=True,
            area=50,
            volume=150,
            Name="Ventilation 2",
        )

        vent_3 = vent_1 + vent_2

        assert vent_3.area == vent_1.area + vent_2.area
        assert vent_3.volume == vent_1.volume + vent_2.volume
        assert vent_3.ScheduledVentilationAch == pytest.approx(
            (vent_1.ScheduledVentilationAch + vent_2.ScheduledVentilationAch) / 2
        )
        annual_air_volume = (
            0
            + (
                vent_2.ScheduledVentilationSchedule.all_values
                * vent_2.ScheduledVentilationAch
                * vent_2.volume
            ).sum()
        )
        combined_annual_air_volume = (
            vent_3.ScheduledVentilationSchedule.all_values
            * vent_3.ScheduledVentilationAch
            * vent_3.volume
        ).sum()
        assert combined_annual_air_volume == annual_air_volume


class TestDomesticHotWaterSetting:
    """Series of tests for the :class:`DomesticHotWaterSetting` class."""

    def test_init_dhw(self):
        dhw = DomesticHotWaterSetting(area=1, Name="DHW 1")
        dhw_dup = dhw.duplicate()
        assert dhw == dhw_dup
        assert dhw.Name == dhw_dup.Name == "DHW 1"

    def test_to_from_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""
        schedules = [UmiSchedule.constant_schedule(id="1")]
        dhw_dict = {
            "$id": "2",
            "FlowRatePerFloorArea": 0.00021,
            "IsOn": True,
            "WaterSchedule": {"$ref": "1"},
            "WaterSupplyTemperature": 55.0,
            "WaterTemperatureInlet": 16.0,
            "Category": "Office Spaces",
            "Comments": None,
            "DataSource": "MIT_SDL",
            "Name": "B_Off_0 hot water",
        }
        dhw = DomesticHotWaterSetting.from_dict(
            dhw_dict, schedules={a.id: a for a in schedules}
        )
        dhw_dup = dhw.duplicate()

        assert dhw == dhw_dup
        assert dhw is not dhw_dup
        assert dhw.FlowRatePerFloorArea == dhw_dup.FlowRatePerFloorArea == 0.00021

    @pytest.fixture(scope="class")
    def five_zone_water_systems(self, config):
        """Parse 5ZoneWaterSystems. Add RunPeriod because not included in file."""
        idf = IDF.from_example_files("5ZoneWaterSystems.idf")
        idf.newidfobject(
            "RUNPERIOD",
            Name="Run period",
            Begin_Month=1,
            Begin_Day_of_Month=1,
            Begin_Year="",
            End_Month=12,
            End_Day_of_Month=31,
            End_Year="",
            Day_of_Week_for_Start_Day="",
            Use_Weather_File_Holidays_and_Special_Days="No",
            Use_Weather_File_Daylight_Saving_Period="No",
            Apply_Weekend_Holiday_Rule="No",
            Use_Weather_File_Rain_Indicators="Yes",
            Use_Weather_File_Snow_Indicators="Yes",
        )
        yield idf

    def test_from_zone(self, five_zone_water_systems):
        zone = five_zone_water_systems.getobject("ZONE", "SPACE5-1")
        dhw = DomesticHotWaterSetting.from_zone(zone)
        assert dhw

    @pytest.mark.skip()
    def test_whole_building(self, five_zone_water_systems):
        dhws = {}
        for zone in five_zone_water_systems.idfobjects["ZONE"]:
            dhws[zone.Name] = DomesticHotWaterSetting.from_zone(zone)
        dhw_per_zone = reduce(DomesticHotWaterSetting.combine, dhws.values())
        # dhw_per_zone = list(dhws.values())
        dhw_whole_bldg = DomesticHotWaterSetting.whole_building(five_zone_water_systems)
        assert dhw_per_zone.__key__() == dhw_whole_bldg.__key__()

    def test_combine(self):
        """"""
        zone_1 = DomesticHotWaterSetting(
            Name="zone_1",
            FlowRatePerFloorArea=0.001,
            area=25,
            WaterSchedule=UmiSchedule.constant_schedule(1, Name="AlwaysOn"),
        )
        zone_2 = DomesticHotWaterSetting(
            Name="zone_2",
            FlowRatePerFloorArea=0.002,
            area=75,
            WaterSchedule=UmiSchedule.constant_schedule(0.5, Name="AlwaysHalf"),
        )
        combined = zone_1 + zone_2
        assert combined.FlowRatePerFloorArea == pytest.approx(0.00175)
        assert combined.area == zone_1.area + zone_2.area

        # assert final annual quantity is kept. multiply schedule by flowrate per
        # area and area.
        total_water_zone_1 = sum(
            zone_1.WaterSchedule.all_values * zone_1.FlowRatePerFloorArea * zone_1.area
        )
        total_water_zone_2 = sum(
            zone_2.WaterSchedule.all_values * zone_2.FlowRatePerFloorArea * zone_2.area
        )
        total_water = total_water_zone_1 + total_water_zone_2
        assert sum(
            combined.WaterSchedule.all_values * combined.FlowRatePerFloorArea * 100
        ) == pytest.approx(total_water)

    def test_hash_eq_dhw(self):
        """Test equality and hashing of :class:`DomesticHotWaterSetting`."""

        dhw = DomesticHotWaterSetting(
            "Domestic",
            WaterSchedule=UmiSchedule.constant_schedule(),
            IsOn=True,
            FlowRatePerFloorArea=0.03,
            WaterSupplyTemperature=65,
            WaterTemperatureInlet=10,
            area=1,
        )
        dhw_2 = dhw.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert dhw == dhw_2
        assert hash(dhw) == hash(dhw_2)
        assert dhw is not dhw_2

        # hash is used to find object in lookup table
        dhw_list = [dhw]
        assert dhw in dhw_list
        assert dhw_2 in dhw_list  # This is weird but expected

        dhw_list.append(dhw_2)
        assert dhw_2 in dhw_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(dhw_list)) == 1

        # dict behavior
        dhw_dict = {dhw: "this_idf", dhw_2: "same_idf"}
        assert len(dhw_dict) == 1

        dhw_2.Name = "some other name"
        # even if name changes, they should be equal
        assert dhw_2 == dhw

        dhw_dict = {dhw: "this_idf", dhw_2: "same_idf"}
        assert dhw in dhw_dict
        assert len(dhw_dict) == 2

        # if an attribute changed, equality is lost
        dhw_2.IsOn = False
        assert dhw != dhw_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(dhw_list)) == 2


class TestWindowSetting:
    """Combines different :class:`WindowSetting` tests."""

    @pytest.fixture(
        scope="class", params=["WindowTests.idf", "AirflowNetwork3zVent.idf"]
    )
    def windowtests(self, config, request):
        """
        Args:
            config:
            request:
        """
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = IDF.from_example_files(request.param, epw=w, design_day=True)
        if idf.sim_info is None:
            idf.simulate()
        yield idf

    def test_window_from_construction_name(self, small_idf):
        """
        Args:
            small_idf:
        """
        idf = small_idf
        construction = idf.getobject("CONSTRUCTION", "B_Dbl_Air_Cl")
        w = WindowSetting.from_construction(construction)

        assert w.to_dict()

    @pytest.fixture(scope="class")
    def allwindowtypes(self, config, windowtests):
        idf = windowtests
        f_surfs = idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]
        windows = []
        for f in f_surfs:
            windows.append(WindowSetting.from_surface(f))
        yield windows

    def test_init(self):
        """Test class init."""
        w = WindowSetting("Window 1")
        w_dup = w.duplicate()

        assert w == w_dup
        assert w.Name == w_dup.Name

    def test_windowsettings_from_to_dict(self):
        """Make dict with `to_dict` and load again with `from_dict`."""

        window_cstrc = WindowConstruction.from_shgc(
            "Window Construction", 0.5, 2.2, 0.21, id="57"
        )
        constructions = [window_cstrc]
        schedules = [UmiSchedule.constant_schedule(id="1")]
        data = {
            "$id": "179",
            "AfnDischargeC": 0.65,
            "AfnTempSetpoint": 20.0,
            "AfnWindowAvailability": {"$ref": "1"},
            "Construction": {"$ref": "57"},
            "IsShadingSystemOn": False,
            "IsVirtualPartition": False,
            "IsZoneMixingOn": False,
            "OperableArea": 0.8,
            "ShadingSystemAvailabilitySchedule": {"$ref": "1"},
            "ShadingSystemSetpoint": 350.0,
            "ShadingSystemTransmittance": 0.5,
            "ShadingSystemType": 0,
            "Type": 0,
            "ZoneMixingAvailabilitySchedule": {"$ref": "1"},
            "ZoneMixingDeltaTemperature": 2.0,
            "ZoneMixingFlowRate": 0.001,
            "Category": "Office Spaces",
            "Comments": "Base building definition for MIT 4433",
            "DataSource": "MIT_SDL",
            "Name": "B_Off_0 windows",
        }

        w = WindowSetting.from_dict(
            data,
            schedules={a.id: a for a in schedules},
            window_constructions={a.id: a for a in constructions},
        )

        w_dict = w.to_dict()

        w_dup = WindowSetting.from_dict(
            w_dict,
            schedules={a.id: a for a in schedules},
            window_constructions={a.id: a for a in constructions},
        )

        assert w == w_dup
        assert w is not w_dup
        assert w.Name == w_dup.Name == "B_Off_0 windows"
        assert w.id == w_dup.id == "179"
        assert isinstance(w.Construction, WindowConstruction)

    def test_winow_add2(self, allwindowtypes):
        from archetypal.utils import reduce

        window = reduce(WindowSetting.combine, allwindowtypes)
        print(window)

    def test_window_add(self, allwindowtypes):
        window_1, window_2, *_ = allwindowtypes  # take 2

        new_w = window_1 + window_2
        assert window_1 == window_2
        assert new_w.id == window_1.id
        assert window_1.id != window_2.id != new_w.id

    def test_window_iadd(self, allwindowtypes):
        window_1, window_2, *_ = allwindowtypes

        previous_id = window_1.id

        window_1 += window_2
        assert window_1
        assert window_1.id == previous_id  # id should not change
        assert window_1.id != window_2.id

    def test_window_generic(self):
        w = WindowSetting.generic("Generic Window")

        assert w.to_dict()

    def test_hash_eq_window_settings(self, small_idf, small_idf_copy):
        """Test equality and hashing of :class:`DomesticHotWaterSetting`"""

        idf = small_idf
        f_surf = idf.idfobjects["FENESTRATIONSURFACE:DETAILED"][0]
        wind = WindowSetting.from_surface(f_surf)
        wind_2 = wind.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert wind == wind_2
        assert hash(wind) == hash(wind_2)
        assert wind is not wind_2

        # hash is used to find object in lookup table
        wind_list = [wind]
        assert wind in wind_list
        assert wind_2 in wind_list  # This is weird but expected

        wind_list.append(wind_2)
        assert wind_2 in wind_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(wind_list)) == 1

        # dict behavior
        wind_dict = {wind: "this_idf", wind_2: "same_idf"}
        assert len(wind_dict) == 1

        wind_2.Name = "some other name"
        # even if name changes, they should be equal
        assert wind_2 == wind

        wind_dict = {wind: "this_idf", wind_2: "same_idf"}
        assert wind in wind_dict
        assert len(wind_dict) == 2

        # if an attribute changed, equality is lost
        wind_2.IsVirtualPartition = True
        assert wind != wind_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(wind_list)) == 2

        # 2 WindowSettings from different idf should not have the same hash
        # if they have different names, not be the same object, yet be equal if they
        # have the same values (Construction, Type, etc.)
        idf_2 = small_idf_copy
        f_surf_3 = idf_2.idfobjects["FENESTRATIONSURFACE:DETAILED"][0]
        wind_3 = WindowSetting.from_surface(f_surf_3, allow_duplicates=True)
        assert idf is not idf_2
        assert f_surf is not f_surf_3
        assert f_surf != f_surf_3
        assert hash(wind) == hash(wind_3)
        assert wind is not wind_3
        assert wind == wind_3

    def test_window_fromsurface(self, config, small_idf):
        """
        Args:
            config:
            small_idf:
        """
        idf = small_idf
        f_surfs = idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]
        for f in f_surfs:
            constr = f.Construction_Name
            idf.newidfobject(
                "WindowMaterial:Shade".upper(),
                Visible_Transmittance=0.5,
                Name="Roll Shade",
            )
            idf.newidfobject(
                "WindowShadingControl".upper(),
                Construction_with_Shading_Name=constr,
                Setpoint=14,
                Shading_Device_Material_Name="Roll Shade",
                Fenestration_Surface_1_Name="test_control",
            )
            f.Name = "test_control"
            w = WindowSetting.from_surface(f)
            assert w


class TestInternalMass:
    """Tests for class InternalMass."""

    def test_init_class(self):
        internal_mass = InternalMass(
            surface_name="InternalMass for zone 1",
            construction=OpaqueConstruction.generic(),
            total_area_exposed_to_zone=10,
        )
        internal_mass_dup = internal_mass.duplicate()
        assert internal_mass == internal_mass_dup
        assert (
            internal_mass.total_area_exposed_to_zone
            == internal_mass_dup.total_area_exposed_to_zone
        )

    def test_from_zone(self, small_idf_obj):
        """Test constructor from Zone EpBunch object."""
        zone_epbunch = small_idf_obj.idfobjects["ZONE"][0]
        internal_mass = InternalMass.from_zone(zone_epbunch=zone_epbunch)
        assert internal_mass.total_area_exposed_to_zone == pytest.approx(5.03, 1e-2)

    def test_to_ep_bunch(self, idf):
        internal_mass = InternalMass(
            construction=OpaqueConstruction.generic(),
            total_area_exposed_to_zone=10,
            surface_name="InternalMass",
        )
        ep_bunch = internal_mass.to_epbunch(idf, "Zone 1")
        assert isinstance(ep_bunch, EpBunch)
        assert ep_bunch.Name == "InternalMass"
        assert idf.getobject("INTERNALMASS", "InternalMass") == ep_bunch


class TestZoneDefinition:
    """Tests for :class:`ZoneDefinition` class"""

    def test_zone_init(self):
        zone = ZoneDefinition(
            Name="Zone 1",
            Constructions=ZoneConstructionSet("Zone 1 Constructions"),
            Loads=ZoneLoad("Zone 1 Load"),
            Conditioning=ZoneConditioning("Zone 1 Conditioning"),
            Ventilation=VentilationSetting("Zone 1 Ventilation"),
            DomesticHotWater=DomesticHotWaterSetting("Zone 1 DHW"),
            InternalMassConstruction=OpaqueConstruction.generic(),
            Windows=WindowSetting("Zone 1 Windows"),
        )
        zone_dup = zone.duplicate()

        assert zone == zone_dup
        assert zone.Name == zone_dup.Name

    def test_from_to_dict(self):
        """"""
        conditionings = [ZoneConditioning("Zone 1 Conditioning", id="165")]
        construction_sets = [ZoneConstructionSet("Zone 1 Constructions", id="168")]
        dhws = [DomesticHotWaterSetting("Zone 1 DHW", id="159")]
        constructions = [OpaqueConstruction.generic(id="54")]
        loads = [ZoneLoad("Zone 1 Load", id="172")]
        ventilations = [VentilationSetting("Zone 1 Ventilation", id="162")]
        data = {
            "$id": "175",
            "Conditioning": {"$ref": "165"},
            "Constructions": {"$ref": "168"},
            "DaylightMeshResolution": 1.0,
            "DaylightWorkplaneHeight": 0.8,
            "DomesticHotWater": {"$ref": "159"},
            "InternalMassConstruction": {"$ref": "54"},
            "InternalMassExposedPerFloorArea": 1.05,
            "Loads": {"$ref": "172"},
            "Ventilation": {"$ref": "162"},
            "Category": "Office Spaces",
            "Comments": None,
            "DataSource": "MIT_SDL",
            "Name": "B_Off_0",
        }
        zone = ZoneDefinition.from_dict(
            data,
            zone_conditionings={a.id: a for a in conditionings},
            zone_construction_sets={a.id: a for a in construction_sets},
            domestic_hot_water_settings={a.id: a for a in dhws},
            opaque_constructions={a.id: a for a in constructions},
            zone_loads={a.id: a for a in loads},
            ventilation_settings={a.id: a for a in ventilations},
        )

        zone_dict = zone.to_dict()

        zone_dup = ZoneDefinition.from_dict(
            zone_dict,
            zone_conditionings={a.id: a for a in conditionings},
            zone_construction_sets={a.id: a for a in construction_sets},
            domestic_hot_water_settings={a.id: a for a in dhws},
            opaque_constructions={a.id: a for a in constructions},
            zone_loads={a.id: a for a in loads},
            ventilation_settings={a.id: a for a in ventilations},
        )

        assert zone == zone_dup

    def test_zone_volume(self, small_idf_copy):
        """Test the zone volume for a sloped roof

        Args:
            small_idf_copy:
        """
        idf = small_idf_copy
        zone = idf.getobject("ZONE", "Perim")
        z = ZoneDefinition.from_epbunch(ep_bunch=zone, construct_parents=False)
        assert z.volume == pytest.approx(25.54, 1e-2)

    def test_add_zone(self):
        """Test __add__() for Zone."""
        z_core = ZoneDefinition("Core Zone", area=10 * 10, volume=10 * 10 * 3)
        z_perim = ZoneDefinition("Perim Zone", area=10 * 10, volume=10 * 10 * 3)

        z_new = z_core + z_perim

        assert z_new
        assert z_new.volume == pytest.approx(z_core.volume + z_perim.volume)
        assert z_new.area == pytest.approx(z_core.area + z_perim.area)

    def test_iadd_zone(self):
        """Test __iadd__() for Zone."""
        z_core = ZoneDefinition(
            "Core Zone",
            area=10 * 10,
            volume=10 * 10 * 3,
            InternalMassExposedPerFloorArea=1,
        )
        z_perim = ZoneDefinition(
            "Perim Zone",
            area=10 * 10,
            volume=10 * 10 * 3,
            InternalMassExposedPerFloorArea=0,
        )

        volume = z_core.volume + z_perim.volume  # save volume before changing
        area = z_core.area + z_perim.area  # save area before changing

        id_ = z_core.id
        z_core += z_perim

        assert z_core
        assert z_core.id == id_
        assert z_core.id != z_perim.id

        assert z_core.volume == pytest.approx(volume)
        assert z_core.area == pytest.approx(area)

    def test_hash_eq_zone(self):
        """Test equality and hashing of :class:`ZoneLoad`."""
        zone = ZoneDefinition(
            "Core Zone",
            area=10 * 10,
            volume=10 * 10 * 3,
            InternalMassExposedPerFloorArea=1,
        )
        zone_2 = zone.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert zone == zone_2
        assert hash(zone) == hash(zone_2)
        assert zone is not zone_2

        # hash is used to find object in lookup table
        zone_list = [zone]
        assert zone in zone_list
        assert zone_2 in zone_list  # This is weird but expected

        zone_list.append(zone_2)
        assert zone_2 in zone_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(zone_list)) == 1

        # dict behavior
        zone_dict = {zone: "this_idf", zone_2: "same_idf"}
        assert len(zone_dict) == 1

        zone_2.Name = "some other name"
        # even if name changes, they should be equal
        assert zone_2 == zone

        zone_dict = {zone: "this_idf", zone_2: "same_idf"}
        assert zone in zone_dict
        assert len(zone_dict) == 2

        # if an attribute changed, equality is lost
        zone_2.DaylightMeshResolution = 69
        assert zone != zone_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(zone_list)) == 2

        # 2 Zones from different idf should not have the same hash, not be the same
        # object, yet be equal if they have the same values (Conditioning, Loads, etc.).
        # 2 Zones with different names should not have the same hash.
        zone_3 = zone.duplicate()
        zone_3.DataSource = "OtherIDF"
        assert hash(zone) != hash(zone_3)
        assert id(zone) != id(zone_3)
        assert zone is not zone_3
        assert zone == zone_3


@pytest.fixture(scope="session")
def bt(config):
    """A building template fixture used in subsequent tests"""

    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF.from_example_files("5ZoneCostEst.idf", epw=w, annual=True)
    if idf.sim_info is None:
        idf.simulate()

    bt = BuildingTemplate.from_idf(idf)
    yield bt


class TestBuildingTemplate:
    """Various tests with the :class:`BuildingTemplate` class"""

    @pytest.fixture()
    def building_template(self, zone_definition, structure_information, window_setting):
        bt = BuildingTemplate(
            "A Building Template",
            Core=zone_definition,
            Perimeter=zone_definition,
            Structure=structure_information,
            Windows=window_setting,
        )
        return bt

    @pytest.fixture()
    def window_setting(self, window_construction):
        window_setting = WindowSetting(
            "Window Setting", Construction=window_construction, id="181"
        )
        return window_setting

    @pytest.fixture()
    def window_construction(self):
        window_cstrc = WindowConstruction.from_shgc(
            "Window Construction", 0.5, 2.2, 0.21, id="57"
        )
        return window_cstrc

    @pytest.fixture()
    def structure_information(self):
        return StructureInformation(
            MassRatios=[MassRatio(600, OpaqueMaterial.generic(), 300)],
            Name="structure",
            id="64",
        )

    @pytest.fixture()
    def zone_definition(self):
        return ZoneDefinition(
            Name="Zone 1",
            Constructions=ZoneConstructionSet("Zone 1 Constructions"),
            Loads=ZoneLoad(
                "Zone 1 Load",
                LightsAvailabilitySchedule=UmiSchedule.constant_schedule(),
            ),
            Conditioning=ZoneConditioning("Zone 1 Conditioning"),
            Ventilation=VentilationSetting("Zone 1 Ventilation"),
            DomesticHotWater=DomesticHotWaterSetting("Zone 1 DHW"),
            InternalMassConstruction=OpaqueConstruction.generic(),
            Windows=WindowSetting("Zone 1 Windows"),
            is_core=False,
            id="178",
        )

    def test_init(self, building_template):
        """Test init."""
        bt = building_template
        bt_dup = bt.duplicate()
        assert bt == bt_dup

    def test_from_to_dict(
        self,
        zone_definition,
        structure_information,
        window_setting,
        window_construction,
    ):
        """Make dict with `to_dict` and load again with `from_dict`."""
        data = {
            "Core": {"$ref": "178"},
            "Lifespan": 60,
            "PartitionRatio": 0.3,
            "Perimeter": {"$ref": "178"},
            "Structure": {"$ref": "64"},
            "Windows": {"$ref": "181"},
            "DefaultWindowToWallRatio": 0.4,
            "YearFrom": 0,
            "YearTo": 0,
            "Country": ["USA"],
            "ClimateZone": ["5A"],
            "Authors": ["Carlos Cerezo"],
            "AuthorEmails": ["ccerezo@mit.edu"],
            "Version": "v1.0",
            "Category": "Residential and Lodging",
            "Comments": "Base building definition for MIT 4433",
            "DataSource": "MIT_SDL",
            "Name": "B_Res_0_WoodFrame",
        }
        zone_definitions = [zone_definition]
        structure_informations = [structure_information]
        window_settings = [window_setting]
        year_schedules = []  # needed only of windowsettings is embedded in dict.
        window_constructions = [window_construction]
        bt = BuildingTemplate.from_dict(
            data,
            zone_definitions={a.id: a for a in zone_definitions},
            structure_definitions={a.id: a for a in structure_informations},
            window_settings={a.id: a for a in window_settings},
            schedules={a.id: a for a in year_schedules},
            window_constructions={a.id: a for a in window_constructions},
        )

        bt_dict = bt.to_dict()

        bt_dup = BuildingTemplate.from_dict(
            bt_dict,
            zone_definitions={a.id: a for a in zone_definitions},
            structure_definitions={a.id: a for a in structure_informations},
            window_settings={a.id: a for a in window_settings},
            schedules={a.id: a for a in year_schedules},
            window_constructions={a.id: a for a in window_constructions},
        )

        assert bt == bt_dup

    def test_hash_eq_bt(self, building_template):
        """Test equality and hashing of class BuildingTemplate"""
        bt = building_template
        bt_2 = building_template.duplicate()

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert bt == bt_2
        assert hash(bt) == hash(bt_2)
        assert bt is not bt_2

        # hash is used to find object in lookup table
        bt_list = [bt]
        assert bt in bt_list
        assert bt_2 in bt_list  # This is weird but expected

        bt_list.append(bt_2)
        assert bt_2 in bt_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(bt_list)) == 1

        # dict behavior
        bt_dict = {bt: "this_idf", bt_2: "same_idf"}
        assert len(bt_dict) == 1

        bt_2.Name = "some other name"
        # even if name changes, they should be equal
        assert bt_2 == bt

        bt_dict = {bt: "this_idf", bt_2: "same_idf"}
        assert bt in bt_dict
        assert len(bt_dict) == 2

        # if an attribute changed, equality is lost
        bt_2.Lifespan = 69
        assert bt != bt_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(bt_list)) == 2

    def test_reduce(self, zone_definition):

        bt = BuildingTemplate.reduced_model(
            "A Building Template",
            [zone_definition],
        )


class TestUniqueName(object):
    def test_uniquename(self):
        name1 = UniqueName("myname")
        name2 = UniqueName("myname")
        name3 = UniqueName("myname")

        assert name1 != name2 != name3
        print([name1, name2, name3])
