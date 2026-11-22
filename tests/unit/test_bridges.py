"""Tests for the temporary idfkit bridge `normalise_schedule_year` (spec 002, T018; UP-6)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from idfkit import load_idf
from idfkit.schedules import values
from idfkit.versioned import as_version

from archetypal.reduction._bridges import normalise_schedule_year

if TYPE_CHECKING:
    from pathlib import Path

HALF = ",".join(["0.5"] * 24)
FULL = ",".join(["1.0"] * 24)
WEEK_HALF = ",".join(["Half"] * 12)
WEEK_FULL = ",".join(["Full"] * 12)
# Half the year at 0.5, half at 1.0: 181 days * 24 h * 0.5 + 184 days * 24 h * 1.0 in 2023.
EXPECTED_SUM = 181 * 24 * 0.5 + 184 * 24 * 1.0

IDF = f"""Version,{{version}};
ScheduleTypeLimits,Fraction,0,1,Continuous;
Schedule:Day:Hourly,Half,Fraction,{HALF};
Schedule:Day:Hourly,Full,Fraction,{FULL};
Schedule:Week:Daily,WeekHalf,{WEEK_HALF};
Schedule:Week:Daily,WeekFull,{WEEK_FULL};
Schedule:Year,Year,Fraction,WeekHalf,1,1,6,30,WeekFull,7,1,12,31;
"""


def _write(tmp_path: Path, version: str, body: str = IDF) -> Path:
    path = tmp_path / f"year_{version}.idf"
    path.write_text(body.format(version=version), encoding="utf-8")
    return path


@pytest.mark.parametrize("version", ["22.1", "22.2", "24.2"])
def test_schedule_year_from_file_evaluates_after_normalisation(tmp_path: Path, version: str) -> None:
    doc = as_version(load_idf(_write(tmp_path, version)), since="22.1")
    year = doc["Schedule:Year"]["Year"]

    normalised = normalise_schedule_year(year)

    assert sum(values(normalised, document=doc, year=2023)) == pytest.approx(EXPECTED_SUM)
    weeks = normalised.schedule_weeks.as_list()
    assert [(w["start_month"], w["start_day"], w["end_month"], w["end_day"]) for w in weeks] == [
        (1, 1, 6, 30),
        (7, 1, 12, 31),
    ]
    for w in weeks:
        for field in ("start_month", "start_day", "end_month", "end_day"):
            assert type(w[field]) is int
    assert [w["schedule_week_name"] for w in weeks] == ["WeekHalf", "WeekFull"]
    assert normalised.name == "Year"
    assert normalised.schedule_type_limits_name == "Fraction"


def test_original_object_is_not_modified(tmp_path: Path) -> None:
    doc = as_version(load_idf(_write(tmp_path, "22.1")), since="22.1")
    year = doc["Schedule:Year"]["Year"]
    before = [dict(g.as_dict()) for g in year.schedule_weeks]

    normalised = normalise_schedule_year(year)

    assert normalised is not year
    assert [dict(g.as_dict()) for g in year.schedule_weeks] == before
    assert doc["Schedule:Year"]["Year"] is year
    assert len(doc["Schedule:Year"]) == 1


def test_fractional_month_or_day_is_refused(tmp_path: Path) -> None:
    body = IDF.replace("WeekHalf,1,1,6,30", "WeekHalf,1,1,6,30.5")
    doc = as_version(load_idf(_write(tmp_path, "22.1", body)), since="22.1")
    with pytest.raises(ValueError, match=r"Year: .*end_day.*30\.5"):
        normalise_schedule_year(doc["Schedule:Year"]["Year"])


def test_remove_bridge_once_idfkit_fixes_up6(tmp_path: Path) -> None:
    """REMOVE ME with the bridge: this fails once idfkit evaluates a 22.1 `Schedule:Year` itself.

    When it fails, UP-6 is released: delete `archetypal/reduction/_bridges.py`, its call in
    `schedules.py` and this test file.
    """
    doc = as_version(load_idf(_write(tmp_path, "22.1")), since="22.1")
    year = doc["Schedule:Year"]["Year"]
    try:
        values(year, document=doc, year=2023)
    except ValueError:
        return
    pytest.fail(
        "idfkit now evaluates a Schedule:Year read from an EnergyPlus 22.1 file (UP-6 is fixed): "
        "remove archetypal.reduction._bridges.normalise_schedule_year and this test."
    )
