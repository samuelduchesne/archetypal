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
  `vent.scheduled`). UP-9's fields of `VentilationComponent` take UMI's names and values. A
  minimum outdoor temperature not below the maximum, which SBEM refuses, is lost with SBEM's
  band kept. An always-on scheduled-ventilation schedule is SBEM's `None` (constant), which
  writes back as the natural-ventilation schedule when that is always on too, else as an
  always-on schedule (noted). UMI's airflow-network switch (`Afn`) has no SBEM field: UP-9
  does not add it, so reading reports it when on and writing gives Basilisk's default.

The VentilationComponent itself, which also holds the conditioning's fresh air, economizer and
heat recovery, is assembled by `archetypal.umi.rules.conditioning`.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple, cast

from epinterface.sbem.components.envelope import InfiltrationComponent

from archetypal.errors import Problem
from archetypal.umi._format import ZoneVentilation
from archetypal.umi.correspondence import rule
from archetypal.umi.rules._common import (
    all_values_equal,
    identity_to_sbem,
    identity_to_umi,
    optional_schedule_to_sbem,
    optional_schedule_to_umi,
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
    from archetypal.umi.rules._common import (
        RuleContext,
        ScheduleToSbem,
        ScheduleToUmi,
    )

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

_LIMITS: tuple[tuple[str, str], ...] = (
    ("NatVentMinOutdoorAirTemp", "nat_vent_min_outdoor_air_temp"),
    ("NatVentMaxOutdoorAirTemp", "nat_vent_max_outdoor_air_temp"),
    ("NatVentMaxRelHumidity", "nat_vent_max_rel_humidity"),
    ("NatVentZoneTempSetpoint", "nat_vent_zone_temp_setpoint"),
    ("IsWindOn", "is_wind_on"),
    ("IsBuoyancyOn", "is_buoyancy_on"),
)
_TEMPERATURE_RANGE = (-100.0, 100.0)


@rule("vent.natural_limits", to="sbem")
def natural_limits_to_sbem(ventilation: ZoneVentilation, *, context: RuleContext) -> dict[str, object]:
    """Read UMI's natural-ventilation limits and switches as UP-9's fields of SBEM's ventilation.

    A temperature outside SBEM's [-100, 100] °C, a humidity outside [0, 100] %, or a minimum
    outdoor temperature not below the maximum is lost, SBEM's default kept. The airflow-network
    switch, which UP-9 does not add, is reported when on.

    Args:
        ventilation: The UMI ventilation settings.
        context: Their reading context.

    Returns:
        The SBEM fields by name.
    """
    report_upstream(ventilation, "vent.natural_limits", context)
    fields: dict[str, object] = {key: getattr(ventilation, name) for key, name in _LIMITS}
    low, high = _TEMPERATURE_RANGE
    bounds = {
        "NatVentMinOutdoorAirTemp": (low, high),
        "NatVentMaxOutdoorAirTemp": (low, high),
        "NatVentZoneTempSetpoint": (low, high),
        "NatVentMaxRelHumidity": (0.0, 100.0),
    }
    for key, (lowest, highest) in bounds.items():
        value = cast("float", fields[key])
        if not lowest <= value <= highest:
            del fields[key]
            context.lose(
                key,
                value,
                rule="vent.natural_limits",
                reason=f"SBEM accepts {lowest} to {highest}; its default is kept",
            )
    minimum, maximum = fields.get("NatVentMinOutdoorAirTemp"), fields.get("NatVentMaxOutdoorAirTemp")
    if minimum is not None and maximum is not None and cast("float", minimum) >= cast("float", maximum):
        for key in ("NatVentMinOutdoorAirTemp", "NatVentMaxOutdoorAirTemp"):
            context.lose(
                key,
                cast("float", fields.pop(key)),
                rule="vent.natural_limits",
                reason="SBEM needs a minimum outdoor temperature below the maximum; its band is kept",
            )
    return fields


@rule("vent.natural_limits", to="umi")
def natural_limits_to_umi(ventilation: VentilationComponent, *, context: RuleContext) -> dict[str, object]:
    """Write SBEM's natural-ventilation limits and switches (UP-9).

    SBEM's `None` humidity limit or indoor limit (no limit) has no UMI value: it is written as
    the widest UMI accepts (100 % and -100 °C) and noted. The airflow-network switch takes
    Basilisk's default (noted).

    Args:
        ventilation: The SBEM ventilation.
        context: The writing context at it (`<group>.Operations.HVAC.Ventilation`).
    """
    fields: dict[str, object] = upstream_defaults(ZoneVentilation, "vent.natural_limits", context)
    for key, name in _LIMITS:
        value: object = getattr(ventilation, key)
        if value is None:
            value = 100.0 if key == "NatVentMaxRelHumidity" else _TEMPERATURE_RANGE[0]
            context.note(
                key,
                value,
                rule="vent.natural_limits",
                reason="SBEM's None is no limit; UMI needs a value, so the widest is written",
            )
        fields[name] = value
    return fields


_SCHEDULED: tuple[tuple[str, str], ...] = (
    ("IsScheduledVentilationOn", "is_scheduled_ventilation_on"),
    ("ScheduledVentilationAch", "scheduled_ventilation_ach"),
    ("ScheduledVentilationSetpoint", "scheduled_ventilation_setpoint"),
)


@rule("vent.scheduled", to="sbem")
def scheduled_to_sbem(
    ventilation: ZoneVentilation, *, schedule: ScheduleToSbem, context: RuleContext
) -> dict[str, object]:
    """Read UMI's scheduled ventilation as UP-9's fields of SBEM's ventilation.

    The schedule may be a Fraction or AnyNumber multiplier; an always-on one is SBEM's `None`
    (constant). A negative air-change rate or a setpoint outside [-100, 100] °C is lost.

    Args:
        ventilation: The UMI ventilation settings.
        schedule: The schedule converter.
        context: Their reading context.

    Returns:
        The SBEM fields by name.
    """
    fields: dict[str, object] = {key: getattr(ventilation, name) for key, name in _SCHEDULED}
    checks = (
        ("ScheduledVentilationAch", ventilation.scheduled_ventilation_ach >= 0, "at least 0"),
        (
            "ScheduledVentilationSetpoint",
            _TEMPERATURE_RANGE[0] <= ventilation.scheduled_ventilation_setpoint <= _TEMPERATURE_RANGE[1],
            "in [-100, 100]",
        ),
    )
    for key, valid, expected in checks:
        if not valid:
            context.lose(
                key,
                cast("float", fields.pop(key)),
                rule="vent.scheduled",
                reason=f"SBEM's {key} must be {expected}; its default is kept",
            )
    fields["ScheduledVentilationSchedule"] = optional_schedule_to_sbem(
        ventilation.scheduled_ventilation_schedule,
        "ScheduledVentilationSchedule",
        "Window",
        schedule=schedule,
        context=context,
        rule_id="vent.scheduled",
        limits=("Fraction", "AnyNumber"),
    )
    return fields


@rule("vent.scheduled", to="umi")
def scheduled_to_umi(
    ventilation: VentilationComponent,
    natural_schedule: YearSchedule,
    *,
    schedule: ScheduleToUmi,
    context: RuleContext,
) -> dict[str, object]:
    """Write SBEM's scheduled ventilation (UP-9).

    SBEM's `None` schedule (constant) is written as the natural-ventilation schedule when that
    is always on, so equal schedules stay one component, else as an always-on schedule (noted).

    Args:
        ventilation: The SBEM ventilation.
        natural_schedule: The UMI natural-ventilation schedule written.
        schedule: The schedule converter.
        context: The writing context at the ventilation.
    """
    fields: dict[str, object] = {name: getattr(ventilation, key) for key, name in _SCHEDULED}
    if ventilation.ScheduledVentilationSetpoint is None:
        fields["scheduled_ventilation_setpoint"] = _TEMPERATURE_RANGE[0]
        context.note(
            "ScheduledVentilationSetpoint",
            _TEMPERATURE_RANGE[0],
            rule="vent.scheduled",
            reason="SBEM's None is no indoor limit; UMI needs a value, so the lowest SBEM accepts is written",
        )
    year = ventilation.ScheduledVentilationSchedule
    if year is None and all_values_equal(natural_schedule, 1.0):
        fields["scheduled_ventilation_schedule"] = natural_schedule
        return fields
    fields["scheduled_ventilation_schedule"] = optional_schedule_to_umi(
        year, "ScheduledVentilationSchedule", schedule=schedule, context=context, rule_id="vent.scheduled"
    )
    return fields


# --- Ventilation settings, whole ----------------------------------------------------------------


def zone_ventilation_to_sbem(ventilation: ZoneVentilation, *, context: RuleContext) -> InfiltrationParts:
    """Read UMI ventilation settings: the infiltration.

    The natural-ventilation switch, schedule and limits and the scheduled ventilation go to
    SBEM's ventilation, which `conditioning.ventilation_to_sbem` assembles.

    Args:
        ventilation: The UMI ventilation settings.
        context: Their reading context (`/VentilationSettings/<i>`).
    """
    return infiltration_to_sbem(ventilation, context=context)


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
    at_ventilation = context.child("Operations.HVAC.Ventilation")
    natural_schedule = natural_schedule_to_umi(ventilation, schedule=schedule, context=at_ventilation)
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
        **natural_limits_to_umi(ventilation, context=at_ventilation),
        **scheduled_to_umi(ventilation, natural_schedule, schedule=schedule, context=at_ventilation),
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
