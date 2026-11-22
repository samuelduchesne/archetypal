"""What the rule modules share (spec 003): report context, schedule converters, upstream fields.

Private: the rule modules import from here; nothing outside `archetypal.umi` should.

- `RuleContext` collects the losses and notes of one translation, located below a JSON pointer
  (reading) or an SBEM field path (writing). The operation rules (`loads`, `conditioning`,
  `ventilation`, `hotwater`) take it as their `context` keyword.
- `ScheduleToSbem` and `ScheduleToUmi` are the schedule converters those rules receive, so they
  never evaluate or project a UMI schedule themselves (research R7).
- `REFERENCE_CALENDAR` is the reference year of UMI schedules.
- `report_upstream` and `upstream_defaults` handle the fields that wait for an upstream item
  (research R6, FR-010).

The module registers no rule, so the registry's auto-import skips it (its name starts with an
underscore) and `RULE_MODULES` names no prefix for it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, TypeAlias, cast

from epinterface.sbem.components.schedules import YearComponent, YearScheduleCategory

from archetypal.reduction.schedules import RunPeriodCalendar, calendar_year, year_values
from archetypal.umi._format import (
    DaySchedule,
    LibraryComponent,
    WeekSchedule,
    YearSchedule,
    YearSchedulePart,
)
from archetypal.umi.correspondence import MappingStatus, mappings_for
from archetypal.umi.report import Loss, LossKind, Note, NoteKind
from archetypal.umi.rules.building import metadata_to_sbem, metadata_to_umi

if TYPE_CHECKING:
    from collections.abc import Collection

    import numpy as np
    import numpy.typing as npt
    from epinterface.sbem.common import MetadataMixin, NamedObject
    from pydantic import JsonValue

    from archetypal.umi._format import (
        FormatModel,
    )
    from archetypal.umi.report import Direction

__all__ = [
    "ALWAYS_ON",
    "REFERENCE_CALENDAR",
    "RuleContext",
    "ScheduleToSbem",
    "ScheduleToUmi",
    "all_values_equal",
    "annual_values",
    "constant_year_schedule",
    "identity_to_sbem",
    "identity_to_umi",
    "json_value",
    "optional_schedule_to_sbem",
    "optional_schedule_to_umi",
    "report_upstream",
    "upstream_defaults",
]

ALWAYS_ON = "Always on"
"""The name of the schedule written where SBEM has none (availability, mechanical ventilation)."""

REFERENCE_CALENDAR = RunPeriodCalendar(calendar_year(1, 1, 0))
"""The reference year of UMI schedules (research R7): non-leap, starting on a Monday."""

ScheduleToSbem: TypeAlias = Callable[[YearSchedule, YearScheduleCategory, str], YearComponent]
"""Converts a UMI schedule: `(schedule, SBEM category, JSON pointer of the field) -> year`."""

ScheduleToUmi: TypeAlias = Callable[[YearComponent, str], YearSchedule]
"""Converts an SBEM schedule: `(year, SBEM field path) -> UMI schedule`."""


@dataclass(frozen=True)
class RuleContext:
    """Where a rule is applied, and the losses and notes it reports.

    Reading (`umi_to_sbem`), `at` is the JSON pointer of the UMI component being read
    (`/ZoneLoads/0`) and locations are pointers below it. Writing (`sbem_to_umi`), `at` is the
    zone group (`perimeter`) or a field path below it, and locations are dotted field paths
    (`perimeter.Operations.SpaceUse.Occupancy.MetabolicRate`), as contracts/translation-report.md
    requires.

    Attributes:
        subject: The template (reading) or archetype (writing).
        at: The JSON pointer or field path the locations start from.
        direction: Which way the translation goes.
        findings: The losses and notes reported so far, shared by every child context.
    """

    subject: str
    at: str
    direction: Direction
    findings: list[Loss | Note] = field(default_factory=list[Loss | Note])

    def location(self, key: str = "") -> str:
        """Return the location of `key` below `at` (`at` itself for an empty key)."""
        if not key:
            return self.at
        separator = "/" if self.direction == "umi_to_sbem" else "."
        return f"{self.at}{separator}{key}" if self.at else key

    def child(self, key: str) -> RuleContext:
        """Return a context at `key` below this one, sharing its findings."""
        return RuleContext(self.subject, self.location(key), self.direction, self.findings)

    def lose(
        self,
        key: str,
        value: JsonValue,
        *,
        rule: str,
        reason: str,
        replacement: JsonValue = None,
        upstream: str | None = None,
        kind: LossKind = LossKind.LOST,
    ) -> None:
        """Report that the value at `key` is not represented in the target."""
        self.findings.append(
            Loss(
                kind=kind,
                subject=self.subject,
                location=self.location(key),
                value=value,
                replacement=replacement,
                rule=rule,
                reason=reason,
                upstream=upstream,
            )
        )

    def note(self, key: str, value: JsonValue, *, rule: str, reason: str, kind: NoteKind = NoteKind.ASSUMED) -> None:
        """Report an assumption or default at `key` that loses nothing."""
        self.findings.append(
            Note(kind=kind, subject=self.subject, location=self.location(key), value=value, rule=rule, reason=reason)
        )

    @property
    def losses(self) -> list[Loss]:
        """The losses reported so far."""
        return [finding for finding in self.findings if isinstance(finding, Loss)]

    @property
    def notes(self) -> list[Note]:
        """The notes reported so far."""
        return [finding for finding in self.findings if isinstance(finding, Note)]


def json_value(value: object) -> JsonValue:
    """Return a UMI value as the report holds it: enums as Basilisk's integers, components by name."""
    if isinstance(value, Enum):
        return cast("JsonValue", value.value)
    if isinstance(value, LibraryComponent):
        return value.name
    if isinstance(value, tuple):
        return [json_value(item) for item in cast("tuple[object, ...]", value)]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    msg = f"no report form for {type(value).__name__}"
    raise TypeError(msg)


def _aliases(model: type[FormatModel]) -> dict[str, str]:
    """Map each Basilisk key of a format model to its field name."""
    return {info.alias or name: name for name, info in model.model_fields.items()}


def _upstream_rows(model: type[FormatModel], rule_id: str) -> list[tuple[str, str, str | None]]:
    """The `(key, field name, upstream item)` of each upstream row of `rule_id` on `model`."""
    aliases = _aliases(model)
    return [
        (row.umi_key, aliases[row.umi_key], row.upstream)
        for row in mappings_for(rule_id)
        if row.status is MappingStatus.UPSTREAM and row.umi_class == model.__name__ and row.umi_key in aliases
    ]


def report_upstream(component: FormatModel, rule_id: str, context: RuleContext, *, skip: Collection[str] = ()) -> None:
    """Report, on reading, the fields of `component` that wait for an upstream item, as lost.

    Until a field lands in a fork release, reading reports it (research R6, FR-010) when it
    differs from Basilisk's default, which is what writing gives back (`upstream_defaults`); the
    always-on schedule writing gives (`ALWAYS_ON`, no metadata) loses nothing either. Any other
    schedule, even one always on, would lose its name or metadata, so it is reported.

    Args:
        component: The UMI component read.
        rule_id: The rule whose upstream rows to report.
        context: The component's reading context.
        skip: Keys the caller reports itself (fields whose written-back value is not a default).
    """
    model = type(component)
    for key, name, upstream in _upstream_rows(model, rule_id):
        value: object = getattr(component, name)
        if key in skip or value == model.model_fields[name].default:
            continue
        if isinstance(value, YearSchedule) and _is_written_always_on(value):
            continue  # writing gives this always-on schedule back
        context.lose(
            key,
            json_value(getattr(component, name)),
            rule=rule_id,
            reason=f"SBEM has no field for {key} yet",
            upstream=upstream,
        )


def upstream_defaults(model: type[FormatModel], rule_id: str, context: RuleContext) -> dict[str, object]:
    """Return Basilisk's default of every upstream field of `rule_id` on `model`, noting each.

    Writing fills the UMI fields SBEM does not hold with Basilisk's defaults
    (contracts/umi-file.md, rule 6). Fields whose default is `None` (schedules) are left to the
    caller.

    Args:
        model: The UMI component class written.
        rule_id: The rule whose upstream rows to fill.
        context: The writing context, at the SBEM component that holds the UMI component.

    Returns:
        The defaults by field name.
    """
    defaults: dict[str, object] = {}
    for key, name, _ in _upstream_rows(model, rule_id):
        default = model.model_fields[name].default
        if default is None:
            continue
        defaults[name] = default
        context.note(
            "",
            json_value(default),
            rule=rule_id,
            reason=f"SBEM holds no {model.__name__}.{key}; Basilisk's default written",
            kind=NoteKind.DEFAULTED,
        )
    return defaults


def identity_to_sbem(component: LibraryComponent) -> dict[str, str | None]:
    """Return the SBEM `Name` and metadata of a UMI component (`names.metadata`, in `building`)."""
    return {"Name": component.name, **metadata_to_sbem(component)}


def identity_to_umi(component: MetadataMixin, context: RuleContext) -> dict[str, object]:
    """Return the UMI `Name` and metadata of an SBEM component, reporting what UMI cannot carry.

    Args:
        component: The SBEM component whose name the UMI component takes (data-model.md).
        context: The writing context at that component; SBEM's `Version` is lost there.
    """
    metadata = metadata_to_umi(component, subject=context.subject, location=context.location())
    context.findings.extend(metadata.losses)
    return {"Name": cast("NamedObject", component).Name, **metadata.fields}


def annual_values(year: YearComponent) -> npt.NDArray[np.float64]:
    """Return an SBEM schedule's hourly values over the reference year (8760 values)."""
    return year_values(year, REFERENCE_CALENDAR)


def constant_year_schedule(name: str, value: float, kind: str = "Fraction") -> YearSchedule:
    """Return a UMI schedule with one value in every hour of the year.

    Its day and week are named `"<name> day"` and `"<name> week"`.

    Args:
        name: The schedule's name.
        value: The value of every hour.
        kind: The schedule's `Type`.
    """
    day = DaySchedule.model_validate({"Name": f"{name} day", "Type": kind, "Values": (float(value),) * 24})
    week = WeekSchedule.model_validate({"Name": f"{name} week", "Type": kind, "Days": (day,) * 7})
    part = YearSchedulePart.model_validate({
        "FromDay": 1,
        "FromMonth": 1,
        "ToDay": 31,
        "ToMonth": 12,
        "Schedule": week,
    })
    return YearSchedule.model_validate({"Name": name, "Type": kind, "Parts": (part,)})


def all_values_equal(year: YearSchedule, value: float) -> bool:
    """Tell whether every hour of every day a UMI schedule uses equals `value`."""
    for part in year.parts:
        if part.schedule is None:
            return False
        for day in part.schedule.days:
            if day is None or any(hour != value for hour in day.values):
                return False
    return bool(year.parts)


def _is_written_always_on(year: YearSchedule) -> bool:
    """Whether a UMI schedule is exactly the always-on schedule written for SBEM's `None`."""
    written = constant_year_schedule(ALWAYS_ON, 1.0, year.type)
    return year.model_dump() == written.model_dump()


def optional_schedule_to_sbem(
    year: YearSchedule | None,
    key: str,
    role: YearScheduleCategory,
    *,
    schedule: ScheduleToSbem,
    context: RuleContext,
    rule_id: str,
    limits: Collection[str] = ("Fraction",),
) -> YearComponent | None:
    """Read a UMI schedule into an optional SBEM schedule whose `None` means always on (UP-9).

    No schedule, or the always-on schedule that `optional_schedule_to_umi` writes for `None`
    (named `ALWAYS_ON`, without metadata), gives `None`. Any other schedule, including an
    always-on one with another name or with metadata, is kept, so that writing it back
    changes nothing. A schedule whose type limits SBEM refuses for the field is lost, `None`
    kept.

    Args:
        year: The UMI schedule, or `None`.
        key: Its UMI key, for the report.
        role: The SBEM year's `Type`.
        schedule: The schedule converter.
        context: The reading context of the component holding it.
        rule_id: The rule reporting a loss.
        limits: The type limits SBEM accepts for the field.
    """
    if year is None or _is_written_always_on(year):
        return None
    component = schedule(year, role, context.location(key))
    if component.schedule_type_limits not in limits:
        context.lose(
            key,
            json_value(year),
            replacement=ALWAYS_ON,
            rule=rule_id,
            reason=f"SBEM needs a schedule of type {' or '.join(limits)} here, not {component.schedule_type_limits}; "
            "it applies at every hour, as an always-on schedule",
        )
        return None
    return component


def optional_schedule_to_umi(
    year: YearComponent | None, key: str, *, schedule: ScheduleToUmi, context: RuleContext, rule_id: str
) -> YearSchedule:
    """Write an optional SBEM schedule (UP-9); `None` (always on) is an always-on UMI schedule, noted.

    Args:
        year: The SBEM schedule, or `None`.
        key: Its SBEM key, for the report.
        schedule: The schedule converter.
        context: The writing context of the component holding it.
        rule_id: The rule noting an always-on schedule.
    """
    if year is not None:
        return schedule(year, context.location(key))
    context.note(
        key,
        ALWAYS_ON,
        rule=rule_id,
        reason="SBEM's None applies at every hour, so an always-on schedule is written",
    )
    return constant_year_schedule(ALWAYS_ON, 1.0)
