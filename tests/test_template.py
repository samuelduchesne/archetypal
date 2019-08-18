from copy import deepcopy

import numpy as np
import pytest
from path import Path

import archetypal as ar
from archetypal import get_eplus_dire, clear_cache


@pytest.fixture(scope="session")
def small_idf(config):
    file = "tests/input_data/umi_samples/B_Off_0.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = ar.load_idf(file)
    sql: dict = ar.run_eplus(
        file,
        weather_file=w,
        output_report="sql",
        prep_outputs=True,
        annual=False,
        design_day=False,
        verbose="v",
    )
    yield idf, sql


@pytest.fixture(scope="session")
def other_idf(config):
    file = "tests/input_data/umi_samples/B_Res_0_Masonry.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = ar.load_idf(file)
    sql = ar.run_eplus(
        file,
        weather_file=w,
        output_report="sql",
        prep_outputs=True,
        annual=False,
        design_day=False,
        verbose="v",
    )
    yield idf, sql


@pytest.fixture(scope="session")
def small_office(config):
    file = "tests/input_data/necb/NECB 2011-SmallOffice-NECB HDD Method-CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = ar.load_idf(file)
    sql = ar.run_eplus(
        file,
        weather_file=w,
        output_report="sql",
        prep_outputs=True,
        expandobjects=True,
        verbose="v",
    )
    yield idf, sql


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


class TestYearScheduleParts:
    """Series of tests for the :class:`YearScheduleParts` class"""

    # todo: Implement tests for YearScheduleParts class
    pass


class TestDaySchedule:
    """Series of tests for the :class:`DaySchedule` class"""

    # todo: Implement tests for DaySchedule class

    def test_from_epbunch(self, small_idf):
        """test the `from_epbunch` constructor"""
        from archetypal import DaySchedule

        idf, sql = small_idf
        epbunch = idf.getobject("Schedule:Day:Hourly".upper(), "B_Off_D_Het_WD")
        sched = DaySchedule.from_epbunch(epbunch)
        assert len(sched.all_values) == 24.0
        assert repr(sched)

    def test_from_values(self):
        """test the `from_epbunch` constructor"""
        from archetypal import DaySchedule

        values = np.array(range(0, 24))
        kwargs = {
            "$id": "66",
            "Category": "Day",
            "schTypeLimitsName": "Fraction",
            "Comments": "default",
            "DataSource": "default",
            "Name": "hourlyAllOn",
        }
        sched = DaySchedule.from_values(values, **kwargs)
        assert len(sched.all_values) == 24.0
        assert repr(sched)

    def test_daySchedule_from_to_json(self, config):
        import json
        from archetypal import load_json_objects

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        daySched_to_json = loading_json_list[6][0].to_json()


class TestWeekSchedule:
    """Series of tests for the :class:`WeekSchedule` class"""

    # todo: Implement tests for WeekSchedule class

    def test_weekSchedule_from_to_json(self, config):
        import json
        from archetypal import WeekSchedule, load_json_objects

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        weekSched_json = [
            WeekSchedule.from_json(**store) for store in datastore["WeekSchedules"]
        ]
        weekSched_to_json = weekSched_json[0].to_json()


class TestYearSchedule:
    """Series of tests for the :class:`YearSchedule` class"""

    # todo: Implement tests for YearSchedule class

    def test_yearSchedule_from_to_json(self, config):
        import json
        from archetypal import YearSchedule, load_json_objects

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        yearSched_json = [
            YearSchedule.from_json(**store) for store in datastore["YearSchedules"]
        ]
        yearSched_to_json = yearSched_json[0].to_json()


class TestWindowType:
    """Series of tests for the :class:`YearScheduleParts` class"""

    # todo: Implement tests for WindowType class

    pass


class TestOpaqueMaterial:
    """Series of tests for the :class:`OpaqueMaterial` class"""

    def test_add_materials(self):
        """test __add__() for OpaqueMaterial"""
        mat_a = ar.OpaqueMaterial(Conductivity=100, SpecificHeat=4.18, Name="mat_a")
        mat_b = ar.OpaqueMaterial(Conductivity=200, SpecificHeat=4.18, Name="mat_b")
        mat_c = mat_a + mat_b
        assert mat_c
        assert mat_c.Conductivity == 150
        assert mat_a.id != mat_b.id != mat_c.id

        mat_d = mat_c + mat_a
        print(mat_c)
        print(mat_d)

    def test_iadd_materials(self):
        """test __iadd__() for OpaqueMaterial"""
        mat_a = ar.OpaqueMaterial(Conductivity=100, SpecificHeat=4.18, Name="mat_ia")
        id_ = mat_a.id  # storing mat_a's id.

        mat_b = ar.OpaqueMaterial(Conductivity=200, SpecificHeat=4.18, Name="mat_ib")
        mat_a += mat_b
        assert mat_a
        assert mat_a.Conductivity == 150
        assert mat_a.id == id_  # id should not change
        assert mat_a.id != mat_b.id

    def test_opaqueMaterial_from_to_json(config, small_idf):
        from archetypal import OpaqueMaterial

        idf, sql = small_idf
        if idf.idfobjects["MATERIAL"]:
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(idf.idfobjects["MATERIAL"][0])
            opaqMat_epBunch.to_json()
        if idf.idfobjects["MATERIAL:NOMASS"]:
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(
                idf.idfobjects["MATERIAL:NOMASS"][0]
            )
            opaqMat_epBunch.to_json()
        if idf.idfobjects["MATERIAL:AIRGAP"]:
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(
                idf.idfobjects["MATERIAL:AIRGAP"][0]
            )
            opaqMat_epBunch.to_json()

    def test_hash_eq_opaq_mat(self, small_idf, other_idf):
        """Test equality and hashing of :class:`TestOpaqueMaterial`"""
        from archetypal.template import OpaqueMaterial
        from copy import copy

        idf, sql = small_idf
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
        # equal and have the same hash.
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

        # 2 OpaqueMaterial from different idf should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same characteristics (Thickness, Roughness, etc.)
        idf_2, sql_2 = other_idf
        assert idf is not idf_2
        opaq_mat_3 = idf_2.getobject("MATERIAL", "B_Gypsum_Plaster_0.02_B_Res_Thm_0")
        assert opaq_mat is not opaq_mat_3
        assert opaq_mat != opaq_mat_3
        om_3 = OpaqueMaterial.from_epbunch(opaq_mat_3)
        assert hash(om) != hash(om_3)
        assert id(om) != id(om_3)
        assert om is not om_3
        assert om == om_3


class TestGlazingMaterial:
    """Series of tests for the :class:`GlazingMaterial` class"""

    def test_add_glazing_material(self):
        """test __add__() for OpaqueMaterial"""
        sg_a = ar.calc_simple_glazing(0.763, 2.716, 0.812)
        sg_b = ar.calc_simple_glazing(0.578, 2.413, 0.706)
        mat_a = ar.GlazingMaterial(Name="mat_a", **sg_a)
        mat_b = ar.GlazingMaterial(Name="mat_b", **sg_b)

        mat_c = mat_a + mat_b

        assert mat_c
        assert mat_a.id != mat_b.id != mat_c.id

    def test_iadd_glazing_material(self):
        """test __iadd__() for OpaqueMaterial"""
        sg_a = ar.calc_simple_glazing(0.763, 2.716, 0.812)
        sg_b = ar.calc_simple_glazing(0.578, 2.413, 0.706)
        mat_a = ar.GlazingMaterial(Name="mat_ia", **sg_a)
        mat_b = ar.GlazingMaterial(Name="mat_ib", **sg_b)

        id_ = mat_a.id  # storing mat_a's id.

        mat_a += mat_b

        assert mat_a
        assert mat_a.id == id_  # id should not change
        assert mat_a.id != mat_b.id

    # todo: Implement from_to_json test for GlazingMaterial class

    def test_hash_eq_glaz_mat(self, config):
        """Test equality and hashing of :class:`OpaqueConstruction`"""
        from copy import copy

        sg_a = ar.calc_simple_glazing(0.763, 2.716, 0.812)
        mat_a = ar.GlazingMaterial(Name="mat_ia", **sg_a)
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
        # equal and have the same hash.
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

    # todo: Implement tests for GasMaterial class

    def test_GasMaterial_from_to_json(self, config):
        import json
        from archetypal import GasMaterial

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        gasMat_json = [
            GasMaterial.from_json(**store) for store in datastore["GasMaterials"]
        ]
        gasMat_to_json = gasMat_json[0].to_json()
        assert gasMat_json[0].Name == gasMat_to_json["Name"]

    def test_hash_eq_gas_mat(self, config):
        """Test equality and hashing of :class:`OpaqueConstruction`"""
        from archetypal.template import GasMaterial
        from copy import copy
        import json

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        gasMat_json = [
            GasMaterial.from_json(**store) for store in datastore["GasMaterials"]
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
        # equal and have the same hash.
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
    def mat_a(self):
        """A :class:Material fixture"""
        mat_a = ar.OpaqueMaterial(
            Conductivity=1.4, SpecificHeat=840, Density=2240, Name="Concrete"
        )
        yield mat_a

    @pytest.fixture()
    def mat_b(self):
        """A :class:Material fixture"""
        mat_b = ar.OpaqueMaterial(
            Conductivity=0.12, SpecificHeat=1210, Density=540, Name="Plywood"
        )

        yield mat_b

    @pytest.fixture()
    def construction_a(self, mat_a, mat_b):
        """A :class:Construction fixture"""
        thickness = 0.10
        layers = [
            ar.MaterialLayer(mat_a, thickness),
            ar.MaterialLayer(mat_b, thickness),
        ]
        oc_a = ar.OpaqueConstruction(Layers=layers, Name="oc_a")

        yield oc_a

    @pytest.fixture()
    def construction_b(self, mat_a):
        """A :class:Construction fixture"""
        thickness = 0.30
        layers = [ar.MaterialLayer(mat_a, thickness)]
        oc_b = ar.OpaqueConstruction(Layers=layers, Name="oc_b")

        yield oc_b

    def test_thermal_properties(self, construction_a):
        """test r_value and u_value properties"""
        assert 1 / construction_a.r_value == construction_a.u_value

    def test_add_opaque_construction(self, construction_a, construction_b):
        """Test __add__() for OpaqueConstruction"""
        oc_c = construction_a + construction_b
        assert oc_c
        desired = np.average(
            [construction_a.u_value, construction_b.u_value],
            weights=[construction_a.total_thickness, construction_b.total_thickness],
        )
        actual = oc_c.u_value
        np.testing.assert_almost_equal(actual, desired, decimal=3)

    def test_iadd_opaque_construction(self, construction_a, construction_b):
        """Test __iadd__() for OpaqueConstruction"""
        id_ = construction_a.id
        construction_a += construction_b

        assert construction_a
        assert construction_a.id == id_  # id should not change
        assert construction_a.id != construction_b.id

    def test_opaqueConstruction_from_to_json(config):
        import json
        from archetypal import (
            OpaqueConstruction,
            OpaqueMaterial,
            MaterialLayer,
            load_json_objects,
        )

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        mat_a = OpaqueMaterial(Conductivity=100, SpecificHeat=4.18, Name="mat_a")
        mat_b = OpaqueMaterial(Conductivity=200, SpecificHeat=4.18, Name="mat_b")
        thickness = 0.10
        layers = [MaterialLayer(mat_a, thickness), MaterialLayer(mat_b, thickness)]
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        opaqConstr_json = [
            OpaqueConstruction.from_json(**store)
            for store in datastore["OpaqueConstructions"]
        ]
        opaqConstr_to_json = opaqConstr_json[0].to_json()

    def test_hash_eq_opaq_constr(self, small_idf, other_idf):
        """Test equality and hashing of :class:`OpaqueConstruction`"""
        from archetypal.template import OpaqueConstruction
        from copy import copy

        idf, sql = small_idf
        clear_cache()
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
        # equal and have the same hash.
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
        oc_2.IsAdiabatic = True
        assert oc != oc_2

        # length of set() should be 2 since both objects are not equal anymore and
        # don't have the same hash.
        assert len(set(oc_list)) == 2

        # 2 OpaqueConstruction from different idf should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same layers (Material and Thickness)
        idf_2, sql_2 = other_idf
        assert idf is not idf_2
        opaq_constr_3 = idf_2.getobject("CONSTRUCTION", "B_Res_Thm_0")
        assert opaq_constr is not opaq_constr_3
        assert opaq_constr != opaq_constr_3
        oc_3 = OpaqueConstruction.from_epbunch(opaq_constr_3)
        assert hash(oc) != hash(oc_3)
        assert id(oc) != id(oc_3)
        assert oc is not oc_3
        assert oc == oc_3


class TestWindowConstruction:
    """Series of tests for the :class:`WindowConstruction` class"""

    # todo: Implement from_to_json for WindowConstruction class

    def test_windowConstr_from_to_json(config):
        import json
        from archetypal import WindowConstruction, load_json_objects

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        winConstr_json = [
            WindowConstruction.from_json(**store)
            for store in datastore["WindowConstructions"]
        ]
        winConstr_to_json = winConstr_json[0].to_json()


class TestStructureDefinition:
    """Series of tests for the :class:`StructureDefinition` class"""

    # todo: Implement from_to_json for StructureDefinition class

    def test_structure_from_to_json(config):
        import json
        from archetypal import StructureDefinition, load_json_objects

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        struct_json = [
            StructureDefinition.from_json(**store)
            for store in datastore["StructureDefinitions"]
        ]
        struct_to_json = struct_json[0].to_json()

    def test_hash_eq_struc_def(self, config):
        """Test equality and hashing of :class:`OpaqueConstruction`"""
        from archetypal import StructureDefinition, load_json_objects
        from copy import copy
        import json

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        struct_json = [
            StructureDefinition.from_json(**store)
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
        # equal and have the same hash.
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
    """Tests for :class:`UmiSchedule` class """

    # todo: Implement from_to_json for UmiSchedule class

    def test_constant_umischedule(self, config):
        from archetypal import UmiSchedule

        const = UmiSchedule.constant_schedule()
        assert const.__class__.__name__ == "UmiSchedule"
        assert const.Name == "AlwaysOn"

    def test_schedule_develop(self, config, small_idf):
        from archetypal import UmiSchedule

        idf, sql = small_idf
        clear_cache()
        sched = UmiSchedule(Name="B_Off_Y_Occ", idf=idf)
        assert sched.to_dict()

    def test_hash_eq_umi_sched(self, small_idf, other_idf):
        """Test equality and hashing of :class:`ZoneLoad`"""
        from archetypal.template import UmiSchedule
        from copy import copy

        idf, sql = small_idf
        clear_cache()
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
        # equal and have the same hash.
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

        # 2 UmiSchedule from different idf should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same values
        idf_2, sql_2 = other_idf
        clear_cache()
        assert idf is not idf_2
        sched_3 = UmiSchedule(Name="On", idf=idf_2)
        assert sched is not sched_3
        assert sched == sched_3
        assert hash(sched) == hash(sched_3)
        assert id(sched) != id(sched_3)


class TestZoneConstructionSet:
    """Combines different :class:`ZoneConstructionSet` tests"""

    @pytest.fixture(params=["RefBldgWarehouseNew2004_Chicago.idf"])
    def zoneConstructionSet_tests(self, config, request):
        from eppy.runner.run_functions import install_paths

        eplus_exe, eplus_weather = install_paths("8-9-0")
        eplusdir = Path(eplus_exe).dirname()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        sql, idf = ar.run_eplus(
            file,
            weather_file=w,
            output_report="sql",
            prep_outputs=True,
            annual=False,
            design_day=False,
            verbose="v",
            return_idf=True,
        )
        yield idf, sql

    def test_add_zoneconstructionset(self, small_idf):
        """Test __add__() for ZoneConstructionSet"""
        idf, sql = small_idf
        zone_core = idf.getobject("ZONE", core_name)
        zone_perim = idf.getobject("ZONE", perim_name)

        z_core = ar.ZoneConstructionSet.from_zone(
            ar.Zone.from_zone_epbunch(zone_core, sql=sql)
        )
        z_perim = ar.ZoneConstructionSet.from_zone(
            ar.Zone.from_zone_epbunch(zone_perim, sql=sql)
        )
        z_new = z_core + z_perim
        assert z_new

    def test_iadd_zoneconstructionset(self, small_idf):
        """Test __iadd__() for ZoneConstructionSet"""
        idf, sql = small_idf
        zone_core = idf.getobject("ZONE", core_name)
        zone_perim = idf.getobject("ZONE", perim_name)

        z_core = ar.ZoneConstructionSet.from_zone(
            ar.Zone.from_zone_epbunch(zone_core, sql=sql)
        )
        z_perim = ar.ZoneConstructionSet.from_zone(
            ar.Zone.from_zone_epbunch(zone_perim, sql=sql)
        )
        id_ = z_core.id
        z_core += z_perim

        assert z_core
        assert z_core.id == id_  # id should not change
        assert z_core.id != z_perim.id

    def test_zoneConstructionSet_init(self, config):
        from archetypal import ZoneConstructionSet

        constrSet = ZoneConstructionSet(Name=None)

    def test_zoneConstructionSet_from_zone(self, config, zoneConstructionSet_tests):
        from archetypal import ZoneConstructionSet, Zone

        idf, sql = zoneConstructionSet_tests
        zone = idf.getobject("ZONE", "Office")
        z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
        constrSet_ = ZoneConstructionSet.from_zone(z)

    def test_zoneConstructionSet_from_to_json(self, config):
        import json
        from archetypal import ZoneConstructionSet, load_json_objects

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        constr_json = [
            ZoneConstructionSet.from_json(**store)
            for store in datastore["ZoneConstructionSets"]
        ]
        constr_to_json = constr_json[0].to_json()


class TestZoneLoad:
    """Combines different :class:`ZoneLoad` tests"""

    @pytest.fixture(scope="class", params=["RefBldgWarehouseNew2004_Chicago.idf"])
    def zoneLoadtests(self, config, request):
        from eppy.runner.run_functions import install_paths

        eplus_exe, eplus_weather = install_paths("8-9-0")
        eplusdir = Path(eplus_exe).dirname()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(
            file,
            weather_file=w,
            output_report="sql",
            prep_outputs=True,
            annual=False,
            design_day=False,
            verbose="v",
        )
        yield idf, sql

    def test_zoneLoad_init(self, config):
        from archetypal import ZoneLoad

        load = ZoneLoad(Name=None)

    def test_zoneLoad_from_zone(self, config, zoneLoadtests):
        from archetypal import ZoneLoad, Zone

        idf, sql = zoneLoadtests
        zone = idf.getobject("ZONE", "Office")
        z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
        load_ = ZoneLoad.from_zone(z)

    def test_zoneLoad_from_to_json(self, config):
        import json
        from archetypal import ZoneLoad, load_json_objects

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        load_json = [ZoneLoad.from_json(**store) for store in datastore["ZoneLoads"]]
        load_to_json = load_json[0].to_json()

    def test_hash_eq_zone_load(self, small_idf):
        """Test equality and hashing of :class:`ZoneLoad`"""
        from archetypal.template import ZoneLoad, Zone
        from copy import copy

        idf, sql = small_idf
        clear_cache()
        zone_ep = idf.idfobjects["ZONE"][0]
        zone = Zone.from_zone_epbunch(zone_ep, sql=sql)
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
        # equal and have the same hash.
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

        # 2 ZoneLoad from different idf should not have the same hash if they
        # have different names, not be the same object, yet be equal if they have the
        # same values (EquipmentPowerDensity, LightingPowerDensity, etc.)
        idf_2 = deepcopy(idf)
        clear_cache()
        zone_ep_3 = idf_2.idfobjects["ZONE"][0]
        zone_3 = Zone.from_zone_epbunch(zone_ep_3, sql=sql)
        assert idf is not idf_2
        zl_3 = ZoneLoad.from_zone(zone_3)
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
            "2ZoneDataCenterHVAC_wEconomizer.idf",
        ],
    )
    def zoneConditioningtests(self, config, request):
        from eppy.runner.run_functions import install_paths

        eplus_exe, eplus_weather = install_paths("8-9-0")
        eplusdir = Path(eplus_exe).dirname()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(
            file,
            weather_file=w,
            output_report="sql",
            prep_outputs=True,
            annual=False,
            design_day=False,
            verbose="v",
        )
        yield idf, sql, request.param

    def test_zoneConditioning_init(self, config):
        from archetypal import ZoneConditioning

        cond = ZoneConditioning(Name=None)
        assert cond.Name == None

    def test_zoneConditioning_from_zone(self, config, zoneConditioningtests):
        from archetypal import ZoneConditioning, Zone

        idf, sql, idf_name = zoneConditioningtests
        if idf_name == "RefMedOffVAVAllDefVRP.idf":
            zone = idf.getobject("ZONE", "Core_mid")
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            cond_ = ZoneConditioning.from_zone(z)
        if idf_name == "AirflowNetwork_MultiZone_SmallOffice_HeatRecoveryHXSL" ".idf":
            zone = idf.getobject("ZONE", "West Zone")
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            cond_HX = ZoneConditioning.from_zone(z)
        if (
            idf_name == "2ZoneDataCenterHVAC_wEconomizer.idf"
            or idf_name == "AirflowNetwork_MultiZone_SmallOffice_CoilHXAssistedDX.idf"
        ):
            zone = idf.getobject("ZONE", "East Zone")
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            cond_HX_eco = ZoneConditioning.from_zone(z)

    def test_zoneConditioning_from_to_json(self, config):
        import json
        from archetypal import ZoneConditioning, load_json_objects

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        cond_json = [
            ZoneConditioning.from_json(**store)
            for store in datastore["ZoneConditionings"]
        ]
        cond_to_json = cond_json[0].to_json()

    def test_hash_eq_zone_cond(self, small_idf):
        """Test equality and hashing of :class:`ZoneConditioning`"""
        from archetypal.template import ZoneConditioning, Zone
        from copy import copy

        idf, sql = small_idf
        clear_cache()
        zone_ep = idf.idfobjects["ZONE"][0]
        zone = Zone.from_zone_epbunch(zone_ep, sql=sql)
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
        # equal and have the same hash.
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
        idf_2 = deepcopy(idf)
        clear_cache()
        zone_ep_3 = idf_2.idfobjects["ZONE"][0]
        zone_3 = Zone.from_zone_epbunch(zone_ep_3, sql=sql)
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
        from eppy.runner.run_functions import install_paths

        eplus_exe, eplus_weather = install_paths("8-9-0")
        eplusdir = Path(eplus_exe).dirname()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(
            file,
            weather_file=w,
            output_report="sql",
            prep_outputs=True,
            annual=False,
            design_day=False,
            verbose="v",
        )
        yield idf, sql, request.param

    def test_ventilation_init(self, config):
        from archetypal import VentilationSetting

        vent = VentilationSetting(Name=None)

    def test_naturalVentilation_from_zone(self, config, ventilatontests):
        from archetypal import VentilationSetting, Zone

        idf, sql, idf_name = ventilatontests
        if idf_name == "VentilationSimpleTest.idf":
            zone = idf.getobject("ZONE", "ZONE 1")
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            natVent = VentilationSetting.from_zone(z)
        if idf_name == "VentilationSimpleTest.idf":
            zone = idf.getobject("ZONE", "ZONE 2")
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            schedVent = VentilationSetting.from_zone(z)
        if idf_name == "RefBldgWarehouseNew2004_Chicago.idf":
            zone = idf.getobject("ZONE", "Office")
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            infiltVent = VentilationSetting.from_zone(z)

    def test_ventilationSetting_from_to_json(self, config):
        import json
        from archetypal import VentilationSetting, load_json_objects

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        with open(filename, "r") as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        vent_json = [
            VentilationSetting.from_json(**store)
            for store in datastore["VentilationSettings"]
        ]
        vent_to_json = vent_json[0].to_json()

    def test_hash_eq_vent_settings(self, small_idf):
        """Test equality and hashing of :class:`DomesticHotWaterSetting`"""
        from archetypal.template import VentilationSetting, Zone
        from copy import copy

        idf, sql = small_idf
        clear_cache()
        zone_ep = idf.idfobjects["ZONE"][0]
        zone = Zone.from_zone_epbunch(zone_ep, sql=sql)
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
        # equal and have the same hash.
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
        # have different names, not be the same object, yet be equal if they have the
        # same values (Infiltration, IsWindOn, etc.)
        idf_2 = deepcopy(idf)
        clear_cache()
        zone_ep_3 = idf_2.idfobjects["ZONE"][0]
        zone_3 = Zone.from_zone_epbunch(zone_ep_3, sql=sql)
        assert idf is not idf_2
        vent_3 = VentilationSetting.from_zone(zone_3)
        assert zone_ep is not zone_ep_3
        assert zone_ep != zone_ep_3
        assert hash(vent) == hash(vent_3)
        assert id(vent) != id(vent_3)
        assert vent is not vent_3
        assert vent == vent_3


class TestDomesticHotWaterSetting:
    """Series of tests for the :class:`DomesticHotWaterSetting` class"""

    def test_hash_eq_dhw(self, small_idf):
        """Test equality and hashing of :class:`DomesticHotWaterSetting`"""
        from archetypal.template import DomesticHotWaterSetting, Zone
        from copy import copy

        idf, sql = small_idf
        clear_cache()
        zone_ep = idf.idfobjects["ZONE"][0]
        zone = Zone.from_zone_epbunch(zone_ep, sql=sql)
        dhw = DomesticHotWaterSetting.from_zone(zone)
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
        # equal and have the same hash.
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

        # 2 DomesticHotWaterSettings from different idf should not have the same hash
        # if they have different names, not be the same object, yet be equal if they
        # have the same values (Infiltration, IsWindOn, etc.)
        idf_2 = deepcopy(idf)
        clear_cache()
        zone_ep_3 = idf_2.idfobjects["ZONE"][0]
        zone_3 = Zone.from_zone_epbunch(zone_ep_3, sql=sql)
        assert idf is not idf_2
        dhw_3 = DomesticHotWaterSetting.from_zone(zone_3)
        assert zone_ep is not zone_ep_3
        assert zone_ep != zone_ep_3
        assert hash(dhw) == hash(dhw_3)
        assert id(dhw) != id(dhw_3)
        assert dhw is not dhw_3
        assert dhw == dhw_3


class TestWindowSetting:
    """Combines different :class:`WindowSetting` tests"""

    @pytest.fixture(
        scope="class", params=["WindowTests.idf", "AirflowNetwork3zVent.idf"]
    )
    def windowtests(self, config, request):
        eplusdir = get_eplus_dire()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(
            file,
            weather_file=w,
            output_report="sql",
            prep_outputs=True,
            annual=False,
            design_day=False,
            verbose="v",
        )
        yield idf, sql

    def test_window_from_construction_name(self, small_idf):
        from archetypal import WindowSetting

        idf, sql = small_idf
        construction = idf.getobject("CONSTRUCTION", "B_Dbl_Air_Cl")
        clear_cache()
        w = WindowSetting.from_construction(construction)

        assert w.to_json()

    @pytest.fixture(scope="class")
    def allwindowtypes(self, config, windowtests):
        from archetypal import WindowSetting

        idf, sql = windowtests
        f_surfs = idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]
        windows = []
        for f in f_surfs:
            windows.append(WindowSetting.from_surface(f))
        yield windows

    def test_allwindowtype(self, allwindowtypes):
        assert allwindowtypes

    def test_window_fromsurface(self, config, small_idf):
        from archetypal import WindowSetting

        idf, sql = small_idf
        f_surfs = idf.idfobjects["FENESTRATIONSURFACE:DETAILED"]
        for f in f_surfs:
            constr = f.Construction_Name
            idf.add_object(
                "WindowMaterial:Shade".upper(),
                Visible_Transmittance=0.5,
                Name="Roll Shade",
                save=False,
            )
            idf.add_object(
                "WINDOWPROPERTY:SHADINGCONTROL",
                Construction_with_Shading_Name=constr,
                Setpoint=14,
                Shading_Device_Material_Name="Roll Shade",
                save=False,
                Name="test_constrol",
            )
            f.Shading_Control_Name = "test_constrol"
            w = WindowSetting.from_surface(f)
            assert w
            print(w)

    def test_winow_add2(self, allwindowtypes):
        from operator import add
        from functools import reduce

        window = reduce(add, allwindowtypes)
        print(window)

    def test_window_add(self, small_idf):
        from archetypal import WindowSetting

        idf, sql = small_idf
        zone = idf.idfobjects["ZONE"][0]
        iterator = iter(zone.zonesurfaces)
        surface = next(iterator, None)
        window_1 = WindowSetting.from_surface(surface)
        surface = next(iterator, None)
        window_2 = WindowSetting.from_surface(surface)

        new_w = window_1 + window_2
        assert new_w
        assert window_1.id != window_2.id != new_w.id

    def test_window_iadd(self, small_idf):
        from archetypal import WindowSetting

        idf, sql = small_idf
        zone = idf.idfobjects["ZONE"][0]
        iterator = iter(zone.zonesurfaces)
        surface = next(iterator, None)
        window_1 = WindowSetting.from_surface(surface)
        id_ = window_1.id
        surface = next(iterator, None)
        window_2 = WindowSetting.from_surface(surface)

        window_1 += window_2
        assert window_1
        assert window_1.id == id_  # id should not change
        assert window_1.id != window_2.id

    def test_glazing_material_from_simple_glazing(self, config):
        """test __add__() for OpaqueMaterial"""
        sg_a = ar.calc_simple_glazing(0.763, 2.716, 0.812)
        mat_a = ar.GlazingMaterial(Name="mat_a", **sg_a)
        glazMat_to_json = mat_a.to_json()
        assert glazMat_to_json

    def test_window_generic(self, small_idf):
        from archetypal import WindowSetting

        idf, sql = small_idf
        w = WindowSetting.generic(idf)

        assert w.to_json()

    def test_hash_eq_window_settings(self, small_idf):
        """Test equality and hashing of :class:`DomesticHotWaterSetting`"""
        from archetypal.template import WindowSetting
        from copy import copy

        idf, sql = small_idf
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
        # equal and have the same hash.
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
        idf_2 = deepcopy(idf)
        clear_cache()
        f_surf_3 = idf_2.idfobjects["FENESTRATIONSURFACE:DETAILED"][0]
        wind_3 = WindowSetting.from_surface(f_surf_3)
        assert idf is not idf_2
        assert f_surf is not f_surf_3
        assert f_surf != f_surf_3
        assert hash(wind) == hash(wind_3)
        assert id(wind) != id(wind_3)
        assert wind is not wind_3
        assert wind == wind_3


class TestZone:
    """Tests for :class:`Zone` class"""

    def test_zone_volume(self, config):
        """Test the zone volume for a sloped roof"""
        from archetypal import Zone

        file = "tests/input_data/trnsys/NECB 2011 - Full Service Restaurant.idf"
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(
            file,
            weather_file=w,
            output_report="sql",
            prep_outputs=True,
            annual=False,
            design_day=False,
            verbose="v",
        )
        zone = idf.getobject(
            "ZONE", "Sp-attic Sys-0 Flr-2 Sch-- undefined - " "HPlcmt-core ZN"
        )
        z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
        np.testing.assert_almost_equal(desired=z.volume, actual=856.3, decimal=1)
        z.to_json()

    def test_add_zone(self, small_idf):
        """Test __add__() for Zone"""
        idf, sql = small_idf
        zone_core = idf.getobject("ZONE", core_name)
        zone_perim = idf.getobject("ZONE", perim_name)

        z_core = ar.Zone.from_zone_epbunch(zone_core, sql=sql)
        z_perim = ar.Zone.from_zone_epbunch(zone_perim, sql=sql)

        z_new = z_core + z_perim

        assert z_new
        np.testing.assert_almost_equal(
            actual=z_core.volume + z_perim.volume, desired=z_new.volume, decimal=3
        )
        np.testing.assert_almost_equal(
            actual=z_core.area + z_perim.area, desired=z_new.area, decimal=3
        )

    def test_iadd_zone(self, small_idf):
        """Test __iadd__() for Zone"""
        idf, sql = small_idf
        zone_core = idf.getobject("ZONE", core_name)
        zone_perim = idf.getobject("ZONE", perim_name)

        z_core = ar.Zone.from_zone_epbunch(zone_core, sql=sql)
        z_perim = ar.Zone.from_zone_epbunch(zone_perim, sql=sql)
        volume = z_core.volume + z_perim.volume  # save volume before changing
        area = z_core.area + z_perim.area  # save area before changing

        id_ = z_core.id
        z_core += z_perim

        assert z_core
        assert z_core.id == id_
        assert z_core.id != z_perim.id

        np.testing.assert_almost_equal(actual=volume, desired=z_core.volume, decimal=3)

        np.testing.assert_almost_equal(actual=area, desired=z_core.area, decimal=3)

    def test_hash_eq_zone(self, small_idf):
        """Test equality and hashing of :class:`ZoneLoad`"""
        from archetypal.template import Zone
        from copy import copy

        idf, sql = map(deepcopy, small_idf)
        clear_cache()
        zone_ep = idf.idfobjects["ZONE"][0]
        zone = Zone.from_zone_epbunch(zone_ep, sql=sql)
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
        # equal and have the same hash.
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
        idf_2 = deepcopy(idf)
        clear_cache()
        zone_ep_3 = idf_2.idfobjects["ZONE"][0]
        zone_3 = Zone.from_zone_epbunch(zone_ep_3, sql=sql)
        assert idf is not idf_2
        assert zone_ep is not zone_ep_3
        assert zone_ep != zone_ep_3
        assert hash(zone) != hash(zone_3)
        assert id(zone) != id(zone_3)
        assert zone is not zone_3
        assert zone == zone_3


@pytest.fixture(scope="session")
def bt():
    """A building template fixture used in subsequent tests"""
    eplus_dir = get_eplus_dire()
    file = eplus_dir / "ExampleFiles" / "5ZoneCostEst.idf"
    w = next(iter((eplus_dir / "WeatherData").glob("*.epw")), None)
    file = ar.copy_file(file)
    idf = ar.load_idf(file)
    sql = ar.run_eplus(
        file,
        weather_file=w,
        output_report="sql",
        prep_outputs=True,
        annual=True,
        expandobjects=True,
        verbose="v",
    )
    from archetypal import BuildingTemplate

    bt = BuildingTemplate.from_idf(idf, sql=sql)
    yield bt


class TestBuildingTemplate:
    """Various tests with the :class:`BuildingTemplate` class"""

    def test_viewbuilding(self, config, bt):
        """test the visualization of a building"""
        bt.view_building()

    def test_buildingTemplate_from_to_json(self, config):
        from archetypal import UmiTemplate

        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        clear_cache()
        b = UmiTemplate.from_json(filename)
        bt = b.BuildingTemplates
        bt_to_json = bt[0].to_json()
        w_to_json = bt[0].Windows.to_json()

    def test_hash_eq_bt(self, other_idf):
        """Test equality and hashing of class DomesticHotWaterSetting"""
        from archetypal.template import BuildingTemplate
        from copy import copy

        idf, sql = other_idf
        clear_cache()
        bt = BuildingTemplate.from_idf(idf, sql=sql)
        bt_2 = copy(bt)

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
        # equal and have the same hash.
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


class TestZoneGraph:
    """Series of tests for the :class:`ZoneGraph` class"""

    def test_traverse_graph(self, small_office):
        from archetypal import ZoneGraph

        idf, sql = small_office

        G = ZoneGraph.from_idf(
            idf, sql=sql, log_adj_report=False, skeleton=False, force=True
        )

        assert G

    @pytest.fixture(scope="session")
    def G(self, small_office):
        from archetypal import ZoneGraph

        idf, sql = small_office
        yield ZoneGraph.from_idf(idf, sql, skeleton=True, force=True)

    @pytest.mark.parametrize("adj_report", [True, False])
    def test_graph1(self, small_office, adj_report):
        """Test the creation of a BuildingTemplate zone graph. Parametrize
        the creation of the adjacency report"""
        import networkx as nx
        from archetypal import ZoneGraph

        idf, sql = small_office
        clear_cache()
        G1 = ZoneGraph.from_idf(
            idf, sql, log_adj_report=adj_report, skeleton=True, force=False
        )
        assert not nx.is_empty(G1)

    def test_graph2(self, small_office):
        """Test the creation of a BuildingTemplate zone graph. Parametrize
            the creation of the adjacency report"""
        # calling from_idf a second time should not recalculate it.
        from archetypal import ZoneGraph

        idf, sql = small_office
        G2 = ZoneGraph.from_idf(
            idf, sql, log_adj_report=False, skeleton=True, force=False
        )

    def test_graph3(self, small_office):
        """Test the creation of a BuildingTemplate zone graph. Parametrize
        the creation of the adjacency report"""
        # calling from_idf a second time with force=True should
        # recalculate it and produce a new id.
        from archetypal import ZoneGraph

        idf, sql = small_office
        G3 = ZoneGraph.from_idf(
            idf, sql, log_adj_report=False, skeleton=True, force=True
        )

    def test_graph4(self, small_office):
        """Test the creation of a BuildingTemplate zone graph. Parametrize
            the creation of the adjacency report"""
        # skeleton False should build the zone elements.
        from archetypal import ZoneGraph

        idf, sql = small_office
        G4 = ZoneGraph.from_idf(
            idf, sql, log_adj_report=False, skeleton=False, force=True
        )

        from eppy.bunch_subclass import EpBunch

        assert isinstance(
            G4.nodes["Sp-Attic Sys-0 Flr-2 Sch-- undefined - HPlcmt-core ZN"][
                "epbunch"
            ],
            EpBunch,
        )

    def test_graph_info(self, G):
        """test the info method on a ZoneGraph"""
        G.info()

    def test_viewgraph2d(self, G):
        """test the visualization of the zonegraph in 2d"""
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
            save=True,
            filename="test",
        )

    @pytest.mark.parametrize("annotate", [True, "Name", ("core", None)])
    def test_viewgraph3d(self, config, G, annotate):
        """test the visualization of the zonegraph in 3d"""
        G.plot_graph3d(annotate=annotate, axis_off=True)

    def test_core_graph(self, G):
        H = G.core_graph

        assert len(H) == 2  # assert G has no nodes since Warehouse does not have a
        # core zone

    def test_perim_graph(self, G):
        H = G.perim_graph

        assert len(H) > 0  # assert G has at least one node
