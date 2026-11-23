"""Validation of a UMI library before translation (spec 003, research R3, FR-004).

Reading resolves references first: a broken reference is a format problem, raised by
`archetypal.umi._refs.resolve` as `UmiFormatError` and never skipped. This module then finds
the completeness and range problems of every component a building template uses, each a
`Problem` with its JSON pointer, the template affected and the rule broken. A component that
no template uses is not validated: it is not translated either (it is reported as unused).

**Completeness** (rule `required-reference`, `day-values`, `year-coverage`): the references
UMI needs to build a model are not null (each layer's material, the 7 days of a week, each
year part's week, a template's `Core`, `Perimeter` and `Windows`, the 6 references of a zone
definition and the 5 of a construction set, every schedule of loads, conditioning,
ventilation, hot water and window settings, and the window settings' construction); each day
has 24 values; year parts cover 1 January to 31 December once, without gap or overlap.

**Range**: every number is finite (no `NaN` or infinity) and meets the constraint of the SBEM
field it maps to (the epinterface field's bounds, found through `CORRESPONDENCE`), the rule
modules' own checks (`range_problems`, `material_problems`) and the plausibility rules of
research R3 (a specific heat of at least 100 J/kg·K, a layer thicker than 0, fractions in
[0, 1]).

Duplicate names are not problems (research R11).
"""

from __future__ import annotations

import inspect
import math
import types
from calendar import monthrange
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING, Final, Union, cast, get_args, get_origin

from epinterface.sbem.archetype import Archetype
from epinterface.sbem.components import envelope, materials, operations, schedules, space_use, systems, zones
from epinterface.sbem.components.zones import ZoneComponent
from pydantic import BaseModel

from archetypal.errors import Problem
from archetypal.umi._format import (
    BuildingTemplate,
    DaySchedule,
    DomesticHotWaterSettings,
    FormatModel,
    GasMaterial,
    GlazingMaterial,
    MaterialLayer,
    OpaqueMaterial,
    UmiLibrary,
    WeekSchedule,
    WindowSettings,
    YearSchedule,
    YearSchedulePart,
    ZoneConditioning,
    ZoneConstructions,
    ZoneDefinition,
    ZoneLoads,
    ZoneVentilation,
)
from archetypal.umi.correspondence import CORRESPONDENCE, MappingStatus
from archetypal.umi.rules import conditioning, hotwater, loads, ventilation
from archetypal.umi.rules.materials import material_problems

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping

    from pydantic.fields import FieldInfo

__all__ = ["LibraryIndex", "template_problems", "validate"]

REQUIRED_REFERENCE: Final = "required-reference"
DAY_VALUES: Final = "day-values"
YEAR_COVERAGE: Final = "year-coverage"

_HOURS: Final = 24
_MIN_SPECIFIC_HEAT: Final = 100.0
_GASES: Final = frozenset({"AIR", "ARGON", "KRYPTON", "XENON"})

# The references of research R3's list, by class: (field name, Basilisk key).
_REQUIRED: Final[Mapping[type[FormatModel], tuple[tuple[str, str], ...]]] = {
    MaterialLayer: (("material", "Material"),),
    BuildingTemplate: (("core", "Core"), ("perimeter", "Perimeter"), ("windows", "Windows")),
    ZoneDefinition: (
        ("conditioning", "Conditioning"),
        ("constructions", "Constructions"),
        ("domestic_hot_water", "DomesticHotWater"),
        ("internal_mass_construction", "InternalMassConstruction"),
        ("loads", "Loads"),
        ("ventilation", "Ventilation"),
    ),
    ZoneConstructions: (
        ("facade", "Facade"),
        ("ground", "Ground"),
        ("partition", "Partition"),
        ("roof", "Roof"),
        ("slab", "Slab"),
    ),
    ZoneLoads: (
        ("occupancy_schedule", "OccupancySchedule"),
        ("lights_availability_schedule", "LightsAvailabilitySchedule"),
        ("equipment_availability_schedule", "EquipmentAvailabilitySchedule"),
    ),
    ZoneConditioning: (
        ("heating_schedule", "HeatingSchedule"),
        ("cooling_schedule", "CoolingSchedule"),
        ("mech_vent_schedule", "MechVentSchedule"),
    ),
    ZoneVentilation: (
        ("nat_vent_schedule", "NatVentSchedule"),
        ("scheduled_ventilation_schedule", "ScheduledVentilationSchedule"),
    ),
    DomesticHotWaterSettings: (("water_schedule", "WaterSchedule"),),
    WindowSettings: (
        ("afn_window_availability", "AfnWindowAvailability"),
        ("shading_system_availability_schedule", "ShadingSystemAvailabilitySchedule"),
        ("zone_mixing_availability_schedule", "ZoneMixingAvailabilitySchedule"),
        ("construction", "Construction"),
    ),
    YearSchedulePart: (("schedule", "Schedule"),),
}

_GLAZING_FRACTIONS: Final = (
    "solar_transmittance",
    "solar_reflectance_front",
    "solar_reflectance_back",
    "visible_transmittance",
    "visible_reflectance_front",
    "visible_reflectance_back",
    "ir_transmittance",
    "ir_emissivity_front",
    "ir_emissivity_back",
    "dirt_factor",
)


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _alias(model: type[FormatModel], name: str) -> str:
    return model.model_fields[name].alias or name


# --- The index of a library -----------------------------------------------------------------------


class LibraryIndex:
    """Where each component of a resolved library is, and which templates use it.

    A component's pointer is where the file defines it: its place in a collection
    (`/ZoneLoads/0`), or, for a component defined inline (window settings in their first
    template, layers, year parts), its place below the object that holds it.

    Args:
        library: The resolved library.
        document: The library's JSON, keys in file order, so pointers follow the file.
    """

    def __init__(self, library: UmiLibrary, document: Mapping[str, object]) -> None:
        """Index the library; see the class for the arguments."""
        self.library = library
        self._pointers: dict[int, str] = {}
        self._keep: list[FormatModel] = []
        self._by_pointer: dict[str, FormatModel] | None = None
        self._fields = {field.alias or name: name for name, field in UmiLibrary.model_fields.items()}
        self._order = [key for key in document if key in self._fields]
        self._order += [key for key in self._fields if key not in document]
        for key in self._order:
            raw = document.get(key)
            elements = cast("list[object]", raw) if isinstance(raw, list) else []
            for index, item in enumerate(cast("tuple[FormatModel, ...]", getattr(library, self._fields[key]))):
                self._define_tree(item, f"/{key}/{index}", elements[index] if index < len(elements) else None)
        self._reach: list[list[tuple[FormatModel, str]]] = []
        self._users: dict[int, list[int]] = {}
        for index, template in enumerate(library.building_templates):
            reached: list[tuple[FormatModel, str]] = []
            self._walk(template, self.pointer(template), reached, set())
            self._reach.append(reached)
            for item, _ in reached:
                self._users.setdefault(id(item), []).append(index)

    def _define(self, item: FormatModel, pointer: str) -> None:
        if id(item) not in self._pointers:
            self._pointers[id(item)] = pointer
            self._keep.append(item)

    def _define_tree(self, item: FormatModel, pointer: str, raw: object) -> None:
        """Give `item` and the objects defined inline in it their place in the file.

        `raw` is the JSON at `pointer`; an object written there as a `$ref` is defined elsewhere.
        """
        if not isinstance(raw, dict) or "$ref" in raw:
            return
        self._define(item, pointer)
        obj = cast("dict[str, object]", raw)
        for name, field in type(item).model_fields.items():
            key = field.alias or name
            value: object = getattr(item, name)
            child = obj.get(key)
            if isinstance(value, FormatModel):
                self._define_tree(value, f"{pointer}/{_escape(key)}", child)
            elif isinstance(value, tuple) and isinstance(child, list):
                children = cast("list[object]", child)
                for position, element in enumerate(cast("tuple[object, ...]", value)):
                    if isinstance(element, FormatModel) and position < len(children):
                        self._define_tree(element, f"{pointer}/{_escape(key)}/{position}", children[position])

    def _walk(self, item: FormatModel, pointer: str, reached: list[tuple[FormatModel, str]], seen: set[int]) -> None:
        if id(item) in seen:
            return
        seen.add(id(item))
        self._define(item, pointer)
        pointer = self.pointer(item)
        reached.append((item, pointer))
        for name, field in type(item).model_fields.items():
            key = _escape(field.alias or name)
            value: object = getattr(item, name)
            if isinstance(value, FormatModel):
                self._walk(value, f"{pointer}/{key}", reached, seen)
            elif isinstance(value, tuple):
                for position, element in enumerate(cast("tuple[object, ...]", value)):
                    if isinstance(element, FormatModel):
                        self._walk(element, f"{pointer}/{key}/{position}", reached, seen)

    def pointer(self, item: FormatModel) -> str:
        """Return the JSON pointer of a component of the library.

        Raises:
            KeyError: The component is not part of the library.
        """
        return self._pointers[id(item)]

    def at(self, pointer: str) -> FormatModel | None:
        """Return the component the file defines at `pointer`, or `None`."""
        if self._by_pointer is None:
            self._by_pointer = {where: item for item in self._keep for where in (self._pointers[id(item)],)}
        return self._by_pointer.get(pointer)

    def reachable(self, template: int) -> list[tuple[FormatModel, str]]:
        """Return every object template number `template` uses, itself first, with its pointer."""
        return list(self._reach[template])

    def users(self, item: FormatModel) -> list[int]:
        """Return the numbers of the templates that use a component, in template order."""
        return list(self._users.get(id(item), []))

    def components(self) -> Iterator[tuple[FormatModel, str]]:
        """Yield every component of the collections once, in file order, with its pointer."""
        seen: set[int] = set()
        for key in self._order:
            for item in cast("tuple[FormatModel, ...]", getattr(self.library, self._fields[key])):
                if id(item) not in seen:
                    seen.add(id(item))
                    yield item, self.pointer(item)


# --- SBEM field constraints -----------------------------------------------------------------------


def _sbem_classes() -> dict[str, type[BaseModel]]:
    found: dict[str, type[BaseModel]] = {}
    for module in (envelope, materials, operations, schedules, space_use, systems, zones):
        for name, value in vars(module).items():
            if inspect.isclass(value) and issubclass(value, BaseModel):
                found.setdefault(name, value)
    return found


def _model_of(annotation: object) -> type[BaseModel] | None:
    if inspect.isclass(annotation) and issubclass(annotation, BaseModel):
        return annotation
    if get_origin(annotation) in {Union, types.UnionType}:
        for arg in cast("tuple[object, ...]", get_args(annotation)):
            model = _model_of(arg)
            if model is not None:
                return model
    return None


def _sbem_field(path: str, classes: Mapping[str, type[BaseModel]]) -> FieldInfo | None:
    """The epinterface field an SBEM path of `CORRESPONDENCE` names, or `None`."""
    head, _, rest = path.partition(".")
    if head == "archetype":
        model: type[BaseModel] | None = Archetype
        steps = rest.split(".")
    elif head in classes:
        model = classes[head]
        steps = rest.split(".")
    else:
        model = ZoneComponent
        steps = path.split(".")
    for step in steps[:-1]:
        info = model.model_fields.get(step) if model is not None else None
        model = _model_of(info.annotation) if info is not None else None
    return model.model_fields.get(steps[-1]) if model is not None else None


@dataclass(frozen=True)
class _Bound:
    """The bounds of one UMI field, from the SBEM field it maps to."""

    key: str
    name: str
    sbem_path: str
    rule: str
    ge: float | None
    gt: float | None
    le: float | None
    lt: float | None

    def message(self, value: float) -> str | None:
        """Describe how `value` breaks the bounds, or `None`."""
        if not math.isfinite(value):
            return f"{self.key} is {value!r}; SBEM's {self.sbem_path} needs a finite value"
        broken = (
            (self.ge is not None and value < self.ge, f"at least {self.ge}"),
            (self.gt is not None and value <= self.gt, f"above {self.gt}"),
            (self.le is not None and value > self.le, f"at most {self.le}"),
            (self.lt is not None and value >= self.lt, f"below {self.lt}"),
        )
        needs = [text for failed, text in broken if failed]
        if not needs:
            return None
        return f"{self.key} is {value!r}; SBEM's {self.sbem_path} needs a value {' and '.join(needs)}"


_LOST_WHEN_OUT_OF_RANGE: Final = frozenset({
    ("BuildingTemplate", "Lifespan"),
    ("ConstructionBase", "AssemblyCarbon"),
    ("ConstructionBase", "AssemblyCost"),
    ("ConstructionBase", "AssemblyEnergy"),
    ("ConstructionBase", "DisassemblyCarbon"),
    ("ConstructionBase", "DisassemblyEnergy"),
    ("MaterialBase", "SubstitutionTimestep"),
    ("MaterialBase", "TransportDistance"),
    ("OpaqueMaterial", "MoistureDiffusionResistance"),
    ("WindowSettings", "OperableArea"),
    ("WindowSettings", "ShadingSystemSetpoint"),
    ("WindowSettings", "ShadingSystemTransmittance"),
    ("ZoneConditioning", "HeatRecoveryEfficiencyLatent"),
    ("ZoneConditioning", "HeatRecoveryEfficiencySensible"),
    ("ZoneConditioning", "MaxCoolFlow"),
    ("ZoneConditioning", "MaxCoolingCapacity"),
    ("ZoneConditioning", "MaxHeatFlow"),
    ("ZoneConditioning", "MaxHeatingCapacity"),
    ("ZoneDefinition", "DaylightMeshResolution"),
    ("ZoneDefinition", "DaylightWorkplaneHeight"),
    ("ZoneLoads", "IlluminanceTarget"),
    ("ZoneVentilation", "NatVentMaxOutdoorAirTemp"),
    ("ZoneVentilation", "NatVentMaxRelHumidity"),
    ("ZoneVentilation", "NatVentMinOutdoorAirTemp"),
    ("ZoneVentilation", "NatVentZoneTempSetpoint"),
    ("ZoneVentilation", "ScheduledVentilationAch"),
    ("ZoneVentilation", "ScheduledVentilationSetpoint"),
})
"""Fields whose translation rule loses a value SBEM refuses, keeping SBEM's default, as the
correspondence notes say: validation leaves them to the rule instead of refusing the template."""


def _bounds() -> dict[str, list[_Bound]]:
    """The SBEM bounds of each UMI class's numeric fields that map exactly, by class name."""
    classes = _sbem_classes()
    found: dict[str, list[_Bound]] = {}
    for row in CORRESPONDENCE:
        if row.status is not MappingStatus.EXACT or not row.sbem_paths:
            continue
        if (row.umi_class, row.umi_key) in _LOST_WHEN_OUT_OF_RANGE:
            continue
        info = _sbem_field(row.sbem_paths[0], classes)
        if info is None:
            continue
        limits: dict[str, float | None] = {"ge": None, "gt": None, "le": None, "lt": None}
        for constraint in info.metadata:
            for limit in limits:
                value = getattr(constraint, limit, None)
                if isinstance(value, (int, float)) and not isinstance(value, bool):
                    limits[limit] = float(value)
        if all(value is None for value in limits.values()):
            continue
        found.setdefault(row.umi_class, []).append(
            _Bound(row.umi_key, "", row.sbem_paths[0], row.rule, limits["ge"], limits["gt"], limits["le"], limits["lt"])
        )
    return found


_BOUNDS: Final = _bounds()


def _bound_problems(item: FormatModel, pointer: str, template: str) -> list[Problem]:
    aliases = {field.alias or name: name for name, field in type(item).model_fields.items()}
    problems: list[Problem] = []
    for klass in type(item).__mro__:
        for bound in _BOUNDS.get(klass.__name__, []):
            name = aliases.get(bound.key)
            value: object = getattr(item, name) if name is not None else None
            if not isinstance(value, (int, float)) or isinstance(value, bool):
                continue
            message = bound.message(float(value))
            if message is not None:
                problems.append(Problem(f"{pointer}/{bound.key}", template, bound.rule, message))
    return problems


# --- Completeness ----------------------------------------------------------------------------------


def _required(item: FormatModel, pointer: str, template: str) -> list[Problem]:
    problems: list[Problem] = []
    for klass, references in _REQUIRED.items():
        if not isinstance(item, klass):
            continue
        for name, key in references:
            if getattr(item, name) is None:
                problems.append(
                    Problem(
                        f"{pointer}/{key}",
                        template,
                        REQUIRED_REFERENCE,
                        f"{key} is null; a {type(item).__name__} needs it",
                    )
                )
    return problems


def _week_problems(week: WeekSchedule, pointer: str, template: str) -> list[Problem]:
    if len(week.days) != len(range(7)):
        return [
            Problem(
                f"{pointer}/Days",
                template,
                REQUIRED_REFERENCE,
                f"a week needs 7 days, Monday first, not {len(week.days)}",
            )
        ]
    return [
        Problem(f"{pointer}/Days/{index}", template, REQUIRED_REFERENCE, "the day is null; a week needs 7 days")
        for index, day in enumerate(week.days)
        if day is None
    ]


def _day_problems(day: DaySchedule, pointer: str, template: str) -> list[Problem]:
    if len(day.values) != _HOURS:
        return [Problem(f"{pointer}/Values", template, DAY_VALUES, f"a day needs 24 values, not {len(day.values)}")]
    if day.type.lower() == "fraction" and any(not 0 <= value <= 1 for value in day.values):
        outside = sorted({value for value in day.values if not 0 <= value <= 1})
        return [
            Problem(
                f"{pointer}/Values",
                template,
                "schedule.day",
                f"a Fraction day holds values outside [0, 1]: {', '.join(repr(v) for v in outside[:3])}",
            )
        ]
    return []


def _day(month: int, day: int) -> str:
    return f"{month:02d}-{day:02d}"


def _valid_date(month: int, day: int) -> bool:
    # February may end on the 29th (research R7), so dates are checked against a leap year.
    return 1 <= month <= 12 and 1 <= day <= monthrange(2024, month)[1]  # noqa: PLR2004


def _year_problems(year: YearSchedule, pointer: str, template: str) -> list[Problem]:
    where = f"{pointer}/Parts"
    problems: list[Problem] = []
    ranges: list[tuple[int, tuple[int, int], tuple[int, int]]] = []
    for index, part in enumerate(year.parts):
        start, end = (part.from_month, part.from_day), (part.to_month, part.to_day)
        bad = [_day(*when) for when in (start, end) if not _valid_date(*when)]
        if bad:
            problems.append(Problem(where, template, YEAR_COVERAGE, f"part {index}: {' and '.join(bad)} is not a date"))
        else:
            ranges.append((index, start, end))
    if problems:
        return problems
    gaps: list[str] = []
    overlaps: list[str] = []
    previous_gap = previous_overlap = False
    today = date(2023, 1, 1)  # a non-leap year: the reference year's calendar
    while today.year == 2023:  # noqa: PLR2004
        key = (today.month, today.day)
        covering = [index for index, start, end in ranges if start <= key <= end]
        gap, overlap = not covering, len(covering) > 1
        if gap and not previous_gap:
            gaps.append(_day(*key))
        if overlap and not previous_overlap:
            overlaps.append(f"{_day(*key)} (parts {', '.join(str(i) for i in covering)})")
        previous_gap, previous_overlap = gap, overlap
        today += timedelta(days=1)
    if gaps:
        problems.append(Problem(where, template, YEAR_COVERAGE, f"no part covers {', '.join(gaps)}"))
    if overlaps:
        problems.append(Problem(where, template, YEAR_COVERAGE, f"parts overlap from {', '.join(overlaps)}"))
    return problems


# --- Range -------------------------------------------------------------------------------------------


def _opaque_material(item: OpaqueMaterial, pointer: str, template: str) -> list[Problem]:
    problems = material_problems(item, pointer, template)
    if not item.specific_heat >= _MIN_SPECIFIC_HEAT:  # NaN included
        message = f"SpecificHeat is {item.specific_heat!r} J/kg-K; a material needs at least {_MIN_SPECIFIC_HEAT}"
        problems.append(Problem(f"{pointer}/SpecificHeat", template, "material.properties", message))
    return problems


def _layer(item: MaterialLayer[OpaqueMaterial], pointer: str, template: str) -> list[Problem]:
    if item.thickness > 0:
        return []
    message = f"Thickness is {item.thickness!r} m; a layer needs more than 0"
    return [Problem(f"{pointer}/Thickness", template, "construction.layers", message)]


def _glazing(item: GlazingMaterial, pointer: str, template: str) -> list[Problem]:
    problems: list[Problem] = []
    for name in _GLAZING_FRACTIONS:
        value: float = getattr(item, name)
        if not 0 <= value <= 1:
            key = _alias(GlazingMaterial, name)
            message = f"{key} is {value!r}; it must be in [0, 1]"
            problems.append(Problem(f"{pointer}/{key}", template, "window.layers", message))
    # Opaque materials may have a conductivity of 0 (SBEM's `ge=0`); glass may not (`gt=0`),
    # and Basilisk writes 0 for a glazing material without one.
    if not item.conductivity > 0:
        key = _alias(GlazingMaterial, "conductivity")
        message = f"{key} is {item.conductivity!r}; a glazing material's must be above 0"
        problems.append(Problem(f"{pointer}/{key}", template, "window.layers", message))
    return problems


def _gas(item: GasMaterial, pointer: str, template: str) -> list[Problem]:
    if item.type.strip().upper() in _GASES or (item.name or "").strip().upper() in _GASES:
        return []
    message = f"gas {item.type!r} is not one EnergyPlus models ({', '.join(sorted(_GASES))})"
    return [Problem(f"{pointer}/Type", template, "window.layers", message)]


def _template(item: BuildingTemplate, pointer: str, template: str) -> list[Problem]:
    ratio = item.default_window_to_wall_ratio
    if 0 <= ratio <= 1:
        return []
    message = f"DefaultWindowToWallRatio is {ratio!r}; it must be in [0, 1]"
    return [Problem(f"{pointer}/DefaultWindowToWallRatio", template, "wwr.uniform", message)]


def _plausibility(item: FormatModel, pointer: str, template: str) -> list[Problem]:  # noqa: PLR0911 - one branch per class
    """The range rules of the rule modules and research R3's plausibility rules for one object."""
    if isinstance(item, OpaqueMaterial):
        return _opaque_material(item, pointer, template)
    if isinstance(item, MaterialLayer):
        return _layer(cast("MaterialLayer[OpaqueMaterial]", item), pointer, template)
    if isinstance(item, GlazingMaterial):
        return _glazing(item, pointer, template)
    if isinstance(item, GasMaterial):
        return _gas(item, pointer, template)
    if isinstance(item, BuildingTemplate):
        return _template(item, pointer, template)
    if isinstance(item, ZoneLoads):
        return loads.range_problems(item, pointer=pointer, template=template)
    if isinstance(item, ZoneConditioning):
        return conditioning.range_problems(item, pointer=pointer, template=template)
    if isinstance(item, ZoneVentilation):
        return ventilation.range_problems(item, pointer=pointer, template=template)
    return []


_RULES: Final = {(row.umi_class, row.umi_key): row.rule for row in CORRESPONDENCE}


def _rule_of(model: type[FormatModel], key: str) -> str:
    """The rule of a UMI field's `CORRESPONDENCE` row, looked up on the class that declares it."""
    for klass in model.__mro__:
        origin = getattr(klass, "__pydantic_generic_metadata__", {}).get("origin") or klass
        rule = _RULES.get((cast("type", origin).__name__, key))
        if rule is not None:
            return rule
    return "format.json"


def _finite_problems(item: FormatModel, pointer: str, template: str) -> list[Problem]:
    """A problem for each number field, or list of numbers, holding `NaN` or an infinity."""
    problems: list[Problem] = []
    for name, field in type(item).model_fields.items():
        key = field.alias or name
        value: object = getattr(item, name)
        numbers = cast("tuple[object, ...]", value) if isinstance(value, tuple) else (value,)
        bad = [number for number in numbers if isinstance(number, float) and not math.isfinite(number)]
        if bad:
            message = f"{key} holds {bad[0]!r}; a value must be a finite number"
            problems.append(Problem(f"{pointer}/{_escape(key)}", template, _rule_of(type(item), key), message))
    return problems


def _problems_of(item: FormatModel, pointer: str, template: str, index: LibraryIndex) -> list[Problem]:
    non_finite = _finite_problems(item, pointer, template)
    problems = _required(item, pointer, template)
    if isinstance(item, WeekSchedule):
        problems.extend(_week_problems(item, pointer, template))
    elif isinstance(item, DaySchedule):
        problems.extend(_day_problems(item, pointer, template))
    elif isinstance(item, YearSchedule):
        problems.extend(_year_problems(item, pointer, template))
    elif isinstance(item, ZoneDefinition) and item.domestic_hot_water is not None:
        dhw = item.domestic_hot_water
        problems.extend(hotwater.range_problems(dhw, item.loads, pointer=index.pointer(dhw), template=template))
    problems.extend(_plausibility(item, pointer, template))
    known = {problem.pointer for problem in problems}
    problems.extend(problem for problem in _bound_problems(item, pointer, template) if problem.pointer not in known)
    # A non-finite number is one problem, not one per comparison it fails.
    known = {problem.pointer for problem in non_finite}
    return non_finite + [problem for problem in problems if problem.pointer not in known]


def template_problems(index: LibraryIndex, template: int) -> list[Problem]:
    """Return the completeness and range problems of one template and everything it uses.

    Args:
        index: The library's index.
        template: The template's number in the library.

    Returns:
        The problems, in the order the template's objects are reached, without repeats.
    """
    name = index.library.building_templates[template].name or index.pointer(index.library.building_templates[template])
    found: list[Problem] = []
    for item, pointer in index.reachable(template):
        for problem in _problems_of(item, pointer, name, index):
            if problem not in found:
                found.append(problem)
    return found


def validate(index: LibraryIndex) -> list[Problem]:
    """Return every completeness and range problem of a resolved library (research R3).

    A problem in a component several templates use is listed once per template.

    Args:
        index: The index of the resolved library (`LibraryIndex(library, document)`).

    Returns:
        The problems, template by template; empty when the library is valid.
    """
    count = len(index.library.building_templates)
    return [problem for number in range(count) for problem in template_problems(index, number)]
