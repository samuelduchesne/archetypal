"""Tests for zone classification (spec 002, T030; research R4, R7, R8; FR-006, FR-007, FR-013)."""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from archetypal.errors import NoConditionedZones
from archetypal.reduction.classify import classify, exposure, space_use_signature
from archetypal.reduction.inventory import (
    GainRecord,
    SurfaceRecord,
    ThermostatControl,
    ThermostatRecord,
    ZoneRecord,
    surface_class,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.inventory import Boundary
    from archetypal.reduction.schedules import Profile, ScheduleEvaluator
    from archetypal.reduction.sources import SourceData

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
HOURS = 48

# --- Synthetic zones ------------------------------------------------------------------------------

SCHEDULES: dict[str, Profile] = {
    "ON": np.ones(HOURS),
    "HALF": np.full(HOURS, 0.5),
    "HEAT": np.full(HOURS, 21.0),
    "COOL": np.full(HOURS, 24.0),
    "HEAT_OFF": np.full(HOURS, -100.0),
    "COOL_OFF": np.full(HOURS, 100.0),
    "DUAL": np.full(HOURS, 4.0),
}


def evaluate(name: str) -> Profile:
    return SCHEDULES[name.upper()]


def _surface(
    name: str, class_name: str, tilt: float, boundary: Boundary, *, adjacent: str | None = None, area: float = 10.0
) -> SurfaceRecord:
    return SurfaceRecord(
        name=name,
        surface_class=surface_class(class_name, tilt, boundary),
        class_name=class_name,
        area=area,
        azimuth=0.0,
        tilt=tilt,
        boundary=boundary,
        adjacent_zone=adjacent,
        construction="C",
        u_factor=1.0,
        u_source="envelope_summary",
        heat_capacity=0.0,
    )


def _thermostat(heating: str = "HEAT", cooling: str = "COOL") -> ThermostatRecord:
    control = ThermostatControl(4, "ThermostatSetpoint:DualSetpoint", "Dual", heating, cooling)
    return ThermostatRecord("T", "DUAL", heating, cooling, (control,))


def _zone(
    name: str,
    *surfaces: SurfaceRecord,
    thermostat: ThermostatRecord | None = None,
    gains: tuple[GainRecord, ...] = (),
    delivered: float = 0.0,
    space_type: str | None = None,
    plenum: bool = False,
    floor_area: float = 100.0,
) -> ZoneRecord:
    return ZoneRecord(
        name=name,
        multiplier=1,
        floor_area=floor_area,
        min_z=0.0,
        volume=300.0,
        surfaces=surfaces,
        gains=gains,
        thermostat=thermostat,
        delivered={"heating": delivered, "cooling": 0.0},
        space_type=space_type,
        plenum=plenum,
        outdoor_air=np.zeros(HOURS),
    )


def _lights(level: float, schedule: str = "ON") -> GainRecord:
    return GainRecord("lights", "L", level, schedule, 0.7, 0.0, 0.0, 0.0)


OUTDOOR_WALL = _surface("W", "Wall", 90.0, "outdoors")
ROOF = _surface("R", "Roof", 0.0, "outdoors")


# --- Exposure (R7, FR-006) ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("surfaces", "expected"),
    [
        ((OUTDOOR_WALL,), "perimeter"),
        ((_surface("W", "Wall", 60.0, "outdoors"),), "perimeter"),
        ((_surface("W", "Wall", 120.0, "outdoors"),), "perimeter"),
        ((_surface("G", "Window", 90.0, "outdoors"),), "perimeter"),
        ((_surface("G", "Window", 0.0, "outdoors"),), "core"),  # a skylight: roofs never decide
        ((ROOF, _surface("G", "Window", 30.0, "outdoors")), "core"),  # a roof window
        ((ROOF,), "core"),
        ((_surface("W", "Wall", 59.0, "outdoors"),), "core"),  # a roof by tilt
        ((_surface("F", "Floor", 180.0, "outdoors"),), "core"),  # exposed floor
        ((_surface("F", "Floor", 180.0, "ground"), _surface("W", "Wall", 90.0, "ground")), "core"),
        ((_surface("W", "Wall", 90.0, "interzone", adjacent="B"),), "core"),
        ((), "core"),
    ],
)
def test_exposure(surfaces: tuple[SurfaceRecord, ...], expected: str) -> None:
    assert exposure(_zone("A", *surfaces)) == expected


# --- Roles (R8, FR-013) ---------------------------------------------------------------------------


def test_conditioned_by_thermostat_or_delivered_energy() -> None:
    zones = [
        _zone("A", OUTDOOR_WALL, thermostat=_thermostat()),
        _zone("B", OUTDOOR_WALL, delivered=1e6),
        _zone("C", OUTDOOR_WALL, thermostat=_thermostat("HEAT_OFF", "COOL_OFF")),
        _zone("D", OUTDOOR_WALL, delivered=1e6, plenum=True),
    ]
    result = {z.zone.name: z for z in classify(zones, evaluate)}
    assert result["A"].conditioned
    assert result["A"].role == "conditioned"
    assert result["B"].conditioned
    assert not result["C"].conditioned
    assert result["C"].role == "excluded"
    # A return plenum's delivered energy is transferred air, not conditioning.
    assert not result["D"].conditioned
    assert result["D"].role == "excluded"


def test_heating_only_thermostat_conditions() -> None:
    zone = _zone("A", OUTDOOR_WALL, thermostat=_thermostat("HEAT", "COOL_OFF"))
    (result,) = classify([zone], evaluate)
    assert result.conditioned


def test_attic_and_basement_roles() -> None:
    attic = _zone(
        "Attic",
        _surface("R1", "Roof", 20.0, "outdoors", area=60.0),
        _surface("F1", "Floor", 180.0, "interzone", adjacent="Office", area=50.0),
        _surface("W1", "Wall", 90.0, "outdoors", area=10.0),
    )
    walled = _zone(
        "Walled",
        _surface("R1", "Roof", 20.0, "outdoors", area=10.0),
        _surface("F1", "Floor", 180.0, "interzone", adjacent="Office", area=10.0),
        _surface("W1", "Wall", 90.0, "outdoors", area=30.0),
    )
    basement = _zone(
        "Basement",
        _surface("F1", "Floor", 180.0, "ground"),
        _surface("W1", "Wall", 90.0, "ground"),
        _surface("C1", "Ceiling", 0.0, "interzone", adjacent="Office"),
    )
    crawl = _zone(
        "Crawl", _surface("F1", "Floor", 180.0, "ground"), _surface("C1", "Ceiling", 0.0, "interzone", adjacent="Store")
    )
    office = _zone("Office", OUTDOOR_WALL, thermostat=_thermostat())
    store = _zone("Store", OUTDOOR_WALL)
    plenum_attic = replace(attic, name="PlenumAttic", plenum=True)
    result = {z.zone.name: z for z in classify([attic, walled, basement, crawl, office, store, plenum_attic], evaluate)}
    assert result["Attic"].role == "attic"
    assert result["Walled"].role == "excluded"  # exterior walls over 50 % of its envelope
    assert result["Basement"].role == "basement"
    assert result["Crawl"].role == "excluded"  # its ceiling is not under a conditioned zone
    assert result["Store"].role == "excluded"
    assert result["PlenumAttic"].role == "excluded"
    assert all(z.role_reason for z in result.values())


def test_no_conditioned_zones() -> None:
    with pytest.raises(NoConditionedZones):
        classify([_zone("A", OUTDOOR_WALL), _zone("B", ROOF)], evaluate, subject="model.idf")


# --- Space use (R4, FR-007) -----------------------------------------------------------------------


def test_three_tiers_and_sources() -> None:
    zones = [
        _zone("Z1", OUTDOOR_WALL, thermostat=_thermostat(), space_type="Office", gains=(_lights(1000.0),)),
        _zone("Z2", OUTDOOR_WALL, thermostat=_thermostat(), space_type="Office", gains=(_lights(2000.0),)),
        _zone("Z3", OUTDOOR_WALL, thermostat=_thermostat(), gains=(_lights(1000.0),)),
        _zone("Z4", ROOF, thermostat=_thermostat(), gains=(_lights(1000.0),)),
        _zone("Z5", ROOF, thermostat=_thermostat(), gains=(_lights(1000.0, "HALF"),)),
    ]
    result = {z.zone.name: z for z in classify(zones, evaluate, space_use_mapping={"z2": "Lab"})}
    assert (result["Z2"].space_use, result["Z2"].space_use_source) == ("Lab", "user")
    assert (result["Z1"].space_use, result["Z1"].space_use_source) == ("Office", "space_type")
    assert (result["Z3"].space_use, result["Z3"].space_use_source) == ("use:Z3", "signature")
    assert result["Z4"].space_use == "use:Z3"  # same loads, schedules and setpoints
    assert result["Z5"].space_use == "use:Z5"  # another lighting schedule
    assert result["Z3"].exposure == "perimeter"
    assert result["Z4"].exposure == "core"


def test_unknown_zone_in_mapping() -> None:
    zone = _zone("Z1", OUTDOOR_WALL, thermostat=_thermostat())
    with pytest.raises(ValueError, match="Nowhere"):
        classify([zone], evaluate, space_use_mapping={"Nowhere": "Lab"})


def test_a_mapping_that_names_one_zone_twice_with_two_uses_is_refused() -> None:
    zone = _zone("Z1", OUTDOOR_WALL, thermostat=_thermostat())
    with pytest.raises(ValueError, match="two space uses"):
        classify([zone], evaluate, space_use_mapping={"Z1": "Office", "z1": "Lobby"})
    (same,) = classify([zone], evaluate, space_use_mapping={"Z1": "Office", "z1": "Office"})
    assert same.space_use == "Office"


def test_rounding_noise_does_not_split_a_space_use() -> None:
    SCHEDULES["NOISY"] = np.ones(HOURS) * (1.0 - 1e-9)
    zones = [
        _zone("A", OUTDOOR_WALL, thermostat=_thermostat(), gains=(_lights(1000.0),)),
        _zone("B", OUTDOOR_WALL, thermostat=_thermostat(), gains=(_lights(1000.0 * (1 + 1e-9), "NOISY"),)),
        _zone("C", OUTDOOR_WALL, thermostat=_thermostat(), gains=(_lights(1001.0),)),
    ]
    result = {z.zone.name: z.space_use for z in classify(zones, evaluate)}
    assert result == {"A": "use:A", "B": "use:A", "C": "use:C"}


def test_signature_ignores_floor_area_scaling() -> None:
    small = _zone("A", OUTDOOR_WALL, thermostat=_thermostat(), gains=(_lights(1000.0),), floor_area=100.0)
    large = _zone("B", OUTDOOR_WALL, thermostat=_thermostat(), gains=(_lights(3000.0),), floor_area=300.0)
    assert space_use_signature(small, evaluate) == space_use_signature(large, evaluate)


_POOL = [
    _zone("Office1", OUTDOOR_WALL, thermostat=_thermostat(), gains=(_lights(1000.0),)),
    _zone("Office2", ROOF, thermostat=_thermostat(), gains=(_lights(1000.0),)),
    _zone("Lab", OUTDOOR_WALL, thermostat=_thermostat(), gains=(_lights(1000.0, "HALF"),)),
    _zone("Store", OUTDOOR_WALL, space_type="Storage", thermostat=_thermostat()),
    _zone("Attic", ROOF, _surface("F", "Floor", 180.0, "interzone", adjacent="Office2")),
    _zone("Plenum", OUTDOOR_WALL, plenum=True, delivered=5.0),
]


@given(st.permutations(_POOL))
def test_classification_does_not_depend_on_zone_order(zones: list[ZoneRecord]) -> None:
    assert classify(zones, evaluate) == classify(_POOL, evaluate)
    assert [z.zone.name for z in classify(zones, evaluate)] == sorted(z.name for z in _POOL)


# --- Fixtures -------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ten(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> dict[str, ClassifiedZone]:
    return {z.zone.name: z for z in detailed("ten_zone_multipliers")[1]}


def test_ten_zone_roles(ten: dict[str, ClassifiedZone]) -> None:
    roles = {name: zone.role for name, zone in ten.items()}
    assert roles == {
        "Attic": "attic",
        "Basement": "basement",
        "G_Core": "conditioned",
        "G_Perimeter": "conditioned",
        "G_Plenum": "excluded",
        "Top_Core": "conditioned",
        "Top_Perimeter": "conditioned",
        "Typical_Core": "conditioned",
        "Typical_Perimeter": "conditioned",
        "Typical_Plenum": "excluded",
    }


def test_ten_zone_exposure_and_space_use(ten: dict[str, ClassifiedZone]) -> None:
    conditioned = {name: zone for name, zone in ten.items() if zone.conditioned}
    assert {name: zone.exposure for name, zone in conditioned.items()} == {
        "G_Core": "core",
        "G_Perimeter": "perimeter",
        "Top_Core": "core",
        "Top_Perimeter": "perimeter",
        "Typical_Core": "core",
        "Typical_Perimeter": "perimeter",
    }
    assert {zone.space_use for zone in conditioned.values()} == {"use:G_Core"}
    assert {zone.space_use_source for zone in conditioned.values()} == {"signature"}


def test_three_zone_space_types(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> None:
    result = {z.zone.name: z for z in detailed("three_zone")[1]}
    assert {name: (z.space_use, z.space_use_source) for name, z in result.items()} == {
        "Core": ("Office", "space_type"),
        "North_Perimeter": ("Office", "space_type"),
        "South_Perimeter": ("Conference", "space_type"),
    }
    assert result["Core"].exposure == "core"
    assert result["South_Perimeter"].exposure == "perimeter"
