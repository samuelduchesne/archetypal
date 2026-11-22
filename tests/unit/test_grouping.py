"""Tests for grouping and thresholding (spec 002, T038, T067; data-model.md: Grouping and thresholding).

Domain modules may not fill real ledgers yet, so these tests use synthetic ledgers: one per
zone, with floor area, gains, setpoints, outdoor air and hot water chosen by the test. The bar
building scenario uses the fixture's classified zones with synthetic ledgers.
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given
from hypothesis import strategies as st

from archetypal.reduction.classify import ClassifiedZone, classify
from archetypal.reduction.grouping import (
    Group,
    Grouping,
    MergedDistinction,
    SmallGroupMerge,
    building_intensities,
    distance,
    finest_groups,
    group,
    group_zones,
    intensities,
)
from archetypal.reduction.inventory import ZoneRecord, build_inventory
from archetypal.reduction.ledger import (
    GainTotals,
    GroupLedger,
    HotWaterTotals,
    OutdoorAirTotals,
    WeightedProfile,
)
from archetypal.reduction.options import Layout
from archetypal.reduction.schedules import ScheduleEvaluator
from archetypal.reduction.sources import load_sources

ROOT = Path(__file__).resolve().parents[2]
MODELS = ROOT / "tests" / "fixtures" / "models"
HOURS = 24
FINEST = Layout.SPACE_USE_EXPOSURE

# --- Synthetic zones and ledgers ------------------------------------------------------------------


def _ledger(
    name: str,
    area: float,
    *,
    lights: float = 10.0,
    lights_on: float = 0.5,
    heat: float = 21.0,
    cool: float = 24.0,
    oa: float = 0.001,
    dhw: float = 0.0,
) -> GroupLedger:
    """A one-zone ledger: densities per m², setpoints in °C, flows per m²."""
    return GroupLedger(
        members=(name,),
        floor_area=area,
        gains={"lights": GainTotals(installed=lights * area, hourly=np.full(HOURS, lights * area * lights_on))},
        heating_setpoint=WeightedProfile(weight=area, weighted=np.full(HOURS, heat * area)),
        cooling_setpoint=WeightedProfile(weight=area, weighted=np.full(HOURS, cool * area)),
        outdoor_air=OutdoorAirTotals(design_flow=oa * area, hourly=np.full(HOURS, oa * area)),
        hot_water=HotWaterTotals(volume=np.full(HOURS, dhw * area), heat=np.full(HOURS, dhw * area * 50.0)),
    )


def _zone(name: str, space_use: str, exposure: str, *, conditioned: bool = True) -> ClassifiedZone:
    record = ZoneRecord(name=name, multiplier=1, floor_area=1.0, min_z=0.0, volume=3.0)
    return ClassifiedZone(
        zone=record,
        conditioned=conditioned,
        role="conditioned" if conditioned else "excluded",
        exposure=exposure,  # type: ignore[arg-type]
        space_use=space_use,
        space_use_source="signature",
        role_reason="test",
    )


def _pair(name: str, space_use: str, exposure: str, area: float, **kwargs: float) -> tuple[ClassifiedZone, GroupLedger]:
    return _zone(name, space_use, exposure), _ledger(name, area, **kwargs)


def _keys(grouping: Grouping) -> list[tuple[str, ...]]:
    return [g.key for g in grouping.groups]


def _members(grouping: Grouping) -> dict[tuple[str, ...], tuple[str, ...]]:
    return {g.key: g.ledger.members for g in grouping.groups}


# --- Default layout (T038) ------------------------------------------------------------------------


def test_one_group_per_space_use_and_exposure() -> None:
    pairs = [
        _pair("B1", "office", "perimeter", 100.0),
        _pair("A1", "office", "core", 100.0),
        _pair("A2", "office", "perimeter", 100.0),
        _pair("C1", "retail", "perimeter", 100.0),
        _pair("C2", "retail", "core", 100.0),
    ]
    result = group_zones(pairs, layout=FINEST, threshold=0.0)
    assert _members(result) == {
        ("office", "core"): ("A1",),
        ("office", "perimeter"): ("A2", "B1"),
        ("retail", "core"): ("C2",),
        ("retail", "perimeter"): ("C1",),
    }
    assert _keys(result) == sorted(_keys(result))
    assert result.groups[1].ledger.floor_area == 200.0
    assert result.merges == ()
    assert result.merged_distinctions == ()
    assert result.layout is FINEST


def test_group_ledger_is_the_sum_of_member_ledgers() -> None:
    pairs = [_pair("A", "office", "perimeter", 100.0, lights=8.0), _pair("B", "office", "perimeter", 50.0, lights=12.0)]
    (only,) = group_zones(pairs, threshold=0.0).groups
    assert only.ledger == pairs[0][1] + pairs[1][1]


def test_unconditioned_zone_is_refused() -> None:
    zone = _zone("Attic", "use:Attic", "perimeter", conditioned=False)
    with pytest.raises(ValueError, match="Attic"):
        group_zones([(zone, _ledger("Attic", 10.0))])


def test_ledger_must_belong_to_its_zone() -> None:
    with pytest.raises(ValueError, match="members"):
        group_zones([(_zone("A", "office", "core"), _ledger("B", 10.0))])


def test_no_zones_is_refused() -> None:
    with pytest.raises(ValueError, match="no conditioned"):
        group_zones([])


def test_small_group_merges_into_most_similar_group_of_same_exposure() -> None:
    pairs = [
        _pair("Office_P", "office", "perimeter", 400.0, lights=10.0),
        _pair("Retail_P", "retail", "perimeter", 300.0, lights=20.0),
        _pair("Shop_P", "shop", "perimeter", 20.0, lights=19.0),  # 2 %, like retail
        _pair("Office_C", "office", "core", 280.0, lights=19.0),  # same lights as shop but core
    ]
    result = group_zones(pairs, threshold=0.05)
    assert _members(result) == {
        ("office", "core"): ("Office_C",),
        ("office", "perimeter"): ("Office_P",),
        ("retail", "perimeter"): ("Retail_P", "Shop_P"),
    }
    (merge,) = result.merges
    assert merge.merged_key == ("shop", "perimeter")
    assert merge.into_key == ("retail", "perimeter")
    assert merge.share == pytest.approx(0.02)
    assert merge.distance > 0.0


def test_smallest_group_merges_first() -> None:
    # Two small groups, each most similar to the other: the smaller merges into the larger.
    # Together they make exactly 5 %, which is not below the threshold, so they stay.
    pairs = [
        _pair("Big", "office", "perimeter", 900.0, lights=5.0),
        _pair("Small", "lab", "perimeter", 30.0, lights=30.0),
        _pair("Tiny", "kitchen", "perimeter", 20.0, lights=31.0),
        _pair("Core", "office", "core", 50.0),
    ]
    result = group_zones(pairs, threshold=0.05)
    assert [(m.merged_key, m.into_key) for m in result.merges] == [
        (("kitchen", "perimeter"), ("lab", "perimeter")),
    ]
    assert _members(result)[("lab", "perimeter")] == ("Small", "Tiny")


def test_merged_group_below_threshold_merges_again() -> None:
    pairs = [
        _pair("Big", "office", "perimeter", 900.0, lights=5.0),
        _pair("Small", "lab", "perimeter", 30.0, lights=30.0),
        _pair("Tiny", "kitchen", "perimeter", 20.0, lights=31.0),
        _pair("Core", "office", "core", 50.0),
    ]
    result = group_zones(pairs, threshold=0.07)
    assert [(m.merged_key, m.into_key) for m in result.merges] == [
        (("kitchen", "perimeter"), ("lab", "perimeter")),
        (("lab", "perimeter"), ("office", "perimeter")),
    ]
    assert result.merges[1].share == pytest.approx(0.05)
    assert _members(result)[("office", "perimeter")] == ("Big", "Small", "Tiny")
    # The core group is 5 % but has no other core group: it is kept.
    assert _members(result)[("office", "core")] == ("Core",)


def test_ties_are_broken_by_key() -> None:
    pairs = [
        _pair("Z", "zeta", "perimeter", 450.0),
        _pair("A", "alpha", "perimeter", 450.0),
        _pair("Tiny1", "tiny", "perimeter", 10.0),  # identical to both: distance 0 to each
        _pair("Tiny2", "tinier", "perimeter", 10.0),
        _pair("C", "alpha", "core", 80.0),
    ]
    result = group_zones(pairs, threshold=0.05)
    # Both tiny groups have the same area: "tinier" < "tiny" goes first, into the key-smaller
    # of its distance-0 partners.
    assert [(m.merged_key, m.into_key) for m in result.merges] == [
        (("tinier", "perimeter"), ("alpha", "perimeter")),
        (("tiny", "perimeter"), ("alpha", "perimeter")),
    ]


def test_small_group_with_nothing_to_merge_into_is_kept() -> None:
    pairs = [_pair("P", "office", "perimeter", 990.0), _pair("C", "office", "core", 10.0)]
    result = group_zones(pairs, threshold=0.05)
    assert _keys(result) == [("office", "core"), ("office", "perimeter")]
    assert result.merges == ()


def test_single_group_is_kept_below_any_threshold() -> None:
    result = group_zones([_pair("P", "office", "perimeter", 10.0)], threshold=0.99)
    assert _keys(result) == [("office", "perimeter")]


def test_pre_threshold_groups_are_kept_at_the_finest_key() -> None:
    pairs = [
        _pair("P", "office", "perimeter", 900.0),
        _pair("Q", "lab", "perimeter", 20.0),
        _pair("C", "office", "core", 80.0),
    ]
    result = group_zones(pairs, threshold=0.05)
    assert len(result.groups) == 2
    assert [(g.key, g.ledger.members) for g in result.pre_threshold_groups] == [
        (("lab", "perimeter"), ("Q",)),
        (("office", "core"), ("C",)),
        (("office", "perimeter"), ("P",)),
    ]


def test_threshold_zero_merges_nothing() -> None:
    pairs = [_pair("P", "office", "perimeter", 999.0), _pair("Q", "lab", "perimeter", 1.0)]
    assert group_zones(pairs, threshold=0.0).merges == ()


def test_threshold_outside_range_is_refused() -> None:
    pairs = [_pair("P", "office", "perimeter", 1.0)]
    with pytest.raises(ValueError, match="threshold"):
        group_zones(pairs, threshold=1.0)
    with pytest.raises(ValueError, match="threshold"):
        group_zones(pairs, threshold=-0.1)


# --- Similarity ----------------------------------------------------------------------------------


def test_intensities_of_a_ledger() -> None:
    ledger = _ledger("A", 100.0, lights=10.0, lights_on=0.5, heat=20.0, cool=25.0, oa=0.002, dhw=0.0001)
    values = intensities(ledger)
    assert values["gain_density:lights"] == pytest.approx(10.0)
    assert values["gain_hours:lights"] == pytest.approx(0.5 * HOURS)
    assert values["heating_setpoint"] == pytest.approx(20.0)
    assert values["cooling_setpoint"] == pytest.approx(25.0)
    assert values["outdoor_air_per_area"] == pytest.approx(0.002 * HOURS)
    assert values["hot_water_per_area"] == pytest.approx(0.0001 * HOURS)


def test_distance_scales_each_component_by_the_building_value() -> None:
    a = _ledger("A", 100.0, lights=10.0, heat=20.0)
    b = _ledger("B", 100.0, lights=20.0, heat=20.0)
    building = building_intensities([a, b])
    assert building["gain_density:lights"] == pytest.approx(15.0)
    # Only the lights density differs: (20 - 10) / 15.
    assert distance(a, b, building) == pytest.approx(10.0 / 15.0)
    assert distance(a, a, building) == 0.0


def test_setpoint_of_a_group_without_heated_area_takes_the_building_value() -> None:
    a = _ledger("A", 100.0, heat=20.0)
    b = _ledger("B", 100.0, heat=20.0).model_copy(update={"heating_setpoint": WeightedProfile()})
    building = building_intensities([a, b])
    assert distance(a, b, building) == 0.0


# --- Properties ----------------------------------------------------------------------------------

_USES = ("alpha", "beta", "gamma", "delta")


@st.composite
def _models(draw: st.DrawFn) -> list[tuple[ClassifiedZone, GroupLedger]]:
    count = draw(st.integers(min_value=1, max_value=12))
    pairs = []
    for i in range(count):
        pairs.append(
            _pair(
                f"Z{i:02d}",
                draw(st.sampled_from(_USES)),
                draw(st.sampled_from(("perimeter", "core"))),
                draw(st.floats(min_value=1.0, max_value=1000.0)),
                lights=draw(st.floats(min_value=0.0, max_value=30.0)),
                heat=draw(st.floats(min_value=15.0, max_value=23.0)),
                oa=draw(st.floats(min_value=0.0, max_value=0.01)),
            )
        )
    return pairs


_LAYOUTS = st.sampled_from(list(Layout))
_THRESHOLDS = st.floats(min_value=0.0, max_value=0.5)


def _exposure_of(layout: Layout, key: tuple[str, ...]) -> str | None:
    return dict(zip(layout.distinctions, key, strict=True)).get("exposure")


@given(_models(), _LAYOUTS, _THRESHOLDS)
def test_grouping_conserves_members_and_area(pairs: list, layout: Layout, threshold: float) -> None:
    result = group_zones(pairs, layout=layout, threshold=threshold)
    members = [m for g in result.groups for m in g.ledger.members]
    assert sorted(members) == sorted(z.zone.name for z, _ in pairs)
    total = sum(ledger.floor_area for _, ledger in pairs)
    assert math.isclose(sum(g.ledger.floor_area for g in result.groups), total, rel_tol=1e-12)
    assert math.isclose(sum(g.ledger.floor_area for g in result.pre_threshold_groups), total, rel_tol=1e-12)


@given(_models(), _LAYOUTS, _THRESHOLDS)
def test_no_group_stays_small_while_it_has_an_eligible_partner(pairs: list, layout: Layout, threshold: float) -> None:
    result = group_zones(pairs, layout=layout, threshold=threshold)
    total = sum(g.ledger.floor_area for g in result.groups)
    for small in result.groups:
        if small.ledger.floor_area / total >= threshold:
            continue
        partners = [
            g
            for g in result.groups
            if g is not small and _exposure_of(layout, g.key) == _exposure_of(layout, small.key)
        ]
        assert partners == []
    for merge in result.merges:
        assert _exposure_of(layout, merge.merged_key) == _exposure_of(layout, merge.into_key)
        assert merge.share < threshold


@given(_models(), _LAYOUTS, _THRESHOLDS, st.randoms(use_true_random=False))
def test_grouping_does_not_depend_on_zone_order(
    pairs: list, layout: Layout, threshold: float, rng: random.Random
) -> None:
    shuffled = list(pairs)
    rng.shuffle(shuffled)
    assert group_zones(shuffled, layout=layout, threshold=threshold) == group_zones(
        pairs, layout=layout, threshold=threshold
    )


@given(_models(), _LAYOUTS, _THRESHOLDS)
def test_pre_threshold_groups_stay_at_the_finest_key_under_every_layout(
    pairs: list, layout: Layout, threshold: float
) -> None:
    result = group_zones(pairs, layout=layout, threshold=threshold)
    assert result.pre_threshold_groups == finest_groups(pairs)
    expected = sorted({(z.space_use, z.exposure) for z, _ in pairs})
    assert [g.key for g in result.pre_threshold_groups] == expected


@given(_models(), _LAYOUTS, _LAYOUTS, _THRESHOLDS)
def test_grouping_from_pre_threshold_groups_equals_grouping_from_zones(
    pairs: list, source: Layout, target: Layout, threshold: float
) -> None:
    """`merge` regroups the report's pre-threshold groups: same result as reducing directly (FR-010)."""
    reduced = group_zones(pairs, layout=source, threshold=threshold)
    assert group(reduced.pre_threshold_groups, target, threshold) == group_zones(
        pairs, layout=target, threshold=threshold
    )


@given(_models(), _LAYOUTS)
def test_merged_distinctions_cover_every_group(pairs: list, layout: Layout) -> None:
    result = group_zones(pairs, layout=layout, threshold=0.1)
    if layout is FINEST:
        assert result.merged_distinctions == ()
        return
    assert [d.into_key for d in result.merged_distinctions] == _keys(result)
    finest_of = {m: (z.space_use, z.exposure) for z, ledger in pairs for m in ledger.members}
    for entry, grp in zip(result.merged_distinctions, result.groups, strict=True):
        assert entry.from_keys == tuple(sorted({finest_of[m] for m in grp.ledger.members}))
        assert entry.lost == layout.lost_from(FINEST)


# --- Coarser layouts (T067) -----------------------------------------------------------------------

_MIXED = [
    _pair("OP", "office", "perimeter", 300.0),
    _pair("OC", "office", "core", 200.0),
    _pair("RP", "retail", "perimeter", 250.0),
    _pair("RC", "retail", "core", 250.0),
]


@pytest.mark.parametrize(
    ("layout", "expected"),
    [
        (
            Layout.SPACE_USE_EXPOSURE,
            [("office", "core"), ("office", "perimeter"), ("retail", "core"), ("retail", "perimeter")],
        ),
        (Layout.SPACE_USE, [("office",), ("retail",)]),
        (Layout.CORE_PERIMETER, [("core",), ("perimeter",)]),
        (Layout.SINGLE_ZONE, [()]),
    ],
)
def test_each_layout_group_keys(layout: Layout, expected: list[tuple[str, ...]]) -> None:
    result = group_zones(_MIXED, layout=layout, threshold=0.0)
    assert _keys(result) == expected
    assert result.layout is layout


def test_merged_distinctions_of_core_perimeter() -> None:
    result = group_zones(_MIXED, layout=Layout.CORE_PERIMETER, threshold=0.0)
    assert result.merged_distinctions == (
        MergedDistinction(into_key=("core",), from_keys=(("office", "core"), ("retail", "core")), lost=("space_use",)),
        MergedDistinction(
            into_key=("perimeter",),
            from_keys=(("office", "perimeter"), ("retail", "perimeter")),
            lost=("space_use",),
        ),
    )


def test_merged_distinctions_of_single_zone() -> None:
    (entry,) = group_zones(_MIXED, layout=Layout.SINGLE_ZONE, threshold=0.0).merged_distinctions
    assert entry.into_key == ()
    assert entry.from_keys == (
        ("office", "core"),
        ("office", "perimeter"),
        ("retail", "core"),
        ("retail", "perimeter"),
    )
    assert entry.lost == ("space_use", "exposure")


def test_merged_distinctions_include_small_group_merges() -> None:
    pairs = [*_MIXED, _pair("LP", "lab", "perimeter", 10.0)]
    result = group_zones(pairs, layout=Layout.SPACE_USE, threshold=0.05)
    (lab_merge,) = result.merges
    assert lab_merge.merged_key == ("lab",)
    into = next(d for d in result.merged_distinctions if d.into_key == lab_merge.into_key)
    assert ("lab", "perimeter") in into.from_keys
    assert into.from_keys == tuple(sorted(into.from_keys))


def test_without_exposure_any_group_is_eligible() -> None:
    # SPACE_USE layout: the small lab group (core only) merges into the most similar group,
    # whatever its exposure.
    pairs = [
        _pair("OP", "office", "perimeter", 500.0, lights=10.0),
        _pair("RC", "retail", "core", 480.0, lights=25.0),
        _pair("LC", "lab", "core", 20.0, lights=11.0),
    ]
    result = group_zones(pairs, layout=Layout.SPACE_USE, threshold=0.05)
    assert [(m.merged_key, m.into_key) for m in result.merges] == [(("lab",), ("office",))]


def test_threshold_is_applied_once_to_the_requested_layout() -> None:
    # Default layout: (office, perimeter) is 3 % and merges into (retail, perimeter), the only
    # other perimeter group. Regrouping that to SPACE_USE would give office 50 %, retail 50 %.
    # Applied directly to SPACE_USE groups, nothing is small: office keeps its perimeter zone.
    pairs = [
        _pair("OP", "office", "perimeter", 30.0),
        _pair("OC", "office", "core", 500.0),
        _pair("RP", "retail", "perimeter", 470.0),
    ]
    finest = group_zones(pairs, threshold=0.05)
    assert [(m.merged_key, m.into_key) for m in finest.merges] == [
        (("office", "perimeter"), ("retail", "perimeter")),
    ]
    direct = group_zones(pairs, layout=Layout.SPACE_USE, threshold=0.05)
    assert direct.merges == ()
    assert _members(direct) == {("office",): ("OC", "OP"), ("retail",): ("RP",)}
    # Merging from the default result regroups its pre-threshold groups, not its final groups.
    assert group(finest.pre_threshold_groups, Layout.SPACE_USE, 0.05) == direct


def test_group_validates_pre_threshold_groups() -> None:
    ledger = _ledger("A", 10.0)
    with pytest.raises(ValueError, match="finest"):
        group([Group(key=("office",), ledger=ledger)], Layout.SPACE_USE, 0.0)
    with pytest.raises(ValueError, match="exposure"):
        group([Group(key=("office", "attic"), ledger=ledger)], Layout.SPACE_USE, 0.0)
    with pytest.raises(ValueError, match="twice"):
        group(
            [Group(key=("office", "core"), ledger=ledger), Group(key=("office", "core"), ledger=_ledger("B", 1.0))],
            Layout.SPACE_USE,
            0.0,
        )
    with pytest.raises(ValueError, match="no conditioned"):
        group([], Layout.SPACE_USE, 0.0)


def test_group_accepts_pre_threshold_groups_in_any_order() -> None:
    pre = finest_groups(_MIXED)
    assert group(list(reversed(pre)), Layout.CORE_PERIMETER, 0.05) == group(pre, Layout.CORE_PERIMETER, 0.05)


def test_layout_with_exposure_notes_a_missing_exposure() -> None:
    pairs = [_pair("A", "office", "perimeter", 10.0), _pair("B", "retail", "perimeter", 10.0)]
    for layout in (Layout.CORE_PERIMETER, Layout.SPACE_USE_EXPOSURE):
        notes = group_zones(pairs, layout=layout, threshold=0.0).notes
        assert len(notes) == 1
        assert "no core zones" in notes[0]
    for layout in (Layout.SPACE_USE, Layout.SINGLE_ZONE):
        assert group_zones(pairs, layout=layout, threshold=0.0).notes == ()
    assert group_zones(_MIXED, layout=Layout.CORE_PERIMETER, threshold=0.0).notes == ()


# --- Bar building at core/perimeter (US2 scenario 3) ----------------------------------------------


@pytest.fixture(scope="module")
def bar_zones() -> list[ClassifiedZone]:
    sources = load_sources(MODELS / "bar_building.idf", MODELS / "bar_building.sql")
    evaluator = ScheduleEvaluator(sources.model, sources.run_period.calendar)
    return [z for z in classify(build_inventory(sources, evaluator), evaluator) if z.conditioned]


def test_bar_building_at_core_perimeter_has_a_perimeter_group_only(bar_zones: list[ClassifiedZone]) -> None:
    pairs = [(z, _ledger(z.zone.name, z.zone.floor_area * z.zone.multiplier)) for z in bar_zones]
    result = group_zones(pairs, layout=Layout.CORE_PERIMETER, threshold=0.05)
    assert _keys(result) == [("perimeter",)]
    assert result.groups[0].ledger.members == tuple(sorted(z.zone.name for z in bar_zones))
    assert result.notes == ("no core zones: the core_perimeter layout has a perimeter group only",)
    (entry,) = result.merged_distinctions
    assert entry.into_key == ("perimeter",)
    assert entry.lost == ("space_use",)
    assert all(key[1] == "perimeter" for key in entry.from_keys)


def test_result_types_are_frozen() -> None:
    result = group_zones(_MIXED, threshold=0.0)
    with pytest.raises((TypeError, ValueError)):
        result.groups[0].key = ("x",)  # type: ignore[misc]
    merge = SmallGroupMerge(merged_key=("a",), into_key=("b",), share=0.01, distance=0.5)
    with pytest.raises((TypeError, ValueError)):
        merge.share = 0.2  # type: ignore[misc]
