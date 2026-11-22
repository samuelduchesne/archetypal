"""Tests for the energy delivered by HVAC equipment (spec 002, FR-022, research R12)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Literal

import numpy as np
import pytest

from archetypal.reduction.delivery import delivered_energy, equipment_outputs
from archetypal.reduction.inventory import build_inventory

if TYPE_CHECKING:
    from archetypal.reduction.sources import SourceData

from archetypal.reduction.sources import load_sources

MODELS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "models"


def _sources(name: str) -> SourceData:
    return load_sources(MODELS / f"{name}.idf", MODELS / f"{name}.sql")


@pytest.fixture(scope="module")
def ten() -> SourceData:
    return _sources("ten_zone_multipliers")


def _raw(sources: SourceData, variable: str, key: str) -> float:
    (series,) = sources.results.get_timeseries_many([(variable, key, "Hourly")])
    return float(np.sum(series.values))


def _multipliers(sources: SourceData) -> dict[str, int]:
    return {zone.name: zone.multiplier for zone in build_inventory(sources)}


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


def test_every_coil_is_delivered_to_zones_exactly(ten: SourceData) -> None:
    multipliers = _multipliers(ten)
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


def test_equipment_outputs_cover_every_copy_and_are_divided_by_the_multiplier(ten: SourceData) -> None:
    multipliers = _multipliers(ten)
    delivery = delivered_energy(ten, multipliers)
    reheat = _raw(ten, "Heating Coil Heating Energy", "Typical_Perimeter Reheat Coil")
    assert multipliers["Typical_Perimeter"] == 10
    assert delivery.annual("Typical_Perimeter")["heating"] == pytest.approx(reheat / 10)
    # Plenums and the attic have no equipment and no inlet flow.
    assert delivery.annual("G_Plenum") == {"heating": 0.0, "cooling": 0.0}
    assert delivery.annual("Attic") == {"heating": 0.0, "cooling": 0.0}


def test_multiplied_and_explicit_models_deliver_the_same_energy_per_copy(ten: SourceData) -> None:
    explicit = _sources("ten_zone_explicit")
    multiplied = delivered_energy(ten, _multipliers(ten))
    drawn = delivered_energy(explicit, _multipliers(explicit))
    for mode in ("heating", "cooling"):
        per_copy = multiplied.annual("Typical_Perimeter")[mode]
        floors = [drawn.annual(f"T{floor:02d}_Perimeter")[mode] for floor in range(1, 11)]
        assert per_copy == pytest.approx(float(np.mean(floors)), rel=0.05)


def test_zone_equipment_delivers_its_own_coils_and_ideal_loads() -> None:
    three = _sources("three_zone")
    delivery = delivered_energy(three, _multipliers(three))
    assert delivery.annual("Core")["heating"] == pytest.approx(
        _raw(three, "Heating Coil Heating Energy", "Core PTAC Heating Coil")
    )
    bar = _sources("bar_building")
    delivery = delivered_energy(bar, _multipliers(bar))
    ideal = _raw(bar, "Zone Ideal Loads Supply Air Total Cooling Energy", "North_Perimeter Ideal Loads")
    assert delivery.annual("North_Perimeter")["cooling"] == pytest.approx(ideal)
    # Outdoor air is part of what the equipment delivers: more than the zone air's sensible load.
    sensible = _raw(bar, "Zone Air System Sensible Heating Energy", "North_Perimeter")
    assert delivery.annual("North_Perimeter")["heating"] > 1.2 * sensible
