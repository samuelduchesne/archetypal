"""The infiltration and natural-ventilation rules (spec 003 T020, research R10)."""

from __future__ import annotations

import pytest
from epinterface.sbem.components.envelope import InfiltrationComponent, ZoneEnvelopeComponent
from epinterface.sbem.components.systems import VentilationComponent

from archetypal.umi._format import ZoneVentilation
from archetypal.umi.correspondence import get_rule
from archetypal.umi.report import LossKind, NoteKind
from archetypal.umi.rules import ventilation as module
from archetypal.umi.rules.ventilation import (
    AIR_CHANGES,
    PROVIDERS,
    UNUSED_COEFFICIENTS,
    natural_schedule_to_sbem,
    provider_to_sbem,
    provider_to_umi,
    range_problems,
    zone_ventilation_to_sbem,
    zone_ventilation_to_umi,
)

from .test_rules_loads import read_schedule, reading, sbem_schedule, umi_schedule, write_schedule, writing

POINTER = "/VentilationSettings/0"


def settings(**fields: object) -> ZoneVentilation:
    natural = umi_schedule("nat", 0.0)
    values: dict[str, object] = {
        "Name": "V",
        "Infiltration": 0.35,
        "IsInfiltrationOn": True,
        "IsNatVentOn": True,
        "NatVentSchedule": natural,
        "ScheduledVentilationSchedule": natural,
        "Category": "Office Spaces",
    }
    values.update(fields)
    return ZoneVentilation.model_validate(values)


def infiltration(name: str = "V", **fields: object) -> InfiltrationComponent:
    values: dict[str, object] = {
        "Name": name,
        "IsOn": True,
        "AirChangesPerHour": 0.35,
        "CalculationMethod": AIR_CHANGES,
        **UNUSED_COEFFICIENTS,
    }
    values.update(fields)
    return InfiltrationComponent.model_validate(values)


def envelope(main: InfiltrationComponent, attic: InfiltrationComponent | None = None) -> ZoneEnvelopeComponent:
    return ZoneEnvelopeComponent.model_construct(
        Name="z",
        Infiltration=main,
        AtticInfiltration=attic or main,
        BasementInfiltration=main,
    )


def hvac_ventilation(provider: str = "Natural") -> VentilationComponent:
    return VentilationComponent.model_validate({
        "Name": "C",
        "FreshAirPerFloorArea": 0.0003,
        "FreshAirPerPerson": 0.0025,
        "Schedule": sbem_schedule("nat", 0.0, "Window"),
        "Provider": provider,
        "HRV": "NoHRV",
        "Economizer": "NoEconomizer",
        "DCV": "NoDCV",
    })


def test_rules_are_registered_in_this_module() -> None:
    for rule_id in (
        "infiltration.ach",
        "vent.provider",
        "vent.natural_schedule",
        "vent.natural_limits",
        "vent.scheduled",
    ):
        registered = get_rule(rule_id)
        assert registered.to_sbem is not None
        assert registered.to_umi is not None
        assert registered.to_sbem.__module__ == module.__name__


# --- infiltration ---------------------------------------------------------------------------------


def test_infiltration_is_air_changes_per_hour() -> None:
    context = reading(POINTER)
    parts = zone_ventilation_to_sbem(settings(), context=context)
    assert parts.infiltration.AirChangesPerHour == 0.35
    assert parts.infiltration.IsOn is True
    assert parts.infiltration.CalculationMethod == "AirChanges/Hour"
    assert parts.infiltration.Name == "V"
    assert parts.infiltration.Category == "Office Spaces"


def test_reading_notes_the_unused_coefficients() -> None:
    context = reading(POINTER)
    parts = zone_ventilation_to_sbem(settings(), context=context)
    assert parts.infiltration.ConstantCoefficient == 1.0
    for key in ("TemperatureCoefficient", "WindVelocityCoefficient", "WindVelocitySquaredCoefficient"):
        assert getattr(parts.infiltration, key) == 0.0
    coefficients = [note for note in context.notes if isinstance(note.value, dict)]
    [note] = coefficients
    assert note.kind is NoteKind.ASSUMED
    assert note.value == dict(UNUSED_COEFFICIENTS)
    assert note.location == f"{POINTER}/Infiltration"


def test_attic_and_basement_take_the_main_value_noted() -> None:
    context = reading(POINTER)
    parts = zone_ventilation_to_sbem(settings(), context=context)
    assert parts.attic == parts.infiltration == parts.basement
    assert any(note.value == 0.35 and "attic" in note.reason for note in context.notes)
    assert context.losses == []


def test_writing_air_changes_is_exact() -> None:
    context = writing()
    written = zone_ventilation_to_umi(
        envelope(infiltration()), hvac_ventilation(), schedule=write_schedule, context=context
    )
    assert (written.infiltration, written.is_infiltration_on) == (0.35, True)
    assert written.name == "V"
    assert context.losses == []


def test_another_method_is_lost_with_its_value() -> None:
    context = writing()
    main = infiltration(CalculationMethod="Flow/ExteriorArea", FlowPerExteriorSurfaceArea=0.0003)
    zone_ventilation_to_umi(envelope(main), hvac_ventilation(), schedule=write_schedule, context=context)
    [loss] = context.losses
    assert loss.kind is LossKind.LOST
    assert loss.location == "perimeter.Envelope.Infiltration.CalculationMethod"
    assert loss.value == {
        "CalculationMethod": "Flow/ExteriorArea",
        "AirChangesPerHour": 0.35,
        "FlowPerExteriorSurfaceArea": 0.0003,
    }
    assert loss.rule == "infiltration.ach"


def test_a_different_attic_infiltration_is_lost() -> None:
    context = writing()
    zone_ventilation_to_umi(
        envelope(infiltration(), infiltration("attic", AirChangesPerHour=1.0)),
        hvac_ventilation(),
        schedule=write_schedule,
        context=context,
    )
    [loss] = context.losses
    assert loss.location == "perimeter.Envelope.AtticInfiltration"
    assert loss.replacement == 0.35


def test_infiltration_round_trip() -> None:
    original = settings(Infiltration=0.7, IsInfiltrationOn=False)
    parts = zone_ventilation_to_sbem(original, context=reading(POINTER))
    back = zone_ventilation_to_umi(
        envelope(parts.infiltration), hvac_ventilation(), schedule=write_schedule, context=writing()
    )
    assert (back.infiltration, back.is_infiltration_on, back.name) == (0.7, False, "V")


def test_negative_infiltration_is_a_range_problem() -> None:
    [problem] = range_problems(settings(Infiltration=-0.1), pointer=POINTER, template="T")
    assert (problem.pointer, problem.rule) == (f"{POINTER}/Infiltration", "infiltration.ach")


# --- provider ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("mechanical", "natural", "provider"),
    [(False, False, "None"), (False, True, "Natural"), (True, False, "Mechanical"), (True, True, "Both")],
)
def test_provider_maps_both_switches_and_back(mechanical: bool, natural: bool, provider: str) -> None:
    assert provider_to_sbem(mechanical, natural) == provider
    assert provider_to_umi(provider) == (mechanical, natural)  # type: ignore[arg-type]
    assert PROVIDERS[mechanical, natural] == provider


def test_writing_takes_the_natural_switch_from_the_provider() -> None:
    for provider, natural in (("None", False), ("Natural", True), ("Mechanical", False), ("Both", True)):
        written = zone_ventilation_to_umi(
            envelope(infiltration()), hvac_ventilation(provider), schedule=write_schedule, context=writing()
        )
        assert written.is_nat_vent_on is natural


# --- natural-ventilation schedule and upstream fields ------------------------------------------


def test_natural_schedule_maps_to_the_ventilation_schedule() -> None:
    year = natural_schedule_to_sbem(settings(), schedule=read_schedule, context=reading(POINTER))
    assert (year.Name, year.Type) == ("nat", "Window")
    written = zone_ventilation_to_umi(
        envelope(infiltration()), hvac_ventilation(), schedule=write_schedule, context=writing()
    )
    assert written.nat_vent_schedule is not None
    assert written.nat_vent_schedule.name == "nat"
    assert written.scheduled_ventilation_schedule == written.nat_vent_schedule


def test_natural_limits_and_scheduled_ventilation_are_lost_with_up9() -> None:
    context = reading(POINTER)
    zone_ventilation_to_sbem(
        settings(NatVentMaxOutdoorAirTemp=26.0, ScheduledVentilationAch=1.0, IsWindOn=True), context=context
    )
    assert {(loss.location, loss.value, loss.upstream) for loss in context.losses} == {
        (f"{POINTER}/NatVentMaxOutdoorAirTemp", 26.0, "UP-9"),
        (f"{POINTER}/IsWindOn", True, "UP-9"),
        (f"{POINTER}/ScheduledVentilationAch", 1.0, "UP-9"),
    }


def test_a_scheduled_ventilation_schedule_other_than_the_natural_one_is_lost() -> None:
    context = reading(POINTER)
    zone_ventilation_to_sbem(settings(ScheduledVentilationSchedule=umi_schedule("other")), context=context)
    [loss] = context.losses
    assert (loss.location, loss.value, loss.replacement, loss.rule) == (
        f"{POINTER}/ScheduledVentilationSchedule",
        "other",
        "nat",
        "vent.scheduled",
    )


def test_writing_gives_basilisk_defaults_for_upstream_fields() -> None:
    context = writing()
    written = zone_ventilation_to_umi(
        envelope(infiltration()), hvac_ventilation(), schedule=write_schedule, context=context
    )
    assert written.nat_vent_max_outdoor_air_temp == 30.0
    assert written.is_scheduled_ventilation_on is False
    defaulted = {note.rule for note in context.notes if note.kind is NoteKind.DEFAULTED}
    assert defaulted == {"vent.natural_limits", "vent.scheduled"}
