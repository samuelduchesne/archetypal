"""Tests for `archetypal.comparison` (spec 002, US3: T074, T075).

The detailed/archetype pairs are committed EnergyPlus 24.2 results:

- `models/ten_zone_multipliers.sql` and `models/ten_zone_explicit.sql`: the same building
  with and without zone multipliers (pumps, gas and electric heating, hot water);
- `comparison/*.sql`: two-week runs of the bar building, each changing one thing from
  `comparison/base.sql` (see `tests/fixtures/regenerate_comparison.py`).
"""

from __future__ import annotations

import hashlib
import math
import re
import shutil
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest
from idfkit.simulation import SQLResult

from archetypal import compare as compare_from_package
from archetypal.comparison import AcceptanceTargets, ComparisonResult, ComparisonRow, compare
from archetypal.errors import NotComparableError

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.schedules import ScheduleEvaluator
    from archetypal.reduction.sources import SourceData

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
MODELS = FIXTURES / "models"
COMPARISON = FIXTURES / "comparison"
CHICAGO = FIXTURES / "weather" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
ABUPS = "AnnualBuildingUtilityPerformanceSummary"

DETAILED = MODELS / "ten_zone_multipliers.sql"
ARCHETYPE = MODELS / "ten_zone_explicit.sql"


@pytest.fixture(scope="module")
def ten_zone() -> ComparisonResult:
    return compare(DETAILED, ARCHETYPE)


@pytest.fixture(scope="module")
def bar_lights() -> ComparisonResult:
    return compare(COMPARISON / "base.sql", COMPARISON / "lights.sql")


def _end_uses(path: Path) -> dict[tuple[str, str], float]:
    """Every non-zero (end use, fuel) of the End Uses table, read independently of archetypal."""
    sql = SQLResult(path)
    try:
        rows = sql.get_tabular_data(report_name=ABUPS, table_name="End Uses")
    finally:
        sql.close()
    found: dict[tuple[str, str], float] = {}
    for row in rows:
        if row.row_name == "Total End Uses" or row.column_name == "Water" or not row.value:
            continue
        value = row.as_float()
        if value != 0:
            found[row.row_name, row.column_name] = value
    return found


def _hourly_sum(sql: SQLResult, pattern: str) -> list[float]:
    """The hourly sum of the meters whose name matches `pattern`."""
    meters = [v for v in sql.list_variables() if v.is_meter and re.fullmatch(pattern, v.name)]
    series = sql.get_timeseries_many(meters)
    return [sum(values) for values in zip(*(s.values for s in series), strict=True)]


# --- T074: rows, values and targets ------------------------------------------------------------


def test_compare_is_reexported_from_the_package() -> None:
    assert compare_from_package is compare


def test_rows_cover_total_site_every_end_use_and_both_peaks(ten_zone: ComparisonResult) -> None:
    metrics = [row.metric for row in ten_zone.rows]
    assert len(metrics) == len(set(metrics))
    assert metrics[0] == "Total site energy"
    end_uses = {(r.end_use, r.fuel) for r in ten_zone.rows if r.kind == "end_use"}
    expected = set(_end_uses(DETAILED)) | set(_end_uses(ARCHETYPE))
    assert end_uses == expected
    assert ("Pumps", "Electricity") in end_uses
    kinds = {r.metric: r.kind for r in ten_zone.rows}
    assert kinds["Heating, with pumps and heat rejection"] == "end_use_with_distribution"
    assert kinds["Cooling, with pumps and heat rejection"] == "end_use_with_distribution"
    assert kinds["Peak heating demand"] == "peak"
    assert kinds["Peak cooling demand"] == "peak"
    assert ten_zone.comparable is True


def test_row_values_difference_and_relative(ten_zone: ComparisonResult) -> None:
    total = ten_zone.row("Total site energy")
    assert total.units == "GJ"
    assert total.detailed == pytest.approx(3999.30)
    assert total.difference == pytest.approx(total.archetype - total.detailed)
    assert total.relative == pytest.approx(total.difference / total.detailed)
    lighting = ten_zone.row("Interior Lighting: Electricity")
    assert lighting.detailed == pytest.approx(_end_uses(DETAILED)["Interior Lighting", "Electricity"])
    assert lighting.archetype == pytest.approx(_end_uses(ARCHETYPE)["Interior Lighting", "Electricity"])


def test_targets_follow_sc001_to_sc003(ten_zone: ComparisonResult) -> None:
    targets = AcceptanceTargets()
    assert (targets.total_site, targets.end_use, targets.end_use_min_share) == (0.05, 0.10, 0.05)
    assert (targets.peak, targets.peak_min_share) == (0.15, 0.10)
    total = ten_zone.row("Total site energy")
    assert total.target == 0.05
    assert total.within_target is (abs(total.relative or 0) <= 0.05)
    lighting = ten_zone.row("Interior Lighting: Electricity")
    assert lighting.target == 0.10
    assert lighting.within_target is (abs(lighting.relative or 0) <= 0.10)


def test_end_uses_below_five_percent_of_site_energy_are_not_judged(ten_zone: ComparisonResult) -> None:
    total = ten_zone.row("Total site energy").detailed
    fans = ten_zone.row("Fans: Electricity")  # 2.5 % of site energy: compared on its own, not judged
    assert fans.detailed / total < 0.05
    assert fans.target == 0.10
    assert fans.within_target is None


def test_pumps_and_heat_rejection_are_reported_but_not_judged(ten_zone: ComparisonResult) -> None:
    pumps = ten_zone.row("Pumps: Electricity")
    assert pumps.detailed == pytest.approx(62.26)
    assert pumps.target is None
    assert pumps.within_target is None


def test_heating_and_cooling_as_reported_are_judged_with_distribution_added(ten_zone: ComparisonResult) -> None:
    for row in ten_zone.rows:
        if row.kind == "end_use" and row.end_use in {"Heating", "Cooling"}:
            assert row.target is None
            assert row.within_target is None
    with_heating = ten_zone.row("Heating, with pumps and heat rejection")
    assert with_heating.target == 0.10
    assert with_heating.within_target is (abs(with_heating.relative or 0) <= 0.10)


_DELIVERY_VARIABLES = {
    "Heating": (
        "Zone Ideal Loads Supply Air Total Heating Energy",
        "Heating Coil Heating Energy",
        "Baseboard Total Heating Energy",
        "Zone Radiant HVAC Heating Energy",
    ),
    "Cooling": (
        "Zone Ideal Loads Supply Air Total Cooling Energy",
        "Cooling Coil Total Cooling Energy",
        "Zone Radiant HVAC Cooling Energy",
    ),
}


def _expected_heating_share_of_pumps(path: Path) -> float:
    """Pumps energy split by each hour's equipment-delivered modes (R12, R13), computed independently."""
    sql = SQLResult(path)
    try:
        pumps = _hourly_sum(sql, r"Pumps:\w+")
        delivered: dict[str, list[float]] = {}
        for mode, names in _DELIVERY_VARIABLES.items():
            variables = [v for v in sql.list_variables() if v.name in names and not v.is_meter]
            series = sql.get_timeseries_many(variables)
            delivered[mode] = [sum(s.values[h] for s in series) for h in range(len(pumps))]
    finally:
        sql.close()
    to_heating = idle = 0.0
    for h, energy in enumerate(pumps):
        both = delivered["Heating"][h] + delivered["Cooling"][h]
        if both > 0:
            to_heating += energy * delivered["Heating"][h] / both
        else:
            idle += energy
    annual_heat, annual_cool = sum(delivered["Heating"]), sum(delivered["Cooling"])
    to_heating += idle * annual_heat / (annual_heat + annual_cool)
    return to_heating / sum(pumps)


@pytest.fixture(scope="module")
def heating_share() -> float:
    """`_expected_heating_share_of_pumps(DETAILED)`, read once for the tests that need it."""
    return _expected_heating_share_of_pumps(DETAILED)


def test_pumps_are_added_to_heating_and_cooling_by_hourly_delivered_mode(
    ten_zone: ComparisonResult, heating_share: float
) -> None:
    uses = _end_uses(DETAILED)
    heating = sum(v for (use, _), v in uses.items() if use == "Heating")
    cooling = sum(v for (use, _), v in uses.items() if use == "Cooling")
    pumps = uses["Pumps", "Electricity"]
    share = heating_share
    assert 0 < share < 1
    with_heating = ten_zone.row("Heating, with pumps and heat rejection").detailed
    with_cooling = ten_zone.row("Cooling, with pumps and heat rejection").detailed
    assert with_heating == pytest.approx(heating + share * pumps, rel=1e-9)
    assert with_heating > heating
    assert with_cooling > cooling
    # Every joule of pump energy goes to heating or cooling, none is created or lost (R12).
    assert with_heating + with_cooling == pytest.approx(heating + cooling + pumps, rel=1e-9)


def test_pump_split_agrees_with_the_reduction_attribution(
    heating_share: float,
    detailed: Callable[[str], tuple[SourceData, tuple[ClassifiedZone, ...], ScheduleEvaluator]],
) -> None:
    """R13 splits pumps on the same equipment-delivered energy as R12's efficiency attribution."""
    from archetypal.reduction.efficiency import building_energy  # noqa: PLC0415 - loads epinterface

    sources, zones, evaluate = detailed("ten_zone_multipliers")
    data = building_energy(sources, zones, evaluate)
    hours = len(data.outdoor_temperature)
    building: dict[str, np.ndarray] = {}
    for mode in ("heating", "cooling"):
        total = np.zeros(hours)
        for name, profile in data.delivered[mode].items():
            total += data.multipliers[name] * np.asarray(profile, dtype=np.float64)
        building[mode] = total
    pumps = np.zeros(hours)
    for profile in data.distribution.values():
        pumps += np.asarray(profile, dtype=np.float64)
    both = building["heating"] + building["cooling"]
    hourly = np.divide(building["heating"], both, out=np.zeros_like(both), where=both > 0)
    idle = float(np.sum(pumps[both <= 0]))
    annual_heat, annual_cool = float(np.sum(building["heating"])), float(np.sum(building["cooling"]))
    hourly_part = float(np.sum(pumps * hourly))
    reduction_share = (hourly_part + idle * annual_heat / (annual_heat + annual_cool)) / float(np.sum(pumps))
    assert reduction_share == pytest.approx(heating_share, rel=1e-6)


def test_without_distribution_the_combined_rows_sum_every_fuel(bar_lights: ComparisonResult) -> None:
    uses = _end_uses(COMPARISON / "base.sql")
    row = bar_lights.row("Heating, with pumps and heat rejection")
    assert row.detailed == pytest.approx(sum(v for (use, _), v in uses.items() if use == "Heating"))
    assert "Pumps: Electricity" not in {r.metric for r in bar_lights.rows}


def test_peaks_are_the_maximum_of_summed_meters(ten_zone: ComparisonResult) -> None:
    sql = SQLResult(DETAILED)
    try:
        heating = max(_hourly_sum(sql, r"Heating:\w+")) / 3600.0
        cooling = max(_hourly_sum(sql, r"Cooling:\w+")) / 3600.0
    finally:
        sql.close()
    assert ten_zone.row("Peak heating demand").detailed == pytest.approx(heating)
    assert ten_zone.row("Peak cooling demand").detailed == pytest.approx(cooling)
    assert ten_zone.row("Peak heating demand").units == "W"
    assert ten_zone.row("Peak heating demand").target == 0.15


def test_a_peak_below_ten_percent_of_the_larger_is_not_judged(bar_lights: ComparisonResult) -> None:
    heating = bar_lights.row("Peak heating demand")
    cooling = bar_lights.row("Peak cooling demand")
    assert 0 < cooling.detailed < 0.10 * heating.detailed
    assert cooling.within_target is None
    assert heating.within_target is not None


def test_differences_outside_the_targets_are_flagged(bar_lights: ComparisonResult) -> None:
    lighting = bar_lights.row("Interior Lighting: Electricity")  # 14 W/m² instead of 10
    assert lighting.relative == pytest.approx(0.4, abs=0.02)
    assert lighting.within_target is False
    assert lighting in bar_lights.failures
    assert not bar_lights.passed


def test_identical_results_pass_every_target() -> None:
    result = compare(COMPARISON / "base.sql", COMPARISON / "base.sql")
    assert all(row.difference == 0 for row in result.rows)
    assert all(row.within_target in {True, None} for row in result.rows)
    assert result.passed
    assert result.failures == ()


def test_custom_targets() -> None:
    loose = AcceptanceTargets(end_use=0.5)
    result = compare(COMPARISON / "base.sql", COMPARISON / "lights.sql", targets=loose)
    assert result.targets is loose
    assert result.row("Interior Lighting: Electricity").within_target is True


@pytest.mark.parametrize("field", ["total_site", "end_use", "end_use_min_share", "peak", "peak_min_share"])
def test_targets_must_be_non_negative_fractions(field: str) -> None:
    with pytest.raises(ValueError, match=field):
        AcceptanceTargets(**{field: -0.1})


def test_accepts_open_sql_results_and_ip_units() -> None:
    detailed = SQLResult(COMPARISON / "ip_units.sql")
    try:
        result = compare(detailed, detailed)
    finally:
        detailed.close()
    assert result.row("Total site energy").units == "kBtu"
    assert result.row("Total site energy").detailed == pytest.approx(14106.92)


def test_unknown_metric_raises_key_error(ten_zone: ComparisonResult) -> None:
    with pytest.raises(KeyError, match="Nonexistent"):
        ten_zone.row("Nonexistent")


def test_rows_are_frozen(ten_zone: ComparisonResult) -> None:
    row: ComparisonRow = ten_zone.rows[0]
    with pytest.raises(AttributeError):
        row.detailed = 0.0  # type: ignore[misc]


def test_relative_is_none_when_the_detailed_value_is_zero() -> None:
    result = compare(COMPARISON / "base.sql", COMPARISON / "base.sql")
    for row in result.rows:
        if row.detailed == 0:
            assert row.relative is None
            assert row.within_target is None
        else:
            assert row.relative is not None
            assert not math.isnan(row.relative)


# --- T075: refusals ----------------------------------------------------------------------------

REFUSALS = {
    "weather": "weather",
    "run_period": "run period",
    "ip_units": "units",
    "timestep": "timestep",
    "frequency": "reporting frequency",
}


@pytest.mark.parametrize(("fixture", "item"), list(REFUSALS.items()))
def test_one_difference_is_refused_and_named(fixture: str, item: str) -> None:
    with pytest.raises(NotComparableError) as caught:
        compare(COMPARISON / "base.sql", COMPARISON / f"{fixture}.sql")
    assert len(caught.value.differences) == 1
    assert caught.value.differences[0].startswith(f"{item}: ")
    assert "base.sql" in caught.value.subject
    assert f"{fixture}.sql" in caught.value.subject


def test_every_difference_is_named_at_once() -> None:
    with pytest.raises(NotComparableError) as caught:
        compare(COMPARISON / "base.sql", COMPARISON / "everything.sql")
    items = [difference.split(": ", 1)[0] for difference in caught.value.differences]
    assert items == list(REFUSALS.values())


def test_refusal_messages_give_both_values() -> None:
    with pytest.raises(NotComparableError) as caught:
        compare(COMPARISON / "base.sql", COMPARISON / "everything.sql")
    text = "\n".join(caught.value.differences)
    assert "Chicago Ohare Intl Ap IL USA TMY3 WMO#=725300" in text
    assert "Duluth International Arpt MN USA TMY3 WMO#=727450" in text
    assert "03-15 00:00 to 03-29 00:00" in text
    assert "03-29 00:00 to 04-12 00:00" in text
    assert "GJ" in text
    assert "kBtu" in text
    assert "4 per hour" in text
    assert "6 per hour" in text
    assert "Hourly" in text
    assert "Zone Timestep" in text


def test_the_weather_file_is_checked_and_hashed() -> None:
    result = compare(COMPARISON / "base.sql", COMPARISON / "lights.sql", weather=CHICAGO)
    assert result.weather_sha256 == hashlib.sha256(CHICAGO.read_bytes()).hexdigest()
    assert compare(COMPARISON / "base.sql", COMPARISON / "lights.sql").weather_sha256 is None


def test_results_run_with_another_weather_file_are_refused(tmp_path: Path) -> None:
    lines = CHICAGO.read_text(encoding="latin-1").splitlines(keepends=True)
    lines[0] = "LOCATION,Duluth International Arpt,MN,USA,TMY3,727450,46.83,-92.22,-6.0,433.0\n"
    duluth = tmp_path / "duluth.epw"
    duluth.write_text("".join(lines), encoding="latin-1")
    with pytest.raises(NotComparableError) as caught:
        compare(COMPARISON / "base.sql", COMPARISON / "lights.sql", weather=duluth)
    assert len(caught.value.differences) == 2  # neither result was run with it
    assert all(d.startswith("weather: ") for d in caught.value.differences)
    assert "duluth.epw" in caught.value.differences[0]


# --- Meter frequencies -------------------------------------------------------------------------


def _with_meter(source: Path, target: Path, meter: str, frequency: str) -> Path:
    """Copy `source` to `target`, declaring `meter` again at `frequency` (with no values)."""
    shutil.copy(source, target)
    with sqlite3.connect(target) as db:
        (index_group,) = db.execute(
            "SELECT IndexGroup FROM ReportDataDictionary WHERE Name = ? AND IsMeter = 1", (meter,)
        ).fetchone()
        db.execute(
            "INSERT INTO ReportDataDictionary (IsMeter, Type, IndexGroup, TimestepType, KeyValue, Name, "
            "ReportingFrequency, ScheduleName, Units) VALUES (1, 'Sum', ?, 'Zone', NULL, ?, ?, NULL, 'J')",
            (index_group, meter, frequency),
        )
    return target


def test_a_run_period_meter_does_not_break_the_distribution_split(tmp_path: Path, ten_zone: ComparisonResult) -> None:
    detailed = _with_meter(DETAILED, tmp_path / "detailed.sql", "Pumps:Electricity", "Run Period")
    result = compare(detailed, ARCHETYPE)
    assert result.row("Peak heating demand").detailed == ten_zone.row("Peak heating demand").detailed


@pytest.mark.parametrize(
    ("meter", "frequency"),
    [("Cooling:DistrictCooling", "Zone Timestep"), ("Heating:DistrictHeatingWater", "HVAC System Timestep")],
)
def test_peaks_use_the_finest_frequency_every_mode_meter_shares(tmp_path: Path, meter: str, frequency: str) -> None:
    base = COMPARISON / "base.sql"
    extra = _with_meter(base, tmp_path / "extra.sql", meter, frequency)
    result = compare(base, extra)
    assert result.row("Peak heating demand").archetype == result.row("Peak heating demand").detailed > 0.0
    assert result.row("Peak cooling demand").archetype == result.row("Peak cooling demand").detailed > 0.0


def test_meters_at_different_frequencies_are_not_compared_on_some_of_them(tmp_path: Path) -> None:
    """Hourly heating and Monthly cooling meters give no peak frequency: refused, not a 0 W cooling peak."""
    copy = tmp_path / "monthly_cooling.sql"
    shutil.copyfile(COMPARISON / "base.sql", copy)
    with sqlite3.connect(copy) as db:
        db.execute(
            "UPDATE ReportDataDictionary SET ReportingFrequency = 'Monthly' WHERE IsMeter = 1 AND Name LIKE 'Cooling:%'"
        )
    db.close()
    with pytest.raises(NotComparableError, match="reporting frequency"):
        compare(copy, copy)


def test_two_runs_compare_peaks_at_the_finest_frequency_they_share() -> None:
    from archetypal.comparison.results import RunResults, common_peak_frequency, differences  # noqa: PLC0415

    detailed = RunResults(
        label="detailed",
        frequency="Zone Timestep",
        peaks={"Heating": 2000.0, "Cooling": 1000.0},
        peaks_by_frequency={
            "Zone Timestep": {"Heating": 2000.0, "Cooling": 1000.0},
            "Hourly": {"Heating": 1800.0, "Cooling": 900.0},
        },
    )
    archetype = RunResults(
        label="archetype",
        frequency="Hourly",
        peaks={"Heating": 1800.0, "Cooling": 900.0},
        peaks_by_frequency={"Hourly": {"Heating": 1800.0, "Cooling": 900.0}},
    )
    assert common_peak_frequency(detailed, archetype) == "Hourly"
    assert not [d for d in differences(detailed, archetype) if d.startswith("reporting frequency")]
    daily = RunResults(label="daily", frequency="Daily", peaks_by_frequency={"Daily": {}})
    assert any(d.startswith("reporting frequency") for d in differences(detailed, daily))


def test_end_uses_in_mixed_units_are_converted_to_the_totals_unit(tmp_path: Path) -> None:
    """`InchPoundExceptElectricity` writes electricity in kWh and the other fuels and total in kBtu."""
    mixed = tmp_path / "mixed.sql"
    shutil.copyfile(COMPARISON / "ip_units.sql", mixed)
    factor = 1.05505585262e6 / 3.6e6  # kBtu to kWh
    with sqlite3.connect(mixed) as db:
        (kwh,) = db.execute("SELECT COALESCE(MAX(StringIndex), 0) + 1 FROM Strings").fetchone()
        (type_index,) = db.execute("SELECT StringTypeIndex FROM Strings WHERE Value = 'kBtu' LIMIT 1").fetchone()
        db.execute("INSERT INTO Strings (StringIndex, StringTypeIndex, Value) VALUES (?, ?, 'kWh')", (kwh, type_index))
        cells = (
            "SELECT td.TabularDataIndex FROM TabularData td "
            "JOIN Strings r ON td.ReportNameIndex = r.StringIndex "
            "JOIN Strings t ON td.TableNameIndex = t.StringIndex "
            "JOIN Strings c ON td.ColumnNameIndex = c.StringIndex "
            "WHERE r.Value = 'AnnualBuildingUtilityPerformanceSummary' AND t.Value = 'End Uses' "
            "AND c.Value = 'Electricity'"
        )
        for (index,) in db.execute(cells).fetchall():
            (value,) = db.execute("SELECT Value FROM TabularData WHERE TabularDataIndex = ?", (index,)).fetchone()
            converted = f"{float(value) * factor:.6f}" if value.strip() else value
            db.execute(
                "UPDATE TabularData SET Value = ?, UnitsIndex = ? WHERE TabularDataIndex = ?", (converted, kwh, index)
            )
    db.close()
    result = compare(COMPARISON / "ip_units.sql", mixed)
    for row in result.rows:
        assert row.archetype == pytest.approx(row.detailed, rel=1e-4, abs=1e-3), row.metric


def test_run_periods_of_two_years_with_the_same_calendar_are_comparable() -> None:
    from datetime import datetime, timezone  # noqa: PLC0415

    from archetypal.comparison.results import RunResults, differences  # noqa: PLC0415

    # 2006 and 2017 both start on a Sunday and have no 29 February.
    first = RunResults(
        label="a", period=(datetime(2006, 1, 1, tzinfo=timezone.utc), datetime(2007, 1, 1, tzinfo=timezone.utc))
    )
    same = RunResults(
        label="b", period=(datetime(2017, 1, 1, tzinfo=timezone.utc), datetime(2018, 1, 1, tzinfo=timezone.utc))
    )
    other = RunResults(
        label="c", period=(datetime(2018, 1, 1, tzinfo=timezone.utc), datetime(2019, 1, 1, tzinfo=timezone.utc))
    )  # Monday
    assert not [d for d in differences(first, same) if d.startswith("run period")]
    (found,) = [d for d in differences(first, other) if d.startswith("run period")]
    assert "Sunday" in found
    assert "Monday" in found
