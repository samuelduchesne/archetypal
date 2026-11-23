"""Features of the detailed model that SBEM cannot express (spec 002, research R20; FR-026).

FR-026 forbids silent drops: every feature of the detailed model the archetype cannot hold is
listed in the report's `not_represented[]`. This module holds

- `NotRepresented`, one entry of that list. The report (`report.py`) gathers entries from
  here and from the modules that fold a value into another parameter (per-orientation
  windows, the infiltration schedule, heat-recovery effectiveness, holidays);
- `UNSUPPORTED_FEATURES`, the explicit table of EnergyPlus object types whose effect SBEM
  cannot hold, each with what it does and the SBEM parameter its effect is folded into, or
  `None`;
- `find_unsupported(source)`, which lists every object of those types found in the model with
  the zones it affects and, where the results give it, its annual energy.

Every object type is read with a literal key through idfkit's typed interface (research R18):
no object-type strings are looked up at run time, so pyright checks every field read. Adding a
row to the table therefore means adding one reader to `_readers`; a test checks that both
agree.

Zone names are the model's spelling (`doc.zones`), as in `inventory.py`. A `Space` name
resolves to its zone; a surface name (shading base surface, window, pool floor) resolves
through the results' `Surfaces` table. Site and building shading and
`ZoneAirMassFlowConservation` affect every zone.

Annual energy comes from the results' tabular reports where they give it:

- `Exterior:Lights`: *Lighting Summary*, Exterior Lighting, per object `Consumption`;
- `Exterior:FuelEquipment`: *Annual Building Utility Performance Summary*, End Uses, row
  `Exterior Equipment`, summed over fuels (water excluded);
- `Daylighting:Controls`: the lighting energy daylight saved, which the archetype's undimmed
  lighting adds back. *Lighting Summary*, Interior Lighting, gives for each `Lights` object
  its `Consumption` and its `Scheduled Hours/Week` and `Full Load Hours/Week`; in a daylit
  zone the saving is `Consumption · (scheduled - full load) / full load`.

`Site:GroundTemperature:BuildingSurface` has no energy: its magnitude is the conductance of
the ground-contact surfaces it drives, W/K (`Surfaces` with a ground boundary, the nominal U of
`Constructions` with the inside film `envelope.FILMS` uses, EnergyPlus's nominal film: 0.1620212
m²K/W for floors, 0.1197548 otherwise; no outside film against the ground), counting every copy
of a multiplied zone.

Other types have no per-object energy in the tabular reports, so their magnitude is `None`.

Decision (spec gap): R20 lists "cooling towers serving process loads". Which loads a cooling
tower serves needs the plant-loop topology; the process load itself is `LoadProfile:Plant`,
which the table lists instead.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import cached_property
from typing import TYPE_CHECKING, Literal

from idfkit.exceptions import ResultLookupError
from idfkit.versioned import as_version
from pydantic import BaseModel, ConfigDict

from archetypal.reduction._sql_tables import (
    read_construction_layers,
    read_constructions,
    read_materials,
    read_surfaces,
    read_zones,
)
from archetypal.reduction.envelope import FILMS

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from idfkit.simulation import SQLResult
    from idfkit.versioned import IDFDocumentSince22_1

    from archetypal.reduction._sql_tables import SurfaceRow
    from archetypal.reduction.sources import SourceData

__all__ = [
    "UNSUPPORTED_FEATURES",
    "NotRepresented",
    "NotRepresentedSource",
    "UnsupportedFeature",
    "find_unsupported",
]

NotRepresentedSource = Literal[
    "unsupported_features",
    "envelope",
    "airflow",
    "thermostats",
    "hotwater",
    "efficiency",
    "fans",
    "schedules",
    "to_sbem",
]
"""Where a `NotRepresented` entry comes from: R20's table, or the module that folds the value."""


class NotRepresented(BaseModel):
    """One entry of the report's `not_represented[]` (data-model.md, ReductionReport; FR-026).

    Attributes:
        feature: What is not represented, in words (`"Daylighting controls"`, `"Fan energy"`).
        effect: What it does in the detailed model.
        object_type: The EnergyPlus object type, when the entry comes from one.
        objects: The names of the objects found, sorted.
        affected_zones: The zones it affects, sorted (model spelling).
        affected_groups: The groups it affects, sorted; filled by the report once zones are
            grouped, empty before.
        magnitude: Its size, such as the annual energy, or `None` when the results do not give
            it.
        unit: The unit of `magnitude` (`"J"` for energy), or `None`.
        folded_into: The SBEM parameter its effect is folded into, or `None` when it is dropped.
        source: R20's table (`"unsupported_features"`) or the module that folded it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    feature: str
    effect: str
    object_type: str | None = None
    objects: tuple[str, ...] = ()
    affected_zones: tuple[str, ...] = ()
    affected_groups: tuple[str, ...] = ()
    magnitude: float | None = None
    unit: str | None = None
    folded_into: str | None = None
    source: NotRepresentedSource = "unsupported_features"


@dataclass(frozen=True)
class UnsupportedFeature:
    """One row of `UNSUPPORTED_FEATURES` (research R20).

    Attributes:
        object_type: The EnergyPlus object type.
        feature: The feature, in words.
        effect: What it does that SBEM cannot hold.
        folded_into: The SBEM parameter its effect is folded into, or `None`.
    """

    object_type: str
    feature: str
    effect: str
    folded_into: str | None = None


UNSUPPORTED_FEATURES: tuple[UnsupportedFeature, ...] = (
    UnsupportedFeature(
        "Daylighting:Controls",
        "Daylighting controls",
        "Dims electric lighting with daylight; the archetype's lighting follows the undimmed schedule.",
    ),
    UnsupportedFeature(
        "Daylighting:ReferencePoint",
        "Daylighting reference points",
        "Locates the illuminance sensors of daylighting controls.",
    ),
    UnsupportedFeature(
        "WindowShadingControl",
        "Window shading control",
        "Deploys shades, blinds or switchable glazing by schedule or condition; "
        "windows keep their unshaded properties.",
    ),
    UnsupportedFeature("WindowMaterial:Shade", "Window shades", "Shade layers that change window transmittance."),
    UnsupportedFeature("WindowMaterial:Blind", "Window blinds", "Slat blinds that change window transmittance."),
    UnsupportedFeature("Shading:Site", "Site shading", "Detached surfaces that shade the building."),
    UnsupportedFeature("Shading:Site:Detailed", "Site shading", "Detached surfaces that shade the building."),
    UnsupportedFeature("Shading:Building", "Building shading", "Surfaces that shade the building."),
    UnsupportedFeature("Shading:Building:Detailed", "Building shading", "Surfaces that shade the building."),
    UnsupportedFeature("Shading:Zone:Detailed", "Attached shading", "Surfaces attached to a zone that shade it."),
    UnsupportedFeature("Shading:Overhang", "Overhangs", "Overhangs above windows or doors."),
    UnsupportedFeature("Shading:Overhang:Projection", "Overhangs", "Overhangs above windows or doors."),
    UnsupportedFeature("Shading:Fin", "Fins", "Side fins beside windows or doors."),
    UnsupportedFeature("Shading:Fin:Projection", "Fins", "Side fins beside windows or doors."),
    UnsupportedFeature(
        "ZoneInfiltration:EffectiveLeakageArea",
        "Infiltration by effective leakage area",
        "Infiltration from an effective leakage area, driven by stack and wind (Sherman-Grimsrud); EnergyPlus "
        "reports no design flow for it, so the archetype's infiltration leaves it out.",
    ),
    UnsupportedFeature(
        "ZoneInfiltration:FlowCoefficient",
        "Infiltration by flow coefficient",
        "Infiltration from a flow coefficient and pressure exponent, driven by stack and wind (AIM-2); EnergyPlus "
        "reports no design flow for it, so the archetype's infiltration leaves it out.",
    ),
    UnsupportedFeature(
        "ElectricEquipment:ITE:AirCooled",
        "IT equipment",
        "Air-cooled IT equipment whose power depends on inlet temperature and load.",
    ),
    UnsupportedFeature(
        "SwimmingPool:Indoor",
        "Indoor swimming pool",
        "Pool water heating, evaporation and its latent gain to the zone.",
    ),
    UnsupportedFeature(
        "Refrigeration:Case", "Refrigerated cases", "Refrigerated display cases and their zone credits."
    ),
    UnsupportedFeature(
        "Refrigeration:WalkIn", "Walk-in coolers", "Walk-in coolers and their heat exchange with zones."
    ),
    UnsupportedFeature(
        "Refrigeration:CompressorRack",
        "Refrigeration compressor racks",
        "Compressor racks serving refrigerated cases, rejecting heat outdoors or to a zone.",
    ),
    UnsupportedFeature("Refrigeration:System", "Refrigeration systems", "Detailed refrigeration systems."),
    UnsupportedFeature(
        "Refrigeration:TranscriticalSystem", "Refrigeration systems", "Transcritical CO2 refrigeration systems."
    ),
    UnsupportedFeature("Refrigeration:SecondarySystem", "Refrigeration systems", "Secondary refrigeration loops."),
    UnsupportedFeature("Refrigeration:AirChiller", "Refrigeration air chillers", "Refrigerated air chillers."),
    UnsupportedFeature("Exterior:Lights", "Exterior lights", "Electricity for lights outside the building."),
    UnsupportedFeature("Exterior:FuelEquipment", "Exterior equipment", "Fuel use of equipment outside the building."),
    UnsupportedFeature("ZoneEarthtube", "Earth tubes", "Outdoor air pre-conditioned through buried pipes."),
    UnsupportedFeature(
        "LoadProfile:Plant",
        "Plant process loads",
        "Scheduled process loads on a plant loop, and the cooling towers or boilers that serve them.",
    ),
    UnsupportedFeature(
        "ZoneAirMassFlowConservation",
        "Zone air mass-flow conservation",
        "Balances zone mixing, return and infiltration flows.",
    ),
    UnsupportedFeature(
        "AirLoopHVAC",
        "Air-side control of central air systems",
        "Supplies air at a set or reset temperature, reheats it at the terminals and holds the "
        "economiser to the mixed-air setpoint and its limits; the archetype's ideal loads supply air "
        "only as cold or warm as each zone needs and economise up to the zone temperature, so the "
        "coil energy the efficiency divides differs.",
    ),
    UnsupportedFeature(
        "Site:GroundTemperature:BuildingSurface",
        "Ground temperatures",
        "Sets the temperature under the ground-contact surfaces; epinterface derives its own from the "
        "archetype's thermostat and the weather file.",
    ),
)
"""EnergyPlus object types with an effect SBEM cannot hold, in report order (research R20)."""

_GJ = 1.0e9
_GROUND_BOUNDARY = -1
"""`Surfaces.ExtBoundCond` of a surface against the ground (`Site:GroundTemperature:BuildingSurface`)."""
_INSIDE_FILM = {"Floor": FILMS["ground_floor"][0]}
_INSIDE_FILM_DEFAULT = FILMS["ground_wall"][0]
"""Inside surface resistances, m²K/W, of the ground classes of `envelope.FILMS` (no outside film)."""
_ENERGY_UNITS: dict[str, float] = {
    "J": 1.0,
    "kJ": 1.0e3,
    "MJ": 1.0e6,
    "GJ": _GJ,
    "kWh": 3.6e6,
    "kBtu": 1055.05585262e3,  # 1 Btu = 1055.05585262 J
}


# --- Zone resolution -------------------------------------------------------------------------------


class _Zones:
    """Resolves zone, space, surface and construction names to the model's zone names.

    The maps that read results tables are built on first use, so a model with no unsupported
    feature reads none of them.
    """

    def __init__(self, doc: IDFDocumentSince22_1, results: SQLResult) -> None:
        self._doc = doc
        self._results = results

    @cached_property
    def all(self) -> tuple[str, ...]:
        return tuple(sorted(zone.name for zone in self._doc.zones))

    @cached_property
    def _by_name(self) -> dict[str, str]:
        by_name = {zone.name.upper(): zone.name for zone in self._doc.zones}
        for space in self._doc.spaces:
            zone = by_name.get(space.zone_name.upper())
            if zone is not None:
                by_name.setdefault(space.name.upper(), zone)
        return by_name

    @cached_property
    def _surfaces(self) -> tuple[SurfaceRow, ...]:
        return read_surfaces(self._results)

    @cached_property
    def _surface_index(self) -> dict[str, int]:
        return {row.name.upper(): row.index for row in self._surfaces}

    @cached_property
    def _surface_zone(self) -> dict[int, str]:
        """Zone of every surface index; subsurfaces take their base surface's zone."""
        zone_rows = {row.index: self._by_name.get(row.name.upper(), row.name) for row in read_zones(self._results)}
        surface_zone = {row.index: zone_rows[row.zone_index] for row in self._surfaces if row.zone_index in zone_rows}
        for row in self._surfaces:
            if row.index not in surface_zone and row.base_surface_index in surface_zone:
                surface_zone[row.index] = surface_zone[row.base_surface_index]
        return surface_zone

    @cached_property
    def _construction_names(self) -> dict[int, str]:
        return {row.index: row.name.upper() for row in read_constructions(self._results)}

    @cached_property
    def _by_construction(self) -> dict[str, frozenset[str]]:
        found: dict[str, set[str]] = {}
        for row in self._surfaces:
            construction = self._construction_names.get(row.construction_index or 0)
            zone = self._surface_zone.get(row.index)
            if construction is not None and zone is not None:
                found.setdefault(construction, set()).add(zone)
        return {name: frozenset(zones) for name, zones in found.items()}

    @cached_property
    def _constructions_with_material(self) -> dict[str, frozenset[str]]:
        material_names = {row.index: row.name.upper() for row in read_materials(self._results)}
        found: dict[str, set[str]] = {}
        for layer in read_construction_layers(self._results):
            material = material_names.get(layer.material_index)
            construction = self._construction_names.get(layer.construction_index)
            if material is not None and construction is not None:
                found.setdefault(material, set()).add(construction)
        return {name: frozenset(names) for name, names in found.items()}

    @cached_property
    def ground_contact(self) -> dict[str, float]:
        """Conductance of each zone's ground-contact surfaces, W/K, over every copy of the zone."""
        u_values = {row.index: row.u_value for row in read_constructions(self._results)}
        multipliers = {
            self._by_name.get(row.name.upper(), row.name): row.multiplier * row.list_multiplier
            for row in read_zones(self._results)
        }
        found: dict[str, float] = {}
        for row in self._surfaces:
            if row.exterior_boundary != _GROUND_BOUNDARY or not row.heat_transfer:
                continue
            zone = self._surface_zone.get(row.index)
            u_value = u_values.get(row.construction_index or 0, 0.0)
            if zone is None or u_value <= 0.0:
                continue
            film = _INSIDE_FILM.get(row.class_name, _INSIDE_FILM_DEFAULT)
            found[zone] = found.get(zone, 0.0) + row.area * multipliers.get(zone, 1.0) / (1.0 / u_value + film)
        return found

    def zone(self, name: str | None) -> tuple[str, ...]:
        """The zone a zone or space name names."""
        zone = self._by_name.get(name.upper()) if name else None
        return (zone,) if zone is not None else ()

    def zones(self, names: Iterable[str | None]) -> tuple[str, ...]:
        """The zones several zone or space names name, sorted."""
        return tuple(sorted({zone for name in names for zone in self.zone(name)}))

    def surface(self, name: str | None) -> tuple[str, ...]:
        """The zone of a surface or subsurface."""
        if not name:
            return ()
        index = self._surface_index.get(name.upper())
        zone = self._surface_zone.get(index) if index is not None else None
        return (zone,) if zone is not None else ()

    def material(self, material: str) -> tuple[str, ...]:
        """The zones whose windows hold a material, directly or through a shading control."""
        constructions = self._constructions_with_material.get(material.upper(), frozenset())
        found = {zone for construction in constructions for zone in self._by_construction.get(construction, ())}
        for control in self._doc["WindowShadingControl"]:
            shaded = (control.construction_with_shading_name or "").upper()
            device = (control.shading_device_material_name or "").upper()
            if device == material.upper() or shaded in constructions:
                found.update(self.zone(control.zone_name))
        return tuple(sorted(found))


# --- Objects per type (literal keys only, research R18) --------------------------------------------

_Found = list[tuple[str, tuple[str, ...]]]
"""(object name, zones it affects) for every object of one type."""


def _readers(doc: IDFDocumentSince22_1, z: _Zones) -> dict[str, Callable[[], _Found]]:
    """One reader per `UNSUPPORTED_FEATURES` type, each with a literal key (research R18)."""
    return {
        "Daylighting:Controls": lambda: [(o.name, z.zone(o.zone_or_space_name)) for o in doc["Daylighting:Controls"]],
        "Daylighting:ReferencePoint": lambda: [
            (o.name, z.zone(o.zone_or_space_name)) for o in doc["Daylighting:ReferencePoint"]
        ],
        "WindowShadingControl": lambda: [(o.name, z.zone(o.zone_name)) for o in doc["WindowShadingControl"]],
        "WindowMaterial:Shade": lambda: [(o.name, z.material(o.name)) for o in doc["WindowMaterial:Shade"]],
        "WindowMaterial:Blind": lambda: [(o.name, z.material(o.name)) for o in doc["WindowMaterial:Blind"]],
        "Shading:Site": lambda: [(o.name, z.all) for o in doc["Shading:Site"]],
        "Shading:Site:Detailed": lambda: [(o.name, z.all) for o in doc["Shading:Site:Detailed"]],
        "Shading:Building": lambda: [(o.name, z.all) for o in doc["Shading:Building"]],
        "Shading:Building:Detailed": lambda: [(o.name, z.all) for o in doc["Shading:Building:Detailed"]],
        "Shading:Zone:Detailed": lambda: [
            (o.name, z.surface(o.base_surface_name)) for o in doc["Shading:Zone:Detailed"]
        ],
        "Shading:Overhang": lambda: [(o.name, z.surface(o.window_or_door_name)) for o in doc["Shading:Overhang"]],
        "Shading:Overhang:Projection": lambda: [
            (o.name, z.surface(o.window_or_door_name)) for o in doc["Shading:Overhang:Projection"]
        ],
        "Shading:Fin": lambda: [(o.name, z.surface(o.window_or_door_name)) for o in doc["Shading:Fin"]],
        "Shading:Fin:Projection": lambda: [
            (o.name, z.surface(o.window_or_door_name)) for o in doc["Shading:Fin:Projection"]
        ],
        "ZoneInfiltration:EffectiveLeakageArea": lambda: _leakage_area(doc, z),
        "ZoneInfiltration:FlowCoefficient": lambda: _flow_coefficient(doc, z),
        "ElectricEquipment:ITE:AirCooled": lambda: [
            (o.name, z.zone(o.zone_or_space_name)) for o in doc["ElectricEquipment:ITE:AirCooled"]
        ],
        "SwimmingPool:Indoor": lambda: [(o.name, z.surface(o.surface_name)) for o in doc["SwimmingPool:Indoor"]],
        "Refrigeration:Case": lambda: [(o.name, z.zone(o.zone_name)) for o in doc["Refrigeration:Case"]],
        "Refrigeration:WalkIn": lambda: [
            (o.name, z.zones(group.zone_name for group in o.zone_data)) for o in doc["Refrigeration:WalkIn"]
        ],
        "Refrigeration:CompressorRack": lambda: [
            (o.name, z.zone(o.heat_rejection_zone_name)) for o in doc["Refrigeration:CompressorRack"]
        ],
        "Refrigeration:System": lambda: [(o.name, ()) for o in doc["Refrigeration:System"]],
        "Refrigeration:TranscriticalSystem": lambda: [(o.name, ()) for o in doc["Refrigeration:TranscriticalSystem"]],
        "Refrigeration:SecondarySystem": lambda: [(o.name, ()) for o in doc["Refrigeration:SecondarySystem"]],
        "Refrigeration:AirChiller": lambda: [(o.name, ()) for o in doc["Refrigeration:AirChiller"]],
        "Exterior:Lights": lambda: [(o.name, ()) for o in doc["Exterior:Lights"]],
        "Exterior:FuelEquipment": lambda: [(o.name, ()) for o in doc["Exterior:FuelEquipment"]],
        "ZoneEarthtube": lambda: [(o.name, z.zone(o.zone_name)) for o in doc["ZoneEarthtube"]],
        "LoadProfile:Plant": lambda: [(o.name, ()) for o in doc["LoadProfile:Plant"]],
        "ZoneAirMassFlowConservation": lambda: [
            ("ZoneAirMassFlowConservation", z.all) for _ in doc["ZoneAirMassFlowConservation"]
        ],
        "AirLoopHVAC": lambda: _air_loops(doc, z),
        "Site:GroundTemperature:BuildingSurface": lambda: [
            ("Site:GroundTemperature:BuildingSurface", tuple(sorted(z.ground_contact)))
            for _ in doc["Site:GroundTemperature:BuildingSurface"]
        ],
    }


# 22.2 renamed the infiltration objects' Zone Name to Zone or Space Name.
_SPACE_INFILTRATION = "22.2"


def _leakage_area(doc: IDFDocumentSince22_1, z: _Zones) -> _Found:
    if doc.version < (22, 2, 0):
        older = as_version(doc, before=_SPACE_INFILTRATION)["ZoneInfiltration:EffectiveLeakageArea"]
        return [(o.name, z.zone(o.zone_name)) for o in older]
    newer = as_version(doc, since=_SPACE_INFILTRATION)["ZoneInfiltration:EffectiveLeakageArea"]
    return [(o.name, z.zone(o.zone_or_space_name)) for o in newer]


def _flow_coefficient(doc: IDFDocumentSince22_1, z: _Zones) -> _Found:
    if doc.version < (22, 2, 0):
        older = as_version(doc, before=_SPACE_INFILTRATION)["ZoneInfiltration:FlowCoefficient"]
        return [(o.name, z.zone(o.zone_name)) for o in older]
    newer = as_version(doc, since=_SPACE_INFILTRATION)["ZoneInfiltration:FlowCoefficient"]
    return [(o.name, z.zone(o.zone_or_space_name)) for o in newer]


def _air_loops(doc: IDFDocumentSince22_1, z: _Zones) -> _Found:
    # Imported here: `airflow` is a domain module, only needed when the model has air loops.
    from archetypal.reduction.airflow import air_loop_zones  # noqa: PLC0415

    if not doc["AirLoopHVAC"]:
        return []
    return [(name, z.zones(served)) for name, served in air_loop_zones(doc).items()]


# --- Annual energy ---------------------------------------------------------------------------------


def _to_joules(value: float, units: str) -> float | None:
    factor = _ENERGY_UNITS.get(units.strip())
    return value * factor if factor is not None else None


def _exterior_lights_energy(results: SQLResult, names: Iterable[str]) -> float | None:
    try:
        rows = results.get_tabular_data("LightingSummary", "Exterior Lighting", report_for="Entire Facility")
    except ResultLookupError:
        return None
    wanted = {name.upper() for name in names}
    total = 0.0
    found = False
    for row in rows:
        if row.column_name != "Consumption" or row.row_name.upper() not in wanted:
            continue
        try:
            joules = _to_joules(row.as_float(), row.units or "GJ")
        except ValueError:
            continue
        if joules is not None:
            total += joules
            found = True
    return total if found else None


def _exterior_equipment_energy(results: SQLResult) -> float | None:
    try:
        rows = results.get_tabular_data(
            "AnnualBuildingUtilityPerformanceSummary", "End Uses", report_for="Entire Facility"
        )
    except ResultLookupError:
        return None
    total = 0.0
    found = False
    for row in rows:
        if row.row_name != "Exterior Equipment" or row.column_name == "Water":
            continue
        try:
            joules = _to_joules(row.as_float(), row.units)
        except ValueError:
            continue
        if joules is not None:
            total += joules
            found = True
    return total if found else None


def _daylighting_saving(results: SQLResult, z: _Zones, zones: Iterable[str]) -> float | None:
    """Lighting energy daylight saved in `zones`, J: `Consumption · (scheduled - full load) / full load`."""
    try:
        rows = results.get_tabular_data("LightingSummary", "Interior Lighting", report_for="Entire Facility")
    except ResultLookupError:
        return None
    daylit = set(zones)
    columns: dict[str, dict[str, tuple[str, str]]] = {}
    for row in rows:
        columns.setdefault(row.row_name, {})[row.column_name] = (str(row.value), row.units or "")
    total = 0.0
    found = False
    for values in columns.values():
        zone = z.zone(values.get("Zone Name", ("", ""))[0].strip())
        if not zone or zone[0] not in daylit:
            continue
        try:
            consumption, units = float(values["Consumption"][0]), values["Consumption"][1] or "GJ"
            scheduled = float(values["Scheduled Hours/Week"][0])
            full_load = float(values["Full Load Hours/Week"][0])
        except (KeyError, ValueError):
            continue
        joules = _to_joules(consumption, units)
        if joules is None or full_load <= 0.0:
            continue
        total += joules * max(scheduled - full_load, 0.0) / full_load
        found = True
    return total if found else None


def _magnitude(
    results: SQLResult, z: _Zones, object_type: str, names: tuple[str, ...], zones: tuple[str, ...]
) -> tuple[float | None, str | None]:
    """An entry's magnitude and its unit, or `(None, None)` when the results do not give it."""
    value: float | None = None
    if object_type == "Exterior:Lights":
        value = _exterior_lights_energy(results, names)
    elif object_type == "Exterior:FuelEquipment":
        value = _exterior_equipment_energy(results)
    elif object_type == "Daylighting:Controls":
        value = _daylighting_saving(results, z, zones)
    elif object_type == "Site:GroundTemperature:BuildingSurface":
        conductance = sum(z.ground_contact.get(zone, 0.0) for zone in zones)
        return (conductance, "W/K") if conductance > 0.0 else (None, None)
    return (value, "J") if value is not None else (None, None)


# --- Public ----------------------------------------------------------------------------------------


def find_unsupported(source: SourceData) -> tuple[NotRepresented, ...]:
    """List every object of an `UNSUPPORTED_FEATURES` type found in the model (research R20).

    Args:
        source: The checked inputs of the reduction.

    Returns:
        One entry per object type present, in table order, with the objects' names, the zones
        they affect and, where the results give it, their magnitude (annual energy in J; the
        ground temperatures' conductance in W/K).
    """
    zones = _Zones(source.model, source.results)
    readers = _readers(source.model, zones)
    entries: list[NotRepresented] = []
    for feature in UNSUPPORTED_FEATURES:
        found = readers[feature.object_type]()
        if not found:
            continue
        names = tuple(sorted(name for name, _ in found))
        affected = tuple(sorted({zone for _, found_zones in found for zone in found_zones}))
        magnitude, unit = _magnitude(source.results, zones, feature.object_type, names, affected)
        entries.append(
            NotRepresented(
                feature=feature.feature,
                effect=feature.effect,
                object_type=feature.object_type,
                objects=names,
                affected_zones=affected,
                magnitude=magnitude,
                unit=unit,
                folded_into=feature.folded_into,
            )
        )
    return tuple(entries)
