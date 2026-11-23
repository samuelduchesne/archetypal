"""Fan energy and air volume per zone, and the quantities UP-8 carries (spec 002, FR-022a, R19).

Attribution
-----------
Every fan's hourly `Fan Electricity Energy` and `Fan Air Mass Flow Rate` go to zones:

- a **zone-equipment fan** (the fan of a PTAC, PTHP, fan coil, unit heater, ..., a zone exhaust
  fan, or the fan of an air terminal such as a PIU) belongs to its zone;
- an **air-loop fan** (the *Equipment Summary* Fans table names its air loop) is split between
  the zones the loop serves, each hour in proportion to the mass flow through each zone's
  air-distribution-unit inlet nodes (`System Node Mass Flow Rate`), counting only the units whose
  terminal the loop's supply path feeds when that is known. An hour with fan flow but no inlet
  flow is split by the zones' annual inlet flow. The zones a loop serves are those whose return
  nodes its return path collects (`AirLoopHVAC:ReturnPath` through zone mixers and return
  plenums), and those its supply path feeds (`airflow.air_loop_zones`, so a dedicated
  outdoor-air loop without a return path serves its zones); with a single air loop, every zone
  fed by an air distribution unit.

Air volume is mass flow ÷ the standard air density EnergyPlus uses for "standard density"
outputs, `StdRhoAir` at 20 °C, dry air and the site's standard pressure, so it matches the ideal
loads' standard-density volume.

HVAC outputs of a multiplied zone describe **every copy** (the equipment is sized for, and the
air loop supplies, all copies; the fixture confirms the inlet-node flows add up to the loop
fan's flow without weighting), while `Zone Air System Sensible Heating/Cooling Energy` describes
one copy. Fan energy and volume are therefore divided by the zone's multiplier here, and
`GroupLedger.from_zone` multiplies once.

Here "delivery" is the zone air's sensible load (`Zone Air System Sensible Heating/Cooling
Energy`), not the equipment delivery of `efficiency` (R12): the supply air temperature difference
acts on the zone air, while the outdoor-air load is met before the air reaches the zone. Per
zone, an hour is a heating hour when heating delivery is positive and at least the cooling
delivery, a cooling hour when cooling delivery is larger. `volume_in_mode` and
`delivered_in_mode` sum those hours; `volume_without_demand` sums hours with neither delivery
nor mechanical outdoor air.

Group quantities (UP-8)
-----------------------
- `specific_fan_power(totals) = energy / volume`, W/(m³/s); times the detailed volume it gives
  the detailed fan energy exactly (SC-005).
- `effective_supply_delta(totals, mode) = delivered_in_mode / (rho·c_p·volume_in_mode)`, K: added
  to the heating setpoint (subtracted from the cooling setpoint) it is the ideal loads' supply
  air temperature limit (rule `fans.effective_supply_delta`).

Building-wide data
------------------
As for `efficiency`, the module-level `ledger_fields` refuses to run; build the hook once::

    hook = fans_hook(sources, classified_zones)
    ledger = GroupLedger.from_zone(zone, evaluate, hooks=[..., hook, ...])

The hook attributes to every zone it serves, conditioned or not; the energy of zones excluded
from the archetype stays in `FanAttribution.zones` for the report.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Literal, TypeAlias

import numpy as np

from archetypal.reduction._sql_tables import read_site_elevation
from archetypal.reduction.airflow import TERMINAL_INLET_FIELDS, air_loop_zones
from archetypal.reduction.efficiency import equipment_table, read_hourly, zone_equipment
from archetypal.reduction.ledger import FanTotals, Mode

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    import numpy.typing as npt
    from idfkit.simulation import SQLResult
    from idfkit.versioned import IDFDocumentSince22_1

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.schedules import Profile, ScheduleEvaluator
    from archetypal.reduction.sources import SourceData

__all__ = [
    "AIR_SPECIFIC_HEAT",
    "AirLoops",
    "BuildingFans",
    "FanAttribution",
    "FanSeries",
    "air_loops",
    "attribute_fans",
    "building_fans",
    "effective_supply_delta",
    "fan_requests",
    "fans_hook",
    "ledger_fields",
    "loop_shares",
    "specific_fan_power",
    "standard_air_density",
]

AIR_SPECIFIC_HEAT = 1004.84
"""Specific heat of dry air, J/(kg·K) (EnergyPlus `PsyCpAirFnW(0)`)."""

_GAS_CONSTANT = 287.0
# EnergyPlus's `PsyRhoAirFnPbTdbW` at its humidity-ratio floor of 1e-5.
_HUMIDITY_FACTOR = 1.0 + 1.6077687 * 1.0e-5
_STANDARD_TEMPERATURE = 20.0
_SECONDS_PER_HOUR = 3600.0
_ENERGY_VARIABLE = "Fan Electricity Energy"
_FLOW_VARIABLE = "Fan Air Mass Flow Rate"
_NODE_VARIABLE = "System Node Mass Flow Rate"
# The zone air's sensible load: what the supply air temperature difference acts on (R19).
HEATING_VARIABLE = "Zone Air System Sensible Heating Energy"
COOLING_VARIABLE = "Zone Air System Sensible Cooling Energy"
_AirMode = Literal["heating", "cooling"]
_Array: TypeAlias = "npt.NDArray[np.float64]"
_Bool: TypeAlias = "npt.NDArray[np.bool_]"


def standard_air_density(elevation: float) -> float:
    """EnergyPlus's `StdRhoAir` (`PsyRhoAirFnPbTdbW(p, 20, 0)`): dry air at 20 °C and the standard pressure at `elevation` (m), kg/m³."""
    pressure = 101325.0 * (1.0 - 2.25577e-5 * elevation) ** 5.2559
    return pressure / (_GAS_CONSTANT * (_STANDARD_TEMPERATURE + 273.15) * _HUMIDITY_FACTOR)


# --- data ----------------------------------------------------------------------------------------


@dataclass(frozen=True)
class FanSeries:
    """One fan's hourly results and what it serves.

    Attributes:
        name: The fan's name.
        energy: Electricity each hour, J (every copy of its zone).
        mass_flow: Air mass flow, hourly mean, kg/s.
        zone: The zone of a zone-equipment fan.
        loop_zones: The zones an air-loop fan serves.
        loop_inlet_flow: Mass flow through the inlet nodes of the air distribution units the
            fan's loop feeds, kg/s, every copy, by zone name; `None` when the units cannot be told
            apart by loop, and `BuildingFans.inlet_flow` (every unit of the zone) is used.
    """

    name: str
    energy: Profile
    mass_flow: Profile
    zone: str | None = None
    loop_zones: tuple[str, ...] = ()
    loop_inlet_flow: Mapping[str, Profile] | None = None


@dataclass(frozen=True)
class BuildingFans:
    """The building-wide hourly data of the fan attribution.

    Attributes:
        fans: Every fan.
        inlet_flow: Mass flow through each zone's air-distribution-unit inlet nodes, kg/s, every copy.
        multipliers: Each zone's multiplier, by zone name.
        floor_area: Each zone's floor area (one copy), m².
        delivered: Delivered heating and cooling each hour for one copy, J, by mode and zone.
        outdoor_air: Mechanical outdoor air each hour for one copy, m³/s, by zone.
        air_density: Standard air density, kg/m³.
    """

    fans: tuple[FanSeries, ...]
    inlet_flow: Mapping[str, Profile]
    multipliers: Mapping[str, int]
    floor_area: Mapping[str, float]
    delivered: Mapping[_AirMode, Mapping[str, Profile]]
    outdoor_air: Mapping[str, Profile]
    air_density: float


@dataclass(frozen=True)
class FanAttribution:
    """The attribution's result, and the `fans` hook of `GroupLedger.from_zone`.

    Attributes:
        zones: One copy's `FanTotals` by zone name.
        multipliers: Each zone's multiplier.
        air_density: The standard air density used, kg/m³.
        unattributed_fans: Fans matched to no zone, by name.
        unattributed_energy: Their energy, J.
        unattributed_volume: Their air volume, m³.
    """

    zones: Mapping[str, FanTotals]
    multipliers: Mapping[str, int]
    air_density: float
    unattributed_fans: tuple[str, ...] = ()
    unattributed_energy: float = 0.0
    unattributed_volume: float = 0.0

    def multipliers_applied(self, name: str) -> FanTotals:
        """Return the totals of every copy of zone `name`."""
        return self.zones[name].scaled(self.multipliers[name])

    def __call__(self, zone: ClassifiedZone, schedules: ScheduleEvaluator, /) -> dict[str, object]:
        """Return `{"fans": ...}` for one copy of `zone`; `{}` for a zone with no fan data."""
        del schedules
        totals = self.zones.get(zone.zone.name)
        return {} if totals is None else {"fans": totals}


# --- attribution ---------------------------------------------------------------------------------


def loop_shares(
    inlet_flow: Mapping[str, Profile], weights: Mapping[str, float], served: Sequence[str], hours: int
) -> _Array:
    """Each served zone's share (every copy) of an air loop's flow, hour by hour (R19).

    Shares follow the hour's mass flow through each zone's air-distribution-unit inlet nodes.
    An hour without inlet flow is split by the zones' annual inlet flow, or by `weights`
    (multiplier times floor area) when no zone has any, or equally.

    Args:
        inlet_flow: Mass flow through each zone's inlet nodes, kg/s, every copy, by zone name.
        weights: The fallback weight of each zone, by zone name.
        served: The zones the loop serves.
        hours: The number of hours.

    Returns:
        A (zone, hour) array whose columns sum to 1.
    """
    flows = np.zeros((len(served), hours))
    for i, zone in enumerate(served):
        if zone in inlet_flow:
            flows[i] = inlet_flow[zone]
    total = flows.sum(axis=0)
    annual = flows.sum(axis=1)
    if float(annual.sum()) <= 0.0:
        annual = np.array([weights.get(z, 0.0) for z in served], dtype=np.float64)
    if float(annual.sum()) <= 0.0:
        annual = np.ones(len(served))
    fallback = np.zeros((len(served), hours)) + (annual / annual.sum())[:, None]
    return np.divide(flows, total, out=fallback, where=total > 0.0)


def _loop_shares(data: BuildingFans, fan: FanSeries, served: Sequence[str], hours: int) -> _Array:
    """Each served zone's share (every copy) of an air-loop fan, hour by hour, by its own loop's inlet flow."""
    weights = {z: data.multipliers[z] * data.floor_area.get(z, 0.0) for z in served}
    inlet_flow = data.inlet_flow if fan.loop_inlet_flow is None else fan.loop_inlet_flow
    return loop_shares(inlet_flow, weights, served, hours)


def _zone_totals(data: BuildingFans, name: str, energy: _Array, volume: _Array) -> FanTotals:
    """One copy's `FanTotals` from its hourly fan energy and volume."""
    zero = np.zeros(len(volume))
    heat = np.asarray(data.delivered.get("heating", {}).get(name, zero), dtype=np.float64)
    cool = np.asarray(data.delivered.get("cooling", {}).get(name, zero), dtype=np.float64)
    outdoor = np.asarray(data.outdoor_air.get(name, zero), dtype=np.float64)
    if len(outdoor) != len(volume):
        outdoor = zero
    idle = (heat <= 0.0) & (cool <= 0.0) & (outdoor <= 0.0)
    modes: tuple[tuple[Mode, _Bool, _Array], ...] = (
        ("heating", (heat > 0.0) & (heat >= cool), heat),
        ("cooling", (cool > 0.0) & (cool > heat), cool),
    )
    volume_in_mode: dict[Mode, float] = {}
    delivered_in_mode: dict[Mode, float] = {}
    for mode, hours_in_mode, delivered in modes:
        mode_volume = float(volume[hours_in_mode].sum())
        if mode_volume != 0.0:
            volume_in_mode[mode] = mode_volume
            delivered_in_mode[mode] = float(delivered[hours_in_mode].sum())
    return FanTotals(
        energy=float(energy.sum()),
        volume=float(volume.sum()),
        volume_in_mode=volume_in_mode,
        delivered_in_mode=delivered_in_mode,
        volume_without_demand=float(volume[idle].sum()),
    )


def attribute_fans(data: BuildingFans) -> FanAttribution:
    """Attribute fan energy and air volume to zones (R19).

    Args:
        data: The hourly data.

    Returns:
        One copy's totals per zone, and the fans matched to no zone.
    """
    names = sorted(data.multipliers)
    profiles = [fan.energy for fan in data.fans] + [p for by_zone in data.delivered.values() for p in by_zone.values()]
    hours = len(profiles[0]) if profiles else 0
    energy = {name: np.zeros(hours) for name in names}
    volume = {name: np.zeros(hours) for name in names}
    orphans: list[str] = []
    orphan_energy = orphan_volume = 0.0
    for fan in data.fans:
        fan_energy = np.asarray(fan.energy, dtype=np.float64)
        fan_volume = np.asarray(fan.mass_flow, dtype=np.float64) * _SECONDS_PER_HOUR / data.air_density
        served = [zone for zone in fan.loop_zones if zone in data.multipliers]
        if fan.zone is not None and fan.zone in data.multipliers:
            shares: list[tuple[str, _Array | float]] = [(fan.zone, 1.0)]
        elif served:
            matrix = _loop_shares(data, fan, served, hours)
            shares = [(zone, matrix[i]) for i, zone in enumerate(served)]
        else:
            orphans.append(fan.name)
            orphan_energy += float(fan_energy.sum())
            orphan_volume += float(fan_volume.sum())
            continue
        for zone, share in shares:
            multiplier = data.multipliers[zone]
            energy[zone] += share * fan_energy / multiplier
            volume[zone] += share * fan_volume / multiplier
    return FanAttribution(
        zones={name: _zone_totals(data, name, energy[name], volume[name]) for name in names},
        multipliers=dict(data.multipliers),
        air_density=data.air_density,
        unattributed_fans=tuple(orphans),
        unattributed_energy=orphan_energy,
        unattributed_volume=orphan_volume,
    )


# --- group quantities ----------------------------------------------------------------------------


def specific_fan_power(totals: FanTotals) -> float | None:
    """Fan energy per volume of air moved, J/m³ = W/(m³/s) (rule `fans.energy_per_volume`).

    Returns:
        `energy / volume`, or `None` when no air was moved.
    """
    if totals.volume <= 0.0:
        return None
    return totals.energy / totals.volume


def effective_supply_delta(
    totals: FanTotals,
    mode: _AirMode,
    *,
    air_density: float = standard_air_density(0.0),
    specific_heat: float = AIR_SPECIFIC_HEAT,
) -> float | None:
    """The detailed model's effective supply temperature difference in a mode, K (R19).

    Args:
        totals: The group's fan totals.
        mode: `heating` or `cooling`.
        air_density: The standard air density of the volumes, kg/m³.
        specific_heat: Air's specific heat, J/(kg·K).

    Returns:
        `delivered_in_mode / (rho·c_p·volume_in_mode)`, or `None` without air moved in that mode.
    """
    volume = totals.volume_in_mode.get(mode, 0.0)
    if volume <= 0.0:
        return None
    return totals.delivered_in_mode.get(mode, 0.0) / (air_density * specific_heat * volume)


# --- building data -------------------------------------------------------------------------------


def _node_lists(doc: IDFDocumentSince22_1) -> dict[str, tuple[str, ...]]:
    return {item.name.casefold(): tuple(group.node_name for group in item.nodes) for item in doc["NodeList"]}


def _expand(name: str | None, node_lists: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    if not name:
        return ()
    return node_lists.get(name.casefold(), (name,))


def _loop_zones(doc: IDFDocumentSince22_1, node_lists: Mapping[str, tuple[str, ...]]) -> dict[str, set[str]]:
    """Case-folded zone names each air loop's return path collects or supply path feeds, by case-folded loop name."""
    mixers = {o.name.casefold(): [n.inlet_node_name for n in o.nodes] for o in doc["AirLoopHVAC:ZoneMixer"]}
    plenums = {o.name.casefold(): [n.inlet_node_name for n in o.nodes] for o in doc["AirLoopHVAC:ReturnPlenum"]}
    paths: dict[str, set[str]] = {}
    for path in doc["AirLoopHVAC:ReturnPath"]:
        nodes: set[str] = set()
        for component in path.components:
            name = component.component_name.casefold()
            for node in mixers.get(name, []) + plenums.get(name, []):
                nodes.update(n.casefold() for n in _expand(node, node_lists))
        paths[path.return_air_path_outlet_node_name.casefold()] = nodes
    returns = {
        c.zone_name.casefold(): {n.casefold() for n in _expand(c.zone_return_air_node_or_nodelist_name, node_lists)}
        for c in doc["ZoneHVAC:EquipmentConnections"]
    }
    loops: dict[str, set[str]] = {}
    for loop in doc["AirLoopHVAC"]:
        collected = paths.get((loop.demand_side_outlet_node_name or "").casefold(), set())
        loops[loop.name.casefold()] = {zone for zone, nodes in returns.items() if nodes & collected}
    for name, zones in air_loop_zones(doc).items():  # the supply side: a loop without a return path
        loops.setdefault(name.casefold(), set()).update(zones)
    return loops


def _elevation(doc: IDFDocumentSince22_1, results: SQLResult | None = None) -> float:
    """The site elevation EnergyPlus ran with, m.

    For a weather-file run EnergyPlus takes the weather file's location unless `Site:Location`
    keeps its own, so the elevation the results report (`read_site_elevation`) is read first;
    `Site:Location`'s elevation, else 0, without it.
    """
    if results is not None:
        reported = read_site_elevation(results)
        if reported is not None:
            return reported
    for location in doc["Site:Location"]:
        return float(location.elevation or 0.0)
    return 0.0


def _adu_nodes(
    doc: IDFDocumentSince22_1, model_names: Mapping[str, str], node_lists: Mapping[str, tuple[str, ...]]
) -> dict[str, tuple[str, ...]]:
    """Each zone's inlet nodes fed by an air distribution unit, by zone name."""
    adu_outlets = {o.air_distribution_unit_outlet_node_name.casefold() for o in doc["ZoneHVAC:AirDistributionUnit"]}
    adu_nodes: dict[str, tuple[str, ...]] = {}
    for connections in doc["ZoneHVAC:EquipmentConnections"]:
        name = model_names.get(connections.zone_name.casefold())
        inlets = _expand(connections.zone_air_inlet_node_or_nodelist_name, node_lists)
        fed = tuple(node for node in inlets if node.casefold() in adu_outlets)
        if name is not None and fed:
            adu_nodes[name] = fed
    return adu_nodes


_TERMINAL_INLETS = TERMINAL_INLET_FIELDS


def _supply_outlets(doc: IDFDocumentSince22_1) -> dict[str, set[str]]:
    """Case-folded outlet nodes of each air loop's supply paths (splitters and supply plenums), by loop."""
    splitters = {o.name.casefold(): [n.outlet_node_name for n in o.nodes] for o in doc["AirLoopHVAC:ZoneSplitter"]}
    plenums = {o.name.casefold(): [n.outlet_node_name for n in o.nodes] for o in doc["AirLoopHVAC:SupplyPlenum"]}
    paths: dict[str, set[str]] = {}
    for path in doc["AirLoopHVAC:SupplyPath"]:
        nodes = paths.setdefault((path.supply_air_path_inlet_node_name or "").casefold(), set())
        for component in path.components:
            name = component.component_name.casefold()
            nodes.update((n or "").casefold() for n in splitters.get(name, []) + plenums.get(name, []))
    return {
        loop.name.casefold(): paths.get((loop.demand_side_inlet_node_names or "").casefold(), set())
        for loop in doc["AirLoopHVAC"]
    }


def _loop_adu_nodes(
    doc: IDFDocumentSince22_1, adu_nodes: Mapping[str, tuple[str, ...]]
) -> dict[str, dict[str, tuple[str, ...]]]:
    """Each zone's ADU inlet nodes fed by each air loop, by case-folded loop name, then zone name.

    An air distribution unit belongs to a loop when its terminal's air inlet node is an outlet of
    the loop's supply path. When a unit cannot be traced to a loop, the result is empty and every
    loop's split uses the zones' whole inlet flow, as with a single loop.
    """
    outlets = _supply_outlets(doc)
    unit_inlets: dict[str, set[str]] = {}  # ADU outlet node -> its terminal's air inlet nodes
    for adu in doc["ZoneHVAC:AirDistributionUnit"]:
        # The terminal's type is data (single duct, PIU, dual duct), read through its inlet fields below.
        collection = doc[adu.air_terminal_object_type]
        terminal = collection.get(adu.air_terminal_name) if adu.air_terminal_name else None
        if terminal is None:
            continue
        inlets = {str(terminal.data[f]).casefold() for f in _TERMINAL_INLETS if terminal.data.get(f)}
        unit_inlets[adu.air_distribution_unit_outlet_node_name.casefold()] = inlets
    loops: dict[str, dict[str, tuple[str, ...]]] = {}
    for loop, supply in outlets.items():
        by_zone = {
            zone: fed
            for zone, nodes in adu_nodes.items()
            if (fed := tuple(n for n in nodes if unit_inlets.get(n.casefold(), set()) & supply))
        }
        if by_zone:
            loops[loop] = by_zone
    traced = {n for by_zone in loops.values() for nodes in by_zone.values() for n in nodes}
    if any(n not in traced for nodes in adu_nodes.values() for n in nodes):
        return {}
    return loops


@dataclass(frozen=True)
class AirLoops:
    """Which zones each air loop serves, and through which inlet nodes (R19).

    Attributes:
        served: The zones each loop serves (model spelling, sorted), by case-folded loop name.
            A zone fed by an air distribution unit but on no loop's return path is given to
            the only loop when there is one.
        inlet_nodes: Each zone's inlet nodes fed by an air distribution unit, by zone name.
        loop_inlet_nodes: Of those, the nodes each loop's supply path feeds, by case-folded loop
            name, then zone name; a loop is absent when none of its units could be traced.
    """

    served: Mapping[str, tuple[str, ...]]
    inlet_nodes: Mapping[str, tuple[str, ...]]
    loop_inlet_nodes: Mapping[str, Mapping[str, tuple[str, ...]]] = field(
        default_factory=dict[str, "Mapping[str, tuple[str, ...]]"]
    )


def air_loops(doc: IDFDocumentSince22_1, zone_names: Iterable[str]) -> AirLoops:
    """Find the zones each air loop serves and their air-distribution-unit inlet nodes.

    Args:
        doc: The model.
        zone_names: The zones that may be served (model spelling).

    Returns:
        The loops' zones and the zones' inlet nodes.
    """
    model_names = {name.casefold(): name for name in zone_names}
    node_lists = _node_lists(doc)
    adu_nodes = _adu_nodes(doc, model_names, node_lists)
    loops = _loop_zones(doc, node_lists)
    assigned = {zone for served in loops.values() for zone in served}
    unassigned = {name.casefold() for name in adu_nodes} - assigned
    if unassigned and len(loops) == 1:
        next(iter(loops.values())).update(unassigned)
    served = {loop: tuple(sorted(model_names[z] for z in zones if z in model_names)) for loop, zones in loops.items()}
    return AirLoops(served=served, inlet_nodes=adu_nodes, loop_inlet_nodes=_loop_adu_nodes(doc, adu_nodes))


def _fan_zones(sources: SourceData, model_names: Mapping[str, str]) -> dict[str, str]:
    """The zone of each zone-equipment and air-terminal fan, by case-folded fan name."""
    fan_zone: dict[str, str] = {}
    for zone_key, parts in zone_equipment(sources.model).items():
        if zone_key in model_names:
            fan_zone.update((fan.casefold(), model_names[zone_key]) for fan in parts.fans)
    for row in equipment_table(sources.results, "Air Terminals").values():
        fan, zone = row.get("Fan Name", ""), row.get("Zone Name", "")
        if fan and zone.casefold() in model_names:
            fan_zone[fan.casefold()] = model_names[zone.casefold()]
    return fan_zone


def fan_requests(sources: SourceData, zone_names: Iterable[str]) -> list[tuple[str, str]]:
    """The hourly series `building_fans` reads for the zones `zone_names` (model spelling)."""
    names = list(zone_names)
    return _requests(sources.facts.fans, air_loops(sources.model, names), names)


def _requests(fan_names: Iterable[str], topology: AirLoops, zone_names: Iterable[str]) -> list[tuple[str, str]]:
    requests = [(variable, fan) for fan in fan_names for variable in (_ENERGY_VARIABLE, _FLOW_VARIABLE)]
    requests += [
        (_NODE_VARIABLE, node) for nodes in topology.inlet_nodes.values() for node in nodes
    ]  # every loop's too
    requests += [(variable, zone) for zone in zone_names for variable in (HEATING_VARIABLE, COOLING_VARIABLE)]
    return requests


def building_fans(sources: SourceData, zones: Sequence[ClassifiedZone]) -> BuildingFans:
    """Read the hourly data of the fan attribution.

    Args:
        sources: The checked model and results.
        zones: The classified zones (every zone a fan serves may receive its share).

    Returns:
        The data.
    """
    doc = sources.model
    results = sources.results
    model_names = {zone.zone.name.casefold(): zone.zone.name for zone in zones}
    topology = air_loops(doc, model_names.values())
    adu_nodes = topology.inlet_nodes

    fan_zone = _fan_zones(sources, model_names)
    fan_loop = {
        name.casefold(): row.get("Airloop Name", "").casefold()
        for name, row in equipment_table(results, "Fans").items()
    }

    fan_names = sources.facts.fans
    series = read_hourly(results, _requests(fan_names, topology, model_names.values()))
    hours = next((len(profile) for profile in series.values()), sources.run_period.calendar.hours)
    zeros = np.zeros(hours)

    def get(variable: str, key: str) -> Profile:
        return series.get((variable.upper(), key.upper()), zeros)

    def flow(nodes: Iterable[str]) -> Profile:
        return sum((get(_NODE_VARIABLE, node) for node in nodes), zeros)

    loop_flows = {
        loop: {name: flow(nodes) for name, nodes in by_zone.items()}
        for loop, by_zone in topology.loop_inlet_nodes.items()
    }
    fans: list[FanSeries] = []
    for fan in fan_names:
        loop = fan_loop.get(fan.casefold(), "")
        served = topology.served.get(loop, ())
        fans.append(
            FanSeries(
                name=fan,
                energy=get(_ENERGY_VARIABLE, fan),
                mass_flow=get(_FLOW_VARIABLE, fan),
                zone=None if served else fan_zone.get(fan.casefold()),
                loop_zones=served,
                loop_inlet_flow=loop_flows.get(loop) if served else None,
            )
        )
    return BuildingFans(
        fans=tuple(fans),
        inlet_flow={name: flow(nodes) for name, nodes in adu_nodes.items()},
        multipliers={zone.zone.name: zone.zone.multiplier for zone in zones},
        floor_area={zone.zone.name: zone.zone.floor_area for zone in zones},
        delivered={
            "heating": {zone.zone.name: get(HEATING_VARIABLE, zone.zone.name) for zone in zones},
            "cooling": {zone.zone.name: get(COOLING_VARIABLE, zone.zone.name) for zone in zones},
        },
        outdoor_air={zone.zone.name: zone.zone.outdoor_air for zone in zones},
        air_density=standard_air_density(_elevation(doc, results)),
    )


def fans_hook(sources: SourceData, zones: Sequence[ClassifiedZone]) -> FanAttribution:
    """Build the `fans` hook of a building: `attribute_fans(building_fans(...))`.

    Args:
        sources: The checked model and results.
        zones: The classified zones.

    Returns:
        The attribution, callable as a `ZoneHook`.
    """
    return attribute_fans(building_fans(sources, zones))


def ledger_fields(zone: ClassifiedZone, schedules: ScheduleEvaluator) -> dict[str, object]:
    """Refuse: air-loop fans are split by building-wide node flows a single zone does not carry.

    Raises:
        ValueError: Always; pass `fans_hook(sources, zones)` to
            `GroupLedger.from_zone(..., hooks=[...])` instead.
    """
    del zone, schedules
    msg = (
        "fans needs building-wide fan and node flows: build the hook with fans_hook(sources, zones) "
        "and pass it to GroupLedger.from_zone(..., hooks=[...])"
    )
    raise ValueError(msg)
