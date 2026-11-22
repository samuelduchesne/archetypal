"""Temporary bridges over idfkit gaps, each removed when its upstream item is released.

Removal conditions:

- `normalise_schedule_year` (**UP-6**): remove it, and its call in `schedules.py`, once the
  installed idfkit evaluates a `Schedule:Year` read from an EnergyPlus 9.0-22.1 file. The test
  `tests/unit/test_bridges.py::test_remove_bridge_once_idfkit_fixes_up6` fails on that day.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from idfkit.document import ScheduleYear, ScheduleYearScheduleWeeksItem
    from idfkit.versioned import ScheduleYear_v9_0_to_v22_1

__all__ = ["normalise_schedule_year"]


def _whole(year_name: str, index: int, field: str, value: float) -> int:
    as_int = int(value)
    if as_int != value:
        msg = f"{year_name}: schedule_weeks[{index}].{field} is {value!r}, not a whole number"
        raise ValueError(msg)
    return as_int


def normalise_schedule_year(obj: ScheduleYear | ScheduleYear_v9_0_to_v22_1) -> ScheduleYear:
    """Return a copy of a `Schedule:Year` whose start and end month and day fields are `int`.

    EnergyPlus schemas 9.0 to 22.1 declare these four fields as numbers, so idfkit reads them
    from such a file as `float` (`1.0`), and `idfkit.schedules` then fails on `int('1.0')`.
    The copy is detached from the document (pass the document to `idfkit.schedules.values`
    so it can resolve the week schedules); the original object is not modified.

    Removal condition: idfkit releases UP-6 (`Schedule:Year` from a pre-22.2 file evaluates,
    and its date fields read as `int`). Delete this function then.

    Args:
        obj: A `Schedule:Year` of any release from 22.1.

    Returns:
        The normalised copy, typed as the latest release's `Schedule:Year`.

    Raises:
        ValueError: If a month or day is not a whole number, naming the schedule and field.
    """
    weeks: list[ScheduleYearScheduleWeeksItem] = []
    for index, group in enumerate(obj.schedule_weeks):
        item = group.as_dict()
        weeks.append({
            "schedule_week_name": item["schedule_week_name"],
            "start_month": _whole(obj.name, index, "start_month", item["start_month"]),
            "start_day": _whole(obj.name, index, "start_day", item["start_day"]),
            "end_month": _whole(obj.name, index, "end_month", item["end_month"]),
            "end_day": _whole(obj.name, index, "end_day", item["end_day"]),
        })
    copy = cast("ScheduleYear", obj.copy())
    copy.update(schedule_weeks=weeks)
    return copy
