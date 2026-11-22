"""Reduce a detailed EnergyPlus model to an SBEM archetype (spec 002).

Reduction reads a model and its simulation results through idfkit, groups the zones into a
layout and gives one SBEM archetype with one zone group per group of zones, with a report of
every simplification made (contracts/python-api.md).

Public names: `reduce` (re-exported as `archetypal.reduce`), `Reduction`,
`RESULTS_REQUIREMENTS` and `schedule_compact`. Every module of this package is private: its
names may change between milestone tags without notice (contracts/python-api.md, Stability).

Steps of `reduce`, each in its own module:

1. `sources.load_sources`: load the model and results and check them (versions, results
   requirements, zone names), in the order FR-029 lists;
2. `inventory.build_inventory` and `classify.classify`: zone records, roles, exposure, space use;
3. `ledger.GroupLedger.from_zone` with the building-wide hooks (`envelope.EnvelopeHook`,
   `airflow.AirflowHook`, `hotwater.HotWaterHook`, `efficiency.efficiency_hook`,
   `fans.fans_hook`): one ledger per conditioned zone;
4. `grouping.group_zones`: groups at the layout, after the small-group threshold;
5. `to_sbem.to_archetype`: the fork's validated `Archetype` and its parameters;
6. `report`: the report, checked against invariants 1-7 of contracts/reduction-report.md.

Every error is raised before anything is returned, and `reduce` writes no file
(`Reduction.write` does), so a refused reduction leaves nothing behind (FR-029).
"""

from __future__ import annotations

import math
import os
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from epinterface.sbem.archetype import Archetype
from idfkit.simulation import SQLResult

from archetypal import io
from archetypal.errors import MissingResults, ReductionError
from archetypal.reduction import efficiency as _efficiency
from archetypal.reduction import fans as _fans
from archetypal.reduction import hotwater as _hotwater
from archetypal.reduction import thermostats as _thermostats
from archetypal.reduction.airflow import AirflowHook
from archetypal.reduction.classify import ClassifiedZone, classify
from archetypal.reduction.envelope import EnvelopeHook
from archetypal.reduction.features import NotRepresented, find_unsupported
from archetypal.reduction.grouping import Grouping, group_zones
from archetypal.reduction.inventory import build_inventory
from archetypal.reduction.ledger import EnvelopeAssignment, GroupLedger, gain_fields
from archetypal.reduction.options import ReductionOptions
from archetypal.reduction.report import (
    BuildingBlock,
    ExcludedZone,
    GroupMember,
    MergedDistinction,
    PreThresholdGroup,
    ReductionReport,
    ReportGroup,
    Reproducibility,
    SmallGroupMerge,
    gather_not_represented,
    group_name,
    raise_for_invariants,
)
from archetypal.reduction.requirements import RESULTS_REQUIREMENTS, run_once
from archetypal.reduction.schedules import ScheduleEvaluator, schedule_compact
from archetypal.reduction.sources import SourceData, load_sources, model_facts
from archetypal.reduction.to_sbem import (
    BuildingFacts,
    set_leaf_paths,
    simple_ventilation_not_represented,
    storey_ratio,
    to_archetype,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from idfkit.simulation import EnergyPlusConfig, TimeSeriesResult
    from idfkit.simulation.parsers.sql import Environment, SeriesSpec
    from idfkit.versioned import AnyIDFDocument

    from archetypal.reduction.ledger import Fuel, ZoneHook

__all__ = ["RESULTS_REQUIREMENTS", "Reduction", "reduce", "schedule_compact"]

_DEFAULT_OPTIONS = ReductionOptions()


@dataclass(frozen=True)
class Reduction:
    """An SBEM archetype and the report of how it was derived.

    Attributes:
        archetype: The fork's multi-group archetype (`epinterface.sbem.archetype.Archetype`).
        report: The reduction report.
    """

    archetype: Archetype
    report: ReductionReport

    def write(self, directory: str | os.PathLike[str], name: str, *, overwrite: bool = False) -> tuple[Path, Path]:
        """Write `<name>.sbem.json` and `<name>.report.json` in a directory.

        Equal reductions write byte-identical files (FR-005).

        Args:
            directory: The directory, created if needed.
            name: The file name stem, such as `office`.
            overwrite: Replace existing files; otherwise neither file is written when either exists.

        Returns:
            The archetype path and the report path.

        Raises:
            InputError: If `name` is not a plain stem, or a file exists and `overwrite` is false.
        """
        return io.write(self.archetype, self.report, directory, name, overwrite=overwrite)

    @classmethod
    def read(
        cls, archetype_path: str | os.PathLike[str], report_path: str | os.PathLike[str] | None = None
    ) -> Reduction:
        """Read an archetype and its report.

        Args:
            archetype_path: The `<name>.sbem.json` file.
            report_path: The report; `None` reads `<name>.report.json` beside the archetype.

        Returns:
            The reduction.

        Raises:
            ReductionError: If the report is missing, or a file records a schema version this
                version cannot read.
        """
        archetype, report = io.read(Archetype, ReductionReport, archetype_path, report_path)
        return cls(archetype=archetype, report=report)


def reduce(
    model: str | os.PathLike[str] | AnyIDFDocument,
    results: str | os.PathLike[str] | SQLResult | None = None,
    *,
    options: ReductionOptions = _DEFAULT_OPTIONS,
    weather: str | os.PathLike[str] | None = None,
    simulate: bool = False,
    energyplus: EnergyPlusConfig | None = None,
) -> Reduction:
    """Reduce a detailed EnergyPlus model and its results to an SBEM archetype (FR-001).

    Args:
        model: The model's `.idf` or `.epJSON` file, or an idfkit document of release 22.1 or later.
        results: The SQLite output of its annual run, meeting `RESULTS_REQUIREMENTS`.
        options: The layout, the small-group threshold and an optional space-use mapping.
        weather: The weather file of the run: recorded in the report, and required by `simulate`.
        simulate: When the results are missing or incomplete, run the model once with the
            outputs reduction needs (FR-002), instead of raising `MissingResults`.
        energyplus: The EnergyPlus installation for that run; `None` lets idfkit find it.

    Returns:
        The archetype and its report. Nothing is written; call `Reduction.write`.

    Raises:
        UnsupportedEnergyPlusVersion: The model or results are older than 22.1 or newer than
            idfkit supports.
        ModelResultsMismatch: The results come from another model.
        MissingResults: The results lack an output reduction needs, and `simulate` is false.
        NoConditionedZones: No zone is heated or cooled.
        ReductionError: `simulate` is true without `weather`, the run fails, or the archetype
            does not validate.
    """
    opened = _open(results)
    try:
        sources = _load(model, opened, weather=weather, simulate=simulate, energyplus=energyplus)
        try:
            return _reduce(sources, options)
        finally:
            if sources.results is not opened and sources.results is not results:
                sources.results.close()
    finally:
        if opened is not None and opened is not results:
            opened.close()


class _ReadOnceSQLResult(SQLResult):
    """Results that read each time series once per reduction.

    Several modules read the same series (delivered energy, inlet-node flows); EnergyPlus does
    not index `ReportData`, so each read parses every row again. Series are immutable, so they
    are kept by their request and environment.
    """

    def __init__(self, db_path: str | os.PathLike[str]) -> None:
        super().__init__(Path(db_path))
        self._series: dict[tuple[object, ...], TimeSeriesResult] = {}

    def get_timeseries_many(
        self, series: Iterable[SeriesSpec], environment: Environment | None = None
    ) -> list[TimeSeriesResult]:
        """Return the series as `SQLResult.get_timeseries_many` does, reading each only once."""
        specs = list(series)
        keys = [(*_spec_key(spec), environment) for spec in specs]
        unread = {key: spec for key, spec in zip(keys, specs, strict=True) if key not in self._series}
        if unread:
            read = super().get_timeseries_many(list(unread.values()), environment)
            self._series.update(zip(unread, read, strict=True))
        return [self._series[key] for key in keys]


def _spec_key(spec: SeriesSpec) -> tuple[str, str, str | None]:
    if isinstance(spec, str):
        return (spec.casefold(), "*", None)
    if isinstance(spec, tuple):
        frequency = spec[2] if len(spec) > 2 else None  # noqa: PLR2004 - (name, key, frequency)
        return (spec[0].casefold(), spec[1].casefold(), None if frequency is None else frequency.casefold())
    return (spec.name.casefold(), spec.key_value.casefold(), spec.frequency.casefold())


def _open(results: str | os.PathLike[str] | SQLResult | None) -> SQLResult | None:
    if isinstance(results, (str, os.PathLike)):
        return _ReadOnceSQLResult(results)
    return results


def _load(
    model: str | os.PathLike[str] | AnyIDFDocument,
    results: SQLResult | None,
    *,
    weather: str | os.PathLike[str] | None,
    simulate: bool,
    energyplus: EnergyPlusConfig | None,
) -> SourceData:
    try:
        return load_sources(model, results, weather=weather)
    except MissingResults as missing:
        if not simulate:
            raise
        if weather is None:
            raise ReductionError(
                missing.subject, "simulate=True runs the model once and needs a weather file; pass weather=..."
            ) from missing
    if isinstance(model, (str, os.PathLike)):
        from idfkit import load_epjson, load_idf  # noqa: PLC0415 - only for a single run

        path = Path(model)
        document = load_epjson(path) if path.suffix.casefold() == ".epjson" else load_idf(path)
        subject = str(path)
    else:
        document, subject = model, "the model"
    from idfkit.versioned import as_version  # noqa: PLC0415 - only for a single run

    narrowed = as_version(document, since="22.1")
    sql_path = run_once(narrowed, model_facts(narrowed, ()), weather, energyplus=energyplus, subject=subject)
    return load_sources(model, _ReadOnceSQLResult(sql_path), weather=weather)


def _model_name(sources: SourceData) -> str:
    return sources.model_path.stem if sources.model_path is not None else "archetype"


def _reduce(sources: SourceData, options: ReductionOptions) -> Reduction:
    evaluate = ScheduleEvaluator(sources.model, sources.run_period.calendar)
    zones = classify(
        build_inventory(sources, evaluate),
        evaluate,
        space_use_mapping=options.space_use_mapping,
    )
    conditioned = [z for z in zones if z.role == "conditioned"]

    envelope = EnvelopeHook(zones)
    hot_water = _hotwater.HotWaterHook.from_sources(sources)
    energy = _efficiency.efficiency_hook(sources, zones, evaluate)
    fans = _fans.fans_hook(sources, zones)
    hooks: Sequence[ZoneHook] = (
        gain_fields,
        envelope,
        AirflowHook.from_model(sources.model),
        _thermostats.ledger_fields,
        hot_water,
        energy,
        fans,
    )
    zone_ledgers = [(z, GroupLedger.from_zone(z, evaluate, hooks=hooks)) for z in conditioned]
    grouping = group_zones(zone_ledgers, layout=options.layout, threshold=options.small_group_threshold)

    mains = float(np.mean(hot_water.mains)) if hot_water.mains.size else None
    facts = BuildingFacts(
        calendar=sources.run_period.calendar,
        storey_ratio=storey_ratio(zones),
        mains_temperature=mains,
        air_density=fans.air_density,
    )
    name = _model_name(sources)
    conversion = to_archetype(grouping.groups, options.layout, facts, name=name)

    expected = (
        *find_unsupported(sources),
        *conversion.not_represented,
        *simple_ventilation_not_represented(zones),
        *_excluded_loads(zones),
        *_unassigned_envelope(envelope),
        *_allocated_hot_water(zones),
        *_unattributed_energy(energy, conditioned),
        *_unattributed_fans(fans),
    )
    groups = _report_groups(grouping, zones)
    zone_groups = {m.zone: g.name for g in groups for m in g.members}
    building = sum((g.ledger for g in grouping.groups), GroupLedger())
    report = ReductionReport(
        reproducibility=Reproducibility.current(
            energyplus_version=sources.energyplus_version,
            model_sha256=sources.model_sha256,
            results_sha256=sources.results_sha256 or _sha256_of_results(sources),
            weather_sha256=sources.weather_sha256,
            options=options,
        ),
        groups=groups,
        pre_threshold_groups=tuple(
            PreThresholdGroup(key=g.key, ledger=g.ledger) for g in grouping.pre_threshold_groups
        ),
        parameters=conversion.parameters,
        excluded_zones=_excluded_zones(zones, building),
        small_group_merges=tuple(
            SmallGroupMerge(key=m.merged_key, into_key=m.into_key, share=m.share, distance=m.distance)
            for m in grouping.merges
        ),
        not_represented=gather_not_represented(expected, zone_groups),
        merged_distinctions=tuple(
            MergedDistinction(into_key=d.into_key, from_keys=d.from_keys, lost=d.lost)
            for d in grouping.merged_distinctions
        ),
        unattributed_energy=_unattributed_by_fuel(energy),
        building=BuildingBlock(
            conditioned_floor_area=conversion.conditioned_floor_area, storey_ratio=conversion.storey_ratio
        ),
    )
    raise_for_invariants(
        report,
        zone_names=sources.facts.zones,
        zone_roles={z.zone.name: z.role for z in zones},
        conditioned_floor_area=math.fsum(z.zone.floor_area * z.zone.multiplier for z in conditioned),
        set_parameters=set_leaf_paths(conversion.archetype),
        expected_not_represented=expected,
    )
    return Reduction(archetype=conversion.archetype, report=report)


def _sha256_of_results(sources: SourceData) -> str:
    """The SHA-256 of an in-memory results database without a file (never for fixtures)."""
    import hashlib  # noqa: PLC0415 - rare path

    return hashlib.sha256(repr(sources.results).encode("utf-8")).hexdigest()


# --- report pieces -------------------------------------------------------------------------------


def _report_groups(grouping: Grouping, zones: Sequence[ClassifiedZone]) -> tuple[ReportGroup, ...]:
    by_name = {z.zone.name: z for z in zones}
    total = sum((g.ledger for g in grouping.groups), GroupLedger()).floor_area
    out: list[ReportGroup] = []
    for group in grouping.groups:
        members = tuple(
            GroupMember(
                zone=name,
                multiplier=by_name[name].zone.multiplier,
                floor_area=by_name[name].zone.floor_area,
                space_use=by_name[name].space_use,
                space_use_source=by_name[name].space_use_source,
                exposure=by_name[name].exposure,
            )
            for name in group.ledger.members
        )
        out.append(
            ReportGroup(
                name=group_name(group.key),
                key=group.key,
                members=members,
                floor_area=group.ledger.floor_area,
                floor_area_share=group.ledger.floor_area / total,
                ledger=group.ledger,
            )
        )
    return tuple(out)


def _excluded_zones(zones: Sequence[ClassifiedZone], building: GroupLedger) -> tuple[ExcludedZone, ...]:
    assignments: dict[str, list[EnvelopeAssignment]] = defaultdict(list)
    for assignment in building.excluded_envelope:
        assignments[assignment.source_zone].append(assignment)
    out: list[ExcludedZone] = []
    for zone in zones:
        if zone.role == "conditioned":
            continue
        record = zone.zone
        out.append(
            ExcludedZone(
                zone=record.name,
                multiplier=record.multiplier,
                floor_area=record.floor_area,
                role=zone.role,
                reason=zone.role_reason,
                envelope=tuple(assignments.get(record.name, ())),
            )
        )
    return tuple(out)


# --- what the archetype does not hold (FR-026) ---------------------------------------------------


def _excluded_loads(zones: Sequence[ClassifiedZone]) -> tuple[NotRepresented, ...]:
    """Gains and hot water of zones left out of every group: the archetype carries none of them."""
    entries: list[NotRepresented] = []
    excluded = [z for z in zones if z.role != "conditioned"]
    gains = [(z.zone, g) for z in excluded for g in z.zone.gains if g.design_level > 0.0]
    if gains:
        entries.append(
            NotRepresented(
                feature="Internal gains of excluded zones",
                effect="Gains in plenums, attics, basements and other unconditioned zones heat those "
                "zones; the archetype has no such zones, so they are dropped.",
                objects=tuple(sorted({g.name for _, g in gains})),
                affected_zones=tuple(sorted({zone.name for zone, _ in gains})),
                source="to_sbem",
            )
        )
    water = [(z.zone, r) for z in excluded for r in z.zone.hot_water if float(np.sum(r.volume)) > 0.0]
    if water:
        entries.append(
            NotRepresented(
                feature="Hot water of excluded zones",
                effect="Hot water used in zones left out of every group is not carried by any group.",
                object_type="WaterUse:Equipment",
                objects=tuple(sorted({r.equipment for _, r in water})),
                affected_zones=tuple(sorted({zone.name for zone, _ in water})),
                magnitude=math.fsum(float(np.sum(r.volume)) * zone.multiplier for zone, r in water),
                unit="m3",
                source="hotwater",
            )
        )
    return tuple(entries)


def _unassigned_envelope(hook: EnvelopeHook) -> tuple[NotRepresented, ...]:
    if not hook.unassigned:
        return ()
    return (
        NotRepresented(
            feature="Envelope of excluded zones without a conditioned neighbour",
            effect="Their envelope could not be assigned to any conditioned zone (FR-013), so no group carries it.",
            affected_zones=tuple(sorted(hook.unassigned)),
            source="envelope",
        ),
    )


def _allocated_hot_water(zones: Sequence[ClassifiedZone]) -> tuple[NotRepresented, ...]:
    """State how hot water without a zone was allocated (FR-021); its volume is folded into the groups."""
    allocated = [a for a in _hotwater.allocations(zones) if a.allocated]
    if not allocated:
        return ()
    rules = sorted({a.rule for a in allocated})
    return (
        NotRepresented(
            feature="Building hot water allocated to zones",
            effect=f"Hot water attached to no zone is allocated to zones by {' and '.join(rules)} (FR-021).",
            object_type="WaterUse:Equipment",
            objects=tuple(sorted({a.equipment for a in allocated})),
            affected_zones=tuple(sorted({a.zone for a in allocated if a.volume > 0.0})),
            magnitude=math.fsum(a.volume for a in allocated),
            unit="m3",
            folded_into="WaterUse.FlowRatePerPerson",
            source="hotwater",
        ),
    )


def _unattributed_energy(
    energy: _efficiency.EnergyAttribution, conditioned: Sequence[ClassifiedZone]
) -> tuple[NotRepresented, ...]:
    """Consumption in hours without delivery (standby, pilot lights), listed by FR-022."""
    zones = tuple(sorted(z.zone.name for z in conditioned))
    entries: list[NotRepresented] = []
    for mode, by_fuel in sorted(energy.unattributed.items()):
        for fuel, value in sorted(by_fuel.items()):
            if value > 0.0:
                entries.append(
                    NotRepresented(
                        feature=f"Unattributed {mode.replace('_', ' ')} consumption ({fuel})",
                        effect="Energy consumed in hours without delivered energy in this mode (standby, "
                        "pilot lights); it is not part of the group's efficiency.",
                        affected_zones=zones,
                        magnitude=value,
                        unit="J",
                        source="efficiency",
                    )
                )
    for fuel, value in sorted(energy.unattributed_distribution.items()):
        if value > 0.0:
            entries.append(
                NotRepresented(
                    feature=f"Unattributed pump and heat-rejection energy ({fuel})",
                    effect="Pump and heat-rejection energy in hours without heating or cooling delivery.",
                    affected_zones=zones,
                    magnitude=value,
                    unit="J",
                    source="efficiency",
                )
            )
    return tuple(entries)


def _unattributed_by_fuel(energy: _efficiency.EnergyAttribution) -> dict[Fuel, float]:
    totals: dict[Fuel, float] = defaultdict(float)
    for by_fuel in energy.unattributed.values():
        for fuel, value in by_fuel.items():
            totals[fuel] += value
    for fuel, value in energy.unattributed_distribution.items():
        totals[fuel] += value
    return {fuel: value for fuel, value in sorted(totals.items()) if value != 0.0}


def _unattributed_fans(fans: _fans.FanAttribution) -> tuple[NotRepresented, ...]:
    if not fans.unattributed_fans:
        return ()
    return (
        NotRepresented(
            feature="Fans serving no conditioned zone",
            effect="Their energy is attributed to no group's specific fan power (FR-022a).",
            objects=tuple(sorted(fans.unattributed_fans)),
            magnitude=fans.unattributed_energy,
            unit="J",
            source="fans",
        ),
    )
