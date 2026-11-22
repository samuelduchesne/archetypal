"""The conversion rules of UMI translation, registered by identifier.

Importing this package imports every public module in it (`materials`, `schedules`, …). Each
module registers its rules at import with `archetypal.umi.correspondence.rule` (or
`declare_rule` for a rule without a function of its own). A new module needs no change here.
Private modules (a leading underscore) are not imported here and own no rule prefix:
`_common` holds what several modules share (`RuleContext`, the schedule converter types,
`REFERENCE_CALENDAR`, `report_upstream`, `upstream_defaults`).

The modules were written in three conventions for reporting losses and notes. Each is
consistent within its module; the translation layer adapts between them:

- **Collector argument** (`materials`, `schedules`): functions take `subject` and `location`
  (JSON pointer when reading, SBEM field path when writing) positionally, and a
  `archetypal.umi.report.Findings` they append to.
- **Context keyword** (`loads`, `conditioning`, `ventilation`, `hotwater`): functions take a
  keyword `context: RuleContext` (`_common`) that carries the subject, the location and the
  shared list of findings, and, where schedules are involved, a keyword `schedule` converter
  (`ScheduleToSbem` or `ScheduleToUmi`).
- **Returned losses** (`building`, `windows`): functions take keyword `subject` (and
  `location` or `pointer` where needed) and return their losses with the result, as a
  `(value, list[Loss])` pair or a list of losses.

Pure numeric conversions (`material.carbon_per_m3`, `cop.system`, `dhw.per_person`, …) take
plain values and report nothing.
"""

from __future__ import annotations

import importlib
import pkgutil

__all__: list[str] = []

for _module in sorted(pkgutil.iter_modules(__path__), key=lambda module: module.name):
    if not _module.name.startswith("_"):
        importlib.import_module(f"{__name__}.{_module.name}")
