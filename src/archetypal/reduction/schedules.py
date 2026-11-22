"""Schedules: evaluation on the run-period calendar, representative days and output forms.

Research R5 (spec 002) fixes the method:

- each distinct schedule of a model is evaluated once, hourly, with `idfkit.schedules.values`,
  on the calendar of the source run period (`RunPeriodCalendar`);
- an hourly `Profile` is projected onto SBEM's representative days, one per month and weekday,
  each the mean over that month's days of that weekday, holidays included (`project`). The
  projection is linear and conserves the energy of every month of the source calendar;
- representative days become epinterface `YearComponent`s (`to_year_component`), and any
  `YearComponent` becomes `Schedule:Compact` text (`schedule_compact`, FR-023).

Special days in SBEM follow epinterface's own EnergyPlus writer: a holiday takes Sunday's day,
custom days and design days take Monday's. `year_values` and `schedule_compact` both use that
rule, so the `Schedule:Compact` text evaluates to the same hourly values as the `YearComponent`
on any calendar.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass, field
from datetime import date
from functools import cached_property
from itertools import count
from typing import TYPE_CHECKING, Any, TypeAlias, cast

import numpy as np
from epinterface.sbem.components.schedules import DayComponent, WeekComponent, YearComponent
from idfkit.schedules import get_holidays, get_special_days_by_type, values

from archetypal.reduction._bridges import normalise_schedule_year

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence
    from pathlib import Path

    import numpy.typing as npt
    from epinterface.sbem.components.schedules import ScheduleTypeLimitType, YearScheduleCategory
    from idfkit.document import (
        AnyScheduleFile,
        AnyScheduleYear,
        ScheduleCompact,
        ScheduleConstant,
        ScheduleYear,
    )
    from idfkit.versioned import IDFDocumentSince22_1, ScheduleYear_v9_0_to_v22_1

__all__ = [
    "MONTHS",
    "WEEKDAYS",
    "AnySchedule",
    "Profile",
    "RepresentativeDays",
    "RunPeriodCalendar",
    "ScheduleEvaluator",
    "calendar_year",
    "expand",
    "project",
    "representative_days",
    "schedule_compact",
    "schedule_index",
    "to_year_component",
    "year_values",
]

Profile: TypeAlias = "npt.NDArray[np.float64]"
"""One float64 value per hour of the run-period calendar: 8760 values, or 8784 in a leap year."""

RepresentativeDays: TypeAlias = "npt.NDArray[np.float64]"
"""SBEM's representative days: a float64 array of shape (12 months, 7 weekdays Monday first, 24 hours)."""

AnySchedule: TypeAlias = "ScheduleCompact | AnyScheduleYear | ScheduleConstant | AnyScheduleFile"
"""A schedule object that covers a whole year, as loads and setpoints reference it."""

MONTHS = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")

_MONDAY = 0
_DECEMBER = 11
_LAST_HOUR = 23
_SUNDAY = 6
# First year searched by `calendar_year`; any year with the same weekday alignment is equivalent.
_FIRST_CANDIDATE_YEAR = 2013
# Through: dates of each month. February ends on 02/29 so that a leap day stays in February;
# idfkit and EnergyPlus both read 02/29 as the end of February in a non-leap year.
_MONTH_ENDS = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
# For: labels, Monday to Sunday. Special days follow epinterface's `WeekComponent.add_week_to_idf`.
_FOR_LABELS = (
    "Monday SummerDesignDay WinterDesignDay CustomDay1 CustomDay2",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday Holiday",
)
# Values of a Fraction schedule this far outside [0, 1] are float round-off, and are clipped.
_FRACTION_TOLERANCE = 1e-9
_FORBIDDEN_NAME_CHARACTERS = frozenset(",;!\n\r")


def calendar_year(begin_month: int, begin_day: int, weekday: int) -> int:
    """Return the calendar year in which a run period's begin date falls on its start weekday.

    The year is the first one from 2013 that is not a leap year (a leap year only for a begin
    date of 29 February) and whose begin date falls on `weekday`. Every such year gives the same
    days of the week, so the choice changes no result.

    Args:
        begin_month: The run period's begin month, 1 to 12.
        begin_day: The run period's begin day of the month.
        weekday: The start weekday, 0 for Monday to 6 for Sunday.

    Returns:
        The year.
    """
    leap = (begin_month, begin_day) == (2, 29)
    for year in count(_FIRST_CANDIDATE_YEAR):  # pragma: no branch - a match comes within 28 years
        if calendar.isleap(year) == leap and date(year, begin_month, begin_day).weekday() == weekday:
            return year
    raise AssertionError  # pragma: no cover


@dataclass(frozen=True)
class RunPeriodCalendar:
    """The calendar of the source run period: a whole calendar year and its special days.

    Attributes:
        year: The calendar year (research R5: the year whose begin date falls on the
            `RunPeriod` start weekday, or the `RunPeriod` begin year when given).
        holidays: Dates marked `Holiday` by `RunPeriodControl:SpecialDays`.
        custom_day_1: Dates marked `CustomDay1`.
        custom_day_2: Dates marked `CustomDay2`.
    """

    year: int
    holidays: frozenset[date] = field(default_factory=frozenset[date])
    custom_day_1: frozenset[date] = field(default_factory=frozenset[date])
    custom_day_2: frozenset[date] = field(default_factory=frozenset[date])

    @classmethod
    def from_document(cls, doc: IDFDocumentSince22_1) -> RunPeriodCalendar:
        """Build the calendar of a model's first `RunPeriod` and its `RunPeriodControl:SpecialDays`.

        Without a `RunPeriod` the calendar starts on a Sunday, EnergyPlus's default start
        weekday.

        Args:
            doc: The model.

        Returns:
            The calendar.
        """
        begin_month, begin_day, begin_year, weekday = 1, 1, None, None
        for run_period in doc.run_periods:
            begin_month = int(run_period.begin_month)  # a float in 22.1 files, as UP-6
            begin_day = int(run_period.begin_day_of_month)
            begin_year = run_period.begin_year
            weekday = run_period.day_of_week_for_start_day
            break
        if begin_year:
            year = int(begin_year)
        else:
            year = calendar_year(begin_month, begin_day, WEEKDAYS.index(weekday or "Sunday"))
        return cls(
            year=year,
            holidays=frozenset(get_holidays(doc, year)),
            custom_day_1=frozenset(get_special_days_by_type(doc, year, "CustomDay1")),
            custom_day_2=frozenset(get_special_days_by_type(doc, year, "CustomDay2")),
        )

    @property
    def start_weekday(self) -> int:
        """The weekday of 1 January, 0 for Monday to 6 for Sunday."""
        return date(self.year, 1, 1).weekday()

    @property
    def days(self) -> int:
        """Number of days in the calendar: 365, or 366 in a leap year."""
        return 366 if calendar.isleap(self.year) else 365

    @property
    def hours(self) -> int:
        """Number of hours in the calendar: 8760, or 8784 in a leap year."""
        return 24 * self.days

    @cached_property
    def day_months(self) -> npt.NDArray[np.intp]:
        """The month of each day of the calendar, 0 for January to 11 for December."""
        months = [month for month in range(12) for _ in range(calendar.monthrange(self.year, month + 1)[1])]
        return np.asarray(months, dtype=np.intp)

    @cached_property
    def day_weekdays(self) -> npt.NDArray[np.intp]:
        """The weekday of each day of the calendar, 0 for Monday to 6 for Sunday."""
        return np.asarray([(self.start_weekday + day) % 7 for day in range(self.days)], dtype=np.intp)

    @cached_property
    def day_schedule_weekdays(self) -> npt.NDArray[np.intp]:
        """The weekday whose SBEM day applies on each day: holidays Sunday, custom days Monday."""
        weekdays = [int(weekday) for weekday in self.day_weekdays]
        for dates, weekday in (
            (self.holidays, _SUNDAY),
            (self.custom_day_1, _MONDAY),
            (self.custom_day_2, _MONDAY),
        ):
            for day in dates:
                if day.year == self.year:
                    weekdays[day.timetuple().tm_yday - 1] = weekday
        return np.asarray(weekdays, dtype=np.intp)


def schedule_index(doc: IDFDocumentSince22_1) -> dict[str, AnySchedule]:
    """Index a model's whole-year schedules by upper-case name.

    The index holds `Schedule:Compact`, `Schedule:Year`, `Schedule:Constant` and
    `Schedule:File` objects: the types a load, setpoint or availability references. EnergyPlus
    names are case-insensitive, hence the upper-case keys.

    Args:
        doc: The model.

    Returns:
        The schedules by upper-case name.

    Raises:
        ValueError: If two schedules share a name.
    """
    index: dict[str, AnySchedule] = {}
    collections: tuple[Any, ...] = (
        doc.schedule_compacts,
        doc.schedule_years,
        doc.schedule_constants,
        doc.schedule_files,
    )
    for collection in collections:
        for obj in cast("list[AnySchedule]", list(collection)):
            key = obj.name.upper()
            if key in index:
                msg = f"two schedules are named {obj.name!r}: {index[key].obj_type} and {obj.obj_type}"
                raise ValueError(msg)
            index[key] = obj
    return index


class ScheduleEvaluator:
    """Evaluate a model's schedules by name, hourly on the run-period calendar, each once.

    Calling the evaluator with a schedule name returns its read-only hourly `Profile`. Results
    are memoised by upper-case name, so a schedule referenced by many objects is evaluated
    once (research R5).
    """

    def __init__(self, doc: IDFDocumentSince22_1, calendar: RunPeriodCalendar, *, base_path: Path | str | None = None):
        """Prepare to evaluate the schedules of `doc`.

        Args:
            doc: The model, which also resolves week and day schedules and special days.
            calendar: The run-period calendar; its year must be the one `doc`'s special days
                were read for.
            base_path: Directory against which relative `Schedule:File` paths are resolved.
        """
        self.doc = doc
        self.calendar = calendar
        self.base_path = base_path
        self.index = schedule_index(doc)
        self._profiles: dict[str, Profile] = {}

    def __call__(self, name: str) -> Profile:
        """Return the hourly profile of the schedule called `name` (case-insensitive).

        Raises:
            KeyError: If the model has no whole-year schedule of that name.
        """
        key = name.upper()
        cached = self._profiles.get(key)
        if cached is not None:
            return cached
        try:
            obj = self.index[key]
        except KeyError:
            msg = f"the model has no Schedule:Compact, Schedule:Year, Schedule:Constant or Schedule:File named {name!r}"
            raise KeyError(msg) from None
        if obj.obj_type == "Schedule:Year":
            obj = normalise_schedule_year(cast("ScheduleYear | ScheduleYear_v9_0_to_v22_1", obj))
        evaluate = cast("Callable[..., list[float]]", values)
        hourly = evaluate(obj, year=self.calendar.year, document=self.doc, base_path=self.base_path)
        profile = np.asarray(hourly, dtype=np.float64)
        profile.flags.writeable = False
        self._profiles[key] = profile
        return profile


def project(
    profile: npt.NDArray[np.floating[Any]] | Sequence[float], calendar: RunPeriodCalendar
) -> RepresentativeDays:
    """Project an hourly profile onto SBEM's representative days (research R5).

    Each representative day is the mean, hour by hour, over a month's days of one weekday,
    holidays included. The projection is linear, and each month's energy is conserved exactly:
    expanding the result back onto `calendar` (`expand`) gives the same monthly sums.

    Args:
        profile: One value per hour of `calendar`.
        calendar: The calendar the profile was evaluated on.

    Returns:
        An array of shape (12, 7, 24): month, weekday (Monday first), hour.

    Raises:
        ValueError: If the profile does not have one value per hour of the calendar.
    """
    hourly = np.asarray(profile, dtype=np.float64)
    if hourly.shape != (calendar.hours,):
        msg = f"the profile has shape {hourly.shape}; the {calendar.year} calendar needs ({calendar.hours},)"
        raise ValueError(msg)
    slots = calendar.day_months * 7 + calendar.day_weekdays
    sums = np.zeros((12 * 7, 24), dtype=np.float64)
    np.add.at(sums, slots, hourly.reshape(-1, 24))  # pyright: ignore[reportUnknownMemberType]
    counts = np.bincount(slots, minlength=12 * 7).astype(np.float64)
    return (sums / counts[:, None]).reshape(12, 7, 24)  # pyright: ignore[reportUnknownMemberType]


def expand(days: RepresentativeDays, calendar: RunPeriodCalendar) -> Profile:
    """Lay representative days out on a calendar, each day taking its month and weekday's day.

    Args:
        days: An array of shape (12, 7, 24), as `project` returns.
        calendar: The calendar.

    Returns:
        The hourly profile.
    """
    return np.asarray(days, dtype=np.float64)[calendar.day_months, calendar.day_weekdays].ravel()


def representative_days(year: YearComponent) -> RepresentativeDays:
    """Return the representative days an epinterface `YearComponent` holds.

    Args:
        year: The schedule.

    Returns:
        An array of shape (12, 7, 24): month, weekday (Monday first), hour.
    """
    return np.array([[day.Values for day in week.Days] for week in year.Weeks], dtype=np.float64)


def year_values(year: YearComponent, calendar: RunPeriodCalendar) -> Profile:
    """Return the hourly values of a `YearComponent` on a calendar, as EnergyPlus would run it.

    Each day takes its month's day for its weekday; a holiday takes Sunday's, a custom day
    Monday's, as epinterface writes the schedule for EnergyPlus.

    Args:
        year: The schedule.
        calendar: The calendar.

    Returns:
        The hourly profile.
    """
    days = representative_days(year)
    return days[calendar.day_months, calendar.day_schedule_weekdays].ravel()


def _default_limits(category: YearScheduleCategory) -> ScheduleTypeLimitType:
    return "Temperature" if category == "Setpoint" else "Fraction"


def to_year_component(
    days: RepresentativeDays,
    *,
    name: str,
    category: YearScheduleCategory,
    limits: ScheduleTypeLimitType | None = None,
) -> YearComponent:
    """Turn representative days into an epinterface `YearComponent`.

    Equal days share one `DayComponent` and equal weeks one `WeekComponent`, named after the
    schedule (`"<name> day 1"`, `"<name> week 1"`, numbered in order of first use from January's
    Monday), so that names stay unique across the schedules of an archetype.

    Args:
        days: An array of shape (12, 7, 24), as `project` returns.
        name: The schedule's name.
        category: What the schedule drives (epinterface's `YearComponent.Type`).
        limits: The schedule type limits of its days. Defaults to `"Temperature"` for a
            setpoint and `"Fraction"` otherwise.

    Returns:
        The schedule.

    Raises:
        ValueError: If `days` has the wrong shape, or a `"Fraction"` value lies outside [0, 1]
            by more than float round-off.
    """
    array = np.asarray(days, dtype=np.float64)
    if array.shape != (12, 7, 24):
        msg = f"{name}: representative days have shape {array.shape}, not (12, 7, 24)"
        raise ValueError(msg)
    kind = _default_limits(category) if limits is None else limits
    if kind == "Fraction":
        if (array < -_FRACTION_TOLERANCE).any() or (array > 1.0 + _FRACTION_TOLERANCE).any():
            msg = f"{name}: a Fraction schedule has values in [{array.min()!r}, {array.max()!r}], outside [0, 1]"
            raise ValueError(msg)
        array = np.minimum(np.maximum(array, 0.0), 1.0)

    day_components: dict[tuple[float, ...], DayComponent] = {}
    week_components: dict[tuple[tuple[float, ...], ...], WeekComponent] = {}
    weeks: list[WeekComponent] = []
    for month in range(12):
        keys: list[tuple[float, ...]] = []
        for weekday in range(7):
            key = tuple(float(v) for v in array[month, weekday])
            if key not in day_components:
                hours = {f"Hour_{hour:02d}": value for hour, value in enumerate(key)}
                day_components[key] = DayComponent.model_validate({
                    "Name": f"{name} day {len(day_components) + 1}",
                    "Type": kind,
                    **hours,
                })
            keys.append(key)
        week_key = tuple(keys)
        if week_key not in week_components:
            week_components[week_key] = WeekComponent.model_validate({
                "Name": f"{name} week {len(week_components) + 1}",
                **{WEEKDAYS[i]: day_components[k] for i, k in enumerate(keys)},
            })
        weeks.append(week_components[week_key])
    return YearComponent.model_validate({
        "Name": name,
        "Type": category,
        **dict(zip(MONTHS, weeks, strict=True)),
    })


def _number(value: float) -> str:
    if not np.isfinite(value):
        msg = f"a schedule value is {value!r}; Schedule:Compact needs finite numbers"
        raise ValueError(msg)
    return repr(float(value))


def _until_fields(hours: npt.NDArray[np.float64]) -> list[str]:
    fields: list[str] = []
    for hour in range(24):
        if hour == _LAST_HOUR or hours[hour + 1] != hours[hour]:
            fields.extend((f"Until: {hour + 1:02d}:00", _number(float(hours[hour]))))
    return fields


def schedule_compact(schedule: YearComponent, *, name: str | None = None) -> str:
    """Return a `YearComponent` as an EnergyPlus `Schedule:Compact` object, in IDF text (FR-023).

    The text has one `Through: <month end>` per run of equal months and `For:` blocks Monday
    to Sunday. As in epinterface's own EnergyPlus writer, holidays follow Sunday and design and
    custom days follow Monday. Values are written as shortest round-trip floats, so idfkit
    evaluates the text to exactly the hourly values of the schedule (`year_values`) on any
    calendar.

    Args:
        schedule: Any SBEM schedule, from a reduction or not.
        name: Name of the `Schedule:Compact`; defaults to the schedule's `Name`.

    Returns:
        The IDF text, ending with a newline.

    Raises:
        ValueError: If the name is empty or holds a character IDF syntax reserves (`,`, `;`,
            `!` or a line break), or a value is not finite.
    """
    object_name = schedule.Name if name is None else name
    if not object_name.strip() or _FORBIDDEN_NAME_CHARACTERS.intersection(object_name):
        msg = f"Schedule:Compact name {object_name!r} is empty or holds ',', ';', '!' or a line break"
        raise ValueError(msg)
    days = representative_days(schedule)
    fields: list[str] = []
    for month in range(12):
        if month < _DECEMBER and bool((days[month] == days[month + 1]).all()):
            continue
        fields.append(f"Through: {month + 1:02d}/{_MONTH_ENDS[month]:02d}")
        for weekday in range(7):
            fields.append(f"For: {_FOR_LABELS[weekday]}")
            fields.extend(_until_fields(days[month, weekday]))
    lines = [
        "Schedule:Compact,",
        f"  {object_name},  !- Name",
        f"  {schedule.schedule_type_limits},  !- Schedule Type Limits Name",
    ]
    last = len(fields)
    lines.extend(f"  {text}{';' if i == last else ','}  !- Field {i}" for i, text in enumerate(fields, start=1))
    return "\n".join(lines) + "\n"
