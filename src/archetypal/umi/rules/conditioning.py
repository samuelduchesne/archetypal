"""Rules for thermostats, heating and cooling systems, fuels and mechanical ventilation.

Spec 003, research R9 and R10.

- **Thermostat** (`thermostat.constant`). Reading gives constant heating and cooling setpoint
  schedules at UMI's setpoints. Writing takes the heating schedule's maximum and the cooling
  schedule's minimum, the occupied setpoints; the hours of a setback are lost, with their count
  and mean difference over the reference year.
- **Switches** (`conditioning.switches`). `IsHeatingOn = false` gives `Heating = None`
  (epinterface's off), and cooling likewise.
- **COP** (`cop.system`). `SystemCOP = COP` with `DistributionCOP = 1`; writing gives
  `COP = SystemCOP * DistributionCOP`, which conserves consumed energy for a given delivered
  energy, and the split is lost when `DistributionCOP ≠ 1`. Hot water uses the same rule.
- **Fuels** (`fuel.system`). Through `FUEL_TABLE`, data-model.md's fuel table: several UMI
  fuels SBEM merges and the fuels one side lacks are lost, with the fuel substituted.
- **Mechanical ventilation** (`conditioning.fresh_air`, `conditioning.economizer`,
  `conditioning.heat_recovery`). Fresh air per area and per person map exactly (SBEM caps both
  at 0.05, above which is a range problem); economizer and heat-recovery types map by name.
  SBEM's demand control (`DCV`) has no UMI field: a value other than `NoDCV` is lost on
  writing. `IsMechVentOn` goes to SBEM's provider with the natural switch (`vent.provider`).
- **Availability, outdoor-air schedule and limits** (`conditioning.availability`,
  `conditioning.mech_vent_schedule`, `conditioning.limits`, UP-9). The heating and cooling
  availability schedules and the mechanical outdoor-air schedule map to SBEM's optional
  schedules, whose `None` is always on: an always-on UMI schedule reads as `None`, and `None`
  writes as an always-on schedule (noted); a schedule without Fraction limits is lost. The
  ideal-loads limit types and the flows and capacities per floor area map exactly; SBEM's
  autosized (`None`) flow or capacity has no UMI value, so writing drops it from the limit type
  (lost) and gives Basilisk's default value.
- **Heat-recovery effectiveness** (`conditioning.heat_recovery_efficiency`, UP-2). Sensible and
  latent effectiveness map exactly to SBEM's numeric fields; a value outside [0, 1] is lost and
  SBEM's assumed constant kept. Writing gives the value SBEM uses: its `None` is the assumed
  constant (0.70 sensible, 0.65 latent, Basilisk's defaults too).

`ventilation_to_sbem` assembles SBEM's `VentilationComponent` from the conditioning and the
ventilation settings; `conditioning_to_sbem` and `conditioning_to_umi` translate a whole
`ZoneConditioning`.
"""

from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, NamedTuple

import numpy as np
from epinterface.sbem.components.space_use import ThermostatComponent
from epinterface.sbem.components.systems import (
    ConditioningSystemsComponent,
    ThermalSystemComponent,
    VentilationComponent,
)

from archetypal.errors import Problem
from archetypal.reduction.schedules import to_year_component
from archetypal.umi._format import EconomizerType, FuelType, HeatRecoveryType, IdealSystemLimit, ZoneConditioning
from archetypal.umi.correspondence import rule
from archetypal.umi.report import NoteKind
from archetypal.umi.rules._common import (
    ALWAYS_ON,
    annual_values,
    identity_to_umi,
    json_value,
    optional_schedule_to_sbem,
    optional_schedule_to_umi,
)
from archetypal.umi.rules.ventilation import (
    natural_limits_to_sbem,
    natural_schedule_to_sbem,
    provider_to_sbem,
    provider_to_umi,
    scheduled_to_sbem,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from epinterface.sbem.components.schedules import YearComponent
    from epinterface.sbem.components.systems import (
        EconomizerMethod,
        HRVMethod,
        ZoneHVACComponent,
    )
    from epinterface.sbem.components.systems import FuelType as SbemFuel
    from pydantic import BaseModel

    from archetypal.umi._format import ZoneVentilation
    from archetypal.umi.rules._common import (
        RuleContext,
        ScheduleToSbem,
        ScheduleToUmi,
    )

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

# (SBEM slot and conditioning type, name suffix, UMI fields: switch, COP, fuel)
_SYSTEMS: tuple[tuple[Literal["Heating", "Cooling"], str, tuple[str, str, str]], ...] = (
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
        _lose_unless_default(system, _SYSTEM_ONLY, rule_id="cop.system", context=here)
    _lose_unless_default(systems, _SYSTEMS_ONLY, rule_id="conditioning.switches", context=context)
    return fields


# SBEM fields of the systems that UMI has no place for; reading gives each its SBEM default.
_SYSTEM_ONLY: tuple[str, ...] = ("EIRTemperatureSlope", "EIRReferenceTemperature")
_SYSTEMS_ONLY: tuple[str, ...] = (
    "MaximumHeatingSupplyAirTemperature",
    "MinimumCoolingSupplyAirTemperature",
    "SpecificFanPower",
)


def _same(value: object, default: object) -> bool:
    """Equal, or two numbers closer than 1e-12 (what `diff_archetypes` counts as equal)."""
    if isinstance(value, float) and isinstance(default, float):
        return abs(value - default) < 1e-12  # noqa: PLR2004 - the diff's absolute tolerance
    return value == default


def _lose_unless_default(component: BaseModel, keys: tuple[str, ...], *, rule_id: str, context: RuleContext) -> None:
    """Report each SBEM-only field of `component` whose value is not SBEM's default as lost."""
    model_fields = type(component).model_fields
    for key in keys:
        if key not in model_fields:  # pragma: no cover - an older fork without the field
            continue
        value: object = getattr(component, key)
        default: object = model_fields[key].get_default(call_default_factory=True)
        if not _same(value, default):
            context.lose(
                key,
                json_value(value),
                replacement=json_value(default),
                rule=rule_id,
                reason=f"UMI has no place for {key}; reading the library back gives SBEM's default",
            )


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
    return VentilationComponent.model_validate({
        "Name": conditioning.name or "",
        "FreshAirPerFloorArea": area,
        "FreshAirPerPerson": person,
        "Schedule": natural_schedule_to_sbem(ventilation, schedule=schedule, context=ventilation_context),
        "MechVentSchedule": mech_vent_schedule_to_sbem(conditioning, schedule=schedule, context=context),
        "Provider": provider,
        "HRV": heat_recovery,
        "Economizer": economizer,
        "DCV": "NoDCV",
        **heat_recovery_efficiency_to_sbem(conditioning, context=context),
        **natural_limits_to_sbem(ventilation, context=ventilation_context),
        **scheduled_to_sbem(ventilation, schedule=schedule, context=ventilation_context),
    })


# --- Effectiveness (UP-2), availability, outdoor-air schedule and limits (UP-9) -----------


_EFFECTIVENESS: tuple[tuple[str, str, str], ...] = (
    ("heat_recovery_efficiency_sensible", "SensibleHeatRecoveryEffectiveness", "sensible_heat_recovery_effectiveness"),
    ("heat_recovery_efficiency_latent", "LatentHeatRecoveryEffectiveness", "latent_heat_recovery_effectiveness"),
)
"""UMI field, SBEM field and SBEM property (the value used) of each heat-recovery effectiveness."""


@rule("conditioning.heat_recovery_efficiency", to="sbem")
def heat_recovery_efficiency_to_sbem(conditioning: ZoneConditioning, *, context: RuleContext) -> dict[str, float]:
    """Return UMI's heat-recovery effectiveness as SBEM's (UP-2); a value outside [0, 1] is lost.

    Args:
        conditioning: The UMI conditioning.
        context: Its reading context; a lost value keeps SBEM's assumed constant.

    Returns:
        SBEM's `SensibleHeatRecoveryEffectiveness` and `LatentHeatRecoveryEffectiveness` that
        are in range, by name.
    """
    fields: dict[str, float] = {}
    for name, key, _ in _EFFECTIVENESS:
        value: float = getattr(conditioning, name)
        if 0 <= value <= 1:
            fields[key] = value
        else:
            context.lose(
                _key(name),
                value,
                rule="conditioning.heat_recovery_efficiency",
                reason="SBEM accepts an effectiveness of 0 to 1; its assumed constant is kept",
            )
    return fields


@rule("conditioning.heat_recovery_efficiency", to="umi")
def heat_recovery_efficiency_to_umi(ventilation: VentilationComponent) -> dict[str, float]:
    """Return SBEM's heat-recovery effectiveness as UMI's (UP-2): the value SBEM uses.

    SBEM's `None` is its assumed constant, which is written.
    """
    return {name: getattr(ventilation, used) for name, _, used in _EFFECTIVENESS}


_AVAILABILITY = (
    ("heating_schedule", "HeatingSchedule", "HeatingAvailabilitySchedule"),
    ("cooling_schedule", "CoolingSchedule", "CoolingAvailabilitySchedule"),
)


@rule("conditioning.availability", to="sbem")
def availability_to_sbem(
    conditioning: ZoneConditioning, *, schedule: ScheduleToSbem, context: RuleContext
) -> dict[str, YearComponent | None]:
    """Read the heating and cooling availability schedules (UP-9); always on is SBEM's `None`.

    Args:
        conditioning: The UMI conditioning.
        schedule: The schedule converter.
        context: Its reading context.

    Returns:
        SBEM's `HeatingAvailabilitySchedule` and `CoolingAvailabilitySchedule`.
    """
    return {
        target: optional_schedule_to_sbem(
            getattr(conditioning, field),
            key,
            "Equipment",
            schedule=schedule,
            context=context,
            rule_id="conditioning.availability",
        )
        for field, key, target in _AVAILABILITY
    }


@rule("conditioning.availability", to="umi")
def availability_to_umi(
    systems: ConditioningSystemsComponent, *, schedule: ScheduleToUmi, context: RuleContext
) -> dict[str, object]:
    """Write the heating and cooling availability schedules (UP-9); `None` is always on (noted).

    Args:
        systems: The SBEM conditioning systems.
        schedule: The schedule converter.
        context: The writing context at them (`<group>.Operations.HVAC.ConditioningSystems`).
    """
    return {
        field: optional_schedule_to_umi(
            getattr(systems, target), target, schedule=schedule, context=context, rule_id="conditioning.availability"
        )
        for field, _, target in _AVAILABILITY
    }


@rule("conditioning.mech_vent_schedule", to="sbem")
def mech_vent_schedule_to_sbem(
    conditioning: ZoneConditioning, *, schedule: ScheduleToSbem, context: RuleContext
) -> YearComponent | None:
    """Read the mechanical outdoor-air schedule as SBEM's `MechVentSchedule` (UP-9); always on is `None`."""
    return optional_schedule_to_sbem(
        conditioning.mech_vent_schedule,
        "MechVentSchedule",
        "Window",
        schedule=schedule,
        context=context,
        rule_id="conditioning.mech_vent_schedule",
    )


@rule("conditioning.mech_vent_schedule", to="umi")
def mech_vent_schedule_to_umi(
    ventilation: VentilationComponent, *, schedule: ScheduleToUmi, context: RuleContext
) -> dict[str, object]:
    """Write SBEM's `MechVentSchedule` (UP-9); `None` is an always-on schedule (noted).

    Args:
        ventilation: The SBEM ventilation.
        schedule: The schedule converter.
        context: The writing context at it (`<group>.Operations.HVAC.Ventilation`).
    """
    return {
        "mech_vent_schedule": optional_schedule_to_umi(
            ventilation.MechVentSchedule,
            "MechVentSchedule",
            schedule=schedule,
            context=context,
            rule_id="conditioning.mech_vent_schedule",
        )
    }


# (UMI limit-type field, its key, SBEM limit type, (UMI field, SBEM field) of the flow, of the capacity)
_LIMITS: tuple[tuple[str, str, str, tuple[str, str], tuple[str, str]], ...] = (
    (
        "heating_limit_type",
        "HeatingLimitType",
        "HeatingLimitType",
        ("max_heat_flow", "MaxHeatingFlowPerFloorArea"),
        ("max_heating_capacity", "MaxHeatingCapacityPerFloorArea"),
    ),
    (
        "cooling_limit_type",
        "CoolingLimitType",
        "CoolingLimitType",
        ("max_cool_flow", "MaxCoolingFlowPerFloorArea"),
        ("max_cooling_capacity", "MaxCoolingCapacityPerFloorArea"),
    ),
)
_USES_FLOW = frozenset({IdealSystemLimit.LimitFlowRate, IdealSystemLimit.LimitFlowRateAndCapacity})
_USES_CAPACITY = frozenset({IdealSystemLimit.LimitCapacity, IdealSystemLimit.LimitFlowRateAndCapacity})


def _limit_type(flow: bool, capacity: bool) -> IdealSystemLimit:
    return {
        (False, False): IdealSystemLimit.NoLimit,
        (True, False): IdealSystemLimit.LimitFlowRate,
        (False, True): IdealSystemLimit.LimitCapacity,
        (True, True): IdealSystemLimit.LimitFlowRateAndCapacity,
    }[flow, capacity]


@rule("conditioning.limits", to="sbem")
def limits_to_sbem(conditioning: ZoneConditioning, *, context: RuleContext) -> dict[str, object]:
    """Read the ideal-loads limits (UP-9): types by name, flows and capacities per floor area copied.

    A negative flow or capacity, which SBEM refuses, is lost and left autosized.

    Args:
        conditioning: The UMI conditioning.
        context: Its reading context.

    Returns:
        SBEM's limit fields of `ConditioningSystemsComponent`.
    """
    fields: dict[str, object] = {}
    for type_field, _, type_target, *quantities in _LIMITS:
        fields[type_target] = getattr(conditioning, type_field).name
        for field, target in quantities:
            value: float = getattr(conditioning, field)
            if value < 0:
                context.lose(
                    _key(field),
                    value,
                    rule="conditioning.limits",
                    reason="SBEM's limit cannot be negative; it is autosized",
                )
                continue
            fields[target] = value
    return fields


@rule("conditioning.limits", to="umi")
def limits_to_umi(systems: ConditioningSystemsComponent, *, context: RuleContext) -> dict[str, object]:
    """Write the ideal-loads limits (UP-9).

    A flow or capacity the limit type names that SBEM autosizes (`None`) has no UMI value: it is
    dropped from the limit type, and lost. An unset value takes Basilisk's default (noted when
    the limit type names it).

    Args:
        systems: The SBEM conditioning systems.
        context: The writing context at them (`<group>.Operations.HVAC.ConditioningSystems`).
    """
    fields: dict[str, object] = {}
    for type_field, _, type_target, flow, capacity in _LIMITS:
        limit = IdealSystemLimit[getattr(systems, type_target)]
        uses = {flow: limit in _USES_FLOW, capacity: limit in _USES_CAPACITY}
        for (field, target), used in list(uses.items()):
            value: float | None = getattr(systems, target)
            if value is not None:
                fields[field] = value
                continue
            fields[field] = _default(field)
            if used:
                uses[field, target] = False
                context.lose(
                    target,
                    None,
                    replacement=_limit_type(*uses.values()).name,
                    rule="conditioning.limits",
                    reason=f"UMI has no autosized limit; {target} is dropped from {type_target}",
                )
        written = _limit_type(*uses.values())
        if written is not limit:
            context.lose(
                type_target,
                limit.name,
                replacement=written.name,
                rule="conditioning.limits",
                reason=f"an autosized limit is dropped from {type_target}, so UMI's limit type changes",
            )
        fields[type_field] = written
    return fields


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
    systems = systems_to_sbem(conditioning, context=context).model_copy(
        update={
            **availability_to_sbem(conditioning, schedule=schedule, context=context),
            **limits_to_sbem(conditioning, context=context),
        }
    )
    return ConditioningParts(
        thermostat_to_sbem(conditioning, context=context),
        ConditioningSystemsComponent.model_validate(systems.model_dump()),
        ventilation_to_sbem(
            conditioning, ventilation, schedule=schedule, context=context, ventilation_context=ventilation_context
        ),
    )


def conditioning_to_umi(
    hvac: ZoneHVACComponent, thermostat: ThermostatComponent, *, schedule: ScheduleToUmi, context: RuleContext
) -> ZoneConditioning:
    """Write UMI conditioning from a zone's HVAC and thermostat.

    The conditioning takes the HVAC's name and metadata (data-model.md).

    Args:
        hvac: The zone's HVAC (systems and ventilation).
        thermostat: The zone's thermostat.
        schedule: The schedule converter.
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
        **heat_recovery_efficiency_to_umi(hvac.Ventilation),
        **availability_to_umi(hvac.ConditioningSystems, schedule=schedule, context=here.child("ConditioningSystems")),
        **mech_vent_schedule_to_umi(hvac.Ventilation, schedule=schedule, context=ventilation),
        **limits_to_umi(hvac.ConditioningSystems, context=here.child("ConditioningSystems")),
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
