"""Tests for the group ledger (spec 002, T031; data-model.md: GroupLedger).

The ledger's fields are sums, so merging is field-wise addition: associative, commutative,
members a sorted union, and `from_zone` applies the zone multiplier exactly once.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pydantic import BaseModel, ValidationError

from archetypal import io
from archetypal.reduction import ledger as ledger_module
from archetypal.reduction.classify import ClassifiedZone
from archetypal.reduction.inventory import GainRecord, ZoneRecord
from archetypal.reduction.ledger import (
    DOMAIN_MODULES,
    AirflowTotals,
    EirSums,
    EnergyTotals,
    EnvelopeAssignment,
    EnvelopeTotals,
    FanTotals,
    GainTotals,
    GroupLedger,
    HotWaterTotals,
    OutdoorAirTotals,
    WeightedProfile,
    WindowTotals,
    gain_fields,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping

HOURS = 6
ENVELOPE_CLASSES = (
    "exterior_wall",
    "roof",
    "exposed_floor",
    "ground_floor",
    "ground_wall",
    "partition",
    "floor_ceiling",
)
ORIENTATIONS = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
GAIN_KINDS = ("people", "lights", "electric", "gas", "hot_water_equipment", "steam", "other", "baseboard")
MODES = ("heating", "cooling", "hot_water")
FUELS = ("Electricity", "NaturalGas", "DistrictHeatingWater")


# --- strategies ---------------------------------------------------------------------------

# Integer-valued floats add exactly, so associativity can be checked with ==.
exact_floats = st.integers(min_value=-(10**6), max_value=10**6).map(float)
any_floats = st.floats(min_value=-1e6, max_value=1e6, allow_nan=False, allow_infinity=False)


def profiles(values: st.SearchStrategy[float]) -> st.SearchStrategy[np.ndarray[Any, Any]]:
    return st.lists(values, min_size=HOURS, max_size=HOURS).map(lambda v: np.asarray(v, dtype=np.float64))


def keyed(keys: tuple[str, ...], values: st.SearchStrategy[Any]) -> st.SearchStrategy[dict[Any, Any]]:
    return st.dictionaries(st.sampled_from(keys), values, max_size=len(keys))


@st.composite
def ledgers(draw: st.DrawFn, prefix: str, values: st.SearchStrategy[float] = exact_floats) -> GroupLedger:
    p = profiles(values)
    envelope = st.builds(
        EnvelopeTotals,
        area=values,
        ua=values,
        capacity_inner=values,
        capacity_outer=values,
        area_by_orientation=keyed(ORIENTATIONS, values),
    )
    window = st.builds(WindowTotals, area=values, ua=values, a_shgc=values, a_vt=values)
    gain = st.builds(GainTotals, installed=values, hourly=p, radiant=values, latent=values, lost=values)
    eir = st.builds(
        EirSums, d=values, d_t=values, d2=values, d2_t=values, d2_t2=values, c=values, c_d=values, c_d_t=values
    )
    energy = st.builds(
        EnergyTotals,
        delivered=values,
        consumed_by_fuel=keyed(FUELS, values),
        distribution_by_fuel=keyed(FUELS, values),
        unattributed=keyed(FUELS, values),
        rated_weight=values,
        rated_weighted=values,
        eir_sums=eir,
    )
    names = draw(st.sets(st.integers(0, 50), min_size=1, max_size=4))
    members = tuple(f"{prefix}{n:02d}" for n in sorted(names))
    assignment = st.builds(
        EnvelopeAssignment,
        source_zone=st.sampled_from(("Plenum", "Attic")),
        target_zone=st.sampled_from(members),
        envelope_class=st.sampled_from(ENVELOPE_CLASSES),
        area=values,
        share=st.floats(0, 1),
    )
    return GroupLedger(
        members=members,
        floor_area=draw(values),
        envelope=draw(keyed(ENVELOPE_CLASSES, envelope)),
        window_by_orientation=draw(keyed(ORIENTATIONS, window)),
        internal_mass_capacity=draw(values),
        internal_mass_area=draw(values),
        gains=draw(keyed(GAIN_KINDS, gain)),
        infiltration=draw(
            st.builds(
                AirflowTotals,
                design_flow=values,
                hourly=p,
                constant_weighted=values,
                temperature_weighted=values,
                velocity_weighted=values,
                velocity_squared_weighted=values,
            )
        ),
        outdoor_air=draw(
            st.builds(
                OutdoorAirTotals,
                design_flow=values,
                hourly=p,
                hrv_weighted=keyed(("NoHRV", "Sensible", "Enthalpy"), values),
                economiser_weighted=keyed(("NoEconomizer", "DifferentialDryBulb"), values),
                effectiveness_weighted=values,
            )
        ),
        heating_setpoint=draw(st.builds(WeightedProfile, weight=values, weighted=p)),
        cooling_setpoint=draw(st.builds(WeightedProfile, weight=values, weighted=p)),
        unheated_area=draw(values),
        uncooled_area=draw(values),
        hot_water=draw(st.builds(HotWaterTotals, volume=p, heat=p)),
        energy=draw(keyed(MODES, energy)),
        fans=draw(
            st.builds(
                FanTotals,
                energy=values,
                volume=values,
                volume_in_mode=keyed(MODES, values),
                delivered_in_mode=keyed(MODES, values),
                volume_without_demand=values,
            )
        ),
        excluded_envelope=tuple(draw(st.lists(assignment, max_size=2))),
    )


# --- helpers ------------------------------------------------------------------------------


def leaves(obj: object, path: str = "") -> Iterator[tuple[str, Any]]:
    """Every additive leaf of a ledger: (path, float or array). Members and assignments are skipped."""
    if isinstance(obj, BaseModel):
        for name in type(obj).model_fields:
            if name in {"members", "excluded_envelope"}:
                continue
            yield from leaves(getattr(obj, name), f"{path}.{name}")
    elif isinstance(obj, dict):
        for key, value in cast("dict[str, Any]", obj).items():
            yield from leaves(value, f"{path}[{key}]")
    else:
        yield path, obj


def leaf_map(obj: object) -> dict[str, Any]:
    return dict(leaves(obj))


def assert_close(a: object, b: object) -> None:
    left, right = leaf_map(a), leaf_map(b)
    assert left.keys() == right.keys()
    for key in left:
        np.testing.assert_allclose(left[key], right[key], rtol=1e-9, atol=1e-6, err_msg=key)


# --- merging ------------------------------------------------------------------------------


@settings(max_examples=25, deadline=None)
@given(ledgers("a", any_floats), ledgers("b", any_floats))
def test_addition_is_commutative(a: GroupLedger, b: GroupLedger) -> None:
    assert a + b == b + a


@settings(max_examples=25, deadline=None)
@given(ledgers("a"), ledgers("b"), ledgers("c"))
def test_addition_is_associative_exactly_on_exact_values(a: GroupLedger, b: GroupLedger, c: GroupLedger) -> None:
    assert (a + b) + c == a + (b + c)


@settings(max_examples=20, deadline=None)
@given(ledgers("a", any_floats), ledgers("b", any_floats), ledgers("c", any_floats))
def test_addition_is_associative_within_rounding(a: GroupLedger, b: GroupLedger, c: GroupLedger) -> None:
    left, right = (a + b) + c, a + (b + c)
    assert left.members == right.members
    assert left.excluded_envelope == right.excluded_envelope
    assert_close(left, right)


@settings(max_examples=25, deadline=None)
@given(ledgers("a"), ledgers("b"))
def test_members_are_a_sorted_union(a: GroupLedger, b: GroupLedger) -> None:
    merged = a + b
    assert merged.members == tuple(sorted(set(a.members) | set(b.members)))
    assert sorted(merged.excluded_envelope, key=EnvelopeAssignment.sort_key) == list(merged.excluded_envelope)
    assert len(merged.excluded_envelope) == len(a.excluded_envelope) + len(b.excluded_envelope)


@settings(max_examples=25, deadline=None)
@given(ledgers("a", any_floats), ledgers("b", any_floats))
def test_every_total_is_a_sum(a: GroupLedger, b: GroupLedger) -> None:
    left, right, merged = leaf_map(a), leaf_map(b), leaf_map(a + b)
    assert merged.keys() == left.keys() | right.keys()
    for key, value in merged.items():
        parts = [part[key] for part in (left, right) if key in part]
        expected = parts[0] if len(parts) == 1 else parts[0] + parts[1]
        np.testing.assert_array_equal(value, expected, err_msg=key)


@settings(max_examples=20, deadline=None)
@given(ledgers("a"), ledgers("b"), ledgers("c"))
def test_builtin_sum_and_empty_ledger_are_identities(a: GroupLedger, b: GroupLedger, c: GroupLedger) -> None:
    assert sum([a, b, c]) == a + b + c
    assert a + GroupLedger() == a
    assert GroupLedger() + a == a


def test_overlapping_members_are_refused() -> None:
    a = GroupLedger(members=("Z1",), floor_area=1.0)
    with pytest.raises(ValueError, match="Z1"):
        _ = a + GroupLedger(members=("Z1", "Z2"), floor_area=2.0)


def test_profiles_of_different_lengths_are_refused() -> None:
    a = GroupLedger(members=("A",), hot_water=HotWaterTotals(volume=np.ones(3), heat=np.ones(3)))
    b = GroupLedger(members=("B",), hot_water=HotWaterTotals(volume=np.ones(4), heat=np.ones(4)))
    with pytest.raises(ValueError, match="length"):
        _ = a + b
    with pytest.raises(ValidationError, match="length"):
        GroupLedger(
            members=("A",),
            hot_water=HotWaterTotals(volume=np.ones(3), heat=np.ones(3)),
            heating_setpoint=WeightedProfile(weight=1.0, weighted=np.ones(5)),
        )


def test_non_finite_values_are_refused() -> None:
    with pytest.raises(ValidationError):
        WindowTotals(area=math.inf)
    with pytest.raises(ValidationError):
        HotWaterTotals(volume=np.array([1.0, math.nan]), heat=np.zeros(2))


def test_profiles_are_read_only_copies() -> None:
    source = np.ones(HOURS)
    totals = HotWaterTotals(volume=source, heat=source)
    source[0] = 5.0
    assert totals.volume[0] == 1.0
    with pytest.raises(ValueError, match="read-only"):
        totals.volume[0] = 2.0


def test_dictionaries_are_held_in_sorted_key_order() -> None:
    totals = EnergyTotals(consumed_by_fuel={"NaturalGas": 1.0, "Electricity": 2.0})
    assert list(totals.consumed_by_fuel) == ["Electricity", "NaturalGas"]


def test_derived_values() -> None:
    setpoint = WeightedProfile(weight=2.0, weighted=np.array([40.0, 44.0]))
    np.testing.assert_array_equal(setpoint.value, [20.0, 22.0])
    assert WeightedProfile().value is None
    assert EnergyTotals(rated_weight=2.0, rated_weighted=5.0).rated_efficiency == 2.5
    assert EnergyTotals().rated_efficiency is None
    hot_water = HotWaterTotals(volume=np.array([1.0, 3.0]), heat=np.array([40.0, 120.0]))
    assert hot_water.mean_rise == 40.0
    assert HotWaterTotals().mean_rise is None


def test_eir_sums_from_hourly() -> None:
    consumed = np.array([2.0, 0.0, 3.0])
    delivered = np.array([1.0, 0.0, 2.0])
    outdoor = np.array([-5.0, 0.0, 10.0])
    sums = EirSums.from_hourly(consumed=consumed, delivered=delivered, outdoor_temperature=outdoor)
    assert sums == EirSums(d=3.0, d_t=15.0, d2=5.0, d2_t=35.0, d2_t2=425.0, c=5.0, c_d=8.0, c_d_t=50.0)


# --- from_zone: the multiplier applied exactly once ---------------------------------------


@dataclass
class FakeRecord:
    name: str
    multiplier: int
    floor_area: float
    gains: tuple[Any, ...] = ()


@dataclass
class FakeZone:
    zone: FakeRecord


@dataclass
class RecordingHook:
    """A synthetic domain hook: returns one copy's totals and counts its calls."""

    fields: Mapping[str, object]
    calls: list[str] = field(default_factory=list[str])

    def __call__(self, zone: Any, schedules: Any) -> Mapping[str, object]:
        self.calls.append(zone.zone.name)
        return self.fields


def one_copy_hooks(hours: int = HOURS) -> list[RecordingHook]:
    profile = np.arange(1.0, hours + 1.0)
    return [
        RecordingHook({
            "envelope": {"roof": EnvelopeTotals(area=10.0, ua=3.0, area_by_orientation={"N": 10.0})},
            "window_by_orientation": {"S": WindowTotals(area=2.0, ua=4.0, a_shgc=0.8, a_vt=1.2)},
            "internal_mass_capacity": 1e6,
            "excluded_envelope": (
                EnvelopeAssignment(
                    source_zone="Plenum", target_zone="Office", envelope_class="roof", area=5.0, share=0.5
                ),
            ),
        }),
        RecordingHook({
            "infiltration": AirflowTotals(design_flow=0.1, hourly=0.1 * profile, constant_weighted=0.1),
            "outdoor_air": OutdoorAirTotals(design_flow=0.2, hourly=0.2 * profile, hrv_weighted={"Sensible": 7.0}),
        }),
        RecordingHook({
            "heating_setpoint": WeightedProfile(weight=100.0, weighted=2100.0 * np.ones(hours)),
            "cooling_setpoint": WeightedProfile(),
            "uncooled_area": 100.0,
        }),
        RecordingHook({"hot_water": HotWaterTotals(volume=profile, heat=30.0 * profile)}),
        RecordingHook({
            "energy": {
                "heating": EnergyTotals(
                    delivered=10.0,
                    consumed_by_fuel={"NaturalGas": 12.0},
                    eir_sums=EirSums(d=10.0, d2=100.0, c=12.0),
                )
            }
        }),
        RecordingHook({"fans": FanTotals(energy=5.0, volume=50.0, volume_in_mode={"heating": 20.0})}),
    ]


def test_from_zone_takes_members_and_floor_area_from_the_zone() -> None:
    hooks = one_copy_hooks()
    zone = FakeZone(FakeRecord("Office", 1, 100.0))
    ledger = GroupLedger.from_zone(zone, schedules=None, hooks=hooks)  # pyright: ignore[reportArgumentType]
    assert ledger.members == ("Office",)
    assert ledger.floor_area == 100.0
    assert all(hook.calls == ["Office"] for hook in hooks)
    assert ledger.fans.energy == 5.0
    assert ledger.energy["heating"].consumed_by_fuel == {"NaturalGas": 12.0}


@settings(max_examples=25, deadline=None)
@given(st.integers(min_value=1, max_value=40))
def test_from_zone_applies_the_multiplier_exactly_once(multiplier: int) -> None:
    single = GroupLedger.from_zone(FakeZone(FakeRecord("Office", 1, 100.0)), None, hooks=one_copy_hooks())  # pyright: ignore[reportArgumentType]
    hooks = one_copy_hooks()
    scaled = GroupLedger.from_zone(FakeZone(FakeRecord("Office", multiplier, 100.0)), None, hooks=hooks)  # pyright: ignore[reportArgumentType]
    # Each hook is asked once, for one copy; the ledger multiplies.
    assert all(len(hook.calls) == 1 for hook in hooks)
    assert scaled.members == ("Office",)
    left, right = leaf_map(scaled), leaf_map(single)
    assert left.keys() == right.keys()
    for key, value in left.items():
        np.testing.assert_allclose(value, multiplier * right[key], rtol=1e-12, err_msg=key)
    # Shares are not extensive; assigned areas are.
    assert scaled.excluded_envelope[0].share == 0.5
    assert scaled.excluded_envelope[0].area == 5.0 * multiplier
    # The weighted setpoint keeps its value.
    assert scaled.heating_setpoint.value is not None
    np.testing.assert_allclose(scaled.heating_setpoint.value, 21.0)


@settings(max_examples=15, deadline=None)
@given(st.integers(min_value=1, max_value=10))
def test_multiplier_equals_adding_copies(multiplier: int) -> None:
    def copy(name: str) -> GroupLedger:
        return GroupLedger.from_zone(FakeZone(FakeRecord(name, 1, 100.0)), None, hooks=one_copy_hooks())  # pyright: ignore[reportArgumentType]

    scaled = GroupLedger.from_zone(FakeZone(FakeRecord("Office", multiplier, 100.0)), None, hooks=one_copy_hooks())  # pyright: ignore[reportArgumentType]
    added = sum(copy(f"Office{i}") for i in range(multiplier))
    assert isinstance(added, GroupLedger)
    assert_close(scaled.model_copy(update={"members": added.members}), added)


def test_from_zone_refuses_a_field_given_twice() -> None:
    hooks = [RecordingHook({"unheated_area": 1.0}), RecordingHook({"unheated_area": 2.0})]
    with pytest.raises(ValueError, match="unheated_area"):
        GroupLedger.from_zone(FakeZone(FakeRecord("Z", 1, 1.0)), None, hooks=hooks)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("name", ["members", "floor_area", "no_such_field"])
def test_from_zone_refuses_fields_hooks_do_not_own(name: str) -> None:
    hooks = [RecordingHook({name: 1.0})]
    with pytest.raises(ValueError, match=name):
        GroupLedger.from_zone(FakeZone(FakeRecord("Z", 1, 1.0)), None, hooks=hooks)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize("multiplier", [0, -2])
def test_from_zone_refuses_a_multiplier_below_one(multiplier: int) -> None:
    with pytest.raises(ValueError, match="multiplier"):
        GroupLedger.from_zone(FakeZone(FakeRecord("Z", multiplier, 1.0)), None, hooks=[])  # pyright: ignore[reportArgumentType]


def test_default_hooks_are_the_domain_modules_and_gains() -> None:
    assert DOMAIN_MODULES == ("envelope", "airflow", "thermostats", "hotwater", "efficiency", "fans")
    owners = ledger_module.FIELD_OWNERS
    owned = {name for names in owners.values() for name in names}
    assert owned == set(GroupLedger.model_fields) - {"members", "floor_area"}
    assert set(owners) == {"gains", *DOMAIN_MODULES}


def test_default_hooks_import_each_domain_module(monkeypatch: pytest.MonkeyPatch) -> None:
    imported: list[str] = []

    def fake_import(name: str) -> Any:
        imported.append(name)

        class Module:
            @staticmethod
            def ledger_fields(zone: Any, schedules: Any) -> dict[str, object]:
                return {}

        return Module

    monkeypatch.setattr(ledger_module.importlib, "import_module", fake_import)
    hooks = ledger_module.default_hooks()
    assert hooks[0] is gain_fields
    assert imported == [f"archetypal.reduction.{name}" for name in DOMAIN_MODULES]


# --- gains, the one domain the ledger computes itself ------------------------------------


def schedule_lookup(table: dict[str, np.ndarray[Any, Any]]) -> Callable[[str], np.ndarray[Any, Any]]:
    return lambda name: table[name]


def test_gain_fields_sum_installed_and_hourly_by_kind() -> None:
    occupancy = np.array([0.0, 0.5, 1.0, 1.0])
    always = np.ones(4)
    gains = (
        GainRecord("lights", "L1", 1000.0, "occ", 0.4, 0.0, 0.0, 0.2),
        GainRecord("lights", "L2", 500.0, "on", 0.0, 0.0, 0.0),
        GainRecord("electric", "E", 200.0, "on", 0.3, 0.1, 0.05),
        GainRecord("people", "P", 10.0, "occ", 0.3, None, 0.0),
    )
    zone = FakeZone(FakeRecord("Office", 3, 50.0, gains))
    fields = gain_fields(zone, schedule_lookup({"occ": occupancy, "on": always}))  # pyright: ignore[reportArgumentType]
    totals = cast("dict[str, GainTotals]", fields["gains"])
    lights: GainTotals = totals["lights"]
    assert lights.installed == 1500.0
    np.testing.assert_array_equal(lights.hourly, [500.0, 1000.0, 1500.0, 1500.0])
    lights_energy_first = 1000.0 * occupancy.sum() * 3600.0
    assert lights.radiant == pytest.approx(0.4 * lights_energy_first)
    assert lights.lost == pytest.approx(0.2 * lights_energy_first)
    electric: GainTotals = totals["electric"]
    energy = 200.0 * 4 * 3600.0
    assert (electric.radiant, electric.latent, electric.lost) == pytest.approx((
        0.3 * energy,
        0.1 * energy,
        0.05 * energy,
    ))
    people: GainTotals = totals["people"]
    assert people.installed == 10.0
    np.testing.assert_array_equal(people.hourly, 10.0 * occupancy)
    assert (people.radiant, people.latent, people.lost) == (0.0, 0.0, 0.0)
    # One copy: the multiplier is applied by from_zone, not by the hook.
    ledger = GroupLedger.from_zone(zone, schedule_lookup({"occ": occupancy, "on": always}), hooks=[gain_fields])  # pyright: ignore[reportArgumentType]
    assert ledger.gains["lights"].installed == 4500.0


def test_gain_without_schedule_is_always_on() -> None:
    zone = FakeZone(FakeRecord("Z", 1, 1.0, (GainRecord("other", "O", 7.0, None, 0.0, 0.0, 0.0),)))
    fields = gain_fields(zone, schedule_lookup({"x": np.zeros(3)}), hours=3)  # pyright: ignore[reportArgumentType]
    totals = cast("dict[str, GainTotals]", fields["gains"])
    np.testing.assert_array_equal(totals["other"].hourly, [7.0, 7.0, 7.0])


# --- the report's JSON form ---------------------------------------------------------------


@settings(max_examples=20, deadline=None)
@given(ledgers("a", any_floats))
def test_json_round_trip_restores_the_full_ledger(a: GroupLedger) -> None:
    text = io.dumps(a)
    restored = GroupLedger.model_validate_json(text)
    assert restored == a
    assert io.dumps(restored) == text


def test_profiles_are_encoded_in_json() -> None:
    ledger = GroupLedger(members=("A",), hot_water=HotWaterTotals(volume=np.arange(4.0), heat=np.zeros(4)))
    data = json.loads(io.dumps(ledger))
    volume = data["hot_water"]["volume"]
    assert volume["encoding"] == "base64-float64-le"
    assert volume["length"] == 4
    np.testing.assert_array_equal(io.EncodedProfile.model_validate(volume).to_array(), np.arange(4.0))
    # An empty profile (no data) is encoded too, with length 0.
    assert data["infiltration"]["hourly"]["length"] == 0


def test_json_is_independent_of_insertion_order() -> None:
    a = EnergyTotals(consumed_by_fuel={"NaturalGas": 1.0, "Electricity": 2.0})
    b = EnergyTotals(consumed_by_fuel={"Electricity": 2.0, "NaturalGas": 1.0})
    assert io.dumps(a) == io.dumps(b)


def test_json_schema_documents_the_profile_encoding() -> None:
    schema = json.dumps(GroupLedger.model_json_schema())
    assert "base64-float64-le" in schema


def test_ledger_reports_its_hours() -> None:
    assert GroupLedger().hours is None
    ledger = GroupLedger(members=("A",), hot_water=HotWaterTotals(volume=np.zeros(5), heat=np.zeros(5)))
    assert ledger.hours == 5


def test_from_zone_with_inventory_records_applies_the_multiplier_once() -> None:
    record = ZoneRecord(
        name="Typical_Perimeter",
        multiplier=10,
        floor_area=200.0,
        min_z=3.0,
        volume=600.0,
        gains=(GainRecord("lights", "L", 1000.0, "on", 0.4, 0.0, 0.0),),
    )
    zone = ClassifiedZone(record, True, "conditioned", "perimeter", "office", "signature", "thermostat")
    ledger = GroupLedger.from_zone(zone, schedule_lookup({"on": np.ones(4)}), hooks=[gain_fields])  # pyright: ignore[reportArgumentType]
    assert ledger.members == ("Typical_Perimeter",)
    assert ledger.floor_area == 2000.0
    assert ledger.gains["lights"].installed == 10_000.0
    np.testing.assert_array_equal(ledger.gains["lights"].hourly, np.full(4, 10_000.0))


# --- approximate_from_group: infiltration method and mechanical ventilation schedule ------------


def _office_group(update: Callable[[Any], Any] | None = None) -> Any:
    from pathlib import Path  # noqa: PLC0415

    from epinterface.sbem.archetype import ZoneGroup  # noqa: PLC0415

    from archetypal.umi import read_umi  # noqa: PLC0415

    library = Path(__file__).parents[1] / "fixtures" / "umi" / "BostonTemplateLibrary_2.json"
    zone = read_umi(library).archetypes[0].Groups[1].Zone
    if update is not None:
        zone = update(zone)
    return ZoneGroup.model_validate({"Name": "g", "Zone": zone, "FloorAreaShare": 0.4, "Exposure": "perimeter"})


def _with(model: Any, path: str, value: object) -> Any:
    head, _, rest = path.partition(".")
    if not rest:
        return model.model_copy(update={head: value})
    return model.model_copy(update={head: _with(getattr(model, head), rest, value)})


def test_approximate_infiltration_follows_flow_per_exterior_area() -> None:
    """D1: SBEM infiltration written as Flow/ExteriorArea (ACH 0) is not rebuilt as zero."""

    def flow_per_area(zone: Any) -> Any:
        infiltration = zone.Envelope.Infiltration.model_copy(
            update={
                "CalculationMethod": "Flow/ExteriorArea",
                "AirChangesPerHour": 0.0,
                "FlowPerExteriorSurfaceArea": 3e-4,
            }
        )
        return _with(zone, "Envelope.Infiltration", infiltration)

    ledger = GroupLedger.approximate_from_group(_office_group(flow_per_area), 0.4).ledger
    assert ledger.infiltration.design_flow == pytest.approx(3e-4 * 0.4)


def test_approximate_infiltration_air_changes_over_a_unit_storey() -> None:
    def ach(zone: Any) -> Any:
        infiltration = zone.Envelope.Infiltration.model_copy(
            update={"CalculationMethod": "AirChanges/Hour", "AirChangesPerHour": 0.5, "FlowPerExteriorSurfaceArea": 9.0}
        )
        return _with(zone, "Envelope.Infiltration", infiltration)

    ledger = GroupLedger.approximate_from_group(_office_group(ach), 0.4).ledger
    assert ledger.infiltration.design_flow == pytest.approx(0.5 * 0.4 * 1.0 / 3600)


def test_approximate_outdoor_air_follows_the_mechanical_schedule_not_natural() -> None:
    """D4: mechanical outdoor air is MechVentSchedule (constant without one), not `Schedule` (natural)."""
    from archetypal.reduction.schedules import RunPeriodCalendar, calendar_year, year_values  # noqa: PLC0415

    group = _office_group(lambda z: _with(z, "Operations.HVAC.Ventilation.MechVentSchedule", None))
    ventilation = group.Zone.Operations.HVAC.Ventilation
    natural = np.asarray(year_values(ventilation.Schedule, RunPeriodCalendar(calendar_year(1, 1, 0))))
    assert float(natural.max()) > float(natural.min())  # the natural schedule is not constant here
    oa = GroupLedger.approximate_from_group(group, 0.4).ledger.outdoor_air
    np.testing.assert_allclose(oa.hourly, np.full(8760, oa.design_flow))

    def mechanical(zone: Any) -> Any:
        schedule = zone.Operations.HVAC.Ventilation.Schedule
        return _with(zone, "Operations.HVAC.Ventilation.MechVentSchedule", schedule)

    group = _office_group(mechanical)
    if group.Zone.Operations.HVAC.Ventilation.MechVentSchedule.schedule_type_limits != "Fraction":
        pytest.skip("the fixture's ventilation schedule is not a Fraction schedule")
    oa = GroupLedger.approximate_from_group(group, 0.4).ledger.outdoor_air
    np.testing.assert_allclose(oa.hourly, oa.design_flow * natural)
