"""The UMI library format, as Basilisk reads and writes it (spec 003, research R1).

Private module (roadmap C-02): nothing here is exported, documented as API or returned to
users. These models are a parsing layer for the JSON of Basilisk at commit `5cce24e8`, not an
archetype model, and they do not depend on epinterface.

- One frozen pydantic model per Basilisk Core class, named after it, plus `UmiLibrary` for
  Basilisk's `Library`. Fields are snake_case with Basilisk's JSON keys as aliases.
- An absent key takes Basilisk's effective default: its `[DefaultValue]` when it has one
  (Basilisk applies them before reading), else its initialiser. `defaulted_keys` lists the
  keys that were absent.
- Basilisk's integer enums are `IntEnum`s with its values; the structural enums, which
  Basilisk writes by name, are string enums. Both also read from a member name, as
  Newtonsoft does.
- References are plain model fields: `archetypal.umi._refs` resolves `$id` and `$ref` into
  them and writes them back.
"""

from __future__ import annotations

from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Annotated, ClassVar, Generic, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field, field_validator

if TYPE_CHECKING:
    from collections.abc import Callable

__all__: list[str] = []

_E = TypeVar("_E", bound=Enum)


def _member_names(enum: type[Enum]) -> dict[str, Enum]:
    """Map each member's C# name, lower case, to the member (`None_` is C#'s `None`)."""
    return {member.name.rstrip("_").lower(): member for member in enum}


def _by_name(enum: type[_E]) -> Callable[[object], object]:
    """A before-validator that reads a member from its name, case-insensitively."""
    names = _member_names(enum)
    members = list(enum)

    def parse(value: object) -> object:
        if isinstance(value, str) and value.lower() in names:
            return names[value.lower()]
        if isinstance(value, int) and not isinstance(value, bool) and not issubclass(enum, int):
            # String enums read from their position too, as Newtonsoft's converter does.
            return members[value] if 0 <= value < len(members) else value
        return value

    return parse


# --- Enums -------------------------------------------------------------------------------


class FuelType(IntEnum):
    """Basilisk's `FuelType` (heating and cooling fuels)."""

    None_ = 0
    Electricity = 1
    NaturalGas = 2
    PropaneGas = 3
    FuelOil1 = 4
    FuelOil2 = 5
    Diesel = 6
    Gasoline = 7
    Coal = 8
    OtherFuel1 = 9
    OtherFuel2 = 10
    Steam = 11
    DistrictHeating = 12
    DistrictCooling = 13


class IdealSystemLimit(IntEnum):
    """Basilisk's `IdealSystemLimit` (heating and cooling limits)."""

    NoLimit = 0
    LimitFlowRate = 1
    LimitCapacity = 2
    LimitFlowRateAndCapacity = 3


class EconomizerType(IntEnum):
    """Basilisk's `EconomizerType`."""

    NoEconomizer = 0
    DifferentialDryBulb = 1
    DifferentialEnthalpy = 2


class HeatRecoveryType(IntEnum):
    """Basilisk's `HeatRecoveryType`."""

    None_ = 0
    Enthalpy = 1
    Sensible = 2


class DimmingType(IntEnum):
    """Basilisk's `DimmingType`."""

    Continuous = 0
    Off = 1
    Stepped = 2


class ShadingType(IntEnum):
    """Basilisk's `ShadingType`."""

    ExteriorShade = 0
    InteriorShade = 1


class WindowType(IntEnum):
    """Basilisk's `WindowType`."""

    External = 0
    Internal = 1


class DomesticHotWaterFuelType(IntEnum):
    """Basilisk's `DomesticHotWaterFuelType`."""

    Unset = 0
    Electricity = 1
    NaturalGas = 2
    Oil = 3


class ConstructionSystemTypeBeam(str, Enum):
    """Basilisk's `ConstructionSystemTypeBeam`, written by name."""

    RectangularSolid = "RectangularSolid"
    IBeam = "IBeam"
    RectangularTube = "RectangularTube"
    Truss = "Truss"


class ConstructionSystemTypeColumn(str, Enum):
    """Basilisk's `ConstructionSystemTypeColumn`, written by name."""

    SquareSolid = "SquareSolid"
    IBeam = "IBeam"
    SquareTube = "SquareTube"


class ConstructionSystemTypeFloor(str, Enum):
    """Basilisk's `ConstructionSystemTypeFloor`, written by name."""

    OneWayFlatSlab = "OneWayFlatSlab"
    OneWayRibbedSlab = "OneWayRibbedSlab"
    OneWaySlabOnMetalDeck = "OneWaySlabOnMetalDeck"
    OneWayJoistSystem = "OneWayJoistSystem"
    TwoWayFlatSlab = "TwoWayFlatSlab"
    TwoWayWaffleSlab = "TwoWayWaffleSlab"


class ConstructionSystemTypeFoundation(str, Enum):
    """Basilisk's `ConstructionSystemTypeFoundation`, written by name."""

    SpreadFootings = "SpreadFootings"
    Raft = "Raft"
    PileAndPileCaps = "PileAndPileCaps"
    ShellFootings = "ShellFootings"


class ConstructionSystemTypeLateralSystem(str, Enum):
    """Basilisk's `ConstructionSystemTypeLateralSystem`, written by name."""

    CrossBracing = "CrossBracing"
    MomentFrames = "MomentFrames"
    ShearWalls = "ShearWalls"


class FoundationSoilPreset(str, Enum):
    """Basilisk's `FoundationSoilPreset`, written by name."""

    Clay = "Clay"
    Gravel = "Gravel"
    Sand = "Sand"
    Other = "Other"


class LiveLoadingPreset(str, Enum):
    """Basilisk's `LiveLoadingPreset`, written by name."""

    Offices = "Offices"
    Residential = "Residential"
    SchoolsClassrooms = "SchoolsClassrooms"
    LibrariesReadingRooms = "LibrariesReadingRooms"
    HospitalsLabs = "HospitalsLabs"
    AssemblyAreas = "AssemblyAreas"
    Restaurants = "Restaurants"
    Recreational = "Recreational"
    Retail = "Retail"
    WarehouseLightStorage = "WarehouseLightStorage"
    LibrariesStackRooms = "LibrariesStackRooms"
    WarehouseHeavyStorage = "WarehouseHeavyStorage"
    Other = "Other"


_FuelType = Annotated[FuelType, BeforeValidator(_by_name(FuelType))]
_IdealSystemLimit = Annotated[IdealSystemLimit, BeforeValidator(_by_name(IdealSystemLimit))]
_EconomizerType = Annotated[EconomizerType, BeforeValidator(_by_name(EconomizerType))]
_HeatRecoveryType = Annotated[HeatRecoveryType, BeforeValidator(_by_name(HeatRecoveryType))]
_DimmingType = Annotated[DimmingType, BeforeValidator(_by_name(DimmingType))]
_ShadingType = Annotated[ShadingType, BeforeValidator(_by_name(ShadingType))]
_WindowType = Annotated[WindowType, BeforeValidator(_by_name(WindowType))]
_DhwFuelType = Annotated[DomesticHotWaterFuelType, BeforeValidator(_by_name(DomesticHotWaterFuelType))]
_SoilPreset = Annotated[FoundationSoilPreset, BeforeValidator(_by_name(FoundationSoilPreset))]
_LoadingPreset = Annotated[LiveLoadingPreset, BeforeValidator(_by_name(LiveLoadingPreset))]


# --- Base classes ------------------------------------------------------------------------


class FormatModel(BaseModel):
    """Base of every format model: frozen, read by alias or by name, unknown keys ignored."""

    model_config = ConfigDict(
        frozen=True,
        validate_by_alias=True,
        validate_by_name=True,
        serialize_by_alias=True,
        extra="ignore",
    )

    @property
    def defaulted_keys(self) -> frozenset[str]:
        """The Basilisk keys that were absent, and so hold Basilisk's default."""
        return frozenset(
            field.alias or name for name, field in type(self).model_fields.items() if name not in self.model_fields_set
        )

    @classmethod
    def basilisk_keys(cls) -> tuple[tuple[str, str], ...]:
        """Each field as `(name, Basilisk key)`, in the order Basilisk writes them.

        Newtonsoft writes the members of the most derived class first, then those of each base
        class; a member a class overrides is written where the overriding class puts it.
        """
        fields = cls.model_fields
        seen: set[str] = set()
        order: list[tuple[str, str]] = []
        for klass in cls.__mro__:
            for name in vars(klass).get("__annotations__", {}):
                if name in fields and name not in seen:
                    seen.add(name)
                    order.append((name, fields[name].alias or name))
        return tuple(order)


class LibraryComponent(FormatModel):
    """Basilisk's `LibraryComponent`: the named, shareable base of every component."""

    category: str = Field(default="Uncategorized", alias="Category")
    comments: str | None = Field(default=None, alias="Comments")
    data_source: str | None = Field(default=None, alias="DataSource")
    name: str | None = Field(default=None, alias="Name")

    fixed_category: ClassVar[str | None] = None
    """The category Basilisk's getter returns whatever the file says, if the class fixes one."""

    @field_validator("category", mode="before")
    @classmethod
    def _fix_category(cls, value: object) -> object:
        return value if cls.fixed_category is None else cls.fixed_category


class MaterialBase(LibraryComponent):
    """Basilisk's `MaterialBase`: the fields shared by every material."""

    conductivity: float = Field(default=0.0, alias="Conductivity")
    cost: float = Field(default=0.0, alias="Cost")
    density: float = Field(default=0.0, alias="Density")
    embodied_carbon: float = Field(default=0.0, alias="EmbodiedCarbon")
    embodied_energy: float = Field(default=0.0, alias="EmbodiedEnergy")
    substitution_rate_pattern: tuple[float, ...] = Field(default=(1.0,), alias="SubstitutionRatePattern")
    substitution_timestep: float = Field(default=0.0, alias="SubstitutionTimestep")
    transport_carbon: float = Field(default=0.0, alias="TransportCarbon")
    transport_distance: float = Field(default=0.0, alias="TransportDistance")
    transport_energy: float = Field(default=0.0, alias="TransportEnergy")


class WindowMaterialBase(MaterialBase):
    """Basilisk's `WindowMaterialBase`: glazing and gas materials (no field of its own)."""


class ConstructionBase(LibraryComponent):
    """Basilisk's `ConstructionBase`: the assembly fields of constructions and structures."""

    assembly_carbon: float = Field(default=0.0, alias="AssemblyCarbon")
    assembly_cost: float = Field(default=0.0, alias="AssemblyCost")
    assembly_energy: float = Field(default=0.0, alias="AssemblyEnergy")
    disassembly_carbon: float = Field(default=0.0, alias="DisassemblyCarbon")
    disassembly_energy: float = Field(default=0.0, alias="DisassemblyEnergy")


# --- Materials and constructions ---------------------------------------------------------


class GasMaterial(WindowMaterialBase):
    """Basilisk's `GasMaterial`; its category is always `Gases`."""

    fixed_category: ClassVar[str | None] = "Gases"

    category: str = Field(default="Gases", alias="Category")
    type: str = Field(default="AIR", alias="Type")


class GlazingMaterial(WindowMaterialBase):
    """Basilisk's `GlazingMaterial`."""

    dirt_factor: float = Field(default=1.0, alias="DirtFactor")
    ir_emissivity_back: float = Field(default=0.84, alias="IREmissivityBack")
    ir_emissivity_front: float = Field(default=0.84, alias="IREmissivityFront")
    ir_transmittance: float = Field(default=0.0, alias="IRTransmittance")
    solar_reflectance_back: float = Field(default=0.075, alias="SolarReflectanceBack")
    solar_reflectance_front: float = Field(default=0.075, alias="SolarReflectanceFront")
    solar_transmittance: float = Field(default=0.837, alias="SolarTransmittance")
    visible_reflectance_back: float = Field(default=0.081, alias="VisibleReflectanceBack")
    visible_reflectance_front: float = Field(default=0.081, alias="VisibleReflectanceFront")
    visible_transmittance: float = Field(default=0.898, alias="VisibleTransmittance")


class OpaqueMaterial(MaterialBase):
    """Basilisk's `OpaqueMaterial`."""

    design_strength: float | None = Field(default=None, alias="DesignStrength")
    modulus_of_elasticity: float | None = Field(default=None, alias="ModulusOfElasticity")
    moisture_diffusion_resistance: float = Field(default=0.0, alias="MoistureDiffusionResistance")
    roughness: str | None = Field(default=None, alias="Roughness")
    solar_absorptance: float = Field(default=0.0, alias="SolarAbsorptance")
    specific_heat: float = Field(default=0.0, alias="SpecificHeat")
    thermal_emittance: float = Field(default=0.0, alias="ThermalEmittance")
    visible_absorptance: float = Field(default=0.0, alias="VisibleAbsorptance")


_M = TypeVar("_M", bound=MaterialBase)


class MaterialLayer(FormatModel, Generic[_M]):
    """Basilisk's `MaterialLayer<T>`: a material at a thickness (m)."""

    material: _M | None = Field(default=None, alias="Material")
    thickness: float = Field(default=0.0, alias="Thickness")


class OpaqueConstruction(ConstructionBase):
    """Basilisk's `OpaqueConstruction`: opaque layers, outside first."""

    layers: tuple[MaterialLayer[OpaqueMaterial], ...] = Field(default=(), alias="Layers")


class WindowConstruction(ConstructionBase):
    """Basilisk's `WindowConstruction`: glazing and gas layers, outside first."""

    layers: tuple[MaterialLayer[GlazingMaterial | GasMaterial], ...] = Field(default=(), alias="Layers")


# --- Structure ---------------------------------------------------------------------------


class MassRatios(FormatModel):
    """Basilisk's `MassRatios`: structural mass per floor area for one material."""

    high_load_ratio: float = Field(default=0.0, alias="HighLoadRatio")
    material: OpaqueMaterial | None = Field(default=None, alias="Material")
    normal_ratio: float = Field(default=0.0, alias="NormalRatio")


MassRatio = MassRatios
"""The name data-model.md uses for Basilisk's `MassRatios`."""


class ColumnWallSpacingSettings(FormatModel):
    """Basilisk's `ColumnWallSpacingSettings` (spans in m)."""

    primary_span: float = Field(default=8.0, alias="PrimarySpan")
    secondary_span: float = Field(default=8.0, alias="SecondarySpan")


class ConstructionSystem(FormatModel, Generic[_E]):
    """Basilisk's `ConstructionSystem<T>`; each slot of `ConstructionSystemSettings` closes it.

    Basilisk marks it as a reference type, so it carries a `$id` in the file.
    """

    material: OpaqueMaterial | None = Field(default=None, alias="Material")
    construction_system_type: _E = Field(alias="ConstructionSystemType")

    @classmethod
    def basilisk_keys(cls) -> tuple[tuple[str, str], ...]:
        """Each field as `(name, Basilisk key)`, in the order of Basilisk's generic class.

        The subclasses only close `ConstructionSystem<T>` (their override of
        `ConstructionSystemType` reads it by name), so they keep its order: `Material` first.
        """
        return tuple((name, cls.model_fields[name].alias or name) for name in ("material", "construction_system_type"))


class BeamSystem(ConstructionSystem[ConstructionSystemTypeBeam]):
    """`ConstructionSystem<ConstructionSystemTypeBeam>`."""

    construction_system_type: Annotated[
        ConstructionSystemTypeBeam, BeforeValidator(_by_name(ConstructionSystemTypeBeam))
    ] = Field(default=ConstructionSystemTypeBeam.RectangularSolid, alias="ConstructionSystemType")


class ColumnSystem(ConstructionSystem[ConstructionSystemTypeColumn]):
    """`ConstructionSystem<ConstructionSystemTypeColumn>`."""

    construction_system_type: Annotated[
        ConstructionSystemTypeColumn, BeforeValidator(_by_name(ConstructionSystemTypeColumn))
    ] = Field(default=ConstructionSystemTypeColumn.SquareSolid, alias="ConstructionSystemType")


class FloorSystem(ConstructionSystem[ConstructionSystemTypeFloor]):
    """`ConstructionSystem<ConstructionSystemTypeFloor>`."""

    construction_system_type: Annotated[
        ConstructionSystemTypeFloor, BeforeValidator(_by_name(ConstructionSystemTypeFloor))
    ] = Field(default=ConstructionSystemTypeFloor.OneWayFlatSlab, alias="ConstructionSystemType")


class FoundationSystem(ConstructionSystem[ConstructionSystemTypeFoundation]):
    """`ConstructionSystem<ConstructionSystemTypeFoundation>`."""

    construction_system_type: Annotated[
        ConstructionSystemTypeFoundation, BeforeValidator(_by_name(ConstructionSystemTypeFoundation))
    ] = Field(default=ConstructionSystemTypeFoundation.SpreadFootings, alias="ConstructionSystemType")


class LateralSystem(ConstructionSystem[ConstructionSystemTypeLateralSystem]):
    """`ConstructionSystem<ConstructionSystemTypeLateralSystem>`."""

    construction_system_type: Annotated[
        ConstructionSystemTypeLateralSystem, BeforeValidator(_by_name(ConstructionSystemTypeLateralSystem))
    ] = Field(default=ConstructionSystemTypeLateralSystem.CrossBracing, alias="ConstructionSystemType")


class ConstructionSystemSettings(FormatModel):
    """Basilisk's `ConstructionSystemSettings`."""

    beams: BeamSystem = Field(default_factory=BeamSystem, alias="Beams")
    columns: ColumnSystem = Field(default_factory=ColumnSystem, alias="Columns")
    floors: FloorSystem = Field(default_factory=FloorSystem, alias="Floors")
    foundations: FoundationSystem = Field(default_factory=FoundationSystem, alias="Foundations")
    lateral_system: LateralSystem = Field(default_factory=LateralSystem, alias="LateralSystem")


class FoundationSoilSettings(FormatModel):
    """Basilisk's `FoundationSoilSettings`."""

    foundation_soil_preset: _SoilPreset = Field(default=FoundationSoilPreset.Clay, alias="FoundationSoilPreset")
    foundation_soil_value: float = Field(default=72.0, alias="FoundationSoilValue")


class LoadingSettings(FormatModel):
    """Basilisk's `LoadingSettings`."""

    live_loading_preset: _LoadingPreset = Field(default=LiveLoadingPreset.Offices, alias="LiveLoadingPreset")
    live_loading_value: float = Field(default=2.4, alias="LiveLoadingValue")


class AdvancedStructuralModel(FormatModel):
    """Basilisk's `AdvancedStructuralModel`."""

    column_wall_spacing: ColumnWallSpacingSettings = Field(
        default_factory=ColumnWallSpacingSettings, alias="ColumnWallSpacing"
    )
    construction_systems: ConstructionSystemSettings = Field(
        default_factory=ConstructionSystemSettings, alias="ConstructionSystems"
    )
    foundation_soil_settings: FoundationSoilSettings = Field(
        default_factory=FoundationSoilSettings, alias="FoundationSoilSettings"
    )
    loading_settings: LoadingSettings = Field(default_factory=LoadingSettings, alias="LoadingSettings")


class StructureInformation(ConstructionBase):
    """Basilisk's `StructureInformation`: a building template's structure."""

    advanced_model: AdvancedStructuralModel = Field(default_factory=AdvancedStructuralModel, alias="AdvancedModel")
    mass_ratios: tuple[MassRatios, ...] = Field(default=(), alias="MassRatios")
    use_advanced_model: bool = Field(default=False, alias="UseAdvancedModel")


# --- Schedules ---------------------------------------------------------------------------


class DaySchedule(LibraryComponent):
    """Basilisk's `DaySchedule`: 24 hourly values; its category is always `Day`."""

    fixed_category: ClassVar[str | None] = "Day"

    category: str = Field(default="Day", alias="Category")
    type: str = Field(default="Fraction", alias="Type")
    values: tuple[float, ...] = Field(default=(), alias="Values")


class WeekSchedule(LibraryComponent):
    """Basilisk's `WeekSchedule`: seven days, Monday first; its category is always `Week`."""

    fixed_category: ClassVar[str | None] = "Week"

    category: str = Field(default="Week", alias="Category")
    days: tuple[DaySchedule | None, ...] = Field(default=(), alias="Days")
    type: str | None = Field(default="Fraction", alias="Type")


class YearSchedulePart(FormatModel):
    """Basilisk's `YearSchedulePart`: a week schedule over a date range (inclusive)."""

    from_day: int = Field(default=0, alias="FromDay")
    from_month: int = Field(default=0, alias="FromMonth")
    to_day: int = Field(default=0, alias="ToDay")
    to_month: int = Field(default=0, alias="ToMonth")
    schedule: WeekSchedule | None = Field(default=None, alias="Schedule")


class YearSchedule(LibraryComponent):
    """Basilisk's `YearSchedule`: parts covering the year; its category is always `Year`."""

    fixed_category: ClassVar[str | None] = "Year"

    category: str = Field(default="Year", alias="Category")
    parts: tuple[YearSchedulePart, ...] = Field(default=(), alias="Parts")
    type: str = Field(default="Fraction", alias="Type")


# --- Zone components ---------------------------------------------------------------------


class DomesticHotWaterSettings(LibraryComponent):
    """Basilisk's `DomesticHotWaterSettings` (flow in m³/h per m², temperatures in °C)."""

    coefficient_of_performance: float = Field(default=0.85, alias="CoefficientOfPerformance")
    flow_rate_per_floor_area: float = Field(default=0.03, alias="FlowRatePerFloorArea")
    fuel_type: _DhwFuelType = Field(default=DomesticHotWaterFuelType.NaturalGas, alias="FuelType")
    is_on: bool = Field(default=True, alias="IsOn")
    water_schedule: YearSchedule | None = Field(default=None, alias="WaterSchedule")
    water_supply_temperature: float = Field(default=65.0, alias="WaterSupplyTemperature")
    water_temperature_inlet: float = Field(default=10.0, alias="WaterTemperatureInlet")


class ZoneVentilation(LibraryComponent):
    """Basilisk's `ZoneVentilation` (collection `VentilationSettings`)."""

    afn: bool = Field(default=False, alias="Afn")
    is_buoyancy_on: bool = Field(default=True, alias="IsBuoyancyOn")
    infiltration: float = Field(default=0.1, alias="Infiltration")
    is_infiltration_on: bool = Field(default=True, alias="IsInfiltrationOn")
    is_nat_vent_on: bool = Field(default=False, alias="IsNatVentOn")
    is_scheduled_ventilation_on: bool = Field(default=False, alias="IsScheduledVentilationOn")
    nat_vent_max_rel_humidity: float = Field(default=90.0, alias="NatVentMaxRelHumidity")
    nat_vent_max_outdoor_air_temp: float = Field(default=30.0, alias="NatVentMaxOutdoorAirTemp")
    nat_vent_min_outdoor_air_temp: float = Field(default=0.0, alias="NatVentMinOutdoorAirTemp")
    nat_vent_schedule: YearSchedule | None = Field(default=None, alias="NatVentSchedule")
    nat_vent_zone_temp_setpoint: float = Field(default=18.0, alias="NatVentZoneTempSetpoint")
    scheduled_ventilation_ach: float = Field(default=0.6, alias="ScheduledVentilationAch")
    scheduled_ventilation_schedule: YearSchedule | None = Field(default=None, alias="ScheduledVentilationSchedule")
    scheduled_ventilation_setpoint: float = Field(default=18.0, alias="ScheduledVentilationSetpoint")
    is_wind_on: bool = Field(default=False, alias="IsWindOn")


class ZoneConditioning(LibraryComponent):
    """Basilisk's `ZoneConditioning`."""

    cooling_schedule: YearSchedule | None = Field(default=None, alias="CoolingSchedule")
    cooling_coeff_of_perf: float = Field(default=0.0, alias="CoolingCoeffOfPerf")
    cooling_setpoint: float = Field(default=26.0, alias="CoolingSetpoint")
    cooling_limit_type: _IdealSystemLimit = Field(default=IdealSystemLimit.NoLimit, alias="CoolingLimitType")
    cooling_fuel_type: _FuelType = Field(default=FuelType.Electricity, alias="CoolingFuelType")
    economizer_type: _EconomizerType = Field(default=EconomizerType.NoEconomizer, alias="EconomizerType")
    heating_coeff_of_perf: float = Field(default=0.0, alias="HeatingCoeffOfPerf")
    heating_limit_type: _IdealSystemLimit = Field(default=IdealSystemLimit.NoLimit, alias="HeatingLimitType")
    heating_fuel_type: _FuelType = Field(default=FuelType.NaturalGas, alias="HeatingFuelType")
    heating_schedule: YearSchedule | None = Field(default=None, alias="HeatingSchedule")
    heating_setpoint: float = Field(default=20.0, alias="HeatingSetpoint")
    heat_recovery_efficiency_latent: float = Field(default=0.65, alias="HeatRecoveryEfficiencyLatent")
    heat_recovery_efficiency_sensible: float = Field(default=0.7, alias="HeatRecoveryEfficiencySensible")
    heat_recovery_type: _HeatRecoveryType = Field(default=HeatRecoveryType.None_, alias="HeatRecoveryType")
    is_cooling_on: bool = Field(default=True, alias="IsCoolingOn")
    is_heating_on: bool = Field(default=True, alias="IsHeatingOn")
    is_mech_vent_on: bool = Field(default=True, alias="IsMechVentOn")
    max_cool_flow: float = Field(default=100.0, alias="MaxCoolFlow")
    max_cooling_capacity: float = Field(default=100.0, alias="MaxCoolingCapacity")
    max_heat_flow: float = Field(default=100.0, alias="MaxHeatFlow")
    max_heating_capacity: float = Field(default=100.0, alias="MaxHeatingCapacity")
    mech_vent_schedule: YearSchedule | None = Field(default=None, alias="MechVentSchedule")
    min_fresh_air_per_area: float = Field(default=0.001, alias="MinFreshAirPerArea")
    min_fresh_air_per_person: float = Field(default=0.001, alias="MinFreshAirPerPerson")


class ZoneConstructions(LibraryComponent):
    """Basilisk's `ZoneConstructions` (collection `ZoneConstructionSets`)."""

    facade: OpaqueConstruction | None = Field(default=None, alias="Facade")
    ground: OpaqueConstruction | None = Field(default=None, alias="Ground")
    partition: OpaqueConstruction | None = Field(default=None, alias="Partition")
    roof: OpaqueConstruction | None = Field(default=None, alias="Roof")
    slab: OpaqueConstruction | None = Field(default=None, alias="Slab")
    is_facade_adiabatic: bool = Field(default=False, alias="IsFacadeAdiabatic")
    is_ground_adiabatic: bool = Field(default=False, alias="IsGroundAdiabatic")
    is_partition_adiabatic: bool = Field(default=False, alias="IsPartitionAdiabatic")
    is_roof_adiabatic: bool = Field(default=False, alias="IsRoofAdiabatic")
    is_slab_adiabatic: bool = Field(default=False, alias="IsSlabAdiabatic")


class ZoneLoads(LibraryComponent):
    """Basilisk's `ZoneLoads` (densities per m² of floor)."""

    dimming_type: _DimmingType = Field(default=DimmingType.Continuous, alias="DimmingType")
    equipment_availability_schedule: YearSchedule | None = Field(default=None, alias="EquipmentAvailabilitySchedule")
    equipment_power_density: float = Field(default=12.0, alias="EquipmentPowerDensity")
    illuminance_target: float = Field(default=500.0, alias="IlluminanceTarget")
    lighting_power_density: float = Field(default=12.0, alias="LightingPowerDensity")
    lights_availability_schedule: YearSchedule | None = Field(default=None, alias="LightsAvailabilitySchedule")
    occupancy_schedule: YearSchedule | None = Field(default=None, alias="OccupancySchedule")
    is_equipment_on: bool = Field(default=True, alias="IsEquipmentOn")
    is_lighting_on: bool = Field(default=True, alias="IsLightingOn")
    is_people_on: bool = Field(default=True, alias="IsPeopleOn")
    people_density: float = Field(default=0.2, alias="PeopleDensity")


class ZoneDefinition(LibraryComponent):
    """Basilisk's `ZoneDefinition` (collection `Zones`)."""

    conditioning: ZoneConditioning | None = Field(default=None, alias="Conditioning")
    constructions: ZoneConstructions | None = Field(default=None, alias="Constructions")
    daylight_mesh_resolution: float = Field(default=1.0, alias="DaylightMeshResolution")
    daylight_workplane_height: float = Field(default=0.8, alias="DaylightWorkplaneHeight")
    domestic_hot_water: DomesticHotWaterSettings | None = Field(default=None, alias="DomesticHotWater")
    internal_mass_construction: OpaqueConstruction | None = Field(default=None, alias="InternalMassConstruction")
    internal_mass_exposed_per_floor_area: float = Field(default=0.0, alias="InternalMassExposedPerFloorArea")
    loads: ZoneLoads | None = Field(default=None, alias="Loads")
    ventilation: ZoneVentilation | None = Field(default=None, alias="Ventilation")


class WindowSettings(LibraryComponent):
    """Basilisk's `WindowSettings`."""

    afn_discharge_c: float = Field(default=0.65, alias="AfnDischargeC")
    afn_temp_setpoint: float = Field(default=20.0, alias="AfnTempSetpoint")
    afn_window_availability: YearSchedule | None = Field(default=None, alias="AfnWindowAvailability")
    construction: WindowConstruction | None = Field(default=None, alias="Construction")
    is_shading_system_on: bool = Field(default=True, alias="IsShadingSystemOn")
    is_virtual_partition: bool = Field(default=False, alias="IsVirtualPartition")
    is_zone_mixing_on: bool = Field(default=False, alias="IsZoneMixingOn")
    operable_area: float = Field(default=0.8, alias="OperableArea")
    shading_system_availability_schedule: YearSchedule | None = Field(
        default=None, alias="ShadingSystemAvailabilitySchedule"
    )
    shading_system_setpoint: float = Field(default=180.0, alias="ShadingSystemSetpoint")
    shading_system_transmittance: float = Field(default=0.5, alias="ShadingSystemTransmittance")
    shading_system_type: _ShadingType = Field(default=ShadingType.ExteriorShade, alias="ShadingSystemType")
    type: _WindowType = Field(default=WindowType.External, alias="Type")
    zone_mixing_availability_schedule: YearSchedule | None = Field(default=None, alias="ZoneMixingAvailabilitySchedule")
    zone_mixing_delta_temperature: float = Field(default=2.0, alias="ZoneMixingDeltaTemperature")
    zone_mixing_flow_rate: float = Field(default=0.001, alias="ZoneMixingFlowRate")


class BuildingTemplate(LibraryComponent):
    """Basilisk's `BuildingTemplate`: core and perimeter zones, structure and windows."""

    core: ZoneDefinition | None = Field(default=None, alias="Core")
    lifespan: int = Field(default=0, alias="Lifespan")
    partition_ratio: float = Field(default=0.0, alias="PartitionRatio")
    perimeter: ZoneDefinition | None = Field(default=None, alias="Perimeter")
    structure: StructureInformation | None = Field(default=None, alias="Structure")
    windows: WindowSettings | None = Field(default=None, alias="Windows")
    default_window_to_wall_ratio: float = Field(default=0.4, alias="DefaultWindowToWallRatio")
    year_from: int | None = Field(default=None, alias="YearFrom")
    year_to: int | None = Field(default=None, alias="YearTo")
    country: tuple[str, ...] = Field(default=(), alias="Country")
    climate_zone: tuple[str, ...] = Field(default=(), alias="ClimateZone")
    authors: tuple[str, ...] = Field(default=(), alias="Authors")
    author_emails: tuple[str, ...] = Field(default=(), alias="AuthorEmails")
    version: str = Field(default="v1.0", alias="Version")


# --- The library -------------------------------------------------------------------------


class UmiLibrary(FormatModel):
    """Basilisk's `Library`: the 17 collections, in the order Basilisk writes them."""

    gas_materials: tuple[GasMaterial, ...] = Field(default=(), alias="GasMaterials")
    glazing_materials: tuple[GlazingMaterial, ...] = Field(default=(), alias="GlazingMaterials")
    opaque_materials: tuple[OpaqueMaterial, ...] = Field(default=(), alias="OpaqueMaterials")
    opaque_constructions: tuple[OpaqueConstruction, ...] = Field(default=(), alias="OpaqueConstructions")
    window_constructions: tuple[WindowConstruction, ...] = Field(default=(), alias="WindowConstructions")
    structure_definitions: tuple[StructureInformation, ...] = Field(default=(), alias="StructureDefinitions")
    day_schedules: tuple[DaySchedule, ...] = Field(default=(), alias="DaySchedules")
    week_schedules: tuple[WeekSchedule, ...] = Field(default=(), alias="WeekSchedules")
    year_schedules: tuple[YearSchedule, ...] = Field(default=(), alias="YearSchedules")
    domestic_hot_water_settings: tuple[DomesticHotWaterSettings, ...] = Field(
        default=(), alias="DomesticHotWaterSettings"
    )
    ventilation_settings: tuple[ZoneVentilation, ...] = Field(default=(), alias="VentilationSettings")
    zone_conditionings: tuple[ZoneConditioning, ...] = Field(default=(), alias="ZoneConditionings")
    zone_construction_sets: tuple[ZoneConstructions, ...] = Field(default=(), alias="ZoneConstructionSets")
    zone_loads: tuple[ZoneLoads, ...] = Field(default=(), alias="ZoneLoads")
    zones: tuple[ZoneDefinition, ...] = Field(default=(), alias="Zones")
    building_templates: tuple[BuildingTemplate, ...] = Field(default=(), alias="BuildingTemplates")
    window_settings: tuple[WindowSettings, ...] = Field(default=(), alias="WindowSettings")
