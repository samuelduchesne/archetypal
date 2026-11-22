"""Rules for internal gains and internal mass (spec 003, research R10).

UMI's `ZoneLoads` maps onto SBEM's occupancy, lighting and equipment components; its
densities, schedules, switches and dimming type map exactly. SBEM's `MetabolicRate` has no UMI
field: reading sets epinterface's default (1.2 met) and notes it, writing lists any other value
as lost. The illuminance target and the zone's daylighting parameters (workplane height, mesh
resolution) map to UP-9's daylighting fields of SBEM's lighting (`loads.daylighting`). Internal
mass maps exactly; an exposed area of 0 means no internal
mass, as SBEM requires (both or neither).

Schedules are converted by the schedule rules (research R7). The functions here take the
converter as an argument (`ScheduleToSbem`, `ScheduleToUmi`, in `_common`), so they never
evaluate or project a UMI schedule themselves.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, TypeVar, cast

from epinterface.constants import assumed_constants
from epinterface.sbem.components.space_use import EquipmentComponent, LightingComponent, OccupancyComponent

from archetypal.errors import Problem
from archetypal.umi._format import (
    DimmingType,
    ZoneDefinition,
    ZoneLoads,
)
from archetypal.umi.correspondence import rule
from archetypal.umi.report import NoteKind
from archetypal.umi.rules._common import (
    identity_to_umi,
    json_value,
)

if TYPE_CHECKING:
    from epinterface.sbem.components.space_use import ZoneSpaceUseComponent

    from archetypal.umi._format import YearSchedule
    from archetypal.umi.rules._common import (
        RuleContext,
        ScheduleToSbem,
        ScheduleToUmi,
    )


__all__ = [
    "METABOLIC_RATE",
    "LoadsParts",
    "daylighting_to_sbem",
    "daylighting_to_umi",
    "equipment_to_sbem",
    "equipment_to_umi",
    "internal_mass_to_sbem",
    "internal_mass_to_umi",
    "lighting_to_sbem",
    "lighting_to_umi",
    "loads_to_sbem",
    "loads_to_umi",
    "occupancy_to_sbem",
    "occupancy_to_umi",
    "range_problems",
]

_T = TypeVar("_T")

METABOLIC_RATE: float = assumed_constants.MetabolicRate_met
"""epinterface's default metabolic rate, in met (1.2): what reading gives SBEM's `MetabolicRate`."""


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
        "MetabolicRate",
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
    occupancy: OccupancyComponent, *, schedule: ScheduleToUmi, context: RuleContext
) -> dict[str, object]:
    """Write SBEM's occupancy; a metabolic rate other than 1.2 met is lost.

    Args:
        occupancy: The SBEM occupancy.
        schedule: The schedule converter.
        context: The writing context at the occupancy (`<group>.Operations.SpaceUse.Occupancy`).

    Returns:
        The UMI fields by name.
    """
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
        DimmingType=loads.dimming_type.name,
        Schedule=schedule(
            _schedule(loads.lights_availability_schedule, "LightsAvailabilitySchedule", context),
            "Lighting",
            context.location("LightsAvailabilitySchedule"),
        ),
        IsOn=loads.is_lighting_on,
    )


@rule("loads.lighting", to="umi")
def lighting_to_umi(lighting: LightingComponent, *, schedule: ScheduleToUmi, context: RuleContext) -> dict[str, object]:
    """Write SBEM's lighting.

    Args:
        lighting: The SBEM lighting.
        schedule: The schedule converter.
        context: The writing context at the lighting.

    Returns:
        The UMI fields by name.
    """
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
    equipment: EquipmentComponent, *, schedule: ScheduleToUmi, context: RuleContext
) -> dict[str, object]:
    """Write SBEM's equipment.

    Args:
        equipment: The SBEM equipment.
        schedule: The schedule converter.
        context: The writing context at the equipment.

    Returns:
        The UMI fields by name.
    """
    return {
        "equipment_power_density": equipment.PowerDensity,
        "equipment_availability_schedule": schedule(equipment.Schedule, context.location("Schedule")),
        "is_equipment_on": equipment.IsOn,
    }


# --- Daylighting (UP-9) ---------------------------------------------------------------------------


@rule("loads.daylighting", to="sbem")
def daylighting_to_sbem(
    lighting: LightingComponent, zone: ZoneDefinition, *, context: RuleContext
) -> LightingComponent:
    """Give SBEM's lighting UMI's daylighting parameters (UP-9).

    The illuminance target comes from the zone's loads, the workplane height and mesh
    resolution from the zone definition. A value SBEM refuses (a target or resolution of 0 or
    less, a negative height) is lost, SBEM's default kept.

    Args:
        lighting: The SBEM lighting read from the zone's loads.
        zone: The UMI zone definition (its `Loads` hold the illuminance target).
        context: The zone definition's reading context (`/Zones/<i>`).

    Returns:
        A copy of the lighting with the daylighting fields.
    """
    target = zone.loads.illuminance_target if zone.loads is not None else lighting.IlluminanceTarget
    candidates = (
        ("IlluminanceTarget", "Loads/IlluminanceTarget", target, target > 0, "above 0"),
        (
            "DaylightWorkplaneHeight",
            "DaylightWorkplaneHeight",
            zone.daylight_workplane_height,
            zone.daylight_workplane_height >= 0,
            "at least 0",
        ),
        (
            "DaylightMeshResolution",
            "DaylightMeshResolution",
            zone.daylight_mesh_resolution,
            zone.daylight_mesh_resolution > 0,
            "above 0",
        ),
    )
    update: dict[str, object] = {}
    for key, location, value, valid, expected in candidates:
        if valid:
            update[key] = value
        else:
            context.lose(location, value, rule="loads.daylighting", reason=f"SBEM's {key} must be {expected}")
    return LightingComponent.model_validate({**lighting.model_dump(), **update})


@rule("loads.daylighting", to="umi")
def daylighting_to_umi(
    lighting: LightingComponent, model: type[ZoneLoads | ZoneDefinition], *, context: RuleContext
) -> dict[str, object]:
    """Return the daylighting fields of UMI loads or a zone definition from SBEM's lighting (UP-9).

    Args:
        lighting: The SBEM lighting.
        model: `ZoneLoads` (illuminance target) or `ZoneDefinition` (workplane height, mesh).
        context: The writing context at the lighting (`<group>.Operations.SpaceUse.Lighting`).

    Returns:
        The UMI fields by name. SBEM's mesh resolution `None` (no illuminance map) takes
        Basilisk's default, noted.
    """
    if model is ZoneLoads:
        return {"illuminance_target": lighting.IlluminanceTarget}
    resolution = lighting.DaylightMeshResolution
    if resolution is None:
        resolution = cast("float", ZoneDefinition.model_fields["daylight_mesh_resolution"].default)
        context.note(
            "DaylightMeshResolution",
            resolution,
            rule="loads.daylighting",
            reason="SBEM writes no illuminance map; Basilisk's default mesh resolution is written",
            kind=NoteKind.DEFAULTED,
        )
    return {"daylight_workplane_height": lighting.DaylightWorkplaneHeight, "daylight_mesh_resolution": resolution}


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
    return LoadsParts(
        occupancy_to_sbem(loads, schedule=schedule, context=context),
        lighting_to_sbem(loads, schedule=schedule, context=context),
        equipment_to_sbem(loads, schedule=schedule, context=context),
    )


def loads_to_umi(space_use: ZoneSpaceUseComponent, *, schedule: ScheduleToUmi, context: RuleContext) -> ZoneLoads:
    """Write an SBEM space use's occupancy, lighting and equipment as UMI loads.

    The loads take the space use's name and metadata (data-model.md).

    Args:
        space_use: The SBEM space use.
        schedule: The schedule converter.
        context: The writing context at the group (`perimeter`).
    """
    here = context.child("Operations.SpaceUse")
    fields: dict[str, object] = {
        **identity_to_umi(space_use, here),
        **occupancy_to_umi(space_use.Occupancy, schedule=schedule, context=here.child("Occupancy")),
        **lighting_to_umi(space_use.Lighting, schedule=schedule, context=here.child("Lighting")),
        **equipment_to_umi(space_use.Equipment, schedule=schedule, context=here.child("Equipment")),
        **daylighting_to_umi(space_use.Lighting, ZoneLoads, context=here.child("Lighting")),
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
def internal_mass_to_sbem(
    construction: _T | None, ratio: float, *, context: RuleContext, written_back: bool = False
) -> tuple[_T | None, float | None]:
    """Read UMI's internal mass: an exposed area of 0 means none (both or neither).

    Args:
        construction: The internal-mass construction, already translated.
        ratio: `InternalMassExposedPerFloorArea`, m² per m² of floor.
        context: The zone definition's reading context (`/Zones/<i>`).
        written_back: The construction is the one writing puts there for no internal mass (the
            zone's partition construction), so dropping it loses nothing.

    Returns:
        SBEM's `(InternalMassAssembly, InternalMassExposedAreaPerArea)`: `(None, None)` when
        the ratio is 0, the construction then being lost unless `written_back`.
    """
    if ratio == 0:
        if construction is not None and not written_back:
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
        msg = f"{context.location()}: internal mass needs an assembly and an exposed area, both or neither"
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
