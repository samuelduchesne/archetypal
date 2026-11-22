"""The field-by-field correspondence between UMI template libraries and SBEM (FR-009, SC-005).

`CORRESPONDENCE` holds one `FieldMapping` per serialised field of every Basilisk Core class,
as listed by `tools/basilisk-check --list-fields` in `tests/data/basilisk_fields.json`. A field
is listed under the class that declares it: `Name`, `Category`, `Comments` and `DataSource`
under `LibraryComponent`, the fields shared by every material under `MaterialBase` (research
R5). The table drives the translation, its tests and the generated reference page
`docs/reference/umi-correspondence.md`, so the published mapping is the implemented one.

SBEM paths are dotted field paths on epinterface's SBEM model. The first segment says where a
path starts:

- `archetype.` for building-level fields of `epinterface.sbem.archetype.Archetype`;
- the name of an SBEM component class (`ConstructionMaterialComponent.Conductivity`,
  `DayComponent.Hour_00`) for fields of a component used in many places;
- anything else is relative to one zone group's `ZoneComponent`
  (`Operations.SpaceUse.Lighting.PowerDensity`).

Conversion rules are registered by identifier with the `rule` decorator. The rule modules in
`archetypal.umi.rules` register their rules when imported; `registered_rules()` imports them.
Each rule identifier belongs to the module named by its prefix (`RULE_MODULES`), and the set of
registered identifiers equals the set of identifiers in `CORRESPONDENCE`.
"""

from __future__ import annotations

import importlib
import sys
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType
from typing import TYPE_CHECKING, Literal, TypeVar

if TYPE_CHECKING:
    from collections.abc import Mapping

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:  # pragma: no cover - Python 3.10 has no StrEnum

    class StrEnum(str, Enum):
        """A `str` enum whose `str()` is its value, as Python 3.11's `enum.StrEnum`."""

        def __str__(self) -> str:
            """Return the member's value."""
            return str(self.value)


__all__ = [
    "CORRESPONDENCE",
    "LIBRARY_RULES",
    "RULE_MODULES",
    "UPSTREAM_ITEMS",
    "FieldMapping",
    "MappingStatus",
    "Relevance",
    "Rule",
    "RuleFunction",
    "declare_rule",
    "get_rule",
    "mapping",
    "mappings_for",
    "registered_rules",
    "rule",
    "rule_ids",
]


class Relevance(StrEnum):
    """What a UMI field is used for."""

    SIMULATION = "S"
    """Read by the energy simulation."""
    LIFE_CYCLE = "L"
    """Used by UMI's life-cycle (embodied carbon, cost) module."""
    DESCRIPTIVE = "D"
    """Describes a component: names and metadata."""


class MappingStatus(StrEnum):
    """How a UMI field is represented in SBEM."""

    EXACT = "exact"
    """Copied without change, possibly under another name."""
    CONVERTED = "converted"
    """Converted by a stated rule that conserves the quantity named in the note."""
    UPSTREAM = "upstream"
    """No SBEM field yet: reported as lost, naming the upstream item that adds it (FR-010)."""
    NONE = "none"
    """No counterpart by design; the note says why."""


UPSTREAM_ITEMS: frozenset[str] = frozenset({"UP-2", "UP-9", "UP-10"})
"""The roadmap's upstream items that a mapping or a loss may name."""

LIBRARY_RULES: frozenset[str] = frozenset({
    "library.unused",
    "names.collision",
    "layout.merged",
    "layout.share_dropped",
    "layout.core_copied",
    "validation.skipped",
})
"""Rules of the whole library or layout, which a `Loss` may name without a registered rule."""

RULE_MODULES: Mapping[str, str] = MappingProxyType({
    "material": "materials",
    "construction": "materials",
    "schedule": "schedules",
    "window": "windows",
    "loads": "loads",
    "mass": "loads",
    "thermostat": "conditioning",
    "conditioning": "conditioning",
    "cop": "conditioning",
    "fuel": "conditioning",
    "vent": "ventilation",
    "infiltration": "ventilation",
    "dhw": "hotwater",
    "building": "building",
    "wwr": "building",
    "names": "building",
    "structure": "building",
})
"""The module of `archetypal.umi.rules` that registers each rule, by identifier prefix."""


@dataclass(frozen=True)
class FieldMapping:
    """How one UMI field maps to SBEM.

    Attributes:
        umi_class: The Basilisk class that declares the field, for example `"ZoneLoads"`.
        umi_key: The field's JSON key, for example `"LightingPowerDensity"`.
        relevance: What the field is used for.
        sbem_paths: The SBEM field paths it maps to; empty when `status` is `UPSTREAM` or `NONE`.
        rule: The identifier of the rule that translates it.
        status: How it is represented.
        upstream: The upstream item that adds what SBEM lacks; set when `status` is
            `UPSTREAM`, and also when a field maps exactly except in some places.
        note: The quantity the conversion conserves, or why there is no counterpart.
    """

    umi_class: str
    umi_key: str
    relevance: Relevance
    sbem_paths: tuple[str, ...]
    rule: str
    status: MappingStatus
    upstream: str | None
    note: str


S, L, D = Relevance.SIMULATION, Relevance.LIFE_CYCLE, Relevance.DESCRIPTIVE
E, C, U, N = MappingStatus.EXACT, MappingStatus.CONVERTED, MappingStatus.UPSTREAM, MappingStatus.NONE

_MONTHS = tuple(
    f"YearComponent.{month}"
    for month in (
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
)
_DAYS = tuple(
    f"WeekComponent.{day}" for day in ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
)
_HOURS = tuple(f"DayComponent.Hour_{hour:02d}" for hour in range(24))
_MAT = "ConstructionMaterialComponent"
_THERMOSTAT = "Operations.SpaceUse.Thermostat"
_SYSTEMS = "Operations.HVAC.ConditioningSystems"
_VENTILATION = "Operations.HVAC.Ventilation"
_SPACE_USE = "Operations.SpaceUse"
_ASSEMBLIES = "Envelope.Assemblies"
_WINDOW = "GlazingConstructionSimpleComponent"
_METADATA_HOLDERS = (
    _MAT,
    "ConstructionAssemblyComponent",
    _WINDOW,
    "ZoneOperationsComponent",
    "ZoneSpaceUseComponent",
    "ZoneHVACComponent",
    "DHWComponent",
    "InfiltrationComponent",
    "EnvelopeAssemblyComponent",
)


def _rows(
    umi_class: str,
    keys: tuple[str, ...],
    relevance: Relevance,
    rule_id: str,
    status: MappingStatus,
    note: str,
    *,
    paths: tuple[str, ...] = (),
    upstream: str | None = None,
) -> tuple[FieldMapping, ...]:
    """Build the rows of several keys of one class that share a rule, status and note."""
    return tuple(FieldMapping(umi_class, key, relevance, paths, rule_id, status, upstream, note) for key in keys)


def _row(
    umi_class: str,
    key: str,
    relevance: Relevance,
    paths: tuple[str, ...],
    rule_id: str,
    status: MappingStatus,
    note: str,
    *,
    upstream: str | None = None,
) -> FieldMapping:
    """Build one row."""
    return FieldMapping(umi_class, key, relevance, paths, rule_id, status, upstream, note)


_UP9 = "SBEM has no such field yet; UP-9 adds it"
_STRUCTURE_NOTE = f"Structural model for UMI's life-cycle module. {_UP9} (a structure component at building level)."

CORRESPONDENCE: tuple[FieldMapping, ...] = (
    # --- LibraryComponent: fields of every component -------------------------------------------
    _row(
        "LibraryComponent",
        "Name",
        D,
        (
            "archetype.Name",
            "Name",
            f"{_MAT}.Name",
            "ConstructionAssemblyComponent.Name",
            f"{_WINDOW}.Name",
            "YearComponent.Name",
            "WeekComponent.Name",
            "DayComponent.Name",
        ),
        "names.component",
        E,
        "The receiving component's name. Components without a one-to-one counterpart are named "
        "by data-model.md's naming rules, so names survive both round trips.",
    ),
    _row(
        "LibraryComponent",
        "Category",
        D,
        tuple(f"{holder}.Category" for holder in _METADATA_HOLDERS),
        "names.metadata",
        E,
        "The receiving component's Category. Templates and schedules have none: lost there (UP-9).",
        upstream="UP-9",
    ),
    _row(
        "LibraryComponent",
        "Comments",
        D,
        tuple(f"{holder}.Comment" for holder in _METADATA_HOLDERS),
        "names.metadata",
        E,
        "The receiving component's Comment. Templates and schedules have none: lost there (UP-9).",
        upstream="UP-9",
    ),
    _row(
        "LibraryComponent",
        "DataSource",
        D,
        tuple(f"{holder}.DataSource" for holder in _METADATA_HOLDERS),
        "names.metadata",
        E,
        "The receiving component's DataSource. Templates and schedules have none: lost there (UP-9).",
        upstream="UP-9",
    ),
    # --- Library: the 17 collections --------------------------------------------------------------
    *_rows(
        "Library",
        (
            "GasMaterials",
            "GlazingMaterials",
            "OpaqueMaterials",
            "OpaqueConstructions",
            "WindowConstructions",
            "StructureDefinitions",
            "DaySchedules",
            "WeekSchedules",
            "YearSchedules",
            "DomesticHotWaterSettings",
            "VentilationSettings",
            "ZoneConditionings",
            "ZoneConstructionSets",
            "ZoneLoads",
            "Zones",
            "BuildingTemplates",
            "WindowSettings",
        ),
        D,
        "building.library",
        N,
        "A collection of the file, not a field: SBEM nests components by value. Each component is "
        "translated where a template uses it; components no template uses are reported as unused "
        "(library.unused).",
    ),
    # --- MaterialBase: fields of opaque, glazing and gas materials --------------------------------
    _row(
        "MaterialBase",
        "Conductivity",
        S,
        (f"{_MAT}.Conductivity",),
        "material.properties",
        E,
        "Same quantity (W/m-K). For glazing and gas materials it enters window.simple_from_layers.",
    ),
    _row(
        "MaterialBase",
        "Density",
        S,
        (f"{_MAT}.Density",),
        "material.properties",
        E,
        "Same quantity (kg/m3).",
    ),
    _row(
        "MaterialBase",
        "Cost",
        L,
        (f"{_MAT}.Cost", f"{_MAT}.RateUnit"),
        "material.cost_per_m3",
        C,
        'Cost per m3, with RateUnit = "m3"; conserves cost per unit volume.',
    ),
    _row(
        "MaterialBase",
        "EmbodiedCarbon",
        L,
        (f"{_MAT}.EmbodiedCarbon", f"{_MAT}.RateUnit"),
        "material.carbon_per_m3",
        C,
        "C_m3 = C_kg x density, inverse C_kg = C_m3 / density (refused for density 0); conserves "
        "embodied carbon per unit volume.",
    ),
    *_rows(
        "MaterialBase",
        (
            "EmbodiedEnergy",
            "SubstitutionRatePattern",
            "SubstitutionTimestep",
            "TransportCarbon",
            "TransportDistance",
            "TransportEnergy",
        ),
        L,
        "material.environmental",
        U,
        f"Life-cycle field of a material. {_UP9} (environmental fields on materials).",
        upstream="UP-9",
    ),
    # --- OpaqueMaterial ---------------------------------------------------------------------------
    *_rows(
        "OpaqueMaterial",
        ("DesignStrength", "ModulusOfElasticity", "MoistureDiffusionResistance"),
        L,
        "material.environmental",
        U,
        f"Structural or hygrothermal property used by UMI's life-cycle module only. {_UP9}.",
        upstream="UP-9",
    ),
    _row(
        "OpaqueMaterial",
        "Roughness",
        S,
        (f"{_MAT}.Roughness",),
        "material.properties",
        E,
        "One of EnergyPlus's six roughness keywords; any other value is a range problem.",
    ),
    *(
        _row("OpaqueMaterial", key, S, (f"{_MAT}.{key}",), "material.properties", E, "Same quantity.")
        for key in ("SolarAbsorptance", "SpecificHeat", "VisibleAbsorptance")
    ),
    _row(
        "OpaqueMaterial",
        "ThermalEmittance",
        S,
        (f"{_MAT}.ThermalAbsorptance",),
        "material.properties",
        E,
        "Thermal emittance and thermal absorptance are the same quantity (Kirchhoff's law).",
    ),
    # --- GlazingMaterial and GasMaterial ----------------------------------------------------------
    *_rows(
        "GlazingMaterial",
        (
            "DirtFactor",
            "IREmissivityBack",
            "IREmissivityFront",
            "IRTransmittance",
            "SolarReflectanceBack",
            "SolarReflectanceFront",
            "SolarTransmittance",
            "VisibleReflectanceBack",
            "VisibleReflectanceFront",
            "VisibleTransmittance",
        ),
        S,
        "window.equivalent_layer",
        U,
        "Per-layer glazing property. SBEM windows are simple glazing: on reading the layers give U, "
        "SHGC and VT (window.simple_from_layers) and the property is lost; on writing it comes from "
        "the equivalent layer of the simple window. UP-9 adds layered windows.",
        upstream="UP-9",
    ),
    _row(
        "GasMaterial",
        "Category",
        D,
        (),
        "window.equivalent_layer",
        U,
        "Category of a gas layer; SBEM windows have no gas layers until UP-9's layered windows.",
        upstream="UP-9",
    ),
    _row(
        "GasMaterial",
        "Type",
        S,
        (),
        "window.equivalent_layer",
        U,
        "Gas of a gas layer; it enters U, SHGC and VT through window.simple_from_layers and is lost "
        "until UP-9's layered windows.",
        upstream="UP-9",
    ),
    # --- Layers, constructions and construction sets ----------------------------------------------
    _row(
        "MaterialLayer",
        "Material",
        S,
        ("ConstructionLayerComponent.ConstructionMaterial",),
        "construction.layers",
        E,
        "The layer's material.",
    ),
    _row(
        "MaterialLayer",
        "Thickness",
        S,
        ("ConstructionLayerComponent.Thickness",),
        "construction.layers",
        E,
        "Same quantity (m); thickness belongs to the layer in both formats.",
    ),
    _row(
        "OpaqueConstruction",
        "Layers",
        S,
        ("ConstructionAssemblyComponent.Layers", "ConstructionLayerComponent.LayerOrder"),
        "construction.layers",
        E,
        "Layers in order, outside first; the list position becomes LayerOrder.",
    ),
    *_rows(
        "ConstructionBase",
        ("AssemblyCarbon", "AssemblyCost", "AssemblyEnergy", "DisassemblyCarbon", "DisassemblyEnergy"),
        L,
        "construction.environmental",
        U,
        f"Life-cycle field of a construction. {_UP9} (environmental fields on assemblies).",
        upstream="UP-9",
    ),
    _row(
        "WindowConstruction",
        "Layers",
        S,
        (f"{_WINDOW}.UValue", f"{_WINDOW}.SHGF", f"{_WINDOW}.TVis"),
        "window.simple_from_layers",
        C,
        "U, SHGC and VT of the layers computed by idfkit.thermal (approximate); the layers "
        "themselves are lost until UP-9's layered windows.",
        upstream="UP-9",
    ),
    *(
        _row(
            "ZoneConstructions",
            key,
            S,
            (f"{_ASSEMBLIES}.{target}",),
            "construction.sets",
            E,
            f"The {key.lower()} assembly. SBEM slots UMI lacks are filled from it on reading (noted) "
            "and lost on writing when they differ.",
        )
        for key, target in (
            ("Facade", "FacadeAssembly"),
            ("Ground", "GroundSlabAssembly"),
            ("Partition", "PartitionAssembly"),
            ("Roof", "FlatRoofAssembly"),
            ("Slab", "FloorCeilingAssembly"),
        )
    ),
    *_rows(
        "ZoneConstructions",
        ("IsFacadeAdiabatic", "IsGroundAdiabatic", "IsPartitionAdiabatic", "IsRoofAdiabatic", "IsSlabAdiabatic"),
        S,
        "construction.adiabatic",
        U,
        f"Adiabatic boundary flag of an assembly. {_UP9} (adiabatic flags per assembly).",
        upstream="UP-9",
    ),
    # --- Structure (life cycle) -------------------------------------------------------------------
    *_rows(
        "StructureInformation",
        ("AdvancedModel", "MassRatios", "UseAdvancedModel"),
        L,
        "structure.upstream",
        U,
        _STRUCTURE_NOTE,
        upstream="UP-9",
    ),
    *_rows(
        "MassRatios",
        ("HighLoadRatio", "Material", "NormalRatio"),
        L,
        "structure.upstream",
        U,
        _STRUCTURE_NOTE,
        upstream="UP-9",
    ),
    *_rows(
        "AdvancedStructuralModel",
        ("ColumnWallSpacing", "ConstructionSystems", "FoundationSoilSettings", "LoadingSettings"),
        L,
        "structure.upstream",
        U,
        _STRUCTURE_NOTE,
        upstream="UP-9",
    ),
    *_rows(
        "ColumnWallSpacingSettings",
        ("PrimarySpan", "SecondarySpan"),
        L,
        "structure.upstream",
        U,
        _STRUCTURE_NOTE,
        upstream="UP-9",
    ),
    *_rows(
        "ConstructionSystem",
        ("Material", "ConstructionSystemType"),
        L,
        "structure.upstream",
        U,
        _STRUCTURE_NOTE,
        upstream="UP-9",
    ),
    *_rows(
        "ConstructionSystemSettings",
        ("Beams", "Columns", "Floors", "Foundations", "LateralSystem"),
        L,
        "structure.upstream",
        U,
        _STRUCTURE_NOTE,
        upstream="UP-9",
    ),
    *_rows(
        "FoundationSoilSettings",
        ("FoundationSoilPreset", "FoundationSoilValue"),
        L,
        "structure.upstream",
        U,
        _STRUCTURE_NOTE,
        upstream="UP-9",
    ),
    *_rows(
        "LoadingSettings",
        ("LiveLoadingPreset", "LiveLoadingValue"),
        L,
        "structure.upstream",
        U,
        _STRUCTURE_NOTE,
        upstream="UP-9",
    ),
    # --- Schedules --------------------------------------------------------------------------------
    *(
        _row(
            cls,
            "Category",
            D,
            (),
            "schedule.metadata",
            U,
            f"Category of a schedule. {_UP9} (metadata on schedules).",
            upstream="UP-9",
        )
        for cls in ("DaySchedule", "WeekSchedule", "YearSchedule")
    ),
    _row(
        "DaySchedule",
        "Values",
        S,
        _HOURS,
        "schedule.day",
        E,
        "The 24 hourly values, hour 0 first.",
    ),
    _row(
        "DaySchedule",
        "Type",
        S,
        ("DayComponent.Type",),
        "schedule.type",
        E,
        "Fraction, Temperature and AnyNumber map by name; any other type becomes AnyNumber, noted.",
    ),
    _row(
        "WeekSchedule",
        "Type",
        S,
        ("DayComponent.Type",),
        "schedule.type",
        C,
        "SBEM keeps the type on days only: a week's type is written from its days' type.",
    ),
    _row(
        "YearSchedule",
        "Type",
        S,
        ("DayComponent.Type",),
        "schedule.type",
        C,
        "SBEM keeps the type on days only (YearComponent.Type is the schedule's role): a year's "
        "type is written from its days' type.",
    ),
    _row(
        "WeekSchedule",
        "Days",
        S,
        _DAYS,
        "schedule.week",
        E,
        "The seven days, Monday first.",
    ),
    _row(
        "YearSchedule",
        "Parts",
        S,
        _MONTHS,
        "schedule.months",
        C,
        "One week per calendar month: copied when a month lies in one part, else projected with "
        "002's projection; conserves each month's sum over the reference year.",
    ),
    *_rows(
        "YearSchedulePart",
        ("FromDay", "FromMonth", "ToDay", "ToMonth", "Schedule"),
        S,
        "schedule.months",
        C,
        "Part boundaries and week: folded into one week per month (schedule.months); on writing, "
        "equal consecutive months merge into one part ending on a month's last day.",
        paths=_MONTHS,
    ),
    # --- DomesticHotWaterSettings -----------------------------------------------------------------
    _row(
        "DomesticHotWaterSettings",
        "FlowRatePerFloorArea",
        S,
        (f"{_SPACE_USE}.WaterUse.FlowRatePerPerson",),
        "dhw.per_person",
        C,
        "q_p = q_a x sum of hourly schedule / (365 x people density); conserves annual hot-water volume per m2.",
    ),
    _row(
        "DomesticHotWaterSettings",
        "WaterSchedule",
        S,
        (f"{_SPACE_USE}.WaterUse.Schedule",),
        "dhw.schedule",
        E,
        "The hot-water use schedule.",
    ),
    *(
        _row("DomesticHotWaterSettings", key, S, (f"Operations.DHW.{key}",), "dhw.settings", E, "Same quantity.")
        for key in ("IsOn", "WaterSupplyTemperature", "WaterTemperatureInlet")
    ),
    _row(
        "DomesticHotWaterSettings",
        "CoefficientOfPerformance",
        S,
        ("Operations.DHW.SystemCOP", "Operations.DHW.DistributionCOP"),
        "cop.system",
        C,
        "SystemCOP = COP with DistributionCOP = 1; inverse COP = SystemCOP x DistributionCOP. "
        "Conserves consumed energy for a given delivered energy.",
    ),
    _row(
        "DomesticHotWaterSettings",
        "FuelType",
        S,
        ("Operations.DHW.FuelType",),
        "dhw.fuel",
        C,
        "Electricity, NaturalGas and Oil map to Electricity, NaturalGas and FuelOil; SBEM Propane "
        "and Steam are written as NaturalGas with a loss; Unset is a range problem.",
    ),
    # --- ZoneVentilation --------------------------------------------------------------------------
    _row(
        "ZoneVentilation",
        "Infiltration",
        S,
        ("Envelope.Infiltration.AirChangesPerHour", "Envelope.Infiltration.CalculationMethod"),
        "infiltration.ach",
        E,
        'Air changes per hour, with CalculationMethod = "AirChanges/Hour". Attic and basement '
        "infiltration are filled from it on reading (noted) and lost on writing when they differ.",
    ),
    _row(
        "ZoneVentilation",
        "IsInfiltrationOn",
        S,
        ("Envelope.Infiltration.IsOn",),
        "infiltration.ach",
        E,
        "Same switch.",
    ),
    _row(
        "ZoneVentilation",
        "IsNatVentOn",
        S,
        (f"{_VENTILATION}.Provider",),
        "vent.provider",
        C,
        "(mechanical, natural) switches map to Provider None, Natural, Mechanical or Both; conserves both switches.",
    ),
    _row(
        "ZoneVentilation",
        "NatVentSchedule",
        S,
        (f"{_VENTILATION}.Schedule",),
        "vent.natural_schedule",
        E,
        "The natural-ventilation schedule.",
    ),
    *_rows(
        "ZoneVentilation",
        (
            "Afn",
            "IsBuoyancyOn",
            "IsWindOn",
            "NatVentMaxRelHumidity",
            "NatVentMaxOutdoorAirTemp",
            "NatVentMinOutdoorAirTemp",
            "NatVentZoneTempSetpoint",
        ),
        S,
        "vent.natural_limits",
        U,
        f"Natural-ventilation limit or switch (SBEM fixes the limits). {_UP9}.",
        upstream="UP-9",
    ),
    *_rows(
        "ZoneVentilation",
        (
            "IsScheduledVentilationOn",
            "ScheduledVentilationAch",
            "ScheduledVentilationSchedule",
            "ScheduledVentilationSetpoint",
        ),
        S,
        "vent.scheduled",
        U,
        f"Scheduled ventilation. {_UP9}.",
        upstream="UP-9",
    ),
    # --- ZoneConditioning -------------------------------------------------------------------------
    _row(
        "ZoneConditioning",
        "HeatingSetpoint",
        S,
        (f"{_THERMOSTAT}.HeatingSetpoint", f"{_THERMOSTAT}.HeatingSchedule"),
        "thermostat.constant",
        C,
        "A constant heating schedule at the setpoint; on writing the schedule's maximum, setback "
        "hours reported. Conserves the occupied setpoint.",
    ),
    _row(
        "ZoneConditioning",
        "CoolingSetpoint",
        S,
        (f"{_THERMOSTAT}.CoolingSetpoint", f"{_THERMOSTAT}.CoolingSchedule"),
        "thermostat.constant",
        C,
        "A constant cooling schedule at the setpoint; on writing the schedule's minimum, setback "
        "hours reported. Conserves the occupied setpoint.",
    ),
    _row(
        "ZoneConditioning",
        "IsHeatingOn",
        S,
        (f"{_SYSTEMS}.Heating",),
        "conditioning.switches",
        C,
        "False gives no heating system (Heating = None), and back.",
    ),
    _row(
        "ZoneConditioning",
        "IsCoolingOn",
        S,
        (f"{_SYSTEMS}.Cooling",),
        "conditioning.switches",
        C,
        "False gives no cooling system (Cooling = None), and back.",
    ),
    *(
        _row(
            "ZoneConditioning",
            key,
            S,
            (f"{_SYSTEMS}.{system}.SystemCOP", f"{_SYSTEMS}.{system}.DistributionCOP"),
            "cop.system",
            C,
            "SystemCOP = COP with DistributionCOP = 1; inverse COP = SystemCOP x DistributionCOP. "
            "Conserves consumed energy for a given delivered energy.",
        )
        for key, system in (("HeatingCoeffOfPerf", "Heating"), ("CoolingCoeffOfPerf", "Cooling"))
    ),
    *(
        _row(
            "ZoneConditioning",
            key,
            S,
            (f"{_SYSTEMS}.{system}.Fuel",),
            "fuel.system",
            C,
            "By data-model.md's fuel table; fuels SBEM merges (fuel oils, other fuels) or lacks "
            "(district heating) are reported.",
        )
        for key, system in (("HeatingFuelType", "Heating"), ("CoolingFuelType", "Cooling"))
    ),
    _row(
        "ZoneConditioning",
        "IsMechVentOn",
        S,
        (f"{_VENTILATION}.Provider",),
        "vent.provider",
        C,
        "(mechanical, natural) switches map to Provider None, Natural, Mechanical or Both; conserves both switches.",
    ),
    _row(
        "ZoneConditioning",
        "MinFreshAirPerArea",
        S,
        (f"{_VENTILATION}.FreshAirPerFloorArea",),
        "conditioning.fresh_air",
        E,
        "Same quantity (m3/s per m2); above SBEM's cap it is a range problem.",
    ),
    _row(
        "ZoneConditioning",
        "MinFreshAirPerPerson",
        S,
        (f"{_VENTILATION}.FreshAirPerPerson",),
        "conditioning.fresh_air",
        E,
        "Same quantity (m3/s per person). SBEM's demand control (DCV) has no UMI field: lost on writing unless NoDCV.",
    ),
    _row(
        "ZoneConditioning",
        "EconomizerType",
        S,
        (f"{_VENTILATION}.Economizer",),
        "conditioning.economizer",
        E,
        "Maps by name.",
    ),
    _row(
        "ZoneConditioning",
        "HeatRecoveryType",
        S,
        (f"{_VENTILATION}.HRV",),
        "conditioning.heat_recovery",
        E,
        "Maps by name.",
    ),
    *_rows(
        "ZoneConditioning",
        ("HeatRecoveryEfficiencyLatent", "HeatRecoveryEfficiencySensible"),
        S,
        "conditioning.heat_recovery_efficiency",
        U,
        "Heat-recovery effectiveness; SBEM fixes it by HRV type. UP-2 adds it.",
        upstream="UP-2",
    ),
    *_rows(
        "ZoneConditioning",
        ("HeatingSchedule", "CoolingSchedule"),
        S,
        "conditioning.availability",
        U,
        f"Heating or cooling availability schedule; lost unless every value is 1. {_UP9}.",
        upstream="UP-9",
    ),
    _row(
        "ZoneConditioning",
        "MechVentSchedule",
        S,
        (),
        "conditioning.mech_vent_schedule",
        U,
        f"Mechanical outdoor-air schedule. {_UP9}.",
        upstream="UP-9",
    ),
    *_rows(
        "ZoneConditioning",
        (
            "HeatingLimitType",
            "CoolingLimitType",
            "MaxHeatFlow",
            "MaxCoolFlow",
            "MaxHeatingCapacity",
            "MaxCoolingCapacity",
        ),
        S,
        "conditioning.limits",
        U,
        f"Ideal-loads limit (SBEM always autosizes). {_UP9}.",
        upstream="UP-9",
    ),
    # --- ZoneLoads --------------------------------------------------------------------------------
    _row(
        "ZoneLoads",
        "PeopleDensity",
        S,
        (f"{_SPACE_USE}.Occupancy.PeopleDensity",),
        "loads.people",
        E,
        "Same quantity (people/m2). SBEM's MetabolicRate has no UMI field: 1.2 met on reading "
        "(noted), lost on writing when different.",
    ),
    _row(
        "ZoneLoads",
        "OccupancySchedule",
        S,
        (f"{_SPACE_USE}.Occupancy.Schedule",),
        "loads.people",
        E,
        "The occupancy schedule.",
    ),
    _row("ZoneLoads", "IsPeopleOn", S, (f"{_SPACE_USE}.Occupancy.IsOn",), "loads.people", E, "Same switch."),
    _row(
        "ZoneLoads",
        "LightingPowerDensity",
        S,
        (f"{_SPACE_USE}.Lighting.PowerDensity",),
        "loads.lighting",
        E,
        "Same quantity (W/m2).",
    ),
    _row(
        "ZoneLoads",
        "LightsAvailabilitySchedule",
        S,
        (f"{_SPACE_USE}.Lighting.Schedule",),
        "loads.lighting",
        E,
        "The lighting schedule.",
    ),
    _row("ZoneLoads", "IsLightingOn", S, (f"{_SPACE_USE}.Lighting.IsOn",), "loads.lighting", E, "Same switch."),
    _row(
        "ZoneLoads",
        "DimmingType",
        S,
        (f"{_SPACE_USE}.Lighting.DimmingType",),
        "loads.lighting",
        E,
        "Maps by name.",
    ),
    _row(
        "ZoneLoads",
        "EquipmentPowerDensity",
        S,
        (f"{_SPACE_USE}.Equipment.PowerDensity",),
        "loads.equipment",
        E,
        "Same quantity (W/m2).",
    ),
    _row(
        "ZoneLoads",
        "EquipmentAvailabilitySchedule",
        S,
        (f"{_SPACE_USE}.Equipment.Schedule",),
        "loads.equipment",
        E,
        "The equipment schedule.",
    ),
    _row("ZoneLoads", "IsEquipmentOn", S, (f"{_SPACE_USE}.Equipment.IsOn",), "loads.equipment", E, "Same switch."),
    _row(
        "ZoneLoads",
        "IlluminanceTarget",
        S,
        (),
        "loads.daylighting",
        U,
        f"Daylighting illuminance target. {_UP9} (daylighting parameters).",
        upstream="UP-9",
    ),
    # --- ZoneDefinition ---------------------------------------------------------------------------
    _row(
        "ZoneDefinition",
        "Conditioning",
        S,
        ("Operations.HVAC", _THERMOSTAT),
        "building.zone_definition",
        E,
        "The zone's conditioning: its HVAC component and thermostat.",
    ),
    _row(
        "ZoneDefinition",
        "Constructions",
        S,
        (_ASSEMBLIES,),
        "building.zone_definition",
        E,
        "The zone's construction set: its envelope assemblies.",
    ),
    _row(
        "ZoneDefinition",
        "DomesticHotWater",
        S,
        ("Operations.DHW", f"{_SPACE_USE}.WaterUse"),
        "building.zone_definition",
        E,
        "The zone's hot-water settings: its DHW system and water use.",
    ),
    _row(
        "ZoneDefinition",
        "Loads",
        S,
        (_SPACE_USE,),
        "building.zone_definition",
        E,
        "The zone's loads: its space use.",
    ),
    _row(
        "ZoneDefinition",
        "Ventilation",
        S,
        ("Envelope.Infiltration", _VENTILATION),
        "building.zone_definition",
        E,
        "The zone's ventilation settings: infiltration and ventilation.",
    ),
    _row(
        "ZoneDefinition",
        "InternalMassConstruction",
        S,
        (f"{_ASSEMBLIES}.InternalMassAssembly",),
        "mass.internal",
        E,
        "The internal-mass construction; with an exposed area of 0 there is no internal mass (both or neither).",
    ),
    _row(
        "ZoneDefinition",
        "InternalMassExposedPerFloorArea",
        S,
        (f"{_ASSEMBLIES}.InternalMassExposedAreaPerArea",),
        "mass.internal",
        E,
        "Same quantity (m2 per m2 of floor); 0 means no internal mass.",
    ),
    *_rows(
        "ZoneDefinition",
        ("DaylightMeshResolution", "DaylightWorkplaneHeight"),
        S,
        "loads.daylighting",
        U,
        f"Daylighting parameter. {_UP9} (daylighting parameters).",
        upstream="UP-9",
    ),
    # --- WindowSettings ---------------------------------------------------------------------------
    _row(
        "WindowSettings",
        "Construction",
        S,
        ("Envelope.Window",),
        "window.placement",
        E,
        "Each group's window. On writing the perimeter window is used; a different core window is lost.",
    ),
    *_rows(
        "WindowSettings",
        (
            "AfnDischargeC",
            "AfnTempSetpoint",
            "AfnWindowAvailability",
            "IsShadingSystemOn",
            "IsVirtualPartition",
            "IsZoneMixingOn",
            "OperableArea",
            "ShadingSystemAvailabilitySchedule",
            "ShadingSystemSetpoint",
            "ShadingSystemTransmittance",
            "ShadingSystemType",
            "Type",
            "ZoneMixingAvailabilitySchedule",
            "ZoneMixingDeltaTemperature",
            "ZoneMixingFlowRate",
        ),
        S,
        "window.settings",
        U,
        f"Window operation, shading, zone mixing or airflow-network setting. {_UP9} (a "
        "window-settings component at building level).",
        upstream="UP-9",
    ),
    # --- BuildingTemplate -------------------------------------------------------------------------
    _row(
        "BuildingTemplate",
        "Core",
        S,
        ("archetype.Groups.Zone", "archetype.Groups.Exposure", "archetype.Groups.FloorAreaShare"),
        "building.groups",
        E,
        'The group "core" (Exposure "core"); floor-area shares unset, set by the geometry (R4).',
    ),
    _row(
        "BuildingTemplate",
        "Perimeter",
        S,
        ("archetype.Groups.Zone", "archetype.Groups.Exposure", "archetype.Groups.FloorAreaShare"),
        "building.groups",
        E,
        'The group "perimeter" (Exposure "perimeter"); floor-area shares unset, set by the geometry (R4).',
    ),
    _row(
        "BuildingTemplate",
        "Windows",
        S,
        ("Envelope.Window",),
        "window.placement",
        E,
        "The template's window settings: their construction becomes each group's window; the "
        "other settings are lost until UP-9.",
        upstream="UP-9",
    ),
    _row(
        "BuildingTemplate",
        "DefaultWindowToWallRatio",
        S,
        ("archetype.Geometry.WindowToWallRatio",),
        "wwr.uniform",
        C,
        "The same ratio on every orientation; on writing the facade-area-weighted mean, lost when "
        "orientations differ. Conserves window area for a given facade.",
    ),
    _row(
        "BuildingTemplate",
        "PartitionRatio",
        S,
        (),
        "building.partition_ratio",
        U,
        f"Partition area per floor area. {_UP9}.",
        upstream="UP-9",
    ),
    _row("BuildingTemplate", "Structure", L, (), "structure.upstream", U, _STRUCTURE_NOTE, upstream="UP-9"),
    _row(
        "BuildingTemplate",
        "Lifespan",
        L,
        (),
        "building.metadata",
        U,
        f"Building lifespan for the life-cycle module. {_UP9} (archetype-level metadata).",
        upstream="UP-9",
    ),
    *_rows(
        "BuildingTemplate",
        ("YearFrom", "YearTo", "Country", "ClimateZone", "Authors", "AuthorEmails", "Version"),
        D,
        "building.metadata",
        U,
        f"Descriptive field of the template. {_UP9} (archetype-level metadata).",
        upstream="UP-9",
    ),
)
"""One row per serialised Basilisk field, in Basilisk class order within each group."""

del S, L, D, E, C, U, N


RuleFunction = Callable[..., object]
"""A rule's conversion function; its signature belongs to the rule module that defines it."""

_F = TypeVar("_F", bound=RuleFunction)


@dataclass(frozen=True)
class Rule:
    """A registered conversion rule.

    Attributes:
        id: The rule identifier, as in `FieldMapping.rule`.
        to_sbem: The UMI to SBEM function, or `None`.
        to_umi: The SBEM to UMI function, or `None`.
    """

    id: str
    to_sbem: RuleFunction | None = None
    to_umi: RuleFunction | None = None

    @property
    def mappings(self) -> tuple[FieldMapping, ...]:
        """The rows of `CORRESPONDENCE` that this rule translates."""
        return mappings_for(self.id)


_REGISTRY: dict[str, Rule] = {}


def rule_ids() -> frozenset[str]:
    """Return the rule identifiers named in `CORRESPONDENCE`."""
    return frozenset(row.rule for row in CORRESPONDENCE)


def mappings_for(rule_id: str) -> tuple[FieldMapping, ...]:
    """Return the rows of `CORRESPONDENCE` translated by one rule, in table order."""
    return tuple(row for row in CORRESPONDENCE if row.rule == rule_id)


def mapping(umi_class: str, umi_key: str) -> FieldMapping:
    """Return the row of one UMI field.

    Args:
        umi_class: The Basilisk class that declares the field.
        umi_key: The field's JSON key.

    Raises:
        KeyError: The field is not in `CORRESPONDENCE`.
    """
    for row in CORRESPONDENCE:
        if row.umi_class == umi_class and row.umi_key == umi_key:
            return row
    raise KeyError(f"{umi_class}.{umi_key}")


def _same_function(a: RuleFunction, b: RuleFunction) -> bool:
    """Tell whether two functions are the same definition (true again after a module reload)."""
    return (getattr(a, "__module__", None), getattr(a, "__qualname__", None)) == (
        getattr(b, "__module__", None),
        getattr(b, "__qualname__", None),
    )


def _check_id(rule_id: str) -> None:
    """Refuse a rule identifier that `CORRESPONDENCE` does not name."""
    if rule_id not in rule_ids():
        msg = f"rule {rule_id!r} is not named by any row of CORRESPONDENCE"
        raise ValueError(msg)


def declare_rule(rule_id: str) -> Rule:
    """Register a rule that has no conversion function of its own.

    Use it for rules whose rows are copied or reported generically, for example an upstream gap
    reported as a loss. Declaring a rule that is already registered changes nothing.

    Args:
        rule_id: The rule identifier; a row of `CORRESPONDENCE` must name it.

    Returns:
        The registered rule.

    Raises:
        ValueError: No row names `rule_id`.
    """
    _check_id(rule_id)
    return _REGISTRY.setdefault(rule_id, Rule(rule_id))


def rule(rule_id: str, *, to: Literal["sbem", "umi"]) -> Callable[[_F], _F]:
    """Register the decorated function as one direction of a rule.

    Example:
        ```python
        @rule("dhw.per_person", to="sbem")
        def flow_per_person(flow_per_area: float, schedule_sum: float, people: float) -> float: ...


        @rule("dhw.per_person", to="umi")
        def flow_per_area(flow_per_person: float, schedule_sum: float, people: float) -> float: ...
        ```

    Args:
        rule_id: The rule identifier; a row of `CORRESPONDENCE` must name it.
        to: `"sbem"` for the UMI to SBEM function, `"umi"` for the SBEM to UMI function.

    Returns:
        A decorator that registers the function and returns it unchanged.

    Raises:
        ValueError: No row names `rule_id`, or another function is already registered for that
            rule and direction.
    """
    _check_id(rule_id)

    def register(function: _F) -> _F:
        current = _REGISTRY.get(rule_id, Rule(rule_id))
        existing = current.to_sbem if to == "sbem" else current.to_umi
        if existing is not None and not _same_function(existing, function):
            msg = f"rule {rule_id!r} already has a to_{to} function: {existing.__qualname__}"
            raise ValueError(msg)
        if to == "sbem":
            _REGISTRY[rule_id] = Rule(rule_id, function, current.to_umi)
        else:
            _REGISTRY[rule_id] = Rule(rule_id, current.to_sbem, function)
        return function

    return register


def registered_rules() -> Mapping[str, Rule]:
    """Return every registered rule by identifier, after importing `archetypal.umi.rules`.

    Returns:
        A read-only view of the registry.
    """
    importlib.import_module("archetypal.umi.rules")
    return MappingProxyType(_REGISTRY)


def get_rule(rule_id: str) -> Rule:
    """Return one registered rule.

    Raises:
        KeyError: No rule is registered under `rule_id`.
    """
    return registered_rules()[rule_id]
