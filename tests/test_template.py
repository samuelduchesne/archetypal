import archetypal as ar
import numpy as np
import pytest


def test_add_materials():
    """test __add__() for OpaqueMaterial"""
    mat_a = ar.OpaqueMaterial(Conductivity=100, SpecificHeat=4.18, Name='mat_a')
    mat_b = ar.OpaqueMaterial(Conductivity=200, SpecificHeat=4.18, Name='mat_b')
    mat_c = mat_a + mat_b
    assert mat_c
    assert mat_c.Conductivity == 150
    assert mat_a.id != mat_b.id != mat_c.id


def test_iadd_materials():
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


def test_add_glazing_material():
    """test __add__() for OpaqueMaterial"""
    sg_a = ar.calc_simple_glazing(0.763, 2.716, 0.812)
    sg_b = ar.calc_simple_glazing(0.678, 2.113, 0.906)
    mat_a = ar.GlazingMaterial(Name='mat_a', **sg_a)
    mat_b = ar.GlazingMaterial(Name='mat_b', **sg_b)

    mat_c = mat_a + mat_b

    assert mat_c
    assert mat_a.id != mat_b.id != mat_c.id


def test_iadd_glazing_material():
    """test __iadd__() for OpaqueMaterial"""
    sg_a = ar.calc_simple_glazing(0.763, 2.716, 0.812)
    sg_b = ar.calc_simple_glazing(0.678, 2.113, 0.906)
    mat_a = ar.GlazingMaterial(Name='mat_ia', **sg_a)
    mat_b = ar.GlazingMaterial(Name='mat_ib', **sg_b)

    id_ = mat_a.id  # storing mat_a's id.

    mat_a += mat_b

    assert mat_a
    assert mat_a.id == id_  # id should not change
    assert mat_a.id != mat_b.id


def test_add_opaque_construction():
    """Test __add__() for OpaqueConstruction"""
    mat_a = ar.OpaqueMaterial(Conductivity=100, SpecificHeat=4.18, Name='mat_a')
    mat_b = ar.OpaqueMaterial(Conductivity=200, SpecificHeat=4.18, Name='mat_b')
    thickness = 0.10
    layers = [ar.MaterialLayer(mat_a, thickness),
              ar.MaterialLayer(mat_b, thickness)]
    oc_a = ar.OpaqueConstruction(Layers=layers, Name="oc_a")

    thickness = 0.30
    layers = [ar.MaterialLayer(mat_a, thickness)]
    oc_b = ar.OpaqueConstruction(Layers=layers, Name="oc_b")
    oc_c = oc_a + oc_b

    assert oc_c


def test_iadd_opaque_construction():
    """Test __iadd__() for OpaqueConstruction"""
    mat_a = ar.OpaqueMaterial(Conductivity=100, SpecificHeat=4.18,
                              Name='mat_ia')
    mat_b = ar.OpaqueMaterial(Conductivity=200, SpecificHeat=4.18,
                              Name='mat_ib')
    thickness = 0.10
    layers = [ar.MaterialLayer(mat_a, thickness),
              ar.MaterialLayer(mat_b, thickness)]
    oc_a = ar.OpaqueConstruction(Layers=layers, Name="oc_ia")
    id_ = oc_a.id  # storing mat_a's id.

    thickness = 0.30
    layers = [ar.MaterialLayer(mat_a, thickness)]
    oc_b = ar.OpaqueConstruction(Layers=layers, Name="oc_ib")
    oc_a += oc_b

    assert oc_a
    assert oc_a.id == id_  # id should not change
    assert oc_a.id != oc_b.id


core_name = 'core'
perim_name = 'perim'


@pytest.fixture(scope='session')
def small_idf(config):
    file = "tests/input_data/umi_samples/B_Off_0.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"
    idf = ar.load_idf(file)
    sql = ar.run_eplus(file, weather_file=w, prep_outputs=True,
                       output_report='sql', verbose='v', design_day=False)
    yield idf, sql


def test_add_zoneconstructionset(small_idf):
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


def test_iadd_zoneconstructionset(small_idf):
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


def test_add_zone(small_idf):
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


def test_iadd_zone(small_idf):
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


def test_add_zoneconditioning(small_idf):
    pass


def test_traverse_graph(config):
    file = "tests/input_data/trnsys/NECB 2011 - Warehouse.idf"
    w = "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw"

    idf = ar.load_idf(file)
    sql = ar.run_eplus(file, weather_file=w, prep_outputs=True, verbose="v",
                       output_report="sql", expandobjects=True)

    from archetypal import BuildingTemplate

    bt = BuildingTemplate.from_idf(idf, sql=sql)
    G = bt.zone_graph(log_adj_report=False, skeleton=False, force=True)

    assert G
