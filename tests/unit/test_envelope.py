"""Tests for the envelope domain (spec 002, T032; research R6; FR-013, FR-016, FR-017, FR-024)."""

from __future__ import annotations

import math
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
import pytest

from archetypal.reduction.classify import ClassifiedZone, classify
from archetypal.reduction.envelope import (
    ASSEMBLY_TYPES,
    FILMS,
    EnvelopeHook,
    assembly_capacities,
    assembly_u_factor,
    capacity_split,
    envelope_class,
    equivalent_construction,
    internal_mass_construction,
    ledger_fields,
    orientation,
    window_construction,
)
from archetypal.reduction.inventory import LayerRecord, SurfaceRecord, ZoneRecord, build_inventory, surface_class
from archetypal.reduction.ledger import EnvelopeTotals, GroupLedger
from archetypal.reduction.schedules import ScheduleEvaluator
from archetypal.reduction.sources import load_sources

if TYPE_CHECKING:
    from archetypal.reduction.classify import Role
    from archetypal.reduction.inventory import Boundary
    from archetypal.reduction.ledger import EnvelopeClass

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
HOURS = 8760
REL = 1e-12
NO_SCHEDULES = cast("ScheduleEvaluator", None)  # the envelope hooks read no schedule


# --- helpers ------------------------------------------------------------------------------


def _layer(name: str, thickness: float, conductivity: float, density: float, specific_heat: float) -> LayerRecord:
    return LayerRecord(
        material=name,
        thickness=thickness,
        conductivity=conductivity,
        density=density,
        specific_heat=specific_heat,
        resistance=thickness / conductivity,
        resistance_only=False,
    )


BRICK = _layer("brick", 0.1, 0.8, 1800.0, 900.0)
INSULATION = _layer("insulation", 0.1, 0.035, 30.0, 1000.0)
CONCRETE = _layer("concrete", 0.15, 1.8, 2300.0, 1000.0)
GYPSUM = _layer("gypsum", 0.013, 0.25, 800.0, 1090.0)
WALL_LAYERS = (BRICK, INSULATION, CONCRETE)  # outside first


def _surface(  # noqa: PLR0913 - a surface has many fields
    name: str,
    class_name: str,
    tilt: float,
    boundary: str,
    *,
    area: float = 10.0,
    azimuth: float = 0.0,
    u: float = 0.5,
    layers: tuple[LayerRecord, ...] = WALL_LAYERS,
    adjacent: str | None = None,
    shgc: float | None = None,
    vt: float | None = None,
) -> SurfaceRecord:
    window = class_name == "Window"
    return SurfaceRecord(
        name=name,
        surface_class=surface_class(class_name, tilt, cast("Boundary", boundary)),
        class_name=class_name,
        area=area,
        azimuth=azimuth,
        tilt=tilt,
        boundary=cast("Boundary", boundary),
        adjacent_zone=adjacent,
        construction="C",
        u_factor=u,
        u_source="envelope_summary",
        heat_capacity=0.0 if window else sum(layer.heat_capacity for layer in layers),
        layers=() if window else layers,
        shgc=shgc,
        visible_transmittance=vt,
    )


def _zone(name: str, *surfaces: SurfaceRecord, multiplier: int = 1, floor_area: float = 100.0) -> ZoneRecord:
    return ZoneRecord(
        name=name,
        multiplier=multiplier,
        floor_area=floor_area,
        min_z=0.0,
        volume=300.0,
        surfaces=surfaces,
        outdoor_air=np.zeros(HOURS),
    )


def _classified(zone: ZoneRecord, role: str = "conditioned") -> ClassifiedZone:
    return ClassifiedZone(
        zone=zone,
        conditioned=role == "conditioned",
        role=cast("Role", role),
        exposure="perimeter",
        space_use="office",
        space_use_source="user",
        role_reason="test",
    )


def _ledger(zone: ZoneRecord) -> GroupLedger:
    return GroupLedger.from_zone(_classified(zone), NO_SCHEDULES, hooks=[ledger_fields])


def _hooked(hook: EnvelopeHook, zone: ClassifiedZone) -> GroupLedger:
    return GroupLedger.from_zone(zone, NO_SCHEDULES, hooks=[hook])


# --- classes and orientation ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("class_name", "tilt", "boundary", "expected"),
    [
        ("Wall", 90.0, "outdoors", "exterior_wall"),
        ("Wall", 60.0, "outdoors", "exterior_wall"),
        ("Wall", 120.0, "outdoors", "exterior_wall"),
        ("Door", 90.0, "outdoors", "exterior_wall"),
        ("Roof", 0.0, "outdoors", "roof"),
        ("Roof", 59.0, "outdoors", "roof"),
        ("Floor", 180.0, "outdoors", "exposed_floor"),
        ("Floor", 121.0, "outdoors", "exposed_floor"),
        ("Floor", 180.0, "ground", "ground_floor"),
        ("Wall", 90.0, "ground", "ground_wall"),
        ("Wall", 90.0, "interzone", "partition"),
        ("Wall", 90.0, "adiabatic", "partition"),
        ("Floor", 180.0, "interzone", "floor_ceiling"),
        ("Ceiling", 0.0, "adiabatic", "floor_ceiling"),
        ("Window", 90.0, "outdoors", None),
        ("Internal Mass", 90.0, "adiabatic", None),
    ],
)
def test_surface_classes_follow_tilt_and_boundary(
    class_name: str, tilt: float, boundary: str, expected: str | None
) -> None:
    assert envelope_class(_surface("S", class_name, tilt, boundary)) == expected


@pytest.mark.parametrize(
    ("azimuth", "expected"),
    [
        (0.0, "N"),
        (22.4, "N"),
        (22.5, "NE"),
        (45.0, "NE"),
        (90.0, "E"),
        (135.0, "SE"),
        (180.0, "S"),
        (225.0, "SW"),
        (270.0, "W"),
        (315.0, "NW"),
        (337.4, "NW"),
        (337.5, "N"),
        (359.9, "N"),
        (360.0, "N"),
        (-90.0, "W"),
    ],
)
def test_eight_45_degree_sectors(azimuth: float, expected: str) -> None:
    assert orientation(azimuth) == expected


# --- per-class totals ----------------------------------------------------------------------


def test_area_ua_and_orientation_per_class() -> None:
    zone = _zone(
        "Z",
        _surface("N wall", "Wall", 90.0, "outdoors", area=20.0, azimuth=0.0, u=0.4),
        _surface("S wall", "Wall", 90.0, "outdoors", area=30.0, azimuth=180.0, u=0.6),
        _surface("S wall 2", "Wall", 90.0, "outdoors", area=5.0, azimuth=190.0, u=0.6),
        _surface("Roof", "Roof", 0.0, "outdoors", area=100.0, u=0.2),
        _surface("Slab", "Floor", 180.0, "ground", area=100.0, u=0.3),
    )
    envelope = _ledger(zone).envelope
    wall = envelope["exterior_wall"]
    assert wall.area == pytest.approx(55.0, rel=REL)
    assert wall.ua == pytest.approx(20 * 0.4 + 35 * 0.6, rel=REL)
    assert wall.area_by_orientation == pytest.approx({"N": 20.0, "S": 35.0})
    assert envelope["roof"].ua == pytest.approx(20.0, rel=REL)
    # Horizontal surfaces have no orientation.
    assert envelope["roof"].area_by_orientation == {}
    assert envelope["ground_floor"].area == pytest.approx(100.0)
    assert set(envelope) == {"exterior_wall", "roof", "ground_floor"}


def test_capacity_split_at_the_most_resistive_layer() -> None:
    # Outside first: brick, insulation, concrete. The insulation's own capacity is halved.
    inner, outer = capacity_split([(layer.resistance, layer.heat_capacity) for layer in WALL_LAYERS])
    assert outer == pytest.approx(BRICK.heat_capacity + INSULATION.heat_capacity / 2, rel=REL)
    assert inner == pytest.approx(CONCRETE.heat_capacity + INSULATION.heat_capacity / 2, rel=REL)
    assert inner + outer == pytest.approx(sum(layer.heat_capacity for layer in WALL_LAYERS), rel=REL)


def test_capacities_are_conserved_per_class() -> None:
    reversed_layers = WALL_LAYERS[::-1]
    zone = _zone(
        "Z",
        _surface("A", "Wall", 90.0, "outdoors", area=10.0),
        _surface("B", "Wall", 90.0, "outdoors", area=4.0, layers=reversed_layers),
    )
    wall = _ledger(zone).envelope["exterior_wall"]
    total = sum(layer.heat_capacity for layer in WALL_LAYERS) * 14.0
    assert wall.capacity_inner + wall.capacity_outer == pytest.approx(total, rel=REL)
    a_inner, a_outer = capacity_split([(x.resistance, x.heat_capacity) for x in WALL_LAYERS])
    assert wall.capacity_inner == pytest.approx(10 * a_inner + 4 * a_outer, rel=REL)
    assert wall.capacity_outer == pytest.approx(10 * a_outer + 4 * a_inner, rel=REL)


def test_internal_mass_conserves_area_times_capacity() -> None:
    zone = _zone(
        "Z",
        _surface("Furniture", "Internal Mass", 90.0, "adiabatic", area=50.0, layers=(CONCRETE,)),
        _surface("Books", "Internal Mass", 90.0, "adiabatic", area=10.0, layers=(GYPSUM,)),
    )
    ledger = _ledger(zone)
    assert ledger.internal_mass_area == pytest.approx(60.0)
    assert ledger.internal_mass_capacity == pytest.approx(
        50 * CONCRETE.heat_capacity + 10 * GYPSUM.heat_capacity, rel=REL
    )
    assert ledger.envelope == {}

    assembly = internal_mass_construction(ledger.internal_mass_capacity, ledger.internal_mass_area)
    assert assembly is not None
    assert assembly.Type == "InternalMass"
    per_area = sum(
        layer.Thickness * layer.ConstructionMaterial.Density * layer.ConstructionMaterial.SpecificHeat
        for layer in assembly.Layers
    )
    assert per_area * 60.0 == pytest.approx(ledger.internal_mass_capacity, rel=1e-9)
    assert internal_mass_construction(0.0, 0.0) is None


# --- windows -------------------------------------------------------------------------------


def test_windows_conserve_area_ua_shgc_and_vt_by_orientation() -> None:
    windows = [
        _surface("W1", "Window", 90.0, "outdoors", area=4.0, azimuth=180.0, u=2.0, shgc=0.4, vt=0.6),
        _surface("W2", "Window", 90.0, "outdoors", area=6.0, azimuth=170.0, u=1.2, shgc=0.3, vt=0.5),
        _surface("W3", "Window", 90.0, "outdoors", area=3.0, azimuth=90.0, u=5.0, shgc=0.7, vt=0.8),
    ]
    ledger = _ledger(_zone("Z", *windows))
    by_orientation = ledger.window_by_orientation
    assert set(by_orientation) == {"S", "E"}
    south = by_orientation["S"]
    assert south.area == pytest.approx(10.0)
    assert south.ua == pytest.approx(4 * 2.0 + 6 * 1.2, rel=REL)
    assert south.a_shgc == pytest.approx(4 * 0.4 + 6 * 0.3, rel=REL)
    assert south.a_vt == pytest.approx(4 * 0.6 + 6 * 0.5, rel=REL)
    east = by_orientation["E"]
    assert (east.area, east.ua, east.a_shgc, east.a_vt) == pytest.approx((3.0, 15.0, 2.1, 2.4))
    # Windows are not opaque envelope.
    assert ledger.envelope == {}

    glazing = window_construction(by_orientation)
    assert glazing is not None
    total_area = 13.0
    assert glazing.UValue * total_area == pytest.approx(4 * 2.0 + 6 * 1.2 + 15.0, rel=REL)
    assert glazing.SHGF * total_area == pytest.approx(1.6 + 1.8 + 2.1, rel=REL)
    assert glazing.TVis * total_area == pytest.approx(2.4 + 3.0 + 2.4, rel=REL)
    assert window_construction({}) is None


def test_window_without_shgc_is_refused() -> None:
    with pytest.raises(ValueError, match="SHGC"):
        _ledger(_zone("Z", _surface("W", "Window", 90.0, "outdoors", shgc=None, vt=0.5)))


# --- the equivalent three-layer construction ------------------------------------------------


@pytest.mark.parametrize("envelope_class_", sorted(ASSEMBLY_TYPES))
@pytest.mark.parametrize(("u", "inner", "outer"), [(0.25, 2.0e5, 1.5e4), (1.8, 1.6e4, 1.6e4), (0.12, 3.0e5, 3.0e5)])
def test_equivalent_construction_reproduces_u_and_both_capacities(
    envelope_class_: EnvelopeClass, u: float, inner: float, outer: float
) -> None:
    area = 37.0
    totals = EnvelopeTotals(area=area, ua=u * area, capacity_inner=inner * area, capacity_outer=outer * area)
    assembly = equivalent_construction(totals, envelope_class_, name="G1 equivalent")
    assert len(assembly.Layers) == 3
    assert assembly.Type == ASSEMBLY_TYPES[envelope_class_]
    # U with epinterface's films reproduces UA / A.
    inside, outside = FILMS[envelope_class_]
    assert 1.0 / (inside + assembly.r_value + outside) == pytest.approx(u, rel=1e-12)
    assert assembly_u_factor(assembly, envelope_class_) == pytest.approx(u, rel=1e-12)
    # Both capacities, by the same split rule, exactly.
    split = assembly_capacities(assembly)
    assert split.inner == pytest.approx(inner, rel=1e-12)
    assert split.outer == pytest.approx(outer, rel=1e-12)
    # The middle layer is the most resistive: the insulation.
    resistances = [layer.r_value for layer in assembly.sorted_layers]
    assert max(resistances) == resistances[1]
    assert sum(layer.Thickness for layer in assembly.Layers) <= 3.0


def test_equivalent_construction_names_its_materials_after_the_assembly() -> None:
    totals = EnvelopeTotals(area=10.0, ua=5.0, capacity_inner=1e5, capacity_outer=1e5)
    a = equivalent_construction(totals, "exterior_wall", name="office/perimeter facade")
    b = equivalent_construction(totals, "exterior_wall", name="office/core facade")
    assert a.Name == "office/perimeter facade"
    names_a = {layer.name for layer in a.Layers}
    names_b = {layer.name for layer in b.Layers}
    assert len(names_a) == 3
    assert not names_a & names_b


def test_equivalent_construction_of_a_fixture_class_round_trips() -> None:
    totals = EnvelopeTotals(area=135.0, ua=135.0 * 0.458, capacity_inner=135.0 * 1.0e5, capacity_outer=135.0 * 6.8e4)
    assembly = equivalent_construction(totals, "exterior_wall")
    assert assembly_u_factor(assembly, "exterior_wall") * 135.0 == pytest.approx(totals.ua, rel=1e-12)


def test_equivalent_construction_refuses_impossible_inputs() -> None:
    with pytest.raises(ValueError, match="area"):
        equivalent_construction(EnvelopeTotals(), "roof")
    inside, outside = FILMS["roof"]
    too_high = 1.0 / (inside + outside) * 1.01
    with pytest.raises(ValueError, match="films"):
        equivalent_construction(EnvelopeTotals(area=1.0, ua=too_high, capacity_inner=1e4, capacity_outer=1e4), "roof")


def test_equivalent_construction_with_a_massless_side_is_close() -> None:
    # A construction with no mass outside its insulation still gets a (minimal) outer layer.
    totals = EnvelopeTotals(area=10.0, ua=3.0, capacity_inner=10.0 * 5e4, capacity_outer=0.0)
    assembly = equivalent_construction(totals, "roof")
    split = assembly_capacities(assembly)
    assert split.inner + split.outer == pytest.approx(5e4, rel=1e-3)
    assert split.outer < 10.0
    assert assembly_u_factor(assembly, "roof") == pytest.approx(0.3, rel=1e-12)


# --- excluded zones (FR-013) ----------------------------------------------------------------


def _plenum_building(plenum_multiplier: int = 1, perimeter_multiplier: int = 1) -> list[ClassifiedZone]:
    plenum = _zone(
        "Plenum",
        _surface("P roof", "Roof", 0.0, "outdoors", area=100.0, u=0.2),
        _surface("P wall S", "Wall", 90.0, "outdoors", area=12.0, azimuth=180.0, u=0.5),
        _surface("P wall N", "Wall", 90.0, "outdoors", area=8.0, azimuth=0.0, u=0.5),
        _surface("P window", "Window", 90.0, "outdoors", area=2.0, azimuth=180.0, u=2.0, shgc=0.4, vt=0.6),
        _surface("P floor 1", "Floor", 180.0, "interzone", area=60.0, adjacent="Perimeter", layers=(GYPSUM,)),
        _surface("P floor 2", "Floor", 180.0, "interzone", area=40.0, adjacent="Core", layers=(GYPSUM,)),
        _surface("P mass", "Internal Mass", 90.0, "adiabatic", area=5.0, layers=(CONCRETE,)),
        multiplier=plenum_multiplier,
    )
    perimeter = _zone(
        "Perimeter",
        _surface("Pe wall", "Wall", 90.0, "outdoors", area=30.0, azimuth=180.0, u=0.5),
        _surface("Pe ceiling", "Ceiling", 0.0, "interzone", area=60.0, adjacent="Plenum", layers=(GYPSUM,)),
        multiplier=perimeter_multiplier,
        floor_area=60.0,
    )
    core = _zone(
        "Core",
        _surface("C ceiling", "Ceiling", 0.0, "interzone", area=40.0, adjacent="Plenum", layers=(GYPSUM,)),
        floor_area=40.0,
    )
    return [_classified(plenum, "excluded"), _classified(perimeter), _classified(core)]


def test_plenum_envelope_goes_to_neighbours_by_shared_area() -> None:
    zones = _plenum_building()
    hook = EnvelopeHook(zones)
    perimeter = _hooked(hook, zones[1])
    core = _hooked(hook, zones[2])
    # Perimeter shares 60 of 100 m² with the plenum, the core 40.
    assert perimeter.envelope["roof"].area == pytest.approx(60.0)
    assert core.envelope["roof"].area == pytest.approx(40.0)
    assert perimeter.envelope["exterior_wall"].area == pytest.approx(30.0 + 0.6 * 20.0)
    assert perimeter.envelope["exterior_wall"].area_by_orientation == pytest.approx({"S": 30 + 7.2, "N": 4.8})
    assert core.envelope["exterior_wall"].ua == pytest.approx(0.4 * 20.0 * 0.5)
    assert perimeter.window_by_orientation["S"].a_shgc == pytest.approx(0.6 * 2.0 * 0.4)
    # Interior surfaces and internal mass of the plenum are not assigned.
    assert perimeter.internal_mass_capacity == 0.0
    assert perimeter.envelope["floor_ceiling"].area == pytest.approx(60.0)
    # The assignment is recorded.
    records = {(r.source_zone, r.target_zone, r.envelope_class): r for r in perimeter.excluded_envelope}
    assert set(records) == {("Plenum", "Perimeter", "roof"), ("Plenum", "Perimeter", "exterior_wall")}
    assert records["Plenum", "Perimeter", "roof"].share == pytest.approx(0.6)
    assert records["Plenum", "Perimeter", "roof"].area == pytest.approx(60.0)


@pytest.mark.parametrize(("plenum_multiplier", "perimeter_multiplier"), [(1, 1), (10, 10), (4, 2)])
def test_plenum_assignment_conserves_envelope_with_multipliers(
    plenum_multiplier: int, perimeter_multiplier: int
) -> None:
    zones = _plenum_building(plenum_multiplier, perimeter_multiplier)
    hook = EnvelopeHook(zones)
    ledger = sum(_hooked(hook, zone) for zone in zones[1:])
    assert isinstance(ledger, GroupLedger)
    m = plenum_multiplier
    assert ledger.envelope["roof"].area == pytest.approx(100.0 * m)
    assert ledger.envelope["roof"].ua == pytest.approx(20.0 * m)
    assert ledger.envelope["exterior_wall"].area == pytest.approx(30.0 * perimeter_multiplier + 20.0 * m)
    assert ledger.window_by_orientation["S"].area == pytest.approx(2.0 * m)
    assert sum(r.area for r in ledger.excluded_envelope if r.envelope_class == "roof") == pytest.approx(100.0 * m)


def test_excluded_zone_without_conditioned_neighbour_passes_through_excluded_neighbours() -> None:
    attic = _zone(
        "Attic",
        _surface("A roof", "Roof", 20.0, "outdoors", area=50.0, u=0.2),
        _surface("A floor", "Floor", 180.0, "interzone", area=50.0, adjacent="Plenum", layers=(GYPSUM,)),
    )
    zones = [*_plenum_building(), _classified(attic, "attic")]
    hook = EnvelopeHook(zones)
    perimeter = _hooked(hook, zones[1])
    # The plenum's roof (100) plus the attic's (50), both split 60/40.
    assert perimeter.envelope["roof"].area == pytest.approx(0.6 * 150.0)
    sources = {r.source_zone for r in perimeter.excluded_envelope}
    assert sources == {"Plenum", "Attic"}


def test_isolated_excluded_zone_falls_back_to_floor_area() -> None:
    shed = _zone("Shed", _surface("S roof", "Roof", 0.0, "outdoors", area=10.0, u=0.3))
    zones = [*_plenum_building(), _classified(shed, "excluded")]
    hook = EnvelopeHook(zones)
    perimeter = _hooked(hook, zones[1])
    shed_records = [r for r in perimeter.excluded_envelope if r.source_zone == "Shed"]
    assert len(shed_records) == 1
    assert shed_records[0].share == pytest.approx(0.6)  # 60 of 100 m² of conditioned floor


def test_basement_is_not_assigned_by_default() -> None:
    basement = _zone(
        "Basement",
        _surface("B slab", "Floor", 180.0, "ground", area=100.0, u=0.3),
        _surface("B ceiling", "Ceiling", 0.0, "interzone", area=100.0, adjacent="Core", layers=(CONCRETE,)),
    )
    zones = [*_plenum_building(), _classified(basement, "basement")]
    core = _hooked(EnvelopeHook(zones), zones[2])
    assert "ground_floor" not in core.envelope
    core = _hooked(EnvelopeHook(zones, assigned_roles={"excluded", "attic", "basement"}), zones[2])
    assert core.envelope["ground_floor"].area == pytest.approx(100.0)


def test_module_hook_matches_envelope_hook_without_excluded_zones() -> None:
    zones = _plenum_building()[1:]
    hook = EnvelopeHook(zones)
    for zone in zones:
        assert _hooked(hook, zone) == GroupLedger.from_zone(zone, NO_SCHEDULES, hooks=[ledger_fields])


# --- on a fixture --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ten_classified() -> list[ClassifiedZone]:
    sources = load_sources(MODELS / "ten_zone_multipliers.idf", MODELS / "ten_zone_multipliers.sql")
    evaluate = ScheduleEvaluator(sources.model, sources.run_period.calendar, base_path=MODELS)
    return list(classify(build_inventory(sources, evaluate), evaluate))


def test_fixture_conserves_exterior_envelope_of_conditioned_plenums_and_attic(
    ten_classified: list[ClassifiedZone],
) -> None:
    hook = EnvelopeHook(ten_classified)
    conditioned = [zone for zone in ten_classified if zone.role == "conditioned"]
    ledger = sum(_hooked(hook, zone) for zone in conditioned)
    assert isinstance(ledger, GroupLedger)
    carried = [zone for zone in ten_classified if zone.role in {"conditioned", "excluded", "attic"}]
    for klass in ("exterior_wall", "roof"):
        expected_area = sum(
            s.area * z.zone.multiplier for z in carried for s in z.zone.surfaces if envelope_class(s) == klass
        )
        expected_ua = sum(
            s.area * s.u_factor * z.zone.multiplier
            for z in carried
            for s in z.zone.surfaces
            if envelope_class(s) == klass
        )
        assert ledger.envelope[klass].area == pytest.approx(expected_area, rel=1e-12)
        assert ledger.envelope[klass].ua == pytest.approx(expected_ua, rel=1e-12)
    windows = sum(s.area * z.zone.multiplier for z in carried for s in z.zone.surfaces if s.surface_class == "window")
    assert sum(w.area for w in ledger.window_by_orientation.values()) == pytest.approx(windows, rel=1e-12)
    # Every class in the ledger yields an equivalent construction reproducing its U.
    for klass, totals in ledger.envelope.items():
        assembly = equivalent_construction(totals, klass)
        assert assembly_u_factor(assembly, klass) * totals.area == pytest.approx(totals.ua, rel=1e-9)
        assert math.isclose(
            sum(assembly_capacities(assembly)) * totals.area,
            totals.capacity_inner + totals.capacity_outer,
            rel_tol=1e-9,
        )
