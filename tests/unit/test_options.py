"""Tests for `archetypal.reduction.options` (spec 002, T013)."""

from __future__ import annotations

import itertools

import pytest
from pydantic import ValidationError

from archetypal.reduction.options import Layout, ReductionOptions

FINEST = Layout.SPACE_USE_EXPOSURE
ALL = tuple(Layout)


def test_members_and_default() -> None:
    assert [m.name for m in Layout] == ["SPACE_USE_EXPOSURE", "SPACE_USE", "CORE_PERIMETER", "SINGLE_ZONE"]
    assert ReductionOptions().layout is Layout.SPACE_USE_EXPOSURE
    assert isinstance(Layout.SPACE_USE, str)
    assert Layout("space_use") is Layout.SPACE_USE
    assert str(Layout.CORE_PERIMETER) == "core_perimeter"


@pytest.mark.parametrize(
    ("finer", "coarser"),
    [
        (Layout.SPACE_USE_EXPOSURE, Layout.SPACE_USE),
        (Layout.SPACE_USE_EXPOSURE, Layout.CORE_PERIMETER),
        (Layout.SPACE_USE_EXPOSURE, Layout.SINGLE_ZONE),
        (Layout.SPACE_USE, Layout.SINGLE_ZONE),
        (Layout.CORE_PERIMETER, Layout.SINGLE_ZONE),
    ],
)
def test_coarseness_order(finer: Layout, coarser: Layout) -> None:
    assert finer.is_finer_or_equal(coarser)
    assert not coarser.is_finer_or_equal(finer)
    assert Layout.is_strictly_finer(finer, coarser)
    assert not Layout.is_strictly_finer(coarser, finer)
    assert finer.is_comparable(coarser)


def test_space_use_and_core_perimeter_are_not_comparable() -> None:
    a, b = Layout.SPACE_USE, Layout.CORE_PERIMETER
    assert not a.is_comparable(b)
    assert not b.is_comparable(a)
    assert not a.is_finer_or_equal(b)
    assert not b.is_finer_or_equal(a)
    # merge refuses only a strictly finer target, so both directions are allowed.
    assert not Layout.is_strictly_finer(a, b)
    assert not Layout.is_strictly_finer(b, a)


def test_partial_order_axioms() -> None:
    for a in ALL:
        assert a.is_finer_or_equal(a)  # reflexive
        assert not Layout.is_strictly_finer(a, a)  # irreflexive strict order
        assert FINEST.is_finer_or_equal(a)  # the finest key is below every layout
        assert a.is_finer_or_equal(Layout.SINGLE_ZONE)
    for a, b in itertools.product(ALL, ALL):
        if a.is_finer_or_equal(b) and b.is_finer_or_equal(a):
            assert a is b  # antisymmetric
        for c in ALL:
            if a.is_finer_or_equal(b) and b.is_finer_or_equal(c):
                assert a.is_finer_or_equal(c)  # transitive


def test_group_keys() -> None:
    assert Layout.SPACE_USE_EXPOSURE.group_key("Office", "core") == ("Office", "core")
    assert Layout.SPACE_USE.group_key("Office", "core") == ("Office",)
    assert Layout.CORE_PERIMETER.group_key("Office", "perimeter") == ("perimeter",)
    assert Layout.SINGLE_ZONE.group_key("Office", "perimeter") == ()


def test_group_key_of_a_finer_key_regroups_consistently() -> None:
    """Regrouping a finest key gives the same key as grouping the zone directly (merge relies on it)."""
    for space_use, exposure in itertools.product(("Office", "Retail"), ("core", "perimeter")):
        finest = FINEST.group_key(space_use, exposure)
        for layout in ALL:
            assert layout.regroup(finest) == layout.group_key(space_use, exposure)


def test_lost_distinctions() -> None:
    assert Layout.SPACE_USE.lost_from(FINEST) == ("exposure",)
    assert Layout.CORE_PERIMETER.lost_from(FINEST) == ("space_use",)
    assert Layout.SINGLE_ZONE.lost_from(FINEST) == ("space_use", "exposure")
    assert FINEST.lost_from(FINEST) == ()


@pytest.mark.parametrize("value", [0.0, 0.05, 0.5, 0.999])
def test_threshold_accepts_shares_in_range(value: float) -> None:
    assert ReductionOptions(small_group_threshold=value).small_group_threshold == value


@pytest.mark.parametrize("value", [-0.01, 1.0, 1.5, float("nan"), float("inf")])
def test_threshold_outside_range_is_refused(value: float) -> None:
    with pytest.raises(ValidationError, match="small_group_threshold"):
        ReductionOptions(small_group_threshold=value)


def test_threshold_default() -> None:
    assert ReductionOptions().small_group_threshold == 0.05


def test_options_are_frozen() -> None:
    options = ReductionOptions()
    with pytest.raises(ValidationError):
        options.layout = Layout.SINGLE_ZONE  # type: ignore[misc]
    assert options.model_copy(update={"layout": Layout.SPACE_USE}).layout is Layout.SPACE_USE


def test_space_use_mapping_and_unknown_fields() -> None:
    options = ReductionOptions(space_use_mapping={"Z1": "Office"}, layout=Layout("single_zone"))
    assert options.space_use_mapping == {"Z1": "Office"}
    assert options.layout is Layout.SINGLE_ZONE
    assert ReductionOptions().space_use_mapping is None
    with pytest.raises(ValidationError):
        ReductionOptions(threshold=0.1)  # type: ignore[call-arg]


def test_options_round_trip_through_json() -> None:
    options = ReductionOptions(layout=Layout.CORE_PERIMETER, small_group_threshold=0.1, space_use_mapping={"Z": "Office"})
    assert ReductionOptions.model_validate_json(options.model_dump_json()) == options
    assert options.model_dump(mode="json")["layout"] == "core_perimeter"
