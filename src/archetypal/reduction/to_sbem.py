"""Ledgers to an SBEM archetype: one function per SBEM component (spec 002, data-model.md, FR-025).

Each function below derives one SBEM component of a group from the group's ledger (and, where a
rule needs it, the building's ledger or calendar) and returns a `Derived`: the component, the
rule id of data-model.md's derivation table that produced it, the rule of every leaf field it
sets, and what the component cannot hold (`NotRepresented`, FR-026). `to_archetype` assembles
the groups into the fork's `Archetype`, validates it, and returns the archetype with its
`parameters[]` entries (report invariant 3) and `not_represented[]` entries.

| SBEM field | Function | Rule id |
|---|---|---|
| `ZoneGroup.FloorAreaShare`, `Geometry.ConditionedFloorArea` | `floor_area_share`, `geometry` | `area.share` |
| `Occupancy`, `Lighting`, `Equipment` density and `IsOn` | `occupancy`, `lighting`, `equipment` | `gain.density` |
| every gain's, infiltration's, ventilation's and water's `Schedule` | (in each) | `schedule.normalised` |
| `Thermostat` | `thermostat` | `setpoint.area_mean` |
| `Assemblies.*Assembly` | `assemblies` | `envelope.equivalent` |
| `InternalMassAssembly`, `InternalMassExposedAreaPerArea` | `assemblies` | `mass.internal` |
| `Window`, `Geometry.WindowToWallRatio` | `window`, `geometry` | `window.area_weighted` |
| `Infiltration` | `infiltration` | `airflow.mean_per_exterior_area` |
| `Ventilation.FreshAirPerFloorArea`, `FreshAirPerPerson`, `Provider`, `DCV` | `ventilation` | `airflow.peak_per_area` |
| `Ventilation.MechVentSchedule` (UP-9) | `ventilation` | `schedule.normalised` |
| `Ventilation.HRV`, `Economizer`, `*HeatRecoveryEffectiveness` | `ventilation` | `airflow.dominant_category` |
| `WaterUse` | `water_use` | `dhw.volume_per_person` |
| `DHW` temperatures | `dhw` | `dhw.mains_plus_rise` |
| `ThermalSystemComponent`, `DHW` COPs, fuel | `thermal_system`, `dhw` | `efficiency.delivered_over_consumed`, `rated` |
| `ThermalSystemComponent.EIRTemperatureSlope`, `EIRReferenceTemperature` | `thermal_system` | `efficiency.eir_linear` |
| `ConditioningSystems.SpecificFanPower` (UP-8) | `conditioning_systems` | `fans.energy_per_volume` |
| `ConditioningSystems.*SupplyAirTemperature` (UP-8) | `conditioning_systems` | `fans.effective_supply_delta` |
| `Attic`, `Basement` and their infiltration | `attic`, `basement` | `zone.attic`, `zone.basement` |
| `Geometry.Storeys` | `storeys` | `geometry.storeys` |
| `Geometry.Facade…`, `Roof…`, `ExposedFloor…`, `GroundContact…` | `geometry` | `envelope.equivalent` |

Decisions of this module (spec gaps)
------------------------------------
- **Parameters.** A parameter is a leaf field the archetype *sets* (pydantic's fields set),
  except names and metadata (`Name`, `Category`, `Comment`, `DataSource`, `Version`) and the
  group's `Exposure`, which is its key (`groups[].key`). A `YearComponent` (value: its name)
  and a `ConstructionAssemblyComponent` (value: name and U with films) count as one leaf
  each; a dict such as `WindowToWallRatio` is one leaf. Paths are dotted from the `ZoneGroup`
  (`Zone.Operations.SpaceUse.Occupancy.PeopleDensity`) or, with `group = None`, from the
  `Archetype` (`Geometry.Storeys`). `set_leaf_paths` lists them for invariant 3.
- **Schedules** are projected with each month's holidays averaged into their weekdays
  (`project`): epinterface's builder declares no holiday (`RunPeriodControl:SpecialDays`, and
  `use_weather_file_holidays_and_special_days = No`), so a `Holiday` slot would never apply and
  the holidays would run as working days. Each month's energy is conserved on the calendar the
  archetype runs; the lost holiday profile is listed as not represented. Every schedule sets its `SummerDesignDay` and
  `WinterDesignDay` slots in every week, so epinterface's builder sizes with them instead of its
  own design days (always-on gains, extreme setpoints). Gains, setpoints and infiltration take
  the ledger's design days (`DesignDays`), weighted as their run-period profiles and normalised
  by the same level. Outdoor air and hot water come from run-period results, which hold no
  design day: their slots repeat each month's Monday and are listed as not represented
  (`design_days_from_results`). A total whose design days do not cover every member (only
  when merging ledgers rebuilt from an archetype) leaves the slots unset, listed too.
- **Infiltration** carries the annual-mean flow per exterior area (exterior walls, roofs,
  exposed floors and windows: the gross outdoor area EnergyPlus's `Flow/ExteriorArea` uses)
  and, with UP-2's schedule, `project(hourly / mean)` as an `AnyNumber` multiplier, so mean ·
  schedule reproduces the hourly profile.
- **Supply-air temperature limits** start from the group's highest heating and lowest cooling
  setpoint (the occupied setpoints, where most delivery happens), design days included, since
  the ideal loads refuse a limit beyond the setpoint they size with. A pair that would put the
  heating limit at or below the cooling limit keeps the mode with more delivered energy and
  leaves the other at epinterface's default, listing it as not represented.
- **Assemblies** take the first class of `SLOT_CLASSES` the group has, else the building
  has (the group's own surfaces first for each class): every slot of SBEM's
  `EnvelopeAssemblyComponent` is required, and a slot without area changes no conserved total.
  Attics' and plenums' envelope is already carried by the conditioned zones (FR-013), so the
  attic and basement are unused and
  unconditioned (`zone.attic`, `zone.basement`), and their infiltration is off.
- **Fuels** map to SBEM's names; district heating becomes `Steam` and other fuels `CustomFuel`,
  which is listed as not represented.
- Simple `ZoneVentilation` (natural ventilation by design flow rate) has no SBEM field in the
  pinned fork: `simple_ventilation_not_represented(zones)` lists it.
"""

from __future__ import annotations

import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Generic, Literal, TypeVar, cast

import numpy as np
from epinterface.constants import assumed_constants, physical_constants
from epinterface.sbem.archetype import (
    Archetype,
    AtticAssumptions,
    BasementAssumptions,
    BuildingGeometry,
    ZoneGroup,
)
from epinterface.sbem.components.envelope import (
    ConstructionAssemblyComponent,
    EnvelopeAssemblyComponent,
    GlazingConstructionSimpleComponent,
    InfiltrationComponent,
    ZoneEnvelopeComponent,
)
from epinterface.sbem.components.operations import ZoneOperationsComponent
from epinterface.sbem.components.schedules import YearComponent
from epinterface.sbem.components.space_use import (
    EquipmentComponent,
    LightingComponent,
    OccupancyComponent,
    ThermostatComponent,
    WaterUseComponent,
    ZoneSpaceUseComponent,
)
from epinterface.sbem.components.systems import (
    ConditioningSystemsComponent,
    DHWComponent,
    ThermalSystemComponent,
    VentilationComponent,
    ZoneHVACComponent,
)
from epinterface.sbem.components.zones import ZoneComponent
from pydantic import BaseModel, ValidationError

from archetypal.errors import ReductionError
from archetypal.reduction.efficiency import fit_eir
from archetypal.reduction.envelope import (
    equivalent_construction,
    internal_mass_construction,
    window_construction,
)
from archetypal.reduction.fans import effective_supply_delta, specific_fan_power, standard_air_density
from archetypal.reduction.features import NotRepresented
from archetypal.reduction.ledger import (
    DesignDays,
    EnvelopeClass,
    EnvelopeTotals,
    GainKind,
    GroupLedger,
    Mode,
    Orientation,
    WeightedProfile,
    WindowTotals,
)
from archetypal.reduction.report import Parameter, group_name
from archetypal.reduction.schedules import project, to_year_component

if TYPE_CHECKING:
    import numpy.typing as npt
    from epinterface.sbem.components.schedules import ScheduleTypeLimitType, YearScheduleCategory
    from pydantic import JsonValue

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.grouping import Group
    from archetypal.reduction.options import Layout
    from archetypal.reduction.schedules import RunPeriodCalendar

__all__ = [
    "EQUIPMENT_KINDS",
    "IDEAL_LOADS_LIMITS",
    "LOWEST_LEVEL_TOLERANCE",
    "SLOT_CLASSES",
    "BuildingFacts",
    "Conversion",
    "Derived",
    "LeafRule",
    "assemblies",
    "attic",
    "basement",
    "conditioning_systems",
    "design_days_from_results",
    "dhw",
    "equipment",
    "floor_area_share",
    "geometry",
    "infiltration",
    "lighting",
    "occupancy",
    "set_leaf_paths",
    "simple_ventilation_not_represented",
    "storey_ratio",
    "storeys",
    "thermal_system",
    "thermostat",
    "to_archetype",
    "ventilation",
    "water_use",
    "window",
    "zone_group",
]

T = TypeVar("T")

ORIENTATIONS: tuple[Orientation, ...] = ("N", "NE", "E", "SE", "S", "SW", "W", "NW")
EQUIPMENT_KINDS: tuple[GainKind, ...] = ("electric", "gas", "steam", "hot_water_equipment", "other")
"""The gain kinds SBEM's single `EquipmentComponent` sums (data-model.md, rule `gain.density`)."""
_NON_ELECTRIC_KINDS: tuple[GainKind, ...] = ("gas", "steam", "hot_water_equipment")

LOWEST_LEVEL_TOLERANCE = 0.1
"""Conditioned zones whose `MinimumZ` is within this many metres of the lowest form the lowest level (R6)."""

SLOT_CLASSES: Mapping[str, tuple[EnvelopeClass, ...]] = {
    "FacadeAssembly": ("exterior_wall", "ground_wall", "partition"),
    "FlatRoofAssembly": ("roof", "floor_ceiling"),
    "AtticRoofAssembly": ("roof", "floor_ceiling"),
    "FloorCeilingAssembly": ("floor_ceiling", "partition", "ground_floor", "exposed_floor"),
    "AtticFloorAssembly": ("floor_ceiling", "partition", "roof", "exterior_wall"),
    "PartitionAssembly": ("partition", "floor_ceiling", "exterior_wall"),
    "ExternalFloorAssembly": ("exposed_floor", "ground_floor", "floor_ceiling"),
    "GroundSlabAssembly": ("ground_floor", "exposed_floor", "floor_ceiling"),
    "GroundWallAssembly": ("ground_wall", "exterior_wall"),
    "BasementCeilingAssembly": ("floor_ceiling", "partition", "ground_floor", "exposed_floor", "roof", "exterior_wall"),
}
"""The surface classes each SBEM assembly slot is built from, in order of preference. Each list
ends with a class every building has, so a slot the building does not use still gets an assembly."""

_SLOT_TYPES: Mapping[str, str] = {
    "FacadeAssembly": "Facade",
    "FlatRoofAssembly": "FlatRoof",
    "AtticRoofAssembly": "AtticRoof",
    "FloorCeilingAssembly": "FloorCeiling",
    "AtticFloorAssembly": "AtticFloor",
    "PartitionAssembly": "Partition",
    "ExternalFloorAssembly": "ExternalFloor",
    "GroundSlabAssembly": "GroundSlab",
    "GroundWallAssembly": "GroundWall",
    "BasementCeilingAssembly": "BasementCeiling",
}

_SUPPLY_HEATING_RANGE = (0.0, 100.0)  # epinterface's open bounds, °C
_SUPPLY_COOLING_RANGE = (-100.0, 50.0)
_HEATING_OFF, _COOLING_OFF = 5.0, 35.0  # thermostats.BAND edges: the mode stays off
_SECONDS_PER_HOUR = 3600.0
_ARCHETYPE_DAYS = 365
"""Days of the year epinterface's builder simulates (a `RunPeriod` with no begin year)."""
_STOREY_TIE_TOLERANCE = 1e-9
_WATTS_PER_MET = assumed_constants.AvgHumanWeight_kg * physical_constants.ConversionFactor_W_per_kg
"""W per person for 1 met in epinterface's people (`OccupancyComponent.MetabolicRate_met_to_W`)."""
_HOURS_PER_DAY = 24
_METADATA = frozenset({"Name", "Category", "Comment", "DataSource", "Version"})
_ATOMIC: tuple[type[BaseModel], ...] = (YearComponent, ConstructionAssemblyComponent)

_FUELS: Mapping[str, str] = {
    "electricity": "Electricity",
    "naturalgas": "NaturalGas",
    "propane": "Propane",
    "fueloil": "FuelOil",
    "fueloilno1": "FuelOil",
    "fueloilno2": "FuelOil",
    "coal": "Coal",
    "gasoline": "Gasoline",
    "diesel": "Diesel",
    "steam": "Steam",
    "districtheatingsteam": "Steam",
    "districtcooling": "ChilledWater",
    "chilledwater": "ChilledWater",
}
_DHW_FUELS = frozenset({"Electricity", "NaturalGas", "Propane", "FuelOil", "Steam"})


# --- results ---------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LeafRule:
    """The rule of one leaf field a component sets.

    Attributes:
        path: The dotted path, relative to the component.
        value: The value written (JSON).
        rule: The rule id.
    """

    path: str
    value: JsonValue
    rule: str


@dataclass(frozen=True)
class Derived(Generic[T]):
    """A derived SBEM value.

    Attributes:
        value: The component (or number).
        rule: The rule id that produced it (the main one when its fields use several).
        leaves: The rule of every leaf field it sets, paths relative to it.
        not_represented: What it cannot hold (FR-026).
    """

    value: T
    rule: str
    leaves: tuple[LeafRule, ...] = ()
    not_represented: tuple[NotRepresented, ...] = ()


@dataclass(frozen=True)
class BuildingFacts:
    """Building-wide facts the rules need besides the ledgers.

    Attributes:
        calendar: The run-period calendar the ledgers' profiles follow.
        storey_ratio: Conditioned floor area ÷ floor area of the lowest level (`storey_ratio`).
        mains_temperature: The annual-mean mains water temperature, °C, or `None` without hot water.
        air_density: The standard air density of the fan volumes, kg/m³.
    """

    calendar: RunPeriodCalendar
    storey_ratio: float
    mains_temperature: float | None = None
    air_density: float = field(default_factory=lambda: standard_air_density(0.0))


@dataclass(frozen=True)
class Conversion:
    """The archetype and what the report needs from the conversion.

    Attributes:
        archetype: The fork's validated archetype.
        parameters: One entry per set leaf field (report invariant 3).
        not_represented: What the archetype cannot hold (FR-026), from the conversion.
        conditioned_floor_area: Σ floor area of the groups, m².
        storey_ratio: The unrounded storey ratio (report's `building` block).
    """

    archetype: Archetype
    parameters: tuple[Parameter, ...]
    not_represented: tuple[NotRepresented, ...]
    conditioned_floor_area: float
    storey_ratio: float


# --- helpers -----------------------------------------------------------------------------------


def _leaf_value(value: object) -> JsonValue:
    if isinstance(value, YearComponent):
        return value.Name
    if isinstance(value, ConstructionAssemblyComponent):
        return {"Name": value.Name, "RValue": value.r_value}
    if isinstance(value, BaseModel):
        return cast("JsonValue", value.model_dump(mode="json"))
    if isinstance(value, Mapping):
        return {str(k): cast("JsonValue", v) for k, v in cast("Mapping[object, object]", value).items()}
    return cast("JsonValue", value)


def _set_leaves(model: BaseModel, prefix: str = "") -> Iterable[tuple[str, object]]:
    for name in type(model).model_fields:
        if name not in model.model_fields_set or name in _METADATA:
            continue
        value = getattr(model, name)
        path = f"{prefix}{name}"
        if isinstance(value, BaseModel) and not isinstance(value, _ATOMIC):
            yield from _set_leaves(value, f"{path}.")
        else:
            yield path, value


def _leaves(model: BaseModel, rules: Mapping[str, str], default: str) -> tuple[LeafRule, ...]:
    """Assign each set leaf the rule of its longest matching path prefix in `rules`, else `default`."""
    out: list[LeafRule] = []
    for path, value in _set_leaves(model):
        rule = default
        best = -1
        for prefix, candidate in rules.items():
            if (path == prefix or path.startswith(f"{prefix}.")) and len(prefix) > best:
                rule, best = candidate, len(prefix)
        out.append(LeafRule(path, _leaf_value(value), rule))
    return tuple(out)


def _nested(prefix: str, derived: Derived[Any]) -> tuple[LeafRule, ...]:
    return tuple(LeafRule(f"{prefix}.{leaf.path}", leaf.value, leaf.rule) for leaf in derived.leaves)


def _profile(values: npt.NDArray[np.float64], calendar: RunPeriodCalendar) -> npt.NDArray[np.float64]:
    array = np.asarray(values, dtype=np.float64)
    return np.zeros(calendar.hours) if array.size == 0 else array


DesignValues = tuple["npt.NDArray[np.float64]", "npt.NDArray[np.float64]"]
"""A schedule's summer and winter design days: 24 values each, or (12, 24) for one per month."""


def _schedule(
    hourly: npt.NDArray[np.float64],
    calendar: RunPeriodCalendar,
    *,
    name: str,
    category: YearScheduleCategory,
    limits: ScheduleTypeLimitType | None = None,
    design: DesignValues | Literal["monday"] | None = None,
) -> YearComponent:
    """Project an hourly profile into a schedule, its design-day slots from `design`.

    `design` gives the slots' values; `"monday"` sets each month's slots to that month's Monday,
    the day epinterface's builder would use; `None` leaves them unset.
    """
    days = project(_profile(hourly, calendar), calendar)
    if isinstance(design, str):
        design = (days[:, 0, :], days[:, 0, :])
    summer, winter = (None, None) if design is None else design
    return to_year_component(
        days,
        name=name,
        category=category,
        limits=limits,
        summer_design_day=summer,
        winter_design_day=winter,
    )


def _design(days: DesignDays, weight: float, scale: float | None = None) -> DesignValues | None:
    """The design days of a total of `weight`, divided by `scale` (default `weight`), when complete.

    A total with no weight has design days of zero, as its run-period profile; one whose design
    days do not cover its weight has none (`None`).
    """
    divisor = weight if scale is None else scale
    if weight == 0 or divisor == 0:
        zeros = np.zeros(_HOURS_PER_DAY)
        return zeros, zeros
    if not days.complete(weight):
        return None
    return days.summer / divisor, days.winter / divisor


def design_days_from_results(ledger: GroupLedger, name: str, quantity: str, path: str) -> NotRepresented:
    """The entry for a schedule whose profile comes from run-period results (outdoor air, hot water).

    The results of the weather-file run period hold no design day, so the schedule's design-day
    slots are set to each month's Monday, the day epinterface's builder would use without them.

    Args:
        ledger: The group's ledger.
        name: The group's name.
        quantity: What the schedule carries, for example `outdoor air`.
        path: The SBEM component whose schedule it is.

    Returns:
        The entry.
    """
    return _entry(
        ledger,
        name,
        f"Design-day {quantity} profile",
        f"The {quantity} profile comes from the run-period results, which hold no design day, so the design-day "
        f"slots of its schedules in {path} repeat each month's Monday.",
        source="schedules",
    )


def _design_lost(ledger: GroupLedger, name: str, schedule: str) -> NotRepresented:
    return _entry(
        ledger,
        name,
        f"Design-day profile of the {schedule} schedule",
        "Some members' design-day profiles are unknown, so the schedule's design-day slots are unset and "
        "epinterface's builder uses its own design days.",
        source="schedules",
    )


def _ratio(numerator: npt.NDArray[np.float64], denominator: float) -> npt.NDArray[np.float64]:
    return numerator / denominator if denominator > 0 else np.zeros_like(numerator)


def _entry(
    ledger: GroupLedger,
    group: str,
    feature: str,
    effect: str,
    *,
    magnitude: float | None = None,
    unit: str | None = None,
    folded_into: str | None = None,
    source: Literal["to_sbem", "schedules", "airflow", "efficiency", "fans", "hotwater", "envelope"] = "to_sbem",
) -> NotRepresented:
    return NotRepresented(
        feature=feature,
        effect=effect,
        affected_zones=ledger.members,
        affected_groups=(group,),
        magnitude=magnitude,
        unit=unit,
        folded_into=folded_into,
        source=source,
    )


def _sbem_fuel(fuel: str) -> str:
    key = fuel.casefold().replace(" ", "")
    if key in _FUELS:
        return _FUELS[key]
    if key.startswith("districtheating"):
        return "Steam"
    return "CustomFuel"


def _dominant(values: Mapping[str, float]) -> str | None:
    positive = {k: v for k, v in values.items() if v > 0}
    if not positive:
        return None
    return max(sorted(positive), key=lambda k: positive[k])


# --- area and geometry -----------------------------------------------------------------------------


def floor_area_share(ledger: GroupLedger, total_floor_area: float) -> Derived[float]:
    """`ZoneGroup.FloorAreaShare = floor_area / Σ floor_area` (rule `area.share`, FR-014).

    Args:
        ledger: The group's ledger.
        total_floor_area: Σ floor area of every group, m².

    Returns:
        The share.
    """
    share = ledger.floor_area / total_floor_area
    return Derived(share, "area.share", (LeafRule("FloorAreaShare", share, "area.share"),))


def storey_ratio(zones: Iterable[ClassifiedZone]) -> float:
    """Conditioned floor area ÷ floor area of the lowest level, multipliers applied (R6).

    The lowest level is the conditioned zones whose `MinimumZ` is within
    `LOWEST_LEVEL_TOLERANCE` of the lowest conditioned zone's.

    Args:
        zones: The classified zones; only conditioned ones count.

    Returns:
        The unrounded ratio.

    Raises:
        ValueError: If no conditioned zone has floor area.
    """
    conditioned = [z.zone for z in zones if z.role == "conditioned"]
    if not conditioned:
        msg = "no conditioned zone to count storeys from"
        raise ValueError(msg)
    lowest = min(z.min_z for z in conditioned)
    total = sum(z.floor_area * z.multiplier for z in conditioned)
    ground = sum(z.floor_area * z.multiplier for z in conditioned if z.min_z <= lowest + LOWEST_LEVEL_TOLERANCE)
    if not ground > 0:
        msg = "the lowest conditioned level has no floor area"
        raise ValueError(msg)
    return total / ground


def storeys(ratio: float) -> Derived[int]:
    """`Geometry.Storeys`: the storey ratio rounded to the nearest integer, halves up, at least 1 (`geometry.storeys`).

    Args:
        ratio: The unrounded ratio (`storey_ratio`).

    Returns:
        The number of storeys.
    """
    # A tolerance on the tie, so a half that summation left one ulp low still rounds up.
    value = max(1, math.floor(ratio + 0.5 + _STOREY_TIE_TOLERANCE))
    return Derived(value, "geometry.storeys", (LeafRule("Storeys", value, "geometry.storeys"),))


def geometry(building: GroupLedger, ratio: float) -> Derived[BuildingGeometry]:
    """The archetype's geometry characteristics (FR-024; UP-2's per-orientation ratios).

    Per orientation, the gross facade is the exterior wall area plus its windows in walls
    (skylights, roof and floor windows are not facade); the window-to-wall ratio is window ÷
    gross facade (0 without facade). Areas are per conditioned floor area.

    Args:
        building: The sum of every group's ledger.
        ratio: The unrounded storey ratio.

    Returns:
        The geometry.
    """
    cfa = building.floor_area
    walls = building.envelope.get("exterior_wall", EnvelopeTotals())
    wwr: dict[Orientation, float] = {}
    facade: dict[Orientation, float] = {}
    for o in ORIENTATIONS:
        window_area = building.window_by_orientation.get(o, WindowTotals()).area
        gross = walls.area_by_orientation.get(o, 0.0) + window_area
        wwr[o] = min(window_area / gross, 1.0) if gross > 0 else 0.0
        facade[o] = gross / cfa

    def area(*classes: EnvelopeClass) -> float:
        return sum(building.envelope.get(c, EnvelopeTotals()).area for c in classes) / cfa

    value = BuildingGeometry(
        Storeys=storeys(ratio).value,
        ConditionedFloorArea=cfa,
        WindowToWallRatio=wwr,
        FacadeAreaPerFloorArea=facade,
        RoofAreaPerFloorArea=area("roof"),
        ExposedFloorAreaPerFloorArea=area("exposed_floor"),
        GroundContactAreaPerFloorArea=area("ground_floor", "ground_wall"),
    )
    rules = {
        "Storeys": "geometry.storeys",
        "ConditionedFloorArea": "area.share",
        "WindowToWallRatio": "window.area_weighted",
    }
    return Derived(value, "geometry.storeys", _leaves(value, rules, "envelope.equivalent"))


# --- gains ---------------------------------------------------------------------------------------


def _gain(
    ledger: GroupLedger, kinds: Sequence[GainKind], calendar: RunPeriodCalendar
) -> tuple[float, npt.NDArray[np.float64]]:
    installed = 0.0
    hourly = np.zeros(calendar.hours)
    for kind in kinds:
        totals = ledger.gains.get(kind)
        if totals is not None:
            installed += totals.installed
            hourly = hourly + _profile(totals.hourly, calendar)
    return installed, hourly


def _gain_design(ledger: GroupLedger, kinds: Sequence[GainKind]) -> DesignValues | None:
    """The gains' design days divided by their installed level, or `None` when incomplete."""
    installed = 0.0
    days = DesignDays()
    for kind in kinds:
        totals = ledger.gains.get(kind)
        if totals is not None:
            installed += totals.installed
            days = days + totals.design_days
    return _design(days, installed)


def _gain_factor(installed: float, hourly: npt.NDArray[np.float64], design: DesignValues | None) -> float:
    """The factor of the installed level that keeps the gain's schedule a fraction: its peak, at least 1."""
    peaks = [float(_ratio(hourly, installed).max()) if hourly.size else 0.0]
    if design is not None:
        peaks.extend(float(day.max()) for day in design)
    return max(1.0, *peaks)


def _people_level(ledger: GroupLedger, calendar: RunPeriodCalendar) -> float:
    """The occupants `occupancy` writes: the installed people times `_gain_factor`."""
    if "people" not in ledger.gains:
        return 0.0
    installed, hourly = _gain(ledger, ("people",), calendar)
    return installed * _gain_factor(installed, hourly, _gain_design(ledger, ("people",)))


def _gain_schedule(
    ledger: GroupLedger,
    kinds: Sequence[GainKind],
    calendar: RunPeriodCalendar,
    *,
    name: str,
    label: str,
    category: YearScheduleCategory,
) -> tuple[float, YearComponent, list[NotRepresented]]:
    """The level of `kinds` and their normalised schedule, design days included.

    The level is the installed level, or the profile's peak when a schedule exceeds 1 (EnergyPlus
    accepts any multiplier): the schedule must stay a fraction, and level · schedule still
    reproduces the hourly gain.
    """
    installed, hourly = _gain(ledger, kinds, calendar)
    design = _gain_design(ledger, kinds)
    factor = _gain_factor(installed, hourly, design)
    level = installed * factor
    if design is not None and factor > 1.0:
        design = (design[0] / factor, design[1] / factor)
    schedule = _schedule(_ratio(hourly, level), calendar, name=f"{name} {label}", category=category, design=design)
    lost = [] if design is not None else [_design_lost(ledger, name, label)]
    return level, schedule, lost


def occupancy(ledger: GroupLedger, calendar: RunPeriodCalendar, *, name: str) -> Derived[OccupancyComponent]:
    """`OccupancyComponent`: people per m² (`gain.density`) and the normalised schedule.

    Args:
        ledger: The group's ledger.
        calendar: The run-period calendar.
        name: The group's name, prefixed to component names.

    Returns:
        The component.
    """
    installed, schedule, lost = _gain_schedule(
        ledger, ("people",), calendar, name=name, label="occupancy", category="Occupancy"
    )
    people = ledger.gains.get("people")
    occupant_seconds = float(np.sum(people.hourly)) * _SECONDS_PER_HOUR if people is not None else 0.0
    metabolic: dict[str, float] = {}
    if people is not None and people.activity > 0 and occupant_seconds > 0:
        # The occupant-hour mean activity level, W per person, as epinterface's met: it
        # multiplies MetabolicRate by its average weight and W per kg.
        metabolic["MetabolicRate"] = (people.activity / occupant_seconds) / _WATTS_PER_MET
    value = OccupancyComponent.model_validate({
        "Name": f"{name} occupancy",
        "PeopleDensity": installed / ledger.floor_area,
        "Schedule": schedule,
        "IsOn": installed > 0,
        **metabolic,
    })
    return Derived(
        value, "gain.density", _leaves(value, {"Schedule": "schedule.normalised"}, "gain.density"), tuple(lost)
    )


def lighting(ledger: GroupLedger, calendar: RunPeriodCalendar, *, name: str) -> Derived[LightingComponent]:
    """`LightingComponent`: W per m² (`gain.density`) and the normalised schedule.

    Args:
        ledger: The group's ledger.
        calendar: The run-period calendar.
        name: The group's name.

    Returns:
        The component.
    """
    installed, schedule, lost = _gain_schedule(
        ledger, ("lights",), calendar, name=name, label="lighting", category="Lighting"
    )
    value = LightingComponent(
        Name=f"{name} lighting",
        PowerDensity=installed / ledger.floor_area,
        DimmingType="Off",
        Schedule=schedule,
        IsOn=installed > 0,
    )
    return Derived(
        value, "gain.density", _leaves(value, {"Schedule": "schedule.normalised"}, "gain.density"), tuple(lost)
    )


def equipment(ledger: GroupLedger, calendar: RunPeriodCalendar, *, name: str) -> Derived[EquipmentComponent]:
    """`EquipmentComponent`: the sum of `EQUIPMENT_KINDS` per m² (`gain.density`) and their schedule.

    epinterface writes it as electric equipment, so the fuel of gas, steam and hot-water
    equipment is listed as not represented.

    Args:
        ledger: The group's ledger.
        calendar: The run-period calendar.
        name: The group's name.

    Returns:
        The component.
    """
    installed, schedule, lost = _gain_schedule(
        ledger, EQUIPMENT_KINDS, calendar, name=name, label="equipment", category="Equipment"
    )
    value = EquipmentComponent(
        Name=f"{name} equipment",
        PowerDensity=installed / ledger.floor_area,
        Schedule=schedule,
        IsOn=installed > 0,
    )
    _, fuelled = _gain(ledger, _NON_ELECTRIC_KINDS, calendar)
    energy = float(fuelled.sum()) * _SECONDS_PER_HOUR
    if energy > 0:
        lost.append(
            _entry(
                ledger,
                name,
                "Fuel of non-electric equipment",
                "Gas, steam and hot-water equipment are written as electric equipment.",
                magnitude=energy,
                unit="J",
                folded_into="Zone.Operations.SpaceUse.Equipment.PowerDensity",
            )
        )
    return Derived(
        value, "gain.density", _leaves(value, {"Schedule": "schedule.normalised"}, "gain.density"), tuple(lost)
    )


def _gain_parts_lost(ledger: GroupLedger, name: str) -> list[NotRepresented]:
    lost: list[NotRepresented] = []
    parts = sum(t.radiant + t.latent + t.lost for t in ledger.gains.values())
    if parts > 0:
        lost.append(
            _entry(
                ledger,
                name,
                "Radiant, latent and lost parts of internal gains",
                "SBEM uses fixed fractions; the annual energy of each part is in the report's ledger.",
                magnitude=parts,
                unit="J",
            )
        )
    baseboard = ledger.gains.get("baseboard")
    if baseboard is not None and baseboard.installed > 0:
        lost.append(
            _entry(
                ledger,
                name,
                "Baseboard heater gains",
                "Heat from baseboard heaters as an internal gain; SBEM has no such gain.",
                magnitude=baseboard.installed,
                unit="W",
            )
        )
    return lost


# --- thermostat ------------------------------------------------------------------------------------


def thermostat(ledger: GroupLedger, calendar: RunPeriodCalendar, *, name: str) -> Derived[ThermostatComponent]:
    """`ThermostatComponent`: the floor-area-weighted mean setpoints (rule `setpoint.area_mean`, FR-020).

    A group without heated (cooled) members keeps the mode off with a constant 5 °C (35 °C), the
    thermostats module's mode-off edge, design days included. A heating setpoint above the cooling
    setpoint (heat-only and cool-only members) is capped at it and listed as not represented. The
    scalar setpoints are the
    schedules' annual means. The design-day slots hold the area-weighted design-day setpoints;
    set, they take precedence over the constant extremes epinterface's builder would give its
    design days for sizing (`HeatingSchedule`'s highest and `CoolingSchedule`'s lowest value).

    Args:
        ledger: The group's ledger.
        calendar: The run-period calendar.
        name: The group's name.

    Returns:
        The component.
    """
    heating = ledger.heating_setpoint.value
    cooling = ledger.cooling_setpoint.value
    heat = np.full(calendar.hours, _HEATING_OFF) if heating is None else heating
    cool = np.full(calendar.hours, _COOLING_OFF) if cooling is None else cooling
    lost: list[NotRepresented] = []

    def design(setpoint: WeightedProfile, off: float, label: str) -> DesignValues | None:
        if setpoint.weight == 0:
            constant = np.full(_HOURS_PER_DAY, off)
            return constant, constant
        days = _design(setpoint.design_days, setpoint.weight)
        if days is None:
            lost.append(_design_lost(ledger, name, label))
        return days

    heat_design = design(ledger.heating_setpoint, _HEATING_OFF, "heating setpoint")
    cool_design = design(ledger.cooling_setpoint, _COOLING_OFF, "cooling setpoint")
    # The heating mean covers the heated members and the cooling mean the cooled ones, so a group
    # of heat-only and cool-only zones can heat above its cooling setpoint; EnergyPlus's dual
    # setpoint refuses that. The heating setpoint is capped at the cooling one.
    crossed = heat > cool
    if crossed.any():
        heat = np.minimum(heat, cool)
        lost.append(
            _entry(
                ledger,
                name,
                "Heating setpoint above cooling setpoint",
                "The group's heated members' mean heating setpoint exceeds its cooled members' mean cooling "
                "setpoint in these hours; the archetype heats to the cooling setpoint instead.",
                magnitude=float(crossed.sum()),
                unit="h",
            )
        )
    if heat_design is not None and cool_design is not None:
        heat_design = (np.minimum(heat_design[0], cool_design[0]), np.minimum(heat_design[1], cool_design[1]))
    value = ThermostatComponent(
        Name=f"{name} thermostat",
        IsOn=heating is not None or cooling is not None,
        HeatingSetpoint=float(np.mean(heat)),
        HeatingSchedule=_schedule(
            heat, calendar, name=f"{name} heating setpoint", category="Setpoint", design=heat_design
        ),
        CoolingSetpoint=float(np.mean(cool)),
        CoolingSchedule=_schedule(
            cool, calendar, name=f"{name} cooling setpoint", category="Setpoint", design=cool_design
        ),
    )
    return Derived(value, "setpoint.area_mean", _leaves(value, {}, "setpoint.area_mean"), tuple(lost))


# --- hot water -----------------------------------------------------------------------------------


def water_use(ledger: GroupLedger, calendar: RunPeriodCalendar, *, name: str) -> Derived[WaterUseComponent]:
    """`WaterUseComponent`: annual volume ÷ occupant-days (rule `dhw.volume_per_person`, FR-021).

    epinterface draws `FlowRatePerPerson · PeopleDensity · floor area` each day, so the
    occupant-days are the occupants `occupancy` writes (the installed people, times the people
    schedule's peak when it exceeds 1) times the days of the run period, and the daily volume is
    conserved: over a 365-day run period, the annual volume too. epinterface runs a 365-day year,
    so a run period of another length (a leap year) is listed as not represented. The schedule is
    the projected volume profile divided by its peak; the volume comes from run-period results, so
    its design-day slots repeat each month's Monday (`design_days_from_results`).

    Args:
        ledger: The group's ledger.
        calendar: The run-period calendar.
        name: The group's name.

    Returns:
        The component.
    """
    volume = _profile(ledger.hot_water.volume, calendar)
    total = float(volume.sum())
    people = _people_level(ledger, calendar)
    lost: list[NotRepresented] = []
    if total > 0 and people > 0:
        per_person = total / (people * calendar.days)
        if calendar.days != _ARCHETYPE_DAYS:
            lost.append(
                _entry(
                    ledger,
                    name,
                    "Hot-water volume outside a 365-day year",
                    f"The run period has {calendar.days} days and epinterface's year 365; the daily volume is kept, "
                    "so the archetype's annual volume differs by the difference in days.",
                    magnitude=total * (_ARCHETYPE_DAYS - calendar.days) / calendar.days,
                    unit="m3",
                    source="hotwater",
                )
            )
    else:
        per_person = 0.0
        if total > 0:
            lost.append(
                _entry(
                    ledger,
                    name,
                    "Hot water without occupants",
                    "SBEM's hot water is per person; the group has none.",
                    magnitude=total,
                    unit="m3",
                    source="hotwater",
                )
            )
    days = project(volume, calendar)
    peak = float(days.max()) if total > 0 else 0.0
    if peak > 0:
        days = days / peak
    # The volume comes from run-period results, which hold no design day: each month's Monday,
    # which the builder would use anyway, is set explicitly (`design_days_from_results`).
    mondays = days[:, 0, :]
    schedule = to_year_component(
        days,
        name=f"{name} water use",
        category="WaterUse",
        summer_design_day=mondays,
        winter_design_day=mondays,
    )
    if total > 0:
        lost.append(design_days_from_results(ledger, name, "hot water", "Zone.Operations.SpaceUse.WaterUse"))
    value = WaterUseComponent(Name=f"{name} water use", FlowRatePerPerson=per_person, Schedule=schedule)
    rules = {"Schedule": "schedule.normalised"}
    return Derived(value, "dhw.volume_per_person", _leaves(value, rules, "dhw.volume_per_person"), tuple(lost))


def _efficiency(
    ledger: GroupLedger, building: GroupLedger, mode: Mode, name: str, path: str, fuel_field: str = "Fuel"
) -> tuple[float, float, str, str, list[NotRepresented]] | None:
    """(SystemCOP, DistributionCOP, SBEM fuel, rule, lost) of a mode, or `None` when unserved."""
    totals = ledger.energy.get(mode)
    lost: list[NotRepresented] = []
    if totals is None:
        return None
    primary = sum(totals.consumed_by_fuel.values())
    distribution = sum(totals.distribution_by_fuel.values())
    fuel = _dominant(totals.consumed_by_fuel) or _dominant(totals.distribution_by_fuel)
    if totals.delivered > 0 and primary + distribution > 0:
        if primary > 0:
            system, dist = totals.delivered / primary, primary / (primary + distribution)
        else:
            system, dist = totals.delivered / distribution, 1.0
        rule = "efficiency.delivered_over_consumed"
        consumed = {**totals.consumed_by_fuel} if primary > 0 else {**totals.distribution_by_fuel}
        secondary = sum(v for k, v in consumed.items() if k != fuel)
        if secondary > 0:
            lost.append(
                _entry(
                    ledger,
                    name,
                    f"Secondary fuels of {mode.replace('_', ' ')}",
                    f"Consumption of fuels other than {fuel} is counted as {fuel} in the system COP.",
                    magnitude=secondary,
                    unit="J",
                    folded_into=f"{path}.SystemCOP",
                    source="efficiency",
                )
            )
        foreign = sum(v for k, v in totals.distribution_by_fuel.items() if k != fuel) if primary > 0 else 0.0
        if foreign > 0:
            lost.append(
                _entry(
                    ledger,
                    name,
                    f"Distribution fuels of {mode.replace('_', ' ')}",
                    f"Pump and heat-rejection consumption of fuels other than {fuel} is counted as {fuel} "
                    "in the distribution COP.",
                    magnitude=foreign,
                    unit="J",
                    folded_into=f"{path}.DistributionCOP",
                    source="efficiency",
                )
            )
    elif totals.rated_efficiency is not None:
        system, dist, rule = totals.rated_efficiency, 1.0, "efficiency.rated"
        fallback = building.energy.get(mode)
        fuel = fuel or (None if fallback is None else _dominant(fallback.consumed_by_fuel))
    else:
        return None
    fuel = fuel or "Electricity"
    sbem = _sbem_fuel(fuel)
    if _FUELS.get(fuel.casefold().replace(" ", "")) != sbem:
        lost.append(
            _entry(
                ledger,
                name,
                f"Fuel {fuel} of {mode.replace('_', ' ')}",
                f"SBEM has no fuel {fuel}; it is written as {sbem}.",
                folded_into=f"{path}.{fuel_field}",
                source="efficiency",
            )
        )
    return system, dist, sbem, rule, lost


def dhw(
    ledger: GroupLedger, building: GroupLedger, mains_temperature: float | None, *, name: str
) -> Derived[DHWComponent]:
    """`DHWComponent`: mains plus the volume-weighted rise (`dhw.mains_plus_rise`) and its efficiency.

    The inlet temperature is the annual-mean mains temperature and the supply temperature that
    plus `heat / volume`, so volume · (supply - inlet) reproduces the heat (FR-021). The COPs
    follow R12 on the hot-water mode; epinterface's effective COP is SystemCOP · DistributionCOP,
    so the distribution COP carries the service hot-water pumps. A group whose hot water is
    never heated (a mean rise of 0 or less) has its hot water off, listed as not represented.

    Args:
        ledger: The group's ledger.
        building: The sum of every group's ledger (fuel of a rated system).
        mains_temperature: The annual-mean mains temperature, °C, or `None`.
        name: The group's name.

    Returns:
        The component.
    """
    rise = ledger.hot_water.mean_rise
    inlet = 10.0 if mains_temperature is None else mains_temperature
    unheated: list[NotRepresented] = []
    if rise is not None and rise <= 0:
        unheated.append(
            _entry(
                ledger,
                name,
                "Unheated hot water",
                f"The hot water is drawn at a mean rise of {rise:.3g} K over the cold water, so it is not heated; "
                "SBEM's hot water is off.",
                magnitude=float(np.sum(ledger.hot_water.volume)),
                unit="m3",
                source="hotwater",
            )
        )
    on = rise is not None and rise > 0
    # 45 K is only a placeholder for a component that is off.
    supply = inlet + (rise if rise is not None and rise > 0 else 45.0)
    efficiency = _efficiency(ledger, building, "hot_water", name, "Zone.Operations.DHW", "FuelType") if on else None
    if efficiency is None:
        system, distribution, fuel, rule, lost = 1.0, 1.0, "Electricity", "efficiency.rated", []
    else:
        system, distribution, fuel, rule, lost = efficiency
    lost.extend(unheated)
    if fuel not in _DHW_FUELS:
        # One entry for the fuel written, replacing `_efficiency`'s, which names CustomFuel.
        lost = [e for e in lost if e.folded_into != "Zone.Operations.DHW.FuelType"]
        totals = ledger.energy.get("hot_water")
        source_fuel = (_dominant(totals.consumed_by_fuel) if totals is not None else None) or fuel
        lost.append(
            _entry(
                ledger,
                name,
                f"Hot-water fuel {source_fuel}",
                f"SBEM's hot water cannot use {source_fuel}; it is written as NaturalGas.",
                folded_into="Zone.Operations.DHW.FuelType",
                source="hotwater",
            )
        )
        fuel = "NaturalGas"
    value = DHWComponent(
        Name=f"{name} hot water",
        SystemCOP=system,
        WaterTemperatureInlet=inlet,
        DistributionCOP=distribution,
        WaterSupplyTemperature=supply,
        IsOn=on,
        FuelType=cast("Any", fuel),
    )
    rules = {"SystemCOP": rule, "DistributionCOP": rule, "FuelType": rule}
    return Derived(value, "dhw.mains_plus_rise", _leaves(value, rules, "dhw.mains_plus_rise"), tuple(lost))


# --- envelope ------------------------------------------------------------------------------------


def _class_source(slot: str, ledger: GroupLedger, building: GroupLedger) -> tuple[EnvelopeClass, EnvelopeTotals] | None:
    for klass in SLOT_CLASSES[slot]:
        for source in (ledger, building):
            totals = source.envelope.get(klass)
            if totals is not None and totals.area > 0 and totals.ua > 0:
                return klass, totals
    return None


def assemblies(ledger: GroupLedger, building: GroupLedger, *, name: str) -> Derived[EnvelopeAssemblyComponent]:
    """`EnvelopeAssemblyComponent`: equivalent assemblies (`envelope.equivalent`), internal mass (`mass.internal`).

    Args:
        ledger: The group's ledger.
        building: The sum of every group's ledger, for slots the group has no surface for.
        name: The group's name.

    Returns:
        The component.

    Raises:
        ValueError: If neither the group nor the building has a surface for a slot, or a U
            cannot be reproduced.
    """
    slots: dict[str, ConstructionAssemblyComponent] = {}
    for slot, sbem_type in _SLOT_TYPES.items():
        found = _class_source(slot, ledger, building)
        if found is None:
            msg = f"no surface of the building can give the {slot} of group {name!r}"
            raise ValueError(msg)
        klass, totals = found
        assembly = equivalent_construction(totals, klass, name=f"{name} {sbem_type}")
        slots[slot] = assembly.model_copy(update={"Type": sbem_type})
    mass = internal_mass_construction(
        ledger.internal_mass_capacity, ledger.internal_mass_area, name=f"{name} InternalMass"
    )
    extra: dict[str, object] = {}
    if mass is not None:
        extra = {
            "InternalMassAssembly": mass,
            "InternalMassExposedAreaPerArea": ledger.internal_mass_area / ledger.floor_area,
        }
    value = EnvelopeAssemblyComponent.model_validate({"Name": f"{name} assemblies", **slots, **extra})
    rules = {"InternalMassAssembly": "mass.internal", "InternalMassExposedAreaPerArea": "mass.internal"}
    return Derived(value, "envelope.equivalent", _leaves(value, rules, "envelope.equivalent"))


def window(ledger: GroupLedger, *, name: str) -> Derived[GlazingConstructionSimpleComponent | None]:
    """The simple glazing with area-weighted U, SHGC and VT (rule `window.area_weighted`), or `None`.

    The glazing is the facade windows'. SBEM's window is a share of the facade, so it cannot hold
    skylights, roof or floor windows (`ledger.skylights`): their area is listed as not represented,
    and their UA, A·SHGC and A·VT, which the ledger conserves, are not written.

    Args:
        ledger: The group's ledger.
        name: The group's name.

    Returns:
        The glazing, or `None` without facade windows.
    """
    value = window_construction(ledger.window_by_orientation, name=f"{name} window")
    leaves = () if value is None else _leaves(value, {}, "window.area_weighted")
    lost: list[NotRepresented] = []
    skylights = ledger.skylights
    if skylights.area > 0:
        lost.append(
            _entry(
                ledger,
                name,
                "Skylights, roof and floor windows",
                f"SBEM's window is a share of the facade; these windows (UA {skylights.ua:.6g} W/K, "
                f"A·SHGC {skylights.a_shgc:.6g} m², A·VT {skylights.a_vt:.6g} m²) are not written.",
                magnitude=skylights.area,
                unit="m2",
                source="envelope",
            )
        )
    return Derived(value, "window.area_weighted", leaves, tuple(lost))


def _exterior_area(ledger: GroupLedger) -> float:
    opaque = sum(ledger.envelope.get(c, EnvelopeTotals()).area for c in ("exterior_wall", "roof", "exposed_floor"))
    return opaque + sum(w.area for w in ledger.window_by_orientation.values()) + ledger.skylights.area


def _off_infiltration(name: str) -> InfiltrationComponent:
    return InfiltrationComponent(
        Name=name,
        IsOn=False,
        ConstantCoefficient=1.0,
        TemperatureCoefficient=0.0,
        WindVelocityCoefficient=0.0,
        WindVelocitySquaredCoefficient=0.0,
        AFNAirMassFlowCoefficientCrack=0.0,
        AirChangesPerHour=0.0,
        FlowPerExteriorSurfaceArea=0.0,
        CalculationMethod="Flow/ExteriorArea",
    )


def infiltration(ledger: GroupLedger, calendar: RunPeriodCalendar, *, name: str) -> Derived[InfiltrationComponent]:
    """`InfiltrationComponent`: annual-mean flow ÷ exterior area (rule `airflow.mean_per_exterior_area`, FR-018).

    The flow-weighted mean coefficients are written; UP-2's schedule is `project(hourly / mean)`
    (`AnyNumber`), so mean · schedule reproduces the hourly design-flow profile, and its
    design-day slots are the design days divided by the same mean. epinterface's
    builder applies the coefficients 1/0/0/0, so the weather response is dropped and listed as
    not represented: the results hold no infiltration flow, zone temperature or wind speed to
    fold it in. A group with infiltration but no exterior area cannot hold it.

    Args:
        ledger: The group's ledger.
        calendar: The run-period calendar.
        name: The group's name.

    Returns:
        The component.
    """
    totals = ledger.infiltration
    hourly = _profile(totals.hourly, calendar)
    mean = float(hourly.mean())
    area = _exterior_area(ledger)
    lost: list[NotRepresented] = []
    if mean <= 0 or totals.design_flow <= 0:
        value = _off_infiltration(f"{name} infiltration")
        return Derived(value, "airflow.mean_per_exterior_area", _leaves(value, {}, "airflow.mean_per_exterior_area"))
    if area <= 0:
        value = _off_infiltration(f"{name} infiltration")
        lost.append(
            _entry(
                ledger,
                name,
                "Infiltration of zones without exterior surfaces",
                "SBEM's infiltration is per exterior area; the group has none.",
                magnitude=totals.design_flow,
                unit="m3/s",
                source="airflow",
            )
        )
        return Derived(
            value, "airflow.mean_per_exterior_area", _leaves(value, {}, "airflow.mean_per_exterior_area"), tuple(lost)
        )
    flow = totals.design_flow
    design = _design(totals.design_days, flow, mean)
    value = InfiltrationComponent(
        Name=f"{name} infiltration",
        IsOn=True,
        ConstantCoefficient=totals.constant_weighted / flow,
        TemperatureCoefficient=totals.temperature_weighted / flow,
        WindVelocityCoefficient=totals.velocity_weighted / flow,
        WindVelocitySquaredCoefficient=totals.velocity_squared_weighted / flow,
        AFNAirMassFlowCoefficientCrack=0.0,
        AirChangesPerHour=0.0,
        FlowPerExteriorSurfaceArea=mean / area,
        CalculationMethod="Flow/ExteriorArea",
        Schedule=_schedule(
            hourly / mean,
            calendar,
            name=f"{name} infiltration",
            category="Infiltration",
            limits="AnyNumber",
            design=design,
        ),
    )
    if design is None:
        lost.append(_design_lost(ledger, name, "infiltration"))
    lost.append(
        _entry(
            ledger,
            name,
            "Infiltration response to weather",
            "EnergyPlus multiplies the design flow by A + B·|ΔT| + C·v + D·v² (flow-weighted means "
            f"{totals.constant_weighted / flow:.4g}, {totals.temperature_weighted / flow:.4g}, "
            f"{totals.velocity_weighted / flow:.4g}, {totals.velocity_squared_weighted / flow:.4g}); the archetype's "
            "flow is the design flow (epinterface writes 1, 0, 0, 0), so the weather response is dropped, not "
            "folded: the annual infiltration differs whenever the coefficients are not 1, 0, 0, 0.",
            source="airflow",
        )
    )
    rules = {"Schedule": "schedule.normalised"}
    return Derived(
        value, "airflow.mean_per_exterior_area", _leaves(value, rules, "airflow.mean_per_exterior_area"), tuple(lost)
    )


# --- ventilation -----------------------------------------------------------------------------------


def ventilation(ledger: GroupLedger, calendar: RunPeriodCalendar, *, name: str) -> Derived[VentilationComponent]:
    """`VentilationComponent`: peak flow per area and `project(hourly / peak)` (`airflow.peak_per_area`, FR-019).

    The projected fraction is the mechanical outdoor air's schedule (UP-9's `MechVentSchedule`),
    so peak · schedule reproduces the hourly profile; it is also the `Schedule` of natural
    ventilation, which the provider `Mechanical` leaves unused. The profile comes from
    run-period results, so the design-day slots repeat each month's Monday
    (`design_days_from_results`).

    EnergyPlus's mechanical-ventilation output holds every outdoor air a zone receives, the
    economiser's included; with an economiser the profile is held at the design minimum outdoor
    air, and the volume above it is left to the archetype's economiser (listed).

    HRV and economiser take the category serving the most outdoor-air volume, and the sensible
    effectiveness its volume-weighted mean over the volume with heat recovery (UP-2's numeric
    field; rule `airflow.dominant_category`). DCV is `NoDCV`: the hourly profile already holds
    what demand control did.

    Args:
        ledger: The group's ledger.
        calendar: The run-period calendar.
        name: The group's name.

    Returns:
        The component.
    """
    oa = ledger.outdoor_air
    hourly = _profile(oa.hourly, calendar)
    lost: list[NotRepresented] = []
    economiser = _dominant(oa.economiser_weighted) or "NoEconomizer"
    if economiser != "NoEconomizer" and oa.design_flow > 0 and float(hourly.max()) > oa.design_flow:
        # EnergyPlus reports all the outdoor air a zone receives, the economiser's included.
        # The minimum outdoor air is held at the design flow; the economiser category lets the
        # ideal loads draw the free-cooling air above it, as the detailed model's did.
        excess = float(np.maximum(hourly - oa.design_flow, 0.0).sum()) * _SECONDS_PER_HOUR
        hourly = np.minimum(hourly, oa.design_flow)
        lost.append(
            _entry(
                ledger,
                name,
                "Economiser outdoor air",
                "The outdoor air above the design minimum, which the detailed model's economiser drew, is left to "
                "the archetype's economiser instead of being forced as a minimum.",
                magnitude=excess,
                unit="m3",
                folded_into="Zone.Operations.HVAC.Ventilation.Economizer",
                source="airflow",
            )
        )
    peak = float(hourly.max()) if hourly.size else 0.0
    schedule = _schedule(_ratio(hourly, peak), calendar, name=f"{name} ventilation", category="Window", design="monday")
    if peak <= 0:
        value = VentilationComponent(
            Name=f"{name} ventilation",
            FreshAirPerFloorArea=0.0,
            FreshAirPerPerson=0.0,
            Schedule=schedule,
            Provider="None",
            HRV="NoHRV",
            Economizer="NoEconomizer",
            DCV="NoDCV",
        )
        rules = {"Schedule": "schedule.normalised"}
        return Derived(value, "airflow.peak_per_area", _leaves(value, rules, "airflow.peak_per_area"))
    hrv = _dominant(oa.hrv_weighted) or "NoHRV"
    recovered = sum(v for k, v in oa.hrv_weighted.items() if k != "NoHRV")
    extra: dict[str, object] = {}
    if hrv != "NoHRV" and recovered > 0:
        extra["SensibleHeatRecoveryEffectiveness"] = min(max(oa.effectiveness_weighted / recovered, 0.0), 1.0)
    mechanical = _schedule(
        _ratio(hourly, peak),
        calendar,
        name=f"{name} mechanical ventilation",
        category="Window",
        limits="Fraction",
        design="monday",
    )
    lost.append(design_days_from_results(ledger, name, "outdoor air", "Zone.Operations.HVAC.Ventilation"))
    value = VentilationComponent.model_validate({
        "Name": f"{name} ventilation",
        "FreshAirPerFloorArea": peak / ledger.floor_area,
        "FreshAirPerPerson": 0.0,
        "Schedule": schedule,
        "MechVentSchedule": mechanical,
        "Provider": "Mechanical",
        "HRV": hrv,
        "Economizer": economiser,
        "DCV": "NoDCV",
        **extra,
    })
    path = "Zone.Operations.HVAC.Ventilation"
    for feature, weighted, chosen, slot in (
        ("Heat recovery", oa.hrv_weighted, hrv, "HRV"),
        ("Economiser", oa.economiser_weighted, economiser, "Economizer"),
    ):
        other = sum(v for k, v in weighted.items() if k != chosen)
        if other > 0:
            lost.append(
                _entry(
                    ledger,
                    name,
                    f"{feature} categories other than {chosen}",
                    f"Outdoor air served by other {feature.lower()} categories takes {chosen}.",
                    magnitude=other,
                    unit="m3",
                    folded_into=f"{path}.{slot}",
                    source="airflow",
                )
            )
    if hrv == "Enthalpy":
        lost.append(
            _entry(
                ledger,
                name,
                "Latent heat-recovery effectiveness",
                "The ledger holds the sensible effectiveness only; epinterface assumes 0.65 latent.",
                folded_into=f"{path}.LatentHeatRecoveryEffectiveness",
                source="airflow",
            )
        )
    rules = {
        "Schedule": "schedule.normalised",
        "MechVentSchedule": "schedule.normalised",
        "HRV": "airflow.dominant_category",
        "Economizer": "airflow.dominant_category",
        "SensibleHeatRecoveryEffectiveness": "airflow.dominant_category",
    }
    return Derived(value, "airflow.peak_per_area", _leaves(value, rules, "airflow.peak_per_area"), tuple(lost))


# --- conditioning ------------------------------------------------------------------------------------


def thermal_system(
    ledger: GroupLedger, building: GroupLedger, mode: Literal["heating", "cooling"], *, name: str
) -> Derived[ThermalSystemComponent | None]:
    """`ThermalSystemComponent` of a mode (R12, FR-022), or `None` when nothing serves it.

    `SystemCOP = delivered / primary consumed` and `DistributionCOP = primary / (primary +
    pumps and heat rejection)` (`efficiency.delivered_over_consumed`); fans are not folded
    (UP-8, R19). Without delivery, the rated efficiency (`efficiency.rated`). The slope of the
    energy input ratio with outdoor temperature and its reference come from `fit_eir`
    (`efficiency.eir_linear`); with that reference the annual consumption stays exact.

    Args:
        ledger: The group's ledger.
        building: The sum of every group's ledger.
        mode: `heating` or `cooling`.
        name: The group's name.

    Returns:
        The system, or `None`.
    """
    label = "Heating" if mode == "heating" else "Cooling"
    found = _efficiency(ledger, building, mode, name, f"Zone.Operations.HVAC.ConditioningSystems.{label}")
    if found is None:
        return Derived(None, "efficiency.delivered_over_consumed")
    system, dist, fuel, rule, lost = found
    extra: dict[str, float] = {}
    totals = ledger.energy[mode]
    if rule == "efficiency.delivered_over_consumed" and totals.eir_sums.d > 0:
        _, slope, reference = fit_eir(totals.eir_sums)
        if slope != 0.0:
            extra = {"EIRTemperatureSlope": slope, "EIRReferenceTemperature": reference}
    value = ThermalSystemComponent.model_validate({
        "Name": f"{name} {mode}",
        "ConditioningType": label,
        "Fuel": fuel,
        "SystemCOP": system,
        "DistributionCOP": dist,
        **extra,
    })
    rules = {"EIRTemperatureSlope": "efficiency.eir_linear", "EIRReferenceTemperature": "efficiency.eir_linear"}
    return Derived(value, rule, _leaves(value, rules, rule), tuple(lost))


IDEAL_LOADS_LIMITS: dict[str, str] = {"HeatingLimitType": "NoLimit", "CoolingLimitType": "LimitFlowRate"}
"""The ideal loads' limits whenever the supply-air limits come from the effective temperature differences (R19).

The supply-air limits are set so the ideal loads move the detailed model's annual air volume;
they are not design temperatures, so the flow and capacity epinterface autosizes from them on its
own design days describe no equipment of the detailed model. With them, the autosized capacity
clipped `three_zone`'s morning recovery after the night setback (stand-in diagnosis). Heating
therefore follows the load (its air volume is then load / (rho·c_p·delta), the volume R19
reproduces), and cooling keeps only its autosized air flow, which bounds the outdoor air the
ideal loads' economiser draws. Neither capacity is limited: the detailed equipment's capacity is
not held by the archetype.
"""


def _extreme(hourly: npt.NDArray[np.float64], setpoint: WeightedProfile, pick: Callable[..., float]) -> float:
    """The highest (`max`) or lowest (`min`) setpoint the schedule takes, its design days included.

    The ideal loads refuse a heating supply limit below the setpoint (and a cooling one above),
    including on the design days the archetype sizes with.
    """
    values = [float(pick(hourly))]
    days = _design(setpoint.design_days, setpoint.weight)
    if days is not None:
        values.extend(float(pick(day)) for day in days)
    return float(pick(values))


def _supply_limits(ledger: GroupLedger, air_density: float, name: str) -> tuple[dict[str, float], list[NotRepresented]]:
    fans = ledger.fans
    limits: dict[str, float] = {}
    lost: list[NotRepresented] = []
    heating, cooling = ledger.heating_setpoint.value, ledger.cooling_setpoint.value
    delta_h = effective_supply_delta(fans, "heating", air_density=air_density)
    delta_c = effective_supply_delta(fans, "cooling", air_density=air_density)
    candidates: dict[str, tuple[float, float]] = {}  # field -> (value, delivered)

    def out_of_range(field: str, value: float, bounds: tuple[float, float]) -> NotRepresented:
        return _entry(
            ledger,
            name,
            f"Effective supply temperature difference ({field})",
            f"The detailed model's supply temperature limit, {value:.4g} °C, lies outside epinterface's range "
            f"({bounds[0]:g} to {bounds[1]:g} °C); it keeps epinterface's default, so the archetype's air volume "
            "(and fan energy) differs in that mode.",
            folded_into=f"Zone.Operations.HVAC.ConditioningSystems.{field}",
            source="fans",
        )

    if heating is not None and delta_h is not None:
        value = _extreme(heating, ledger.heating_setpoint, max) + delta_h
        if _SUPPLY_HEATING_RANGE[0] < value < _SUPPLY_HEATING_RANGE[1]:
            candidates["MaximumHeatingSupplyAirTemperature"] = (value, fans.delivered_in_mode.get("heating", 0.0))
        else:
            lost.append(out_of_range("MaximumHeatingSupplyAirTemperature", value, _SUPPLY_HEATING_RANGE))
    if cooling is not None and delta_c is not None:
        value = _extreme(cooling, ledger.cooling_setpoint, min) - delta_c
        if _SUPPLY_COOLING_RANGE[0] < value < _SUPPLY_COOLING_RANGE[1]:
            candidates["MinimumCoolingSupplyAirTemperature"] = (value, fans.delivered_in_mode.get("cooling", 0.0))
        else:
            lost.append(out_of_range("MinimumCoolingSupplyAirTemperature", value, _SUPPLY_COOLING_RANGE))
    defaults = {"MaximumHeatingSupplyAirTemperature": 30.0, "MinimumCoolingSupplyAirTemperature": 13.0}
    chosen = {k: v for k, (v, _) in candidates.items()}
    merged = {**defaults, **chosen}
    if merged["MaximumHeatingSupplyAirTemperature"] <= merged["MinimumCoolingSupplyAirTemperature"]:
        keep = max(sorted(candidates), key=lambda k: candidates[k][1])
        dropped = [k for k in candidates if k != keep] or [keep]
        chosen = {keep: candidates[keep][0]} if dropped != [keep] else {}
        merged = {**defaults, **chosen}
        if merged["MaximumHeatingSupplyAirTemperature"] <= merged["MinimumCoolingSupplyAirTemperature"]:
            chosen, dropped = {}, sorted(candidates)
        lost.extend(
            _entry(
                ledger,
                name,
                f"Effective supply temperature difference ({k})",
                "The detailed model's supply temperature limits would cross; this one keeps "
                "epinterface's default, so the archetype's air volume (and fan energy) differs in that mode.",
                folded_into=f"Zone.Operations.HVAC.ConditioningSystems.{k}",
                source="fans",
            )
            for k in dropped
        )
    limits.update(chosen)
    return limits, lost


def conditioning_systems(
    ledger: GroupLedger, building: GroupLedger, *, name: str, air_density: float
) -> Derived[ConditioningSystemsComponent]:
    """`ConditioningSystemsComponent`: the two thermal systems and UP-8's fan quantities (R19, FR-022a).

    `SpecificFanPower = fan energy / air volume` (`fans.energy_per_volume`); the ideal loads'
    supply-air limits are the setpoint ± the detailed model's effective supply temperature
    difference in that mode (`fans.effective_supply_delta`), and, when at least one is set, their
    limit types are `IDEAL_LOADS_LIMITS` (same rule).

    Args:
        ledger: The group's ledger.
        building: The sum of every group's ledger.
        name: The group's name.
        air_density: The standard air density of the fan volumes, kg/m³.

    Returns:
        The component.
    """
    heating = thermal_system(ledger, building, "heating", name=name)
    cooling = thermal_system(ledger, building, "cooling", name=name)
    extra: dict[str, float | str] = {}
    lost: list[NotRepresented] = [*heating.not_represented, *cooling.not_represented]
    sfp = specific_fan_power(ledger.fans)
    if sfp is not None:
        extra["SpecificFanPower"] = sfp
        limits, limit_lost = _supply_limits(ledger, air_density, name)
        if limits:  # epinterface's default limits stay with its default supply temperatures
            extra.update(limits)
            extra.update(IDEAL_LOADS_LIMITS)
        lost.extend(limit_lost)
        if ledger.fans.volume_without_demand > 0:
            lost.append(
                _entry(
                    ledger,
                    name,
                    "Fan air volume without load or outdoor-air demand",
                    "Air a fan moves with neither a load nor outdoor-air demand has no counterpart in ideal loads.",
                    magnitude=ledger.fans.volume_without_demand,
                    unit="m3",
                    source="fans",
                )
            )
    value = ConditioningSystemsComponent.model_validate({
        "Name": f"{name} conditioning",
        "Heating": heating.value,
        "Cooling": cooling.value,
        **extra,
    })
    leaves = [*_nested("Heating", heating), *_nested("Cooling", cooling)]
    if value.Heating is None:
        leaves.append(LeafRule("Heating", None, heating.rule))
    if value.Cooling is None:
        leaves.append(LeafRule("Cooling", None, cooling.rule))
    for key, setting in extra.items():
        rule = "fans.energy_per_volume" if key == "SpecificFanPower" else "fans.effective_supply_delta"
        leaves.append(LeafRule(key, setting, rule))
    return Derived(value, "efficiency.delivered_over_consumed", tuple(leaves), tuple(lost))


# --- attic, basement ---------------------------------------------------------------------------------


def attic() -> Derived[AtticAssumptions]:
    """`Archetype.Attic`: unused and unconditioned (rule `zone.attic`, R8).

    An attic is an unconditioned zone; its envelope is carried by the conditioned zones below
    it (FR-013), so the archetype adds no attic of its own.
    """
    value = AtticAssumptions(UseFraction=None, Conditioned=False)
    return Derived(value, "zone.attic", _leaves(value, {}, "zone.attic"))


def basement() -> Derived[BasementAssumptions]:
    """`Archetype.Basement`: unused and unconditioned (rule `zone.basement`, R8)."""
    value = BasementAssumptions(UseFraction=None, Conditioned=False)
    return Derived(value, "zone.basement", _leaves(value, {}, "zone.basement"))


# --- a group ---------------------------------------------------------------------------------------


def zone_group(
    name: str,
    ledger: GroupLedger,
    building: GroupLedger,
    facts: BuildingFacts,
    *,
    exposure: Literal["core", "perimeter"] | None,
) -> Derived[ZoneGroup]:
    """One `ZoneGroup`: every component of the group, and its floor-area share.

    Args:
        name: The group's name (`report.group_name(key)`).
        ledger: The group's ledger.
        building: The sum of every group's ledger.
        facts: Building facts.
        exposure: The group's exposure when the layout keeps it.

    Returns:
        The group; leaf paths are relative to the `ZoneGroup`.
    """
    cal = facts.calendar
    parts: dict[str, Derived[Any]] = {
        "Zone.Operations.SpaceUse.Occupancy": occupancy(ledger, cal, name=name),
        "Zone.Operations.SpaceUse.Lighting": lighting(ledger, cal, name=name),
        "Zone.Operations.SpaceUse.Equipment": equipment(ledger, cal, name=name),
        "Zone.Operations.SpaceUse.Thermostat": thermostat(ledger, cal, name=name),
        "Zone.Operations.SpaceUse.WaterUse": water_use(ledger, cal, name=name),
        "Zone.Operations.HVAC.ConditioningSystems": conditioning_systems(
            ledger, building, name=name, air_density=facts.air_density
        ),
        "Zone.Operations.HVAC.Ventilation": ventilation(ledger, cal, name=name),
        "Zone.Operations.DHW": dhw(ledger, building, facts.mains_temperature, name=name),
        "Zone.Envelope.Assemblies": assemblies(ledger, building, name=name),
        "Zone.Envelope.Infiltration": infiltration(ledger, cal, name=name),
        "Zone.Envelope.Window": window(ledger, name=name),
    }
    v = {path.rsplit(".", 1)[-1]: part.value for path, part in parts.items()}
    attic_inf = _off_infiltration(f"{name} attic infiltration")
    basement_inf = _off_infiltration(f"{name} basement infiltration")
    zone = ZoneComponent(
        Name=name,
        Operations=ZoneOperationsComponent(
            Name=f"{name} operations",
            SpaceUse=ZoneSpaceUseComponent(
                Name=f"{name} space use",
                Occupancy=v["Occupancy"],
                Lighting=v["Lighting"],
                Equipment=v["Equipment"],
                Thermostat=v["Thermostat"],
                WaterUse=v["WaterUse"],
            ),
            HVAC=ZoneHVACComponent(
                Name=f"{name} HVAC", ConditioningSystems=v["ConditioningSystems"], Ventilation=v["Ventilation"]
            ),
            DHW=v["DHW"],
        ),
        Envelope=ZoneEnvelopeComponent(
            Name=f"{name} envelope",
            Assemblies=v["Assemblies"],
            Infiltration=v["Infiltration"],
            AtticInfiltration=attic_inf,
            BasementInfiltration=basement_inf,
            Window=v["Window"],
        ),
    )
    share = floor_area_share(ledger, building.floor_area)
    value = ZoneGroup(Name=name, Zone=zone, FloorAreaShare=share.value, Exposure=exposure)
    leaves: list[LeafRule] = list(share.leaves)
    for path, part in parts.items():
        leaves.extend(_nested(path, part))
        if part.value is None:
            leaves.append(LeafRule(path, None, part.rule))
    leaves.extend(
        _nested(
            "Zone.Envelope.AtticInfiltration", Derived(attic_inf, "zone.attic", _leaves(attic_inf, {}, "zone.attic"))
        )
    )
    leaves.extend(
        _nested(
            "Zone.Envelope.BasementInfiltration",
            Derived(basement_inf, "zone.basement", _leaves(basement_inf, {}, "zone.basement")),
        )
    )
    lost = [entry for part in parts.values() for entry in part.not_represented]
    lost.extend(_gain_parts_lost(ledger, name))
    if cal.holidays:
        lost.append(_holidays_lost(ledger, name, len(cal.holidays)))
    return Derived(value, "area.share", tuple(leaves), tuple(lost))


def _holidays_lost(ledger: GroupLedger, name: str, count: int) -> NotRepresented:
    return _entry(
        ledger,
        name,
        "Holiday profiles",
        f"The detailed model has {count} holidays; epinterface's builder declares none, so each holiday is "
        "averaged into its weekday's day of the month, which conserves each month's energy but not the holiday "
        "profile itself.",
        magnitude=float(count),
        unit="days",
        source="schedules",
    )


# --- the archetype -----------------------------------------------------------------------------------


def _exposure(key: tuple[str, ...], layout: Layout) -> Literal["core", "perimeter"] | None:
    distinctions = layout.distinctions
    if "exposure" not in distinctions:
        return None
    value = key[distinctions.index("exposure")]
    return cast("Literal['core', 'perimeter']", value)


def to_archetype(groups: Sequence[Group], layout: Layout, facts: BuildingFacts, *, name: str) -> Conversion:
    """Convert the groups' ledgers to the fork's multi-group `Archetype` (FR-003, FR-025).

    Args:
        groups: The groups after the threshold (`Grouping.groups`), in key order.
        layout: Their layout, which tells whether keys carry the exposure.
        facts: Building facts.
        name: The archetype's name.

    Returns:
        The archetype, its parameters and what it cannot hold.

    Raises:
        ReductionError: When a group has no floor area, or, with epinterface's message, when a
            component or the archetype does not validate, or a rule cannot produce a component.
            Either of the latter is a bug, never silenced.
    """
    if not groups:
        raise ReductionError(name, "no group to convert")
    for group in groups:
        if not group.ledger.floor_area > 0:  # every intensity is per floor area
            members = ", ".join(group.ledger.members)
            msg = f"group {group_name(group.key)!r} ({members}) has no floor area; its intensities are undefined"
            raise ReductionError(name, msg)
    building = sum((g.ledger for g in groups), GroupLedger())
    parameters: list[Parameter] = []
    lost: list[NotRepresented] = []
    try:
        zone_groups: list[ZoneGroup] = []
        for group in groups:
            group_label = group_name(group.key)
            derived = zone_group(group_label, group.ledger, building, facts, exposure=_exposure(group.key, layout))
            zone_groups.append(derived.value)
            parameters.extend(
                Parameter(group=group_label, path=leaf.path, value=leaf.value, rule=leaf.rule)
                for leaf in derived.leaves
            )
            lost.extend(derived.not_represented)
        geo = geometry(building, facts.storey_ratio)
        attic_value, basement_value = attic(), basement()
        archetype = Archetype(
            Name=name,
            Groups=zone_groups,
            Geometry=geo.value,
            Attic=attic_value.value,
            Basement=basement_value.value,
        )
    except (ValidationError, ValueError) as exc:
        raise ReductionError(name, f"the archetype does not validate as epinterface's model: {exc}") from exc
    for prefix, derived_building in (("Geometry", geo), ("Attic", attic_value), ("Basement", basement_value)):
        parameters.extend(
            Parameter(group=None, path=leaf.path, value=leaf.value, rule=leaf.rule)
            for leaf in _nested(prefix, derived_building)
        )
    return Conversion(
        archetype=archetype,
        parameters=tuple(parameters),
        not_represented=tuple(lost),
        conditioned_floor_area=building.floor_area,
        storey_ratio=facts.storey_ratio,
    )


def set_leaf_paths(archetype: Archetype) -> tuple[tuple[str | None, str], ...]:
    """`(group, path)` of every leaf field the archetype sets, as `parameters[]` must list them.

    Names, metadata and the groups' `Exposure` are left out (see the module's decisions).

    Args:
        archetype: The archetype.

    Returns:
        The pairs, groups in order.
    """
    out: list[tuple[str | None, str]] = []
    for group in archetype.Groups:
        for path, _ in _set_leaves(group):
            if path != "Exposure":
                out.append((group.Name, path))
    for prefix in ("Geometry", "Attic", "Basement"):
        if prefix in archetype.model_fields_set:
            out.extend((None, f"{prefix}.{path}") for path, _ in _set_leaves(getattr(archetype, prefix)))
    return tuple(out)


# --- zone-level features ---------------------------------------------------------------------------


def simple_ventilation_not_represented(zones: Iterable[ClassifiedZone]) -> tuple[NotRepresented, ...]:
    """List simple `ZoneVentilation` (design-flow natural ventilation) of conditioned zones.

    The pinned SBEM fork's natural ventilation opens windows (`ZoneVentilation:WindandStackOpenArea`)
    and has no design-flow ventilation, so these flows have no SBEM field (FR-026).

    Args:
        zones: The classified zones.

    Returns:
        One entry when any conditioned zone has such ventilation, else none.
    """
    found = [(z.zone, r) for z in zones if z.role == "conditioned" for r in z.zone.ventilation if r.design_flow > 0]
    if not found:
        return ()
    return (
        NotRepresented(
            feature="Simple ventilation (ZoneVentilation)",
            effect="Design-flow natural or exhaust ventilation; SBEM has no such airflow.",
            object_type="ZoneVentilation:DesignFlowRate",
            objects=tuple(sorted({r.name for _, r in found})),
            affected_zones=tuple(sorted({zone.name for zone, _ in found})),
            magnitude=sum(r.design_flow * zone.multiplier for zone, r in found),
            unit="m3/s",
            source="to_sbem",
        ),
    )
