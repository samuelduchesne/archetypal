"""The checks of tools/basilisk-check in Python, for runs without .NET (spec 003, research R15).

A port of the harness's check 1 (the raw-JSON reference scan of research R1), check 3 (the
orphan check: Basilisk's `OrphanedComponents()`, components a template reaches that are in no
collection, and with `no_unused` components no template reaches) and check 4 (names and the
required references of research R3, days, weeks, years and layers). Check 2 (`FromJson`) is
not ported: the library is loaded the way Newtonsoft loads it, by these rules:

- an object whose first key is a string `$id` is registered under it;
- `{"$ref": id}` is the object registered earlier under `id`, else `null`, as Basilisk turns
  a dangling or forward reference into `null`;
- a component's class comes from where it stands (its collection, or the key that holds it).

It is independent of `archetypal.umi`, so it checks what archetypal writes against Basilisk's
rules, not against archetypal's own reading. The messages are the harness's.

Usage from a test::

    failures = check_file(path, no_unused=True)
    assert failures == [], "\\n".join(map(str, failures))
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from collections.abc import Iterator

Json = dict[str, object]

CHECK_NAMES = {1: "refs", 2: "load", 3: "orphans", 4: "complete"}

# The 17 collections in Basilisk's order, with the class of their components.
COLLECTIONS: dict[str, str] = {
    "GasMaterials": "GasMaterial",
    "GlazingMaterials": "GlazingMaterial",
    "OpaqueMaterials": "OpaqueMaterial",
    "OpaqueConstructions": "OpaqueConstruction",
    "WindowConstructions": "WindowConstruction",
    "StructureDefinitions": "StructureInformation",
    "DaySchedules": "DaySchedule",
    "WeekSchedules": "WeekSchedule",
    "YearSchedules": "YearSchedule",
    "DomesticHotWaterSettings": "DomesticHotWaterSettings",
    "VentilationSettings": "ZoneVentilation",
    "ZoneConditionings": "ZoneConditioning",
    "ZoneConstructionSets": "ZoneConstructions",
    "ZoneLoads": "ZoneLoads",
    "Zones": "ZoneDefinition",
    "BuildingTemplates": "BuildingTemplate",
    "WindowSettings": "WindowSettings",
}
COLLECTION_OF = {cls: name for name, cls in COLLECTIONS.items()}

_YEAR = "YearSchedule"
_OPAQUE = "OpaqueConstruction"

# Each reference a component holds directly: (key, class), as the harness's `Children`.
DIRECT: dict[str, list[tuple[str, str]]] = {
    "BuildingTemplate": [
        ("Core", "ZoneDefinition"),
        ("Perimeter", "ZoneDefinition"),
        ("Structure", "StructureInformation"),
        ("Windows", "WindowSettings"),
    ],
    "ZoneDefinition": [
        ("Conditioning", "ZoneConditioning"),
        ("Constructions", "ZoneConstructions"),
        ("DomesticHotWater", "DomesticHotWaterSettings"),
        ("InternalMassConstruction", _OPAQUE),
        ("Loads", "ZoneLoads"),
        ("Ventilation", "ZoneVentilation"),
    ],
    "ZoneConstructions": [(key, _OPAQUE) for key in ("Facade", "Ground", "Partition", "Roof", "Slab")],
    "ZoneLoads": [
        (key, _YEAR) for key in ("EquipmentAvailabilitySchedule", "LightsAvailabilitySchedule", "OccupancySchedule")
    ],
    "ZoneConditioning": [(key, _YEAR) for key in ("CoolingSchedule", "HeatingSchedule", "MechVentSchedule")],
    "ZoneVentilation": [(key, _YEAR) for key in ("NatVentSchedule", "ScheduledVentilationSchedule")],
    "DomesticHotWaterSettings": [("WaterSchedule", _YEAR)],
    "WindowSettings": [
        ("AfnWindowAvailability", _YEAR),
        ("Construction", "WindowConstruction"),
        ("ShadingSystemAvailabilitySchedule", _YEAR),
        ("ZoneMixingAvailabilitySchedule", _YEAR),
    ],
}
# References held in a list: class -> (list key, key inside each item or None, class).
LISTED: dict[str, tuple[str, str | None, str]] = {
    "OpaqueConstruction": ("Layers", "Material", "OpaqueMaterial"),
    "WindowConstruction": ("Layers", "Material", "WindowMaterialBase"),
    "StructureInformation": ("MassRatios", "Material", "OpaqueMaterial"),
    "YearSchedule": ("Parts", "Schedule", "WeekSchedule"),
    "WeekSchedule": ("Days", None, "DaySchedule"),
}
# Classes whose `ReferencedComponents` also include what their direct references reference.
TRANSITIVE = {"ZoneDefinition", "ZoneConstructions", "WindowSettings"}

DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)


@dataclass(frozen=True)
class Failure:
    """One failed check, numbered and worded as tools/basilisk-check reports it."""

    check: int
    message: str

    def __str__(self) -> str:
        """Return the failure as the harness prints it after the file name."""
        return f"check {self.check} {CHECK_NAMES[self.check]}: {self.message}"


def parse(text: str) -> Json:
    """Parse a library's text, keys in file order (a UTF-8 byte order mark is dropped)."""
    return cast("Json", json.loads(text.removeprefix("﻿")))


# --- Check 1 -----------------------------------------------------------------------------


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


def _scan_id(item: object, index: int, at: str, seen: set[str]) -> list[str]:
    problems: list[str] = []
    if index != 0:
        problems.append(f'{at}: "$id" is not the first key of its object')
    if not isinstance(item, str):
        problems.append(f'{at}: "$id" is not a string')
    elif item in seen:
        problems.append(f'{at}: duplicate "$id" "{item}"')
    else:
        seen.add(item)
    return problems


def _scan_ref(item: object, at: str, seen: set[str]) -> list[str]:
    if not isinstance(item, str):
        return [f'{at}: "$ref" is not a string']
    if item not in seen:
        return [f'{at}: "$ref" "{item}" does not point to an "$id" defined earlier in the file']
    return []


def _scan(value: object, pointer: str, seen: set[str], problems: list[str]) -> None:
    if isinstance(value, list):
        for index, item in enumerate(cast("list[object]", value)):
            _scan(item, f"{pointer}/{index}", seen, problems)
        return
    if not isinstance(value, dict):
        return
    obj = cast("Json", value)
    for index, (key, item) in enumerate(obj.items()):
        at = f"{pointer}/{_escape(key)}"
        if key == "$id":
            problems.extend(_scan_id(item, index, at, seen))
        elif key == "$ref":
            problems.extend(_scan_ref(item, at, seen))
        else:
            _scan(item, at, seen, problems)
    if "$ref" in obj and len(obj) != 1:
        problems.append(f'{pointer}: an object holding "$ref" has other keys')


def reference_scan(document: object) -> list[str]:
    """Check 1: research R1's reference rules on the raw JSON, in file order."""
    if not isinstance(document, dict):
        return ["the document is not a JSON object"]
    problems: list[str] = []
    _scan(cast("Json", document), "", set(), problems)
    return problems


# --- Loading as Newtonsoft does ----------------------------------------------------------


class Loaded:
    """A library loaded the way Newtonsoft loads it: every `$ref` followed or `None`."""

    def __init__(self, document: Json) -> None:
        """Load a parsed library, following its references in file order."""
        self.document = document
        self.targets: dict[int, Json | None] = {}
        self._register(document, {})
        self.members: dict[int, str] = {
            id(c): cls for name, cls in COLLECTIONS.items() for c in self.collection(name) if c is not None
        }

    def _register(self, value: object, ids: dict[str, Json]) -> None:
        if isinstance(value, list):
            for item in cast("list[object]", value):
                self._register(item, ids)
            return
        if not isinstance(value, dict):
            return
        obj = cast("Json", value)
        first = next(iter(obj), None)
        if first == "$id" and isinstance(obj["$id"], str):
            ids[obj["$id"]] = obj
        if "$ref" in obj:
            ref = obj["$ref"]
            self.targets[id(obj)] = ids.get(ref) if isinstance(ref, str) else None
            return
        for item in obj.values():
            self._register(item, ids)

    def deref(self, value: object) -> Json | None:
        """The component a JSON value stands for: itself, the target of its `$ref`, or None."""
        if not isinstance(value, dict):
            return None
        obj = cast("Json", value)
        return self.targets.get(id(obj)) if "$ref" in obj else obj

    def collection(self, name: str) -> list[Json | None]:
        items = self.document.get(name)
        return [self.deref(item) for item in cast("list[object]", items)] if isinstance(items, list) else []

    def children(self, cls: str, component: Json) -> Iterator[tuple[str, str, Json | None]]:
        """Every reference a component holds, as `(key, class, component or None)`."""
        for key, child_cls in DIRECT.get(cls, []):
            yield key, child_cls, self.deref(component.get(key))
        if cls in LISTED:
            list_key, item_key, child_cls = LISTED[cls]
            items = component.get(list_key)
            for index, item in enumerate(cast("list[object]", items) if isinstance(items, list) else []):
                if item_key is None:
                    yield f"{list_key}[{index}]", child_cls, self.deref(item)
                else:
                    holder = cast("Json", item) if isinstance(item, dict) else {}
                    child = self.deref(holder.get(item_key))
                    yield f"{list_key}[{index}].{item_key}", self.concrete(child_cls, child), child

    def concrete(self, cls: str, component: Json | None) -> str:
        """The class of a window layer's material: glazing or gas, from its collection."""
        if cls != "WindowMaterialBase" or component is None:
            return cls
        if id(component) in self.members:
            return self.members[id(component)]
        return "GasMaterial" if component.get("Category") == "Gases" else "GlazingMaterial"


def _name(component: Json | None) -> str:
    name = None if component is None else component.get("Name")
    return name if isinstance(name, str) else "<null name>"


def _describe(cls: str, component: Json | None) -> str:
    if component is None:
        return "<null>"
    return f'{cls} "{_name(component)}"'


# --- Check 3 -----------------------------------------------------------------------------


def _referenced(lib: Loaded, cls: str, component: Json) -> list[tuple[str, Json | None]]:
    """Basilisk's `ReferencedComponents`: direct references, and more for some classes."""
    if cls == "BuildingTemplate":
        found: list[tuple[str, Json | None]] = []
        for key, child_cls, child in lib.children(cls, component):
            if child is not None:
                found.extend([(child_cls, child)] if key == "Windows" else _referenced(lib, child_cls, child))
        return found
    # A week's days are returned unfiltered, so a null day is listed; every other class drops nulls.
    direct = [(c, child) for _, c, child in lib.children(cls, component) if child is not None or cls == "WeekSchedule"]
    if cls not in TRANSITIVE:
        return direct
    nested = [r for c, child in direct if child is not None for r in _referenced(lib, c, child)]
    return direct + nested


def _known_key(cls: str, component: Json) -> object:
    """The identity `Except` uses: gases compare by `Type`, everything else by object."""
    if cls == "GasMaterial":
        return ("gas", component.get("Type", "AIR"))
    return id(component)


def orphan_check(lib: Loaded, *, no_unused: bool) -> list[str]:
    """Check 3: orphans, components reached but in no collection, and optionally unused ones."""
    problems: list[str] = []
    known = {_known_key(cls, c) for name, cls in COLLECTIONS.items() for c in lib.collection(name) if c is not None}
    orphans: dict[object, tuple[str, Json | None]] = {}
    for name, cls in COLLECTIONS.items():
        for component in lib.collection(name):
            for child_cls, child in [] if component is None else _referenced(lib, cls, component):
                key = None if child is None else _known_key(child_cls, child)
                if key not in known and key not in orphans:
                    orphans[key] = (child_cls, child)
    problems.extend(f"OrphanedComponents() lists {_describe(c, o)}" for c, o in orphans.values())

    reached: set[int] = set()
    stack = [
        ("BuildingTemplate", t, f"BuildingTemplates[{i}]")
        for i, t in enumerate(lib.collection("BuildingTemplates"))
        if t is not None
    ]
    while stack:
        cls, component, path = stack.pop()
        if id(component) in reached:
            continue
        reached.add(id(component))
        if id(component) not in lib.members:
            where = COLLECTION_OF.get(cls, "a collection")
            problems.append(f"{_describe(cls, component)} at {path} is not in {where}")
        stack.extend((c, child, f"{path}.{key}") for key, c, child in lib.children(cls, component) if child is not None)
    if no_unused:
        for name, cls in COLLECTIONS.items():
            problems.extend(
                f"{_describe(cls, c)} is not used by any building template"
                for c in lib.collection(name)
                if c is not None and id(c) not in reached
            )
    return problems


# --- Check 4 -----------------------------------------------------------------------------


def _names(problems: list[str], label: str, items: list[tuple[str, Json | None]]) -> None:
    first: dict[str, str] = {}
    for where, component in items:
        if component is None:
            continue
        name = component.get("Name")
        if not isinstance(name, str):
            problems.append(f"{where}: Name is null")
        elif name in first:
            problems.append(f'{where}: name "{name}" is already used by {first[name]} ({label})')
        else:
            first[name] = where


def _day_of_year(month: object, day: object) -> int:
    if not isinstance(month, int) or not isinstance(day, int) or not 1 <= month <= 12:
        return -1
    if not 1 <= day <= DAYS_IN_MONTH[month - 1]:
        return -1
    return sum(DAYS_IN_MONTH[: month - 1]) + day


def _year_coverage(year: Json) -> list[str]:
    """Year parts cover 1 January to 31 December (a leap year) with no gap or overlap."""
    problems: list[str] = []
    spans: list[tuple[int, int, int]] = []
    parts = year.get("Parts")
    for index, part in enumerate(cast("list[object]", parts) if isinstance(parts, list) else []):
        if not isinstance(part, dict):
            problems.append(f"Parts[{index}] is null")
            continue
        p = cast("Json", part)
        dates = f"{p.get('FromMonth')}/{p.get('FromDay')} to {p.get('ToMonth')}/{p.get('ToDay')}"
        start, end = _day_of_year(p.get("FromMonth"), p.get("FromDay")), _day_of_year(p.get("ToMonth"), p.get("ToDay"))
        if start < 0 or end < 0:
            problems.append(f"Parts[{index}] has an invalid date ({dates})")
        elif end < start:
            problems.append(f"Parts[{index}] ends before it starts ({dates})")
        else:
            spans.append((start, end, index))
    if not spans:
        return [*problems, "Parts is empty"]
    following = 1
    for start, end, index in sorted(spans, key=lambda s: s[0]):
        if start > following:
            problems.append(f"Parts leave a gap before Parts[{index}] (days {following} to {start - 1})")
        if start < following:
            problems.append(f"Parts[{index}] overlaps an earlier part")
        following = max(following, end + 1)
    if following <= 366:
        problems.append(f"Parts end before 31 December (day {following - 1})")
    return problems


def _length(component: Json, key: str) -> int:
    value = component.get(key)
    return len(cast("list[object]", value)) if isinstance(value, list) else 0


def _shape(cls: str, component: Json) -> list[str]:
    """The shape rules: 24 values a day, 7 days a week, year coverage, layers present."""
    if cls == "DaySchedule" and _length(component, "Values") != 24:
        return [f"Values has {_length(component, 'Values')} entries, not 24"]
    if cls == "WeekSchedule" and _length(component, "Days") != 7:
        return [f"Days has {_length(component, 'Days')} entries, not 7"]
    if cls == "YearSchedule":
        return _year_coverage(component)
    if cls in {"OpaqueConstruction", "WindowConstruction"} and _length(component, "Layers") == 0:
        return ["Layers is empty"]
    return []


def completeness_check(lib: Loaded) -> list[str]:
    """Check 4: names unique and non-null, required references non-null, and shapes."""
    problems: list[str] = []
    for name in COLLECTIONS:
        if name not in {"GlazingMaterials", "GasMaterials"}:
            _names(problems, name, [(f"{name}[{i}]", c) for i, c in enumerate(lib.collection(name))])
    windows = [(f"GlazingMaterials[{i}]", c) for i, c in enumerate(lib.collection("GlazingMaterials"))]
    windows += [(f"GasMaterials[{i}]", c) for i, c in enumerate(lib.collection("GasMaterials"))]
    _names(problems, "GlazingMaterials and GasMaterials together", windows)

    for name, cls in COLLECTIONS.items():
        for index, component in enumerate(lib.collection(name)):
            if component is None:
                problems.append(f"{name}[{index}]: the entry is null")
                continue
            where = f'{name}[{index}] "{component.get("Name")}"'
            for key, _, child in lib.children(cls, component):
                # Structure and its mass ratios are optional; everything else is required.
                optional = cls == "StructureInformation" or (cls == "BuildingTemplate" and key == "Structure")
                if child is None and not optional:
                    problems.append(f"{where}: {key} is null")
            problems.extend(f"{where}: {problem}" for problem in _shape(cls, component))
    return problems


# --- Entry points ------------------------------------------------------------------------


def check_library(document: object, *, no_unused: bool = False) -> list[Failure]:
    """Run checks 1, 3 and 4 on a parsed library.

    Args:
        document: The library as parsed from JSON, keys in file order.
        no_unused: Also fail check 3 on components no building template uses, as the
            harness's `--no-unused` does for libraries archetypal writes.

    Returns:
        Every failure, check 1 first; empty when the library passes.
    """
    failures = [Failure(1, message) for message in reference_scan(document)]
    if not isinstance(document, dict):
        return failures
    lib = Loaded(cast("Json", document))
    failures += [Failure(3, message) for message in orphan_check(lib, no_unused=no_unused)]
    failures += [Failure(4, message) for message in completeness_check(lib)]
    return failures


def check_text(text: str, *, no_unused: bool = False) -> list[Failure]:
    """Run checks 1, 3 and 4 on a library's text; text that is not JSON fails check 1."""
    try:
        document = parse(text)
    except json.JSONDecodeError as error:
        return [Failure(1, f"malformed JSON: {error}")]
    return check_library(document, no_unused=no_unused)


def check_file(path: str | Path, *, no_unused: bool = False) -> list[Failure]:
    """Run checks 1, 3 and 4 on a library file."""
    return check_text(Path(path).read_text(encoding="utf-8"), no_unused=no_unused)
