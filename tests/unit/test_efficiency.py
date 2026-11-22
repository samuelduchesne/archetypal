"""Tests for conditioning efficiency (spec 002, T036; FR-022, research R12)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from archetypal.reduction.classify import classify
from archetypal.reduction.efficiency import (
    BuildingEnergy,
    attribute_energy,
    building_energy,
    efficiency_hook,
    fit_eir,
    ledger_fields,
    rated_efficiencies,
)
from archetypal.reduction.inventory import build_inventory
from archetypal.reduction.ledger import EirSums, GroupLedger
from archetypal.reduction.schedules import ScheduleEvaluator
from archetypal.reduction.sources import load_sources

if TYPE_CHECKING:
    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.sources import SourceData

MODELS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "models"


def _a(*values: float) -> np.ndarray:
    return np.asarray(values, dtype=np.float64)


def _data(**overrides: object) -> BuildingEnergy:
    """Two zones, A (multiplier 1) and B (multiplier 2), over four hours."""
    values: dict[str, object] = {
        "outdoor_temperature": _a(0.0, 5.0, 10.0, 15.0),
        "multipliers": {"A": 1, "B": 2},
        "floor_area": {"A": 100.0, "B": 50.0},
        "delivered": {
            "heating": {"A": _a(10.0, 0.0, 4.0, 0.0), "B": _a(5.0, 3.0, 0.0, 0.0)},
            "cooling": {"A": _a(0.0, 0.0, 0.0, 6.0), "B": _a(0.0, 0.0, 0.0, 0.0)},
        },
        "consumed": {"heating": {"NaturalGas": _a(40.0, 12.0, 8.0, 2.0)}, "cooling": {"Electricity": _a(0, 0, 0, 3.0)}},
        "distribution": {"Electricity": _a(1.0, 1.0, 1.0, 1.0)},
        "rated": {},
    }
    values.update(overrides)
    return BuildingEnergy(**values)  # pyright: ignore[reportArgumentType]


# --- attribution ----------------------------------------------------------------------------------


def test_consumption_follows_each_hours_delivery_in_the_mode() -> None:
    result = attribute_energy(_data())
    a, b = result.zones["A"]["heating"], result.zones["B"]["heating"]
    # hour 0: D = 10 + 2*5 = 20, C = 40 -> A 20, B (per copy) 10; hour 1: D = 6, C = 12 -> B 6;
    # hour 2: D = 4, C = 8 -> A 8; hour 3: no delivery, 2 J unattributed.
    assert a.consumed_by_fuel == pytest.approx({"NaturalGas": 28.0})
    assert b.consumed_by_fuel == pytest.approx({"NaturalGas": 16.0})
    assert a.delivered == pytest.approx(14.0)
    assert b.delivered == pytest.approx(8.0)
    assert result.zones["A"]["cooling"].consumed_by_fuel == pytest.approx({"Electricity": 3.0})


def test_standby_is_reported_not_attributed() -> None:
    result = attribute_energy(_data())
    assert result.unattributed["heating"] == pytest.approx({"NaturalGas": 2.0})
    a, b = result.zones["A"]["heating"], result.zones["B"]["heating"]
    # Spread by the annual delivered share (A 14, B 2*8 = 16) so groups add up to the building.
    assert a.unattributed["NaturalGas"] + 2 * b.unattributed["NaturalGas"] == pytest.approx(2.0)
    assert a.unattributed["NaturalGas"] == pytest.approx(2.0 * 14 / 30)


def test_every_joule_of_the_meters_is_conserved() -> None:
    data = _data()
    result = attribute_energy(data)
    for mode, meters in data.consumed.items():
        for fuel, series in meters.items():
            total = sum(
                data.multipliers[z]
                * (
                    result.zones[z][mode].consumed_by_fuel.get(fuel, 0.0)
                    + result.zones[z][mode].unattributed.get(fuel, 0.0)
                )
                for z in result.zones
            )
            assert total == pytest.approx(float(series.sum()))


def test_pumps_and_heat_rejection_split_by_the_hours_delivered_modes() -> None:
    delivered = {
        "heating": {"A": _a(3.0, 0.0), "B": _a(0.0, 0.0)},
        "cooling": {"A": _a(0.0, 0.0), "B": _a(1.0, 0.0)},
    }
    data = _data(
        outdoor_temperature=_a(0.0, 0.0),
        delivered=delivered,
        consumed={},
        distribution={"Electricity": _a(10.0, 4.0)},
    )
    result = attribute_energy(data)
    # hour 0: heating 3, cooling 2*1 = 2 -> 6 J to heating (A), 4 J to cooling (B, 2 J per copy).
    assert result.zones["A"]["heating"].distribution_by_fuel == pytest.approx({"Electricity": 6.0})
    assert result.zones["B"]["cooling"].distribution_by_fuel == pytest.approx({"Electricity": 2.0})
    # hour 1: no delivery: 4 J unattributed, split heating:cooling by annual delivery (3:2).
    assert result.unattributed_distribution == pytest.approx({"Electricity": 4.0})
    # In the zones' ledgers it is split heating:cooling by annual delivery (3:2).
    assert result.zones["A"]["heating"].unattributed["Electricity"] == pytest.approx(4.0 * 3 / 5)
    assert 2 * result.zones["B"]["cooling"].unattributed["Electricity"] == pytest.approx(4.0 * 2 / 5)


def test_fans_are_not_folded_into_distribution() -> None:
    result = attribute_energy(_data(distribution={}))
    assert result.zones["A"]["heating"].distribution_by_fuel == {}


def test_eir_sums_are_built_from_the_zones_hourly_attribution() -> None:
    data = _data()
    result = attribute_energy(data)
    sums = result.zones["A"]["heating"].eir_sums
    expected = EirSums.from_hourly(
        consumed=_a(20.0, 0.0, 8.0, 0.0), delivered=_a(10.0, 0.0, 4.0, 0.0), outdoor_temperature=_a(0, 5, 10, 15)
    )
    assert sums == expected


def test_zone_without_delivery_takes_the_rated_efficiency() -> None:
    delivered = {"heating": {"A": _a(1.0, 1.0, 1.0, 1.0), "B": _a(0, 0, 0, 0)}}
    result = attribute_energy(_data(delivered=delivered, rated={"B": {"heating": 3.2, "cooling": 3.4}}))
    b = result.zones["B"]["heating"]
    assert b.delivered == 0.0
    assert b.consumed_by_fuel == {}
    assert b.rated_efficiency == pytest.approx(3.2)
    assert result.zones["B"]["cooling"].rated_efficiency == pytest.approx(3.4)
    # Weighted by floor area, so a merged group keeps an area-weighted mean.
    assert (b + result.zones["B"]["heating"].scaled(1.0)).rated_efficiency == pytest.approx(3.2)


def test_the_hook_returns_one_copy_and_from_zone_scales_it() -> None:
    result = attribute_energy(_data())

    class Record:
        name = "B"
        multiplier = 2
        floor_area = 50.0

    class Zone:
        zone = Record()

    ledger = GroupLedger.from_zone(Zone(), None, hooks=[result])  # pyright: ignore[reportArgumentType]
    assert ledger.energy["heating"].consumed_by_fuel == pytest.approx({"NaturalGas": 32.0})
    Record.name = "unknown"
    assert result(Zone(), None) == {}  # pyright: ignore[reportArgumentType]


def test_the_module_hook_needs_building_data() -> None:
    with pytest.raises(ValueError, match="efficiency_hook"):
        ledger_fields(None, None)  # pyright: ignore[reportArgumentType]


# --- the energy-input-ratio fit --------------------------------------------------------------------

rng = np.random.default_rng(42)
T = rng.uniform(-10.0, 30.0, 500)
D = rng.uniform(0.0, 1e6, 500)


def test_fit_reproduces_annual_consumption_exactly() -> None:
    c = (0.3 + 0.01 * T + 0.02 * np.sin(T)) * D
    sums = EirSums.from_hourly(consumed=c, delivered=D, outdoor_temperature=T)
    a, b, t_ref = fit_eir(sums)
    assert float(np.sum((a + b * (T - t_ref)) * D)) == pytest.approx(float(c.sum()), rel=1e-12)
    assert t_ref == pytest.approx(float(np.sum(D * T) / D.sum()))


def test_fit_recovers_a_linear_eir() -> None:
    c = (0.3 - 0.008 * (T - 5.0)) * D
    a, b, t_ref = fit_eir(EirSums.from_hourly(consumed=c, delivered=D, outdoor_temperature=T))
    assert b == pytest.approx(-0.008, rel=1e-9)
    assert a + b * (5.0 - t_ref) == pytest.approx(0.3, rel=1e-9)


def test_a_boiler_has_no_slope() -> None:
    a, b, _ = fit_eir(EirSums.from_hourly(consumed=D / 0.85, delivered=D, outdoor_temperature=T))
    assert a == pytest.approx(1 / 0.85)
    assert abs(b) < 1e-12


def test_refitting_merged_sums_equals_fitting_the_merged_hours() -> None:
    c = (0.3 + 0.01 * T) * D * rng.uniform(0.9, 1.1, 500)
    first = EirSums.from_hourly(consumed=c[:200], delivered=D[:200], outdoor_temperature=T[:200])
    second = EirSums.from_hourly(consumed=c[200:], delivered=D[200:], outdoor_temperature=T[200:])
    whole = EirSums.from_hourly(consumed=c, delivered=D, outdoor_temperature=T)
    assert fit_eir(first + second) == pytest.approx(fit_eir(whole), rel=1e-9)


def test_constant_temperature_gives_no_slope() -> None:
    a, b, t_ref = fit_eir(EirSums.from_hourly(consumed=2 * D, delivered=D, outdoor_temperature=np.full(500, 7.0)))
    assert (a, b, t_ref) == pytest.approx((2.0, 0.0, 7.0))


def test_fit_without_delivery_is_refused() -> None:
    with pytest.raises(ValueError, match="no delivered"):
        fit_eir(EirSums())


# --- fixtures -------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def ten() -> tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]:
    sources = load_sources(MODELS / "ten_zone_multipliers.idf", MODELS / "ten_zone_multipliers.sql")
    evaluate = ScheduleEvaluator(sources.model, sources.run_period.calendar)
    zones = classify(build_inventory(sources, evaluate), evaluate)
    return sources, zones, evaluate


def _meter(sources: SourceData, name: str) -> float:
    (series,) = sources.results.get_timeseries_many([(name, "*", "Hourly")])
    return float(np.sum(series.values))


def test_fixture_meters_are_conserved_over_conditioned_zones(
    ten: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator],
) -> None:
    sources, zones, evaluate = ten
    hook = efficiency_hook(sources, zones, evaluate)
    ledgers = [GroupLedger.from_zone(z, evaluate, hooks=[hook]) for z in zones if z.conditioned]
    total = sum(ledgers, GroupLedger())
    for mode, meter, fuel in (
        ("heating", "Heating:NaturalGas", "NaturalGas"),
        ("heating", "Heating:Electricity", "Electricity"),
        ("cooling", "Cooling:Electricity", "Electricity"),
        ("hot_water", "WaterSystems:NaturalGas", "NaturalGas"),
    ):
        energy = total.energy[mode]
        assert energy.consumed_by_fuel[fuel] + hook.unattributed[mode].get(fuel, 0.0) == pytest.approx(
            _meter(sources, meter), rel=1e-9
        )
    distribution = sum(total.energy[m].distribution_by_fuel.get("Electricity", 0.0) for m in ("heating", "cooling"))
    assert distribution + hook.unattributed_distribution.get("Electricity", 0.0) == pytest.approx(
        _meter(sources, "Pumps:Electricity"), rel=1e-9
    )
    by_name = {z.zone.name: z for z in zones}
    assert hook(by_name["G_Plenum"], evaluate) == {}
    assert hook(by_name["Attic"], evaluate) == {}


def test_fixture_delivered_energy_matches_the_zone_records(
    ten: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator],
) -> None:
    sources, zones, evaluate = ten
    data = building_energy(sources, zones, evaluate)
    for z in zones:
        if z.conditioned:
            assert float(data.delivered["heating"][z.zone.name].sum()) == pytest.approx(z.zone.delivered["heating"])
    assert data.outdoor_temperature.shape == (8760,)


def test_fixture_rated_efficiencies_from_equipment_summary(
    ten: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator],
) -> None:
    sources, zones, _ = ten
    rated = rated_efficiencies(sources, zones)
    # Top floor: the PTHP's own coils (supplemental heater excluded).
    assert rated["Top_Perimeter"]["heating"] == pytest.approx(3.2)
    assert rated["Top_Perimeter"]["cooling"] == pytest.approx(3.4)
    # Water coils on the VAV: the plant's boiler and chiller.
    assert rated["G_Perimeter"]["heating"] == pytest.approx(0.85)
    assert rated["G_Perimeter"]["cooling"] == pytest.approx(2.8)
    assert rated["G_Perimeter"]["hot_water"] == pytest.approx(0.8)


def test_fixture_boiler_heating_has_a_small_slope_and_delivered_over_consumed(
    ten: tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator],
) -> None:
    sources, zones, evaluate = ten
    hook = efficiency_hook(sources, zones, evaluate)
    energy = hook.zones["Typical_Perimeter"]["heating"]
    a, _, _ = fit_eir(energy.eir_sums)
    assert a == pytest.approx(sum(energy.consumed_by_fuel.values()) / energy.delivered, rel=1e-9)
