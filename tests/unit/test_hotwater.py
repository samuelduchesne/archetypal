"""Tests for domestic hot water (spec 002, T035; research R11; FR-021)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from archetypal.reduction.classify import ClassifiedZone, classify
from archetypal.reduction.hotwater import (
    MAINS_VARIABLE,
    HotWaterHook,
    allocations,
    hot_water_totals,
    ledger_fields,
    supply_temperature,
)
from archetypal.reduction.inventory import HotWaterRecord, ZoneRecord, build_inventory
from archetypal.reduction.ledger import GroupLedger
from archetypal.reduction.schedules import ScheduleEvaluator
from archetypal.reduction.sources import load_sources

if TYPE_CHECKING:
    from archetypal.reduction.schedules import Profile
    from archetypal.reduction.sources import SourceData

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
HOURS = 24


@dataclass
class FakeEvaluator:
    table: dict[str, Profile]
    calendar: Any = field(default_factory=lambda: SimpleNamespace(hours=HOURS))
    doc: Any = None

    def __call__(self, name: str) -> Profile:
        return self.table[name.upper()]


MAINS = np.linspace(8.0, 14.0, HOURS)
SCHEDULES: dict[str, Profile] = {"TARGET": np.full(HOURS, 43.0), "SUPPLY": np.full(HOURS, 60.0)}


def _zone(name: str, records: tuple[HotWaterRecord, ...], multiplier: int = 1) -> ClassifiedZone:
    record = ZoneRecord(name=name, multiplier=multiplier, floor_area=10.0, min_z=0.0, volume=30.0, hot_water=records)
    return ClassifiedZone(record, True, "conditioned", "core", "office", "signature", "test")


def _volume(scale: float) -> Profile:
    return scale * np.where(np.arange(HOURS) % 24 >= 7, 1.0, 0.0)


def test_heat_is_volume_times_rise_above_mains() -> None:
    volume = _volume(0.01)
    zone = _zone("A", (HotWaterRecord("Sink", volume, "TARGET", 1.0, allocated=False),))
    totals = hot_water_totals(zone, FakeEvaluator(SCHEDULES), MAINS, {"sink": "SUPPLY"})
    np.testing.assert_allclose(totals.volume, volume)
    np.testing.assert_allclose(totals.heat, volume * (60.0 - MAINS))


def test_target_temperature_is_used_without_a_hot_water_supply_schedule() -> None:
    volume = _volume(0.01)
    zone = _zone("A", (HotWaterRecord("Sink", volume, "TARGET", 1.0, allocated=False),))
    totals = hot_water_totals(zone, FakeEvaluator(SCHEDULES), MAINS, {})
    np.testing.assert_allclose(totals.heat, volume * (43.0 - MAINS))


def test_a_zone_without_hot_water_contributes_nothing_and_needs_no_mains() -> None:
    fields = ledger_fields(_zone("A", ()), FakeEvaluator(SCHEDULES))  # pyright: ignore[reportArgumentType]
    assert fields["hot_water"].volume.size == 0
    assert fields["hot_water"].mean_rise is None


def test_the_default_hook_refuses_hot_water_without_mains() -> None:
    zone = _zone("A", (HotWaterRecord("Sink", _volume(0.01), "TARGET", 1.0, allocated=False),))
    with pytest.raises(ValueError, match="HotWaterHook"):
        ledger_fields(zone, FakeEvaluator(SCHEDULES))  # pyright: ignore[reportArgumentType]


def test_supply_temperature_is_mean_mains_plus_volume_weighted_rise() -> None:
    hook = HotWaterHook(mains=MAINS, supply_schedules={"sink": "SUPPLY"})
    big = _volume(0.02)
    small = np.full(HOURS, 0.001)
    evaluator = FakeEvaluator(SCHEDULES)
    a = GroupLedger.from_zone(_zone("A", (HotWaterRecord("Sink", big, None, 1.0, False),)), evaluator, hooks=[hook])  # pyright: ignore[reportArgumentType]
    b = GroupLedger.from_zone(  # pyright: ignore[reportArgumentType]
        _zone("B", (HotWaterRecord("Shower", small, "TARGET", 1.0, False),), multiplier=2),
        evaluator,  # pyright: ignore[reportArgumentType]
        hooks=[hook],
    )
    group = (a + b).hot_water
    rise = (np.sum(big * (60.0 - MAINS)) + 2 * np.sum(small * (43.0 - MAINS))) / (big.sum() + 2 * small.sum())
    assert group.mean_rise == pytest.approx(rise)
    assert supply_temperature(group, MAINS) == pytest.approx(float(MAINS.mean()) + rise)
    assert supply_temperature(GroupLedger().hot_water, MAINS) is None


@given(st.lists(st.tuples(st.floats(0.0, 0.1), st.integers(1, 10), st.booleans()), min_size=1, max_size=6))
def test_group_volume_and_heat_are_conserved(members: list[tuple[float, int, bool]]) -> None:
    hook = HotWaterHook(mains=MAINS, supply_schedules={})
    evaluator = FakeEvaluator(SCHEDULES)
    ledgers = [
        GroupLedger.from_zone(  # pyright: ignore[reportArgumentType]
            _zone(f"Z{i}", (HotWaterRecord("E", _volume(scale), "TARGET" if target else "SUPPLY", 1.0, False),), m),
            evaluator,  # pyright: ignore[reportArgumentType]
            hooks=[hook],
        )
        for i, (scale, m, target) in enumerate(members)
    ]
    group = sum(ledgers)
    assert isinstance(group, GroupLedger)
    volume = sum(m * _volume(s) for s, m, _ in members)
    heat = sum(m * _volume(s) * ((43.0 if t else 60.0) - MAINS) for s, m, t in members)
    np.testing.assert_allclose(group.hot_water.volume, volume, atol=1e-15)
    np.testing.assert_allclose(group.hot_water.heat, heat, atol=1e-12)


# --- Fixture: zoneless equipment allocated by occupant-hours ---------------------------------------


@pytest.fixture(scope="module")
def ten_sources() -> SourceData:
    return load_sources(MODELS / "ten_zone_multipliers.idf", MODELS / "ten_zone_multipliers.sql")


def _raw(sources: SourceData, variable: str, key: str) -> Profile:
    return np.asarray(sources.results.get_timeseries(variable, key, frequency="Hourly").values, dtype=np.float64)


def test_fixture_conserves_volume_and_heat(ten_sources: SourceData) -> None:
    evaluator = ScheduleEvaluator(ten_sources.model, ten_sources.run_period.calendar)
    zones = classify(build_inventory(ten_sources, evaluator), evaluator)
    hook = HotWaterHook.from_sources(ten_sources)
    mains = _raw(ten_sources, MAINS_VARIABLE, "Environment")
    np.testing.assert_allclose(hook.mains, mains)
    total = sum(GroupLedger.from_zone(zone, evaluator, hooks=[hook]) for zone in zones)
    assert isinstance(total, GroupLedger)

    expected_volume = np.zeros_like(mains)
    expected_heat = np.zeros_like(mains)
    for equipment in ten_sources.model.water_use_equipments:
        volume = _raw(ten_sources, "Water Use Equipment Hot Water Volume", equipment.name.upper())
        schedule = equipment.hot_water_supply_temperature_schedule_name or equipment.target_temperature_schedule_name
        assert schedule
        expected_volume += volume
        expected_heat += volume * (evaluator(schedule) - mains)
    np.testing.assert_allclose(total.hot_water.volume, expected_volume, rtol=1e-9, atol=1e-15)
    np.testing.assert_allclose(total.hot_water.heat, expected_heat, rtol=1e-9, atol=1e-12)

    # The allocation of building-wide equipment is recorded for the report.
    recorded = allocations(zones)
    zoneless = [a for a in recorded if a.allocated]
    assert zoneless
    assert {a.equipment for a in zoneless} == {"Building Hot Water"}
    assert sum(a.share * a.multiplier for a in zoneless) == pytest.approx(1.0)
    assert all(a.rule == "occupant-hours" for a in zoneless)
    building = _raw(ten_sources, "Water Use Equipment Hot Water Volume", "BUILDING HOT WATER")
    assert sum(a.volume for a in zoneless) == pytest.approx(float(building.sum()))
    zoned = [a for a in recorded if not a.allocated]
    assert all(a.rule == "zone" and a.share == 1.0 for a in zoned)
