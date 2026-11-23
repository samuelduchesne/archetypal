"""The envelope domain: surface classes, orientation, conserved totals and SBEM assemblies (spec 002, R6).

What a group conserves (FR-016, FR-017, FR-024)
------------------------------------------------
Each heat-transfer surface of a zone falls in one class (`envelope_class`), from inventory's
`surface_class` (tilt and outside boundary, R6): `exterior_wall`, `roof`, `exposed_floor`,
`ground_floor`, `ground_wall`, and the interior classes `partition` (walls) and
`floor_ceiling` (floors and ceilings, including adiabatic ones). Windows are kept apart, by
orientation; internal masses are kept as one capacity and one area.

Per class a zone contributes, for one copy:

- `area` (Σ net area) and `ua` (Σ area · U with films, the Envelope Summary's U);
- `capacity_inner` and `capacity_outer`: each construction is split at its most resistive
  layer; the capacity of the layers inside it, plus half of its own, is inner, the rest outer
  (`capacity_split`). Splitting the dividing layer in half keeps inner + outer equal to the
  construction's total capacity, so FR-017 holds;
- `area_by_orientation`: area per 45° sector of azimuth (`orientation`), for non-horizontal
  surfaces only (a flat roof faces no direction).

Windows conserve area, UA, Σ A·SHGC and Σ A·VT per orientation. A window without an SHGC or
visible transmittance in the results is refused rather than given a made-up one.

Excluded zones (FR-013)
-----------------------
A plenum's or attic's exterior envelope (opaque outdoor and ground classes, and windows) is
carried by the conditioned zones it shares interzone surfaces with, in proportion to the
shared area, counted on the excluded zone's side. Multipliers are respected: target `Z`
receives, per copy, `share · m_source / m_Z` of the source's one-copy envelope, so after
`GroupLedger.from_zone` applies `m_Z`, every target together carries `m_source` copies.
An excluded zone touching no conditioned zone passes its envelope on through the excluded
zones it touches (weighted by shared area); one touching none at all is spread over the
conditioned zones by floor area (multipliers applied). Interior surfaces and internal mass of
an excluded zone are not envelope and are not carried. Which roles are carried is
`ASSIGNED_ROLES` (`excluded` and `attic`); basements map to SBEM's basement assumptions and are
left out unless asked for.

That assignment needs every zone, so it is done by `EnvelopeHook(zones)`, a ledger hook built
with the whole building and passed to `GroupLedger.from_zone(..., hooks=[...])` in place of
this module's `ledger_fields`, which returns a zone's own envelope only. Each carried part is
recorded as an `EnvelopeAssignment` in the ledger's `excluded_envelope`; window assignments
are carried but not recorded, since `EnvelopeClass` has no window class.

SBEM assemblies
---------------
`equivalent_construction(totals, envelope_class)` turns a class's totals into a three-layer
`ConstructionAssemblyComponent`, outside first: an outer mass layer, an insulation layer and
an inner mass layer. With the films of `FILMS`, its U is exactly `ua / area`; split by the same
rule as the sources (the insulation is the most resistive layer), its capacities per area are
exactly `capacity_inner / area` and `capacity_outer / area`. epinterface's assemblies carry
layers only and epinterface defines no surface films; `FILMS` are therefore this module's:
the nominal films EnergyPlus used to compute the Envelope Summary's U that `ua` comes from (no
outside film against the ground, an inside film on both faces of interior classes), so the
equivalent layers have the source layers' resistance. A side without any capacity gets
`MIN_CAPACITY` (a layer must have mass in EnergyPlus); that is the one case where the
capacities are not reproduced exactly.

`internal_mass_construction` and `window_construction` give the internal-mass assembly and the
simple glazing of R6.
"""

from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, NamedTuple

from epinterface.geometry import orientation_of
from epinterface.sbem.components.envelope import (
    ConstructionAssemblyComponent,
    ConstructionLayerComponent,
    GlazingConstructionSimpleComponent,
)
from epinterface.sbem.components.materials import (
    ConstructionComponentSurfaceType,
    ConstructionMaterialComponent,
    ConstructionMaterialType,
)

from archetypal.reduction.ledger import EnvelopeAssignment, EnvelopeClass, EnvelopeTotals, Orientation, WindowTotals

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    from archetypal.reduction.classify import ClassifiedZone, Role
    from archetypal.reduction.inventory import SurfaceRecord, ZoneRecord
    from archetypal.reduction.schedules import ScheduleEvaluator

__all__ = [
    "ASSEMBLY_TYPES",
    "ASSIGNED_ROLES",
    "EXTERIOR_CLASSES",
    "FILMS",
    "MIN_CAPACITY",
    "CapacitySplit",
    "EnvelopeHook",
    "ZoneEnvelope",
    "assembly_capacities",
    "assembly_u_factor",
    "capacity_split",
    "envelope_class",
    "equivalent_construction",
    "internal_mass_construction",
    "ledger_fields",
    "orientation",
    "window_construction",
    "zone_envelope",
]

FILMS: Mapping[EnvelopeClass, tuple[float, float]] = {
    "exterior_wall": (0.1197548, 0.0299387),
    "roof": (0.1074271, 0.0299387),
    "exposed_floor": (0.1620212, 0.0299387),
    "ground_floor": (0.1620212, 0.0),
    "ground_wall": (0.1197548, 0.0),
    "partition": (0.1197548, 0.1197548),
    "floor_ceiling": (0.1074271, 0.1620212),
}
"""Inside and outside surface resistances per class, m²K/W: the films EnergyPlus's Envelope
Summary uses for 'U-Factor with Film' (ASHRAE 90.1 nominal films, as in EnergyPlus's
`ComputeNominalUwithConvCoeffs`: inside 0.1197548 for walls, 0.1074271 for roofs and ceilings,
0.1620212 for floors; outside 0.0299387 outdoors, none against the ground; an inside film on
both faces of interior classes). The source U is read from that report, so subtracting the same
films recovers the source layers' resistance."""

ASSEMBLY_TYPES: Mapping[EnvelopeClass, ConstructionComponentSurfaceType] = {
    "exterior_wall": "Facade",
    "roof": "FlatRoof",
    "exposed_floor": "ExternalFloor",
    "ground_floor": "GroundSlab",
    "ground_wall": "GroundWall",
    "partition": "Partition",
    "floor_ceiling": "FloorCeiling",
}
"""The SBEM assembly slot of each class (data-model.md, rule `envelope.equivalent`)."""

EXTERIOR_CLASSES: frozenset[EnvelopeClass] = frozenset({
    "exterior_wall",
    "roof",
    "exposed_floor",
    "ground_floor",
    "ground_wall",
})
"""The opaque classes of an excluded zone that conditioned zones carry (FR-013)."""

ASSIGNED_ROLES: frozenset[Role] = frozenset({"excluded", "attic"})
"""The roles whose envelope `EnvelopeHook` assigns to conditioned zones by default."""

MIN_CAPACITY = 1.0
"""Heat capacity given to a mass layer whose side has none, J/m²K."""

_WALL_TILT = (60.0, 120.0)
_HORIZONTAL_TOLERANCE = 1.0  # degrees: a surface this close to flat has no orientation
_MIN_THICKNESS = 0.001  # m
_MAX_THICKNESS = 0.9  # m, per layer; epinterface caps an assembly at 3 m
_MASS_DENSITY = 2000.0  # kg/m³
_MASS_CONDUCTIVITY = 1.8  # W/mK
_SPECIFIC_HEAT = 1000.0  # J/kgK
_INSULATION_DENSITY = 30.0  # kg/m³
_INSULATION_CONDUCTIVITY = 0.04  # W/mK
_MASS_SHARE_OF_RESISTANCE = 1.0 / 3.0  # mass layers take at most this share of the layer resistance
_SINGLE_GLAZING_U = 3.0  # W/m²K: at or above, a window is called single glazing
_DOUBLE_GLAZING_U = 1.2  # W/m²K: at or above (and below single), double glazing


# --- classes and orientation -----------------------------------------------------------------


def envelope_class(surface: SurfaceRecord) -> EnvelopeClass | None:
    """Return a surface's opaque envelope class (R6), or `None` for a window or an internal mass.

    Args:
        surface: The surface; its inventory `surface_class` and tilt are read.

    Returns:
        The class; inventory's `interior` becomes `partition` for walls (60° to 120° tilt) and
        `floor_ceiling` otherwise.
    """
    match surface.surface_class:
        case "window" | "internal_mass":
            return None
        case "interior":
            low, high = _WALL_TILT
            return "partition" if low <= surface.tilt <= high else "floor_ceiling"
        case other:
            return other


def orientation(azimuth: float) -> Orientation:
    """Return the 45° sector of an azimuth, centred on the compass points (R6).

    Args:
        azimuth: Degrees clockwise from north, any value.

    Returns:
        `"N"` for [337.5°, 22.5°), `"NE"` for [22.5°, 67.5°), and so on.
    """
    return orientation_of(azimuth)


def _horizontal(tilt: float) -> bool:
    return tilt < _HORIZONTAL_TOLERANCE or tilt > 180.0 - _HORIZONTAL_TOLERANCE


# --- capacities ------------------------------------------------------------------------------


class CapacitySplit(NamedTuple):
    """Heat capacity inside and outside a construction's most resistive layer, J/m²K (or J/K)."""

    inner: float
    outer: float


def capacity_split(layers: Sequence[tuple[float, float]]) -> CapacitySplit:
    """Split a construction's heat capacity at its most resistive layer (R6).

    Args:
        layers: `(resistance m²K/W, capacity J/m²K)` per layer, outside first.

    Returns:
        The capacity of the layers inside the most resistive one plus half of its own (inner),
        and the rest (outer). The first of equally resistive layers divides. No layers: (0, 0).
    """
    if not layers:
        return CapacitySplit(0.0, 0.0)
    index = max(range(len(layers)), key=lambda i: (layers[i][0], -i))
    core = layers[index][1] / 2.0
    outer = math.fsum(capacity for _, capacity in layers[:index]) + core
    inner = math.fsum(capacity for _, capacity in layers[index + 1 :]) + core
    return CapacitySplit(inner, outer)


def _surface_split(surface: SurfaceRecord) -> CapacitySplit:
    if not surface.layers:
        half = surface.heat_capacity / 2.0
        return CapacitySplit(half, half)
    return capacity_split([(layer.resistance, layer.heat_capacity) for layer in surface.layers])


def assembly_capacities(assembly: ConstructionAssemblyComponent) -> CapacitySplit:
    """Split an epinterface assembly's capacity by the rule of `capacity_split`.

    Args:
        assembly: The assembly; layers are taken outside first (`LayerOrder` 0 outside).

    Returns:
        The inner and outer capacity per area, J/m²K.
    """
    return capacity_split([
        (
            layer.r_value,
            layer.Thickness * layer.ConstructionMaterial.Density * layer.ConstructionMaterial.SpecificHeat,
        )
        for layer in assembly.sorted_layers
    ])


def assembly_u_factor(assembly: ConstructionAssemblyComponent, envelope_class: EnvelopeClass) -> float:
    """Return an assembly's U with the films of its class, W/m²K.

    Args:
        assembly: The assembly.
        envelope_class: Its class, which selects the films.

    Returns:
        `1 / (R_inside + Σ layer R + R_outside)`.
    """
    inside, outside = FILMS[envelope_class]
    return 1.0 / (inside + assembly.r_value + outside)


# --- one zone's envelope ---------------------------------------------------------------------


@dataclass
class ZoneEnvelope:
    """The envelope totals of one copy of a zone, as ledger fields.

    Attributes:
        envelope: Opaque totals per class.
        window_by_orientation: Totals of the windows in walls (60° to 120° tilt) per orientation.
        skylights: Totals of the other windows (skylights, roof and floor windows).
        internal_mass_capacity: Σ area · heat capacity of internal masses, J/K.
        internal_mass_area: Σ area of internal masses, m².
        excluded_envelope: Assignments of excluded zones' envelope to this zone.
    """

    envelope: dict[EnvelopeClass, EnvelopeTotals] = field(default_factory=dict[EnvelopeClass, EnvelopeTotals])
    window_by_orientation: dict[Orientation, WindowTotals] = field(default_factory=dict[Orientation, WindowTotals])
    skylights: WindowTotals = field(default_factory=WindowTotals)
    internal_mass_capacity: float = 0.0
    internal_mass_area: float = 0.0
    excluded_envelope: list[EnvelopeAssignment] = field(default_factory=list[EnvelopeAssignment])

    def add_envelope(self, klass: EnvelopeClass, totals: EnvelopeTotals) -> None:
        """Add opaque totals to a class."""
        self.envelope[klass] = self.envelope[klass] + totals if klass in self.envelope else totals

    def add_window(self, sector: Orientation, totals: WindowTotals) -> None:
        """Add window totals to an orientation."""
        current = self.window_by_orientation.get(sector)
        self.window_by_orientation[sector] = current + totals if current is not None else totals

    def fields(self) -> dict[str, object]:
        """Return the ledger fields."""
        return {
            "envelope": dict(self.envelope),
            "window_by_orientation": dict(self.window_by_orientation),
            "skylights": self.skylights,
            "internal_mass_capacity": self.internal_mass_capacity,
            "internal_mass_area": self.internal_mass_area,
            "excluded_envelope": tuple(self.excluded_envelope),
        }


def _window_totals(surface: SurfaceRecord) -> WindowTotals:
    if surface.shgc is None or surface.visible_transmittance is None:
        msg = (
            f"window {surface.name!r} has no SHGC or visible transmittance in the results' Envelope Summary; "
            "its solar and light admittance cannot be conserved"
        )
        raise ValueError(msg)
    area = surface.area
    return WindowTotals(
        area=area, ua=area * surface.u_factor, a_shgc=area * surface.shgc, a_vt=area * surface.visible_transmittance
    )


_CLASS_FILMS: Mapping[str, float] = {"WALL": 0.1197548, "DOOR": 0.1197548, "FLOOR": 0.1620212, "ROOF": 0.1074271}
"""EnergyPlus's nominal film of each surface class (`ComputeNominalUwithConvCoeffs`), upper case."""
_OUTDOOR_FILM = 0.0299387
_FACING_CLASS: Mapping[str, str] = {"FLOOR": "ROOF", "ROOF": "FLOOR"}
"""The class of the surface an interzone surface faces, where it differs from its own."""
_WINDOW_CLASS_NAMES = frozenset({"WINDOW", "GLASS DOOR", "GLASSDOOR", "TUBULARDAYLIGHTDOME", "TUBULARDAYLIGHTDIFFUSER"})
# The films `inventory._with_films` adds to `Constructions.Uvalue` when the Envelope Summary has no U.
_FALLBACK_INSIDE = 0.13
_FALLBACK_OUTSIDE = 0.04


def _surface_films(surface: SurfaceRecord, klass: EnvelopeClass) -> float:
    """The films in a surface's U-factor: EnergyPlus's for its class and boundary, or the fallback's.

    EnergyPlus's Envelope Summary gives a surface its class's inside film and, outside, the film of
    the surface it faces: an adiabatic surface faces itself, so its own film twice. An interzone
    surface faces its companion, whose films `FILMS` holds for the class.
    """
    inside, outside = FILMS[klass]
    declared = surface.class_name.upper()
    if surface.u_source == "constructions":
        if declared in _WINDOW_CLASS_NAMES:
            # A window construction's U already holds its films: `inventory._with_films` adds none.
            return inside + outside
        return _FALLBACK_INSIDE + (_FALLBACK_OUTSIDE if surface.boundary == "outdoors" else _FALLBACK_INSIDE)
    own = _CLASS_FILMS.get(declared)
    # The declared class sets the film, whatever class the tilt gives the surface here.
    facing: Mapping[str, float] = (
        {}
        if own is None
        else {
            "adiabatic": own,
            "outdoors": _OUTDOOR_FILM,
            "interzone": _CLASS_FILMS[_FACING_CLASS.get(declared, declared)],
        }
    )
    if own is None or surface.boundary not in facing:
        return inside + outside
    return own + facing[surface.boundary]


def _class_u_factor(surface: SurfaceRecord, klass: EnvelopeClass) -> float:
    """The surface's U-factor with its class's `FILMS` instead of its own: its layers' resistance kept."""
    u = surface.u_factor
    films = _surface_films(surface, klass)
    inside, outside = FILMS[klass]
    if not u > 0 or abs(films - inside - outside) < 1e-12:  # noqa: PLR2004 - equal films
        return u
    layers = 1.0 / u - films
    return 1.0 / (layers + inside + outside) if layers > 0 else u


def _opaque_totals(surface: SurfaceRecord, klass: EnvelopeClass) -> EnvelopeTotals:
    area = surface.area
    split = _surface_split(surface)
    by_orientation: dict[Orientation, float] = {} if _horizontal(surface.tilt) else {orientation(surface.azimuth): area}
    return EnvelopeTotals(
        area=area,
        ua=area * _class_u_factor(surface, klass),
        capacity_inner=area * split.inner,
        capacity_outer=area * split.outer,
        area_by_orientation=by_orientation,
    )


def zone_envelope(
    zone: ZoneRecord, *, classes: Iterable[EnvelopeClass] | None = None, internal_mass: bool = True
) -> ZoneEnvelope:
    """Return the envelope totals of one copy of a zone (multiplier not applied).

    Args:
        zone: The zone record.
        classes: Only these opaque classes (windows are always included); `None` for all.
        internal_mass: Whether to include internal masses.

    Returns:
        The totals.

    Raises:
        ValueError: If a window has no SHGC or visible transmittance.
    """
    wanted = None if classes is None else frozenset(classes)
    result = ZoneEnvelope()
    for surface in zone.surfaces:
        if surface.surface_class == "window":
            low, high = _WALL_TILT
            if low <= surface.tilt <= high:
                result.add_window(orientation(surface.azimuth), _window_totals(surface))
            else:  # a skylight, roof or floor window: not part of any facade (FR-016, FR-024)
                result.skylights = result.skylights + _window_totals(surface)
            continue
        if surface.surface_class == "internal_mass":
            if internal_mass:
                result.internal_mass_capacity += surface.area * surface.heat_capacity
                result.internal_mass_area += surface.area
            continue
        klass = envelope_class(surface)
        if klass is None or (wanted is not None and klass not in wanted):
            continue
        result.add_envelope(klass, _opaque_totals(surface, klass))
    return result


def ledger_fields(zone: ClassifiedZone, schedules: ScheduleEvaluator) -> dict[str, object]:
    """The envelope hook for one copy of a zone, without excluded zones' envelope.

    Use `EnvelopeHook(zones)` to also carry plenums' and attics' envelope (FR-013).

    Args:
        zone: The classified zone.
        schedules: Unused; part of the hook signature.

    Returns:
        `envelope`, `window_by_orientation`, `skylights`, `internal_mass_capacity`,
        `internal_mass_area` and an empty `excluded_envelope`.
    """
    del schedules
    return zone_envelope(zone.zone).fields()


# --- excluded zones (FR-013) -----------------------------------------------------------------


def _key(name: str) -> str:
    return name.casefold()


class EnvelopeHook:
    """The envelope hook with excluded zones' envelope assigned to conditioned zones (FR-013).

    Build it once with every classified zone of the building and pass it to
    `GroupLedger.from_zone(zone, schedules, hooks=[..., hook, ...])` in place of `ledger_fields`.

    Attributes:
        shares: Source zone name → target zone name → share of the source's envelope.
        unassigned: Excluded zones whose envelope could not be assigned (no conditioned zone).
    """

    def __init__(self, zones: Iterable[ClassifiedZone], *, assigned_roles: Iterable[Role] = ASSIGNED_ROLES) -> None:
        """Compute every assignment.

        Args:
            zones: Every classified zone of the building.
            assigned_roles: The roles whose envelope is assigned.
        """
        roles = frozenset(assigned_roles) - {"conditioned"}
        all_zones = list(zones)
        self._conditioned = {_key(z.zone.name): z for z in all_zones if z.role == "conditioned"}
        self._sources = {_key(z.zone.name): z for z in all_zones if z.role in roles}
        self._shared: dict[str, dict[str, float]] = {}
        for key, source in self._sources.items():
            shared: dict[str, float] = defaultdict(float)
            for surface in source.zone.surfaces:
                if surface.boundary == "interzone" and surface.adjacent_zone is not None:
                    shared[_key(surface.adjacent_zone)] += surface.area
            self._shared[key] = dict(shared)
        self.shares: dict[str, dict[str, float]] = {}
        unassigned: list[str] = []
        self._incoming: dict[str, list[tuple[ClassifiedZone, float]]] = defaultdict(list)
        resolved = self._resolve_all()
        for key in sorted(self._sources):
            source = self._sources[key]
            targets = resolved.get(key) or self._fallback()
            if not targets:
                unassigned.append(source.zone.name)
                continue
            self.shares[source.zone.name] = {self._conditioned[t].zone.name: s for t, s in sorted(targets.items())}
            for target, share in targets.items():
                self._incoming[target].append((source, share))
        self.unassigned: tuple[str, ...] = tuple(unassigned)
        self._carried: dict[str, ZoneEnvelope] = {}

    def _resolve_all(self) -> dict[str, dict[str, float]]:
        """Each source zone's shares, by layers of distance from the conditioned zones.

        A zone touching conditioned zones shares by the shared area. Any other zone combines the
        shares of its neighbours one layer closer, weighted by the area it shares with each. The
        sweep visits each zone once, so its cost is linear in the number of shared surfaces.
        """
        resolved: dict[str, dict[str, float]] = {}
        for key, shared in self._shared.items():
            direct = {t: area for t, area in shared.items() if t in self._conditioned and area > 0}
            if direct:
                total = math.fsum(direct.values())
                resolved[key] = {t: area / total for t, area in direct.items()}
        layer = set(resolved)
        while layer:
            following: dict[str, dict[str, float]] = {}
            for key in sorted(self._sources):
                if key in resolved:
                    continue
                via = sorted((n, area) for n, area in self._shared[key].items() if n in layer and area > 0)
                if not via:
                    continue
                total = math.fsum(area for _, area in via)
                combined: dict[str, float] = defaultdict(float)
                for neighbour, area in via:
                    for target, share in resolved[neighbour].items():
                        combined[target] += area / total * share
                following[key] = dict(combined)
            resolved.update(following)
            layer = set(following)
        return resolved

    def _fallback(self) -> dict[str, float]:
        weights = {t: z.zone.floor_area * z.zone.multiplier for t, z in self._conditioned.items()}
        total = math.fsum(weights.values())
        return {t: w / total for t, w in weights.items() if w > 0} if total > 0 else {}

    def _carried_envelope(self, source: ClassifiedZone) -> ZoneEnvelope:
        key = _key(source.zone.name)
        if key not in self._carried:
            self._carried[key] = zone_envelope(source.zone, classes=EXTERIOR_CLASSES, internal_mass=False)
        return self._carried[key]

    def __call__(self, zone: ClassifiedZone, schedules: ScheduleEvaluator) -> dict[str, object]:
        """Return the zone's own envelope plus what it carries of excluded zones, for one copy.

        Args:
            zone: The classified zone.
            schedules: Unused; part of the hook signature.

        Returns:
            The six envelope ledger fields.
        """
        del schedules
        result = zone_envelope(zone.zone)
        for source, share in self._incoming.get(_key(zone.zone.name), ()):
            factor = share * source.zone.multiplier / zone.zone.multiplier
            carried = self._carried_envelope(source)
            for klass, totals in sorted(carried.envelope.items()):
                part = totals.scaled(factor)
                result.add_envelope(klass, part)
                result.excluded_envelope.append(
                    EnvelopeAssignment(
                        source_zone=source.zone.name,
                        target_zone=zone.zone.name,
                        envelope_class=klass,
                        area=part.area,
                        share=min(max(share, 0.0), 1.0),
                    )
                )
            for sector, window in sorted(carried.window_by_orientation.items()):
                result.add_window(sector, window.scaled(factor))
            result.skylights = result.skylights + carried.skylights.scaled(factor)
        return result.fields()


# --- SBEM assemblies -------------------------------------------------------------------------


def _material(
    name: str, conductivity: float, density: float, material_type: ConstructionMaterialType
) -> ConstructionMaterialComponent:
    return ConstructionMaterialComponent(
        Name=name,
        Conductivity=conductivity,
        Density=density,
        SpecificHeat=_SPECIFIC_HEAT,
        Roughness="MediumRough",
        ThermalAbsorptance=0.9,
        SolarAbsorptance=0.7,
        VisibleAbsorptance=0.7,
        TemperatureCoefficientThermalConductivity=0.0,
        Type=material_type,
        Comment="Equivalent layer synthesised by archetypal (rule envelope.equivalent, R6)",
    )


def _mass_thickness(capacity: float) -> float:
    return min(max(capacity / (_MASS_DENSITY * _SPECIFIC_HEAT), _MIN_THICKNESS), _MAX_THICKNESS)


def equivalent_construction(
    totals: EnvelopeTotals, envelope_class: EnvelopeClass, *, name: str | None = None
) -> ConstructionAssemblyComponent:
    """Return the three-layer assembly that reproduces a class's U and both capacities (R6).

    Layers, outside first: outer mass, insulation, inner mass. The mass layers take at most a
    third of the layer resistance, so the insulation is the most resistive layer and the
    capacities split as `capacity_split` splits the sources'. The insulation's own capacity is
    taken from both mass layers by halves.

    Args:
        totals: The class's totals (`area` > 0, `ua` > 0).
        envelope_class: The class: it selects the films and the SBEM slot (`ASSEMBLY_TYPES`).
        name: The assembly's name; materials are named after it. Default `"Equivalent <slot>"`.

    Returns:
        The assembly. `assembly_u_factor(assembly, envelope_class) == ua / area`, and
        `assembly_capacities(assembly)` equals the capacities per area (a side without capacity
        gets `MIN_CAPACITY`).

    Raises:
        ValueError: If the area or UA is not positive, or U is too high to reproduce with the films.
    """
    slot = ASSEMBLY_TYPES[envelope_class]
    name = name if name is not None else f"Equivalent {slot}"
    area = totals.area
    if not area > 0:
        msg = f"cannot build an equivalent {envelope_class} construction for an area of {area} m²"
        raise ValueError(msg)
    u = totals.ua / area
    if not u > 0:
        msg = f"cannot build an equivalent {envelope_class} construction for U = {u} W/m²K"
        raise ValueError(msg)
    inside, outside = FILMS[envelope_class]
    budget = 1.0 / u - inside - outside
    if not budget > 0:
        msg = (
            f"U = {u:.4g} W/m²K of {envelope_class} cannot be reproduced with the films "
            f"({inside} + {outside} m²K/W): it would need a negative layer resistance"
        )
        raise ValueError(msg)
    c_inner = max(totals.capacity_inner / area, MIN_CAPACITY)
    c_outer = max(totals.capacity_outer / area, MIN_CAPACITY)

    # Resistance of the two mass layers together, then the insulation's.
    natural = (_mass_thickness(c_inner) + _mass_thickness(c_outer)) / _MASS_CONDUCTIVITY
    r_mass = min(natural, budget * _MASS_SHARE_OF_RESISTANCE)
    r_insulation = budget - r_mass
    d_insulation = min(max(_INSULATION_CONDUCTIVITY * r_insulation, _MIN_THICKNESS), _MAX_THICKNESS)
    k_insulation = d_insulation / r_insulation
    # The insulation's capacity, at most each side's, is taken from both sides by halves.
    c_insulation = min(_INSULATION_DENSITY * _SPECIFIC_HEAT * d_insulation, c_inner, c_outer)
    rho_insulation = c_insulation / (_SPECIFIC_HEAT * d_insulation)
    c_outer_mass = c_outer - c_insulation / 2.0
    c_inner_mass = c_inner - c_insulation / 2.0
    d_outer = _mass_thickness(c_outer_mass)
    d_inner = _mass_thickness(c_inner_mass)
    k_mass = (d_outer + d_inner) / r_mass

    def layer(order: int, thickness: float, material: ConstructionMaterialComponent) -> ConstructionLayerComponent:
        return ConstructionLayerComponent(Thickness=thickness, LayerOrder=order, ConstructionMaterial=material)

    layers = [
        layer(
            0, d_outer, _material(f"{name} outer mass", k_mass, c_outer_mass / (_SPECIFIC_HEAT * d_outer), "Concrete")
        ),
        layer(1, d_insulation, _material(f"{name} insulation", k_insulation, rho_insulation, "Insulation")),
        layer(
            2, d_inner, _material(f"{name} inner mass", k_mass, c_inner_mass / (_SPECIFIC_HEAT * d_inner), "Concrete")
        ),
    ]
    return ConstructionAssemblyComponent(
        Name=name,
        Layers=layers,
        Type=slot,
        Comment=f"U = {u:.6g} W/m²K with films {inside} + {outside} m²K/W (rule envelope.equivalent, R6)",
    )


def internal_mass_construction(
    capacity: float, area: float, *, name: str = "Equivalent InternalMass"
) -> ConstructionAssemblyComponent | None:
    """Return a one-layer internal-mass assembly holding `capacity / area` per m² (rule `mass.internal`).

    With `InternalMassExposedAreaPerArea = area / floor_area`, the group's internal mass
    capacity is conserved.

    Args:
        capacity: Σ area · capacity of the internal masses, J/K.
        area: Σ their area, m².
        name: The assembly's name.

    Returns:
        The assembly, or `None` without internal mass.
    """
    if not (area > 0 and capacity > 0):
        return None
    per_area = capacity / area
    thickness = _mass_thickness(per_area)
    material = _material(f"{name} mass", _MASS_CONDUCTIVITY, per_area / (_SPECIFIC_HEAT * thickness), "Concrete")
    return ConstructionAssemblyComponent(
        Name=name,
        Layers=[ConstructionLayerComponent(Thickness=thickness, LayerOrder=0, ConstructionMaterial=material)],
        Type="InternalMass",
        Comment="Internal mass capacity per exposed area (rule mass.internal, R6)",
    )


def window_construction(
    windows: Mapping[Orientation, WindowTotals] | WindowTotals, *, name: str = "Equivalent Window"
) -> GlazingConstructionSimpleComponent | None:
    """Return the simple glazing with area-weighted U, SHGC and VT (rule `window.area_weighted`).

    Args:
        windows: Window totals by orientation, or already summed.
        name: The glazing's name.

    Returns:
        The glazing (`UValue = ΣUA/ΣA`, `SHGF = ΣA·SHGC/ΣA`, `TVis = ΣA·VT/ΣA`; `Type` from U:
        single at 3 W/m²K or more, double from 1.2, triple below), or `None` without windows.
    """
    if isinstance(windows, WindowTotals):
        total = windows
    else:
        total = WindowTotals()
        for _, item in sorted(windows.items()):
            total = total + item
    if not total.area > 0:
        return None
    u = total.ua / total.area
    glazing_type: Literal["Single", "Double", "Triple"] = (
        "Single" if u >= _SINGLE_GLAZING_U - 1e-9 else "Double" if u >= _DOUBLE_GLAZING_U - 1e-9 else "Triple"
    )
    return GlazingConstructionSimpleComponent(
        Name=name,
        UValue=u,
        SHGF=min(max(total.a_shgc / total.area, 0.0), 1.0),
        TVis=min(max(total.a_vt / total.area, 0.0), 1.0),
        Type=glazing_type,
        Comment="Area-weighted glazing (rule window.area_weighted, R6)",
    )
