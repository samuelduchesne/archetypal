import archetypal as ar


def test_add_materials():
    mat_a = ar.OpaqueMaterial(Name='mat_a', Conductivity=100, SpecificHeat=4.18)
    mat_b = ar.OpaqueMaterial(Name='mat_b', Conductivity=100, SpecificHeat=4.18)
    assert mat_a + mat_b


def test_iadd_materials():
    mat_a = ar.OpaqueMaterial(Name='mat_a', Conductivity=100, SpecificHeat=4.18)
    mat_b = ar.OpaqueMaterial(Name='mat_b', Conductivity=100, SpecificHeat=4.18)
    mat_a += mat_b
    assert mat_a
