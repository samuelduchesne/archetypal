"""Tests for thermostat setpoints (spec 002, T034; research R10; FR-020)."""

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
from archetypal.reduction.inventory import ThermostatControl, ThermostatRecord, ZoneRecord, build_inventory
from archetypal.reduction.ledger import GroupLedger
from archetypal.reduction.schedules import ScheduleEvaluator
from archetypal.reduction.sources import load_sources
from archetypal.reduction.thermostats import BAND, ledger_fields, setpoint_fields

if TYPE_CHECKING:
    from archetypal.reduction.schedules import Profile

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
HOURS = 24


def step(hours: int, before: float, after: float) -> Profile:
    """`before` for the first `hours` hours of each day, `after` for the rest."""
    return np.array([before if h % 24 < hours else after for h in range(HOURS)], dtype=np.float64)


@dataclass
class FakeEvaluator:
    """A schedule evaluator over a fixed table, with a calendar of HOURS hours."""

    table: dict[str, Profile]
    calendar: Any = field(default_factory=lambda: SimpleNamespace(hours=HOURS))
    doc: Any = None

    def __call__(self, name: str) -> Profile:
        return self.table[name.upper()]


def _dual(heating: str, cooling: str, control: str = "DUAL") -> ThermostatRecord:
    return ThermostatRecord(
        name="T",
        control_type_schedule=control,
        heating_schedule=heating,
        cooling_schedule=cooling,
        controls=(ThermostatControl(4, "ThermostatSetpoint:DualSetpoint", "D", heating, cooling),),
    )


def _zone(name: str, area: float, thermostat: ThermostatRecord | None, multiplier: int = 1) -> ClassifiedZone:
    record = ZoneRecord(
        name=name, multiplier=multiplier, floor_area=area, min_z=0.0, volume=3 * area, thermostat=thermostat
    )
    return ClassifiedZone(record, True, "conditioned", "core", "office", "signature", "test")


def _table(**profiles: Profile) -> dict[str, Profile]:
    base: dict[str, Profile] = {"DUAL": np.full(HOURS, 4.0)}
    base.update({k.upper(): v for k, v in profiles.items()})
    return base


def test_band_is_five_to_thirty_five() -> None:
    assert BAND == (5.0, 35.0)


def test_heated_and_cooled_zone_enters_both_means() -> None:
    heat = step(8, 15.0, 21.0)
    evaluator = FakeEvaluator(_table(heat=heat, cool=np.full(HOURS, 24.0)))
    fields = setpoint_fields(_zone("A", 50.0, _dual("HEAT", "COOL")), evaluator)
    assert fields["heating_setpoint"].weight == 50.0
    np.testing.assert_allclose(fields["heating_setpoint"].weighted, 50.0 * heat)
    np.testing.assert_allclose(fields["cooling_setpoint"].weighted, 50.0 * 24.0)
    assert fields["unheated_area"] == 0.0
    assert fields["uncooled_area"] == 0.0


def test_a_setpoint_that_disables_a_mode_keeps_the_zone_out_of_that_mean() -> None:
    evaluator = FakeEvaluator(_table(off=np.full(HOURS, -100.0), cool=np.full(HOURS, 24.0)))
    fields = setpoint_fields(_zone("A", 40.0, _dual("OFF", "COOL")), evaluator)
    assert fields["heating_setpoint"].weight == 0.0
    assert fields["heating_setpoint"].weighted.size == 0
    assert fields["unheated_area"] == 40.0
    assert fields["cooling_setpoint"].weight == 40.0
    assert fields["uncooled_area"] == 0.0


def test_a_zone_without_thermostat_is_neither_heated_nor_cooled() -> None:
    fields = setpoint_fields(_zone("A", 30.0, None), FakeEvaluator(_table()))
    assert fields["heating_setpoint"].weight == 0.0
    assert fields["cooling_setpoint"].weight == 0.0
    assert fields["unheated_area"] == 30.0
    assert fields["uncooled_area"] == 30.0


def test_hours_outside_the_band_are_clamped_to_it() -> None:
    # Heated by day (21 °C), set back to -100 °C (off) at night; cooled by day, 100 °C at night.
    heat = step(8, -100.0, 21.0)
    cool = step(8, 100.0, 24.0)
    evaluator = FakeEvaluator(_table(heat=heat, cool=cool))
    fields = setpoint_fields(_zone("A", 1.0, _dual("HEAT", "COOL")), evaluator)
    np.testing.assert_allclose(fields["heating_setpoint"].weighted, step(8, 5.0, 21.0))
    np.testing.assert_allclose(fields["cooling_setpoint"].weighted, step(8, 35.0, 24.0))


def test_uncontrolled_hours_take_the_band_edge_that_leaves_the_mode_off() -> None:
    control = step(6, 0.0, 4.0)
    evaluator = FakeEvaluator(_table(ctl=control, heat=np.full(HOURS, 20.0), cool=np.full(HOURS, 25.0)))
    fields = setpoint_fields(_zone("A", 1.0, _dual("HEAT", "COOL", control="CTL")), evaluator)
    np.testing.assert_allclose(fields["heating_setpoint"].weighted, step(6, 5.0, 20.0))
    np.testing.assert_allclose(fields["cooling_setpoint"].weighted, step(6, 35.0, 25.0))


@given(
    st.lists(
        st.tuples(st.floats(1.0, 1000.0), st.sampled_from(["HEAT", "OFF"]), st.integers(1, 5)),
        min_size=1,
        max_size=6,
    )
)
def test_group_mean_is_area_weighted_over_heated_members_only(members: list[tuple[float, str, int]]) -> None:
    evaluator = FakeEvaluator(
        _table(heat=np.linspace(18.0, 22.0, HOURS), off=np.full(HOURS, -50.0), cool=np.full(HOURS, 26.0))
    )
    hooks = [ledger_fields]
    ledgers = [
        GroupLedger.from_zone(_zone(f"Z{i}", area, _dual(heat, "COOL"), mult), evaluator, hooks=hooks)  # pyright: ignore[reportArgumentType]
        for i, (area, heat, mult) in enumerate(members)
    ]
    group = sum(ledgers)
    assert isinstance(group, GroupLedger)
    heated = sum(area * mult for area, heat, mult in members if heat == "HEAT")
    unheated = sum(area * mult for area, heat, mult in members if heat == "OFF")
    assert group.heating_setpoint.weight == pytest.approx(heated)
    assert group.unheated_area == pytest.approx(unheated)
    assert group.uncooled_area == 0.0
    if heated:
        mean = group.heating_setpoint.value
        assert mean is not None
        np.testing.assert_allclose(mean, np.linspace(18.0, 22.0, HOURS))
    else:
        assert group.heating_setpoint.value is None
    assert (group.heating_setpoint.weight + group.unheated_area) == pytest.approx(group.floor_area)


def test_three_zone_fixture() -> None:
    sources = load_sources(MODELS / "three_zone.idf", MODELS / "three_zone.sql")
    evaluator = ScheduleEvaluator(sources.model, sources.run_period.calendar)
    zones = classify(build_inventory(sources, evaluator), evaluator)
    for zone in zones:
        fields = ledger_fields(zone, evaluator)
        thermostat = zone.zone.thermostat
        assert thermostat is not None
        heating, cooling = thermostat.setpoints(evaluator)
        assert fields["heating_setpoint"].weight == zone.zone.floor_area
        weighted = fields["heating_setpoint"].weighted
        assert weighted.size == sources.run_period.calendar.hours
        in_band = (heating >= 5.0) & (heating <= 35.0)
        np.testing.assert_allclose(weighted[in_band], zone.zone.floor_area * heating[in_band])
        assert fields["cooling_setpoint"].weight == zone.zone.floor_area
        assert bool((fields["cooling_setpoint"].weighted / zone.zone.floor_area <= 35.0).all())
        assert cooling.size == weighted.size
