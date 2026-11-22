"""The hot-water rules (spec 003 T021, research R10)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from epinterface.sbem.components.space_use import OccupancyComponent, WaterUseComponent
from epinterface.sbem.components.systems import DHWComponent
from hypothesis import given
from hypothesis import strategies as st

from archetypal.reduction.schedules import to_year_component
from archetypal.umi._format import DomesticHotWaterFuelType, DomesticHotWaterSettings, ZoneLoads
from archetypal.umi.correspondence import get_rule
from archetypal.umi.report import LossKind
from archetypal.umi.rules import hotwater as module
from archetypal.umi.rules._common import annual_values, constant_year_schedule
from archetypal.umi.rules.hotwater import (
    DHW_FUELS,
    dhw_to_sbem,
    dhw_to_umi,
    flow_per_area,
    flow_per_person,
    fuel_to_sbem,
    fuel_to_umi,
    range_problems,
)

from .test_rules_loads import reading, sbem_schedule, writing

if TYPE_CHECKING:
    from epinterface.sbem.components.schedules import YearComponent, YearScheduleCategory
    from epinterface.sbem.components.systems import DHWFuelType as SbemDhwFuel

    from archetypal.umi._format import YearSchedule

POINTER = "/DomesticHotWaterSettings/0"


def office_day() -> np.ndarray:
    hours = np.zeros(24)
    hours[8:18] = 0.5
    return hours


def read_schedule(year: YearSchedule, category: YearScheduleCategory, pointer: str) -> YearComponent:
    """Office hours on weekdays, nothing at weekends: Σ s(h) = 5 h * 261 weekdays."""
    del year, pointer
    days = np.zeros((12, 7, 24))
    days[:, :5, :] = office_day()
    return to_year_component(days, name="dhw", category=category)


def write_schedule(year: YearComponent, path: str) -> YearSchedule:
    del path
    return constant_year_schedule(year.Name, 0.0)


def settings(**fields: object) -> DomesticHotWaterSettings:
    values: dict[str, object] = {
        "Name": "B_Off_0 hot water",
        "FlowRatePerFloorArea": 0.00021,
        "IsOn": True,
        "WaterSchedule": constant_year_schedule("dhw", 0.5),
        "WaterSupplyTemperature": 55.0,
        "WaterTemperatureInlet": 16.0,
        "CoefficientOfPerformance": 0.9,
        "FuelType": DomesticHotWaterFuelType.Oil,
        "Category": "Office Spaces",
    }
    values.update(fields)
    return DomesticHotWaterSettings.model_validate(values)


def loads(**fields: object) -> ZoneLoads:
    values: dict[str, object] = {"Name": "L", "PeopleDensity": 0.055, "IsPeopleOn": True}
    values.update(fields)
    return ZoneLoads.model_validate(values)


def occupancy(density: float = 0.055, *, on: bool = True) -> OccupancyComponent:
    return OccupancyComponent(Name="o", PeopleDensity=density, Schedule=sbem_schedule("occ"), IsOn=on)


def dhw(*, cop: float = 0.9, distribution: float = 1.0, fuel: str = "FuelOil", on: bool = True) -> DHWComponent:
    return DHWComponent.model_validate({
        "Name": "H",
        "SystemCOP": cop,
        "DistributionCOP": distribution,
        "WaterSupplyTemperature": 55.0,
        "WaterTemperatureInlet": 16.0,
        "IsOn": on,
        "FuelType": fuel,
    })


def water_use(flow: float, value: float = 0.25) -> WaterUseComponent:
    return WaterUseComponent(Name="H", FlowRatePerPerson=flow, Schedule=sbem_schedule("w", value, "WaterUse"))


def test_rules_are_registered_in_this_module() -> None:
    for rule_id in ("dhw.per_person", "dhw.schedule", "dhw.settings", "dhw.fuel"):
        registered = get_rule(rule_id)
        assert registered.to_sbem is not None
        assert registered.to_umi is not None
        assert registered.to_sbem.__module__ == module.__name__


# --- dhw.per_person ------------------------------------------------------------------------------


def test_flow_per_person_formula() -> None:
    # q_p = q_a * Σ s(h) / (365 * rho_p)
    assert flow_per_person(0.00021, 1305.0, 0.055) == pytest.approx(0.00021 * 1305.0 / (365 * 0.055), rel=1e-15)
    assert flow_per_area(0.01, 1305.0, 0.055) == pytest.approx(0.01 * 365 * 0.055 / 1305.0, rel=1e-15)


@given(
    st.floats(min_value=1e-7, max_value=0.01),
    st.floats(min_value=1.0, max_value=8760.0),
    st.floats(min_value=0.001, max_value=2.0),
)
def test_per_person_conserves_annual_volume_per_area(flow: float, schedule_sum: float, density: float) -> None:
    per_person = flow_per_person(flow, schedule_sum, density)
    # Annual volume per m²: UMI q_a * Σ s(h); SBEM q_p * rho_p * 365.
    assert per_person * density * 365 == pytest.approx(flow * schedule_sum, rel=1e-12)
    assert flow_per_area(per_person, schedule_sum, density) == pytest.approx(flow, rel=1e-12)


def test_reading_uses_the_schedule_sum_over_the_reference_year() -> None:
    parts = dhw_to_sbem(settings(), loads(), schedule=read_schedule, context=reading(POINTER))
    schedule_sum = float(annual_values(parts.water_use.Schedule).sum())
    assert schedule_sum == pytest.approx(5.0 * 261)  # 2018 has 261 weekdays
    assert parts.water_use.FlowRatePerPerson == pytest.approx(0.00021 * schedule_sum / (365 * 0.055), rel=1e-15)
    assert parts.water_use.Schedule.Type == "WaterUse"


def test_writing_inverts_reading() -> None:
    parts = dhw_to_sbem(settings(), loads(), schedule=read_schedule, context=reading(POINTER))
    context = writing()
    back = dhw_to_umi(parts.dhw, parts.water_use, occupancy(), schedule=write_schedule, context=context)
    assert back.flow_rate_per_floor_area == pytest.approx(0.00021, rel=1e-12)
    assert context.losses == []


@pytest.mark.parametrize("fields", [{"PeopleDensity": 0.0}, {"IsPeopleOn": False}])
def test_hot_water_without_people_is_a_range_problem_on_reading(fields: dict[str, object]) -> None:
    [problem] = range_problems(settings(), loads(**fields), pointer=POINTER, template="T")
    assert (problem.pointer, problem.rule) == (f"{POINTER}/FlowRatePerFloorArea", "dhw.per_person")
    assert range_problems(settings(IsOn=False), loads(**fields), pointer=POINTER, template="T") == []
    assert range_problems(settings(), loads(), pointer=POINTER, template="T") == []


@pytest.mark.parametrize(("density", "on"), [(0.0, True), (0.055, False)])
def test_hot_water_without_people_is_a_loss_on_writing(density: float, on: bool) -> None:
    context = writing()
    dhw_to_umi(dhw(), water_use(0.01), occupancy(density, on=on), schedule=write_schedule, context=context)
    [loss] = context.losses
    assert (loss.kind, loss.location, loss.value, loss.rule) == (
        LossKind.LOST,
        "perimeter.Operations.SpaceUse.WaterUse.FlowRatePerPerson",
        0.01,
        "dhw.per_person",
    )


def test_writing_a_flow_with_a_zero_schedule_is_lost() -> None:
    context = writing()
    written = dhw_to_umi(dhw(), water_use(0.01, 0.0), occupancy(), schedule=write_schedule, context=context)
    assert written.flow_rate_per_floor_area == 0.0
    [loss] = context.losses
    assert loss.rule == "dhw.per_person"


# --- COP, fuel, temperatures ---------------------------------------------------------------------


def test_cop_as_in_cop_system() -> None:
    parts = dhw_to_sbem(settings(), loads(), schedule=read_schedule, context=reading(POINTER))
    assert (parts.dhw.SystemCOP, parts.dhw.DistributionCOP) == (0.9, 1.0)
    context = writing()
    written = dhw_to_umi(
        dhw(cop=1.0, distribution=0.85), water_use(0.0), occupancy(), schedule=write_schedule, context=context
    )
    assert written.coefficient_of_performance == pytest.approx(0.85)
    [loss] = context.losses
    assert (loss.location, loss.rule) == ("perimeter.Operations.DHW.DistributionCOP", "cop.system")


@pytest.mark.parametrize(
    ("umi", "sbem"),
    [
        (DomesticHotWaterFuelType.Electricity, "Electricity"),
        (DomesticHotWaterFuelType.NaturalGas, "NaturalGas"),
        (DomesticHotWaterFuelType.Oil, "FuelOil"),
    ],
)
def test_fuels_map_both_ways(umi: DomesticHotWaterFuelType, sbem: SbemDhwFuel) -> None:
    assert fuel_to_sbem(umi, context=reading(POINTER)) == sbem
    context = writing("perimeter.Operations.DHW")
    assert fuel_to_umi(sbem, context=context) is umi
    assert context.losses == []


@pytest.mark.parametrize("sbem", ["Propane", "Steam"])
def test_propane_and_steam_are_written_as_natural_gas_with_a_loss(sbem: SbemDhwFuel) -> None:
    context = writing("perimeter.Operations.DHW")
    assert fuel_to_umi(sbem, context=context) is DomesticHotWaterFuelType.NaturalGas
    [loss] = context.losses
    assert (loss.location, loss.value, loss.replacement, loss.rule) == (
        "perimeter.Operations.DHW.FuelType",
        sbem,
        int(DomesticHotWaterFuelType.NaturalGas),
        "dhw.fuel",
    )


def test_unset_fuel_is_a_range_problem() -> None:
    [problem] = range_problems(
        settings(FuelType=DomesticHotWaterFuelType.Unset), loads(), pointer=POINTER, template="T"
    )
    assert (problem.pointer, problem.rule) == (f"{POINTER}/FuelType", "dhw.fuel")
    with pytest.raises(ValueError, match="validation"):
        fuel_to_sbem(DomesticHotWaterFuelType.Unset, context=reading(POINTER))
    assert set(DHW_FUELS) == set(DomesticHotWaterFuelType) - {DomesticHotWaterFuelType.Unset}


def test_temperatures_and_switch_map_exactly() -> None:
    parts = dhw_to_sbem(
        settings(WaterSupplyTemperature=60.0, WaterTemperatureInlet=12.5, IsOn=False),
        loads(),
        schedule=read_schedule,
        context=reading(POINTER),
    )
    assert (parts.dhw.WaterSupplyTemperature, parts.dhw.WaterTemperatureInlet, parts.dhw.IsOn) == (60.0, 12.5, False)
    written = dhw_to_umi(parts.dhw, parts.water_use, occupancy(), schedule=write_schedule, context=writing())
    assert (written.water_supply_temperature, written.water_temperature_inlet, written.is_on) == (60.0, 12.5, False)


def test_supply_not_above_inlet_is_a_range_problem() -> None:
    problems = range_problems(settings(WaterSupplyTemperature=10.0), loads(), pointer=POINTER, template="T")
    assert [(problem.pointer, problem.rule) for problem in problems] == [
        (f"{POINTER}/WaterSupplyTemperature", "dhw.settings")
    ]


def test_names_and_metadata() -> None:
    parts = dhw_to_sbem(settings(), loads(), schedule=read_schedule, context=reading(POINTER))
    assert parts.dhw.Name == parts.water_use.Name == "B_Off_0 hot water"
    assert parts.dhw.Category == "Office Spaces"
    written = dhw_to_umi(parts.dhw, parts.water_use, occupancy(), schedule=write_schedule, context=writing())
    assert (written.name, written.category) == ("B_Off_0 hot water", "Office Spaces")
    assert written.water_schedule is not None
    assert written.water_schedule.name == "dhw"


def test_writing_a_flow_per_person_without_people_is_lost_even_with_hot_water_off() -> None:
    context = writing()
    written = dhw_to_umi(dhw(on=False), water_use(0.01), occupancy(0.0), schedule=write_schedule, context=context)
    assert written.flow_rate_per_floor_area == 0.0
    [loss] = context.losses
    assert (loss.location, loss.value, loss.replacement) == (
        "perimeter.Operations.SpaceUse.WaterUse.FlowRatePerPerson",
        0.01,
        0.0,
    )


def test_writing_hot_water_off_with_people_off_loses_nothing() -> None:
    context = writing()
    dhw_to_umi(dhw(on=False), water_use(0.01), occupancy(on=False), schedule=write_schedule, context=context)
    assert context.losses == []
