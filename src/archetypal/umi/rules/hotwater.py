"""Rules for domestic hot water (spec 003, research R10).

- **Flow** (`dhw.per_person`). UMI gives hot water per floor area and hour, SBEM per person and
  day. With `s(h)` the water schedule's hourly value over the reference year and `rho_p` the
  people density:

  ```text
  q_p [m³/day/person] = q_a [m³/h/m²] * Σ s(h) / (365 * rho_p)
  q_a = q_p * 365 * rho_p / Σ s(h)
  ```

  which conserves the annual hot-water volume per m². Hot water in a zone without people
  (`rho_p = 0` or people off) cannot be represented per person: it is a range problem on reading
  and a loss on writing.
- **Schedule** (`dhw.schedule`) and **settings** (`dhw.settings`: `IsOn`, supply and inlet
  temperatures) map exactly.
- **COP** as `cop.system` (in `conditioning`): `SystemCOP = COP`, `DistributionCOP = 1`.
- **Fuel** (`dhw.fuel`). UMI `Electricity`, `NaturalGas` and `Oil` map to SBEM `Electricity`,
  `NaturalGas` and `FuelOil`. SBEM `Propane` and `Steam` have no UMI counterpart and are written
  as `NaturalGas` with a loss. Basilisk's `Unset` is a range problem.
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, NamedTuple

from epinterface.sbem.components.space_use import WaterUseComponent
from epinterface.sbem.components.systems import DHWComponent

from archetypal.errors import Problem
from archetypal.umi._format import DomesticHotWaterFuelType, DomesticHotWaterSettings
from archetypal.umi.correspondence import rule
from archetypal.umi.rules._common import (
    RuleContext,
    ScheduleToSbem,
    ScheduleToUmi,
    annual_values,
    identity_to_sbem,
    identity_to_umi,
)
from archetypal.umi.rules.conditioning import cop_to_umi, system_cop

if TYPE_CHECKING:
    from collections.abc import Mapping

    from epinterface.sbem.components.schedules import YearComponent
    from epinterface.sbem.components.space_use import OccupancyComponent
    from epinterface.sbem.components.systems import DHWFuelType

    from archetypal.umi._format import ZoneLoads

__all__ = [
    "DAYS_PER_YEAR",
    "DHW_FUELS",
    "HotWaterParts",
    "dhw_to_sbem",
    "dhw_to_umi",
    "flow_per_area",
    "flow_per_person",
    "fuel_to_sbem",
    "fuel_to_umi",
    "range_problems",
    "schedule_to_sbem",
    "schedule_to_umi",
    "settings_to_sbem",
    "settings_to_umi",
]

DAYS_PER_YEAR = 365
"""Days of the reference year (research R7: non-leap)."""

DHW_FUELS: Mapping[DomesticHotWaterFuelType, DHWFuelType] = MappingProxyType({
    DomesticHotWaterFuelType.Electricity: "Electricity",
    DomesticHotWaterFuelType.NaturalGas: "NaturalGas",
    DomesticHotWaterFuelType.Oil: "FuelOil",
})
"""SBEM's hot-water fuel by UMI's. `Unset` has none (a range problem)."""

_SUBSTITUTE = DomesticHotWaterFuelType.NaturalGas
_FROM_SBEM: Mapping[str, DomesticHotWaterFuelType] = MappingProxyType({sbem: umi for umi, sbem in DHW_FUELS.items()})


# --- Flow ---------------------------------------------------------------------------------------


@rule("dhw.per_person", to="sbem")
def flow_per_person(flow_per_area: float, schedule_sum: float, people_density: float) -> float:
    """Return SBEM's daily flow per person: `q_a * Σ s(h) / (365 * rho_p)`.

    Args:
        flow_per_area: UMI's `FlowRatePerFloorArea`, m³/h per m².
        schedule_sum: `Σ s(h)`, the water schedule summed over the reference year's hours.
        people_density: `rho_p`, people per m²; must be above 0.

    Raises:
        ValueError: `people_density` is not above 0.
    """
    if people_density <= 0:
        msg = f"hot water per person needs a people density above 0, not {people_density!r}"
        raise ValueError(msg)
    return flow_per_area * schedule_sum / (DAYS_PER_YEAR * people_density)


@rule("dhw.per_person", to="umi")
def flow_per_area(flow_per_person: float, schedule_sum: float, people_density: float) -> float:
    """Return UMI's hourly flow per floor area: `q_p * 365 * rho_p / Σ s(h)`.

    Args:
        flow_per_person: SBEM's `FlowRatePerPerson`, m³/day per person.
        schedule_sum: `Σ s(h)` over the reference year; must be above 0.
        people_density: `rho_p`, people per m².

    Raises:
        ValueError: `schedule_sum` is not above 0.
    """
    if schedule_sum <= 0:
        msg = f"hot water per floor area needs a water schedule whose annual sum is above 0, not {schedule_sum!r}"
        raise ValueError(msg)
    return flow_per_person * DAYS_PER_YEAR * people_density / schedule_sum


def _flow_to_sbem(dhw: DomesticHotWaterSettings, loads: ZoneLoads, schedule_sum: float, context: RuleContext) -> float:
    """Return SBEM's flow per person; a zone without people holds none (lost unless the flow is 0)."""
    if loads.people_density > 0:
        return flow_per_person(dhw.flow_rate_per_floor_area, schedule_sum, loads.people_density)
    if dhw.flow_rate_per_floor_area != 0:
        context.lose(
            "FlowRatePerFloorArea",
            dhw.flow_rate_per_floor_area,
            replacement=0.0,
            rule="dhw.per_person",
            reason="the zone has no people, so SBEM's flow per person cannot hold this hot water",
        )
    return 0.0


def _flow_to_umi(
    dhw: DHWComponent, water_use: WaterUseComponent, occupancy: OccupancyComponent, context: RuleContext
) -> float:
    """Return UMI's flow per floor area, reporting hot water UMI cannot read back."""
    flow = water_use.FlowRatePerPerson
    schedule_sum = float(annual_values(water_use.Schedule).sum())
    if schedule_sum <= 0:
        if flow != 0:
            context.lose(
                "Operations.SpaceUse.WaterUse.FlowRatePerPerson",
                flow,
                replacement=0.0,
                rule="dhw.per_person",
                reason="the water schedule is 0 all year, so no flow per floor area gives this hot water",
            )
        return 0.0
    result = flow_per_area(flow, schedule_sum, occupancy.PeopleDensity)
    if dhw.IsOn and flow != 0 and (occupancy.PeopleDensity == 0 or not occupancy.IsOn):
        context.lose(
            "Operations.SpaceUse.WaterUse.FlowRatePerPerson",
            flow,
            replacement=result,
            rule="dhw.per_person",
            reason="hot water per person in a zone without people (density 0 or people off) has no UMI "
            "counterpart that reads back",
        )
    return result


# --- Schedule, settings and fuel ----------------------------------------------------------------


@rule("dhw.schedule", to="sbem")
def schedule_to_sbem(dhw: DomesticHotWaterSettings, *, schedule: ScheduleToSbem, context: RuleContext) -> YearComponent:
    """Read UMI's water schedule as SBEM's water-use schedule (category `WaterUse`)."""
    year = dhw.water_schedule
    if year is None:
        msg = f"{context.location('WaterSchedule')} is null; validation should have refused it"
        raise ValueError(msg)
    return schedule(year, "WaterUse", context.location("WaterSchedule"))


@rule("dhw.schedule", to="umi")
def schedule_to_umi(
    water_use: WaterUseComponent, *, schedule: ScheduleToUmi, context: RuleContext
) -> dict[str, object]:
    """Write SBEM's water-use schedule as UMI's water schedule.

    Args:
        water_use: The SBEM water use.
        schedule: The schedule converter.
        context: The writing context at the water use (`<group>.Operations.SpaceUse.WaterUse`).
    """
    return {"water_schedule": schedule(water_use.Schedule, context.location("Schedule"))}


@rule("dhw.settings", to="sbem")
def settings_to_sbem(dhw: DomesticHotWaterSettings) -> dict[str, object]:
    """Return SBEM's `IsOn`, `WaterSupplyTemperature` and `WaterTemperatureInlet`: UMI's values."""
    return {
        "IsOn": dhw.is_on,
        "WaterSupplyTemperature": dhw.water_supply_temperature,
        "WaterTemperatureInlet": dhw.water_temperature_inlet,
    }


@rule("dhw.settings", to="umi")
def settings_to_umi(dhw: DHWComponent) -> dict[str, object]:
    """Return UMI's `is_on`, supply and inlet temperatures: SBEM's values."""
    return {
        "is_on": dhw.IsOn,
        "water_supply_temperature": dhw.WaterSupplyTemperature,
        "water_temperature_inlet": dhw.WaterTemperatureInlet,
    }


@rule("dhw.fuel", to="sbem")
def fuel_to_sbem(fuel: DomesticHotWaterFuelType, *, context: RuleContext) -> DHWFuelType:
    """Return SBEM's hot-water fuel for UMI's.

    Raises:
        ValueError: The fuel is `Unset`, a range problem.
    """
    if fuel not in DHW_FUELS:
        msg = f"{context.location('FuelType')}: hot-water fuel {fuel.name!r}; validation should have refused it"
        raise ValueError(msg)
    return DHW_FUELS[fuel]


@rule("dhw.fuel", to="umi")
def fuel_to_umi(fuel: DHWFuelType, *, context: RuleContext) -> DomesticHotWaterFuelType:
    """Return UMI's hot-water fuel for SBEM's; `Propane` and `Steam` are written as `NaturalGas` (lost).

    Args:
        fuel: SBEM's hot-water fuel.
        context: The writing context at the DHW (`<group>.Operations.DHW`).
    """
    if fuel in _FROM_SBEM:
        return _FROM_SBEM[fuel]
    context.lose(
        "FuelType",
        fuel,
        replacement=int(_SUBSTITUTE),
        rule="dhw.fuel",
        reason=f"UMI's hot-water fuels have no {fuel}; NaturalGas written",
    )
    return _SUBSTITUTE


# --- Hot water, whole ---------------------------------------------------------------------------


class HotWaterParts(NamedTuple):
    """The SBEM components read from UMI hot-water settings."""

    dhw: DHWComponent
    """Held by the zone's operations."""
    water_use: WaterUseComponent
    """Held by the zone's space use."""


def dhw_to_sbem(
    dhw: DomesticHotWaterSettings, loads: ZoneLoads, *, schedule: ScheduleToSbem, context: RuleContext
) -> HotWaterParts:
    """Read UMI hot-water settings into SBEM's DHW and water use.

    Both take the settings' name (data-model.md); the DHW also takes their metadata.

    Args:
        dhw: The UMI hot-water settings.
        loads: The zone's UMI loads, for the people density.
        schedule: The schedule converter.
        context: The settings' reading context (`/DomesticHotWaterSettings/<i>`).
    """
    water_schedule = schedule_to_sbem(dhw, schedule=schedule, context=context)
    schedule_sum = float(annual_values(water_schedule).sum())
    system, distribution = system_cop(dhw.coefficient_of_performance)
    identity = identity_to_sbem(dhw)
    return HotWaterParts(
        DHWComponent.model_validate({
            **identity,
            **settings_to_sbem(dhw),
            "SystemCOP": system,
            "DistributionCOP": distribution,
            "FuelType": fuel_to_sbem(dhw.fuel_type, context=context),
        }),
        WaterUseComponent(
            Name=identity["Name"] or "",
            FlowRatePerPerson=_flow_to_sbem(dhw, loads, schedule_sum, context),
            Schedule=water_schedule,
        ),
    )


def dhw_to_umi(
    dhw: DHWComponent,
    water_use: WaterUseComponent,
    occupancy: OccupancyComponent,
    *,
    schedule: ScheduleToUmi,
    context: RuleContext,
) -> DomesticHotWaterSettings:
    """Write UMI hot-water settings from a zone's DHW, water use and occupancy.

    The settings take the DHW's name and metadata (data-model.md).

    Args:
        dhw: The zone's DHW.
        water_use: The zone's water use.
        occupancy: The zone's occupancy, for the people density.
        schedule: The schedule converter.
        context: The writing context at the group (`perimeter`).
    """
    here = context.child("Operations.DHW")
    fields: dict[str, object] = {
        **identity_to_umi(dhw, here),
        **settings_to_umi(dhw),
        "coefficient_of_performance": cop_to_umi(dhw.SystemCOP, dhw.DistributionCOP, context=here),
        "fuel_type": fuel_to_umi(dhw.FuelType, context=here),
        "flow_rate_per_floor_area": _flow_to_umi(dhw, water_use, occupancy, context),
        **schedule_to_umi(water_use, schedule=schedule, context=context.child("Operations.SpaceUse.WaterUse")),
    }
    return DomesticHotWaterSettings.model_validate(fields)


def range_problems(
    dhw: DomesticHotWaterSettings, loads: ZoneLoads | None, *, pointer: str, template: str | None
) -> list[Problem]:
    """Return the range problems of UMI hot-water settings (research R3, R10).

    `Unset` fuel; for hot water that is on, a COP of 0 or less, a supply temperature not above
    the inlet temperature, temperatures outside SBEM's [0, 100] °C, a negative flow, and a
    flow in a zone without people (`rho_p = 0` or people off).

    Args:
        dhw: The UMI hot-water settings.
        loads: The loads of the zone that uses them, or `None` when unknown.
        pointer: The settings' JSON pointer.
        template: The template affected.
    """
    problems: list[Problem] = []

    def problem(key: str, rule_id: str, message: str) -> None:
        problems.append(Problem(f"{pointer}/{key}", template, rule_id, message))

    if dhw.fuel_type not in DHW_FUELS:
        problem("FuelType", "dhw.fuel", "the hot-water fuel is Unset; SBEM needs a fuel")
    for key, value in (
        ("WaterSupplyTemperature", dhw.water_supply_temperature),
        ("WaterTemperatureInlet", dhw.water_temperature_inlet),
    ):
        if not 0 <= value <= 100:  # noqa: PLR2004 - SBEM's bounds, in °C
            problem(key, "dhw.settings", f"{key} is {value!r} °C; SBEM accepts 0 to 100")
    if dhw.water_supply_temperature <= dhw.water_temperature_inlet:
        problem(
            "WaterSupplyTemperature",
            "dhw.settings",
            f"the supply temperature ({dhw.water_supply_temperature!r} °C) must be above the inlet temperature "
            f"({dhw.water_temperature_inlet!r} °C)",
        )
    if dhw.flow_rate_per_floor_area < 0:
        problem("FlowRatePerFloorArea", "dhw.per_person", "the hot-water flow is negative")
    if dhw.is_on and dhw.coefficient_of_performance <= 0:
        problem(
            "CoefficientOfPerformance",
            "cop.system",
            f"hot water is on with a COP of {dhw.coefficient_of_performance!r}; it must be above 0",
        )
    if (
        loads is not None
        and dhw.is_on
        and dhw.flow_rate_per_floor_area > 0
        and (loads.people_density <= 0 or not loads.is_people_on)
    ):
        problem(
            "FlowRatePerFloorArea",
            "dhw.per_person",
            "the zone has hot water but no people (people density 0 or people off); SBEM gives hot water per person",
        )
    return problems
