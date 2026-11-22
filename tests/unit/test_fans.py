"""Tests for fan energy and air volume (spec 002, T037; FR-022a, research R19)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from archetypal.reduction.classify import classify
from archetypal.reduction.fans import (
    AIR_SPECIFIC_HEAT,
    BuildingFans,
    FanSeries,
    attribute_fans,
    building_fans,
    effective_supply_delta,
    fans_hook,
    ledger_fields,
    specific_fan_power,
    standard_air_density,
)
from archetypal.reduction.inventory import build_inventory
from archetypal.reduction.ledger import FanTotals, GroupLedger
from archetypal.reduction.schedules import ScheduleEvaluator
from archetypal.reduction.sources import load_sources

if TYPE_CHECKING:
    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.sources import SourceData

MODELS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "models"
RHO = standard_air_density(0.0)


def _a(*values: float) -> np.ndarray:
    return np.asarray(values, dtype=np.float64)


def _data(fans: tuple[FanSeries, ...], **overrides: object) -> BuildingFans:
    """Zones A (multiplier 1) and B (multiplier 2) over three hours."""
    values: dict[str, object] = {
        "fans": fans,
        "inlet_flow": {"A": _a(1.0, 0.0, 1.0), "B": _a(3.0, 2.0, 0.0)},
        "multipliers": {"A": 1, "B": 2},
        "floor_area": {"A": 100.0, "B": 50.0},
        "delivered": {
            "heating": {"A": _a(1000.0, 0.0, 0.0), "B": _a(0.0, 500.0, 0.0)},
            "cooling": {"A": _a(0.0, 0.0, 0.0), "B": _a(300.0, 0.0, 0.0)},
        },
        "outdoor_air": {"A": _a(0.1, 0.0, 0.0), "B": _a(0.0, 0.0, 0.0)},
        "air_density": RHO,
    }
    values.update(overrides)
    return BuildingFans(**values)  # pyright: ignore[reportArgumentType]


LOOP = FanSeries("AHU fan", energy=_a(400.0, 200.0, 100.0), mass_flow=_a(4.0, 2.0, 1.0), loop_zones=("A", "B"))


def test_standard_density_is_energyplus_std_rho_air() -> None:
    assert pytest.approx(1.2041, abs=1e-4) == RHO
    assert standard_air_density(1000.0) < RHO


def test_zone_equipment_fan_belongs_to_its_zone_per_copy() -> None:
    fan = FanSeries("PTHP fan", energy=_a(60.0, 0.0, 0.0), mass_flow=_a(0.5, 0.0, 0.0), zone="B")
    result = attribute_fans(_data((fan,)))
    assert result.zones["B"].energy == pytest.approx(30.0)  # outputs cover every copy
    assert result.zones["B"].volume == pytest.approx(0.25 * 3600 / RHO)
    assert result.zones["A"].energy == 0.0


def test_air_loop_fan_is_split_by_hourly_inlet_node_flow() -> None:
    result = attribute_fans(_data((LOOP,)))
    # hour 0: A 1/4, B 3/4 (all copies); hour 1: B only; hour 2: A only.
    assert result.zones["A"].energy == pytest.approx(100.0 + 100.0)
    assert result.zones["B"].energy == pytest.approx((300.0 + 200.0) / 2)
    total = sum(result.multipliers_applied(z).energy for z in ("A", "B"))
    assert total == pytest.approx(700.0)
    volume = sum(result.multipliers_applied(z).volume for z in ("A", "B"))
    assert volume == pytest.approx(7.0 * 3600 / RHO)


def test_hours_without_inlet_flow_fall_back_to_the_annual_share() -> None:
    data = _data((LOOP,), inlet_flow={"A": _a(0.0, 0.0, 0.0), "B": _a(0.0, 1.0, 0.0)})
    result = attribute_fans(data)
    assert result.zones["B"].energy * 2 + result.zones["A"].energy == pytest.approx(700.0)


def test_specific_fan_power_times_volume_is_fan_energy() -> None:
    result = attribute_fans(_data((LOOP,)))
    group = result.zones["A"] + result.zones["B"].scaled(2)
    sfp = specific_fan_power(group)
    assert sfp is not None
    assert sfp * group.volume == pytest.approx(700.0)
    assert specific_fan_power(FanTotals()) is None


def test_volume_per_mode_and_effective_supply_delta() -> None:
    result = attribute_fans(_data((LOOP,)))
    a = result.zones["A"]
    # A heats in hour 0 only: volume 1 kg/s * 3600 / rho, delivered 1000 J.
    assert a.volume_in_mode["heating"] == pytest.approx(3600 / RHO)
    assert a.delivered_in_mode["heating"] == pytest.approx(1000.0)
    delta = effective_supply_delta(a, "heating", air_density=RHO)
    assert delta == pytest.approx(1000.0 / (RHO * AIR_SPECIFIC_HEAT * 3600 / RHO))
    assert effective_supply_delta(a, "cooling", air_density=RHO) is None
    b = result.zones["B"]
    assert b.volume_in_mode["cooling"] == pytest.approx(1.5 * 3600 / RHO)
    assert b.volume_in_mode["heating"] == pytest.approx(1.0 * 3600 / RHO)


def test_volume_without_demand_is_reported() -> None:
    result = attribute_fans(_data((LOOP,)))
    # A: hour 2 has neither load nor outdoor air; hour 0 has a load.
    assert result.zones["A"].volume_without_demand == pytest.approx(1.0 * 3600 / RHO)
    assert result.zones["B"].volume_without_demand == 0.0


def test_unmatched_fans_are_reported() -> None:
    orphan = FanSeries("lost fan", energy=_a(5.0, 5.0, 5.0), mass_flow=_a(1.0, 1.0, 1.0))
    result = attribute_fans(_data((orphan,)))
    assert result.unattributed_energy == pytest.approx(15.0)
    assert result.unattributed_fans == ("lost fan",)


def test_the_module_hook_needs_building_data() -> None:
    with pytest.raises(ValueError, match="fans_hook"):
        ledger_fields(None, None)  # pyright: ignore[reportArgumentType]


# --- fixtures -------------------------------------------------------------------------------------


def _load(model: str) -> tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]:
    sources = load_sources(MODELS / f"{model}.idf", MODELS / f"{model}.sql")
    evaluate = ScheduleEvaluator(sources.model, sources.run_period.calendar)
    return sources, classify(build_inventory(sources, evaluate), evaluate), evaluate


@pytest.fixture(scope="module")
def ten() -> tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]:
    return _load("ten_zone_multipliers")


@pytest.fixture(scope="module")
def three() -> tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]:
    return _load("three_zone")


def _series(sources: SourceData, name: str, key: str) -> np.ndarray:
    (series,) = sources.results.get_timeseries_many([(name, key, "Hourly")])
    return np.asarray(series.values, dtype=np.float64)


def test_fixture_fans_are_assigned(ten: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]) -> None:
    sources, zones, _ = ten
    data = building_fans(sources, zones)
    by_name = {fan.name.upper(): fan for fan in data.fans}
    assert by_name["TOP_CORE PTHP FAN"].zone == "Top_Core"
    assert set(by_name["VAV SUPPLY FAN"].loop_zones) == {"G_Perimeter", "G_Core", "Typical_Perimeter", "Typical_Core"}
    assert set(data.inlet_flow) == {"G_Perimeter", "G_Core", "Typical_Perimeter", "Typical_Core"}


def test_fixture_fan_energy_and_volume_are_conserved(
    ten: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator],
) -> None:
    sources, zones, evaluate = ten
    hook = fans_hook(sources, zones)
    ledgers = [GroupLedger.from_zone(z, evaluate, hooks=[hook]) for z in zones if z.conditioned]
    total = sum(ledgers, GroupLedger()).fans
    (meter,) = sources.results.get_timeseries_many([("Fans:Electricity", "*", "Hourly")])
    assert total.energy == pytest.approx(float(np.sum(meter.values)), rel=1e-9)
    flow = sum(
        _series(sources, "Fan Air Mass Flow Rate", key).sum()
        for key in ("VAV SUPPLY FAN", "TOP_CORE PTHP FAN", "TOP_PERIMETER PTHP FAN")
    )
    assert total.volume == pytest.approx(flow * 3600 / hook.air_density, rel=1e-6)
    sfp = specific_fan_power(total)
    assert sfp is not None
    assert sfp * total.volume == pytest.approx(total.energy)
    vav = _series(sources, "Fan Electricity Energy", "VAV SUPPLY FAN").sum()
    vav_zones = sum(
        hook.multipliers_applied(name).energy for name in ("G_Perimeter", "G_Core", "Typical_Perimeter", "Typical_Core")
    )
    assert vav_zones == pytest.approx(vav, rel=1e-6)
    assert 0.0 <= total.volume_without_demand <= total.volume
    delta = effective_supply_delta(total, "heating", air_density=hook.air_density)
    assert delta is not None
    assert 0.0 < delta < 40.0


def test_fixture_zone_equipment_fans_three_zone(
    three: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator],
) -> None:
    sources, zones, _ = three
    hook = fans_hook(sources, zones)
    for zone in ("Core", "North_Perimeter", "South_Perimeter"):
        key = f"{zone} PTAC Fan".upper()
        assert hook.zones[zone].energy == pytest.approx(_series(sources, "Fan Electricity Energy", key).sum())
    assert hook.unattributed_fans == ()
