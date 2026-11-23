"""Tests for the energy delivered by HVAC equipment (spec 002, FR-022, research R12)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

import numpy as np
import pytest

from archetypal.reduction.delivery import delivered_energy, equipment_outputs

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from archetypal.reduction.sources import SourceData


@pytest.fixture(scope="module")
def sources(detailed: Callable[[str], Any]) -> Callable[[str], SourceData]:
    """The checked sources of a fixture, shared with the session's other tests."""
    return lambda name: detailed(name)[0]


@pytest.fixture(scope="module")
def multipliers_of(detailed: Callable[[str], Any]) -> Callable[[str], dict[str, int]]:
    """Every zone's multiplier, from the fixture's (session-cached) inventory."""
    return lambda name: {zone.zone.name: zone.zone.multiplier for zone in detailed(name)[1]}


@pytest.fixture(scope="module")
def ten(sources: Callable[[str], SourceData]) -> SourceData:
    return sources("ten_zone_multipliers")


def _raw(sources: SourceData, variable: str, key: str) -> float:
    (series,) = sources.results.get_timeseries_many([(variable, key, "Hourly")])
    return float(np.sum(series.values))


def test_equipment_outputs_follow_zone_equipment_terminals_and_air_loops(ten: SourceData) -> None:
    outputs = equipment_outputs(ten.model)
    heating = "Heating Coil Heating Energy"
    cooling = "Cooling Coil Total Cooling Energy"
    # A terminal's reheat coil belongs to the terminal's zone.
    assert outputs.zones["typical_perimeter"] == (("heating", heating, "Typical_Perimeter Reheat Coil"),)
    # A PTHP's coils, its supplemental heater included, belong to its zone.
    assert set(outputs.zones["top_core"]) == {
        ("heating", heating, "Top_Core PTHP Heat Pump Coil"),
        ("heating", heating, "Top_Core PTHP Backup Heater"),
        ("cooling", cooling, "Top_Core PTHP Cooling Coil"),
    }
    # The air loop's coil (heat recovery is no coil) is split later, by inlet flow.
    assert outputs.loops == {"vav": (("cooling", cooling, "VAV Cooling Coil"),)}
    assert outputs.unmeasured == ()


def test_every_coil_is_delivered_to_zones_exactly(
    ten: SourceData, multipliers_of: Callable[[str], dict[str, int]]
) -> None:
    multipliers = multipliers_of("ten_zone_multipliers")
    delivery = delivered_energy(ten, multipliers)
    modes: tuple[tuple[Literal["heating", "cooling"], str], ...] = (
        ("heating", "Heating Coil Heating Energy"),
        ("cooling", "Cooling Coil Total Cooling Energy"),
    )
    for mode, variable in modes:
        coils = sum(_raw(ten, variable, name) for v, name in ten.facts.hvac_outputs if v == variable)
        zones = sum(multipliers[name] * float(np.sum(profile)) for name, profile in delivery.zones[mode].items())
        assert zones == pytest.approx(coils, rel=1e-9)
    assert delivery.unassigned == ()


def test_equipment_outputs_cover_every_copy_and_are_divided_by_the_multiplier(
    ten: SourceData, multipliers_of: Callable[[str], dict[str, int]]
) -> None:
    multipliers = multipliers_of("ten_zone_multipliers")
    delivery = delivered_energy(ten, multipliers)
    reheat = _raw(ten, "Heating Coil Heating Energy", "Typical_Perimeter Reheat Coil")
    assert multipliers["Typical_Perimeter"] == 10
    assert delivery.annual("Typical_Perimeter")["heating"] == pytest.approx(reheat / 10)
    # Plenums and the attic have no equipment and no inlet flow.
    assert delivery.annual("G_Plenum") == {"heating": 0.0, "cooling": 0.0}
    assert delivery.annual("Attic") == {"heating": 0.0, "cooling": 0.0}


def test_multiplied_and_explicit_models_deliver_the_same_energy_per_copy(
    ten: SourceData, sources: Callable[[str], SourceData], multipliers_of: Callable[[str], dict[str, int]]
) -> None:
    explicit = sources("ten_zone_explicit")
    multiplied = delivered_energy(ten, multipliers_of("ten_zone_multipliers"))
    drawn = delivered_energy(explicit, multipliers_of("ten_zone_explicit"))
    for mode in ("heating", "cooling"):
        per_copy = multiplied.annual("Typical_Perimeter")[mode]
        floors = [drawn.annual(f"T{floor:02d}_Perimeter")[mode] for floor in range(1, 11)]
        assert per_copy == pytest.approx(float(np.mean(floors)), rel=0.05)


def test_zone_equipment_delivers_its_own_coils_and_ideal_loads(
    sources: Callable[[str], SourceData], multipliers_of: Callable[[str], dict[str, int]]
) -> None:
    three = sources("three_zone")
    delivery = delivered_energy(three, multipliers_of("three_zone"))
    assert delivery.annual("Core")["heating"] == pytest.approx(
        _raw(three, "Heating Coil Heating Energy", "Core PTAC Heating Coil")
    )
    bar = sources("bar_building")
    delivery = delivered_energy(bar, multipliers_of("bar_building"))
    ideal = _raw(bar, "Zone Ideal Loads Supply Air Total Cooling Energy", "North_Perimeter Ideal Loads")
    assert delivery.annual("North_Perimeter")["cooling"] == pytest.approx(ideal)
    # Outdoor air is part of what the equipment delivers: more than the zone air's sensible load.
    sensible = _raw(bar, "Zone Air System Sensible Heating Energy", "North_Perimeter")
    assert delivery.annual("North_Perimeter")["heating"] > 1.2 * sensible


_OUTDOOR_AIR_UNIT = """Version, 24.2;
Zone, Zone 1;
ZoneHVAC:EquipmentConnections,
  Zone 1, Zone 1 Equipment, Zone 1 Inlets, , Zone 1 Air Node, Zone 1 Return;
ZoneHVAC:EquipmentList,
  Zone 1 Equipment, SequentialLoad,
  ZoneHVAC:OutdoorAirUnit, OA Unit 1, 1, 1, , ;
ZoneHVAC:OutdoorAirUnit,
  OA Unit 1, , Zone 1, 0.5, , OA Unit Fan, BlowThrough, , , , NeutralControl, , ,
  OA Node, Zone 1 Inlets, OA Unit Return, Fan Outlet, OA Unit Equipment, ;
ZoneHVAC:OutdoorAirUnit:EquipmentList,
  OA Unit Equipment,
  Coil:Heating:Electric, OA Unit Heating Coil,
  Coil:Cooling:Water, OA Unit Cooling Coil;
Coil:Heating:Electric,
  OA Unit Heating Coil, , 1.0, 10000, Fan Outlet, Heating Outlet;
Coil:Cooling:Water,
  OA Unit Cooling Coil, , autosize, autosize, autosize, autosize, autosize, autosize, autosize,
  CW Inlet, CW Outlet, Heating Outlet, Zone 1 Inlets;
"""

_EVAPORATIVE = """Version, 24.2;
Zone, Zone 1;
ZoneHVAC:EquipmentConnections,
  Zone 1, Zone 1 Equipment, Zone 1 Inlets, , Zone 1 Air Node, Zone 1 Return;
ZoneHVAC:EquipmentList,
  Zone 1 Equipment, SequentialLoad,
  ZoneHVAC:HybridUnitaryHVAC, Hybrid 1, 1, 1, , ;
ZoneHVAC:HybridUnitaryHVAC,
  Hybrid 1;
"""


def test_an_outdoor_air_unit_delivers_the_coils_of_its_equipment_list(tmp_path: Path) -> None:
    from idfkit import load_idf  # noqa: PLC0415
    from idfkit.versioned import as_version  # noqa: PLC0415

    path = tmp_path / "oau.idf"
    path.write_text(_OUTDOOR_AIR_UNIT)
    outputs = equipment_outputs(as_version(load_idf(path), since="22.1"))
    names = {name for _, _, name in outputs.zones["zone 1"]}
    assert names == {"OA Unit Heating Coil", "OA Unit Cooling Coil"}


def test_hybrid_units_are_listed_as_unmeasured(tmp_path: Path) -> None:
    from idfkit import load_idf  # noqa: PLC0415
    from idfkit.versioned import as_version  # noqa: PLC0415

    path = tmp_path / "hybrid.idf"
    path.write_text(_EVAPORATIVE)
    assert equipment_outputs(as_version(load_idf(path), since="22.1")).unmeasured == ("Hybrid 1",)
