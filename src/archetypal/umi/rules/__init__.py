"""The conversion rules of UMI translation, registered by identifier.

Importing this package imports every public module in it (`materials`, `schedules`, …). Each
module registers its rules at import with `archetypal.umi.correspondence.rule` (or
`declare_rule` for a rule without a function of its own). A new module needs no change here.
"""

from __future__ import annotations

import importlib
import pkgutil

__all__: list[str] = []

for _module in sorted(pkgutil.iter_modules(__path__), key=lambda module: module.name):
    if not _module.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_module.name}")
