"""Domestic hot water of a zone, for the group ledger (spec 002, research R11, FR-021).

Inventory has already attributed every `WaterUse:Equipment` to zones (`HotWaterRecord`, per
copy of each zone): equipment with a zone is that zone's, and equipment without one is
allocated to zones in proportion to their occupant-hours (R11). This module turns those records
into the ledger's `HotWaterTotals`:

- `volume`: Σ hot-water volume per hour, m³ (from `Water Use Equipment Hot Water Volume`);
- `heat`: Σ volume · temperature rise per hour, m³·K, where the rise is the equipment's hot
  water temperature minus the mains temperature (`Site Mains Water Temperature`) that hour.

The group's supply temperature is then the annual-mean mains plus the volume-weighted mean rise
(`supply_temperature`), so volume and heating energy are both conserved (FR-021).

Which temperature
-----------------
EnergyPlus reports the volume of *hot* water an equipment draws, the part it mixes with cold
water to reach its target temperature. The energy to heat it follows the hot water's
temperature, so the rise uses the equipment's `Hot Water Supply Temperature Schedule` when it
has one, and its `Target Temperature Schedule` otherwise (EnergyPlus then draws only hot water
at the target temperature). This refines R11, which names the target temperature: with a
separate hot supply the target would understate the heat. A rise is kept as it is, even where
negative.

Building-wide data
------------------
The mains temperature comes from the results, which a domain hook does not receive. Build the
hook with `HotWaterHook.from_sources(sources)` and pass it to `GroupLedger.from_zone(...,
hooks=[...])`. The module function `ledger_fields` serves zones without hot water only, and
refuses a zone with hot water, naming `HotWaterHook`.

`allocations(zones)` lists every record with its rule (`zone` or `occupant-hours`, or
`floor-area` when no zone has occupants), for the report (R11: "the report states the rule and
the result").
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypedDict

import numpy as np

from archetypal.reduction.ledger import HotWaterTotals

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping

    from idfkit.versioned import IDFDocumentSince22_1

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.schedules import Profile, ScheduleEvaluator
    from archetypal.reduction.sources import SourceData

__all__ = [
    "MAINS_VARIABLE",
    "HotWaterAllocation",
    "HotWaterFields",
    "HotWaterHook",
    "allocations",
    "hot_water_totals",
    "ledger_fields",
    "mains_temperature",
    "supply_schedules",
    "supply_temperature",
]

MAINS_VARIABLE = "Site Mains Water Temperature"
"""The hourly output (key `Environment`) that gives the mains temperature, °C (R2)."""

_MAINS_KEY = "Environment"
_HOURLY = "Hourly"

AllocationRule = Literal["zone", "occupant-hours", "floor-area"]


class HotWaterFields(TypedDict):
    """The ledger field this module fills, for one copy of a zone."""

    hot_water: HotWaterTotals


def supply_schedules(doc: IDFDocumentSince22_1) -> dict[str, str | None]:
    """Return each `WaterUse:Equipment`'s hot-water temperature schedule, by case-folded name.

    Args:
        doc: The model.

    Returns:
        The hot water supply temperature schedule, else the target temperature schedule, else
        `None`.
    """
    return {
        item.name.casefold(): item.hot_water_supply_temperature_schedule_name
        or item.target_temperature_schedule_name
        or None
        for item in doc.water_use_equipments
    }


def mains_temperature(sources: SourceData) -> Profile:
    """Read the hourly mains water temperature from the results.

    Args:
        sources: The checked model and results.

    Returns:
        The mains temperature each hour, °C.
    """
    series = sources.results.get_timeseries(MAINS_VARIABLE, _MAINS_KEY, frequency=_HOURLY)
    profile = np.asarray(series.values, dtype=np.float64)
    profile.flags.writeable = False
    return profile


def hot_water_totals(
    zone: ClassifiedZone,
    evaluate: Callable[[str], Profile],
    mains: Profile,
    schedules_by_equipment: Mapping[str, str | None],
) -> HotWaterTotals:
    """Return the hot-water totals of one copy of `zone`.

    Args:
        zone: The classified zone; its record's `hot_water` is read.
        evaluate: Returns a schedule's hourly profile by name.
        mains: The mains temperature each hour, °C.
        schedules_by_equipment: Hot-water temperature schedule by case-folded equipment name
            (`supply_schedules`); an equipment missing here uses its target temperature schedule.

    Returns:
        The volume and heat (volume · rise) per hour; empty profiles without hot water.

    Raises:
        ValueError: If an equipment with volume has no temperature schedule.
    """
    totals = HotWaterTotals()
    for record in zone.zone.hot_water:
        schedule = schedules_by_equipment.get(record.equipment.casefold()) or record.target_temperature_schedule
        volume = np.asarray(record.volume, dtype=np.float64)
        if schedule is None:
            if not volume.any():
                continue
            msg = f"WaterUse:Equipment {record.equipment!r} has no hot water or target temperature schedule"
            raise ValueError(msg)
        rise = np.asarray(evaluate(schedule), dtype=np.float64) - mains
        totals = totals + HotWaterTotals(volume=volume, heat=volume * rise)
    return totals


def supply_temperature(totals: HotWaterTotals, mains: Profile) -> float | None:
    """The group's supply temperature: annual-mean mains plus the volume-weighted mean rise (R11).

    Args:
        totals: The group's hot-water totals.
        mains: The mains temperature each hour, °C.

    Returns:
        The supply temperature, °C, or `None` without hot water.
    """
    rise = totals.mean_rise
    if rise is None:
        return None
    return float(np.mean(mains)) + rise


@dataclass(frozen=True, eq=False)
class HotWaterHook:
    """The hot-water domain hook with the building-wide data it needs.

    Attributes:
        mains: The mains temperature each hour, °C.
        supply_schedules: Hot-water temperature schedule by case-folded equipment name.
    """

    mains: Profile
    supply_schedules: Mapping[str, str | None] = field(default_factory=dict[str, "str | None"])

    @classmethod
    def from_sources(cls, sources: SourceData) -> HotWaterHook:
        """Build the hook from the model and results.

        Args:
            sources: The checked model and results.

        Returns:
            The hook. A model without `WaterUse:Equipment` needs no mains output; its mains
            profile is then empty.
        """
        schedules = supply_schedules(sources.model)
        mains = mains_temperature(sources) if schedules else np.zeros(0, dtype=np.float64)
        return cls(mains=mains, supply_schedules=schedules)

    def __call__(self, zone: ClassifiedZone, schedules: ScheduleEvaluator, /) -> HotWaterFields:
        """Return `{"hot_water": HotWaterTotals}` for one copy of `zone`."""
        return HotWaterFields(hot_water=hot_water_totals(zone, schedules, self.mains, self.supply_schedules))


def ledger_fields(zone: ClassifiedZone, schedules: ScheduleEvaluator) -> HotWaterFields:
    """The default hot-water hook: only for zones without hot water.

    Args:
        zone: The classified zone.
        schedules: The model's schedule evaluator.

    Returns:
        `{"hot_water": HotWaterTotals()}`.

    Raises:
        ValueError: If the zone uses hot water; the mains temperature needs
            `HotWaterHook.from_sources`.
    """
    del schedules
    if any(np.asarray(record.volume).any() for record in zone.zone.hot_water):
        msg = (
            f"zone {zone.zone.name!r} uses hot water, whose heat needs the mains temperature from the "
            "results: pass HotWaterHook.from_sources(sources) to GroupLedger.from_zone"
        )
        raise ValueError(msg)
    return HotWaterFields(hot_water=HotWaterTotals())


@dataclass(frozen=True)
class HotWaterAllocation:
    """One equipment's part in one zone, for the report (R11).

    Attributes:
        equipment: The `WaterUse:Equipment`'s name.
        zone: The zone's name.
        share: The share of the equipment's volume one copy of the zone receives.
        multiplier: The zone's multiplier.
        volume: Annual hot-water volume over every copy of the zone, m³.
        allocated: The equipment has no zone and was allocated.
        rule: `zone` (the equipment's own zone), `occupant-hours`, or `floor-area` (no zone has
            occupants).
    """

    equipment: str
    zone: str
    share: float
    multiplier: int
    volume: float
    allocated: bool
    rule: AllocationRule


def allocations(zones: Iterable[ClassifiedZone]) -> tuple[HotWaterAllocation, ...]:
    """List how every equipment's hot water was attributed to zones, sorted by equipment and zone.

    Args:
        zones: The classified zones.

    Returns:
        One entry per (equipment, zone).
    """
    zones = tuple(zones)
    occupied: dict[str, bool] = {}
    for zone in zones:
        has_people = any(g.kind == "people" and g.design_level > 0.0 for g in zone.zone.gains)
        for record in zone.zone.hot_water:
            if record.allocated:
                occupied[record.equipment] = occupied.get(record.equipment, False) or has_people
    entries: list[HotWaterAllocation] = []
    for zone in zones:
        record_zone = zone.zone
        for record in record_zone.hot_water:
            rule: AllocationRule = "zone"
            if record.allocated:
                rule = "occupant-hours" if occupied.get(record.equipment) else "floor-area"
            entries.append(
                HotWaterAllocation(
                    equipment=record.equipment,
                    zone=record_zone.name,
                    share=record.share,
                    multiplier=record_zone.multiplier,
                    volume=float(np.sum(record.volume)) * record_zone.multiplier,
                    allocated=record.allocated,
                    rule=rule,
                )
            )
    return tuple(sorted(entries, key=lambda e: (e.equipment, e.zone)))
