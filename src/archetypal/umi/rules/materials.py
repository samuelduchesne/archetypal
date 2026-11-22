"""Rules for materials, layers, constructions and construction sets (spec 003, research R11).

UMI to SBEM (reading):

- an opaque material becomes a `ConstructionMaterialComponent`: same properties,
  `ThermalEmittance` as `ThermalAbsorptance`, `Type` from `Category` when it names one of SBEM's
  12 types (else `Other`, noted), `TemperatureCoefficientThermalConductivity` set to 0 (noted),
  cost and embodied carbon per m³ (`RateUnit = "m3"`, `material.carbon_per_m3`);
- an opaque construction becomes a `ConstructionAssemblyComponent` whose layers keep their order
  (outside first, `LayerOrder` from 0) and thickness;
- a construction set fills SBEM's five slots of the same name, and SBEM's five other slots from
  their nearest UMI counterpart (`FILLED_SLOTS`), each noted.

SBEM to UMI (writing) inverts each rule and lists as lost what UMI cannot hold: a filled slot that
differs from the one it would be filled from, a non-zero temperature coefficient, a material
type its category does not name, a vegetation layer, and cost or carbon given per m² or m (or
through a density of 0).

Life-cycle fields (UP-9): a material's embodied energy and transport carbon and energy are per
unit of `RateUnit`, like its embodied carbon, so per m³ = per kg x density (`material.environmental`);
its transport distance, substitution pattern and timestep and an opaque material's structural and
hygrothermal properties are copied. An assembly's assembly and disassembly fields are copied
(`construction.environmental`), and so are a construction set's adiabatic flags
(`construction.adiabatic`). A negative value, which SBEM refuses, is lost.

Every function takes the `subject` (template or archetype), the `location` of the component
translated (a JSON pointer when reading, an SBEM field path when writing) and a `Findings` that
collects losses and notes (`archetypal.umi.report.Findings`).
"""

from __future__ import annotations

from types import MappingProxyType
from typing import TYPE_CHECKING, cast, get_args

from epinterface.sbem.components.envelope import (
    ConstructionAssemblyComponent,
    ConstructionLayerComponent,
    EnvelopeAssemblyComponent,
)
from epinterface.sbem.components.materials import (
    ConstructionMaterialComponent,
    ConstructionMaterialType,
    MaterialRoughness,
)

from archetypal.errors import Problem
from archetypal.umi._format import (
    ConstructionBase,
    MaterialBase,
    MaterialLayer,
    OpaqueConstruction,
    OpaqueMaterial,
    ZoneConstructions,
)
from archetypal.umi.correspondence import rule
from archetypal.umi.report import LossKind

if TYPE_CHECKING:
    from collections.abc import Mapping

    from epinterface.sbem.components.materials import (
        AssemblyLifeCycleMixin,
        ConstructionComponentSurfaceType,
        MaterialLifeCycleMixin,
    )

    from archetypal.umi.report import Findings


__all__ = [
    "ADIABATIC_FLAGS",
    "ASSEMBLY_LIFE_CYCLE",
    "FILLED_SLOTS",
    "MATERIAL_LIFE_CYCLE",
    "ROUGHNESS",
    "SBEM_MATERIAL_TYPES",
    "SET_SLOTS",
    "SLOT_SURFACE_TYPES",
    "adiabatic_to_sbem",
    "adiabatic_to_umi",
    "assemblies_to_sbem",
    "assemblies_to_umi",
    "assembly_life_cycle_to_sbem",
    "assembly_life_cycle_to_umi",
    "carbon_per_kg",
    "carbon_per_m3",
    "construction_to_sbem",
    "construction_to_umi",
    "cost_from_sbem",
    "cost_per_m3",
    "life_cycle_to_sbem",
    "life_cycle_to_umi",
    "material_problems",
    "material_to_sbem",
    "material_to_umi",
]

ROUGHNESS: tuple[MaterialRoughness, ...] = get_args(MaterialRoughness)
"""EnergyPlus's six roughness keywords."""

SBEM_MATERIAL_TYPES: tuple[ConstructionMaterialType, ...] = get_args(ConstructionMaterialType)
"""SBEM's 12 material types."""

SET_SLOTS: Mapping[str, str] = MappingProxyType({
    "Facade": "FacadeAssembly",
    "Roof": "FlatRoofAssembly",
    "Slab": "FloorCeilingAssembly",
    "Ground": "GroundSlabAssembly",
    "Partition": "PartitionAssembly",
})
"""The SBEM slot of each UMI construction-set slot."""

FILLED_SLOTS: Mapping[str, str] = MappingProxyType({
    "AtticRoofAssembly": "Roof",
    "AtticFloorAssembly": "Slab",
    "ExternalFloorAssembly": "Slab",
    "BasementCeilingAssembly": "Slab",
    "GroundWallAssembly": "Ground",
})
"""SBEM slots UMI lacks, and the UMI slot each is filled from on reading (research R11)."""

SLOT_SURFACE_TYPES: Mapping[str, ConstructionComponentSurfaceType] = MappingProxyType({
    "FacadeAssembly": "Facade",
    "FlatRoofAssembly": "FlatRoof",
    "FloorCeilingAssembly": "FloorCeiling",
    "GroundSlabAssembly": "GroundSlab",
    "PartitionAssembly": "Partition",
    "AtticRoofAssembly": "AtticRoof",
    "AtticFloorAssembly": "AtticFloor",
    "ExternalFloorAssembly": "ExternalFloor",
    "BasementCeilingAssembly": "BasementCeiling",
    "GroundWallAssembly": "GroundWall",
    "InternalMassAssembly": "InternalMass",
})
"""The surface type (`ConstructionAssemblyComponent.Type`) of the assembly in each SBEM slot."""

_UMI_SLOT_FIELDS: Mapping[str, str] = MappingProxyType({
    "Facade": "facade",
    "Roof": "roof",
    "Slab": "slab",
    "Ground": "ground",
    "Partition": "partition",
})

_ROUGHNESS_BY_LOWER: dict[str, MaterialRoughness] = {keyword.lower(): keyword for keyword in ROUGHNESS}
_TYPE_BY_LOWER: dict[str, ConstructionMaterialType] = {kind.lower(): kind for kind in SBEM_MATERIAL_TYPES}
_PER_VOLUME = "m3"
_PER_MASS = "kg"

MATERIAL_LIFE_CYCLE: Mapping[str, str] = MappingProxyType({
    "EmbodiedEnergy": "embodied_energy",
    "TransportCarbon": "transport_carbon",
    "TransportEnergy": "transport_energy",
    "TransportDistance": "transport_distance",
    "SubstitutionRatePattern": "substitution_rate_pattern",
    "SubstitutionTimestep": "substitution_timestep",
})
"""A material's life-cycle fields (UP-9): SBEM key → UMI field name; the keys are the same in both."""

_PER_UNIT: frozenset[str] = frozenset({"EmbodiedEnergy", "TransportCarbon", "TransportEnergy"})
_OPAQUE_LIFE_CYCLE: Mapping[str, str] = MappingProxyType({
    "MoistureDiffusionResistance": "moisture_diffusion_resistance",
    "DesignStrength": "design_strength",
    "ModulusOfElasticity": "modulus_of_elasticity",
})

ASSEMBLY_LIFE_CYCLE: Mapping[str, str] = MappingProxyType({
    "AssemblyCarbon": "assembly_carbon",
    "AssemblyCost": "assembly_cost",
    "AssemblyEnergy": "assembly_energy",
    "DisassemblyCarbon": "disassembly_carbon",
    "DisassemblyEnergy": "disassembly_energy",
})
"""An assembly's life-cycle fields (UP-9): SBEM key → UMI field name; the keys are the same in both."""

ADIABATIC_FLAGS: Mapping[str, str] = MappingProxyType({
    "IsFacadeAdiabatic": "is_facade_adiabatic",
    "IsGroundAdiabatic": "is_ground_adiabatic",
    "IsPartitionAdiabatic": "is_partition_adiabatic",
    "IsRoofAdiabatic": "is_roof_adiabatic",
    "IsSlabAdiabatic": "is_slab_adiabatic",
})
"""The adiabatic flags of a construction set (UP-9): key → UMI field name; SBEM uses the same keys."""


def _pointer(location: str, key: str) -> str:
    """Append a key to a JSON pointer."""
    return f"{location}/{key.replace('~', '~0').replace('/', '~1')}"


def _path(location: str, key: str) -> str:
    """Append a field to an SBEM field path."""
    return f"{location}.{key}" if location else key


# --- Environmental fields -----------------------------------------------------------------


@rule("material.carbon_per_m3", to="sbem")
def carbon_per_m3(carbon_per_kg: float, density: float) -> float:
    """Return embodied carbon per m³ from carbon per kg: `C_m3 = C_kg x density`.

    Args:
        carbon_per_kg: Embodied carbon, kg CO₂e/kg.
        density: Density, kg/m³.

    Returns:
        Embodied carbon, kg CO₂e/m³.
    """
    return carbon_per_kg * density


@rule("material.carbon_per_m3", to="umi")
def carbon_per_kg(carbon_per_m3: float, density: float) -> float:
    """Return embodied carbon per kg from carbon per m³: `C_kg = C_m3 / density`.

    Args:
        carbon_per_m3: Embodied carbon, kg CO₂e/m³.
        density: Density, kg/m³.

    Returns:
        Embodied carbon, kg CO₂e/kg; 0 when there is no carbon, whatever the density.

    Raises:
        ValueError: The density is 0 and the carbon is not, so carbon per kg is undefined.
    """
    if carbon_per_m3 == 0.0:
        return 0.0
    if density == 0.0:
        msg = f"embodied carbon of {carbon_per_m3!r} kg/m3 cannot be given per kg: the density is 0"
        raise ValueError(msg)
    return carbon_per_m3 / density


@rule("material.cost_per_m3", to="sbem")
def cost_per_m3(cost: float) -> float:
    """Return a UMI material's cost as SBEM's cost per m³ (`RateUnit = "m3"`): unchanged."""
    return cost


@rule("material.cost_per_m3", to="umi")
def cost_from_sbem(cost: float | None, rate_unit: str | None, density: float) -> float | None:
    """Return an SBEM material's cost per m³, as UMI holds it.

    Args:
        cost: SBEM's `Cost`, per `rate_unit`; `None` means no cost.
        rate_unit: SBEM's `RateUnit`; `None` is taken as per m³.
        density: Density, kg/m³, to convert a cost per kg.

    Returns:
        Cost per m³ (0 when there is no cost), or `None` when a cost cannot be given per m³:
        per m² or per m, which needs a thickness the material does not have, or per kg of a
        material of density 0.
    """
    if not cost:
        return 0.0
    if rate_unit in (None, _PER_VOLUME):
        return cost
    if rate_unit == _PER_MASS and density != 0.0:
        return cost * density
    return None


# --- Life-cycle fields (UP-9) ----------------------------------------------------------------


def _negative(value: object) -> bool:
    if isinstance(value, tuple):
        return any(_negative(item) for item in cast("tuple[object, ...]", value))
    return isinstance(value, (int, float)) and value < 0


@rule("material.environmental", to="sbem")
def life_cycle_to_sbem(
    material: MaterialBase, subject: str, location: str, findings: Findings, *, per_volume: bool = True
) -> dict[str, object]:
    """Return the SBEM life-cycle fields of a UMI material (UP-9).

    UMI gives embodied energy and transport carbon and energy per kg. With `per_volume` (opaque
    materials, `RateUnit = "m3"`) they are multiplied by the density, and lost for a material of
    density 0; otherwise (glazing and gas, `RateUnit = "kg"`) they are copied. The other fields
    are copied, and an opaque material's structural and hygrothermal properties too. A negative
    value, which SBEM refuses, is lost.

    Args:
        material: The UMI material.
        subject: The template being read.
        location: The material's JSON pointer.
        findings: Collects the losses.
        per_volume: Give per-unit quantities per m³ rather than per kg.

    Returns:
        The SBEM fields by name.
    """
    fields: dict[str, object] = {}
    names = dict(MATERIAL_LIFE_CYCLE)
    if isinstance(material, OpaqueMaterial):
        names.update(_OPAQUE_LIFE_CYCLE)
    for key, name in names.items():
        value: object = getattr(material, name)
        if value is None:
            continue
        if _negative(value):
            findings.lose(
                LossKind.LOST,
                subject,
                _pointer(location, key),
                cast("float", value) if not isinstance(value, tuple) else list(cast("tuple[float, ...]", value)),
                "material.environmental",
                f"SBEM's {key} cannot be negative.",
            )
            continue
        if key in _PER_UNIT and per_volume:
            number = cast("float", value)
            if material.density == 0.0 and number != 0.0:
                findings.lose(
                    LossKind.LOST,
                    subject,
                    _pointer(location, key),
                    number,
                    "material.environmental",
                    f"SBEM holds {key} per m3, and a material of density 0 has none per m3.",
                    replacement=0.0,
                )
            value = number * material.density
        fields[key] = list(cast("tuple[float, ...]", value)) if isinstance(value, tuple) else value
    return fields


@rule("material.environmental", to="umi")
def life_cycle_to_umi(
    component: MaterialLifeCycleMixin,
    rate_unit: str | None,
    density: float | None,
    subject: str,
    location: str,
    findings: Findings,
) -> dict[str, object]:
    """Return the UMI life-cycle fields of an SBEM material (UP-9), per kg.

    Unset fields take Basilisk's defaults. Per-unit quantities are divided by the density when
    `rate_unit` is per m³ (or unset), copied when it is per kg, and lost when it is per m² or m,
    which needs a thickness, or the density is 0.

    Args:
        component: The SBEM material (opaque, glazing or gas).
        rate_unit: Its `RateUnit`.
        density: Its density, kg/m³ (`None` for a gas).
        subject: The archetype being written.
        location: The material's SBEM field path.
        findings: Collects the losses.

    Returns:
        The UMI fields by Basilisk key.
    """
    fields: dict[str, object] = {}
    names = dict(MATERIAL_LIFE_CYCLE)
    if hasattr(component, "DesignStrength"):
        names.update(_OPAQUE_LIFE_CYCLE)
    for key in names:
        value: object = getattr(component, key)
        if value is None:
            continue
        if key in _PER_UNIT and rate_unit != _PER_MASS and value != 0.0:
            number = cast("float", value)
            if rate_unit not in (None, _PER_VOLUME) or (not density and number != 0.0):
                why = (
                    f"a {key} per {rate_unit} needs a thickness the material lacks"
                    if rate_unit not in (None, _PER_VOLUME)
                    else f"a {key} per m3 cannot be given per kg without a density"
                )
                findings.lose(
                    LossKind.LOST,
                    subject,
                    _path(location, key),
                    number,
                    "material.environmental",
                    f"UMI holds {key} per kg; {why}.",
                    replacement=0.0,
                )
                continue
            value = number / density if density else 0.0
        fields[key] = value
    return fields


@rule("construction.environmental", to="sbem")
def assembly_life_cycle_to_sbem(construction: ConstructionBase) -> dict[str, float]:
    """Return the SBEM life-cycle fields of a UMI construction or structure (UP-9): copied.

    Negative values, which SBEM refuses, are left out; `assembly_life_cycle_losses` lists them.
    """
    return {key: value for key, name in ASSEMBLY_LIFE_CYCLE.items() if (value := getattr(construction, name)) >= 0}


def assembly_life_cycle_losses(construction: ConstructionBase, subject: str, location: str, findings: Findings) -> None:
    """List the negative life-cycle fields of a UMI construction, which SBEM refuses, as lost."""
    for key, name in ASSEMBLY_LIFE_CYCLE.items():
        value: float = getattr(construction, name)
        if value < 0:
            findings.lose(
                LossKind.LOST,
                subject,
                _pointer(location, key),
                value,
                "construction.environmental",
                f"SBEM's {key} cannot be negative.",
            )


@rule("construction.environmental", to="umi")
def assembly_life_cycle_to_umi(component: AssemblyLifeCycleMixin) -> dict[str, float]:
    """Return the UMI life-cycle fields of an SBEM assembly (UP-9); unset fields are left to Basilisk's 0."""
    return {key: value for key in ASSEMBLY_LIFE_CYCLE if (value := getattr(component, key)) is not None}


@rule("construction.adiabatic", to="sbem")
def adiabatic_to_sbem(constructions: ZoneConstructions) -> dict[str, bool]:
    """Return SBEM's adiabatic flags of a UMI construction set (UP-9): copied."""
    return {key: getattr(constructions, name) for key, name in ADIABATIC_FLAGS.items()}


@rule("construction.adiabatic", to="umi")
def adiabatic_to_umi(envelope: EnvelopeAssemblyComponent) -> dict[str, bool]:
    """Return UMI's adiabatic flags of SBEM's envelope assemblies (UP-9): copied."""
    return {key: getattr(envelope, key) for key in ADIABATIC_FLAGS}


# --- Materials ----------------------------------------------------------------------------


def _roughness(value: str | None) -> MaterialRoughness | None:
    """Return the EnergyPlus keyword a roughness names (case-insensitive), or `None`."""
    return None if value is None else _ROUGHNESS_BY_LOWER.get(value.lower())


def material_problems(material: OpaqueMaterial, pointer: str, template: str | None) -> list[Problem]:
    """Return the range problems of an opaque material that this module's rules refuse.

    Args:
        material: The material.
        pointer: Its JSON pointer in the library.
        template: The building template affected, if any.

    Returns:
        A problem when `Roughness` is not one of EnergyPlus's six keywords; else nothing.
    """
    if _roughness(material.roughness) is not None:
        return []
    return [
        Problem(
            pointer=_pointer(pointer, "Roughness"),
            template=template,
            rule="range",
            message=f"Roughness {material.roughness!r} is not one of {', '.join(ROUGHNESS)}",
        )
    ]


@rule("material.properties", to="sbem")
def material_to_sbem(
    material: OpaqueMaterial, subject: str, location: str, findings: Findings
) -> ConstructionMaterialComponent:
    """Translate a UMI opaque material to an SBEM construction material.

    Args:
        material: The material.
        subject: The template being read.
        location: The material's JSON pointer.
        findings: Collects the notes (type, temperature coefficient) and losses (carbon of a
            material without density).

    Returns:
        The SBEM material.

    Raises:
        ValueError: `Roughness` is not one of the six keywords (`material_problems` reports it
            beforehand).
    """
    roughness = _roughness(material.roughness)
    if roughness is None:
        msg = f"{location}: Roughness {material.roughness!r} is not one of {', '.join(ROUGHNESS)}"
        raise ValueError(msg)
    kind = _TYPE_BY_LOWER.get(material.category.lower())
    if kind is None:
        kind = "Other"
        findings.assume(
            subject,
            _pointer(location, "Category"),
            material.category,
            "material.properties",
            f"SBEM's material Type is Other: Category {material.category!r} names none of SBEM's 12 types.",
        )
    findings.assume(
        subject,
        _pointer(location, "TemperatureCoefficientThermalConductivity"),
        0.0,
        "material.properties",
        "UMI has no TemperatureCoefficientThermalConductivity; SBEM's is set to 0 (constant conductivity).",
    )
    carbon = carbon_per_m3(material.embodied_carbon, material.density)
    if material.density == 0.0 and material.embodied_carbon != 0.0:
        findings.lose(
            LossKind.LOST,
            subject,
            _pointer(location, "EmbodiedCarbon"),
            material.embodied_carbon,
            "material.carbon_per_m3",
            "SBEM holds embodied carbon per m3, and a material of density 0 has none per m3.",
            replacement=0.0,
        )
    return ConstructionMaterialComponent(
        Name=material.name or "",
        Category=material.category,
        Comment=material.comments,
        DataSource=material.data_source,
        Conductivity=material.conductivity,
        Density=material.density,
        Roughness=roughness,
        SpecificHeat=material.specific_heat,
        ThermalAbsorptance=material.thermal_emittance,
        SolarAbsorptance=material.solar_absorptance,
        VisibleAbsorptance=material.visible_absorptance,
        TemperatureCoefficientThermalConductivity=0.0,
        Type=kind,
        Cost=cost_per_m3(material.cost),
        EmbodiedCarbon=carbon,
        RateUnit=_PER_VOLUME,
        **life_cycle_to_sbem(material, subject, location, findings),  # pyright: ignore[reportArgumentType]
    )


def _environmental_to_umi(
    component: ConstructionMaterialComponent, subject: str, location: str, findings: Findings
) -> tuple[float, float]:
    """Return UMI's cost and carbon per kg of an SBEM material, listing what cannot be converted."""
    cost = cost_from_sbem(component.Cost, component.RateUnit, component.Density)
    if cost is None:
        why = (
            "a cost per kg cannot be given per m3 without a density"
            if component.RateUnit == _PER_MASS
            else f"a cost per {component.RateUnit} needs a thickness the material lacks"
        )
        findings.lose(
            LossKind.LOST,
            subject,
            _path(location, "Cost"),
            component.Cost,
            "material.cost_per_m3",
            f"UMI holds cost per m3; {why}.",
            replacement=0.0,
        )
        cost = 0.0
    carbon = component.EmbodiedCarbon or 0.0
    if component.RateUnit == _PER_MASS or carbon == 0.0:
        return cost, carbon
    if component.RateUnit in (None, _PER_VOLUME) and component.Density != 0.0:
        return cost, carbon_per_kg(carbon, component.Density)
    why = (
        "a carbon per m3 cannot be given per kg without a density"
        if component.RateUnit in (None, _PER_VOLUME)
        else f"a carbon per {component.RateUnit} needs a thickness the material lacks"
    )
    findings.lose(
        LossKind.LOST,
        subject,
        _path(location, "EmbodiedCarbon"),
        carbon,
        "material.carbon_per_m3",
        f"UMI holds carbon per kg; {why}.",
        replacement=0.0,
    )
    return cost, 0.0


# SBEM fields that may be unset and that UMI always holds: writing fills them (noted).
_MATERIAL_FILLED: tuple[str, ...] = (
    "Category",
    "Cost",
    "RateUnit",
    "EmbodiedCarbon",
    "EmbodiedEnergy",
    "TransportCarbon",
    "TransportDistance",
    "TransportEnergy",
    "SubstitutionRatePattern",
    "SubstitutionTimestep",
    "MoistureDiffusionResistance",
)
_ASSEMBLY_FILLED: tuple[str, ...] = (
    "Category",
    "AssemblyCarbon",
    "AssemblyCost",
    "AssemblyEnergy",
    "DisassemblyCarbon",
    "DisassemblyEnergy",
)


@rule("material.properties", to="umi")
def material_to_umi(
    component: ConstructionMaterialComponent, subject: str, location: str, findings: Findings
) -> OpaqueMaterial:
    """Translate an SBEM construction material to a UMI opaque material.

    The UMI `Category` is SBEM's `Category`, or the material `Type` when the category is unset,
    so that reading the material back gives the same type.

    Args:
        component: The SBEM material.
        subject: The archetype being written.
        location: The material's SBEM field path.
        findings: Collects the losses: a non-zero temperature coefficient, a type its category
            does not name (or `Other` with a category that names a type), the material life
            (UP-9), cost or carbon per m² or m, and carbon per m³ or cost per kg of a material
            of density 0.

    Returns:
        The UMI material.
    """
    category = component.Category if component.Category is not None else component.Type
    read_back = _TYPE_BY_LOWER.get(category.lower(), "Other")
    if read_back != component.Type:
        findings.lose(
            LossKind.LOST,
            subject,
            _path(location, "Type"),
            component.Type,
            "material.properties",
            f"UMI has no material type; Category {category!r} does not name it, so it reads back as {read_back}.",
            replacement=read_back,
        )
    if component.TemperatureCoefficientThermalConductivity != 0.0:
        findings.lose(
            LossKind.LOST,
            subject,
            _path(location, "TemperatureCoefficientThermalConductivity"),
            component.TemperatureCoefficientThermalConductivity,
            "material.properties",
            "UMI materials have a constant conductivity.",
            replacement=0.0,
        )
    if component.Life is not None:
        findings.lose(
            LossKind.LOST,
            subject,
            _path(location, "Life"),
            component.Life,
            "material.environmental",
            "UMI materials have no life; their substitution timestep and pattern describe replacement.",
        )
    findings.unset(component, _MATERIAL_FILLED, subject, location, "material.environmental")
    cost, carbon = _environmental_to_umi(component, subject, location, findings)
    life_cycle = life_cycle_to_umi(component, component.RateUnit, component.Density, subject, location, findings)
    return OpaqueMaterial.model_validate({
        "Name": component.Name,
        "Category": category,
        "Comments": component.Comment,
        "DataSource": component.DataSource,
        "Conductivity": component.Conductivity,
        "Density": component.Density,
        "SpecificHeat": component.SpecificHeat,
        "Roughness": component.Roughness,
        "ThermalEmittance": component.ThermalAbsorptance,
        "SolarAbsorptance": component.SolarAbsorptance,
        "VisibleAbsorptance": component.VisibleAbsorptance,
        "Cost": cost,
        "EmbodiedCarbon": carbon,
        **life_cycle,
    })


# --- Constructions ------------------------------------------------------------------------


@rule("construction.layers", to="sbem")
def construction_to_sbem(
    construction: OpaqueConstruction,
    surface_type: ConstructionComponentSurfaceType,
    subject: str,
    location: str,
    findings: Findings,
) -> ConstructionAssemblyComponent:
    """Translate a UMI opaque construction to an SBEM assembly, layers in order, outside first.

    Args:
        construction: The construction.
        surface_type: Where SBEM uses the assembly (`Facade`, `FlatRoof`, …).
        subject: The template being read.
        location: The construction's JSON pointer.
        findings: Collects the materials' notes and losses.

    Returns:
        The assembly, named as the construction.

    Raises:
        ValueError: A layer has no material, or a material's roughness is not a keyword.
    """
    layers: list[ConstructionLayerComponent] = []
    for order, layer in enumerate(construction.layers):
        where = _pointer(_pointer(location, "Layers"), str(order))
        if layer.material is None:
            msg = f"{where}: the layer has no material"
            raise ValueError(msg)
        material = material_to_sbem(layer.material, subject, _pointer(where, "Material"), findings)
        layers.append(
            ConstructionLayerComponent(Thickness=layer.thickness, LayerOrder=order, ConstructionMaterial=material)
        )
    assembly_life_cycle_losses(construction, subject, location, findings)
    return ConstructionAssemblyComponent(
        Name=construction.name or "",
        Category=construction.category,
        Comment=construction.comments,
        DataSource=construction.data_source,
        Layers=layers,
        Type=surface_type,
        **assembly_life_cycle_to_sbem(construction),  # pyright: ignore[reportArgumentType]
    )


@rule("construction.layers", to="umi")
def construction_to_umi(
    assembly: ConstructionAssemblyComponent, subject: str, location: str, findings: Findings
) -> OpaqueConstruction:
    """Translate an SBEM assembly to a UMI opaque construction, layers sorted by `LayerOrder`.

    Args:
        assembly: The assembly.
        subject: The archetype being written.
        location: The assembly's SBEM field path.
        findings: Collects the losses: a vegetation layer, and the materials' losses.

    Returns:
        The construction.
    """
    if assembly.VegetationLayer is not None:
        findings.lose(
            LossKind.LOST,
            subject,
            _path(location, "VegetationLayer"),
            assembly.VegetationLayer,
            "construction.layers",
            "UMI constructions have no vegetation layer.",
        )
    layers = [
        MaterialLayer[OpaqueMaterial](
            Material=material_to_umi(
                layer.ConstructionMaterial, subject, _path(location, f"Layers.{index}.ConstructionMaterial"), findings
            ),
            Thickness=layer.Thickness,
        )
        for index, layer in enumerate(sorted(assembly.Layers, key=lambda layer: layer.LayerOrder))
    ]
    findings.unset(assembly, _ASSEMBLY_FILLED, subject, location, "construction.layers")
    return OpaqueConstruction.model_validate({
        "Name": assembly.Name,
        "Category": assembly.Category if assembly.Category is not None else "Uncategorized",
        "Comments": assembly.Comment,
        "DataSource": assembly.DataSource,
        "Layers": layers,
        **assembly_life_cycle_to_umi(assembly),
    })


# --- Construction sets --------------------------------------------------------------------


@rule("construction.sets", to="sbem")
def assemblies_to_sbem(
    constructions: ZoneConstructions,
    subject: str,
    location: str,
    findings: Findings,
    *,
    internal_mass: ConstructionAssemblyComponent | None = None,
    internal_mass_exposed: float | None = None,
    partition_area: float = 0.0,
) -> EnvelopeAssemblyComponent:
    """Translate a UMI construction set to SBEM's envelope assemblies.

    The five UMI slots fill the SBEM slots of the same name (`SET_SLOTS`); SBEM's five other
    slots are filled from their nearest UMI slot (`FILLED_SLOTS`), each noted. Internal mass
    comes from the zone, not the set (`mass.internal`), and is passed through.

    Args:
        constructions: The construction set.
        subject: The template being read.
        location: The set's JSON pointer.
        findings: Collects the notes and the materials' losses.
        internal_mass: The zone's internal-mass assembly, if any.
        internal_mass_exposed: Its exposed area per floor area.
        partition_area: The internal partitions' area per floor area (UP-9), from the
            template's `PartitionRatio` (`building.partition_ratio`).

    Returns:
        The envelope assemblies, named as the set.

    Raises:
        ValueError: A slot of the set is empty (validation reports it beforehand).
    """
    by_umi_slot: dict[str, OpaqueConstruction] = {}
    for umi_slot, attribute in _UMI_SLOT_FIELDS.items():
        construction = cast("OpaqueConstruction | None", getattr(constructions, attribute))
        if construction is None:
            msg = f"{location}: the construction set has no {umi_slot} construction"
            raise ValueError(msg)
        by_umi_slot[umi_slot] = construction
    slots: dict[str, ConstructionAssemblyComponent] = {}
    for umi_slot, sbem_slot in SET_SLOTS.items():
        slots[sbem_slot] = construction_to_sbem(
            by_umi_slot[umi_slot], SLOT_SURFACE_TYPES[sbem_slot], subject, _pointer(location, umi_slot), findings
        )
    for sbem_slot, umi_slot in FILLED_SLOTS.items():
        source = slots[SET_SLOTS[umi_slot]]
        slots[sbem_slot] = source.model_copy(update={"Type": SLOT_SURFACE_TYPES[sbem_slot]})
        findings.assume(
            subject,
            _pointer(location, umi_slot),
            source.Name,
            "construction.sets",
            f"UMI has no {sbem_slot}; it is filled from the {umi_slot} construction.",
        )
    return EnvelopeAssemblyComponent(
        Name=constructions.name or "",
        Category=constructions.category,
        Comment=constructions.comments,
        DataSource=constructions.data_source,
        InternalMassAssembly=internal_mass,
        InternalMassExposedAreaPerArea=internal_mass_exposed,
        PartitionAreaPerFloorArea=partition_area,
        **adiabatic_to_sbem(constructions),  # pyright: ignore[reportArgumentType]
        **slots,  # pyright: ignore[reportArgumentType]
    )


def _same_assembly(a: ConstructionAssemblyComponent, b: ConstructionAssemblyComponent) -> bool:
    """Tell whether two assemblies are equal but for the surface type."""
    return a.model_dump(exclude={"Type"}) == b.model_dump(exclude={"Type"})


@rule("construction.sets", to="umi")
def assemblies_to_umi(
    envelope: EnvelopeAssemblyComponent, subject: str, location: str, findings: Findings
) -> ZoneConstructions:
    """Translate SBEM's envelope assemblies to a UMI construction set.

    Args:
        envelope: The envelope assemblies.
        subject: The archetype being written.
        location: The assemblies' SBEM field path.
        findings: Collects the losses: each slot of `FILLED_SLOTS` that differs from the slot
            it would be filled from, and the constructions' losses. Internal mass belongs to the
            zone (`mass.internal`) and internal partitions to the template
            (`building.partition_ratio`); neither is translated here.

    Returns:
        The construction set, named as the assemblies.
    """
    for sbem_slot, umi_slot in FILLED_SLOTS.items():
        filled = cast("ConstructionAssemblyComponent", getattr(envelope, sbem_slot))
        source = cast("ConstructionAssemblyComponent", getattr(envelope, SET_SLOTS[umi_slot]))
        if not _same_assembly(filled, source):
            findings.lose(
                LossKind.LOST,
                subject,
                _path(location, sbem_slot),
                filled.Name,
                "construction.sets",
                f"UMI has no {sbem_slot}; it reads back as the {umi_slot} construction.",
                replacement=source.Name,
            )
    slots: dict[str, OpaqueConstruction] = {
        umi_slot: construction_to_umi(
            cast("ConstructionAssemblyComponent", getattr(envelope, sbem_slot)),
            subject,
            _path(location, sbem_slot),
            findings,
        )
        for umi_slot, sbem_slot in SET_SLOTS.items()
    }
    findings.unset(envelope, ("Category",), subject, location, "construction.sets")
    return ZoneConstructions.model_validate({
        "Name": envelope.Name,
        "Category": envelope.Category if envelope.Category is not None else "Uncategorized",
        "Comments": envelope.Comment,
        "DataSource": envelope.DataSource,
        **adiabatic_to_umi(envelope),
        **slots,
    })
