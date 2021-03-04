import numpy as np
import pytest

from archetypal import IDF, settings
from archetypal.eplus_interface.version import get_eplus_dirs
from archetypal.template import (
    DaySchedule,
    DimmingTypes,
    GlazingMaterial,
    MaterialLayer,
    OpaqueConstruction,
    OpaqueMaterial,
    WeekSchedule,
    YearSchedule,
    ZoneConstructionSet,
    ZoneDefinition,
    ZoneGraph,
    calc_simple_glazing,
)
from archetypal.template.umi_base import UniqueName, load_json_objects


@pytest.fixture(scope="class")
def small_idf(config, small_idf_obj):
    """An IDF model"""
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
    if idf.sim_info is None:
        idf.simulate()
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

    # todo: Implement tests for MaterialLayer class
    pass


class TestConstructionBase:
    """Series of tests for the :class:`ConstructionBase` class"""

    # todo: Implement tests for ConstructionBase class
    pass


class TestLayeredConstruction:
    """Series of tests for the :class:`LayeredConstruction` class"""

    # todo: Implement tests for LayeredConstruction class
    pass


class TestMassRatio:
    """Series of tests for the :class:`MassRatio` class"""

    # todo: Implement tests for MassRatio class
    pass


class TestInternalMass:
    """Series of tests for the parsing of internal mass"""

    def test_with_thermalmassobject(self, small_idf):
        """
        Args:
            small_idf:
        """
        idf = small_idf
        intmass = OpaqueConstruction.generic_internalmass(idf)
        assert intmass.to_json()


class TestYearScheduleParts:
    """Series of tests for the :class:`YearSchedulePart` class"""

    # todo: Implement tests for YearSchedulePart class
    pass


class TestDaySchedule:
    """Series of tests for the :class:`DaySchedule` class"""

    # todo: Implement tests for DaySchedule class

    def test_from_epbunch(self, small_idf):
        """test the `from_epbunch` constructor

        Args:
            small_idf:
        """
        from archetypal.template import DaySchedule

        idf = small_idf
        epbunch = idf.getobject("Schedule:Day:Hourly".upper(), "B_Off_D_Het_WD")
        sched = DaySchedule.from_epbunch(epbunch)
        assert len(sched.all_values) == 24.0
        assert repr(sched)

    def test_from_values(self, config, idf):
        """test the `from_epbunch` constructor

        Args:
            config:
            idf:
        """
        from archetypal.template import DaySchedule

        values = np.array(range(0, 24))
        kwargs = {
            "Category": "Day",
            "Type": "Fraction",
            "Name": "hourlyAllOn",
            "Values": values,
            "idf": idf,
        }
        sched = DaySchedule.from_values(**kwargs)
        assert len(sched.all_values) == 24.0
        assert repr(sched)

    def test_daySchedule_from_to_json(self, config, idf):
        """
        Args:
            config:
            idf:
        """
        import json

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"

        with open(filename, "r") as f:
            datastore = json.load(f)
        loaded_dict = load_json_objects(datastore, idf)
        assert loaded_dict["DaySchedules"][0].to_json()


class TestWeekSchedule:
    """Series of tests for the :class:`WeekSchedule` class"""

    # todo: Implement tests for WeekSchedule class

    @pytest.fixture(scope="class")
    def idf(self):
        yield IDF(prep_outputs=False)

    def test_weekSchedule_from_to_json(self, config, idf):
        """
        Args:
            config:
            idf:
        """
        import json

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)
        loaded_dict = load_json_objects(datastore, idf)
        assert (
            dict(loaded_dict["WeekSchedules"][0].to_json())
            == datastore["WeekSchedules"][0]
        )

    def test_weekSchedule(self, config, idf):
        """Creates WeekSchedule from DaySchedule

        Args:
            config:
            idf:
        """

        # Creates 2 DaySchedules : 1 always ON and 1 always OFF
        sch_d_on = DaySchedule.from_values(
            Values=[1] * 24,
            Category="Day",
            Type="Fraction",
            Name="AlwaysOn",
            idf=idf,
        )
        sch_d_off = DaySchedule.from_values(
            Values=[0] * 24,
            Category="Day",
            Type="Fraction",
            Name="AlwaysOff",
            idf=idf,
        )

        # List of 7 dict with id of DaySchedule, representing the 7 days of the week
        days = [sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on]
        # Creates WeekSchedule from list of DaySchedule
        a = WeekSchedule(
            Days=days,
            Category="Week",
            Type="Fraction",
            Name="OnOff_1",
            idf=idf,
        )

        # Dict of a WeekSchedule (like it would be written in json file)
        dict_w_on = {
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
        b = WeekSchedule.from_dict(**dict_w_on, idf=idf, allow_duplicates=True)

        # Makes sure WeekSchedules created with 2 methods have the same values
        # And different ids
        assert np.array_equal(a.all_values, b.all_values)
        assert a.id != b.id


class TestYearSchedule:
    """Series of tests for the :class:`YearSchedule` class"""

    # todo: Implement tests for YearSchedule class

    def test_yearSchedule_from_to_json(self, config, idf):
        """
        Args:
            config:
            idf:
        """
        import json

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)
        loaded_dict = load_json_objects(datastore, idf)

        assert json.loads(json.dumps(loaded_dict["YearSchedules"][0].to_json())) == (
            datastore["YearSchedules"][0]
        )

    def test_yearSchedule(self, config, idf):
        """Creates YearSchedule from dict (json)

        Args:
            config:
            idf:
        """
        # Creates 2 DaySchedules : 1 always ON and 1 always OFF
        sch_d_on = DaySchedule.from_values(
            Values=[1] * 24,
            Category="Day",
            Type="Fraction",
            Name="AlwaysOn",
            idf=idf,
        )
        sch_d_off = DaySchedule.from_values(
            Values=[0] * 24,
            Category="Day",
            Type="Fraction",
            Name="AlwaysOff",
            idf=idf,
        )

        # List of 7 dict with id of DaySchedule, representing the 7 days of the week
        days = [sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on, sch_d_off, sch_d_on]
        # Creates WeekSchedule from list of DaySchedule
        sch_w_on_off = WeekSchedule(
            Days=days,
            Category="Week",
            Type="Fraction",
            Name="OnOff",
            idf=idf,
        )

        # Dict of a YearSchedule (like it would be written in json file)
        dict_year = {
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
        a = YearSchedule.from_dict(**dict_year, idf=idf, allow_duplicates=True)

        # Makes sure YearSchedule has the same values as concatenate WeekSchedule
        np.testing.assert_equal(a.all_values, np.resize(sch_w_on_off.all_values, 8760))


class TestWindowType:
    """Series of tests for the :class:`YearSchedulePart` class"""

    # todo: Implement tests for WindowType class

    pass


class TestOpaqueMaterial:
    """Series of tests for the :class:`OpaqueMaterial` class"""

    @pytest.fixture()
    def mat_a(self, idf):
        """
        Args:
            idf:
        """
        yield OpaqueMaterial(Conductivity=0.1, SpecificHeat=4.18, Name="mat_a", idf=idf)

    @pytest.fixture()
    def mat_b(self, idf):
        """
        Args:
            idf:
        """
        yield OpaqueMaterial(Conductivity=0.2, SpecificHeat=4.18, Name="mat_b", idf=idf)

    def test_add_materials(self, mat_a, mat_b):
        """test __add__() for OpaqueMaterial

        Args:
            mat_a:
            mat_b:
        """
        mat_c = mat_a + mat_b
        assert mat_c
        np.testing.assert_almost_equal(mat_c.Conductivity, 0.150)
        assert mat_a.id != mat_b.id != mat_c.id

        mat_d = mat_c + mat_a
        print(mat_c)
        print(mat_d)

    def test_iadd_materials(self, idf):
        """test __iadd__() for OpaqueMaterial

        Args:
            idf:
        """
        mat_a = OpaqueMaterial(
            Conductivity=0.1, SpecificHeat=4.18, Name="mat_ia", idf=idf
        )
        id_ = mat_a.id  # storing mat_a's id.

        mat_b = OpaqueMaterial(
            Conductivity=0.2, SpecificHeat=4.18, Name="mat_ib", idf=idf
        )
        mat_a += mat_b
        assert mat_a
        np.testing.assert_almost_equal(mat_a.Conductivity, 0.150)
        assert mat_a.id == id_  # id should not change
        assert mat_a.id != mat_b.id

    def test_opaqueMaterial_from_to_json(self, config, small_idf_obj):
        """Get OpaqueMaterial, convert to json, load back and compare."""
        from archetypal.template import OpaqueMaterial

        idf = small_idf_obj
        if idf.idfobjects["MATERIAL"]:
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(idf.idfobjects["MATERIAL"][0])
            opaqMat_json = opaqMat_epBunch.to_json()
            assert OpaqueMaterial(**opaqMat_json) == opaqMat_epBunch
        if idf.idfobjects["MATERIAL:NOMASS"]:
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(
                idf.idfobjects["MATERIAL:NOMASS"][0]
            )
            opaqMat_json = opaqMat_epBunch.to_json()
            assert OpaqueMaterial(**opaqMat_json) == opaqMat_epBunch
        if idf.idfobjects["MATERIAL:AIRGAP"]:
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(
                idf.idfobjects["MATERIAL:AIRGAP"][0]
            )
            opaqMat_json = opaqMat_epBunch.to_json()
            assert OpaqueMaterial(**opaqMat_json) == opaqMat_epBunch

    def test_hash_eq_opaq_mat(self, small_idf_obj, other_idf_object):
        """Test equality and hashing of :class:`TestOpaqueMaterial`

        Args:
            small_idf_obj:
            other_idf_object:
        """
        from copy import copy

        from archetypal.template import OpaqueMaterial

        idf = small_idf_obj
        opaq_mat = idf.getobject("MATERIAL", "B_Gypsum_Plaster_0.02_B_Off_Thm_0")
        om = OpaqueMaterial.from_epbunch(opaq_mat)
        om_2 = copy(om)

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
        idf_2 = other_idf_object
        assert idf is not idf_2
        opaq_mat_3 = idf_2.getobject("MATERIAL", "B_Gypsum_Plaster_0.02_B_Res_Thm_0")
        assert opaq_mat is not opaq_mat_3
        assert opaq_mat != opaq_mat_3
        om_3 = OpaqueMaterial.from_epbunch(opaq_mat_3, allow_duplicates=True)
        assert hash(om) != hash(om_3)
        assert id(om) != id(om_3)
        assert om is not om_3
        assert om == om_3


class TestGlazingMaterial:
    """Series of tests for the :class:`GlazingMaterial` class"""

    def test_simple_glazing_material(self, config):
        """
        Args:
            config:
            idf:
        """
        name = "A Glass Material"
        glass = GlazingMaterial(
            Name=name,
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
        )
        assert glass.Name == name

    def test_add_glazing_material(self, config):
        """test __add__() for OpaqueMaterial

        Args:
            config:
            idf:
        """
        sg_a = calc_simple_glazing(0.763, 2.716, 0.812)
        sg_b = calc_simple_glazing(0.578, 2.413, 0.706)
        mat_a = GlazingMaterial(Name="mat_a", **sg_a)
        mat_b = GlazingMaterial(Name="mat_b", **sg_b)

        mat_c = mat_a + mat_b

        assert mat_c
        assert mat_a.id != mat_b.id != mat_c.id

    def test_iadd_glazing_material(self, config):
        """test __iadd__() for OpaqueMaterial

        Args:
            config:
            idf:
        """
        sg_a = calc_simple_glazing(0.763, 2.716, 0.812)
        sg_b = calc_simple_glazing(0.578, 2.413, 0.706)
        mat_a = GlazingMaterial(Name="mat_ia", **sg_a)
        mat_b = GlazingMaterial(Name="mat_ib", **sg_b)

        id_ = mat_a.id  # storing mat_a's id.

        mat_a += mat_b

        assert mat_a
        assert mat_a.id == id_  # id should not change
        assert mat_a.id != mat_b.id

    # todo: Implement from_to_json test for GlazingMaterial class

    def test_hash_eq_glaz_mat(self, config):
        """Test equality and hashing of :class:`OpaqueConstruction`

        Args:
            config:
            idf:
        """
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

    def test_gas_material(self, config):
        """
        Args:
            config:
            idf:
        """
        from archetypal.template import GasMaterial

        air = GasMaterial(Name="Air", Conductivity=0.02, Density=1.24)

        assert air.Conductivity == 0.02

    def test_GasMaterial_from_to_json(self, config, idf):
        """
        Args:
            config:
            idf:
        """
        import json

        from archetypal.template import GasMaterial

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)
        gasMat_json = [
            GasMaterial.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["GasMaterials"]
        ]
        gasMat_to_json = gasMat_json[0].to_json()
        assert gasMat_json[0].Name == gasMat_to_json["Name"]

    def test_hash_eq_gas_mat(self, config, idf):
        """Test equality and hashing of :class:`OpaqueConstruction`

        Args:
            config:
            idf:
        """
        import json
        from copy import copy

        from archetypal.template import GasMaterial

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)
        gasMat_json = [
            GasMaterial.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["GasMaterials"]
        ]
        gm = gasMat_json[0]
        gm_2 = copy(gm)

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
        gm_3 = copy(gm)
        gm_3.Name = "other name"
        assert hash(gm) != hash(gm_3)
        assert id(gm) != id(gm_3)
        assert gm is not gm_3
        assert gm == gm_3


class TestOpaqueConstruction:
    """Series of tests for the :class:`OpaqueConstruction` class"""

    @pytest.fixture()
    def mat_a(self, idf):
        """A :class:Material fixture

        Args:
            idf:
        """
        mat_a = OpaqueMaterial(
            Conductivity=1.4, SpecificHeat=840, Density=2240, Name="Concrete", idf=idf
        )
        yield mat_a

    @pytest.fixture()
    def mat_b(self, idf):
        """A :class:Material fixture

        Args:
            idf:
        """
        mat_b = OpaqueMaterial(
            Conductivity=0.12, SpecificHeat=1210, Density=540, Name="Plywood", idf=idf
        )

        yield mat_b

    @pytest.fixture()
    def construction_a(self, mat_a, mat_b, idf):
        """A :class:Construction fixture

        Args:
            mat_a:
            mat_b:
            idf:
        """
        thickness = 0.10
        layers = [
            MaterialLayer(mat_a, thickness),
            MaterialLayer(mat_b, thickness),
        ]
        oc_a = OpaqueConstruction(Layers=layers, Name="oc_a", idf=idf)

        yield oc_a

    @pytest.fixture()
    def face_brick(self, idf):
        """A :class:Material fixture

        Args:
            idf:
        """
        face_brick = OpaqueMaterial(
            Conductivity=1.20,
            Density=1900,
            SpecificHeat=850,
            Name="Face Brick",
            idf=idf,
        )
        yield face_brick

    @pytest.fixture()
    def thermal_insulation(self, idf):
        """A :class:Material fixture

        Args:
            idf:
        """
        thermal_insulation = OpaqueMaterial(
            Conductivity=0.041,
            Density=40,
            SpecificHeat=850,
            Name="Thermal insulation",
            idf=idf,
        )
        yield thermal_insulation

    @pytest.fixture()
    def hollow_concrete_block(self, idf):
        """A :class:Material fixture

        Args:
            idf:
        """
        hollow_concrete_block = OpaqueMaterial(
            Conductivity=0.85,
            Density=2000,
            SpecificHeat=920,
            Name="Hollow concrete block",
            idf=idf,
        )
        yield hollow_concrete_block

    @pytest.fixture()
    def plaster(self, idf):
        """A :class:Material fixture

        Args:
            idf:
        """
        plaster = OpaqueMaterial(
            Conductivity=1.39, Density=2000, SpecificHeat=1085, Name="Plaster", idf=idf
        )
        yield plaster

    @pytest.fixture()
    def concrete_layer(self, idf):
        """A :class:Material fixture

        Args:
            idf:
        """
        concrete = OpaqueMaterial(
            Conductivity=1.70,
            Density=2300,
            SpecificHeat=920,
            Name="Concrete layer",
            idf=idf,
        )
        yield concrete

    @pytest.fixture()
    def facebrick_and_concrete(
        self, face_brick, thermal_insulation, hollow_concrete_block, plaster, idf
    ):
        """A :class:Construction based on the `Facebrick–concrete wall` from: On
        the thermal time constant of structural walls. Applied Thermal
        Engineering, 24(5–6), 743–757.
        https://doi.org/10.1016/j.applthermaleng.2003.10.015

        Args:
            face_brick:
            thermal_insulation:
            hollow_concrete_block:
            plaster:
            idf:
        """
        layers = [
            MaterialLayer(face_brick, 0.1),
            MaterialLayer(thermal_insulation, 0.04),
            MaterialLayer(hollow_concrete_block, 0.2),
            MaterialLayer(plaster, 0.02),
        ]
        oc_a = OpaqueConstruction(
            Layers=layers, Name="Facebrick–concrete wall", idf=idf
        )

        yield oc_a

    @pytest.fixture()
    def insulated_concrete_wall(
        self, face_brick, thermal_insulation, concrete_layer, plaster, idf
    ):
        """A :class:Construction based on the `Facebrick–concrete wall` from: On
        the thermal time constant of structural walls. Applied Thermal
        Engineering, 24(5–6), 743–757.
        https://doi.org/10.1016/j.applthermaleng.2003.10.015

        Args:
            face_brick:
            thermal_insulation:
            concrete_layer:
            plaster:
            idf:
        """
        layers = [
            MaterialLayer(plaster, 0.02),
            MaterialLayer(concrete_layer, 0.20),
            MaterialLayer(thermal_insulation, 0.04),
            MaterialLayer(plaster, 0.02),
        ]
        oc_a = OpaqueConstruction(
            Layers=layers, Name="Insulated Concrete Wall", idf=idf
        )

        yield oc_a

    @pytest.fixture()
    def construction_b(self, mat_a, idf):
        """A :class:Construction fixture

        Args:
            mat_a:
            idf:
        """
        thickness = 0.30
        layers = [MaterialLayer(mat_a, thickness)]
        oc_b = OpaqueConstruction(Layers=layers, Name="oc_b", idf=idf)

        yield oc_b

    def test_thermal_properties(self, construction_a):
        """test r_value and u_value properties

        Args:
            construction_a:
        """
        assert 1 / construction_a.r_value == construction_a.u_value()

    def test_add_opaque_construction(self, construction_a, construction_b):
        """Test __add__() for OpaqueConstruction

        Args:
            construction_a:
            construction_b:
        """
        oc_c = OpaqueConstruction.combine(
            construction_a, construction_b, method="constant_ufactor"
        )
        assert oc_c
        desired = 3.237
        actual = oc_c.u_value()
        np.testing.assert_almost_equal(actual, desired, decimal=3)

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

    def test_opaqueConstruction_from_to_json(self, config, idf):
        """
        Args:
            config:
            idf:
        """
        import json

        from archetypal.template import (
            MaterialLayer,
            OpaqueConstruction,
            OpaqueMaterial,
        )

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        mat_a = OpaqueMaterial(
            Conductivity=100, SpecificHeat=4.18, Name="mat_a", idf=idf
        )
        mat_b = OpaqueMaterial(
            Conductivity=0.2, SpecificHeat=4.18, Name="mat_b", idf=idf
        )
        thickness = 0.10
        layers = [MaterialLayer(mat_a, thickness), MaterialLayer(mat_b, thickness)]

        with open(filename, "r") as f:
            datastore = json.load(f)
        load_json_objects(datastore, idf)
        opaqConstr_json = [
            OpaqueConstruction.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["OpaqueConstructions"]
        ]
        assert opaqConstr_json[0].to_json()

    def test_hash_eq_opaq_constr(self, small_idf, other_idf):
        """Test equality and hashing of :class:`OpaqueConstruction`

        Args:
            small_idf:
            other_idf:
        """
        from copy import copy

        from archetypal.template import OpaqueConstruction

        idf = small_idf
        opaq_constr = idf.getobject("CONSTRUCTION", "B_Off_Thm_0")
        oc = OpaqueConstruction.from_epbunch(opaq_constr)
        oc_2 = copy(oc)

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert oc == oc_2
        assert hash(oc) == hash(oc_2)
        assert oc is not oc_2

        # hash is used to find object in lookup table
        oc_list = [oc]
        assert oc in oc_list
        assert oc_2 in oc_list  # This is weird but expected

        oc_list.append(oc_2)
        assert oc_2 in oc_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(oc_list)) == 1

        # dict behavior
        oc_dict = {oc: "this_idf", oc_2: "same_idf"}
        assert len(oc_dict) == 1

        oc_2.Name = "some other name"
        # even if name changes, they should be equal
        assert oc_2 == oc

        oc_dict = {oc: "this_idf", oc_2: "same_idf"}
        assert oc in oc_dict
        assert len(oc_dict) == 2

        # if an attribute changed, equality is lost
        oc_2.Layers = None
        assert oc != oc_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(oc_list)) == 2

        # 2 OpaqueConstruction from different idf should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same layers (Material and Thickness)
        idf_2 = other_idf
        assert idf is not idf_2
        opaq_constr_3 = idf_2.getobject("CONSTRUCTION", "B_Res_Thm_0")
        assert opaq_constr is not opaq_constr_3
        assert opaq_constr != opaq_constr_3
        oc_3 = OpaqueConstruction.from_epbunch(opaq_constr_3, allow_duplicates=True)
        assert hash(oc) != hash(oc_3)
        assert id(oc) != id(oc_3)
        assert oc is not oc_3
        assert oc == oc_3

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
        assert facebrick_and_concrete.u_value(include_h=True) == pytest.approx(
            0.6740, 0.01
        )
        assert (
            facebrick_and_concrete.equivalent_heat_capacity_per_unit_volume
            == pytest.approx(1595166.7, 0.01)
        )
        assert facebrick_and_concrete.heat_capacity_per_unit_wall_area == pytest.approx(
            574260.0, 0.1
        )

        assert insulated_concrete_wall.u_value(include_h=True) == pytest.approx(
            0.7710, 0.01
        )
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


class TestWindowConstruction:
    """Series of tests for the :class:`WindowConstruction` class"""

    # todo: Implement from_to_json for WindowConstruction class

    def test_windowConstr_from_to_json(self, config, idf):
        """
        Args:
            config:
            idf:
        """
        import json

        from archetypal.template import WindowConstruction

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)
        load_json_objects(datastore, idf)
        winConstr_json = [
            WindowConstruction.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["WindowConstructions"]
        ]
        assert winConstr_json[0].to_json()


class TestStructureDefinition:
    """Series of tests for the :class:`StructureInformation` class"""

    # todo: Implement from_to_json for StructureInformation class

    def test_structure_from_to_json(self, config, idf):
        """
        Args:
            config:
            idf:
        """
        import json

        from archetypal.template import StructureInformation

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)
        load_json_objects(datastore, idf)
        struct_json = [
            StructureInformation.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["StructureDefinitions"]
        ]
        assert struct_json[0].to_json()

    def test_hash_eq_struc_def(self, config, idf):
        """Test equality and hashing of :class:`OpaqueConstruction`

        Args:
            config:
            idf:
        """
        import json
        from copy import copy

        from archetypal.template import StructureInformation

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)

        struct_json = [
            StructureInformation.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["StructureDefinitions"]
        ]
        sd = struct_json[0]
        sd_2 = copy(sd)

        # a copy of dhw should be equal and have the same hash, but still not be the
        # same object
        assert sd == sd_2
        assert hash(sd) == hash(sd_2)
        assert sd is not sd_2

        # hash is used to find object in lookup table
        sd_list = [sd]
        assert sd in sd_list
        assert sd_2 in sd_list  # This is weird but expected

        sd_list.append(sd_2)
        assert sd_2 in sd_list

        # length of set() should be 1 since both objects are
        # equal but don't have the same hash.
        assert len(set(sd_list)) == 1

        # dict behavior
        sd_dict = {sd: "this_idf", sd_2: "same_idf"}
        assert len(sd_dict) == 1

        sd_2.Name = "some other name"
        # even if name changes, they should be equal
        assert sd_2 == sd

        sd_dict = {sd: "this_idf", sd_2: "same_idf"}
        assert sd in sd_dict
        assert len(sd_dict) == 2

        # if an attribute changed, equality is lost
        sd_2.AssemblyCost = 69
        assert sd != sd_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(sd_list)) == 2

        # 2 GasMaterial from same json should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same layers (Material and Thickness)
        sd_3 = copy(sd)
        sd_3.Name = "other name"
        assert hash(sd) != hash(sd_3)
        assert id(sd) != id(sd_3)
        assert sd is not sd_3
        assert sd == sd_3


class TestUmiSchedule:
    """Tests for :class:`UmiSchedule` class"""

    # todo: Implement from_to_json for UmiSchedule class

    def test_constant_umischedule(self, config, idf):
        """
        Args:
            config:
            idf:
        """
        from archetypal.template import UmiSchedule

        const = UmiSchedule.constant_schedule(idf=idf)
        assert const.__class__.__name__ == "UmiSchedule"
        assert const.Name == "AlwaysOn"

    def test_schedule_develop(self, config, small_idf):
        """
        Args:
            config:
            small_idf:
        """
        from archetypal.template import UmiSchedule

        idf = small_idf
        # clear_cache()
        sched = UmiSchedule(Name="B_Off_Y_Occ", idf=idf)
        assert sched.to_dict()

    def test_hash_eq_umi_sched(self, small_idf, other_idf):
        """Test equality and hashing of :class:`ZoneLoad`"""
        from copy import copy

        from archetypal.template import UmiSchedule

        idf = small_idf
        sched = UmiSchedule(Name="On", idf=idf)
        sched_2 = copy(sched)

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

        # 2 UmiSchedule from different idf should have the same hash,
        # not be the same object, yet be equal if they have the same values
        idf_2 = other_idf
        assert idf is not idf_2
        sched_3 = UmiSchedule(Name="On", idf=idf_2, allow_duplicates=True)
        assert sched is not sched_3
        assert sched == sched_3
        assert hash(sched) == hash(sched_3)
        assert id(sched) != id(sched_3)

    def test_combine(self):
        import numpy as np

        from archetypal.template import UmiSchedule
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
    """Combines different :class:`ZoneConstructionSet` tests"""

    def test_add_zoneconstructionset(self, small_idf):
        """Test __add__() for ZoneConstructionSet."""
        idf = small_idf
        zone_core = idf.getobject("ZONE", core_name)
        zone_perim = idf.getobject("ZONE", perim_name)

        z_core = ZoneConstructionSet.from_zone(
            ZoneDefinition.from_zone_epbunch(zone_core)
        )
        z_perim = ZoneConstructionSet.from_zone(
            ZoneDefinition.from_zone_epbunch(zone_perim)
        )
        z_new = z_core + z_perim
        assert z_new

    def test_iadd_zoneconstructionset(self, small_idf):
        """Test __iadd__() for ZoneConstructionSet."""
        idf = small_idf
        zone_core = idf.getobject("ZONE", core_name)
        zone_perim = idf.getobject("ZONE", perim_name)

        z_core = ZoneConstructionSet.from_zone(
            ZoneDefinition.from_zone_epbunch(zone_core)
        )
        z_perim = ZoneConstructionSet.from_zone(
            ZoneDefinition.from_zone_epbunch(zone_perim)
        )
        id_ = z_core.id
        z_core += z_perim

        assert z_core
        assert z_core.id == id_  # id should not change
        assert z_core.id != z_perim.id

    def test_zoneConstructionSet_init(self, config, idf):
        """"""
        from archetypal.template import ZoneConstructionSet

        constrSet = ZoneConstructionSet(Name="A construction set", idf=idf)

    def test_zoneConstructionSet_from_zone(self, config, warehouse):
        """"""
        from archetypal.template import ZoneConstructionSet, ZoneDefinition

        idf = warehouse
        zone = idf.getobject("ZONE", "Office")
        z = ZoneDefinition.from_zone_epbunch(zone_ep=zone)
        constrSet_ = ZoneConstructionSet.from_zone(z)

    def test_zoneConstructionSet_from_to_json(self, config, idf):
        """"""
        import json

        from archetypal.template import ZoneConstructionSet

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)

        constr_json = [
            ZoneConstructionSet.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["ZoneConstructionSets"]
        ]
        assert constr_json[0].to_json()


class TestZoneLoad:
    """Combines different :class:`ZoneLoad` tests"""

    @pytest.fixture(scope="class")
    def fiveZoneEndUses(self, config):
        """"""
        w = (
            get_eplus_dirs(settings.ep_version)
            / "WeatherData"
            / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
        )
        idf = IDF.from_example_files(
            "5ZoneAirCooled_AirBoundaries_Daylighting.idf", epw=w
        )
        if idf.sim_info is None:
            idf.simulate()
        yield idf

    def test_zoneLoad_init(self, config, idf):
        """"""
        from archetypal.template import ZoneLoad

        load = ZoneLoad(Name=None, idf=idf)

    def test_zoneLoad_picle(self, config, idf):
        import pickle

        from archetypal.template import ZoneLoad

        zone_load = ZoneLoad(Name=None, idf=idf)

        with open("Emp.pickle", "wb") as pickling_on:
            pickle.dump(zone_load, pickling_on)

        with open("Emp.pickle", "rb") as pickle_off:
            emp = pickle.load(pickle_off)
            print(emp)

        assert zone_load == emp

    def test_zoneLoad_from_zone(self, config, warehouse):
        """"""
        from archetypal.template import ZoneDefinition, ZoneLoad

        idf = warehouse
        zone = idf.getobject("ZONE", "Office")
        z = ZoneDefinition.from_zone_epbunch(zone_ep=zone)
        zone_loads = ZoneLoad.from_zone(z)

        assert zone_loads.DimmingType == DimmingTypes.Off
        assert zone_loads.EquipmentPowerDensity == 8.07
        assert zone_loads.IlluminanceTarget == 500
        assert zone_loads.IsEquipmentOn
        assert zone_loads.IsPeopleOn
        assert zone_loads.LightingPowerDensity == 11.84
        assert zone_loads.PeopleDensity == 0.021

    def test_zoneLoad_from_zone_mixedparams(self, config, fiveZoneEndUses):
        """"""
        from archetypal.template import ZoneDefinition, ZoneLoad

        idf = fiveZoneEndUses
        zone = idf.getobject("ZONE", "SPACE1-1")
        z = ZoneDefinition.from_zone_epbunch(zone_ep=zone)
        zone_loads = ZoneLoad.from_zone(z)

        assert zone_loads.DimmingType == DimmingTypes.Stepped
        assert zone_loads.EquipmentPowerDensity == 10.649
        assert zone_loads.IlluminanceTarget == 400
        assert zone_loads.IsEquipmentOn
        assert zone_loads.IsPeopleOn
        assert zone_loads.LightingPowerDensity == 15.974
        assert zone_loads.PeopleDensity == 0.111

    def test_zoneLoad_from_to_json(self, config, idf):
        """"""
        import json

        from archetypal.template import ZoneLoad
        from archetypal.utils import reduce

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)

        load_json = [
            ZoneLoad.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["ZoneLoads"]
        ]
        assert load_json[0].to_json()

    def test_hash_eq_zone_load(self, small_idf, small_idf_copy):
        """Test equality and hashing of :class:`ZoneLoad`."""
        from copy import copy

        from archetypal.template import ZoneDefinition, ZoneLoad

        idf = small_idf
        zone_ep = idf.idfobjects["ZONE"][0]
        zone = ZoneDefinition.from_zone_epbunch(zone_ep)
        zl = ZoneLoad.from_zone(zone)
        zl_2 = copy(zl)

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

        # 2 ZoneLoad from different idf should have the same hash if they
        # have the same name, not be the same object, yet be equal if they have the
        # same values (EquipmentPowerDensity, LightingPowerDensity, etc.)
        idf_2 = small_idf_copy
        zone_ep_3 = idf_2.idfobjects["ZONE"][0]
        zone_3 = ZoneDefinition.from_zone_epbunch(zone_ep_3)
        assert idf is not idf_2
        zl_3 = ZoneLoad.from_zone(zone_3, allow_duplicates=True)
        assert zone_ep is not zone_ep_3
        assert zone_ep != zone_ep_3
        assert hash(zl) == hash(zl_3)
        assert id(zl) != id(zl_3)
        assert zl is not zl_3
        assert zl == zl_3


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

    def test_zoneConditioning_init(self, config, idf):
        """"""
        from archetypal.template import ZoneConditioning

        cond = ZoneConditioning(Name="A Name", idf=idf)
        assert cond.Name == "A Name"

        with pytest.raises(TypeError):
            # Name should be required, so it should raise a TypeError if it is missing
            cond = ZoneConditioning()

    def test_zoneConditioning_from_zone(self, config, zoneConditioningtests):
        """"""
        from archetypal.template import ZoneConditioning, ZoneDefinition

        idf, idf_name, _ = zoneConditioningtests
        if idf_name == "RefMedOffVAVAllDefVRP.idf":
            zone = idf.getobject("ZONE", "Core_mid")
            z = ZoneDefinition.from_zone_epbunch(zone_ep=zone)
            cond_ = ZoneConditioning.from_zone(z)
        if idf_name == "AirflowNetwork_MultiZone_SmallOffice_HeatRecoveryHXSL.idf":
            zone = idf.getobject("ZONE", "West Zone")
            z = ZoneDefinition.from_zone_epbunch(zone_ep=zone)
            cond_HX = ZoneConditioning.from_zone(z)
        if idf_name == "AirflowNetwork_MultiZone_SmallOffice_CoilHXAssistedDX.idf":
            zone = idf.getobject("ZONE", "East Zone")
            z = ZoneDefinition.from_zone_epbunch(zone_ep=zone)
            cond_HX_eco = ZoneConditioning.from_zone(z)

    def test_zoneConditioning_from_to_json(self, config, idf):
        """"""
        import json

        from archetypal.template import ZoneConditioning
        from archetypal.utils import reduce

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)
        load_json_objects(datastore, idf)
        cond_json = [
            ZoneConditioning.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["ZoneConditionings"]
        ]
        assert reduce(ZoneConditioning.combine, cond_json, weights=[1, 1]).to_json()

    def test_hash_eq_zone_cond(self, zoneConditioningtests):
        """Test equality and hashing of :class:`ZoneConditioning`

        Args:
            zoneConditioningtests:
        """
        from copy import copy

        from archetypal.template import ZoneConditioning, ZoneDefinition

        idf, idf_name, idf_2 = zoneConditioningtests

        zone_ep = idf.idfobjects["ZONE"][0]
        zone = ZoneDefinition.from_zone_epbunch(zone_ep, construct_parents=False)
        zc = ZoneConditioning.from_zone(zone)
        zc_2 = copy(zc)

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
        zc_2.IsCoolingOn = False
        assert zc != zc_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(zc_list)) == 2

        # 2 ZoneConditioning from different idf should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same values (CoolingSetpoint, HeatingSetpoint, etc.)
        zone_ep_3 = idf_2.idfobjects["ZONE"][0]
        zone_3 = ZoneDefinition.from_zone_epbunch(zone_ep_3, construct_parents=False)
        assert idf is not idf_2
        zc_3 = ZoneConditioning.from_zone(zone_3)
        assert zone_ep is not zone_ep_3
        assert zone_ep != zone_ep_3
        assert hash(zc) == hash(zc_3)
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
        """
        Args:
            config:
            request:
        """

        eplusdir = get_eplus_dirs(settings.ep_version)
        w = eplusdir / "WeatherData" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
        idf = IDF.from_example_files(request.param, epw=w, annual=True)
        if idf.sim_info is None:
            idf.simulate()
        copy = IDF.from_example_files(request.param, epw=w, annual=True)
        if copy.sim_info is None:
            copy.simulate()
        yield idf, request.param, copy  # passes a copy as well

    def test_ventilation_init(self, config, idf):
        """
        Args:
            config:
            idf:
        """
        from archetypal.template import VentilationSetting

        vent = VentilationSetting(Name=None, idf=idf)

    def test_naturalVentilation_from_zone(self, config, ventilatontests):
        """
        Args:
            config:
            ventilatontests:
        """
        from archetypal.template import VentilationSetting, ZoneDefinition

        idf, idf_name, _ = ventilatontests
        if idf_name == "VentilationSimpleTest.idf":
            zone = idf.getobject("ZONE", "ZONE 1")
            z = ZoneDefinition.from_zone_epbunch(zone_ep=zone, construct_parents=False)
            natVent = VentilationSetting.from_zone(z)
        if idf_name == "VentilationSimpleTest.idf":
            zone = idf.getobject("ZONE", "ZONE 2")
            z = ZoneDefinition.from_zone_epbunch(zone_ep=zone, construct_parents=False)
            schedVent = VentilationSetting.from_zone(z)
        if idf_name == "RefBldgWarehouseNew2004_Chicago.idf":
            zone = idf.getobject("ZONE", "Office")
            z = ZoneDefinition.from_zone_epbunch(zone_ep=zone, construct_parents=False)
            infiltVent = VentilationSetting.from_zone(z)

    def test_ventilationSetting_from_to_json(self, config, idf):
        """"""
        import json

        from archetypal.template import VentilationSetting
        from archetypal.utils import reduce

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        with open(filename, "r") as f:
            datastore = json.load(f)
        load_json_objects(datastore, idf)
        vent_json = [
            VentilationSetting.from_dict(**store, idf=idf, allow_duplicates=True)
            for store in datastore["VentilationSettings"]
        ]
        assert reduce(VentilationSetting.combine, vent_json, weights=[1, 1]).to_json()

    def test_hash_eq_vent_settings(self, ventilatontests):
        """Test equality and hashing of :class:`DomesticHotWaterSetting`."""
        from copy import copy

        from archetypal.template import VentilationSetting, ZoneDefinition

        idf, idf_name, idf_2 = ventilatontests

        zone_ep = idf.idfobjects["ZONE"][0]
        zone = ZoneDefinition.from_zone_epbunch(zone_ep, construct_parents=False)
        vent = VentilationSetting.from_zone(zone)
        vent_2 = copy(vent)

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

        # 2 VentilationSettings from different idf should have the same hash if they
        # have same names, not be the same object, yet be equal if they have the
        # same values (Infiltration, IsWindOn, etc.)

        zone_ep_3 = idf_2.idfobjects["ZONE"][0]
        zone_3 = ZoneDefinition.from_zone_epbunch(
            zone_ep_3, construct_parents=False, allow_duplicates=True
        )
        vent_3 = VentilationSetting.from_zone(zone)
        assert idf is not idf_2
        vent_3 = VentilationSetting.from_zone(zone_3, allow_duplicates=True)
        assert zone_ep is not zone_ep_3
        assert zone_ep != zone_ep_3
        assert hash(vent) == hash(vent_3)
        assert id(vent) != id(vent_3)
        assert vent is not vent_3
        assert vent == vent_3


class TestDomesticHotWaterSetting:
    """Series of tests for the :class:`DomesticHotWaterSetting` class"""

    def test_hash_eq_dhw(self, small_idf):
        """Test equality and hashing of :class:`DomesticHotWaterSetting`

        Args:
            small_idf:
        """
        from copy import copy

        from archetypal.template import DomesticHotWaterSetting, UmiSchedule

        dhw = DomesticHotWaterSetting(
            Name="",
            IsOn=True,
            WaterSchedule=UmiSchedule.constant_schedule(),
            FlowRatePerFloorArea=0.03,
            WaterSupplyTemperature=65,
            WaterTemperatureInlet=10,
        )
        dhw_2 = copy(dhw)

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
    """Combines different :class:`WindowSetting` tests"""

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
        from archetypal.template import WindowSetting

        idf = small_idf
        construction = idf.getobject("CONSTRUCTION", "B_Dbl_Air_Cl")
        # clear_cache()
        w = WindowSetting.from_construction(construction)

        assert w.to_json()

    @pytest.fixture(scope="class")
    def allwindowtypes(self, config, windowtests):
        """
        Args:
            config:
            windowtests:
        """
        from archetypal.template import WindowSetting

        idf = windowtests
        f_surfs = idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]
        windows = []
        for f in f_surfs:
            windows.append(WindowSetting.from_surface(f))
        yield windows

    def test_allwindowtype(self, allwindowtypes):
        """
        Args:
            allwindowtypes:
        """
        assert allwindowtypes

    def test_winow_add2(self, allwindowtypes):
        """
        Args:
            allwindowtypes:
        """
        from archetypal.template import WindowSetting
        from archetypal.utils import reduce

        window = reduce(WindowSetting.combine, allwindowtypes)
        print(window)

    def test_window_add(self):
        """
        Args:
            small_idf:
            other_idf:
        """
        from archetypal.template import WindowSetting

        idf = IDF()
        window_1 = WindowSetting.generic(idf, Name="window_1")
        window_2 = WindowSetting.generic(idf, Name="window_2")

        new_w = window_1 + window_2
        assert window_1 == window_2
        assert new_w.id == window_1.id
        assert window_1.id != window_2.id != new_w.id

    def test_window_iadd(self, small_idf, other_idf):
        """
        Args:
            small_idf:
            other_idf:
        """
        from archetypal.template import WindowSetting

        idf = small_idf
        idf2 = other_idf
        zone = idf.idfobjects["ZONE"][0]
        iterator = iter([win for surf in zone.zonesurfaces for win in surf.subsurfaces])
        surface = next(iterator, None)
        window_1 = WindowSetting.from_surface(surface)
        id_ = window_1.id
        zone = idf2.idfobjects["ZONE"][0]
        iterator = iter([win for surf in zone.zonesurfaces for win in surf.subsurfaces])
        surface = next(iterator, None)
        window_2 = WindowSetting.from_surface(surface, allow_duplicates=True)

        window_1 += window_2
        assert window_1
        assert window_1.id == id_  # id should not change
        assert window_1.id != window_2.id

    def test_glazing_material_from_simple_glazing(self, config, idf):
        """test __add__() for OpaqueMaterial

        Args:
            config:
            idf:
        """
        sg_a = calc_simple_glazing(0.763, 2.716, 0.812)
        mat_a = GlazingMaterial(Name="mat_a", **sg_a, idf=idf)
        glazMat_to_json = mat_a.to_json()
        assert glazMat_to_json

    def test_window_generic(self, small_idf):
        """
        Args:
            small_idf:
        """
        from archetypal.template import WindowSetting

        idf = small_idf
        w = WindowSetting.generic(idf, "Generic Window")

        assert w.to_json()

    def test_hash_eq_window_settings(self, small_idf, small_idf_copy):
        """Test equality and hashing of :class:`DomesticHotWaterSetting`"""
        from copy import copy

        from archetypal.template import WindowSetting

        idf = small_idf
        f_surf = idf.idfobjects["FENESTRATIONSURFACE:DETAILED"][0]
        wind = WindowSetting.from_surface(f_surf)
        wind_2 = copy(wind)

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
        from archetypal.template import WindowSetting

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


class TestZone:
    """Tests for :class:`Zone` class"""

    def test_zone_volume(self, small_idf_copy):
        """Test the zone volume for a sloped roof

        Args:
            small_idf_copy:
        """
        from archetypal.template import ZoneDefinition

        idf = small_idf_copy
        zone = idf.getobject("ZONE", "Perim")
        z = ZoneDefinition.from_zone_epbunch(zone_ep=zone, construct_parents=False)
        np.testing.assert_almost_equal(desired=z.volume, actual=25.54, decimal=1)

    def test_add_zone(self, small_idf_copy):
        """Test __add__() for Zone

        Args:
            small_idf_copy:
        """
        idf = small_idf_copy
        zone_core = idf.getobject("ZONE", core_name)
        zone_perim = idf.getobject("ZONE", perim_name)

        z_core = ZoneDefinition.from_zone_epbunch(zone_core, construct_parents=False)
        z_perim = ZoneDefinition.from_zone_epbunch(zone_perim, construct_parents=False)

        z_new = z_core + z_perim

        assert z_new
        np.testing.assert_almost_equal(
            actual=z_core.volume + z_perim.volume, desired=z_new.volume, decimal=3
        )
        np.testing.assert_almost_equal(
            actual=z_core.area + z_perim.area, desired=z_new.area, decimal=3
        )

    def test_iadd_zone(self, small_idf_copy):
        """Test __iadd__() for Zone

        Args:
            small_idf_copy:
        """
        idf = small_idf_copy
        zone_core = idf.getobject("ZONE", core_name)
        zone_perim = idf.getobject("ZONE", perim_name)

        z_core = ZoneDefinition.from_zone_epbunch(zone_core, construct_parents=False)
        z_perim = ZoneDefinition.from_zone_epbunch(zone_perim, construct_parents=False)
        volume = z_core.volume + z_perim.volume  # save volume before changing
        area = z_core.area + z_perim.area  # save area before changing

        id_ = z_core.id
        z_core += z_perim

        assert z_core
        assert z_core.id == id_
        assert z_core.id != z_perim.id

        np.testing.assert_almost_equal(actual=volume, desired=z_core.volume, decimal=3)

        np.testing.assert_almost_equal(actual=area, desired=z_core.area, decimal=3)

    def test_hash_eq_zone(self, small_idf, small_idf_copy):
        """Test equality and hashing of :class:`ZoneLoad`."""
        from copy import copy

        from archetypal.template import ZoneDefinition

        idf = small_idf
        zone_ep = idf.idfobjects["ZONE"][0]
        zone = ZoneDefinition.from_zone_epbunch(zone_ep)
        zone_2 = copy(zone)

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
        idf_2 = small_idf_copy
        zone_ep_3 = idf_2.idfobjects["ZONE"][0]
        zone_3 = ZoneDefinition.from_zone_epbunch(zone_ep_3, DataSource="OtherIDF")
        assert idf is not idf_2
        assert zone_ep is not zone_ep_3
        assert zone_ep != zone_ep_3
        assert hash(zone) != hash(zone_3)
        assert id(zone) != id(zone_3)
        assert zone is not zone_3
        assert zone == zone_3


@pytest.fixture(scope="session")
def bt(config):
    """A building template fixture used in subsequent tests"""
    from archetypal.template import BuildingTemplate

    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = IDF.from_example_files("5ZoneCostEst.idf", epw=w, annual=True)
    if idf.sim_info is None:
        idf.simulate()

    bt = BuildingTemplate.from_idf(idf)
    yield bt


class TestBuildingTemplate:
    """Various tests with the :class:`BuildingTemplate` class"""

    def test_buildingTemplate_from_to_json(self, config):
        from archetypal import UmiTemplateLibrary

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"

        b = UmiTemplateLibrary.open(filename)
        bt = b.BuildingTemplates
        bt_to_json = bt[0].to_json()
        w_to_json = bt[0].Windows.to_json()

    def test_hash_eq_bt(self, config, other_idf_object, other_idf_object_copy):
        """Test equality and hashing of class BuildingTemplate"""
        from archetypal.template import BuildingTemplate

        idf = other_idf_object
        bt = BuildingTemplate.from_idf(idf)
        idf2 = other_idf_object_copy
        bt_2 = BuildingTemplate.from_idf(idf2)

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

    def test_building_template(self, bt):
        """
        Args:
            bt:
        """
        assert bt


class TestZoneGraph:
    """Series of tests for the :class:`ZoneGraph` class"""

    def test_traverse_graph(self, small_office):
        """
        Args:
            small_office:
        """

        idf = small_office

        G = ZoneGraph.from_idf(idf, log_adj_report=False)

        assert G

    @pytest.fixture(scope="module")
    def G(self, config, small_office):
        """
        Args:
            config:
            small_office:
        """

        idf = small_office
        yield ZoneGraph.from_idf(idf)

    @pytest.mark.parametrize("adj_report", [True, False])
    def test_graph(self, small_office, adj_report):
        """Test the creation of a BuildingTemplate zone graph. Parametrize the
        creation of the adjacency report

        Args:
            small_office:
            adj_report:
        """
        import networkx as nx

        idf = small_office

        G1 = ZoneGraph.from_idf(idf, log_adj_report=adj_report)
        assert not nx.is_empty(G1)
        from eppy.bunch_subclass import EpBunch

        assert isinstance(
            G1.nodes["Sp-Attic Sys-0 Flr-2 Sch-- undefined - HPlcmt-core ZN"][
                "epbunch"
            ],
            EpBunch,
        )

    def test_graph_info(self, G):
        """test the info method on a ZoneGraph

        Args:
            G:
        """
        G.info()

    def test_viewgraph2d(self, G):
        """test the visualization of the zonegraph in 2d

        Args:
            G:
        """
        import networkx as nx

        G.plot_graph2d(
            nx.layout.circular_layout,
            (1),
            font_color="w",
            legend=True,
            font_size=8,
            color_nodes="core",
            node_labels_to_integers=True,
            plt_style="seaborn",
            save=False,
            show=False,
            filename="test",
        )

    @pytest.mark.parametrize("annotate", [True, "Name", ("core", None)])
    def test_viewgraph3d(self, G, annotate):
        """test the visualization of the zonegraph in 3d

        Args:
            G:
            annotate:
        """
        G.plot_graph3d(
            annotate=annotate,
            axis_off=True,
            save=False,
            show=False,
        )

    def test_core_graph(self, G):
        """
        Args:
            G:
        """
        H = G.core_graph

        assert len(H) == 1  # assert G has no nodes since Warehouse does not have a
        # core zone

    def test_perim_graph(self, G):
        """
        Args:
            G:
        """
        H = G.perim_graph

        assert len(H) > 0  # assert G has at least one node


class TestUniqueName(object):
    def test_uniquename(self):
        name1 = UniqueName("myname")
        name2 = UniqueName("myname")
        name3 = UniqueName("myname")

        assert name1 != name2 != name3
        print([name1, name2, name3])
