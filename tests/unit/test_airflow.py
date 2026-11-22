"""Tests for infiltration and outdoor air (spec 002, T033; research R9, R18; FR-018, FR-019)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from archetypal.reduction.airflow import (
    NO_CONTROL,
    AirflowHook,
    OutdoorAirControl,
    economiser_category,
    infiltration_totals,
    ledger_fields,
    outdoor_air_controls,
    outdoor_air_totals,
)
from archetypal.reduction.classify import ClassifiedZone, classify
from archetypal.reduction.inventory import AirflowRecord, GainRecord, ZoneRecord, build_inventory
from archetypal.reduction.ledger import GroupLedger
from archetypal.reduction.schedules import ScheduleEvaluator
from archetypal.reduction.sources import load_sources

if TYPE_CHECKING:
    from archetypal.reduction.schedules import Profile
    from archetypal.reduction.sources import SourceData

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
HOURS = 24


def step(hours: int, before: float, after: float) -> Profile:
    """`before` for the first `hours` hours of each day, `after` for the rest."""
    return np.array([before if h % 24 < hours else after for h in range(HOURS)], dtype=np.float64)


SECONDS = 3600.0


@dataclass
class FakeEvaluator:
    table: dict[str, Profile]
    calendar: Any = field(default_factory=lambda: SimpleNamespace(hours=HOURS))
    doc: Any = None

    def __call__(self, name: str) -> Profile:
        return self.table[name.upper()]


SCHEDULES: dict[str, Profile] = {
    "ON": np.ones(HOURS),
    "DAY": step(8, 0.25, 1.0),
    "OCC": step(9, 0.0, 0.8),
}


def _zone(
    name: str = "Z",
    *,
    infiltration: tuple[AirflowRecord, ...] = (),
    outdoor_air: Profile | None = None,
    area: float = 100.0,
    multiplier: int = 1,
    per_area: float = 0.0,
    per_person: float = 0.0,
    people: float = 0.0,
) -> ClassifiedZone:
    gains = (GainRecord("people", f"{name} people", people, "OCC", 0.3, None, 0.0),) if people else ()
    record = ZoneRecord(
        name=name,
        multiplier=multiplier,
        floor_area=area,
        min_z=0.0,
        volume=3 * area,
        gains=gains,
        infiltration=infiltration,
        outdoor_air=np.zeros(HOURS) if outdoor_air is None else outdoor_air,
        outdoor_air_per_area=per_area,
        outdoor_air_per_person=per_person,
    )
    return ClassifiedZone(record, True, "conditioned", "perimeter", "office", "signature", "test")


# --- Infiltration ---------------------------------------------------------------------------------


def test_infiltration_conserves_design_flow_and_profile() -> None:
    records = (
        AirflowRecord("a", 0.02, "DAY", 0.6, 0.02, 0.2, 0.0),
        AirflowRecord("b", 0.01, None, 1.0, 0.0, 0.0, 0.0),
    )
    totals = infiltration_totals(_zone(infiltration=records), FakeEvaluator(SCHEDULES))
    assert totals.design_flow == pytest.approx(0.03)
    np.testing.assert_allclose(totals.hourly, 0.02 * SCHEDULES["DAY"] + 0.01)
    assert totals.constant_weighted == pytest.approx(0.02 * 0.6 + 0.01 * 1.0)
    assert totals.temperature_weighted == pytest.approx(0.02 * 0.02)
    assert totals.velocity_weighted == pytest.approx(0.02 * 0.2)
    assert totals.velocity_squared_weighted == 0.0


def test_a_zone_without_infiltration_contributes_nothing() -> None:
    totals = infiltration_totals(_zone(), FakeEvaluator(SCHEDULES))
    assert totals.design_flow == 0.0
    assert totals.hourly.size == 0


@given(
    st.lists(
        st.tuples(st.floats(0.0, 1.0), st.floats(0.0, 1.0), st.floats(0.0, 0.05), st.integers(1, 10)),
        min_size=1,
        max_size=5,
    )
)
def test_group_infiltration_conserves_totals_and_flow_weighted_coefficients(
    members: list[tuple[float, float, float, int]],
) -> None:
    evaluator = FakeEvaluator(SCHEDULES)
    ledgers: list[GroupLedger] = []
    for i, (flow, constant, temperature, multiplier) in enumerate(members):
        record = AirflowRecord(f"i{i}", flow, "DAY", constant, temperature, 0.0, 0.0)
        zone = _zone(f"Z{i}", infiltration=(record,), multiplier=multiplier)
        ledgers.append(GroupLedger.from_zone(zone, evaluator, hooks=[ledger_fields]))  # pyright: ignore[reportArgumentType]
    group = sum(ledgers)
    assert isinstance(group, GroupLedger)
    design = sum(flow * m for flow, _, _, m in members)
    assert group.infiltration.design_flow == pytest.approx(design)
    np.testing.assert_allclose(group.infiltration.hourly, design * SCHEDULES["DAY"], atol=1e-12)
    assert group.infiltration.constant_weighted == pytest.approx(sum(f * c * m for f, c, _, m in members))
    assert group.infiltration.temperature_weighted == pytest.approx(sum(f * t * m for f, _, t, m in members))


# --- Outdoor air ----------------------------------------------------------------------------------


def test_outdoor_air_conserves_the_hourly_profile_and_peak_times_fraction_reproduces_it() -> None:
    hourly = 0.05 * SCHEDULES["OCC"] + 0.01
    zone = _zone(outdoor_air=hourly, per_area=0.0003, per_person=0.0025, people=10.0)
    totals = outdoor_air_totals(zone, NO_CONTROL)
    np.testing.assert_allclose(totals.hourly, hourly)
    assert totals.design_flow == pytest.approx(0.0003 * 100.0 + 0.0025 * 10.0)
    # SBEM: FreshAirPerFloorArea = peak / area, Schedule = hourly / peak (R9).
    peak = float(totals.hourly.max())
    fraction = totals.hourly / peak
    np.testing.assert_allclose(peak * fraction, hourly)
    assert totals.hrv_weighted == {"NoHRV": pytest.approx(hourly.sum() * SECONDS)}
    assert totals.economiser_weighted == {"NoEconomizer": pytest.approx(hourly.sum() * SECONDS)}
    assert totals.effectiveness_weighted == 0.0


def test_heat_recovery_and_economiser_are_weighted_by_the_outdoor_air_they_serve() -> None:
    control = OutdoorAirControl(hrv="Sensible", economiser="DifferentialDryBulb", effectiveness=0.7, source="VAV")
    hourly = np.full(HOURS, 0.1)
    totals = outdoor_air_totals(_zone(outdoor_air=hourly), control)
    volume = 0.1 * HOURS * SECONDS
    assert totals.hrv_weighted == {"Sensible": pytest.approx(volume)}
    assert totals.economiser_weighted == {"DifferentialDryBulb": pytest.approx(volume)}
    assert totals.effectiveness_weighted == pytest.approx(0.7 * volume)


def test_the_group_takes_the_category_with_the_largest_outdoor_air_share() -> None:
    hrv = OutdoorAirControl("Sensible", "DifferentialDryBulb", 0.7, "VAV")
    controls = {"big": hrv, "small": NO_CONTROL}
    hook = AirflowHook(controls)
    evaluator = FakeEvaluator(SCHEDULES)
    big = GroupLedger.from_zone(_zone("Big", outdoor_air=np.full(HOURS, 0.2)), evaluator, hooks=[hook])  # pyright: ignore[reportArgumentType]
    small = GroupLedger.from_zone(  # pyright: ignore[reportArgumentType]
        _zone("Small", outdoor_air=np.full(HOURS, 0.05), multiplier=3),
        evaluator,  # pyright: ignore[reportArgumentType]
        hooks=[hook],
    )
    group = big + small
    weighted = group.outdoor_air.hrv_weighted
    assert weighted["Sensible"] == pytest.approx(0.2 * HOURS * SECONDS)
    assert weighted["NoHRV"] == pytest.approx(3 * 0.05 * HOURS * SECONDS)
    assert max(weighted, key=lambda key: weighted[key]) == "Sensible"
    np.testing.assert_allclose(group.outdoor_air.hourly, 0.2 + 3 * 0.05)
    # The airflow-weighted effectiveness over the air with heat recovery is the member's.
    assert group.outdoor_air.effectiveness_weighted / weighted["Sensible"] == pytest.approx(0.7)


def test_a_zone_without_outdoor_air_records_no_category() -> None:
    totals = outdoor_air_totals(_zone(), NO_CONTROL)
    assert totals.hrv_weighted == {}
    assert totals.economiser_weighted == {}


@pytest.mark.parametrize(
    ("energyplus", "sbem"),
    [
        ("NoEconomizer", "NoEconomizer"),
        ("DifferentialDryBulb", "DifferentialDryBulb"),
        ("FixedDryBulb", "DifferentialDryBulb"),
        ("FixedDewPointAndDryBulb", "DifferentialDryBulb"),
        ("DifferentialEnthalpy", "DifferentialEnthalpy"),
        ("DifferentialDryBulbAndEnthalpy", "DifferentialEnthalpy"),
        ("FixedEnthalpy", "DifferentialEnthalpy"),
        ("ElectronicEnthalpy", "DifferentialEnthalpy"),
        (None, "NoEconomizer"),
    ],
)
def test_economiser_category(energyplus: str | None, sbem: str) -> None:
    assert economiser_category(energyplus) == sbem


def test_default_hook_without_a_model_attributes_no_heat_recovery() -> None:
    zone = _zone(outdoor_air=np.full(HOURS, 0.1))
    fields = ledger_fields(zone, FakeEvaluator(SCHEDULES))  # pyright: ignore[reportArgumentType]
    assert set(fields) == {"infiltration", "outdoor_air"}
    assert set(fields["outdoor_air"].hrv_weighted) == {"NoHRV"}


# --- Fixtures: air loops read from the model (R18) -------------------------------------------------


@pytest.fixture(scope="module")
def ten_sources() -> SourceData:
    return load_sources(MODELS / "ten_zone_multipliers.idf", MODELS / "ten_zone_multipliers.sql")


def test_air_loop_heat_recovery_and_economiser_reach_the_zones_it_serves(ten_sources: SourceData) -> None:
    controls = outdoor_air_controls(ten_sources.model)
    served = {"g_perimeter", "g_core", "typical_perimeter", "typical_core"}
    for zone in served:
        control = controls[zone]
        assert control.hrv == "Sensible"
        assert control.economiser == "DifferentialDryBulb"
        assert control.effectiveness == pytest.approx(0.7)
        assert control.source == "VAV"
    # Top floor PTHPs and unconditioned zones are not on the air loop.
    for zone in ("top_perimeter", "top_core", "attic", "basement", "g_plenum"):
        assert controls.get(zone, NO_CONTROL) == NO_CONTROL


def test_fixture_outdoor_air_is_conserved(ten_sources: SourceData) -> None:
    evaluator = ScheduleEvaluator(ten_sources.model, ten_sources.run_period.calendar)
    hook = AirflowHook.from_model(ten_sources.model)
    zones = classify(build_inventory(ten_sources, evaluator), evaluator)
    ledgers = [GroupLedger.from_zone(zone, evaluator, hooks=[hook]) for zone in zones]
    total = sum(ledgers)
    assert isinstance(total, GroupLedger)
    raw = np.zeros(ten_sources.run_period.calendar.hours)
    infiltration = 0.0
    variable = "Zone Mechanical Ventilation Standard Density Volume Flow Rate"
    reported = {info.key_value.upper() for info in ten_sources.results.list_variables() if info.name == variable}
    for zone in zones:
        if zone.zone.name.upper() in reported:
            series = ten_sources.results.get_timeseries(variable, zone.zone.name.upper(), frequency="Hourly")
            raw += np.asarray(series.values, dtype=np.float64)
        infiltration += sum(r.design_flow for r in zone.zone.infiltration) * zone.zone.multiplier
    np.testing.assert_allclose(total.outdoor_air.hourly, raw, rtol=1e-9, atol=1e-12)
    assert total.infiltration.design_flow == pytest.approx(infiltration)
    volume = float(raw.sum()) * SECONDS
    assert sum(total.outdoor_air.hrv_weighted.values()) == pytest.approx(volume)
    assert sum(total.outdoor_air.economiser_weighted.values()) == pytest.approx(volume)
    # The default hook reads the same model through the evaluator.
    assert ledger_fields(zones[0], evaluator)["outdoor_air"] == hook(zones[0], evaluator)["outdoor_air"]
