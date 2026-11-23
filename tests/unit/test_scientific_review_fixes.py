"""Regression tests for findings of the scientific review of the reduction's physics modules."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import numpy as np
import pytest

from archetypal.reduction.airflow import doas_loops
from archetypal.reduction.efficiency import (
    BuildingEnergy,
    _weighted_mean,  # pyright: ignore[reportPrivateUsage]
    attribute_energy,
)
from archetypal.reduction.envelope import window_construction
from archetypal.reduction.inventory import _mean_set  # pyright: ignore[reportPrivateUsage]
from archetypal.reduction.ledger import EnergyTotals, GroupLedger, HotWaterTotals, WindowTotals
from archetypal.reduction.schedules import (
    RunPeriodCalendar,
    parse_date,
    project,
    to_year_component,
    year_values,
)
from archetypal.reduction.to_sbem import dhw, storey_ratio, thermal_system

MODELS = Path(__file__).parents[1] / "fixtures" / "models"


def test_rated_efficiencies_combine_as_output_over_input() -> None:
    # Two chillers of equal capacity, COP 2 and 6: 2000 W delivered for 667 W consumed.
    assert _weighted_mean([(2.0, 1000.0), (6.0, 1000.0)]) == pytest.approx(3.0)
    # A water heater's weight is its input: output over input is the arithmetic mean.
    assert _weighted_mean([(0.8, 1000.0), (0.9, 1000.0)], weight_is_input=True) == pytest.approx(0.85)


def test_standby_is_shared_equally_without_delivery_or_floor_area() -> None:
    data = BuildingEnergy(
        outdoor_temperature=np.zeros(4),
        multipliers={"a": 1, "b": 2},
        floor_area={},
        delivered={},
        consumed={"heating": {"Electricity": np.ones(4)}},
    )
    result = attribute_energy(data)
    shared = sum(
        data.multipliers[name] * sum(result.zones[name]["heating"].unattributed.values()) for name in ("a", "b")
    )
    assert shared == pytest.approx(4.0)


def _joint(joint_fuels: frozenset[str] | None) -> BuildingEnergy:
    hours = 4
    return BuildingEnergy(
        outdoor_temperature=np.zeros(hours),
        multipliers={"a": 1},
        floor_area={"a": 10.0},
        delivered={
            "heating": {"a": np.array([3.0, 0.0, 9.0, 9.0])},
            "hot_water": {"a": np.array([1.0, 0.0, 1.0, 1.0])},
        },
        consumed={
            "heating": {
                "NaturalGas": np.array([0.0, 100.0, 10.0, 10.0]),
                "Electricity": np.array([0.0, 0.0, 3.0, 3.0]),
            }
        },
        joint_fuels=joint_fuels,
    )


def test_a_shared_heating_meters_idle_consumption_is_reported_per_mode() -> None:
    result = attribute_energy(_joint(None))
    heating = result.unattributed["heating"]["NaturalGas"]
    hot_water = result.unattributed["hot_water"]["NaturalGas"]
    assert heating + hot_water == pytest.approx(100.0)
    assert hot_water == pytest.approx(100.0 * 3.0 / 24.0)
    zone = result.zones["a"]
    assert zone["hot_water"].unattributed["NaturalGas"] == pytest.approx(hot_water)


def test_only_the_plants_fuels_are_shared_with_hot_water() -> None:
    result = attribute_energy(_joint(frozenset({"naturalgas"})))
    zone = result.zones["a"]
    assert "Electricity" not in zone["hot_water"].consumed_by_fuel
    assert zone["heating"].consumed_by_fuel["Electricity"] == pytest.approx(6.0)
    assert zone["hot_water"].consumed_by_fuel["NaturalGas"] == pytest.approx(2.0)


def test_heat_rejection_is_charged_to_cooling() -> None:
    hours = 2
    data = BuildingEnergy(
        outdoor_temperature=np.zeros(hours),
        multipliers={"a": 1},
        floor_area={"a": 10.0},
        delivered={"heating": {"a": np.full(hours, 15.0)}, "cooling": {"a": np.full(hours, 80.0)}},
        consumed={},
        heat_rejection={"Electricity": np.full(hours, 2.0)},
    )
    zone = attribute_energy(data).zones["a"]
    assert zone["cooling"].distribution_by_fuel["Electricity"] == pytest.approx(4.0)
    assert "Electricity" not in zone["heating"].distribution_by_fuel


def test_glazing_at_a_threshold_keeps_its_type() -> None:
    total = WindowTotals()
    for area in (11.85, 6.62, 8.61, 7.42):
        total = total + WindowTotals(area=area, ua=area * 1.2, a_shgc=area * 0.4, a_vt=area * 0.5)
    glazing = window_construction(total)
    assert glazing is not None
    assert glazing.Type == "Double"


def test_an_hour_mixing_a_setpoint_with_an_off_sentinel_is_clamped_per_timestep() -> None:
    steps = np.array([[-100.0, -100.0, -100.0, 21.0, 21.0, 21.0], [-100.0] * 6, [21.0] * 6])
    hourly = _mean_set(steps, (5.0, 35.0))
    assert hourly[0] == pytest.approx((3 * 5.0 + 3 * 21.0) / 6)
    assert hourly[1] == -100.0  # wholly off: left out of band, so the mode is not enabled by it
    assert hourly[2] == 21.0


def test_dates_are_read_in_english_whatever_the_locale() -> None:
    assert parse_date("2nd Sunday in March", 2013).isoformat() == "2013-03-10"
    assert parse_date("Last Monday in May", 2013).isoformat() == "2013-05-27"


def test_a_constant_profile_projects_to_one_value() -> None:
    cal = RunPeriodCalendar(year=2013)
    days = project(np.full(cal.hours, 0.98), cal)
    assert float(days.min()) == float(days.max()) == 0.98


def test_a_schedule_with_a_value_that_is_not_finite_is_refused() -> None:
    days = np.full((12, 7, 24), 0.5)
    days[0, 0, 0] = np.nan
    with pytest.raises(ValueError, match="not finite"):
        to_year_component(days, name="n", category="Occupancy")


def test_a_date_that_is_a_holiday_and_a_custom_day_is_a_custom_day() -> None:
    from datetime import date  # noqa: PLC0415

    day = date(2013, 1, 10)  # a Thursday
    cal = RunPeriodCalendar(year=2013, holidays=frozenset({day}), custom_day_1=frozenset({day}))
    days = np.zeros((12, 7, 24))
    days[:, 0, :] = 0.1  # Monday's day, which a custom day takes
    year = to_year_component(days, name="n", category="Occupancy", holidays={0: np.full(24, 0.9)})
    values = [float(v) for v in year_values(year, cal)[9 * 24 : 10 * 24]]
    assert set(values) == {0.1}


def test_a_leap_begin_year_run_on_365_days_has_no_leap_day() -> None:
    from idfkit import load_idf  # noqa: PLC0415
    from idfkit.versioned import as_version  # noqa: PLC0415

    doc = as_version(load_idf(MODELS / "ten_zone_multipliers.idf"), since="22.1")
    for run_period in doc.run_periods:
        run_period.begin_year = 2024
    leap = RunPeriodCalendar.from_document(doc)
    plain = RunPeriodCalendar.from_document(doc, leap_day=False)
    assert (leap.days, plain.days) == (366, 365)
    assert plain.start_weekday == leap.start_weekday


def _zone(min_z: float, area: float, multiplier: int = 1) -> Any:
    return SimpleNamespace(
        role="conditioned", zone=SimpleNamespace(min_z=min_z, floor_area=area, multiplier=multiplier)
    )


def test_a_small_lowest_level_does_not_multiply_the_storeys() -> None:
    zones = [_zone(0.0, 100.0), *(_zone(3.0 * level, 1000.0) for level in range(1, 11))]
    assert storey_ratio(cast("Any", zones)) == pytest.approx(10.1)
    # A typical floor drawn once with a multiplier still counts its copies.
    stacked = [_zone(0.0, 1000.0), _zone(3.0, 1000.0, 10), _zone(33.0, 1000.0)]
    assert storey_ratio(cast("Any", stacked)) == pytest.approx(12.0)


def test_delivery_without_consumption_or_rating_is_reported() -> None:
    ledger = GroupLedger(floor_area=100.0, members=("z",), energy={"heating": EnergyTotals(delivered=1e9)})
    derived = thermal_system(ledger, ledger, "heating", name="g")
    assert derived.value is None
    (entry,) = derived.not_represented
    assert entry.magnitude == 1e9
    assert entry.unit == "J"


def test_hot_water_without_an_efficiency_is_reported() -> None:
    ledger = GroupLedger(
        floor_area=100.0,
        members=("z",),
        hot_water=HotWaterTotals(volume=np.full(8760, 0.001), heat=np.full(8760, 0.04)),
    )
    derived = dhw(ledger, ledger, 10.0, name="g")
    assert derived.value.IsOn
    assert [e.feature for e in derived.not_represented] == ["Hot-water efficiency unknown"]


def test_the_loops_a_dedicated_outdoor_air_system_feeds() -> None:
    data = {"airloophvac_outdoorairsystem_name": "OA", "airloophvacs": [{"airloophvac_name": "Loop A"}, {}]}
    assert doas_loops(data) == ["loop a"]


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


def test_a_large_cluster_of_excluded_zones_is_assigned_in_one_sweep() -> None:
    from archetypal.reduction.envelope import EnvelopeHook  # noqa: PLC0415

    size = 8

    def surface(other: str) -> Any:
        return SimpleNamespace(boundary="interzone", adjacent_zone=other, area=10.0)

    zones: list[Any] = []
    for row in range(size):
        for column in range(size):
            near = [(row + 1, column), (row - 1, column), (row, column + 1), (row, column - 1)]
            surfaces = [surface(f"g{r}_{c}") for r, c in near if 0 <= r < size and 0 <= c < size]
            if (row, column) == (0, 0):
                surfaces.append(surface("office"))
            record = SimpleNamespace(name=f"g{row}_{column}", surfaces=surfaces, floor_area=25.0, multiplier=1)
            zones.append(SimpleNamespace(role="excluded", zone=record))
    office = SimpleNamespace(name="office", surfaces=[surface("g0_0")], floor_area=100.0, multiplier=1)
    zones.append(SimpleNamespace(role="conditioned", zone=office))
    hook = EnvelopeHook(cast("Any", zones), assigned_roles=("excluded",))
    assert hook.unassigned == ()
    assert all(shares == {"office": pytest.approx(1.0)} for shares in hook.shares.values())
    assert len(hook.shares) == size * size
