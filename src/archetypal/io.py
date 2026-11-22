"""Deterministic archetype and report files (spec 002, research R14; contracts/reduction-report.md).

A reduction writes two files side by side:

- `<name>.sbem.json`: the archetype, as epinterface's pydantic JSON (fields in model order);
- `<name>.report.json`: the reduction report.

Both are written with the same encoding, so equal inputs give byte-identical files (FR-005):

- UTF-8, two-space indent, a final newline;
- object keys in model order (arrays in the order the model holds them: the report builder
  sorts them by group key, then zone name);
- floats as their shortest round-trip `repr`, and non-finite floats refused;
- no timestamp;
- profiles as `EncodedProfile`: base64 of little-endian float64 values, with their length.

The functions take any pydantic model, so they serve the SBEM fork's archetype model as well
as archetypal's report.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Literal, TypeVar

import numpy as np
from pydantic import BaseModel, ConfigDict, model_validator

from .errors import InputError, ReductionError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from numpy.typing import NDArray

__all__ = [
    "ARCHETYPE_SUFFIX",
    "REPORT_SUFFIX",
    "EncodedProfile",
    "dumps",
    "read",
    "read_model",
    "report_path_for",
    "write",
    "write_model",
]

ARCHETYPE_SUFFIX = ".sbem.json"
"""The suffix of an archetype file."""

REPORT_SUFFIX = ".report.json"
"""The suffix of a report file."""

_FLOAT64_LE = np.dtype("<f8")

ArchetypeT = TypeVar("ArchetypeT", bound=BaseModel)
ReportT = TypeVar("ReportT", bound=BaseModel)
ModelT = TypeVar("ModelT", bound=BaseModel)


class EncodedProfile(BaseModel):
    """A profile (for example 8760 hourly values) stored compactly in a JSON file.

    Attributes:
        encoding: Always `"base64-float64-le"`: the values as little-endian IEEE 754 float64,
            base64-encoded (RFC 4648, with padding).
        length: The number of values.
        data: The base64 text.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    encoding: Literal["base64-float64-le"] = "base64-float64-le"
    length: int
    data: str

    @model_validator(mode="after")
    def _check_length(self) -> EncodedProfile:
        size = len(base64.b64decode(self.data, validate=True))
        if size != self.length * _FLOAT64_LE.itemsize:
            msg = f"profile data holds {size} bytes, not the {self.length * _FLOAT64_LE.itemsize} its length {self.length} needs"
            raise ValueError(msg)
        return self

    @classmethod
    def from_values(cls, values: Sequence[float] | NDArray[np.floating]) -> EncodedProfile:
        """Encode a sequence of finite floats.

        Args:
            values: The profile.

        Returns:
            The encoded profile.

        Raises:
            ValueError: If a value is not finite.
        """
        array = np.asarray(values, dtype=_FLOAT64_LE)
        if not bool(np.isfinite(array).all()):
            msg = "profile values must be finite"
            raise ValueError(msg)
        data = base64.b64encode(array.tobytes()).decode("ascii")
        return cls(length=int(array.size), data=data)

    def to_array(self) -> NDArray[np.float64]:
        """Decode the profile.

        Returns:
            A new, writable float64 array in native byte order.
        """
        raw = base64.b64decode(self.data, validate=True)
        view = np.ndarray(shape=(len(raw) // _FLOAT64_LE.itemsize,), dtype=_FLOAT64_LE, buffer=raw)
        return view.astype(np.float64)


def dumps(model: BaseModel) -> str:
    """Return a model's deterministic JSON text (the encoding rules of this module).

    Args:
        model: Any pydantic model: an archetype, a report.

    Returns:
        The JSON text, ending with a newline.

    Raises:
        ValueError: If the model holds a non-finite float (JSON cannot hold it).
    """
    data = model.model_dump(mode="json")
    try:
        text = json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False, sort_keys=False)
    except ValueError as exc:
        msg = f"{type(model).__name__}: every float must be finite to be written as JSON ({exc})"
        raise ValueError(msg) from exc
    return text + "\n"


def _refuse_existing(path: Path, overwrite: bool) -> None:
    if not overwrite and path.exists():
        raise InputError(path, "already exists; pass overwrite=True to replace it")


def write_model(model: BaseModel, path: str | os.PathLike[str], *, overwrite: bool = False) -> Path:
    """Write one model as deterministic JSON.

    Args:
        model: The model to write.
        path: The file to write.
        overwrite: Replace an existing file.

    Returns:
        The path written.

    Raises:
        InputError: If the file exists and `overwrite` is false.
    """
    target = Path(path)
    _refuse_existing(target, overwrite)
    text = dumps(model)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(text.encode("utf-8"))
    return target


def _check_name(name: str) -> None:
    bad = (
        not name
        or name in {".", ".."}
        or "/" in name
        or "\\" in name
        or os.sep in name
        or name.endswith(".json")
    )
    if bad:
        raise InputError(name or "''", "is not a file name stem; give a name such as 'office' (no directory, no suffix)")


def write(
    archetype: BaseModel,
    report: BaseModel,
    directory: str | os.PathLike[str],
    name: str,
    *,
    overwrite: bool = False,
) -> tuple[Path, Path]:
    """Write `<name>.sbem.json` and `<name>.report.json` in a directory.

    Neither file is written when either exists and `overwrite` is false.

    Args:
        archetype: The archetype (epinterface's model).
        report: The reduction report.
        directory: The directory, created if needed.
        name: The file name stem.
        overwrite: Replace existing files.

    Returns:
        The archetype path and the report path.

    Raises:
        InputError: If `name` is not a plain stem, or a file exists and `overwrite` is false.
    """
    _check_name(name)
    folder = Path(directory)
    archetype_path = folder / f"{name}{ARCHETYPE_SUFFIX}"
    report_path = folder / f"{name}{REPORT_SUFFIX}"
    for path in (archetype_path, report_path):
        _refuse_existing(path, overwrite)
    archetype_text, report_text = dumps(archetype), dumps(report)
    folder.mkdir(parents=True, exist_ok=True)
    archetype_path.write_bytes(archetype_text.encode("utf-8"))
    report_path.write_bytes(report_text.encode("utf-8"))
    return archetype_path, report_path


def read_model(model_type: type[ModelT], path: str | os.PathLike[str]) -> ModelT:
    """Read one model from a JSON file.

    Args:
        model_type: The pydantic model class to validate with.
        path: The file to read.

    Returns:
        The validated model.
    """
    return model_type.model_validate_json(Path(path).read_bytes())


def report_path_for(archetype_path: str | os.PathLike[str]) -> Path:
    """Return the report path beside an archetype file: `<name>.report.json` for `<name>.sbem.json`.

    Args:
        archetype_path: The archetype file.

    Returns:
        The report file's path.
    """
    path = Path(archetype_path)
    name = path.name
    for suffix in (ARCHETYPE_SUFFIX, ".json"):
        if name.endswith(suffix):
            name = name[: -len(suffix)]
            break
    return path.with_name(f"{name}{REPORT_SUFFIX}")


def read(
    archetype_type: type[ArchetypeT],
    report_type: type[ReportT],
    archetype_path: str | os.PathLike[str],
    report_path: str | os.PathLike[str] | None = None,
) -> tuple[ArchetypeT, ReportT]:
    """Read an archetype and its report.

    Args:
        archetype_type: The archetype's model class.
        report_type: The report's model class.
        archetype_path: The `<name>.sbem.json` file.
        report_path: The report file; `None` reads `<name>.report.json` beside the archetype.

    Returns:
        The archetype and the report.

    Raises:
        ReductionError: If the report file does not exist.
    """
    report_file = report_path_for(archetype_path) if report_path is None else Path(report_path)
    if not report_file.is_file():
        raise ReductionError(report_file, "no reduction report; an archetype is read with the report written beside it")
    return read_model(archetype_type, archetype_path), read_model(report_type, report_file)
