"""Conditioning efficiency: consumed energy attributed to the zones it was delivered to (spec 002, FR-022, R12).

Attribution
-----------
EnergyPlus meters consumption by end use and fuel for the whole building (`Heating:<fuel>`,
`Cooling:<fuel>`, `WaterSystems:<fuel>`), while delivery is known per zone. Each hour's
consumption of a mode is attributed to the conditioned zones in proportion to that hour's
delivered energy in the same mode, counting every copy of a multiplied zone
(`multiplier · d_z,h`). Delivery is `Zone Air System Sensible Heating/Cooling Energy` (reported
for one copy, research R2) and, for hot water, the heat its volume needs above mains
temperature (`HotWaterRecord.volume · (target − mains) · ρ·c`, unless the caller passes the hot
water module's own heat profile).

- **Standby.** Consumption in hours without delivery in that mode (standby, pilot lights) is
  not attributed hour by hour. It is reported as the building's total
  (`EnergyAttribution.unattributed`), and each zone's ledger carries its share of it in
  `EnergyTotals.unattributed`, by the zone's annual delivered share of the mode (by floor area
  when the building delivers nothing in that mode), so that group ledgers still add up to the
  building.
- **Pumps and heat rejection** (`Pumps:Electricity`, `HeatRejection:<fuel>`) are split each hour
  between heating and cooling by the hour's building-wide delivery in each mode, then to zones
  as above, into `EnergyTotals.distribution_by_fuel`. Hours with neither go to
  `EnergyAttribution.unattributed_distribution`, and into the zones' `unattributed`, split
  between the modes by annual delivery.
- **Fans are not folded** (FR-022, R19): their energy is the `fans` module's `FanTotals`. Before
  UP-8, a conversion that must fold them into `DistributionCOP` adds `FanTotals.energy` itself.
- **Only conditioned zones** take part. A return plenum reports delivered energy (its
  `Zone Air System` outputs), but it is excluded from the archetype, so it must not take a share.
- **Rated efficiency** (`rated_efficiencies`) comes from the tabular *Equipment Summary*: the
  zone's own zone-equipment coils (supplemental heaters excluded), else the plant serving the
  mode (boilers, chillers, water heaters), else every coil of the mode, each weighted by its
  capacity. A zone's ledger carries it weighted by floor area, and it is used only by a group
  with no delivery in the mode.

The energy-input-ratio fit
--------------------------
`fit_eir(sums)` fits `c_h = (a + b·(T_h − T_ref))·d_h` over (zone, hour) pairs by least squares,
under the constraint that the annual consumption is reproduced exactly, with `T_ref` the
delivered-weighted mean outdoor temperature. With that `T_ref` the constraint reduces to
`a = Σc / Σd`, the seasonal energy input ratio, and `b` is the least-squares slope of the
residual `c − a·d` on `d·(T − T_ref)`. Both only need the additive `EirSums`, so a merged group
refits exactly. `SystemCOP = 1 / a`; `b` is UP-8's slope.

Building-wide data
------------------
The module-level `ledger_fields` cannot see the building's meters, so it refuses to run. The
reduction builds the hook once per building and passes it to `GroupLedger.from_zone`::

    hook = efficiency_hook(sources, classified_zones, evaluate)
    ledger = GroupLedger.from_zone(zone, evaluate, hooks=[..., hook, ...])

`efficiency_hook` is `attribute_energy(building_energy(...))`; `attribute_energy` works on plain
arrays (`BuildingEnergy`) for tests and synthetic data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal

import numpy as np
from idfkit.exceptions import ResultLookupError

from archetypal.reduction.ledger import EirSums, EnergyTotals, Fuel, Mode

if TYPE_CHECKING:
    from collections.abc import Callable

    from idfkit.simulation import SQLResult
    from idfkit.versioned import IDFDocumentSince22_1

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.schedules import Profile, ScheduleEvaluator
    from archetypal.reduction.sources import SourceData

__all__ = [
    "WATER_VOLUMETRIC_HEAT",
    "BuildingEnergy",
    "EnergyAttribution",
    "ZoneEquipment",
    "attribute_energy",
    "building_energy",
    "efficiency_hook",
    "fit_eir",
    "ledger_fields",
    "rated_efficiencies",
    "read_hourly",
    "zone_equipment",
]

WATER_VOLUMETRIC_HEAT = 1000.0 * 4180.0
"""ρ·c of water, J/(m³·K): EnergyPlus's `CPHW` (4180 J/(kg·K)) at 1000 kg/m³."""

HEATING_VARIABLE = "Zone Air System Sensible Heating Energy"
COOLING_VARIABLE = "Zone Air System Sensible Cooling Energy"
OUTDOOR_VARIABLE = "Site Outdoor Air Drybulb Temperature"
MAINS_VARIABLE = "Site Mains Water Temperature"
_HOURLY = "Hourly"
_ENVIRONMENT = "Environment"
_EQUIPMENT_SUMMARY = "EquipmentSummary"
_PRIMARY: Mapping[str, Mode] = {"Heating": "heating", "Cooling": "cooling", "WaterSystems": "hot_water"}
_DISTRIBUTION = ("Pumps", "HeatRejection")
_NOT_FUELS = frozenset({"energytransfer", "water", "mainswater", "rainwater", "wellwater", "onsitewater", "condensate"})
_AIR_MODES: tuple[Literal["heating", "cooling"], ...] = ("heating", "cooling")


# --- hourly results ------------------------------------------------------------------------------


def read_hourly(results: SQLResult, requests: Iterable[tuple[str, str]]) -> dict[tuple[str, str], Profile]:
    """Read hourly series in one scan, keyed by upper-case (name, key); unreported ones are absent.

    Args:
        results: The results.
        requests: (variable or meter name, key) pairs; a meter's key is ignored.

    Returns:
        The run-period series found, as float64 arrays; a meter is keyed with key `""`.
    """
    reported: dict[tuple[str, str], bool] = {}
    for info in results.list_variables():
        if info.frequency == _HOURLY:
            reported[info.name.upper(), "" if info.is_meter else info.key_value.upper()] = info.is_meter
    wanted: list[tuple[str, str]] = []
    for name, key in requests:
        upper = (name.upper(), key.upper())
        meter = (name.upper(), "")
        if reported.get(meter):
            upper = meter
        if upper in reported and upper not in wanted:
            wanted.append(upper)
    if not wanted:
        return {}
    found = results.get_timeseries_many([(name, key or "*", _HOURLY) for name, key in wanted])
    return {item: np.asarray(series.values, dtype=np.float64) for item, series in zip(wanted, found, strict=True)}


def _meters(results: SQLResult) -> dict[str, list[tuple[str, str]]]:
    """End-use meters by end use: `{"Heating": [(meter, fuel), ...], ...}`."""
    meters: dict[str, list[tuple[str, str]]] = {}
    for info in results.list_variables():
        if not info.is_meter or info.frequency != _HOURLY:
            continue
        parts = info.name.split(":")
        if len(parts) != 2 or parts[1].casefold() in _NOT_FUELS:
            continue
        end_use, fuel = parts
        if end_use in _PRIMARY or end_use in _DISTRIBUTION:
            meters.setdefault(end_use, []).append((info.name, fuel))
    return meters


# --- data ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class BuildingEnergy:
    """The building-wide hourly data of the attribution.

    Attributes:
        outdoor_temperature: Outdoor dry-bulb temperature each hour, °C.
        multipliers: Each conditioned zone's multiplier, by zone name.
        floor_area: Each zone's floor area (one copy), m².
        delivered: Delivered energy each hour for one copy, J, by mode and zone.
        consumed: Primary meters each hour, J, by mode and fuel (whole building).
        distribution: Pumps and heat rejection each hour, J, by fuel (whole building).
        rated: Rated efficiency by zone and mode, where known.
    """

    outdoor_temperature: Profile
    multipliers: Mapping[str, int]
    floor_area: Mapping[str, float]
    delivered: Mapping[Mode, Mapping[str, Profile]]
    consumed: Mapping[Mode, Mapping[Fuel, Profile]]
    distribution: Mapping[Fuel, Profile] = field(default_factory=dict[Fuel, "Profile"])
    rated: Mapping[str, Mapping[Mode, float]] = field(default_factory=dict[str, Mapping[Mode, float]])


@dataclass(frozen=True)
class EnergyAttribution:
    """The attribution's result, and the `energy` hook of `GroupLedger.from_zone`.

    Attributes:
        zones: One copy's `EnergyTotals` by zone name and mode.
        unattributed: Primary consumption in hours without delivery, by mode and fuel, J
            (whole building; FR-022's standby list).
        unattributed_distribution: Pump and heat-rejection energy in hours with no delivery, by
            fuel, J (whole building).
    """

    zones: Mapping[str, Mapping[Mode, EnergyTotals]]
    unattributed: Mapping[Mode, Mapping[Fuel, float]]
    unattributed_distribution: Mapping[Fuel, float]

    def __call__(self, zone: ClassifiedZone, schedules: ScheduleEvaluator, /) -> dict[str, object]:
        """Return `{"energy": ...}` for one copy of `zone`; `{}` for a zone not attributed to."""
        del schedules
        totals = self.zones.get(zone.zone.name)
        return {} if totals is None else {"energy": dict(totals)}


# --- attribution ---------------------------------------------------------------------------------


def _nonzero(values: Mapping[str, float]) -> dict[str, float]:
    return {key: value for key, value in sorted(values.items()) if value != 0.0}


def attribute_energy(data: BuildingEnergy) -> EnergyAttribution:
    """Attribute the building's consumption to its conditioned zones (R12).

    Args:
        data: The hourly data.

    Returns:
        One copy's totals per zone and mode, and the unattributed consumption.
    """
    names = sorted(data.multipliers)
    hours = len(data.outdoor_temperature)
    mult = np.asarray([data.multipliers[n] for n in names], dtype=np.float64)
    area = np.asarray([data.floor_area.get(n, 0.0) for n in names], dtype=np.float64)
    zeros = np.zeros(hours)
    modes: list[Mode] = list(dict.fromkeys([*_AIR_MODES, *data.delivered, *data.consumed]))

    delivered: dict[Mode, np.ndarray] = {}
    building: dict[Mode, np.ndarray] = {}
    hourly_share: dict[Mode, np.ndarray] = {}
    annual_share: dict[Mode, np.ndarray] = {}
    for mode in modes:
        by_zone = data.delivered.get(mode, {})
        matrix = np.vstack([np.asarray(by_zone.get(n, zeros), dtype=np.float64) for n in names]) if names else np.zeros((0, hours))
        total = (mult[:, None] * matrix).sum(axis=0)
        delivered[mode] = matrix
        building[mode] = total
        with np.errstate(invalid="ignore", divide="ignore"):
            hourly_share[mode] = np.where(total > 0.0, matrix / np.where(total > 0.0, total, 1.0), 0.0)
        annual = matrix.sum(axis=1)
        weight = annual if float((mult * annual).sum()) > 0.0 else area
        denominator = float((mult * weight).sum())
        annual_share[mode] = weight / denominator if denominator > 0.0 else np.zeros(len(names))

    consumed: dict[Mode, dict[str, dict[Fuel, float]]] = {m: {n: {} for n in names} for m in modes}
    primary_hourly: dict[Mode, np.ndarray] = {m: np.zeros((len(names), hours)) for m in modes}
    distribution: dict[Mode, dict[str, dict[Fuel, float]]] = {m: {n: {} for n in names} for m in modes}
    standby: dict[Mode, dict[str, dict[Fuel, float]]] = {m: {n: {} for n in names} for m in modes}
    unattributed: dict[Mode, dict[Fuel, float]] = {}

    def spread(mode: Mode, fuel: Fuel, amount: float) -> None:
        for i, name in enumerate(names):
            part = amount * float(annual_share[mode][i])
            if part != 0.0:
                standby[mode][name][fuel] = standby[mode][name].get(fuel, 0.0) + part

    for mode in modes:
        for fuel, series in data.consumed.get(mode, {}).items():
            meter = np.asarray(series, dtype=np.float64)
            per_zone = hourly_share[mode] * meter
            primary_hourly[mode] += per_zone
            for i, name in enumerate(names):
                consumed[mode][name][fuel] = float(per_zone[i].sum())
            idle = float(meter[building[mode] <= 0.0].sum())
            if idle != 0.0:
                unattributed.setdefault(mode, {})[fuel] = idle
                spread(mode, fuel, idle)

    unattributed_distribution: dict[Fuel, float] = {}
    heat, cool = building["heating"], building["cooling"]
    both = heat + cool
    with np.errstate(invalid="ignore", divide="ignore"):
        heat_fraction = np.where(both > 0.0, heat / np.where(both > 0.0, both, 1.0), 0.0)
    annual_heat, annual_cool = float(heat.sum()), float(cool.sum())
    idle_heat_fraction = annual_heat / (annual_heat + annual_cool) if annual_heat + annual_cool > 0.0 else 1.0
    for fuel, series in data.distribution.items():
        energy = np.asarray(series, dtype=np.float64)
        for mode, fraction in (("heating", heat_fraction), ("cooling", 1.0 - heat_fraction)):
            per_zone = hourly_share[mode] * (energy * np.where(both > 0.0, fraction, 0.0))
            for i, name in enumerate(names):
                value = float(per_zone[i].sum())
                if value != 0.0:
                    distribution[mode][name][fuel] = distribution[mode][name].get(fuel, 0.0) + value
        idle = float(energy[both <= 0.0].sum())
        if idle != 0.0:
            unattributed_distribution[fuel] = idle
            spread("heating", fuel, idle * idle_heat_fraction)
            spread("cooling", fuel, idle * (1.0 - idle_heat_fraction))

    temperature = np.asarray(data.outdoor_temperature, dtype=np.float64)
    zones: dict[str, dict[Mode, EnergyTotals]] = {}
    for i, name in enumerate(names):
        per_mode: dict[Mode, EnergyTotals] = {}
        for mode in modes:
            rated = data.rated.get(name, {}).get(mode)
            weight = float(area[i]) if rated is not None else 0.0
            per_mode[mode] = EnergyTotals(
                delivered=float(delivered[mode][i].sum()),
                consumed_by_fuel=_nonzero(consumed[mode][name]),
                distribution_by_fuel=_nonzero(distribution[mode][name]),
                unattributed=_nonzero(standby[mode][name]),
                rated_weight=weight,
                rated_weighted=weight * rated if rated is not None else 0.0,
                eir_sums=EirSums.from_hourly(
                    consumed=primary_hourly[mode][i], delivered=delivered[mode][i], outdoor_temperature=temperature
                ),
            )
        zones[name] = per_mode
    return EnergyAttribution(
        zones=zones,
        unattributed={mode: _nonzero(values) for mode, values in sorted(unattributed.items())},
        unattributed_distribution=_nonzero(unattributed_distribution),
    )


# --- the energy-input-ratio fit ------------------------------------------------------------------


def fit_eir(sums: EirSums) -> tuple[float, float, float]:
    """Fit `c = (a + b·(T − T_ref))·d` with the annual consumption exact (R12).

    Args:
        sums: The additive sums over (zone, hour) pairs.

    Returns:
        `(a, b, t_ref)`: the energy input ratio at `t_ref` (1 / COP), its slope per K, and the
        delivered-weighted mean outdoor temperature, °C. `b` is 0 when the outdoor temperature
        does not vary over the delivery hours.

    Raises:
        ValueError: If there is no delivered energy to fit.
    """
    if sums.d <= 0.0:
        msg = "cannot fit an energy input ratio with no delivered energy"
        raise ValueError(msg)
    t_ref = sums.d_t / sums.d
    a = sums.c / sums.d
    denominator = sums.d2_t2 - 2.0 * t_ref * sums.d2_t + t_ref * t_ref * sums.d2
    scale = sums.d2_t2 + t_ref * t_ref * sums.d2
    if denominator <= 1e-9 * scale:
        return a, 0.0, t_ref
    numerator = sums.c_d_t - t_ref * sums.c_d - a * (sums.d2_t - t_ref * sums.d2)
    return a, numerator / denominator, t_ref


# --- zone equipment and rated efficiency ---------------------------------------------------------


@dataclass(frozen=True)
class ZoneEquipment:
    """What a zone's own equipment (not its air loop) holds, by object name.

    Attributes:
        fans: The fans of its zone-equipment units and its exhaust fans.
        heating_coils: The units' main heating coils (supplemental heaters excluded).
        cooling_coils: The units' cooling coils.
    """

    fans: tuple[str, ...] = ()
    heating_coils: tuple[str, ...] = ()
    cooling_coils: tuple[str, ...] = ()

    def __add__(self, other: ZoneEquipment) -> ZoneEquipment:
        """Concatenate two units' parts."""
        return ZoneEquipment(
            self.fans + other.fans,
            self.heating_coils + other.heating_coils,
            self.cooling_coils + other.cooling_coils,
        )


def _names(*values: str | None) -> tuple[str, ...]:
    return tuple(value for value in values if value)


def _units(doc: IDFDocumentSince22_1) -> dict[tuple[str, str], ZoneEquipment]:
    """Each zone-equipment unit's parts, keyed by (object type, name), case-folded."""
    units: dict[tuple[str, str], ZoneEquipment] = {}

    def add(object_type: str, name: str, parts: ZoneEquipment) -> None:
        units[object_type.casefold(), name.casefold()] = parts

    for o in doc["ZoneHVAC:PackagedTerminalAirConditioner"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_name), _names(o.heating_coil_name), _names(o.cooling_coil_name)))
    for o in doc["ZoneHVAC:PackagedTerminalHeatPump"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_name), _names(o.heating_coil_name), _names(o.cooling_coil_name)))
    for o in doc["ZoneHVAC:WaterToAirHeatPump"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_name), _names(o.heating_coil_name), _names(o.cooling_coil_name)))
    for o in doc["ZoneHVAC:FourPipeFanCoil"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_name), _names(o.heating_coil_name), _names(o.cooling_coil_name)))
    for o in doc["ZoneHVAC:UnitHeater"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_name), _names(o.heating_coil_name)))
    for o in doc["ZoneHVAC:UnitVentilator"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_name), _names(o.heating_coil_name), _names(o.cooling_coil_name)))
    for o in doc["ZoneHVAC:WindowAirConditioner"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_name), (), _names(o.dx_cooling_coil_name)))
    for o in doc["ZoneHVAC:EnergyRecoveryVentilator"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_name, o.exhaust_air_fan_name)))
    for o in doc["ZoneHVAC:EvaporativeCoolerUnit"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_name)))
    for o in doc["ZoneHVAC:TerminalUnit:VariableRefrigerantFlow"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_air_fan_object_name)))
    for o in doc["AirLoopHVAC:UnitarySystem"]:
        add(o.obj_type, o.name, ZoneEquipment(_names(o.supply_fan_name), _names(o.heating_coil_name), _names(o.cooling_coil_name)))
    for o in doc["Fan:ZoneExhaust"]:
        add(o.obj_type, o.name, ZoneEquipment((o.name,)))
    return units


def zone_equipment(doc: IDFDocumentSince22_1) -> dict[str, ZoneEquipment]:
    """Each zone's own equipment, from its `ZoneHVAC:EquipmentList`.

    Air distribution units are not included: their air comes from an air loop (see the `fans`
    module for loop attribution).

    Args:
        doc: The model.

    Returns:
        The parts by case-folded zone name; zones without such equipment are absent.
    """
    units = _units(doc)
    lists = {item.name.casefold(): item for item in doc["ZoneHVAC:EquipmentList"]}
    result: dict[str, ZoneEquipment] = {}
    for connections in doc["ZoneHVAC:EquipmentConnections"]:
        equipment_list = lists.get(connections.zone_conditioning_equipment_list_name.casefold())
        if equipment_list is None:
            continue
        parts = ZoneEquipment()
        for entry in equipment_list.equipment:
            unit = units.get((entry.zone_equipment_object_type.casefold(), entry.zone_equipment_name.casefold()))
            if unit is not None:
                parts += unit
        if parts != ZoneEquipment():
            result[connections.zone_name.casefold()] = parts
    return result


def _number(text: str | None) -> float | None:
    if text is None:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def equipment_table(results: SQLResult, table: str) -> dict[str, dict[str, str]]:
    """One *Equipment Summary* table as `{ROW NAME: {column: value}}`; `{}` when absent."""
    try:
        rows = results.get_tabular_data(report_name=_EQUIPMENT_SUMMARY, table_name=table, report_for="Entire Facility")
    except ResultLookupError:
        return {}
    table_rows: dict[str, dict[str, str]] = {}
    for row in rows:
        table_rows.setdefault(row.row_name.upper(), {})[row.column_name] = row.value
    return table_rows


def _weighted_mean(pairs: Iterable[tuple[float | None, float | None]]) -> float | None:
    total = weight_sum = 0.0
    for efficiency, weight in pairs:
        if efficiency is None or efficiency <= 0.0:
            continue
        w = weight if weight is not None and weight > 0.0 else 1.0
        total += w * efficiency
        weight_sum += w
    return total / weight_sum if weight_sum > 0.0 else None


def _coil_mean(coils: Mapping[str, Mapping[str, str]], names: Iterable[str] | None = None) -> float | None:
    keys = list(coils) if names is None else [name.upper() for name in names]
    return _weighted_mean(
        (_number(coils[k].get("Nominal Efficiency")), _number(coils[k].get("Nominal Total Capacity")))
        for k in keys
        if k in coils and coils[k].get("Used as Supplementary Heat", "N") != "Y"
    )


def _plant_mean(plant: Mapping[str, Mapping[str, str]], prefix: str) -> float | None:
    def first(row: Mapping[str, str], *columns: str) -> float | None:
        for column in columns:
            value = _number(row.get(column))
            if value is not None:
                return value
        return None

    return _weighted_mean(
        (first(row, "Rated Efficiency", "Reference Efficiency"), first(row, "Rated Capacity", "Reference Capacity"))
        for row in plant.values()
        if row.get("Type", "").startswith(prefix)
    )


def rated_efficiencies(sources: SourceData, zones: Sequence[ClassifiedZone]) -> dict[str, dict[Mode, float]]:
    """Each zone's rated efficiency per mode, from the tabular *Equipment Summary* (R12).

    In order: the capacity-weighted mean of the zone's own zone-equipment coils (supplemental
    heaters excluded); else the plant's (boilers for heating, chillers for cooling); else every
    coil of the mode with a nominal efficiency. Hot water takes the water heaters' thermal
    efficiency, weighted by input.

    Args:
        sources: The checked model and results.
        zones: The zones.

    Returns:
        The efficiencies (COP, or efficiency as a fraction) by zone name and mode, where known.
    """
    results = sources.results
    heating_coils = equipment_table(results, "Heating Coils")
    cooling_coils = equipment_table(results, "Cooling Coils")
    plant = equipment_table(results, "Central Plant")
    water_heaters = equipment_table(results, "Service Water Heating")
    fallback: dict[Mode, float | None] = {
        "heating": _plant_mean(plant, "Boiler:") or _coil_mean(heating_coils),
        "cooling": _plant_mean(plant, "Chiller:") or _coil_mean(cooling_coils),
        "hot_water": _weighted_mean(
            (_number(row.get("Thermal Efficiency")), _number(row.get("Input"))) for row in water_heaters.values()
        ),
    }
    own = zone_equipment(sources.model)
    rated: dict[str, dict[Mode, float]] = {}
    for zone in zones:
        parts = own.get(zone.zone.name.casefold(), ZoneEquipment())
        values: dict[Mode, float | None] = {
            "heating": _coil_mean(heating_coils, parts.heating_coils) if parts.heating_coils else None,
            "cooling": _coil_mean(cooling_coils, parts.cooling_coils) if parts.cooling_coils else None,
            "hot_water": None,
        }
        chosen = {mode: value if value is not None else fallback[mode] for mode, value in values.items()}
        rated[zone.zone.name] = {mode: value for mode, value in chosen.items() if value is not None}
    return rated


# --- building data -------------------------------------------------------------------------------


def _hot_water_heat(
    zone: ClassifiedZone, mains: Profile, evaluate: Callable[[str], Profile], hours: int
) -> Profile:
    heat = np.zeros(hours)
    for record in zone.zone.hot_water:
        if record.target_temperature_schedule is None:
            continue
        rise = np.maximum(np.asarray(evaluate(record.target_temperature_schedule), dtype=np.float64) - mains, 0.0)
        heat += np.asarray(record.volume, dtype=np.float64) * rise * WATER_VOLUMETRIC_HEAT
    return heat


def building_energy(
    sources: SourceData,
    zones: Sequence[ClassifiedZone],
    evaluate: Callable[[str], Profile],
    *,
    hot_water_heat: Mapping[str, Profile] | None = None,
) -> BuildingEnergy:
    """Read the hourly data of the attribution for the conditioned zones.

    Args:
        sources: The checked model and results.
        zones: The classified zones; only conditioned ones are attributed to.
        evaluate: The schedule evaluator (hot-water target temperatures).
        hot_water_heat: Hot water heat delivered each hour to one copy, J, by zone name, to use
            instead of `volume · (target − mains) · ρ·c` (pass the hot-water module's heat so
            both agree).

    Returns:
        The data.
    """
    results = sources.results
    conditioned = [zone for zone in zones if zone.conditioned]
    meters = _meters(results)
    requests: list[tuple[str, str]] = [(OUTDOOR_VARIABLE, _ENVIRONMENT), (MAINS_VARIABLE, _ENVIRONMENT)]
    for zone in conditioned:
        requests += [(HEATING_VARIABLE, zone.zone.name), (COOLING_VARIABLE, zone.zone.name)]
    requests += [(meter, "") for pairs in meters.values() for meter, _ in pairs]
    series = read_hourly(results, requests)
    hours = len(series.get((OUTDOOR_VARIABLE.upper(), _ENVIRONMENT.upper()), ())) or sources.run_period.calendar.hours
    zeros = np.zeros(hours)

    def get(name: str, key: str) -> Profile:
        return series.get((name.upper(), key.upper()), zeros)

    mains = get(MAINS_VARIABLE, _ENVIRONMENT)
    delivered: dict[Mode, dict[str, Profile]] = {"heating": {}, "cooling": {}}
    for zone in conditioned:
        name = zone.zone.name
        delivered["heating"][name] = get(HEATING_VARIABLE, name)
        delivered["cooling"][name] = get(COOLING_VARIABLE, name)
    consumed: dict[Mode, dict[Fuel, Profile]] = {}
    for end_use, mode in _PRIMARY.items():
        for meter, fuel in meters.get(end_use, []):
            consumed.setdefault(mode, {})[fuel] = get(meter, "")
    if "hot_water" in consumed or any(zone.zone.hot_water for zone in conditioned):
        delivered["hot_water"] = {
            zone.zone.name: (
                np.asarray(hot_water_heat[zone.zone.name], dtype=np.float64)
                if hot_water_heat is not None and zone.zone.name in hot_water_heat
                else _hot_water_heat(zone, mains, evaluate, hours)
            )
            for zone in conditioned
        }
    distribution: dict[Fuel, Profile] = {}
    for end_use in _DISTRIBUTION:
        for meter, fuel in meters.get(end_use, []):
            distribution[fuel] = distribution.get(fuel, zeros) + get(meter, "")
    return BuildingEnergy(
        outdoor_temperature=get(OUTDOOR_VARIABLE, _ENVIRONMENT),
        multipliers={zone.zone.name: zone.zone.multiplier for zone in conditioned},
        floor_area={zone.zone.name: zone.zone.floor_area for zone in conditioned},
        delivered=delivered,
        consumed=consumed,
        distribution=distribution,
        rated=rated_efficiencies(sources, conditioned),
    )


def efficiency_hook(
    sources: SourceData,
    zones: Sequence[ClassifiedZone],
    evaluate: Callable[[str], Profile],
    *,
    hot_water_heat: Mapping[str, Profile] | None = None,
) -> EnergyAttribution:
    """Build the `energy` hook of a building: `attribute_energy(building_energy(...))`.

    Args:
        sources: The checked model and results.
        zones: The classified zones.
        evaluate: The schedule evaluator.
        hot_water_heat: See `building_energy`.

    Returns:
        The attribution, callable as a `ZoneHook`.
    """
    return attribute_energy(building_energy(sources, zones, evaluate, hot_water_heat=hot_water_heat))


def ledger_fields(zone: ClassifiedZone, schedules: ScheduleEvaluator) -> dict[str, object]:
    """Refuse: attribution needs the building's meters, which a single zone does not carry.

    Raises:
        ValueError: Always; pass `efficiency_hook(sources, zones, evaluate)` to
            `GroupLedger.from_zone(..., hooks=[...])` instead.
    """
    del zone, schedules
    msg = (
        "efficiency needs building-wide meters: build the hook with "
        "efficiency_hook(sources, zones, evaluate) and pass it to GroupLedger.from_zone(..., hooks=[...])"
    )
    raise ValueError(msg)
