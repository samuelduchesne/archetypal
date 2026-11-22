"""Tests for schedule evaluation, projection and conversion (spec 002, T017; research R5, FR-023)."""

from __future__ import annotations

import calendar as pycalendar
from datetime import date, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest
from epinterface.sbem.archetype import Archetype
from epinterface.sbem.components.schedules import DayComponent, WeekComponent, YearComponent
from hypothesis import given
from hypothesis import strategies as st
from idfkit import load_idf, new_document
from idfkit.schedules import evaluate as evaluate_at
from idfkit.schedules import values
from pydantic import BaseModel

from archetypal import reduction
from archetypal.reduction import schedules as schedules_module
from archetypal.reduction.schedules import (
    MONTHS,
    WEEKDAYS,
    RunPeriodCalendar,
    ScheduleEvaluator,
    calendar_year,
    expand,
    holiday_days,
    project,
    project_holidays,
    representative_days,
    schedule_compact,
    schedule_index,
    to_year_component,
    year_values,
)

if TYPE_CHECKING:
    from collections.abc import Iterator

    from idfkit import IDFDocument

FIXTURES = Path(__file__).parent.parent / "fixtures"
ARCHETYPE_FILES = sorted((FIXTURES / "archetypes").glob("*.sbem.json"))
MODEL_FILES = sorted((FIXTURES / "models").glob("*.idf"))
WEEKDAY_NAMES = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")


# --- helpers ---------------------------------------------------------------------------------


def _doc(
    *, weekday: str | None = "Tuesday", year: int | None = None, special: tuple[tuple[str, int, str], ...] = ()
) -> IDFDocument:
    doc = new_document()
    if weekday is not None or year is not None:
        doc.run_periods.add(
            "Annual",
            begin_month=1,
            begin_day_of_month=1,
            begin_year=year,
            end_month=12,
            end_day_of_month=31,
            day_of_week_for_start_day=weekday,  # type: ignore[arg-type]
        )
    for index, (start, duration, kind) in enumerate(special):
        doc.run_period_control_special_days.add(
            f"Special {index}",
            start_date=start,
            duration=duration,
            special_day_type=kind,  # type: ignore[arg-type]
        )
    return doc


def _day(name: str, hours: list[float], kind: str = "Fraction") -> DayComponent:
    return DayComponent.model_validate({
        "Name": name,
        "Type": kind,
        **{f"Hour_{h:02d}": v for h, v in enumerate(hours)},
    })


def _week(name: str, workday: DayComponent, weekend: DayComponent) -> WeekComponent:
    return WeekComponent.model_validate({
        "Name": name,
        **dict.fromkeys(WEEKDAY_NAMES[:5], workday),
        **dict.fromkeys(WEEKDAY_NAMES[5:], weekend),
    })


def _fixture_years() -> list[YearComponent]:
    """A small fixture archetype's schedules, with several distinct month patterns."""
    office = _day("office", [0.05] * 7 + [0.5, 0.9] + [1.0] * 8 + [0.6, 0.3] + [0.05] * 5)
    closed = _day("closed", [0.05] * 24)
    summer = _day("summer", [0.05] * 8 + [0.7] * 9 + [0.05] * 7)
    half = _day("half", [0.0] * 6 + [0.123456789] * 12 + [1 / 3] * 6)
    winter_week = _week("winter", office, closed)
    summer_week = _week("summer", summer, closed)
    mixed = WeekComponent.model_validate({
        "Name": "mixed",
        "Monday": office,
        "Tuesday": half,
        "Wednesday": summer,
        "Thursday": office,
        "Friday": half,
        "Saturday": closed,
        "Sunday": summer,
    })
    occupancy_weeks = [winter_week] * 5 + [summer_week] * 3 + [winter_week] * 3 + [mixed]
    occupancy = YearComponent.model_validate({
        "Name": "Occupancy",
        "Type": "Occupancy",
        **dict(zip(MONTHS, occupancy_weeks, strict=True)),
    })
    flat = YearComponent.model_validate({
        "Name": "Always half",
        "Type": "Equipment",
        **dict.fromkeys(MONTHS, _week("flat", _day("h", [0.5] * 24), _day("h", [0.5] * 24))),
    })
    heat_on = _day("heat on", [16.0] * 6 + [21.0] * 16 + [16.0] * 2, "Temperature")
    heat_off = _day("heat off", [12.5] * 24, "Temperature")
    setpoint_weeks = [_week("on", heat_on, heat_off)] * 4 + [_week("off", heat_off, heat_off)] * 6
    setpoint_weeks += [_week("on", heat_on, heat_off)] * 2
    setpoint = YearComponent.model_validate({
        "Name": "Heating setpoint",
        "Type": "Setpoint",
        **dict(zip(MONTHS, setpoint_weeks, strict=True)),
    })
    # Every month different: twelve Through: blocks.
    monthly = YearComponent.model_validate({
        "Name": "Lighting by month",
        "Type": "Lighting",
        **{m: _week(f"w{i}", _day(f"d{i}", [i / 12] * 24), closed) for i, m in enumerate(MONTHS, start=1)},
    })
    return [occupancy, flat, setpoint, monthly]


def _years_in(model: BaseModel) -> Iterator[YearComponent]:
    if isinstance(model, YearComponent):
        yield model
        return
    for field in type(model).model_fields:
        value = getattr(model, field)
        items = cast("list[object]", value) if isinstance(value, list) else [value]
        for item in items:
            if isinstance(item, BaseModel):
                yield from _years_in(item)


def _evaluate_text(tmp_path: Path, text: str, cal: RunPeriodCalendar, doc: IDFDocument | None = None) -> np.ndarray:
    idf = tmp_path / "compact.idf"
    limits = "ScheduleTypeLimits,Fraction,0,1,Continuous;\nScheduleTypeLimits,Temperature,-270,1000,Continuous;\n"
    idf.write_text(f"Version,24.2;\n{limits}{text}\n", encoding="utf-8")
    parsed = load_idf(idf)
    (compact,) = parsed.schedule_compacts
    if doc is not None:  # carry the special days into the evaluation
        for special in doc.run_period_control_special_days:
            parsed.run_period_control_special_days.add(
                special.name,
                start_date=special.start_date,
                duration=special.duration,
                special_day_type=special.special_day_type,
            )
    return np.asarray(values(compact, year=cal.year, document=parsed), dtype=np.float64)


# --- calendar --------------------------------------------------------------------------------


@pytest.mark.parametrize("weekday", WEEKDAY_NAMES)
def test_calendar_starts_on_the_run_period_weekday(weekday: str) -> None:
    cal = RunPeriodCalendar.from_document(_doc(weekday=weekday))

    assert date(cal.year, 1, 1).weekday() == WEEKDAY_NAMES.index(weekday)
    assert cal.start_weekday == WEEKDAY_NAMES.index(weekday)
    assert not pycalendar.isleap(cal.year)
    assert cal.hours == 8760


def test_calendar_defaults_to_sunday_without_a_run_period() -> None:
    cal = RunPeriodCalendar.from_document(_doc(weekday=None))

    assert date(cal.year, 1, 1).weekday() == 6


def test_calendar_uses_the_begin_year_when_given() -> None:
    cal = RunPeriodCalendar.from_document(_doc(weekday=None, year=2024))

    assert cal.year == 2024
    assert cal.hours == 8784


def test_calendar_year_matches_a_begin_date_other_than_january_first() -> None:
    year = calendar_year(3, 15, WEEKDAY_NAMES.index("Friday"))

    assert date(year, 3, 15).weekday() == 4
    assert not pycalendar.isleap(year)


def test_calendar_marks_special_days() -> None:
    doc = _doc(
        weekday="Monday",
        special=(("1/1", 1, "Holiday"), ("12/24", 2, "Holiday"), ("3rd Monday in January", 1, "CustomDay1")),
    )
    cal = RunPeriodCalendar.from_document(doc)

    assert cal.holidays == frozenset({date(cal.year, 1, 1), date(cal.year, 12, 24), date(cal.year, 12, 25)})
    assert cal.custom_day_1 == frozenset({date(cal.year, 1, 15)})
    assert cal.custom_day_2 == frozenset()


@pytest.mark.parametrize("path", MODEL_FILES, ids=lambda p: p.name)
def test_calendar_of_fixture_models(path: Path) -> None:
    doc = load_idf(path, since="22.1")
    cal = RunPeriodCalendar.from_document(doc)

    first = next(iter(doc.run_periods))
    weekday = str(first.day_of_week_for_start_day or "Sunday")  # EnergyPlus's default
    assert date(cal.year, int(first.begin_month), int(first.begin_day_of_month)).weekday() == WEEKDAY_NAMES.index(
        weekday
    )
    holiday_days = sum(
        int(s.duration or 1)
        for s in doc.run_period_control_special_days
        if (s.special_day_type or "Holiday") == "Holiday"
    )
    assert len(cal.holidays) == holiday_days


# --- index and evaluation --------------------------------------------------------------------


def _schedule_doc() -> IDFDocument:
    doc = _doc(weekday="Monday", special=(("7/4", 1, "Holiday"),))
    doc.schedule_type_limits.add("Fraction", lower_limit_value=0, upper_limit_value=1)
    doc.schedule_constants.add("Constant", schedule_type_limits_name="Fraction", hourly_value=0.25)
    doc.schedule_compacts.add(
        "Office",
        schedule_type_limits_name="Fraction",
        data=[
            {"field": "Through: 12/31"},
            {"field": "For: Weekdays"},
            {"field": "Until: 08:00"},
            {"field": "0.0"},
            {"field": "Until: 18:00"},
            {"field": "1.0"},
            {"field": "Until: 24:00"},
            {"field": "0.0"},
            {"field": "For: Weekends Holiday SummerDesignDay WinterDesignDay CustomDay1 CustomDay2"},
            {"field": "Until: 24:00"},
            {"field": "0.1"},
        ],
    )
    hourlies: Any = doc.schedule_day_hourlies  # field names built in a loop
    weeks: Any = doc.schedule_week_dailies
    hourlies.add("Half", schedule_type_limits_name="Fraction", **{f"hour_{h}": 0.5 for h in range(1, 25)})
    hourlies.add("Full", schedule_type_limits_name="Fraction", **{f"hour_{h}": 1.0 for h in range(1, 25)})
    days = ("sunday", "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "holiday")
    days += ("summerdesignday", "winterdesignday", "customday1", "customday2")
    weeks.add("WeekHalf", **{f"{d}_schedule_day_name": "Half" for d in days})
    weeks.add("WeekFull", **{f"{d}_schedule_day_name": "Full" for d in days})
    doc.schedule_years.add(
        "Year",
        schedule_type_limits_name="Fraction",
        schedule_weeks=[
            {"schedule_week_name": "WeekHalf", "start_month": 1, "start_day": 1, "end_month": 6, "end_day": 30},
            {"schedule_week_name": "WeekFull", "start_month": 7, "start_day": 1, "end_month": 12, "end_day": 31},
        ],
    )
    return doc


def test_index_holds_the_full_year_schedule_types_case_insensitively() -> None:
    index = schedule_index(_schedule_doc())

    assert set(index) == {"CONSTANT", "OFFICE", "YEAR"}
    assert index["OFFICE"].name == "Office"


def test_evaluation_on_the_run_period_calendar() -> None:
    doc = _schedule_doc()
    cal = RunPeriodCalendar.from_document(doc)
    evaluate = ScheduleEvaluator(doc, cal)

    constant = evaluate("Constant")
    office = evaluate("office")
    year = evaluate("Year")

    assert constant.dtype == np.float64
    assert constant.shape == (cal.hours,)
    assert (constant == 0.25).all()
    # 1 January is a Monday: 10 occupied hours on day one; 4 July is a holiday.
    assert office[:24].sum() == pytest.approx(10.0)
    july_4 = date(cal.year, 7, 4).timetuple().tm_yday - 1
    assert office[july_4 * 24 : july_4 * 24 + 24].sum() == pytest.approx(2.4)
    assert year.sum() == pytest.approx(181 * 24 * 0.5 + 184 * 24 * 1.0)


def test_evaluation_is_memoised_by_name(monkeypatch: pytest.MonkeyPatch) -> None:
    doc = _schedule_doc()
    calls: list[str] = []
    original = schedules_module.values

    def counting(schedule: object, *args: object, **kwargs: object) -> list[float]:
        calls.append(schedule.name)  # type: ignore[attr-defined]
        return original(schedule, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(schedules_module, "values", counting)
    evaluate = ScheduleEvaluator(doc, RunPeriodCalendar.from_document(doc))

    first = evaluate("Office")
    second = evaluate("OFFICE")
    evaluate("Year")
    evaluate("year")

    assert first is second
    assert calls == ["Office", "Year"]
    assert not first.flags.writeable


def test_evaluation_of_an_unknown_schedule_names_it() -> None:
    doc = _schedule_doc()
    evaluate = ScheduleEvaluator(doc, RunPeriodCalendar.from_document(doc))

    with pytest.raises(KeyError, match="Nope"):
        evaluate("Nope")


def _design_day_doc() -> IDFDocument:
    doc = _schedule_doc()
    doc.schedule_compacts.add(
        "Design",
        schedule_type_limits_name="Fraction",
        data=[
            {"field": "Through: 06/30"},
            {"field": "For: SummerDesignDay"},
            {"field": "Until: 24:00"},
            {"field": "0.2"},
            {"field": "For: AllOtherDays"},
            {"field": "Until: 24:00"},
            {"field": "0.5"},
            {"field": "Through: 12/31"},
            {"field": "For: SummerDesignDay"},
            {"field": "Until: 12:00"},
            {"field": "0.8"},
            {"field": "Until: 24:00"},
            {"field": "1.0"},
            {"field": "For: WinterDesignDay"},
            {"field": "Until: 24:00"},
            {"field": "0.0"},
            {"field": "For: AllOtherDays"},
            {"field": "Until: 24:00"},
            {"field": "0.5"},
        ],
    )
    return doc


def test_design_days_follow_the_models_sizing_periods() -> None:
    doc = _design_day_doc()
    cal = RunPeriodCalendar.from_document(doc)
    assert schedules_module.design_dates(doc, cal.year) == schedules_module.DEFAULT_DESIGN_DATES
    evaluate = ScheduleEvaluator(doc, cal)
    summer = evaluate.design_day("design", "summer")
    winter = evaluate.design_day("Design", "winter")
    assert summer.shape == winter.shape == (24,)
    np.testing.assert_array_equal(summer, [0.8] * 12 + [1.0] * 12)  # 21 July: the second period
    np.testing.assert_array_equal(winter, np.full(24, 0.5))  # 21 January: no winter day, AllOtherDays
    assert evaluate.design_day("DESIGN", "summer") is summer
    assert not summer.flags.writeable
    # The Office schedule's design days are its weekend day, not its Monday.
    np.testing.assert_array_equal(evaluate.design_day("Office", "winter"), np.full(24, 0.1))

    doc.add(
        "SizingPeriod:DesignDay",
        "June cooling",
        validate=False,
        month=6,
        day_of_month=15,
        day_type="SummerDesignDay",
        maximum_dry_bulb_temperature=30.0,
        barometric_pressure=101325.0,
        wind_speed=0.0,
    )
    moved = ScheduleEvaluator(doc, cal)
    assert moved.design_dates["summer"] == (6, 15)
    np.testing.assert_array_equal(moved.design_day("Design", "summer"), np.full(24, 0.2))


def test_design_day_evaluators_need_a_schedule_evaluator() -> None:
    doc = _design_day_doc()
    evaluate = ScheduleEvaluator(doc, RunPeriodCalendar.from_document(doc))
    evaluators = schedules_module.design_day_evaluators(evaluate)
    assert evaluators is not None
    np.testing.assert_array_equal(evaluators["summer"]("Design"), evaluate.design_day("Design", "summer"))

    def plain(name: str) -> np.ndarray[Any, Any]:
        return np.zeros(8760)

    assert schedules_module.design_day_evaluators(plain) is None


def test_design_day_slots_take_one_day_or_one_per_month() -> None:
    days = np.zeros((12, 7, 24))
    per_month = np.linspace(0.0, 1.0, 12)[:, None] * np.ones((1, 24))
    year = to_year_component(
        days, name="S", category="Occupancy", summer_design_day=np.full(24, 0.5), winter_design_day=per_month
    )
    for month, week in enumerate(year.Weeks):
        assert week.SummerDesignDay is not None
        assert week.WinterDesignDay is not None
        assert week.SummerDesignDay.Values == [0.5] * 24
        assert week.WinterDesignDay.Values == pytest.approx([per_month[month, 0]] * 24)
    with pytest.raises(ValueError, match="summer design day has shape"):
        to_year_component(days, name="S", category="Occupancy", summer_design_day=np.zeros((7, 24)))


# --- projection ------------------------------------------------------------------------------


def _random_profile(cal: RunPeriodCalendar, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).random(cal.hours)


def _monthly_energy(profile: np.ndarray, cal: RunPeriodCalendar) -> np.ndarray:
    months = cal.day_months.repeat(24)
    return np.bincount(months, weights=profile, minlength=12)


@pytest.mark.parametrize("year", [2017, 2023, 2024])
def test_projection_conserves_each_months_energy(year: int) -> None:
    cal = RunPeriodCalendar(year=year)
    profile = _random_profile(cal, year)

    days = project(profile, cal)

    assert days.shape == (12, 7, 24)
    np.testing.assert_allclose(_monthly_energy(expand(days, cal), cal), _monthly_energy(profile, cal), rtol=1e-13)


def test_projection_is_the_mean_of_each_months_weekdays() -> None:
    cal = RunPeriodCalendar(year=2023)  # 1 January 2023 is a Sunday
    profile = _random_profile(cal, 1)

    days = project(profile, cal)

    january_sundays = [profile[d * 24 : d * 24 + 24] for d in (0, 7, 14, 21, 28)]
    np.testing.assert_allclose(days[0, 6], np.mean(january_sundays, axis=0), rtol=1e-14)


def test_projection_of_a_representative_profile_is_exact() -> None:
    cal = RunPeriodCalendar(year=2021)
    days = np.random.default_rng(3).random((12, 7, 24))

    np.testing.assert_allclose(project(expand(days, cal), cal), days, rtol=1e-14)


def test_projection_refuses_a_profile_of_the_wrong_length() -> None:
    with pytest.raises(ValueError, match="8760"):
        project(np.zeros(8784), RunPeriodCalendar(year=2023))


@given(
    weights=st.lists(st.floats(min_value=-1e3, max_value=1e3, allow_nan=False), min_size=1, max_size=4),
    seed=st.integers(min_value=0, max_value=2**32 - 1),
    year=st.sampled_from([2017, 2018, 2020, 2021]),
)
def test_projection_is_linear(weights: list[float], seed: int, year: int) -> None:
    cal = RunPeriodCalendar(year=year)
    rng = np.random.default_rng(seed)
    profiles = rng.random((len(weights), cal.hours)) * 1e3
    w = np.asarray(weights)

    merged = project(w @ profiles, cal)
    combined = sum((wi * project(p, cal) for wi, p in zip(w, profiles, strict=True)), np.zeros((12, 7, 24)))

    scale = max(1.0, float(np.abs(w).sum()) * 1e3)
    np.testing.assert_allclose(merged, combined, rtol=0, atol=1e-11 * scale)


# --- conversion to epinterface components ----------------------------------------------------


def test_to_year_component_round_trips_and_shares_equal_days() -> None:
    cal = RunPeriodCalendar(year=2023)
    office = np.r_[np.zeros(8), np.ones(10), np.zeros(6)]
    days = np.zeros((12, 7, 24))
    days[:, :5] = office
    days[5:8, :5] *= 0.5

    year = to_year_component(days, name="Occupancy", category="Occupancy")

    assert year.Type == "Occupancy"
    assert year.schedule_type_limits == "Fraction"
    np.testing.assert_array_equal(representative_days(year), days)
    np.testing.assert_array_equal(year_values(year, cal), expand(days, cal))
    assert year.January.Monday is year.January.Friday
    assert year.January is year.February
    assert year.January.Monday.Name != year.June.Monday.Name
    assert len({d.Name for w in year.Weeks for d in w.Days}) == 3


def test_to_year_component_types_setpoints_as_temperature() -> None:
    year = to_year_component(np.full((12, 7, 24), 21.0), name="Heating", category="Setpoint")

    assert year.schedule_type_limits == "Temperature"


def test_to_year_component_clips_fraction_round_off_only() -> None:
    days = np.full((12, 7, 24), 0.5)
    days[0, 0, 0] = 1.0 + 1e-12
    days[0, 0, 1] = -1e-13

    year = to_year_component(days, name="Lights", category="Lighting")

    assert year.January.Monday.Hour_00 == 1.0
    assert year.January.Monday.Hour_01 == 0.0
    days[0, 0, 0] = 1.01
    with pytest.raises(ValueError, match="Lights"):
        to_year_component(days, name="Lights", category="Lighting")


# --- schedule_compact ------------------------------------------------------------------------


def test_schedule_compact_text_has_one_through_per_run_of_equal_months() -> None:
    occupancy = _fixture_years()[0]

    text = schedule_compact(occupancy)

    lines = [line.split("!-")[0].strip().rstrip(",;") for line in text.splitlines()]
    assert lines[0] == "Schedule:Compact"
    assert lines[1] == "Occupancy"
    assert lines[2] == "Fraction"
    throughs = [line for line in lines if line.startswith("Through:")]
    assert throughs == ["Through: 05/31", "Through: 08/31", "Through: 11/30", "Through: 12/31"]
    fors = [line.split()[1] for line in lines if line.startswith("For:")]
    assert fors == list(WEEKDAYS) * 4
    assert text.splitlines()[-1].split("!-")[0].strip().endswith(";")


def test_schedule_compact_name_override_and_february_end() -> None:
    monthly = _fixture_years()[3]

    text = schedule_compact(monthly, name="Lights")

    assert "  Lights," in text
    assert "Through: 02/29" in text
    with pytest.raises(ValueError, match="name"):
        schedule_compact(monthly, name="bad;name")


@pytest.mark.parametrize("year", [2017, 2023, 2024])
@pytest.mark.parametrize("index", range(4))
def test_schedule_compact_evaluates_to_the_year_components_values(tmp_path: Path, year: int, index: int) -> None:
    schedule = _fixture_years()[index]
    cal = RunPeriodCalendar(year=year)

    hourly = _evaluate_text(tmp_path, schedule_compact(schedule), cal)

    np.testing.assert_array_equal(hourly, year_values(schedule, cal))
    np.testing.assert_array_equal(hourly, expand(representative_days(schedule), cal))


def test_schedule_compact_follows_epinterface_on_special_days(tmp_path: Path) -> None:
    doc = _doc(weekday="Wednesday", special=(("1/1", 1, "Holiday"), ("2/7", 3, "CustomDay2")))
    cal = RunPeriodCalendar.from_document(doc)
    schedule = _fixture_years()[0]

    hourly = _evaluate_text(tmp_path, schedule_compact(schedule), cal, doc)

    expected = year_values(schedule, cal)
    np.testing.assert_array_equal(hourly, expected)
    np.testing.assert_array_equal(expected[:24], schedule.January.Sunday.Values)  # holiday follows Sunday
    feb_7 = 31 + 6
    np.testing.assert_array_equal(expected[feb_7 * 24 : feb_7 * 24 + 24], schedule.February.Monday.Values)


def test_reduced_schedule_converts_without_loss(tmp_path: Path) -> None:
    doc = _schedule_doc()
    cal = RunPeriodCalendar.from_document(doc)
    profile = ScheduleEvaluator(doc, cal)("Office")

    year = to_year_component(project(profile, cal), name="Office reduced", category="Occupancy")
    hourly = _evaluate_text(tmp_path, schedule_compact(year), RunPeriodCalendar(year=cal.year))

    np.testing.assert_allclose(_monthly_energy(hourly, cal), _monthly_energy(profile, cal), rtol=1e-12)


@pytest.mark.parametrize("path", ARCHETYPE_FILES, ids=lambda p: p.name)
def test_every_schedule_of_a_committed_fixture_archetype(tmp_path: Path, path: Path) -> None:
    archetype = Archetype.load(path)
    years = {y.Name: y for y in _years_in(archetype)}
    assert years
    cal = RunPeriodCalendar(year=2023)
    for schedule in years.values():
        hourly = _evaluate_text(tmp_path, schedule_compact(schedule), cal)
        np.testing.assert_array_equal(hourly, year_values(schedule, cal))


def test_fixture_archetype_files_are_optional() -> None:
    if not ARCHETYPE_FILES:
        pytest.skip("no committed fixture archetype in tests/fixtures/archetypes/ yet")
    assert all(p.stat().st_size > 0 for p in ARCHETYPE_FILES)


def test_a_22_1_file_evaluates_through_the_schedule_year_bridge(tmp_path: Path) -> None:
    half = ",".join(["0.5"] * 24)
    week = ",".join(["Half"] * 12)
    idf = tmp_path / "v22_1.idf"
    idf.write_text(
        "Version,22.1;\n"
        "RunPeriod,Annual,1,1,,12,31,,Thursday,Yes,Yes,No,Yes,Yes;\n"
        "ScheduleTypeLimits,Fraction,0,1,Continuous;\n"
        f"Schedule:Day:Hourly,Half,Fraction,{half};\n"
        f"Schedule:Week:Daily,Week,{week};\n"
        "Schedule:Year,Year,Fraction,Week,1,1,12,31;\n",
        encoding="utf-8",
    )
    doc = load_idf(idf, since="22.1")
    cal = RunPeriodCalendar.from_document(doc)

    profile = ScheduleEvaluator(doc, cal)("Year")

    assert date(cal.year, 1, 1).weekday() == WEEKDAY_NAMES.index("Thursday")
    assert profile.sum() == pytest.approx(0.5 * cal.hours)


def test_schedule_compact_is_public() -> None:
    assert reduction.schedule_compact is schedule_compact
    assert "schedule_compact" in reduction.__all__


# --- holiday and design-day slots (UP-2; T087) ------------------------------------------------


def _holiday_calendar() -> RunPeriodCalendar:
    doc = _doc(weekday="Monday", special=(("1/1", 1, "Holiday"), ("7/4", 1, "Holiday"), ("12/25", 2, "Holiday")))
    return RunPeriodCalendar.from_document(doc)


@pytest.mark.parametrize("seed", [1, 2])
def test_projection_with_holidays_conserves_each_months_energy(seed: int) -> None:
    cal = _holiday_calendar()
    profile = _random_profile(cal, seed)

    days, holidays = project_holidays(profile, cal)

    assert days.shape == (12, 7, 24)
    assert sorted(holidays) == [0, 6, 11]
    hourly = expand(days, cal, holidays=holidays)
    np.testing.assert_allclose(_monthly_energy(hourly, cal), _monthly_energy(profile, cal), rtol=1e-13)


def test_projection_with_holidays_keeps_the_holiday_profile_apart() -> None:
    cal = _holiday_calendar()
    profile = np.ones(cal.hours)
    july_4 = date(cal.year, 7, 4).timetuple().tm_yday - 1
    profile[july_4 * 24 : july_4 * 24 + 24] = 0.0

    days, holidays = project_holidays(profile, cal)

    np.testing.assert_array_equal(holidays[6], np.zeros(24))
    np.testing.assert_array_equal(days[6], np.ones((7, 24)))  # weekday means exclude the holiday


def test_to_year_component_writes_holiday_and_design_day_slots() -> None:
    cal = _holiday_calendar()
    days = np.full((12, 7, 24), 0.5)
    holidays = {0: np.full(24, 0.1), 6: np.full(24, 0.2)}
    summer, winter = np.full(24, 1.0), np.full(24, 0.0)

    year = to_year_component(
        days,
        name="Occ",
        category="Occupancy",
        holidays=holidays,
        summer_design_day=summer,
        winter_design_day=winter,
    )

    assert year.January.Holiday is not None
    assert year.January.Holiday.Values == [0.1] * 24
    assert year.February.Holiday is None
    assert year.March.SummerDesignDay is not None
    assert year.March.SummerDesignDay.Values == [1.0] * 24
    assert year.March.WinterDesignDay is not None
    assert year.January is not year.February  # weeks differ by their holiday slot
    assert year.February is year.March
    np.testing.assert_array_equal(holiday_days(year)[0], holidays[0])
    expected = expand(days, cal, holidays=holidays)
    np.testing.assert_array_equal(year_values(year, cal), expected)


def test_schedule_compact_writes_holiday_and_design_day_blocks(tmp_path: Path) -> None:
    doc = _doc(weekday="Monday", special=(("1/1", 1, "Holiday"), ("7/4", 1, "Holiday")))
    cal = RunPeriodCalendar.from_document(doc)
    days = np.full((12, 7, 24), 0.5)
    year = to_year_component(
        days,
        name="Occ",
        category="Occupancy",
        holidays={0: np.full(24, 0.25), 6: np.full(24, 0.75)},
        summer_design_day=np.full(24, 1.0),
        winter_design_day=np.full(24, 0.0),
    )

    text = schedule_compact(year)

    fors = [line.split("!-")[0].strip().rstrip(",;") for line in text.splitlines() if "For:" in line]
    assert "For: Holiday" in fors
    assert "For: SummerDesignDay" in fors
    assert "For: WinterDesignDay" in fors
    assert "For: Monday CustomDay1 CustomDay2" in fors
    hourly = _evaluate_text(tmp_path, text, cal, doc)
    np.testing.assert_array_equal(hourly, year_values(year, cal))
    assert hourly[:24].tolist() == [0.25] * 24
    idf = tmp_path / "compact.idf"
    (compact,) = load_idf(idf).schedule_compacts
    summer_noon = datetime(cal.year, 7, 15, 14)  # noqa: DTZ001 - schedules are in local time
    winter_noon = datetime(cal.year, 1, 15, 14)  # noqa: DTZ001
    assert evaluate_at(compact, summer_noon, day_type="summer") == 1.0
    assert evaluate_at(compact, winter_noon, day_type="winter") == 0.0


def test_schedule_compact_without_slots_is_unchanged() -> None:
    text = schedule_compact(_fixture_years()[0])

    assert "For: Monday SummerDesignDay WinterDesignDay CustomDay1 CustomDay2" in text
    assert "For: Sunday Holiday" in text
