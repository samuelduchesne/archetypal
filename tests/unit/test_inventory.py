"""Tests for the zone inventory (spec 002, T029; data-model.md, ZoneRecord; research R1, R2, R11)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from idfkit import load_idf
from idfkit.versioned import as_version

from archetypal.reduction._sql_tables import (
    read_construction_layers,
    read_constructions,
    read_materials,
    read_nominal_infiltration,
    read_nominal_loads,
    read_zones,
)
from archetypal.reduction.inventory import (
    GainRecord,
    HotWaterRecord,
    SurfaceRecord,
    ThermostatRecord,
    build_inventory,
    surface_class,
)
from archetypal.reduction.schedules import ScheduleEvaluator
from archetypal.reduction.sources import load_sources

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.inventory import ZoneRecord
    from archetypal.reduction.sources import SourceData

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"


@pytest.fixture(scope="module")
def three_sources(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> SourceData:
    return detailed("three_zone")[0]


@pytest.fixture(scope="module")
def three(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> dict[str, ZoneRecord]:
    """The inventory of the session's cached classification (the same records `build_inventory` built)."""
    return {zone.zone.name: zone.zone for zone in detailed("three_zone")[1]}


@pytest.fixture(scope="module")
def ten_sources(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> SourceData:
    return detailed("ten_zone_multipliers")[0]


@pytest.fixture(scope="module")
def ten(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> dict[str, ZoneRecord]:
    """The inventory of the session's cached classification (the same records `build_inventory` built)."""
    return {zone.zone.name: zone.zone for zone in detailed("ten_zone_multipliers")[1]}


def _raw_series(sources: SourceData, variable: str, key: str) -> np.ndarray:
    series = sources.results.get_timeseries(variable, key, frequency="Hourly")
    return np.asarray(series.values, dtype=np.float64)


# --- One record per zone, multipliers and areas --------------------------------------------------


def test_one_record_per_zone_in_results_order(ten_sources: SourceData) -> None:
    zones = build_inventory(ten_sources)
    rows = read_zones(ten_sources.results)
    assert len(zones) == len(rows) == 10
    assert [zone.name.upper() for zone in zones] == [row.name for row in rows]
    # Names take the model's spelling, not the upper-case results spelling.
    assert [zone.name for zone in zones][:3] == ["Basement", "G_Perimeter", "G_Core"]


def test_multiplier_is_zone_times_list_multiplier(ten: dict[str, ZoneRecord]) -> None:
    assert ten["Typical_Perimeter"].multiplier == 10
    assert ten["Typical_Core"].multiplier == 10  # 5 x ZoneGroup multiplier 2
    assert ten["Typical_Plenum"].multiplier == 10
    assert {name for name, zone in ten.items() if zone.multiplier == 1} == {
        "Basement",
        "G_Perimeter",
        "G_Core",
        "G_Plenum",
        "Top_Perimeter",
        "Top_Core",
        "Attic",
    }


def test_floor_area_volume_and_min_z_are_one_copy(ten: dict[str, ZoneRecord], ten_sources: SourceData) -> None:
    rows = {row.name: row for row in read_zones(ten_sources.results)}
    for zone in ten.values():
        row = rows[zone.name.upper()]
        assert zone.floor_area == row.floor_area
        assert zone.volume == row.volume
        assert zone.min_z == row.minimum_z
    assert ten["Typical_Perimeter"].floor_area == ten["G_Perimeter"].floor_area == 456.0
    assert ten["Basement"].min_z == -3.0


# --- Surfaces -------------------------------------------------------------------------------------


def test_surfaces_carry_envelope_summary_figures(three: dict[str, ZoneRecord]) -> None:
    windows = [s for s in three["North_Perimeter"].surfaces if s.surface_class == "window"]
    assert len(windows) == 3
    for window in windows:
        assert window.u_factor == pytest.approx(2.001)
        assert window.shgc == pytest.approx(0.401)
        assert window.visible_transmittance is not None
        assert window.u_source == "envelope_summary"
        assert window.heat_capacity == 0.0
    interior = next(s for s in three["Core"].surfaces if s.name == "CORE_WALL_03")
    assert interior.surface_class == "interior"
    assert interior.boundary == "interzone"
    assert interior.adjacent_zone is not None
    assert interior.u_factor == pytest.approx(1.824)


def test_ground_and_internal_mass_surfaces(three: dict[str, ZoneRecord], ten: dict[str, ZoneRecord]) -> None:
    classes = {s.surface_class for s in ten["Basement"].surfaces}
    assert {"ground_wall", "ground_floor"} <= classes
    floor = next(s for s in ten["Basement"].surfaces if s.surface_class == "ground_floor")
    assert floor.boundary == "ground"
    assert floor.u_factor == pytest.approx(3.779)
    mass = [s for s in three["Core"].surfaces if s.surface_class == "internal_mass"]
    assert len(mass) == 1
    assert mass[0].heat_capacity > 0


def test_heat_capacity_is_sum_of_rho_c_d(three: dict[str, ZoneRecord], three_sources: SourceData) -> None:
    sql = three_sources.results
    materials = {m.index: m for m in read_materials(sql)}
    constructions = {c.name: c for c in read_constructions(sql)}
    layers = read_construction_layers(sql)
    wall = next(s for s in three["North_Perimeter"].surfaces if s.surface_class == "exterior_wall")
    assert wall.construction is not None
    index = constructions[wall.construction].index
    expected = sum(
        materials[layer.material_index].density
        * materials[layer.material_index].specific_heat
        * materials[layer.material_index].thickness
        for layer in layers
        if layer.construction_index == index
    )
    assert wall.heat_capacity == pytest.approx(expected)
    assert wall.heat_capacity == pytest.approx(sum(layer.heat_capacity for layer in wall.layers))
    assert len(wall.layers) == sum(1 for layer in layers if layer.construction_index == index)


@pytest.mark.parametrize(
    ("class_name", "tilt", "boundary", "expected"),
    [
        ("Wall", 90.0, "outdoors", "exterior_wall"),
        ("Wall", 60.0, "outdoors", "exterior_wall"),
        ("Wall", 120.0, "outdoors", "exterior_wall"),
        ("Roof", 0.0, "outdoors", "roof"),
        ("Wall", 59.0, "outdoors", "roof"),
        ("Floor", 180.0, "outdoors", "exposed_floor"),
        ("Floor", 180.0, "ground", "ground_floor"),
        ("Wall", 90.0, "ground", "ground_wall"),
        ("Wall", 90.0, "interzone", "interior"),
        ("Floor", 180.0, "adiabatic", "interior"),
        ("Window", 90.0, "outdoors", "window"),
        ("Window", 90.0, "interzone", "interior"),
        ("Internal Mass", 90.0, "adiabatic", "internal_mass"),
    ],
)
def test_surface_class(class_name: str, tilt: float, boundary: str, expected: str) -> None:
    assert surface_class(class_name, tilt, boundary) == expected  # type: ignore[arg-type]


# --- Gains, airflow, thermostats ------------------------------------------------------------------


def test_gains_are_nominal_rows_without_multiplier(ten: dict[str, ZoneRecord], ten_sources: SourceData) -> None:
    rows = [r for r in read_nominal_loads(ten_sources.results) if r.zone_index == 5]  # Typical_Perimeter
    gains = ten["Typical_Perimeter"].gains
    assert len(gains) == len(rows) > 0
    assert sorted(g.design_level for g in gains) == sorted(r.design_level for r in rows)
    people = next(g for g in gains if g.kind == "people")
    assert isinstance(people, GainRecord)
    assert people.schedule is not None


def test_infiltration_with_coefficients(ten: dict[str, ZoneRecord], ten_sources: SourceData) -> None:
    rows = {r.object_name: r for r in read_nominal_infiltration(ten_sources.results)}
    (record,) = ten["Typical_Perimeter"].infiltration
    assert record.design_flow == rows["TYPICAL_PERIMETER INFILTRATION"].design_level
    assert record.schedule is not None
    assert (record.constant, record.temperature, record.velocity, record.velocity_squared) == (1.0, 0.0, 0.0, 0.0)
    assert ten["G_Core"].infiltration == ()


def test_thermostat_dispatch(three: dict[str, ZoneRecord], ten: dict[str, ZoneRecord]) -> None:
    thermostat = three["Core"].thermostat
    assert isinstance(thermostat, ThermostatRecord)
    assert thermostat.heating_schedule == "Heating Setpoint"
    assert thermostat.cooling_schedule == "Cooling Setpoint"
    assert thermostat.control_type_schedule == "Thermostat Control Type"
    assert [c.control_type for c in thermostat.controls] == [4]
    assert ten["Attic"].thermostat is None
    assert ten["G_Plenum"].thermostat is None


def test_thermostat_setpoints_follow_control_type(three: dict[str, ZoneRecord], three_sources: SourceData) -> None:
    evaluate = ScheduleEvaluator(three_sources.model, three_sources.run_period.calendar)
    thermostat = three["Core"].thermostat
    assert thermostat is not None
    heating, cooling = thermostat.setpoints(evaluate)
    control = evaluate("Thermostat Control Type")
    active = control == 4
    np.testing.assert_array_equal(heating[active], evaluate("Heating Setpoint")[active])
    np.testing.assert_array_equal(cooling[active], evaluate("Cooling Setpoint")[active])
    assert np.isnan(heating[~active]).all()


# --- Hourly results -------------------------------------------------------------------------------


def test_delivered_energy_is_the_equipments_for_one_copy(ten: dict[str, ZoneRecord], ten_sources: SourceData) -> None:
    # The reheat coil serves every copy of the x10 zone; heating comes only from it.
    raw = _raw_series(ten_sources, "Heating Coil Heating Energy", "TYPICAL_PERIMETER REHEAT COIL").sum()
    assert ten["Typical_Perimeter"].delivered["heating"] == pytest.approx(raw / 10)
    assert ten["Typical_Perimeter"].delivered["cooling"] > 0.0
    assert ten["Attic"].delivered == {"heating": 0.0, "cooling": 0.0}
    # A return plenum's transferred air is no delivery.
    assert ten["G_Plenum"].delivered == {"heating": 0.0, "cooling": 0.0}
    assert ten["G_Plenum"].plenum
    assert not ten["G_Core"].plenum


def test_outdoor_air_is_divided_by_the_multiplier(ten: dict[str, ZoneRecord], ten_sources: SourceData) -> None:
    variable = "Zone Mechanical Ventilation Standard Density Volume Flow Rate"
    raw = _raw_series(ten_sources, variable, "TYPICAL_PERIMETER")
    np.testing.assert_allclose(ten["Typical_Perimeter"].outdoor_air * 10, raw)
    np.testing.assert_allclose(ten["G_Core"].outdoor_air, _raw_series(ten_sources, variable, "G_CORE"))
    # A zone without equipment connections reports none: zeros.
    assert not ten["Attic"].outdoor_air.any()
    assert ten["Attic"].outdoor_air.shape == raw.shape


def test_design_outdoor_air_rates(three: dict[str, ZoneRecord], ten: dict[str, ZoneRecord]) -> None:
    assert three["Core"].outdoor_air_per_person == pytest.approx(0.0025)
    assert three["Core"].outdoor_air_per_area == pytest.approx(0.0003)
    assert ten["Attic"].outdoor_air_per_person == 0.0


def test_hot_water_conserves_volume(ten: dict[str, ZoneRecord], ten_sources: SourceData) -> None:
    variable = "Water Use Equipment Hot Water Volume"
    zoned = _raw_series(ten_sources, variable, "TYPICAL_CORE RESTROOM HOT WATER")
    (record,) = [r for r in ten["Typical_Core"].hot_water if not r.allocated]
    assert isinstance(record, HotWaterRecord)
    assert record.share == 1.0
    assert record.target_temperature_schedule == "SHW Target Temperature"
    np.testing.assert_allclose(record.volume * ten["Typical_Core"].multiplier, zoned)

    building = _raw_series(ten_sources, variable, "BUILDING HOT WATER")
    allocated = [(zone, r) for zone in ten.values() for r in zone.hot_water if r.allocated]
    assert allocated
    assert sum(r.share * zone.multiplier for zone, r in allocated) == pytest.approx(1.0)
    total = sum(r.volume * zone.multiplier for zone, r in allocated)
    np.testing.assert_allclose(total, building)
    # Occupant-hours drive the allocation: zones without people receive none.
    assert all(any(g.kind == "people" for g in zone.gains) for zone, _ in allocated)


# --- Space types ----------------------------------------------------------------------------------


def test_space_type_when_all_spaces_agree(three: dict[str, ZoneRecord], ten: dict[str, ZoneRecord]) -> None:
    assert three["Core"].space_type == "Office"
    assert three["North_Perimeter"].space_type == "Office"
    assert three["South_Perimeter"].space_type == "Conference"
    assert ten["G_Core"].space_type is None  # no Space objects


def test_space_type_unset_when_spaces_disagree() -> None:
    doc = as_version(load_idf(MODELS / "three_zone.idf"), since="22.1")
    for space in doc.spaces:
        if space.name == "Core_East_Space":
            space.space_type = "Storage"
    zones = {z.name: z for z in build_inventory(load_sources(doc, MODELS / "three_zone.sql"))}
    assert zones["Core"].space_type is None
    assert zones["Core"].space_types == ("Storage", "Office")  # Core_East_Space, Core_West_Space
    assert zones["North_Perimeter"].space_type == "Office"


def test_records_are_frozen(three: dict[str, ZoneRecord]) -> None:
    zone = three["Core"]
    with pytest.raises(AttributeError):
        zone.multiplier = 2  # type: ignore[misc]
    assert all(isinstance(s, SurfaceRecord) for s in zone.surfaces)
