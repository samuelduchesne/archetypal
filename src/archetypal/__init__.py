"""Create, translate and codify building energy archetypes on SBEM.

Importing archetypal reads no environment variable, writes no file and configures no logging
beyond a `NullHandler` on its own logger (FR-006).
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version
from typing import NoReturn

from archetypal.comparison import compare as compare

try:
    __version__: str = version("archetypal")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled source tree
    __version__ = "0+unknown"

logging.getLogger(__name__).addHandler(logging.NullHandler())

# Public re-exports of specs 002 and 003 are added here.
__all__ = ["__version__"]


def __getattr__(name: str) -> NoReturn:
    """Raise the migration error for a name or module that archetypal 2 had (PEP 562, FR-016).

    `archetypal.IDF` and `from archetypal import IDF` raise `RemovedInArchetypal3Error`, which
    names the replacement and the migration guide's section. Because that error is an
    `ImportError`, not an `AttributeError`, `hasattr(archetypal, "IDF")` raises it too instead
    of returning `False`. Any other unknown name raises `AttributeError`.

    Args:
        name: The attribute looked up on the package.

    Raises:
        RemovedInArchetypal3Error: `name` is a removed v2 name or module.
        AttributeError: `name` is anything else.
    """
    from archetypal._removed import REMOVED, raise_removed  # noqa: PLC0415 - only when a lookup fails

    v2_path = f"{__name__}.{name}"
    if any(row.v2_path == v2_path and row.kind in {"name", "module"} for row in REMOVED):
        raise_removed(v2_path)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
