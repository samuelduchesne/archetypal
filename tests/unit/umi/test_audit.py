"""The audit: no loss goes unreported (spec 003 T059, SC-006, research R16).

For each library of the UMI test set: read it, write it back, and translate each archetype the
other way too (write it, read it back); diff the results with `diff_umi` and `diff_archetypes`.
Every difference must appear in a loss of the matching report, by subject and location, and
every loss must match a difference or a value with no counterpart. Spec 002's fixture
reductions are audited the same way (SC-004, scenario 2 of `test_round_trip.py`). The audit is
`tests/umi/audit.py`, shared with the reference tier.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from archetypal.umi import Loss, LossKind, diff_umi

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction import Reduction

    from ...umi import audit
else:
    _path = Path(__file__).parents[2] / "umi" / "audit.py"
    _spec = importlib.util.spec_from_file_location("audit", _path)
    audit = importlib.util.module_from_spec(_spec)
    sys.modules["audit"] = audit
    _spec.loader.exec_module(audit)


@pytest.mark.parametrize("library", audit.TEST_SET, ids=lambda path: path.stem)
def test_every_difference_of_a_round_trip_is_reported(
    library: Path, tmp_path: Path, save_library: Callable[[Path], Path | None]
) -> None:
    result = audit.audit_library(library, tmp_path)
    for written in result.libraries:
        save_library(written)
    assert result.problems == []
    if library.name in audit.SAMPLES:  # the samples lose something, so the audit is not vacuous
        assert result.differences > 0
        assert result.losses > 0


@pytest.mark.parametrize("fixture", ["three_zone", "bar_building"])
def test_a_written_reduction_comes_back_apart_from_reported_losses(
    fixture: str, reduced: Callable[..., Reduction], tmp_path: Path, save_library: Callable[[Path], Path | None]
) -> None:
    result = audit.audit_archetypes([reduced(fixture)], tmp_path, fixture)
    for written in result.libraries:
        save_library(written)
    assert result.problems == []


def test_an_unreported_difference_fails_with_its_location(tmp_path: Path) -> None:
    original = audit.TEST_SET[0]
    document = json.loads(original.read_text(encoding="utf-8"))
    document["ZoneLoads"][0]["LightingPowerDensity"] = 99.0
    edited = tmp_path / "edited.json"
    edited.write_text(json.dumps(document), encoding="utf-8")
    result = audit.Audit()
    result.unexplained(diff_umi(original, edited).beyond(), [], "edited")
    [problem] = result.problems
    assert "/ZoneLoads/0/LightingPowerDensity" in problem


def test_a_loss_with_no_difference_fails_with_its_location() -> None:
    loss = Loss(
        kind=LossKind.LOST,
        subject="B_Off_0",
        location="/ZoneLoads/0/LightingPowerDensity",
        value=12.0,
        rule="loads.people",
        reason="test",
    )
    result = audit.Audit()
    result.unmatched([loss], [], "edited", set())
    [problem] = result.problems
    assert "/ZoneLoads/0/LightingPowerDensity" in problem
