"""Tests for features SBEM cannot express (spec 002, T044; research R20; FR-026)."""

from __future__ import annotations

from pathlib import Path

import pytest
from idfkit import load_idf
from pydantic import ValidationError

from archetypal.reduction.features import UNSUPPORTED_FEATURES, NotRepresented, find_unsupported
from archetypal.reduction.sources import SourceData, load_sources

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"

# The fixture's Exterior:Lights consumption, as the LightingSummary table reports it (31.39 GJ).
EXTERIOR_LIGHTS_J = 31.39e9


def _sources(name: str) -> SourceData:
    return load_sources(MODELS / f"{name}.idf", MODELS / f"{name}.sql")


@pytest.fixture(scope="module")
def bar_building() -> tuple[NotRepresented, ...]:
    return find_unsupported(_sources("bar_building"))


def _entry(entries: tuple[NotRepresented, ...], object_type: str) -> NotRepresented:
    matches = [entry for entry in entries if entry.object_type == object_type]
    assert len(matches) == 1, f"{object_type}: {matches}"
    return matches[0]


def test_table_covers_research_r20() -> None:
    types = {feature.object_type for feature in UNSUPPORTED_FEATURES}
    for object_type in (
        "Daylighting:Controls",
        "Daylighting:ReferencePoint",
        "WindowShadingControl",
        "WindowMaterial:Shade",
        "WindowMaterial:Blind",
        "Shading:Site:Detailed",
        "Shading:Building:Detailed",
        "Shading:Zone:Detailed",
        "Shading:Overhang",
        "Shading:Fin",
        "ElectricEquipment:ITE:AirCooled",
        "SwimmingPool:Indoor",
        "Refrigeration:Case",
        "Refrigeration:WalkIn",
        "Exterior:Lights",
        "Exterior:FuelEquipment",
        "ZoneEarthtube",
        "ZoneAirMassFlowConservation",
    ):
        assert object_type in types
    assert len(types) == len(UNSUPPORTED_FEATURES), "each object type appears once"
    for feature in UNSUPPORTED_FEATURES:
        assert feature.effect


def test_daylighting_controls_listed_with_zones(bar_building: tuple[NotRepresented, ...]) -> None:
    entry = _entry(bar_building, "Daylighting:Controls")
    assert entry.affected_zones == ("North_Perimeter", "South_Perimeter")
    assert entry.objects == ("North_Perimeter Daylighting", "South_Perimeter Daylighting")
    assert entry.folded_into is None
    assert entry.source == "unsupported_features"


def test_daylighting_reference_points_listed(bar_building: tuple[NotRepresented, ...]) -> None:
    entry = _entry(bar_building, "Daylighting:ReferencePoint")
    assert entry.affected_zones == ("North_Perimeter", "South_Perimeter")


def test_exterior_lights_listed_with_annual_energy(bar_building: tuple[NotRepresented, ...]) -> None:
    entry = _entry(bar_building, "Exterior:Lights")
    assert entry.objects == ("Facade and Parking Lights",)
    assert entry.affected_zones == ()
    assert entry.magnitude == pytest.approx(EXTERIOR_LIGHTS_J, rel=1e-3)
    assert entry.unit == "J"


def test_only_present_features_listed(bar_building: tuple[NotRepresented, ...]) -> None:
    assert {entry.object_type for entry in bar_building} == {
        "Daylighting:Controls",
        "Daylighting:ReferencePoint",
        "Exterior:Lights",
        "Site:GroundTemperature:BuildingSurface",
    }


def test_entries_in_table_order(bar_building: tuple[NotRepresented, ...]) -> None:
    order = [feature.object_type for feature in UNSUPPORTED_FEATURES]
    found = [order.index(entry.object_type or "") for entry in bar_building]
    assert found == sorted(found)


def test_shading_resolves_zones_through_surfaces() -> None:
    doc = load_idf(MODELS / "bar_building.idf")
    doc.add("Shading:Overhang", "South Overhang", window_or_door_name="South_Perimeter_Wall_01_Window", depth=1.0)
    doc.add(
        "Shading:Site:Detailed",
        "Tree",
        vertices=[
            {"vertex_x_coordinate": 0.0, "vertex_y_coordinate": -5.0, "vertex_z_coordinate": 0.0},
            {"vertex_x_coordinate": 1.0, "vertex_y_coordinate": -5.0, "vertex_z_coordinate": 0.0},
            {"vertex_x_coordinate": 1.0, "vertex_y_coordinate": -5.0, "vertex_z_coordinate": 5.0},
        ],
    )
    entries = find_unsupported(load_sources(doc, MODELS / "bar_building.sql"))
    assert _entry(entries, "Shading:Overhang").affected_zones == ("South_Perimeter",)
    assert _entry(entries, "Shading:Site:Detailed").affected_zones == ("North_Perimeter", "South_Perimeter")


def test_three_zone_has_only_its_ground_temperatures() -> None:
    # Runs every reader of the table: a row without one raises KeyError.
    found = find_unsupported(_sources("three_zone"))
    assert [entry.object_type for entry in found] == ["Site:GroundTemperature:BuildingSurface"]


def test_not_represented_is_frozen_and_strict() -> None:
    entry = NotRepresented(feature="Fans", effect="fan energy", folded_into="DistributionCOP")
    assert entry.affected_zones == ()
    assert entry.magnitude is None
    with pytest.raises(ValidationError):
        entry.feature = "other"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        NotRepresented(feature="x", effect="y", unknown=1)  # type: ignore[call-arg]
    assert NotRepresented.model_validate_json(entry.model_dump_json()) == entry


def test_energy_units_convert_to_joules() -> None:
    from archetypal.reduction.features import _to_joules  # noqa: PLC0415  # pyright: ignore[reportPrivateUsage]

    assert _to_joules(1.0, "kBtu") == pytest.approx(1.05505585262e6)
    assert _to_joules(1.0, "kWh") == pytest.approx(3.6e6)
    assert _to_joules(1.0, "GJ") == pytest.approx(1e9)
