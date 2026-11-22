"""Strict mode (spec 003 T060, FR-011a, SC-006a).

Over the UMI test set, in both directions: every read and write whose report lists a loss fails
in strict mode with `LossyTranslationError`, carrying that report, and writes nothing; every one
whose report lists no loss succeeds.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from archetypal.errors import LossyTranslationError
from archetypal.umi import read_umi, to_umi, write_umi

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

IDS = {"ids": lambda path: path.stem}


@pytest.mark.parametrize("library", audit.TEST_SET, **IDS)
def test_strict_reading_fails_if_and_only_if_something_is_lost(library: Path, tmp_path: Path) -> None:
    lenient = read_umi(library)
    if lenient.report.losses:
        with pytest.raises(LossyTranslationError) as raised:
            read_umi(library, strict=True)
        assert raised.value.report.losses == lenient.report.losses
    else:
        assert read_umi(library, strict=True).archetypes == lenient.archetypes
    assert list(tmp_path.iterdir()) == []  # reading never writes


@pytest.mark.parametrize("library", audit.TEST_SET, **IDS)
def test_strict_writing_fails_if_and_only_if_something_is_lost(library: Path, tmp_path: Path) -> None:
    archetypes = read_umi(library).archetypes
    if not archetypes:
        pytest.skip("no template, so nothing to write")
    lenient = to_umi(archetypes)
    target = tmp_path / "library.json"
    if lenient.report.losses:
        with pytest.raises(LossyTranslationError) as raised:
            write_umi(archetypes, target, strict=True)
        assert raised.value.report.losses == lenient.report.losses
        assert list(tmp_path.iterdir()) == []
    else:
        assert write_umi(archetypes, target, strict=True).losses == []
        assert sorted(path.name for path in tmp_path.iterdir()) == ["library.json", "library.loss.json"]


def test_a_lossless_library_reads_strictly(tmp_path: Path) -> None:
    """B2's archetypes write without loss, and the library written reads back without loss."""
    archetypes = read_umi(audit.TEST_SET[0]).archetypes
    target = tmp_path / "library.json"
    assert write_umi(archetypes, target, strict=True).losses == []
    again = read_umi(target, strict=True)
    assert [a.Name for a in again.archetypes] == [a.Name for a in archetypes]


@pytest.mark.parametrize("fixture", ["three_zone", "bar_building"])
def test_a_reduction_fails_strict_writing_and_writes_nothing(
    fixture: str, reduced: Callable[..., Reduction], tmp_path: Path
) -> None:
    reduction = reduced(fixture)
    assert to_umi([reduction]).report.losses
    with pytest.raises(LossyTranslationError):
        write_umi([reduction], tmp_path / "library.json", strict=True)
    assert list(tmp_path.iterdir()) == []


@pytest.mark.xfail(
    strict=True,
    reason="UP-9: the SBEM fork has no airflow-network or zone-mixing window settings, and ND sets "
    "AfnWindowAvailability and ZoneMixingAvailabilitySchedule to occupancy schedules",
)
def test_the_sample_without_unused_components_reads_strictly() -> None:
    """ND's only losses are the UP-9 window settings: it reads strictly once SBEM holds them."""
    read_umi(audit.FIXTURES / "BostonTemplateLibrary_nodup.json", strict=True)
