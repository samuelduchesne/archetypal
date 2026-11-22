"""Regression tests for the stand-in diagnosis (specs/002-reduce-to-sbem/verification/stand-in-diagnosis.md).

Each test pins one root cause found by comparing the fixtures' detailed runs with their
archetypes' runs:

- the hot-water efficiency must divide the detailed consumption by the heat at the hot-water
  supply temperature, the same heat the archetype's hot-water supply temperature gives back;
- the ideal loads' heating and cooling capacities must not be left to epinterface's autosizing,
  which clipped the morning-recovery peak of `three_zone` by 20 %;
- daylighting, which the archetype does not hold, must be quantified in the report;
- the ground temperatures, which the archetype does not hold, must be listed;
- the verification shoebox must not draw a core for an archetype that has none.
"""

from __future__ import annotations

import importlib.util
import math
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction import Reduction

WATER_VOLUMETRIC_HEAT = 1000.0 * 4180.0
"""rho·c_p of water, J/(m³·K), as the reduction uses it."""


def _meter(sources: Any, name: str) -> float:
    (series,) = sources.results.get_timeseries_many([(name, "*", "Hourly")])
    return math.fsum(float(v) for v in series.values)


def _verification_report() -> Any:
    path = Path(__file__).resolve().parents[2] / "verification" / "report.py"
    spec = importlib.util.spec_from_file_location("verification_report_for_tests", path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module  # dataclasses look their module up
    spec.loader.exec_module(module)
    return module


# --- hot water --------------------------------------------------------------------------------------


def test_hot_water_delivered_heat_uses_the_hot_water_supply_temperature(
    detailed: Callable[[str], Any],
) -> None:
    """`ten_zone_multipliers` draws 60 °C water to reach 43 °C; the heat follows the 60 °C water."""
    from archetypal.reduction.efficiency import building_energy  # noqa: PLC0415
    from archetypal.reduction.hotwater import HotWaterHook  # noqa: PLC0415

    sources, zones, evaluate = detailed("ten_zone_multipliers")
    hook = HotWaterHook.from_sources(sources)
    data = building_energy(sources, zones, evaluate)
    for zone in zones:
        if not zone.conditioned:
            continue
        expected = hook(zone, evaluate)["hot_water"].heat * WATER_VOLUMETRIC_HEAT
        delivered = data.delivered["hot_water"][zone.zone.name]
        np.testing.assert_allclose(delivered, expected if expected.size else 0.0, rtol=1e-9, atol=1e-6)


def test_archetype_hot_water_gives_back_the_detailed_consumption(
    reduced: Callable[..., Reduction], detailed: Callable[[str], Any]
) -> None:
    """Volume · (supply - inlet) · rho·c_p / efficiency over the groups is the WaterSystems meter."""
    sources, _, _ = detailed("ten_zone_multipliers")
    reduction = reduced("ten_zone_multipliers")
    consumed = 0.0
    for report_group, zone_group in zip(reduction.report.groups, reduction.archetype.Groups, strict=True):
        dhw = zone_group.Zone.Operations.DHW
        volume = float(report_group.ledger.hot_water.volume.sum())
        if volume == 0.0:
            continue
        rise = dhw.WaterSupplyTemperature - dhw.WaterTemperatureInlet
        consumed += volume * rise * WATER_VOLUMETRIC_HEAT / dhw.effective_system_cop
    assert consumed == pytest.approx(_meter(sources, "WaterSystems:NaturalGas"), rel=0.01)


# --- ideal-loads limits ----------------------------------------------------------------------------


@pytest.mark.parametrize("fixture", ["three_zone", "ten_zone_multipliers"])
def test_ideal_loads_capacity_is_not_autosized(fixture: str, reduced: Callable[..., Reduction]) -> None:
    """Heating follows the load; cooling keeps an autosized air flow (the economiser's bound) only."""
    reduction = reduced(fixture)
    paths = {(p.group, p.path): p for p in reduction.report.parameters}
    for group in reduction.archetype.Groups:
        systems = group.Zone.Operations.HVAC.ConditioningSystems
        assert systems.HeatingLimitType == "NoLimit"
        assert systems.CoolingLimitType == "LimitFlowRate"
        assert systems.MaxHeatingCapacityPerFloorArea is None
        assert systems.MaxCoolingCapacityPerFloorArea is None
        for field in ("HeatingLimitType", "CoolingLimitType"):
            key = (group.Name, f"Zone.Operations.HVAC.ConditioningSystems.{field}")
            assert key in paths, key
            assert paths[key].rule == "fans.effective_supply_delta"


# --- what the archetype does not hold ---------------------------------------------------------------


def _undimmed_and_actual_lighting(reduction: Reduction, sources: Any) -> tuple[float, float]:
    lights = [g.ledger.gains.get("lights") for g in reduction.report.groups]
    undimmed = math.fsum(float(np.sum(g.hourly)) * 3600.0 for g in lights if g is not None)
    rows = sources.results.get_tabular_data(
        "AnnualBuildingUtilityPerformanceSummary", "End Uses", report_for="Entire Facility"
    )
    (actual,) = [
        r.as_float() * 1.0e9 for r in rows if r.row_name == "Interior Lighting" and r.column_name == "Electricity"
    ]
    return undimmed, actual


def test_daylighting_saving_is_quantified(reduced: Callable[..., Reduction], detailed: Callable[[str], Any]) -> None:
    """`bar_building` dims its lights with daylight: the report gives the energy the archetype misses."""
    reduction = reduced("bar_building")
    sources, _, _ = detailed("bar_building")
    (entry,) = [n for n in reduction.report.not_represented if n.object_type == "Daylighting:Controls"]
    undimmed, actual = _undimmed_and_actual_lighting(reduction, sources)
    assert undimmed > actual
    assert entry.unit == "J"
    assert entry.magnitude == pytest.approx(undimmed - actual, rel=0.01)


def test_no_daylighting_no_saving(reduced: Callable[..., Reduction]) -> None:
    reduction = reduced("three_zone")
    assert not [n for n in reduction.report.not_represented if n.object_type == "Daylighting:Controls"]


@pytest.mark.parametrize("fixture", ["three_zone", "bar_building", "ten_zone_multipliers"])
def test_ground_temperatures_are_listed(fixture: str, reduced: Callable[..., Reduction]) -> None:
    """epinterface derives its own ground temperatures; the detailed model's are not carried."""
    reduction = reduced(fixture)
    (entry,) = [
        n for n in reduction.report.not_represented if n.object_type == "Site:GroundTemperature:BuildingSurface"
    ]
    assert entry.affected_zones
    assert entry.unit == "W/K"
    assert entry.magnitude is not None
    assert entry.magnitude > 0.0


# --- verification shoebox ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("fixture", "zoning"),
    [("bar_building", "by_storey"), ("three_zone", "core/perim"), ("ten_zone_multipliers", "core/perim")],
)
def test_shoebox_draws_a_core_only_for_a_core_group(
    fixture: str, zoning: str, reduced: Callable[..., Reduction]
) -> None:
    """`bar_building` is all perimeter: a core zone would hold 29 % of its floor without a facade."""
    report = _verification_report()
    archetype = reduced(fixture).archetype
    assert report.shoebox(archetype).zoning == zoning


@pytest.mark.parametrize(
    ("fixture", "served"),
    [
        ("ten_zone_multipliers", {"G_Core", "G_Perimeter", "Typical_Core", "Typical_Perimeter"}),
        ("three_zone", set[str]()),
        ("bar_building", set[str]()),
    ],
)
def test_air_side_control_of_central_systems_is_listed(
    fixture: str, served: set[str], reduced: Callable[..., Reduction]
) -> None:
    """`ten_zone_multipliers`' VAV supplies air at a reset temperature with reheat, which ideal loads do not."""
    entries = [n for n in reduced(fixture).report.not_represented if n.object_type == "AirLoopHVAC"]
    if not served:
        assert not entries
        return
    (entry,) = entries
    assert served <= set(entry.affected_zones)
    assert entry.affected_groups
