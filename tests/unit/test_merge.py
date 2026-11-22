"""Tests of `merge` (spec 002, T068): FR-010, SC-007, US2 and quickstart scenario 4.

`merge(reduce(m, r, options=o), L)` must equal reducing directly to `L` for every target that is
not strictly finer than the source, including the incomparable `SPACE_USE` → `CORE_PERIMETER`.
Fixture reductions come from the session-scoped `reduced` fixture of `tests/conftest.py`, so
each (fixture, layout) pair is reduced once per session; hypothesis draws few examples because
the space has only 11 valid layout pairs per fixture.
"""

from __future__ import annotations

import dataclasses
import math
from typing import TYPE_CHECKING, Any, cast

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

import archetypal
from archetypal.errors import ReductionError
from archetypal.reduction import Reduction, merge
from archetypal.reduction.options import Layout, ReductionOptions

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

FIXTURES = ("three_zone", "bar_building")
"""Fixtures of the property: three groups at the finest key, and a perimeter-only building."""

RTOL = 1e-3
"""SC-007: parameters within 0.1 %."""

pytestmark = pytest.mark.timeout(60)  # the first test reduces each fixture at each layout (about 8 s)

_PAIRS = tuple((source, target) for source in Layout for target in Layout if not target.is_strictly_finer(source))
_FINER = tuple((source, target) for source in Layout for target in Layout if target.is_strictly_finer(source))


def _at(reduced: Callable[..., Reduction], fixture: str, layout: Layout) -> Reduction:
    """The fixture reduced directly to a layout (the default options share the plain cache entry)."""
    if layout is Layout.SPACE_USE_EXPOSURE:
        return reduced(fixture)
    return reduced(fixture, ReductionOptions(layout=layout))


def _assert_close(a: Any, b: Any, path: str = "") -> None:
    """Assert two JSON values are equal, numbers within `RTOL` (exactly when either is 0)."""
    if isinstance(a, dict) and isinstance(b, dict):
        x, y = cast("dict[str, Any]", a), cast("dict[str, Any]", b)
        assert set(x) == set(y), f"{path}: keys {sorted(set(x) ^ set(y))} differ"
        for key in x:
            _assert_close(x[key], y[key], f"{path}.{key}")
    elif isinstance(a, list) and isinstance(b, list):
        x_items, y_items = cast("list[Any]", a), cast("list[Any]", b)
        assert len(x_items) == len(y_items), f"{path}: {len(x_items)} items, not {len(y_items)}"
        for i, (x_item, y_item) in enumerate(zip(x_items, y_items, strict=True)):
            _assert_close(x_item, y_item, f"{path}[{i}]")
    elif isinstance(a, float | int) and isinstance(b, float | int) and not isinstance(a, bool | type(None)):
        assert a == b or math.isclose(a, b, rel_tol=RTOL, abs_tol=0.0), f"{path}: {a!r} not within 0.1 % of {b!r}"
    else:
        assert a == b, f"{path}: {a!r} != {b!r}"


def _assert_same_reduction(merged: Reduction, direct: Reduction) -> None:
    _assert_close(merged.archetype.model_dump(mode="json"), direct.archetype.model_dump(mode="json"), "archetype")
    m, d = merged.report, direct.report
    assert [g.key for g in m.groups] == [g.key for g in d.groups]
    assert [g.members for g in m.groups] == [g.members for g in d.groups]
    assert m.pre_threshold_groups == d.pre_threshold_groups
    assert m.excluded_zones == d.excluded_zones
    assert m.small_group_merges == d.small_group_merges
    assert m.merged_distinctions == d.merged_distinctions
    assert m.not_represented == d.not_represented
    assert m.building == d.building
    assert m.reproducibility == d.reproducibility
    assert [(p.group, p.path, p.rule) for p in m.parameters] == [(p.group, p.path, p.rule) for p in d.parameters]
    for mp, dp in zip(m.parameters, d.parameters, strict=True):
        _assert_close(mp.value, dp.value, f"{mp.group}:{mp.path}")


@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(fixture=st.sampled_from(FIXTURES), pair=st.sampled_from(_PAIRS))
def test_merging_equals_reducing_directly(
    reduced: Callable[..., Reduction], fixture: str, pair: tuple[Layout, Layout]
) -> None:
    source, target = pair
    _assert_same_reduction(merge(_at(reduced, fixture, source), target), _at(reduced, fixture, target))


@pytest.mark.parametrize("fixture", FIXTURES)
def test_space_use_merges_to_core_perimeter(reduced: Callable[..., Reduction], fixture: str) -> None:
    """The incomparable pair is allowed: the report keeps ledgers at the finest key."""
    merged = merge(_at(reduced, fixture, Layout.SPACE_USE), Layout.CORE_PERIMETER)
    _assert_same_reduction(merged, _at(reduced, fixture, Layout.CORE_PERIMETER))


def test_merge_applies_its_own_threshold_once(reduced: Callable[..., Reduction]) -> None:
    options = ReductionOptions(layout=Layout.SPACE_USE, small_group_threshold=0.4)
    merged = merge(reduced("three_zone"), Layout.SPACE_USE, small_group_threshold=0.4)
    direct = reduced("three_zone", options)
    assert direct.report.small_group_merges  # the threshold does merge a group here
    _assert_same_reduction(merged, direct)


def test_merge_keeps_the_source_threshold_by_default(reduced: Callable[..., Reduction]) -> None:
    source = reduced("three_zone")
    merged = merge(source, Layout.SINGLE_ZONE)
    options = merged.report.reproducibility.options
    assert options.layout is Layout.SINGLE_ZONE
    assert options.small_group_threshold == source.report.reproducibility.options.small_group_threshold


@pytest.mark.parametrize(("source", "target"), _FINER)
def test_a_strictly_finer_target_is_refused(reduced: Callable[..., Reduction], source: Layout, target: Layout) -> None:
    with pytest.raises(ReductionError, match="strictly finer"):
        merge(_at(reduced, "three_zone", source), target)


def test_a_reduction_without_a_report_is_refused(reduced: Callable[..., Reduction]) -> None:
    bare = dataclasses.replace(reduced("three_zone"), report=None)  # pyright: ignore[reportArgumentType]
    with pytest.raises(ReductionError, match="report"):
        merge(bare, Layout.SINGLE_ZONE)


def test_a_report_without_building_facts_is_refused(reduced: Callable[..., Reduction]) -> None:
    source = reduced("three_zone")
    building = source.report.building.model_copy(update={"calendar": None})
    report = source.report.model_copy(update={"building": building})
    with pytest.raises(ReductionError, match="calendar"):
        merge(dataclasses.replace(source, report=report), Layout.SINGLE_ZONE)


def test_quickstart_4_merge_from_files(reduced: Callable[..., Reduction], tmp_path: Path) -> None:
    """Write at the default layout, read back without the model, merge: same as reducing directly."""
    archetype_path, report_path = reduced("three_zone").write(tmp_path, "office")
    assert report_path == tmp_path / "office.report.json"
    read = Reduction.read(archetype_path)
    assert read.report.pre_threshold_groups == reduced("three_zone").report.pre_threshold_groups
    assert read.report.building == reduced("three_zone").report.building
    merged = merge(read, Layout.CORE_PERIMETER)
    _assert_same_reduction(merged, _at(reduced, "three_zone", Layout.CORE_PERIMETER))
    again = Reduction.read(*merged.write(tmp_path, "office_cp"))
    _assert_same_reduction(merge(again, Layout.SINGLE_ZONE), _at(reduced, "three_zone", Layout.SINGLE_ZONE))


def test_read_restores_full_ledgers_with_profiles(reduced: Callable[..., Reduction], tmp_path: Path) -> None:
    source = reduced("three_zone")
    archetype_path, _ = source.write(tmp_path, "office")
    read = Reduction.read(archetype_path)
    for got, expected in zip(read.report.pre_threshold_groups, source.report.pre_threshold_groups, strict=True):
        assert got.ledger == expected.ledger
        calendar = source.report.building.calendar
        assert calendar is not None
        assert got.ledger.gains["people"].hourly.size == calendar.to_calendar().hours


def test_merge_is_public() -> None:
    assert archetypal.merge is merge
    assert "merge" in archetypal.__all__
