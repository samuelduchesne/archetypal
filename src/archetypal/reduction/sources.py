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
non-zero energy. Reading it from the model would mean following every coil, boiler and plant
loop to its fuel, which EnergyPlus has already done.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from idfkit import LATEST_VERSION, load_epjson, load_idf, write_idf
from idfkit.exceptions import ResultLookupError
from idfkit.simulation import SQLResult
from idfkit.versioned import as_version

from archetypal.errors import MissingResults, ModelResultsMismatch, UnsupportedEnergyPlusVersion
from archetypal.reduction._sql_tables import database_path, read_simulations, read_zones
from archetypal.reduction.requirements import RESULTS_REQUIREMENTS, ModelFacts, check_results, delivery_outputs
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
    def from_document(cls, doc: IDFDocumentSince22_1) -> RunPeriodInfo:
        """Read a model's first `RunPeriod`; without one, a whole year starting on a Sunday.

        Args:
            doc: The model.

        Returns:
            The run period.
        """
        calendar = RunPeriodCalendar.from_document(doc)
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
    become `HeatRejection` and `NaturalGas`. The `Water` column is not a fuel.

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
    for object_type, collection in doc.objects_by_type():
        outputs = delivery_outputs(object_type)
        if outputs:
            pairs.extend((variable, obj.name) for obj in collection for _, variable in outputs)
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
    """
    doc, model_path, model_sha256 = _load_model(model)
    model_subject = _subject(model_path, "the model")

    # 1. Versions.
    if not _supported(doc.version):
        raise UnsupportedEnergyPlusVersion(model_subject, _release(doc.version), supported_versions())
    narrowed = as_version(doc, since="22.1")
    if model_sha256 is None:
        model_sha256 = hashlib.sha256(write_idf(narrowed).encode("utf-8")).hexdigest()

    if results is None:
        no_fuels = model_facts(narrowed, ())
        missing = [text for r in RESULTS_REQUIREMENTS if r.applies_to(no_fuels) for text in r.idf_objects(no_fuels)]
        raise MissingResults(model_subject, [*missing, *TABULAR_OUTPUTS])

    sql = results if isinstance(results, SQLResult) else SQLResult(Path(results))
    results_path = database_path(sql) if isinstance(results, SQLResult) else Path(results).resolve()
    results_subject = _subject(results_path, "the results")
    try:
        return _check(sql, narrowed, model_path, model_sha256, results_path, results_subject, weather)
    except BaseException:
        if sql is not results:
            sql.close()
        raise


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
    if fuels is None:
        missing.extend(TABULAR_OUTPUTS)
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

    version = doc.version
    return SourceData(
        model=doc,
        results=sql,
        energyplus_version=(version[0], version[1], version[2]),
        run_period=RunPeriodInfo.from_document(doc),
        facts=facts,
        model_sha256=model_sha256,
        results_sha256=_sha256_file(results_path) if results_path is not None else "",
        weather_sha256=_sha256_file(Path(weather)) if weather is not None else None,
        model_path=model_path,
        results_path=results_path,
    )
