"""Writing SBEM archetypes as one UMI template library (spec 003, US1, research R12, R13, R14).

`to_umi` runs the writing pipeline of data-model.md; `write_umi` also writes the files.

1. **Layout** (research R12). Each item becomes an archetype with core and perimeter groups, or a
   single group:
   - a `Reduction` (spec 002) already at core/perimeter is taken as it is; a finer one is merged
     with 002's `merge(reduction, Layout.CORE_PERIMETER)`. Each resulting group that merged
     several finest groups is reported (`layout.merged`) with its pre-merge keys, from the
     report's `merged_distinctions`. The merge is exact: it starts from the report's
     pre-threshold ledgers, so it equals reducing the model directly to core/perimeter;
   - a bare archetype with other groups is merged approximately (`approximate_merge`): ledgers
     rebuilt from the groups' parameters (`GroupLedger.approximate_from_group`) are grouped
     with 002's `grouping.group`, and each merged group's parameters are derived from the
     summed ledger with 002's `to_sbem` functions where the rebuilt ledger holds what they need
     (gains, setpoint schedules, outdoor air, hot water) and 002's envelope functions.
2. **Translation.** Each archetype becomes one building template through the registered
   SBEM → UMI rules: `building.groups` (shares dropped, a single group copied),
   `wwr.uniform`, `window.placement`, `window.layers` and `window.settings`, the template's
   metadata, structure and partition ratio (UP-9), and per zone group the loads, conditioning,
   ventilation, hot water, constructions and internal mass.
3. **Assembly** (research R13). Components are keyed by content (their canonical JSON without
   `Name`): the same name and content is one component; a name used for different content gets
   ` #2`, ` #3`, … in order of first appearance (`names.collision`). Duplicate archetype names
   are renamed the same way. Only components a template reaches are written.
4. **Text** (`archetypal.umi.serialise`), then the report; strict mode raises before anything
   is written.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, NamedTuple, Protocol, TypeVar, cast

from epinterface.sbem.archetype import Archetype, ZoneGroup
from epinterface.sbem.components.envelope import GlazingConstructionSimpleComponent

from archetypal.errors import InputError
from archetypal.io import write_atomically
from archetypal.reduction.envelope import (
    ASSEMBLY_TYPES,
    equivalent_construction,
    internal_mass_construction,
    window_construction,
)
from archetypal.reduction.grouping import Group, group
from archetypal.reduction.ledger import APPROXIMATE_PATHS, GainKind, GroupLedger, Mode
from archetypal.reduction.options import Layout
from archetypal.reduction.schedules import RunPeriodCalendar, calendar_year
from archetypal.reduction.to_sbem import equipment, lighting, occupancy, thermostat, ventilation, water_use
from archetypal.reduction.to_sbem import infiltration as infiltration_component
from archetypal.umi._format import (
    BuildingTemplate,
    FormatModel,
    LibraryComponent,
    WindowSettings,
    ZoneDefinition,
)
from archetypal.umi.read import LOSS_SUFFIX
from archetypal.umi.report import Findings, Loss, LossKind, Note, SourceInfo, TranslationReport
from archetypal.umi.rules._common import RuleContext, identity_to_umi
from archetypal.umi.rules.building import (
    CORE_GROUP,
    DERIVED_NAMES,
    NAMED_FROM,
    PERIMETER_GROUP,
    UniqueNames,
    collision_loss,
    derived_name,
    partition_ratio_to_umi,
    structure_to_umi,
    template_metadata_notes,
    template_metadata_to_umi,
    template_zones,
    umi_names,
    wwr_to_umi,
)
from archetypal.umi.rules.conditioning import conditioning_to_umi
from archetypal.umi.rules.hotwater import dhw_to_umi
from archetypal.umi.rules.loads import daylighting_to_umi, internal_mass_to_umi, loads_to_umi
from archetypal.umi.rules.materials import assemblies_to_umi, construction_to_umi
from archetypal.umi.rules.schedules import year_to_umi
from archetypal.umi.rules.ventilation import zone_ventilation_to_umi
from archetypal.umi.rules.windows import layers_to_umi, settings_to_umi, template_settings, template_window
from archetypal.umi.serialise import NAME_GROUPS, serialise

if TYPE_CHECKING:
    import os
    from collections.abc import Hashable, Iterable, Sequence

    from epinterface.sbem.archetype import ExposureType
    from epinterface.sbem.components.schedules import YearComponent
    from epinterface.sbem.components.zones import ZoneComponent
    from pydantic import JsonValue

    from archetypal.umi._format import YearSchedule

__all__ = ["ArchetypeLike", "CorePerimeter", "ReductionLike", "UmiExport", "approximate_merge", "to_umi", "write_umi"]

_DIRECTION: Final = "sbem_to_umi"
_CALENDAR: Final = RunPeriodCalendar(calendar_year(1, 1, 0))
_SECONDS_PER_HOUR: Final = 3600.0
_MERGED: Final = "merged"
_DEFAULT_WINDOW: Final = GlazingConstructionSimpleComponent(
    Name="Default single glazing", UValue=5.8, SHGF=0.81, TVis=0.88, Type="Single"
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


def _renamed(schedule: YearComponent, name: str) -> YearComponent:
    """`schedule` named `name`, its weeks and days renamed alike (`"<name> week 1"`, `"<name> day 1"`).

    002's functions name a schedule after its group; the merge names it after the member's.
    """
    old = schedule.Name

    def rename(node: object) -> object:
        if isinstance(node, dict):
            items = cast("dict[str, object]", node).items()
            return {
                key: name + value[len(old) :]
                if key == "Name" and isinstance(value, str) and value.startswith(old)
                else rename(value)
                for key, value in items
            }
        return node

    return type(schedule).model_validate(rename(schedule.model_dump()))


def _merged_name(name: str) -> str:
    return f"{name} ({_MERGED})"


def _largest_with(members: Sequence[ZoneGroup], path: str) -> Any:
    """The component at `path` of the largest member that has one."""
    for member in members:
        component = _get(member.Zone, path)
        if component is not None:
            return component
    return None


def _derived(parent: str, suffix: str | None) -> str:
    return parent if suffix is None else derived_name(parent, suffix)


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
        for path in NAMED_FROM.values():
            component = _get(merged, path)
            if component is not None and _dump(component) != _dump(_get(base, path)):
                merged = _replace(merged, f"{path}.Name" if path else "Name", _merged_name(component.Name))
        # A sub-component named after its UMI parent keeps following it, so reading the library
        # back finds the names it derives; one named otherwise is renamed as the others.
        before = {umi_class: _get(base, path).Name for umi_class, path in NAMED_FROM.items()}
        after = {umi_class: _get(merged, path).Name for umi_class, path in NAMED_FROM.items()}
        for path, umi_class, suffix in DERIVED_NAMES:
            component, original = _get(merged, path), _get(base, path)
            if component is None or original is None:
                continue
            if original.Name == _derived(before[umi_class], suffix):
                merged = _replace(merged, f"{path}.Name", _derived(after[umi_class], suffix))
            elif _dump(component) != _dump(original):
                merged = _replace(merged, f"{path}.Name", _merged_name(component.Name))
        return merged

    def gains(self) -> None:
        """Density and normalised schedule from 002's `occupancy`, `lighting` and `equipment`."""
        gains: tuple[tuple[str, GainKind, str, Any], ...] = (
            ("Operations.SpaceUse.Occupancy", "people", "PeopleDensity", occupancy),
            ("Operations.SpaceUse.Lighting", "lights", "PowerDensity", lighting),
            ("Operations.SpaceUse.Equipment", "electric", "PowerDensity", equipment),
        )
        for path, kind, density, derive in gains:
            if not _differ(self.members, path):
                continue
            totals = self.ledger.gains.get(kind)
            component = _get(self.zone, path)
            if totals is None or totals.installed <= 0:
                self.set(path, component.model_copy(update={"IsOn": False}))
                continue
            derived = derive(self.ledger, _CALENDAR, name=_MERGED).value
            schedule = _renamed(derived.Schedule, _merged_name(component.Schedule.Name))
            update = {density: getattr(derived, density), "Schedule": schedule, "IsOn": True}
            self.set(path, component.model_copy(update=update))

    def thermostat(self) -> None:
        """Area-mean setpoint schedules from 002's `thermostat`; a mode no member serves is kept.

        The scalar setpoints are the occupied ones (the heating maximum, the cooling minimum),
        which UMI's constant setpoints hold (`thermostat.constant`), not 002's annual means.
        """
        path = "Operations.SpaceUse.Thermostat"
        if not _differ(self.members, path):
            return
        current = _get(self.zone, path)
        derived = thermostat(self.ledger, _CALENDAR, name=_MERGED).value
        update: dict[str, object] = {}
        for key, totals, pick in (
            ("Heating", self.ledger.heating_setpoint, True),
            ("Cooling", self.ledger.cooling_setpoint, False),
        ):
            values = totals.value
            if values is None:
                continue
            schedule = getattr(current, f"{key}Schedule")
            update[f"{key}Schedule"] = _renamed(getattr(derived, f"{key}Schedule"), _merged_name(schedule.Name))
            update[f"{key}Setpoint"] = float(values.max() if pick else values.min())
        self.set(path, current.model_copy(update=update))

    def systems(self) -> None:
        path = "Operations.HVAC.ConditioningSystems"
        if not _differ(self.members, path):
            return
        systems = _get(self.zone, path)
        update: dict[str, object] = {}
        modes: tuple[tuple[str, Mode], ...] = (("Heating", "heating"), ("Cooling", "cooling"))
        for key, mode in modes:
            system = _largest_with(self.members, f"{path}.{key}")
            totals = self.ledger.energy.get(mode)
            efficiency = None if totals is None else totals.rated_efficiency
            if system is not None and efficiency is not None and system.DistributionCOP > 0:
                system = system.model_copy(update={"SystemCOP": efficiency / system.DistributionCOP})
            update[key] = system
        self.set(path, systems.model_copy(update=update))

    def ventilation(self) -> None:
        """Peak flow per area, its profile and the dominant categories from 002's `ventilation`.

        The provider stays `Both` when a member has natural ventilation, the outdoor-air
        schedule is set only when a member has one, and the sensible heat-recovery
        effectiveness, with heat recovery, is the outdoor-air-volume-weighted mean the rebuilt
        ledgers carry. The rest (natural-ventilation limits, the latent effectiveness, which the
        ledgers do not hold) is the largest member's.
        """
        path = "Operations.HVAC.Ventilation"
        if not _differ(self.members, path):
            return
        air = self.ledger.outdoor_air
        peak = float(air.hourly.max()) if air.hourly.size else 0.0
        if peak <= 0:
            return
        current = _get(self.zone, path)
        derived = ventilation(self.ledger, _CALENDAR, name=_MERGED).value
        natural_members = [m for m in self.members if _get(m.Zone, path).Provider in {"Natural", "Both"}]
        natural = bool(natural_members)
        mechanical = next((m.Zone for m in self.members if _get(m.Zone, f"{path}.MechVentSchedule") is not None), None)
        if natural:
            # `Schedule` opens the windows: the largest naturally ventilated member's, not the
            # mechanical outdoor-air profile (`approximate_merge` reports a difference).
            schedule = _get(natural_members[0].Zone, f"{path}.Schedule")
        else:
            derived_schedule = _renamed(derived.Schedule, _merged_name(current.Schedule.Name))
            schedule = derived_schedule.model_copy(update={"Type": current.Schedule.Type})
        update = {
            "FreshAirPerFloorArea": derived.FreshAirPerFloorArea,
            "FreshAirPerPerson": derived.FreshAirPerPerson,
            "Schedule": schedule,
            "MechVentSchedule": None
            if mechanical is None
            else _renamed(
                cast("YearComponent", derived.MechVentSchedule),
                _merged_name(_get(mechanical, f"{path}.MechVentSchedule").Name),
            ),
            "Provider": "Both" if natural else "Mechanical",
            "HRV": derived.HRV,
            "Economizer": derived.Economizer,
        }
        if derived.HRV != "NoHRV":
            update["SensibleHeatRecoveryEffectiveness"] = derived.SensibleHeatRecoveryEffectiveness
        self.set(path, current.model_copy(update=update))

    def hot_water(self) -> None:
        """Volume per person-day and its profile from 002's `water_use`; supply at inlet plus the mean rise."""
        use_path, dhw_path = "Operations.SpaceUse.WaterUse", "Operations.DHW"
        if not (_differ(self.members, use_path) or _differ(self.members, dhw_path)):
            return
        water = self.ledger.hot_water
        people = self.ledger.gains.get("people")
        volume = float(water.volume.sum()) if water.volume.size else 0.0
        rise = water.mean_rise
        if volume <= 0 or people is None or people.installed <= 0 or rise is None:
            return
        current = _get(self.zone, use_path)
        derived = water_use(self.ledger, _CALENDAR, name=_MERGED).value
        schedule = _renamed(derived.Schedule, _merged_name(current.Schedule.Name))
        self.set(
            use_path, current.model_copy(update={"FlowRatePerPerson": derived.FlowRatePerPerson, "Schedule": schedule})
        )
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
        update: dict[str, object] = {
            "IsOn": True,
            # epinterface reads only the field its method names, so the merged flow is given in ACH.
            "CalculationMethod": "AirChanges/Hour",
            "AirChangesPerHour": flow * _SECONDS_PER_HOUR / self.area,
            "ConstantCoefficient": totals.constant_weighted / flow,
            "TemperatureCoefficient": totals.temperature_weighted / flow,
            "WindVelocityCoefficient": totals.velocity_weighted / flow,
            "WindVelocitySquaredCoefficient": totals.velocity_squared_weighted / flow,
        }
        if totals.hourly.size and _differ(self.members, f"{path}.Schedule"):
            # Members with different schedules: the merged flow is the annual mean and its
            # schedule the summed profile over that mean, so the annual volume is conserved.
            derived = infiltration_component(self.ledger, _CALENDAR, name=_MERGED).value
            mean = float(totals.hourly.mean())
            if derived.Schedule is not None and mean > 0:
                base = infiltration.Schedule
                name = _merged_name(base.Name if base is not None else f"{infiltration.Name} schedule")
                update["AirChangesPerHour"] = mean * _SECONDS_PER_HOUR / self.area
                update["Schedule"] = _renamed(derived.Schedule, name)
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
    (`GroupLedger.approximate_from_group`, floor area = share times 1 m²), the ledgers are grouped
    by exposure with 002's `grouping.group` (by nothing when a group has no exposure, giving
    one group), and each merged group's parameters are derived from its summed ledger by
    002's `to_sbem` functions: densities and setpoints area-weighted with their profiles
    projected onto SBEM's representative days, outdoor air as peak flow per area with its
    profile, hot water as volume per person-day. Parameters every member agrees on are kept exactly. The others in
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
        exposures: set[ExposureType | None] = {member.Exposure for member in members}
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
            losses.extend(_natural_schedule_losses(members, zone, subject=subject, name=name))
        share = result.ledger.floor_area if len(grouping.groups) > 1 else None
        merged_groups.append(ZoneGroup(Name=name, Zone=zone, FloorAreaShare=share, Exposure=exposure))
    merged = archetype.model_copy(update={"Groups": merged_groups})
    return CorePerimeter(merged, tuple(losses))


_NATURAL_SCHEDULE = "Operations.HVAC.Ventilation.Schedule"


def _natural_schedule_losses(
    members: Sequence[ZoneGroup], zone: ZoneComponent, *, subject: str, name: str
) -> list[Loss]:
    """An `approximate` loss when the members open their windows differently, or only some of them do."""
    natural = [m for m in members if _get(m.Zone, "Operations.HVAC.Ventilation").Provider in {"Natural", "Both"}]
    schedules = {json.dumps(_json(_get(m.Zone, _NATURAL_SCHEDULE)), sort_keys=True) for m in natural}
    if not natural or (len(schedules) <= 1 and len(natural) == len(members)):
        return []
    return [
        Loss(
            kind=LossKind.APPROXIMATE,
            subject=subject,
            location=f"{name}.{_NATURAL_SCHEDULE}",
            value=cast("JsonValue", {m.Name: _get(m.Zone, _NATURAL_SCHEDULE).Name for m in natural}),
            replacement=_get(zone, _NATURAL_SCHEDULE).Name,
            rule="layout.merged",
            reason="The groups open their windows on different schedules, or only some of them have natural "
            "ventilation; the merged group opens its windows on the largest naturally ventilated group's.",
        )
    ]


def _json(value: Any) -> JsonValue:
    if not hasattr(value, "model_dump"):
        return cast("JsonValue", value)
    return cast("JsonValue", value.model_dump(mode="json", exclude_none=True))


def _from_reduction(reduction: ReductionLike) -> CorePerimeter:
    """Bring a 002 reduction to core and perimeter, listing the groups merged (research R12)."""
    source = reduction
    if not _is_core_perimeter(reduction.archetype):
        from archetypal.reduction import Reduction, merge  # noqa: PLC0415 - imports the reduction pipeline only when needed

        source = merge(cast("Reduction", reduction), Layout.CORE_PERIMETER)
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


def _perimeter_name(archetype: Archetype) -> str:
    """The name of the group the template's window, settings and partitions come from.

    It is the perimeter-exposed group (the template's `Perimeter`), else the first group.
    """
    groups = archetype.Groups
    return next((g.Name for g in groups if g.Exposure == PERIMETER_GROUP), groups[0].Name if groups else "")


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
            mass_umi,
            assemblies.InternalMassExposedAreaPerArea,
            fallback=fallback,
            context=context.child("Envelope.Assemblies"),
        )
        self.context.findings.extend(umi_names(zone, subject=self.subject, group=group_name).losses)
        fields: dict[str, object] = {
            **identity_to_umi(operations, context.child("Operations")),
            "Name": zone.Name,
            "loads": loads_to_umi(space_use, schedule=self.schedule, context=context),
            "conditioning": conditioning_to_umi(hvac, space_use.Thermostat, schedule=self.schedule, context=context),
            "ventilation": zone_ventilation_to_umi(envelope, hvac.Ventilation, schedule=self.schedule, context=context),
            "domestic_hot_water": dhw_to_umi(
                operations.DHW, space_use.WaterUse, space_use.Occupancy, schedule=self.schedule, context=context
            ),
            "constructions": constructions,
            "internal_mass_construction": mass_construction,
            "internal_mass_exposed_per_floor_area": exposed,
            **daylighting_to_umi(
                space_use.Lighting, ZoneDefinition, context=context.child("Operations.SpaceUse.Lighting")
            ),
        }
        return ZoneDefinition.model_validate(fields)

    def window(self, archetype: Archetype) -> WindowSettings:
        """The template's window settings, from the perimeter group's window and settings (R8, UP-9)."""
        group = _perimeter_name(archetype)
        chosen, losses = template_window(
            {g.Name: g.Zone.Envelope.Window for g in archetype.Groups}, subject=self.subject, chosen=group
        )
        self.context.findings.extend(losses)
        # The settings go with the window: from the group whose window was chosen (another group's
        # when the perimeter has none).
        window_group = next(
            (g.Name for g in archetype.Groups if chosen is not None and g.Zone.Envelope.Window is chosen), group
        )
        location = f"{window_group}.Envelope.Window" if chosen is not None else "Envelope.Window"
        if chosen is None:
            construction, _ = layers_to_umi(_DEFAULT_WINDOW, subject=self.subject, location=location)
            self.context.note(
                location,
                _DEFAULT_WINDOW.Name,
                rule="window.placement",
                reason="The archetype has no window; UMI needs one, so a single clear glazing was written.",
            )
        else:
            construction, layer_losses = layers_to_umi(chosen, subject=self.subject, location=location)
            self.context.findings.extend(layer_losses)
        # A group with neither window nor settings (a core with no facade) simulates no window:
        # gaining the template's settings changes nothing, so it is noted below, not lost.
        _, settings, settings_losses = template_settings(
            {
                g.Name: g.Zone.Envelope.WindowSettings
                for g in archetype.Groups
                if g.Name in {group, window_group}
                or g.Zone.Envelope.Window is not None
                or g.Zone.Envelope.WindowSettings is not None
            },
            subject=self.subject,
            chosen=window_group,
        )
        self.context.findings.extend(settings_losses)
        for other in archetype.Groups:
            # Reading back gives every group the template's window and settings: a group without
            # them (a core with no facade) gains them, which changes nothing it simulates.
            if other.Name in {group, window_group} or other.Zone.Envelope.Window is not None:
                continue
            for key in ("Window", "WindowSettings"):
                if getattr(other.Zone.Envelope, key) is None:
                    self.context.note(
                        f"{other.Name}.Envelope.{key}",
                        None,
                        rule="window.placement" if key == "Window" else "window.settings",
                        reason=f"The group has no {key}; UMI has one per template, which reads back into every group.",
                    )
        context = self.context.child(f"{group}.Envelope.WindowSettings")
        return settings_to_umi(settings, construction, schedule=self.schedule, context=context)

    def template(self, archetype: Archetype) -> BuildingTemplate:
        zones = template_zones(archetype)
        # These name the archetype by its own name; a renamed duplicate (`X #2`) is the subject.
        self.context.findings.extend(_as_subject(zones.losses, self.subject))
        self.context.findings.extend(_as_subject(template_metadata_notes(archetype), self.subject))
        names = {id(g.Zone): g.Name for g in archetype.Groups}
        core = self.zone(zones.core, names.get(id(zones.core), CORE_GROUP))
        perimeter = core if zones.perimeter is zones.core else self.zone(zones.perimeter, names[id(zones.perimeter)])
        ratio = wwr_to_umi(archetype.Geometry, subject=self.subject)
        self.context.findings.extend([*ratio.losses, *ratio.notes])
        partition, partition_losses = partition_ratio_to_umi(
            {g.Name: g.Zone.Envelope.Assemblies.PartitionAreaPerFloorArea for g in archetype.Groups},
            subject=self.subject,
            chosen=_perimeter_name(archetype),
        )
        self.context.findings.extend(partition_losses)
        structure = None
        if archetype.Structure is not None:
            structure, structure_losses = structure_to_umi(
                archetype.Structure, location="archetype.Structure", subject=self.subject
            )
            self.context.findings.extend(structure_losses)
        return BuildingTemplate.model_validate({
            **template_metadata_to_umi(archetype),
            "Name": self.subject,
            "Core": core,
            "Perimeter": perimeter,
            "Windows": self.window(archetype),
            "DefaultWindowToWallRatio": ratio.value,
            "PartitionRatio": partition,
            "Structure": structure,
        })

    @property
    def all_findings(self) -> list[Loss | Note]:
        return [*self.context.findings, *self.findings.losses, *self.findings.notes]


# --- Assembly (research R13) ------------------------------------------------------------------------


class _Assembler:
    """Shares equal components and renames clashing names, in order of first appearance.

    Components are canonicalised bottom-up: each one is keyed by its class, name and fields,
    with every child component replaced by the identity of its canonical object, so equal
    subtrees become one object and each node is keyed in time proportional to its own fields.
    """

    def __init__(self) -> None:
        self.namers: dict[str, UniqueNames] = {}
        self.memo: dict[Hashable, FormatModel] = {}
        self.inputs: dict[int, tuple[FormatModel, FormatModel]] = {}
        """Each input object already assembled (kept alive, so its `id` stays its own)."""
        self.losses: list[Loss] = []

    def component(self, model: FormatModel, pointer: str, subject: str) -> FormatModel:
        seen = self.inputs.get(id(model))
        if seen is not None and seen[0] is model:
            return seen[1]
        result = self._component(model, pointer, subject)
        self.inputs[id(model)] = (model, result)
        return result

    def _component(self, model: FormatModel, pointer: str, subject: str) -> FormatModel:
        updates: dict[str, object] = {}
        content: list[tuple[str, Hashable]] = []
        for name, info in type(model).model_fields.items():
            value: object = getattr(model, name)
            new = self.value(value, f"{pointer}/{info.alias or name}", subject)
            if new is not value:
                updates[name] = new
            if name != "name":
                content.append((name, _identity(new)))
        if updates:
            model = model.model_copy(update=updates)
        if isinstance(model, BuildingTemplate):
            return model
        named = isinstance(model, LibraryComponent)
        key = (type(model), model.name if named else None, tuple(content))
        hit = self.memo.get(key)
        if hit is not None:
            return hit
        if named:
            original = model.name or ""
            namer = self.namers.setdefault(NAME_GROUPS[type(model)], UniqueNames())
            unique = namer.assign(original, (type(model).__name__, tuple(content)))
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
            if not any(isinstance(item, FormatModel | tuple) for item in items):
                return items
            new: tuple[object, ...] = tuple(
                self.value(item, f"{pointer}/{index}", subject) for index, item in enumerate(items)
            )
            return items if all(a is b for a, b in zip(new, items, strict=True)) else new
        return value


_NAN: Final = ("nan",)
"""The identity of every NaN, which never equals itself (equal components must share a key).

0.0 and -0.0 keep one identity: they are equal, as `diff_umi` compares values.
"""


def _identity(value: object) -> Hashable:
    """A hashable stand-in for a field value whose components are already canonical."""
    if isinstance(value, FormatModel):
        return ("component", id(value))
    if isinstance(value, tuple):
        items = cast("tuple[object, ...]", value)
        if not any(isinstance(item, FormatModel | tuple | Enum) or _is_nan(item) for item in items):
            return items
        return tuple(_identity(item) for item in items)
    if isinstance(value, Enum):
        return (type(value).__name__, value.value)
    if _is_nan(value):
        return _NAN
    return cast("Hashable", value)


def _is_nan(value: object) -> bool:
    return isinstance(value, float) and math.isnan(value)


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
        write_atomically([(library, self.text.encode("utf-8")), (loss, self.report.to_json().encode("utf-8"))])
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
        findings.extend(
            loss if loss.subject == subject else loss.model_copy(update={"subject": subject}) for loss in losses
        )
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


_FindingT = TypeVar("_FindingT", Loss, Note)


def _as_subject(findings: Iterable[_FindingT], subject: str) -> list[_FindingT]:
    return [f if f.subject == subject else f.model_copy(update={"subject": subject}) for f in findings]


def _unique(findings: Sequence[Loss | Note]) -> list[Loss | Note]:
    seen: set[str] = set()
    kept: list[Loss | Note] = []
    for finding in findings:
        key = f"{type(finding).__name__}:{finding.model_dump_json()}"
        if key not in seen:
            seen.add(key)
            kept.append(finding)
    return kept


def to_umi(
    archetypes: Sequence[ArchetypeLike], *, strict: bool = False, path: str | os.PathLike[str] | None = None
) -> UmiExport:
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
        path: The library file the text will be written to, recorded in the report's source
            (`write_umi` passes it); `None` records none.

    Returns:
        The library text and the report.

    Raises:
        InputError: `archetypes` is empty, or an archetype has more than two groups and unset
            shares.
        LossyTranslationError: `strict` is set and the report lists losses.
    """
    return _export(archetypes, strict=strict, path=path)


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
