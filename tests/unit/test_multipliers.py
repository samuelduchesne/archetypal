"""Zone multipliers against every floor drawn (spec 002, T043; US1 acceptance scenario 3, FR-012).

`ten_zone_multipliers` and `ten_zone_explicit` are the same building, modelled once with zone
multipliers and once with every floor drawn (tests/fixtures/SOURCES.md). Their reductions must
give the same groups, floor areas and FR-014 to FR-021 totals within 0.1 %.

What the two models cannot agree on, and how it is compared instead:

- **Simulation results** (FR-022, FR-022a). The two runs differ: adiabatic floors in one are
  interzone in the other. Their difference, `delta`, is the largest relative difference between
  the two runs' building meters, read from the results (about 3 %). Building totals of delivered
  and consumed energy and fan energy and volume, and each group's efficiencies, specific fan
  power and supply-air temperatures, are compared within `delta`. The fit's slope and reference
  temperature (`efficiency.eir_linear`) are second-order and not compared.
- **Mechanical outdoor air each hour** (FR-019) is reported by the simulation per zone and its
  split between core and perimeter follows each run's zone loads, so it agrees within 0.1 % for
  the building, and only within `delta`-sized differences per group; its design flow agrees
  exactly per group.
- **Interior floors** (`floor_ceiling`) are adiabatic in one model and interzone in the other;
  EnergyPlus's U-factor with films differs between the two boundary conditions, so their UA is
  not compared. They are not an FR-016 class; their area and heat capacity (FR-017) are.
- **Hot water each hour** (FR-021) is the simulated volume drawn at each hour's tank
  temperature, which follows each run; its annual volume and heat agree within 0.1 %.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

from archetypal.reduction.ledger import GroupLedger

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction import Reduction
    from archetypal.reduction.report import ReductionReport
    from archetypal.reduction.sources import SourceData

RTOL = 1e-3
"""FR-014 to FR-021: 0.1 %."""

EXTERIOR_CLASSES = ("exterior_wall", "roof", "exposed_floor", "ground_floor", "ground_wall")
METERS = (
    "Heating:NaturalGas",
    "Heating:Electricity",
    "Cooling:Electricity",
    "Fans:Electricity",
    "Pumps:Electricity",
    "WaterSystems:NaturalGas",
)
SIMULATED_RULES = frozenset({
    "efficiency.delivered_over_consumed",
    "fans.energy_per_volume",
    "fans.effective_supply_delta",
})

pytestmark = pytest.mark.timeout(30)  # the first test reduces the 37-zone model (about 6 s)


@pytest.fixture(scope="module")
def pair(reduced: Callable[[str], Reduction]) -> tuple[ReductionReport, ReductionReport]:
    return reduced("ten_zone_multipliers").report, reduced("ten_zone_explicit").report


@pytest.fixture(scope="module")
def delta(detailed: Callable[[str], Any]) -> float:
    """The largest relative difference between the two runs' building meters."""
    differences: list[float] = []
    for meter in METERS:
        totals: list[float] = []
        for fixture in ("ten_zone_multipliers", "ten_zone_explicit"):
            sources: SourceData = detailed(fixture)[0]
            (series,) = sources.results.get_timeseries_many([(meter, "*", "Hourly")])
            totals.append(math.fsum(series.values))
        differences.append(abs(totals[0] - totals[1]) / abs(totals[1]))
    return max(differences)


def _close(a: float, b: float, rtol: float = RTOL) -> bool:
    if b == 0.0:
        return a == 0.0
    return abs(a - b) <= rtol * abs(b)


def _pairs(report: ReductionReport, other: ReductionReport) -> list[tuple[GroupLedger, GroupLedger, str]]:
    assert [g.key for g in report.groups] == [g.key for g in other.groups]
    return [(a.ledger, b.ledger, a.name) for a, b in zip(report.groups, other.groups, strict=True)]


def test_simulations_differ_by_a_few_percent(delta: float) -> None:
    # tests/fixtures/SOURCES.md: delivered and consumed energy differ by 0.1-3.5 %.
    assert 0.0 < delta < 0.05


def test_same_groups_and_floor_areas(pair: tuple[ReductionReport, ReductionReport]) -> None:
    multiplied, explicit = pair
    assert [g.key for g in multiplied.groups] == [g.key for g in explicit.groups]
    for a, b in zip(multiplied.groups, explicit.groups, strict=True):
        assert _close(a.floor_area, b.floor_area)
        assert a.floor_area_share == pytest.approx(b.floor_area_share, rel=RTOL)
    assert _close(multiplied.building.conditioned_floor_area, explicit.building.conditioned_floor_area)
    assert multiplied.building.storey_ratio == pytest.approx(explicit.building.storey_ratio, rel=RTOL)
    # One typical floor times 10 counts like ten drawn floors.
    members = {m.zone: m.multiplier for g in multiplied.groups for m in g.members}
    assert members["Typical_Perimeter"] == 10
    assert members["Typical_Core"] == 10
    assert sum(len(g.members) for g in explicit.groups) == 24


def test_gains_are_equal(pair: tuple[ReductionReport, ReductionReport]) -> None:
    for a, b, name in _pairs(*pair):
        assert set(a.gains) == set(b.gains), name
        for kind, totals in b.gains.items():
            assert _close(a.gains[kind].installed, totals.installed), (name, kind)
            np.testing.assert_allclose(a.gains[kind].hourly, totals.hourly, rtol=RTOL, err_msg=f"{name} {kind}")
            for part in ("radiant", "latent", "lost"):
                assert _close(getattr(a.gains[kind], part), getattr(totals, part)), (name, kind, part)


def test_envelope_and_thermal_mass_are_equal(pair: tuple[ReductionReport, ReductionReport]) -> None:
    for a, b, name in _pairs(*pair):
        assert set(a.envelope) == set(b.envelope), name
        for envelope_class, totals in b.envelope.items():
            mine = a.envelope[envelope_class]
            assert _close(mine.area, totals.area), (name, envelope_class)
            assert _close(mine.capacity_inner + mine.capacity_outer, totals.capacity_inner + totals.capacity_outer)
            if envelope_class in EXTERIOR_CLASSES:
                assert _close(mine.ua, totals.ua), (name, envelope_class)
                assert mine.area_by_orientation.keys() == totals.area_by_orientation.keys()
                for orientation, area in totals.area_by_orientation.items():
                    assert _close(mine.area_by_orientation[orientation], area)
        assert set(a.window_by_orientation) == set(b.window_by_orientation), name
        for orientation, window in b.window_by_orientation.items():
            for field in ("area", "ua", "a_shgc", "a_vt"):
                assert _close(getattr(a.window_by_orientation[orientation], field), getattr(window, field))
        assert _close(a.internal_mass_capacity, b.internal_mass_capacity)
        assert _close(a.internal_mass_area, b.internal_mass_area)


def test_infiltration_setpoints_and_hot_water_are_equal(pair: tuple[ReductionReport, ReductionReport]) -> None:
    for a, b, name in _pairs(*pair):
        assert _close(a.infiltration.design_flow, b.infiltration.design_flow), name
        np.testing.assert_allclose(a.infiltration.hourly, b.infiltration.hourly, rtol=RTOL)
        assert _close(a.outdoor_air.design_flow, b.outdoor_air.design_flow), name
        for setpoint in ("heating_setpoint", "cooling_setpoint"):
            mine, theirs = getattr(a, setpoint), getattr(b, setpoint)
            assert _close(mine.weight, theirs.weight)
            np.testing.assert_allclose(mine.value, theirs.value, rtol=RTOL)
        assert _close(a.unheated_area, b.unheated_area)
        assert _close(a.uncooled_area, b.uncooled_area)
        np.testing.assert_allclose(a.hot_water.volume.sum(), b.hot_water.volume.sum(), rtol=RTOL)
        np.testing.assert_allclose(a.hot_water.heat.sum(), b.hot_water.heat.sum(), rtol=RTOL)


def test_building_outdoor_air_is_equal(pair: tuple[ReductionReport, ReductionReport], delta: float) -> None:
    multiplied, explicit = (sum((g.ledger for g in r.groups), GroupLedger()) for r in pair)
    assert _close(float(multiplied.outdoor_air.hourly.sum()), float(explicit.outdoor_air.hourly.sum()))
    # Per group, the split follows each run's zone loads.
    for a, b, name in _pairs(*pair):
        assert _close(float(a.outdoor_air.hourly.sum()), float(b.outdoor_air.hourly.sum()), rtol=3 * delta), name


def test_energy_and_fans_within_the_difference_of_the_simulations(
    pair: tuple[ReductionReport, ReductionReport], delta: float
) -> None:
    multiplied, explicit = (sum((g.ledger for g in r.groups), GroupLedger()) for r in pair)
    for mode, totals in explicit.energy.items():
        mine = multiplied.energy[mode]
        assert _close(mine.delivered, totals.delivered, rtol=delta), mode
        for fuel, consumed in totals.consumed_by_fuel.items():
            theirs = consumed + totals.unattributed.get(fuel, 0.0)
            assert _close(mine.consumed_by_fuel[fuel] + mine.unattributed.get(fuel, 0.0), theirs, rtol=delta)
    assert _close(multiplied.fans.energy, explicit.fans.energy, rtol=delta)
    assert _close(multiplied.fans.volume, explicit.fans.volume, rtol=delta)


def test_derived_efficiencies_and_fan_parameters_within_the_difference(
    pair: tuple[ReductionReport, ReductionReport], delta: float
) -> None:
    multiplied, explicit = pair
    theirs = {(p.group, p.path): p.value for p in explicit.parameters}
    compared = 0
    for parameter in multiplied.parameters:
        if parameter.rule not in SIMULATED_RULES or isinstance(parameter.value, (str, bool)):
            continue
        value = theirs[parameter.group, parameter.path]
        assert isinstance(parameter.value, float)
        assert isinstance(value, float)
        assert _close(parameter.value, value, rtol=delta), (parameter.group, parameter.path)
        compared += 1
    assert compared >= 10


def test_every_other_parameter_is_equal(pair: tuple[ReductionReport, ReductionReport]) -> None:
    """Parameters not derived from simulation results agree within 0.1 % (or exactly)."""
    multiplied, explicit = pair
    theirs = {(p.group, p.path): p.value for p in explicit.parameters}
    assert set(theirs) == {(p.group, p.path) for p in multiplied.parameters}
    skipped_rules = SIMULATED_RULES | {"efficiency.eir_linear", "airflow.peak_per_area", "envelope.equivalent"}
    for parameter in multiplied.parameters:
        if parameter.rule in skipped_rules:
            continue
        value = theirs[parameter.group, parameter.path]
        if isinstance(parameter.value, float) and isinstance(value, float):
            assert _close(parameter.value, value), (parameter.group, parameter.path)
        else:
            assert parameter.value == value, (parameter.group, parameter.path)
