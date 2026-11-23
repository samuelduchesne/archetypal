"""The schedule rules (spec 003, T016, research R7)."""

from __future__ import annotations

import calendar
from datetime import date, timedelta
from typing import TypedDict

import numpy as np
import pytest
from epinterface.sbem.components.schedules import DayComponent, WeekComponent, YearComponent
from hypothesis import given
from hypothesis import strategies as st

from archetypal.reduction.schedules import MONTHS, expand, representative_days, to_year_component
from archetypal.umi._format import DaySchedule, WeekSchedule, YearSchedule, YearSchedulePart
from archetypal.umi.correspondence import get_rule
from archetypal.umi.report import Findings, LossKind, NoteKind
from archetypal.umi.rules import schedules
from archetypal.umi.rules.schedules import (
    REFERENCE_CALENDAR,
    day_to_sbem,
    day_to_umi,
    type_to_sbem,
    type_to_umi,
    week_to_sbem,
    week_to_umi,
    year_to_sbem,
    year_to_umi,
)


def day(name: str, values: list[float], kind: str = "Fraction") -> DaySchedule:
    return DaySchedule.model_validate({"Name": name, "Type": kind, "Values": values})


def week(name: str, days: list[DaySchedule], kind: str | None = "Fraction") -> WeekSchedule:
    return WeekSchedule.model_validate({"Name": name, "Days": days, "Type": kind})


def part(fm: int, fd: int, tm: int, td: int, schedule: WeekSchedule) -> YearSchedulePart:
    return YearSchedulePart.model_validate({
        "FromMonth": fm,
        "FromDay": fd,
        "ToMonth": tm,
        "ToDay": td,
        "Schedule": schedule,
    })


def year(name: str, *parts: YearSchedulePart, kind: str = "Fraction") -> YearSchedule:
    return YearSchedule.model_validate({"Name": name, "Parts": parts, "Type": kind})


ON = day("On", [1.0] * 24)
OFF = day("Off", [0.0] * 24)
WORK = day("Work", [0.0] * 8 + [1.0] * 10 + [0.5] * 6)
# Days distinct by weekday, so that the Monday-first order is visible.
NUMBERED = [day(f"D{i}", [i / 10] * 24) for i in range(7)]
OFFICE_WEEK = week("Office week", [WORK] * 5 + [OFF, OFF])
ALL_ON = week("All on", [ON] * 7)
NUMBERED_WEEK = week("Numbered", NUMBERED)
ALIGNED = year("Aligned", part(1, 1, 3, 31, OFFICE_WEEK), part(4, 1, 9, 30, ALL_ON), part(10, 1, 12, 31, OFFICE_WEEK))
MISALIGNED = year(
    "Misaligned", part(1, 1, 3, 15, OFFICE_WEEK), part(3, 16, 10, 15, ALL_ON), part(10, 16, 12, 31, OFFICE_WEEK)
)


class Context(TypedDict):
    subject: str
    location: str
    findings: Findings


def kw(findings: Findings | None = None) -> Context:
    return {"subject": "T", "location": "/YearSchedules/0", "findings": findings or Findings()}


# --- Calendar -------------------------------------------------------------------------------


def test_reference_year_is_non_leap_and_starts_on_monday() -> None:
    assert not calendar.isleap(REFERENCE_CALENDAR.year)
    assert date(REFERENCE_CALENDAR.year, 1, 1).weekday() == 0
    assert not REFERENCE_CALENDAR.holidays


# --- schedule.type ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("umi", "sbem"),
    [("Fraction", "Fraction"), ("Temperature", "Temperature"), ("AnyNumber", "AnyNumber"), ("fraction", "Fraction")],
)
def test_types_map_by_name(umi: str, sbem: str) -> None:
    findings = Findings()
    assert type_to_sbem(umi, subject="T", location="/d", findings=findings) == sbem
    assert not findings.notes
    assert type_to_umi(sbem) == sbem  # type: ignore[arg-type]


@pytest.mark.parametrize("umi", ["On/Off", "ON/OFF", "OnOff"])
def test_on_off_becomes_fraction_with_a_note(umi: str) -> None:
    findings = Findings()
    assert type_to_sbem(umi, subject="T", location="/d", findings=findings) == "Fraction"
    (note,) = findings.notes
    assert (note.kind, note.location, note.value, note.rule) == (NoteKind.ASSUMED, "/d/Type", umi, "schedule.type")


@pytest.mark.parametrize("umi", ["Humidity", ""])
def test_other_types_become_anynumber_with_a_note(umi: str) -> None:
    findings = Findings()
    assert type_to_sbem(umi, subject="T", location="/d", findings=findings) == "AnyNumber"
    (note,) = findings.notes
    assert (note.kind, note.location, note.value, note.rule) == (NoteKind.ASSUMED, "/d/Type", umi, "schedule.type")


# --- schedule.day and schedule.week -----------------------------------------------------------


def test_day_copies_the_24_values() -> None:
    sbem = day_to_sbem(WORK, **kw())
    assert isinstance(sbem, DayComponent)
    assert sbem.Name == "Work"
    assert sbem.Type == "Fraction"
    assert sbem.Values == list(WORK.values)
    assert day_to_umi(sbem) == WORK


def test_day_with_wrong_length_is_refused() -> None:
    with pytest.raises(ValueError, match="24"):
        day_to_sbem(day("Short", [1.0] * 23), **kw())


def test_week_days_are_monday_first() -> None:
    sbem = week_to_sbem(NUMBERED_WEEK, **kw())
    assert isinstance(sbem, WeekComponent)
    assert sbem.Name == "Numbered"
    assert [d.Name for d in sbem.Days] == [f"D{i}" for i in range(7)]
    assert sbem.Monday.Name == "D0"
    assert sbem.Sunday.Name == "D6"
    findings = Findings()
    assert week_to_umi(sbem, subject="A", location="w", findings=findings) == NUMBERED_WEEK
    assert not findings.losses


def test_reading_leaves_the_holiday_and_design_day_slots_unset() -> None:
    sbem = week_to_sbem(NUMBERED_WEEK, **kw())
    assert (sbem.Holiday, sbem.SummerDesignDay, sbem.WinterDesignDay) == (None, None, None)


def test_special_days_are_lost_on_writing_unless_a_holiday_equals_sunday() -> None:
    """UP-2's slots: a holiday on Sunday's day loses nothing; a set design day is always lost."""
    base = week_to_sbem(NUMBERED_WEEK, **kw())
    peak = day_to_sbem(day("Peak", [1.0] * 24), **kw())
    special = WeekComponent.model_validate({
        **{name: getattr(base, name) for name in ("Name", *schedules.WEEKDAYS)},
        "Holiday": base.Sunday,
        "SummerDesignDay": peak,
        "WinterDesignDay": base.Monday,
    })
    findings = Findings()
    umi = week_to_umi(special, subject="A", location="perimeter.w", findings=findings)
    assert umi == NUMBERED_WEEK
    summer, winter = findings.losses
    assert (summer.kind, summer.location, summer.value, summer.replacement, summer.rule) == (
        LossKind.LOST,
        "perimeter.w.SummerDesignDay",
        "Peak",
        "D0",
        "schedule.week",
    )
    # Equal to Monday's day, but read back unset: epinterface would size gains with its own day.
    assert (winter.location, winter.value, winter.replacement) == ("perimeter.w.WinterDesignDay", "D0", "D0")


# --- schedule.months: UMI to SBEM -------------------------------------------------------------


def test_month_in_one_part_is_copied_exactly() -> None:
    findings = Findings()
    sbem = year_to_sbem(ALIGNED, "Occupancy", **kw(findings))
    assert isinstance(sbem, YearComponent)
    assert sbem.Name == "Aligned"
    assert sbem.Type == "Occupancy"
    assert [w.Name for w in sbem.Weeks] == ["Office week"] * 3 + ["All on"] * 6 + ["Office week"] * 3
    assert sbem.January.Monday.Name == "Work"
    assert sbem.January.Saturday.Name == "Off"
    assert not findings.losses


def hourly(schedule: YearSchedule) -> np.ndarray:
    """Evaluate a UMI year on the reference calendar, by hand: each date takes its part's week."""
    start = date(REFERENCE_CALENDAR.year, 1, 1)
    values: list[float] = []
    for offset in range(365):
        today = start + timedelta(days=offset)
        (covering,) = (
            p
            for p in schedule.parts
            if (p.from_month, p.from_day) <= (today.month, today.day) <= (p.to_month, p.to_day)
        )
        assert covering.schedule is not None
        weekday = covering.schedule.days[today.weekday()]
        assert weekday is not None
        values.extend(weekday.values)
    return np.asarray(values)


def monthly_sums(profile: np.ndarray) -> np.ndarray:
    hours = np.repeat(REFERENCE_CALENDAR.day_months, 24)  # pyright: ignore[reportUnknownMemberType]
    return np.bincount(hours, weights=profile, minlength=12)


def test_split_month_is_projected_conserving_its_sum() -> None:
    findings = Findings()
    sbem = year_to_sbem(MISALIGNED, "Lighting", **kw(findings))
    got = monthly_sums(expand(representative_days(sbem), REFERENCE_CALENDAR))
    want = monthly_sums(hourly(MISALIGNED))
    np.testing.assert_allclose(got, want, rtol=1e-12)
    # Unsplit months are copied, not projected.
    assert sbem.February.Name == "Office week"
    assert sbem.April.Name == "All on"
    assert sbem.November.Name == "Office week"
    assert sbem.March.Name not in {"Office week", "All on"}
    assert sbem.March.Type == "Fraction"


def test_a_month_split_between_parts_of_one_week_is_copied_exactly() -> None:
    findings = Findings()
    split = year("Split", part(1, 1, 1, 15, OFFICE_WEEK), part(1, 16, 12, 31, OFFICE_WEEK))
    sbem = year_to_sbem(split, "Occupancy", **kw(findings))
    assert sbem.January.Name == "Office week"
    assert not findings.losses


def test_split_month_is_listed_as_approximate() -> None:
    findings = Findings()
    year_to_sbem(MISALIGNED, "Lighting", **kw(findings))
    assert [loss.kind for loss in findings.losses] == [LossKind.APPROXIMATE] * 2
    assert {loss.rule for loss in findings.losses} == {"schedule.months"}
    values = [loss.value for loss in findings.losses]
    months = sorted(v["month"] for v in values if isinstance(v, dict))  # type: ignore[index]
    assert months == ["March", "October"]
    march = next(v for v in values if isinstance(v, dict) and v["month"] == "March")
    assert march["parts"] == [
        {"week": "Office week", "from": "03-01", "to": "03-15"},
        {"week": "All on", "from": "03-16", "to": "03-31"},
    ]


def test_uncovered_days_are_refused() -> None:
    gap = year("Gap", part(1, 1, 6, 30, ALL_ON), part(7, 2, 12, 31, ALL_ON))
    with pytest.raises(ValueError, match="07-01"):
        year_to_sbem(gap, "Occupancy", **kw())


def test_one_schedule_in_several_roles_gives_one_year_per_role() -> None:
    years = [year_to_sbem(ALIGNED, role, **kw()) for role in ("Occupancy", "Lighting", "Equipment")]
    assert {y.Name for y in years} == {"Aligned"}
    assert [y.Type for y in years] == ["Occupancy", "Lighting", "Equipment"]
    assert years[0].model_dump(exclude={"Type"}) == years[1].model_dump(exclude={"Type"})


def test_type_of_days_is_mapped_with_a_note() -> None:
    odd = day("Odd", [2.0] * 24, kind="On/Off")
    findings = Findings()
    sbem = year_to_sbem(
        year("Y", part(1, 1, 12, 31, week("W", [odd] * 7, kind="On/Off")), kind="On/Off"), "Equipment", **kw(findings)
    )
    assert sbem.schedule_type_limits == "AnyNumber"
    assert {n.rule for n in findings.notes} == {"schedule.type"}


# --- schedule.months: SBEM to UMI -------------------------------------------------------------


def representative(weeks_by_month: list[int]) -> np.ndarray:
    """(12, 7, 24) days where month m uses one of a few distinct weeks."""
    ramp = [[(7 * 24 - 1 - (24 * d + h)) / (7 * 24 - 1) for h in range(24)] for d in range(7)]
    patterns = [[[0.25] * 24] * 7, [[0.75] * 24] * 7, ramp]
    return np.asarray([patterns[w] for w in weeks_by_month], dtype=np.float64)


def test_writing_merges_equal_consecutive_months() -> None:
    sbem = to_year_component(representative([0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0]), name="Y", category="Occupancy")
    findings = Findings()
    umi = year_to_umi(sbem, subject="A", location="perimeter.Y", findings=findings)
    assert umi.name == "Y"
    assert umi.type == "Fraction"
    assert [(p.from_month, p.from_day, p.to_month, p.to_day) for p in umi.parts] == [
        (1, 1, 3, 31),
        (4, 1, 9, 30),
        (10, 1, 12, 31),
    ]
    assert umi.parts[0].schedule == umi.parts[2].schedule
    assert not findings.losses


def test_each_months_design_days_are_lost_where_that_month_is() -> None:
    days = representative([0, 0, 0, 1, 1, 1, 1, 1, 1, 0, 0, 0])
    sbem = to_year_component(
        days, name="Y", category="Occupancy", summer_design_day=np.ones(24), winter_design_day=np.zeros(24)
    )
    findings = Findings()
    umi = year_to_umi(sbem, subject="A", location="perimeter.Y", findings=findings)
    assert len(umi.parts) == 3  # equal months still make one part
    locations = [loss.location for loss in findings.losses]
    assert locations == [
        f"perimeter.Y.{month}.{slot}" for month in MONTHS for slot in ("SummerDesignDay", "WinterDesignDay")
    ]


def test_february_parts_end_on_the_29th() -> None:
    sbem = to_year_component(representative([2, 2] + [1] * 10), name="Y", category="Occupancy")
    umi = year_to_umi(sbem, subject="A", location="Y", findings=Findings())
    assert [(p.from_month, p.from_day, p.to_month, p.to_day) for p in umi.parts] == [(1, 1, 2, 29), (3, 1, 12, 31)]


def test_aligned_round_trip_is_exact() -> None:
    sbem = year_to_sbem(ALIGNED, "Occupancy", **kw())
    findings = Findings()
    assert year_to_umi(sbem, subject="A", location="Y", findings=findings) == ALIGNED
    assert not findings.losses


@pytest.mark.parametrize(
    ("rule_id", "to_sbem", "to_umi"),
    [
        ("schedule.type", type_to_sbem, type_to_umi),
        ("schedule.day", day_to_sbem, day_to_umi),
        ("schedule.week", week_to_sbem, week_to_umi),
        ("schedule.months", year_to_sbem, year_to_umi),
    ],
)
def test_rules_are_registered(rule_id: str, to_sbem: object, to_umi: object) -> None:
    rule = get_rule(rule_id)
    assert (rule.to_sbem, rule.to_umi) == (to_sbem, to_umi)


def test_metadata_rule_is_registered() -> None:
    rule = get_rule("schedule.metadata")
    assert (rule.to_sbem, rule.to_umi) == (schedules.metadata_to_sbem, schedules.metadata_to_umi)


def test_schedule_metadata_maps_both_ways() -> None:
    """UP-9: comments and data source map; Basilisk's fixed category reads as unset."""
    day = DaySchedule.model_validate({"Name": "d", "Values": [0.5] * 24, "Comments": "c", "DataSource": "s"})
    findings = Findings()
    component = day_to_sbem(day, "T", "/DaySchedules/0", findings)
    assert (component.Category, component.Comment, component.DataSource) == (None, "c", "s")
    back = day_to_umi(component)
    assert (back.category, back.comments, back.data_source) == ("Day", "c", "s")
    labelled = component.model_copy(update={"Category": "Office"})
    schedules.metadata_to_umi(labelled, "A", "y", findings)
    [loss] = findings.losses
    assert (loss.location, loss.value, loss.rule, loss.upstream) == ("y.Category", "Office", "schedule.metadata", None)


@given(st.lists(st.integers(min_value=0, max_value=2), min_size=12, max_size=12))
def test_writing_then_reading_is_the_identity(weeks_by_month: list[int]) -> None:
    sbem = to_year_component(representative(weeks_by_month), name="Y", category="Occupancy")
    findings = Findings()
    umi = year_to_umi(sbem, subject="A", location="Y", findings=findings)
    back = year_to_sbem(umi, "Occupancy", **kw(findings))
    np.testing.assert_array_equal(representative_days(back), representative_days(sbem))
    assert not findings.losses
