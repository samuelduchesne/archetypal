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
    mat_a = ar.OpaqueMaterial(Name='mat_a', Conductivity=100, SpecificHeat=4.18)
    id_ = mat_a.id  # storing mat_a's id.

    mat_b = ar.OpaqueMaterial(Name='mat_b', Conductivity=200, SpecificHeat=4.18)
    mat_a += mat_b
    assert mat_a
    assert mat_a.Conductivity == 150
    assert mat_a.id == id_  # id should not change
    assert mat_a.id != mat_b.id
