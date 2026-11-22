"""Rules for infiltration and natural ventilation (spec 003, research R10).

- **Infiltration** (`infiltration.ach`). UMI's `Infiltration` (air changes per hour) and its
  switch map to SBEM's `AirChangesPerHour` and `IsOn`, with `CalculationMethod =
  "AirChanges/Hour"`. Reading notes the coefficients UMI does not have (constant 1, the others
  0, which is what epinterface writes anyway) and fills the attic and basement infiltration from
  the main value (noted). Writing an archetype whose method is not air changes per hour would
  need the building's volume, so it is lost with its value; attic or basement infiltration that
  differs from the main one is lost too.
- **Provider** (`vent.provider`). UMI's two switches, mechanical (`ZoneConditioning.IsMechVentOn`)
  and natural (`ZoneVentilation.IsNatVentOn`), map to SBEM's `Provider`: `None`, `Natural`,
  `Mechanical` or `Both`, and back. Both switches are conserved.
- **Natural-ventilation schedule** (`vent.natural_schedule`). `NatVentSchedule` maps to
  `Ventilation.Schedule`, which epinterface uses for natural ventilation only.
- **Natural-ventilation limits and scheduled ventilation** (`vent.natural_limits`,
  `vent.scheduled`). SBEM has no fields for them until UP-9: reading reports each value that
  differs from Basilisk's default as lost; writing gives Basilisk's defaults (noted).

The VentilationComponent itself, which also holds the conditioning's fresh air, economizer and
heat recovery, is assembled by `archetypal.umi.rules.conditioning`.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple

from epinterface.sbem.components.envelope import InfiltrationComponent

from archetypal.errors import Problem
from archetypal.umi._format import ZoneVentilation
from archetypal.umi.correspondence import rule
from archetypal.umi.rules._common import (
    RuleContext,
    ScheduleToSbem,
    ScheduleToUmi,
    identity_to_sbem,
    identity_to_umi,
    json_value,
    report_upstream,
    upstream_defaults,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from epinterface.sbem.components.envelope import ZoneEnvelopeComponent
    from epinterface.sbem.components.schedules import YearComponent
    from epinterface.sbem.components.systems import VentilationComponent, VentilationProvider
    from pydantic import JsonValue

    from archetypal.umi._format import YearSchedule

__all__ = [
    "AIR_CHANGES",
    "PROVIDERS",
    "UNUSED_COEFFICIENTS",
    "InfiltrationParts",
    "infiltration_to_sbem",
    "infiltration_to_umi",
    "natural_limits_to_sbem",
    "natural_limits_to_umi",
    "natural_schedule_to_sbem",
    "natural_schedule_to_umi",
    "provider_to_sbem",
    "provider_to_umi",
    "range_problems",
    "scheduled_to_sbem",
    "scheduled_to_umi",
    "zone_ventilation_to_sbem",
    "zone_ventilation_to_umi",
]

AIR_CHANGES = "AirChanges/Hour"
"""SBEM's calculation method for UMI's infiltration."""

UNUSED_COEFFICIENTS: Mapping[str, float] = MappingProxyType({
    "ConstantCoefficient": 1.0,
    "TemperatureCoefficient": 0.0,
    "WindVelocityCoefficient": 0.0,
    "WindVelocitySquaredCoefficient": 0.0,
    "AFNAirMassFlowCoefficientCrack": 0.0,
    "FlowPerExteriorSurfaceArea": 0.0,
})
"""The SBEM infiltration fields UMI does not have, and the values reading gives them."""

PROVIDERS: Mapping[tuple[bool, bool], VentilationProvider] = MappingProxyType({
    (False, False): "None",
    (False, True): "Natural",
    (True, False): "Mechanical",
    (True, True): "Both",
})
"""SBEM's ventilation provider by UMI's (mechanical, natural) switches."""

_SWITCHES: Mapping[VentilationProvider, tuple[bool, bool]] = MappingProxyType({
    provider: switches for switches, provider in PROVIDERS.items()
})

_INFILTRATION_PATH = "Envelope.Infiltration"
# The infiltration fields that change a simulation (epinterface ignores the coefficients).
_COMPARED = ("IsOn", "AirChangesPerHour", "FlowPerExteriorSurfaceArea", "CalculationMethod")


# --- Provider -----------------------------------------------------------------------------------


@rule("vent.provider", to="sbem")
def provider_to_sbem(mechanical: bool, natural: bool) -> VentilationProvider:
    """Return SBEM's ventilation provider for UMI's mechanical and natural switches.

    Args:
        mechanical: `ZoneConditioning.IsMechVentOn`.
        natural: `ZoneVentilation.IsNatVentOn`.
    """
    return PROVIDERS[mechanical, natural]


@rule("vent.provider", to="umi")
def provider_to_umi(provider: VentilationProvider) -> tuple[bool, bool]:
    """Return UMI's (mechanical, natural) switches for SBEM's ventilation provider."""
    return _SWITCHES[provider]


# --- Infiltration -------------------------------------------------------------------------------


class InfiltrationParts(NamedTuple):
    """The SBEM infiltration of a zone's envelope, read from UMI ventilation settings."""

    infiltration: InfiltrationComponent
    attic: InfiltrationComponent
    basement: InfiltrationComponent


@rule("infiltration.ach", to="sbem")
def infiltration_to_sbem(ventilation: ZoneVentilation, *, context: RuleContext) -> InfiltrationParts:
    """Read UMI's infiltration as air changes per hour; attic and basement take the same value.

    The component takes the ventilation settings' name and metadata (data-model.md); the attic
    and basement hold the same component.

    Args:
        ventilation: The UMI ventilation settings.
        context: Their reading context (`/VentilationSettings/<i>`).
    """
    infiltration = InfiltrationComponent.model_validate({
        **identity_to_sbem(ventilation),
        "IsOn": ventilation.is_infiltration_on,
        "AirChangesPerHour": ventilation.infiltration,
        "CalculationMethod": AIR_CHANGES,
        **UNUSED_COEFFICIENTS,
    })
    context.note(
        "Infiltration",
        dict(UNUSED_COEFFICIENTS),
        rule="infiltration.ach",
        reason="UMI gives air changes per hour only; SBEM's other infiltration fields set as epinterface uses them",
    )
    context.note(
        "Infiltration",
        ventilation.infiltration,
        rule="infiltration.ach",
        reason="UMI has one infiltration; the attic and basement infiltration take the same value",
    )
    return InfiltrationParts(infiltration, infiltration, infiltration)


def _behaviour(infiltration: InfiltrationComponent) -> dict[str, JsonValue]:
    return {key: getattr(infiltration, key) for key in _COMPARED}


@rule("infiltration.ach", to="umi")
def infiltration_to_umi(
    infiltration: InfiltrationComponent,
    attic: InfiltrationComponent,
    basement: InfiltrationComponent,
    *,
    context: RuleContext,
) -> dict[str, object]:
    """Write SBEM's infiltration as air changes per hour.

    Args:
        infiltration: The zone's infiltration.
        attic: The attic's infiltration; lost when it differs from the zone's.
        basement: The basement's infiltration; lost when it differs from the zone's.
        context: The writing context at the envelope (`<group>.Envelope`).

    Returns:
        UMI's `infiltration` and `is_infiltration_on`.
    """
    if infiltration.CalculationMethod != AIR_CHANGES:
        context.lose(
            "Infiltration.CalculationMethod",
            {
                "CalculationMethod": infiltration.CalculationMethod,
                "AirChangesPerHour": infiltration.AirChangesPerHour,
                "FlowPerExteriorSurfaceArea": infiltration.FlowPerExteriorSurfaceArea,
            },
            replacement=infiltration.AirChangesPerHour,
            rule="infiltration.ach",
            reason=f"UMI holds air changes per hour only; converting {infiltration.CalculationMethod} needs the "
            "building's volume",
        )
    main = _behaviour(infiltration)
    for key, other in (("AtticInfiltration", attic), ("BasementInfiltration", basement)):
        if _behaviour(other) != main:
            context.lose(
                key,
                _behaviour(other),
                replacement=infiltration.AirChangesPerHour,
                rule="infiltration.ach",
                reason="UMI has one infiltration for the whole zone; the zone's is written",
            )
    return {"infiltration": infiltration.AirChangesPerHour, "is_infiltration_on": infiltration.IsOn}


# --- Natural-ventilation schedule ---------------------------------------------------------------


@rule("vent.natural_schedule", to="sbem")
def natural_schedule_to_sbem(
    ventilation: ZoneVentilation, *, schedule: ScheduleToSbem, context: RuleContext
) -> YearComponent:
    """Read UMI's natural-ventilation schedule as SBEM's ventilation schedule (category `Window`).

    Args:
        ventilation: The UMI ventilation settings.
        schedule: The schedule converter.
        context: Their reading context.
    """
    year = ventilation.nat_vent_schedule
    if year is None:
        msg = f"{context.location('NatVentSchedule')} is null; validation should have refused it"
        raise ValueError(msg)
    return schedule(year, "Window", context.location("NatVentSchedule"))


@rule("vent.natural_schedule", to="umi")
def natural_schedule_to_umi(
    ventilation: VentilationComponent, *, schedule: ScheduleToUmi, context: RuleContext
) -> YearSchedule:
    """Write SBEM's ventilation schedule as UMI's natural-ventilation schedule.

    Args:
        ventilation: The SBEM ventilation.
        schedule: The schedule converter.
        context: The writing context at the ventilation (`<group>.Operations.HVAC.Ventilation`).
    """
    return schedule(ventilation.Schedule, context.location("Schedule"))


# --- Natural-ventilation limits and scheduled ventilation (UP-9) --------------------------------


@rule("vent.natural_limits", to="sbem")
def natural_limits_to_sbem(ventilation: ZoneVentilation, *, context: RuleContext) -> None:
    """Report UMI's natural-ventilation limits and switches that differ from Basilisk's defaults (UP-9)."""
    report_upstream(ventilation, "vent.natural_limits", context)


@rule("vent.natural_limits", to="umi")
def natural_limits_to_umi(*, context: RuleContext) -> dict[str, object]:
    """Return Basilisk's defaults for the natural-ventilation limits and switches, noting each."""
    return upstream_defaults(ZoneVentilation, "vent.natural_limits", context)


@rule("vent.scheduled", to="sbem")
def scheduled_to_sbem(ventilation: ZoneVentilation, *, context: RuleContext) -> None:
    """Report UMI's scheduled ventilation that differs from what writing gives back (UP-9).

    The scheduled-ventilation schedule is lost unless it is the natural-ventilation schedule,
    which writing uses for it.
    """
    report_upstream(ventilation, "vent.scheduled", context, skip=("ScheduledVentilationSchedule",))
    scheduled, natural = ventilation.scheduled_ventilation_schedule, ventilation.nat_vent_schedule
    if scheduled != natural:
        context.lose(
            "ScheduledVentilationSchedule",
            json_value(scheduled),
            replacement=json_value(natural),
            rule="vent.scheduled",
            reason="SBEM has no scheduled ventilation yet; writing gives the natural-ventilation schedule",
            upstream="UP-9",
        )


@rule("vent.scheduled", to="umi")
def scheduled_to_umi(natural_schedule: YearSchedule, *, context: RuleContext) -> dict[str, object]:
    """Return Basilisk's defaults for scheduled ventilation, noting each.

    UMI requires a scheduled-ventilation schedule; the natural-ventilation schedule is written.

    Args:
        natural_schedule: The UMI natural-ventilation schedule written.
        context: The writing context at the SBEM component that holds the ventilation settings.
    """
    context.note(
        "",
        natural_schedule.name,
        rule="vent.scheduled",
        reason="SBEM has no scheduled ventilation; UMI needs a schedule, so the natural-ventilation one is written",
    )
    return {
        **upstream_defaults(ZoneVentilation, "vent.scheduled", context),
        "scheduled_ventilation_schedule": natural_schedule,
    }


# --- Ventilation settings, whole ----------------------------------------------------------------


def zone_ventilation_to_sbem(ventilation: ZoneVentilation, *, context: RuleContext) -> InfiltrationParts:
    """Read UMI ventilation settings: the infiltration, and the losses of what SBEM lacks.

    The natural-ventilation switch and schedule go to SBEM's ventilation, which
    `conditioning.ventilation_to_sbem` assembles.

    Args:
        ventilation: The UMI ventilation settings.
        context: Their reading context (`/VentilationSettings/<i>`).
    """
    parts = infiltration_to_sbem(ventilation, context=context)
    natural_limits_to_sbem(ventilation, context=context)
    scheduled_to_sbem(ventilation, context=context)
    return parts


def zone_ventilation_to_umi(
    envelope: ZoneEnvelopeComponent,
    ventilation: VentilationComponent,
    *,
    schedule: ScheduleToUmi,
    context: RuleContext,
) -> ZoneVentilation:
    """Write UMI ventilation settings from a zone's infiltration and ventilation.

    The settings take the infiltration's name and metadata (data-model.md).

    Args:
        envelope: The zone's envelope (its three infiltrations).
        ventilation: The zone's ventilation (provider and schedule).
        schedule: The schedule converter.
        context: The writing context at the group (`perimeter`).
    """
    natural_schedule = natural_schedule_to_umi(
        ventilation, schedule=schedule, context=context.child("Operations.HVAC.Ventilation")
    )
    here = context.child(_INFILTRATION_PATH)
    fields: dict[str, object] = {
        **identity_to_umi(envelope.Infiltration, here),
        **infiltration_to_umi(
            envelope.Infiltration,
            envelope.AtticInfiltration,
            envelope.BasementInfiltration,
            context=context.child("Envelope"),
        ),
        "is_nat_vent_on": provider_to_umi(ventilation.Provider)[1],
        "nat_vent_schedule": natural_schedule,
        **natural_limits_to_umi(context=here),
        **scheduled_to_umi(natural_schedule, context=here),
    }
    return ZoneVentilation.model_validate(fields)


def range_problems(ventilation: ZoneVentilation, *, pointer: str, template: str | None) -> list[Problem]:
    """Return the range problems of UMI ventilation settings (research R3): a negative infiltration.

    Args:
        ventilation: The UMI ventilation settings.
        pointer: Their JSON pointer.
        template: The template affected.
    """
    if ventilation.infiltration < 0:
        return [
            Problem(
                f"{pointer}/Infiltration",
                template,
                "infiltration.ach",
                f"Infiltration is {ventilation.infiltration!r} air changes per hour; SBEM needs at least 0",
            )
        ]
    return []
