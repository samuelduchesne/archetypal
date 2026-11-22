"""The v2 names, modules, commands and options that archetypal 3 does not provide.

`REMOVED` is the only source (spec 001, data-model.md, RemovedCapability): import errors,
rejected options, the migration guide's table and the removed-names reference are generated
from it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from archetypal.errors import RemovedInArchetypal3Error

if TYPE_CHECKING:
    from typing import NoReturn

__all__ = [
    "MIGRATION_GUIDE_URL",
    "REMOVED",
    "FrequentTask",
    "Kind",
    "RemovedCapability",
    "Replacement",
    "anchor",
    "raise_removed",
]

MIGRATION_GUIDE_URL = "https://samuelduchesne.github.io/archetypal/how-to/migrate-from-v2/"
"""The migration guide; each row has a section whose heading is its `v2_path`."""

Kind = Literal["name", "module", "command", "option"]
"""What a v2 path is: a Python name, a module, a command or a command option."""

FrequentTask = Literal[
    "reduce-to-umi", "edit-umi-library", "open-and-simulate", "read-results", "upgrade-version", "evaluate-schedule"
]
"""The frequent v2 tasks that have a before/after example in the migration guide (FR-018)."""


@dataclass(frozen=True)
class Replacement:
    """What to use instead of a removed capability.

    Attributes:
        package: The package that provides it.
        target: The name, module or command to use.
        docs_url: The page that documents it.
    """

    package: Literal["archetypal", "idfkit", "epinterface"]
    target: str
    docs_url: str


@dataclass(frozen=True)
class RemovedCapability:
    """One v2 name, module, command or option that archetypal 3 does not provide.

    Attributes:
        kind: What the v2 path is.
        v2_path: The path as a v2 user writes it, such as `archetypal.IDF` or
            `archetypal reduce --all_zones`. Unique in `REMOVED`.
        replacement: What to use instead; `None` only when `reason` says why there is none.
        reason: Why it was removed, in one sentence. Always set.
        frequent_task: The before/after example of the migration guide it belongs to, if any.
    """

    kind: Kind
    v2_path: str
    replacement: Replacement | None
    reason: str
    frequent_task: FrequentTask | None = None

    def __post_init__(self) -> None:
        """Refuse a row without a reason."""
        if not self.reason.strip():
            msg = f"{self.v2_path}: a removed capability needs a reason"
            raise ValueError(msg)


REMOVED: tuple[RemovedCapability, ...] = ()
"""Every removed v2 capability, filled by spec 001's user stories 1 and 2."""


def anchor(heading: str) -> str:
    """Return the anchor the docs site gives a heading (Python-Markdown's default slug).

    Args:
        heading: The heading text, such as `archetypal.IDF`.

    Returns:
        The anchor, such as `archetypalidf`.
    """
    slug = re.sub(r"[^\w\s-]", "", heading).strip().lower()
    return re.sub(r"[-\s]+", "-", slug)


def _message(row: RemovedCapability) -> str:
    instead = (
        row.reason if row.replacement is None else f"Use {row.replacement.target} ({row.replacement.package}) instead."
    )
    return f"was removed in archetypal 3.\n{instead}\nSee {MIGRATION_GUIDE_URL}#{anchor(row.v2_path)}"


def raise_removed(v2_path: str) -> NoReturn:
    """Raise the error for a removed v2 capability.

    Args:
        v2_path: A `v2_path` of `REMOVED`.

    Raises:
        RemovedInArchetypal3Error: Always, naming the replacement and the migration guide's section.
        LookupError: `v2_path` is not in `REMOVED`.
    """
    for row in REMOVED:
        if row.v2_path == v2_path:
            raise RemovedInArchetypal3Error(row.v2_path, _message(row)) from None
    msg = f"{v2_path} is not a removed v2 capability"
    raise LookupError(msg)
