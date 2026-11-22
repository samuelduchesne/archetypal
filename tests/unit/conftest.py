"""Fixtures shared by the command-line tests (spec 001, US1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from archetypal.reduction import Reduction
    from archetypal.reduction.options import ReductionOptions


@pytest.fixture
def cli_reductions(monkeypatch: pytest.MonkeyPatch, reduced: Callable[..., Reduction]) -> list[tuple[str, str]]:
    """Reduce through the session cache; a model whose stem starts with `broken` fails.

    Returns the list of (model stem, layout) the command asked for, in order.
    """
    from archetypal.cli import _reduce  # noqa: PLC0415
    from archetypal.errors import NoConditionedZones  # noqa: PLC0415

    calls: list[tuple[str, str]] = []

    def reduce_one(model: Path, results: Path | None, weather: Path | None, options: ReductionOptions) -> Reduction:
        del results, weather
        calls.append((model.stem, options.layout.value))
        if model.stem.startswith("broken"):
            raise NoConditionedZones(model)
        return reduced(model.stem, options)

    monkeypatch.setattr(_reduce, "_reduce_one", reduce_one)
    return calls
