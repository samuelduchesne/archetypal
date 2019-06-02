import archetypal as ar


def test_add_materials():
    """test __add__() for OpaqueMaterial"""
    mat_a = ar.OpaqueMaterial(Name='mat_a', Conductivity=100, SpecificHeat=4.18)
    mat_b = ar.OpaqueMaterial(Name='mat_b', Conductivity=200, SpecificHeat=4.18)
    mat_c = mat_a + mat_b
    assert mat_c
    assert mat_c.Conductivity == 150
    assert mat_a.id != mat_b.id != mat_c.id


def test_iadd_materials():
    """test __iadd__() for OpaqueMaterial"""
    mat_a = ar.OpaqueMaterial(Name='mat_ia', Conductivity=100,
                              SpecificHeat=4.18)
    id_ = mat_a.id  # storing mat_a's id.

    mat_b = ar.OpaqueMaterial(Name='mat_ib', Conductivity=200,
                              SpecificHeat=4.18)
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
    mat_a = ar.OpaqueMaterial(Name='mat_a', Conductivity=100, SpecificHeat=4.18)
    mat_b = ar.OpaqueMaterial(Name='mat_b', Conductivity=200, SpecificHeat=4.18)
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
    mat_a = ar.OpaqueMaterial(Name='mat_ia', Conductivity=100,
                              SpecificHeat=4.18)
    mat_b = ar.OpaqueMaterial(Name='mat_ib', Conductivity=200,
                              SpecificHeat=4.18)
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