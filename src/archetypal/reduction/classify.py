"""Zone classification: conditioned or not, role, exposure and space use (spec 002, data-model.md, ClassifiedZone).

Rules, from research:

- **Conditioned** (R8): a zone is conditioned when its thermostat sets a heating or cooling
  setpoint within 5-35 °C at some hour (`ThermostatRecord.enabled`), or when its HVAC equipment
  delivers heating or cooling to it (non-zero `ZoneRecord.delivered`: the energy of its own zone
  equipment and its share of its air loop's coils, from `delivery.delivered_energy`, research
  R12). An air-loop plenum is the exception to the second test: air passing through it is not
  conditioning it, so a plenum counts only through a thermostat.
- **Role** (R8, FR-013): an unconditioned zone is an *attic* when it has a roof, a floor
  adjacent to a conditioned zone, and exterior walls (windows included) over no more than 50 %
  of its envelope area; a *basement* when it has ground-contact walls or floor and a ceiling
  adjacent to a conditioned zone; otherwise, and always for a plenum, it is *excluded*.
- **Exposure** (R7, FR-006): *perimeter* when any surface is a wall (60° to 120° tilt) facing the
  outdoors or a window facing the outdoors; *core* otherwise. Roofs, exposed floors and ground
  contact never decide it. Exposure is computed for every zone; only conditioned zones use it.
- **Space use** (R4, FR-007), in order of precedence: the user's mapping (zone name to label,
  names compared case-insensitively); the zone's declared `Space` type when all its spaces
  agree; otherwise the zone's *signature* (`space_use_signature`). Zones with equal signatures
  share the label `use:<lexicographically smallest zone name>`. Conditioned and unconditioned
  zones form separate signature classes, so a conditioned use is never named after a plenum.

Zones are sorted by name before anything else, so the result never depends on model order.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from archetypal.errors import NoConditionedZones

if TYPE_CHECKING:
    from collections.abc import Callable, Hashable, Iterable, Mapping, Sequence

    from archetypal.reduction.inventory import GainRecord, ZoneRecord
    from archetypal.reduction.options import Exposure
    from archetypal.reduction.schedules import Profile

__all__ = [
    "ATTIC_WALL_SHARE",
    "ClassifiedZone",
    "Role",
    "SpaceUseSource",
    "classify",
    "digest",
    "exposure",
    "round_significant",
    "space_use_signature",
]

Role = Literal["conditioned", "attic", "basement", "excluded"]
"""A zone's role (research R8)."""

SpaceUseSource = Literal["user", "space_type", "signature"]
"""Which tier of FR-007 decided a zone's space use."""

ATTIC_WALL_SHARE = 0.5
"""An attic's exterior walls cover at most this share of its envelope area (research R8)."""

SIGNIFICANT_FIGURES = 6
"""Densities and rates are rounded to this many significant figures in a signature (R4)."""

DECIMALS = 6
"""Schedule values are rounded to this many decimal places before hashing (R4)."""

_WALL_TILT = (60.0, 120.0)
_ROOF_TILT = 60.0
_FLOOR_TILT = 120.0
_SPACE_USE_PREFIX = "use:"


@dataclass(frozen=True)
class ClassifiedZone:
    """A zone with its classification.

    Attributes:
        zone: The zone.
        conditioned: Whether it is conditioned (R8).
        role: Its role (R8).
        exposure: Its exposure (R7); grouping uses it for conditioned zones only.
        space_use: Its space-use label (R4).
        space_use_source: Which tier decided the space use (FR-007).
        role_reason: Why it has its role, in words, for the report.
    """

    zone: ZoneRecord
    conditioned: bool
    role: Role
    exposure: Exposure
    space_use: str
    space_use_source: SpaceUseSource
    role_reason: str


# --- Exposure -------------------------------------------------------------------------------------


def exposure(zone: ZoneRecord) -> Exposure:
    """Return a zone's exposure (research R7).

    Args:
        zone: The zone.

    Returns:
        `"perimeter"` when it has an outdoor wall or an outdoor window in a wall (both 60° to 120°
        tilt), else `"core"`: roofs and skylights never decide.
    """
    low, high = _WALL_TILT
    for surface in zone.surfaces:
        if surface.boundary != "outdoors":
            continue
        if surface.surface_class == "exterior_wall" or (
            surface.surface_class == "window" and low <= surface.tilt <= high
        ):
            return "perimeter"
    return "core"


# --- Roles ----------------------------------------------------------------------------------------


def _conditioning(zone: ZoneRecord, evaluate: Callable[[str], Profile]) -> str | None:
    """Return why a zone is conditioned, or `None` when it is not."""
    if zone.thermostat is not None:
        enabled = zone.thermostat.enabled(evaluate)
        modes = [mode for mode in ("heating", "cooling") if enabled[mode]]
        if modes:
            return f"thermostat {zone.thermostat.name} enables {' and '.join(modes)}"
    if not zone.plenum:
        modes = [mode for mode in ("heating", "cooling") if zone.delivered.get(mode, 0.0) != 0.0]
        if modes:
            return f"equipment delivers {' and '.join(modes)}"
    return None


def _adjacent_to(zone: ZoneRecord, conditioned: frozenset[str], *, facing: Literal["up", "down"]) -> bool:
    for surface in zone.surfaces:
        if surface.boundary != "interzone" or surface.adjacent_zone is None:
            continue
        if surface.adjacent_zone.casefold() not in conditioned:
            continue
        if (facing == "down" and surface.tilt > _FLOOR_TILT) or (facing == "up" and surface.tilt < _ROOF_TILT):
            return True
    return False


def _unconditioned_role(zone: ZoneRecord, conditioned: frozenset[str]) -> tuple[Role, str]:
    if zone.plenum:
        return "excluded", "air-loop plenum"
    classes = {surface.surface_class for surface in zone.surfaces}
    envelope = sum(s.area for s in zone.surfaces if s.surface_class != "internal_mass")
    low, high = _WALL_TILT
    walls = sum(
        s.area
        for s in zone.surfaces
        if s.surface_class == "exterior_wall" or (s.surface_class == "window" and low <= s.tilt <= high)
    )
    if "roof" in classes and _adjacent_to(zone, conditioned, facing="down"):
        if envelope > 0.0 and walls <= ATTIC_WALL_SHARE * envelope:
            return "attic", "roof, floor over a conditioned zone, exterior walls at most 50 % of its envelope"
        return "excluded", "unconditioned; exterior walls over 50 % of its envelope, so not an attic"
    if classes & {"ground_wall", "ground_floor"} and _adjacent_to(zone, conditioned, facing="up"):
        return "basement", "ground contact and a ceiling under a conditioned zone"
    return "excluded", "unconditioned, neither attic nor basement"


# --- Signatures -----------------------------------------------------------------------------------


def round_significant(value: float, figures: int = SIGNIFICANT_FIGURES) -> float:
    """Round to a number of significant figures, with -0.0 read as 0.0.

    Args:
        value: The value.
        figures: Significant figures.

    Returns:
        The rounded value.
    """
    return float(f"{value:.{figures}g}") + 0.0


def digest(profile: Profile | None) -> str:
    """Return the SHA-256 of an hourly profile's values rounded to `DECIMALS` places.

    NaN (a mode not set at that hour) hashes as a distinct value. `None` gives `"none"`.

    Args:
        profile: The profile.

    Returns:
        The hex digest.
    """
    if profile is None:
        return "none"
    values = np.round(np.asarray(profile, dtype=np.float64), DECIMALS) + 0.0
    values[np.isnan(values)] = np.inf
    return hashlib.sha256(np.ascontiguousarray(values).tobytes()).hexdigest()


def _gain_signature(
    gains: Iterable[GainRecord], floor_area: float, evaluate: Callable[[str], Profile]
) -> tuple[Hashable, ...]:
    by_kind: dict[str, dict[str, float]] = {}
    for gain in gains:
        if gain.design_level == 0.0:
            continue
        schedule = digest(evaluate(gain.schedule)) if gain.schedule else "none"
        levels = by_kind.setdefault(gain.kind, {})
        levels[schedule] = levels.get(schedule, 0.0) + gain.design_level
    signature: list[Hashable] = []
    for kind in sorted(by_kind):
        levels = by_kind[kind]
        total = sum(levels.values())
        if total == 0.0:
            continue
        density = round_significant(total / floor_area) if floor_area > 0.0 else round_significant(total)
        shares = tuple(sorted((schedule, round_significant(level / total)) for schedule, level in levels.items()))
        signature.append((kind, density, shares))
    return tuple(signature)


def space_use_signature(zone: ZoneRecord, evaluate: Callable[[str], Profile]) -> tuple[Hashable, ...]:
    """Return a zone's space-use signature (research R4).

    The signature holds, rounded so that numerical noise does not split a space use:

    - per gain kind, its density (installed total ÷ floor area, 6 significant figures) and, for
      each distinct schedule (digest of values rounded to 6 decimals), its share of the total;
    - the digests of the hourly heating and cooling setpoints (NaN where a mode is not set);
    - the design outdoor air per floor area and per person (6 significant figures).

    Args:
        zone: The zone.
        evaluate: Returns a schedule's hourly profile by name.

    Returns:
        A hashable signature; equal signatures mean one space use.
    """
    if zone.thermostat is not None:
        heating, cooling = zone.thermostat.setpoints(evaluate)
        setpoints = (digest(heating), digest(cooling))
    else:
        setpoints = ("none", "none")
    outdoor_air = (round_significant(zone.outdoor_air_per_area), round_significant(zone.outdoor_air_per_person))
    return (_gain_signature(zone.gains, zone.floor_area, evaluate), setpoints, outdoor_air)


def _signature_labels(zones: Sequence[ZoneRecord], evaluate: Callable[[str], Profile]) -> dict[str, str]:
    classes: dict[tuple[Hashable, ...], list[str]] = {}
    for zone in zones:
        classes.setdefault(space_use_signature(zone, evaluate), []).append(zone.name)
    return {name: _SPACE_USE_PREFIX + min(names) for names in classes.values() for name in names}


# --- Classification -------------------------------------------------------------------------------


def _casefolded(space_use_mapping: Mapping[str, str]) -> dict[str, str]:
    """The mapping by case-folded zone name; one zone named in two letter cases must get one use."""
    mapping: dict[str, str] = {}
    for key, value in sorted(space_use_mapping.items()):
        if mapping.setdefault(key.casefold(), value) != value:
            msg = f"the space-use mapping gives zone {key} two space uses, in two letter cases of its name"
            raise ValueError(msg)
    return mapping


def classify(
    zones: Iterable[ZoneRecord],
    evaluate: Callable[[str], Profile],
    *,
    space_use_mapping: Mapping[str, str] | None = None,
    subject: str = "the model",
) -> tuple[ClassifiedZone, ...]:
    """Classify every zone, sorted by name.

    Args:
        zones: The zones, in any order.
        evaluate: Returns a schedule's hourly profile by name (`ScheduleEvaluator`).
        space_use_mapping: The user's zone-name to space-use mapping (FR-007 tier 1).
        subject: What the error names when no zone is conditioned (the model's path).

    Returns:
        One classified zone per zone, sorted by zone name.

    Raises:
        NoConditionedZones: No zone is conditioned.
        ValueError: The mapping names a zone the model does not have, or gives one zone two
            space uses under two letter cases of its name.
    """
    ordered = sorted(zones, key=lambda zone: zone.name)
    mapping = _casefolded(space_use_mapping or {})
    unknown = sorted(set(mapping) - {zone.name.casefold() for zone in ordered})
    if unknown:
        names = sorted(key for key in (space_use_mapping or {}) if key.casefold() in unknown)
        msg = f"the space-use mapping names zones the model does not have: {', '.join(names)}"
        raise ValueError(msg)

    reasons = {zone.name: _conditioning(zone, evaluate) for zone in ordered}
    conditioned = frozenset(zone.name.casefold() for zone in ordered if reasons[zone.name] is not None)
    if not conditioned:
        raise NoConditionedZones(subject)

    roles: dict[str, tuple[Role, str]] = {}
    for zone in ordered:
        reason = reasons[zone.name]
        roles[zone.name] = ("conditioned", reason) if reason is not None else _unconditioned_role(zone, conditioned)

    uses: dict[str, tuple[str, SpaceUseSource]] = {}
    for zone in ordered:
        if zone.name.casefold() in mapping:
            uses[zone.name] = (mapping[zone.name.casefold()], "user")
        elif zone.space_type:
            uses[zone.name] = (zone.space_type, "space_type")
    for pool_conditioned in (True, False):
        pool = [
            zone
            for zone in ordered
            if zone.name not in uses and (zone.name.casefold() in conditioned) == pool_conditioned
        ]
        for name, label in _signature_labels(pool, evaluate).items():
            uses[name] = (label, "signature")

    return tuple(
        ClassifiedZone(
            zone=zone,
            conditioned=zone.name.casefold() in conditioned,
            role=roles[zone.name][0],
            exposure=exposure(zone),
            space_use=uses[zone.name][0],
            space_use_source=uses[zone.name][1],
            role_reason=roles[zone.name][1],
        )
        for zone in ordered
    )
