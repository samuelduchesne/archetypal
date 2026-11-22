"""The reduction report: how each SBEM value was derived, and what was lost (spec 002).

`ReductionReport` is the content of `<name>.report.json`, written beside the archetype by
`archetypal.io` (research R14; contracts/reduction-report.md). Its fields follow
data-model.md, section ReductionReport:

| Field | Model |
|---|---|
| `schema_version` | `"1.0"`; a reader accepts every `1.x` |
| `reproducibility` | `Reproducibility`: versions, SHA-256 of the inputs, the options |
| `groups[]` | `ReportGroup`: key, members (`GroupMember`), floor area and share, ledger |
| `pre_threshold_groups[]` | `PreThresholdGroup`: ledgers at the finest key, input to `merge` |
| `parameters[]` | `Parameter`: group, SBEM field path, value, rule id |
| `excluded_zones[]` | `ExcludedZone`: role, reason, envelope assignment |
| `small_group_merges[]` | `SmallGroupMerge` |
| `not_represented[]` | `archetypal.reduction.features.NotRepresented` |
| `merged_distinctions[]` | `MergedDistinction` (coarser layouts, US2) |
| `unattributed_energy` | standby and pilot energy by fuel, J |
| `building` | `BuildingBlock`: conditioned floor area, unrounded storey ratio |

Ledgers are `GroupLedger`s, whose profiles are written as `archetypal.io.EncodedProfile`
(base64 little-endian float64 with their length), so the report reads back exactly.

Order. Every array is sorted on validation (groups and pre-threshold groups by key, members
and excluded zones by name, parameters by group then path), so a builder may pass them in any
order and equal reports write byte-identical files.

Versions. `schema_version` is `MAJOR.MINOR`. Minor versions only add fields, so the report's
own models ignore unknown keys: a reader accepts every `1.x` file. The embedded ledger and
`NotRepresented` models refuse unknown keys; adding a field there is therefore a major change
(a decision of this module, so a ledger never silently loses a conserved total).

Invariants. `check_report_invariants(report, ...)` returns one message per violation of the
contract's invariants 1-7, each starting with `"invariant N (name):"`; one function per
invariant (`check_accounting`, `check_area`, `check_parameters`, `check_not_represented`,
`check_mergeable`, `check_reproducible`, `check_schema_version`) is available on its own.
`raise_for_invariants` raises `ReductionError` instead. Optional arguments pass facts the
report alone cannot know (the model's zone names, the zone roles, the leaf fields the
archetype sets, the unsupported features found).

Run `python -m archetypal.reduction.report --schema [PATH]` to write the published JSON
Schema, by default `docs/schemas/reduction-report-1.0.json`.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from collections import Counter
from dataclasses import dataclass, field
from datetime import date  # noqa: TC003 - pydantic resolves annotations at run time
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, JsonValue, ValidationError, field_validator

from archetypal.errors import ReductionError
from archetypal.io import dumps
from archetypal.reduction.classify import Role, SpaceUseSource  # noqa: TC001 - pydantic needs them
from archetypal.reduction.features import NotRepresented  # noqa: TC001 - pydantic needs it
from archetypal.reduction.ledger import EnvelopeAssignment, Fuel, GroupLedger
from archetypal.reduction.options import (
    Distinction,
    Exposure,
    GroupKey,
    Layout,
    ReductionOptions,
)
from archetypal.reduction.schedules import RunPeriodCalendar

if TYPE_CHECKING:
    from collections.abc import Callable, Collection, Iterable, Mapping, Sequence

    from numpy.typing import NDArray

__all__ = [
    "RULE_IDS",
    "SCHEMA_ID",
    "SCHEMA_PATH",
    "SCHEMA_VERSION",
    "BuildingBlock",
    "CalendarBlock",
    "ExcludedZone",
    "GroupMember",
    "MergedDistinction",
    "Parameter",
    "PreThresholdGroup",
    "ReductionReport",
    "ReportGroup",
    "Reproducibility",
    "SmallGroupMerge",
    "check_accounting",
    "check_area",
    "check_mergeable",
    "check_not_represented",
    "check_parameters",
    "check_report_invariants",
    "check_reproducible",
    "check_schema_version",
    "gather_not_represented",
    "group_name",
    "raise_for_invariants",
    "report_json_schema",
]

SCHEMA_VERSION = "1.0"
"""The version of the report's file format."""

SCHEMA_PATH = Path("docs/schemas/reduction-report-1.0.json")
"""Where the published JSON Schema lives, relative to the repository root."""

SCHEMA_ID = "https://samuelduchesne.github.io/archetypal/schemas/reduction-report-1.0.json"
"""The `$id` of the published JSON Schema."""

RULE_IDS: frozenset[str] = frozenset({
    "area.share",
    "gain.density",
    "schedule.normalised",
    "setpoint.area_mean",
    "envelope.equivalent",
    "mass.internal",
    "window.area_weighted",
    "airflow.mean_per_exterior_area",
    "airflow.peak_per_area",
    "airflow.dominant_category",
    "dhw.volume_per_person",
    "dhw.mains_plus_rise",
    "efficiency.delivered_over_consumed",
    "efficiency.rated",
    "efficiency.eir_linear",
    "fans.energy_per_volume",
    "fans.effective_supply_delta",
    "zone.attic",
    "zone.basement",
    "geometry.storeys",
})
"""The rule ids of data-model.md's derivation table (FR-025). Every parameter names one."""

_SCHEMA_VERSION_PATTERN = r"^1\.(0|[1-9][0-9]*)$"
_ANY_VERSION = re.compile(r"^(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
_SHA256_PATTERN = r"^[0-9a-f]{64}$"
_SHA256 = re.compile(_SHA256_PATTERN)
_ENERGYPLUS_PATTERN = r"^[0-9]+\.[0-9]+\.[0-9]+$"
_FINEST_KEY_LENGTH = 2

SHARE_TOLERANCE = 1e-12
"""Σ floor-area share differs from 1 by at most this much (invariant 2)."""

AREA_RTOL = 1e-12
"""Relative tolerance on floor-area equalities (invariant 2)."""

LEDGER_RTOL = 1e-9
"""Relative tolerance when pre-threshold ledgers are summed and compared with a group's (invariant 5)."""

LEDGER_ATOL = 1e-9
"""Absolute tolerance of that comparison, for totals that should be zero."""

ExcludedRole = Literal["attic", "basement", "excluded"]
"""The role of a zone left out of every group (R8)."""


class _Record(BaseModel):
    """A frozen record of the report; unknown keys from a later 1.x file are ignored."""

    model_config = ConfigDict(frozen=True, extra="ignore", allow_inf_nan=False)


def group_name(key: GroupKey) -> str:
    """Return the default name of a group: its key joined by `" / "`, or `"building"`.

    Args:
        key: The group key.

    Returns:
        The name, as `parameters[].group` and `not_represented[].affected_groups` give it.
    """
    return " / ".join(key) or "building"


# --- records -----------------------------------------------------------------------------------


class Reproducibility(_Record):
    """What a reduction needs to be repeated (invariant 6; research R14).

    Attributes:
        archetypal: The version of archetypal.
        epinterface: The version of epinterface (the SBEM fork).
        idfkit: The version of idfkit.
        energyplus: The EnergyPlus version of the model and results, `MAJOR.MINOR.PATCH`.
        model_sha256: SHA-256 of the model.
        results_sha256: SHA-256 of the SQLite results.
        weather_sha256: SHA-256 of the weather file, or `None` without one.
        options: The reduction's options; a space-use mapping is held sorted by zone.
    """

    archetypal: str
    epinterface: str
    idfkit: str
    energyplus: str = Field(pattern=_ENERGYPLUS_PATTERN)
    model_sha256: str = Field(pattern=_SHA256_PATTERN)
    results_sha256: str = Field(pattern=_SHA256_PATTERN)
    weather_sha256: str | None = Field(default=None, pattern=_SHA256_PATTERN)
    options: ReductionOptions

    @field_validator("options", mode="after")
    @classmethod
    def _sorted_mapping(cls, value: ReductionOptions) -> ReductionOptions:
        mapping = value.space_use_mapping
        if mapping is None:
            return value
        return value.model_copy(update={"space_use_mapping": dict(sorted(mapping.items()))})

    @classmethod
    def current(
        cls,
        *,
        energyplus_version: tuple[int, int, int],
        model_sha256: str,
        results_sha256: str,
        weather_sha256: str | None,
        options: ReductionOptions,
    ) -> Reproducibility:
        """Describe a reduction run with the installed versions of archetypal, epinterface and idfkit.

        Args:
            energyplus_version: The EnergyPlus version of the sources.
            model_sha256: SHA-256 of the model.
            results_sha256: SHA-256 of the results.
            weather_sha256: SHA-256 of the weather file, or `None`.
            options: The options.

        Returns:
            The block.
        """
        return cls(
            archetypal=_version("archetypal"),
            epinterface=_version("epinterface"),
            idfkit=_version("idfkit"),
            energyplus=".".join(str(part) for part in energyplus_version),
            model_sha256=model_sha256,
            results_sha256=results_sha256,
            weather_sha256=weather_sha256,
            options=options,
        )


def _version(distribution: str) -> str:
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:  # pragma: no cover - all three are dependencies
        return "unknown"


class GroupMember(_Record):
    """A zone of a group (FR-007, FR-012).

    Attributes:
        zone: The zone name (model spelling).
        multiplier: Its multiplier, `Multiplier` times `ListMultiplier`.
        floor_area: The floor area of one copy, m².
        space_use: Its space use (R4).
        space_use_source: Which tier of FR-007 decided the space use.
        exposure: Its exposure (R7).
    """

    zone: str
    multiplier: int = Field(ge=1)
    floor_area: float = Field(ge=0.0)
    space_use: str
    space_use_source: SpaceUseSource
    exposure: Exposure


class ReportGroup(_Record):
    """One SBEM zone group of the archetype.

    Attributes:
        name: The group's name, unique; `group_name(key)` by default.
        key: The group key of the layout (`Layout.group_key`).
        members: The zones, sorted by name.
        floor_area: Σ floor area, multipliers applied, m² (equals `ledger.floor_area`).
        floor_area_share: `floor_area / Σ floor_area` over the groups (rule `area.share`).
        ledger: The group's conserved totals.
    """

    name: str
    key: GroupKey
    members: tuple[GroupMember, ...]
    floor_area: float = Field(ge=0.0)
    floor_area_share: float = Field(ge=0.0, le=1.0)
    ledger: GroupLedger

    @field_validator("members", mode="after")
    @classmethod
    def _sorted_members(cls, value: tuple[GroupMember, ...]) -> tuple[GroupMember, ...]:
        return tuple(sorted(value, key=lambda m: m.zone))


class PreThresholdGroup(_Record):
    """A ledger before small groups are merged, at the finest key (FR-011; input to `merge`).

    Attributes:
        key: `(space_use, exposure)`, whatever the layout.
        ledger: The totals of the zones with that key.
    """

    key: GroupKey
    ledger: GroupLedger


class Parameter(_Record):
    """One SBEM value and the rule that produced it (FR-025).

    Attributes:
        group: The group name, or `None` for a building-level field (number of storeys).
        path: The SBEM field path, dotted (`"Space.Occupancy.PeopleDensity"`).
        value: The value written (JSON).
        rule: The rule id from the derivation table (`RULE_IDS`).
    """

    group: str | None
    path: str
    value: JsonValue
    rule: str


class ExcludedZone(_Record):
    """A zone in no group (FR-013, R8).

    Attributes:
        zone: The zone name.
        multiplier: Its multiplier.
        floor_area: The floor area of one copy, m².
        role: `attic`, `basement` or `excluded` (plenums, unconditioned spaces).
        reason: Why, in words.
        envelope: Where its envelope went, sorted.
    """

    zone: str
    multiplier: int = Field(default=1, ge=1)
    floor_area: float = Field(ge=0.0)
    role: ExcludedRole
    reason: str
    envelope: tuple[EnvelopeAssignment, ...] = ()

    @field_validator("envelope", mode="after")
    @classmethod
    def _sorted_envelope(cls, value: tuple[EnvelopeAssignment, ...]) -> tuple[EnvelopeAssignment, ...]:
        return tuple(sorted(value, key=EnvelopeAssignment.sort_key))


class SmallGroupMerge(_Record):
    """A group below the threshold merged into its most similar group (FR-008).

    Attributes:
        key: The merged group's key.
        into_key: The key of the group it went into.
        share: Its share of the conditioned floor area.
        distance: The similarity distance that chose `into_key`.
    """

    key: GroupKey
    into_key: GroupKey
    share: float = Field(ge=0.0, le=1.0)
    distance: float = Field(ge=0.0)


class MergedDistinction(_Record):
    """For a coarser layout, which finest keys one resulting group merges (US2; read by spec 003).

    Attributes:
        into_key: The resulting group's key.
        from_keys: The finest keys merged into it, sorted.
        lost: The distinctions lost, in group-key order.
    """

    into_key: GroupKey
    from_keys: tuple[GroupKey, ...]
    lost: tuple[Distinction, ...] = Field(min_length=1)

    @field_validator("from_keys", mode="after")
    @classmethod
    def _sorted_keys(cls, value: tuple[GroupKey, ...]) -> tuple[GroupKey, ...]:
        return tuple(sorted(value))


class CalendarBlock(_Record):
    """The run-period calendar the ledgers' profiles follow (`schedules.RunPeriodCalendar`).

    Attributes:
        year: The calendar year of the profiles (research R5).
        holidays: Dates marked `Holiday`, sorted.
        custom_day_1: Dates marked `CustomDay1`, sorted.
        custom_day_2: Dates marked `CustomDay2`, sorted.
    """

    year: int
    holidays: tuple[date, ...] = ()
    custom_day_1: tuple[date, ...] = ()
    custom_day_2: tuple[date, ...] = ()

    @field_validator("holidays", "custom_day_1", "custom_day_2", mode="after")
    @classmethod
    def _sorted_dates(cls, value: tuple[date, ...]) -> tuple[date, ...]:
        return tuple(sorted(set(value)))

    @classmethod
    def from_calendar(cls, calendar: RunPeriodCalendar) -> CalendarBlock:
        """Record a run-period calendar.

        Args:
            calendar: The calendar of the sources.

        Returns:
            The block.
        """
        return cls(
            year=calendar.year,
            holidays=tuple(calendar.holidays),
            custom_day_1=tuple(calendar.custom_day_1),
            custom_day_2=tuple(calendar.custom_day_2),
        )

    def to_calendar(self) -> RunPeriodCalendar:
        """Return the run-period calendar this block records."""
        return RunPeriodCalendar(
            year=self.year,
            holidays=frozenset(self.holidays),
            custom_day_1=frozenset(self.custom_day_1),
            custom_day_2=frozenset(self.custom_day_2),
        )


class BuildingBlock(_Record):
    """Building facts `merge` needs without the model (R6).

    Attributes:
        conditioned_floor_area: Σ floor area of the conditioned zones, multipliers applied, m².
        storey_ratio: Conditioned floor area ÷ floor area of the lowest level, unrounded.
        calendar: The run-period calendar of the profiles; `None` in a report that does not
            record it, which `merge` refuses.
        mains_temperature: The annual-mean mains water temperature, °C, or `None` without hot water.
        air_density: The standard air density of the fan volumes, kg/m³, or `None` when not recorded.
    """

    conditioned_floor_area: float = Field(gt=0.0)
    storey_ratio: float = Field(gt=0.0)
    calendar: CalendarBlock | None = None
    mains_temperature: float | None = None
    air_density: float | None = Field(default=None, gt=0.0)


def _not_represented_key(entry: NotRepresented) -> tuple[Any, ...]:
    return (
        entry.feature,
        entry.object_type or "",
        entry.objects,
        entry.affected_zones,
        entry.source,
        entry.folded_into or "",
        entry.affected_groups,
        entry.effect,
    )


def _parameter_key(parameter: Parameter) -> tuple[bool, str, str]:
    return (parameter.group is not None, parameter.group or "", parameter.path)


class ReductionReport(_Record):
    """The report of a reduction (data-model.md, ReductionReport; contracts/reduction-report.md).

    Attributes:
        schema_version: The file format's version, `MAJOR.MINOR`; `"1.0"` when written.
        reproducibility: Versions, input hashes and options.
        groups: The zone groups, sorted by key.
        pre_threshold_groups: Ledgers at the finest key before thresholding, sorted by key.
        parameters: Every SBEM value with its rule, sorted by group then path.
        excluded_zones: Zones in no group, sorted by name.
        small_group_merges: Small groups merged, sorted by key.
        not_represented: Features and values SBEM cannot hold (FR-026), sorted.
        merged_distinctions: For a coarser layout, the finest keys each group merges.
        unattributed_energy: Standby and pilot consumption by fuel, J (FR-022).
        building: Conditioned floor area and the unrounded storey ratio.
    """

    model_config = ConfigDict(
        frozen=True,
        extra="ignore",
        allow_inf_nan=False,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": SCHEMA_ID},
    )

    schema_version: str = Field(default=SCHEMA_VERSION, pattern=_SCHEMA_VERSION_PATTERN)
    reproducibility: Reproducibility
    groups: tuple[ReportGroup, ...]
    pre_threshold_groups: tuple[PreThresholdGroup, ...]
    parameters: tuple[Parameter, ...] = ()
    excluded_zones: tuple[ExcludedZone, ...] = ()
    small_group_merges: tuple[SmallGroupMerge, ...] = ()
    not_represented: tuple[NotRepresented, ...] = ()
    merged_distinctions: tuple[MergedDistinction, ...] = ()
    unattributed_energy: dict[Fuel, float] = Field(default_factory=dict[Fuel, float])
    building: BuildingBlock

    @field_validator("groups", mode="after")
    @classmethod
    def _sorted_groups(cls, value: tuple[ReportGroup, ...]) -> tuple[ReportGroup, ...]:
        return tuple(sorted(value, key=lambda g: g.key))

    @field_validator("pre_threshold_groups", mode="after")
    @classmethod
    def _sorted_pre(cls, value: tuple[PreThresholdGroup, ...]) -> tuple[PreThresholdGroup, ...]:
        return tuple(sorted(value, key=lambda g: g.key))

    @field_validator("parameters", mode="after")
    @classmethod
    def _sorted_parameters(cls, value: tuple[Parameter, ...]) -> tuple[Parameter, ...]:
        return tuple(sorted(value, key=_parameter_key))

    @field_validator("excluded_zones", mode="after")
    @classmethod
    def _sorted_excluded(cls, value: tuple[ExcludedZone, ...]) -> tuple[ExcludedZone, ...]:
        return tuple(sorted(value, key=lambda z: z.zone))

    @field_validator("small_group_merges", mode="after")
    @classmethod
    def _sorted_merges(cls, value: tuple[SmallGroupMerge, ...]) -> tuple[SmallGroupMerge, ...]:
        return tuple(sorted(value, key=lambda m: (m.key, m.into_key)))

    @field_validator("not_represented", mode="after")
    @classmethod
    def _sorted_not_represented(cls, value: tuple[NotRepresented, ...]) -> tuple[NotRepresented, ...]:
        return tuple(sorted(value, key=_not_represented_key))

    @field_validator("merged_distinctions", mode="after")
    @classmethod
    def _sorted_distinctions(cls, value: tuple[MergedDistinction, ...]) -> tuple[MergedDistinction, ...]:
        return tuple(sorted(value, key=lambda d: d.into_key))

    @field_validator("unattributed_energy", mode="after")
    @classmethod
    def _sorted_fuels(cls, value: dict[Fuel, float]) -> dict[Fuel, float]:
        return dict(sorted(value.items()))


def gather_not_represented(
    entries: Iterable[NotRepresented], zone_groups: Mapping[str, str]
) -> tuple[NotRepresented, ...]:
    """Fill each entry's affected groups from its zones, drop duplicates and sort (FR-026).

    Args:
        entries: Entries from `features.find_unsupported` and the folding modules.
        zone_groups: Zone name to the name of its group; zones in no group are skipped.

    Returns:
        The entries for `ReductionReport.not_represented`.
    """
    gathered: dict[str, NotRepresented] = {}
    for entry in entries:
        groups = {zone_groups[z] for z in entry.affected_zones if z in zone_groups} | set(entry.affected_groups)
        filled = entry.model_copy(update={"affected_groups": tuple(sorted(groups))})
        gathered[filled.model_dump_json()] = filled
    return tuple(sorted(gathered.values(), key=_not_represented_key))


# --- invariants ----------------------------------------------------------------------------------


def _message(number: int, name: str, text: str) -> str:
    return f"invariant {number} ({name}): {text}"


def _close(a: float, b: float, rtol: float, atol: float = 0.0) -> bool:
    return math.isclose(a, b, rel_tol=rtol, abs_tol=atol)


def _all_zones(report: ReductionReport) -> list[str]:
    zones = [m.zone for g in report.groups for m in g.members]
    zones.extend(z.zone for z in report.excluded_zones)
    return zones


def check_accounting(
    report: ReductionReport,
    *,
    zone_names: Iterable[str] | None = None,
    zone_roles: Mapping[str, Role] | None = None,
) -> list[str]:
    """Invariant 1: every zone appears exactly once, in a group or among the excluded zones (SC-006).

    Zone names are compared case-insensitively, as EnergyPlus does (its results upper-case them).

    Args:
        report: The report.
        zone_names: Every zone of the model, when known.
        zone_roles: Zone roles from classification, when known: attics, basements and other
            excluded zones must be excluded with that role, conditioned zones grouped.

    Returns:
        One message per violation.
    """
    texts: list[str] = []
    counts = Counter(z.casefold() for z in _all_zones(report))
    texts.extend(
        f"zone {zone!r} appears {count} times among the groups and excluded zones"
        for zone, count in sorted(counts.items())
        if count > 1
    )
    for group in report.groups:
        names = tuple(sorted(m.zone for m in group.members))
        if names != group.ledger.members:
            texts.append(
                f"group {group.name!r} lists members {list(names)} but its ledger holds {list(group.ledger.members)}"
            )
    if zone_names is not None:
        expected = {z.casefold() for z in zone_names}
        missing, extra = sorted(expected - set(counts)), sorted(set(counts) - expected)
        if missing:
            texts.append(f"zones of the model missing from the report: {missing}")
        if extra:
            texts.append(f"zones in the report that the model lacks: {extra}")
    if zone_roles is not None:
        texts.extend(_role_mismatches(report, zone_roles))
    return [_message(1, "accounting", text) for text in texts]


def _role_mismatches(report: ReductionReport, zone_roles: Mapping[str, Role]) -> list[str]:
    excluded = {z.zone.casefold(): z.role for z in report.excluded_zones}
    grouped = {m.zone.casefold() for g in report.groups for m in g.members}
    texts: list[str] = []
    for zone, role in sorted(zone_roles.items()):
        key = zone.casefold()
        if role == "conditioned":
            if key not in grouped:
                texts.append(f"conditioned zone {zone!r} is in no group")
        elif excluded.get(key) != role:
            where = f"excluded with role {excluded[key]!r}" if key in excluded else "not excluded"
            texts.append(f"zone {zone!r} has role {role!r} but is {where}")
    return texts


def check_area(report: ReductionReport, *, conditioned_floor_area: float | None = None) -> list[str]:
    """Invariant 2: shares sum to 1 and floor areas add up to the conditioned floor area (FR-014).

    Args:
        report: The report.
        conditioned_floor_area: The results' conditioned floor area, when known, m².

    Returns:
        One message per violation.
    """
    if not report.groups:
        return [_message(2, "area", "the report has no group")]
    texts: list[str] = []
    share_sum = math.fsum(g.floor_area_share for g in report.groups)
    if abs(share_sum - 1.0) > SHARE_TOLERANCE:
        texts.append(f"floor-area shares sum to {share_sum!r}, not 1 within {SHARE_TOLERANCE}")
    total = math.fsum(g.floor_area for g in report.groups)
    for group in report.groups:
        if not _close(group.floor_area, group.ledger.floor_area, AREA_RTOL):
            texts.append(
                f"group {group.name!r} floor area {group.floor_area!r} differs from its ledger's {group.ledger.floor_area!r}"
            )
        from_members = math.fsum(m.multiplier * m.floor_area for m in group.members)
        if not _close(group.floor_area, from_members, LEDGER_RTOL):
            texts.append(
                f"group {group.name!r} floor area {group.floor_area!r} differs from its members' {from_members!r}"
            )
        if total > 0 and abs(group.floor_area_share - group.floor_area / total) > SHARE_TOLERANCE:
            texts.append(f"group {group.name!r} share {group.floor_area_share!r} is not its floor area over the total")
    if not _close(total, report.building.conditioned_floor_area, AREA_RTOL):
        texts.append(
            f"groups' floor area {total!r} differs from the building's {report.building.conditioned_floor_area!r}"
        )
    if conditioned_floor_area is not None and not _close(total, conditioned_floor_area, AREA_RTOL):
        texts.append(
            f"groups' floor area {total!r} differs from the results' conditioned floor area {conditioned_floor_area!r}"
        )
    return [_message(2, "area", text) for text in texts]


def check_parameters(
    report: ReductionReport,
    *,
    set_parameters: Iterable[tuple[str | None, str]] | None = None,
    rule_ids: Collection[str] = RULE_IDS,
) -> list[str]:
    """Invariant 3: every parameter names a known rule, once per field (FR-025).

    Args:
        report: The report.
        set_parameters: `(group, path)` of every leaf field the archetype sets, when known;
            each must appear in `parameters[]`.
        rule_ids: The known rule ids.

    Returns:
        One message per violation.
    """
    texts: list[str] = []
    names = {g.name for g in report.groups}
    if len(names) != len(report.groups):
        texts.append("group names are not unique")
    counts = Counter((p.group, p.path) for p in report.parameters)
    texts.extend(
        f"parameter {path!r} of group {group!r} appears {count} times"
        for (group, path), count in sorted(counts.items(), key=lambda item: (item[0][0] or "", item[0][1]))
        if count > 1
    )
    for parameter in report.parameters:
        if parameter.rule not in rule_ids:
            texts.append(
                f"parameter {parameter.path!r} of group {parameter.group!r} has unknown rule {parameter.rule!r}"
            )
        if parameter.group is not None and parameter.group not in names:
            texts.append(f"parameter {parameter.path!r} names group {parameter.group!r}, which the report lacks")
    if set_parameters is not None:
        texts.extend(
            f"field {path!r} of group {group!r} is set but has no parameters[] entry"
            for group, path in set_parameters
            if (group, path) not in counts
        )
    return [_message(3, "parameters", text) for text in texts]


def _identity(entry: NotRepresented) -> str:
    return entry.model_copy(update={"affected_groups": ()}).model_dump_json()


def check_not_represented(report: ReductionReport, *, expected: Iterable[NotRepresented] | None = None) -> list[str]:
    """Invariant 4: nothing is dropped silently (FR-026).

    Args:
        report: The report.
        expected: Entries that must appear, such as `features.find_unsupported(source)` and the
            folding modules' entries; affected groups are ignored in the comparison, since the
            report fills them.

    Returns:
        One message per violation.
    """
    texts: list[str] = []
    names = {g.name for g in report.groups}
    zones = {z.casefold() for z in _all_zones(report)}
    for entry in report.not_represented:
        unknown_groups = sorted(set(entry.affected_groups) - names)
        if unknown_groups:
            texts.append(f"{entry.feature!r} names groups the report lacks: {unknown_groups}")
        unknown_zones = sorted(z for z in entry.affected_zones if z.casefold() not in zones)
        if unknown_zones:
            texts.append(f"{entry.feature!r} names zones the report lacks: {unknown_zones}")
    if expected is not None:
        present = {_identity(e) for e in report.not_represented}
        for entry in expected:
            if _identity(entry) not in present:
                what = entry.feature if entry.object_type is None else f"{entry.feature} ({entry.object_type})"
                texts.append(f"{what!r} is missing from not_represented[]")
    return [_message(4, "not represented", text) for text in texts]


def _arrays_close(a: NDArray[np.float64], b: NDArray[np.float64]) -> bool:
    if a.shape != b.shape:
        return False
    return bool((np.abs(a - b) <= LEDGER_ATOL + LEDGER_RTOL * np.abs(b)).all())


def _ledger_differences(a: object, b: object, path: str) -> list[str]:
    """The paths where two ledgers (or parts of them) differ beyond the ledger tolerances."""
    if isinstance(a, BaseModel) and isinstance(b, BaseModel):
        return [
            d
            for name in type(a).model_fields
            for d in _ledger_differences(getattr(a, name), getattr(b, name), f"{path}.{name}")
        ]
    if isinstance(a, dict) and isinstance(b, dict):
        left, right = cast("dict[Any, Any]", a), cast("dict[Any, Any]", b)
        if left.keys() == right.keys():
            return [d for k in left for d in _ledger_differences(left[k], right[k], f"{path}[{k}]")]
        same = False
    elif isinstance(a, np.ndarray) and isinstance(b, np.ndarray):
        same = _arrays_close(cast("NDArray[np.float64]", a), cast("NDArray[np.float64]", b))
    elif isinstance(a, float) and isinstance(b, float):
        same = _close(a, b, LEDGER_RTOL, LEDGER_ATOL)
    else:
        same = a == b
    return [] if same else [path]


@dataclass
class _Split:
    """How the pre-threshold ledgers fall into the report's groups."""

    parts: dict[str, list[GroupLedger]] = field(default_factory=dict[str, list[GroupLedger]])
    from_keys: dict[GroupKey, set[GroupKey]] = field(default_factory=dict[GroupKey, set[GroupKey]])
    seen: Counter[str] = field(default_factory=Counter[str])


def _split_pre_threshold(report: ReductionReport, texts: list[str]) -> _Split:
    member_info = {m.zone: (g, m) for g in report.groups for m in g.members}
    split = _Split(parts={g.name: [] for g in report.groups}, from_keys={g.key: set() for g in report.groups})
    for pre in report.pre_threshold_groups:
        if len(pre.key) != _FINEST_KEY_LENGTH:
            texts.append(f"pre-threshold key {pre.key!r} is not a (space use, exposure) key")
        split.seen.update(pre.ledger.members)
        owners: set[str] = set()
        for zone in pre.ledger.members:
            if zone not in member_info:
                texts.append(f"pre-threshold zone {zone!r} is in no group")
                continue
            group, info = member_info[zone]
            owners.add(group.name)
            if (info.space_use, info.exposure) != pre.key:
                texts.append(
                    f"zone {zone!r} has key {(info.space_use, info.exposure)!r} but sits in pre-threshold {pre.key!r}"
                )
            split.from_keys[group.key].add(pre.key)
        if len(owners) > 1:
            texts.append(f"pre-threshold {pre.key!r} is split over groups {sorted(owners)}")
        elif owners:
            split.parts[owners.pop()].append(pre.ledger)
    texts.extend(
        f"grouped zone {zone!r} is in no pre-threshold ledger" for zone in sorted(set(member_info) - set(split.seen))
    )
    texts.extend(
        f"zone {zone!r} is in {count} pre-threshold ledgers" for zone, count in sorted(split.seen.items()) if count > 1
    )
    return split


def check_mergeable(report: ReductionReport) -> list[str]:
    """Invariant 5: the pre-threshold ledgers, at the finest key, add up to the groups (FR-010, FR-011).

    Checks that each pre-threshold key is `(space_use, exposure)` of its members, that every
    grouped zone is in exactly one pre-threshold ledger, that each pre-threshold ledger lies in
    one group, that a group's ledger equals the sum of its pre-threshold ledgers, and, for a
    coarser layout, that `merged_distinctions[]` describes every group.

    Args:
        report: The report.

    Returns:
        One message per violation.
    """
    texts: list[str] = []
    layout = report.reproducibility.options.layout
    texts.extend(
        f"group {group.name!r} key {group.key!r} does not fit layout {layout.value!r}"
        for group in report.groups
        if len(group.key) != len(layout.distinctions)
    )
    keys = Counter(p.key for p in report.pre_threshold_groups)
    texts.extend(f"pre-threshold key {key!r} appears {count} times" for key, count in sorted(keys.items()) if count > 1)
    split = _split_pre_threshold(report, texts)
    for group in report.groups:
        try:
            total = sum(split.parts[group.name], GroupLedger())
        except ValueError as exc:
            texts.append(f"group {group.name!r}: pre-threshold ledgers cannot be added ({exc})")
            continue
        differences = _ledger_differences(total, group.ledger, "ledger")
        if differences:
            texts.append(f"group {group.name!r}: pre-threshold ledgers do not add up to its ledger at {differences}")
    texts.extend(_distinction_mismatches(report, layout, split.from_keys))
    return [_message(5, "mergeable", text) for text in texts]


def _distinction_mismatches(
    report: ReductionReport, layout: Layout, from_keys: Mapping[GroupKey, set[GroupKey]]
) -> list[str]:
    entries = report.merged_distinctions
    if layout is Layout.SPACE_USE_EXPOSURE:
        return ["merged_distinctions[] must be empty for the finest layout"] if entries else []
    possible = set(layout.lost_from(Layout.SPACE_USE_EXPOSURE))
    listed = {e.into_key for e in entries}
    texts = [f"group {key!r} has no merged_distinctions[] entry" for key in sorted(set(from_keys) - listed)]
    for entry in entries:
        if entry.into_key not in from_keys:
            texts.append(f"merged_distinctions[] names group {entry.into_key!r}, which the report lacks")
            continue
        if set(entry.from_keys) != from_keys[entry.into_key]:
            texts.append(
                f"group {entry.into_key!r} merges {sorted(from_keys[entry.into_key])}, not {list(entry.from_keys)}"
            )
        if not set(entry.lost) <= possible:
            texts.append(
                f"group {entry.into_key!r} loses {list(entry.lost)}; layout {layout.value!r} can only lose {sorted(possible)}"
            )
    return texts


def _is_sorted(items: Sequence[Any], key: Callable[[Any], Any]) -> bool:
    keys = [key(item) for item in items]
    return keys == sorted(keys)


def _block_problems(block: Reproducibility) -> list[str]:
    texts = [
        f"the {name} version is missing"
        for name in ("archetypal", "epinterface", "idfkit", "energyplus")
        if not getattr(block, name)
    ]
    hashes = {"model_sha256": block.model_sha256, "results_sha256": block.results_sha256}
    if block.weather_sha256 is not None:
        hashes["weather_sha256"] = block.weather_sha256
    texts.extend(
        f"{name} is not a lowercase SHA-256: {value!r}" for name, value in hashes.items() if not _SHA256.match(value)
    )
    return texts


def _order_problems(report: ReductionReport) -> list[str]:
    orders: tuple[tuple[str, Sequence[Any], Callable[[Any], Any]], ...] = (
        ("groups", report.groups, lambda g: g.key),
        ("pre_threshold_groups", report.pre_threshold_groups, lambda g: g.key),
        ("parameters", report.parameters, _parameter_key),
        ("excluded_zones", report.excluded_zones, lambda z: z.zone),
        ("small_group_merges", report.small_group_merges, lambda m: (m.key, m.into_key)),
        ("not_represented", report.not_represented, _not_represented_key),
        ("merged_distinctions", report.merged_distinctions, lambda d: d.into_key),
    )
    texts = [f"{name}[] is not sorted" for name, items, key in orders if not _is_sorted(items, key)]
    texts.extend(
        f"members of group {group.name!r} are not sorted"
        for group in report.groups
        if not _is_sorted(group.members, lambda m: m.zone)
    )
    return texts


def _read_back_problem(report: ReductionReport) -> str | None:
    try:
        text = dumps(report)
    except ValueError as exc:
        return str(exc)
    try:
        again = dumps(ReductionReport.model_validate_json(text))
    except ValidationError as exc:
        return f"the written report does not read back: {exc.error_count()} validation errors"
    return None if again == text else "the written report does not read back to the same text"


def check_reproducible(report: ReductionReport) -> list[str]:
    """Invariant 6: the reproducibility block is complete, and the file is deterministic.

    Byte identity of two reductions is tested end to end; this checks what one report can
    show: versions and hashes, sorted arrays, and a JSON text that reads back to itself.

    Args:
        report: The report.

    Returns:
        One message per violation.
    """
    texts = [*_block_problems(report.reproducibility), *_order_problems(report)]
    problem = _read_back_problem(report)
    if problem is not None:
        texts.append(problem)
    return [_message(6, "reproducible", text) for text in texts]


def check_schema_version(report: ReductionReport) -> list[str]:
    """Invariant 7: `schema_version` is `MAJOR.MINOR` with major version 1.

    Args:
        report: The report.

    Returns:
        One message per violation.
    """
    match = _ANY_VERSION.match(report.schema_version)
    if match is None:
        return [_message(7, "schema version", f"{report.schema_version!r} is not MAJOR.MINOR")]
    if match.group(1) != "1":
        return [_message(7, "schema version", f"{report.schema_version!r} is not a 1.x version this reader accepts")]
    return []


def check_report_invariants(
    report: ReductionReport,
    *,
    zone_names: Iterable[str] | None = None,
    zone_roles: Mapping[str, Role] | None = None,
    conditioned_floor_area: float | None = None,
    set_parameters: Iterable[tuple[str | None, str]] | None = None,
    expected_not_represented: Iterable[NotRepresented] | None = None,
    rule_ids: Collection[str] = RULE_IDS,
) -> list[str]:
    """Check invariants 1-7 of contracts/reduction-report.md.

    Args:
        report: The report.
        zone_names: Every zone of the model (invariant 1).
        zone_roles: Zone roles from classification (invariant 1).
        conditioned_floor_area: The results' conditioned floor area, m² (invariant 2).
        set_parameters: `(group, path)` of every leaf field the archetype sets (invariant 3).
        expected_not_represented: Entries that must be listed (invariant 4).
        rule_ids: The known rule ids (invariant 3).

    Returns:
        One message per violation, each starting with `"invariant N (name):"`; empty when the
        report holds every invariant.
    """
    return [
        *check_accounting(report, zone_names=zone_names, zone_roles=zone_roles),
        *check_area(report, conditioned_floor_area=conditioned_floor_area),
        *check_parameters(report, set_parameters=set_parameters, rule_ids=rule_ids),
        *check_not_represented(report, expected=expected_not_represented),
        *check_mergeable(report),
        *check_reproducible(report),
        *check_schema_version(report),
    ]


def raise_for_invariants(
    report: ReductionReport,
    *,
    zone_names: Iterable[str] | None = None,
    zone_roles: Mapping[str, Role] | None = None,
    conditioned_floor_area: float | None = None,
    set_parameters: Iterable[tuple[str | None, str]] | None = None,
    expected_not_represented: Iterable[NotRepresented] | None = None,
    rule_ids: Collection[str] = RULE_IDS,
) -> None:
    """Raise if the report breaks an invariant; a violation is a bug in reduction.

    Args:
        report: The report.
        zone_names: As `check_report_invariants`.
        zone_roles: As `check_report_invariants`.
        conditioned_floor_area: As `check_report_invariants`.
        set_parameters: As `check_report_invariants`.
        expected_not_represented: As `check_report_invariants`.
        rule_ids: As `check_report_invariants`.

    Raises:
        ReductionError: Listing every violation.
    """
    found = check_report_invariants(
        report,
        zone_names=zone_names,
        zone_roles=zone_roles,
        conditioned_floor_area=conditioned_floor_area,
        set_parameters=set_parameters,
        expected_not_represented=expected_not_represented,
        rule_ids=rule_ids,
    )
    if found:
        raise ReductionError("reduction report", "; ".join(found))  # noqa: TRY003 - lists the violations


# --- the published schema ------------------------------------------------------------------------


def report_json_schema() -> dict[str, Any]:
    """Return the JSON Schema of the report file, as published."""
    return ReductionReport.model_json_schema(mode="serialization")


def _schema_text() -> str:
    """Return the published schema's text: two-space indent, ASCII, final newline."""
    return json.dumps(report_json_schema(), indent=2, ensure_ascii=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the report's JSON Schema (`python -m archetypal.reduction.report --schema [PATH]`).

    Args:
        argv: The arguments, `sys.argv[1:]` by default.

    Returns:
        The exit status: 0 on success, 2 without `--schema`.
    """
    parser = argparse.ArgumentParser(
        prog="python -m archetypal.reduction.report", description="Write the reduction report's JSON Schema."
    )
    parser.add_argument(
        "--schema",
        nargs="?",
        const=str(SCHEMA_PATH),
        metavar="PATH",
        help=f"write the JSON Schema to PATH (default {SCHEMA_PATH})",
    )
    args = parser.parse_args(argv)
    if args.schema is None:
        parser.print_help()
        return 2
    path = Path(args.schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_schema_text(), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
