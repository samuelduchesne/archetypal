"""Tests for the typed rows of EnergyPlus's static SQLite tables (spec 002, T014; research R18)."""

from __future__ import annotations

import ast
import shutil
import sqlite3
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from idfkit.simulation import SQLResult

from archetypal.reduction import _sql_tables as tables
from archetypal.reduction._sql_tables import (
    ConstructionLayerRow,
    ConstructionRow,
    EnvironmentPeriodRow,
    MaterialRow,
    NominalInfiltrationRow,
    NominalLoadRow,
    NominalVentilationRow,
    SimulationRow,
    SQLTableError,
    SurfaceRow,
    ZoneRow,
)

if TYPE_CHECKING:
    from collections.abc import Callable

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
THREE_ZONE = MODELS / "three_zone.sql"
TEN_ZONE = MODELS / "ten_zone_multipliers.sql"


def _count(path: Path, table: str) -> int:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
        (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()  # noqa: S608 - constant table names
    conn.close()
    return int(count)


@pytest.fixture
def ten_zone() -> SQLResult:
    return SQLResult(TEN_ZONE)


# --- One typed row per record -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("reader", "table", "row_type"),
    [
        (tables.read_zones, "Zones", ZoneRow),
        (tables.read_surfaces, "Surfaces", SurfaceRow),
        (tables.read_constructions, "Constructions", ConstructionRow),
        (tables.read_construction_layers, "ConstructionLayers", ConstructionLayerRow),
        (tables.read_materials, "Materials", MaterialRow),
        (tables.read_nominal_infiltration, "NominalInfiltration", NominalInfiltrationRow),
        (tables.read_nominal_ventilation, "NominalVentilation", NominalVentilationRow),
        (tables.read_simulations, "Simulations", SimulationRow),
        (tables.read_environment_periods, "EnvironmentPeriods", EnvironmentPeriodRow),
    ],
)
def test_one_row_per_record(
    reader: Callable[[SQLResult], tuple[object, ...]], table: str, row_type: type, ten_zone: SQLResult
) -> None:
    with ten_zone as sql:
        rows = reader(sql)
    assert isinstance(rows, tuple)
    assert len(rows) == _count(TEN_ZONE, table)
    assert all(type(row) is row_type for row in rows)


def test_nominal_loads_cover_every_gain_table(ten_zone: SQLResult) -> None:
    with ten_zone as sql:
        rows = tables.read_nominal_loads(sql)
    expected = sum(_count(TEN_ZONE, table) for table in tables.NOMINAL_LOAD_TABLES.values())
    assert len(rows) == expected
    assert {row.kind for row in rows} == {"people", "lights", "electric"}
    assert all(type(row) is NominalLoadRow for row in rows)
    # Ordered by kind (in NOMINAL_LOAD_TABLES order), then by the table's index.
    kinds = list(tables.NOMINAL_LOAD_TABLES)
    assert [kinds.index(row.kind) for row in rows] == sorted(kinds.index(row.kind) for row in rows)


def test_rows_are_frozen(ten_zone: SQLResult) -> None:
    with ten_zone as sql:
        zone = tables.read_zones(sql)[0]
    with pytest.raises(FrozenInstanceError):
        zone.name = "X"  # type: ignore[misc]


# --- Types converted and checked at the boundary ----------------------------------------------


def test_zone_rows(ten_zone: SQLResult) -> None:
    with ten_zone as sql:
        zones = {zone.name: zone for zone in tables.read_zones(sql)}
    assert next(iter(zones)) == "BASEMENT"
    typical = zones["TYPICAL_PERIMETER"]
    assert (typical.multiplier, typical.list_multiplier) == (10, 1)
    assert isinstance(typical.multiplier, int)
    core = zones["TYPICAL_CORE"]
    assert (core.multiplier, core.list_multiplier) == (5, 2)
    basement = zones["BASEMENT"]
    assert basement.floor_area == pytest.approx(600.0)
    assert basement.volume == pytest.approx(1800.0)
    assert basement.minimum_z == pytest.approx(-3.0)
    assert basement.is_part_of_total_area is False
    assert zones["G_PERIMETER"].is_part_of_total_area is True
    for zone in zones.values():
        for field in fields(zone):
            value = getattr(zone, field.name)
            assert not isinstance(value, bool) or field.name == "is_part_of_total_area"


def test_surface_and_construction_rows(ten_zone: SQLResult) -> None:
    with ten_zone as sql:
        surfaces = tables.read_surfaces(sql)
        constructions = {c.index: c for c in tables.read_constructions(sql)}
        layers = tables.read_construction_layers(sql)
        materials = {m.index: m for m in tables.read_materials(sql)}
    wall = surfaces[0]
    assert wall.name == "BASEMENT_WALL_01"
    assert wall.class_name == "Wall"
    assert wall.area == pytest.approx(60.0)
    assert wall.azimuth == pytest.approx(270.0)
    assert wall.tilt == pytest.approx(90.0)
    assert wall.heat_transfer is True
    assert wall.zone_index == 1
    assert wall.construction_index is not None
    assert constructions[wall.construction_index].name == "BASEMENT WALL"
    assert all(isinstance(c.type_is_window, bool) for c in constructions.values())
    exterior = next(c for c in constructions.values() if c.name == "EXTERIOR WALL")
    exterior_layers = sorted(
        (layer for layer in layers if layer.construction_index == exterior.index), key=lambda x: x.layer_index
    )
    assert len(exterior_layers) == exterior.total_layers
    brick = materials[exterior_layers[0].material_index]
    assert (brick.name, brick.conductivity, brick.density, brick.specific_heat, brick.thickness) == (
        "Brick",
        pytest.approx(0.89),
        pytest.approx(1920.0),
        pytest.approx(790.0),
        pytest.approx(0.1016),
    )


def test_nominal_rows(ten_zone: SQLResult) -> None:
    with ten_zone as sql:
        loads = tables.read_nominal_loads(sql)
        infiltration = tables.read_nominal_infiltration(sql)
    people = next(row for row in loads if row.kind == "people")
    # NumberOfPeople is declared INTEGER but holds a real number: converted to float, not truncated.
    assert people.design_level == pytest.approx(22.8)
    assert isinstance(people.design_level, float)
    assert people.schedule_name == "OFFICE OCCUPANCY"
    assert people.fraction_radiant == pytest.approx(0.3)
    assert people.fraction_latent is None
    lights = next(row for row in loads if row.kind == "lights")
    assert lights.design_level == pytest.approx(4560.0)
    assert lights.fraction_radiant == pytest.approx(0.42)
    assert lights.fraction_return_air == pytest.approx(0.0)
    assert lights.fraction_latent == 0.0
    assert lights.zone_index == 2
    assert infiltration[0].object_name == "G_PERIMETER INFILTRATION"
    assert infiltration[0].design_level == pytest.approx(0.09)
    assert infiltration[0].schedule_name is not None


def test_simulation_and_environment_rows(ten_zone: SQLResult) -> None:
    with ten_zone as sql:
        (simulation,) = tables.read_simulations(sql)
        periods = tables.read_environment_periods(sql)
    assert simulation.energyplus_version == (24, 2, 0)
    assert simulation.version_text.startswith("EnergyPlus, Version 24.2.0")
    assert simulation.timesteps_per_hour == 4
    assert isinstance(simulation.completed, bool)
    assert [(p.name, p.environment_type) for p in periods] == [("ANNUAL", 3)]


def test_every_fixture_reads(tmp_path: Path) -> None:
    for path in sorted(MODELS.glob("*.sql")):
        if path.stat().st_size > 20_000_000:  # the explicit ten-zone file is read in the integration tier
            continue
        with SQLResult(path) as sql:
            assert tables.read_zones(sql)
            assert tables.read_surfaces(sql)
            tables.read_nominal_loads(sql)
            tables.read_nominal_infiltration(sql)
            tables.read_nominal_ventilation(sql)
            assert tables.read_simulations(sql)[0].energyplus_version[:2] == (24, 2)


def test_database_path() -> None:
    with SQLResult(THREE_ZONE) as sql:
        assert tables.database_path(sql) == THREE_ZONE.resolve()


# --- A clear error on an unexpected column type ------------------------------------------------


def _copy(tmp_path: Path, statement: str) -> Path:
    path = tmp_path / "three_zone.sql"
    shutil.copyfile(THREE_ZONE, path)
    with sqlite3.connect(path) as conn:
        conn.execute(statement)
    conn.close()
    return path


def test_text_in_a_real_column_names_table_column_and_value(tmp_path: Path) -> None:
    path = _copy(tmp_path, "UPDATE Zones SET FloorArea = 'lots' WHERE ZoneIndex = 1")
    with SQLResult(path) as sql, pytest.raises(SQLTableError) as caught:
        tables.read_zones(sql)
    message = str(caught.value)
    assert "Zones" in message
    assert "FloorArea" in message
    assert "'lots'" in message
    assert caught.value.table == "Zones"
    assert caught.value.column == "FloorArea"


def test_null_in_a_required_column(tmp_path: Path) -> None:
    path = _copy(tmp_path, "UPDATE Zones SET ZoneName = NULL WHERE ZoneIndex = 2")
    with SQLResult(path) as sql, pytest.raises(SQLTableError, match="ZoneName"):
        tables.read_zones(sql)


def test_fractional_multiplier_is_refused(tmp_path: Path) -> None:
    path = _copy(tmp_path, "UPDATE Zones SET Multiplier = 2.5 WHERE ZoneIndex = 1")
    with SQLResult(path) as sql, pytest.raises(SQLTableError, match="Multiplier"):
        tables.read_zones(sql)


def test_missing_table_is_named(tmp_path: Path) -> None:
    path = _copy(tmp_path, "DROP TABLE NominalVentilation")
    with SQLResult(path) as sql, pytest.raises(SQLTableError, match="NominalVentilation"):
        tables.read_nominal_ventilation(sql)


def test_unparseable_version_is_refused(tmp_path: Path) -> None:
    path = _copy(tmp_path, "UPDATE Simulations SET EnergyPlusVersion = 'unknown'")
    with SQLResult(path) as sql, pytest.raises(SQLTableError, match="EnergyPlusVersion"):
        tables.read_simulations(sql)


# --- The only module that calls SQLResult.query (research R18, UP-7) ---------------------------


def test_only_sql_tables_calls_query() -> None:
    offenders: list[str] = []
    for path in sorted((ROOT / "src" / "archetypal").rglob("*.py")):
        if path.name == "_sql_tables.py":
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        offenders.extend(
            f"{path.relative_to(ROOT)}:{node.lineno}"
            for node in ast.walk(tree)
            if isinstance(node, ast.Attribute) and node.attr == "query"
        )
    assert offenders == []
