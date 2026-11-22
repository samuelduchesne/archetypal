"""Rules for internal gains and internal mass (spec 003, research R10).

UMI's `ZoneLoads` maps onto SBEM's occupancy, lighting and equipment components; its
densities, schedules, switches and dimming type map exactly. SBEM's `MetabolicRate` has no UMI
field: reading sets epinterface's default (1.2 met) and notes it, writing lists any other value
as lost. The illuminance target and the zone's daylighting parameters have no SBEM field until
UP-9 and are lost on reading. Internal mass maps exactly; an exposed area of 0 means no internal
mass, as SBEM requires (both or neither).

The module also holds what the operation rules (`conditioning`, `ventilation`, `hotwater`)
share: `RuleContext`, which collects a translation's losses and notes, the schedule converter
types, the reference calendar and the handling of fields that wait for an upstream item.

Schedules are converted by the schedule rules (research R7). The functions here take the
converter as an argument (`ScheduleToSbem`, `ScheduleToUmi`), so they never evaluate or
project a UMI schedule themselves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Literal, NamedTuple, TypeVar, cast

import numpy as np
from epinterface.constants import assumed_constants
from epinterface.sbem.components.space_use import EquipmentComponent, LightingComponent, OccupancyComponent

from archetypal.errors import Problem
from archetypal.reduction.schedules import RunPeriodCalendar, calendar_year, year_values
from archetypal.umi._format import (
    DaySchedule,
    DimmingType,
    FormatModel,
    LibraryComponent,
    WeekSchedule,
    YearSchedule,
    YearSchedulePart,
    ZoneDefinition,
    ZoneLoads,
)
from archetypal.umi.correspondence import MappingStatus, mappings_for, rule
from archetypal.umi.report import Loss, LossKind, Note, NoteKind

if TYPE_CHECKING:
    from collections.abc import Callable

    import numpy.typing as npt
    from epinterface.sbem.components.schedules import YearComponent, YearScheduleCategory
    from epinterface.sbem.components.space_use import DimmingTypeType, ZoneSpaceUseComponent
    from pydantic import JsonValue

    from archetypal.umi.report import Direction

__all__ = [
    "METABOLIC_RATE",
    "REFERENCE_CALENDAR",
    "LoadsParts",
    "RuleContext",
    "ScheduleToSbem",
    "ScheduleToUmi",
    "all_values_equal",
    "annual_values",
    "constant_year_schedule",
    "daylighting_to_sbem",
    "daylighting_to_umi",
    "equipment_to_sbem",
    "equipment_to_umi",
    "internal_mass_to_sbem",
    "internal_mass_to_umi",
    "json_value",
    "lighting_to_sbem",
    "lighting_to_umi",
    "loads_to_sbem",
    "loads_to_umi",
    "occupancy_to_sbem",
    "occupancy_to_umi",
    "range_problems",
    "report_name",
    "report_upstream",
    "upstream_defaults",
]

_T = TypeVar("_T")

METABOLIC_RATE: float = assumed_constants.MetabolicRate_met
"""epinterface's default metabolic rate, in met (1.2): what reading gives SBEM's `MetabolicRate`."""

REFERENCE_CALENDAR = RunPeriodCalendar(calendar_year(1, 1, 0))
"""The reference year of UMI schedules (research R7): non-leap, starting on a Monday."""

ScheduleToSbem = "Callable[[YearSchedule, YearScheduleCategory, str], YearComponent]"
ScheduleToUmi = "Callable[[YearComponent, str], YearSchedule]"
# The two aliases above are strings so that the module imports without the type-only names;
# pyright reads them through the `TYPE_CHECKING` block below.
if TYPE_CHECKING:
    ScheduleToSbem = Callable[[YearSchedule, YearScheduleCategory, str], YearComponent]
    """Converts a UMI schedule: `(schedule, SBEM category, JSON pointer of the field) -> year`."""
    ScheduleToUmi = Callable[[YearComponent, str], YearSchedule]
    """Converts an SBEM schedule: `(year, SBEM field path) -> UMI schedule`."""


# --- What the operation rules share --------------------------------------------------------------


@dataclass(frozen=True)
class RuleContext:
    """Where a rule is applied, and the losses and notes it reports.

    Reading (`umi_to_sbem`), `at` is the JSON pointer of the UMI component being read
    (`/ZoneLoads/0`) and locations are pointers below it. Writing (`sbem_to_umi`), `at` is the
    zone group (`perimeter`) or a field path below it, and locations are dotted field paths
    (`perimeter.Operations.SpaceUse.Occupancy.MetabolicRate`), as contracts/translation-report.md
    requires.

    Attributes:
        subject: The template (reading) or archetype (writing).
        at: The JSON pointer or field path the locations start from.
        direction: Which way the translation goes.
        findings: The losses and notes reported so far, shared by every child context.
    """

    subject: str
    at: str
    direction: Direction
    findings: list[Loss | Note] = field(default_factory=list[Loss | Note])

    def location(self, key: str = "") -> str:
        """Return the location of `key` below `at` (`at` itself for an empty key)."""
        if not key:
            return self.at
        separator = "/" if self.direction == "umi_to_sbem" else "."
        return f"{self.at}{separator}{key}" if self.at else key

    def child(self, key: str) -> RuleContext:
        """Return a context at `key` below this one, sharing its findings."""
        return RuleContext(self.subject, self.location(key), self.direction, self.findings)

    def lose(  # noqa: PLR0913 - every argument is a field of the loss
        self,
        key: str,
        value: JsonValue,
        *,
        rule: str,
        reason: str,
        replacement: JsonValue = None,
        upstream: str | None = None,
        kind: LossKind = LossKind.LOST,
    ) -> None:
        """Report that the value at `key` is not represented in the target."""
        self.findings.append(
            Loss(
                kind=kind,
                subject=self.subject,
                location=self.location(key),
                value=value,
                replacement=replacement,
                rule=rule,
                reason=reason,
                upstream=upstream,
            )
        )

    def note(
        self, key: str, value: JsonValue, *, rule: str, reason: str, kind: NoteKind = NoteKind.ASSUMED
    ) -> None:
        """Report an assumption or default at `key` that loses nothing."""
        self.findings.append(
            Note(kind=kind, subject=self.subject, location=self.location(key), value=value, rule=rule, reason=reason)
        )

    @property
    def losses(self) -> list[Loss]:
        """The losses reported so far."""
        return [finding for finding in self.findings if isinstance(finding, Loss)]

    @property
    def notes(self) -> list[Note]:
        """The notes reported so far."""
        return [finding for finding in self.findings if isinstance(finding, Note)]


def json_value(value: object) -> JsonValue:
    """Return a UMI value as the report holds it: enums as Basilisk's integers, components by name."""
    if isinstance(value, Enum):
        member = cast("Enum", value)
        return cast("JsonValue", member.value)
    if isinstance(value, LibraryComponent):
        return value.name
    if isinstance(value, tuple):
        return [json_value(item) for item in cast("tuple[object, ...]", value)]
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    msg = f"no report form for {type(value).__name__}"
    raise TypeError(msg)


def _aliases(model: type[FormatModel]) -> dict[str, str]:
    """Map each Basilisk key of a format model to its field name."""
    return {info.alias or name: name for name, info in model.model_fields.items()}


def _upstream_rows(model: type[FormatModel], rule_id: str) -> list[tuple[str, str, str | None]]:
    """The `(key, field name, upstream item)` of each upstream row of `rule_id` on `model`."""
    aliases = _aliases(model)
    return [
        (row.umi_key, aliases[row.umi_key], row.upstream)
        for row in mappings_for(rule_id)
        if row.status is MappingStatus.UPSTREAM and row.umi_class == model.__name__ and row.umi_key in aliases
    ]


def report_upstream(component: FormatModel, rule_id: str, context: RuleContext) -> None:
    """Report, on reading, every field of `component` that waits for an upstream item as lost.

    Until a field lands in a fork release, every read reports it (research R6, FR-010).

    Args:
        component: The UMI component read.
        rule_id: The rule whose upstream rows to report.
        context: The component's reading context.
    """
    for key, name, upstream in _upstream_rows(type(component), rule_id):
        context.lose(
            key,
            json_value(getattr(component, name)),
            rule=rule_id,
            reason=f"SBEM has no field for {key} yet",
            upstream=upstream,
        )


def upstream_defaults(model: type[FormatModel], rule_id: str, context: RuleContext) -> dict[str, object]:
    """Return Basilisk's default of every upstream field of `rule_id` on `model`, noting each.

    Writing fills the UMI fields SBEM does not hold with Basilisk's defaults
    (contracts/umi-file.md, rule 6). Fields whose default is `None` (schedules) are left to the
    caller.

    Args:
        model: The UMI component class written.
        rule_id: The rule whose upstream rows to fill.
        context: The writing context, at the SBEM component that holds the UMI component.

    Returns:
        The defaults by field name.
    """
    defaults: dict[str, object] = {}
    for key, name, _ in _upstream_rows(model, rule_id):
        default = model.model_fields[name].default
        if default is None:
            continue
        defaults[name] = default
        context.note(
            "",
            json_value(default),
            rule=rule_id,
            reason=f"SBEM holds no {model.__name__}.{key}; Basilisk's default written",
            kind=NoteKind.DEFAULTED,
        )
    return defaults


def report_name(actual: str, expected: str, key: str, context: RuleContext) -> None:
    """Report, on writing, a sub-component name that reading would not derive back (data-model.md)."""
    if actual != expected:
        context.lose(
            key,
            actual,
            replacement=expected,
            rule="names.component",
            reason="UMI has no component of its own here; reading names it after its parent",
        )


def annual_values(year: YearComponent) -> npt.NDArray[np.float64]:
    """Return an SBEM schedule's hourly values over the reference year (8760 values)."""
    return year_values(year, REFERENCE_CALENDAR)


def constant_year_schedule(name: str, value: float, kind: str = "Fraction") -> YearSchedule:
    """Return a UMI schedule with one value in every hour of the year.

    Its day and week are named `"<name> day"` and `"<name> week"`.

    Args:
        name: The schedule's name.
        value: The value of every hour.
        kind: The schedule's `Type`.
    """
    day = DaySchedule.model_validate({"Name": f"{name} day", "Type": kind, "Values": (float(value),) * 24})
    week = WeekSchedule.model_validate({"Name": f"{name} week", "Type": kind, "Days": (day,) * 7})
    part = YearSchedulePart.model_validate({
        "FromDay": 1,
        "FromMonth": 1,
        "ToDay": 31,
        "ToMonth": 12,
        "Schedule": week,
    })
    return YearSchedule.model_validate({"Name": name, "Type": kind, "Parts": (part,)})


def all_values_equal(year: YearSchedule, value: float) -> bool:
    """Tell whether every hour of every day a UMI schedule uses equals `value`."""
    for part in year.parts:
        if part.schedule is None:
            return False
        for day in part.schedule.days:
            if day is None or any(hour != value for hour in day.values):
                return False
    return bool(year.parts)


def _schedule(year: YearSchedule | None, key: str, context: RuleContext) -> YearSchedule:
    """Return a required UMI schedule, refusing `None` (a completeness problem, research R3)."""
    if year is None:
        msg = f"{context.location(key)} is null; validation should have refused it"
        raise ValueError(msg)
    return year


# --- Occupancy ------------------------------------------------------------------------------------


@rule("loads.people", to="sbem")
def occupancy_to_sbem(loads: ZoneLoads, *, schedule: ScheduleToSbem, context: RuleContext) -> OccupancyComponent:
    """Read UMI's people density, schedule and switch; set the metabolic rate to 1.2 met (noted).

    Args:
        loads: The UMI loads.
        schedule: The schedule converter.
        context: The loads' reading context.
    """
    context.note(
        "PeopleDensity",
        METABOLIC_RATE,
        rule="loads.people",
        reason="SBEM's Occupancy.MetabolicRate has no UMI field; epinterface's default used",
    )
    return OccupancyComponent(
        Name=f"{loads.name} occupancy",
        PeopleDensity=loads.people_density,
        Schedule=schedule(
            _schedule(loads.occupancy_schedule, "OccupancySchedule", context),
            "Occupancy",
            context.location("OccupancySchedule"),
        ),
        IsOn=loads.is_people_on,
        MetabolicRate=METABOLIC_RATE,
    )


@rule("loads.people", to="umi")
def occupancy_to_umi(
    occupancy: OccupancyComponent, *, schedule: ScheduleToUmi, name: str, context: RuleContext
) -> dict[str, object]:
    """Write SBEM's occupancy; a metabolic rate other than 1.2 met is lost.

    Args:
        occupancy: The SBEM occupancy.
        schedule: The schedule converter.
        name: The UMI loads' name, from which reading derives the occupancy's.
        context: The writing context at the occupancy (`<group>.Operations.SpaceUse.Occupancy`).

    Returns:
        The UMI fields by name.
    """
    report_name(occupancy.Name, f"{name} occupancy", "Name", context)
    if occupancy.MetabolicRate != METABOLIC_RATE:
        context.lose(
            "MetabolicRate",
            occupancy.MetabolicRate,
            rule="loads.people",
            reason=f"UMI has no metabolic rate; reading gives {METABOLIC_RATE} met",
        )
    return {
        "people_density": occupancy.PeopleDensity,
        "occupancy_schedule": schedule(occupancy.Schedule, context.location("Schedule")),
        "is_people_on": occupancy.IsOn,
    }


# --- Lighting -------------------------------------------------------------------------------------


@rule("loads.lighting", to="sbem")
def lighting_to_sbem(loads: ZoneLoads, *, schedule: ScheduleToSbem, context: RuleContext) -> LightingComponent:
    """Read UMI's lighting density, schedule, switch and dimming type.

    Args:
        loads: The UMI loads.
        schedule: The schedule converter.
        context: The loads' reading context.
    """
    return LightingComponent(
        Name=f"{loads.name} lighting",
        PowerDensity=loads.lighting_power_density,
        DimmingType=cast("DimmingTypeType", loads.dimming_type.name),
        Schedule=schedule(
            _schedule(loads.lights_availability_schedule, "LightsAvailabilitySchedule", context),
            "Lighting",
            context.location("LightsAvailabilitySchedule"),
        ),
        IsOn=loads.is_lighting_on,
    )


@rule("loads.lighting", to="umi")
def lighting_to_umi(
    lighting: LightingComponent, *, schedule: ScheduleToUmi, name: str, context: RuleContext
) -> dict[str, object]:
    """Write SBEM's lighting.

    Args:
        lighting: The SBEM lighting.
        schedule: The schedule converter.
        name: The UMI loads' name.
        context: The writing context at the lighting.

    Returns:
        The UMI fields by name.
    """
    report_name(lighting.Name, f"{name} lighting", "Name", context)
    return {
        "lighting_power_density": lighting.PowerDensity,
        "lights_availability_schedule": schedule(lighting.Schedule, context.location("Schedule")),
        "is_lighting_on": lighting.IsOn,
        "dimming_type": DimmingType[lighting.DimmingType],
    }


# --- Equipment ------------------------------------------------------------------------------------


@rule("loads.equipment", to="sbem")
def equipment_to_sbem(loads: ZoneLoads, *, schedule: ScheduleToSbem, context: RuleContext) -> EquipmentComponent:
    """Read UMI's equipment density, schedule and switch.

    Args:
        loads: The UMI loads.
        schedule: The schedule converter.
        context: The loads' reading context.
    """
    return EquipmentComponent(
        Name=f"{loads.name} equipment",
        PowerDensity=loads.equipment_power_density,
        Schedule=schedule(
            _schedule(loads.equipment_availability_schedule, "EquipmentAvailabilitySchedule", context),
            "Equipment",
            context.location("EquipmentAvailabilitySchedule"),
        ),
        IsOn=loads.is_equipment_on,
    )


@rule("loads.equipment", to="umi")
def equipment_to_umi(
    equipment: EquipmentComponent, *, schedule: ScheduleToUmi, name: str, context: RuleContext
) -> dict[str, object]:
    """Write SBEM's equipment.

    Args:
        equipment: The SBEM equipment.
        schedule: The schedule converter.
        name: The UMI loads' name.
        context: The writing context at the equipment.

    Returns:
        The UMI fields by name.
    """
    report_name(equipment.Name, f"{name} equipment", "Name", context)
    return {
        "equipment_power_density": equipment.PowerDensity,
        "equipment_availability_schedule": schedule(equipment.Schedule, context.location("Schedule")),
        "is_equipment_on": equipment.IsOn,
    }


# --- Daylighting (UP-9) ---------------------------------------------------------------------------


@rule("loads.daylighting", to="sbem")
def daylighting_to_sbem(component: ZoneLoads | ZoneDefinition, *, context: RuleContext) -> None:
    """Report the daylighting fields of UMI loads or a zone definition as lost (UP-9).

    Args:
        component: The UMI loads (illuminance target) or zone definition (mesh, workplane).
        context: The component's reading context.
    """
    report_upstream(component, "loads.daylighting", context)


@rule("loads.daylighting", to="umi")
def daylighting_to_umi(model: type[ZoneLoads | ZoneDefinition], *, context: RuleContext) -> dict[str, object]:
    """Return Basilisk's defaults for the daylighting fields of `model`, noting each.

    Args:
        model: `ZoneLoads` or `ZoneDefinition`.
        context: The writing context at the SBEM component that holds it.

    Returns:
        The defaults by field name.
    """
    return upstream_defaults(model, "loads.daylighting", context)


# --- Loads, whole ---------------------------------------------------------------------------------


class LoadsParts(NamedTuple):
    """The SBEM components read from UMI loads, which the zone's space use holds."""

    occupancy: OccupancyComponent
    lighting: LightingComponent
    equipment: EquipmentComponent


def loads_to_sbem(loads: ZoneLoads, *, schedule: ScheduleToSbem, context: RuleContext) -> LoadsParts:
    """Read UMI loads into SBEM's occupancy, lighting and equipment.

    The zone's `ZoneSpaceUseComponent` takes the loads' name and metadata (data-model.md); it
    also holds the thermostat and water use, which other rules read.

    Args:
        loads: The UMI loads.
        schedule: The schedule converter.
        context: The loads' reading context (`/ZoneLoads/<i>`).
    """
    parts = LoadsParts(
        occupancy_to_sbem(loads, schedule=schedule, context=context),
        lighting_to_sbem(loads, schedule=schedule, context=context),
        equipment_to_sbem(loads, schedule=schedule, context=context),
    )
    daylighting_to_sbem(loads, context=context)
    return parts


def loads_to_umi(space_use: ZoneSpaceUseComponent, *, schedule: ScheduleToUmi, context: RuleContext) -> ZoneLoads:
    """Write an SBEM space use's occupancy, lighting and equipment as UMI loads.

    The loads take the space use's name and metadata (data-model.md).

    Args:
        space_use: The SBEM space use.
        schedule: The schedule converter.
        context: The writing context at the group (`perimeter`).
    """
    here = context.child("Operations.SpaceUse")
    name = space_use.Name
    fields: dict[str, object] = {
        "name": name,
        "category": space_use.Category or "Uncategorized",
        "comments": space_use.Comment,
        "data_source": space_use.DataSource,
        **occupancy_to_umi(space_use.Occupancy, schedule=schedule, name=name, context=here.child("Occupancy")),
        **lighting_to_umi(space_use.Lighting, schedule=schedule, name=name, context=here.child("Lighting")),
        **equipment_to_umi(space_use.Equipment, schedule=schedule, name=name, context=here.child("Equipment")),
        **daylighting_to_umi(ZoneLoads, context=here),
    }
    return ZoneLoads.model_validate(fields)


def range_problems(loads: ZoneLoads, *, pointer: str, template: str | None) -> list[Problem]:
    """Return the range problems of UMI loads (research R3): densities SBEM refuses.

    Args:
        loads: The UMI loads.
        pointer: Their JSON pointer.
        template: The template affected.
    """
    checks = (
        ("PeopleDensity", loads.people_density, "loads.people"),
        ("LightingPowerDensity", loads.lighting_power_density, "loads.lighting"),
        ("EquipmentPowerDensity", loads.equipment_power_density, "loads.equipment"),
    )
    return [
        Problem(f"{pointer}/{key}", template, rule_id, f"{key} is {value!r}; SBEM needs a value of at least 0")
        for key, value, rule_id in checks
        if value < 0
    ]


# --- Internal mass --------------------------------------------------------------------------------


@rule("mass.internal", to="sbem")
def internal_mass_to_sbem(construction: _T | None, ratio: float, *, context: RuleContext) -> tuple[_T | None, float | None]:
    """Read UMI's internal mass: an exposed area of 0 means none (both or neither).

    Args:
        construction: The internal-mass construction, already translated.
        ratio: `InternalMassExposedPerFloorArea`, m² per m² of floor.
        context: The zone definition's reading context (`/Zones/<i>`).

    Returns:
        SBEM's `(InternalMassAssembly, InternalMassExposedAreaPerArea)`: `(None, None)` when
        the ratio is 0, the construction then being lost.
    """
    if ratio == 0:
        if construction is not None:
            context.lose(
                "InternalMassConstruction",
                json_value(getattr(construction, "Name", construction)),
                rule="mass.internal",
                reason="the exposed area is 0, so SBEM holds no internal mass and the construction is dropped",
            )
        return None, None
    return construction, ratio


@rule("mass.internal", to="umi")
def internal_mass_to_umi(
    assembly: _T | None, ratio: float | None, *, fallback: _T, context: RuleContext
) -> tuple[_T, float]:
    """Write SBEM's internal mass; none is written as an exposed area of 0.

    UMI requires an internal-mass construction even when there is no internal mass, so the
    caller's `fallback` construction is written then (noted).

    Args:
        assembly: SBEM's `InternalMassAssembly`, already translated, or `None`.
        ratio: SBEM's `InternalMassExposedAreaPerArea`, or `None`.
        fallback: The construction to write when SBEM has no internal mass.
        context: The writing context at the envelope assemblies.

    Returns:
        UMI's `(InternalMassConstruction, InternalMassExposedPerFloorArea)`.

    Raises:
        ValueError: Exactly one of the assembly and a non-zero ratio is given, which SBEM's
            validator refuses.
    """
    has_area = ratio is not None and ratio != 0
    if (assembly is None) == has_area:
        msg = f"{context.location()}: internal mass needs both an assembly and an exposed area, or neither"
        raise ValueError(msg)
    if assembly is None or ratio is None:
        context.note(
            "InternalMassAssembly",
            json_value(getattr(fallback, "Name", fallback)),
            rule="mass.internal",
            reason="SBEM has no internal mass; UMI needs a construction, written with an exposed area of 0",
        )
        return fallback, 0.0
    return assembly, ratio
