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

from archetypal.reduction.classify import ClassifiedZone
from archetypal.reduction.hotwater import (
    MAINS_VARIABLE,
    HotWaterHook,
    allocations,
    hot_water_totals,
    ledger_fields,
    supply_temperature,
)
from archetypal.reduction.inventory import HotWaterRecord, ZoneRecord
from archetypal.reduction.ledger import GroupLedger

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction.schedules import Profile, ScheduleEvaluator
    from archetypal.reduction.sources import SourceData

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
HOURS = 24


def step(hours: int, before: float, after: float) -> Profile:
    """`before` for the first `hours` hours of each day, `after` for the rest."""
    return np.array([before if h % 24 < hours else after for h in range(HOURS)], dtype=np.float64)


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
    return scale * step(7, 0.0, 1.0)


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
def ten_detailed(
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]:
    return detailed("ten_zone_multipliers")


@pytest.fixture(scope="module")
def ten_sources(ten_detailed: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]) -> SourceData:
    return ten_detailed[0]


def _raw(sources: SourceData, variable: str, key: str) -> Profile:
    return np.asarray(sources.results.get_timeseries(variable, key, frequency="Hourly").values, dtype=np.float64)


def test_fixture_conserves_volume_and_heat(
    ten_detailed: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator],
) -> None:
    ten_sources, zones, evaluator = ten_detailed
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
    assert all(a.rule == "zone" and a.share * a.multiplier == pytest.approx(1.0) for a in zoned)


def test_allocations_report_the_rule_the_inventory_used() -> None:
    # People with a zero schedule: the inventory fell back to floor area, which the report must say.
    people = SimpleNamespace(kind="people", design_level=10.0)
    record = HotWaterRecord("Building Hot Water", np.ones(2), None, 1.0, allocated=True, rule="floor-area")
    zone = SimpleNamespace(zone=SimpleNamespace(name="A", multiplier=1, gains=(people,), hot_water=(record,)))
    (entry,) = allocations([zone])  # pyright: ignore[reportArgumentType]
    assert entry.rule == "floor-area"


def test_an_equipment_without_a_temperature_schedule_draws_at_the_water_heater_setpoint() -> None:
    from idfkit import load_idf  # noqa: PLC0415
    from idfkit.versioned import as_version  # noqa: PLC0415

    from archetypal.reduction.hotwater import supply_schedules  # noqa: PLC0415

    doc = as_version(load_idf(MODELS / "ten_zone_multipliers.idf"), since="22.1")
    for connection in doc["WaterUse:Connections"]:
        connection.hot_water_supply_temperature_schedule_name = None
    for equipment in doc.water_use_equipments:
        equipment.hot_water_supply_temperature_schedule_name = None
        equipment.target_temperature_schedule_name = None
    (heater,) = doc["WaterHeater:Mixed"]
    schedules = supply_schedules(doc)
    assert set(schedules.values()) == {heater.setpoint_temperature_schedule_name}


def test_connected_equipment_draws_at_the_water_heater_setpoint_before_its_target() -> None:
    from idfkit import load_idf  # noqa: PLC0415
    from idfkit.versioned import as_version  # noqa: PLC0415

    from archetypal.reduction.hotwater import supply_schedules  # noqa: PLC0415

    doc = as_version(load_idf(MODELS / "ten_zone_multipliers.idf"), since="22.1")
    connected: set[str] = set()
    for connection in doc["WaterUse:Connections"]:
        connection.hot_water_supply_temperature_schedule_name = None
        connected |= {
            str(entry["water_use_equipment_name"]).casefold() for entry in connection.data.get("connections") or ()
        }
    assert connected
    (heater,) = doc["WaterHeater:Mixed"]
    schedules = supply_schedules(doc)
    for equipment in doc.water_use_equipments:
        if equipment.name.casefold() in connected and equipment.target_temperature_schedule_name:
            assert schedules[equipment.name.casefold()] == heater.setpoint_temperature_schedule_name
