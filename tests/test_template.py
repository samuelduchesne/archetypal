import numpy as np
import pytest
from path import Path

import archetypal as ar
from archetypal import get_eplus_dire


@pytest.fixture(scope='session')
def small_idf(config):
    file = "tests/input_data/umi_samples/B_Off_0.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = ar.load_idf(file)
    sql = ar.run_eplus(file, weather_file=w, prep_outputs=True,
                       output_report='sql', verbose='v', design_day=False,
                       annual=False)
    yield idf, sql


core_name = 'core'
perim_name = 'perim'


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

    def test_daySchedule_from_to_json(self, config):
        import json
        from archetypal import load_json_objects
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        # WeekSchedule(Name='weekSched').clear_cache()
        with open(filename, 'r') as f:
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
        # WeekSchedule(Name='weekSched').clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        weekSched_json = [WeekSchedule.from_json(**store)
                          for store in datastore["WeekSchedules"]]
        weekSched_to_json = weekSched_json[0].to_json()


class TestYearSchedule:
    """Series of tests for the :class:`YearSchedule` class"""

    # todo: Implement tests for YearSchedule class

    def test_yearSchedule_from_to_json(self, config):
        import json
        from archetypal import YearSchedule, load_json_objects
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        # WeekSchedule(Name='weekSched').clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        yearSched_json = [YearSchedule.from_json(**store)
                          for store in datastore["YearSchedules"]]
        yearSched_to_json = yearSched_json[0].to_json()


class TestWindowType:
    """Series of tests for the :class:`YearScheduleParts` class"""

    # todo: Implement tests for WindowType class

    pass


class TestOpaqueMaterial:
    """Series of tests for the :class:`OpaqueMaterial` class"""

    def test_add_materials(self):
        """test __add__() for OpaqueMaterial"""
        mat_a = ar.OpaqueMaterial(Conductivity=100, SpecificHeat=4.18,
                                  Name='mat_a')
        mat_b = ar.OpaqueMaterial(Conductivity=200, SpecificHeat=4.18,
                                  Name='mat_b')
        mat_c = mat_a + mat_b
        assert mat_c
        assert mat_c.Conductivity == 150
        assert mat_a.id != mat_b.id != mat_c.id

        mat_d = mat_c + mat_a
        print(mat_c)
        print(mat_d)

    def test_iadd_materials(self):
        """test __iadd__() for OpaqueMaterial"""
        mat_a = ar.OpaqueMaterial(Conductivity=100, SpecificHeat=4.18,
                                  Name='mat_ia')
        id_ = mat_a.id  # storing mat_a's id.

        mat_b = ar.OpaqueMaterial(Conductivity=200, SpecificHeat=4.18,
                                  Name='mat_ib')
        mat_a += mat_b
        assert mat_a
        assert mat_a.Conductivity == 150
        assert mat_a.id == id_  # id should not change
        assert mat_a.id != mat_b.id

    def test_opaqueMaterial_from_to_json(config, small_idf):
        from archetypal import OpaqueMaterial
        idf, sql = small_idf
        if idf.idfobjects['MATERIAL']:
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(
                idf.idfobjects['MATERIAL'][0])
            opaqMat_epBunch.to_json()
        if idf.idfobjects['MATERIAL:NOMASS']:
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(
                idf.idfobjects['MATERIAL:NOMASS'][0])
            opaqMat_epBunch.to_json()
        if idf.idfobjects['MATERIAL:AIRGAP']:
            opaqMat_epBunch = OpaqueMaterial.from_epbunch(
                idf.idfobjects['MATERIAL:AIRGAP'][0])
            opaqMat_epBunch.to_json()

    # todo: Implement from_to_json test for OpaqueMaterial class


class TestGlazingMaterial:
    """Series of tests for the :class:`GlazingMaterial` class"""

    def test_add_glazing_material(self):
        """test __add__() for OpaqueMaterial"""
        sg_a = ar.calc_simple_glazing(0.763, 2.716, 0.812)
        sg_b = ar.calc_simple_glazing(0.578, 2.413, 0.706)
        mat_a = ar.GlazingMaterial(Name='mat_a', **sg_a)
        mat_b = ar.GlazingMaterial(Name='mat_b', **sg_b)

        mat_c = mat_a + mat_b

        assert mat_c
        assert mat_a.id != mat_b.id != mat_c.id

    def test_iadd_glazing_material(self):
        """test __iadd__() for OpaqueMaterial"""
        sg_a = ar.calc_simple_glazing(0.763, 2.716, 0.812)
        sg_b = ar.calc_simple_glazing(0.578, 2.413, 0.706)
        mat_a = ar.GlazingMaterial(Name='mat_ia', **sg_a)
        mat_b = ar.GlazingMaterial(Name='mat_ib', **sg_b)

        id_ = mat_a.id  # storing mat_a's id.

        mat_a += mat_b

        assert mat_a
        assert mat_a.id == id_  # id should not change
        assert mat_a.id != mat_b.id

    # todo: Implement from_to_json test for GlazingMaterial class


class TestGasMaterial:
    """Series of tests for the GasMaterial class"""

    # todo: Implement tests for GasMaterial class

    def test_GasMaterial_from_to_json(self, config):
        import json
        from archetypal import GasMaterial
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        GasMaterial(Name='GasMat').clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        gasMat_json = [GasMaterial.from_json(**store)
                       for store in datastore["GasMaterials"]]
        gasMat_to_json = gasMat_json[0].to_json()
        assert gasMat_json[0].Name == gasMat_to_json['Name']


class TestOpaqueConstruction:
    """Series of tests for the :class:`OpaqueConstruction` class"""

    @pytest.fixture()
    def mat_a(self):
        """A :class:Material fixture"""
        mat_a = ar.OpaqueMaterial(Conductivity=1.4, SpecificHeat=840,
                                  Density=2240,
                                  Name='Concrete')
        yield mat_a

    @pytest.fixture()
    def mat_b(self):
        """A :class:Material fixture"""
        mat_b = ar.OpaqueMaterial(Conductivity=0.12, SpecificHeat=1210,
                                  Density=540,
                                  Name='Plywood')

        yield mat_b

    @pytest.fixture()
    def construction_a(self, mat_a, mat_b):
        """A :class:Construction fixture"""
        thickness = 0.10
        layers = [ar.MaterialLayer(mat_a, thickness),
                  ar.MaterialLayer(mat_b, thickness)]
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
        desired = (construction_a.u_value + construction_b.u_value) * 0.5
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
        from archetypal import OpaqueConstruction, OpaqueMaterial, \
            MaterialLayer, \
            load_json_objects
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        mat_a = OpaqueMaterial(Conductivity=100, SpecificHeat=4.18,
                               Name='mat_a')
        mat_b = OpaqueMaterial(Conductivity=200, SpecificHeat=4.18,
                               Name='mat_b')
        thickness = 0.10
        layers = [MaterialLayer(mat_a, thickness),
                  MaterialLayer(mat_b, thickness)]
        OpaqueConstruction(Name='Name', Layers=layers).clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        opaqConstr_json = [OpaqueConstruction.from_json(**store)
                           for store in datastore["OpaqueConstructions"]]
        opaqConstr_to_json = opaqConstr_json[0].to_json()


class TestWindowConstruction:
    """Series of tests for the :class:`WindowConstruction` class"""

    # todo: Implement from_to_json for WindowConstruction class

    def test_windowConstr_from_to_json(config):
        import json
        from archetypal import WindowConstruction, load_json_objects
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        WindowConstruction(Name='winConstr').clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        winConstr_json = [WindowConstruction.from_json(**store)
                          for store in datastore["WindowConstructions"]]
        winConstr_to_json = winConstr_json[0].to_json()


class TestStructureDefinition:
    """Series of tests for the :class:`StructureDefinition` class"""

    # todo: Implement from_to_json for StructureDefinition class

    def test_structure_from_to_json(config):
        import json
        from archetypal import StructureDefinition, load_json_objects
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        StructureDefinition(Name='structDef').clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        struct_json = [StructureDefinition.from_json(**store)
                       for store in datastore["StructureDefinitions"]]
        struct_to_json = struct_json[0].to_json()


class TestUmiSchedule:
    """Tests for :class:`UmiSchedule` class """

    # todo: Implement from_to_json for UmiSchedule class

    def test_constant_umischedule(self, config):
        from archetypal import UmiSchedule
        const = UmiSchedule.constant_schedule()
        assert const.__class__.__name__ == 'UmiSchedule'
        assert const.Name == 'AlwaysOn'


class TestZoneConstructionSet:
    """Combines different :class:`ZoneConstructionSet` tests"""

    @pytest.fixture(scope='class',
                    params=["RefBldgWarehouseNew2004_Chicago.idf"])
    def zoneConstructionSet_tests(self, config, request):
        from eppy.runner.run_functions import install_paths
        eplus_exe, eplus_weather = install_paths("8-9-0")
        eplusdir = Path(eplus_exe).dirname()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(file, weather_file=w, prep_outputs=True,
                           output_report='sql', verbose='v', design_day=False,
                           annual=False)
        yield idf, sql

    def test_add_zoneconstructionset(self, small_idf):
        """Test __add__() for ZoneConstructionSet"""
        idf, sql = small_idf
        zone_core = idf.getobject('ZONE', core_name)
        zone_perim = idf.getobject('ZONE', perim_name)

        z_core = ar.ZoneConstructionSet.from_zone(
            ar.Zone.from_zone_epbunch(zone_core, sql=sql))
        z_perim = ar.ZoneConstructionSet.from_zone(
            ar.Zone.from_zone_epbunch(zone_perim, sql=sql))
        z_new = z_core + z_perim
        assert z_new

    def test_iadd_zoneconstructionset(self, small_idf):
        """Test __iadd__() for ZoneConstructionSet"""
        idf, sql = small_idf
        zone_core = idf.getobject('ZONE', core_name)
        zone_perim = idf.getobject('ZONE', perim_name)

        z_core = ar.ZoneConstructionSet.from_zone(
            ar.Zone.from_zone_epbunch(zone_core))
        z_perim = ar.ZoneConstructionSet.from_zone(
            ar.Zone.from_zone_epbunch(zone_perim))
        id_ = z_core.id
        z_core += z_perim

        assert z_core
        assert z_core.id == id_  # id should not change
        assert z_core.id != z_perim.id

    def test_zoneConstructionSet_init(self, config):
        from archetypal import ZoneConstructionSet
        constrSet = ZoneConstructionSet(Name=None)

    def test_zoneConstructionSet_from_zone(self, config,
                                           zoneConstructionSet_tests):
        from archetypal import ZoneConstructionSet, Zone
        idf, sql = zoneConstructionSet_tests
        zone = idf.getobject('ZONE', 'Office')
        z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
        constrSet_ = ZoneConstructionSet.from_zone(z)

    def test_zoneConstructionSet_from_to_json(self, config):
        import json
        from archetypal import ZoneConstructionSet, load_json_objects
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        ZoneConstructionSet(Name='Constr').clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        constr_json = [ZoneConstructionSet.from_json(**store)
                       for store in datastore["ZoneConstructionSets"]]
        constr_to_json = constr_json[0].to_json()


class TestZoneLoad:
    """Combines different :class:`ZoneLoad` tests"""

    @pytest.fixture(scope='class',
                    params=["RefBldgWarehouseNew2004_Chicago.idf"])
    def zoneLoadtests(self, config, request):
        from eppy.runner.run_functions import install_paths
        eplus_exe, eplus_weather = install_paths("8-9-0")
        eplusdir = Path(eplus_exe).dirname()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(file, weather_file=w, prep_outputs=True,
                           output_report='sql', verbose='v', design_day=False,
                           annual=False)
        yield idf, sql

    def test_zoneLoad_init(self, config):
        from archetypal import ZoneLoad
        load = ZoneLoad(Name=None)

    def test_zoneLoad_from_zone(self, config, zoneLoadtests):
        from archetypal import ZoneLoad, Zone
        idf, sql = zoneLoadtests
        zone = idf.getobject('ZONE', 'Office')
        z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
        load_ = ZoneLoad.from_zone(z)

    def test_zoneLoad_from_to_json(self, config):
        import json
        from archetypal import ZoneLoad, load_json_objects
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        ZoneLoad(Name='Load').clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        load_json = [ZoneLoad.from_json(**store)
                     for store in datastore["ZoneLoads"]]
        load_to_json = load_json[0].to_json()


class TestZoneConditioning:
    """Combines different :class:`ZoneConditioning` tests"""

    @pytest.fixture(scope='class', params=["RefMedOffVAVAllDefVRP.idf",
                                           "AirflowNetwork_MultiZone_SmallOffice_HeatRecoveryHXSL.idf",
                                           "AirflowNetwork_MultiZone_SmallOffice_CoilHXAssistedDX.idf",
                                           "2ZoneDataCenterHVAC_wEconomizer.idf"])
    def zoneConditioningtests(self, config, request):
        from eppy.runner.run_functions import install_paths
        eplus_exe, eplus_weather = install_paths("8-9-0")
        eplusdir = Path(eplus_exe).dirname()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(file, weather_file=w, prep_outputs=True,
                           output_report='sql', verbose='v', design_day=False,
                           annual=False)
        yield idf, sql, request.param

    def test_zoneConditioning_init(self, config):
        from archetypal import ZoneConditioning
        cond = ZoneConditioning(Name=None)
        assert cond.Name == None

    def test_zoneConditioning_from_zone(self, config, zoneConditioningtests):
        from archetypal import ZoneConditioning, Zone
        idf, sql, idf_name = zoneConditioningtests
        if idf_name == "RefMedOffVAVAllDefVRP.idf":
            zone = idf.getobject('ZONE', 'Core_mid')
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            cond_ = ZoneConditioning.from_zone(z)
        if idf_name == "AirflowNetwork_MultiZone_SmallOffice_HeatRecoveryHXSL" \
                       ".idf":
            zone = idf.getobject('ZONE', 'West Zone')
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            cond_HX = ZoneConditioning.from_zone(z)
        if idf_name == "2ZoneDataCenterHVAC_wEconomizer.idf" \
                or idf_name == \
                "AirflowNetwork_MultiZone_SmallOffice_CoilHXAssistedDX.idf":
            zone = idf.getobject('ZONE', 'East Zone')
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            cond_HX_eco = ZoneConditioning.from_zone(z)

    def test_zoneConditioning_from_to_json(self, config):
        import json
        from archetypal import ZoneConditioning, load_json_objects
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        ZoneConditioning(Name='Cond').clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        cond_json = [ZoneConditioning.from_json(**store)
                     for store in datastore["ZoneConditionings"]]
        cond_to_json = cond_json[0].to_json()


class TestVentilationSetting:
    """Combines different :class:`VentilationSetting` tests"""

    @pytest.fixture(scope='class', params=["VentilationSimpleTest.idf",
                                           "RefBldgWarehouseNew2004_Chicago.idf"])
    def ventilatontests(self, config, request):
        from eppy.runner.run_functions import install_paths
        eplus_exe, eplus_weather = install_paths("8-9-0")
        eplusdir = Path(eplus_exe).dirname()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(file, weather_file=w, prep_outputs=True,
                           output_report='sql', verbose='v', design_day=False,
                           annual=False)
        yield idf, sql, request.param

    def test_ventilation_init(self, config):
        from archetypal import VentilationSetting
        vent = VentilationSetting(Name=None)

    def test_naturalVentilation_from_zone(self, config, ventilatontests):
        from archetypal import VentilationSetting, Zone
        idf, sql, idf_name = ventilatontests
        if idf_name == "VentilationSimpleTest.idf":
            zone = idf.getobject('ZONE', 'ZONE 1')
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            natVent = VentilationSetting.from_zone(z)
        if idf_name == "VentilationSimpleTest.idf":
            zone = idf.getobject('ZONE', 'ZONE 2')
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            schedVent = VentilationSetting.from_zone(z)
        if idf_name == "RefBldgWarehouseNew2004_Chicago.idf":
            zone = idf.getobject('ZONE', 'Office')
            z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
            infiltVent = VentilationSetting.from_zone(z)

    def test_ventilationSetting_from_to_json(self, config):
        import json
        from archetypal import VentilationSetting, load_json_objects
        filename = "tests/input_data/umi_samples/BostonTemplateLibrary_2.json"
        VentilationSetting(Name='Vent').clear_cache()
        with open(filename, 'r') as f:
            datastore = json.load(f)
        loading_json_list = load_json_objects(datastore)
        vent_json = [VentilationSetting.from_json(**store)
                     for store in datastore["VentilationSettings"]]
        vent_to_json = vent_json[0].to_json()


class TestDomesticHotWaterSetting:
    """Series of tests for the :class:`DomesticHotWaterSetting` class"""

    # todo: Implement from_to_json for DomesticHotWaterSetting class

    pass


class TestWindowSetting:
    """Combines different :class:`WindowSetting` tests"""

    @pytest.fixture(scope='class', params=["WindowTests.idf",
                                           'AirflowNetwork3zVent.idf'])
    def windowtests(self, config, request):
        eplusdir = get_eplus_dire()
        file = eplusdir / "ExampleFiles" / request.param
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(file, weather_file=w, prep_outputs=True,
                           output_report='sql', verbose='v', design_day=False,
                           annual=False)
        yield idf, sql

    def test_window_from_construction_name(self, small_idf):
        from archetypal import WindowSetting
        idf, sql = small_idf
        construction = idf.getobject('CONSTRUCTION', 'B_Dbl_Air_Cl')
        WindowSetting(Name='Unnamed').clear_cache()
        w = WindowSetting.from_construction(construction)

    @pytest.fixture(scope='class')
    def allwindowtypes(self, config, windowtests):
        from archetypal import WindowSetting
        idf, sql = windowtests
        f_surfs = idf.idfobjects['FENESTRATIONSURFACE:DETAILED']
        windows = []
        for f in f_surfs:
            windows.append(WindowSetting.from_surface(f))
        yield windows

    def test_allwindowtype(self, allwindowtypes):
        assert allwindowtypes

    def test_window_fromsurface(self, config, small_idf):
        from archetypal import WindowSetting
        idf, sql = small_idf
        f_surfs = idf.idfobjects['FENESTRATIONSURFACE:DETAILED']
        for f in f_surfs:
            constr = f.Construction_Name
            idf.add_object("WindowMaterial:Shade".upper(),
                           Visible_Transmittance=0.5,
                           Name='Roll Shade', save=False)
            idf.add_object("WINDOWPROPERTY:SHADINGCONTROL",
                           Construction_with_Shading_Name=constr,
                           Setpoint=14,
                           Shading_Device_Material_Name='Roll Shade',
                           save=False, Name='test_constrol')
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
        zone = idf.idfobjects['ZONE'][0]
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
        zone = idf.idfobjects['ZONE'][0]
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
        mat_a = ar.GlazingMaterial(Name='mat_a', **sg_a)
        glazMat_to_json = mat_a.to_json()
        assert glazMat_to_json


class TestZone:
    """Tests for :class:`Zone` class"""

    def test_zone_volume(self, config):
        """Test the zone volume for a sloped roof"""
        from archetypal import Zone
        file = "tests/input_data/trnsys/NECB 2011 - Full Service Restaurant.idf"
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
        idf = ar.load_idf(file)
        sql = ar.run_eplus(file, weather_file=w, prep_outputs=True,
                           output_report='sql', verbose='v', design_day=False,
                           annual=False)
        zone = idf.getobject('ZONE',
                             'Sp-attic Sys-0 Flr-2 Sch-- undefined - '
                             'HPlcmt-core ZN')
        z = Zone.from_zone_epbunch(zone_ep=zone, sql=sql)
        np.testing.assert_almost_equal(desired=z.volume,
                                       actual=856.3,
                                       decimal=1)
        z.to_json()

    def test_add_zone(self, small_idf):
        """Test __add__() for Zone"""
        idf, sql = small_idf
        zone_core = idf.getobject('ZONE', core_name)
        zone_perim = idf.getobject('ZONE', perim_name)

        z_core = ar.Zone.from_zone_epbunch(zone_core, sql=sql)
        z_perim = ar.Zone.from_zone_epbunch(zone_perim, sql=sql)

        z_new = z_core + z_perim

        assert z_new
        np.testing.assert_almost_equal(actual=z_core.volume + z_perim.volume,
                                       desired=z_new.volume, decimal=3)
        np.testing.assert_almost_equal(actual=z_core.area + z_perim.area,
                                       desired=z_new.area, decimal=3)

    def test_iadd_zone(self, small_idf):
        """Test __iadd__() for Zone"""
        idf, sql = small_idf
        zone_core = idf.getobject('ZONE', core_name)
        zone_perim = idf.getobject('ZONE', perim_name)

        z_core = ar.Zone.from_zone_epbunch(zone_core)
        z_perim = ar.Zone.from_zone_epbunch(zone_perim)
        volume = z_core.volume + z_perim.volume  # save volume before changing
        area = z_core.area + z_perim.area  # save area before changing

        id_ = z_core.id
        z_core += z_perim

        assert z_core
        assert z_core.id == id_
        assert z_core.id != z_perim.id

        np.testing.assert_almost_equal(actual=volume,
                                       desired=z_core.volume, decimal=3)

        np.testing.assert_almost_equal(actual=area,
                                       desired=z_core.area, decimal=3)


@pytest.fixture(scope="session")
def bt():
    """A building template fixture used in subsequent tests"""
    eplus_dir = get_eplus_dire()
    file = eplus_dir / "ExampleFiles" / "5ZoneCostEst.idf"
    w = next(iter((eplus_dir / "WeatherData").glob("*.epw")), None)
    file = ar.copy_file(file)[0]
    idf = ar.load_idf(file)
    sql = ar.run_eplus(file, weather_file=w, prep_outputs=True, verbose="v",
                       output_report="sql", expandobjects=True, annual=True)
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
        b = UmiTemplate.from_json(filename)
        bt = b.BuildingTemplates
        bt_to_json = bt[0].to_json()
        w_to_json = bt[0].Windows.to_json()


class TestZoneGraph:
    """Series of tests for the :class:`ZoneGraph` class"""

    def test_traverse_graph(self, config):
        file = "tests/input_data/trnsys/ASHRAE90" \
               ".1_Warehouse_STD2004_Rochester.idf"
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"

        idf = ar.load_idf(file)
        sql = ar.run_eplus(file, weather_file=w, prep_outputs=True, verbose="v",
                           output_report="sql", expandobjects=True)

        from archetypal import BuildingTemplate

        bt = BuildingTemplate.from_idf(idf, sql=sql)
        G = bt.zone_graph(log_adj_report=False, skeleton=False, force=True)

        # from operator import add
        # from functools import reduce
        #
        # zone_list = [node[1] for node in G.nodes(data='zone') if
        #              not G.nodes(data='core')[node[0]]]
        #
        # zone = reduce(add, zone)_list

        assert G

    @pytest.fixture(scope="class")
    def G(self, bt):
        yield bt.zone_graph(skeleton=True, force=True)

    @pytest.mark.parametrize('adj_report', [True, False])
    def test_graph1(self, config, bt, adj_report):
        """Test the creation of a BuildingTemplate zone graph. Parametrize
        the creation of the adjacency report"""
        import networkx as nx
        bt.clear_cache()
        G1 = bt.zone_graph(log_adj_report=adj_report, skeleton=True,
                           force=False)
        assert not nx.is_empty(G1)

    def test_graph2(self, config, bt):
        """Test the creation of a BuildingTemplate zone graph. Parametrize
            the creation of the adjacency report"""
        # calling zone_graph a second time should not recalculate it.
        G2 = bt.zone_graph(log_adj_report=False, skeleton=True,
                           force=False)

    def test_graph3(self, config, bt):
        """Test the creation of a BuildingTemplate zone graph. Parametrize
        the creation of the adjacency report"""
        # calling zone_graph a second time with force=True should
        # recalculate it and produce a new id.
        G3 = bt.zone_graph(log_adj_report=False, skeleton=True,
                           force=True)

    def test_graph4(self, config, bt):
        """Test the creation of a BuildingTemplate zone graph. Parametrize
            the creation of the adjacency report"""
        # skeleton False should build the zone elements.
        G4 = bt.zone_graph(log_adj_report=False, skeleton=False,
                           force=True)

        from eppy.bunch_subclass import EpBunch
        assert isinstance(G4.nodes['ZN5_Core_Space_1']['epbunch'], EpBunch)

    def test_graph_info(self, G):
        """test the info method on a ZoneGraph"""
        G.info()

    def test_viewgraph2d(self, config, G):
        """test the visualization of the zonegraph in 2d"""
        import networkx as nx
        G.plot_graph2d(nx.layout.circular_layout, (1),
                       font_color='w', legend=True, font_size=8,
                       color_nodes='core',
                       node_labels_to_integers=True,
                       plt_style='seaborn', save=True,
                       filename='test')

    @pytest.mark.parametrize('annotate', [True, 'Name', ('core', None)])
    def test_viewgraph3d(self, config, G, annotate):
        """test the visualization of the zonegraph in 3d"""
        G.plot_graph3d(annotate=annotate, axis_off=True)

    def test_core_graph(self, G):
        H = G.core_graph

        assert len(H) > 0  # assert G has at least one node

    def test_perim_graph(self, G):
        H = G.perim_graph

        assert len(H) > 0  # assert G has at least one node

    def test_reduce(self, config):
        file = "tests/input_data/trnsys/ASHRAE90" \
               ".1_OfficeSmall_STD2004_Rochester" \
               ".idf"
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"

        idf = ar.load_idf(file)
        sql = ar.run_eplus(file, weather_file=w, prep_outputs=True, verbose="v",
                           output_report="sql", expandobjects=True)

        from archetypal import BuildingTemplate
        bt = BuildingTemplate.from_idf(idf, sql=sql)
        bt.clear_cache()
        R = bt.reduce()

    def test_reduce_graph(self, config):
        file = "tests/input_data/trnsys/ASHRAE90" \
               ".1_OfficeSmall_STD2004_Rochester" \
               ".idf"
        w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"

        idf = ar.load_idf(file)
        sql = ar.run_eplus(file, weather_file=w, prep_outputs=True, verbose="v",
                           output_report="sql", expandobjects=True)

        from archetypal import BuildingTemplate

        bt = BuildingTemplate.from_idf(idf, sql=sql)
        bt.clear_cache()
        G = bt.zone_graph(log_adj_report=False, skeleton=False, force=True)

        r_G = bt._graph_reduce(G)

        assert r_G
