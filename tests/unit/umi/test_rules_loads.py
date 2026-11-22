"""The load rules and internal mass (spec 003 T018, research R10)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest
from epinterface.sbem.components.space_use import (
    EquipmentComponent,
    LightingComponent,
    OccupancyComponent,
    ThermostatComponent,
    WaterUseComponent,
    ZoneSpaceUseComponent,
)

from archetypal.reduction.schedules import to_year_component
from archetypal.umi._format import DimmingType, ZoneDefinition, ZoneLoads
from archetypal.umi.correspondence import get_rule
from archetypal.umi.report import LossKind, NoteKind
from archetypal.umi.rules import loads
from archetypal.umi.rules._common import (
    REFERENCE_CALENDAR,
    RuleContext,
    all_values_equal,
    annual_values,
    constant_year_schedule,
)
from archetypal.umi.rules.loads import (
    METABOLIC_RATE,
    internal_mass_to_sbem,
    internal_mass_to_umi,
    loads_to_sbem,
    loads_to_umi,
    range_problems,
)

if TYPE_CHECKING:
    from epinterface.sbem.components.schedules import YearComponent

    from archetypal.umi._format import YearSchedule
    from archetypal.umi.report import Loss, Note

# --- helpers shared by the rule tests --------------------------------------------------------------


def umi_schedule(name: str, value: float = 1.0) -> YearSchedule:
    return constant_year_schedule(name, value)


def sbem_schedule(name: str, value: float = 1.0, category: str = "Occupancy") -> YearComponent:
    limits = "Temperature" if category == "Setpoint" else "Fraction"
    return to_year_component(np.full((12, 7, 24), value), name=name, category=category, limits=limits)  # type: ignore[arg-type]


def read_schedule(year: YearSchedule, category: str, pointer: str) -> YearComponent:
    """A stand-in for the schedule rules: a constant SBEM year at the first hour's value."""
    del pointer
    first = year.parts[0].schedule
    assert first is not None
    day = first.days[0]
    assert day is not None
    assert year.name is not None
    return sbem_schedule(year.name, day.values[0], category)


def write_schedule(year: YearComponent, path: str) -> YearSchedule:
    del path
    return constant_year_schedule(year.Name, year.January.Monday.Values[0])


def reading(pointer: str = "/ZoneLoads/0") -> RuleContext:
    return RuleContext("T", pointer, "umi_to_sbem")


def writing(group: str = "perimeter") -> RuleContext:
    return RuleContext("A", group, "sbem_to_umi")


def zone_loads(**fields: object) -> ZoneLoads:
    values: dict[str, object] = {
        "Name": "L",
        "PeopleDensity": 0.055,
        "OccupancySchedule": umi_schedule("occ", 0.5),
        "IsPeopleOn": True,
        "LightingPowerDensity": 12.0,
        "LightsAvailabilitySchedule": umi_schedule("lgt", 0.8),
        "IsLightingOn": False,
        "DimmingType": DimmingType.Stepped,
        "EquipmentPowerDensity": 8.0,
        "EquipmentAvailabilitySchedule": umi_schedule("plg", 0.3),
        "IsEquipmentOn": True,
        "IlluminanceTarget": 400.0,
        "Category": "Office Spaces",
        "DataSource": "MIT_SDL",
    }
    values.update(fields)
    return ZoneLoads.model_validate(values)


def space_use(*, metabolic: float = METABOLIC_RATE, occupancy_name: str = "L occupancy") -> ZoneSpaceUseComponent:
    return ZoneSpaceUseComponent(
        Name="L",
        Category="Office Spaces",
        Comment="c",
        Occupancy=OccupancyComponent(
            Name=occupancy_name,
            PeopleDensity=0.055,
            Schedule=sbem_schedule("occ", 0.5),
            IsOn=True,
            MetabolicRate=metabolic,
        ),
        Lighting=LightingComponent(
            Name="L lighting",
            PowerDensity=12.0,
            DimmingType="Off",
            Schedule=sbem_schedule("lgt", 0.8, "Lighting"),
            IsOn=True,
        ),
        Equipment=EquipmentComponent(
            Name="L equipment",
            PowerDensity=8.0,
            Schedule=sbem_schedule("plg", 0.3, "Equipment"),
            IsOn=False,
        ),
        Thermostat=ThermostatComponent(
            Name="t",
            IsOn=True,
            HeatingSetpoint=20.0,
            HeatingSchedule=sbem_schedule("h", 20.0, "Setpoint"),
            CoolingSetpoint=24.0,
            CoolingSchedule=sbem_schedule("c", 24.0, "Setpoint"),
        ),
        WaterUse=WaterUseComponent(Name="w", FlowRatePerPerson=0.01, Schedule=sbem_schedule("w", 0.2, "WaterUse")),
    )


def losses(context: RuleContext) -> list[Loss]:
    return context.losses


def notes(context: RuleContext) -> list[Note]:
    return context.notes


# --- registry -----------------------------------------------------------------------------------


def test_rules_are_registered_in_this_module() -> None:
    for rule_id in ("loads.people", "loads.lighting", "loads.equipment", "loads.daylighting", "mass.internal"):
        registered = get_rule(rule_id)
        assert registered.to_sbem is not None
        assert registered.to_umi is not None
        assert registered.to_sbem.__module__ == loads.__name__


# --- reading ------------------------------------------------------------------------------------


def test_reading_maps_densities_switches_schedules_and_dimming_exactly() -> None:
    context = reading()
    parts = loads_to_sbem(zone_loads(), schedule=read_schedule, context=context)
    assert (parts.occupancy.PeopleDensity, parts.occupancy.IsOn) == (0.055, True)
    assert (parts.lighting.PowerDensity, parts.lighting.IsOn, parts.lighting.DimmingType) == (12.0, False, "Stepped")
    assert (parts.equipment.PowerDensity, parts.equipment.IsOn) == (8.0, True)
    assert parts.occupancy.Schedule.Name == "occ"
    assert parts.occupancy.Schedule.Type == "Occupancy"
    assert parts.lighting.Schedule.Type == "Lighting"
    assert parts.equipment.Schedule.Type == "Equipment"
    assert parts.lighting.Schedule.January.Monday.Values[0] == 0.8


def test_reading_names_sub_components_after_the_loads() -> None:
    parts = loads_to_sbem(zone_loads(Name="B_Off_0 loads"), schedule=read_schedule, context=reading())
    assert parts.occupancy.Name == "B_Off_0 loads occupancy"
    assert parts.lighting.Name == "B_Off_0 loads lighting"
    assert parts.equipment.Name == "B_Off_0 loads equipment"


@pytest.mark.parametrize("dimming", list(DimmingType))
def test_dimming_type_maps_by_name_both_ways(dimming: DimmingType) -> None:
    parts = loads_to_sbem(zone_loads(DimmingType=dimming), schedule=read_schedule, context=reading())
    assert parts.lighting.DimmingType == dimming.name
    use = space_use().model_copy(update={"Lighting": parts.lighting})
    assert loads_to_umi(use, schedule=write_schedule, context=writing()).dimming_type is dimming


def test_reading_sets_metabolic_rate_with_a_note() -> None:
    context = reading()
    parts = loads_to_sbem(zone_loads(), schedule=read_schedule, context=context)
    assert parts.occupancy.MetabolicRate == METABOLIC_RATE == 1.2
    [note] = [note for note in notes(context) if note.rule == "loads.people"]
    assert note.kind is NoteKind.ASSUMED
    assert note.value == 1.2
    assert note.location == "/ZoneLoads/0/PeopleDensity"
    assert "MetabolicRate" in note.reason


def test_illuminance_target_is_lost_with_up9() -> None:
    context = reading()
    loads_to_sbem(zone_loads(), schedule=read_schedule, context=context)
    [loss] = losses(context)
    assert loss.kind is LossKind.LOST
    assert (loss.location, loss.value, loss.rule, loss.upstream) == (
        "/ZoneLoads/0/IlluminanceTarget",
        400.0,
        "loads.daylighting",
        "UP-9",
    )
    assert loss.subject == "T"


def test_zone_definition_daylighting_fields_are_lost_with_up9() -> None:
    context = reading("/Zones/0")
    zone = ZoneDefinition.model_validate({"Name": "z", "DaylightMeshResolution": 2.0})
    get_rule("loads.daylighting").to_sbem(zone, context=context)  # type: ignore[misc]
    [loss] = losses(context)  # the workplane height is Basilisk's default, which writing gives back
    assert (loss.location, loss.value, loss.upstream) == ("/Zones/0/DaylightMeshResolution", 2.0, "UP-9")


def test_an_upstream_field_at_basilisk_default_is_not_lost() -> None:
    context = reading()
    loads_to_sbem(zone_loads(IlluminanceTarget=500.0), schedule=read_schedule, context=context)
    assert losses(context) == []


def test_negative_density_is_a_range_problem() -> None:
    problems = range_problems(zone_loads(PeopleDensity=-1.0), pointer="/ZoneLoads/0", template="T")
    assert [(problem.pointer, problem.rule) for problem in problems] == [("/ZoneLoads/0/PeopleDensity", "loads.people")]
    assert range_problems(zone_loads(), pointer="/ZoneLoads/0", template="T") == []


# --- writing ------------------------------------------------------------------------------------


def test_writing_maps_densities_switches_schedules_and_metadata() -> None:
    context = writing()
    written = loads_to_umi(space_use(), schedule=write_schedule, context=context)
    assert written.name == "L"
    assert (written.category, written.comments) == ("Office Spaces", "c")
    assert (written.people_density, written.is_people_on) == (0.055, True)
    assert (written.lighting_power_density, written.is_lighting_on, written.dimming_type) == (
        12.0,
        True,
        DimmingType.Off,
    )
    assert (written.equipment_power_density, written.is_equipment_on) == (8.0, False)
    assert written.occupancy_schedule is not None
    assert written.occupancy_schedule.name == "occ"
    assert written.lights_availability_schedule is not None
    assert written.lights_availability_schedule.name == "lgt"
    assert losses(context) == []


def test_writing_defaults_illuminance_target_with_a_note() -> None:
    context = writing()
    written = loads_to_umi(space_use(), schedule=write_schedule, context=context)
    assert written.illuminance_target == 500.0
    [note] = [note for note in notes(context) if note.rule == "loads.daylighting"]
    assert note.kind is NoteKind.DEFAULTED
    assert note.value == 500.0


def test_writing_a_non_default_metabolic_rate_is_lost() -> None:
    context = writing()
    loads_to_umi(space_use(metabolic=1.5), schedule=write_schedule, context=context)
    [loss] = losses(context)
    assert (loss.kind, loss.location, loss.value, loss.replacement, loss.rule) == (
        LossKind.LOST,
        "perimeter.Operations.SpaceUse.Occupancy.MetabolicRate",
        1.5,
        None,
        "loads.people",
    )


def test_sub_component_names_are_left_to_the_building_rules() -> None:
    """`building.umi_names` reports sub-component names; the load rules do not repeat it."""
    context = writing()
    loads_to_umi(space_use(occupancy_name="people"), schedule=write_schedule, context=context)
    assert losses(context) == []


def test_writing_reports_the_space_use_version_as_lost() -> None:
    context = writing()
    use = space_use().model_copy(update={"Version": "2"})
    loads_to_umi(use, schedule=write_schedule, context=context)
    [loss] = losses(context)
    assert (loss.location, loss.rule) == ("perimeter.Operations.SpaceUse.Version", "names.metadata")


def test_loads_round_trip() -> None:
    original = zone_loads()
    parts = loads_to_sbem(original, schedule=read_schedule, context=reading())
    use = space_use().model_copy(
        update={"Occupancy": parts.occupancy, "Lighting": parts.lighting, "Equipment": parts.equipment}
    )
    back = loads_to_umi(use, schedule=write_schedule, context=writing())
    for field in (
        "people_density",
        "is_people_on",
        "lighting_power_density",
        "is_lighting_on",
        "dimming_type",
        "equipment_power_density",
        "is_equipment_on",
    ):
        assert getattr(back, field) == getattr(original, field), field


# --- internal mass ------------------------------------------------------------------------------


def test_internal_mass_maps_exactly() -> None:
    context = reading("/Zones/0")
    assert internal_mass_to_sbem("wall", 1.05, context=context) == ("wall", 1.05)
    assert context.findings == []
    assert internal_mass_to_umi("wall", 1.05, fallback="partition", context=writing()) == ("wall", 1.05)


def test_internal_mass_ratio_zero_means_none() -> None:
    context = reading("/Zones/0")
    assert internal_mass_to_sbem("wall", 0.0, context=context) == (None, None)
    [loss] = losses(context)
    assert (loss.location, loss.value, loss.rule) == ("/Zones/0/InternalMassConstruction", "wall", "mass.internal")


def test_internal_mass_none_is_written_as_ratio_zero_with_the_fallback() -> None:
    context = writing()
    assert internal_mass_to_umi(None, None, fallback="partition", context=context) == ("partition", 0.0)
    [note] = notes(context)
    assert (note.kind, note.rule, note.value) == (NoteKind.ASSUMED, "mass.internal", "partition")
    context = writing()
    assert internal_mass_to_umi(None, 0.0, fallback="partition", context=context) == ("partition", 0.0)


def test_internal_mass_without_area_or_construction_is_refused() -> None:
    with pytest.raises(ValueError, match="both or neither"):
        internal_mass_to_umi("wall", 0.0, fallback="partition", context=writing())
    with pytest.raises(ValueError, match="both or neither"):
        internal_mass_to_umi(None, 1.0, fallback="partition", context=writing())


# --- shared helpers -----------------------------------------------------------------------------


def test_reference_calendar_is_a_non_leap_year_starting_on_monday() -> None:
    assert REFERENCE_CALENDAR.days == 365
    assert REFERENCE_CALENDAR.start_weekday == 0


def test_annual_values_and_constant_schedules() -> None:
    values = annual_values(sbem_schedule("x", 0.25))
    assert values.shape == (8760,)
    assert values.sum() == pytest.approx(0.25 * 8760)
    year = constant_year_schedule("Always on", 1.0)
    assert all_values_equal(year, 1.0)
    assert not all_values_equal(year, 0.0)
    assert year.parts[0].to_month == 12
    assert year.parts[0].to_day == 31


def test_context_locations_follow_the_direction() -> None:
    assert reading("/ZoneLoads/3").location("PeopleDensity") == "/ZoneLoads/3/PeopleDensity"
    assert writing("core").location("Operations.DHW") == "core.Operations.DHW"
    child = writing("core").child("Operations")
    assert child.location("DHW") == "core.Operations.DHW"
