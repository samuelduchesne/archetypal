"""End-to-end tests of `reduce` (spec 002, T042): US1 acceptance scenarios 1, 2 and 4, FR-029, quickstart 2 and 3.

Fixture reductions come from the session-scoped `reduced` fixture of `tests/conftest.py`, so each
fixture is reduced once per test session; the reproducibility test reduces again on purpose.
"""

from __future__ import annotations

import dataclasses
import json
import math
import os
import shutil
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from epinterface.sbem.archetype import Archetype
from idfkit import load_idf, new_document
from idfkit.simulation import SQLResult
from idfkit.versioned import IDFDocumentV9_6, as_version

import archetypal
from archetypal.errors import (
    InputError,
    MissingResults,
    ModelResultsMismatch,
    NoConditionedZones,
    ReductionError,
    UnsupportedEnergyPlusVersion,
)
from archetypal.reduction import RESULTS_REQUIREMENTS, Reduction, reduce, schedule_compact
from archetypal.reduction.options import Layout, ReductionOptions
from archetypal.reduction.requirements import add_missing_outputs, single_run_facts
from archetypal.reduction.sources import model_facts

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator

    from archetypal.reduction.inventory import ZoneRecord
    from archetypal.reduction.sources import SourceData

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
WEATHER = ROOT / "tests" / "fixtures" / "weather" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
FIXTURES = ("three_zone", "ten_zone_multipliers", "bar_building")


def _paths(fixture: str) -> tuple[Path, Path]:
    return MODELS / f"{fixture}.idf", MODELS / f"{fixture}.sql"


@pytest.fixture
def in_tmp(tmp_path: Path) -> Iterator[Path]:
    """Run the test from an empty directory, to check that nothing is written there."""
    cwd = Path.cwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(cwd)


# --- the public names (T061) -----------------------------------------------------------------------


def test_public_names() -> None:
    assert archetypal.reduce is reduce
    assert archetypal.Layout is Layout
    assert archetypal.ReductionOptions is ReductionOptions
    assert archetypal.MissingResults is MissingResults
    assert archetypal.NoConditionedZones is NoConditionedZones
    assert {"reduce", "Layout", "ReductionOptions"} <= set(archetypal.__all__)
    import archetypal.reduction as package  # noqa: PLC0415

    assert set(package.__all__) == {"RESULTS_REQUIREMENTS", "Reduction", "merge", "reduce", "schedule_compact"}
    assert RESULTS_REQUIREMENTS
    assert callable(schedule_compact)


# --- acceptance scenario 1: shares and accounting ---------------------------------------------------


@pytest.mark.parametrize("fixture", FIXTURES)
def test_shares_sum_to_one_and_every_zone_is_accounted_for(
    fixture: str, reduced: Callable[..., Reduction], detailed: Callable[[str], Any]
) -> None:
    report = reduced(fixture).report
    sources, zones, _ = detailed(fixture)
    assert math.fsum(g.floor_area_share for g in report.groups) == pytest.approx(1.0, abs=1e-12)
    grouped = [m.zone for g in report.groups for m in g.members]
    excluded = [z.zone for z in report.excluded_zones]
    assert sorted(grouped + excluded) == sorted(sources.facts.zones)
    assert len(set(grouped + excluded)) == len(grouped) + len(excluded)
    assert all(z.reason for z in report.excluded_zones)
    roles = {z.zone.name: z.role for z in zones}
    assert all(roles[z.zone] == z.role for z in report.excluded_zones)
    assert all(roles[m] == "conditioned" for m in grouped)


def test_plenums_attic_and_basement_are_excluded_with_their_role(reduced: Callable[..., Reduction]) -> None:
    excluded = {z.zone: z for z in reduced("ten_zone_multipliers").report.excluded_zones}
    assert excluded["Attic"].role == "attic"
    assert excluded["Basement"].role == "basement"
    assert excluded["G_Plenum"].role == "excluded"
    assert excluded["Typical_Plenum"].role == "excluded"
    assert excluded["Typical_Plenum"].multiplier == 10
    # The attic's roof went to the top floor (FR-013).
    assert excluded["Attic"].envelope
    assert {a.target_zone for a in excluded["Attic"].envelope} <= {"Top_Core", "Top_Perimeter"}


def test_archetype_has_one_zone_group_per_report_group(reduced: Callable[..., Reduction]) -> None:
    reduction = reduced("ten_zone_multipliers")
    names = [g.Name for g in reduction.archetype.Groups]
    assert sorted(names) == sorted(g.name for g in reduction.report.groups)
    shares = {g.Name: g.FloorAreaShare for g in reduction.archetype.Groups}
    for group in reduction.report.groups:
        assert shares[group.name] == pytest.approx(group.floor_area_share, abs=1e-12)
    assert reduction.archetype.Geometry.Storeys == 12


# --- acceptance scenario 2: different loads and schedules stay apart -------------------------------


def test_spaces_with_different_loads_and_schedules_are_in_different_groups(
    reduced: Callable[..., Reduction],
) -> None:
    report = reduced("three_zone").report
    by_zone = {m.zone: g.key for g in report.groups for m in g.members}
    # The conference room (south) and the offices (north, core) differ in loads and schedules.
    assert by_zone["South_Perimeter"][0] != by_zone["North_Perimeter"][0]
    assert by_zone["North_Perimeter"] != by_zone["Core"]
    assert len(report.groups) == 3


def test_user_space_uses_keep_operating_rooms_and_corridors_apart(reduced: Callable[..., Reduction]) -> None:
    mapping = {"North_Perimeter": "operating_room", "South_Perimeter": "corridor", "Core": "corridor"}
    options = ReductionOptions(space_use_mapping=mapping, small_group_threshold=0.0)
    report = reduced("three_zone", options).report
    keys = {m.zone: g.key for g in report.groups for m in g.members}
    assert keys["North_Perimeter"] == ("operating_room", "perimeter")
    assert keys["South_Perimeter"] == ("corridor", "perimeter")
    assert keys["Core"] == ("corridor", "core")
    assert all(m.space_use_source == "user" for g in report.groups for m in g.members)


# --- acceptance scenario 4 and quickstart 2: reproducible files -------------------------------------


def test_quickstart_2_write_and_reduce_again_byte_identical(reduced: Callable[..., Reduction], tmp_path: Path) -> None:
    reduction = reduced("ten_zone_multipliers")
    archetype_path, report_path = reduction.write(tmp_path / "out", "ten_zone")
    assert archetype_path == tmp_path / "out" / "ten_zone.sbem.json"
    assert report_path == tmp_path / "out" / "ten_zone.report.json"
    # The archetype loads with epinterface alone.
    assert Archetype.model_validate_json(archetype_path.read_bytes()) == reduction.archetype
    report = json.loads(report_path.read_bytes())
    assert math.fsum(g["floor_area_share"] for g in report["groups"]) == pytest.approx(1.0, abs=1e-12)
    assert "G_Plenum" in {z["zone"] for z in report["excluded_zones"]}


def test_two_reductions_are_byte_identical(reduced: Callable[..., Reduction], tmp_path: Path) -> None:
    model, results = _paths("three_zone")
    first = reduced("three_zone")
    second = reduce(model, results)
    assert second.archetype == first.archetype
    assert second.report == first.report
    a = first.write(tmp_path / "a", "three_zone")
    b = second.write(tmp_path / "b", "three_zone")
    assert [p.read_bytes() for p in a] == [p.read_bytes() for p in b]


def test_hourly_series_are_read_in_one_scan(monkeypatch: pytest.MonkeyPatch) -> None:
    # Each read scans all of ReportData, which is most of a read's cost in a large results file.
    model, results = _paths("three_zone")
    reads: list[int] = []
    read = SQLResult.get_timeseries_many

    def counted(self: SQLResult, series: Any, environment: Any = None) -> Any:
        specs = list(series)
        reads.append(len(specs))
        return read(self, specs, environment)

    monkeypatch.setattr(SQLResult, "get_timeseries_many", counted)
    reduce(model, results)
    assert len(reads) == 1
    assert reads[0] > 0


def test_open_results_and_a_document_give_the_same_reduction(reduced: Callable[..., Reduction]) -> None:
    model, results = _paths("bar_building")
    sql = SQLResult(results)
    try:
        reduction = reduce(load_idf(model), sql)
        # The caller's results stay open.
        assert sql.list_variables()
    finally:
        sql.close()
    expected = reduced("bar_building")
    assert reduction.archetype.model_copy(update={"Name": expected.archetype.Name}) == expected.archetype
    assert reduction.report.groups == expected.report.groups
    # A document given without its file is hashed from the IDF text idfkit writes.
    assert reduction.report.reproducibility.model_sha256 != expected.report.reproducibility.model_sha256


def test_report_records_inputs_and_options(reduced: Callable[..., Reduction]) -> None:
    block = reduced("three_zone").report.reproducibility
    assert block.energyplus == "24.2.0"
    assert block.options == ReductionOptions()
    assert block.weather_sha256 is None
    assert len(block.model_sha256) == len(block.results_sha256) == 64


def test_write_refuses_to_overwrite_and_read_round_trips(reduced: Callable[..., Reduction], tmp_path: Path) -> None:
    reduction = reduced("bar_building")
    archetype_path, report_path = reduction.write(tmp_path, "bar")
    with pytest.raises(InputError):
        reduction.write(tmp_path, "bar")
    reduction.write(tmp_path, "bar", overwrite=True)
    again = Reduction.read(archetype_path)
    assert again.archetype == reduction.archetype
    assert again.report == reduction.report
    assert Reduction.read(archetype_path, report_path) == again
    report_path.unlink()
    with pytest.raises(ReductionError, match="no reduction report"):
        Reduction.read(archetype_path)


def test_report_lists_what_the_archetype_does_not_hold(reduced: Callable[..., Reduction]) -> None:
    features = {n.feature for n in reduced("bar_building").report.not_represented}
    assert {"Daylighting controls", "Exterior lights"} <= features
    ten = reduced("ten_zone_multipliers").report
    by_feature = {n.feature: n for n in ten.not_represented}
    allocated = by_feature["Building hot water allocated to zones"]
    assert allocated.folded_into is not None
    assert allocated.affected_groups
    # Pump energy in hours without delivery is listed and counted in unattributed_energy (FR-022).
    standby = [n for n in ten.not_represented if n.feature.startswith("Unattributed")]
    assert math.fsum(n.magnitude or 0.0 for n in standby) == pytest.approx(math.fsum(ten.unattributed_energy.values()))


# --- FR-029 and quickstart 3: refusals write nothing ------------------------------------------------


def test_quickstart_3_missing_results_are_named(in_tmp: Path) -> None:
    model, _ = _paths("three_zone")
    with pytest.raises(MissingResults) as caught:
        reduce(model)
    assert caught.value.missing
    assert all(item.startswith("Output:") and item.endswith(";") for item in caught.value.missing)
    assert "simulate=True" in str(caught.value)
    assert list(in_tmp.iterdir()) == []


def test_design_day_results_are_refused(in_tmp: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    """Results of a run without its weather-file run period name the SimulationControl switch."""
    model, results = _paths("three_zone")
    design_days = tmp_path_factory.mktemp("results") / "design_days.sql"
    shutil.copyfile(results, design_days)
    with sqlite3.connect(design_days) as connection:
        connection.execute("UPDATE EnvironmentPeriods SET EnvironmentType = 1")
    connection.close()
    with pytest.raises(MissingResults) as caught:
        reduce(model, design_days)
    assert any("Run Simulation for Weather File Run Periods" in item for item in caught.value.missing)
    assert list(in_tmp.iterdir()) == []


def test_single_run_turns_on_the_weather_file_run_period() -> None:
    """The single run's copy of a model set to run only its design days runs its run period."""
    model, _ = _paths("three_zone")
    doc = as_version(load_idf(model), since="22.1")
    for control in doc["SimulationControl"]:
        control.run_simulation_for_weather_file_run_periods = "No"
    add_missing_outputs(doc, single_run_facts(model_facts(doc, ())))
    controls = list(doc["SimulationControl"])
    assert controls
    assert all(str(c.run_simulation_for_weather_file_run_periods) == "Yes" for c in controls)


def test_simulate_needs_weather(in_tmp: Path) -> None:
    model, _ = _paths("three_zone")
    with pytest.raises(ReductionError, match="weather"):
        reduce(model, simulate=True)
    assert list(in_tmp.iterdir()) == []


def test_mismatched_results_are_refused(in_tmp: Path, tmp_path_factory: pytest.TempPathFactory) -> None:
    model, results = _paths("three_zone")
    other = tmp_path_factory.mktemp("results") / "other.sql"
    shutil.copyfile(results, other)
    with sqlite3.connect(other) as connection:
        connection.execute("UPDATE Zones SET ZoneName = 'OTHER' WHERE ZoneIndex = 1")
    connection.close()
    with pytest.raises(ModelResultsMismatch, match="OTHER"):
        reduce(model, other)
    assert list(in_tmp.iterdir()) == []


def test_unsupported_version_is_refused(in_tmp: Path) -> None:
    _, results = _paths("three_zone")
    with pytest.raises(UnsupportedEnergyPlusVersion):
        reduce(new_document(IDFDocumentV9_6), results)
    assert list(in_tmp.iterdir()) == []


def test_no_conditioned_zones_is_refused(in_tmp: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import archetypal.reduction as package  # noqa: PLC0415

    real = package.build_inventory

    def unconditioned(sources: SourceData, evaluate: Any = None) -> tuple[ZoneRecord, ...]:
        records = real(sources, evaluate)
        return tuple(
            dataclasses.replace(r, thermostat=None, delivered={"heating": 0.0, "cooling": 0.0}) for r in records
        )

    # A zone with no thermostat and no delivered energy is not conditioned (R8).
    monkeypatch.setattr(package, "build_inventory", unconditioned)
    model, results = _paths("bar_building")
    with pytest.raises(NoConditionedZones):
        reduce(model, results)
    assert list(in_tmp.iterdir()) == []
