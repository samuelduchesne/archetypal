"""The conservation suite (spec 002, T041; quickstart scenario 5, SC-005).

Every total of FR-014 to FR-019, FR-021, FR-022 and FR-022a must match the detailed model within
0.1 %, and exactly where the detailed total is 0:

- on **synthetic ledgers** (hypothesis): zones of random space use, exposure, multiplier and
  totals are grouped at a random layout and threshold; the groups, and the pre-threshold groups
  `merge` starts from, must hold the zones' totals;
- on the **fixtures**: the report's groups must hold the totals read from the detailed model
  directly (its inventory, schedules and results), and the archetype's intensities times their
  bases must give them back where a rule conserves a total.
"""

from __future__ import annotations

import math
from collections import defaultdict
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel

from archetypal.reduction.classify import ClassifiedZone
from archetypal.reduction.grouping import group, group_zones
from archetypal.reduction.inventory import ZoneRecord
from archetypal.reduction.ledger import (
    AirflowTotals,
    EirSums,
    EnergyTotals,
    EnvelopeTotals,
    FanTotals,
    GainTotals,
    GroupLedger,
    HotWaterTotals,
    OutdoorAirTotals,
    WeightedProfile,
    WindowTotals,
)
from archetypal.reduction.options import Layout

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from archetypal.reduction import Reduction
    from archetypal.reduction._sql_tables import GainKind

RTOL = 1e-3
"""SC-005: 0.1 %."""

HOURS = 24
SECONDS = 3600.0
FIXTURES = ("three_zone", "ten_zone_multipliers", "bar_building")
EXTERIOR = frozenset({"outdoors", "ground"})


def flatten(model: object, prefix: str = "") -> dict[str, float]:
    """Every additive total of a ledger as `path -> value`; a profile counts as its sum."""
    out: dict[str, float] = {}
    if isinstance(model, BaseModel):
        for name in type(model).model_fields:
            if name in {"members", "excluded_envelope"}:
                continue
            out.update(flatten(getattr(model, name), f"{prefix}{name}."))
    elif isinstance(model, dict):
        items = cast("dict[str, object]", model)
        for key, value in items.items():
            out.update(flatten(value, f"{prefix}{key}."))
    elif isinstance(model, np.ndarray):
        out[prefix.rstrip(".")] = float(np.sum(cast("np.ndarray[Any, np.dtype[np.float64]]", model)))
    elif isinstance(model, (int, float)):
        out[prefix.rstrip(".")] = float(model)
    return out


def assert_conserved(actual: Mapping[str, float], expected: Mapping[str, float], what: str) -> None:
    """Every expected total is matched within 0.1 %, and exactly where it is 0."""
    for path, value in expected.items():
        got = actual.get(path, 0.0)
        if value == 0.0:
            assert got == 0.0, f"{what}: {path} is {got!r}, the detailed total is 0"
        else:
            assert abs(got - value) <= RTOL * abs(value), f"{what}: {path} is {got!r}, not {value!r}"
    extra = {p: v for p, v in actual.items() if p not in expected and v != 0.0}
    assert not extra, f"{what}: totals the detailed model lacks: {extra}"


def total(ledgers: Iterable[GroupLedger]) -> dict[str, float]:
    return flatten(sum(ledgers, GroupLedger()))


# --- synthetic ledgers -------------------------------------------------------------------------------

_amount = st.one_of(st.just(0.0), st.floats(min_value=1e-3, max_value=1e4, allow_nan=False))
_profile = st.lists(_amount, min_size=HOURS, max_size=HOURS).map(lambda v: np.asarray(v, dtype=np.float64))


@st.composite
def zone_ledger(draw: st.DrawFn, name: str) -> tuple[ClassifiedZone, GroupLedger]:
    """A zone with every kind of total; any of them may be 0."""
    multiplier = draw(st.integers(min_value=1, max_value=10))
    area = draw(st.floats(min_value=1.0, max_value=1e3))
    record = ZoneRecord(name=name, multiplier=multiplier, floor_area=area, min_z=0.0, volume=3.0 * area)
    zone = ClassifiedZone(
        zone=record,
        conditioned=True,
        role="conditioned",
        exposure=draw(st.sampled_from(["perimeter", "core"])),
        space_use=draw(st.sampled_from(["office", "retail", "storage"])),
        space_use_source="signature",
        role_reason="test",
    )
    wall = draw(_amount)
    window = draw(_amount)
    consumed = draw(_amount)
    delivered = draw(_amount)
    one_copy = GroupLedger(
        members=(name,),
        floor_area=area,
        gains={
            "people": GainTotals(installed=draw(_amount), hourly=draw(_profile)),
            "lights": GainTotals(installed=draw(_amount), hourly=draw(_profile), radiant=draw(_amount)),
        },
        envelope={"exterior_wall": EnvelopeTotals(area=wall, ua=0.4 * wall, capacity_inner=draw(_amount))},
        window_by_orientation={"S": WindowTotals(area=window, ua=2.0 * window, a_shgc=0.4 * window, a_vt=0.6 * window)},
        internal_mass_capacity=draw(_amount),
        internal_mass_area=draw(_amount),
        infiltration=AirflowTotals(design_flow=draw(_amount), hourly=draw(_profile)),
        outdoor_air=OutdoorAirTotals(
            design_flow=draw(_amount), hourly=draw(_profile), hrv_weighted={"Sensible": draw(_amount)}
        ),
        heating_setpoint=WeightedProfile(weight=area, weighted=np.full(HOURS, 21.0 * area)),
        hot_water=HotWaterTotals(volume=draw(_profile), heat=draw(_profile)),
        energy={
            "heating": EnergyTotals(
                delivered=delivered,
                consumed_by_fuel={"NaturalGas": consumed},
                distribution_by_fuel={"Electricity": draw(_amount)},
                eir_sums=EirSums(d=delivered, c=consumed),
            )
        },
        fans=FanTotals(energy=draw(_amount), volume=draw(_amount)),
    )
    return zone, one_copy.scaled(multiplier) if multiplier > 1 else one_copy


@st.composite
def buildings(draw: st.DrawFn) -> list[tuple[ClassifiedZone, GroupLedger]]:
    count = draw(st.integers(min_value=1, max_value=7))
    return [draw(zone_ledger(f"Z{i:02d}")) for i in range(count)]


@settings(max_examples=40, deadline=None)
@given(
    zones=buildings(),
    layout=st.sampled_from(list(Layout)),
    threshold=st.floats(min_value=0.0, max_value=0.6),
)
def test_groups_conserve_every_total_of_synthetic_zones(
    zones: list[tuple[ClassifiedZone, GroupLedger]], layout: Layout, threshold: float
) -> None:
    expected = total(ledger for _, ledger in zones)
    grouping = group_zones(zones, layout=layout, threshold=threshold)
    assert_conserved(total(g.ledger for g in grouping.groups), expected, "groups")
    assert_conserved(total(g.ledger for g in grouping.pre_threshold_groups), expected, "pre-threshold groups")
    # Every zone is in exactly one group, and its multiplier is applied once.
    members = [m for g in grouping.groups for m in g.ledger.members]
    assert sorted(members) == sorted(z.zone.name for z, _ in zones)
    floor_area = math.fsum(z.zone.floor_area * z.zone.multiplier for z, _ in zones)
    assert math.fsum(g.ledger.floor_area for g in grouping.groups) == pytest.approx(floor_area, rel=1e-12)
    # Regrouping the pre-threshold groups (what merge does) conserves them too.
    for target in Layout:
        if not Layout.is_strictly_finer(target, layout):
            merged = group(grouping.pre_threshold_groups, target, threshold)
            assert_conserved(total(g.ledger for g in merged.groups), expected, f"merged to {target}")


# --- the fixtures ------------------------------------------------------------------------------------


def _building(reduction: Reduction) -> GroupLedger:
    return sum((g.ledger for g in reduction.report.groups), GroupLedger())


def _hourly(evaluate: Callable[[str], Any], schedule: str | None, hours: int) -> np.ndarray[Any, Any]:
    return np.ones(hours) if schedule is None else np.asarray(evaluate(schedule), dtype=np.float64)


def _series(sources: Any, name: str, key: str) -> np.ndarray[Any, Any]:
    (series,) = sources.results.get_timeseries_many([(name, key, "Hourly")])
    return np.asarray(series.values, dtype=np.float64)


def _close(actual: float, expected: float, what: str) -> None:
    if expected == 0.0:
        assert actual == 0.0, what
    else:
        assert actual == pytest.approx(expected, rel=RTOL), what


@pytest.mark.parametrize("fixture", FIXTURES)
def test_floor_area_fr014(fixture: str, reduced: Callable[[str], Reduction], detailed: Callable[[str], Any]) -> None:
    reduction = reduced(fixture)
    _, zones, _ = detailed(fixture)
    expected = math.fsum(z.zone.floor_area * z.zone.multiplier for z in zones if z.role == "conditioned")
    _close(_building(reduction).floor_area, expected, "floor area")
    geometry = reduction.archetype.Geometry
    assert geometry.ConditionedFloorArea is not None
    _close(geometry.ConditionedFloorArea, expected, "Geometry.ConditionedFloorArea")
    shares = {g.Name: g.FloorAreaShare for g in reduction.archetype.Groups}
    for group_report in reduction.report.groups:
        share = shares[group_report.name]
        assert share is not None
        _close(share * expected, group_report.ledger.floor_area, group_report.name)


@pytest.mark.parametrize("fixture", FIXTURES)
def test_internal_gains_fr015(
    fixture: str, reduced: Callable[[str], Reduction], detailed: Callable[[str], Any]
) -> None:
    reduction = reduced(fixture)
    sources, zones, evaluate = detailed(fixture)
    hours = sources.run_period.calendar.hours
    installed: dict[GainKind, float] = defaultdict(float)
    hourly: dict[GainKind, np.ndarray[Any, Any]] = defaultdict(lambda: np.zeros(hours))
    for zone in zones:
        if zone.role != "conditioned":
            continue
        for gain in zone.zone.gains:
            installed[gain.kind] += gain.design_level * zone.zone.multiplier
            hourly[gain.kind] = hourly[gain.kind] + gain.design_level * zone.zone.multiplier * _hourly(
                evaluate, gain.schedule, hours
            )
    building = _building(reduction)
    assert set(installed) <= set(building.gains)
    for kind, value in installed.items():
        _close(building.gains[kind].installed, value, f"{kind} installed")
        np.testing.assert_allclose(building.gains[kind].hourly, hourly[kind], rtol=RTOL, atol=1e-9)
    # The archetype's densities give the installed totals back (rule gain.density).
    area = {g.name: g.ledger.floor_area for g in reduction.report.groups}
    people = math.fsum(
        g.Zone.Operations.SpaceUse.Occupancy.PeopleDensity * area[g.Name] for g in reduction.archetype.Groups
    )
    lights = math.fsum(
        g.Zone.Operations.SpaceUse.Lighting.PowerDensity * area[g.Name] for g in reduction.archetype.Groups
    )
    _close(people, installed["people"], "people from PeopleDensity")
    _close(lights, installed["lights"], "lights from PowerDensity")


def _detailed_envelope(zones: Iterable[ClassifiedZone]) -> dict[str, float]:
    """Envelope totals of the detailed model as `"<class>.<total>"`, multipliers applied.

    Exterior surfaces of conditioned zones and of the plenums and attics whose envelope they
    carry (FR-013, `envelope.ASSIGNED_ROLES`); interior surfaces and internal mass of conditioned
    zones only. Windows are summed over orientations.
    """
    totals: dict[str, float] = defaultdict(float)
    for zone in zones:
        if zone.role == "basement":
            continue
        k = zone.zone.multiplier
        conditioned = zone.role == "conditioned"
        for s in zone.zone.surfaces:
            exterior = s.boundary in EXTERIOR
            if s.surface_class == "internal_mass" or not exterior:
                if conditioned:
                    kind = "mass" if s.surface_class == "internal_mass" else "interior"
                    totals[f"{kind}.capacity"] += k * s.area * s.heat_capacity
                    totals[f"{kind}.area"] += k * s.area
                continue
            totals[f"{s.surface_class}.area"] += k * s.area
            totals[f"{s.surface_class}.ua"] += k * s.area * s.u_factor
            totals[f"{s.surface_class}.capacity"] += k * s.area * s.heat_capacity
            totals[f"{s.surface_class}.a_shgc"] += k * s.area * (s.shgc or 0.0)
            totals[f"{s.surface_class}.a_vt"] += k * s.area * (s.visible_transmittance or 0.0)
    return totals


@pytest.mark.parametrize("fixture", FIXTURES)
def test_envelope_and_mass_fr016_fr017(
    fixture: str, reduced: Callable[[str], Reduction], detailed: Callable[[str], Any]
) -> None:
    building = _building(reduced(fixture))
    expected = _detailed_envelope(detailed(fixture)[1])
    for envelope_class, totals in building.envelope.items():
        if envelope_class in {"partition", "floor_ceiling"}:
            continue
        _close(totals.area, expected[f"{envelope_class}.area"], f"{envelope_class} area")
        _close(totals.ua, expected[f"{envelope_class}.ua"], f"{envelope_class} UA")
        capacity = totals.capacity_inner + totals.capacity_outer
        _close(capacity, expected[f"{envelope_class}.capacity"], f"{envelope_class} capacity")
    opaque = {key.split(".")[0] for key in expected} - {"window", "mass", "interior"}
    assert opaque <= set(building.envelope)
    interior = [building.envelope[c] for c in ("partition", "floor_ceiling") if c in building.envelope]
    capacity = math.fsum(t.capacity_inner + t.capacity_outer for t in interior)
    _close(capacity, expected["interior.capacity"], "interior capacity")
    windows = building.window_by_orientation.values()
    for field in ("area", "ua", "a_shgc", "a_vt"):
        _close(math.fsum(getattr(w, field) for w in windows), expected[f"window.{field}"], f"window {field}")
    _close(building.internal_mass_capacity, expected["mass.capacity"], "internal mass capacity")
    _close(building.internal_mass_area, expected["mass.area"], "internal mass area")


@pytest.mark.parametrize("fixture", FIXTURES)
def test_infiltration_and_outdoor_air_fr018_fr019(
    fixture: str, reduced: Callable[[str], Reduction], detailed: Callable[[str], Any]
) -> None:
    building = _building(reduced(fixture))
    sources, zones, evaluate = detailed(fixture)
    hours = sources.run_period.calendar.hours
    design = 0.0
    hourly = np.zeros(hours)
    outdoor_air = np.zeros(hours)
    variable = "Zone Mechanical Ventilation Standard Density Volume Flow Rate"
    reported = {v.key_value.casefold() for v in sources.results.list_variables() if v.name == variable}
    for zone in zones:
        if zone.role != "conditioned":
            continue
        for record in zone.zone.infiltration:
            design += record.design_flow * zone.zone.multiplier
            hourly += record.design_flow * zone.zone.multiplier * _hourly(evaluate, record.schedule, hours)
        if zone.zone.name.casefold() in reported:
            # The output already counts every copy of the zone (tests/fixtures/SOURCES.md).
            outdoor_air += _series(sources, variable, zone.zone.name.upper())
    _close(building.infiltration.design_flow, design, "infiltration design flow")
    np.testing.assert_allclose(building.infiltration.hourly, hourly, rtol=RTOL, atol=1e-12)
    if outdoor_air.any():
        np.testing.assert_allclose(building.outdoor_air.hourly, outdoor_air, rtol=RTOL, atol=1e-12)
        volume = float(outdoor_air.sum()) * SECONDS
        _close(math.fsum(building.outdoor_air.hrv_weighted.values()), volume, "HRV-weighted volume")
    else:
        assert not building.outdoor_air.hourly.any()


@pytest.mark.parametrize("fixture", FIXTURES)
def test_hot_water_fr021(fixture: str, reduced: Callable[[str], Reduction], detailed: Callable[[str], Any]) -> None:
    building = _building(reduced(fixture))
    sources, _, _ = detailed(fixture)
    volume = np.zeros(sources.run_period.calendar.hours)
    for equipment in sources.model.water_use_equipments:
        volume += _series(sources, "Water Use Equipment Hot Water Volume", equipment.name.upper())
    if volume.any():
        np.testing.assert_allclose(building.hot_water.volume, volume, rtol=RTOL, atol=1e-12)
    else:
        assert not building.hot_water.volume.any()


@pytest.mark.parametrize("fixture", FIXTURES)
def test_energy_by_fuel_and_delivered_fr022(
    fixture: str, reduced: Callable[[str], Reduction], detailed: Callable[[str], Any]
) -> None:
    """Every joule of the conditioning meters is in a group, attributed or not (standby, pumps)."""
    reduction = reduced(fixture)
    building = _building(reduction)
    sources, zones, _ = detailed(fixture)
    meters: dict[str, float] = defaultdict(float)
    for info in sources.results.list_variables():
        end_use, _, fuel = info.name.partition(":")
        if info.is_meter and end_use in {"Heating", "Cooling", "WaterSystems", "Pumps", "HeatRejection"}:
            meters[fuel] += float(_series(sources, info.name, "*").sum())
    in_groups: dict[str, float] = defaultdict(float)
    for energy in building.energy.values():
        for values in (energy.consumed_by_fuel, energy.distribution_by_fuel, energy.unattributed):
            for fuel, value in values.items():
                in_groups[fuel] += value
    assert set(in_groups) == set(meters)
    for fuel, value in meters.items():
        _close(in_groups[fuel], value, f"{fuel} consumed")
    for mode in ("heating", "cooling"):
        delivered = math.fsum(
            z.zone.delivered.get(mode, 0.0) * z.zone.multiplier for z in zones if z.role == "conditioned"
        )
        _close(building.energy[mode].delivered if mode in building.energy else 0.0, delivered, f"{mode} delivered")


@pytest.mark.parametrize("fixture", FIXTURES)
def test_fan_energy_fr022a(fixture: str, reduced: Callable[[str], Reduction], detailed: Callable[[str], Any]) -> None:
    reduction = reduced(fixture)
    building = _building(reduction)
    sources, _, _ = detailed(fixture)
    names = {v.name for v in sources.results.list_variables() if v.is_meter}
    meter = float(_series(sources, "Fans:Electricity", "*").sum()) if "Fans:Electricity" in names else 0.0
    unattributed = math.fsum(
        n.magnitude or 0.0 for n in reduction.report.not_represented if n.feature == "Fans serving no conditioned zone"
    )
    _close(building.fans.energy + unattributed, meter, "fan energy")
    # The archetype's specific fan power gives each group's fan energy back from its air volume.
    sfp = {
        g.Name: g.Zone.Operations.HVAC.ConditioningSystems.model_dump().get("SpecificFanPower")
        for g in reduction.archetype.Groups
    }
    for group_report in reduction.report.groups:
        fans = group_report.ledger.fans
        if fans.volume > 0.0:
            value = sfp[group_report.name]
            assert value is not None
            _close(value * fans.volume, fans.energy, f"{group_report.name} fan energy from SpecificFanPower")
