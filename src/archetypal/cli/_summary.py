"""The command line's exit statuses and the summary it prints (spec 001, data-model.md; FR-014).

A command builds a `RunSummary` from the reports it wrote, prints it to stderr and exits with
its `status`. The summary is never stored.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from enum import IntEnum
from typing import TYPE_CHECKING

import click

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

__all__ = ["ExitStatus", "Failure", "RunSummary", "count_reduction", "count_translation"]


class ExitStatus(IntEnum):
    """The exit statuses of the `archetypal` command (data-model.md, ExitStatus).

    When both `PARTIAL_FAILURE` and `SUCCESS_WITH_LOSSES` apply, `PARTIAL_FAILURE` wins: a
    failure matters more than a loss.

    Attributes:
        SUCCESS: Every model processed; no loss or approximation reported.
        FAILURE: Nothing written: invalid input, every model failed, or an unexpected error.
        USAGE: A usage error, including a removed v2 option or command (FR-013).
        PARTIAL_FAILURE: Some models failed; the output holds the others, and the summary and
            reports name the failures.
        SUCCESS_WITH_LOSSES: Every model processed; at least one loss or approximation reported.
    """

    SUCCESS = 0
    FAILURE = 1
    USAGE = 2
    PARTIAL_FAILURE = 3
    SUCCESS_WITH_LOSSES = 4


@dataclass(frozen=True)
class Failure:
    """A model that could not be processed.

    Attributes:
        model: The model's path, as given or expanded.
        error: The error's class name, such as `NoConditionedZones`.
        message: The error's message, which starts with the input at fault.
    """

    model: Path
    error: str
    message: str


def _plural(count: int, word: str, plural: str | None = None) -> str:
    return f"{count} {word if count == 1 else (plural or word + 's')}"


@dataclass
class RunSummary:
    """What a command prints to stderr after its work (data-model.md, RunSummary).

    Attributes:
        models_ok: Models processed.
        failures: The models that failed, with their error.
        losses: Losses reported: 002's `not_represented` entries that were dropped, and 003's
            losses other than approximations.
        approximations: Approximations reported: 002's `not_represented` entries folded into
            another parameter, and 003's `approximate` losses.
        outputs: The output files written.
        reports: The report files written.
        verb: How the summary names the work done on a model (`reduced`, `merged`, ...).
        noun: What the summary counts (`model`, `template`, `archetype`).
    """

    models_ok: int = 0
    failures: list[Failure] = field(default_factory=list[Failure])
    losses: int = 0
    approximations: int = 0
    outputs: list[Path] = field(default_factory=list["Path"])
    reports: list[Path] = field(default_factory=list["Path"])
    verb: str = "reduced"
    noun: str = "model"

    @property
    def models_failed(self) -> int:
        """The number of models that failed."""
        return len(self.failures)

    @property
    def status(self) -> ExitStatus:
        """The exit status: failures first, then losses (3 wins over 4)."""
        if self.failures:
            return ExitStatus.FAILURE if self.models_ok == 0 else ExitStatus.PARTIAL_FAILURE
        if self.losses or self.approximations:
            return ExitStatus.SUCCESS_WITH_LOSSES
        return ExitStatus.SUCCESS

    def render(self) -> str:
        """Return the summary as text, one fact per line."""
        noun = _plural(self.models_ok, self.noun)
        lines = [f"{noun} {self.verb}, {self.models_failed} failed."]
        lines += [f"  failed: {f.model}: {f.error}: {f.message}" for f in self.failures]
        if self.models_ok:
            counts = f"{_plural(self.losses, 'loss', 'losses')}, {_plural(self.approximations, 'approximation')}"
            lines.append(f"{counts} reported{'; see the reports' if self.losses or self.approximations else ''}.")
        lines += _listing("Written", self.outputs)
        lines += _listing("Reports", self.reports)
        return "\n".join(lines)

    def echo(self) -> None:
        """Print the summary to stderr."""
        click.echo(self.render(), err=True)
        sys.stderr.flush()


def _listing(title: str, paths: Iterable[Path]) -> list[str]:
    items = [f"  {path}" for path in paths]
    return [f"{title}:", *items] if items else []


def count_reduction(report: object) -> tuple[int, int]:
    """Return the losses and approximations of a 002 reduction report.

    An entry of `not_represented` folded into another parameter is an approximation; one that
    is dropped is a loss.

    Args:
        report: A `ReductionReport`.

    Returns:
        The losses and the approximations.
    """
    entries = getattr(report, "not_represented", ())
    folded = sum(1 for entry in entries if getattr(entry, "folded_into", None) is not None)
    return len(entries) - folded, folded


def count_translation(report: object) -> tuple[int, int]:
    """Return the losses and approximations of a 003 translation report.

    Args:
        report: A `TranslationReport`.

    Returns:
        The losses other than `approximate` ones, and the `approximate` losses.
    """
    losses = getattr(report, "losses", ())
    approximate = sum(1 for loss in losses if str(getattr(loss, "kind", "")) == "approximate")
    return len(losses) - approximate, approximate
