"""Create, translate and codify building energy archetypes on SBEM.

Importing archetypal reads no environment variable, writes no file and configures no logging
beyond a `NullHandler` on its own logger (FR-006).
"""

from __future__ import annotations

import importlib
import logging
from importlib.metadata import PackageNotFoundError, version
from typing import TYPE_CHECKING, Any

from archetypal.comparison import compare as compare

if TYPE_CHECKING:
    from archetypal.errors import (
        ArchetypalError as ArchetypalError,
    )
    from archetypal.errors import (
        MissingResults as MissingResults,
    )
    from archetypal.errors import (
        ModelResultsMismatch as ModelResultsMismatch,
    )
    from archetypal.errors import (
        NoConditionedZones as NoConditionedZones,
    )
    from archetypal.errors import (
        NotComparableError as NotComparableError,
    )
    from archetypal.errors import (
        ReductionError as ReductionError,
    )
    from archetypal.errors import (
        UnsupportedEnergyPlusVersion as UnsupportedEnergyPlusVersion,
    )
    from archetypal.reduction import merge as merge
    from archetypal.reduction import reduce as reduce
    from archetypal.reduction.options import Layout as Layout
    from archetypal.reduction.options import ReductionOptions as ReductionOptions
    from archetypal.umi.read import read_umi as read_umi
    from archetypal.umi.write import write_umi as write_umi

try:
    __version__: str = version("archetypal")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled source tree
    __version__ = "0+unknown"

logging.getLogger(__name__).addHandler(logging.NullHandler())

# The public interface (spec 001, data-model.md, Public interface). The errors of spec 002 are
# also reachable here, as `_LAZY` lists, but are documented and exported by `archetypal.errors`.
__all__ = [
    "Layout",
    "ReductionOptions",
    "__version__",
    "compare",
    "merge",
    "read_umi",
    "reduce",
    "write_umi",
]

# Names imported on first use: their modules import epinterface, whose settings read the
# environment, and importing archetypal reads none (FR-006).
_LAZY: dict[str, str] = {
    "read_umi": "archetypal.umi.read",
    "write_umi": "archetypal.umi.write",
    # Spec 002: reduction and its errors.
    "reduce": "archetypal.reduction",
    "merge": "archetypal.reduction",
    "Layout": "archetypal.reduction.options",
    "ReductionOptions": "archetypal.reduction.options",
    "ArchetypalError": "archetypal.errors",
    "ReductionError": "archetypal.errors",
    "NoConditionedZones": "archetypal.errors",
    "MissingResults": "archetypal.errors",
    "ModelResultsMismatch": "archetypal.errors",
    "UnsupportedEnergyPlusVersion": "archetypal.errors",
    "NotComparableError": "archetypal.errors",
}


def __getattr__(name: str) -> Any:
    """Import a lazy name on first use; raise the migration error for a v2 name (PEP 562, FR-016).

    Each name of `_LAZY` (`read_umi`, `write_umi`, `reduce`, `merge`, `Layout`, `ReductionOptions` and the
    errors of spec 002) is imported from its module on first use and kept. `archetypal.IDF` and `from archetypal import IDF` raise `RemovedInArchetypal3Error`, which
    names the replacement and the migration guide's section. Because that error is an
    `ImportError`, not an `AttributeError`, `hasattr(archetypal, "IDF")` raises it too instead
    of returning `False`. Any other unknown name raises `AttributeError`.

    Args:
        name: The attribute looked up on the package.

    Returns:
        The lazy name's value.

    Raises:
        RemovedInArchetypal3Error: `name` is a removed v2 name or module.
        AttributeError: `name` is anything else.
    """
    if name in _LAZY:
        value = getattr(importlib.import_module(_LAZY[name]), name)
        globals()[name] = value
        return value
    from archetypal._removed import REMOVED, raise_removed  # noqa: PLC0415 - only when a lookup fails

    v2_path = f"{__name__}.{name}"
    if any(row.v2_path == v2_path and row.kind in {"name", "module"} for row in REMOVED):
        raise_removed(v2_path)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
