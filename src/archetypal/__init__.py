"""Create, translate and codify building energy archetypes on SBEM.

Importing archetypal reads no environment variable, writes no file and configures no logging
beyond a `NullHandler` on its own logger (FR-006).
"""

from __future__ import annotations

import logging
from importlib.metadata import PackageNotFoundError, version

try:
    __version__: str = version("archetypal")
except PackageNotFoundError:  # pragma: no cover - only when run from an uninstalled source tree
    __version__ = "0+unknown"

logging.getLogger(__name__).addHandler(logging.NullHandler())

# Public re-exports of specs 002 and 003, and the module `__getattr__` that raises for removed
# v2 names (spec 001, user story 2), are added here.
__all__ = ["__version__"]
