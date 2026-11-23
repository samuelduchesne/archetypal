"""Tests for loading and validating the model and its results (spec 002, T016; data-model.md, SourceData)."""

from __future__ import annotations

import hashlib
import shutil
import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest
from idfkit import load_idf, new_document
from idfkit.simulation import SQLResult
from idfkit.simulation.parsers.sql import TabularRow, VariableInfo
from idfkit.versioned import IDFDocumentV9_6

from archetypal.errors import MissingResults, ModelResultsMismatch, ReductionError, UnsupportedEnergyPlusVersion
from archetypal.reduction.requirements import check_results
from archetypal.reduction.sources import RunPeriodInfo, SourceData, end_use_fuels, load_sources, model_facts

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
WEATHER = ROOT / "tests" / "fixtures" / "weather" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
THREE_IDF = MODELS / "three_zone.idf"
THREE_SQL = MODELS / "three_zone.sql"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _results_copy(tmp_path: Path, *statements: str, source: Path = THREE_SQL) -> Path:
    path = tmp_path / source.name
    shutil.copyfile(source, path)
    with sqlite3.connect(path) as conn:
        for statement in statements:
            conn.execute(statement)
    conn.close()
    return path


@pytest.fixture(scope="module")
def three_zone() -> SourceData:
    return load_sources(THREE_IDF, THREE_SQL, weather=WEATHER)


# --- Loading -----------------------------------------------------------------------------------


def test_load_from_paths(three_zone: SourceData) -> None:
    assert three_zone.energyplus_version == (24, 2, 0)
    assert isinstance(three_zone.results, SQLResult)
    assert [zone.name for zone in three_zone.model.zones] == ["Core", "North_Perimeter", "South_Perimeter"]
    assert three_zone.model_path == THREE_IDF
    assert three_zone.results_path == THREE_SQL.resolve()


def test_sha256_of_model_results_and_weather(three_zone: SourceData) -> None:
    assert three_zone.model_sha256 == _sha256(THREE_IDF)
    assert three_zone.results_sha256 == _sha256(THREE_SQL)
    assert three_zone.weather_sha256 == _sha256(WEATHER)


def test_weather_is_optional() -> None:
    sources = load_sources(THREE_IDF, THREE_SQL)
    assert sources.weather_sha256 is None


def test_load_from_document_and_open_results() -> None:
    doc = load_idf(THREE_IDF)
    with SQLResult(THREE_SQL) as sql:
        sources = load_sources(doc, sql)
        assert sources.results is sql
    assert sources.model is doc
    assert sources.model_path == THREE_IDF
    # A document is hashed as the IDF text idfkit writes for it, not as the file it came from.
    assert len(sources.model_sha256) == 64
    assert sources.model_sha256 == load_sources(load_idf(THREE_IDF), THREE_SQL).model_sha256
    assert sources.results_sha256 == _sha256(THREE_SQL)


def test_run_period(three_zone: SourceData) -> None:
    run_period = three_zone.run_period
    assert isinstance(run_period, RunPeriodInfo)
    assert run_period.name == "Annual"
    assert (run_period.begin.month, run_period.begin.day) == (1, 1)
    assert (run_period.end.month, run_period.end.day) == (12, 31)
    assert run_period.begin.year == run_period.year == run_period.calendar.year
    assert run_period.begin.strftime("%A") == run_period.start_weekday
    assert run_period.holidays == run_period.calendar.holidays
    assert all(isinstance(day, date) for day in run_period.holidays)


def test_run_period_defaults_without_a_run_period() -> None:
    info = RunPeriodInfo.from_document(new_document())
    assert info.name is None
    assert info.start_weekday == "Sunday"
    assert (info.begin, info.end) == (date(info.year, 1, 1), date(info.year, 12, 31))


# --- Model facts -------------------------------------------------------------------------------


def test_model_facts_three_zone(three_zone: SourceData) -> None:
    facts = three_zone.facts
    assert facts.zones == ("Core", "North_Perimeter", "South_Perimeter")
    assert facts.fans == ("Core PTAC Fan", "North_Perimeter PTAC Fan", "South_Perimeter PTAC Fan")
    assert facts.pumps == ()
    assert facts.zone_air_inlet_nodes == (
        "Core Supply Inlet",
        "North_Perimeter Supply Inlet",
        "South_Perimeter Supply Inlet",
    )
    assert facts.water_use_equipment == ()
    assert facts.end_use_fuels == (("Cooling", "Electricity"), ("Heating", "NaturalGas"))


def test_model_facts_ten_zone() -> None:
    doc = load_idf(MODELS / "ten_zone_multipliers.idf", since="22.1")
    with SQLResult(MODELS / "ten_zone_multipliers.sql") as sql:
        fuels = end_use_fuels(sql)
        assert fuels is not None
        facts = model_facts(doc, fuels)
        assert check_results(sql, facts) == ()
    assert fuels == (
        ("Cooling", "Electricity"),
        ("Heating", "Electricity"),
        ("Heating", "NaturalGas"),
        ("WaterSystems", "NaturalGas"),
    )
    assert set(facts.fans) == {"VAV Supply Fan", "Top_Perimeter PTHP Fan", "Top_Core PTHP Fan"}
    assert set(facts.pumps) == {"SHW Pump", "CHW Pump", "HW Pump"}
    assert set(facts.water_use_equipment) == {"Typical_Core Restroom Hot Water", "Building Hot Water"}
    assert len(facts.zones) == 10
    # Basement, plenums and attic have no equipment connections, so no mechanical ventilation.
    assert facts.served_zones == (
        "G_Perimeter",
        "G_Core",
        "Typical_Perimeter",
        "Typical_Core",
        "Top_Perimeter",
        "Top_Core",
    )


def test_model_facts_bar_building_has_district_fuels() -> None:
    sources = load_sources(MODELS / "bar_building.idf", MODELS / "bar_building.sql")
    assert sources.facts.fans == ()
    assert sources.facts.end_use_fuels == (("Cooling", "DistrictCooling"), ("Heating", "DistrictHeatingWater"))


@pytest.mark.parametrize("name", ["three_zone", "ten_zone_multipliers", "ten_zone_explicit", "bar_building"])
def test_committed_fixtures_load_and_meet_the_requirements(name: str) -> None:
    sources = load_sources(MODELS / f"{name}.idf", MODELS / f"{name}.sql", weather=WEATHER)
    try:
        assert check_results(sources.results, sources.facts) == ()
        assert sources.facts.served_zones is not None
    finally:
        sources.results.close()


def test_node_lists_are_expanded() -> None:
    doc = new_document()
    doc.zones.add("A")
    doc["NodeList"].add("A Inlets", nodes=[{"node_name": "A Inlet 1"}, {"node_name": "A Inlet 2"}])
    doc["ZoneHVAC:EquipmentConnections"].add(
        zone_name="A",
        zone_conditioning_equipment_list_name="A Equipment",
        zone_air_inlet_node_or_nodelist_name="a inlets",
        zone_air_node_name="A Air",
    )
    assert model_facts(doc, ()).zone_air_inlet_nodes == ("A Inlet 1", "A Inlet 2")


# --- Validation, in the order of data-model.md -------------------------------------------------


def test_older_document_is_refused() -> None:
    doc = new_document(IDFDocumentV9_6)
    with pytest.raises(UnsupportedEnergyPlusVersion) as caught:
        load_sources(doc, THREE_SQL)
    assert caught.value.version == "9.6"
    assert caught.value.supported[0] == "22.1"
    assert "idfkit.migration.migrate" in str(caught.value)


def test_older_document_is_refused_before_looking_at_results(tmp_path: Path) -> None:
    results = _results_copy(tmp_path, "UPDATE Zones SET ZoneName = 'OTHER' WHERE ZoneIndex = 1")
    with pytest.raises(UnsupportedEnergyPlusVersion):
        load_sources(new_document(IDFDocumentV9_6), results)


def test_older_results_are_refused(tmp_path: Path) -> None:
    results = _results_copy(
        tmp_path, "UPDATE Simulations SET EnergyPlusVersion = 'EnergyPlus, Version 9.6.0-f420c06a69'"
    )
    with pytest.raises(UnsupportedEnergyPlusVersion) as caught:
        load_sources(THREE_IDF, results)
    assert caught.value.version == "9.6"
    assert str(caught.value).startswith(str(results))


def test_model_and_results_versions_must_agree(tmp_path: Path) -> None:
    results = _results_copy(
        tmp_path, "UPDATE Simulations SET EnergyPlusVersion = 'EnergyPlus, Version 23.1.0-87ed9199d4'"
    )
    with pytest.raises(ModelResultsMismatch) as caught:
        load_sources(THREE_IDF, results)
    assert any("24.2" in d and "23.1" in d for d in caught.value.differences)


def test_no_results_means_missing_results() -> None:
    with pytest.raises(MissingResults) as caught:
        load_sources(THREE_IDF, None)
    assert "Output:Variable,*,Zone Air System Sensible Heating Energy,Hourly;" in caught.value.missing
    assert "Output:Meter,Heating:<fuel>,Hourly;" not in caught.value.missing


def test_removed_outputs_are_named(tmp_path: Path) -> None:
    results = _results_copy(
        tmp_path,
        "DELETE FROM ReportDataDictionary WHERE Name IN ('Fan Air Mass Flow Rate', 'Heating:NaturalGas')",
    )
    with pytest.raises(MissingResults) as caught:
        load_sources(THREE_IDF, results)
    assert caught.value.missing == (
        "Output:Variable,*,Fan Air Mass Flow Rate,Hourly;",
        "Output:Meter,Heating:NaturalGas,Hourly;",
    )


def test_missing_tabular_reports_are_named(tmp_path: Path) -> None:
    results = _results_copy(tmp_path, "DELETE FROM TabularData")
    with pytest.raises(MissingResults) as caught:
        load_sources(THREE_IDF, results)
    assert "Output:Table:SummaryReports,AllSummary;" in caught.value.missing


def _three_zone_with_run_period(tmp_path: Path, **fields: object) -> Path:
    doc = load_idf(THREE_IDF)
    for run_period in doc.run_periods:
        for key, value in fields.items():
            setattr(run_period, key, value)
    path = tmp_path / "three_zone.idf"
    doc.save(path)
    return path


def test_a_run_period_shorter_than_a_year_is_refused(tmp_path: Path) -> None:
    model = _three_zone_with_run_period(tmp_path, end_month=6, end_day_of_month=30)
    with pytest.raises(ReductionError, match="one whole calendar year"):
        load_sources(model, THREE_SQL)


def test_a_run_period_across_1_january_is_refused(tmp_path: Path) -> None:
    model = _three_zone_with_run_period(tmp_path, begin_month=7, end_month=6, end_day_of_month=30)
    with pytest.raises(ReductionError, match="across 1 January"):
        load_sources(model, THREE_SQL)


def test_results_with_two_weather_file_run_periods_are_refused(tmp_path: Path) -> None:
    results = _results_copy(
        tmp_path,
        "INSERT INTO EnvironmentPeriods (EnvironmentPeriodIndex, SimulationIndex, EnvironmentName, EnvironmentType) "
        "SELECT MAX(EnvironmentPeriodIndex) + 1, 1, 'SECOND RUN', 3 FROM EnvironmentPeriods",
    )
    with pytest.raises(ReductionError, match="2 weather-file run periods"):
        load_sources(THREE_IDF, results)


def test_a_file_that_is_not_sqlite_is_a_reduction_error(tmp_path: Path) -> None:
    results = tmp_path / "eplusout.sql"
    results.write_text("not a database")
    with pytest.raises(ReductionError, match="cannot be read as EnergyPlus SQLite results") as caught:
        load_sources(THREE_IDF, results)
    assert str(results.resolve()) in str(caught.value)


# `?` is not allowed in a Windows file name; the other URI characters are.
URI_FOLDER = "run #1 %41" if sys.platform == "win32" else "run #1 ?a=%41"


def test_a_results_path_with_uri_characters_opens_that_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    folder = tmp_path / URI_FOLDER
    folder.mkdir()
    results = folder / "eplusout.sql"
    shutil.copyfile(THREE_SQL, results)
    monkeypatch.chdir(tmp_path)
    sources = load_sources(THREE_IDF, Path(URI_FOLDER) / "eplusout.sql")
    sources.results.close()
    assert sorted(p.name for p in tmp_path.iterdir()) == [URI_FOLDER]


def test_a_model_with_hvac_templates_is_refused() -> None:
    doc = load_idf(THREE_IDF)
    doc.add("HVACTemplate:Thermostat", "Office", validate=False, constant_heating_setpoint=21.0)
    with pytest.raises(ReductionError, match="HVACTemplate:Thermostat"):
        load_sources(doc, THREE_SQL)


def test_results_without_the_envelope_summary_are_missing_results(tmp_path: Path) -> None:
    results = _results_copy(
        tmp_path,
        "DELETE FROM TabularData WHERE ReportNameIndex IN "
        "(SELECT StringIndex FROM Strings WHERE Value = 'EnvelopeSummary')",
    )
    with pytest.raises(MissingResults) as caught:
        load_sources(THREE_IDF, results)
    assert "Output:Table:SummaryReports,AllSummary;" in caught.value.missing


def test_zone_names_must_agree(tmp_path: Path) -> None:
    results = _results_copy(tmp_path, "UPDATE Zones SET ZoneName = 'ATTIC' WHERE ZoneName = 'CORE'")
    with pytest.raises(ModelResultsMismatch) as caught:
        load_sources(THREE_IDF, results)
    assert caught.value.differences == ("zone ATTIC is only in the results", "zone Core is only in the model")
    assert isinstance(caught.value, ReductionError)


def test_missing_outputs_are_reported_before_zone_names(tmp_path: Path) -> None:
    results = _results_copy(
        tmp_path,
        "UPDATE Zones SET ZoneName = 'ATTIC' WHERE ZoneName = 'CORE'",
        "DELETE FROM ReportDataDictionary WHERE Name = 'Site Outdoor Air Drybulb Temperature'",
    )
    with pytest.raises(MissingResults):
        load_sources(THREE_IDF, results)


def test_end_use_fuels_keeps_hourly_metered_fuels_the_table_rounds_to_zero() -> None:
    class _Results:
        def get_tabular_data(self, report_name: str, table_name: str, report_for: str) -> list[TabularRow]:
            row = "AnnualBuildingUtilityPerformanceSummary", report_for, table_name
            return [
                TabularRow(*row, "Heating", "Natural Gas", "GJ", "12.00"),
                # Under 5 MJ a year: EnergyPlus prints 0.00 GJ.
                TabularRow(*row, "Heating", "Propane", "GJ", "0.00"),
                TabularRow(*row, "Cooling", "Electricity", "GJ", "0.00"),
            ]

        def list_variables(self) -> list[VariableInfo]:
            return [
                VariableInfo("Heating:Propane", "", "Hourly", "J", True, "Sum"),
                VariableInfo("Cooling:Electricity", "", "Monthly", "J", True, "Sum"),
                VariableInfo("WaterSystems:Water", "", "Hourly", "m3", True, "Sum"),
            ]

    fuels = end_use_fuels(_Results())  # pyright: ignore[reportArgumentType]
    assert fuels == (("Heating", "NaturalGas"), ("Heating", "Propane"))
