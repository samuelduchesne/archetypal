"""Rules for thermostats, heating and cooling systems, fuels and mechanical ventilation.

Spec 003, research R9 and R10.

- **Thermostat** (`thermostat.constant`). Reading gives constant heating and cooling setpoint
  schedules at UMI's setpoints. Writing takes the heating schedule's maximum and the cooling
  schedule's minimum, the occupied setpoints; the hours of a setback are lost, with their count
  and mean difference over the reference year.
- **Switches** (`conditioning.switches`). `IsHeatingOn = false` gives `Heating = None`
  (epinterface's off), and cooling likewise.
- **COP** (`cop.system`). `SystemCOP = COP` with `DistributionCOP = 1`; writing gives
  `COP = SystemCOP × DistributionCOP`, which conserves consumed energy for a given delivered
  energy, and the split is lost when `DistributionCOP ≠ 1`. Hot water uses the same rule.
- **Fuels** (`fuel.system`). Through `FUEL_TABLE`, data-model.md's fuel table: several UMI
  fuels SBEM merges and the fuels one side lacks are lost, with the fuel substituted.
- **Mechanical ventilation** (`conditioning.fresh_air`, `conditioning.economizer`,
  `conditioning.heat_recovery`). Fresh air per area and per person map exactly (SBEM caps both
  at 0.05, above which is a range problem); economizer and heat-recovery types map by name.
  SBEM's demand control (`DCV`) has no UMI field: a value other than `NoDCV` is lost on
  writing. `IsMechVentOn` goes to SBEM's provider with the natural switch (`vent.provider`).
- **Upstream** (`conditioning.heat_recovery_efficiency` UP-2, `conditioning.availability`,
  `conditioning.mech_vent_schedule`, `conditioning.limits` UP-9). Reading reports values SBEM
  cannot hold yet as lost: effectiveness and limits when they differ from Basilisk's defaults,
  schedules unless every value is 1 (SBEM conditions and ventilates whenever a system exists).
  Writing gives Basilisk's defaults and always-on schedules (noted).

`ventilation_to_sbem` assembles SBEM's `VentilationComponent` from the conditioning and the
ventilation settings; `conditioning_to_sbem` and `conditioning_to_umi` translate a whole
`ZoneConditioning`.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple

import numpy as np
from epinterface.sbem.components.space_use import ThermostatComponent
from epinterface.sbem.components.systems import (
    ConditioningSystemsComponent,
    ThermalSystemComponent,
    VentilationComponent,
)

from archetypal.errors import Problem
from archetypal.reduction.schedules import to_year_component
from archetypal.umi._format import EconomizerType, FuelType, HeatRecoveryType, ZoneConditioning
from archetypal.umi.correspondence import rule
from archetypal.umi.report import NoteKind
from archetypal.umi.rules.loads import (
    RuleContext,
    ScheduleToSbem,
    all_values_equal,
    annual_values,
    constant_year_schedule,
    identity_to_umi,
    json_value,
    report_upstream,
    upstream_defaults,
)
from archetypal.umi.rules.ventilation import natural_schedule_to_sbem, provider_to_sbem, provider_to_umi

if TYPE_CHECKING:
    from collections.abc import Mapping

    from epinterface.sbem.components.schedules import YearComponent
    from epinterface.sbem.components.systems import (
        EconomizerMethod,
        HRVMethod,
        ZoneHVACComponent,
    )
    from epinterface.sbem.components.systems import FuelType as SbemFuel

    from archetypal.umi._format import YearSchedule, ZoneVentilation

__all__ = [
    "ALWAYS_ON",
    "FRESH_AIR_CAP",
    "FUEL_TABLE",
    "ConditioningParts",
    "FuelMapping",
    "availability_to_sbem",
    "availability_to_umi",
    "combined_cop",
    "conditioning_to_sbem",
    "conditioning_to_umi",
    "cop_to_umi",
    "economizer_to_sbem",
    "economizer_to_umi",
    "fresh_air_to_sbem",
    "fresh_air_to_umi",
    "fuel_to_sbem",
    "fuel_to_umi",
    "heat_recovery_efficiency_to_sbem",
    "heat_recovery_efficiency_to_umi",
    "heat_recovery_to_sbem",
    "heat_recovery_to_umi",
    "limits_to_sbem",
    "limits_to_umi",
    "mech_vent_schedule_to_sbem",
    "mech_vent_schedule_to_umi",
    "range_problems",
    "system_cop",
    "systems_to_sbem",
    "systems_to_umi",
    "thermostat_to_sbem",
    "thermostat_to_umi",
    "ventilation_to_sbem",
]

FRESH_AIR_CAP = 0.05
"""SBEM's upper bound on fresh air per area (m³/s·m²) and per person (m³/s·p)."""

ALWAYS_ON = "Always on"
"""The name of the schedule written where SBEM has none (availability, mechanical ventilation)."""


# --- Fuels --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FuelMapping:
    """One row of data-model.md's fuel table.

    Attributes:
        umi: Basilisk's fuel.
        sbem: SBEM's fuel.
        reads: Whether reading `umi` gives `sbem`.
        writes: Whether writing `sbem` gives `umi`.
        loss: Why the row loses information (in its direction), or `None`.
    """

    umi: FuelType
    sbem: SbemFuel
    reads: bool = True
    writes: bool = True
    loss: str | None = None


FUEL_TABLE: tuple[FuelMapping, ...] = (
    FuelMapping(FuelType.Electricity, "Electricity"),
    FuelMapping(FuelType.NaturalGas, "NaturalGas"),
    FuelMapping(FuelType.PropaneGas, "Propane"),
    FuelMapping(FuelType.FuelOil1, "FuelOil", loss="SBEM has one fuel oil; which oil it was is lost"),
    FuelMapping(FuelType.FuelOil2, "FuelOil", writes=False, loss="SBEM has one fuel oil; which oil it was is lost"),
    FuelMapping(FuelType.Diesel, "Diesel"),
    FuelMapping(FuelType.Gasoline, "Gasoline"),
    FuelMapping(FuelType.Coal, "Coal"),
    FuelMapping(FuelType.OtherFuel1, "CustomFuel", loss="SBEM has one custom fuel; which other fuel it was is lost"),
    FuelMapping(
        FuelType.OtherFuel2,
        "CustomFuel",
        writes=False,
        loss="SBEM has one custom fuel; which other fuel it was is lost",
    ),
    FuelMapping(FuelType.Steam, "Steam"),
    FuelMapping(FuelType.DistrictCooling, "ChilledWater"),
    FuelMapping(
        FuelType.DistrictHeating, "Steam", writes=False, loss="SBEM has no district heating; steam substituted"
    ),
    FuelMapping(FuelType.OtherFuel1, "WoodPellets", reads=False, loss="UMI has no wood pellets; OtherFuel1 written"),
)
"""data-model.md's fuel table, one row per direction a pair is used in. `FuelType.None_` has no
row: it is a range problem when the system is on."""

_FUEL_TO_SBEM: Mapping[FuelType, FuelMapping] = MappingProxyType({row.umi: row for row in FUEL_TABLE if row.reads})
_FUEL_TO_UMI: Mapping[str, FuelMapping] = MappingProxyType({row.sbem: row for row in FUEL_TABLE if row.writes})


@rule("fuel.system", to="sbem")
def fuel_to_sbem(fuel: FuelType, *, key: str, context: RuleContext) -> SbemFuel:
    """Return SBEM's fuel for a UMI heating or cooling fuel, reporting what the table loses.

    Args:
        fuel: `HeatingFuelType` or `CoolingFuelType`.
        key: The UMI key, for the report.
        context: The conditioning's reading context.

    Raises:
        ValueError: The fuel is `None` (0), a range problem when the system is on.
    """
    row = _FUEL_TO_SBEM.get(fuel)
    if row is None:
        msg = f"{context.location(key)}: fuel {fuel.name!r} has no SBEM fuel; validation should have refused it"
        raise ValueError(msg)
    if row.loss is not None:
        context.lose(key, int(fuel), replacement=row.sbem, rule="fuel.system", reason=row.loss)
    return row.sbem


@rule("fuel.system", to="umi")
def fuel_to_umi(fuel: SbemFuel, *, context: RuleContext) -> FuelType:
    """Return UMI's fuel for an SBEM system fuel, reporting what the table loses.

    Args:
        fuel: The system's `Fuel`.
        context: The writing context at the system (`…ConditioningSystems.Heating`).
    """
    row = _FUEL_TO_UMI[fuel]
    if row.loss is not None and not row.reads:
        context.lose("Fuel", fuel, replacement=int(row.umi), rule="fuel.system", reason=row.loss)
    return row.umi


# --- COP ----------------------------------------------------------------------------------------


@rule("cop.system", to="sbem")
def system_cop(cop: float) -> tuple[float, float]:
    """Return SBEM's `(SystemCOP, DistributionCOP)` for a UMI COP: `(cop, 1.0)`."""
    return cop, 1.0


@rule("cop.system", to="umi")
def combined_cop(system: float, distribution: float) -> float:
    """Return UMI's COP for SBEM's system and distribution COPs: their product.

    The product conserves the energy consumed for a given energy delivered.
    """
    return system * distribution


def cop_to_umi(system: float, distribution: float, *, context: RuleContext) -> float:
    """Return UMI's COP, reporting the split as lost when `DistributionCOP ≠ 1`.

    Args:
        system: SBEM's `SystemCOP`.
        distribution: SBEM's `DistributionCOP`.
        context: The writing context at the component holding both COPs.
    """
    cop = combined_cop(system, distribution)
    if distribution != 1:
        context.lose(
            "DistributionCOP",
            {"SystemCOP": system, "DistributionCOP": distribution},
            replacement=cop,
            rule="cop.system",
            reason="UMI has one COP; the product of the system and distribution COPs is written",
        )
    return cop


# --- Thermostat ---------------------------------------------------------------------------------


def _constant_setpoint(name: str, value: float) -> YearComponent:
    return to_year_component(np.full((12, 7, 24), value), name=name, category="Setpoint", limits="Temperature")


@rule("thermostat.constant", to="sbem")
def thermostat_to_sbem(conditioning: ZoneConditioning, *, context: RuleContext) -> ThermostatComponent:
    """Read UMI's setpoints as constant heating and cooling schedules.

    The thermostat takes the conditioning's name (data-model.md); its schedules are named
    `"<name> heating setpoint"` and `"<name> cooling setpoint"`.

    Args:
        conditioning: The UMI conditioning.
        context: Its reading context.
    """
    del context
    name = conditioning.name or ""
    return ThermostatComponent(
        Name=name,
        IsOn=True,
        HeatingSetpoint=conditioning.heating_setpoint,
        HeatingSchedule=_constant_setpoint(f"{name} heating setpoint", conditioning.heating_setpoint),
        CoolingSetpoint=conditioning.cooling_setpoint,
        CoolingSchedule=_constant_setpoint(f"{name} cooling setpoint", conditioning.cooling_setpoint),
    )


def _setpoint(schedule: YearComponent, scalar: float, *, heating: bool, key: str, context: RuleContext) -> float:
    """Return the occupied setpoint of a schedule, reporting setback hours and a stray scalar."""
    values = annual_values(schedule)
    setpoint = float(values.max() if heating else values.min())
    setback = values < setpoint if heating else values > setpoint
    hours = int(setback.sum())
    if hours:
        context.lose(
            f"{key}Schedule",
            {"hours": hours, "mean_difference": float(np.abs(values[setback] - setpoint).mean())},
            replacement=setpoint,
            rule="thermostat.constant",
            reason=f"UMI holds one {key.lower()} setpoint; the schedule's {'maximum' if heating else 'minimum'} "
            "is written and its setback hours over the reference year are lost",
        )
    if scalar != setpoint:
        context.lose(
            f"{key}Setpoint",
            scalar,
            replacement=setpoint,
            rule="thermostat.constant",
            reason="UMI holds one setpoint; the schedule's is written",
        )
    return setpoint


@rule("thermostat.constant", to="umi")
def thermostat_to_umi(thermostat: ThermostatComponent, *, context: RuleContext) -> dict[str, object]:
    """Write SBEM's thermostat as UMI's setpoints: heating maximum, cooling minimum.

    Args:
        thermostat: The SBEM thermostat.
        context: The writing context at the thermostat (`<group>.Operations.SpaceUse.Thermostat`).

    Returns:
        UMI's `heating_setpoint` and `cooling_setpoint`.
    """
    if not thermostat.IsOn:
        context.lose(
            "IsOn",
            value=False,
            rule="thermostat.constant",
            reason="UMI has no thermostat switch (epinterface does not read it either)",
        )
    return {
        "heating_setpoint": _setpoint(
            thermostat.HeatingSchedule, thermostat.HeatingSetpoint, heating=True, key="Heating", context=context
        ),
        "cooling_setpoint": _setpoint(
            thermostat.CoolingSchedule, thermostat.CoolingSetpoint, heating=False, key="Cooling", context=context
        ),
    }


# --- Heating and cooling systems ----------------------------------------------------------------

# (UMI system, SBEM slot, SBEM conditioning type, UMI keys: switch, COP, fuel)
_SYSTEMS = (
    ("Heating", "heating", ("is_heating_on", "heating_coeff_of_perf", "heating_fuel_type")),
    ("Cooling", "cooling", ("is_cooling_on", "cooling_coeff_of_perf", "cooling_fuel_type")),
)


def _key(model_field: str) -> str:
    alias = ZoneConditioning.model_fields[model_field].alias
    return alias or model_field


def _default(model_field: str) -> object:
    return ZoneConditioning.model_fields[model_field].default


@rule("conditioning.switches", to="sbem")
def systems_to_sbem(conditioning: ZoneConditioning, *, context: RuleContext) -> ConditioningSystemsComponent:
    """Read UMI's heating and cooling: a system when on, `None` when off.

    The systems take the conditioning's name, and each system `"<name> heating"` or
    `"<name> cooling"` (data-model.md). A system that is off holds no COP or fuel: values that
    differ from Basilisk's defaults, which writing gives back, are lost.

    Args:
        conditioning: The UMI conditioning.
        context: Its reading context.
    """
    name = conditioning.name or ""
    systems: dict[str, ThermalSystemComponent | None] = {}
    for slot, suffix, (switch, cop_field, fuel_field) in _SYSTEMS:
        if getattr(conditioning, switch):
            system, distribution = system_cop(getattr(conditioning, cop_field))
            systems[slot] = ThermalSystemComponent(
                Name=f"{name} {suffix}",
                ConditioningType=slot,
                Fuel=fuel_to_sbem(getattr(conditioning, fuel_field), key=_key(fuel_field), context=context),
                SystemCOP=system,
                DistributionCOP=distribution,
            )
            continue
        systems[slot] = None
        for field in (cop_field, fuel_field):
            value = getattr(conditioning, field)
            if value != _default(field):
                context.lose(
                    _key(field),
                    json_value(value),
                    rule="conditioning.switches",
                    reason=f"{slot.lower()} is off, so SBEM has no {slot.lower()} system to hold it",
                )
    return ConditioningSystemsComponent(Name=name, Heating=systems["Heating"], Cooling=systems["Cooling"])


@rule("conditioning.switches", to="umi")
def systems_to_umi(systems: ConditioningSystemsComponent, *, context: RuleContext) -> dict[str, object]:
    """Write SBEM's heating and cooling systems as UMI's switches, COPs and fuels.

    Args:
        systems: The SBEM conditioning systems.
        context: The writing context at them (`<group>.Operations.HVAC.ConditioningSystems`).

    Returns:
        The UMI fields by name; Basilisk's defaults (noted) for a system that is off.
    """
    fields: dict[str, object] = {}
    for slot, _, (switch, cop_field, fuel_field) in _SYSTEMS:
        system: ThermalSystemComponent | None = getattr(systems, slot)
        here = context.child(slot)
        if system is None:
            fields[switch] = False
            for field in (cop_field, fuel_field):
                fields[field] = _default(field)
                here.note(
                    "",
                    json_value(_default(field)),
                    rule="conditioning.switches",
                    reason=f"no {slot.lower()} system; Basilisk's default {_key(field)} written",
                    kind=NoteKind.DEFAULTED,
                )
            continue
        if system.ConditioningType != slot:
            here.lose(
                "ConditioningType",
                system.ConditioningType,
                replacement=slot,
                rule="conditioning.switches",
                reason=f"UMI describes heating and cooling separately; this system is written as {slot.lower()}",
            )
        fields[switch] = True
        fields[cop_field] = cop_to_umi(system.SystemCOP, system.DistributionCOP, context=here)
        fields[fuel_field] = fuel_to_umi(system.Fuel, context=here)
    return fields


# --- Mechanical ventilation ---------------------------------------------------------------------

_ECONOMIZERS: Mapping[EconomizerType, EconomizerMethod] = MappingProxyType({
    EconomizerType.NoEconomizer: "NoEconomizer",
    EconomizerType.DifferentialDryBulb: "DifferentialDryBulb",
    EconomizerType.DifferentialEnthalpy: "DifferentialEnthalpy",
})
_HEAT_RECOVERY: Mapping[HeatRecoveryType, HRVMethod] = MappingProxyType({
    HeatRecoveryType.None_: "NoHRV",
    HeatRecoveryType.Enthalpy: "Enthalpy",
    HeatRecoveryType.Sensible: "Sensible",
})


@rule("conditioning.fresh_air", to="sbem")
def fresh_air_to_sbem(conditioning: ZoneConditioning) -> tuple[float, float]:
    """Return SBEM's `(FreshAirPerFloorArea, FreshAirPerPerson)`: UMI's values unchanged."""
    return conditioning.min_fresh_air_per_area, conditioning.min_fresh_air_per_person


@rule("conditioning.fresh_air", to="umi")
def fresh_air_to_umi(ventilation: VentilationComponent, *, context: RuleContext) -> dict[str, object]:
    """Write SBEM's fresh air; demand control other than `NoDCV` is lost.

    Args:
        ventilation: The SBEM ventilation.
        context: The writing context at it (`<group>.Operations.HVAC.Ventilation`).

    Returns:
        UMI's `min_fresh_air_per_area` and `min_fresh_air_per_person`.
    """
    if ventilation.DCV != "NoDCV":
        context.lose(
            "DCV",
            ventilation.DCV,
            replacement="NoDCV",
            rule="conditioning.fresh_air",
            reason="UMI has no demand-controlled ventilation; the design fresh air is written",
        )
    return {
        "min_fresh_air_per_area": ventilation.FreshAirPerFloorArea,
        "min_fresh_air_per_person": ventilation.FreshAirPerPerson,
    }


@rule("conditioning.economizer", to="sbem")
def economizer_to_sbem(economizer: EconomizerType) -> EconomizerMethod:
    """Return SBEM's economizer for UMI's, by name."""
    return _ECONOMIZERS[economizer]


@rule("conditioning.economizer", to="umi")
def economizer_to_umi(economizer: EconomizerMethod) -> EconomizerType:
    """Return UMI's economizer for SBEM's, by name."""
    return EconomizerType[economizer]


@rule("conditioning.heat_recovery", to="sbem")
def heat_recovery_to_sbem(heat_recovery: HeatRecoveryType) -> HRVMethod:
    """Return SBEM's heat recovery for UMI's, by name (`None` is SBEM's `NoHRV`)."""
    return _HEAT_RECOVERY[heat_recovery]


@rule("conditioning.heat_recovery", to="umi")
def heat_recovery_to_umi(heat_recovery: HRVMethod) -> HeatRecoveryType:
    """Return UMI's heat recovery for SBEM's, by name."""
    return next(umi for umi, sbem in _HEAT_RECOVERY.items() if sbem == heat_recovery)


def ventilation_to_sbem(
    conditioning: ZoneConditioning,
    ventilation: ZoneVentilation,
    *,
    schedule: ScheduleToSbem,
    context: RuleContext,
    ventilation_context: RuleContext,
) -> VentilationComponent:
    """Assemble SBEM's ventilation from UMI's conditioning and ventilation settings.

    The provider comes from both switches (`vent.provider`), the schedule from the ventilation
    settings, everything else from the conditioning, whose name it takes (data-model.md).
    Without mechanical ventilation SBEM refuses an economizer or heat recovery: they are lost.

    Args:
        conditioning: The UMI conditioning.
        ventilation: The UMI ventilation settings.
        schedule: The schedule converter.
        context: The conditioning's reading context.
        ventilation_context: The ventilation settings' reading context.
    """
    provider = provider_to_sbem(conditioning.is_mech_vent_on, ventilation.is_nat_vent_on)
    area, person = fresh_air_to_sbem(conditioning)
    economizer = economizer_to_sbem(conditioning.economizer_type)
    heat_recovery = heat_recovery_to_sbem(conditioning.heat_recovery_type)
    if provider in {"None", "Natural"}:
        for key, value, off, rule_id in (
            ("EconomizerType", conditioning.economizer_type, EconomizerType.NoEconomizer, "conditioning.economizer"),
            ("HeatRecoveryType", conditioning.heat_recovery_type, HeatRecoveryType.None_, "conditioning.heat_recovery"),
        ):
            if value != off:
                context.lose(
                    key,
                    int(value),
                    replacement=int(off),
                    rule=rule_id,
                    reason="mechanical ventilation is off, and SBEM allows no economizer or heat recovery without it",
                )
        economizer, heat_recovery = "NoEconomizer", "NoHRV"
    return VentilationComponent(
        Name=conditioning.name or "",
        FreshAirPerFloorArea=area,
        FreshAirPerPerson=person,
        Schedule=natural_schedule_to_sbem(ventilation, schedule=schedule, context=ventilation_context),
        Provider=provider,
        HRV=heat_recovery,
        Economizer=economizer,
        DCV="NoDCV",
    )


# --- Upstream: effectiveness (UP-2), availability, outdoor-air schedule and limits (UP-9) --------

@rule("conditioning.heat_recovery_efficiency", to="sbem")
def heat_recovery_efficiency_to_sbem(conditioning: ZoneConditioning, *, context: RuleContext) -> None:
    """Report heat-recovery effectiveness that differs from Basilisk's default as lost (UP-2)."""
    report_upstream(conditioning, "conditioning.heat_recovery_efficiency", context)


@rule("conditioning.heat_recovery_efficiency", to="umi")
def heat_recovery_efficiency_to_umi(*, context: RuleContext) -> dict[str, object]:
    """Return Basilisk's default heat-recovery effectiveness, noting it."""
    return upstream_defaults(ZoneConditioning, "conditioning.heat_recovery_efficiency", context)


def _always_on_or_lost(year: YearSchedule | None, key: str, rule_id: str, context: RuleContext) -> None:
    if year is not None and not all_values_equal(year, 1.0):
        context.lose(
            key,
            json_value(year),
            replacement=ALWAYS_ON,
            rule=rule_id,
            reason=f"SBEM has no {key} yet; it applies whenever the system exists, as an always-on schedule",
            upstream="UP-9",
        )


def _always_on(key: str, rule_id: str, context: RuleContext) -> YearSchedule:
    context.note(
        "",
        ALWAYS_ON,
        rule=rule_id,
        reason=f"SBEM has no {key}; it applies whenever the system exists, so an always-on schedule is written",
    )
    return constant_year_schedule(ALWAYS_ON, 1.0)


@rule("conditioning.availability", to="sbem")
def availability_to_sbem(conditioning: ZoneConditioning, *, context: RuleContext) -> None:
    """Report heating and cooling availability schedules as lost unless every value is 1 (R9)."""
    _always_on_or_lost(conditioning.heating_schedule, "HeatingSchedule", "conditioning.availability", context)
    _always_on_or_lost(conditioning.cooling_schedule, "CoolingSchedule", "conditioning.availability", context)


@rule("conditioning.availability", to="umi")
def availability_to_umi(*, context: RuleContext) -> dict[str, object]:
    """Return always-on heating and cooling availability schedules, noting them (R9)."""
    return {
        "heating_schedule": _always_on("HeatingSchedule", "conditioning.availability", context),
        "cooling_schedule": _always_on("CoolingSchedule", "conditioning.availability", context),
    }


@rule("conditioning.mech_vent_schedule", to="sbem")
def mech_vent_schedule_to_sbem(conditioning: ZoneConditioning, *, context: RuleContext) -> None:
    """Report the mechanical outdoor-air schedule as lost unless every value is 1 (UP-9)."""
    _always_on_or_lost(conditioning.mech_vent_schedule, "MechVentSchedule", "conditioning.mech_vent_schedule", context)


@rule("conditioning.mech_vent_schedule", to="umi")
def mech_vent_schedule_to_umi(*, context: RuleContext) -> dict[str, object]:
    """Return an always-on mechanical outdoor-air schedule, noting it."""
    return {"mech_vent_schedule": _always_on("MechVentSchedule", "conditioning.mech_vent_schedule", context)}


@rule("conditioning.limits", to="sbem")
def limits_to_sbem(conditioning: ZoneConditioning, *, context: RuleContext) -> None:
    """Report ideal-loads limits that differ from Basilisk's defaults as lost (UP-9; SBEM autosizes)."""
    report_upstream(conditioning, "conditioning.limits", context)


@rule("conditioning.limits", to="umi")
def limits_to_umi(*, context: RuleContext) -> dict[str, object]:
    """Return Basilisk's default ideal-loads limits, noting each."""
    return upstream_defaults(ZoneConditioning, "conditioning.limits", context)


# --- Conditioning, whole ------------------------------------------------------------------------


class ConditioningParts(NamedTuple):
    """The SBEM components read from UMI conditioning and ventilation settings."""

    thermostat: ThermostatComponent
    """Held by the zone's space use."""
    systems: ConditioningSystemsComponent
    """Held by the zone's HVAC."""
    ventilation: VentilationComponent
    """Held by the zone's HVAC."""


def conditioning_to_sbem(
    conditioning: ZoneConditioning,
    ventilation: ZoneVentilation,
    *,
    schedule: ScheduleToSbem,
    context: RuleContext,
    ventilation_context: RuleContext,
) -> ConditioningParts:
    """Read UMI conditioning into SBEM's thermostat, systems and ventilation.

    The zone's `ZoneHVACComponent` takes the conditioning's name and metadata (data-model.md).

    Args:
        conditioning: The UMI conditioning.
        ventilation: The zone's UMI ventilation settings (natural switch and schedule).
        schedule: The schedule converter.
        context: The conditioning's reading context (`/ZoneConditionings/<i>`).
        ventilation_context: The ventilation settings' reading context.
    """
    parts = ConditioningParts(
        thermostat_to_sbem(conditioning, context=context),
        systems_to_sbem(conditioning, context=context),
        ventilation_to_sbem(
            conditioning, ventilation, schedule=schedule, context=context, ventilation_context=ventilation_context
        ),
    )
    heat_recovery_efficiency_to_sbem(conditioning, context=context)
    availability_to_sbem(conditioning, context=context)
    mech_vent_schedule_to_sbem(conditioning, context=context)
    limits_to_sbem(conditioning, context=context)
    return parts


def conditioning_to_umi(
    hvac: ZoneHVACComponent, thermostat: ThermostatComponent, *, context: RuleContext
) -> ZoneConditioning:
    """Write UMI conditioning from a zone's HVAC and thermostat.

    The conditioning takes the HVAC's name and metadata (data-model.md).

    Args:
        hvac: The zone's HVAC (systems and ventilation).
        thermostat: The zone's thermostat.
        context: The writing context at the group (`perimeter`).
    """
    here = context.child("Operations.HVAC")
    ventilation = here.child("Ventilation")
    fields: dict[str, object] = {
        **identity_to_umi(hvac, here),
        **thermostat_to_umi(thermostat, context=context.child("Operations.SpaceUse.Thermostat")),
        **systems_to_umi(hvac.ConditioningSystems, context=here.child("ConditioningSystems")),
        "is_mech_vent_on": provider_to_umi(hvac.Ventilation.Provider)[0],
        **fresh_air_to_umi(hvac.Ventilation, context=ventilation),
        "economizer_type": economizer_to_umi(hvac.Ventilation.Economizer),
        "heat_recovery_type": heat_recovery_to_umi(hvac.Ventilation.HRV),
        **heat_recovery_efficiency_to_umi(context=ventilation),
        **availability_to_umi(context=here.child("ConditioningSystems")),
        **mech_vent_schedule_to_umi(context=ventilation),
        **limits_to_umi(context=here.child("ConditioningSystems")),
    }
    return ZoneConditioning.model_validate(fields)


def range_problems(conditioning: ZoneConditioning, *, pointer: str, template: str | None) -> list[Problem]:
    """Return the range problems of UMI conditioning (research R3, R10).

    Fresh air outside SBEM's [0, 0.05]; for a system that is on, a COP of 0 or less or no fuel.

    Args:
        conditioning: The UMI conditioning.
        pointer: Its JSON pointer.
        template: The template affected.
    """
    problems: list[Problem] = []
    for field in ("min_fresh_air_per_area", "min_fresh_air_per_person"):
        value: float = getattr(conditioning, field)
        if not 0 <= value <= FRESH_AIR_CAP:
            problems.append(
                Problem(
                    f"{pointer}/{_key(field)}",
                    template,
                    "conditioning.fresh_air",
                    f"{_key(field)} is {value!r}; SBEM accepts 0 to {FRESH_AIR_CAP}",
                )
            )
    for slot, _, (switch, cop_field, fuel_field) in _SYSTEMS:
        if not getattr(conditioning, switch):
            continue
        cop: float = getattr(conditioning, cop_field)
        if cop <= 0:
            problems.append(
                Problem(
                    f"{pointer}/{_key(cop_field)}",
                    template,
                    "cop.system",
                    f"{slot.lower()} is on with a COP of {cop!r}; it must be above 0",
                )
            )
        fuel: FuelType = getattr(conditioning, fuel_field)
        if fuel not in _FUEL_TO_SBEM:
            problems.append(
                Problem(
                    f"{pointer}/{_key(fuel_field)}",
                    template,
                    "fuel.system",
                    f"{slot.lower()} is on with fuel {fuel.name.rstrip('_')!r}; a fuel is required",
                )
            )
    return problems
