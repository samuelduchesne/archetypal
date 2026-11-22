"""Tests for `RESULTS_REQUIREMENTS` and `check_results` (spec 002, T015)."""

from __future__ import annotations

import re
import shutil
import sqlite3
from pathlib import Path

from idfkit.simulation import SQLResult

from archetypal.errors import MissingResults
from archetypal.reduction.requirements import RESULTS_REQUIREMENTS, ModelFacts, ResultRequirement, check_results

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "specs" / "002-reduce-to-sbem" / "contracts" / "results-requirements.md"
FIXTURES = ROOT / "tests" / "fixtures" / "models"

FACTS = ModelFacts(
    zones=("Core", "Perimeter_1"),
    fans=("Supply Fan",),
    pumps=("HW Pump",),
    zone_air_inlet_nodes=("Core Inlet", "Perimeter_1 Inlet"),
    water_use_equipment=("Sinks",),
    end_use_fuels=(("Heating", "NaturalGas"), ("Heating", "Electricity"), ("Cooling", "Electricity")),
)


# --- The contract's table ----------------------------------------------------------------------


def _contract_rows() -> list[tuple[str, str, str, str, str]]:
    """Parse the "Output variables and meters" table into (kind, item, key, frequency, used for)."""
    text = CONTRACT.read_text(encoding="utf-8")
    section = text.split("## Output variables and meters", 1)[1].split("\n## ", 1)[0]
    lines = [line for line in section.splitlines() if line.startswith("|")]
    header = [cell.strip() for cell in lines[0].strip("|").split("|")]
    assert header == ["Item", "Key", "Frequency", "Used for"]
    assert set(lines[1]) <= set("|-: ")
    rows: list[tuple[str, str, str, str, str]] = []
    for line in lines[2:]:
        item, key, frequency, used_for = (cell.strip() for cell in line.strip().strip("|").split("|"))
        kind = "meter" if item.startswith("Meters ") else "variable"
        names = re.findall(r"`([^`]+)`", item)
        assert names, line
        rows.extend((kind, name, key.replace("`", ""), frequency, used_for) for name in names)
    return rows


def _constant_rows() -> list[tuple[str, str, str, str, str]]:
    return [(r.kind, r.item, r.key, r.frequency, r.used_for) for r in RESULTS_REQUIREMENTS]


def test_constant_lists_exactly_the_contract_rows() -> None:
    assert _constant_rows() == _contract_rows()


def test_idf_text() -> None:
    by_item = {r.item: r for r in RESULTS_REQUIREMENTS}
    heating = by_item["Zone Air System Sensible Heating Energy"]
    assert heating.idf_text == "Output:Variable,*,Zone Air System Sensible Heating Energy,Hourly;"
    assert heating.idf_objects(FACTS) == (heating.idf_text,)
    fans = by_item["Fans:Electricity"]
    assert fans.idf_text == "Output:Meter,Fans:Electricity,Hourly;"
    fuel = by_item["Heating:<fuel>"]
    assert fuel.idf_text == "Output:Meter,Heating:<fuel>,Hourly;"
    assert fuel.idf_objects(FACTS) == (
        "Output:Meter,Heating:Electricity,Hourly;",
        "Output:Meter,Heating:NaturalGas,Hourly;",
    )


# --- A results database built in a temporary directory ----------------------------------------

_DDL = """
CREATE TABLE ReportDataDictionary(
    ReportDataDictionaryIndex INTEGER PRIMARY KEY,
    IsMeter INTEGER,
    Type TEXT,
    IndexGroup TEXT,
    TimestepType TEXT,
    KeyValue TEXT,
    Name TEXT,
    ReportingFrequency TEXT,
    ScheduleName TEXT,
    Units TEXT
);
"""


def _complete_entries(facts: ModelFacts) -> list[tuple[bool, str, str, str]]:
    """Every (is meter, key, name, frequency) the facts need, as EnergyPlus writes them (keys upper-cased)."""
    entries: list[tuple[bool, str, str, str]] = []
    for requirement in RESULTS_REQUIREMENTS:
        for expected in requirement.expected(facts):
            if requirement.kind == "meter":
                entries.append((True, "", expected, "Hourly"))
            else:
                entries.append((False, expected.upper(), requirement.item, "Hourly"))
    return entries


def _database(path: Path, entries: list[tuple[bool, str, str, str]]) -> Path:
    with sqlite3.connect(path) as conn:
        conn.executescript(_DDL)
        conn.executemany(
            "INSERT INTO ReportDataDictionary(IsMeter, Type, IndexGroup, TimestepType, KeyValue, Name, "
            "ReportingFrequency, ScheduleName, Units) VALUES (?, 'Sum', 'Zone', 'Zone', ?, ?, ?, NULL, 'J')",
            [(int(m), None if m else k, n, f) for m, k, n, f in entries],
        )
    conn.close()
    return path


def _check(tmp_path: Path, entries: list[tuple[bool, str, str, str]], facts: ModelFacts = FACTS) -> tuple[str, ...]:
    with SQLResult(_database(tmp_path / "eplusout.sql", entries)) as sql:
        return tuple(r.item for r in check_results(sql, facts))


def test_complete_results_miss_nothing(tmp_path: Path) -> None:
    assert _check(tmp_path, _complete_entries(FACTS)) == ()


def test_each_removed_output_is_named(tmp_path: Path) -> None:
    removed = {
        "Zone Mechanical Ventilation Standard Density Volume Flow Rate",
        "Fan Air Mass Flow Rate",
        "Heating:NaturalGas",
    }
    entries = [e for e in _complete_entries(FACTS) if e[2] not in removed]
    assert _check(tmp_path, entries) == (
        "Fan Air Mass Flow Rate",
        "Zone Mechanical Ventilation Standard Density Volume Flow Rate",
        "Heating:<fuel>",
    )


def test_one_missing_key_is_enough(tmp_path: Path) -> None:
    entries = [
        e
        for e in _complete_entries(FACTS)
        if not (e[2] == "Zone Air System Sensible Heating Energy" and e[1] == "CORE")
    ]
    assert _check(tmp_path, entries) == ("Zone Air System Sensible Heating Energy",)


def test_wrong_frequency_does_not_count(tmp_path: Path) -> None:
    entries = [
        (m, k, n, "Monthly" if n == "Site Outdoor Air Drybulb Temperature" else f)
        for m, k, n, f in _complete_entries(FACTS)
    ]
    assert _check(tmp_path, entries) == ("Site Outdoor Air Drybulb Temperature",)


def test_items_that_do_not_apply_are_not_required(tmp_path: Path) -> None:
    facts = ModelFacts(zones=("Core",), end_use_fuels=(("Heating", "DistrictHeatingWater"),))
    by_item = {r.item: r for r in RESULTS_REQUIREMENTS}
    for item in (
        "Site Mains Water Temperature",
        "Water Use Equipment Hot Water Volume",
        "Fan Electricity Energy",
        "Fans:Electricity",
        "Pumps:Electricity",
        "Cooling:<fuel>",
    ):
        assert not by_item[item].applies_to(facts)
    assert by_item["Site Outdoor Air Drybulb Temperature"].applies_to(facts)
    assert _check(tmp_path, _complete_entries(facts), facts) == ()


def test_mechanical_ventilation_is_needed_only_for_served_zones(tmp_path: Path) -> None:
    facts = ModelFacts(zones=("Core", "Attic"), served_zones=("Core",))
    by_item = {r.item: r for r in RESULTS_REQUIREMENTS}
    assert by_item["Zone Mechanical Ventilation Standard Density Volume Flow Rate"].expected(facts) == ("Core",)
    assert by_item["Zone Air System Sensible Heating Energy"].expected(facts) == ("Core", "Attic")
    assert _check(tmp_path, _complete_entries(facts), facts) == ()


def test_empty_results_name_every_applicable_item(tmp_path: Path) -> None:
    facts = ModelFacts(zones=("Core",))
    assert _check(tmp_path, [], facts) == (
        "Zone Air System Sensible Heating Energy",
        "Zone Air System Sensible Cooling Energy",
        "Site Outdoor Air Drybulb Temperature",
        "Zone Mechanical Ventilation Standard Density Volume Flow Rate",
    )


def test_missing_results_error_carries_the_idf_text(tmp_path: Path) -> None:
    entries = [e for e in _complete_entries(FACTS) if e[2] not in {"Fan Electricity Energy", "Heating:Electricity"}]
    with SQLResult(_database(tmp_path / "eplusout.sql", entries)) as sql:
        missing = check_results(sql, FACTS)
    error = MissingResults("eplusout.sql", [text for r in missing for text in r.idf_objects(FACTS)])
    message = str(error)
    assert "Output:Variable,*,Fan Electricity Energy,Hourly;" in message
    assert "Output:Meter,Heating:Electricity,Hourly;" in message
    assert "simulate=True" in message


# --- The committed EnergyPlus fixtures ---------------------------------------------------------


def _fixture_sql(name: str) -> Path:
    path = FIXTURES / name
    assert path.is_file(), f"{path.relative_to(ROOT)} is a committed fixture (T028, tests/fixtures/regenerate.py)"
    return path


def _zone_names(path: Path) -> tuple[str, ...]:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        rows: list[tuple[str]] = conn.execute("SELECT ZoneName FROM Zones ORDER BY ZoneIndex").fetchall()
    conn.close()
    return tuple(row[0] for row in rows)


def test_fixture_results_meet_the_zone_and_site_requirements() -> None:
    path = _fixture_sql("three_zone.sql")
    facts = ModelFacts(zones=_zone_names(path))
    with SQLResult(path) as sql:
        assert check_results(sql, facts) == ()


def test_fixture_with_outputs_removed_names_each_one(tmp_path: Path) -> None:
    source = _fixture_sql("three_zone.sql")
    path = tmp_path / "three_zone.sql"
    shutil.copyfile(source, path)
    facts = ModelFacts(zones=_zone_names(path))
    removed = ("Zone Air System Sensible Cooling Energy", "Site Outdoor Air Drybulb Temperature")
    with sqlite3.connect(path) as conn:
        conn.executemany("DELETE FROM ReportDataDictionary WHERE Name = ?", [(name,) for name in removed])
    conn.close()
    with SQLResult(path) as sql:
        missing: tuple[ResultRequirement, ...] = check_results(sql, facts)
    assert tuple(r.item for r in missing) == removed
    assert [r.idf_text for r in missing] == [f"Output:Variable,*,{name},Hourly;" for name in removed]
