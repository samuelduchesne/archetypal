"""The approximate merge of an archetype without its reduction (spec 003 T040, research R12).

`GroupLedger.approximate_from_group(group, floor_area)` rebuilds a group's ledger from its SBEM
parameters, the floor area being the group's share times 1 m². Gains and their profiles,
setpoints, outdoor air and hot water rebuild exactly from intensities; the envelope, the
efficiencies, infiltration and the window need surface areas or energies the archetype does not
hold, so they are floor-area weighted and listed as approximate. `approximate_merge` merges the
rebuilt ledgers with 002's grouping to core and perimeter.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

import numpy as np
import pytest
from epinterface.sbem.archetype import Archetype, ZoneGroup
from epinterface.sbem.components.envelope import GlazingConstructionLayeredComponent, GlazingConstructionSimpleComponent
from idfkit import new_document
from idfkit.thermal import calculate_u_value

from archetypal.errors import InputError
from archetypal.reduction.ledger import APPROXIMATE_PATHS, GroupLedger
from archetypal.reduction.schedules import RunPeriodCalendar, calendar_year, year_values
from archetypal.reduction.to_sbem import ventilation
from archetypal.umi import read_umi
from archetypal.umi.report import LossKind
from archetypal.umi.write import approximate_merge

if TYPE_CHECKING:
    from epinterface.sbem.components.zones import ZoneComponent

B2 = Path(__file__).parents[2] / "fixtures" / "umi" / "BostonTemplateLibrary_2.json"
CALENDAR = RunPeriodCalendar(calendar_year(1, 1, 0))


@pytest.fixture(scope="module")
def office() -> ZoneComponent:
    return read_umi(B2).archetypes[0].Groups[1].Zone


def replace(model: Any, path: str, value: object) -> Any:
    """Return a copy of a pydantic model with the field at a dotted path replaced."""
    head, _, rest = path.partition(".")
    if not rest:
        return model.model_copy(update={head: value})
    return model.model_copy(update={head: replace(getattr(model, head), rest, value)})


def _idf_construction(window: GlazingConstructionLayeredComponent) -> Any:
    doc = new_document()
    window.add_to_idf(cast("Any", doc))
    return doc.constructions[window.Name]


def group(zone: ZoneComponent, name: str, share: float | None, exposure: str | None) -> ZoneGroup:
    return ZoneGroup.model_validate({"Name": name, "Zone": zone, "FloorAreaShare": share, "Exposure": exposure})


# --- Rebuilding one group's ledger ----------------------------------------------------------


def test_exact_parts_rebuild_from_intensities(office: ZoneComponent) -> None:
    space_use = office.Operations.SpaceUse
    rebuilt = GroupLedger.approximate_from_group(group(office, "perimeter", 0.4, "perimeter"), 0.4)
    ledger = rebuilt.ledger
    assert ledger.members == ("perimeter",)
    assert ledger.floor_area == 0.4
    people = ledger.gains["people"]
    assert people.installed == pytest.approx(space_use.Occupancy.PeopleDensity * 0.4)
    np.testing.assert_allclose(
        people.hourly, people.installed * year_values(space_use.Occupancy.Schedule, CALENDAR), rtol=1e-12
    )
    assert ledger.gains["lights"].installed == pytest.approx(space_use.Lighting.PowerDensity * 0.4)
    assert ledger.gains["electric"].installed == pytest.approx(space_use.Equipment.PowerDensity * 0.4)
    heating = ledger.heating_setpoint
    assert heating.weight == 0.4
    np.testing.assert_allclose(
        heating.weighted / heating.weight, year_values(space_use.Thermostat.HeatingSchedule, CALENDAR)
    )
    ventilation = office.Operations.HVAC.Ventilation
    design = 0.4 * (
        ventilation.FreshAirPerFloorArea + ventilation.FreshAirPerPerson * space_use.Occupancy.PeopleDensity
    )
    assert ledger.outdoor_air.design_flow == pytest.approx(design)
    mechanical = ventilation.MechVentSchedule
    fraction = year_values(mechanical, CALENDAR) if mechanical is not None else np.ones(8760)
    np.testing.assert_allclose(ledger.outdoor_air.hourly, design * fraction)
    annual = space_use.WaterUse.FlowRatePerPerson * 365 * space_use.Occupancy.PeopleDensity * 0.4
    assert float(ledger.hot_water.volume.sum()) == pytest.approx(annual)
    dhw = office.Operations.DHW
    assert ledger.hot_water.mean_rise == pytest.approx(dhw.WaterSupplyTemperature - dhw.WaterTemperatureInlet)


def test_parts_needing_report_data_are_listed_as_approximate(office: ZoneComponent) -> None:
    rebuilt = GroupLedger.approximate_from_group(group(office, "perimeter", 0.4, "perimeter"), 0.4)
    assert set(rebuilt.approximate) == set(APPROXIMATE_PATHS)
    ledger = rebuilt.ledger
    assert ledger.envelope["exterior_wall"].area == 0.4
    assert ledger.window_by_orientation  # floor-area weighted window
    assert ledger.infiltration.design_flow > 0
    assert ledger.energy["heating"].rated_efficiency is not None


def test_floor_area_must_be_positive(office: ZoneComponent) -> None:
    with pytest.raises(ValueError, match="floor area"):
        GroupLedger.approximate_from_group(group(office, "perimeter", None, "perimeter"), 0.0)


def test_ledgers_of_groups_add(office: ZoneComponent) -> None:
    a = GroupLedger.approximate_from_group(group(office, "a", 0.3, "perimeter"), 0.3).ledger
    b = GroupLedger.approximate_from_group(group(office, "b", 0.2, "perimeter"), 0.2).ledger
    total = a + b
    assert total.members == ("a", "b")
    assert total.gains["lights"].installed == pytest.approx(office.Operations.SpaceUse.Lighting.PowerDensity * 0.5)


# --- Merging an archetype -------------------------------------------------------------------------


def three_groups(office: ZoneComponent) -> Archetype:
    bright = replace(office, "Operations.SpaceUse.Lighting.PowerDensity", 20.0)
    bright = replace(
        bright,
        "Envelope.Window",
        GlazingConstructionSimpleComponent(Name="Bright glazing", UValue=1.5, SHGF=0.4, TVis=0.6, Type="Double"),
    )
    bright = replace(bright, "Name", "Bright office")
    return Archetype(
        Name="three groups",
        Groups=[
            group(office, "perimeter office", 0.3, "perimeter"),
            group(bright, "perimeter bright", 0.2, "perimeter"),
            group(office, "core office", 0.5, "core"),
        ],
    )


def test_merge_weights_intensities_by_floor_area(office: ZoneComponent) -> None:
    merged = approximate_merge(three_groups(office))
    by_exposure = {g.Exposure: g for g in merged.archetype.Groups}
    assert set(by_exposure) == {"core", "perimeter"}
    perimeter = by_exposure["perimeter"]
    assert perimeter.FloorAreaShare == pytest.approx(0.5)
    lighting = perimeter.Zone.Operations.SpaceUse.Lighting
    density = office.Operations.SpaceUse.Lighting.PowerDensity
    assert lighting.PowerDensity == pytest.approx((0.3 * density + 0.2 * 20.0) / 0.5)
    # The schedule is the same in both groups, so the merged schedule reproduces it.
    np.testing.assert_allclose(
        year_values(lighting.Schedule, CALENDAR),
        year_values(office.Operations.SpaceUse.Lighting.Schedule, CALENDAR),
        atol=1e-12,
    )
    window = perimeter.Zone.Envelope.Window
    assert window is not None
    # The office's window is layered (UP-9): the ledger takes its U from idfkit.thermal.
    assert isinstance(office.Envelope.Window, GlazingConstructionLayeredComponent)
    office_u = calculate_u_value(_idf_construction(office.Envelope.Window))
    assert isinstance(window, GlazingConstructionSimpleComponent)
    assert window.UValue == pytest.approx((0.3 * office_u + 0.2 * 1.5) / 0.5)
    # The core group has one member: it is kept as it is.
    assert by_exposure["core"].Zone == office


def test_rebuilt_ledgers_weight_heat_recovery_effectiveness_by_outdoor_air_volume(office: ZoneComponent) -> None:
    """Summed rebuilt ledgers give the outdoor-air-volume-weighted sensible effectiveness (R9, FR-019)."""
    path = "Operations.HVAC.Ventilation"
    low = replace(office, f"{path}.HRV", "Sensible")
    low = replace(low, f"{path}.SensibleHeatRecoveryEffectiveness", 0.6)
    high = replace(low, f"{path}.SensibleHeatRecoveryEffectiveness", 0.9)
    high = replace(high, f"{path}.FreshAirPerFloorArea", 3 * office.Operations.HVAC.Ventilation.FreshAirPerFloorArea)
    high = replace(high, "Name", "High recovery office")
    groups = [group(low, "perimeter low", 0.3, "perimeter"), group(high, "perimeter high", 0.2, "perimeter")]
    volumes: list[float] = []
    for g in groups:
        outdoor_air = GroupLedger.approximate_from_group(g, cast("float", g.FloorAreaShare)).ledger.outdoor_air
        volumes.append(outdoor_air.hrv_weighted["Sensible"])
        effectiveness = g.Zone.Operations.HVAC.Ventilation.sensible_heat_recovery_effectiveness
        assert outdoor_air.effectiveness_weighted == pytest.approx(volumes[-1] * effectiveness)
    assert volumes[0] != pytest.approx(volumes[1] * 0.3 / 0.2)  # the volumes are not proportional to area
    total = sum(
        (GroupLedger.approximate_from_group(g, cast("float", g.FloorAreaShare)).ledger for g in groups), GroupLedger()
    )
    expected = (volumes[0] * 0.6 + volumes[1] * 0.9) / (volumes[0] + volumes[1])
    # The merged ledger derives the volume-weighted effectiveness with 002's `ventilation` rule.
    result = ventilation(total, CALENDAR, name="merged").value.SensibleHeatRecoveryEffectiveness
    assert result == pytest.approx(expected)
    assert result != pytest.approx(0.9)  # not the largest member's value


def test_merge_sets_outdoor_air_weighted_heat_recovery_effectiveness(office: ZoneComponent) -> None:
    """The merged zone takes the volume-weighted sensible effectiveness, not the largest member's (R9, R12)."""
    path = "Operations.HVAC.Ventilation"
    low = replace(office, f"{path}.HRV", "Sensible")
    low = replace(low, f"{path}.SensibleHeatRecoveryEffectiveness", 0.6)
    high = replace(low, f"{path}.SensibleHeatRecoveryEffectiveness", 0.9)
    high = replace(high, f"{path}.FreshAirPerFloorArea", 3 * office.Operations.HVAC.Ventilation.FreshAirPerFloorArea)
    high = replace(high, "Name", "High recovery office")
    groups = [group(low, "perimeter low", 0.3, "perimeter"), group(high, "perimeter high", 0.2, "perimeter")]
    volumes = [
        GroupLedger.approximate_from_group(g, cast("float", g.FloorAreaShare)).ledger.outdoor_air.hrv_weighted[
            "Sensible"
        ]
        for g in groups
    ]
    archetype = Archetype(Name="two recoveries", Groups=[*groups, group(office, "core office", 0.5, "core")])
    zone = next(g.Zone for g in approximate_merge(archetype).archetype.Groups if g.Exposure == "perimeter")
    effectiveness = zone.Operations.HVAC.Ventilation.SensibleHeatRecoveryEffectiveness
    assert effectiveness == pytest.approx((volumes[0] * 0.6 + volumes[1] * 0.9) / (volumes[0] + volumes[1]))
    assert effectiveness != pytest.approx(0.6)  # not the largest member's value
    assert zone.Operations.HVAC.Ventilation.HRV == "Sensible"


def test_merge_reports_merged_groups_and_approximate_parameters(office: ZoneComponent) -> None:
    merged = approximate_merge(three_groups(office))
    kinds = {(loss.kind, loss.location) for loss in merged.losses}
    merged_losses = [loss for loss in merged.losses if loss.kind is LossKind.MERGED]
    assert len(merged_losses) == 1
    assert merged_losses[0].value == ["perimeter bright", "perimeter office"]
    assert merged_losses[0].rule == "layout.merged"
    assert (LossKind.APPROXIMATE, "perimeter.Envelope.Window") in kinds
    # Groups that agree on a parameter merge it exactly: no approximate loss for it.
    assert (LossKind.APPROXIMATE, "perimeter.Envelope.Assemblies") not in kinds
    assert all(loss.subject == "three groups" for loss in merged.losses)


def test_merged_archetype_validates(office: ZoneComponent) -> None:
    merged = approximate_merge(three_groups(office))
    Archetype.model_validate(merged.archetype.model_dump())


def test_core_and_perimeter_archetype_is_unchanged(office: ZoneComponent) -> None:
    archetype = read_umi(B2).archetypes[0]
    merged = approximate_merge(archetype)
    assert merged.archetype == archetype
    assert merged.losses == ()


def test_groups_without_exposure_merge_into_one(office: ZoneComponent) -> None:
    other = replace(office, "Operations.SpaceUse.Occupancy.PeopleDensity", 0.1)
    archetype = Archetype(
        Name="no exposure",
        Groups=[group(office, "a", 0.25, None), group(other, "b", 0.75, None)],
    )
    merged = approximate_merge(archetype)
    (only,) = merged.archetype.Groups
    density = only.Zone.Operations.SpaceUse.Occupancy.PeopleDensity
    assert density == pytest.approx(0.25 * office.Operations.SpaceUse.Occupancy.PeopleDensity + 0.75 * 0.1)


def test_more_than_two_groups_with_unset_shares_is_refused(office: ZoneComponent) -> None:
    groups = [
        group(office, name, None, exposure) for name, exposure in (("a", "core"), ("b", "perimeter"), ("c", None))
    ]
    archetype = Archetype.model_construct(Name="unweighted", Groups=groups)
    with pytest.raises(InputError, match="unweighted"):
        approximate_merge(archetype)


def test_merged_infiltration_is_given_in_air_changes(office: ZoneComponent) -> None:
    """The merged ACH is the one epinterface uses: the method is AirChanges/Hour whatever the members'."""
    path = "Envelope.Infiltration"
    by_surface = replace(office, f"{path}.CalculationMethod", "Flow/ExteriorArea")
    by_surface = replace(by_surface, f"{path}.FlowPerExteriorSurfaceArea", 0.0003)
    leaky = replace(office, f"{path}.CalculationMethod", "AirChanges/Hour")
    leaky = replace(leaky, f"{path}.AirChangesPerHour", 2.0)
    leaky = replace(leaky, "Name", "Leaky office")
    archetype = Archetype(
        Name="two infiltrations",
        Groups=[
            group(by_surface, "perimeter surface", 0.3, "perimeter"),
            group(leaky, "perimeter leaky", 0.2, "perimeter"),
            group(office, "core office", 0.5, "core"),
        ],
    )
    zone = next(g.Zone for g in approximate_merge(archetype).archetype.Groups if g.Exposure == "perimeter")
    infiltration = zone.Envelope.Infiltration
    assert infiltration.CalculationMethod == "AirChanges/Hour"
    assert infiltration.AirChangesPerHour > 0


def test_a_merged_zone_is_named_once_and_its_parts_follow_it(office: ZoneComponent) -> None:
    from archetypal.umi import to_umi  # noqa: PLC0415

    export = to_umi([three_groups(office)])
    names = [zone["Name"] for zone in json.loads(export.text)["Zones"]]
    assert not any("(merged) (merged)" in name for name in names)
    spurious = [
        loss
        for loss in export.report.losses
        if loss.rule == "names.component" and loss.location.endswith((".Operations.Name", ".Envelope.Name"))
    ]
    assert spurious == []


def test_natural_ventilation_keeps_a_window_schedule_not_the_mechanical_profile(office: ZoneComponent) -> None:
    ventilation = office.Operations.HVAC.Ventilation
    windows = ventilation.Schedule.model_copy(update={"Name": "Windows open"})
    natural = replace(
        office,
        "Operations.HVAC.Ventilation",
        ventilation.model_copy(update={"Provider": "Natural", "Schedule": windows}),
    )
    natural = replace(natural, "Operations.SpaceUse.Lighting.PowerDensity", 20.0)  # so the groups differ
    archetype = Archetype(
        Name="natural",
        Groups=[
            group(natural, "perimeter natural", 0.3, "perimeter"),
            group(office, "perimeter mechanical", 0.2, "perimeter"),
            group(office, "core office", 0.5, "core"),
        ],
    )
    merged = approximate_merge(archetype)
    (perimeter,) = [g for g in merged.archetype.Groups if g.Exposure == "perimeter"]
    merged_ventilation = perimeter.Zone.Operations.HVAC.Ventilation
    assert merged_ventilation.Provider == "Both"
    assert merged_ventilation.Schedule.Name == "Windows open"
    assert any(loss.location.endswith("Operations.HVAC.Ventilation.Schedule") for loss in merged.losses)
