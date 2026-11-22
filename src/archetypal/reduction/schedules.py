"""Schedules: evaluation on the run-period calendar, representative days and output forms.

Research R5 (spec 002) fixes the method:

- each distinct schedule of a model is evaluated once, hourly, with `idfkit.schedules.values`,
  on the calendar of the source run period (`RunPeriodCalendar`);
- an hourly `Profile` is projected onto SBEM's representative days, one per month and weekday,
  each the mean over that month's days of that weekday, holidays included (`project`). The
  projection is linear and conserves the energy of every month of the source calendar;
- representative days become epinterface `YearComponent`s (`to_year_component`), and any
  `YearComponent` becomes `Schedule:Compact` text (`schedule_compact`, FR-023).

Special days in SBEM follow epinterface's own EnergyPlus writer: a holiday takes the week's
`Holiday` day when it has one (UP-2's slot), else Sunday's; custom days take Monday's; design
days take the week's `SummerDesignDay` / `WinterDesignDay` when set, else Monday's.
`year_values` and `schedule_compact` both use that rule, so the `Schedule:Compact` text
evaluates to the same hourly values as the `YearComponent` on any calendar.

Holidays (UP-2, T087). `project_holidays` projects a profile with the holidays of each month
kept apart: each weekday's day is the mean over that month's non-holiday days of that weekday,
and the month's holiday day the mean over its holidays. Each month's energy is still conserved
exactly (`expand(..., holidays=...)`). `to_year_component(..., holidays=...)` writes the holiday
days into the weeks' `Holiday` slots, and design days into `SummerDesignDay` and
`WinterDesignDay` when given.
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
    "HolidayDays",
    "Profile",
    "RepresentativeDays",
    "RunPeriodCalendar",
    "ScheduleEvaluator",
    "calendar_year",
    "expand",
    "holiday_days",
    "project",
    "project_holidays",
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

HolidayDays: TypeAlias = "dict[int, npt.NDArray[np.float64]]"
"""The holiday day of each month that has holidays: month index (0 for January) → 24 values."""

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
# For: labels, Monday to Sunday. Special days follow epinterface's `WeekComponent.add_week_to_idf`:
# a slot the week does not set falls back to Sunday (holidays) or Monday (design days).
_FOR_LABELS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
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


def _holiday_mask(calendar: RunPeriodCalendar) -> npt.NDArray[np.bool_]:
    mask = np.zeros(calendar.days, dtype=bool)
    for day in calendar.holidays:
        if day.year == calendar.year:
            mask[day.timetuple().tm_yday - 1] = True
    return mask


def project_holidays(
    profile: npt.NDArray[np.floating[Any]] | Sequence[float], calendar: RunPeriodCalendar
) -> tuple[RepresentativeDays, HolidayDays]:
    """Project an hourly profile onto representative days with each month's holidays apart (UP-2).

    Each weekday's day is the mean, hour by hour, over the month's days of that weekday that are
    not holidays; each month with holidays gets a holiday day, the mean over its holidays. A
    weekday whose every occurrence in a month is a holiday keeps the mean over all of them. The
    projection is linear and each month's energy is conserved exactly:
    `expand(days, calendar, holidays=holidays)` gives the same monthly sums.

    Args:
        profile: One value per hour of `calendar`.
        calendar: The calendar the profile was evaluated on; its `holidays` are kept apart.

    Returns:
        The representative days, shape (12, 7, 24), and the holiday day of each month that has
        holidays.

    Raises:
        ValueError: If the profile does not have one value per hour of the calendar.
    """
    hourly = np.asarray(profile, dtype=np.float64)
    if hourly.shape != (calendar.hours,):
        msg = f"the profile has shape {hourly.shape}; the {calendar.year} calendar needs ({calendar.hours},)"
        raise ValueError(msg)
    by_day = hourly.reshape(-1, 24)
    holiday = _holiday_mask(calendar)
    slots = calendar.day_months * 7 + calendar.day_weekdays
    ordinary = ~holiday
    sums = np.zeros((12 * 7, 24), dtype=np.float64)
    np.add.at(sums, slots[ordinary], by_day[ordinary])  # pyright: ignore[reportUnknownMemberType]
    counts = np.bincount(slots[ordinary], minlength=12 * 7).astype(np.float64)
    days = np.zeros((12 * 7, 24), dtype=np.float64)
    present = counts > 0
    days[present] = sums[present] / counts[present, None]
    if not present.all():  # a weekday that is a holiday every time it occurs in a month
        inclusive = project(hourly, calendar).reshape(12 * 7, 24)
        days[~present] = inclusive[~present]
    holidays: HolidayDays = {}
    for month in sorted({int(m) for m in calendar.day_months[holiday]}):
        chosen = holiday & (calendar.day_months == month)
        holidays[month] = by_day[chosen].mean(axis=0)
    return days.reshape(12, 7, 24), holidays


def expand(
    days: RepresentativeDays, calendar: RunPeriodCalendar, *, holidays: HolidayDays | None = None
) -> Profile:
    """Lay representative days out on a calendar, each day taking its month and weekday's day.

    Args:
        days: An array of shape (12, 7, 24), as `project` returns.
        calendar: The calendar.
        holidays: Holiday days by month (`project_holidays`); a holiday of a month listed here
            takes that day instead of its weekday's.

    Returns:
        The hourly profile.
    """
    by_day = np.array(np.asarray(days, dtype=np.float64)[calendar.day_months, calendar.day_weekdays])
    if holidays:
        _apply_holidays(by_day, calendar, holidays)
    return by_day.ravel()


def _apply_holidays(by_day: npt.NDArray[np.float64], calendar: RunPeriodCalendar, holidays: HolidayDays) -> None:
    for index in np.flatnonzero(_holiday_mask(calendar)):
        month = int(calendar.day_months[index])
        if month in holidays:
            by_day[index] = holidays[month]


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

    Each day takes its month's day for its weekday; a holiday takes the week's `Holiday` day,
    else Sunday's, and a custom day Monday's, as epinterface writes the schedule for EnergyPlus.

    Args:
        year: The schedule.
        calendar: The calendar.

    Returns:
        The hourly profile.
    """
    days = representative_days(year)
    by_day = np.array(days[calendar.day_months, calendar.day_schedule_weekdays])
    holidays = holiday_days(year)
    if holidays:
        _apply_holidays(by_day, calendar, holidays)
    return by_day.ravel()


def holiday_days(year: YearComponent) -> HolidayDays:
    """Return the holiday days a `YearComponent` sets, by month (weeks without a `Holiday` slot are left out).

    Args:
        year: The schedule.

    Returns:
        Month index (0 for January) → the 24 values of that month's week's `Holiday` day.
    """
    return {
        month: np.asarray(week.Holiday.Values, dtype=np.float64)
        for month, week in enumerate(year.Weeks)
        if week.Holiday is not None
    }


def _default_limits(category: YearScheduleCategory) -> ScheduleTypeLimitType:
    return "Temperature" if category == "Setpoint" else "Fraction"


def to_year_component(
    days: RepresentativeDays,
    *,
    name: str,
    category: YearScheduleCategory,
    limits: ScheduleTypeLimitType | None = None,
    holidays: HolidayDays | None = None,
    summer_design_day: npt.NDArray[np.floating[Any]] | Sequence[float] | None = None,
    winter_design_day: npt.NDArray[np.floating[Any]] | Sequence[float] | None = None,
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
        holidays: Holiday days by month (`project_holidays`); each listed month's week gets a
            `Holiday` slot, the others keep none (Sunday's day applies).
        summer_design_day: 24 values for every week's `SummerDesignDay` slot, or `None`.
        winter_design_day: 24 values for every week's `WinterDesignDay` slot, or `None`.

    Returns:
        The schedule.

    Raises:
        ValueError: If `days` has the wrong shape, or a `"Fraction"` value lies outside [0, 1]
            by more than float round-off.
    """
    array = _checked_values(np.asarray(days, dtype=np.float64), name, _default_limits(category) if limits is None else limits)
    if array.shape != (12, 7, 24):
        msg = f"{name}: representative days have shape {array.shape}, not (12, 7, 24)"
        raise ValueError(msg)
    kind = _default_limits(category) if limits is None else limits

    def special(values: object, what: str) -> tuple[float, ...] | None:
        if values is None:
            return None
        hours = np.asarray(values, dtype=np.float64)
        if hours.shape != (24,):
            msg = f"{name}: a {what} day has shape {hours.shape}, not (24,)"
            raise ValueError(msg)
        return tuple(float(v) for v in _checked_values(hours, name, kind))

    holiday_keys = {month: special(values, "holiday") for month, values in (holidays or {}).items()}
    summer = special(summer_design_day, "summer design")
    winter = special(winter_design_day, "winter design")

    day_components: dict[tuple[float, ...], DayComponent] = {}

    def day(key: tuple[float, ...]) -> DayComponent:
        if key not in day_components:
            hours = {f"Hour_{hour:02d}": value for hour, value in enumerate(key)}
            day_components[key] = DayComponent.model_validate({
                "Name": f"{name} day {len(day_components) + 1}",
                "Type": kind,
                **hours,
            })
        return day_components[key]

    week_components: dict[tuple[object, ...], WeekComponent] = {}
    weeks: list[WeekComponent] = []
    for month in range(12):
        keys = [tuple(float(v) for v in array[month, weekday]) for weekday in range(7)]
        for key in keys:
            day(key)
        slots = {"Holiday": holiday_keys.get(month), "SummerDesignDay": summer, "WinterDesignDay": winter}
        week_key = (*keys, *slots.values())
        if week_key not in week_components:
            extra = {slot: day(key) for slot, key in slots.items() if key is not None}
            week_components[week_key] = WeekComponent.model_validate({
                "Name": f"{name} week {len(week_components) + 1}",
                **{WEEKDAYS[i]: day_components[k] for i, k in enumerate(keys)},
                **extra,
            })
        weeks.append(week_components[week_key])
    return YearComponent.model_validate({
        "Name": name,
        "Type": category,
        **dict(zip(MONTHS, weeks, strict=True)),
    })


def _checked_values(array: npt.NDArray[np.float64], name: str, kind: ScheduleTypeLimitType) -> npt.NDArray[np.float64]:
    """Refuse Fraction values outside [0, 1] beyond round-off, and clip the round-off."""
    if kind != "Fraction" or array.size == 0:
        return array
    if (array < -_FRACTION_TOLERANCE).any() or (array > 1.0 + _FRACTION_TOLERANCE).any():
        msg = f"{name}: a Fraction schedule has values in [{array.min()!r}, {array.max()!r}], outside [0, 1]"
        raise ValueError(msg)
    return np.minimum(np.maximum(array, 0.0), 1.0)


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


def _special_slots(week: WeekComponent) -> dict[str, npt.NDArray[np.float64]]:
    slots: dict[str, npt.NDArray[np.float64]] = {}
    for slot in ("Holiday", "SummerDesignDay", "WinterDesignDay"):
        day: DayComponent | None = getattr(week, slot)
        if day is not None:
            slots[slot] = np.asarray(day.Values, dtype=np.float64)
    return slots


def _same_slots(a: dict[str, npt.NDArray[np.float64]], b: dict[str, npt.NDArray[np.float64]]) -> bool:
    return a.keys() == b.keys() and all(bool((a[k] == b[k]).all()) for k in a)


def schedule_compact(schedule: YearComponent, *, name: str | None = None) -> str:
    """Return a `YearComponent` as an EnergyPlus `Schedule:Compact` object, in IDF text (FR-023).

    The text has one `Through: <month end>` per run of equal months and `For:` blocks Monday
    to Sunday, then `For: Holiday`, `For: SummerDesignDay` and `For: WinterDesignDay` for the
    slots the month's week sets (UP-2). As in epinterface's own EnergyPlus writer, a holiday
    the week does not set follows Sunday, a design day it does not set follows Monday, and
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
    weeks = schedule.Weeks
    specials = [_special_slots(week) for week in weeks]
    fields: list[str] = []
    for month in range(12):
        if (
            month < _DECEMBER
            and bool((days[month] == days[month + 1]).all())
            and _same_slots(specials[month], specials[month + 1])
        ):
            continue
        fields.append(f"Through: {month + 1:02d}/{_MONTH_ENDS[month]:02d}")
        slots = specials[month]
        for weekday in range(7):
            label = _FOR_LABELS[weekday]
            if weekday == _MONDAY:
                label += "".join(f" {slot}" for slot in ("SummerDesignDay", "WinterDesignDay") if slot not in slots)
                label += " CustomDay1 CustomDay2"
            elif weekday == _SUNDAY and "Holiday" not in slots:
                label += " Holiday"
            fields.append(f"For: {label}")
            fields.extend(_until_fields(days[month, weekday]))
        for slot, values in slots.items():
            fields.append(f"For: {slot}")
            fields.extend(_until_fields(values))
    lines = [
        "Schedule:Compact,",
        f"  {object_name},  !- Name",
        f"  {schedule.schedule_type_limits},  !- Schedule Type Limits Name",
    ]
    last = len(fields)
    lines.extend(f"  {text}{';' if i == last else ','}  !- Field {i}" for i, text in enumerate(fields, start=1))
    return "\n".join(lines) + "\n"
