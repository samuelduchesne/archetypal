"""Grouping and thresholding of conditioned zones (spec 002, data-model.md: Grouping and thresholding).

Grouping always runs in two steps, whether it starts from a model (`reduce`) or from a
report (`merge`):

1. `finest_groups` sums one ledger per conditioned zone by the finest key, `(space_use,
   exposure)`, summing each group's ledgers in zone-name order. These are the
   **pre-threshold groups** the report keeps whatever the layout (FR-011).
2. `group` regroups pre-threshold groups by the requested layout's key (`Layout.regroup`),
   summing them in finest-key order, then applies the small-group threshold **once**, to those
   groups (FR-011), and lists the distinctions the layout merged (FR-009).

`group_zones` chains the two for `reduce`. `merge` rebuilds the pre-threshold groups from the
report and calls `group` alone, so merging an archetype and reducing directly to the target
layout run the same code on the same groups in the same order and give identical results
(FR-010, SC-007).

Threshold
---------
While some group's floor-area share is below the threshold and it has an eligible partner (any
other group with the same exposure where the layout keeps exposure, any other group otherwise),
the smallest such group (ties by key) merges into its most similar eligible partner (ties by
key), which keeps its key. Shares are of the total conditioned floor area, which merging does
not change. A small group with no eligible partner is kept.

Similarity is the Euclidean distance between two groups' intensity vectors (`intensities`),
each component divided by the building-wide value of the same intensity
(`building_intensities`). A component whose building-wide value is 0 is left out. A setpoint
mean a group lacks (no heated or no cooled area) takes the building-wide value, so it adds
nothing to the distance (a decision of this module).
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence  # noqa: TC003 - pydantic resolves annotations at run time
from functools import reduce
from operator import add

from pydantic import BaseModel, ConfigDict, Field

from archetypal.reduction.classify import ClassifiedZone  # noqa: TC001 - used at run time in annotations
from archetypal.reduction.ledger import GroupLedger  # noqa: TC001 - pydantic resolves annotations at run time
from archetypal.reduction.options import Distinction, GroupKey, Layout

__all__ = [
    "Group",
    "Grouping",
    "MergedDistinction",
    "SmallGroupMerge",
    "building_intensities",
    "distance",
    "finest_groups",
    "group",
    "group_zones",
    "intensities",
]

_EXPOSURES = ("core", "perimeter")


class _Frozen(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", arbitrary_types_allowed=True)


class Group(_Frozen):
    """A group of zones: its key and its ledger.

    Attributes:
        key: The group key, the values of the distinctions the layout keeps.
        ledger: The sum of the members' ledgers; `ledger.members` are the zones.
    """

    key: GroupKey
    ledger: GroupLedger


class SmallGroupMerge(_Frozen):
    """A merge of a small group into its most similar eligible group (report: `small_group_merges[]`).

    Attributes:
        merged_key: The small group's key, which disappears.
        into_key: The key of the group it merged into, which stays.
        share: The small group's floor-area share when it merged.
        distance: The similarity distance between the two groups.
    """

    merged_key: GroupKey
    into_key: GroupKey
    share: float
    distance: float


class MergedDistinction(_Frozen):
    """For a layout coarser than the finest, which finest keys a resulting group holds.

    Report: `merged_distinctions[]`, read by spec 003.

    Attributes:
        into_key: The resulting group's key.
        from_keys: The finest keys `(space_use, exposure)` of its members, sorted, including
            those of small groups merged into it.
        lost: The distinctions the layout loses, `"space_use"`, `"exposure"` or both.
    """

    into_key: GroupKey
    from_keys: tuple[GroupKey, ...]
    lost: tuple[Distinction, ...]


class Grouping(_Frozen):
    """The outcome of grouping: final groups, pre-threshold groups and what was merged.

    Attributes:
        layout: The requested layout.
        threshold: The small-group threshold applied.
        groups: The groups after the threshold, sorted by key.
        pre_threshold_groups: The groups at the finest key before any threshold, sorted by
            key, whatever the layout (FR-011; `merge` starts from these).
        merges: Each small-group merge, in the order it happened.
        merged_distinctions: One entry per group, in group order, for a layout coarser than
            the finest; empty at the finest layout.
        notes: Remarks for the report, for example a layout with exposure in a building with
            no core zones (US2 scenario 3).
    """

    layout: Layout
    threshold: float
    groups: tuple[Group, ...]
    pre_threshold_groups: tuple[Group, ...]
    merges: tuple[SmallGroupMerge, ...] = ()
    merged_distinctions: tuple[MergedDistinction, ...] = ()
    notes: tuple[str, ...] = Field(default=())


# --- Pre-threshold groups -------------------------------------------------------------------------


def finest_groups(zone_ledgers: Iterable[tuple[ClassifiedZone, GroupLedger]]) -> tuple[Group, ...]:
    """Sum zone ledgers by the finest key, `(space_use, exposure)`: the pre-threshold groups.

    Args:
        zone_ledgers: Each conditioned zone with its ledger (`GroupLedger.from_zone`), in any
            order.

    Returns:
        One group per key, sorted by key; each ledger is summed in zone-name order.

    Raises:
        ValueError: If a zone is not conditioned, or a ledger's members are not its zone.
    """
    by_key: dict[GroupKey, list[tuple[str, GroupLedger]]] = {}
    for zone, ledger in zone_ledgers:
        name = zone.zone.name
        if not zone.conditioned:
            msg = f"zone {name!r} is not conditioned; only conditioned zones are grouped (FR-013)"
            raise ValueError(msg)
        if ledger.members != (name,):
            msg = f"the ledger of zone {name!r} has members {ledger.members}, not that zone"
            raise ValueError(msg)
        key = Layout.SPACE_USE_EXPOSURE.group_key(zone.space_use, zone.exposure)
        by_key.setdefault(key, []).append((name, ledger))
    return tuple(
        Group(key=key, ledger=_sum(ledger for _, ledger in sorted(by_key[key], key=lambda item: item[0])))
        for key in sorted(by_key)
    )


# --- Grouping -------------------------------------------------------------------------------------


def group_zones(
    zone_ledgers: Iterable[tuple[ClassifiedZone, GroupLedger]],
    *,
    layout: Layout = Layout.SPACE_USE_EXPOSURE,
    threshold: float = 0.05,
) -> Grouping:
    """Group conditioned zones by a layout and apply the small-group threshold (for `reduce`).

    Args:
        zone_ledgers: Each conditioned zone with its ledger, in any order.
        layout: The requested layout.
        threshold: The small-group threshold, a share of conditioned floor area in [0, 1).

    Returns:
        The grouping; `group(result.pre_threshold_groups, layout, threshold)` equals it.

    Raises:
        ValueError: As `finest_groups` and `group` do.
    """
    return group(finest_groups(zone_ledgers), layout, threshold)


def group(pre_threshold_groups: Iterable[Group], layout: Layout, threshold: float) -> Grouping:
    """Regroup pre-threshold groups by a layout's key and apply the threshold once (FR-009 to FR-011).

    `merge` calls this with the groups rebuilt from a report's `pre_threshold_groups`.

    Args:
        pre_threshold_groups: Groups at the finest key `(space_use, exposure)`, in any order.
        layout: The requested layout.
        threshold: The small-group threshold, a share of conditioned floor area in [0, 1).

    Returns:
        The grouping.

    Raises:
        ValueError: If the threshold is outside [0, 1), there are no groups, the total floor
            area is not positive, a key is not a finest key, a key appears twice, or two groups
            share a member.
    """
    if not 0.0 <= threshold < 1.0:
        msg = f"the small-group threshold {threshold!r} is not a share in [0, 1)"
        raise ValueError(msg)
    pre = _checked(pre_threshold_groups)

    # Regroup by the layout's key, summing in finest-key order.
    regrouped: dict[GroupKey, list[Group]] = {}
    for finest in pre:
        regrouped.setdefault(layout.regroup(finest.key), []).append(finest)
    ledgers = {key: _sum(g.ledger for g in members) for key, members in regrouped.items()}
    origins = {key: {g.key for g in members} for key, members in regrouped.items()}

    merges = _threshold(ledgers, origins, layout, threshold)

    groups = tuple(Group(key=key, ledger=ledgers[key]) for key in sorted(ledgers))
    distinctions: tuple[MergedDistinction, ...] = ()
    if layout is not Layout.SPACE_USE_EXPOSURE:
        lost = layout.lost_from(Layout.SPACE_USE_EXPOSURE)
        distinctions = tuple(
            MergedDistinction(into_key=g.key, from_keys=tuple(sorted(origins[g.key])), lost=lost) for g in groups
        )
    return Grouping(
        layout=layout,
        threshold=threshold,
        groups=groups,
        pre_threshold_groups=pre,
        merges=merges,
        merged_distinctions=distinctions,
        notes=_notes(pre, layout),
    )


def _checked(pre_threshold_groups: Iterable[Group]) -> tuple[Group, ...]:
    pre = tuple(sorted(pre_threshold_groups, key=lambda g: g.key))
    if not pre:
        msg = "no conditioned zones to group"
        raise ValueError(msg)
    seen: set[str] = set()
    for i, finest in enumerate(pre):
        if len(finest.key) != len(Layout.SPACE_USE_EXPOSURE.distinctions):
            msg = f"pre-threshold group key {finest.key!r} is not a finest key (space use, exposure)"
            raise ValueError(msg)
        if finest.key[1] not in _EXPOSURES:
            msg = f"pre-threshold group key {finest.key!r} has exposure {finest.key[1]!r}, not one of {_EXPOSURES}"
            raise ValueError(msg)
        if i and pre[i - 1].key == finest.key:
            msg = f"pre-threshold group key {finest.key!r} appears twice"
            raise ValueError(msg)
        shared = seen & set(finest.ledger.members)
        if shared:
            msg = f"zones {sorted(shared)} belong to more than one pre-threshold group"
            raise ValueError(msg)
        seen.update(finest.ledger.members)
    if not sum(g.ledger.floor_area for g in pre) > 0.0:
        msg = "the conditioned floor area of the groups is not positive"
        raise ValueError(msg)
    return pre


def _threshold(
    ledgers: dict[GroupKey, GroupLedger],
    origins: dict[GroupKey, set[GroupKey]],
    layout: Layout,
    threshold: float,
) -> tuple[SmallGroupMerge, ...]:
    """Merge small groups in place (`ledgers` and `origins`) and return the merges, in order."""
    total = math.fsum(ledger.floor_area for ledger in ledgers.values())
    building = building_intensities([ledgers[key] for key in sorted(ledgers)])
    exposure_at = layout.distinctions.index("exposure") if "exposure" in layout.distinctions else None

    def partners(key: GroupKey) -> list[GroupKey]:
        return sorted(
            other
            for other in ledgers
            if other != key and (exposure_at is None or other[exposure_at] == key[exposure_at])
        )

    merges: list[SmallGroupMerge] = []
    while True:
        small = sorted(
            (ledger.floor_area, key)
            for key, ledger in ledgers.items()
            if ledger.floor_area / total < threshold and partners(key)
        )
        if not small:
            break
        _, key = small[0]
        merged = ledgers[key]
        best = min(partners(key), key=lambda other: (distance(merged, ledgers[other], building), other))
        merges.append(
            SmallGroupMerge(
                merged_key=key,
                into_key=best,
                share=merged.floor_area / total,
                distance=distance(merged, ledgers[best], building),
            )
        )
        ledgers[best] = ledgers[best] + ledgers.pop(key)
        origins[best] |= origins.pop(key)
    return tuple(merges)


def _notes(pre: tuple[Group, ...], layout: Layout) -> tuple[str, ...]:
    if "exposure" not in layout.distinctions:
        return ()
    present = {g.key[1] for g in pre}
    notes: list[str] = []
    for missing in _EXPOSURES:
        if missing not in present:
            (kept,) = present
            groups = f"a {kept} group only" if layout is Layout.CORE_PERIMETER else f"{kept} groups only"
            notes.append(f"no {missing} zones: the {layout} layout has {groups}")
    return tuple(notes)


def _sum(ledgers: Iterable[GroupLedger]) -> GroupLedger:
    return reduce(add, ledgers)


# --- Similarity -----------------------------------------------------------------------------------

_SETPOINTS = ("heating_setpoint", "cooling_setpoint")


def _sums(ledger: GroupLedger) -> dict[str, tuple[float, float]]:
    """Each intensity as (numerator, denominator) of additive sums, so building values add up."""
    sums: dict[str, tuple[float, float]] = {}
    area = ledger.floor_area
    for kind, gain in ledger.gains.items():
        sums[f"gain_density:{kind}"] = (gain.installed, area)
        sums[f"gain_hours:{kind}"] = (float(gain.hourly.sum()), gain.installed)
    for name in _SETPOINTS:
        setpoint = getattr(ledger, name)
        weighted = float(setpoint.weighted.mean()) if setpoint.weighted.size else 0.0
        sums[name] = (weighted, setpoint.weight)
    sums["outdoor_air_per_area"] = (float(ledger.outdoor_air.hourly.sum()), area)
    sums["hot_water_per_area"] = (float(ledger.hot_water.volume.sum()), area)
    return sums


def intensities(ledger: GroupLedger) -> dict[str, float]:
    """A group's intensity vector (data-model.md: similarity).

    Components:

    - `gain_density:<kind>`: installed level ÷ floor area;
    - `gain_hours:<kind>`: annual gain hours, Σ hourly ÷ installed (0 when nothing is installed);
    - `heating_setpoint`, `cooling_setpoint`: the area-weighted mean setpoint over the run
      period; absent when the group has no heated (cooled) area;
    - `outdoor_air_per_area`: Σ hourly mechanical outdoor air ÷ floor area;
    - `hot_water_per_area`: Σ hourly hot-water volume ÷ floor area.

    Args:
        ledger: The group's ledger.

    Returns:
        Component name → value, in sorted name order.
    """
    values: dict[str, float] = {}
    for name, (numerator, denominator) in sorted(_sums(ledger).items()):
        if denominator > 0.0:
            values[name] = numerator / denominator
        elif name not in _SETPOINTS:
            values[name] = 0.0
    return values


def building_intensities(ledgers: Sequence[GroupLedger]) -> dict[str, float]:
    """The building-wide value of each intensity, from the sums of all groups' ledgers.

    Args:
        ledgers: Every group's ledger.

    Returns:
        Component name → building-wide value, for components with a positive denominator.
    """
    totals: dict[str, list[float]] = {}
    for ledger in ledgers:
        for name, (numerator, denominator) in _sums(ledger).items():
            pair = totals.setdefault(name, [0.0, 0.0])
            pair[0] += numerator
            pair[1] += denominator
    return {name: num / den for name, (num, den) in sorted(totals.items()) if den > 0.0}


def distance(a: GroupLedger, b: GroupLedger, building: Mapping[str, float]) -> float:
    """The similarity distance of two groups: Euclidean, each component ÷ its building-wide value.

    Args:
        a: One group's ledger.
        b: The other's.
        building: `building_intensities` of all groups.

    Returns:
        The distance; components whose building-wide value is 0 are left out, and a missing
        setpoint takes the building-wide value.
    """
    va, vb = intensities(a), intensities(b)
    squares: list[float] = []
    for name, scale in building.items():
        if scale == 0.0:
            continue
        x = va.get(name, scale if name in _SETPOINTS else 0.0)
        y = vb.get(name, scale if name in _SETPOINTS else 0.0)
        squares.append(((x - y) / scale) ** 2)
    return math.sqrt(math.fsum(squares))
