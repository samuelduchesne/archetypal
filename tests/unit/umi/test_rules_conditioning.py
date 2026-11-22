"""The thermostat, system, fuel and mechanical-ventilation rules (spec 003 T019, research R9, R10)."""

from __future__ import annotations

import numpy as np
import pytest
from epinterface.sbem.components.space_use import ThermostatComponent
from epinterface.sbem.components.systems import (
    ConditioningSystemsComponent,
    ThermalSystemComponent,
    VentilationComponent,
    ZoneHVACComponent,
)
from epinterface.sbem.components.systems import FuelType as SbemFuelType
from hypothesis import given
from hypothesis import strategies as st

from archetypal.reduction.schedules import to_year_component
from archetypal.umi._format import EconomizerType, FuelType, HeatRecoveryType, ZoneConditioning, ZoneVentilation
from archetypal.umi.correspondence import get_rule
from archetypal.umi.report import LossKind, NoteKind
from archetypal.umi.rules import conditioning as module
from archetypal.umi.rules.conditioning import (
    ALWAYS_ON,
    FRESH_AIR_CAP,
    FUEL_TABLE,
    combined_cop,
    conditioning_to_sbem,
    conditioning_to_umi,
    fuel_to_sbem,
    fuel_to_umi,
    range_problems,
    system_cop,
)

from .test_rules_loads import read_schedule, reading, sbem_schedule, umi_schedule, writing

POINTER = "/ZoneConditionings/0"


def conditioning(**fields: object) -> ZoneConditioning:
    values: dict[str, object] = {
        "Name": "C",
        "HeatingSetpoint": 20.0,
        "CoolingSetpoint": 24.0,
        "IsHeatingOn": True,
        "IsCoolingOn": True,
        "HeatingCoeffOfPerf": 0.9,
        "CoolingCoeffOfPerf": 3.0,
        "HeatingFuelType": FuelType.NaturalGas,
        "CoolingFuelType": FuelType.Electricity,
        "HeatingSchedule": umi_schedule("on"),
        "CoolingSchedule": umi_schedule("on"),
        "MechVentSchedule": umi_schedule("on"),
        "IsMechVentOn": True,
        "MinFreshAirPerArea": 0.0003,
        "MinFreshAirPerPerson": 0.0025,
    }
    values.update(fields)
    return ZoneConditioning.model_validate(values)


def settings(natural: bool = False) -> ZoneVentilation:
    return ZoneVentilation.model_validate({
        "Name": "V",
        "IsNatVentOn": natural,
        "NatVentSchedule": umi_schedule("nat", 0.0),
        "ScheduledVentilationSchedule": umi_schedule("nat", 0.0),
    })


def read(original: ZoneConditioning, natural: bool = False):
    context = reading(POINTER)
    parts = conditioning_to_sbem(
        original,
        settings(natural),
        schedule=read_schedule,
        context=context,
        ventilation_context=reading("/VentilationSettings/0"),
    )
    return parts, context


def system(
    slot: str, *, cop: float = 3.0, distribution: float = 1.0, fuel: str = "Electricity"
) -> ThermalSystemComponent:
    return ThermalSystemComponent.model_validate({
        "Name": f"C {slot.lower()}",
        "ConditioningType": slot,
        "Fuel": fuel,
        "SystemCOP": cop,
        "DistributionCOP": distribution,
    })


def hvac(
    *,
    heating: ThermalSystemComponent | None = None,
    cooling: ThermalSystemComponent | None = None,
    provider: str = "Mechanical",
    dcv: str = "NoDCV",
    hrv: str = "Sensible",
    economizer: str = "DifferentialDryBulb",
) -> ZoneHVACComponent:
    return ZoneHVACComponent(
        Name="C",
        Category="Office Spaces",
        ConditioningSystems=ConditioningSystemsComponent(Name="C", Heating=heating, Cooling=cooling),
        Ventilation=VentilationComponent.model_validate({
            "Name": "C",
            "FreshAirPerFloorArea": 0.0003,
            "FreshAirPerPerson": 0.0025,
            "Schedule": sbem_schedule("nat", 0.0, "Window"),
            "Provider": provider,
            "HRV": hrv,
            "Economizer": economizer,
            "DCV": dcv,
        }),
    )


def thermostat(heating: object = 20.0, cooling: object = 24.0) -> ThermostatComponent:
    def year(name: str, value: object) -> object:
        days = np.zeros((12, 7, 24)) + np.asarray(value, dtype=np.float64)
        return to_year_component(days, name=name, category="Setpoint", limits="Temperature")

    return ThermostatComponent.model_validate({
        "Name": "C",
        "IsOn": True,
        "HeatingSetpoint": 20.0,
        "HeatingSchedule": year("C heating setpoint", heating),
        "CoolingSetpoint": 24.0,
        "CoolingSchedule": year("C cooling setpoint", cooling),
    })


def test_rules_are_registered_in_this_module() -> None:
    for rule_id in (
        "thermostat.constant",
        "conditioning.switches",
        "cop.system",
        "fuel.system",
        "conditioning.fresh_air",
        "conditioning.economizer",
        "conditioning.heat_recovery",
        "conditioning.heat_recovery_efficiency",
        "conditioning.availability",
        "conditioning.mech_vent_schedule",
        "conditioning.limits",
    ):
        registered = get_rule(rule_id)
        assert registered.to_sbem is not None
        assert registered.to_umi is not None
        assert registered.to_sbem.__module__ == module.__name__


# --- thermostat.constant -------------------------------------------------------------------------


def test_reading_gives_constant_setpoint_schedules() -> None:
    parts, _ = read(conditioning(HeatingSetpoint=21.0, CoolingSetpoint=25.5))
    heating = parts.thermostat.HeatingSchedule
    cooling = parts.thermostat.CoolingSchedule
    assert heating.Type == cooling.Type == "Setpoint"
    assert {value for week in heating.Weeks for day in week.Days for value in day.Values} == {21.0}
    assert {value for week in cooling.Weeks for day in week.Days for value in day.Values} == {25.5}
    assert (parts.thermostat.HeatingSetpoint, parts.thermostat.CoolingSetpoint) == (21.0, 25.5)
    assert parts.thermostat.Name == "C"


def test_writing_takes_the_heating_maximum_and_cooling_minimum() -> None:
    context = writing()
    written = conditioning_to_umi(hvac(heating=system("Heating")), thermostat(), context=context)
    assert (written.heating_setpoint, written.cooling_setpoint) == (20.0, 24.0)
    assert [loss for loss in context.losses if loss.rule == "thermostat.constant"] == []


def test_setback_hours_are_lost_with_their_count_and_mean_difference() -> None:
    hours = np.full(24, 20.0)
    hours[:6] = 16.0  # 6 setback hours a day, 4 °C below
    cooling = np.full(24, 24.0)
    cooling[:6] = 29.0
    context = writing()
    written = conditioning_to_umi(hvac(), thermostat(hours, cooling), context=context)
    assert (written.heating_setpoint, written.cooling_setpoint) == (20.0, 24.0)
    by_location = {loss.location: loss for loss in context.losses if loss.rule == "thermostat.constant"}
    heating = by_location["perimeter.Operations.SpaceUse.Thermostat.HeatingSchedule"]
    assert heating.kind is LossKind.LOST
    assert heating.value == {"hours": 6 * 365, "mean_difference": 4.0}
    assert heating.replacement == 20.0
    cooling_loss = by_location["perimeter.Operations.SpaceUse.Thermostat.CoolingSchedule"]
    assert cooling_loss.value == {"hours": 6 * 365, "mean_difference": 5.0}


# --- conditioning.switches -----------------------------------------------------------------------


def test_heating_off_gives_no_heating_system_and_cooling_likewise() -> None:
    parts, _ = read(conditioning(IsHeatingOn=False))
    assert parts.systems.Heating is None
    assert parts.systems.Cooling is not None
    parts, _ = read(conditioning(IsCoolingOn=False))
    assert parts.systems.Cooling is None
    assert parts.systems.Heating is not None


def test_systems_are_named_after_the_conditioning() -> None:
    parts, _ = read(conditioning(Name="B_Off_0 conditioning"))
    assert parts.systems.Name == "B_Off_0 conditioning"
    assert parts.systems.Heating is not None
    assert parts.systems.Heating.Name == "B_Off_0 conditioning heating"
    assert parts.systems.Cooling is not None
    assert parts.systems.Cooling.Name == "B_Off_0 conditioning cooling"
    assert parts.ventilation.Name == "B_Off_0 conditioning"


def test_an_off_system_loses_values_other_than_basilisk_defaults() -> None:
    _, context = read(conditioning(IsHeatingOn=False, HeatingCoeffOfPerf=0.9))
    [loss] = context.losses
    assert (loss.location, loss.value, loss.rule) == (
        f"{POINTER}/HeatingCoeffOfPerf",
        0.9,
        "conditioning.switches",
    )


def test_writing_no_system_gives_switch_off_and_defaults() -> None:
    context = writing()
    written = conditioning_to_umi(hvac(cooling=system("Cooling")), thermostat(), context=context)
    assert (written.is_heating_on, written.is_cooling_on) == (False, True)
    assert written.heating_coeff_of_perf == 0.0
    assert written.heating_fuel_type is FuelType.NaturalGas
    assert any(note.rule == "conditioning.switches" for note in context.notes)


# --- cop.system ----------------------------------------------------------------------------------


def test_cop_maps_to_system_cop_with_unit_distribution() -> None:
    assert system_cop(0.9) == (0.9, 1.0)
    parts, _ = read(conditioning())
    assert parts.systems.Heating is not None
    assert (parts.systems.Heating.SystemCOP, parts.systems.Heating.DistributionCOP) == (0.9, 1.0)


@given(st.floats(min_value=0.01, max_value=10.0), st.floats(min_value=0.01, max_value=2.0))
def test_writing_cop_is_the_product(system_value: float, distribution: float) -> None:
    assert combined_cop(system_value, distribution) == system_value * distribution
    assert combined_cop(*system_cop(system_value)) == system_value


def test_split_is_lost_when_distribution_cop_is_not_one() -> None:
    context = writing()
    written = conditioning_to_umi(
        hvac(heating=system("Heating", cop=4.0, distribution=0.8)), thermostat(), context=context
    )
    assert written.heating_coeff_of_perf == pytest.approx(3.2)
    [loss] = [loss for loss in context.losses if loss.rule == "cop.system"]
    assert loss.location == "perimeter.Operations.HVAC.ConditioningSystems.Heating.DistributionCOP"
    assert loss.value == {"SystemCOP": 4.0, "DistributionCOP": 0.8}
    context = writing()
    conditioning_to_umi(hvac(heating=system("Heating")), thermostat(), context=context)
    assert [loss for loss in context.losses if loss.rule == "cop.system"] == []


# --- fuel.system ---------------------------------------------------------------------------------

READ_CASES = [
    (FuelType.Electricity, "Electricity", False),
    (FuelType.NaturalGas, "NaturalGas", False),
    (FuelType.PropaneGas, "Propane", False),
    (FuelType.FuelOil1, "FuelOil", True),
    (FuelType.FuelOil2, "FuelOil", True),
    (FuelType.Diesel, "Diesel", False),
    (FuelType.Gasoline, "Gasoline", False),
    (FuelType.Coal, "Coal", False),
    (FuelType.OtherFuel1, "CustomFuel", True),
    (FuelType.OtherFuel2, "CustomFuel", True),
    (FuelType.Steam, "Steam", False),
    (FuelType.DistrictCooling, "ChilledWater", False),
    (FuelType.DistrictHeating, "Steam", True),
]

WRITE_CASES = [
    ("Electricity", FuelType.Electricity, False),
    ("NaturalGas", FuelType.NaturalGas, False),
    ("Propane", FuelType.PropaneGas, False),
    ("FuelOil", FuelType.FuelOil1, False),
    ("Diesel", FuelType.Diesel, False),
    ("Gasoline", FuelType.Gasoline, False),
    ("Coal", FuelType.Coal, False),
    ("CustomFuel", FuelType.OtherFuel1, False),
    ("Steam", FuelType.Steam, False),
    ("ChilledWater", FuelType.DistrictCooling, False),
    ("WoodPellets", FuelType.OtherFuel1, True),
]


@pytest.mark.parametrize(("umi", "sbem", "lossy"), READ_CASES, ids=str)
def test_fuel_table_on_reading(umi: FuelType, sbem: str, lossy: bool) -> None:
    context = reading(POINTER)
    assert fuel_to_sbem(umi, key="HeatingFuelType", context=context) == sbem
    if lossy:
        [loss] = context.losses
        assert (loss.kind, loss.location, loss.value, loss.replacement, loss.rule) == (
            LossKind.LOST,
            f"{POINTER}/HeatingFuelType",
            int(umi),
            sbem,
            "fuel.system",
        )
    else:
        assert context.losses == []


@pytest.mark.parametrize(("sbem", "umi", "lossy"), WRITE_CASES, ids=str)
def test_fuel_table_on_writing(sbem: SbemFuelType, umi: FuelType, lossy: bool) -> None:
    context = writing("perimeter.Operations.HVAC.ConditioningSystems.Heating")
    assert fuel_to_umi(sbem, context=context) is umi
    if lossy:
        [loss] = context.losses
        assert (loss.location, loss.value, loss.replacement) == (
            "perimeter.Operations.HVAC.ConditioningSystems.Heating.Fuel",
            sbem,
            int(umi),
        )
    else:
        assert context.losses == []


def test_fuel_table_covers_both_enums() -> None:
    assert {row.umi for row in FUEL_TABLE if row.reads} == set(FuelType) - {FuelType.None_}
    assert {row.sbem for row in FUEL_TABLE if row.writes} == set(SbemFuelType.__args__)  # type: ignore[attr-defined]
    assert {case[0] for case in READ_CASES} == {row.umi for row in FUEL_TABLE if row.reads}


def test_no_fuel_for_a_system_that_is_on_is_a_range_problem() -> None:
    problems = range_problems(conditioning(HeatingFuelType=FuelType.None_), pointer=POINTER, template="T")
    assert [(problem.pointer, problem.rule) for problem in problems] == [(f"{POINTER}/HeatingFuelType", "fuel.system")]
    assert (
        range_problems(conditioning(HeatingFuelType=FuelType.None_, IsHeatingOn=False), pointer=POINTER, template="T")
        == []
    )
    with pytest.raises(ValueError, match="validation"):
        fuel_to_sbem(FuelType.None_, key="HeatingFuelType", context=reading(POINTER))


def test_a_cop_of_zero_for_a_system_that_is_on_is_a_range_problem() -> None:
    problems = range_problems(conditioning(CoolingCoeffOfPerf=0.0), pointer=POINTER, template="T")
    assert [(problem.pointer, problem.rule) for problem in problems] == [
        (f"{POINTER}/CoolingCoeffOfPerf", "cop.system")
    ]


# --- fresh air, economizer, heat recovery --------------------------------------------------------


def test_fresh_air_maps_exactly_both_ways() -> None:
    parts, _ = read(conditioning())
    assert (parts.ventilation.FreshAirPerFloorArea, parts.ventilation.FreshAirPerPerson) == (0.0003, 0.0025)
    written = conditioning_to_umi(hvac(), thermostat(), context=writing())
    assert (written.min_fresh_air_per_area, written.min_fresh_air_per_person) == (0.0003, 0.0025)


def test_fresh_air_above_the_cap_is_a_range_problem() -> None:
    problems = range_problems(conditioning(MinFreshAirPerPerson=FRESH_AIR_CAP * 2), pointer=POINTER, template="T")
    assert [(problem.pointer, problem.rule) for problem in problems] == [
        (f"{POINTER}/MinFreshAirPerPerson", "conditioning.fresh_air")
    ]
    assert range_problems(conditioning(MinFreshAirPerArea=FRESH_AIR_CAP), pointer=POINTER, template="T") == []


@pytest.mark.parametrize("economizer", list(EconomizerType))
@pytest.mark.parametrize("heat_recovery", list(HeatRecoveryType))
def test_economizer_and_heat_recovery_map_by_name(economizer: EconomizerType, heat_recovery: HeatRecoveryType) -> None:
    parts, context = read(conditioning(EconomizerType=economizer, HeatRecoveryType=heat_recovery))
    assert parts.ventilation.Economizer == economizer.name
    assert ("NoHRV" if heat_recovery is HeatRecoveryType.None_ else heat_recovery.name) == parts.ventilation.HRV
    assert context.losses == []
    use = hvac(hrv=parts.ventilation.HRV)
    use = use.model_copy(update={"Ventilation": parts.ventilation})
    written = conditioning_to_umi(use, thermostat(), context=writing())
    assert (written.economizer_type, written.heat_recovery_type) == (economizer, heat_recovery)


def test_heat_recovery_without_mechanical_ventilation_is_lost() -> None:
    parts, context = read(conditioning(IsMechVentOn=False, HeatRecoveryType=HeatRecoveryType.Sensible), natural=True)
    assert (parts.ventilation.Provider, parts.ventilation.HRV) == ("Natural", "NoHRV")
    [loss] = context.losses
    assert (loss.location, loss.rule) == (f"{POINTER}/HeatRecoveryType", "conditioning.heat_recovery")


def test_mechanical_switch_goes_to_the_provider() -> None:
    parts, _ = read(conditioning(IsMechVentOn=True), natural=True)
    assert parts.ventilation.Provider == "Both"
    written = conditioning_to_umi(
        hvac(provider="Natural", hrv="NoHRV", economizer="NoEconomizer"), thermostat(), context=writing()
    )
    assert written.is_mech_vent_on is False


def test_a_dcv_other_than_no_dcv_is_lost_on_writing() -> None:
    context = writing()
    conditioning_to_umi(hvac(dcv="OccupancySchedule"), thermostat(), context=context)
    [loss] = [loss for loss in context.losses if loss.rule == "conditioning.fresh_air"]
    assert (loss.location, loss.value, loss.replacement) == (
        "perimeter.Operations.HVAC.Ventilation.DCV",
        "OccupancySchedule",
        "NoDCV",
    )


def test_reading_uses_the_natural_ventilation_schedule() -> None:
    parts, _ = read(conditioning())
    assert (parts.ventilation.Schedule.Name, parts.ventilation.DCV) == ("nat", "NoDCV")


# --- upstream fields -----------------------------------------------------------------------------


def test_heat_recovery_effectiveness_is_lost_with_up2() -> None:
    _, context = read(conditioning(HeatRecoveryEfficiencySensible=0.8))
    [loss] = context.losses
    assert (loss.location, loss.value, loss.upstream) == (f"{POINTER}/HeatRecoveryEfficiencySensible", 0.8, "UP-2")


def test_availability_schedules_are_lost_unless_every_value_is_one() -> None:
    _, context = read(conditioning())
    assert context.losses == []
    _, context = read(
        conditioning(HeatingSchedule=umi_schedule("season", 0.0), MechVentSchedule=umi_schedule("occ", 0.5))
    )
    assert {(loss.location, loss.value, loss.upstream, loss.rule) for loss in context.losses} == {
        (f"{POINTER}/HeatingSchedule", "season", "UP-9", "conditioning.availability"),
        (f"{POINTER}/MechVentSchedule", "occ", "UP-9", "conditioning.mech_vent_schedule"),
    }


def test_limits_other_than_defaults_are_lost_with_up9() -> None:
    _, context = read(conditioning(MaxHeatingCapacity=50.0))
    [loss] = context.losses
    assert (loss.location, loss.value, loss.upstream, loss.rule) == (
        f"{POINTER}/MaxHeatingCapacity",
        50.0,
        "UP-9",
        "conditioning.limits",
    )


def test_writing_gives_always_on_schedules_and_defaults() -> None:
    context = writing()
    written = conditioning_to_umi(hvac(heating=system("Heating")), thermostat(), context=context)
    for year in (written.heating_schedule, written.cooling_schedule, written.mech_vent_schedule):
        assert year is not None
        assert year.name == ALWAYS_ON
    assert (written.max_heating_capacity, written.heat_recovery_efficiency_sensible) == (100.0, 0.7)
    defaulted = {note.rule for note in context.notes if note.kind is NoteKind.DEFAULTED}
    assert {"conditioning.limits", "conditioning.heat_recovery_efficiency"} <= defaulted
    assert written.name == "C"
    assert written.category == "Office Spaces"


def test_conditioning_round_trip() -> None:
    original = conditioning(
        EconomizerType=EconomizerType.DifferentialEnthalpy, HeatRecoveryType=HeatRecoveryType.Enthalpy
    )
    parts, _ = read(original)
    use = hvac().model_copy(update={"ConditioningSystems": parts.systems, "Ventilation": parts.ventilation})
    context = writing()
    back = conditioning_to_umi(use, parts.thermostat, context=context)
    assert context.losses == []
    for field in (
        "heating_setpoint",
        "cooling_setpoint",
        "is_heating_on",
        "is_cooling_on",
        "heating_coeff_of_perf",
        "cooling_coeff_of_perf",
        "heating_fuel_type",
        "cooling_fuel_type",
        "is_mech_vent_on",
        "min_fresh_air_per_area",
        "min_fresh_air_per_person",
        "economizer_type",
        "heat_recovery_type",
        "max_heating_capacity",
    ):
        assert getattr(back, field) == getattr(original, field), field
