"""Infiltration and mechanical outdoor air of a zone, for the group ledger (spec 002, R9, FR-018, FR-019).

Infiltration
------------
`infiltration_totals` sums a zone's `NominalInfiltration` rows (inventory's `AirflowRecord`s):
the design flow, its hourly profile (design flow · schedule, R5; a row without a schedule is
always on), and the design-flow-weighted sums of the four coefficients of EnergyPlus's
`design_flow · schedule · (A + B·|ΔT| + C·v + D·v²)`. SBEM's `InfiltrationComponent` then
carries the annual-mean flow with the flow-weighted mean coefficients; the profile and the
spread of the coefficients are named in the report as not represented (R9).

Outdoor air
-----------
`outdoor_air_totals` takes the zone's hourly mechanical outdoor air from the results (`Zone
Mechanical Ventilation Standard Density Volume Flow Rate`, which inventory has already divided
by the zone's multiplier), so DCV, economiser and minimum-outdoor-air control are captured as
EnergyPlus ran them (R2). `design_flow` is the zone's design outdoor air from its
`DesignSpecification:OutdoorAir` (per area · floor area + per person · installed people).

Heat recovery and economiser are SBEM categories (`HRV`: `NoHRV`, `Sensible`, `Enthalpy`;
`Economizer`: `NoEconomizer`, `DifferentialDryBulb`, `DifferentialEnthalpy`). Each zone adds its
annual outdoor-air volume (m³) to the category that serves it, in `hrv_weighted` and
`economiser_weighted`, and volume · sensible effectiveness to `effectiveness_weighted`. The
group takes the category with the largest volume, and the airflow-weighted effectiveness is
`effectiveness_weighted / Σ volume with heat recovery` (R9, FR-019).

Where the categories come from (R9, R18)
-----------------------------------------
`outdoor_air_controls(doc)` reads the model through idfkit's typed accessors and literal keys:

- an `AirLoopHVAC` serves the zones whose return nodes its `AirLoopHVAC:ReturnPath` collects
  (through `AirLoopHVAC:ZoneMixer` and `AirLoopHVAC:ReturnPlenum`), and the zones its
  `AirLoopHVAC:SupplyPath` feeds (through `AirLoopHVAC:ZoneSplitter` and
  `AirLoopHVAC:SupplyPlenum`) directly or through the air terminal of a
  `ZoneHVAC:AirDistributionUnit` (single-duct VAV and constant-volume terminals);
- its `AirLoopHVAC:OutdoorAirSystem`, found on its branches, gives the heat exchanger
  (`HeatExchanger:AirToAir:SensibleAndLatent`, `HeatExchanger:AirToAir:FlatPlate`,
  `HeatExchanger:Desiccant:BalancedFlow`) in its equipment list and the `Controller:OutdoorAir`
  in its controller list;
- a `ZoneHVAC:IdealLoadsAirSystem` in a zone's equipment list gives its own heat recovery and
  economiser types, and takes precedence over an air loop.

A zone served by neither gets `NO_CONTROL` (`NoHRV`, `NoEconomizer`). EnergyPlus economiser
types map to SBEM's two by what they compare: dry-bulb types (`FixedDryBulb`,
`FixedDewPointAndDryBulb`) to `DifferentialDryBulb`, enthalpy types (`FixedEnthalpy`,
`ElectronicEnthalpy`, `DifferentialDryBulbAndEnthalpy`) to `DifferentialEnthalpy`. A sensible
and latent heat exchanger is `Enthalpy` when either latent effectiveness is above 0, else
`Sensible`, with its sensible effectiveness at 100 % heating airflow. A flat-plate or desiccant
exchanger has no effectiveness field; its effectiveness is unknown (`None`) and counts as 0 in
`effectiveness_weighted`, which the report names.

The hook
--------
`ledger_fields(zone, schedules)` reads the controls from `schedules.doc` (memoised for the
last model), so the default hook is complete. `AirflowHook.from_model(doc)` builds the same hook
explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, TypedDict

import numpy as np

from archetypal.reduction.ledger import AirflowTotals, OutdoorAirTotals, schedule_design_days
from archetypal.reduction.schedules import design_day_evaluators

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from idfkit.versioned import IDFDocumentSince22_1

    from archetypal.reduction.classify import ClassifiedZone
    from archetypal.reduction.schedules import Profile, ScheduleEvaluator

__all__ = [
    "NO_CONTROL",
    "AirflowFields",
    "AirflowHook",
    "EconomiserCategory",
    "HRVCategory",
    "OutdoorAirControl",
    "air_loop_zones",
    "economiser_category",
    "infiltration_totals",
    "ledger_fields",
    "outdoor_air_controls",
    "outdoor_air_totals",
]

HRVCategory = Literal["NoHRV", "Sensible", "Enthalpy"]
"""SBEM's heat-recovery categories (epinterface `HRVMethod`)."""

EconomiserCategory = Literal["NoEconomizer", "DifferentialDryBulb", "DifferentialEnthalpy"]
"""SBEM's economiser categories (epinterface `EconomizerMethod`)."""

_SECONDS_PER_HOUR = 3600.0

_ECONOMISERS: dict[str, EconomiserCategory] = {
    "nodeconomizer": "NoEconomizer",
    "noeconomizer": "NoEconomizer",
    "differentialdrybulb": "DifferentialDryBulb",
    "fixeddrybulb": "DifferentialDryBulb",
    "fixeddewpointanddrybulb": "DifferentialDryBulb",
    "differentialenthalpy": "DifferentialEnthalpy",
    "differentialdrybulbandenthalpy": "DifferentialEnthalpy",
    "fixedenthalpy": "DifferentialEnthalpy",
    "electronicenthalpy": "DifferentialEnthalpy",
}

# EnergyPlus's defaults for ZoneHVAC:IdealLoadsAirSystem heat recovery effectiveness.
_IDEAL_SENSIBLE_DEFAULT = 0.7


@dataclass(frozen=True)
class OutdoorAirControl:
    """The heat recovery and economiser serving a zone's outdoor air.

    Attributes:
        hrv: SBEM heat-recovery category.
        economiser: SBEM economiser category.
        effectiveness: Sensible heat-recovery effectiveness; 0 without heat recovery, `None`
            when the exchanger has no effectiveness field.
        source: The air loop or ideal-loads system it comes from, or `None`.
    """

    hrv: HRVCategory = "NoHRV"
    economiser: EconomiserCategory = "NoEconomizer"
    effectiveness: float | None = 0.0
    source: str | None = None


NO_CONTROL = OutdoorAirControl()
"""Neither heat recovery nor economiser."""


def economiser_category(control_type: str | None) -> EconomiserCategory:
    """Map an EnergyPlus economiser control type to SBEM's category.

    Args:
        control_type: `Controller:OutdoorAir`'s `Economizer Control Type`, or `None`.

    Returns:
        The SBEM category.
    """
    if not control_type:
        return "NoEconomizer"
    return _ECONOMISERS.get(control_type.casefold(), "NoEconomizer")


# --- Infiltration ---------------------------------------------------------------------------------


def _hours(schedules: object, zone: ClassifiedZone) -> int | None:
    calendar = getattr(schedules, "calendar", None)
    hours = getattr(calendar, "hours", None)
    if isinstance(hours, int):
        return hours
    size = int(np.asarray(zone.zone.outdoor_air).size)
    return size or None


def infiltration_totals(zone: ClassifiedZone, evaluate: Callable[[str], Profile]) -> AirflowTotals:
    """Return the infiltration totals of one copy of `zone` (FR-018).

    Args:
        zone: The classified zone; its record's `infiltration` is read.
        evaluate: Returns a schedule's hourly profile by name. For rows without a schedule its
            `calendar.hours` (or the length of the zone's outdoor-air profile) gives the length.

    Returns:
        The design flow, hourly flow, design days (when `evaluate` is a `ScheduleEvaluator`)
        and flow-weighted coefficient sums; zero without infiltration.

    Raises:
        ValueError: If a row has no schedule and the run period's length is unknown.
    """
    design = design_day_evaluators(evaluate)
    totals = AirflowTotals()
    for record in zone.zone.infiltration:
        if record.schedule is None:
            hours = _hours(evaluate, zone)
            if hours is None:
                msg = f"infiltration {record.name!r} has no schedule and the run period's length is unknown"
                raise ValueError(msg)
            fraction = np.ones(hours, dtype=np.float64)
        else:
            fraction = np.asarray(evaluate(record.schedule), dtype=np.float64)
        flow = record.design_flow
        totals = totals + AirflowTotals(
            design_flow=flow,
            hourly=flow * fraction,
            constant_weighted=flow * record.constant,
            temperature_weighted=flow * record.temperature,
            velocity_weighted=flow * record.velocity,
            velocity_squared_weighted=flow * record.velocity_squared,
            design_days=schedule_design_days(design, record.schedule, flow),
        )
    return totals


# --- Outdoor air ----------------------------------------------------------------------------------


def outdoor_air_totals(zone: ClassifiedZone, control: OutdoorAirControl) -> OutdoorAirTotals:
    """Return the outdoor-air totals of one copy of `zone` (FR-019).

    Args:
        zone: The classified zone; its record's `outdoor_air` (m³/s per hour, one copy) is read.
        control: The heat recovery and economiser serving it.

    Returns:
        The design and hourly flow, and the annual volume by category.
    """
    record = zone.zone
    hourly = np.asarray(record.outdoor_air, dtype=np.float64)
    people = sum(gain.design_level for gain in record.gains if gain.kind == "people")
    design = record.outdoor_air_per_area * record.floor_area + record.outdoor_air_per_person * people
    volume = float(hourly.sum()) * _SECONDS_PER_HOUR
    hrv: dict[str, float] = {}
    economiser: dict[str, float] = {}
    effectiveness = 0.0
    if volume != 0.0:
        hrv[control.hrv] = volume
        economiser[control.economiser] = volume
        if control.hrv != "NoHRV" and control.effectiveness is not None:
            effectiveness = volume * control.effectiveness
    return OutdoorAirTotals(
        design_flow=design,
        hourly=hourly,
        hrv_weighted=hrv,
        economiser_weighted=economiser,
        effectiveness_weighted=effectiveness,
    )


# --- Reading air loops from the model (R18) ------------------------------------------------------


def _cf(name: str | None) -> str:
    return (name or "").casefold()


def _nodes(name: str | None, node_lists: Mapping[str, tuple[str, ...]]) -> tuple[str, ...]:
    """Expand a node or `NodeList` name into case-folded node names."""
    if not name:
        return ()
    key = name.casefold()
    return node_lists.get(key, (key,))


def _terminal_inlets(doc: IDFDocumentSince22_1) -> dict[tuple[str, str], str]:
    """Air inlet node of each single-duct terminal, by (object type, name), case-folded."""
    inlets: dict[tuple[str, str], str] = {}
    for obj in doc["AirTerminal:SingleDuct:VAV:Reheat"]:
        inlets["airterminal:singleduct:vav:reheat", obj.name.casefold()] = _cf(obj.air_inlet_node_name)
    for obj in doc["AirTerminal:SingleDuct:VAV:NoReheat"]:
        inlets["airterminal:singleduct:vav:noreheat", obj.name.casefold()] = _cf(obj.air_inlet_node_name)
    for obj in doc["AirTerminal:SingleDuct:ConstantVolume:Reheat"]:
        inlets["airterminal:singleduct:constantvolume:reheat", obj.name.casefold()] = _cf(obj.air_inlet_node_name)
    for obj in doc["AirTerminal:SingleDuct:ConstantVolume:NoReheat"]:
        inlets["airterminal:singleduct:constantvolume:noreheat", obj.name.casefold()] = _cf(obj.air_inlet_node_name)
    return inlets


@dataclass(frozen=True)
class _ZoneConnections:
    zone: str
    inlets: frozenset[str]
    returns: frozenset[str]
    equipment: tuple[tuple[str, str], ...]


def _zone_connections(doc: IDFDocumentSince22_1, node_lists: Mapping[str, tuple[str, ...]]) -> list[_ZoneConnections]:
    equipment_lists = {
        item.name.casefold(): tuple(
            (_cf(group.zone_equipment_object_type), _cf(group.zone_equipment_name)) for group in item.equipment
        )
        for item in doc["ZoneHVAC:EquipmentList"]
    }
    return [
        _ZoneConnections(
            zone=conn.zone_name.casefold(),
            inlets=frozenset(_nodes(conn.zone_air_inlet_node_or_nodelist_name, node_lists)),
            returns=frozenset(_nodes(conn.zone_return_air_node_or_nodelist_name, node_lists)),
            equipment=equipment_lists.get(_cf(conn.zone_conditioning_equipment_list_name), ()),
        )
        for conn in doc["ZoneHVAC:EquipmentConnections"]
    ]


def _supply_nodes(doc: IDFDocumentSince22_1, inlet: str) -> set[str]:
    """Outlet nodes of the supply paths that start at `inlet` (splitters and supply plenums)."""
    splitters = {s.name.casefold(): s for s in doc["AirLoopHVAC:ZoneSplitter"]}
    plenums = {p.name.casefold(): p for p in doc["AirLoopHVAC:SupplyPlenum"]}
    nodes: set[str] = set()
    for path in doc["AirLoopHVAC:SupplyPath"]:
        if _cf(path.supply_air_path_inlet_node_name) != inlet:
            continue
        for component in path.components:
            name = _cf(component.component_name)
            splitter = splitters.get(name)
            if splitter is not None:
                nodes.update(_cf(group.outlet_node_name) for group in splitter.nodes)
            plenum = plenums.get(name)
            if plenum is not None:
                nodes.update(_cf(group.outlet_node_name) for group in plenum.nodes)
    return nodes


def _return_nodes(doc: IDFDocumentSince22_1, outlet: str) -> set[str]:
    """Inlet nodes of the return paths that end at `outlet` (mixers and return plenums)."""
    mixers = {m.name.casefold(): m for m in doc["AirLoopHVAC:ZoneMixer"]}
    plenums = {p.name.casefold(): p for p in doc["AirLoopHVAC:ReturnPlenum"]}
    nodes: set[str] = set()
    for path in doc["AirLoopHVAC:ReturnPath"]:
        if _cf(path.return_air_path_outlet_node_name) != outlet:
            continue
        for component in path.components:
            name = _cf(component.component_name)
            mixer = mixers.get(name)
            if mixer is not None:
                nodes.update(_cf(group.inlet_node_name) for group in mixer.nodes)
            plenum = plenums.get(name)
            if plenum is not None:
                nodes.update(_cf(group.inlet_node_name) for group in plenum.nodes)
    return nodes


def air_loop_zones(doc: IDFDocumentSince22_1) -> dict[str, frozenset[str]]:
    """Return the zones each `AirLoopHVAC` serves, by loop name (zone names case-folded).

    A zone is served when its return air reaches the loop's return path, or when the loop's
    supply path feeds one of its air inlet nodes directly or through a single-duct air terminal
    of one of its `ZoneHVAC:AirDistributionUnit`s.

    Args:
        doc: The model.

    Returns:
        Loop name (model spelling) → case-folded names of the zones it serves.
    """
    node_lists = {nl.name.casefold(): tuple(_cf(g.node_name) for g in nl.nodes) for nl in doc["NodeList"]}
    connections = _zone_connections(doc, node_lists)
    terminals = _terminal_inlets(doc)
    adus = {
        adu.name.casefold(): (_cf(adu.air_terminal_object_type), _cf(adu.air_terminal_name))
        for adu in doc["ZoneHVAC:AirDistributionUnit"]
    }
    served: dict[str, frozenset[str]] = {}
    for loop in doc["AirLoopHVAC"]:
        supply = _supply_nodes(doc, _cf(loop.demand_side_inlet_node_names))
        returns = _return_nodes(doc, _cf(loop.demand_side_outlet_node_name))
        zones: set[str] = set()
        for conn in connections:
            terminal_inlets = {
                terminals.get(adus[name], "")
                for kind, name in conn.equipment
                if kind == "zonehvac:airdistributionunit" and name in adus
            }
            if conn.returns & returns or conn.inlets & supply or (terminal_inlets - {""}) & supply:
                zones.add(conn.zone)
        served[loop.name] = frozenset(zones)
    return served


def _oa_systems(doc: IDFDocumentSince22_1, branch_list: str) -> list[str]:
    """Names (case-folded) of the outdoor-air systems on a loop's branches."""
    branch_lists = {bl.name.casefold(): bl for bl in doc["BranchList"]}
    branches = {b.name.casefold(): b for b in doc["Branch"]}
    found = branch_lists.get(branch_list)
    if found is None:
        return []
    systems: list[str] = []
    for item in found.branches:
        branch = branches.get(_cf(item.branch_name))
        if branch is None:
            continue
        systems += [
            _cf(c.component_name)
            for c in branch.components
            if _cf(c.component_object_type) == "airloophvac:outdoorairsystem"
        ]
    return systems


def _heat_exchangers(doc: IDFDocumentSince22_1) -> dict[tuple[str, str], tuple[HRVCategory, float | None]]:
    exchangers: dict[tuple[str, str], tuple[HRVCategory, float | None]] = {}
    for hx in doc["HeatExchanger:AirToAir:SensibleAndLatent"]:
        latent = max(
            hx.latent_effectiveness_at_100_heating_air_flow or 0.0,
            hx.latent_effectiveness_at_100_cooling_air_flow or 0.0,
        )
        category: HRVCategory = "Enthalpy" if latent > 0.0 else "Sensible"
        exchangers["heatexchanger:airtoair:sensibleandlatent", hx.name.casefold()] = (
            category,
            hx.sensible_effectiveness_at_100_heating_air_flow or 0.0,
        )
    for hx in doc["HeatExchanger:AirToAir:FlatPlate"]:
        exchangers["heatexchanger:airtoair:flatplate", hx.name.casefold()] = ("Sensible", None)
    for hx in doc["HeatExchanger:Desiccant:BalancedFlow"]:
        exchangers["heatexchanger:desiccant:balancedflow", hx.name.casefold()] = ("Enthalpy", None)
    return exchangers


def _equipment_components(doc: IDFDocumentSince22_1) -> dict[str, tuple[tuple[str, str], ...]]:
    lists: dict[str, tuple[tuple[str, str], ...]] = {}
    for item in doc["AirLoopHVAC:OutdoorAirSystem:EquipmentList"]:
        pairs = (
            (item.component_1_object_type, item.component_1_name),
            (item.component_2_object_type, item.component_2_name),
            (item.component_3_object_type, item.component_3_name),
            (item.component_4_object_type, item.component_4_name),
            (item.component_5_object_type, item.component_5_name),
            (item.component_6_object_type, item.component_6_name),
            (item.component_7_object_type, item.component_7_name),
            (item.component_8_object_type, item.component_8_name),
            (item.component_9_object_type, item.component_9_name),
        )
        lists[item.name.casefold()] = tuple((_cf(kind), _cf(name)) for kind, name in pairs if kind and name)
    return lists


def _outdoor_air_controllers(doc: IDFDocumentSince22_1) -> dict[str, tuple[str, ...]]:
    """`Controller:OutdoorAir` names (case-folded) of each controller list."""
    lists: dict[str, tuple[str, ...]] = {}
    for item in doc["AirLoopHVAC:ControllerList"]:
        pairs = (
            (item.controller_1_object_type, item.controller_1_name),
            (item.controller_2_object_type, item.controller_2_name),
            (item.controller_3_object_type, item.controller_3_name),
            (item.controller_4_object_type, item.controller_4_name),
            (item.controller_5_object_type, item.controller_5_name),
            (item.controller_6_object_type, item.controller_6_name),
            (item.controller_7_object_type, item.controller_7_name),
            (item.controller_8_object_type, item.controller_8_name),
        )
        lists[item.name.casefold()] = tuple(
            _cf(name) for kind, name in pairs if _cf(kind) == "controller:outdoorair" and name
        )
    return lists


def _loop_controls(doc: IDFDocumentSince22_1) -> dict[str, OutdoorAirControl]:
    """The heat recovery and economiser of each air loop's outdoor-air system, by loop name."""
    systems = {s.name.casefold(): s for s in doc["AirLoopHVAC:OutdoorAirSystem"]}
    equipment = _equipment_components(doc)
    controller_lists = _outdoor_air_controllers(doc)
    economisers = {c.name.casefold(): c.economizer_control_type for c in doc["Controller:OutdoorAir"]}
    exchangers = _heat_exchangers(doc)
    controls: dict[str, OutdoorAirControl] = {}
    for loop in doc["AirLoopHVAC"]:
        hrv: HRVCategory = "NoHRV"
        effectiveness: float | None = 0.0
        economiser: EconomiserCategory = "NoEconomizer"
        for system_name in _oa_systems(doc, _cf(loop.branch_list_name)):
            system = systems.get(system_name)
            if system is None:
                continue
            exchanger = next(
                (
                    exchangers[c]
                    for c in equipment.get(_cf(system.outdoor_air_equipment_list_name), ())
                    if c in exchangers
                ),
                None,
            )
            if exchanger is not None and hrv == "NoHRV":
                hrv, effectiveness = exchanger
            controllers = controller_lists.get(_cf(system.controller_list_name), ())
            for controller in controllers:
                category = economiser_category(economisers.get(controller))
                if category != "NoEconomizer" and economiser == "NoEconomizer":
                    economiser = category
        controls[loop.name] = OutdoorAirControl(hrv, economiser, effectiveness, loop.name)
    return controls


_IDEAL_RECOVERY: dict[str, HRVCategory] = {"none": "NoHRV", "sensible": "Sensible", "enthalpy": "Enthalpy"}


def _treatment(control: OutdoorAirControl) -> tuple[bool, bool, float]:
    """Rank an outdoor-air control by how much it treats the outdoor air."""
    return (control.hrv != "NoHRV", control.economiser != "NoEconomizer", control.effectiveness or 0.0)


def _ideal_loads_controls(doc: IDFDocumentSince22_1) -> dict[str, OutdoorAirControl]:
    controls: dict[str, OutdoorAirControl] = {}
    for system in doc["ZoneHVAC:IdealLoadsAirSystem"]:
        # EnergyPlus accepts choice keys in any case; map them to SBEM's categories.
        hrv: HRVCategory = _IDEAL_RECOVERY.get((system.heat_recovery_type or "None").casefold(), "NoHRV")
        effectiveness = 0.0
        if hrv != "NoHRV":
            sensible = system.sensible_heat_recovery_effectiveness
            effectiveness = _IDEAL_SENSIBLE_DEFAULT if sensible is None else sensible
        economiser = economiser_category(system.outdoor_air_economizer_type)
        controls[system.name.casefold()] = OutdoorAirControl(hrv, economiser, effectiveness, system.name)
    return controls


def outdoor_air_controls(doc: IDFDocumentSince22_1) -> dict[str, OutdoorAirControl]:
    """Return the heat recovery and economiser serving each zone, by case-folded zone name.

    Args:
        doc: The model.

    Returns:
        Zones served by an air loop or an ideal-loads system; other zones are absent (use
        `NO_CONTROL`).
    """
    node_lists = {nl.name.casefold(): tuple(_cf(g.node_name) for g in nl.nodes) for nl in doc["NodeList"]}
    controls: dict[str, OutdoorAirControl] = {}
    loop_controls = _loop_controls(doc)
    # A zone served by several loops takes the control with the most outdoor-air treatment
    # (heat recovery first, then an economiser, then the higher effectiveness), so the
    # result depends on the physical content of the loops, not on their names; the loop
    # name only breaks ties between equivalent controls.
    for loop, zones in sorted(air_loop_zones(doc).items()):
        candidate = loop_controls[loop]
        for zone in zones:
            current = controls.get(zone)
            if current is None or _treatment(candidate) > _treatment(current):
                controls[zone] = candidate
    ideal = _ideal_loads_controls(doc)
    for conn in _zone_connections(doc, node_lists):
        for kind, name in conn.equipment:
            if kind == "zonehvac:idealloadsairsystem" and name in ideal:
                controls[conn.zone] = ideal[name]
                break
    return controls


# --- Hooks ----------------------------------------------------------------------------------------


class AirflowFields(TypedDict):
    """The ledger fields this module fills, for one copy of a zone."""

    infiltration: AirflowTotals
    outdoor_air: OutdoorAirTotals


@dataclass(frozen=True, eq=False)
class AirflowHook:
    """The airflow domain hook with each zone's outdoor-air control.

    Attributes:
        controls: Case-folded zone name → its heat recovery and economiser.
    """

    controls: Mapping[str, OutdoorAirControl]

    @classmethod
    def from_model(cls, doc: IDFDocumentSince22_1) -> AirflowHook:
        """Build the hook from the model's air loops and ideal-loads systems.

        Args:
            doc: The model.

        Returns:
            The hook.
        """
        return cls(outdoor_air_controls(doc))

    def __call__(self, zone: ClassifiedZone, schedules: ScheduleEvaluator, /) -> AirflowFields:
        """Return `infiltration` and `outdoor_air` for one copy of `zone`."""
        control = self.controls.get(zone.zone.name.casefold(), NO_CONTROL)
        return AirflowFields(
            infiltration=infiltration_totals(zone, schedules), outdoor_air=outdoor_air_totals(zone, control)
        )


_cache: list[tuple[object, AirflowHook]] = []


def _hook_for(doc: IDFDocumentSince22_1 | None) -> AirflowHook:
    if doc is None:
        return AirflowHook({})
    if _cache and _cache[0][0] is doc:
        return _cache[0][1]
    hook = AirflowHook.from_model(doc)
    _cache[:] = [(doc, hook)]
    return hook


def ledger_fields(zone: ClassifiedZone, schedules: ScheduleEvaluator) -> AirflowFields:
    """The airflow domain hook of `GroupLedger.from_zone` (one copy, multiplier not applied).

    The outdoor-air controls are read from `schedules.doc`, memoised for the last model; an
    evaluator without a model attributes no heat recovery or economiser.

    Args:
        zone: The classified zone.
        schedules: The model's schedule evaluator.

    Returns:
        `infiltration` (`AirflowTotals`) and `outdoor_air` (`OutdoorAirTotals`).
    """
    doc: IDFDocumentSince22_1 | None = getattr(schedules, "doc", None)
    return _hook_for(doc)(zone, schedules)
