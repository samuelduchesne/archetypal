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
_LAYERED = "GlazingConstructionLayeredComponent"
_GLASS = "GlazingMaterialComponent"
_GAS = "GasMaterialComponent"
_STRUCTURE = "archetype.Structure"
_ADVANCED = f"{_STRUCTURE}.AdvancedModel"
_SYSTEMS_OF_STRUCTURE = f"{_ADVANCED}.ConstructionSystems"
_WINDOW_SETTINGS = "Envelope.WindowSettings"
_METADATA_HOLDERS = (
    "archetype",
    _MAT,
    _GLASS,
    _GAS,
    "ConstructionAssemblyComponent",
    _WINDOW,
    _LAYERED,
    "ZoneOperationsComponent",
    "ZoneSpaceUseComponent",
    "ZoneHVACComponent",
    "DHWComponent",
    "InfiltrationComponent",
    "EnvelopeAssemblyComponent",
    "WindowSettingsComponent",
    _STRUCTURE,
)
_SCHEDULE_HOLDERS = ("DayComponent", "WeekComponent", "YearComponent")


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


_STRUCTURE_NOTE = (
    "Structural model for UMI's life-cycle module: the archetype's StructureComponent (UP-9), field by field."
)
_UP9_NOT_ADDED = (
    "UP-9 does not add it: a shoebox has no interior windows and the builder models no airflow network, so it "
    "is lost on reading unless at Basilisk's default, which writing gives"
)

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
            f"{_GLASS}.Name",
            f"{_GAS}.Name",
            "ConstructionAssemblyComponent.Name",
            f"{_WINDOW}.Name",
            f"{_LAYERED}.Name",
            f"{_WINDOW_SETTINGS}.Name",
            f"{_STRUCTURE}.Name",
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
        "The receiving component's Category (a template's: the archetype's, UP-9). Basilisk fixes the "
        "category of schedules and gas materials: see their rows.",
    ),
    _row(
        "LibraryComponent",
        "Comments",
        D,
        tuple(f"{holder}.Comment" for holder in (*_METADATA_HOLDERS, *_SCHEDULE_HOLDERS)),
        "names.metadata",
        E,
        "The receiving component's Comment (a template's and a schedule's included, UP-9).",
    ),
    _row(
        "LibraryComponent",
        "DataSource",
        D,
        tuple(f"{holder}.DataSource" for holder in (*_METADATA_HOLDERS, *_SCHEDULE_HOLDERS)),
        "names.metadata",
        E,
        "The receiving component's DataSource (a template's and a schedule's included, UP-9).",
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
        (f"{_MAT}.Conductivity", f"{_GLASS}.Conductivity"),
        "material.properties",
        E,
        "Same quantity (W/m-K). SBEM gases have none (EnergyPlus knows each gas's): lost there unless 0.",
    ),
    _row(
        "MaterialBase",
        "Density",
        S,
        (f"{_MAT}.Density", f"{_GLASS}.Density"),
        "material.properties",
        E,
        "Same quantity (kg/m3). SBEM gases have none: lost there unless 0.",
    ),
    _row(
        "MaterialBase",
        "Cost",
        L,
        (f"{_MAT}.Cost", f"{_MAT}.RateUnit", f"{_GLASS}.Cost", f"{_GLASS}.RateUnit", f"{_GAS}.Cost"),
        "material.cost_per_m3",
        C,
        'Cost per m3, with RateUnit = "m3" (glazing: "kg", cost / density); conserves cost per unit volume. '
        "SBEM gases have no density: their cost is lost unless 0.",
    ),
    _row(
        "MaterialBase",
        "EmbodiedCarbon",
        L,
        (f"{_MAT}.EmbodiedCarbon", f"{_MAT}.RateUnit", f"{_GLASS}.EmbodiedCarbon", f"{_GAS}.EmbodiedCarbon"),
        "material.carbon_per_m3",
        C,
        "C_m3 = C_kg x density, inverse C_kg = C_m3 / density (refused for density 0); conserves "
        'embodied carbon per unit volume. Glazing and gas materials keep it per kg (RateUnit = "kg").',
    ),
    *(
        _row(
            "MaterialBase",
            key,
            L,
            (f"{_MAT}.{key}", f"{_GLASS}.{key}", f"{_GAS}.{key}"),
            "material.environmental",
            C,
            "The material's life-cycle field (UP-9), per unit of RateUnit like EmbodiedCarbon: per m3 = per kg x "
            'density for opaque materials (lost for density 0), per kg (RateUnit = "kg") for glazing and gas.',
        )
        for key in ("EmbodiedEnergy", "TransportCarbon", "TransportEnergy")
    ),
    *(
        _row(
            "MaterialBase",
            key,
            L,
            (f"{_MAT}.{key}", f"{_GLASS}.{key}", f"{_GAS}.{key}"),
            "material.environmental",
            E,
            "The material's life-cycle field (UP-9); same quantity.",
        )
        for key in ("SubstitutionRatePattern", "SubstitutionTimestep", "TransportDistance")
    ),
    # --- OpaqueMaterial ---------------------------------------------------------------------------
    *(
        _row(
            "OpaqueMaterial",
            key,
            L,
            (f"{_MAT}.{key}",),
            "material.environmental",
            E,
            "Structural or hygrothermal property of the material (UP-9), used by UMI's life-cycle module only.",
        )
        for key in ("DesignStrength", "ModulusOfElasticity", "MoistureDiffusionResistance")
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
    *(
        _row(
            "GlazingMaterial",
            key,
            S,
            (f"{_GLASS}.{key}",),
            "window.layers",
            E,
            "Same property of the pane's GlazingMaterialComponent (UP-9's layered windows). A simple SBEM "
            "window is written as one equivalent layer (approximate).",
        )
        for key in (
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
        )
    ),
    _row(
        "GasMaterial",
        "Category",
        D,
        (f"{_GAS}.Category",),
        "window.layers",
        E,
        'Basilisk fixes it to "Gases": read as an unset category, written as "Gases".',
    ),
    _row(
        "GasMaterial",
        "Type",
        S,
        (f"{_GAS}.GasType",),
        "window.layers",
        E,
        "The cavity's gas (Air, Argon, Krypton, Xenon), from Type or else the material's name; another gas "
        "gives simple glazing (approximate, as for WindowConstruction.Layers).",
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
    *(
        _row(
            "ConstructionBase",
            key,
            L,
            ("ConstructionAssemblyComponent." + key, f"{_LAYERED}.{key}", f"{_STRUCTURE}.{key}"),
            "construction.environmental",
            E,
            "The assembly's life-cycle field (UP-9), per m2 of assembly; same quantity.",
        )
        for key in ("AssemblyCarbon", "AssemblyCost", "AssemblyEnergy", "DisassemblyCarbon", "DisassemblyEnergy")
    ),
    _row(
        "WindowConstruction",
        "Layers",
        S,
        (
            f"{_LAYERED}.Layers",
            "GlazingLayerComponent.Thickness",
            "GlazingLayerComponent.GlazingMaterial",
            "GasLayerComponent.Thickness",
            "GasLayerComponent.GasMaterial",
        ),
        "window.layers",
        E,
        "The panes and cavities, outside first, as UP-9's layered window. Layers the fork cannot hold (more "
        "than 4 panes, panes and gases not alternating, an unknown gas) give simple glazing whose U, SHGC "
        "and VT idfkit.thermal computes (approximate); a simple SBEM window is written as the one glazing "
        "layer EnergyPlus's simple window model derives from it (approximate, a bridge until UP-10).",
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
    *(
        _row(
            "ZoneConstructions",
            key,
            S,
            (f"{_ASSEMBLIES}.{key}",),
            "construction.adiabatic",
            E,
            "The same adiabatic flag of the envelope assemblies (UP-9).",
        )
        for key in (
            "IsFacadeAdiabatic",
            "IsGroundAdiabatic",
            "IsPartitionAdiabatic",
            "IsRoofAdiabatic",
            "IsSlabAdiabatic",
        )
    ),
    # --- Structure (life cycle) -------------------------------------------------------------------
    *(
        _row("StructureInformation", key, L, (f"{_STRUCTURE}.{key}",), "structure.component", E, _STRUCTURE_NOTE)
        for key in ("AdvancedModel", "MassRatios", "UseAdvancedModel")
    ),
    *(
        _row("MassRatios", key, L, (f"{_STRUCTURE}.MassRatios.{key}",), "structure.component", E, _STRUCTURE_NOTE)
        for key in ("HighLoadRatio", "NormalRatio")
    ),
    _row(
        "MassRatios",
        "Material",
        L,
        (f"{_STRUCTURE}.MassRatios.Material",),
        "structure.component",
        C,
        f"{_STRUCTURE_NOTE} The opaque material, translated by the material rules.",
    ),
    *(
        _row("AdvancedStructuralModel", key, L, (f"{_ADVANCED}.{key}",), "structure.component", E, _STRUCTURE_NOTE)
        for key in ("ColumnWallSpacing", "ConstructionSystems", "FoundationSoilSettings", "LoadingSettings")
    ),
    *(
        _row(
            "ColumnWallSpacingSettings",
            key,
            L,
            (f"{_ADVANCED}.ColumnWallSpacing.{key}",),
            "structure.component",
            E,
            _STRUCTURE_NOTE,
        )
        for key in ("PrimarySpan", "SecondarySpan")
    ),
    _row(
        "ConstructionSystem",
        "Material",
        L,
        tuple(
            f"{_SYSTEMS_OF_STRUCTURE}.{slot}.Material"
            for slot in ("Beams", "Columns", "Floors", "Foundations", "LateralSystem")
        ),
        "structure.component",
        C,
        f"{_STRUCTURE_NOTE} The opaque material, translated by the material rules.",
    ),
    _row(
        "ConstructionSystem",
        "ConstructionSystemType",
        L,
        tuple(
            f"{_SYSTEMS_OF_STRUCTURE}.{slot}.ConstructionSystemType"
            for slot in ("Beams", "Columns", "Floors", "Foundations", "LateralSystem")
        ),
        "structure.component",
        E,
        f"{_STRUCTURE_NOTE} Types map by name.",
    ),
    *(
        _row(
            "ConstructionSystemSettings",
            key,
            L,
            (f"{_SYSTEMS_OF_STRUCTURE}.{key}",),
            "structure.component",
            E,
            _STRUCTURE_NOTE,
        )
        for key in ("Beams", "Columns", "Floors", "Foundations", "LateralSystem")
    ),
    *(
        _row(
            "FoundationSoilSettings",
            key,
            L,
            (f"{_ADVANCED}.FoundationSoilSettings.{key}",),
            "structure.component",
            E,
            _STRUCTURE_NOTE,
        )
        for key in ("FoundationSoilPreset", "FoundationSoilValue")
    ),
    *(
        _row(
            "LoadingSettings",
            key,
            L,
            (f"{_ADVANCED}.LoadingSettings.{key}",),
            "structure.component",
            E,
            _STRUCTURE_NOTE,
        )
        for key in ("LiveLoadingPreset", "LiveLoadingValue")
    ),
    # --- Schedules --------------------------------------------------------------------------------
    *(
        _row(
            cls,
            "Category",
            D,
            (f"{cls.replace('Schedule', 'Component')}.Category",),
            "schedule.metadata",
            E,
            f'Basilisk fixes it to "{cls.removesuffix("Schedule")}": read as an unset category (UP-9\'s schedule '
            "metadata), written as the fixed one; another SBEM category is lost on writing.",
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
        "The seven days, Monday first. UMI weeks have no holiday or design-day slots: reading leaves "
        "SBEM's (UP-2) unset; writing loses a slot only when it differs from the day UMI uses instead, Sunday "
        "on holidays and Monday on design days.",
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
    _row(
        "ZoneVentilation",
        "Afn",
        S,
        (),
        "vent.natural_limits",
        U,
        f"Airflow-network switch. {_UP9_NOT_ADDED}.",
        upstream="UP-9",
    ),
    *(
        _row(
            "ZoneVentilation",
            key,
            S,
            (f"{_VENTILATION}.{key}",),
            "vent.natural_limits",
            E,
            "The same natural-ventilation limit or switch (UP-9). A minimum outdoor temperature not below the "
            "maximum, which SBEM refuses, is lost and SBEM's band kept.",
        )
        for key in (
            "IsBuoyancyOn",
            "IsWindOn",
            "NatVentMaxRelHumidity",
            "NatVentMaxOutdoorAirTemp",
            "NatVentMinOutdoorAirTemp",
            "NatVentZoneTempSetpoint",
        )
    ),
    *(
        _row(
            "ZoneVentilation",
            key,
            S,
            (f"{_VENTILATION}.{key}",),
            "vent.scheduled",
            E,
            "The same scheduled-ventilation field (UP-9). An always-on schedule is SBEM's None (constant); "
            "a Temperature schedule, which SBEM refuses, is lost.",
        )
        for key in (
            "IsScheduledVentilationOn",
            "ScheduledVentilationAch",
            "ScheduledVentilationSchedule",
            "ScheduledVentilationSetpoint",
        )
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
    *(
        _row(
            "ZoneConditioning",
            f"HeatRecoveryEfficiency{kind}",
            S,
            (f"{_VENTILATION}.{kind}HeatRecoveryEffectiveness",),
            "conditioning.heat_recovery_efficiency",
            E,
            f"{kind} effectiveness at 100% airflow (UP-2). A value outside [0, 1] is lost and SBEM's assumed "
            "constant kept; SBEM's None (the assumed constant) is written as that constant.",
        )
        for kind in ("Latent", "Sensible")
    ),
    *(
        _row(
            "ZoneConditioning",
            key,
            S,
            (f"{_SYSTEMS}.{key.replace('Schedule', 'AvailabilitySchedule')}",),
            "conditioning.availability",
            E,
            "The heating or cooling availability schedule (UP-9). An always-on schedule is SBEM's None "
            "(always available); a schedule without Fraction limits, which SBEM refuses, is lost.",
        )
        for key in ("HeatingSchedule", "CoolingSchedule")
    ),
    _row(
        "ZoneConditioning",
        "MechVentSchedule",
        S,
        (f"{_VENTILATION}.MechVentSchedule",),
        "conditioning.mech_vent_schedule",
        E,
        "The mechanical outdoor-air schedule (UP-9). An always-on schedule is SBEM's None (constant); a "
        "schedule without Fraction limits, which SBEM refuses, is lost.",
    ),
    *(
        _row(
            "ZoneConditioning",
            key,
            S,
            (f"{_SYSTEMS}.{key}",),
            "conditioning.limits",
            E,
            "The same ideal-loads limit type (UP-9). On writing, a flow or capacity it names that SBEM autosizes "
            "(None) has no UMI value: it is dropped from the type, and lost.",
        )
        for key in ("HeatingLimitType", "CoolingLimitType")
    ),
    *(
        _row(
            "ZoneConditioning",
            key,
            S,
            (f"{_SYSTEMS}.{target}",),
            "conditioning.limits",
            E,
            f"Same quantity per floor area ({unit}, UP-9); SBEM's None (autosized) is written as Basilisk's default.",
        )
        for key, target, unit in (
            ("MaxHeatFlow", "MaxHeatingFlowPerFloorArea", "m3/s-m2"),
            ("MaxCoolFlow", "MaxCoolingFlowPerFloorArea", "m3/s-m2"),
            ("MaxHeatingCapacity", "MaxHeatingCapacityPerFloorArea", "W/m2"),
            ("MaxCoolingCapacity", "MaxCoolingCapacityPerFloorArea", "W/m2"),
        )
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
        (f"{_SPACE_USE}.Lighting.IlluminanceTarget",),
        "loads.daylighting",
        E,
        "Same quantity (lux, UP-9's daylighting); a target of 0 or less, which SBEM refuses, is lost.",
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
    *(
        _row(
            "ZoneDefinition",
            key,
            S,
            (f"{_SPACE_USE}.Lighting.{key}",),
            "loads.daylighting",
            E,
            "Same quantity (m, UP-9's daylighting), held by the zone's lighting. SBEM's mesh resolution None "
            "(no illuminance map) is written as Basilisk's default.",
        )
        for key in ("DaylightMeshResolution", "DaylightWorkplaneHeight")
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
    *(
        _row(
            "WindowSettings",
            key,
            S,
            (f"{_WINDOW_SETTINGS}.{key}",),
            "window.settings",
            E,
            "The same field of each group's WindowSettingsComponent (UP-9). On writing the perimeter group's "
            "settings are used; different settings of another group are lost. An always-on availability "
            "schedule is SBEM's None.",
        )
        for key in (
            "IsShadingSystemOn",
            "OperableArea",
            "ShadingSystemAvailabilitySchedule",
            "ShadingSystemSetpoint",
            "ShadingSystemTransmittance",
            "ShadingSystemType",
        )
    ),
    *_rows(
        "WindowSettings",
        (
            "AfnDischargeC",
            "AfnTempSetpoint",
            "AfnWindowAvailability",
            "IsVirtualPartition",
            "IsZoneMixingOn",
            "Type",
            "ZoneMixingAvailabilitySchedule",
            "ZoneMixingDeltaTemperature",
            "ZoneMixingFlowRate",
        ),
        S,
        "window.settings",
        U,
        f"Interior-window, zone-mixing or airflow-network setting. {_UP9_NOT_ADDED}.",
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
        "The template's window settings: their construction becomes each group's window, the other "
        "settings each group's WindowSettings (window.settings).",
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
        (f"{_ASSEMBLIES}.PartitionAreaPerFloorArea",),
        "building.partition_ratio",
        C,
        "Partition wall area (one face) per floor area; SBEM's internal partitions (UP-9) count both faces, "
        "as EnergyPlus internal mass does: A = 2 x ratio in every group. Conserves the partition wall area. "
        "On writing the perimeter group's is used; a different one of another group is lost.",
    ),
    _row("BuildingTemplate", "Structure", L, (_STRUCTURE,), "structure.component", E, _STRUCTURE_NOTE),
    _row(
        "BuildingTemplate",
        "Lifespan",
        L,
        ("archetype.Lifespan",),
        "building.metadata",
        E,
        "Building lifespan for the life-cycle module (years; UP-9's archetype metadata).",
    ),
    *(
        _row(
            "BuildingTemplate",
            key,
            D,
            (f"archetype.{key}",),
            "building.metadata",
            E,
            "The same descriptive field of the archetype (UP-9's archetype metadata). A YearFrom after "
            "YearTo, which SBEM refuses, loses YearTo.",
        )
        for key in ("YearFrom", "YearTo", "Country", "ClimateZone", "Authors", "AuthorEmails", "Version")
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
