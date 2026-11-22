"""The errors archetypal raises.

One hierarchy for the whole package (spec 001, research R8), extended by spec 002 (reduction)
and spec 003 (UMI translation):

```text
ArchetypalError
├── InputError
│   ├── ReductionError
│   │   ├── NoConditionedZones
│   │   ├── MissingResults
│   │   ├── ModelResultsMismatch
│   │   └── UnsupportedEnergyPlusVersion
│   ├── UmiFormatError
│   └── UmiValidationError
├── UnsupportedFeatureError
├── LossyTranslationError
├── NotComparableError
├── OptionalDependencyError
└── RemovedInArchetypal3Error (also an ImportError)
```

Every error takes the input at fault (a path, a zone name, an option) first, and its message
starts with it: `models/office.idf: no conditioned zones`. A script can catch one cause, or
every archetypal error with `except ArchetypalError`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from collections.abc import Sequence

__all__ = [
    "ArchetypalError",
    "InputError",
    "LossReport",
    "LossyTranslationError",
    "MissingResults",
    "ModelResultsMismatch",
    "NoConditionedZones",
    "NotComparableError",
    "OptionalDependencyError",
    "Problem",
    "ReductionError",
    "RemovedInArchetypal3Error",
    "UmiFormatError",
    "UmiValidationError",
    "UnsupportedEnergyPlusVersion",
    "UnsupportedFeatureError",
]


def _bullets(items: Sequence[object]) -> str:
    return "".join(f"\n  - {item}" for item in items)


class ArchetypalError(Exception):
    """The base of every error archetypal raises.

    Args:
        subject: The input at fault: a path, a zone name, an option.
        message: What is wrong with it.

    Attributes:
        subject: The input at fault, as text.
        message: What is wrong with it, without the subject.
    """

    def __init__(self, subject: str | os.PathLike[str], message: str) -> None:
        """Create the error; see the class for the arguments."""
        self.subject: str = os.fspath(subject)
        self.message: str = message
        super().__init__(self.subject, message)

    def __str__(self) -> str:
        """Return the subject, then the message."""
        return f"{self.subject}: {self.message}"


class InputError(ArchetypalError):
    """An input is invalid: a file, a model, a library or an option (FR-010)."""


class UnsupportedFeatureError(ArchetypalError):
    """The input uses a feature the operation cannot handle."""


class LossReport(Protocol):
    """What `LossyTranslationError.report` holds: a report with a list of losses.

    Spec 003's `TranslationReport` satisfies it; spec 001 does not import spec 003.
    """

    @property
    def losses(self) -> Sequence[object]:
        """What the translation would lose."""
        ...


class LossyTranslationError(ArchetypalError):
    """A translation in strict mode would lose information.

    Args:
        subject: The input being translated.
        message: What would be lost, in short.
        report: The report of everything that would have been lost.

    Attributes:
        report: The report of everything that would have been lost.
    """

    def __init__(self, subject: str | os.PathLike[str], message: str, report: LossReport) -> None:
        """Create the error; see the class for the arguments."""
        super().__init__(subject, message)
        self.report: LossReport = report
        self.args = (self.subject, message, report)


class NotComparableError(ArchetypalError):
    """Two sets of results cannot be compared (spec 002, FR-028).

    Args:
        subject: The results at fault.
        differences: Every difference that prevents the comparison (weather, run period, units,
            timestep, reporting frequency).

    Attributes:
        differences: Every difference that prevents the comparison.
    """

    def __init__(self, subject: str | os.PathLike[str], differences: Sequence[str]) -> None:
        """Create the error; see the class for the arguments."""
        self.differences: tuple[str, ...] = tuple(differences)
        super().__init__(subject, "the results cannot be compared; they differ in:" + _bullets(self.differences))
        self.args = (self.subject, self.differences)


class OptionalDependencyError(ArchetypalError):
    """A feature needs a dependency that is not installed (FR-005).

    Args:
        subject: The module that is missing.
        extra: The archetypal extra that installs it.

    Attributes:
        extra: The archetypal extra that installs the missing module.
    """

    def __init__(self, subject: str, extra: str) -> None:
        """Create the error; see the class for the arguments."""
        self.extra: str = extra
        super().__init__(
            subject,
            f'not installed; it comes with the "{extra}" extra. Install it with: pip install "archetypal[{extra}]"',
        )
        self.args = (self.subject, extra)


class RemovedInArchetypal3Error(ArchetypalError, ImportError):
    """A v2 name, module, command or option that archetypal 3 does not provide (FR-016).

    It is also an `ImportError`, so `except ImportError` in v2-era code still catches it.
    (CPython does not let a class derive from both `ImportError` and `AttributeError`.)

    Args:
        subject: The v2 path, as a v2 user writes it, such as `archetypal.IDF`.
        message: The rest of the sentence, such as `was removed in archetypal 3.`

    Attributes:
        name: The v2 path, as `ImportError.name`.
    """

    def __init__(self, subject: str, message: str) -> None:
        """Create the error; see the class for the arguments."""
        super().__init__(subject, message)
        self.name = self.subject

    def __str__(self) -> str:
        """Return the v2 path, then the message, as one sentence."""
        return f"{self.subject} {self.message}"


# --- Spec 002: reduction -----------------------------------------------------------------------


class ReductionError(InputError):
    """A model or its results cannot be reduced, or a reduction cannot be merged (spec 002)."""


class NoConditionedZones(ReductionError):
    """The model has no conditioned zone, so there is nothing to reduce.

    Args:
        subject: The model.
    """

    def __init__(self, subject: str | os.PathLike[str]) -> None:
        """Create the error; see the class for the arguments."""
        super().__init__(subject, "no conditioned zones; reduction needs at least one heated or cooled zone")
        self.args = (self.subject,)


class MissingResults(ReductionError):
    """The results lack outputs that reduction needs.

    Args:
        subject: The results (or the model, when no results were given).
        missing: Each missing item, as the IDF object to add (an `Output:Variable` or
            `Output:Meter`).

    Attributes:
        missing: Each missing item.
    """

    def __init__(self, subject: str | os.PathLike[str], missing: Sequence[str]) -> None:
        """Create the error; see the class for the arguments."""
        self.missing: tuple[str, ...] = tuple(missing)
        super().__init__(
            subject,
            f"{len(self.missing)} required result(s) missing; add these objects to the model and run it again:"
            + _bullets(self.missing)
            + "\nor call reduce(..., simulate=True) to run it once with them.",
        )
        self.args = (self.subject, self.missing)


class ModelResultsMismatch(ReductionError):
    """The results were not produced by the model (zone names or versions differ).

    Args:
        subject: The results.
        differences: Each difference, such as `zone CORE is only in the model`.

    Attributes:
        differences: Each difference.
    """

    def __init__(self, subject: str | os.PathLike[str], differences: Sequence[str]) -> None:
        """Create the error; see the class for the arguments."""
        self.differences: tuple[str, ...] = tuple(differences)
        super().__init__(subject, "the results do not match the model:" + _bullets(self.differences))
        self.args = (self.subject, self.differences)


class UnsupportedEnergyPlusVersion(ReductionError):
    """The model or results come from an EnergyPlus release reduction does not support.

    Args:
        subject: The model or results.
        version: Their EnergyPlus version, such as `9.6`.
        supported: The oldest and newest supported versions, such as `("22.1", "25.2")`.

    Attributes:
        version: The EnergyPlus version found.
        supported: The oldest and newest supported versions.
    """

    def __init__(self, subject: str | os.PathLike[str], version: str, supported: tuple[str, str]) -> None:
        """Create the error; see the class for the arguments."""
        self.version: str = version
        self.supported: tuple[str, str] = supported
        oldest, newest = supported
        super().__init__(
            subject,
            f"EnergyPlus {version} is not supported; reduction accepts {oldest} to {newest}. "
            f"Upgrade the model with idfkit.migration.migrate, then simulate it again.",
        )
        self.args = (self.subject, version, supported)


# --- Spec 003: UMI translation -----------------------------------------------------------------


@dataclass(frozen=True)
class Problem:
    """One problem found in a UMI library.

    Attributes:
        pointer: Where the problem is, as a JSON pointer into the library (`/Zones/2/Loads`).
        template: The building template affected, if any.
        rule: The rule broken, such as `required-reference`.
        message: What is wrong.
    """

    pointer: str
    template: str | None
    rule: str
    message: str

    def __str__(self) -> str:
        """Return the problem on one line."""
        where = self.pointer if self.template is None else f"{self.pointer} (template {self.template})"
        return f"{where}: [{self.rule}] {self.message}"


class UmiFormatError(InputError):
    """A UMI library cannot be read: refused dialect, malformed JSON or broken reference.

    Args:
        subject: The library path.
        message: What is wrong.
        problems: The format problems found, each with its JSON pointer.

    Attributes:
        problems: The format problems found.
    """

    def __init__(self, subject: str | os.PathLike[str], message: str, problems: Sequence[Problem] = ()) -> None:
        """Create the error; see the class for the arguments."""
        self.problems: list[Problem] = list(problems)
        super().__init__(subject, message + _bullets(self.problems))
        self.args = (self.subject, message, self.problems)


class UmiValidationError(InputError):
    """A UMI library breaks completeness or range rules.

    Reading collects every problem before raising this error once.

    Args:
        subject: The library path, or the archetype name when writing.
        problems: Every problem found.

    Attributes:
        problems: Every problem found.
    """

    def __init__(self, subject: str | os.PathLike[str], problems: Sequence[Problem]) -> None:
        """Create the error; see the class for the arguments."""
        self.problems: list[Problem] = list(problems)
        super().__init__(subject, f"{len(self.problems)} problem(s) found:" + _bullets(self.problems))
        self.args = (self.subject, self.problems)
