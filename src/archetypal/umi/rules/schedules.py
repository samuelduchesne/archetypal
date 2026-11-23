"""Rules for day, week and year schedules (spec 003, research R7).

- **Calendar.** A UMI week's days are Monday to Sunday, as SBEM's. Weeks follow calendar
  weekdays. Monthly sums are taken over the reference year, a non-leap year starting on Monday
  (`REFERENCE_CALENDAR`).
- **UMI to SBEM.** A month covered by one year part takes that part's week, exactly. A month
  split by part boundaries is evaluated hour by hour and projected to one representative week
  with 002's projection (`archetypal.reduction.schedules.project`), which conserves the month's
  sum; the month is listed as approximate.
- **SBEM to UMI.** Consecutive equal months become one part ending on a month's last day,
  February on the 29th; equal weeks and days are one object. UMI weeks have no holiday or
  design-day slots: reading leaves SBEM's (UP-2) unset. Writing loses a holiday slot when it
  differs from Sunday's day, which UMI uses instead, and every set design-day slot: UMI uses
  Monday's day, but read back the slot is unset, and epinterface's builder then gives gains,
  setpoints and availability its own design days. Each month's week reports its own losses.
- **Metadata** (`schedule.metadata`, UP-9). `Comments` and `DataSource` map to the SBEM
  schedule's `Comment` and `DataSource`. Basilisk fixes each schedule's `Category` (`Day`,
  `Week`, `Year`): it reads as an unset SBEM category, and another SBEM category is lost on
  writing.
- **Type.** `Fraction`, `Temperature` and `AnyNumber` map by name (case-insensitive); any other
  UMI type becomes `AnyNumber`, noted. SBEM's year `Type` is the schedule's role, given by the
  field the schedule fills, so a UMI schedule used in several roles gives one SBEM year per
  role, each with the UMI name.

Functions take the `subject`, the `location` of the schedule (JSON pointer when reading, SBEM
field path when writing) and a `Findings` (`archetypal.umi.report`) that collects losses and notes.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, cast, get_args

from epinterface.interface import PROTECTED_SCHEDULE_NAMES
from epinterface.sbem.components.schedules import (
    DayComponent,
    ScheduleTypeLimitType,
    WeekComponent,
    YearComponent,
)

from archetypal.reduction.schedules import MONTHS, WEEKDAYS, project
from archetypal.umi._format import DaySchedule, WeekSchedule, YearSchedule, YearSchedulePart
from archetypal.umi.correspondence import rule
from archetypal.umi.report import LossKind
from archetypal.umi.rules._common import REFERENCE_CALENDAR

if TYPE_CHECKING:
    from collections.abc import Sequence

    import numpy as np
    from epinterface.sbem.common import MetadataMixin
    from epinterface.sbem.components.schedules import YearScheduleCategory
    from pydantic import JsonValue

    from archetypal.umi._format import LibraryComponent
    from archetypal.umi.report import Findings

__all__ = [
    "MONTHS",
    "REFERENCE_CALENDAR",
    "SPECIAL_DAYS",
    "WEEKDAYS",
    "day_to_sbem",
    "day_to_umi",
    "metadata_to_sbem",
    "metadata_to_umi",
    "type_to_sbem",
    "type_to_umi",
    "week_to_sbem",
    "week_to_umi",
    "year_to_sbem",
    "year_to_umi",
]

SPECIAL_DAYS: tuple[tuple[str, int], ...] = (
    ("Holiday", 6),
    ("SummerDesignDay", 0),
    ("WinterDesignDay", 0),
)
"""SBEM's holiday and design-day slots (UP-2), each with the weekday (0 Monday) whose day UMI uses."""

_TYPES: tuple[ScheduleTypeLimitType, ...] = get_args(ScheduleTypeLimitType)
_TYPE_BY_LOWER: dict[str, ScheduleTypeLimitType] = {kind.lower(): kind for kind in _TYPES}
_HOURS = 24
# Last day of each month for a part's end; February ends on the 29th (research R7).
_MONTH_ENDS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@rule("schedule.metadata", to="sbem")
def metadata_to_sbem(schedule: LibraryComponent) -> dict[str, str | None]:
    """Return an SBEM schedule's metadata (UP-9): UMI's comments and data source; no category.

    Basilisk fixes a schedule's category (`Day`, `Week`, `Year`), so it carries nothing.
    """
    return {"Comment": schedule.comments, "DataSource": schedule.data_source}


@rule("schedule.metadata", to="umi")
def metadata_to_umi(schedule: MetadataMixin, subject: str, location: str, findings: Findings) -> dict[str, str | None]:
    """Return a UMI schedule's metadata (UP-9), listing what Basilisk's schedules cannot hold.

    Args:
        schedule: The SBEM day, week or year.
        subject: The archetype being written.
        location: The schedule's SBEM field path.
        findings: Collects the losses: a category (Basilisk fixes it) and a version.

    Returns:
        `Comments` and `DataSource`, by Basilisk key.
    """
    for key, value, reason in (
        ("Category", schedule.Category, "Basilisk fixes the category of schedules (Day, Week, Year)."),
        ("Version", schedule.Version, "UMI schedules have no version."),
    ):
        if value is not None:
            findings.lose(LossKind.LOST, subject, _path(location, key), value, "schedule.metadata", reason)
    return {"Comments": schedule.Comment, "DataSource": schedule.DataSource}


def _pointer(location: str, *keys: str | int) -> str:
    """Append keys to a JSON pointer."""
    return location + "".join(f"/{key}" for key in keys)


def _path(location: str, key: str) -> str:
    """Append a field to an SBEM field path."""
    return f"{location}.{key}" if location else key


# --- schedule.type ------------------------------------------------------------------------


_ON_OFF = frozenset({"on/off", "onoff"})
"""The spellings of EnergyPlus's On/Off schedule type, lower case and without spaces."""


@rule("schedule.type", to="sbem")
def type_to_sbem(
    umi_type: str, subject: str, location: str, findings: Findings, values: Sequence[float] | None = None
) -> ScheduleTypeLimitType:
    """Return the SBEM day type of a UMI schedule type.

    Args:
        umi_type: The UMI `Type`.
        subject: The template being read.
        location: The JSON pointer of the schedule that holds the type.
        findings: Collects a note when the type is not one of SBEM's three.
        values: A day's values, when known: an On/Off day with a value outside [0, 1] is not a
            fraction, so it is read as AnyNumber.

    Returns:
        `Fraction`, `Temperature` or `AnyNumber`; `On/Off` (0 or 1) is read as `Fraction`.
    """
    kind = _TYPE_BY_LOWER.get(umi_type.lower())
    if kind is not None:
        return kind
    fractions = values is None or all(0.0 <= value <= 1.0 for value in values)
    if umi_type.lower().replace(" ", "") in _ON_OFF and fractions:
        # EnergyPlus's availability type, 0 or 1: a fraction, so availability and outdoor-air
        # schedules keep their hours instead of reading as always on.
        findings.assume(
            subject,
            _pointer(location, "Type"),
            umi_type,
            "schedule.type",
            f"SBEM's day types are {', '.join(_TYPES)}; type {umi_type!r} (0 or 1) is read as Fraction.",
        )
        return "Fraction"
    findings.assume(
        subject,
        _pointer(location, "Type"),
        umi_type,
        "schedule.type",
        f"SBEM's day types are {', '.join(_TYPES)}; type {umi_type!r} is read as AnyNumber.",
    )
    return "AnyNumber"


@rule("schedule.type", to="umi")
def type_to_umi(sbem_type: ScheduleTypeLimitType) -> str:
    """Return the UMI schedule type of an SBEM day type: the same name."""
    return sbem_type


# --- schedule.day -------------------------------------------------------------------------


@rule("schedule.day", to="sbem")
def day_to_sbem(day: DaySchedule, subject: str, location: str, findings: Findings) -> DayComponent:
    """Translate a UMI day schedule: its 24 values, hour 0 first.

    Raises:
        ValueError: The day does not have 24 values, or a value is outside its type's limits.
    """
    if len(day.values) != _HOURS:
        msg = f"{location}: a day schedule needs 24 values, not {len(day.values)}"
        raise ValueError(msg)
    kind = type_to_sbem(day.type, subject, location, findings, day.values)
    hours = {f"Hour_{hour:02d}": value for hour, value in enumerate(day.values)}
    return DayComponent.model_validate({"Name": day.name or "", "Type": kind, **metadata_to_sbem(day), **hours})


@rule("schedule.day", to="umi")
def day_to_umi(day: DayComponent) -> DaySchedule:
    """Translate an SBEM day to a UMI day schedule, with its comment and data source."""
    return DaySchedule.model_validate({
        "Name": day.Name,
        "Comments": day.Comment,
        "DataSource": day.DataSource,
        "Type": type_to_umi(day.Type),
        "Values": day.Values,
    })


# --- schedule.week ------------------------------------------------------------------------


class _Reader:
    """Translates the schedules of one UMI year, each day and week once."""

    def __init__(self, subject: str, findings: Findings) -> None:
        self.subject = subject
        self.findings = findings
        self.days: dict[int, DayComponent] = {}
        self.weeks: dict[int, WeekComponent] = {}

    def day(self, day: DaySchedule, location: str) -> DayComponent:
        key = id(day)
        if key not in self.days:
            self.days[key] = day_to_sbem(day, self.subject, location, self.findings)
        return self.days[key]

    def week(self, week: WeekSchedule, location: str) -> WeekComponent:
        key = id(week)
        if key in self.weeks:
            return self.weeks[key]
        if len(week.days) != len(WEEKDAYS):
            msg = f"{location}: a week schedule needs 7 days, not {len(week.days)}"
            raise ValueError(msg)
        days: dict[str, DayComponent] = {}
        for index, (weekday, day) in enumerate(zip(WEEKDAYS, week.days, strict=True)):
            if day is None:
                msg = f"{_pointer(location, 'Days', index)}: the week has no {weekday} schedule"
                raise ValueError(msg)
            days[weekday] = self.day(day, _pointer(location, "Days", index))
        component = WeekComponent.model_validate({"Name": week.name or "", **metadata_to_sbem(week), **days})
        _check_type(week.type, component.Type, self.subject, location, self.findings)
        self.weeks[key] = component
        return component


def _check_type(
    declared: str | None, days_type: ScheduleTypeLimitType, subject: str, location: str, findings: Findings
) -> None:
    """List a week's or year's type as lost when it is not its days' type (SBEM types days only)."""
    if declared is None or _TYPE_BY_LOWER.get(declared.lower()) == days_type:
        return
    findings.lose(
        LossKind.LOST,
        subject,
        _pointer(location, "Type"),
        declared,
        "schedule.type",
        "SBEM keeps the type on days only; this type differs from its days' type.",
        replacement=days_type,
    )


@rule("schedule.week", to="sbem")
def week_to_sbem(week: WeekSchedule, subject: str, location: str, findings: Findings) -> WeekComponent:
    """Translate a UMI week schedule: its seven days, Monday first.

    Raises:
        ValueError: The week does not have seven days, or a day is invalid.
    """
    return _Reader(subject, findings).week(week, location)


@rule("schedule.week", to="umi")
def week_to_umi(week: WeekComponent, subject: str, location: str, findings: Findings) -> WeekSchedule:
    """Translate an SBEM week to a UMI week schedule.

    Args:
        week: The week.
        subject: The archetype being written.
        location: The week's SBEM field path.
        findings: Collects the losses: each holiday slot (UP-2) that differs from Sunday's day,
            and each set design-day slot, which UMI has no slot for.

    Returns:
        The week schedule, its type the days' type.
    """
    writer = _Writer(subject, findings)
    writer.lose_slots(week, location)
    return writer.week(week, location)


class _Writer:
    """Translates the schedules of one SBEM year, equal days and weeks to one object."""

    def __init__(self, subject: str, findings: Findings) -> None:
        self.subject = subject
        self.findings = findings
        self.days: dict[str, DaySchedule] = {}
        self.weeks: dict[str, WeekSchedule] = {}

    def day(self, day: DayComponent, location: str) -> DaySchedule:
        key = day.model_dump_json()
        if key not in self.days:
            metadata_to_umi(day, self.subject, location, self.findings)
            self.days[key] = day_to_umi(day)
        return self.days[key]

    def lose_slots(self, week: WeekComponent, location: str) -> None:
        """Report the week's special-day slots UMI cannot hold, at `location` (one month's week).

        A holiday slot is lost when it differs from Sunday's day, which both UMI and
        epinterface's builder use without one. A design-day slot is lost whenever it is set:
        reading leaves it unset, and the builder then uses its own design day for gains,
        setpoints and availability (always on, extreme setpoints), Monday's elsewhere.
        """
        for slot, weekday in SPECIAL_DAYS:
            special = cast("DayComponent | None", getattr(week, slot))
            if special is None:
                continue
            replaced = week.Days[weekday]
            if slot == "Holiday" and special.model_dump() == replaced.model_dump():
                continue
            reason = f"UMI weeks have no {slot} slot; UMI uses the {WEEKDAYS[weekday]} day instead"
            if slot != "Holiday":
                reason += (
                    ", and reading leaves the slot unset, so epinterface's builder uses its own design day "
                    "where it gives one (gains, setpoints, availability)"
                )
            self.findings.lose(
                LossKind.LOST,
                self.subject,
                _path(location, slot),
                special.Name,
                "schedule.week",
                f"{reason}.",
                replacement=replaced.Name,
            )

    def week(self, week: WeekComponent, location: str) -> WeekSchedule:
        key = week.model_dump_json()
        if key in self.weeks:
            return self.weeks[key]
        schedule = WeekSchedule.model_validate({
            "Name": week.Name,
            **metadata_to_umi(week, self.subject, location, self.findings),
            "Days": [self.day(day, _path(location, weekday)) for weekday, day in zip(WEEKDAYS, week.Days, strict=True)],
            "Type": type_to_umi(week.Type),
        })
        self.weeks[key] = schedule
        return schedule


# --- schedule.months ----------------------------------------------------------------------


def _part_of_each_day(year: YearSchedule, location: str) -> list[int]:
    """Return the index of the part covering each day of the reference year (first match)."""
    start = date(REFERENCE_CALENDAR.year, 1, 1)
    covering: list[int] = []
    for offset in range(REFERENCE_CALENDAR.days):
        today = start + timedelta(days=offset)
        key = (today.month, today.day)
        index = next(
            (
                i
                for i, part in enumerate(year.parts)
                if (part.from_month, part.from_day) <= key <= (part.to_month, part.to_day)
            ),
            None,
        )
        if index is None:
            msg = f"{_pointer(location, 'Parts')}: no part covers {today:%m-%d}"
            raise ValueError(msg)
        covering.append(index)
    return covering


def _part_week(year: YearSchedule, index: int, location: str) -> WeekSchedule:
    part: YearSchedulePart = year.parts[index]
    if part.schedule is None:
        msg = f"{_pointer(location, 'Parts', index, 'Schedule')}: the part has no week schedule"
        raise ValueError(msg)
    return part.schedule


def _runs(month: int, parts: list[int], year: YearSchedule, location: str) -> list[JsonValue]:
    """Describe the date ranges of a split month and the week each used."""
    runs: list[JsonValue] = []
    first = 0
    for day in range(1, len(parts) + 1):
        if day == len(parts) or parts[day] != parts[first]:
            runs.append({
                "week": _part_week(year, parts[first], location).name,
                "from": f"{month + 1:02d}-{first + 1:02d}",
                "to": f"{month + 1:02d}-{day:02d}",
            })
            first = day
    return runs


def _projected_week(days: np.ndarray, kind: ScheduleTypeLimitType, name: str, month: int) -> WeekComponent:
    """Build the representative week of one month from projected (7, 24) values."""
    week: dict[str, DayComponent] = {}
    for weekday, values in zip(WEEKDAYS, days, strict=True):
        hours = {f"Hour_{hour:02d}": float(value) for hour, value in enumerate(values)}
        week[weekday] = DayComponent.model_validate({
            "Name": f"{name} {MONTHS[month]} {weekday}",
            "Type": kind,
            **hours,
        })
    return WeekComponent.model_validate({"Name": f"{name} {MONTHS[month]}", **week})


@rule("schedule.months", to="sbem")
def year_to_sbem(
    year: YearSchedule, role: YearScheduleCategory, subject: str, location: str, findings: Findings
) -> YearComponent:
    """Translate a UMI year schedule to an SBEM year, one week per calendar month.

    A month covered by one part takes that part's week. A month split by part boundaries is
    projected, from the hourly values of the reference year, onto one representative week
    (002's projection: each weekday's day is the mean of that weekday's days in the month),
    which conserves the month's sum; it is listed as approximate.

    Args:
        year: The year schedule.
        role: What the schedule drives (SBEM's year `Type`), from the field it fills.
        subject: The template being read.
        location: The year's JSON pointer.
        findings: Collects the losses (split months, types) and notes (types).

    Returns:
        The SBEM year, named as the UMI schedule.

    Raises:
        ValueError: A day of the reference year is in no part, a part has no week, or a week or
            day is invalid.
    """
    reader = _Reader(subject, findings)
    covering = _part_of_each_day(year, location)
    by_month: list[list[int]] = [[] for _ in MONTHS]
    for day, index in enumerate(covering):
        by_month[int(REFERENCE_CALENDAR.day_months[day])].append(index)
    weeks: dict[int, WeekComponent] = {
        index: reader.week(_part_week(year, index, location), _pointer(location, "Parts", index, "Schedule"))
        for index in sorted(set(covering))
    }
    projected: np.ndarray | None = None
    months: dict[str, WeekComponent] = {}
    for month, parts in enumerate(by_month):
        # Parts that use one week (a converter's split periods with deduplicated weeks) are one week.
        if len({id(weeks[index]) for index in parts}) == 1:
            months[MONTHS[month]] = weeks[parts[0]]
            continue
        if projected is None:
            profile = [
                value
                for day, index in enumerate(covering)
                for value in weeks[index].Days[int(REFERENCE_CALENDAR.day_weekdays[day])].Values
            ]
            projected = project(profile, REFERENCE_CALENDAR)
        kinds: set[ScheduleTypeLimitType] = {weeks[index].Type for index in parts}
        if len(kinds) != 1:
            msg = f"{_pointer(location, 'Parts')}: {MONTHS[month]} mixes weeks of types {sorted(kinds)}"
            raise ValueError(msg)
        week = _projected_week(projected[month], kinds.pop(), year.name or "", month)
        months[MONTHS[month]] = week
        findings.lose(
            LossKind.APPROXIMATE,
            subject,
            _pointer(location, "Parts"),
            {"month": MONTHS[month], "parts": _runs(month, parts, year, location)},
            "schedule.months",
            f"Part boundaries fall inside {MONTHS[month]}; its weeks are projected to one "
            "representative week that conserves the month's sum over the reference year.",
            replacement=week.Name,
        )
    name = year.name or ""
    if name in PROTECTED_SCHEDULE_NAMES or "Activity_Schedule" in name:
        # epinterface keeps these names for its own schedules (AllOn, AlwaysOn, ...).
        renamed = f"{name} (UMI)".replace("Activity_Schedule", "Activity Schedule")
        findings.lose(
            LossKind.RENAMED,
            subject,
            _pointer(location, "Name"),
            name,
            "names.collision",
            f"epinterface keeps the schedule name {name!r} for its own schedules.",
            replacement=renamed,
        )
        name = renamed
    component = YearComponent.model_validate({
        "Name": name,
        "Type": role,
        **metadata_to_sbem(year),
        **months,
    })
    _check_type(year.type, component.schedule_type_limits, subject, location, findings)
    return component


@rule("schedule.months", to="umi")
def year_to_umi(year: YearComponent, subject: str, location: str, findings: Findings) -> YearSchedule:
    """Translate an SBEM year to a UMI year schedule, exactly.

    Consecutive months with equal weeks become one part, ending on the last month's last day,
    February on the 29th. Equal weeks and days are one object, so the writer shares them.

    Args:
        year: The SBEM year.
        subject: The archetype being written.
        location: The year's SBEM field path.
        findings: Collects the weeks' losses (holiday and design-day slots).

    Returns:
        The year schedule, named as the SBEM year, its type the days' type.
    """
    writer = _Writer(subject, findings)
    parts: list[YearSchedulePart] = []
    weeks = year.Weeks
    first = 0
    for month in range(1, len(weeks) + 1):
        writer.lose_slots(weeks[month - 1], _path(location, MONTHS[month - 1]))
        if month < len(weeks) and weeks[month].model_dump() == weeks[first].model_dump():
            continue
        parts.append(
            YearSchedulePart.model_validate({
                "FromMonth": first + 1,
                "FromDay": 1,
                "ToMonth": month,
                "ToDay": _MONTH_ENDS[month - 1],
                "Schedule": writer.week(weeks[first], _path(location, MONTHS[first])),
            })
        )
        first = month
    return YearSchedule.model_validate({
        "Name": year.Name,
        **metadata_to_umi(year, subject, location, findings),
        "Parts": parts,
        "Type": type_to_umi(year.schedule_type_limits),
    })
