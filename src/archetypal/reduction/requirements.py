"""The simulation results reduction needs (spec 002, FR-002, research R2).

`RESULTS_REQUIREMENTS` is the single source for the outputs reduction reads: error messages,
the outputs the single run adds (`reduce(..., simulate=True)`) and
`contracts/results-requirements.md` all come from it, and a unit test checks that the
constant and the contract's table agree.

Whether an item applies, and which keys it needs, depends on the model: a model without
`WaterUse:Equipment` needs no hot-water outputs. The model side is summarised in
`ModelFacts`, which the source loader (`sources.py`) builds from the document, with the
metered fuels read from the results' End Uses table.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

if TYPE_CHECKING:
    from collections.abc import Callable

    from idfkit.simulation import SQLResult

__all__ = [
    "BASEBOARD_VARIABLE",
    "COOLING_COIL_VARIABLE",
    "HEATING_COIL_VARIABLE",
    "IDEAL_COOLING_VARIABLE",
    "IDEAL_HEATING_VARIABLE",
    "RADIANT_COOLING_VARIABLE",
    "RADIANT_HEATING_VARIABLE",
    "RESULTS_REQUIREMENTS",
    "ModelFacts",
    "ResultRequirement",
    "check_results",
    "delivery_outputs",
]

FUEL = "<fuel>"
"""The placeholder for a fuel in a meter's name (`Heating:<fuel>`)."""

IDEAL_HEATING_VARIABLE = "Zone Ideal Loads Supply Air Total Heating Energy"
IDEAL_COOLING_VARIABLE = "Zone Ideal Loads Supply Air Total Cooling Energy"
HEATING_COIL_VARIABLE = "Heating Coil Heating Energy"
COOLING_COIL_VARIABLE = "Cooling Coil Total Cooling Energy"
BASEBOARD_VARIABLE = "Baseboard Total Heating Energy"
RADIANT_HEATING_VARIABLE = "Zone Radiant HVAC Heating Energy"
RADIANT_COOLING_VARIABLE = "Zone Radiant HVAC Cooling Energy"


def delivery_outputs(object_type: str) -> tuple[tuple[Literal["heating", "cooling"], str], ...]:
    """The outputs that report the energy an HVAC object delivers, by mode (research R12).

    Heating and cooling coils (air-loop, terminal and zone-equipment coils alike), ideal loads
    (supply air total, outdoor air and latent load included), baseboards and low-temperature
    radiant systems. Coil performance sub-objects (`Coil:Cooling:DX:CurveFit:*`) and
    thermal-storage coils are not coils that report these outputs.

    Args:
        object_type: The EnergyPlus object type, in any case.

    Returns:
        (mode, variable) pairs; empty for an object that delivers nothing reduction measures.
    """
    t = object_type.casefold()
    outputs: tuple[tuple[Literal["heating", "cooling"], str], ...] = ()
    if t == "zonehvac:idealloadsairsystem":
        outputs = (("heating", IDEAL_HEATING_VARIABLE), ("cooling", IDEAL_COOLING_VARIABLE))
    elif t.startswith("coil:heating:"):
        outputs = (("heating", HEATING_COIL_VARIABLE),)
    elif t.startswith("coil:cooling:") and not t.startswith("coil:cooling:dx:curvefit:") and "thermalstorage" not in t:
        outputs = (("cooling", COOLING_COIL_VARIABLE),)
    elif t.startswith("zonehvac:baseboard:"):
        outputs = (("heating", BASEBOARD_VARIABLE),)
    elif t.startswith("zonehvac:lowtemperatureradiant:") and not t.endswith(":design"):
        outputs = (("heating", RADIANT_HEATING_VARIABLE),)
        if not t.endswith(":electric"):
            outputs = (("heating", RADIANT_HEATING_VARIABLE), ("cooling", RADIANT_COOLING_VARIABLE))
    return outputs


@dataclass(frozen=True)
class ModelFacts:
    """What a model contains that decides which results it needs.

    Names are compared with results case-insensitively, as EnergyPlus upper-cases key values.

    Attributes:
        zones: Every zone's name.
        fans: Every fan's name.
        pumps: Every pump's name.
        zone_air_inlet_nodes: Every zone air inlet node's name (nodes of node lists included).
        served_zones: The zones with HVAC equipment connections (`ZoneHVAC:EquipmentConnections`),
            or `None` for every zone. EnergyPlus reports mechanical ventilation only for these:
            a zone without equipment connections (an attic, a basement, a return plenum) has none.
        water_use_equipment: Every `WaterUse:Equipment`'s name.
        end_use_fuels: The (end use, fuel) pairs the model meters, with EnergyPlus's meter
            spelling: `("Heating", "NaturalGas")` stands for the meter `Heating:NaturalGas`.
            End uses are `Heating`, `Cooling`, `HeatRejection` and `WaterSystems`.
        hvac_outputs: (variable, object name) pairs reporting the energy each HVAC object
            delivers (`delivery_outputs`), in model order.
    """

    zones: tuple[str, ...] = ()
    fans: tuple[str, ...] = ()
    pumps: tuple[str, ...] = ()
    zone_air_inlet_nodes: tuple[str, ...] = ()
    served_zones: tuple[str, ...] | None = None
    water_use_equipment: tuple[str, ...] = ()
    end_use_fuels: tuple[tuple[str, str], ...] = ()
    hvac_outputs: tuple[tuple[str, str], ...] = ()

    def fuels(self, end_use: str) -> tuple[str, ...]:
        """Return the fuels metered for an end use, sorted and without duplicates.

        Args:
            end_use: `Heating`, `Cooling`, `HeatRejection` or `WaterSystems`.

        Returns:
            The fuels, in EnergyPlus's meter spelling.
        """
        return tuple(sorted({fuel for use, fuel in self.end_use_fuels if use == end_use}))


@dataclass(frozen=True)
class ResultRequirement:
    """One output variable or meter that reduction reads.

    Attributes:
        item: The variable's name, or the meter's name (`Heating:<fuel>` for one meter per fuel).
        kind: `"variable"` (`Output:Variable`) or `"meter"` (`Output:Meter`).
        key: Which keys are needed, as the contract's table says it (`every zone`, `Environment`,
            `—` for a meter).
        frequency: The reporting frequency needed.
        used_for: What reduction uses it for, with the requirement it serves.
        expected: The keys (for a variable) or meter names (for a meter) the model needs
            reported. An empty tuple means the item does not apply to the model.
    """

    item: str
    kind: Literal["variable", "meter"]
    key: str
    frequency: Literal["Hourly"]
    used_for: str
    expected: Callable[[ModelFacts], tuple[str, ...]]

    @property
    def idf_text(self) -> str:
        """The output object that requests the item, in IDF syntax.

        A variable is requested for every key (`*`). A meter per fuel keeps the `<fuel>`
        placeholder; `idf_objects` names the model's fuels.
        """
        if self.kind == "variable":
            return f"Output:Variable,*,{self.item},{self.frequency};"
        return f"Output:Meter,{self.item},{self.frequency};"

    def applies_to(self, facts: ModelFacts) -> bool:
        """Whether the model needs this item at all.

        Args:
            facts: The model's facts.

        Returns:
            `False` when the model has nothing this item reports on.
        """
        return bool(self.expected(facts))

    def idf_objects(self, facts: ModelFacts) -> tuple[str, ...]:
        """The output objects to add to the model for this item, in IDF syntax.

        Args:
            facts: The model's facts.

        Returns:
            One object for a variable; one per meter name for a meter.
        """
        if self.kind == "variable":
            return (self.idf_text,)
        return tuple(f"Output:Meter,{name},{self.frequency};" for name in self.expected(facts))


def _always_environment(_facts: ModelFacts) -> tuple[str, ...]:
    return ("Environment",)


def _zones(facts: ModelFacts) -> tuple[str, ...]:
    return facts.zones


def _served_zones(facts: ModelFacts) -> tuple[str, ...]:
    return facts.zones if facts.served_zones is None else facts.served_zones


def _fans(facts: ModelFacts) -> tuple[str, ...]:
    return facts.fans


def _inlet_nodes(facts: ModelFacts) -> tuple[str, ...]:
    return facts.zone_air_inlet_nodes


def _water_use(facts: ModelFacts) -> tuple[str, ...]:
    return facts.water_use_equipment


def _environment_if_water_use(facts: ModelFacts) -> tuple[str, ...]:
    return ("Environment",) if facts.water_use_equipment else ()


def _fuel_meters(end_use: str) -> Callable[[ModelFacts], tuple[str, ...]]:
    def expected(facts: ModelFacts) -> tuple[str, ...]:
        return tuple(f"{end_use}:{fuel}" for fuel in facts.fuels(end_use))

    return expected


def _meter_if(name: str, present: Callable[[ModelFacts], tuple[str, ...]]) -> Callable[[ModelFacts], tuple[str, ...]]:
    def expected(facts: ModelFacts) -> tuple[str, ...]:
        return (name,) if present(facts) else ()

    return expected


def _pumps(facts: ModelFacts) -> tuple[str, ...]:
    return facts.pumps


def _delivering(variable: str) -> Callable[[ModelFacts], tuple[str, ...]]:
    def expected(facts: ModelFacts) -> tuple[str, ...]:
        return tuple(dict.fromkeys(name for item, name in facts.hvac_outputs if item == variable))

    return expected


def _variable(
    item: str, key: str, used_for: str, expected: Callable[[ModelFacts], tuple[str, ...]]
) -> ResultRequirement:
    return ResultRequirement(item, "variable", key, "Hourly", used_for, expected)


def _meter(item: str, expected: Callable[[ModelFacts], tuple[str, ...]]) -> ResultRequirement:
    return ResultRequirement(item, "meter", "—", "Hourly", "consumed energy (FR-022), peaks (FR-027)", expected)


_DELIVERED = "energy delivered by HVAC equipment (FR-022)"
_SUPPLY = "supply-air temperature limits (FR-022a), hourly mode of pumps in the comparison (R13)"

RESULTS_REQUIREMENTS: tuple[ResultRequirement, ...] = (
    _variable("Zone Air System Sensible Heating Energy", "every zone", _SUPPLY, _zones),
    _variable("Zone Air System Sensible Cooling Energy", "every zone", _SUPPLY, _zones),
    _variable(
        IDEAL_HEATING_VARIABLE, "every ZoneHVAC:IdealLoadsAirSystem", _DELIVERED, _delivering(IDEAL_HEATING_VARIABLE)
    ),
    _variable(
        IDEAL_COOLING_VARIABLE, "every ZoneHVAC:IdealLoadsAirSystem", _DELIVERED, _delivering(IDEAL_COOLING_VARIABLE)
    ),
    _variable(HEATING_COIL_VARIABLE, "every heating coil", _DELIVERED, _delivering(HEATING_COIL_VARIABLE)),
    _variable(COOLING_COIL_VARIABLE, "every cooling coil", _DELIVERED, _delivering(COOLING_COIL_VARIABLE)),
    _variable(BASEBOARD_VARIABLE, "every ZoneHVAC:Baseboard:*", _DELIVERED, _delivering(BASEBOARD_VARIABLE)),
    _variable(
        RADIANT_HEATING_VARIABLE,
        "every ZoneHVAC:LowTemperatureRadiant:*",
        _DELIVERED,
        _delivering(RADIANT_HEATING_VARIABLE),
    ),
    _variable(
        RADIANT_COOLING_VARIABLE,
        "every hydronic ZoneHVAC:LowTemperatureRadiant:*",
        _DELIVERED,
        _delivering(RADIANT_COOLING_VARIABLE),
    ),
    _variable("Fan Electricity Energy", "every fan", "fan energy and air volume (FR-022a)", _fans),
    _variable("Fan Air Mass Flow Rate", "every fan", "fan energy and air volume (FR-022a)", _fans),
    _variable(
        "System Node Mass Flow Rate",
        "each zone's air inlet nodes",
        "attributing air-loop fans to zones (FR-022a)",
        _inlet_nodes,
    ),
    _variable(
        "Site Outdoor Air Drybulb Temperature",
        "Environment",
        "efficiency's dependence on outdoor temperature (FR-022)",
        _always_environment,
    ),
    _variable(
        "Zone Mechanical Ventilation Standard Density Volume Flow Rate",
        "every zone",
        "outdoor air (FR-019)",
        _served_zones,
    ),
    _variable("Site Mains Water Temperature", "Environment", "hot water (FR-021)", _environment_if_water_use),
    _variable("Water Use Equipment Hot Water Volume", "every WaterUse:Equipment", "hot water (FR-021)", _water_use),
    _meter(f"Heating:{FUEL}", _fuel_meters("Heating")),
    _meter(f"Cooling:{FUEL}", _fuel_meters("Cooling")),
    _meter("Fans:Electricity", _meter_if("Fans:Electricity", _fans)),
    _meter("Pumps:Electricity", _meter_if("Pumps:Electricity", _pumps)),
    _meter(f"HeatRejection:{FUEL}", _fuel_meters("HeatRejection")),
    _meter(f"WaterSystems:{FUEL}", _fuel_meters("WaterSystems")),
)
"""Every output reduction reads, in the order of `contracts/results-requirements.md`."""


def check_results(results: SQLResult, facts: ModelFacts) -> tuple[ResultRequirement, ...]:
    """Return the requirements the results do not meet, in `RESULTS_REQUIREMENTS` order.

    An item is met when every key (or meter name) the model needs is reported at the
    required frequency. Items that do not apply to the model are never returned. Names and
    keys are compared case-insensitively.

    Args:
        results: The results of the detailed model's annual run.
        facts: What the model contains.

    Returns:
        The missing items; an empty tuple when the results are complete.
    """
    variables: set[tuple[str, str, str]] = set()
    meters: set[tuple[str, str]] = set()
    for info in results.list_variables():
        if info.is_meter:
            meters.add((info.name.casefold(), info.frequency))
        else:
            variables.add((info.name.casefold(), info.key_value.casefold(), info.frequency))

    missing: list[ResultRequirement] = []
    for requirement in RESULTS_REQUIREMENTS:
        expected = requirement.expected(facts)
        if requirement.kind == "variable":
            name = requirement.item.casefold()
            met = all((name, key.casefold(), requirement.frequency) in variables for key in expected)
        else:
            met = all((meter.casefold(), requirement.frequency) in meters for meter in expected)
        if not met:
            missing.append(requirement)
    return tuple(missing)
