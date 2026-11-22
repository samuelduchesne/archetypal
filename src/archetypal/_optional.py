"""Import optional dependencies, or say which extra installs them (FR-005, research R12)."""

from __future__ import annotations

import importlib
from typing import TYPE_CHECKING

from archetypal.errors import OptionalDependencyError

if TYPE_CHECKING:
    from types import ModuleType

__all__ = ["require"]


def require(module: str, extra: str) -> ModuleType:
    """Import an optional module.

    Args:
        module: The module to import, such as `pandas`.
        extra: The archetypal extra that installs it, such as `tabula`.

    Returns:
        The imported module.

    Raises:
        OptionalDependencyError: The module is not installed; the message names the extra.
    """
    try:
        return importlib.import_module(module)
    except ModuleNotFoundError as error:
        raise OptionalDependencyError(module, extra) from error
