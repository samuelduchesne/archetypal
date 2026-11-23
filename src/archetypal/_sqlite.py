"""Open EnergyPlus SQLite results read-only, whatever characters their path holds.

Kept apart from `archetypal.reduction` so that `archetypal.comparison`, which `import archetypal`
loads, reads results without loading the reduction (and epinterface).
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, TypeVar
from urllib.parse import quote

if TYPE_CHECKING:
    import os

    from idfkit.simulation import SQLResult

__all__ = ["open_results"]

_SQL = TypeVar("_SQL", bound="SQLResult")


def open_results(path: str | os.PathLike[str], kind: type[_SQL]) -> _SQL:
    """Open an EnergyPlus SQLite file read-only, whatever characters its path holds.

    `SQLResult` opens `file:<path>?mode=ro` as a URI without escaping the path, so a `#`, `?`
    or `%` in it opens (and creates) another file, read-write. The path is given percent-encoded
    instead, and the result keeps the path as given.

    Args:
        path: The results file.
        kind: `SQLResult` or a subclass whose constructor takes the path alone.

    Returns:
        The open results.
    """
    given = Path(path)
    encoded = quote(given.resolve().as_posix(), safe="/:")
    sql = kind(encoded)
    sql._db_path = given  # pyright: ignore[reportPrivateUsage] - the path as given, not its URI form
    return sql
