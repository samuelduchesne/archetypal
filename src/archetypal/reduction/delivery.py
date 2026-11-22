"""Energy delivered by HVAC equipment to each zone, hour by hour (spec 002, FR-022, research R12).

Delivered energy is what the zone's HVAC equipment hands to the air or the room, not the zone
air's sensible load: it includes the outdoor-air load and, for cooling, the latent load, which
the archetype's ideal loads also meet (they condition their outdoor air). Each object's output
comes from `requirements.delivery_outputs`:

- **zone equipment** in the zone's `ZoneHVAC:EquipmentList` delivers to that zone: ideal loads
  (`Zone Ideal Loads Supply Air Total Heating/Cooling Energy`), baseboards, low-temperature
  radiant systems, and every coil found inside a unit (PTAC, PTHP, fan coil, unit heater,
  zone unitary system, ...) or inside an air distribution unit's terminal (reheat coils);
- **air-loop coils** (on the loop's branches, in its outdoor air system, inside a unitary system
  or coil system on a branch) are split between the zones the loop serves, each hour in
  proportion to the mass flow through each zone's air-distribution-unit inlet nodes, as the
  `fans` module splits a loop's fans (`fans.air_loops`, `fans.loop_shares`).

Heat recovery is not a delivery: it lowers the coils' load, so the efficiency it brings shows
in the coils' smaller delivery. Equipment of no other kind (evaporative coolers, beams, cooling
panels, high-temperature radiant heaters, ventilated slabs) is not measured; its names are in
`Delivery.unmeasured`.

EnergyPlus reports equipment outputs for **every copy** of a multiplied zone (the equipment
meets the load of all copies), so they are divided by the zone's multiplier here: profiles are
per copy, as everywhere in the ledger.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

import numpy as np

from archetypal.reduction.efficiency import read_hourly
from archetypal.reduction.fans import air_loops, loop_shares
from archetypal.reduction.requirements import delivery_outputs

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable, Iterator, Mapping

    import numpy.typing as npt
    from idfkit.versioned import IDFDocumentSince22_1

    from archetypal.reduction.fans import AirLoops
    from archetypal.reduction.schedules import Profile
    from archetypal.reduction.sources import SourceData

__all__ = ["Delivery", "EquipmentOutputs", "Output", "delivered_energy", "delivery_requests", "equipment_outputs"]

AirMode = Literal["heating", "cooling"]
Output = tuple[AirMode, str, str]
"""(mode, variable, object name) of one delivery output."""

_NODE_VARIABLE = "System Node Mass Flow Rate"
# Objects whose fields name the coils they hold, as (object type, name) pairs.
_CONTAINERS = ("zonehvac:", "airterminal:", "airloophvac:unitary", "coilsystem:", "airloophvac:outdoorairsystem")
_UNMEASURED = (
    "zonehvac:evaporativecoolerunit",
    "zonehvac:hightemperatureradiant",
    "zonehvac:ventilatedslab",
    "zonehvac:coolingpanel:",
    "airterminal:singleduct:constantvolume:cooledbeam",
    "airterminal:singleduct:constantvolume:fourpipebeam",
)


@dataclass(frozen=True)
class EquipmentOutputs:
    """Where each delivery output goes.

    Attributes:
        zones: The outputs of each zone's own equipment, by case-folded zone name.
        loops: The outputs of each air loop's coils, by case-folded loop name.
        unmeasured: Zone equipment that conditions but reports no delivery reduction reads.
    """

    zones: Mapping[str, tuple[Output, ...]]
    loops: Mapping[str, tuple[Output, ...]]
    unmeasured: tuple[str, ...] = ()


@dataclass(frozen=True)
class Delivery:
    """Energy delivered to each zone by its HVAC equipment.

    Attributes:
        zones: Delivered energy each hour for one copy, J, by mode and zone name.
        unassigned: Air loops whose coils deliver energy but serve no zone, by name.
        unmeasured: Zone equipment whose delivery is not measured (`EquipmentOutputs`).
    """

    zones: Mapping[AirMode, Mapping[str, Profile]]
    unassigned: tuple[str, ...] = ()
    unmeasured: tuple[str, ...] = ()

    def annual(self, name: str) -> dict[AirMode, float]:
        """The run-period heating and cooling delivered to one copy of zone `name`, J."""
        return {mode: float(np.sum(self.zones[mode][name])) for mode in ("heating", "cooling")}


class _Walker:
    """Follows (object type, name) references from a starting object to the outputs it holds."""

    def __init__(self, doc: IDFDocumentSince22_1) -> None:
        self.types = {obj.obj_type.casefold() for obj in doc.all_objects}
        self.objects = {
            (obj.obj_type.casefold(), obj.name.casefold()): obj
            for obj in doc.all_objects
            if obj.obj_type.casefold().startswith(_CONTAINERS)
        }
        self.unmeasured: list[str] = []

    def outputs(self, object_type: str, name: str, seen: set[tuple[str, str]] | None = None) -> Iterator[Output]:
        key = (object_type.casefold(), name.casefold())
        seen = set() if seen is None else seen
        if key in seen:
            return
        seen.add(key)
        direct = delivery_outputs(object_type)
        if direct:
            for mode, variable in direct:
                output: Output = (mode, variable, name)
                yield output
            return
        if key[0].startswith(_UNMEASURED):
            self.unmeasured.append(name)
            return
        obj = self.objects.get(key)
        if obj is None:
            return
        values = [value for value in obj.fieldvalues[2:] if isinstance(value, str)]
        if key[0] == "airloophvac:outdoorairsystem":
            # The equipment list is named without its type.
            equipment = obj.outdoor_air_equipment_list_name
            yield from self.outputs("AirLoopHVAC:OutdoorAirSystem:EquipmentList", equipment or "", seen)
            return
        for first, second in itertools.pairwise(values):
            if first.casefold() in self.types and first.casefold() != key[0]:
                yield from self.outputs(first, second, seen)


def equipment_outputs(doc: IDFDocumentSince22_1) -> EquipmentOutputs:
    """Find the delivery outputs of each zone's equipment and of each air loop's coils.

    Args:
        doc: The model.

    Returns:
        The outputs by zone and by loop.
    """
    walker = _Walker(doc)
    lists = {item.name.casefold(): item for item in doc["ZoneHVAC:EquipmentList"]}
    zones: dict[str, tuple[Output, ...]] = {}
    for connections in doc["ZoneHVAC:EquipmentConnections"]:
        equipment_list = lists.get(connections.zone_conditioning_equipment_list_name.casefold())
        if equipment_list is None:
            continue
        found: list[Output] = []
        for entry in equipment_list.equipment:
            found += walker.outputs(entry.zone_equipment_object_type, entry.zone_equipment_name)
        zones[connections.zone_name.casefold()] = tuple(dict.fromkeys(found))
    branch_lists = {item.name.casefold(): item for item in doc["BranchList"]}
    branches = {item.name.casefold(): item for item in doc["Branch"]}
    loops: dict[str, tuple[Output, ...]] = {}
    for loop in doc["AirLoopHVAC"]:
        found = []
        branch_list = branch_lists.get(loop.branch_list_name.casefold())
        for item in branch_list.branches if branch_list is not None else ():
            branch = branches.get(item.branch_name.casefold())
            for component in branch.components if branch is not None else ():
                found += walker.outputs(component.component_object_type, component.component_name)
        loops[loop.name.casefold()] = tuple(dict.fromkeys(found))
    return EquipmentOutputs(zones=zones, loops=loops, unmeasured=tuple(dict.fromkeys(walker.unmeasured)))


def _split(
    totals: dict[AirMode, dict[str, Profile]],
    found: tuple[Output, ...],
    shares: npt.NDArray[np.float64],
    served: tuple[str, ...],
    get: Callable[[str, str], Profile],
) -> None:
    """Add an air loop's coils to the zones it serves, each by its hourly share."""
    for mode, variable, key in found:
        energy = get(variable, key)
        for i, name in enumerate(served):
            totals[mode][name] += shares[i] * energy


def delivery_requests(doc: IDFDocumentSince22_1, zone_names: Iterable[str]) -> list[tuple[str, str]]:
    """The hourly series `delivered_energy` reads for the zones `zone_names` (model spelling)."""
    return _requests(equipment_outputs(doc), air_loops(doc, zone_names))


def _requests(outputs: EquipmentOutputs, topology: AirLoops) -> list[tuple[str, str]]:
    requests = [(variable, key) for found in outputs.zones.values() for _, variable, key in found]
    requests += [(variable, key) for found in outputs.loops.values() for _, variable, key in found]
    requests += [(_NODE_VARIABLE, node) for nodes in topology.inlet_nodes.values() for node in nodes]
    return requests


def delivered_energy(
    sources: SourceData, multipliers: Mapping[str, int], floor_area: Mapping[str, float] | None = None
) -> Delivery:
    """Read the energy each zone's HVAC equipment delivered, hour by hour, for one copy.

    Args:
        sources: The checked model and results.
        multipliers: Each zone's multiplier, by zone name (model spelling); only these zones
            receive delivery.
        floor_area: Each zone's floor area (one copy), m², to split an air loop's coils in
            hours without any inlet flow when no zone has inlet flow all year.

    Returns:
        The delivery per copy, zeros for zones without equipment.
    """
    doc = sources.model
    names = {name.casefold(): name for name in multipliers}
    outputs = equipment_outputs(doc)
    topology = air_loops(doc, names.values())
    series = read_hourly(sources.results, _requests(outputs, topology))
    hours = next((len(profile) for profile in series.values()), sources.run_period.calendar.hours)
    zeros = np.zeros(hours)

    def get(variable: str, key: str) -> Profile:
        return series.get((variable.upper(), key.upper()), zeros)

    totals: dict[AirMode, dict[str, Profile]] = {
        mode: {name: np.zeros(hours) for name in multipliers} for mode in ("heating", "cooling")
    }
    for zone_key, found in outputs.zones.items():
        name = names.get(zone_key)
        if name is None:
            continue
        for mode, variable, key in found:
            totals[mode][name] += get(variable, key)
    inlet_flow = {
        name: sum((get(_NODE_VARIABLE, node) for node in nodes), zeros) for name, nodes in topology.inlet_nodes.items()
    }
    weights = {name: multipliers[name] * (floor_area or {}).get(name, 1.0) for name in multipliers}
    unassigned: list[str] = []
    for loop in doc["AirLoopHVAC"]:
        found = outputs.loops.get(loop.name.casefold(), ())
        served = topology.served.get(loop.name.casefold(), ())
        if found and not served:
            unassigned.append(loop.name)
        elif found:
            _split(totals, found, loop_shares(inlet_flow, weights, served, hours), served, get)
    for mode_totals in totals.values():
        for name in mode_totals:
            mode_totals[name] /= multipliers[name]
    return Delivery(zones=totals, unassigned=tuple(unassigned), unmeasured=outputs.unmeasured)
