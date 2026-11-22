"""References in UMI libraries: `$id` and `$ref` (spec 003, research R1 and R13).

Private module (roadmap C-02). Basilisk writes each shared component once, with a `$id`, and
refers to it later with `{"$ref": id}`; it turns a reference it cannot follow into `null`
without a word. Here:

- `scan_references` walks the raw JSON in file order and reports every broken reference as a
  format problem with its JSON pointer;
- `resolve` builds the format model of `archetypal.umi._format`, so that a reference becomes
  the very object it names, never `None`;
- `dump_library` writes a format model back as Basilisk JSON, numbering components `"1"`,
  `"2"`, … in document order, defining each at its first occurrence and referring back to it
  afterwards.
"""

from __future__ import annotations

import types
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Union, cast, get_args, get_origin

from pydantic import ValidationError

from archetypal.errors import Problem, UmiFormatError
from archetypal.umi._format import BuildingTemplate, ConstructionSystem, FormatModel, LibraryComponent, UmiLibrary

if TYPE_CHECKING:
    import os

__all__: list[str] = []

_Json = dict[str, object]


def _escape(key: str) -> str:
    """Escape one JSON pointer token (RFC 6901)."""
    return key.replace("~", "~0").replace("/", "~1")


def _child(pointer: str, key: str | int) -> str:
    return f"{pointer}/{_escape(key) if isinstance(key, str) else key}"


# --- Pre-scan ----------------------------------------------------------------------------


def _all_ids(value: object, found: set[str]) -> set[str]:
    """Every string `$id` in a JSON value, wherever it is."""
    if isinstance(value, dict):
        for key, item in cast("_Json", value).items():
            if key == "$id" and isinstance(item, str):
                found.add(item)
            else:
                _all_ids(item, found)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            _all_ids(item, found)
    return found


class _Scan:
    """One pass over the raw JSON in file order, as research R1 describes."""

    def __init__(self, document: _Json) -> None:
        self.defined = _all_ids(document, set())
        self.seen: set[str] = set()
        self.problems: list[Problem] = []

    def problem(self, pointer: str, rule: str, message: str) -> None:
        self.problems.append(Problem(pointer=pointer, template=None, rule=rule, message=message))

    def walk(self, value: object, pointer: str) -> None:
        if isinstance(value, dict):
            self.walk_object(cast("_Json", value), pointer)
        elif isinstance(value, list):
            for index, item in enumerate(cast("list[object]", value)):
                self.walk(item, _child(pointer, index))

    def walk_object(self, obj: _Json, pointer: str) -> None:
        for index, (key, item) in enumerate(obj.items()):
            if key == "$id":
                self.check_id(item, index, pointer)
            elif key == "$ref":
                self.check_ref(item, pointer)
            else:
                self.walk(item, _child(pointer, key))
        if "$ref" in obj and len(obj) != 1:
            others = ", ".join(sorted(k for k in obj if k != "$ref"))
            self.problem(pointer, "refs.ref-extra-keys", f'an object holding "$ref" has other keys ({others})')

    def check_id(self, value: object, index: int, pointer: str) -> None:
        if index != 0:
            self.problem(pointer, "refs.id-not-first", '"$id" is not the first key of its object')
        if not isinstance(value, str):
            self.problem(pointer, "refs.id-not-string", f'"$id" {value!r} is not a string')
        elif value in self.seen:
            self.problem(pointer, "refs.duplicate-id", f'"$id" "{value}" is already defined earlier in the file')
        else:
            self.seen.add(value)

    def check_ref(self, value: object, pointer: str) -> None:
        if not isinstance(value, str):
            self.problem(pointer, "refs.ref-not-string", f'"$ref" {value!r} is not a string')
        elif value not in self.seen:
            if value in self.defined:
                self.problem(pointer, "refs.forward", f'"$ref" "{value}" points to an "$id" defined later in the file')
            else:
                self.problem(pointer, "refs.dangling", f'"$ref" "{value}" points to no "$id"')


def scan_references(document: object) -> list[Problem]:
    """Check the references of a parsed library against research R1's rules.

    Each `$id` is a string, the first key of its object and unique; each `$ref` is a string,
    alone in its object, and names an `$id` seen earlier in the file.

    Args:
        document: The library as parsed from JSON, keys in file order.

    Returns:
        Every problem found, in file order, each pointing at the object that holds the key.
    """
    if not isinstance(document, dict):
        return [
            Problem(pointer="", template=None, rule="format.not-object", message="the library is not a JSON object")
        ]
    obj = cast("_Json", document)
    scan = _Scan(obj)
    scan.walk_object(obj, "")
    return scan.problems


# --- Resolution --------------------------------------------------------------------------


@dataclass(frozen=True)
class Resolution:
    """A library resolved into the format model.

    Attributes:
        library: The library; each reference is the object it names.
        defaulted: JSON pointers of the keys that were absent and took Basilisk's default,
            recorded where each object is defined.
        unknown_keys: Each key the format does not know, as `(JSON pointer, value)`.
    """

    library: UmiLibrary
    defaulted: tuple[str, ...]
    unknown_keys: tuple[tuple[str, object], ...]


class _Failed:
    """Marks a value that could not be built; its problem is already recorded."""


_FAILED = _Failed()


def _model_classes(annotation: object) -> tuple[type[FormatModel], ...]:
    """The format models an annotation admits, outside any tuple (`X | None` gives `(X,)`)."""
    if isinstance(annotation, type) and issubclass(annotation, FormatModel):
        return (annotation,)
    if get_origin(annotation) in {Union, types.UnionType}:
        found: list[type[FormatModel]] = []
        for arg in cast("tuple[object, ...]", get_args(annotation)):
            found.extend(_model_classes(arg))
        return tuple(found)
    return ()


def _tuple_item(annotation: object) -> object | None:
    """The item type of `tuple[X, ...]`, else None."""
    if get_origin(annotation) is tuple:
        return cast("tuple[object, ...]", get_args(annotation))[0]
    return None


def _collection_classes() -> dict[str, tuple[str, type[FormatModel]]]:
    """Each collection key with its field name and item class."""
    found: dict[str, tuple[str, type[FormatModel]]] = {}
    for name, field in UmiLibrary.model_fields.items():
        (item,) = _model_classes(_tuple_item(field.annotation))
        found[field.alias or name] = (name, item)
    return found


_COLLECTIONS = _collection_classes()


class _Builder:
    """Builds format models from raw JSON in file order, following `$ref` to built objects."""

    def __init__(self) -> None:
        self.index: dict[str, FormatModel] = {}
        self.failed_ids: set[str] = set()
        self.problems: list[Problem] = []
        self.defaulted: list[str] = []
        self.unknown: list[tuple[str, object]] = []

    def problem(self, pointer: str, rule: str, message: str) -> None:
        self.problems.append(Problem(pointer=pointer, template=None, rule=rule, message=message))

    def value(self, annotation: object, raw: object, pointer: str) -> object:
        """Build one field value: models are built, references followed, scalars passed on."""
        item = _tuple_item(annotation)
        if item is not None:
            if not _model_classes(item) or not isinstance(raw, list):
                return raw
            built = [
                self.value(item, element, _child(pointer, i)) for i, element in enumerate(cast("list[object]", raw))
            ]
            return _FAILED if any(b is _FAILED for b in built) else tuple(built)
        classes = _model_classes(annotation)
        if not classes or not isinstance(raw, dict):
            return raw
        obj = cast("_Json", raw)
        if "$ref" in obj:
            return self.follow(cast("str", obj["$ref"]), classes, pointer)
        if len(classes) == 1:
            return self.model(classes[0], obj, pointer)
        names = " or ".join(c.__name__ for c in classes)
        self.problem(pointer, "refs.inline-ambiguous", f"a {names} must be given by reference here")
        return _FAILED

    def follow(self, ref: str, classes: tuple[type[FormatModel], ...], pointer: str) -> object:
        """The object a `$ref` names, checked against the classes the field admits."""
        if ref in self.failed_ids:
            return _FAILED
        target = self.index.get(ref)
        if target is None:
            self.problem(pointer, "refs.enclosing", f'"$ref" "{ref}" points to an object that encloses it')
            return _FAILED
        if not isinstance(target, classes):
            expected = " or ".join(c.__name__ for c in classes)
            self.problem(
                pointer,
                "refs.wrong-class",
                f'"$ref" "{ref}" points to a {type(target).__name__}, where a {expected} is expected',
            )
            return _FAILED
        return target

    def model(self, cls: type[FormatModel], obj: _Json, pointer: str) -> object:
        """Build one object of class `cls`, and index it under its `$id`."""
        fields = {field.alias or name: field for name, field in cls.model_fields.items()}
        data: _Json = {}
        failed = False
        for key, raw in obj.items():
            if key == "$id":
                continue
            field = fields.get(key)
            if field is None:
                self.unknown.append((_child(pointer, key), raw))
                continue
            data[key] = self.value(field.annotation, raw, _child(pointer, key))
            failed = failed or data[key] is _FAILED
        self.defaulted.extend(_child(pointer, key) for key in fields if key not in obj)
        ident = obj.get("$id")
        built = _FAILED if failed else self.validate(cls, data, pointer)
        if isinstance(ident, str):
            if isinstance(built, FormatModel):
                self.index[ident] = built
            else:
                self.failed_ids.add(ident)
        return built

    def validate(self, cls: type[FormatModel], data: _Json, pointer: str) -> object:
        try:
            return cls.model_validate(data)
        except ValidationError as error:
            for detail in error.errors():
                where = pointer
                for part in detail["loc"]:
                    where = _child(where, part)
                self.problem(where, "format.value", detail["msg"])
            return _FAILED


def resolve(document: object, subject: str | os.PathLike[str]) -> Resolution:
    """Resolve a parsed library into the format model.

    Collections are read in file order, so window settings resolve whether they are defined
    inline in the first template that uses them (Basilisk's order) or in the `WindowSettings`
    collection written before the templates (v2's order). A missing collection is empty.

    Args:
        document: The library as parsed from JSON, keys in file order.
        subject: The library path, for the error.

    Returns:
        The library, with the keys that were defaulted or unknown.

    Raises:
        UmiFormatError: A reference breaks research R1's rules, points to an object of the
            wrong class, or a value does not convert. Every such problem is listed.
    """
    problems = scan_references(document)
    if problems:
        raise UmiFormatError(subject, "the library's references are broken", problems)
    builder = _Builder()
    collections: _Json = {}
    for key, raw in cast("_Json", document).items():
        if key not in _COLLECTIONS:
            builder.unknown.append((_child("", key), raw))
            continue
        _, item = _COLLECTIONS[key]
        collections[key] = builder.value(tuple[item, ...], raw, _child("", key))
    builder.defaulted.extend(_child("", key) for key in _COLLECTIONS if key not in collections)
    library = _FAILED
    if not builder.problems and not any(value is _FAILED for value in collections.values()):
        library = builder.validate(UmiLibrary, collections, "")
    if builder.problems or not isinstance(library, UmiLibrary):
        raise UmiFormatError(subject, "the library does not convert to Basilisk's classes", builder.problems)
    return Resolution(library=library, defaulted=tuple(builder.defaulted), unknown_keys=tuple(builder.unknown))


# --- Writing -----------------------------------------------------------------------------


def _has_id(model: FormatModel) -> bool:
    """Whether Basilisk gives objects of this class a `$id` (templates have none)."""
    return isinstance(model, (LibraryComponent, ConstructionSystem)) and not isinstance(model, BuildingTemplate)


class _Writer:
    def __init__(self) -> None:
        self.ids: dict[tuple[type[FormatModel], FormatModel], str] = {}

    def model(self, model: FormatModel) -> _Json:
        out: _Json = {}
        if _has_id(model):
            key = (type(model), model)
            if key in self.ids:
                return {"$ref": self.ids[key]}
            self.ids[key] = out["$id"] = str(len(self.ids) + 1)
        for name, alias in type(model).basilisk_keys():
            out[alias] = self.value(getattr(model, name))
        return out

    def value(self, value: object) -> object:
        if isinstance(value, FormatModel):
            return self.model(value)
        if isinstance(value, tuple):
            return [self.value(item) for item in cast("tuple[object, ...]", value)]
        if isinstance(value, Enum):
            return int(value) if isinstance(value, int) else value.value
        return value


def dump_library(library: UmiLibrary) -> dict[str, object]:
    """Write a library as Basilisk JSON, with `$id` and `$ref` (research R13).

    Components are numbered `"1"`, `"2"`, … in document order: the 17 collections in Basilisk's
    order, keys in Basilisk's order. Each component is defined, with its `$id` first, at its
    first occurrence, and every later occurrence is `{"$ref": id}`. Two components are the
    same when they are equal (same class, name and content). Building templates have no
    `$id`, so window settings are defined inline in the first template that uses them.
    Enums are written as integers, structural enums by name.

    Args:
        library: The library to write.

    Returns:
        The library as a JSON value, ready for `json.dumps`.
    """
    return _Writer().model(library)
