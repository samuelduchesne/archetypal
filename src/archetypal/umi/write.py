"""Writing SBEM archetypes as one UMI template library (spec 003, US1, research R12, R13, R14).

`to_umi` runs the writing pipeline of data-model.md; `write_umi` also writes the files.

1. **Layout** (research R12). Each item becomes an archetype with core and perimeter groups, or a
   single group:
   - a `Reduction` (spec 002) already at core/perimeter is taken as it is; a finer one is merged
     with 002's `merge(reduction, Layout.CORE_PERIMETER)`. Each resulting group that merged
     several finest groups is reported (`layout.merged`) with its pre-merge keys, from the
     report's `merged_distinctions`. Until 002's `merge` exists, a finer reduction's archetype
     is merged approximately, as a bare archetype;
   - a bare archetype with other groups is merged approximately (`approximate_merge`): ledgers
     rebuilt from the groups' parameters (`GroupLedger.approximate_from_group`) are grouped
     with 002's `grouping.group`, and each merged group's parameters are derived from the
     summed ledger.
2. **Translation.** Each archetype becomes one building template through the registered
   SBEM → UMI rules: `building.groups` (shares dropped, a single group copied),
   `wwr.uniform`, `window.placement` and `window.equivalent_layer`, and per zone group the
   loads, conditioning, ventilation, hot water, constructions and internal mass.
3. **Assembly** (research R13). Components are keyed by content (their canonical JSON without
   `Name`): the same name and content is one component; a name used for different content gets
   ` #2`, ` #3`, … in order of first appearance (`names.collision`). Duplicate archetype names
   are renamed the same way. Only components a template reaches are written.
4. **Text** (`archetypal.umi.serialise`), then the report; strict mode raises before anything
   is written.
"""

from __future__ import annotations

import importlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple, Protocol, cast

import numpy as np
from epinterface.sbem.archetype import Archetype, ZoneGroup
from epinterface.sbem.components.envelope import GlazingConstructionSimpleComponent

from archetypal.errors import InputError
from archetypal.reduction.envelope import (
    ASSEMBLY_TYPES,
    equivalent_construction,
    internal_mass_construction,
    window_construction,
)
from archetypal.reduction.grouping import Group, group
from archetypal.reduction.ledger import APPROXIMATE_PATHS, GroupLedger
from archetypal.reduction.options import Layout
from archetypal.reduction.schedules import RunPeriodCalendar, calendar_year, project, to_year_component
from archetypal.umi._format import (
    BuildingTemplate,
    FormatModel,
    GasMaterial,
    GlazingMaterial,
    LibraryComponent,
    MaterialLayer,
    WindowConstruction,
    WindowSettings,
    ZoneDefinition,
)
from archetypal.umi.correspondence import MappingStatus, mappings_for
from archetypal.umi.read import LOSS_SUFFIX
from archetypal.umi.report import Findings, Loss, LossKind, Note, NoteKind, SourceInfo, TranslationReport
from archetypal.umi.rules._common import RuleContext, constant_year_schedule, identity_to_umi
from archetypal.umi.rules.building import (
    CORE_GROUP,
    NAMED_FROM,
    PERIMETER_GROUP,
    UniqueNames,
    collision_loss,
    template_zones,
    umi_names,
    window_settings_name,
    wwr_to_umi,
)
from archetypal.umi.rules.conditioning import ALWAYS_ON, conditioning_to_umi
from archetypal.umi.rules.hotwater import dhw_to_umi
from archetypal.umi.rules.loads import daylighting_to_umi, internal_mass_to_umi, loads_to_umi
from archetypal.umi.rules.materials import assemblies_to_umi, construction_to_umi
from archetypal.umi.rules.schedules import year_to_umi
from archetypal.umi.rules.ventilation import zone_ventilation_to_umi
from archetypal.umi.rules.windows import equivalent_layer, template_window
from archetypal.umi.serialise import NAME_GROUPS, serialise

if TYPE_CHECKING:
    from collections.abc import Sequence

    from epinterface.sbem.components.schedules import YearComponent, YearScheduleCategory
    from epinterface.sbem.components.zones import ZoneComponent
    from numpy.typing import NDArray
    from pydantic import JsonValue

    from archetypal.umi._format import YearSchedule

__all__ = ["ArchetypeLike", "CorePerimeter", "ReductionLike", "UmiExport", "approximate_merge", "to_umi", "write_umi"]

_DIRECTION: Final = "sbem_to_umi"
_CALENDAR: Final = RunPeriodCalendar(calendar_year(1, 1, 0))
_SECONDS_PER_HOUR: Final = 3600.0
_DAYS_PER_YEAR: Final = 365.0
_MERGED: Final = "merged"
_DEFAULT_WINDOW: Final = GlazingConstructionSimpleComponent(
    Name="Default single glazing", UValue=5.8, SHGF=0.81, TVis=0.88, Type="Single"
)
# Rules without a function whose UMI fields take Basilisk's defaults on writing (research R6).
_DEFAULTED_RULES: Final = (
    "material.environmental",
    "construction.environmental",
    "schedule.metadata",
    "window.settings",
)


class ReductionLike(Protocol):
    """What the writer reads of spec 002's `Reduction`: its archetype and its report."""

    @property
    def archetype(self) -> Archetype:
        """The reduced archetype."""
        ...

    @property
    def report(self) -> Any:
        """The reduction report; its `merged_distinctions` are read."""
        ...


ArchetypeLike = Archetype | ReductionLike
"""An item `to_umi` and `write_umi` accept: a bare SBEM archetype or a 002 `Reduction`."""


class CorePerimeter(NamedTuple):
    """An archetype brought to core and perimeter groups (or one group), and what that lost."""

    archetype: Archetype
    """The archetype, with core and perimeter groups or a single group."""
    losses: tuple[Loss, ...]
    """The merged groups and the parameters merged approximately."""


# --- Layout (research R12) --------------------------------------------------------------------------


def _is_core_perimeter(archetype: Archetype) -> bool:
    groups = archetype.Groups
    return len(groups) == 1 or (len(groups) == 2 and {g.Exposure for g in groups} == {"core", "perimeter"})  # noqa: PLR2004


def _get(model: Any, path: str) -> Any:
    node = model
    for step in path.split(".") if path else ():
        if node is None:
            return None
        node = getattr(node, step)
    return node


def _replace(model: Any, path: str, value: object) -> Any:
    head, _, rest = path.partition(".")
    if not rest:
        return model.model_copy(update={head: value})
    return model.model_copy(update={head: _replace(getattr(model, head), rest, value)})


def _dump(value: Any) -> str:
    return json.dumps(value.model_dump(mode="json") if hasattr(value, "model_dump") else value, sort_keys=True)


def _differ(members: Sequence[ZoneGroup], path: str) -> bool:
    return len({_dump(_get(member.Zone, path)) for member in members}) > 1


def _schedule(profile: NDArray[np.float64], *, name: str, category: YearScheduleCategory) -> YearComponent:
    limits = "Temperature" if category == "Setpoint" else "Fraction"
    days = project(profile, _CALENDAR)
    if limits == "Fraction":
        days = np.clip(days, 0.0, 1.0)
    return to_year_component(days, name=name, category=category, limits=limits)


def _merged_name(name: str) -> str:
    return f"{name} ({_MERGED})"


def _largest_with(members: Sequence[ZoneGroup], path: str) -> Any:
    """The component at `path` of the largest member that has one."""
    for member in members:
        component = _get(member.Zone, path)
        if component is not None:
            return component
    return None


class _ZoneMerger:
    """Derives one zone definition from the summed ledger of several groups (research R12)."""

    def __init__(self, members: Sequence[ZoneGroup], ledger: GroupLedger) -> None:
        # Largest share first; the first member wins ties.
        self.members = sorted(members, key=lambda member: -(member.FloorAreaShare or 0.0))
        self.ledger = ledger
        self.area = ledger.floor_area
        self.zone: ZoneComponent = self.members[0].Zone

    def set(self, path: str, value: object) -> None:
        self.zone = _replace(self.zone, path, value)

    def merge(self) -> ZoneComponent:
        base = self.zone
        self.gains()
        self.thermostat()
        self.systems()
        self.ventilation()
        self.hot_water()
        self.infiltration()
        self.assemblies()
        self.window()
        merged = self.zone
        for path in ("", *NAMED_FROM.values(), "Operations", "Envelope"):
            component = _get(merged, path)
            if component is not None and _dump(component) != _dump(_get(base, path)):
                merged = _replace(merged, f"{path}.Name" if path else "Name", _merged_name(component.Name))
        return merged

    def gains(self) -> None:
        for path, kind, density, category in (
            ("Operations.SpaceUse.Occupancy", "people", "PeopleDensity", "Occupancy"),
            ("Operations.SpaceUse.Lighting", "lights", "PowerDensity", "Lighting"),
            ("Operations.SpaceUse.Equipment", "electric", "PowerDensity", "Equipment"),
        ):
            if not _differ(self.members, path):
                continue
            totals = self.ledger.gains.get(kind)
            component = _get(self.zone, path)
            if totals is None or totals.installed <= 0:
                self.set(path, component.model_copy(update={"IsOn": False}))
                continue
            schedule = _schedule(
                totals.hourly / totals.installed, name=_merged_name(component.Schedule.Name), category=category
            )
            update = {density: totals.installed / self.area, "Schedule": schedule, "IsOn": True}
            self.set(path, component.model_copy(update=update))

    def thermostat(self) -> None:
        path = "Operations.SpaceUse.Thermostat"
        if not _differ(self.members, path):
            return
        thermostat = _get(self.zone, path)
        update: dict[str, object] = {}
        for key, totals, pick in (
            ("Heating", self.ledger.heating_setpoint, np.max),
            ("Cooling", self.ledger.cooling_setpoint, np.min),
        ):
            values = totals.value
            if values is None:
                continue
            schedule = getattr(thermostat, f"{key}Schedule")
            update[f"{key}Schedule"] = _schedule(values, name=_merged_name(schedule.Name), category="Setpoint")
            update[f"{key}Setpoint"] = float(pick(values))
        self.set(path, thermostat.model_copy(update=update))

    def systems(self) -> None:
        path = "Operations.HVAC.ConditioningSystems"
        if not _differ(self.members, path):
            return
        systems = _get(self.zone, path)
        update: dict[str, object] = {}
        for key, mode in (("Heating", "heating"), ("Cooling", "cooling")):
            system = _largest_with(self.members, f"{path}.{key}")
            totals = self.ledger.energy.get(mode)
            efficiency = None if totals is None else totals.rated_efficiency
            if system is not None and efficiency is not None and system.DistributionCOP > 0:
                system = system.model_copy(update={"SystemCOP": efficiency / system.DistributionCOP})
            update[key] = system
        self.set(path, systems.model_copy(update=update))

    def ventilation(self) -> None:
        path = "Operations.HVAC.Ventilation"
        if not _differ(self.members, path):
            return
        air = self.ledger.outdoor_air
        peak = float(air.hourly.max()) if air.hourly.size else 0.0
        if peak <= 0:
            return
        ventilation = _get(self.zone, path)
        natural = any(_get(m.Zone, path).Provider in {"Natural", "Both"} for m in self.members)
        update = {
            "FreshAirPerFloorArea": peak / self.area,
            "FreshAirPerPerson": 0.0,
            "Schedule": _schedule(air.hourly / peak, name=_merged_name(ventilation.Schedule.Name), category="Ventilation"),
            "Provider": "Both" if natural else "Mechanical",
            "HRV": max(sorted(air.hrv_weighted), key=lambda key: air.hrv_weighted[key]),
            "Economizer": max(sorted(air.economiser_weighted), key=lambda key: air.economiser_weighted[key]),
        }
        self.set(path, ventilation.model_copy(update=update))

    def hot_water(self) -> None:
        use_path, dhw_path = "Operations.SpaceUse.WaterUse", "Operations.DHW"
        if not (_differ(self.members, use_path) or _differ(self.members, dhw_path)):
            return
        water = self.ledger.hot_water
        people = self.ledger.gains.get("people")
        volume = float(water.volume.sum()) if water.volume.size else 0.0
        rise = water.mean_rise
        if volume <= 0 or people is None or people.installed <= 0 or rise is None:
            return
        water_use = _get(self.zone, use_path)
        schedule = _schedule(
            water.volume / float(water.volume.max()), name=_merged_name(water_use.Schedule.Name), category="WaterUse"
        )
        flow = volume / (_DAYS_PER_YEAR * people.installed)
        self.set(use_path, water_use.model_copy(update={"FlowRatePerPerson": flow, "Schedule": schedule}))
        dhw = _get(self.zone, dhw_path)
        update: dict[str, object] = {"IsOn": True, "WaterSupplyTemperature": dhw.WaterTemperatureInlet + rise}
        totals = self.ledger.energy.get("hot_water")
        if totals is not None and totals.rated_efficiency is not None and dhw.DistributionCOP > 0:
            update["SystemCOP"] = totals.rated_efficiency / dhw.DistributionCOP
        self.set(dhw_path, dhw.model_copy(update=update))

    def infiltration(self) -> None:
        path = "Envelope.Infiltration"
        flow = self.ledger.infiltration.design_flow
        if not _differ(self.members, path) or flow <= 0:
            return
        totals = self.ledger.infiltration
        infiltration = _get(self.zone, path)
        update = {
            "IsOn": True,
            "AirChangesPerHour": flow * _SECONDS_PER_HOUR / self.area,
            "ConstantCoefficient": totals.constant_weighted / flow,
            "TemperatureCoefficient": totals.temperature_weighted / flow,
            "WindVelocityCoefficient": totals.velocity_weighted / flow,
            "WindVelocitySquaredCoefficient": totals.velocity_squared_weighted / flow,
        }
        self.set(path, infiltration.model_copy(update=update))

    def assemblies(self) -> None:
        for envelope_class, slot in ASSEMBLY_TYPES.items():
            path = f"Envelope.Assemblies.{slot}Assembly"
            totals = self.ledger.envelope.get(envelope_class)
            if not _differ(self.members, path) or totals is None:
                continue
            base = _get(self.zone, path)
            try:
                assembly = equivalent_construction(totals, envelope_class, name=_merged_name(base.Name))
            except ValueError:
                continue
            self.set(path, assembly)
        paths = ("Envelope.Assemblies.InternalMassAssembly", "Envelope.Assemblies.InternalMassExposedAreaPerArea")
        if any(_differ(self.members, path) for path in paths):
            base = _get(self.zone, paths[0])
            name = _merged_name(base.Name if base is not None else "Internal mass")
            mass = internal_mass_construction(
                self.ledger.internal_mass_capacity, self.ledger.internal_mass_area, name=name
            )
            self.set(paths[0], mass)
            self.set(paths[1], None if mass is None else self.ledger.internal_mass_area / self.area)

    def window(self) -> None:
        path = "Envelope.Window"
        if not _differ(self.members, path):
            return
        base = _get(self.zone, path)
        name = _merged_name(base.Name if base is not None else "Window")
        window = window_construction(self.ledger.window_by_orientation, name=name)
        if window is not None:
            self.set(path, window)


def approximate_merge(archetype: Archetype) -> CorePerimeter:
    """Merge an archetype's groups to core and perimeter without its reduction (research R12).

    An archetype that already has core and perimeter groups, or a single group, is returned
    as it is. Otherwise each group's ledger is rebuilt from its parameters
    (`GroupLedger.approximate_from_group`, floor area = share × 1 m²), the ledgers are grouped
    by exposure with 002's `grouping.group` (by nothing when a group has no exposure, giving
    one group), and each merged group's parameters are derived from its summed ledger:
    densities and setpoints area-weighted with their profiles projected onto SBEM's
    representative days, outdoor air as peak flow per area with its profile, hot water as
    volume per person-day. Parameters every member agrees on are kept exactly. The others in
    `APPROXIMATE_PATHS` are floor-area weighted and reported as `approximate`; each merged
    group is reported as `merged` with the names of the groups it holds.

    Args:
        archetype: The archetype.

    Returns:
        The archetype with core and perimeter groups (shares summed) or a single group (share
        unset), and the losses.

    Raises:
        InputError: The archetype has more than two groups and unset shares, which cannot be
            weighted.
    """
    if _is_core_perimeter(archetype):
        return CorePerimeter(archetype, ())
    groups = list(archetype.Groups)
    subject = archetype.Name
    if any(g.FloorAreaShare is None for g in groups):
        msg = (
            f"has {len(groups)} groups with unset floor-area shares, which cannot be weighted to merge them to "
            "core and perimeter; set the shares, or write the archetype with its reduction"
        )
        raise InputError(subject, msg)
    layout = Layout.SINGLE_ZONE if any(g.Exposure is None for g in groups) else Layout.CORE_PERIMETER
    rebuilt = {g.Name: GroupLedger.approximate_from_group(g, cast("float", g.FloorAreaShare)) for g in groups}
    pre = [Group(key=(g.Name, g.Exposure or PERIMETER_GROUP), ledger=rebuilt[g.Name].ledger) for g in groups]
    grouping = group(pre, layout, 0.0)
    by_name = {g.Name: g for g in groups}
    losses: list[Loss] = []
    merged_groups: list[ZoneGroup] = []
    for result in grouping.groups:
        members = [by_name[name] for name in result.ledger.members]
        exposures = {member.Exposure for member in members}
        exposure = next(iter(exposures)) if len(exposures) == 1 else None
        name = CORE_GROUP if exposure == "core" else PERIMETER_GROUP
        if len(members) == 1:
            zone = members[0].Zone
        else:
            zone = _ZoneMerger(members, result.ledger).merge()
            losses.append(
                Loss(
                    kind=LossKind.MERGED,
                    subject=subject,
                    location=name,
                    value=cast("JsonValue", sorted(member.Name for member in members)),
                    rule="layout.merged",
                    reason="A UMI template has core and perimeter zones only: these groups were merged into one, "
                    "weighted by their floor-area shares.",
                )
            )
            approximate = {path for member in members for path in rebuilt[member.Name].approximate}
            losses.extend(
                Loss(
                    kind=LossKind.APPROXIMATE,
                    subject=subject,
                    location=f"{name}.{path}",
                    value=cast("JsonValue", {member.Name: _json(_get(member.Zone, path)) for member in members}),
                    replacement=_json(_get(zone, path)),
                    rule="layout.merged",
                    reason="Merging this needs surface areas or energies the archetype does not hold, so the groups' "
                    "values were weighted by floor area.",
                )
                for path in APPROXIMATE_PATHS
                if path in approximate and _differ(members, path)
            )
        share = result.ledger.floor_area if len(grouping.groups) > 1 else None
        merged_groups.append(ZoneGroup(Name=name, Zone=zone, FloorAreaShare=share, Exposure=exposure))
    merged = archetype.model_copy(update={"Groups": merged_groups})
    return CorePerimeter(merged, tuple(losses))


def _json(value: Any) -> JsonValue:
    if not hasattr(value, "model_dump"):
        return cast("JsonValue", value)
    return cast("JsonValue", value.model_dump(mode="json", exclude_none=True))


def _from_reduction(reduction: ReductionLike) -> CorePerimeter:
    """Bring a 002 reduction to core and perimeter, listing the groups merged (research R12)."""
    source = reduction
    if not _is_core_perimeter(reduction.archetype):
        merge = getattr(importlib.import_module("archetypal.reduction"), "merge", None)
        if merge is None:  # spec 002's merge (T070) is not implemented yet
            return approximate_merge(reduction.archetype)
        source = merge(reduction, Layout.CORE_PERIMETER)
    subject = source.archetype.Name
    losses = [
        Loss(
            kind=LossKind.MERGED,
            subject=subject,
            location=" / ".join(entry.into_key) or "building",
            value=cast("JsonValue", [list(key) for key in entry.from_keys]),
            rule="layout.merged",
            reason="A UMI template has core and perimeter zones only: the reduction's groups with these keys were "
            "merged into one by spec 002's merge.",
        )
        for entry in getattr(source.report, "merged_distinctions", ())
        if len(entry.from_keys) > 1
    ]
    return CorePerimeter(source.archetype, tuple(losses))


def _core_perimeter(item: ArchetypeLike) -> CorePerimeter:
    if isinstance(item, Archetype):
        return approximate_merge(item)
    return _from_reduction(item)


# --- Translation --------------------------------------------------------------------------------------


class _TemplateWriter:
    """Translates one archetype into one building template, collecting its findings."""

    def __init__(self, subject: str) -> None:
        self.subject = subject
        self.findings = Findings()
        self.context = RuleContext(subject, "", _DIRECTION)

    def schedule(self, year: YearComponent, path: str) -> YearSchedule:
        return year_to_umi(year, self.subject, path, self.findings)

    def zone(self, zone: ZoneComponent, group_name: str) -> ZoneDefinition:
        """The UMI zone definition of an SBEM zone definition."""
        context = RuleContext(self.subject, group_name, _DIRECTION, self.context.findings)
        operations = zone.Operations
        space_use = operations.SpaceUse
        hvac = operations.HVAC
        envelope = zone.Envelope
        assemblies = envelope.Assemblies
        assemblies_path = f"{group_name}.Envelope.Assemblies"
        constructions = assemblies_to_umi(assemblies, self.subject, assemblies_path, self.findings)
        mass = assemblies.InternalMassAssembly
        mass_umi = (
            None
            if mass is None
            else construction_to_umi(mass, self.subject, f"{assemblies_path}.InternalMassAssembly", self.findings)
        )
        fallback = constructions.partition
        if fallback is None:  # pragma: no cover - assemblies_to_umi fills every slot
            msg = f"{assemblies_path}: no partition construction"
            raise ValueError(msg)
        mass_construction, exposed = internal_mass_to_umi(
            mass_umi, assemblies.InternalMassExposedAreaPerArea, fallback=fallback, context=context.child("Envelope.Assemblies")
        )
        flags = {
            f"is_{slot}_adiabatic": bool(getattr(assemblies, f"Is{slot.capitalize()}Adiabatic", False))
            for slot in ("facade", "ground", "partition", "roof", "slab")
        }
        constructions = constructions.model_copy(update=flags)
        # Fields of later fork versions (UP-9 work), read only when the installed fork has them.
        partition_area: float = getattr(assemblies, "PartitionAreaPerFloorArea", 0.0)
        if partition_area:
            context.lose(
                "Envelope.Assemblies.PartitionAreaPerFloorArea",
                partition_area,
                rule="building.partition_ratio",
                reason="A UMI zone definition has no partition area; the template's PartitionRatio is not written "
                "from it.",
            )
        window_settings = getattr(envelope, "WindowSettings", None)
        if window_settings is not None:
            context.lose(
                "Envelope.WindowSettings",
                _json(window_settings),
                rule="window.settings",
                reason="The window settings of an SBEM zone are not written to UMI yet; Basilisk's defaults are.",
                upstream="UP-9",
            )
        self.context.findings.extend(umi_names(zone, subject=self.subject, group=group_name).losses)
        fields: dict[str, object] = {
            **identity_to_umi(operations, context.child("Operations")),
            "Name": zone.Name,
            "loads": loads_to_umi(space_use, schedule=self.schedule, context=context),
            "conditioning": conditioning_to_umi(hvac, space_use.Thermostat, context=context),
            "ventilation": zone_ventilation_to_umi(envelope, hvac.Ventilation, schedule=self.schedule, context=context),
            "domestic_hot_water": dhw_to_umi(
                operations.DHW, space_use.WaterUse, space_use.Occupancy, schedule=self.schedule, context=context
            ),
            "constructions": constructions,
            "internal_mass_construction": mass_construction,
            "internal_mass_exposed_per_floor_area": exposed,
            **daylighting_to_umi(ZoneDefinition, context=context),
        }
        return ZoneDefinition.model_validate(fields)

    def window(self, archetype: Archetype) -> WindowSettings:
        """The template's window settings, from the perimeter group's window (research R8)."""
        chosen, losses = template_window({g.Name: g.Zone.Envelope.Window for g in archetype.Groups}, subject=self.subject)
        self.context.findings.extend(losses)
        location = next(
            (f"{g.Name}.Envelope.Window" for g in archetype.Groups if g.Zone.Envelope.Window is chosen),
            "Envelope.Window",
        )
        if chosen is None:
            construction, _ = equivalent_layer(_DEFAULT_WINDOW, subject=self.subject, location=location)
            self.context.note(
                location,
                _DEFAULT_WINDOW.Name,
                rule="window.placement",
                reason="The archetype has no window; UMI needs one, so a single clear glazing was written.",
            )
        elif isinstance(chosen, GlazingConstructionSimpleComponent):
            construction, layer_losses = equivalent_layer(chosen, subject=self.subject, location=location)
            self.context.findings.extend(layer_losses)
        else:
            construction = _layered(chosen)
        always_on = constant_year_schedule(ALWAYS_ON, 1.0)
        self.context.note(
            "WindowSettings",
            [row.umi_key for row in mappings_for("window.settings") if row.status is MappingStatus.UPSTREAM],
            rule="window.settings",
            reason="SBEM holds no window settings for UMI yet: Basilisk's defaults were written, with always-on "
            "availability schedules and the shading system off, as SBEM simulates no shading.",
        )
        return WindowSettings.model_validate({
            "Name": window_settings_name(construction.name or ""),
            "Construction": construction,
            "AfnWindowAvailability": always_on,
            "ShadingSystemAvailabilitySchedule": always_on,
            "ZoneMixingAvailabilitySchedule": always_on,
            "IsShadingSystemOn": False,
        })

    def template(self, archetype: Archetype) -> BuildingTemplate:
        zones = template_zones(archetype)
        self.context.findings.extend(zones.losses)
        names = {id(g.Zone): g.Name for g in archetype.Groups}
        core = self.zone(zones.core, names.get(id(zones.core), CORE_GROUP))
        perimeter = core if zones.perimeter is zones.core else self.zone(zones.perimeter, names[id(zones.perimeter)])
        ratio = wwr_to_umi(archetype.Geometry, subject=self.subject)
        self.context.findings.extend([*ratio.losses, *ratio.notes])
        for rule_id in _DEFAULTED_RULES[:-1]:
            keys = sorted({row.umi_key for row in mappings_for(rule_id) if row.status is MappingStatus.UPSTREAM})
            self.context.note(
                "",
                cast("JsonValue", keys),
                rule=rule_id,
                reason="SBEM has no counterpart for these fields yet: every component written carries Basilisk's "
                "defaults.",
                kind=NoteKind.DEFAULTED,
            )
        return BuildingTemplate.model_validate({
            "Name": self.subject,
            "Core": core,
            "Perimeter": perimeter,
            "Windows": self.window(archetype),
            "DefaultWindowToWallRatio": ratio.value,
        })

    @property
    def all_findings(self) -> list[Loss | Note]:
        return [*self.context.findings, *self.findings.losses, *self.findings.notes]


def _layered(window: Any) -> WindowConstruction:
    """A layered SBEM window as UMI glazing and gas layers, exactly."""
    layers: list[MaterialLayer[GlazingMaterial | GasMaterial]] = []
    for layer in window.Layers:
        if hasattr(layer, "GlazingMaterial"):
            material = layer.GlazingMaterial
            umi: GlazingMaterial | GasMaterial = GlazingMaterial.model_validate({
                "Name": material.Name,
                **{
                    alias: getattr(material, alias)
                    for alias in (
                        "Conductivity",
                        "SolarTransmittance",
                        "SolarReflectanceFront",
                        "SolarReflectanceBack",
                        "VisibleTransmittance",
                        "VisibleReflectanceFront",
                        "VisibleReflectanceBack",
                        "IRTransmittance",
                        "IREmissivityFront",
                        "IREmissivityBack",
                        "DirtFactor",
                    )
                },
                "Density": material.Density or 0.0,
            })
        else:
            material = layer.GasMaterial
            umi = GasMaterial.model_validate({"Name": material.Name, "Type": str(material.GasType).upper()})
        layers.append(MaterialLayer[GlazingMaterial | GasMaterial](Material=umi, Thickness=layer.Thickness))
    return WindowConstruction.model_validate({"Name": window.Name, "Layers": tuple(layers)})


# --- Assembly (research R13) ------------------------------------------------------------------------


class _Assembler:
    """Shares equal components and renames clashing names, in order of first appearance."""

    def __init__(self) -> None:
        self.namers: dict[str, UniqueNames] = {}
        self.memo: dict[tuple[type[FormatModel], str | None, str], FormatModel] = {}
        self.losses: list[Loss] = []

    def component(self, model: FormatModel, pointer: str, subject: str) -> FormatModel:
        updates: dict[str, object] = {}
        for name, info in type(model).model_fields.items():
            value: object = getattr(model, name)
            new = self.value(value, f"{pointer}/{info.alias or name}", subject)
            if new is not value:
                updates[name] = new
        if updates:
            model = model.model_copy(update=updates)
        if not isinstance(model, LibraryComponent) or isinstance(model, BuildingTemplate):
            return model
        content = json.dumps(model.model_dump(mode="json", exclude={"name"}), sort_keys=True)
        key = (type(model), model.name, content)
        hit = self.memo.get(key)
        if hit is not None:
            return hit
        original = model.name or ""
        namer = self.namers.setdefault(NAME_GROUPS[type(model)], UniqueNames())
        unique = namer.assign(original, (type(model).__name__, content))
        if unique != original:
            model = model.model_copy(update={"name": unique})
            self.losses.append(collision_loss(subject=subject, location=pointer, original=original, renamed=unique))
        self.memo[key] = model
        return model

    def value(self, value: object, pointer: str, subject: str) -> object:
        if isinstance(value, FormatModel):
            return self.component(value, pointer, subject)
        if isinstance(value, tuple):
            items = cast("tuple[object, ...]", value)
            new = tuple(self.value(item, f"{pointer}/{index}", subject) for index, item in enumerate(items))
            return value if all(a is b for a, b in zip(new, items, strict=True)) else new
        return value


# --- Public interface ------------------------------------------------------------------------------


@dataclass(frozen=True)
class UmiExport:
    """A UMI library written from SBEM archetypes, and the report of the translation.

    Attributes:
        text: The library, as Basilisk Core JSON.
        report: What the translation lost and assumed.
    """

    text: str
    report: TranslationReport

    def write(self, path: str | os.PathLike[str], *, overwrite: bool = False) -> tuple[Path, Path]:
        """Write the library at `path` and the report at `<stem>.loss.json` beside it.

        Both files are written to temporary files first and then renamed, so neither is left
        half written. No file is written when one exists and `overwrite` is false.

        Args:
            path: The library file; its folder is created if needed.
            overwrite: Replace existing files.

        Returns:
            The library's path and the report's path.

        Raises:
            InputError: A file exists and `overwrite` is false.
        """
        library = Path(path)
        loss = library.with_name(f"{library.stem}{LOSS_SUFFIX}")
        if not overwrite:
            for target in (library, loss):
                if target.exists():
                    raise InputError(target, "already exists; pass overwrite=True to replace it")
        library.parent.mkdir(parents=True, exist_ok=True)
        staged: list[tuple[Path, Path]] = []
        try:
            for target, text in ((library, self.text), (loss, self.report.to_json())):
                handle, temporary = tempfile.mkstemp(dir=target.parent, prefix=f".{target.name}.", suffix=".tmp")
                with os.fdopen(handle, "wb") as stream:
                    stream.write(text.encode("utf-8"))
                staged.append((Path(temporary), target))
            for temporary, target in staged:
                temporary.replace(target)
        finally:
            for temporary, _ in staged:
                temporary.unlink(missing_ok=True)
        return library, loss


def _export(items: Sequence[ArchetypeLike], *, strict: bool, path: str | os.PathLike[str] | None) -> UmiExport:
    if not items:
        raise InputError(path if path is not None else "archetypes", "no archetype to write; give at least one")
    layouts = [_core_perimeter(item) for item in items]
    findings: list[Loss | Note] = []
    namer = UniqueNames()
    subjects: list[str] = []
    for number, (archetype, _) in enumerate(layouts):
        subject = namer.assign(archetype.Name, number)
        subjects.append(subject)
        if subject != archetype.Name:
            findings.append(
                collision_loss(
                    subject=subject, location=f"/BuildingTemplates/{number}", original=archetype.Name, renamed=subject
                )
            )
    assembler = _Assembler()
    templates: list[BuildingTemplate] = []
    for number, ((archetype, losses), subject) in enumerate(zip(layouts, subjects, strict=True)):
        findings.extend(loss if loss.subject == subject else loss.model_copy(update={"subject": subject}) for loss in losses)
        writer = _TemplateWriter(subject)
        template = writer.template(archetype)
        findings.extend(writer.all_findings)
        templates.append(
            cast("BuildingTemplate", assembler.component(template, f"/BuildingTemplates/{number}", subject))
        )
    findings.extend(assembler.losses)
    text = serialise(templates)
    unique = _unique(findings)
    report = TranslationReport(
        direction=_DIRECTION,
        source=SourceInfo.current(path),
        subjects=subjects,
        losses=[finding for finding in unique if isinstance(finding, Loss)],
        notes=[finding for finding in unique if isinstance(finding, Note)],
    )
    if strict:
        report.raise_for_losses(path if path is not None else ", ".join(subjects))
    return UmiExport(text=text, report=report)


def _unique(findings: Sequence[Loss | Note]) -> list[Loss | Note]:
    seen: set[str] = set()
    kept: list[Loss | Note] = []
    for finding in findings:
        key = f"{type(finding).__name__}:{finding.model_dump_json()}"
        if key not in seen:
            seen.add(key)
            kept.append(finding)
    return kept


def to_umi(archetypes: Sequence[ArchetypeLike], *, strict: bool = False) -> UmiExport:
    """Translate SBEM archetypes into one UMI template library, without writing it.

    One building template per archetype, named after it (a repeated name gets ` #2`, …).
    Archetypes with groups other than core and perimeter are merged first: exactly through
    002's `merge` for a `Reduction`, approximately for a bare archetype (`approximate_merge`).
    Equal components are written once. Equal inputs give identical text (FR-012).

    Example:
        ```python
        from archetypal import read_umi
        from archetypal.umi import to_umi

        archetypes = read_umi("BostonTemplateLibrary.json").archetypes
        export = to_umi(archetypes)
        print(export.report.summary)
        ```

    Args:
        archetypes: SBEM archetypes or 002 reductions, in the order their templates are written.
        strict: Raise `LossyTranslationError` when anything is lost, after the whole
            translation.

    Returns:
        The library text and the report.

    Raises:
        InputError: `archetypes` is empty, or an archetype has more than two groups and unset
            shares.
        LossyTranslationError: `strict` is set and the report lists losses.
    """
    return _export(archetypes, strict=strict, path=None)


def write_umi(
    archetypes: Sequence[ArchetypeLike],
    path: str | os.PathLike[str],
    *,
    strict: bool = False,
    overwrite: bool = False,
) -> TranslationReport:
    """Write SBEM archetypes as one UMI template library, with its loss report beside it.

    The library is written at `path` and the report at `<stem>.loss.json`, only after the
    whole translation succeeds; in strict mode nothing is written when anything is lost. See
    `to_umi` for the translation.

    Example:
        ```python
        from archetypal import read_umi, write_umi

        archetypes = read_umi("BostonTemplateLibrary.json").archetypes
        report = write_umi(archetypes, "library.json")
        print(report.summary)
        ```

    Args:
        archetypes: SBEM archetypes or 002 reductions, in the order their templates are written.
        path: The library file (UMI's JSON).
        strict: Raise `LossyTranslationError`, writing nothing, when anything is lost.
        overwrite: Replace existing files.

    Returns:
        The report, as written to `<stem>.loss.json`.

    Raises:
        InputError: `archetypes` is empty, an archetype has more than two groups and unset
            shares, or a file exists and `overwrite` is false.
        LossyTranslationError: `strict` is set and the report lists losses.
    """
    export = _export(archetypes, strict=strict, path=path)
    export.write(path, overwrite=overwrite)
    return export.report
