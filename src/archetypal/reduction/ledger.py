"""The group ledger: the conserved totals of a group of zones (spec 002, data-model.md: GroupLedger).

A ledger's fields are **sums**, never averages, so merging two ledgers is field-wise addition
(`a + b`). Addition is commutative exactly and associative up to float rounding (exactly on
values whose sums are exact), which makes FR-010 and SC-007 hold by construction. Members are
a sorted union; adding two ledgers that share a member is refused, because it would count
that zone twice.

Totals types
------------
Every totals type is a frozen pydantic model whose fields are additive: floats, profiles
(float64 arrays, one value per hour of the run period), dicts of either keyed by a category,
and nested totals. A dict key missing on one side counts as absent (zero), and an empty
profile (length 0) is the identity of profile addition, so `GroupLedger()` is the identity of
`+` and `sum(ledgers)` works. Dicts are held in sorted key order and profiles as read-only
copies, so equal ledgers serialise to identical bytes.

Two data-model fields are held in additive form (a decision of this module):

- `EnergyTotals.rated_efficiency` is a property, `rated_weighted / rated_weight`, from the two
  additive fields `rated_weight` (for example rated capacity or floor area) and
  `rated_weighted` (Σ weight · rated efficiency), so merging keeps a weighted mean;
- `GroupLedger.outdoor_air` is an `OutdoorAirTotals`: `AirflowTotals` plus `hrv_weighted` and
  `economiser_weighted` (SBEM category → Σ annual outdoor-air volume it serves, m³) and
  `effectiveness_weighted` (Σ volume · sensible effectiveness).

`GroupLedger.internal_mass_area` is added next to `internal_mass_capacity`, since
`InternalMassExposedAreaPerArea` needs the area (R6).

The multiplier, exactly once
----------------------------
`GroupLedger.from_zone(zone, schedules)` asks each **domain hook** for the totals of **one
copy** of the zone, builds a one-copy ledger with the zone's name and floor area, and then
multiplies every extensive quantity by `zone.zone.multiplier` (`GroupLedger.scaled`). That is
the only place a multiplier is applied (data-model.md, ZoneRecord invariant). A hook must
therefore return per-copy values; where an EnergyPlus output already includes the multiplier
(zone mechanical-ventilation and zoned hot-water outputs do), the hook divides it out.

Every total, including Σ d² in `EirSums`, scales linearly with the multiplier: a multiplied
zone counts as that many identical zones. Shares (`EnvelopeAssignment.share`) and the
area-weighted mean of a `WeightedProfile` are unchanged by scaling.

Domain hooks
------------
A hook is any callable `hook(zone: ClassifiedZone, schedules: ScheduleEvaluator) ->
Mapping[str, object]` (`ZoneHook`) returning ledger field names and their one-copy values
(totals instances or data pydantic validates into them). Fields no hook returns keep their
zero default; a field returned by two hooks, `members`, `floor_area` or an unknown name is
refused. `from_zone(..., hooks=None)` uses `default_hooks()`: `gain_fields` of this module,
then `ledger_fields` of each domain module, imported lazily so this module imports none of
them and they can import the totals types from here. Each domain module defines:

| Module (`archetypal.reduction.*`) | Function | Fields it returns |
|---|---|---|
| (this module) | `gain_fields` | `gains` |
| `envelope` (T049) | `ledger_fields` | `envelope`, `window_by_orientation`, `internal_mass_capacity`, `internal_mass_area`, `excluded_envelope` |
| `airflow` (T050) | `ledger_fields` | `infiltration`, `outdoor_air` |
| `thermostats` (T051) | `ledger_fields` | `heating_setpoint`, `cooling_setpoint`, `unheated_area`, `uncooled_area` |
| `hotwater` (T052) | `ledger_fields` | `hot_water` |
| `efficiency` (T053) | `ledger_fields` | `energy` |
| `fans` (T054) | `ledger_fields` | `fans` |

`FIELD_OWNERS` holds this table. A domain that needs building-wide data (R11's allocation,
R12's hourly attribution, R19's air-loop split) either reads what inventory stored on the zone
record or is passed to `from_zone` as a callable object built with that data (any callable
with the hook signature works), in place of its module function.

Report form
-----------
Ledgers are pydantic models, so the report embeds them directly. In JSON every profile is an
`archetypal.io.EncodedProfile` (base64 little-endian float64 and its length); reading
validates it back into an array, so `GroupLedger.model_validate_json(io.dumps(ledger))` equals
the ledger, profiles included (report invariant 5, T071).

Units are SI (data-model.md): m², W, J, m³/s for flows, m³ for volumes, W/K for UA, J/K for
heat capacity.
"""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from typing import TYPE_CHECKING, Annotated, Any, ClassVar, Literal, Protocol, TypeAlias, cast

import numpy as np
from numpy.typing import NDArray
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PlainSerializer,
    PlainValidator,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from archetypal.io import EncodedProfile
from archetypal.reduction._sql_tables import GainKind

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

    from typing_extensions import Self

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.schedules import ScheduleEvaluator

__all__ = [
    "DOMAIN_MODULES",
    "FIELD_OWNERS",
    "AirflowTotals",
    "EirSums",
    "EnergyTotals",
    "EnvelopeAssignment",
    "EnvelopeClass",
    "EnvelopeTotals",
    "FanTotals",
    "Fuel",
    "GainKind",
    "GainTotals",
    "GroupLedger",
    "HotWaterTotals",
    "Mode",
    "Orientation",
    "OutdoorAirTotals",
    "ProfileArray",
    "WeightedProfile",
    "WindowTotals",
    "ZoneHook",
    "default_hooks",
    "gain_fields",
]

EnvelopeClass = Literal[
    "exterior_wall", "roof", "exposed_floor", "ground_floor", "ground_wall", "partition", "floor_ceiling"
]
"""An opaque surface class (R6). Windows are kept by orientation in `window_by_orientation`;
interior surfaces are `partition` (walls) or `floor_ceiling` (floors and ceilings)."""

Orientation = Literal["N", "NE", "E", "SE", "S", "SW", "W", "NW"]
"""One of eight 45° azimuth sectors, centred on the compass points (R6)."""

Mode = Literal["heating", "cooling", "hot_water"]
"""A conditioning mode. Delivered and fan quantities use heating and cooling; energy also hot water."""

Fuel: TypeAlias = str
"""An EnergyPlus resource name as its meters report it, for example `Electricity`, `NaturalGas`."""

_SECONDS_PER_HOUR = 3600.0


# --- profiles -----------------------------------------------------------------------------


def _to_profile(value: object) -> NDArray[np.float64]:
    if isinstance(value, EncodedProfile):
        array = value.to_array()
    elif isinstance(value, Mapping):
        array = EncodedProfile.model_validate(value).to_array()
    else:
        array = np.array(value, dtype=np.float64)
    if array.ndim != 1:
        msg = f"a profile is one-dimensional, not of shape {array.shape}"
        raise ValueError(msg)
    if not bool(np.isfinite(array).all()):
        msg = "profile values must be finite"
        raise ValueError(msg)
    array.flags.writeable = False
    return array


def _profile_json(array: NDArray[np.float64]) -> dict[str, Any]:
    return EncodedProfile.from_values(array).model_dump(mode="json")


ProfileArray = Annotated[
    NDArray[np.float64],
    PlainValidator(_to_profile),
    PlainSerializer(_profile_json, when_used="json"),
    WithJsonSchema(EncodedProfile.model_json_schema()),
]
"""A profile field: a read-only float64 array in Python, an `EncodedProfile` in JSON.

Validation accepts an array, a sequence of floats, an `EncodedProfile` or its JSON data. An
empty profile (length 0) means "no data" and is the identity of addition."""


def _empty_profile() -> NDArray[np.float64]:
    return _to_profile(())


def _add_profiles(a: NDArray[np.float64], b: NDArray[np.float64]) -> NDArray[np.float64]:
    if a.size == 0:
        return b
    if b.size == 0:
        return a
    if a.size != b.size:
        msg = f"cannot add profiles of length {a.size} and {b.size}; every profile of a reduction has the run period's length"
        raise ValueError(msg)
    return a + b


# --- generic additive models --------------------------------------------------------------


def _add(a: Any, b: Any) -> Any:
    if isinstance(a, _Totals):
        return a + b
    if isinstance(a, np.ndarray):
        return _add_profiles(cast("NDArray[np.float64]", a), b)
    if isinstance(a, dict):
        left, right = cast("dict[Any, Any]", a), cast("dict[Any, Any]", b)
        return {
            key: _add(left[key], right[key]) if key in left and key in right else left.get(key, right.get(key))
            for key in sorted(left.keys() | right.keys())
        }
    return a + b


def _scale(value: Any, factor: float) -> Any:
    if isinstance(value, _Totals):
        return value.scaled(factor)
    if isinstance(value, np.ndarray):
        return value * factor
    if isinstance(value, dict):
        return {key: _scale(item, factor) for key, item in cast("dict[Any, Any]", value).items()}
    if isinstance(value, tuple):
        return tuple(_scale(item, factor) for item in cast("tuple[Any, ...]", value))
    if isinstance(value, str):
        return value
    return value * factor


def _equal(a: Any, b: Any) -> bool:
    if isinstance(a, np.ndarray) or isinstance(b, np.ndarray):
        return isinstance(a, np.ndarray) and isinstance(b, np.ndarray) and bool(np.array_equal(a, b))
    if isinstance(a, dict):
        left = cast("dict[Any, Any]", a)
        right = cast("dict[Any, Any]", b) if isinstance(b, dict) else None
        return right is not None and left.keys() == right.keys() and all(_equal(left[k], right[k]) for k in left)
    if isinstance(a, tuple):
        left_items = cast("tuple[Any, ...]", a)
        return (
            isinstance(b, tuple)
            and len(left_items) == len(cast("tuple[Any, ...]", b))
            and all(_equal(x, y) for x, y in zip(left_items, cast("tuple[Any, ...]", b), strict=True))
        )
    return bool(a == b)


def _profiles_in(value: Any) -> Iterator[NDArray[np.float64]]:
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            yield from _profiles_in(getattr(value, name))
    elif isinstance(value, np.ndarray):
        yield cast("NDArray[np.float64]", value)
    elif isinstance(value, dict):
        for item in cast("dict[Any, Any]", value).values():
            yield from _profiles_in(item)
    elif isinstance(value, tuple):
        for item in cast("tuple[Any, ...]", value):
            yield from _profiles_in(item)


class _Totals(BaseModel):
    """Additive totals: `+` adds field by field, `scaled(k)` multiplies extensive fields by k."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False, arbitrary_types_allowed=True)

    _intensive: ClassVar[frozenset[str]] = frozenset()
    """Fields `scaled` leaves unchanged."""

    @field_validator("*", mode="after")
    @classmethod
    def _sort_dict(cls, value: Any) -> Any:
        if isinstance(value, dict):
            items = cast("dict[Any, Any]", value)
            return {key: items[key] for key in sorted(items)}
        return value

    def _add_field(self, name: str, a: Any, b: Any) -> Any:
        del name
        return _add(a, b)

    def __add__(self, other: object) -> Self:
        """Return the field-wise sum of two totals of the same type."""
        if type(other) is not type(self):
            return NotImplemented
        values = {
            name: self._add_field(name, getattr(self, name), getattr(other, name)) for name in type(self).model_fields
        }
        return type(self)(**values)

    def scaled(self, factor: float) -> Self:
        """Return these totals for `factor` identical copies (extensive fields · `factor`).

        Args:
            factor: The number of copies, for example a zone multiplier.

        Returns:
            The scaled totals.
        """
        values = {
            name: getattr(self, name) if name in self._intensive else _scale(getattr(self, name), factor)
            for name in type(self).model_fields
        }
        return type(self)(**values)

    def __eq__(self, other: object) -> bool:
        """Compare field by field, arrays by value."""
        if type(other) is not type(self):
            return NotImplemented
        return all(_equal(getattr(self, name), getattr(other, name)) for name in type(self).model_fields)

    __hash__ = None  # type: ignore[assignment]  # pyright: ignore[reportAssignmentType]


# --- totals types -------------------------------------------------------------------------


class EnvelopeTotals(_Totals):
    """One opaque surface class of a group (R6, FR-016, FR-017).

    Attributes:
        area: Σ net area, m².
        ua: Σ area · U with films, W/K.
        capacity_inner: Σ heat capacity inside each construction's most resistive layer, J/K.
        capacity_outer: Σ heat capacity outside it, J/K.
        area_by_orientation: Σ area per orientation sector, m².
    """

    area: float = 0.0
    ua: float = 0.0
    capacity_inner: float = 0.0
    capacity_outer: float = 0.0
    area_by_orientation: dict[Orientation, float] = Field(default_factory=dict)


class WindowTotals(_Totals):
    """The windows of one orientation (R6, FR-016, FR-024).

    Attributes:
        area: Σ glazed area, m².
        ua: Σ area · U, W/K.
        a_shgc: Σ area · SHGC, m².
        a_vt: Σ area · visible transmittance, m².
    """

    area: float = 0.0
    ua: float = 0.0
    a_shgc: float = 0.0
    a_vt: float = 0.0


class GainTotals(_Totals):
    """One kind of internal gain (FR-015).

    Attributes:
        installed: Σ design level: W, or people for occupancy.
        hourly: Σ design level · schedule, per hour (W, or people).
        radiant: Annual radiant energy, J.
        latent: Annual latent energy, J.
        lost: Annual energy lost to the zone (lost fraction, and lights' return-air fraction), J.
    """

    installed: float = 0.0
    hourly: ProfileArray = Field(default_factory=_empty_profile)
    radiant: float = 0.0
    latent: float = 0.0
    lost: float = 0.0


class AirflowTotals(_Totals):
    """An airflow: infiltration, or the base of outdoor air (R9, FR-018, FR-019).

    Attributes:
        design_flow: Σ design flow, m³/s.
        hourly: Σ flow per hour, m³/s.
        constant_weighted: Σ design flow · constant coefficient (infiltration).
        temperature_weighted: Σ design flow · temperature coefficient.
        velocity_weighted: Σ design flow · velocity coefficient.
        velocity_squared_weighted: Σ design flow · velocity-squared coefficient.
    """

    design_flow: float = 0.0
    hourly: ProfileArray = Field(default_factory=_empty_profile)
    constant_weighted: float = 0.0
    temperature_weighted: float = 0.0
    velocity_weighted: float = 0.0
    velocity_squared_weighted: float = 0.0


class OutdoorAirTotals(AirflowTotals):
    """Mechanical outdoor air, with heat recovery and economiser categories (R9, FR-019).

    Attributes:
        hrv_weighted: SBEM HRV category → Σ annual outdoor-air volume it serves, m³.
        economiser_weighted: SBEM economiser category → Σ annual outdoor-air volume, m³.
        effectiveness_weighted: Σ annual volume · sensible heat-recovery effectiveness, m³.
    """

    hrv_weighted: dict[str, float] = Field(default_factory=dict)
    economiser_weighted: dict[str, float] = Field(default_factory=dict)
    effectiveness_weighted: float = 0.0


class WeightedProfile(_Totals):
    """An area-weighted hourly profile, such as a setpoint (FR-020).

    Attributes:
        weight: Σ area of the members that count, m².
        weighted: Σ area · value per hour.
    """

    weight: float = 0.0
    weighted: ProfileArray = Field(default_factory=_empty_profile)

    @property
    def value(self) -> NDArray[np.float64] | None:
        """The weighted mean per hour, `weighted / weight`, or `None` with no weight."""
        if self.weight == 0:
            return None
        return self.weighted / self.weight


class HotWaterTotals(_Totals):
    """Domestic hot water (R11, FR-021).

    Attributes:
        volume: Σ hot-water volume per hour, m³.
        heat: Σ volume · temperature rise per hour, m³·K.
    """

    volume: ProfileArray = Field(default_factory=_empty_profile)
    heat: ProfileArray = Field(default_factory=_empty_profile)

    @property
    def mean_rise(self) -> float | None:
        """The volume-weighted mean temperature rise, K, or `None` with no volume."""
        total = float(self.volume.sum())
        if total == 0:
            return None
        return float(self.heat.sum()) / total


class EirSums(_Totals):
    """The additive sums of R12's constrained fit `c_h = (a + b·(T_h - T_ref))·d_h`.

    Each sum runs over (zone, hour) pairs, with d the delivered and c the consumed energy (J)
    and T the outdoor dry-bulb temperature (°C).

    Attributes:
        d: Σ d.
        d_t: Σ d·T.
        d2: Σ d².
        d2_t: Σ d²·T.
        d2_t2: Σ d²·T².
        c: Σ c.
        c_d: Σ c·d.
        c_d_t: Σ c·d·T.
    """

    d: float = 0.0
    d_t: float = 0.0
    d2: float = 0.0
    d2_t: float = 0.0
    d2_t2: float = 0.0
    c: float = 0.0
    c_d: float = 0.0
    c_d_t: float = 0.0

    @classmethod
    def from_hourly(
        cls,
        *,
        consumed: NDArray[np.floating[Any]],
        delivered: NDArray[np.floating[Any]],
        outdoor_temperature: NDArray[np.floating[Any]],
    ) -> EirSums:
        """Return the sums of one zone's hourly consumed and delivered energy.

        Args:
            consumed: Consumed energy per hour, J.
            delivered: Delivered energy per hour, J.
            outdoor_temperature: Outdoor dry-bulb temperature per hour, °C.

        Returns:
            The sums.
        """
        c = np.asarray(consumed, dtype=np.float64)
        d = np.asarray(delivered, dtype=np.float64)
        t = np.asarray(outdoor_temperature, dtype=np.float64)
        d2 = d * d
        return cls(
            d=float(d.sum()),
            d_t=float((d * t).sum()),
            d2=float(d2.sum()),
            d2_t=float((d2 * t).sum()),
            d2_t2=float((d2 * t * t).sum()),
            c=float(c.sum()),
            c_d=float((c * d).sum()),
            c_d_t=float((c * d * t).sum()),
        )


class EnergyTotals(_Totals):
    """Delivered and consumed energy of one mode (R12, FR-022).

    Attributes:
        delivered: Σ delivered energy, J.
        consumed_by_fuel: Σ consumed energy of the primary meters per fuel, J.
        distribution_by_fuel: Σ pump and heat-rejection energy folded into this mode (and fans
            until UP-8, R19) per fuel, J.
        unattributed: Consumption in hours without delivery (standby, pilot) per fuel, J.
        rated_weight: Σ weight of the rated efficiencies (for example rated capacity).
        rated_weighted: Σ weight · rated efficiency, from *Equipment Summary*.
        eir_sums: The sums of the energy-input-ratio fit.
    """

    delivered: float = 0.0
    consumed_by_fuel: dict[Fuel, float] = Field(default_factory=dict)
    distribution_by_fuel: dict[Fuel, float] = Field(default_factory=dict)
    unattributed: dict[Fuel, float] = Field(default_factory=dict)
    rated_weight: float = 0.0
    rated_weighted: float = 0.0
    eir_sums: EirSums = Field(default_factory=EirSums)

    @property
    def rated_efficiency(self) -> float | None:
        """The weighted mean rated efficiency, used only when `delivered == 0`, or `None`."""
        if self.rated_weight == 0:
            return None
        return self.rated_weighted / self.rated_weight


class FanTotals(_Totals):
    """Fan energy and air volume (R19, FR-022a).

    Attributes:
        energy: Σ fan electricity, J.
        volume: Σ air volume at standard density, m³.
        volume_in_mode: Σ air volume in hours of each mode, m³.
        delivered_in_mode: Σ delivered energy in those hours, J.
        volume_without_demand: Σ air volume in hours with neither load nor outdoor-air demand, m³.
    """

    energy: float = 0.0
    volume: float = 0.0
    volume_in_mode: dict[Mode, float] = Field(default_factory=dict)
    delivered_in_mode: dict[Mode, float] = Field(default_factory=dict)
    volume_without_demand: float = 0.0


class EnvelopeAssignment(_Totals):
    """Envelope of an excluded zone assigned to a conditioned member (R6, R8, FR-013).

    The assigned totals themselves are added to the member's `envelope`; this records where
    they came from, for the report.

    Attributes:
        source_zone: The excluded zone (plenum, attic, crawlspace...).
        target_zone: The conditioned zone that receives the envelope.
        envelope_class: The class of the assigned surfaces.
        area: The area assigned, m² (extensive).
        share: The target's share of the source's envelope of that class, by shared area.
    """

    _intensive: ClassVar[frozenset[str]] = frozenset({"share"})

    source_zone: str
    target_zone: str
    envelope_class: EnvelopeClass
    area: float
    share: float = Field(ge=0.0, le=1.0)

    def sort_key(self) -> tuple[str, str, str, float, float]:
        """The order assignments are held in."""
        return (self.source_zone, self.target_zone, self.envelope_class, self.share, self.area)

    def __add__(self, other: object) -> Self:  # noqa: D105 - an assignment is a record, not a total
        return NotImplemented


# --- the ledger ---------------------------------------------------------------------------


class GroupLedger(_Totals):
    """The conserved totals of a group of zones (data-model.md: GroupLedger).

    Attributes:
        members: The zone names, sorted (FR-025 provenance).
        floor_area: Σ floor area, multipliers applied, m² (FR-014).
        envelope: Opaque totals per surface class (FR-016, FR-017).
        window_by_orientation: Window totals per orientation (FR-016, FR-024).
        internal_mass_capacity: Σ heat capacity of internal mass, J/K (FR-017).
        internal_mass_area: Σ exposed area of internal mass, m².
        gains: Totals per gain kind (FR-015).
        infiltration: Infiltration (FR-018).
        outdoor_air: Mechanical outdoor air with HRV and economiser categories (FR-019).
        heating_setpoint: Area-weighted heating setpoint of the heated members (FR-020).
        cooling_setpoint: Area-weighted cooling setpoint of the cooled members (FR-020).
        unheated_area: Σ floor area of members not heated, m².
        uncooled_area: Σ floor area of members not cooled, m².
        hot_water: Domestic hot water (FR-021).
        energy: Delivered and consumed energy per mode (FR-022).
        fans: Fan energy and air volume (FR-022a).
        excluded_envelope: Envelope of excluded zones assigned to members, sorted (FR-013).
    """

    members: tuple[str, ...] = ()
    floor_area: float = 0.0
    envelope: dict[EnvelopeClass, EnvelopeTotals] = Field(default_factory=dict)
    window_by_orientation: dict[Orientation, WindowTotals] = Field(default_factory=dict)
    internal_mass_capacity: float = 0.0
    internal_mass_area: float = 0.0
    gains: dict[GainKind, GainTotals] = Field(default_factory=dict)
    infiltration: AirflowTotals = Field(default_factory=AirflowTotals)
    outdoor_air: OutdoorAirTotals = Field(default_factory=OutdoorAirTotals)
    heating_setpoint: WeightedProfile = Field(default_factory=WeightedProfile)
    cooling_setpoint: WeightedProfile = Field(default_factory=WeightedProfile)
    unheated_area: float = 0.0
    uncooled_area: float = 0.0
    hot_water: HotWaterTotals = Field(default_factory=HotWaterTotals)
    energy: dict[Mode, EnergyTotals] = Field(default_factory=dict)
    fans: FanTotals = Field(default_factory=FanTotals)
    excluded_envelope: tuple[EnvelopeAssignment, ...] = ()

    _OWN_FIELDS: ClassVar[frozenset[str]] = frozenset({"members", "floor_area"})

    @field_validator("members", mode="after")
    @classmethod
    def _sorted_members(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if len(set(value)) != len(value):
            msg = f"members must be distinct: {value}"
            raise ValueError(msg)
        return tuple(sorted(value))

    @field_validator("excluded_envelope", mode="after")
    @classmethod
    def _sorted_assignments(cls, value: tuple[EnvelopeAssignment, ...]) -> tuple[EnvelopeAssignment, ...]:
        return tuple(sorted(value, key=EnvelopeAssignment.sort_key))

    @model_validator(mode="after")
    def _one_profile_length(self) -> Self:
        lengths = {profile.size for profile in _profiles_in(self) if profile.size}
        if len(lengths) > 1:
            msg = f"every profile of a ledger has the same length, not {sorted(lengths)}"
            raise ValueError(msg)
        return self

    @property
    def hours(self) -> int | None:
        """The length of the ledger's profiles, or `None` when it holds none."""
        return next((profile.size for profile in _profiles_in(self) if profile.size), None)

    def _add_field(self, name: str, a: Any, b: Any) -> Any:
        if name == "members":
            shared = set(a) & set(b)
            if shared:
                msg = f"cannot add ledgers that share members {sorted(shared)}: each zone is counted once"
                raise ValueError(msg)
            return tuple(sorted((*a, *b)))
        if name == "excluded_envelope":
            return (*a, *b)
        return super()._add_field(name, a, b)

    def __radd__(self, other: object) -> Self:
        """Support `sum(ledgers)`, which starts from 0."""
        if isinstance(other, int) and other == 0:
            return self
        return NotImplemented

    @classmethod
    def from_zone(
        cls,
        zone: ClassifiedZone,
        schedules: ScheduleEvaluator,
        *,
        hooks: Sequence[ZoneHook] | None = None,
    ) -> GroupLedger:
        """Build one zone's ledger, applying its multiplier exactly once.

        Args:
            zone: The classified zone; `zone.zone` is its `ZoneRecord` (name, multiplier,
                floor area of one copy).
            schedules: The model's schedule evaluator, passed to every hook.
            hooks: The domain hooks; `None` uses `default_hooks()`.

        Returns:
            The ledger of all copies of the zone.

        Raises:
            ValueError: If the multiplier is below 1, or a hook returns `members`,
                `floor_area`, an unknown field, or a field another hook returned.
        """
        record = zone.zone
        multiplier = record.multiplier
        if multiplier < 1:
            msg = f"zone {record.name!r} has multiplier {multiplier}; a multiplier is at least 1"
            raise ValueError(msg)
        values: dict[str, object] = {}
        for hook in default_hooks() if hooks is None else hooks:
            for name, value in hook(zone, schedules).items():
                if name in cls._OWN_FIELDS or name not in cls.model_fields:
                    msg = f"a domain hook returned {name!r}, which is not a ledger field it may set"
                    raise ValueError(msg)
                if name in values:
                    msg = f"two domain hooks returned the ledger field {name!r}"
                    raise ValueError(msg)
                values[name] = value
        one_copy = cls(members=(record.name,), floor_area=record.floor_area, **cast("dict[str, Any]", values))
        return one_copy if multiplier == 1 else one_copy.scaled(multiplier)


# --- domain hooks -------------------------------------------------------------------------


class ZoneHook(Protocol):
    """A domain's contribution to a zone's ledger: field name → value, for one copy of the zone."""

    def __call__(self, zone: ClassifiedZone, schedules: ScheduleEvaluator, /) -> Mapping[str, object]:
        """Return ledger fields for one copy of `zone` (multiplier not applied)."""
        ...


DOMAIN_MODULES: tuple[str, ...] = ("envelope", "airflow", "thermostats", "hotwater", "efficiency", "fans")
"""The modules of `archetypal.reduction` whose `ledger_fields` function is a default hook."""

FIELD_OWNERS: Mapping[str, tuple[str, ...]] = {
    "gains": ("gains",),
    "envelope": (
        "envelope",
        "window_by_orientation",
        "internal_mass_capacity",
        "internal_mass_area",
        "excluded_envelope",
    ),
    "airflow": ("infiltration", "outdoor_air"),
    "thermostats": ("heating_setpoint", "cooling_setpoint", "unheated_area", "uncooled_area"),
    "hotwater": ("hot_water",),
    "efficiency": ("energy",),
    "fans": ("fans",),
}
"""Which hook fills which ledger fields (`gains` is this module's `gain_fields`)."""


def default_hooks() -> tuple[ZoneHook, ...]:
    """Return `gain_fields` and each domain module's `ledger_fields`, importing the modules lazily.

    Returns:
        The hooks, in `FIELD_OWNERS` order.
    """
    hooks: list[ZoneHook] = [gain_fields]
    for name in DOMAIN_MODULES:
        module = importlib.import_module(f"archetypal.reduction.{name}")
        hooks.append(cast("ZoneHook", module.ledger_fields))
    return tuple(hooks)


class _GainLike(Protocol):
    """The attributes of a `GainRecord` that `gain_fields` reads (names as `NominalLoadRow`'s)."""

    @property
    def kind(self) -> GainKind: ...
    @property
    def design_level(self) -> float: ...
    @property
    def schedule_name(self) -> str | None: ...
    @property
    def fraction_radiant(self) -> float: ...
    @property
    def fraction_latent(self) -> float | None: ...
    @property
    def fraction_lost(self) -> float: ...


def gain_fields(
    zone: ClassifiedZone, schedules: Callable[[str], NDArray[np.float64]] | ScheduleEvaluator, hours: int | None = None
) -> dict[str, object]:
    """The `gains` hook: installed level, hourly profile and annual parts per gain kind, one copy.

    For each `GainRecord` of the zone, the hourly profile is design level · its schedule (a
    gain without a schedule is always on). Annual radiant, latent and lost energy are the
    annual energy (Σ hourly · 3600 s) times the record's fractions; lights' return-air fraction
    counts as lost. People's parts are 0: their heat follows an activity level the record does
    not carry, and `installed` counts people.

    Args:
        zone: The classified zone; its record's `gains` are read.
        schedules: The schedule evaluator (any callable from schedule name to hourly profile).
        hours: The profile length for gains without a schedule; by default the evaluator's
            calendar hours.

    Returns:
        `{"gains": {kind: GainTotals}}`.

    Raises:
        ValueError: If a gain has no schedule and the profile length is unknown.
    """
    totals: dict[GainKind, GainTotals] = {}
    record = zone.zone
    for gain in cast("Sequence[_GainLike]", record.gains):
        if gain.schedule_name is None:
            length = hours if hours is not None else getattr(getattr(schedules, "calendar", None), "hours", None)
            if length is None:
                msg = f"gain of kind {gain.kind!r} in zone {record.name!r} has no schedule and the run period's length is unknown"
                raise ValueError(msg)
            fraction = np.ones(int(length))
        else:
            fraction = np.asarray(schedules(gain.schedule_name), dtype=np.float64)
        hourly = gain.design_level * fraction
        if gain.kind == "people":
            radiant = latent = lost = 0.0
        else:
            energy = float(hourly.sum()) * _SECONDS_PER_HOUR
            radiant = energy * gain.fraction_radiant
            latent = energy * (gain.fraction_latent or 0.0)
            lost = energy * (gain.fraction_lost + float(getattr(gain, "fraction_return_air", 0.0)))
        part = GainTotals(installed=gain.design_level, hourly=hourly, radiant=radiant, latent=latent, lost=lost)
        totals[gain.kind] = totals[gain.kind] + part if gain.kind in totals else part
    return {"gains": totals}
