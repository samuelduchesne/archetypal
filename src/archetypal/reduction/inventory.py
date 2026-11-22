"""The zone inventory: one `ZoneRecord` per EnergyPlus zone (spec 002, data-model.md, ZoneRecord).

Every figure EnergyPlus computes comes from the results (research R1):

- zones, surfaces, constructions, layers and materials from the static SQLite tables, through
  the typed rows of `_sql_tables`;
- U-factors with films, SHGC and visible transmittance from the tabular *Envelope Summary*;
- installed gains and design infiltration from the `Nominal*` tables;
- delivered energy, mechanical outdoor air and hot-water volume from the hourly outputs of R2.

The model, read through idfkit's typed accessors (R18), supplies only what the results do not
hold: infiltration coefficients, thermostat controls, design outdoor-air rates, `Space` types,
`WaterUse:Equipment` and which zones are air-loop plenums.

**No multiplier is applied here** (data-model.md invariant). Every figure is for one copy of the
zone; `GroupLedger.from_zone` multiplies once. Two hourly outputs already include the zone's
multipliers in EnergyPlus, and are divided by `ZoneRecord.multiplier` here so that they too
describe one copy: `Zone Mechanical Ventilation Standard Density Volume Flow Rate` and
`Water Use Equipment Hot Water Volume` of equipment with a zone. `Zone Air System Sensible
Heating/Cooling Energy` is reported for one copy and is kept as it is.

Domestic hot water follows research R11: equipment with a zone belongs to that zone; equipment
without one is allocated to zones in proportion to their occupant-hours (Σ people * schedule,
times the zone's multiplier). Without any occupant-hours it is allocated by floor area of the
zones that count towards the building's total area.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeVar

import numpy as np
from idfkit.exceptions import ResultLookupError

from archetypal.reduction._sql_tables import (
    NominalInfiltrationRow,
    NominalLoadRow,
    read_construction_layers,
    read_constructions,
    read_materials,
    read_nominal_infiltration,
    read_nominal_loads,
    read_nominal_ventilation,
    read_surfaces,
    read_zones,
)
from archetypal.reduction.schedules import ScheduleEvaluator

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Mapping, Sequence

    from idfkit.simulation import SQLResult
    from idfkit.versioned import IDFDocumentSince22_1

    from archetypal.reduction._sql_tables import ConstructionRow, GainKind, MaterialRow, SurfaceRow, ZoneRow
    from archetypal.reduction.schedules import Profile
    from archetypal.reduction.sources import SourceData

__all__ = [
    "BAND",
    "AirflowRecord",
    "Boundary",
    "GainRecord",
    "HotWaterRecord",
    "LayerRecord",
    "Mode",
    "SurfaceClass",
    "SurfaceRecord",
    "ThermostatControl",
    "ThermostatRecord",
    "ZoneRecord",
    "build_inventory",
    "surface_class",
]

Mode = Literal["heating", "cooling"]
"""A conditioning mode."""

SurfaceClass = Literal[
    "exterior_wall",
    "roof",
    "exposed_floor",
    "ground_floor",
    "ground_wall",
    "window",
    "interior",
    "internal_mass",
]
"""A surface's class (research R6)."""

Boundary = Literal["outdoors", "ground", "interzone", "adiabatic", "other"]
"""A surface's outside boundary condition, from `Surfaces.ExtBoundCond`."""

BAND = (5.0, 35.0)
"""Setpoints within this band (°C, inclusive) enable their mode; outside it they disable it (R10)."""

_WALL_TILT = (60.0, 120.0)
# EnergyPlus `ExtBoundCond` codes (DataSurfaces): 0 outdoors, -1 ground, -2 to -4 other-side
# coefficients or conditions, -5 ground by F/C-factor, -6 Kiva foundation.
_OUTDOORS = 0
_GROUND = frozenset({-1, -5, -6})
_WINDOW_CLASSES = frozenset({"WINDOW", "GLASSDOOR", "TUBULARDAYLIGHTDOME", "TUBULARDAYLIGHTDIFFUSER"})
_INTERNAL_MASS = "INTERNAL MASS"
# Film resistances (m²K/W) used only when a surface is missing from the Envelope Summary: the
# ISO 6946 inside film plus an outside film (still air for any boundary but outdoors).
_R_INSIDE = 0.13
_R_OUTSIDE = 0.04
# Default of DesignSpecification:OutdoorAir's Outdoor Air Flow per Person (m³/s per person).
_DEFAULT_OA_PER_PERSON = 0.00944

_HEATING_VARIABLE = "Zone Air System Sensible Heating Energy"
_COOLING_VARIABLE = "Zone Air System Sensible Cooling Energy"
_OUTDOOR_AIR_VARIABLE = "Zone Mechanical Ventilation Standard Density Volume Flow Rate"
_HOT_WATER_VARIABLE = "Water Use Equipment Hot Water Volume"
_HOURLY = "Hourly"
_ENVELOPE_SUMMARY = "EnvelopeSummary"


# --- Records --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LayerRecord:
    """One layer of a surface's construction, outside first.

    Attributes:
        material: The material's name.
        thickness: m.
        conductivity: W/mK.
        density: kg/m³.
        specific_heat: J/kgK.
        resistance: m²K/W, as EnergyPlus reports it.
        resistance_only: A no-mass material (`Material:NoMass`, air gap).
    """

    material: str
    thickness: float
    conductivity: float
    density: float
    specific_heat: float
    resistance: float
    resistance_only: bool

    @property
    def heat_capacity(self) -> float:
        """rho·c·d, J/m²K (0 for a no-mass layer)."""
        if self.resistance_only:
            return 0.0
        return self.density * self.specific_heat * self.thickness


@dataclass(frozen=True)
class SurfaceRecord:
    """One heat-transfer surface of a zone (or an internal mass), one copy.

    Attributes:
        name: `Surfaces.SurfaceName` (upper case, as EnergyPlus writes it).
        surface_class: Its class (research R6, `surface_class`).
        class_name: EnergyPlus's `ClassName` (`Wall`, `Roof`, `Window`, `Internal Mass`, ...).
        area: Net area, m².
        azimuth: Degrees clockwise from north.
        tilt: Degrees from horizontal facing up (0 a roof, 90 a wall, 180 a floor).
        boundary: The outside boundary condition.
        adjacent_zone: For an interzone surface, the other zone (model spelling); else `None`.
        construction: The construction's name, or `None`.
        u_factor: U-factor with films, W/m²K: the Envelope Summary's figure (assembly, else glass,
            for windows); without one, `Constructions.Uvalue` plus standard films.
        u_source: Where `u_factor` comes from.
        heat_capacity: sum of rho·c·d of the construction's layers, J/m²K; 0 for windows.
        layers: The construction's layers, outside first.
        base_surface: For a subsurface (window, door), its base surface's name.
        shgc: For a window, the Envelope Summary's SHGC.
        visible_transmittance: For a window, the Envelope Summary's visible transmittance.
    """

    name: str
    surface_class: SurfaceClass
    class_name: str
    area: float
    azimuth: float
    tilt: float
    boundary: Boundary
    adjacent_zone: str | None
    construction: str | None
    u_factor: float
    u_source: Literal["envelope_summary", "constructions"]
    heat_capacity: float
    layers: tuple[LayerRecord, ...] = ()
    base_surface: str | None = None
    shgc: float | None = None
    visible_transmittance: float | None = None


@dataclass(frozen=True)
class GainRecord:
    """One installed internal gain of a zone, one copy (a row of a `Nominal*` table).

    Attributes:
        kind: The gain's kind (its `Nominal*` table).
        name: `ObjectName` (for a ZoneList object, EnergyPlus prefixes the zone's name).
        design_level: People for `people`; W otherwise (capacity for `baseboard`).
        schedule: The schedule's name, or `None`.
        fraction_radiant: Radiant fraction.
        fraction_latent: Latent fraction; `None` for people (EnergyPlus computes it).
        fraction_lost: Lost fraction.
        fraction_return_air: Return-air fraction (lights); 0 otherwise.
    """

    kind: GainKind
    name: str
    design_level: float
    schedule: str | None
    fraction_radiant: float
    fraction_latent: float | None
    fraction_lost: float
    fraction_return_air: float = 0.0


@dataclass(frozen=True)
class AirflowRecord:
    """One design airflow of a zone, one copy (`NominalInfiltration` or `NominalVentilation`).

    EnergyPlus's flow each hour is `design_flow * schedule * (constant + temperature·|ΔT| +
    velocity·v + velocity_squared·v²)`. The coefficients come from the model's
    `ZoneInfiltration:DesignFlowRate` or `ZoneVentilation:DesignFlowRate` of the same name;
    `coefficients_found` is `False` when no such object exists (EnergyPlus's defaults 1, 0, 0, 0
    are then used).

    Attributes:
        name: `ObjectName`.
        design_flow: m³/s.
        schedule: The schedule's name, or `None`.
        constant: Constant term coefficient.
        temperature: Temperature term coefficient.
        velocity: Velocity term coefficient.
        velocity_squared: Velocity squared term coefficient.
        coefficients_found: Whether the coefficients were read from the model.
    """

    name: str
    design_flow: float
    schedule: str | None
    constant: float = 1.0
    temperature: float = 0.0
    velocity: float = 0.0
    velocity_squared: float = 0.0
    coefficients_found: bool = True


ControlType = Literal[1, 2, 3, 4]
"""A thermostat control type: 1 single heating, 2 single cooling, 3 single heating or cooling, 4 dual."""

_CONTROL_TYPES: dict[str, ControlType] = {
    "ThermostatSetpoint:SingleHeating": 1,
    "ThermostatSetpoint:SingleCooling": 2,
    "ThermostatSetpoint:SingleHeatingOrCooling": 3,
    "ThermostatSetpoint:DualSetpoint": 4,
}


@dataclass(frozen=True)
class ThermostatControl:
    """One control of a `ZoneControl:Thermostat`, active when the control-type schedule equals `control_type`.

    Attributes:
        control_type: The control-type value that activates it.
        object_type: Its `ThermostatSetpoint:*` object type.
        name: The setpoint object's name.
        heating_schedule: Its heating setpoint schedule, or `None` when it does not heat.
        cooling_schedule: Its cooling setpoint schedule, or `None` when it does not cool.
    """

    control_type: ControlType
    object_type: str
    name: str
    heating_schedule: str | None
    cooling_schedule: str | None


@dataclass(frozen=True)
class ThermostatRecord:
    """A zone's thermostat (research R10).

    Attributes:
        name: The `ZoneControl:Thermostat`'s name.
        control_type_schedule: The control-type schedule's name.
        heating_schedule: The heating setpoint schedule of the first control that heats, or `None`.
        cooling_schedule: The cooling setpoint schedule of the first control that cools, or `None`.
        controls: Every control, in the order of the thermostat's fields.
    """

    name: str
    control_type_schedule: str
    heating_schedule: str | None
    cooling_schedule: str | None
    controls: tuple[ThermostatControl, ...] = ()

    def setpoints(self, evaluate: Callable[[str], Profile]) -> tuple[Profile, Profile]:
        """Return the hourly heating and cooling setpoints, NaN where no control sets that mode.

        At each hour the control-type schedule selects the control whose `control_type` it
        equals (0 leaves the zone uncontrolled).

        Args:
            evaluate: Returns a schedule's hourly profile by name.

        Returns:
            The heating and cooling setpoints, °C.
        """
        control = np.asarray(evaluate(self.control_type_schedule), dtype=np.float64)
        heating = np.full(control.shape, np.nan)
        cooling = np.full(control.shape, np.nan)
        for item in self.controls:
            active = control == item.control_type
            if not active.any():
                continue
            if item.heating_schedule is not None:
                heating[active] = np.asarray(evaluate(item.heating_schedule), dtype=np.float64)[active]
            if item.cooling_schedule is not None:
                cooling[active] = np.asarray(evaluate(item.cooling_schedule), dtype=np.float64)[active]
        return heating, cooling

    def enabled(self, evaluate: Callable[[str], Profile]) -> dict[Mode, bool]:
        """Whether each mode's setpoint lies within `BAND` at some hour (research R8, R10).

        Args:
            evaluate: Returns a schedule's hourly profile by name.

        Returns:
            The modes the thermostat enables.
        """
        heating, cooling = self.setpoints(evaluate)
        low, high = BAND
        with np.errstate(invalid="ignore"):
            return {
                "heating": bool(((heating >= low) & (heating <= high)).any()),
                "cooling": bool(((cooling >= low) & (cooling <= high)).any()),
            }


@dataclass(frozen=True, eq=False)
class HotWaterRecord:
    """The part of one `WaterUse:Equipment` a zone's single copy uses (research R11).

    Attributes:
        equipment: The equipment's name.
        volume: Hot-water volume each hour for one copy of the zone, m³.
        target_temperature_schedule: The equipment's target-temperature schedule, or `None`.
        share: The fraction of the equipment's volume one copy receives (1 for equipment in the
            zone, divided by the zone's multiplier in EnergyPlus's own reporting; the
            occupant-hour share otherwise). Over every copy of every zone the shares sum to 1.
        allocated: `True` when the equipment has no zone and was allocated by occupant-hours.
    """

    equipment: str
    volume: Profile
    target_temperature_schedule: str | None
    share: float
    allocated: bool


def _zeros() -> Profile:
    return np.zeros(0, dtype=np.float64)


@dataclass(frozen=True)
class ZoneRecord:
    """One EnergyPlus zone, one copy, with everything reduction reads about it.

    Attributes:
        name: The zone's name, in the model's spelling.
        multiplier: `Zones.Multiplier * Zones.ListMultiplier` (FR-012).
        floor_area: `Zones.FloorArea` of one copy, m².
        min_z: `Zones.MinimumZ`, m (number of storeys, R6).
        volume: `Zones.Volume` of one copy, m³.
        surfaces: Heat-transfer surfaces and internal masses.
        gains: Installed internal gains.
        infiltration: Design infiltration (`NominalInfiltration`).
        ventilation: Design simple ventilation (`NominalVentilation`).
        outdoor_air: Mechanical outdoor air each hour for one copy, m³/s at standard density;
            zeros for a zone without HVAC equipment connections.
        outdoor_air_per_area: Design outdoor air per floor area from the zone's
            `DesignSpecification:OutdoorAir` (via `Sizing:Zone`), m³/s·m², per-zone flow and air
            changes included; 0 without one.
        outdoor_air_per_person: Design outdoor air per person, m³/s; 0 without one.
        thermostat: The zone's thermostat, or `None`.
        hot_water: Hot-water use attributed to the zone (R11).
        delivered: Run-period sensible heating and cooling delivered to one copy, J.
        space_type: The type of the zone's spaces when every one declares the same type.
        space_types: Each of the zone's declared spaces' types, sorted by space name.
        plenum: The zone is an `AirLoopHVAC:ReturnPlenum` or `AirLoopHVAC:SupplyPlenum`.
        part_of_total_area: `Zones.IsPartOfTotalArea`.
    """

    name: str
    multiplier: int
    floor_area: float
    min_z: float
    volume: float
    surfaces: tuple[SurfaceRecord, ...] = ()
    gains: tuple[GainRecord, ...] = ()
    infiltration: tuple[AirflowRecord, ...] = ()
    ventilation: tuple[AirflowRecord, ...] = ()
    outdoor_air: Profile = field(default_factory=_zeros, compare=False)
    outdoor_air_per_area: float = 0.0
    outdoor_air_per_person: float = 0.0
    thermostat: ThermostatRecord | None = None
    hot_water: tuple[HotWaterRecord, ...] = field(default=(), compare=False)
    delivered: Mapping[Mode, float] = field(default_factory=lambda: {"heating": 0.0, "cooling": 0.0})
    space_type: str | None = None
    space_types: tuple[str | None, ...] = ()
    plenum: bool = False
    part_of_total_area: bool = True

    def __hash__(self) -> int:
        """Hash by name: a zone's name is unique in a model."""
        return hash(self.name)


# --- Surfaces -------------------------------------------------------------------------------------


def surface_class(class_name: str, tilt: float, boundary: Boundary) -> SurfaceClass:
    """Classify a surface (research R6).

    A wall has a tilt within 60° to 120°, a roof below 60° and a floor above 120°. Windows facing
    the outdoors are `window`; any surface whose outside is another zone, itself (adiabatic) or
    other-side coefficients is `interior`.

    Args:
        class_name: EnergyPlus's `ClassName`.
        tilt: Degrees from horizontal facing up.
        boundary: The outside boundary condition.

    Returns:
        The class.
    """
    upper = class_name.upper()
    low, high = _WALL_TILT
    wall = low <= tilt <= high
    result: SurfaceClass
    if upper == _INTERNAL_MASS:
        result = "internal_mass"
    elif boundary == "ground":
        result = "ground_wall" if wall else "ground_floor"
    elif boundary != "outdoors":
        result = "interior"
    elif upper in _WINDOW_CLASSES:
        result = "window"
    elif wall:
        result = "exterior_wall"
    else:
        result = "roof" if tilt < low else "exposed_floor"
    return result


def _boundary(row: SurfaceRow) -> Boundary:
    code = row.exterior_boundary
    if code == _OUTDOORS:
        return "outdoors"
    if code in _GROUND:
        return "ground"
    if code == row.index:
        return "adiabatic"
    if code > 0:
        return "interzone"
    return "other"


@dataclass(frozen=True)
class _Envelope:
    u_factor: dict[str, float]
    shgc: dict[str, float]
    vt: dict[str, float]


def _tabular(results: SQLResult, table: str, column: str) -> dict[str, float]:
    try:
        rows = results.get_tabular_data(_ENVELOPE_SUMMARY, table, report_for="Entire Facility")
    except ResultLookupError:
        return {}
    values: dict[str, float] = {}
    for row in rows:
        if row.column_name != column:
            continue
        try:
            values[row.row_name.upper()] = row.as_float()
        except ValueError:
            continue
    return values


def _first(*sources: dict[str, float]) -> dict[str, float]:
    merged: dict[str, float] = {}
    for source in reversed(sources):
        merged.update(source)
    return merged


def _envelope_summary(results: SQLResult) -> _Envelope:
    film = "U-Factor with Film"
    return _Envelope(
        u_factor=_first(
            _tabular(results, "Opaque Exterior", film),
            _tabular(results, "Opaque Interior", film),
            _tabular(results, "Exterior Door", film),
            _tabular(results, "Interior Door", film),
            _tabular(results, "Exterior Fenestration", "Assembly U-Factor"),
            _tabular(results, "Exterior Fenestration", "Glass U-Factor"),
            _tabular(results, "Interior Fenestration", "Glass U-Factor"),
        ),
        shgc=_first(
            _tabular(results, "Exterior Fenestration", "Assembly SHGC"),
            _tabular(results, "Exterior Fenestration", "Glass SHGC"),
            _tabular(results, "Interior Fenestration", "Glass SHGC"),
        ),
        vt=_first(
            _tabular(results, "Exterior Fenestration", "Assembly Visible Transmittance"),
            _tabular(results, "Exterior Fenestration", "Glass Visible Transmittance"),
            _tabular(results, "Interior Fenestration", "Glass Visible Transmittance"),
        ),
    )


def _layers(results: SQLResult) -> dict[int, tuple[LayerRecord, ...]]:
    materials: dict[int, MaterialRow] = {m.index: m for m in read_materials(results)}
    layers: dict[int, list[LayerRecord]] = {}
    for row in read_construction_layers(results):
        material = materials[row.material_index]
        layers.setdefault(row.construction_index, []).append(
            LayerRecord(
                material=material.name,
                thickness=material.thickness,
                conductivity=material.conductivity,
                density=material.density,
                specific_heat=material.specific_heat,
                resistance=material.resistance,
                resistance_only=material.resistance_only,
            )
        )
    return {index: tuple(items) for index, items in layers.items()}


def _surfaces(results: SQLResult, zone_names: Mapping[int, str]) -> dict[int, tuple[SurfaceRecord, ...]]:
    rows = read_surfaces(results)
    by_index = {row.index: row for row in rows}
    constructions: dict[int, ConstructionRow] = {c.index: c for c in read_constructions(results)}
    layers = _layers(results)
    envelope = _envelope_summary(results)
    surfaces: dict[int, list[SurfaceRecord]] = {}
    for row in rows:
        if row.zone_index is None or not (row.heat_transfer or row.class_name.upper() == _INTERNAL_MASS):
            continue
        boundary = _boundary(row)
        adjacent: str | None = None
        if boundary == "interzone":
            other = by_index.get(row.exterior_boundary)
            if other is not None and other.zone_index is not None:
                adjacent = zone_names.get(other.zone_index)
        construction = constructions.get(row.construction_index) if row.construction_index is not None else None
        construction_layers = layers.get(construction.index, ()) if construction is not None else ()
        is_window = construction.type_is_window if construction is not None else False
        key = row.name.upper()
        u_source: Literal["envelope_summary", "constructions"] = "envelope_summary"
        u_factor = envelope.u_factor.get(key)
        if u_factor is None:
            u_source = "constructions"
            u_factor = _with_films(construction, boundary)
        windowish = row.class_name.upper() in _WINDOW_CLASSES
        surfaces.setdefault(row.zone_index, []).append(
            SurfaceRecord(
                name=row.name,
                surface_class=surface_class(row.class_name, row.tilt, boundary),
                class_name=row.class_name,
                area=row.area,
                azimuth=row.azimuth,
                tilt=row.tilt,
                boundary=boundary,
                adjacent_zone=adjacent,
                construction=construction.name if construction is not None else None,
                u_factor=u_factor,
                u_source=u_source,
                heat_capacity=0.0 if is_window else sum(layer.heat_capacity for layer in construction_layers),
                layers=construction_layers,
                base_surface=by_index[row.base_surface_index].name
                if row.base_surface_index is not None
                and row.base_surface_index != row.index
                and row.base_surface_index in by_index
                else None,
                shgc=envelope.shgc.get(key) if windowish else None,
                visible_transmittance=envelope.vt.get(key) if windowish else None,
            )
        )
    return {index: tuple(items) for index, items in surfaces.items()}


def _with_films(construction: ConstructionRow | None, boundary: Boundary) -> float:
    if construction is None or construction.u_value <= 0.0:
        return 0.0
    if construction.type_is_window:
        return construction.u_value
    outside = _R_OUTSIDE if boundary == "outdoors" else _R_INSIDE
    return 1.0 / (1.0 / construction.u_value + _R_INSIDE + outside)


# --- Gains and airflow ----------------------------------------------------------------------------


def _gain(row: NominalLoadRow) -> GainRecord:
    return GainRecord(
        kind=row.kind,
        name=row.object_name,
        design_level=row.design_level,
        schedule=row.schedule_name,
        fraction_radiant=row.fraction_radiant,
        fraction_latent=row.fraction_latent,
        fraction_lost=row.fraction_lost,
        fraction_return_air=row.fraction_return_air,
    )


_Coefficients = tuple[float, float, float, float]


def _coefficient(value: float | None, default: float) -> float:
    return default if value is None else float(value)


def _infiltration_coefficients(doc: IDFDocumentSince22_1) -> dict[str, _Coefficients]:
    return {
        obj.name.upper(): (
            _coefficient(obj.constant_term_coefficient, 1.0),
            _coefficient(obj.temperature_term_coefficient, 0.0),
            _coefficient(obj.velocity_term_coefficient, 0.0),
            _coefficient(obj.velocity_squared_term_coefficient, 0.0),
        )
        for obj in doc["ZoneInfiltration:DesignFlowRate"]
    }


def _ventilation_coefficients(doc: IDFDocumentSince22_1) -> dict[str, _Coefficients]:
    return {
        obj.name.upper(): (
            _coefficient(obj.constant_term_coefficient, 1.0),
            _coefficient(obj.temperature_term_coefficient, 0.0),
            _coefficient(obj.velocity_term_coefficient, 0.0),
            _coefficient(obj.velocity_squared_term_coefficient, 0.0),
        )
        for obj in doc["ZoneVentilation:DesignFlowRate"]
    }


def _airflow(row: NominalInfiltrationRow, coefficients: Mapping[str, _Coefficients]) -> AirflowRecord:
    name = row.object_name.upper()
    found = coefficients.get(name)
    if found is None:
        # A ZoneList or SpaceList object: EnergyPlus names each copy "<ZONE> <OBJECT>".
        found = next((value for key, value in coefficients.items() if name.endswith(" " + key)), None)
    constant, temperature, velocity, squared = found or (1.0, 0.0, 0.0, 0.0)
    return AirflowRecord(
        name=row.object_name,
        design_flow=row.design_level,
        schedule=row.schedule_name,
        constant=constant,
        temperature=temperature,
        velocity=velocity,
        velocity_squared=squared,
        coefficients_found=found is not None,
    )


# --- Model lookups --------------------------------------------------------------------------------


def _zone_lists(doc: IDFDocumentSince22_1) -> dict[str, tuple[str, ...]]:
    return {
        zone_list.name.casefold(): tuple(group.zone_name.casefold() for group in zone_list.zones)
        for zone_list in doc["ZoneList"]
    }


def _expand(name: str, zone_lists: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    key = name.casefold()
    return zone_lists.get(key, (key,))


def _setpoint_schedules(doc: IDFDocumentSince22_1, object_type: str, name: str) -> tuple[str | None, str | None]:
    """Return a setpoint object's (heating, cooling) schedule names, dispatching on its type (R18)."""
    found: dict[str, tuple[str | None, str | None]]
    match object_type:
        case "ThermostatSetpoint:SingleHeating":
            found = {o.name.casefold(): (o.setpoint_temperature_schedule_name, None) for o in doc[object_type]}
        case "ThermostatSetpoint:SingleCooling":
            found = {o.name.casefold(): (None, o.setpoint_temperature_schedule_name) for o in doc[object_type]}
        case "ThermostatSetpoint:SingleHeatingOrCooling":
            found = {
                o.name.casefold(): (o.setpoint_temperature_schedule_name, o.setpoint_temperature_schedule_name)
                for o in doc[object_type]
            }
        case "ThermostatSetpoint:DualSetpoint":
            found = {
                o.name.casefold(): (
                    o.heating_setpoint_temperature_schedule_name,
                    o.cooling_setpoint_temperature_schedule_name,
                )
                for o in doc[object_type]
            }
        case _:
            found = {}
    return found.get(name.casefold(), (None, None))


def _thermostats(doc: IDFDocumentSince22_1, zone_lists: Mapping[str, tuple[str, ...]]) -> dict[str, ThermostatRecord]:
    records: dict[str, ThermostatRecord] = {}
    for thermostat in doc.zone_control_thermostats:
        pairs = (
            (thermostat.control_1_object_type, thermostat.control_1_name),
            (thermostat.control_2_object_type, thermostat.control_2_name),
            (thermostat.control_3_object_type, thermostat.control_3_name),
            (thermostat.control_4_object_type, thermostat.control_4_name),
        )
        controls: list[ThermostatControl] = []
        for object_type, name in pairs:
            if object_type is None or not name:
                continue
            heating, cooling = _setpoint_schedules(doc, object_type, name)
            controls.append(ThermostatControl(_CONTROL_TYPES[object_type], object_type, name, heating, cooling))
        record = ThermostatRecord(
            name=thermostat.name,
            control_type_schedule=thermostat.control_type_schedule_name,
            heating_schedule=next((c.heating_schedule for c in controls if c.heating_schedule), None),
            cooling_schedule=next((c.cooling_schedule for c in controls if c.cooling_schedule), None),
            controls=tuple(controls),
        )
        for zone in _expand(thermostat.zone_or_zonelist_name, zone_lists):
            records.setdefault(zone, record)
    return records


@dataclass(frozen=True)
class _OutdoorAirSpec:
    method: str
    per_person: float
    per_area: float
    per_zone: float
    air_changes: float


def _outdoor_air_specs(
    doc: IDFDocumentSince22_1, zone_lists: Mapping[str, tuple[str, ...]]
) -> dict[str, _OutdoorAirSpec]:
    specs: dict[str, _OutdoorAirSpec] = {}
    for obj in doc["DesignSpecification:OutdoorAir"]:
        specs[obj.name.casefold()] = _OutdoorAirSpec(
            method=obj.outdoor_air_method or "Flow/Person",
            per_person=_coefficient(obj.outdoor_air_flow_per_person, _DEFAULT_OA_PER_PERSON),
            per_area=_coefficient(obj.outdoor_air_flow_per_zone_floor_area, 0.0),
            per_zone=_coefficient(obj.outdoor_air_flow_per_zone, 0.0),
            air_changes=_coefficient(obj.outdoor_air_flow_air_changes_per_hour, 0.0),
        )
    by_zone: dict[str, _OutdoorAirSpec] = {}
    for sizing in doc["Sizing:Zone"]:
        name = sizing.design_specification_outdoor_air_object_name
        spec = specs.get(name.casefold()) if name else None
        if spec is None:
            continue
        for zone in _expand(sizing.zone_or_zonelist_name, zone_lists):
            by_zone.setdefault(zone, spec)
    return by_zone


def _design_outdoor_air(spec: _OutdoorAirSpec | None, floor_area: float, volume: float) -> tuple[float, float]:
    """Return (per area, per person) for a zone; per-zone flow and air changes count per area."""
    if spec is None:
        return 0.0, 0.0
    method = spec.method.casefold()
    combined = method in {"sum", "maximum"}
    per_person = spec.per_person if combined or method == "flow/person" else 0.0
    per_area = spec.per_area if combined or method == "flow/area" else 0.0
    if floor_area > 0.0:
        if combined or method == "flow/zone":
            per_area += spec.per_zone / floor_area
        if combined or method == "airchanges/hour":
            per_area += spec.air_changes * volume / 3600.0 / floor_area
    return per_area, per_person


def _space_types(doc: IDFDocumentSince22_1) -> dict[str, tuple[str | None, ...]]:
    spaces: dict[str, list[tuple[str, str | None]]] = {}
    for space in doc.spaces:
        declared = space.space_type or None
        spaces.setdefault(space.zone_name.casefold(), []).append((space.name, declared))
    return {zone: tuple(kind for _, kind in sorted(items, key=lambda item: item[0])) for zone, items in spaces.items()}


def _agreed(types: Sequence[str | None]) -> str | None:
    distinct = set(types)
    if len(distinct) != 1:
        return None
    return next(iter(distinct))


def _plenums(doc: IDFDocumentSince22_1) -> frozenset[str]:
    names = [obj.zone_name for obj in doc["AirLoopHVAC:ReturnPlenum"]]
    names += [obj.zone_name for obj in doc["AirLoopHVAC:SupplyPlenum"]]
    return frozenset(name.casefold() for name in names)


# --- Hourly results -------------------------------------------------------------------------------


def _series(results: SQLResult, requests: Iterable[tuple[str, str]]) -> dict[tuple[str, str], Profile]:
    """Read hourly series by (variable, key), upper-case; a series not reported is absent."""
    reported = {
        (info.name.casefold(), info.key_value.casefold())
        for info in results.list_variables()
        if not info.is_meter and info.frequency == _HOURLY
    }
    wanted = [(v, k) for v, k in dict.fromkeys(requests) if (v.casefold(), k.casefold()) in reported]
    if not wanted:
        return {}
    found = results.get_timeseries_many([(v, k, _HOURLY) for v, k in wanted])
    profiles: dict[tuple[str, str], Profile] = {}
    for (variable, key), series in zip(wanted, found, strict=True):
        profile = np.asarray(series.values, dtype=np.float64)
        profiles[variable.upper(), key.upper()] = profile
    return profiles


# --- Inventory ------------------------------------------------------------------------------------


def _occupant_hours(gains: Sequence[GainRecord], evaluate: Callable[[str], Profile]) -> float:
    total = 0.0
    for gain in gains:
        if gain.kind != "people" or gain.design_level == 0.0:
            continue
        profile = evaluate(gain.schedule) if gain.schedule else None
        total += gain.design_level * (float(np.sum(profile)) if profile is not None else 0.0)
    return total


_Row = TypeVar("_Row", NominalLoadRow, NominalInfiltrationRow)
_Record = TypeVar("_Record")


def _by_zone(rows: Iterable[_Row], make: Callable[[_Row], _Record]) -> dict[int, tuple[_Record, ...]]:
    grouped: dict[int, list[_Record]] = {}
    for row in rows:
        grouped.setdefault(row.zone_index, []).append(make(row))
    return {index: tuple(items) for index, items in grouped.items()}


def _hot_water(
    sources: SourceData,
    zone_rows: Sequence[ZoneRow],
    gains: Mapping[int, Sequence[GainRecord]],
    get: Callable[[str, str], Profile],
    evaluate: Callable[[str], Profile],
) -> dict[int, list[HotWaterRecord]]:
    """Attribute each `WaterUse:Equipment` to zones (R11), per copy of each zone."""
    multipliers = {row.index: row.multiplier * row.list_multiplier for row in zone_rows}
    index_by_name = {row.name.casefold(): row.index for row in zone_rows}
    hot_water: dict[int, list[HotWaterRecord]] = {}
    zoneless: list[tuple[str, Profile, str | None]] = []
    for item in sources.model.water_use_equipments:
        volume = get(_HOT_WATER_VARIABLE, item.name)
        target = item.target_temperature_schedule_name or None
        zone_index = index_by_name.get(item.zone_name.casefold()) if item.zone_name else None
        if zone_index is None:
            zoneless.append((item.name, volume, target))
            continue
        # EnergyPlus reports a zoned equipment's volume with the zone's multipliers applied.
        record = HotWaterRecord(item.name, volume / multipliers[zone_index], target, 1.0, allocated=False)
        hot_water.setdefault(zone_index, []).append(record)
    if not zoneless:
        return hot_water
    weights = {row.index: _occupant_hours(gains.get(row.index, ()), evaluate) for row in zone_rows}
    if sum(weights[i] * multipliers[i] for i in weights) <= 0.0:
        weights = {row.index: row.floor_area if row.is_part_of_total_area else 0.0 for row in zone_rows}
    total = sum(weights[i] * multipliers[i] for i in weights)
    for name, volume, target in zoneless:
        for row in zone_rows:
            share = weights[row.index] / total if total > 0.0 else 0.0
            if share > 0.0:
                hot_water.setdefault(row.index, []).append(
                    HotWaterRecord(name, volume * share, target, share, allocated=True)
                )
    return hot_water


def _hourly_getter(sources: SourceData, zone_rows: Sequence[ZoneRow]) -> Callable[[str, str], Profile]:
    """Read every hourly series the inventory needs in one scan; a series not reported reads as zeros."""
    requests: list[tuple[str, str]] = []
    for row in zone_rows:
        requests += [(_HEATING_VARIABLE, row.name), (_COOLING_VARIABLE, row.name), (_OUTDOOR_AIR_VARIABLE, row.name)]
    requests += [(_HOT_WATER_VARIABLE, item.name) for item in sources.model.water_use_equipments]
    series = _series(sources.results, requests)
    length = next((len(profile) for profile in series.values()), sources.run_period.calendar.hours)
    zeros = np.zeros(length, dtype=np.float64)
    zeros.flags.writeable = False

    def get(variable: str, key: str) -> Profile:
        return series.get((variable.upper(), key.upper()), zeros)

    return get


def build_inventory(sources: SourceData, evaluate: Callable[[str], Profile] | None = None) -> tuple[ZoneRecord, ...]:
    """Build one `ZoneRecord` per zone, in `Zones` order, without applying any multiplier.

    Args:
        sources: The checked model and results.
        evaluate: Returns a schedule's hourly profile by name, used for occupant-hours (R11).
            Defaults to a `ScheduleEvaluator` on the run-period calendar.

    Returns:
        The zones.
    """
    doc = sources.model
    results = sources.results
    if evaluate is None:
        base = sources.model_path.parent if sources.model_path is not None else None
        evaluate = ScheduleEvaluator(doc, sources.run_period.calendar, base_path=base)

    zone_rows = read_zones(results)
    model_names = {zone.name.casefold(): zone.name for zone in doc.zones}
    names = {row.index: model_names.get(row.name.casefold(), row.name) for row in zone_rows}

    surfaces = _surfaces(results, names)
    gains = _by_zone(read_nominal_loads(results), _gain)
    infiltration_coefficients = _infiltration_coefficients(doc)
    infiltration = _by_zone(read_nominal_infiltration(results), lambda r: _airflow(r, infiltration_coefficients))
    ventilation_coefficients = _ventilation_coefficients(doc)
    ventilation = _by_zone(read_nominal_ventilation(results), lambda r: _airflow(r, ventilation_coefficients))

    zone_lists = _zone_lists(doc)
    thermostats = _thermostats(doc, zone_lists)
    outdoor_air_specs = _outdoor_air_specs(doc, zone_lists)
    space_types = _space_types(doc)
    plenums = _plenums(doc)
    get = _hourly_getter(sources, zone_rows)
    hot_water = _hot_water(sources, zone_rows, gains, get, evaluate)

    records: list[ZoneRecord] = []
    for row in zone_rows:
        name = names[row.index]
        key = name.casefold()
        multiplier = row.multiplier * row.list_multiplier
        per_area, per_person = _design_outdoor_air(outdoor_air_specs.get(key), row.floor_area, row.volume)
        types = space_types.get(key, ())
        records.append(
            ZoneRecord(
                name=name,
                multiplier=multiplier,
                floor_area=row.floor_area,
                min_z=row.minimum_z,
                volume=row.volume,
                surfaces=surfaces.get(row.index, ()),
                gains=gains.get(row.index, ()),
                infiltration=infiltration.get(row.index, ()),
                ventilation=ventilation.get(row.index, ()),
                # EnergyPlus reports mechanical ventilation with the zone's multipliers applied.
                outdoor_air=get(_OUTDOOR_AIR_VARIABLE, row.name) / multiplier,
                outdoor_air_per_area=per_area,
                outdoor_air_per_person=per_person,
                thermostat=thermostats.get(key),
                hot_water=tuple(hot_water.get(row.index, ())),
                delivered={
                    "heating": float(get(_HEATING_VARIABLE, row.name).sum()),
                    "cooling": float(get(_COOLING_VARIABLE, row.name).sum()),
                },
                space_type=_agreed(types) if types else None,
                space_types=types,
                plenum=key in plenums,
                part_of_total_area=row.is_part_of_total_area,
            )
        )
    return tuple(records)
