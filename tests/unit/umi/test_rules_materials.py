"""The material and construction rules (spec 003, T015, research R11)."""

from __future__ import annotations

import math

import pytest
from epinterface.sbem.components.envelope import ConstructionAssemblyComponent, EnvelopeAssemblyComponent
from epinterface.sbem.components.materials import ConstructionMaterialComponent
from hypothesis import given
from hypothesis import strategies as st

from archetypal.umi._format import MaterialLayer, OpaqueConstruction, OpaqueMaterial, ZoneConstructions
from archetypal.umi.correspondence import get_rule
from archetypal.umi.report import Findings, LossKind, NoteKind
from archetypal.umi.rules import materials
from archetypal.umi.rules.materials import (
    FILLED_SLOTS,
    ROUGHNESS,
    SBEM_MATERIAL_TYPES,
    SET_SLOTS,
    adiabatic_to_sbem,
    adiabatic_to_umi,
    assemblies_to_sbem,
    assemblies_to_umi,
    assembly_life_cycle_to_sbem,
    assembly_life_cycle_to_umi,
    carbon_per_kg,
    carbon_per_m3,
    construction_to_sbem,
    construction_to_umi,
    cost_from_sbem,
    cost_per_m3,
    life_cycle_to_sbem,
    life_cycle_to_umi,
    material_problems,
    material_to_sbem,
    material_to_umi,
)

REL = 1e-12


def brick(**changes: object) -> OpaqueMaterial:
    fields: dict[str, object] = {
        "Name": "Brick",
        "Category": "Masonry",
        "Comments": "a comment",
        "DataSource": "a source",
        "Conductivity": 0.9,
        "Density": 1900.0,
        "SpecificHeat": 840.0,
        "Roughness": "Rough",
        "ThermalEmittance": 0.88,
        "SolarAbsorptance": 0.6,
        "VisibleAbsorptance": 0.65,
        "Cost": 120.0,
        "EmbodiedCarbon": 0.25,
    }
    fields.update(changes)
    return OpaqueMaterial.model_validate(fields)


def construction(name: str, *layers: tuple[OpaqueMaterial, float]) -> OpaqueConstruction:
    return OpaqueConstruction.model_validate({
        "Name": name,
        "Layers": [MaterialLayer[OpaqueMaterial](Material=m, Thickness=t) for m, t in layers],
    })


INSULATION = brick(Name="Insulation", Category="insulation", Conductivity=0.04, Density=30.0)
WALL = construction("Wall", (brick(), 0.1), (INSULATION, 0.05), (brick(Name="Plaster", Category="Plaster"), 0.01))
ROOF = construction("Roof", (INSULATION, 0.2))
SLAB = construction("Slab", (brick(Name="Concrete", Category="Concrete"), 0.15))
GROUND = construction("Ground", (brick(Name="Concrete", Category="Concrete"), 0.3))
PARTITION = construction("Partition", (brick(Name="Board", Category="Boards"), 0.02))
SET = ZoneConstructions.model_validate({
    "Name": "Set",
    "Category": "Office",
    "Facade": WALL,
    "Roof": ROOF,
    "Slab": SLAB,
    "Ground": GROUND,
    "Partition": PARTITION,
})


def close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=REL, abs_tol=0.0) or a == b


# --- material.carbon_per_m3 and material.cost_per_m3 ------------------------------------------


def test_carbon_per_m3_multiplies_by_density() -> None:
    assert carbon_per_m3(0.25, 1900.0) == pytest.approx(475.0, rel=REL)


def test_carbon_per_kg_divides_by_density() -> None:
    assert carbon_per_kg(475.0, 1900.0) == pytest.approx(0.25, rel=REL)


def test_carbon_per_kg_is_refused_for_zero_density() -> None:
    with pytest.raises(ValueError, match="density"):
        carbon_per_kg(1.0, 0.0)


def test_carbon_per_kg_of_no_carbon_at_zero_density_is_zero() -> None:
    assert carbon_per_kg(0.0, 0.0) == 0.0


def test_carbon_rule_is_registered_both_ways() -> None:
    rule = get_rule("material.carbon_per_m3")
    assert rule.to_sbem is carbon_per_m3
    assert rule.to_umi is carbon_per_kg


def test_cost_is_per_m3_as_is() -> None:
    assert cost_per_m3(120.0) == 120.0
    assert cost_from_sbem(120.0, "m3", 1900.0) == 120.0
    assert cost_from_sbem(2.0, "kg", 50.0) == 100.0
    assert cost_from_sbem(None, None, 50.0) == 0.0
    assert cost_from_sbem(10.0, "m2", 50.0) is None


# --- material.properties ----------------------------------------------------------------------


def test_material_to_sbem_maps_every_field() -> None:
    findings = Findings()
    sbem = material_to_sbem(brick(), subject="T", location="/OpaqueMaterials/0", findings=findings)
    assert isinstance(sbem, ConstructionMaterialComponent)
    assert sbem.Name == "Brick"
    assert sbem.ThermalAbsorptance == 0.88
    assert sbem.Roughness == "Rough"
    assert (sbem.Conductivity, sbem.Density, sbem.SpecificHeat) == (0.9, 1900.0, 840.0)
    assert (sbem.SolarAbsorptance, sbem.VisibleAbsorptance) == (0.6, 0.65)
    assert sbem.Type == "Masonry"
    assert (sbem.Category, sbem.Comment, sbem.DataSource) == ("Masonry", "a comment", "a source")
    assert sbem.RateUnit == "m3"
    assert sbem.Cost == 120.0
    assert sbem.EmbodiedCarbon == pytest.approx(0.25 * 1900.0, rel=REL)
    assert sbem.TemperatureCoefficientThermalConductivity == 0.0
    (note,) = findings.notes
    assert note.kind is NoteKind.ASSUMED
    assert note.rule == "material.properties"
    assert "TemperatureCoefficientThermalConductivity" in note.reason
    assert not findings.losses


@pytest.mark.parametrize("category", ["insulation", "INSULATION", "Insulation"])
def test_type_from_category_is_case_insensitive(category: str) -> None:
    findings = Findings()
    sbem = material_to_sbem(brick(Category=category), subject="T", location="/m", findings=findings)
    assert sbem.Type == "Insulation"
    assert [n.location for n in findings.notes] == ["/m/TemperatureCoefficientThermalConductivity"]


def test_type_other_when_category_names_no_type() -> None:
    findings = Findings()
    sbem = material_to_sbem(brick(Category="Uncategorized"), subject="T", location="/m", findings=findings)
    assert sbem.Type == "Other"
    notes = {n.location: n for n in findings.notes}
    assert notes["/m/Category"].value == "Uncategorized"
    assert notes["/m/Category"].rule == "material.properties"
    assert notes["/m/Category"].kind is NoteKind.ASSUMED


def test_twelve_sbem_material_types() -> None:
    assert len(SBEM_MATERIAL_TYPES) == 12


@pytest.mark.parametrize("roughness", ["Grainy", None, ""])
def test_roughness_outside_the_six_keywords_is_a_range_problem(roughness: str | None) -> None:
    (problem,) = material_problems(brick(Roughness=roughness), pointer="/OpaqueMaterials/3", template="T")
    assert problem.pointer == "/OpaqueMaterials/3/Roughness"
    assert problem.template == "T"
    assert problem.rule == "range"
    with pytest.raises(ValueError, match="Roughness"):
        material_to_sbem(brick(Roughness=roughness), subject="T", location="/m", findings=Findings())


def test_six_roughness_keywords_pass() -> None:
    assert len(ROUGHNESS) == 6
    for keyword in ROUGHNESS:
        assert material_problems(brick(Roughness=keyword), pointer="/m", template=None) == []


def test_roughness_keyword_case_is_normalised() -> None:
    assert material_problems(brick(Roughness="mediumrough"), pointer="/m", template=None) == []
    sbem = material_to_sbem(brick(Roughness="mediumrough"), subject="T", location="/m", findings=Findings())
    assert sbem.Roughness == "MediumRough"


def test_carbon_at_zero_density_is_lost_on_reading() -> None:
    findings = Findings()
    sbem = material_to_sbem(brick(Density=0.0), subject="T", location="/m", findings=findings)
    assert sbem.EmbodiedCarbon == 0.0
    (loss,) = findings.losses
    assert (loss.kind, loss.location, loss.value, loss.rule) == (
        LossKind.LOST,
        "/m/EmbodiedCarbon",
        0.25,
        "material.carbon_per_m3",
    )


def test_material_to_umi_inverts() -> None:
    findings = Findings()
    sbem = material_to_sbem(brick(), subject="T", location="/m", findings=Findings())
    assert_material_close(material_to_umi(sbem, "T", "m", findings), brick())
    assert not findings.losses


def sbem_material(**changes: object) -> ConstructionMaterialComponent:
    findings = Findings()
    base = material_to_sbem(brick(), subject="T", location="/m", findings=findings)
    return base.model_copy(update=changes)


def test_material_to_umi_reports_what_umi_lacks() -> None:
    findings = Findings()
    material = sbem_material(TemperatureCoefficientThermalConductivity=0.002, Category="Bricks", Life=50.0)
    umi = material_to_umi(material, "A", "perimeter.m", findings)
    assert umi.category == "Bricks"
    losses = {loss.location: loss for loss in findings.losses}
    assert losses["perimeter.m.TemperatureCoefficientThermalConductivity"].value == 0.002
    assert losses["perimeter.m.Type"].value == "Masonry"
    assert losses["perimeter.m.Life"].upstream is None  # UMI has no life: no upstream item adds it
    assert all(loss.subject == "A" for loss in findings.losses)


def test_material_to_umi_category_from_type_when_unset() -> None:
    umi = material_to_umi(sbem_material(Category=None), "A", "m", Findings())
    assert umi.category == "Masonry"


def test_material_to_umi_carbon_per_kg_rate() -> None:
    umi = material_to_umi(sbem_material(RateUnit="kg", EmbodiedCarbon=0.3, Cost=2.0), "A", "m", Findings())
    assert umi.embodied_carbon == 0.3
    assert umi.cost == pytest.approx(2.0 * 1900.0, rel=REL)


def test_material_to_umi_area_rate_is_lost() -> None:
    findings = Findings()
    umi = material_to_umi(sbem_material(RateUnit="m2", EmbodiedCarbon=5.0, Cost=3.0), "A", "m", findings)
    assert (umi.embodied_carbon, umi.cost) == (0.0, 0.0)
    assert {loss.location for loss in findings.losses} == {"m.EmbodiedCarbon", "m.Cost"}


def test_material_to_umi_refuses_carbon_at_zero_density() -> None:
    with pytest.raises(ValueError, match="density"):
        material_to_umi(sbem_material(Density=0.0, EmbodiedCarbon=4.0), "A", "m", Findings())


# --- construction.layers ----------------------------------------------------------------------


def test_layers_keep_order_and_thickness() -> None:
    findings = Findings()
    assembly = construction_to_sbem(WALL, "Facade", subject="T", location="/c", findings=findings)
    assert isinstance(assembly, ConstructionAssemblyComponent)
    assert assembly.Name == "Wall"
    assert assembly.Type == "Facade"
    assert [layer.LayerOrder for layer in assembly.Layers] == [0, 1, 2]
    assert [layer.ConstructionMaterial.Name for layer in assembly.Layers] == ["Brick", "Insulation", "Plaster"]
    assert [layer.Thickness for layer in assembly.Layers] == [0.1, 0.05, 0.01]
    back = construction_to_umi(assembly, "T", "c", Findings())
    assert back == WALL


def test_construction_to_umi_sorts_by_layer_order() -> None:
    assembly = construction_to_sbem(WALL, "Facade", subject="T", location="/c", findings=Findings())
    shuffled = assembly.model_copy(update={"Layers": list(reversed(assembly.Layers))})
    assert construction_to_umi(shuffled, "T", "c", Findings()) == WALL


def test_construction_to_umi_reports_a_vegetation_layer() -> None:
    assembly = construction_to_sbem(ROOF, "FlatRoof", subject="T", location="/c", findings=Findings())
    findings = Findings()
    construction_to_umi(assembly.model_copy(update={"VegetationLayer": "Sedum"}), "T", "c", findings)
    (loss,) = findings.losses
    assert (loss.location, loss.value, loss.rule) == ("c.VegetationLayer", "Sedum", "construction.layers")


# --- construction.sets ------------------------------------------------------------------------


def test_set_slots_map_to_sbem() -> None:
    assert SET_SLOTS == {
        "Facade": "FacadeAssembly",
        "Roof": "FlatRoofAssembly",
        "Slab": "FloorCeilingAssembly",
        "Ground": "GroundSlabAssembly",
        "Partition": "PartitionAssembly",
    }
    assert FILLED_SLOTS == {
        "AtticRoofAssembly": "Roof",
        "AtticFloorAssembly": "Slab",
        "ExternalFloorAssembly": "Slab",
        "BasementCeilingAssembly": "Slab",
        "GroundWallAssembly": "Ground",
    }


def test_set_to_sbem_fills_the_five_other_slots_and_notes_them() -> None:
    findings = Findings()
    envelope = assemblies_to_sbem(SET, subject="T", location="/ZoneConstructionSets/0", findings=findings)
    assert isinstance(envelope, EnvelopeAssemblyComponent)
    assert envelope.Name == "Set"
    assert envelope.Category == "Office"
    assert envelope.FacadeAssembly.Name == "Wall"
    assert envelope.FlatRoofAssembly.Type == "FlatRoof"
    assert envelope.AtticRoofAssembly.Name == "Roof"
    assert envelope.AtticRoofAssembly.Type == "AtticRoof"
    assert envelope.AtticFloorAssembly.Name == "Slab"
    assert envelope.ExternalFloorAssembly.Name == "Slab"
    assert envelope.BasementCeilingAssembly.Name == "Slab"
    assert envelope.GroundWallAssembly.Name == "Ground"
    assert envelope.GroundWallAssembly.Type == "GroundWall"
    assert envelope.InternalMassAssembly is None
    set_notes = [n for n in findings.notes if n.rule == "construction.sets"]
    assert len(set_notes) == 5
    assert {n.kind for n in set_notes} == {NoteKind.ASSUMED}
    assert not findings.losses


def test_set_to_sbem_passes_internal_mass_through() -> None:
    mass = construction_to_sbem(SLAB, "InternalMass", subject="T", location="/c", findings=Findings())
    envelope = assemblies_to_sbem(
        SET, subject="T", location="/s", findings=Findings(), internal_mass=mass, internal_mass_exposed=0.5
    )
    assert envelope.InternalMassAssembly == mass
    assert envelope.InternalMassExposedAreaPerArea == 0.5


def test_set_to_sbem_refuses_a_missing_slot() -> None:
    with pytest.raises(ValueError, match="Roof"):
        assemblies_to_sbem(SET.model_copy(update={"roof": None}), subject="T", location="/s", findings=Findings())


def test_set_round_trip_loses_nothing() -> None:
    envelope = assemblies_to_sbem(SET, subject="T", location="/s", findings=Findings())
    findings = Findings()
    assert assemblies_to_umi(envelope, "A", "perimeter.Envelope.Assemblies", findings) == SET
    assert not findings.losses


def test_set_to_umi_lists_differing_filled_slots_as_lost() -> None:
    envelope = assemblies_to_sbem(SET, subject="T", location="/s", findings=Findings())
    other = construction_to_sbem(WALL, "GroundWall", subject="T", location="/c", findings=Findings())
    findings = Findings()
    assemblies_to_umi(envelope.model_copy(update={"GroundWallAssembly": other}), "A", "core.E", findings)
    (loss,) = findings.losses
    assert loss.kind is LossKind.LOST
    assert loss.location == "core.E.GroundWallAssembly"
    assert loss.value == "Wall"
    assert loss.replacement == "Ground"
    assert loss.rule == "construction.sets"


# --- registration and the round-trip property -------------------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "to_sbem", "to_umi"),
    [
        ("material.properties", material_to_sbem, material_to_umi),
        ("material.cost_per_m3", cost_per_m3, cost_from_sbem),
        ("construction.layers", construction_to_sbem, construction_to_umi),
        ("construction.sets", assemblies_to_sbem, assemblies_to_umi),
    ],
)
def test_rules_are_registered(rule_id: str, to_sbem: object, to_umi: object) -> None:
    rule = get_rule(rule_id)
    assert (rule.to_sbem, rule.to_umi) == (to_sbem, to_umi)
    assert rule.to_sbem.__module__ == materials.__name__  # type: ignore[union-attr]


@pytest.mark.parametrize(
    ("rule_id", "to_sbem", "to_umi"),
    [
        ("material.environmental", life_cycle_to_sbem, life_cycle_to_umi),
        ("construction.environmental", assembly_life_cycle_to_sbem, assembly_life_cycle_to_umi),
        ("construction.adiabatic", adiabatic_to_sbem, adiabatic_to_umi),
    ],
)
def test_up9_rules_are_registered(rule_id: str, to_sbem: object, to_umi: object) -> None:
    rule = get_rule(rule_id)
    assert (rule.to_sbem, rule.to_umi) == (to_sbem, to_umi)


LIFE_CYCLE = {
    "EmbodiedEnergy": 2.5,
    "TransportCarbon": 0.01,
    "TransportDistance": 300.0,
    "TransportEnergy": 0.02,
    "SubstitutionRatePattern": [0.5, 1.0],
    "SubstitutionTimestep": 20.0,
    "MoistureDiffusionResistance": 10.0,
    "DesignStrength": 2.0e7,
    "ModulusOfElasticity": 1.5e10,
}


def test_material_life_cycle_maps_per_m3_and_back() -> None:
    """UP-9: per-kg quantities become per m3 (x density); the others are copied; both ways."""
    findings = Findings()
    original = brick(**LIFE_CYCLE)
    sbem = material_to_sbem(original, subject="T", location="/m", findings=findings)
    assert sbem.EmbodiedEnergy == pytest.approx(2.5 * 1900.0, rel=REL)
    assert sbem.TransportCarbon == pytest.approx(0.01 * 1900.0, rel=REL)
    assert sbem.TransportEnergy == pytest.approx(0.02 * 1900.0, rel=REL)
    assert (sbem.TransportDistance, sbem.SubstitutionRatePattern, sbem.SubstitutionTimestep) == (
        300.0,
        [0.5, 1.0],
        20.0,
    )
    assert (sbem.MoistureDiffusionResistance, sbem.DesignStrength, sbem.ModulusOfElasticity) == (10.0, 2.0e7, 1.5e10)
    back = material_to_umi(sbem, "A", "m", findings)
    for key, value in LIFE_CYCLE.items():
        expected = tuple(value) if isinstance(value, list) else value
        assert getattr(back, _name(key)) == pytest.approx(expected), key
    assert findings.losses == []


def _name(key: str) -> str:
    return next(name for name, info in OpaqueMaterial.model_fields.items() if info.alias == key)


def test_life_cycle_of_a_material_without_density_is_lost() -> None:
    findings = Findings()
    sbem = material_to_sbem(brick(Density=0.0, EmbodiedEnergy=2.5), subject="T", location="/m", findings=findings)
    assert sbem.EmbodiedEnergy == 0.0
    [loss] = [loss for loss in findings.losses if loss.rule == "material.environmental"]
    assert (loss.location, loss.rule, loss.upstream) == ("/m/EmbodiedEnergy", "material.environmental", None)


def test_assembly_life_cycle_and_adiabatic_flags_map_both_ways() -> None:
    findings = Findings()
    wall = WALL.model_copy(update={"assembly_carbon": 12.0, "disassembly_energy": 3.0})
    original = SET.model_copy(update={"facade": wall, "is_facade_adiabatic": True, "is_slab_adiabatic": True})
    envelope = assemblies_to_sbem(original, subject="T", location="/s", findings=findings, partition_area=0.7)
    assert (envelope.IsFacadeAdiabatic, envelope.IsSlabAdiabatic, envelope.IsRoofAdiabatic) == (True, True, False)
    assert envelope.PartitionAreaPerFloorArea == 0.7
    assert (envelope.FacadeAssembly.AssemblyCarbon, envelope.FacadeAssembly.DisassemblyEnergy) == (12.0, 3.0)
    back = assemblies_to_umi(envelope, "A", "perimeter.Envelope.Assemblies", findings)
    assert (back.is_facade_adiabatic, back.is_slab_adiabatic, back.is_roof_adiabatic) == (True, True, False)
    assert back.facade is not None
    assert (back.facade.assembly_carbon, back.facade.disassembly_energy) == (12.0, 3.0)


positive = st.floats(min_value=1e-6, max_value=1e6, allow_nan=False, allow_infinity=False)
fraction = st.floats(min_value=0.0, max_value=1.0, allow_nan=False)
names = st.text(st.characters(categories=("L", "N")), min_size=1, max_size=12)


carbons = st.one_of(st.just(0.0), st.floats(min_value=1e-9, max_value=1e6))


@given(carbon=carbons, density=positive)
def test_carbon_round_trip(carbon: float, density: float) -> None:
    assert close(carbon_per_kg(carbon_per_m3(carbon, density), density), carbon)


@given(cost=st.floats(min_value=0.0, max_value=1e9))
def test_cost_round_trip(cost: float) -> None:
    assert cost_from_sbem(cost_per_m3(cost), "m3", 1.0) == cost


materials_strategy = st.builds(
    brick,
    Name=names,
    Category=st.sampled_from([*SBEM_MATERIAL_TYPES, "Uncategorized"]),
    Conductivity=positive,
    Density=positive,
    SpecificHeat=positive,
    Roughness=st.sampled_from(ROUGHNESS),
    ThermalEmittance=fraction,
    SolarAbsorptance=fraction,
    VisibleAbsorptance=fraction,
    Cost=carbons,
    EmbodiedCarbon=carbons,
)


def assert_material_close(a: OpaqueMaterial, b: OpaqueMaterial) -> None:
    da, db = a.model_dump(), b.model_dump()
    assert da.keys() == db.keys()
    for key, value in da.items():
        if isinstance(value, float):
            assert close(db[key], value), key
        else:
            assert db[key] == value, key


@given(material=materials_strategy)
def test_material_round_trip(material: OpaqueMaterial) -> None:
    findings = Findings()
    sbem = material_to_sbem(material, subject="T", location="/m", findings=findings)
    back = material_to_umi(sbem, "T", "m", findings)
    assert_material_close(back, material)
    assert not findings.losses


@given(
    layers=st.lists(st.tuples(materials_strategy, st.floats(min_value=0.001, max_value=0.5)), min_size=1, max_size=5)
)
def test_construction_round_trip(layers: list[tuple[OpaqueMaterial, float]]) -> None:
    original = construction("C", *layers)
    findings = Findings()
    back = construction_to_umi(
        construction_to_sbem(original, "Facade", subject="T", location="/c", findings=findings), "T", "c", findings
    )
    assert [layer.thickness for layer in back.layers] == [layer.thickness for layer in original.layers]
    for got, want in zip(back.layers, original.layers, strict=True):
        assert got.material is not None
        assert want.material is not None
        assert_material_close(got.material, want.material)
    assert not findings.losses
