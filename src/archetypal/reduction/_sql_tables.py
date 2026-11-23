"""Typed rows of EnergyPlus's static SQLite tables (research R1, R18).

idfkit's `SQLResult.query` returns `list[tuple[object, ...]]`. This module is the only one in
archetypal that calls it: each table is read into frozen dataclasses whose values are converted
and checked here, at the boundary, so the rest of the package stays fully typed.

SQLite types are per value, not per column: `NominalPeople.NumberOfPeople` is declared
`INTEGER` but holds `22.8`, and `Simulations.Completed` holds the text `'FALSE'`. The readers
accept what EnergyPlus writes and refuse anything else with an `SQLTableError` naming the table,
the column and the value.

Removal condition (UP-7): once idfkit ships typed readers for these tables, archetypal uses
them and this module is deleted.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from idfkit.simulation import SQLResult

__all__ = [
    "NOMINAL_LOAD_TABLES",
    "ConstructionLayerRow",
    "ConstructionRow",
    "EnvironmentPeriodRow",
    "GainKind",
    "MaterialRow",
    "NominalInfiltrationRow",
    "NominalLoadRow",
    "NominalVentilationRow",
    "SQLTableError",
    "SimulationRow",
    "SurfaceRow",
    "ZoneRow",
    "database_path",
    "has_tabular_report",
    "read_construction_layers",
    "read_constructions",
    "read_environment_periods",
    "read_materials",
    "read_nominal_infiltration",
    "read_nominal_loads",
    "read_nominal_ventilation",
    "read_simulations",
    "read_site_elevation",
    "read_surfaces",
    "read_zones",
]

GainKind = Literal["people", "lights", "electric", "gas", "hot_water_equipment", "steam", "other", "baseboard"]
"""The kind of an internal gain, one per `Nominal*` gain table (data-model.md, GainRecord)."""

NOMINAL_LOAD_TABLES: dict[GainKind, str] = {
    "people": "NominalPeople",
    "lights": "NominalLighting",
    "electric": "NominalElectricEquipment",
    "gas": "NominalGasEquipment",
    "hot_water_equipment": "NominalHotWaterEquipment",
    "steam": "NominalSteamEquipment",
    "other": "NominalOtherEquipment",
    "baseboard": "NominalBaseboardHeaters",
}
"""Each gain kind's table, in the order `read_nominal_loads` returns them."""

_VERSION = re.compile(r"Version\s+(\d+)\.(\d+)\.(\d+)")


class SQLTableError(ValueError):
    """A static table of the results is missing, or holds a value of an unexpected type.

    Attributes:
        table: The table.
        column: The column, or `None` when the table itself is at fault.
        value: The value found.
    """

    def __init__(self, table: str, column: str | None, problem: str, value: object = None) -> None:
        """Create the error.

        Args:
            table: The table.
            column: The column, or `None` when the table itself is at fault.
            problem: What is wrong, such as `expected a number`.
            value: The value found.
        """
        self.table = table
        self.column = column
        self.value = value
        where = f"{table}.{column}" if column else table
        found = f", found {value!r} ({type(value).__name__})" if column else ""
        super().__init__(f"EnergyPlus results table {where}: {problem}{found}")


# --- Conversion at the boundary ----------------------------------------------------------------


class _Row:
    """One record of a table, with typed accessors that name the table and column on failure."""

    def __init__(self, table: str, columns: Sequence[str], values: tuple[object, ...]) -> None:
        self.table = table
        self.values = dict(zip(columns, values, strict=True))

    def _raw(self, column: str) -> object:
        return self.values[column]

    def opt_real(self, column: str) -> float | None:
        value = self._raw(column)
        if value is None:
            return None
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise SQLTableError(self.table, column, "expected a number", value)
        return float(value)

    def real(self, column: str) -> float:
        value = self.opt_real(column)
        if value is None:
            raise SQLTableError(self.table, column, "expected a number", None)
        return value

    def opt_whole(self, column: str) -> int | None:
        value = self.opt_real(column)
        if value is None:
            return None
        if not value.is_integer():
            raise SQLTableError(self.table, column, "expected a whole number", self._raw(column))
        return int(value)

    def whole(self, column: str) -> int:
        value = self.opt_whole(column)
        if value is None:
            raise SQLTableError(self.table, column, "expected a whole number", None)
        return value

    def opt_text(self, column: str) -> str | None:
        value = self._raw(column)
        if value is None:
            return None
        if not isinstance(value, str):
            raise SQLTableError(self.table, column, "expected text", value)
        return value

    def text(self, column: str) -> str:
        value = self.opt_text(column)
        if value is None:
            raise SQLTableError(self.table, column, "expected text", None)
        return value

    def flag(self, column: str) -> bool:
        value = self._raw(column)
        if isinstance(value, str) and value.strip().upper() in {"TRUE", "FALSE"}:
            return value.strip().upper() == "TRUE"
        if isinstance(value, int) and not isinstance(value, bool) and value in {0, 1}:
            return value == 1
        raise SQLTableError(self.table, column, "expected 0, 1, TRUE or FALSE", value)

    def opt_index(self, column: str) -> int | None:
        """A foreign key: EnergyPlus writes NULL, or -1 or 0, for none."""
        value = self.opt_whole(column)
        return None if value is None or value <= 0 else value


def _select(
    sql: SQLResult, table: str, columns: Sequence[str], *, order_by: str, joins: str = "", prefix: str = ""
) -> list[_Row]:
    selected = ", ".join(columns if not prefix else [c if "." in c else f"{prefix}.{c}" for c in columns])
    statement = f"SELECT {selected} FROM {table} {prefix} {joins} ORDER BY {order_by}"  # noqa: S608 - constant names
    try:
        records = sql.query(statement)
    except sqlite3.Error as error:
        raise SQLTableError(table, None, f"cannot be read ({error})") from error
    names = [column.rsplit(".", 1)[-1].split(" AS ")[-1] for column in columns]
    return [_Row(table, names, record) for record in records]


def has_tabular_report(sql: SQLResult, report: str) -> bool:
    """Whether the results hold any row of a tabular report.

    Args:
        sql: The results.
        report: The report's name, as `TabularDataWithStrings.ReportName` writes it.

    Returns:
        `True` when the report has at least one row.

    Raises:
        SQLTableError: If the table cannot be read.
    """
    try:
        rows = sql.query("SELECT 1 FROM TabularDataWithStrings WHERE ReportName = ? LIMIT 1", (report,))
    except sqlite3.Error as error:
        raise SQLTableError("TabularDataWithStrings", None, f"cannot be read ({error})") from error
    return bool(rows)


def simulated_leap_day(sql: SQLResult) -> bool | None:
    """Whether the weather-file run simulated 29 February.

    EnergyPlus runs a leap year's 29 February only when the weather file allows leap years.

    Args:
        sql: The results.

    Returns:
        `True` or `False`, or `None` when the results' `Time` table cannot tell.
    """
    try:
        rows = sql.query(
            "SELECT COUNT(*), SUM(t.Month = 2 AND t.Day = 29) FROM Time t JOIN EnvironmentPeriods e "
            "ON e.EnvironmentPeriodIndex = t.EnvironmentPeriodIndex WHERE e.EnvironmentType = 3"
        )
    except sqlite3.Error:
        return None
    if not rows or not rows[0][0]:
        return None
    return bool(rows[0][1])


_FEET = 0.3048


def read_site_elevation(sql: SQLResult) -> float | None:
    """The site elevation EnergyPlus ran with, m (Input Verification and Results Summary, General).

    Args:
        sql: The results.

    Returns:
        The elevation, or `None` when the results do not report it.
    """
    try:
        rows = sql.query(
            "SELECT Value, Units FROM TabularDataWithStrings WHERE ReportName = "
            "'InputVerificationandResultsSummary' AND TableName = 'General' AND RowName = 'Elevation'"
        )
    except sqlite3.Error:
        return None
    for value, units in rows:
        try:
            elevation = float(str(value).strip())
        except ValueError:
            continue
        return elevation * _FEET if str(units).strip().casefold() == "ft" else elevation
    return None


def database_path(sql: SQLResult) -> Path | None:
    """Return the file an open `SQLResult` reads, or `None` for an in-memory database.

    Args:
        sql: The results.

    Returns:
        The absolute path of the SQLite file.
    """
    for record in sql.query("PRAGMA database_list"):
        if len(record) >= 3 and record[1] == "main" and isinstance(record[2], str) and record[2]:  # noqa: PLR2004
            return Path(record[2]).resolve()
    return None


# --- Zones and envelope ------------------------------------------------------------------------


@dataclass(frozen=True)
class ZoneRow:
    """One row of `Zones`.

    Attributes:
        index: `ZoneIndex`, which other tables reference.
        name: `ZoneName`, upper-cased by EnergyPlus.
        multiplier: `Multiplier`.
        list_multiplier: `ListMultiplier`.
        floor_area: `FloorArea` of one copy, m².
        volume: `Volume` of one copy, m³.
        ceiling_height: `CeilingHeight`, m.
        minimum_z: `MinimumZ`, m.
        maximum_z: `MaximumZ`, m.
        exterior_gross_wall_area: `ExtGrossWallArea`, m².
        exterior_net_wall_area: `ExtNetWallArea`, m².
        exterior_window_area: `ExtWindowArea`, m².
        is_part_of_total_area: `IsPartOfTotalArea`.
    """

    index: int
    name: str
    multiplier: int
    list_multiplier: int
    floor_area: float
    volume: float
    ceiling_height: float
    minimum_z: float
    maximum_z: float
    exterior_gross_wall_area: float
    exterior_net_wall_area: float
    exterior_window_area: float
    is_part_of_total_area: bool


def read_zones(sql: SQLResult) -> tuple[ZoneRow, ...]:
    """Read `Zones`, in `ZoneIndex` order.

    Args:
        sql: The results.

    Returns:
        One row per zone.

    Raises:
        SQLTableError: If the table is missing or a value has an unexpected type.
    """
    columns = (
        "ZoneIndex",
        "ZoneName",
        "Multiplier",
        "ListMultiplier",
        "FloorArea",
        "Volume",
        "CeilingHeight",
        "MinimumZ",
        "MaximumZ",
        "ExtGrossWallArea",
        "ExtNetWallArea",
        "ExtWindowArea",
        "IsPartOfTotalArea",
    )
    return tuple(
        ZoneRow(
            index=row.whole("ZoneIndex"),
            name=row.text("ZoneName"),
            multiplier=row.whole("Multiplier"),
            list_multiplier=row.whole("ListMultiplier"),
            floor_area=row.real("FloorArea"),
            volume=row.real("Volume"),
            ceiling_height=row.real("CeilingHeight"),
            minimum_z=row.real("MinimumZ"),
            maximum_z=row.real("MaximumZ"),
            exterior_gross_wall_area=row.real("ExtGrossWallArea"),
            exterior_net_wall_area=row.real("ExtNetWallArea"),
            exterior_window_area=row.real("ExtWindowArea"),
            is_part_of_total_area=row.flag("IsPartOfTotalArea"),
        )
        for row in _select(sql, "Zones", columns, order_by="ZoneIndex")
    )


@dataclass(frozen=True)
class SurfaceRow:
    """One row of `Surfaces`.

    Attributes:
        index: `SurfaceIndex`.
        name: `SurfaceName`.
        construction_index: `ConstructionIndex`, or `None` for a surface without one.
        class_name: `ClassName` (`Wall`, `Floor`, `Roof`, `Window`, `Internal Mass`, ...).
        area: Net `Area`, m².
        gross_area: `GrossArea`, m².
        azimuth: `Azimuth`, degrees clockwise from north.
        tilt: `Tilt`, degrees from horizontal facing up.
        heat_transfer: `HeatTransferSurf`.
        base_surface_index: `BaseSurfaceIndex`, or `None`.
        zone_index: `ZoneIndex`, or `None` for a shading surface.
        exterior_boundary: `ExtBoundCond`: a surface index for an interzone surface, or one of
            EnergyPlus's negative codes (outdoors, ground, ...), or 0 for adiabatic.
    """

    index: int
    name: str
    construction_index: int | None
    class_name: str
    area: float
    gross_area: float
    azimuth: float
    tilt: float
    heat_transfer: bool
    base_surface_index: int | None
    zone_index: int | None
    exterior_boundary: int


def read_surfaces(sql: SQLResult) -> tuple[SurfaceRow, ...]:
    """Read `Surfaces`, in `SurfaceIndex` order.

    Args:
        sql: The results.

    Returns:
        One row per surface.

    Raises:
        SQLTableError: If the table is missing or a value has an unexpected type.
    """
    columns = (
        "SurfaceIndex",
        "SurfaceName",
        "ConstructionIndex",
        "ClassName",
        "Area",
        "GrossArea",
        "Azimuth",
        "Tilt",
        "HeatTransferSurf",
        "BaseSurfaceIndex",
        "ZoneIndex",
        "ExtBoundCond",
    )
    return tuple(
        SurfaceRow(
            index=row.whole("SurfaceIndex"),
            name=row.text("SurfaceName"),
            construction_index=row.opt_index("ConstructionIndex"),
            class_name=row.text("ClassName"),
            area=row.real("Area"),
            gross_area=row.real("GrossArea"),
            azimuth=row.real("Azimuth"),
            tilt=row.real("Tilt"),
            heat_transfer=row.flag("HeatTransferSurf"),
            base_surface_index=row.opt_index("BaseSurfaceIndex"),
            zone_index=row.opt_index("ZoneIndex"),
            exterior_boundary=row.whole("ExtBoundCond"),
        )
        for row in _select(sql, "Surfaces", columns, order_by="SurfaceIndex")
    )


@dataclass(frozen=True)
class ConstructionRow:
    """One row of `Constructions`.

    Attributes:
        index: `ConstructionIndex`.
        name: `Name`.
        total_layers: `TotalLayers`.
        type_is_window: `TypeIsWindow`.
        u_value: `Uvalue`, W/m²K (EnergyPlus's nominal value, without films for opaque layers).
    """

    index: int
    name: str
    total_layers: int
    type_is_window: bool
    u_value: float


def read_constructions(sql: SQLResult) -> tuple[ConstructionRow, ...]:
    """Read `Constructions`, in `ConstructionIndex` order.

    Args:
        sql: The results.

    Returns:
        One row per construction.

    Raises:
        SQLTableError: If the table is missing or a value has an unexpected type.
    """
    columns = ("ConstructionIndex", "Name", "TotalLayers", "TypeIsWindow", "Uvalue")
    return tuple(
        ConstructionRow(
            index=row.whole("ConstructionIndex"),
            name=row.text("Name"),
            total_layers=row.whole("TotalLayers"),
            type_is_window=row.flag("TypeIsWindow"),
            u_value=row.real("Uvalue"),
        )
        for row in _select(sql, "Constructions", columns, order_by="ConstructionIndex")
    )


@dataclass(frozen=True)
class ConstructionLayerRow:
    """One row of `ConstructionLayers`.

    Attributes:
        construction_index: `ConstructionIndex`.
        layer_index: `LayerIndex`, 1 for the outside layer.
        material_index: `MaterialIndex`.
    """

    construction_index: int
    layer_index: int
    material_index: int


def read_construction_layers(sql: SQLResult) -> tuple[ConstructionLayerRow, ...]:
    """Read `ConstructionLayers`, by construction then layer.

    Args:
        sql: The results.

    Returns:
        One row per layer.

    Raises:
        SQLTableError: If the table is missing or a value has an unexpected type.
    """
    columns = ("ConstructionIndex", "LayerIndex", "MaterialIndex")
    return tuple(
        ConstructionLayerRow(
            construction_index=row.whole("ConstructionIndex"),
            layer_index=row.whole("LayerIndex"),
            material_index=row.whole("MaterialIndex"),
        )
        for row in _select(sql, "ConstructionLayers", columns, order_by="ConstructionIndex, LayerIndex")
    )


@dataclass(frozen=True)
class MaterialRow:
    """One row of `Materials`.

    Attributes:
        index: `MaterialIndex`.
        name: `Name`.
        material_type: `MaterialType`, EnergyPlus's material group code.
        conductivity: `Conductivity`, W/mK.
        density: `Density`, kg/m³.
        specific_heat: `SpecHeat`, J/kgK.
        thickness: `Thickness`, m.
        resistance: `Resistance`, m²K/W.
        resistance_only: `ROnly` (a no-mass material).
    """

    index: int
    name: str
    material_type: int
    conductivity: float
    density: float
    specific_heat: float
    thickness: float
    resistance: float
    resistance_only: bool


def read_materials(sql: SQLResult) -> tuple[MaterialRow, ...]:
    """Read `Materials`, in `MaterialIndex` order.

    Args:
        sql: The results.

    Returns:
        One row per material.

    Raises:
        SQLTableError: If the table is missing or a value has an unexpected type.
    """
    columns = (
        "MaterialIndex",
        "Name",
        "MaterialType",
        "Conductivity",
        "Density",
        "SpecHeat",
        "Thickness",
        "Resistance",
        "ROnly",
    )
    return tuple(
        MaterialRow(
            index=row.whole("MaterialIndex"),
            name=row.text("Name"),
            material_type=row.whole("MaterialType"),
            conductivity=row.real("Conductivity"),
            density=row.real("Density"),
            specific_heat=row.real("SpecHeat"),
            thickness=row.real("Thickness"),
            resistance=row.real("Resistance"),
            resistance_only=row.flag("ROnly"),
        )
        for row in _select(sql, "Materials", columns, order_by="MaterialIndex")
    )


# --- Internal gains and airflows ---------------------------------------------------------------


@dataclass(frozen=True)
class NominalLoadRow:
    """One row of a `Nominal*` gain table, in one shape for every kind.

    Attributes:
        kind: Which table the row comes from.
        index: The row's index in its table.
        object_name: `ObjectName`.
        zone_index: `ZoneIndex`.
        schedule_name: The name of the row's schedule (number of people for `people`), or `None`.
        design_level: People for `people`; W otherwise (`CapatLowTemperature` for `baseboard`).
        fraction_radiant: `FractionRadiant`.
        fraction_latent: `FractionLatent`; 0 for lights and baseboards, `None` for people
            (EnergyPlus computes it from the activity level).
        fraction_lost: `FractionLost`; 0 for people, lights and baseboards.
        fraction_return_air: `FractionReturnAir` for lights; 0 otherwise.
        activity_schedule_name: For people, the activity level schedule's name (W per person);
            `None` otherwise.
    """

    kind: GainKind
    index: int
    object_name: str
    zone_index: int
    schedule_name: str | None
    design_level: float
    fraction_radiant: float
    fraction_latent: float | None
    fraction_lost: float
    fraction_return_air: float
    activity_schedule_name: str | None = None


def _read_nominal(sql: SQLResult, kind: GainKind) -> list[NominalLoadRow]:
    table = NOMINAL_LOAD_TABLES[kind]
    index = "NominalBaseboardHeaterIndex" if kind == "baseboard" else f"{table}Index"
    schedule = {"people": "NumberOfPeopleScheduleIndex", "hot_water_equipment": "SchedNo"}.get(kind, "ScheduleIndex")
    level = {"people": "NumberOfPeople", "baseboard": "CapatLowTemperature"}.get(kind, "DesignLevel")
    extra: tuple[str, ...] = {
        "people": (),
        "lights": ("FractionReturnAir",),
        "baseboard": (),
    }.get(kind, ("FractionLatent", "FractionLost"))
    columns: tuple[str, ...] = (
        index,
        "ObjectName",
        "ZoneIndex",
        level,
        "FractionRadiant",
        *extra,
        "s.ScheduleName AS ScheduleName",
    )
    joins = f"LEFT JOIN Schedules s ON s.ScheduleIndex = t.{schedule}"
    if kind == "people":
        columns = (*columns, "a.ScheduleName AS ActivityScheduleName")
        joins += " LEFT JOIN Schedules a ON a.ScheduleIndex = t.ActivityScheduleIndex"
    rows = _select(sql, table, columns, order_by=f"t.{index}", joins=joins, prefix="t")
    return [
        NominalLoadRow(
            kind=kind,
            index=row.whole(index),
            object_name=row.text("ObjectName"),
            zone_index=row.whole("ZoneIndex"),
            schedule_name=row.opt_text("ScheduleName"),
            design_level=row.real(level),
            fraction_radiant=row.real("FractionRadiant"),
            fraction_latent=None if kind == "people" else (row.real("FractionLatent") if extra[1:] else 0.0),
            fraction_lost=row.real("FractionLost") if extra[1:] else 0.0,
            fraction_return_air=row.real("FractionReturnAir") if kind == "lights" else 0.0,
            activity_schedule_name=row.opt_text("ActivityScheduleName") if kind == "people" else None,
        )
        for row in rows
    ]


def read_nominal_loads(sql: SQLResult, kinds: Sequence[GainKind] | None = None) -> tuple[NominalLoadRow, ...]:
    """Read the `Nominal*` gain tables, in `NOMINAL_LOAD_TABLES` order, then by index.

    Args:
        sql: The results.
        kinds: The kinds to read; every kind when `None`.

    Returns:
        One row per gain object.

    Raises:
        SQLTableError: If a table is missing or a value has an unexpected type.
    """
    selected: tuple[GainKind, ...] = tuple(k for k in NOMINAL_LOAD_TABLES if kinds is None or k in kinds)
    return tuple(row for kind in selected for row in _read_nominal(sql, kind))


@dataclass(frozen=True)
class NominalInfiltrationRow:
    """One row of `NominalInfiltration`.

    Attributes:
        index: `NominalInfiltrationIndex`.
        object_name: `ObjectName`.
        zone_index: `ZoneIndex`.
        schedule_name: The schedule's name, or `None`.
        design_level: `DesignLevel`, m³/s.
    """

    index: int
    object_name: str
    zone_index: int
    schedule_name: str | None
    design_level: float


@dataclass(frozen=True)
class NominalVentilationRow(NominalInfiltrationRow):
    """One row of `NominalVentilation`, with the fields of `NominalInfiltrationRow`."""


_A = TypeVar("_A", bound=NominalInfiltrationRow)


def _read_airflow(sql: SQLResult, table: str, make: Callable[[int, str, int, str | None, float], _A]) -> list[_A]:
    index = f"{table}Index"
    columns = (index, "ObjectName", "ZoneIndex", "DesignLevel", "s.ScheduleName AS ScheduleName")
    joins = "LEFT JOIN Schedules s ON s.ScheduleIndex = t.ScheduleIndex"
    return [
        make(
            row.whole(index),
            row.text("ObjectName"),
            row.whole("ZoneIndex"),
            row.opt_text("ScheduleName"),
            row.real("DesignLevel"),
        )
        for row in _select(sql, table, columns, order_by=f"t.{index}", joins=joins, prefix="t")
    ]


def read_nominal_infiltration(sql: SQLResult) -> tuple[NominalInfiltrationRow, ...]:
    """Read `NominalInfiltration`, in index order.

    Args:
        sql: The results.

    Returns:
        One row per infiltration object.

    Raises:
        SQLTableError: If the table is missing or a value has an unexpected type.
    """
    return tuple(_read_airflow(sql, "NominalInfiltration", NominalInfiltrationRow))


def read_nominal_ventilation(sql: SQLResult) -> tuple[NominalVentilationRow, ...]:
    """Read `NominalVentilation`, in index order.

    Args:
        sql: The results.

    Returns:
        One row per simple ventilation object.

    Raises:
        SQLTableError: If the table is missing or a value has an unexpected type.
    """
    return tuple(_read_airflow(sql, "NominalVentilation", NominalVentilationRow))


# --- Run ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class SimulationRow:
    """One row of `Simulations`.

    Attributes:
        index: `SimulationIndex`.
        version_text: `EnergyPlusVersion` as written (`EnergyPlus, Version 24.2.0-94a887817b, ...`).
        energyplus_version: The version parsed from it.
        timesteps_per_hour: `NumTimestepsPerHour`.
        completed: `Completed`.
        completed_successfully: `CompletedSuccessfully`.
    """

    index: int
    version_text: str
    energyplus_version: tuple[int, int, int]
    timesteps_per_hour: int
    completed: bool
    completed_successfully: bool


def read_simulations(sql: SQLResult) -> tuple[SimulationRow, ...]:
    """Read `Simulations`, in index order.

    Args:
        sql: The results.

    Returns:
        One row per simulation (normally one).

    Raises:
        SQLTableError: If the table is missing, a value has an unexpected type or the version
            cannot be parsed.
    """
    columns = (
        "SimulationIndex",
        "EnergyPlusVersion",
        "NumTimestepsPerHour",
        "Completed",
        "CompletedSuccessfully",
    )
    result: list[SimulationRow] = []
    for row in _select(sql, "Simulations", columns, order_by="SimulationIndex"):
        text = row.text("EnergyPlusVersion")
        match = _VERSION.search(text)
        if match is None:
            raise SQLTableError("Simulations", "EnergyPlusVersion", "expected 'Version X.Y.Z'", text)
        major, minor, patch = (int(part) for part in match.groups())
        result.append(
            SimulationRow(
                index=row.whole("SimulationIndex"),
                version_text=text,
                energyplus_version=(major, minor, patch),
                timesteps_per_hour=row.whole("NumTimestepsPerHour"),
                completed=row.flag("Completed"),
                completed_successfully=row.flag("CompletedSuccessfully"),
            )
        )
    return tuple(result)


@dataclass(frozen=True)
class EnvironmentPeriodRow:
    """One row of `EnvironmentPeriods`.

    Attributes:
        index: `EnvironmentPeriodIndex`.
        simulation_index: `SimulationIndex`.
        name: `EnvironmentName`.
        environment_type: `EnvironmentType`: 1 design day, 2 design run period, 3 weather-file
            run period.
    """

    index: int
    simulation_index: int
    name: str
    environment_type: int


def read_environment_periods(sql: SQLResult) -> tuple[EnvironmentPeriodRow, ...]:
    """Read `EnvironmentPeriods`, in index order.

    Args:
        sql: The results.

    Returns:
        One row per environment.

    Raises:
        SQLTableError: If the table is missing or a value has an unexpected type.
    """
    columns = ("EnvironmentPeriodIndex", "SimulationIndex", "EnvironmentName", "EnvironmentType")
    return tuple(
        EnvironmentPeriodRow(
            index=row.whole("EnvironmentPeriodIndex"),
            simulation_index=row.whole("SimulationIndex"),
            name=row.text("EnvironmentName"),
            environment_type=row.whole("EnvironmentType"),
        )
        for row in _select(sql, "EnvironmentPeriods", columns, order_by="EnvironmentPeriodIndex")
    )
