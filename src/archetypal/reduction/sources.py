"""The inputs of a reduction, loaded and checked (data-model.md, SourceData; research R2, R3, R18).

`load_sources` reads the detailed model and the SQLite results of its annual run, narrows the
model to the releases reduction supports (`as_version(doc, since="22.1")`) and validates them in
the order of data-model.md, raising before any other work:

1. the EnergyPlus version of the model, then of the results, is within 22.1 to idfkit's latest,
   and the two agree (`UnsupportedEnergyPlusVersion`, `ModelResultsMismatch`);
2. every item of `RESULTS_REQUIREMENTS` that applies to the model is present
   (`MissingResults`);
3. the model's zone names equal the results' (`ModelResultsMismatch`).

The fourth check, at least one conditioned zone, needs classification and is made there.

Which fuels each end use meters (`ModelFacts.end_use_fuels`) is read from the results' tabular
*Annual Building Utility Performance Summary*, End Uses, which the run conditions of
`contracts/results-requirements.md` require: a fuel is needed where that table reports
non-zero energy, or where the results already hold its hourly `<end use>:<fuel>` meter (the
table rounds a fuel under 5 MJ a year to zero). Reading it from the model would mean following
every coil, boiler and plant loop to its fuel, which EnergyPlus has already done.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from idfkit import LATEST_VERSION, load_epjson, load_idf, write_idf
from idfkit.exceptions import ResultLookupError
from idfkit.simulation import SQLResult
from idfkit.versioned import as_version

from archetypal._sqlite import open_results
from archetypal.errors import MissingResults, ModelResultsMismatch, ReductionError, UnsupportedEnergyPlusVersion
from archetypal.reduction._sql_tables import (
    SQLTableError,
    database_path,
    has_tabular_report,
    read_simulations,
    read_zones,
    simulated_leap_day,
)
from archetypal.reduction.requirements import (
    ENERGYPLUS_FUELS,
    RESULTS_REQUIREMENTS,
    ModelFacts,
    check_results,
    delivery_outputs,
)
from archetypal.reduction.schedules import WEEKDAYS, RunPeriodCalendar

if TYPE_CHECKING:
    from idfkit.document import AnyIDFDocument
    from idfkit.versioned import IDFDocumentSince22_1

__all__ = [
    "OLDEST_SUPPORTED",
    "TABULAR_OUTPUTS",
    "RunPeriodInfo",
    "SourceData",
    "end_use_fuels",
    "load_sources",
    "model_facts",
    "supported_versions",
]

OLDEST_SUPPORTED = "22.1"
"""The oldest EnergyPlus release reduction accepts (research R3)."""

TABULAR_OUTPUTS = (
    "Output:SQLite,SimpleAndTabular;",
    "Output:Table:SummaryReports,AllSummary;",
)
"""The objects that make EnergyPlus write the tabular reports reduction reads."""

WEATHER_FILE_RUN = (
    "SimulationControl with 'Run Simulation for Weather File Run Periods' set to Yes, and an annual RunPeriod;"
)
"""What a run needs to report its weather-file run period: results of design days alone hold too
few hours to reduce (EnergyPlus's example files often run only their design days)."""

_WEATHER_FILE_RUN_PERIOD = 3
"""`EnvironmentPeriods.EnvironmentType` of a weather-file run period."""

_ABUPS = "AnnualBuildingUtilityPerformanceSummary"
_END_USES = ("Heating", "Cooling", "HeatRejection", "WaterSystems")
_NOT_A_FUEL = frozenset({"Water"})
_FAN_TYPES = (
    "Fan:ConstantVolume",
    "Fan:VariableVolume",
    "Fan:OnOff",
    "Fan:ZoneExhaust",
    "Fan:SystemModel",
    "Fan:ComponentModel",
)
_PUMP_TYPES = (
    "Pump:VariableSpeed",
    "Pump:ConstantSpeed",
    "Pump:VariableSpeed:Condensate",
    "HeaderedPumps:VariableSpeed",
    "HeaderedPumps:ConstantSpeed",
)


def supported_versions() -> tuple[str, str]:
    """Return the oldest and newest EnergyPlus releases reduction accepts, such as `("22.1", "26.2")`."""
    return OLDEST_SUPPORTED, f"{LATEST_VERSION[0]}.{LATEST_VERSION[1]}"


def _release(version: tuple[int, ...]) -> str:
    return f"{version[0]}.{version[1]}"


def _supported(version: tuple[int, ...]) -> bool:
    oldest = tuple(int(part) for part in OLDEST_SUPPORTED.split("."))
    return oldest <= tuple(version[:2]) <= tuple(LATEST_VERSION[:2])


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


# --- Run period --------------------------------------------------------------------------------


@dataclass(frozen=True)
class RunPeriodInfo:
    """The model's run period, on the calendar reduction evaluates schedules on (research R5).

    Attributes:
        name: The `RunPeriod`'s name, or `None` when the model has none.
        begin: The first day, in the calendar year.
        end: The last day (in the next year when the run period wraps around 1 January).
        start_weekday: The weekday of `begin` (`Monday` ... `Sunday`).
        calendar: The calendar year and its special days.
    """

    name: str | None
    begin: date
    end: date
    start_weekday: str
    calendar: RunPeriodCalendar

    @property
    def year(self) -> int:
        """The calendar year chosen per research R5."""
        return self.calendar.year

    @property
    def holidays(self) -> frozenset[date]:
        """The dates `RunPeriodControl:SpecialDays` marks as holidays."""
        return self.calendar.holidays

    @classmethod
    def from_document(cls, doc: IDFDocumentSince22_1, *, leap_day: bool | None = None) -> RunPeriodInfo:
        """Read a model's first `RunPeriod`; without one, a whole year starting on a Sunday.

        Args:
            doc: The model.
            leap_day: Whether the simulation ran 29 February (`RunPeriodCalendar.from_document`).

        Returns:
            The run period.
        """
        calendar = RunPeriodCalendar.from_document(doc, leap_day=leap_day)
        year = calendar.year
        name: str | None = None
        begin_month, begin_day, end_month, end_day = 1, 1, 12, 31
        for run_period in doc.run_periods:
            name = run_period.name
            begin_month = int(run_period.begin_month)  # a float in 22.1 files, as UP-6
            begin_day = int(run_period.begin_day_of_month)
            end_month = int(run_period.end_month)
            end_day = int(run_period.end_day_of_month)
            break
        begin = _day(year, begin_month, begin_day)
        end = _day(year, end_month, end_day)
        if end < begin:
            end = _day(year + 1, end_month, end_day)
        return cls(name=name, begin=begin, end=end, start_weekday=WEEKDAYS[begin.weekday()], calendar=calendar)


def _day(year: int, month: int, day: int) -> date:
    """The date, with 29 February read as 28 February in a non-leap year."""
    try:
        return date(year, month, day)
    except ValueError:
        return date(year, month, 1) + timedelta(days=day - 2)


# --- Model facts -------------------------------------------------------------------------------


def end_use_fuels(results: SQLResult) -> tuple[tuple[str, str], ...] | None:
    """Return the (end use, fuel) pairs with energy in the results' End Uses table.

    Names follow EnergyPlus's meter spelling: the table's `Heat Rejection` and `Natural Gas`
    become `HeatRejection` and `NaturalGas`. The `Water` column is not a fuel. The table rounds
    to 0.01 GJ, so a fuel under 5 MJ a year reads as zero there: the `<end use>:<fuel>` meters
    the results already report hourly are added too.

    Args:
        results: The results.

    Returns:
        The pairs, sorted; `None` when the results hold no End Uses table.
    """
    try:
        rows = results.get_tabular_data(_ABUPS, "End Uses", report_for="Entire Facility")
    except ResultLookupError:
        return None
    pairs: set[tuple[str, str]] = set()
    for row in rows:
        end_use = row.row_name.replace(" ", "")
        if end_use not in _END_USES or row.column_name in _NOT_A_FUEL:
            continue
        try:
            value = row.as_float()
        except ValueError:
            continue
        if value != 0.0:
            pairs.add((end_use, row.column_name.replace(" ", "")))
    for info in results.list_variables():
        end_use, _, fuel = info.name.partition(":")
        if info.is_meter and info.frequency == "Hourly" and end_use in _END_USES and fuel in ENERGYPLUS_FUELS:
            pairs.add((end_use, fuel))
    return tuple(sorted(pairs))


def _names(doc: IDFDocumentSince22_1, object_types: tuple[str, ...]) -> tuple[str, ...]:
    collections = {
        "Fan:ConstantVolume": doc["Fan:ConstantVolume"],
        "Fan:VariableVolume": doc["Fan:VariableVolume"],
        "Fan:OnOff": doc["Fan:OnOff"],
        "Fan:ZoneExhaust": doc["Fan:ZoneExhaust"],
        "Fan:SystemModel": doc["Fan:SystemModel"],
        "Fan:ComponentModel": doc["Fan:ComponentModel"],
        "Pump:VariableSpeed": doc["Pump:VariableSpeed"],
        "Pump:ConstantSpeed": doc["Pump:ConstantSpeed"],
        "Pump:VariableSpeed:Condensate": doc["Pump:VariableSpeed:Condensate"],
        "HeaderedPumps:VariableSpeed": doc["HeaderedPumps:VariableSpeed"],
        "HeaderedPumps:ConstantSpeed": doc["HeaderedPumps:ConstantSpeed"],
    }
    return tuple(obj.name for object_type in object_types for obj in collections[object_type])


def _inlet_nodes(doc: IDFDocumentSince22_1) -> tuple[str, ...]:
    node_lists = {
        node_list.name.casefold(): tuple(group.node_name for group in node_list.nodes) for node_list in doc["NodeList"]
    }
    nodes: list[str] = []
    for connections in doc["ZoneHVAC:EquipmentConnections"]:
        inlet = connections.zone_air_inlet_node_or_nodelist_name
        if inlet:
            nodes.extend(node_lists.get(inlet.casefold(), (inlet,)))
    return tuple(dict.fromkeys(nodes))


def _hvac_outputs(doc: IDFDocumentSince22_1) -> tuple[tuple[str, str], ...]:
    """(variable, object name) pairs reporting the energy each HVAC object delivers (R12)."""
    pairs: list[tuple[str, str]] = []
    for obj in doc.all_objects:
        pairs.extend((variable, obj.name) for _, variable in delivery_outputs(obj.obj_type))
    return tuple(pairs)


def _served_zones(doc: IDFDocumentSince22_1) -> tuple[str, ...]:
    served = {connections.zone_name.casefold() for connections in doc["ZoneHVAC:EquipmentConnections"]}
    return tuple(zone.name for zone in doc.zones if zone.name.casefold() in served)


def model_facts(doc: IDFDocumentSince22_1, fuels: tuple[tuple[str, str], ...]) -> ModelFacts:
    """Summarise what decides which results a model needs.

    Args:
        doc: The model.
        fuels: The (end use, fuel) pairs it meters, from `end_use_fuels`.

    Returns:
        The facts, names in model order.
    """
    return ModelFacts(
        zones=tuple(zone.name for zone in doc.zones),
        fans=_names(doc, _FAN_TYPES),
        pumps=_names(doc, _PUMP_TYPES),
        zone_air_inlet_nodes=_inlet_nodes(doc),
        served_zones=_served_zones(doc),
        water_use_equipment=tuple(equipment.name for equipment in doc.water_use_equipments),
        end_use_fuels=fuels,
        hvac_outputs=_hvac_outputs(doc),
    )


# --- Source data -------------------------------------------------------------------------------


@dataclass(frozen=True)
class SourceData:
    """The inputs of a reduction, checked.

    Attributes:
        model: The model, narrowed to the releases reduction supports.
        results: The results of its annual run.
        energyplus_version: The model's EnergyPlus version (the results agree on the release).
        run_period: The run period and its calendar.
        facts: What the model contains that decides the results it needs.
        model_sha256: SHA-256 of the model file, or of the IDF text idfkit writes for a document
            given without a file.
        results_sha256: SHA-256 of the SQLite file.
        weather_sha256: SHA-256 of the weather file, or `None` without one.
        model_path: The model's file, when it has one.
        results_path: The SQLite file, when known.
    """

    model: IDFDocumentSince22_1
    results: SQLResult
    energyplus_version: tuple[int, int, int]
    run_period: RunPeriodInfo
    facts: ModelFacts
    model_sha256: str
    results_sha256: str
    weather_sha256: str | None
    model_path: Path | None = field(default=None)
    results_path: Path | None = field(default=None)


def _load_model(model: str | os.PathLike[str] | AnyIDFDocument) -> tuple[AnyIDFDocument, Path | None, str | None]:
    if isinstance(model, (str, os.PathLike)):
        path = Path(model)
        doc = load_epjson(path) if path.suffix.casefold() == ".epjson" else load_idf(path)
        return doc, path, _sha256_file(path)
    return model, model.filepath, None


def _subject(path: Path | None, fallback: str) -> str:
    return str(path) if path is not None else fallback


def load_sources(
    model: str | os.PathLike[str] | AnyIDFDocument,
    results: str | os.PathLike[str] | SQLResult | None,
    *,
    weather: str | os.PathLike[str] | None = None,
) -> SourceData:
    """Load a model and its results, and check them in the order of data-model.md.

    Args:
        model: The model's `.idf` or `.epJSON` file, or an idfkit document of any release.
        results: The SQLite file of its annual run, an open `SQLResult`, or `None` when there
            are none yet (which raises `MissingResults` listing every output the model needs).
        weather: The weather file of the run, recorded by its SHA-256 only.

    Returns:
        The checked inputs. A results file given by path is opened here; the caller closes
        `SourceData.results` when done.

    Raises:
        UnsupportedEnergyPlusVersion: The model or results are older than 22.1 or newer than
            idfkit's latest release.
        ModelResultsMismatch: The model and results differ in EnergyPlus release or zone names.
        MissingResults: The results lack an output or tabular report that reduction reads.
        ReductionError: The model holds HVACTemplate objects, its run period is not one whole
            calendar year, or the results cannot be read as EnergyPlus SQLite results.
    """
    doc, model_path, model_sha256 = _load_model(model)
    model_subject = _subject(model_path, "the model")

    # 1. Versions.
    if not _supported(doc.version):
        raise UnsupportedEnergyPlusVersion(model_subject, _release(doc.version), supported_versions())
    narrowed = as_version(doc, since="22.1")
    templates = sorted({
        obj.obj_type for obj in narrowed.all_objects if obj.obj_type.casefold().startswith("hvactemplate:")
    })
    if templates:
        # Reduction reads the HVAC objects EnergyPlus simulates; HVACTemplate objects are only
        # expanded into them (by ExpandObjects) when EnergyPlus runs, so the model holds none.
        message = (
            f"holds {', '.join(templates)} objects; reduction reads the objects EnergyPlus simulates: reduce the "
            "expanded model (expanded.idf, written by EnergyPlus's ExpandObjects) with its results"
        )
        raise ReductionError(model_subject, message)
    if model_sha256 is None:
        model_sha256 = hashlib.sha256(write_idf(narrowed).encode("utf-8")).hexdigest()

    if results is None:
        no_fuels = model_facts(narrowed, ())
        missing = [text for r in RESULTS_REQUIREMENTS if r.applies_to(no_fuels) for text in r.idf_objects(no_fuels)]
        raise MissingResults(model_subject, [*missing, *TABULAR_OUTPUTS])

    sql = results if isinstance(results, SQLResult) else open_results(results, SQLResult)
    results_path = database_path(sql) if isinstance(results, SQLResult) else Path(results).resolve()
    results_subject = _subject(results_path, "the results")
    try:
        return _check(sql, narrowed, model_path, model_sha256, results_path, results_subject, weather)
    except (SQLTableError, sqlite3.Error) as error:
        if sql is not results:
            sql.close()
        message = f"cannot be read as EnergyPlus SQLite results ({error})"
        raise ReductionError(results_subject, message) from error
    except BaseException:
        if sql is not results:
            sql.close()
        raise


def _annual_run_period(
    doc: IDFDocumentSince22_1,
    model_path: Path | None,
    results_subject: str,
    weather_runs: int,
    leap_day: bool | None = None,
) -> RunPeriodInfo:
    """The model's run period, refused unless it is one whole calendar year.

    Schedules and results are read on one calendar year from 1 January: a run period that wraps
    around 1 January runs its January in the next year, and a shorter or longer one (or a second
    one, whose rows follow the first's) gives hourly series of another length than the schedules'.
    """
    run_period = RunPeriodInfo.from_document(doc, leap_day=leap_day)
    if run_period.end.year != run_period.begin.year:
        message = (
            f"the RunPeriod {run_period.name or ''} runs from {run_period.begin:%d %B} to {run_period.end:%d %B} "
            "across 1 January; reduction reads one calendar year from 1 January: run the model from 1 January "
            "to 31 December"
        )
        raise ReductionError(model_path or "the model", message)
    if (run_period.begin.month, run_period.begin.day, run_period.end.month, run_period.end.day) != (1, 1, 12, 31):
        message = (
            f"the RunPeriod {run_period.name or ''} runs from {run_period.begin:%d %B} to {run_period.end:%d %B}; "
            "reduction reads one whole calendar year: run the model from 1 January to 31 December"
        )
        raise ReductionError(model_path or "the model", message)
    if weather_runs > 1:
        message = (
            f"the results hold {weather_runs} weather-file run periods; reduction reads one annual run period: "
            "run the model with one RunPeriod from 1 January to 31 December"
        )
        raise ReductionError(results_subject, message)
    return run_period


def _check(
    sql: SQLResult,
    doc: IDFDocumentSince22_1,
    model_path: Path | None,
    model_sha256: str,
    results_path: Path | None,
    results_subject: str,
    weather: str | os.PathLike[str] | None,
) -> SourceData:
    simulations = read_simulations(sql)
    if simulations:
        results_version = simulations[-1].energyplus_version
        if not _supported(results_version):
            raise UnsupportedEnergyPlusVersion(results_subject, _release(results_version), supported_versions())
        if results_version[:2] != doc.version[:2]:
            raise ModelResultsMismatch(
                results_subject,
                [f"EnergyPlus {_release(doc.version)} in the model, {_release(results_version)} in the results"],
            )

    # 2. Results requirements.
    fuels = end_use_fuels(sql)
    facts = model_facts(doc, fuels or ())
    missing = [text for requirement in check_results(sql, facts) for text in requirement.idf_objects(facts)]
    if fuels is None or not has_tabular_report(sql, "EnvelopeSummary"):
        # The End Uses table (fuels) and the Envelope Summary (U-factors, SHGC) both come from
        # the summary reports.
        missing.extend(text for text in TABULAR_OUTPUTS if text not in missing)
    weather_runs = [env for env in sql.list_environments() if env.environment_type == _WEATHER_FILE_RUN_PERIOD]
    if not weather_runs:
        missing.append(WEATHER_FILE_RUN)
    if missing:
        raise MissingResults(results_subject, missing)

    # 3. Zone names (EnergyPlus upper-cases them in the results).
    model_zones = {name.casefold(): name for name in facts.zones}
    result_zones = {zone.name.casefold(): zone.name for zone in read_zones(sql)}
    differences = [
        f"zone {result_zones[key]} is only in the results" for key in sorted(result_zones.keys() - model_zones.keys())
    ] + [f"zone {model_zones[key]} is only in the model" for key in sorted(model_zones.keys() - result_zones.keys())]
    if differences:
        raise ModelResultsMismatch(results_subject, differences)

    # 4. One annual run period.
    run_period = _annual_run_period(
        doc, model_path, results_subject, len(weather_runs), simulated_leap_day(sql) if weather_runs else None
    )

    version = doc.version
    return SourceData(
        model=doc,
        results=sql,
        energyplus_version=(version[0], version[1], version[2]),
        run_period=run_period,
        facts=facts,
        model_sha256=model_sha256,
        results_sha256=_sha256_file(results_path) if results_path is not None else "",
        weather_sha256=_sha256_file(Path(weather)) if weather is not None else None,
        model_path=model_path,
        results_path=results_path,
    )
