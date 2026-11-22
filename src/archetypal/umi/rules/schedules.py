"""Rules for day, week and year schedules (spec 003, research R7).

- **Calendar.** A UMI week's days are Monday to Sunday, as SBEM's. Weeks follow calendar
  weekdays. Monthly sums are taken over the reference year, a non-leap year starting on Monday
  (`REFERENCE_CALENDAR`).
- **UMI to SBEM.** A month covered by one year part takes that part's week, exactly. A month
  split by part boundaries is evaluated hour by hour and projected to one representative week
  with 002's projection (`archetypal.reduction.schedules.project`), which conserves the month's
  sum; the month is listed as approximate.
- **SBEM to UMI.** Consecutive equal months become one part ending on a month's last day,
  February on the 29th; equal weeks and days are one object. Holiday and design-day slots (when
  the SBEM week has them, UP-2) that differ from the day they replace are lost.
- **Type.** `Fraction`, `Temperature` and `AnyNumber` map by name (case-insensitive); any other
  UMI type becomes `AnyNumber`, noted. SBEM's year `Type` is the schedule's role, given by the
  field the schedule fills, so a UMI schedule used in several roles gives one SBEM year per
  role, each with the UMI name.

Functions take the `subject`, the `location` of the schedule (JSON pointer when reading, SBEM
field path when writing) and a `Findings` that collects losses and notes.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import TYPE_CHECKING, cast, get_args

import numpy as np
from epinterface.sbem.components.schedules import (
    DayComponent,
    ScheduleTypeLimitType,
    WeekComponent,
    YearComponent,
)

from archetypal.reduction.schedules import MONTHS, WEEKDAYS, RunPeriodCalendar, calendar_year, project
from archetypal.umi._format import DaySchedule, WeekSchedule, YearSchedule, YearSchedulePart
from archetypal.umi.correspondence import declare_rule, rule
from archetypal.umi.report import LossKind

if TYPE_CHECKING:
    from epinterface.sbem.components.schedules import YearScheduleCategory
    from pydantic import JsonValue

    from archetypal.umi.rules.materials import Findings

__all__ = [
    "MONTHS",
    "REFERENCE_CALENDAR",
    "SPECIAL_DAYS",
    "WEEKDAYS",
    "day_to_sbem",
    "day_to_umi",
    "type_to_sbem",
    "type_to_umi",
    "week_to_sbem",
    "week_to_umi",
    "year_to_sbem",
    "year_to_umi",
]

REFERENCE_CALENDAR = RunPeriodCalendar(year=calendar_year(1, 1, 0))
"""The reference year of UMI schedules: non-leap, starting on Monday, without holidays."""

SPECIAL_DAYS: tuple[tuple[str, int], ...] = (
    ("Holiday", 6),
    ("SummerDesignDay", 0),
    ("WinterDesignDay", 0),
    ("CustomDay1", 0),
    ("CustomDay2", 0),
)
"""SBEM's special-day slots (UP-2), each with the weekday (0 Monday) whose day it replaces."""

_TYPES: tuple[ScheduleTypeLimitType, ...] = get_args(ScheduleTypeLimitType)
_TYPE_BY_LOWER: dict[str, ScheduleTypeLimitType] = {kind.lower(): kind for kind in _TYPES}
_HOURS = 24
# Last day of each month for a part's end; February ends on the 29th (research R7).
_MONTH_ENDS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)

declare_rule("schedule.metadata")


def _pointer(location: str, *keys: str | int) -> str:
    """Append keys to a JSON pointer."""
    return location + "".join(f"/{key}" for key in keys)


def _path(location: str, key: str) -> str:
    """Append a field to an SBEM field path."""
    return f"{location}.{key}" if location else key


# --- schedule.type ------------------------------------------------------------------------


@rule("schedule.type", to="sbem")
def type_to_sbem(umi_type: str, subject: str, location: str, findings: Findings) -> ScheduleTypeLimitType:
    """Return the SBEM day type of a UMI schedule type.

    Args:
        umi_type: The UMI `Type`.
        subject: The template being read.
        location: The JSON pointer of the schedule that holds the type.
        findings: Collects a note when the type is not one of SBEM's three.

    Returns:
        `Fraction`, `Temperature` or `AnyNumber`.
    """
    kind = _TYPE_BY_LOWER.get(umi_type.lower())
    if kind is not None:
        return kind
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
    kind = type_to_sbem(day.type, subject, location, findings)
    hours = {f"Hour_{hour:02d}": value for hour, value in enumerate(day.values)}
    return DayComponent.model_validate({"Name": day.name or "", "Type": kind, **hours})


@rule("schedule.day", to="umi")
def day_to_umi(day: DayComponent) -> DaySchedule:
    """Translate an SBEM day to a UMI day schedule."""
    return DaySchedule.model_validate({"Name": day.Name, "Type": type_to_umi(day.Type), "Values": day.Values})


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
        component = WeekComponent.model_validate({"Name": week.name or "", **days})
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
        findings: Collects the losses: each holiday or design-day slot (UP-2) that differs from
            the day it would be replaced by in UMI, which has no such slots.

    Returns:
        The week schedule, its type the days' type.
    """
    return _Writer(subject, findings).week(week, location)


class _Writer:
    """Translates the schedules of one SBEM year, equal days and weeks to one object."""

    def __init__(self, subject: str, findings: Findings) -> None:
        self.subject = subject
        self.findings = findings
        self.days: dict[str, DaySchedule] = {}
        self.weeks: dict[str, WeekSchedule] = {}

    def day(self, day: DayComponent) -> DaySchedule:
        key = day.model_dump_json()
        if key not in self.days:
            self.days[key] = day_to_umi(day)
        return self.days[key]

    def week(self, week: WeekComponent, location: str) -> WeekSchedule:
        key = week.model_dump_json()
        if key in self.weeks:
            return self.weeks[key]
        for slot, weekday in SPECIAL_DAYS:
            special = cast("DayComponent | None", getattr(week, slot, None))
            replaced = week.Days[weekday]
            if special is not None and special.model_dump() != replaced.model_dump():
                self.findings.lose(
                    LossKind.LOST,
                    self.subject,
                    _path(location, slot),
                    special.Name,
                    "schedule.week",
                    f"UMI weeks have no {slot} slot; UMI uses the {WEEKDAYS[weekday]} day instead.",
                    replacement=replaced.Name,
                )
        schedule = WeekSchedule.model_validate({
            "Name": week.Name,
            "Days": [self.day(day) for day in week.Days],
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
        if len(set(parts)) == 1:
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
    component = YearComponent.model_validate({"Name": year.name or "", "Type": role, **months})
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
        "Parts": parts,
        "Type": type_to_umi(year.schedule_type_limits),
    })
