"""The building rules of UMI translation (spec 003 T022; research R4, R6, R11, R13).

A building template becomes an archetype with two zone groups, `core` and `perimeter`, whose
floor-area shares are unset (`None`, set by the geometry). The template's single
window-to-wall ratio becomes the ratio of every orientation. Template-level fields map to the
archetype's fields of UP-9. Components without a one-to-one counterpart are
named by data-model.md's naming rules, so names survive both round trips.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Literal

import pytest
from epinterface.sbem.archetype import (
    ORIENTATIONS,
    Archetype,
    AtticAssumptions,
    BuildingGeometry,
    ZoneGroup,
)
from epinterface.sbem.components.envelope import (
    ConstructionAssemblyComponent,
    ConstructionLayerComponent,
    EnvelopeAssemblyComponent,
    GlazingConstructionSimpleComponent,
    InfiltrationComponent,
)
from epinterface.sbem.components.materials import ConstructionMaterialComponent
from epinterface.sbem.components.schedules import DayComponent, WeekComponent, YearComponent
from epinterface.sbem.components.space_use import (
    EquipmentComponent,
    LightingComponent,
    OccupancyComponent,
    ThermostatComponent,
    WaterUseComponent,
    ZoneSpaceUseComponent,
)
from epinterface.sbem.components.systems import (
    ConditioningSystemsComponent,
    DHWComponent,
    ThermalSystemComponent,
    VentilationComponent,
    ZoneHVACComponent,
)

from archetypal.umi import _format
from archetypal.umi._refs import resolve
from archetypal.umi.correspondence import get_rule
from archetypal.umi.report import LossKind, NoteKind
from archetypal.umi.rules import building
from archetypal.umi.rules.building import (
    CORE_GROUP,
    PERIMETER_GROUP,
    UniqueNames,
    apply_names,
    archetype_from_template,
    collision_loss,
    derived_name,
    groups_from_template,
    metadata_to_sbem,
    metadata_to_umi,
    template_losses,
    template_zones,
    umi_names,
    window_settings_name,
    wwr_to_sbem,
    wwr_to_umi,
    zone_component,
)

if TYPE_CHECKING:
    from collections.abc import Sequence

    from epinterface.sbem.components.zones import ZoneComponent

FIXTURES = Path(__file__).resolve().parents[2] / "fixtures" / "umi"
B2 = FIXTURES / "BostonTemplateLibrary_2.json"
ND = FIXTURES / "BostonTemplateLibrary_nodup.json"


# --- a minimal SBEM zone definition ------------------------------------------------------------


def _year(name: str, kind: str = "Occupancy", day_type: str = "Fraction", value: float = 1.0) -> YearComponent:
    day = DayComponent(Name=f"{name} day", Type=day_type, **{f"Hour_{h:02d}": value for h in range(24)})  # pyright: ignore[reportArgumentType]
    week = WeekComponent(
        Name=f"{name} week",
        Monday=day,
        Tuesday=day,
        Wednesday=day,
        Thursday=day,
        Friday=day,
        Saturday=day,
        Sunday=day,
    )
    months = (
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    )
    return YearComponent(Name=name, Type=kind, **dict.fromkeys(months, week))  # pyright: ignore[reportArgumentType]


def _assembly(name: str, surface: str) -> ConstructionAssemblyComponent:
    material = ConstructionMaterialComponent(
        Name="Concrete",
        Conductivity=1.4,
        Density=2240.0,
        Roughness="Rough",
        SpecificHeat=840.0,
        ThermalAbsorptance=0.9,
        SolarAbsorptance=0.7,
        VisibleAbsorptance=0.7,
        TemperatureCoefficientThermalConductivity=0.0,
        Type="Concrete",
    )
    layer = ConstructionLayerComponent(Thickness=0.2, LayerOrder=0, ConstructionMaterial=material)
    return ConstructionAssemblyComponent(Name=name, Layers=[layer], Type=surface)  # pyright: ignore[reportArgumentType]


def _infiltration(name: str) -> InfiltrationComponent:
    return InfiltrationComponent(
        Name=name,
        IsOn=True,
        ConstantCoefficient=1.0,
        TemperatureCoefficient=0.0,
        WindVelocityCoefficient=0.0,
        WindVelocitySquaredCoefficient=0.0,
        AFNAirMassFlowCoefficientCrack=0.0,
        AirChangesPerHour=0.3,
        FlowPerExteriorSurfaceArea=0.0,
        CalculationMethod="AirChanges/Hour",
    )


def _system(name: str, kind: Literal["Heating", "Cooling"]) -> ThermalSystemComponent:
    return ThermalSystemComponent(
        Name=name, ConditioningType=kind, Fuel="Electricity", SystemCOP=3.0, DistributionCOP=1.0
    )


def make_zone(name: str = "Office", *, lighting: float = 10.0) -> ZoneComponent:
    """A small valid SBEM zone whose every component is named `name` (or derived from it)."""
    schedule = _year("Office on")
    setpoint = _year("Setpoint", "Setpoint", "Temperature", 20.0)
    space_use = ZoneSpaceUseComponent(
        Name=name,
        Occupancy=OccupancyComponent(Name=name, PeopleDensity=0.05, Schedule=schedule, IsOn=True),
        Lighting=LightingComponent(
            Name=name, PowerDensity=lighting, DimmingType="Off", Schedule=_year("Office on", "Lighting"), IsOn=True
        ),
        Equipment=EquipmentComponent(Name=name, PowerDensity=8.0, Schedule=_year("Office on", "Equipment"), IsOn=True),
        Thermostat=ThermostatComponent(
            Name=name,
            IsOn=True,
            HeatingSetpoint=20.0,
            HeatingSchedule=setpoint,
            CoolingSetpoint=26.0,
            CoolingSchedule=setpoint,
        ),
        WaterUse=WaterUseComponent(Name=name, FlowRatePerPerson=0.05, Schedule=_year("Office on", "WaterUse")),
    )
    hvac = ZoneHVACComponent(
        Name=name,
        ConditioningSystems=ConditioningSystemsComponent(
            Name=name, Heating=_system(name, "Heating"), Cooling=_system(name, "Cooling")
        ),
        Ventilation=VentilationComponent(
            Name=name,
            FreshAirPerFloorArea=0.0003,
            FreshAirPerPerson=0.0025,
            Schedule=schedule,
            Provider="Mechanical",
            HRV="NoHRV",
            Economizer="NoEconomizer",
            DCV="NoDCV",
        ),
    )
    dhw = DHWComponent(
        Name=name,
        SystemCOP=0.85,
        WaterTemperatureInlet=10.0,
        DistributionCOP=1.0,
        WaterSupplyTemperature=55.0,
        IsOn=True,
        FuelType="NaturalGas",
    )
    assemblies = EnvelopeAssemblyComponent(
        Name=name,
        FlatRoofAssembly=_assembly("Roof", "FlatRoof"),
        FacadeAssembly=_assembly("Facade", "Facade"),
        FloorCeilingAssembly=_assembly("Slab", "FloorCeiling"),
        AtticRoofAssembly=_assembly("Roof", "AtticRoof"),
        AtticFloorAssembly=_assembly("Slab", "AtticFloor"),
        PartitionAssembly=_assembly("Partition", "Partition"),
        ExternalFloorAssembly=_assembly("Slab", "ExternalFloor"),
        GroundSlabAssembly=_assembly("Ground", "GroundSlab"),
        GroundWallAssembly=_assembly("Ground", "GroundWall"),
        BasementCeilingAssembly=_assembly("Slab", "BasementCeiling"),
    )
    window = GlazingConstructionSimpleComponent(Name="Double", SHGF=0.6, UValue=2.7, TVis=0.7, Type="Double")
    return zone_component(
        name,
        space_use=space_use,
        hvac=hvac,
        dhw=dhw,
        assemblies=assemblies,
        infiltration=_infiltration(name),
        attic_infiltration=_infiltration(name),
        basement_infiltration=_infiltration(name),
        window=window,
    )


UMI_NAMES = {
    "ZoneDefinition": "Office zone",
    "ZoneLoads": "Office loads",
    "ZoneConditioning": "Office conditioning",
    "ZoneVentilation": "Office ventilation",
    "DomesticHotWaterSettings": "Office hot water",
    "ZoneConstructions": "Office constructions",
}


def _archetype(groups: Sequence[ZoneGroup], **geometry: object) -> Archetype:
    return Archetype(Name="office", Groups=list(groups), Geometry=BuildingGeometry(**geometry))  # pyright: ignore[reportArgumentType]


def _library(path: Path) -> _format.UmiLibrary:
    return resolve(json.loads(path.read_text(encoding="utf-8")), path).library


# --- registration ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("rule_id", "to_sbem", "to_umi"),
    [
        ("building.groups", groups_from_template, template_zones),
        ("wwr.uniform", wwr_to_sbem, wwr_to_umi),
        ("names.component", apply_names, umi_names),
        ("names.metadata", metadata_to_sbem, metadata_to_umi),
        ("building.zone_definition", zone_component, None),
    ],
)
def test_rules_are_registered(rule_id: str, to_sbem: object, to_umi: object) -> None:
    registered = get_rule(rule_id)
    assert registered.to_sbem is to_sbem
    assert registered.to_umi is to_umi


def test_reporting_rules_are_registered() -> None:
    assert get_rule("building.library").id == "building.library"


@pytest.mark.parametrize(
    ("rule_id", "to_sbem", "to_umi"),
    [
        ("building.metadata", building.template_metadata_to_sbem, building.template_metadata_to_umi),
        ("building.partition_ratio", building.partition_area_to_sbem, building.partition_ratio_to_umi),
        ("structure.component", building.structure_to_sbem, building.structure_to_umi),
    ],
)
def test_up9_template_rules_are_registered(rule_id: str, to_sbem: object, to_umi: object) -> None:
    registered = get_rule(rule_id)
    assert (registered.to_sbem, registered.to_umi) == (to_sbem, to_umi)


# --- groups and shares (R4) --------------------------------------------------------------------


def _translate_counting(calls: list[_format.ZoneDefinition]):
    def translate(definition: _format.ZoneDefinition) -> ZoneComponent:
        calls.append(definition)
        return make_zone(definition.name or "unnamed", lighting=float(len(calls)))

    return translate


def test_template_gives_core_and_perimeter_with_unset_shares() -> None:
    core = _format.ZoneDefinition(Name="Core zone")
    perimeter = _format.ZoneDefinition(Name="Perimeter zone", DaylightWorkplaneHeight=0.9)
    template = _format.BuildingTemplate(Name="B", Core=core, Perimeter=perimeter)
    calls: list[_format.ZoneDefinition] = []
    groups = groups_from_template(template, _translate_counting(calls))
    assert [group.Name for group in groups] == [CORE_GROUP, PERIMETER_GROUP] == ["core", "perimeter"]
    assert [group.Exposure for group in groups] == ["core", "perimeter"]
    assert all(group.FloorAreaShare is None for group in groups)
    assert groups[0].Zone.Name == "Core zone"
    assert groups[1].Zone.Name == "Perimeter zone"
    assert groups[0].Zone != groups[1].Zone
    assert calls == [core, perimeter]


def test_one_zone_definition_gives_equal_groups_translated_once() -> None:
    zone = _format.ZoneDefinition(Name="Shared")
    template = _format.BuildingTemplate(Name="B", Core=zone, Perimeter=zone)
    calls: list[_format.ZoneDefinition] = []
    core, perimeter = groups_from_template(template, _translate_counting(calls))
    assert core.Zone == perimeter.Zone
    assert len(calls) == 1


def test_template_without_core_or_perimeter_is_refused() -> None:
    template = _format.BuildingTemplate(Name="B", Perimeter=_format.ZoneDefinition(Name="P"))
    with pytest.raises(ValueError, match="Core"):
        groups_from_template(template, _translate_counting([]))


@pytest.mark.parametrize("path", [B2, ND], ids=["B2", "ND"])
def test_every_sample_template_gives_equal_groups(path: Path) -> None:
    library = _library(path)
    assert library.building_templates
    for template in library.building_templates:
        calls: list[_format.ZoneDefinition] = []
        core, perimeter = groups_from_template(template, _translate_counting(calls))
        assert core.Zone == perimeter.Zone
        assert len(calls) == 1


def test_archetype_from_template() -> None:
    zone = _format.ZoneDefinition(Name="Shared")
    template = _format.BuildingTemplate(Name="B2 office", Core=zone, Perimeter=zone, DefaultWindowToWallRatio=0.25)
    archetype, losses = archetype_from_template(template, _translate_counting([]), pointer="/BuildingTemplates/0")
    assert archetype.Name == "B2 office"
    assert not archetype.shares_set
    assert [group.Name for group in archetype.Groups] == ["core", "perimeter"]
    assert archetype.Geometry.WindowToWallRatio == dict.fromkeys(ORIENTATIONS, 0.25)
    assert losses == []  # every other template field is at Basilisk's default
    assert Archetype.from_json(archetype.to_json()) == archetype


def test_core_and_perimeter_archetype_gives_both_zones_without_loss() -> None:
    core, perimeter = make_zone("Core"), make_zone("Perimeter")
    archetype = _archetype([
        ZoneGroup(Name="perimeter", Zone=perimeter, Exposure="perimeter"),
        ZoneGroup(Name="core", Zone=core, Exposure="core"),
    ])
    zones = template_zones(archetype)
    assert zones.core == core
    assert zones.perimeter == perimeter
    assert zones.losses == ()


def test_set_shares_are_dropped_with_their_values() -> None:
    archetype = _archetype([
        ZoneGroup(Name="perimeter", Zone=make_zone("P"), Exposure="perimeter", FloorAreaShare=0.6),
        ZoneGroup(Name="core", Zone=make_zone("C"), Exposure="core", FloorAreaShare=0.4),
    ])
    losses = template_zones(archetype).losses
    assert [(loss.kind, loss.location, loss.value, loss.rule) for loss in losses] == [
        (LossKind.SHARE_DROPPED, "core.FloorAreaShare", 0.4, "layout.share_dropped"),
        (LossKind.SHARE_DROPPED, "perimeter.FloorAreaShare", 0.6, "layout.share_dropped"),
    ]
    assert all(loss.subject == "office" for loss in losses)


@pytest.mark.parametrize("exposure", [None, "perimeter", "core"])
def test_single_group_is_copied_to_both(exposure: str | None) -> None:
    zone = make_zone("Only")
    archetype = _archetype([ZoneGroup(Name="all", Zone=zone, Exposure=exposure)])  # pyright: ignore[reportArgumentType]
    zones = template_zones(archetype)
    assert zones.core == zones.perimeter == zone
    [loss] = [loss for loss in zones.losses if loss.kind is LossKind.COPIED]
    [renamed] = [loss for loss in zones.losses if loss.kind is LossKind.RENAMED]
    assert (renamed.location, renamed.value) == ("all.Name", "all")
    assert renamed.replacement == ("core" if exposure == "core" else "perimeter")
    assert loss.rule == "layout.core_copied"
    assert loss.location == "all"
    assert loss.value == "all"


def test_groups_that_are_not_core_and_perimeter_are_refused() -> None:
    archetype = Archetype(
        Name="campus",
        Groups=[
            ZoneGroup(Name="a", Zone=make_zone("A"), FloorAreaShare=0.5),
            ZoneGroup(Name="b", Zone=make_zone("B"), FloorAreaShare=0.5),
        ],
    )
    with pytest.raises(ValueError, match="core and perimeter"):
        template_zones(archetype)


def test_building_level_sbem_fields_are_lost_on_writing() -> None:
    archetype = Archetype(
        Name="office",
        Groups=[
            ZoneGroup(Name="core", Zone=make_zone("C"), Exposure="core"),
            ZoneGroup(Name="perimeter", Zone=make_zone("P"), Exposure="perimeter"),
        ],
        Geometry=BuildingGeometry(Storeys=3, ConditionedFloorArea=1200.0),
        Attic=AtticAssumptions(UseFraction=0.5, Conditioned=True),
    )
    lost = {loss.location: loss for loss in template_zones(archetype).losses}
    assert set(lost) == {"archetype.Attic", "archetype.Geometry.Storeys", "archetype.Geometry.ConditionedFloorArea"}
    assert lost["archetype.Geometry.Storeys"].value == 3
    assert lost["archetype.Attic"].value == {"UseFraction": 0.5, "Conditioned": True}
    assert all(loss.kind is LossKind.LOST for loss in lost.values())


# --- wwr.uniform -------------------------------------------------------------------------------


def test_wwr_reads_as_the_same_ratio_on_every_orientation() -> None:
    ratios = wwr_to_sbem(0.37)
    assert list(ratios) == list(ORIENTATIONS)
    assert set(ratios.values()) == {0.37}


def test_uniform_wwr_writes_back_exactly() -> None:
    result = wwr_to_umi(BuildingGeometry(WindowToWallRatio=wwr_to_sbem(0.37)), subject="office")
    assert result.value == 0.37
    assert result.losses == ()
    assert result.notes == ()


def test_differing_wwr_writes_the_facade_area_weighted_mean_and_is_lost() -> None:
    ratios = dict.fromkeys(ORIENTATIONS, 0.2) | {"S": 0.6}
    facades = dict.fromkeys(ORIENTATIONS, 1.0) | {"S": 3.0}
    result = wwr_to_umi(
        BuildingGeometry(WindowToWallRatio=ratios, FacadeAreaPerFloorArea=facades),  # pyright: ignore[reportArgumentType]
        subject="office",
    )
    expected = (7 * 0.2 + 3.0 * 0.6) / 10.0
    assert result.value == pytest.approx(expected, rel=1e-12)
    [loss] = result.losses
    assert loss.kind is LossKind.LOST
    assert loss.rule == "wwr.uniform"
    assert loss.location == "archetype.Geometry.WindowToWallRatio"
    assert loss.value == ratios
    assert loss.replacement == pytest.approx(expected, rel=1e-12)
    assert loss.subject == "office"


def test_differing_wwr_without_facade_areas_uses_the_plain_mean() -> None:
    ratios = dict.fromkeys(ORIENTATIONS, 0.2) | {"N": 0.6}
    result = wwr_to_umi(BuildingGeometry(WindowToWallRatio=ratios), subject="office")  # pyright: ignore[reportArgumentType]
    assert result.value == pytest.approx((7 * 0.2 + 0.6) / 8, rel=1e-12)
    assert len(result.losses) == 1


def test_unknown_wwr_writes_basilisk_default_with_a_note() -> None:
    result = wwr_to_umi(BuildingGeometry(), subject="office")
    assert result.value == _format.BuildingTemplate().default_window_to_wall_ratio == 0.4
    assert result.losses == ()
    [note] = result.notes
    assert note.kind is NoteKind.DEFAULTED
    assert note.rule == "wwr.uniform"


# --- template-level fields of R6's table -------------------------------------------------------

R6_TEMPLATE_FIELDS: dict[str, object] = {
    "PartitionRatio": 0.35,
    "Lifespan": 60,
    "YearFrom": 1950,
    "YearTo": 1980,
    "Country": ["US"],
    "ClimateZone": ["5A"],
    "Authors": ["A. Author"],
    "AuthorEmails": ["author@example.org"],
    "Version": "v2.1",
    "Category": "Office",
    "Comments": "A comment",
    "DataSource": "A survey",
}


def test_each_template_level_field_maps_to_the_archetype() -> None:
    """UP-9: R6's template-level fields map to the archetype (T070)."""
    structure = _format.StructureInformation(Name="Steel frame", UseAdvancedModel=True, AssemblyCarbon=4.0)
    template = _format.BuildingTemplate.model_validate({
        "Name": "B",
        "Structure": structure,
        "Core": _format.ZoneDefinition(Name="z"),
        "Perimeter": _format.ZoneDefinition(Name="z"),
        **R6_TEMPLATE_FIELDS,
    })
    assert template_losses(template, pointer="/BuildingTemplates/3") == []
    archetype, losses = archetype_from_template(
        template, lambda zone: make_zone(zone.name or ""), pointer="/BuildingTemplates/3"
    )
    assert losses == []
    assert (archetype.Lifespan, archetype.YearFrom, archetype.YearTo) == (60, 1950, 1980)
    assert (archetype.Country, archetype.ClimateZone) == (["US"], ["5A"])
    assert (archetype.Authors, archetype.AuthorEmails, archetype.Version) == (
        ["A. Author"],
        ["author@example.org"],
        "v2.1",
    )
    assert (archetype.Category, archetype.Comment, archetype.DataSource) == ("Office", "A comment", "A survey")
    assert archetype.Structure is not None
    assert (archetype.Structure.Name, archetype.Structure.UseAdvancedModel) == ("Steel frame", True)
    assert archetype.Structure.AssemblyCarbon == 4.0
    area, _ = building.partition_area_to_sbem(template, pointer="/BuildingTemplates/3")
    assert area == pytest.approx(0.7)  # both faces of 0.35 m2 of partition per m2 of floor
    back = building.template_metadata_to_umi(archetype)
    for key in R6_TEMPLATE_FIELDS.keys() - {"PartitionRatio"}:
        expected = R6_TEMPLATE_FIELDS[key]
        assert back[key] == expected, key
    structure_back, losses = building.structure_to_umi(archetype.Structure, location="archetype.Structure", subject="B")
    assert losses == []
    assert structure_back == structure


def test_values_sbem_refuses_are_lost() -> None:
    template = _format.BuildingTemplate.model_validate({
        "Name": "B",
        "PartitionRatio": -0.1,
        "Lifespan": -5,
        "YearFrom": 1990,
        "YearTo": 1980,
    })
    losses = template_losses(template, pointer="/BuildingTemplates/0")
    assert {(loss.location, loss.upstream) for loss in losses} == {
        ("/BuildingTemplates/0/PartitionRatio", None),
        ("/BuildingTemplates/0/Lifespan", None),
        ("/BuildingTemplates/0/YearTo", None),
    }


def test_partition_ratio_is_written_from_the_perimeter_group() -> None:
    ratio, losses = building.partition_ratio_to_umi({"core": 0.4, "perimeter": 0.7}, subject="A")
    assert ratio == pytest.approx(0.35)
    (loss,) = losses
    assert (loss.location, loss.value, loss.rule) == (
        "core.Envelope.Assemblies.PartitionAreaPerFloorArea",
        0.4,
        "building.partition_ratio",
    )


def test_template_fields_at_basilisk_defaults_lose_nothing() -> None:
    assert template_losses(_format.BuildingTemplate(Name="B"), pointer="/BuildingTemplates/0") == []


def test_sample_templates_map_their_structure() -> None:
    library = _library(B2)
    for index, template in enumerate(library.building_templates):
        assert template_losses(template, pointer=f"/BuildingTemplates/{index}") == []
        if template.structure is not None:
            structure, losses = building.structure_to_sbem(
                template.structure, pointer=f"/BuildingTemplates/{index}/Structure", subject="B"
            )
            assert [loss for loss in losses if loss.rule == "structure.component"] == []
            assert len(structure.MassRatios) == len(template.structure.mass_ratios)


# --- names (data-model.md, "Names of components without a one-to-one counterpart") ------------


def test_reading_names_sub_components_by_the_rules() -> None:
    zone = apply_names(make_zone("x"), UMI_NAMES)
    assert zone.Name == zone.Operations.Name == zone.Envelope.Name == "Office zone"
    space_use = zone.Operations.SpaceUse
    assert space_use.Name == "Office loads"
    assert space_use.Occupancy.Name == "Office loads occupancy"
    assert space_use.Lighting.Name == "Office loads lighting"
    assert space_use.Equipment.Name == "Office loads equipment"
    hvac = zone.Operations.HVAC
    assert hvac.Name == hvac.ConditioningSystems.Name == hvac.Ventilation.Name == "Office conditioning"
    assert space_use.Thermostat.Name == "Office conditioning"
    assert hvac.ConditioningSystems.Heating is not None
    assert hvac.ConditioningSystems.Cooling is not None
    assert hvac.ConditioningSystems.Heating.Name == "Office conditioning heating"
    assert hvac.ConditioningSystems.Cooling.Name == "Office conditioning cooling"
    assert zone.Envelope.Infiltration.Name == "Office ventilation"
    assert zone.Operations.DHW.Name == space_use.WaterUse.Name == "Office hot water"
    assert zone.Envelope.Assemblies.Name == "Office constructions"


def test_names_survive_umi_sbem_umi() -> None:
    zone = apply_names(make_zone("x"), UMI_NAMES)
    result = umi_names(zone, subject="office", group="perimeter")
    assert result.names == UMI_NAMES
    assert result.losses == ()


def test_names_survive_sbem_umi_sbem() -> None:
    zone = apply_names(make_zone("x"), UMI_NAMES)
    assert apply_names(zone, umi_names(zone, subject="office", group="core").names) == zone


def test_naming_skips_systems_that_are_off() -> None:
    zone = make_zone("x")
    zone.Operations.HVAC.ConditioningSystems.Cooling = None
    named = apply_names(zone, UMI_NAMES)
    assert named.Operations.HVAC.ConditioningSystems.Cooling is None
    assert zone.Name == "x"  # the input is not changed


def test_sub_component_names_that_break_the_rules_are_lost_on_writing() -> None:
    zone = apply_names(make_zone("x"), UMI_NAMES)
    zone.Operations.SpaceUse.Lighting.Name = "Custom lights"
    zone.Envelope.AtticInfiltration.Name = "Attic leaks"
    result = umi_names(zone, subject="office", group="perimeter")
    assert result.names == UMI_NAMES
    lost = {loss.location: loss for loss in result.losses}
    assert set(lost) == {"perimeter.Operations.SpaceUse.Lighting.Name", "perimeter.Envelope.AtticInfiltration.Name"}
    assert lost["perimeter.Operations.SpaceUse.Lighting.Name"].value == "Custom lights"
    assert lost["perimeter.Operations.SpaceUse.Lighting.Name"].replacement == "Office loads lighting"
    assert all(loss.rule == "names.component" and loss.kind is LossKind.LOST for loss in lost.values())


def test_derived_names() -> None:
    assert derived_name("Office loads", "occupancy") == "Office loads occupancy"
    assert window_settings_name("Double clear") == "Double clear settings"


def test_unique_names_suffix_different_content_in_order() -> None:
    names = UniqueNames()
    assert names.assign("Concrete", "a") == "Concrete"
    assert names.assign("Concrete", "a") == "Concrete"  # same content: one component
    assert names.assign("Concrete", "b") == "Concrete #2"
    assert names.assign("Concrete", "c") == "Concrete #3"
    assert names.assign("Concrete", "b") == "Concrete #2"
    assert names.assign("Brick", "a") == "Brick"  # same content, other name: kept apart
    assert names.renamed == (("Concrete", "Concrete #2"), ("Concrete", "Concrete #3"))


def test_unique_names_never_reuse_an_existing_name() -> None:
    names = UniqueNames()
    assert names.assign("A #2", "x") == "A #2"
    assert names.assign("A", "y") == "A"
    assert names.assign("A", "z") == "A #3"


def test_collision_loss() -> None:
    loss = collision_loss(subject="", location="/OpaqueMaterials/4", original="Concrete", renamed="Concrete #2")
    assert loss.kind is LossKind.RENAMED
    assert loss.rule == "names.collision"
    assert loss.value == "Concrete"
    assert loss.replacement == "Concrete #2"


# --- metadata (names.metadata) -----------------------------------------------------------------


def test_metadata_round_trips() -> None:
    material = _format.OpaqueMaterial(Name="Brick", Category="Masonry", Comments="old", DataSource="ASHRAE")
    fields = metadata_to_sbem(material)
    assert fields == {"Category": "Masonry", "Comment": "old", "DataSource": "ASHRAE"}
    sbem = make_zone().Envelope.Assemblies.FacadeAssembly.model_copy(update=fields)
    result = metadata_to_umi(sbem, subject="office", location="perimeter.Envelope.Assemblies.FacadeAssembly")
    assert result.fields == {"Category": "Masonry", "Comments": "old", "DataSource": "ASHRAE"}
    assert result.losses == ()


def test_default_category_is_unset_in_sbem() -> None:
    assert metadata_to_sbem(_format.OpaqueMaterial(Name="Brick"))["Category"] is None
    unset = make_zone().Envelope.Assemblies.FacadeAssembly
    assert metadata_to_umi(unset, subject="o", location="x").fields["Category"] == "Uncategorized"


def test_sbem_version_metadata_is_lost_on_writing() -> None:
    sbem = make_zone().Envelope.Assemblies.FacadeAssembly.model_copy(update={"Version": "3"})
    [loss] = metadata_to_umi(sbem, subject="office", location="perimeter.Envelope.Assemblies.FacadeAssembly").losses
    assert loss.location == "perimeter.Envelope.Assemblies.FacadeAssembly.Version"
    assert loss.value == "3"
    assert loss.rule == "names.metadata"


def test_zone_component_carries_zone_definition_metadata() -> None:
    zone = make_zone("Office")
    named = zone_component(
        "Office",
        space_use=zone.Operations.SpaceUse,
        hvac=zone.Operations.HVAC,
        dhw=zone.Operations.DHW,
        assemblies=zone.Envelope.Assemblies,
        infiltration=zone.Envelope.Infiltration,
        attic_infiltration=zone.Envelope.AtticInfiltration,
        basement_infiltration=zone.Envelope.BasementInfiltration,
        window=zone.Envelope.Window,
        metadata=metadata_to_sbem(_format.ZoneDefinition(Name="Office", Category="Office", Comments="c")),
    )
    assert named.Operations.Category == "Office"
    assert named.Operations.Comment == "c"
    assert named.Name == named.Operations.Name == named.Envelope.Name == "Office"


def test_module_exports() -> None:
    assert set(building.__all__) >= {"groups_from_template", "template_zones", "wwr_to_sbem", "wwr_to_umi"}
