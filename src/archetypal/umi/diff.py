"""Field-by-field comparison of UMI libraries and of SBEM archetypes (spec 003, US3, research R16).

- `diff_umi(original, result)` compares two UMI library files after resolving their references.
  Building templates are matched by name, and each template's components are compared through
  the template's tree, so a component is matched with the one in the same place of the
  template of the same name. Year schedules are compared by their hourly values over the
  reference year (research R7), not by their parts, weeks and days, which a writer may arrange
  differently. A component no template of the original uses is matched by type and name; one
  no template of the result uses and nothing matches is located at `/<collection>/-`.
- `diff_archetypes(a, b)` compares two SBEM archetypes field by field. Zone groups are matched
  by name, then by exposure; locations are dotted field paths prefixed by the group (`perimeter.Operations…`) or
  by `archetype.`, as in the translation report.

Each difference names its location (a JSON pointer into the original library, or an SBEM field
path), its relevance, both values and, for numbers, their relative difference. Values whose
absolute difference is below 1e-12 are equal. `within_tolerance` is false only when a
simulation-relevant (`S`) difference exceeds `rel_tol`; a non-numeric `S` difference always
exceeds it.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import cache
from typing import TYPE_CHECKING, Final, cast

from pydantic import BaseModel

from archetypal.umi import dialects
from archetypal.umi._format import (
    BuildingTemplate,
    DaySchedule,
    FormatModel,
    LibraryComponent,
    WeekSchedule,
    YearSchedule,
)
from archetypal.umi._refs import resolve
from archetypal.umi.correspondence import CORRESPONDENCE, Relevance
from archetypal.umi.rules._common import REFERENCE_CALENDAR
from archetypal.umi.validate import LibraryIndex

if TYPE_CHECKING:
    import os

    from epinterface.sbem.archetype import Archetype, ZoneGroup
    from pydantic import JsonValue

__all__ = ["ABS_TOL", "ArchetypeDiff", "Difference", "UmiDiff", "diff_archetypes", "diff_umi"]

ABS_TOL: Final = 1e-12
"""Two numbers closer than this are equal."""

_HOURS: Final = 24


@dataclass(frozen=True)
class Difference:
    """One value that differs between the original and the result.

    Attributes:
        location: Where, in the original: a JSON pointer into the UMI library, or an SBEM field
            path prefixed by the zone group or `archetype.`.
        relevance: What the field is used for (`S`, `L` or `D`).
        original: The original value; `None` when the original has no such value.
        result: The resulting value; `None` when the result has no such value.
        relative: For two numbers, `|original - result| / max(|original|, |result|)`; for
            schedules, the largest hourly difference relative to the largest hourly magnitude;
            `None` for other values.
        subject: The building template (UMI) or archetype the difference belongs to; `""` for
            a component no template uses. A template renamed on reading is named as renamed.
        via: The pointers of the reference fields through which the value was reached, from
            the template down (`/BuildingTemplates/0/Perimeter`, `/Zones/0/Loads`, …); empty for
            SBEM paths. A loss at one of them explains the difference.
    """

    location: str
    relevance: Relevance
    original: JsonValue
    result: JsonValue
    relative: float | None
    subject: str = ""
    via: tuple[str, ...] = ()

    def exceeds(self, rel_tol: float) -> bool:
        """Whether the difference is larger than `rel_tol` (always, for a non-numeric one)."""
        return self.relative is None or self.relative > rel_tol


@dataclass(frozen=True)
class _Diff:
    """The differences found by a comparison, and the tolerance of `within_tolerance`."""

    differences: tuple[Difference, ...]
    rel_tol: float

    @property
    def within_tolerance(self) -> bool:
        """Whether no simulation-relevant difference exceeds `rel_tol`."""
        return not any(d.relevance is Relevance.SIMULATION and d.exceeds(self.rel_tol) for d in self.differences)

    def __bool__(self) -> bool:
        """Whether there is any difference."""
        return bool(self.differences)

    def __len__(self) -> int:
        """The number of differences."""
        return len(self.differences)

    def beyond(self, rel_tol: float | None = None) -> tuple[Difference, ...]:
        """The differences larger than `rel_tol` (default: the diff's own), of any relevance."""
        tolerance = self.rel_tol if rel_tol is None else rel_tol
        return tuple(d for d in self.differences if d.exceeds(tolerance))


@dataclass(frozen=True)
class UmiDiff(_Diff):
    """The differences between two UMI libraries.

    Attributes:
        differences: Every difference, in the original's order (templates, then the
            components no template uses).
        rel_tol: The relative tolerance of `within_tolerance` (default 1e-4, SC-003).
    """


@dataclass(frozen=True)
class ArchetypeDiff(_Diff):
    """The differences between two SBEM archetypes.

    Attributes:
        differences: Every difference, in field order.
        rel_tol: The relative tolerance of `within_tolerance` (default 0).
    """


# --- Values ----------------------------------------------------------------------------------------


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and not isinstance(value, Enum)


def _relative(a: float, b: float) -> float | None:
    """Return the relative difference, `0.0` for equal numbers (two NaNs included), `None` when one is not finite."""
    if a == b or abs(a - b) < ABS_TOL or (math.isnan(a) and math.isnan(b)):
        return 0.0
    if not (math.isfinite(a) and math.isfinite(b)):
        return None
    return abs(a - b) / max(abs(a), abs(b))


def _json(value: object) -> JsonValue:
    """Return a compared value as JSON: enums by value, components by name, tuples as lists."""
    if isinstance(value, Enum):
        return cast("JsonValue", value.value)
    if isinstance(value, LibraryComponent):
        return value.name
    if isinstance(value, BaseModel):
        return cast("JsonValue", value.model_dump(mode="json"))
    if isinstance(value, tuple | list):
        return [_json(item) for item in cast("Sequence[object]", value)]
    if isinstance(value, Mapping):
        return {str(k): _json(v) for k, v in cast("Mapping[object, object]", value).items()}
    return cast("JsonValue", value)


def _escape(key: str) -> str:
    return key.replace("~", "~0").replace("/", "~1")


# --- UMI -----------------------------------------------------------------------------------------------


@cache
def _relevance_table() -> dict[tuple[str, str], Relevance]:
    return {(row.umi_class, row.umi_key): row.relevance for row in CORRESPONDENCE}


def _umi_relevance(model: type[FormatModel], key: str) -> Relevance:
    """The relevance of a UMI field, looked up on the class that declares it."""
    table = _relevance_table()
    for klass in model.__mro__:
        name = getattr(klass, "__pydantic_generic_metadata__", {}).get("origin") or klass
        found = table.get((cast("type", name).__name__, key))
        if found is not None:
            return found
    return Relevance.SIMULATION


def hourly_values(year: YearSchedule) -> tuple[float, ...]:
    """Return a UMI year schedule's 8760 hourly values over the reference year (research R7).

    Each day takes the first part that covers it, and the day of its week for its weekday.

    Raises:
        ValueError: A day is in no part, or a part, week or day is missing or has the wrong size.
    """
    values: list[float] = []
    covering = _covering(year)
    weekdays = REFERENCE_CALENDAR.day_weekdays
    for day, index in enumerate(covering):
        week = year.parts[index].schedule
        if week is None:
            msg = f"part {index} of {year.name!r} has no week schedule"
            raise ValueError(msg)
        today = _day_of(week, int(weekdays[day]))
        values.extend(today.values)
    return tuple(values)


def _covering(year: YearSchedule) -> list[int]:
    from datetime import date, timedelta  # noqa: PLC0415 - small, local helper

    start = date(REFERENCE_CALENDAR.year, 1, 1)
    bounds = [((p.from_month, p.from_day), (p.to_month, p.to_day)) for p in year.parts]
    covering: list[int] = []
    for offset in range(REFERENCE_CALENDAR.days):
        today = start + timedelta(days=offset)
        key = (today.month, today.day)
        index = next((i for i, (lo, hi) in enumerate(bounds) if lo <= key <= hi), None)
        if index is None:
            msg = f"no part of {year.name!r} covers {today:%m-%d}"
            raise ValueError(msg)
        covering.append(index)
    return covering


def _day_of(week: WeekSchedule, weekday: int) -> DaySchedule:
    if len(week.days) <= weekday or week.days[weekday] is None:
        msg = f"week {week.name!r} has no day {weekday}"
        raise ValueError(msg)
    day = cast("DaySchedule", week.days[weekday])
    if len(day.values) != _HOURS:
        msg = f"day {day.name!r} has {len(day.values)} values, not 24"
        raise ValueError(msg)
    return day


class _UmiComparer:
    """Compares two resolved libraries through their templates."""

    _SCHEDULE_PARTS: Final = "Parts"

    def __init__(self, original: LibraryIndex) -> None:
        self.original = original
        self.found: list[Difference] = []
        self.subject = ""
        self._via: list[str] = []
        self._seen: set[tuple[str, str, int, int]] = set()
        self._keys: set[tuple[str, str, str, str, tuple[str, ...]]] = set()
        self._hourly: dict[int, tuple[float, ...] | str] = {}

    def add(
        self, location: str, relevance: Relevance, original: object, result: object, relative: float | None
    ) -> None:
        a, b = _json(original), _json(result)
        via = tuple(self._via)
        key = (self.subject, location, repr(a), repr(b), via)
        if key in self._keys:
            return
        self._keys.add(key)
        self.found.append(Difference(location, relevance, a, b, relative, self.subject, via))

    def hourly(self, year: YearSchedule) -> tuple[float, ...] | str:
        key = id(year)
        if key not in self._hourly:
            try:
                self._hourly[key] = hourly_values(year)
            except ValueError as error:
                self._hourly[key] = str(error)
        return self._hourly[key]

    def pointer(self, item: FormatModel, fallback: str) -> str:
        try:
            return self.original.pointer(item)
        except KeyError:
            return fallback

    def compare(self, a: FormatModel, b: FormatModel, pointer: str) -> None:
        """Compare two components of the same place in a template, field by field."""
        key = (self.subject, pointer, id(a), id(b))
        if key in self._seen:
            return
        self._seen.add(key)
        model = type(a)
        if not isinstance(b, model) and not isinstance(a, type(b)):
            self.add(pointer, Relevance.SIMULATION, type(a).__name__, type(b).__name__, None)
            return
        for name, field in model.model_fields.items():
            key_name = field.alias or name
            where = f"{pointer}/{_escape(key_name)}"
            if isinstance(a, YearSchedule) and name == "parts":
                self.schedule(a, cast("YearSchedule", b), where)
                continue
            self.value(model, key_name, getattr(a, name), getattr(b, name, None), where)

    def value(self, model: type[FormatModel], key: str, a: object, b: object, where: str) -> None:
        relevance = _umi_relevance(model, key)
        if isinstance(a, FormatModel) and isinstance(b, FormatModel):
            self._via.append(where)
            try:
                self.compare(a, b, self.pointer(a, where))
            finally:
                self._via.pop()
            return
        if isinstance(a, FormatModel) or isinstance(b, FormatModel):
            self.add(where, relevance, a, b, None)
            return
        if isinstance(a, tuple) and isinstance(b, tuple):
            first, second = cast("tuple[object, ...]", a), cast("tuple[object, ...]", b)
            if any(isinstance(item, FormatModel) for item in (*first, *second)):
                if len(first) != len(second):
                    self.add(where, relevance, first, second, None)
                    return
                for position, (x, y) in enumerate(zip(first, second, strict=True)):
                    self.value(model, key, x, y, f"{where}/{position}")
                return
        self.scalar(where, relevance, cast("object", a), cast("object", b))

    def scalar(self, where: str, relevance: Relevance, a: object, b: object) -> None:
        values: tuple[object, object] = (a, b)
        if _is_number(a) and _is_number(b):
            relative = _relative(float(cast("float", a)), float(cast("float", b)))
            if relative != 0.0:
                self.add(where, relevance, a, b, relative)
            return
        if isinstance(a, tuple | list) and isinstance(b, tuple | list):
            first, second = cast("Sequence[object]", a), cast("Sequence[object]", b)
            if len(first) == len(second) and all(
                _is_number(x) and _is_number(y) for x, y in zip(first, second, strict=True)
            ):
                pairs = zip(first, second, strict=True)
                relatives = [_relative(float(cast("float", x)), float(cast("float", y))) for x, y in pairs]
                if all(r == 0.0 for r in relatives):
                    return
                worst = None if None in relatives else max(cast("list[float]", relatives))
                self.add(where, relevance, first, second, worst)
                return
        if _json(values[0]) != _json(values[1]):
            self.add(where, relevance, values[0], values[1], None)

    def schedule(self, a: YearSchedule, b: YearSchedule, where: str) -> None:
        """Compare two year schedules by their hourly values over the reference year."""
        relevance = _umi_relevance(YearSchedule, self._SCHEDULE_PARTS)
        first, second = self.hourly(a), self.hourly(b)
        if isinstance(first, str) or isinstance(second, str):
            if first != second:
                self.add(
                    where,
                    relevance,
                    first if isinstance(first, str) else a.name,
                    second if isinstance(second, str) else b.name,
                    None,
                )
            return
        scale = max(max(map(abs, first), default=0.0), max(map(abs, second), default=0.0))
        worst, hour = 0.0, -1
        for index, (x, y) in enumerate(zip(first, second, strict=True)):
            gap = abs(x - y)
            if gap >= ABS_TOL and gap > worst:
                worst, hour = gap, index
        if hour < 0:
            return
        self.add(
            where,
            relevance,
            {"hour": hour, "value": first[hour]},
            {"hour": hour, "value": second[hour]},
            worst / scale if scale > 0 else None,
        )


def _load(path: str | os.PathLike[str]) -> LibraryIndex:
    raw = dialects.load(path)
    resolution = resolve(raw.document, path)
    return LibraryIndex(resolution.library, raw.document)


def _match_templates(
    originals: Sequence[BuildingTemplate], results: Sequence[BuildingTemplate]
) -> list[BuildingTemplate | None]:
    """Match each original template with a result template by name.

    A template whose name an earlier template already has (renamed ` #2` on reading) is matched
    with the unmatched result template in its place. Any other template with no namesake is
    unmatched.
    """
    free = list(range(len(results)))
    matched: list[BuildingTemplate | None] = [None] * len(originals)
    for index, template in enumerate(originals):
        found = next((i for i in free if results[i].name == template.name), None)
        if found is not None:
            free.remove(found)
            matched[index] = results[found]
    repeated = {
        index for index, template in enumerate(originals) if any(t.name == template.name for t in originals[:index])
    }
    for index in range(len(originals)):
        if matched[index] is not None or index not in repeated:
            continue
        # A repeated name was renamed `<name> #k` on reading; templates skipped before it shift
        # the positions, so the renamed result is found by name first, then by place.
        name = originals[index].name
        renamed = next((i for i in free if (results[i].name or "").startswith(f"{name} #")), None)
        found = renamed if renamed is not None else (index if index in free else None)
        if found is not None:
            free.remove(found)
            matched[index] = results[found]
    return matched


def diff_umi(original: str | os.PathLike[str], result: str | os.PathLike[str], *, rel_tol: float = 1e-4) -> UmiDiff:
    """Compare two UMI libraries field by field (research R16).

    Building templates are matched by name (a repeated name, which reading renames ` #2`, by
    place; a renamed template is missing and extra), and their components through the
    template: the `Perimeter` of a template is compared with the `Perimeter` of its match, and
    so on down to materials. Year schedules
    are compared by their hourly values over the reference year. Components that no template
    of the original uses are matched by type and name. A template, or an unused component,
    with no counterpart is one difference whose other value is `None`; one only in the result
    is located at `/BuildingTemplates/-` or `/<collection>/-`.

    Args:
        original: The original library.
        result: The library to compare with it, for example the original read and written back.
        rel_tol: The relative tolerance of `within_tolerance`; SC-003's 0.01 % by default.

    Returns:
        Every difference, located by JSON pointer in the original.

    Raises:
        UmiFormatError: Either library cannot be read (refused dialect, malformed JSON, broken
            references).
    """
    first, second = _load(original), _load(result)
    comparer = _UmiComparer(first)
    originals, results = first.library.building_templates, second.library.building_templates
    matches = _match_templates(originals, results)
    for template, other in zip(originals, matches, strict=True):
        pointer = first.pointer(template)
        if other is None:
            comparer.subject = template.name or ""
            comparer.add(pointer, Relevance.SIMULATION, template.name, None, None)
            continue
        comparer.subject = other.name or ""
        comparer.compare(template, other, pointer)
    used = {id(other) for other in matches if other is not None}
    for template in results:
        if id(template) not in used:
            comparer.subject = template.name or ""
            comparer.add("/BuildingTemplates/-", Relevance.SIMULATION, None, template.name, None)
    comparer.subject = ""
    _unused(first, second, comparer)
    return UmiDiff(differences=tuple(comparer.found), rel_tol=rel_tol)


def _collections(index: LibraryIndex) -> dict[int, str]:
    """The collection key of each component of a library's collections, by `id`."""
    found: dict[int, str] = {}
    for name, field in type(index.library).model_fields.items():
        for item in cast("tuple[FormatModel, ...]", getattr(index.library, name)):
            found.setdefault(id(item), field.alias or name)
    return found


def _unused(first: LibraryIndex, second: LibraryIndex, comparer: _UmiComparer) -> None:
    """Compare the components no template of the original uses with the result's, by type and name.

    A component no template of the result uses and no unused component of the original matches
    is a difference located at `/<collection>/-`, with no original value.
    """
    by_name: dict[tuple[type, str | None], FormatModel] = {}
    for item, _ in second.components():
        # Only the result's unused components: a used one is compared through its template.
        if isinstance(item, LibraryComponent) and not second.users(item):
            by_name.setdefault((type(item), item.name), item)
    matched: set[int] = set()
    for item, pointer in first.components():
        if first.users(item) or not isinstance(item, LibraryComponent):
            continue
        other = by_name.get((type(item), item.name))
        if other is None:
            comparer.add(pointer, Relevance.DESCRIPTIVE, item.name, None, None)
        else:
            matched.add(id(other))
            comparer.compare(item, other, pointer)
    collections = _collections(second)
    for item, _ in second.components():
        if second.users(item) or id(item) in matched or not isinstance(item, LibraryComponent):
            continue
        comparer.add(f"/{collections[id(item)]}/-", Relevance.DESCRIPTIVE, None, item.name, None)


# --- SBEM ------------------------------------------------------------------------------------------


@cache
def _sbem_relevance_table() -> dict[str, Relevance]:
    """Map each SBEM path suffix of `CORRESPONDENCE` to the most simulation-relevant row's relevance."""
    order = {Relevance.SIMULATION: 0, Relevance.LIFE_CYCLE: 1, Relevance.DESCRIPTIVE: 2}
    table: dict[str, Relevance] = {}
    for row in CORRESPONDENCE:
        for path in row.sbem_paths:
            field = path.rsplit(".", 1)[-1]
            for key in (path, field):
                known = table.get(key)
                if known is None or order[row.relevance] < order[known]:
                    table[key] = row.relevance
    return table


_DESCRIPTIVE_FIELDS: Final = frozenset({
    "Name",
    "Category",
    "Comment",
    "Comments",
    "DataSource",
    "Version",
    "Authors",
    "AuthorEmails",
    "SchemaVersion",
})


def _sbem_relevance(path: str) -> Relevance:
    # A list element (`archetype.Authors.0`) has its list's relevance.
    parts = path.split(".")
    while len(parts) > 1 and parts[-1].isdigit():
        parts.pop()
    path = ".".join(parts)
    field = parts[-1].split("[", 1)[0]
    if field in _DESCRIPTIVE_FIELDS:
        return Relevance.DESCRIPTIVE
    table = _sbem_relevance_table()
    for prefix in (path, field):
        if prefix in table:
            return table[prefix]
    return Relevance.SIMULATION


class _SbemComparer:
    def __init__(self) -> None:
        self.found: list[Difference] = []
        self.subject = ""

    def add(self, path: str, a: object, b: object, relative: float | None) -> None:
        self.found.append(Difference(path, _sbem_relevance(path), _json(a), _json(b), relative, self.subject))

    def walk(self, first: object, second: object, path: str) -> None:
        a, b = first, second
        if isinstance(a, BaseModel) and isinstance(b, BaseModel):
            self.models(a, b, path)
        elif isinstance(a, Mapping) and isinstance(b, Mapping):
            self.mappings(cast("Mapping[object, object]", a), cast("Mapping[object, object]", b), path)
        elif isinstance(a, list | tuple) and isinstance(b, list | tuple):
            self.sequences(cast("Sequence[object]", a), cast("Sequence[object]", b), path)
        elif _is_number(first) and _is_number(second):
            relative = _relative(float(cast("float", first)), float(cast("float", second)))
            if relative != 0.0:
                self.add(path, first, second, relative)
        elif _json(first) != _json(second):
            self.add(path, first, second, None)

    def models(self, a: BaseModel, b: BaseModel, path: str) -> None:
        if type(a) is not type(b):
            self.add(path, type(a).__name__, type(b).__name__, None)
            return
        for name in type(a).model_fields:
            self.walk(getattr(a, name), getattr(b, name), f"{path}.{name}" if path else name)

    def mappings(self, first: Mapping[object, object], second: Mapping[object, object], path: str) -> None:
        for key in dict.fromkeys([*first, *second]):
            where = f"{path}.{key}"
            if key not in first or key not in second:
                self.add(where, first.get(key), second.get(key), None)
            else:
                self.walk(first[key], second[key], where)

    def sequences(self, first: Sequence[object], second: Sequence[object], path: str) -> None:
        if len(first) != len(second):
            self.add(path, first, second, None)
            return
        for index, (x, y) in enumerate(zip(first, second, strict=True)):
            self.walk(x, y, f"{path}.{index}")


def _match_groups(
    originals: Sequence[ZoneGroup], results: Sequence[ZoneGroup]
) -> tuple[list[ZoneGroup | None], list[ZoneGroup]]:
    """Match each original group with a result group, by name, then by exposure; return the rest too."""
    free = list(results)
    matched: list[ZoneGroup | None] = []
    for group in originals:
        found = next((g for g in free if g.Name == group.Name), None)
        matched.append(found)
        if found is not None:
            free.remove(found)
    for index, group in enumerate(originals):
        if matched[index] is None and group.Exposure is not None:
            found = next((g for g in free if g.Exposure == group.Exposure), None)
            if found is not None:
                free.remove(found)
                matched[index] = found
    return matched, free


def diff_archetypes(a: Archetype, b: Archetype, *, rel_tol: float = 0.0) -> ArchetypeDiff:
    """Compare two SBEM archetypes field by field (SC-004).

    Zone groups are matched by name, then by exposure (UMI names its zones `core` and
    `perimeter`); a group's fields are located as
    `<group name>.<field path below its ZoneComponent>` and building-level fields as
    `archetype.<field>`, as in the translation report. A group with no counterpart is one
    difference whose other value is `None`.

    Args:
        a: The original archetype.
        b: The archetype to compare with it, for example `a` written to UMI and read back.
        rel_tol: The relative tolerance of `within_tolerance`; exact by default.

    Returns:
        Every difference, in field order.
    """
    comparer = _SbemComparer()
    comparer.subject = a.Name
    for name in type(a).model_fields:
        if name == "Groups":
            continue
        comparer.walk(getattr(a, name), getattr(b, name), f"archetype.{name}")
    matched, extra = _match_groups(a.Groups, b.Groups)
    for group, other in zip(a.Groups, matched, strict=True):
        if other is None:
            comparer.add(group.Name, group.Name, None, None)
            continue
        for name in ("Name", "FloorAreaShare", "Exposure"):
            comparer.walk(getattr(group, name), getattr(other, name), f"{group.Name}.{name}")
        comparer.walk(group.Zone, other.Zone, group.Name)
    for group in extra:
        comparer.add(group.Name, None, group.Name, None)
    return ArchetypeDiff(differences=tuple(comparer.found), rel_tol=rel_tol)
