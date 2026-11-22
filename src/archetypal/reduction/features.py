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
  `Exterior Equipment`, summed over fuels (water excluded).

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
from pydantic import BaseModel, ConfigDict

from archetypal.reduction._sql_tables import (
    read_construction_layers,
    read_constructions,
    read_materials,
    read_surfaces,
    read_zones,
)

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
        "Deploys shades, blinds or switchable glazing by schedule or condition; windows keep their unshaded properties.",
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
)
"""EnergyPlus object types with an effect SBEM cannot hold, in report order (research R20)."""

_GJ = 1.0e9
_ENERGY_UNITS: dict[str, float] = {"J": 1.0, "kJ": 1.0e3, "MJ": 1.0e6, "GJ": _GJ, "kWh": 3.6e6, "kBtu": 1055.05585262}


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
    }


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


def _energy(results: SQLResult, object_type: str, names: tuple[str, ...]) -> float | None:
    if object_type == "Exterior:Lights":
        return _exterior_lights_energy(results, names)
    if object_type == "Exterior:FuelEquipment":
        return _exterior_equipment_energy(results)
    return None


# --- Public ----------------------------------------------------------------------------------------


def find_unsupported(source: SourceData) -> tuple[NotRepresented, ...]:
    """List every object of an `UNSUPPORTED_FEATURES` type found in the model (research R20).

    Args:
        source: The checked inputs of the reduction.

    Returns:
        One entry per object type present, in table order, with the objects' names, the zones
        they affect and, where the results give it, their annual energy in J.
    """
    readers = _readers(source.model, _Zones(source.model, source.results))
    entries: list[NotRepresented] = []
    for feature in UNSUPPORTED_FEATURES:
        found = readers[feature.object_type]()
        if not found:
            continue
        names = tuple(sorted(name for name, _ in found))
        energy = _energy(source.results, feature.object_type, names)
        entries.append(
            NotRepresented(
                feature=feature.feature,
                effect=feature.effect,
                object_type=feature.object_type,
                objects=names,
                affected_zones=tuple(sorted({zone for _, zones in found for zone in zones})),
                magnitude=energy,
                unit="J" if energy is not None else None,
                folded_into=feature.folded_into,
            )
        )
    return tuple(entries)
