"""UMI library dialects: which kind of file a library is, from its shape (spec 003, research R2).

UMI libraries carry no version number, so the reader recognises the dialect from the keys the
file holds:

| Dialect | Recognised by | Outcome |
|---|---|---|
| `core-json` | JSON with UMI's collections and any of `AdvancedModel`, `UseAdvancedModel` or a hot-water `FuelType` | Read. |
| `core-json-pre-2023` | The same, with none of those fields | Read; each absent field takes Basilisk's default. |
| `archsim-json` | Materials carrying `GasType`, `Life` or `Comment` | Read through the Archsim key map. |
| Legacy or Core XML, a `.umi` project | An XML root, or a zip archive | Refused, naming the dialect. |

The Archsim key map renames `Comment` to `Comments`, turns `GasType` 0–4 into the gas names
`AIR`, `ARGON`, `KRYPTON`, `XENON` and `SF6` (the gas's own `Type: "Gas"` is ignored), and moves
a material's `Type` to its `Category`. The keys of the collections' objects that have no Core
counterpart (`Life`, `EmbodiedEnergyStdDev`, `PhaseChange`, `Optical`, …) are removed and listed
in `RawLibrary.lost`, so the reader can report them as lost.
"""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Final, cast

from archetypal.errors import Problem, UmiFormatError
from archetypal.umi._format import UmiLibrary

if TYPE_CHECKING:
    import os

__all__ = [
    "ARCHSIM_JSON",
    "COLLECTIONS",
    "CORE_JSON",
    "CORE_JSON_PRE_2023",
    "RawLibrary",
    "detect",
    "from_document",
    "load",
    "parse",
]

CORE_JSON: Final = "core-json"
"""The current Core JSON of Basilisk, with the fields added in 2023."""

CORE_JSON_PRE_2023: Final = "core-json-pre-2023"
"""Core JSON written before 2023: no `AdvancedModel`, `UseAdvancedModel` or hot-water `FuelType`."""

ARCHSIM_JSON: Final = "archsim-json"
"""The Archsim-era JSON: materials with `GasType`, `Life` or `Comment`."""

COLLECTIONS: Final[tuple[str, ...]] = tuple(field.alias or name for name, field in UmiLibrary.model_fields.items())
"""The 17 collection keys of a UMI library, in the order Basilisk writes them."""

LEGACY_XML_MESSAGE: Final = (
    "Legacy UMI XML library is not supported; open and save it in UMI to convert it to JSON"
)

_MATERIALS: Final = ("GasMaterials", "GlazingMaterials", "OpaqueMaterials")
_ARCHSIM_MARKERS: Final = frozenset({"GasType", "Life", "Comment"})
_GASES: Final = ("AIR", "ARGON", "KRYPTON", "XENON", "SF6")
_ZIP_MAGIC: Final = b"PK\x03\x04"

Json = dict[str, object]


@dataclass(frozen=True)
class RawLibrary:
    """A library file read as JSON, in its dialect, before references are resolved.

    Attributes:
        dialect: The dialect recognised (`CORE_JSON`, `CORE_JSON_PRE_2023` or `ARCHSIM_JSON`).
        document: The library as Core JSON, keys in file order (the Archsim key map applied).
        sha256: The SHA-256 of the bytes read.
        lost: Each Archsim key with no Core counterpart, as `(JSON pointer, value)`, in file
            order; removed from `document`.
    """

    dialect: str
    document: Json
    sha256: str
    lost: tuple[tuple[str, object], ...] = ()


def _refuse(subject: str | os.PathLike[str], message: str, problems: tuple[Problem, ...] = ()) -> UmiFormatError:
    return UmiFormatError(subject, message, problems)


def _objects(document: Json, collection: str) -> list[Json]:
    value = document.get(collection)
    if not isinstance(value, list):
        return []
    return [cast("Json", item) for item in cast("list[object]", value) if isinstance(item, dict)]


def detect(document: Json) -> str:
    """Return the dialect of a parsed library from its shape (research R2).

    Args:
        document: The library as parsed from JSON; it must hold a UMI collection.

    Returns:
        `ARCHSIM_JSON` when a material carries `GasType`, `Life` or `Comment`; else `CORE_JSON`
        when a structure carries `AdvancedModel` or `UseAdvancedModel` or a hot-water setting a
        `FuelType`; else `CORE_JSON_PRE_2023`.
    """
    if any(_ARCHSIM_MARKERS & item.keys() for collection in _MATERIALS for item in _objects(document, collection)):
        return ARCHSIM_JSON
    structures = _objects(document, "StructureDefinitions")
    if any({"AdvancedModel", "UseAdvancedModel"} & item.keys() for item in structures) or any(
        "FuelType" in item for item in _objects(document, "DomesticHotWaterSettings")
    ):
        return CORE_JSON
    return CORE_JSON_PRE_2023


def _known_keys() -> dict[str, frozenset[str]]:
    """The Core keys of each collection's objects."""
    known: dict[str, frozenset[str]] = {}
    for name, field in UmiLibrary.model_fields.items():
        item = cast("tuple[type, ...]", getattr(field.annotation, "__args__", ()))
        model = item[0] if item else None
        keys = getattr(model, "model_fields", {})
        known[field.alias or name] = frozenset({"$id", "$ref", *(info.alias or key for key, info in keys.items())})
    return known


def _archsim_object(item: Json, collection: str, known: frozenset[str], pointer: str) -> tuple[Json, list[tuple[str, object]]]:
    """Map one Archsim object to Core keys; return it and the keys without a counterpart."""
    material = collection in _MATERIALS
    mapped: Json = {}
    lost: list[tuple[str, object]] = []
    for key, value in item.items():
        if key == "Comment" and "Comments" not in item:
            mapped["Comments"] = value
        elif material and key == "GasType":
            mapped["Type"] = _GASES[value] if isinstance(value, int) and 0 <= value < len(_GASES) else value
        elif material and key == "Type":
            if collection != "GasMaterials" and "Category" not in item:
                mapped["Category"] = value
            # A gas's own `Type` ("Gas") is ignored: `GasType` gives the gas.
            elif collection == "GasMaterials" and "GasType" not in item:
                mapped["Type"] = value
        elif key in known:
            mapped[key] = value
        else:
            lost.append((f"{pointer}/{key.replace('~', '~0').replace('/', '~1')}", value))
    return mapped, lost


def _apply_archsim_map(document: Json) -> tuple[Json, tuple[tuple[str, object], ...]]:
    known = _known_keys()
    mapped: Json = {}
    lost: list[tuple[str, object]] = []
    for collection, value in document.items():
        if collection not in known or not isinstance(value, list):
            mapped[collection] = value
            continue
        items: list[object] = []
        for index, item in enumerate(cast("list[object]", value)):
            if isinstance(item, dict) and "$ref" not in item:
                item_map, item_lost = _archsim_object(
                    cast("Json", item), collection, known[collection], f"/{collection}/{index}"
                )
                items.append(item_map)
                lost.extend(item_lost)
            else:
                items.append(item)
        mapped[collection] = items
    return mapped, tuple(lost)


def from_document(document: object, subject: str | os.PathLike[str], *, sha256: str) -> RawLibrary:
    """Recognise the dialect of a parsed library and bring it to Core JSON.

    Args:
        document: The library as parsed from JSON, keys in file order.
        subject: The library path, for errors.
        sha256: The SHA-256 of the bytes it was parsed from.

    Returns:
        The library in Core JSON, with its dialect.

    Raises:
        UmiFormatError: The document is not a JSON object holding a UMI collection.
    """
    if not isinstance(document, dict) or not any(key in COLLECTIONS for key in cast("Json", document)):
        found = f"a JSON {type(document).__name__}" if not isinstance(document, dict) else "no UMI collection"
        message = (
            f"not a UMI template library: it holds {found}; a library is a JSON object with collections such as "
            f"{', '.join(COLLECTIONS[:3])}, …, BuildingTemplates"
        )
        raise _refuse(subject, message)
    library = cast("Json", document)
    dialect = detect(library)
    lost: tuple[tuple[str, object], ...] = ()
    if dialect == ARCHSIM_JSON:
        library, lost = _apply_archsim_map(library)
    return RawLibrary(dialect=dialect, document=library, sha256=sha256, lost=lost)


def _refuse_zip(data: bytes, subject: str | os.PathLike[str]) -> UmiFormatError:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            members = [name for name in archive.namelist() if name.lower().endswith(".json")]
    except zipfile.BadZipFile:
        members = []
    named = ", ".join(members) if members else "the library's .json file"
    return _refuse(
        subject,
        f"a UMI project (.umi) is a zip archive, not a library; extract {named} from it and read that file",
    )


def _refuse_xml(text: str, subject: str | os.PathLike[str]) -> UmiFormatError:
    if "<LibSerializable" in text[:4096]:
        return _refuse(subject, LEGACY_XML_MESSAGE)
    return _refuse(subject, "UMI XML library is not supported; open and save it in UMI to convert it to JSON")


def parse(data: bytes, subject: str | os.PathLike[str]) -> RawLibrary:
    """Read the bytes of a library file and recognise its dialect.

    Args:
        data: The file's bytes.
        subject: The library path, for errors.

    Returns:
        The library in Core JSON, with its dialect and the SHA-256 of `data`.

    Raises:
        UmiFormatError: The file is a `.umi` project, XML, malformed JSON or not a UMI library.
    """
    sha256 = hashlib.sha256(data).hexdigest()
    if data.startswith(_ZIP_MAGIC):
        raise _refuse_zip(data, subject)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        problem = Problem(pointer="", template=None, rule="format.encoding", message=str(error))
        raise _refuse(subject, "the library is not UTF-8 text", (problem,)) from error
    if text.lstrip().startswith("<"):
        raise _refuse_xml(text, subject)
    try:
        document: object = json.loads(text)
    except json.JSONDecodeError as error:
        problem = Problem(
            pointer="",
            template=None,
            rule="format.json",
            message=f"{error.msg} at line {error.lineno}, column {error.colno}",
        )
        raise _refuse(subject, "the library is not valid JSON", (problem,)) from error
    return from_document(document, subject, sha256=sha256)


def load(path: str | os.PathLike[str]) -> RawLibrary:
    """Read a library file and recognise its dialect.

    Args:
        path: The library file.

    Returns:
        The library in Core JSON, with its dialect.

    Raises:
        UmiFormatError: The file cannot be read, or is refused (`parse`).
    """
    try:
        data = Path(path).read_bytes()
    except OSError as error:
        raise _refuse(path, f"the file cannot be read ({error.strerror or error})") from error
    return parse(data, path)
