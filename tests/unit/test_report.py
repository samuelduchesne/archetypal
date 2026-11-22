"""Tests for the reduction report (spec 002, T040, T058; contracts/reduction-report.md).

The report's invariants 1-7 are checked by `check_report_invariants`, a reusable function the
end-to-end tests and `reduce` itself call. Here it runs on a hand-built report that holds every
invariant, and on copies that each break one. The published JSON Schema must validate a file
written by `archetypal.io`. A last test runs the checks on real fixture reductions once
`archetypal.reduction.reduce` exists.
"""

from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from pydantic import ValidationError

from archetypal import io
from archetypal.errors import ReductionError
from archetypal.reduction.features import NotRepresented
from archetypal.reduction.ledger import EnvelopeAssignment, GainTotals, GroupLedger, WeightedProfile
from archetypal.reduction.options import Layout, ReductionOptions
from archetypal.reduction.report import (
    RULE_IDS,
    SCHEMA_PATH,
    SCHEMA_VERSION,
    BuildingBlock,
    ExcludedZone,
    GroupMember,
    MergedDistinction,
    Parameter,
    PreThresholdGroup,
    ReductionReport,
    ReportGroup,
    Reproducibility,
    SmallGroupMerge,
    check_accounting,
    check_area,
    check_mergeable,
    check_not_represented,
    check_parameters,
    check_report_invariants,
    check_reproducible,
    check_schema_version,
    gather_not_represented,
    group_name,
    main,
    raise_for_invariants,
    report_json_schema,
)

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = ROOT / "tests" / "fixtures"
HOURS = 6
SHA = "0" * 64

# --- a hand-built report that holds every invariant ------------------------------------------------

ZONES: dict[str, tuple[int, float, str, str]] = {
    # zone: (multiplier, floor area of one copy, space use, exposure)
    "Office_P": (1, 60.0, "office", "perimeter"),
    "Office_C": (2, 20.0, "office", "core"),
    "Store_P": (1, 5.0, "storage", "perimeter"),
}
CONDITIONED_AREA = 105.0


def zone_ledger(zone: str) -> GroupLedger:
    multiplier, area, _, _ = ZONES[zone]
    total = multiplier * area
    return GroupLedger(
        members=(zone,),
        floor_area=total,
        gains={"people": GainTotals(installed=total / 10.0, hourly=np.full(HOURS, total / 20.0))},
        heating_setpoint=WeightedProfile(weight=total, weighted=np.full(HOURS, 21.0 * total)),
    )


def member(zone: str) -> GroupMember:
    multiplier, area, space_use, exposure = ZONES[zone]
    return GroupMember(
        zone=zone,
        multiplier=multiplier,
        floor_area=area,
        space_use=space_use,
        space_use_source="signature",
        exposure=exposure,  # pyright: ignore[reportArgumentType]
    )


def report_group(key: tuple[str, ...], zones: tuple[str, ...]) -> ReportGroup:
    ledger = sum((zone_ledger(z) for z in zones), GroupLedger())
    return ReportGroup(
        name=group_name(key),
        key=key,
        members=tuple(member(z) for z in zones),
        floor_area=ledger.floor_area,
        floor_area_share=ledger.floor_area / CONDITIONED_AREA,
        ledger=ledger,
    )


def make_report(**update: Any) -> ReductionReport:
    perimeter = report_group(("office", "perimeter"), ("Office_P", "Store_P"))
    core = report_group(("office", "core"), ("Office_C",))
    groups = (perimeter, core)
    parameters = [Parameter(group=None, path="BuildingGeometry.NumStoreys", value=1, rule="geometry.storeys")]
    for group in groups:
        parameters.append(
            Parameter(
                group=group.name, path="ZoneGroup.FloorAreaShare", value=group.floor_area_share, rule="area.share"
            )
        )
        density = group.ledger.gains["people"].installed / group.floor_area
        parameters.append(
            Parameter(group=group.name, path="Space.Occupancy.PeopleDensity", value=density, rule="gain.density")
        )
    data: dict[str, Any] = {
        "reproducibility": Reproducibility(
            archetypal="3.0.0",
            epinterface="1.2.0",
            idfkit="0.13.0",
            energyplus="24.2.0",
            model_sha256=SHA,
            results_sha256="1" * 64,
            weather_sha256=None,
            options=ReductionOptions(),
        ),
        "groups": groups,
        "pre_threshold_groups": tuple(
            PreThresholdGroup(key=(ZONES[z][2], ZONES[z][3]), ledger=zone_ledger(z)) for z in ZONES
        ),
        "parameters": tuple(parameters),
        "excluded_zones": (
            ExcludedZone(
                zone="Attic",
                multiplier=1,
                floor_area=60.0,
                role="attic",
                reason="unconditioned, has a roof",
                envelope=(
                    EnvelopeAssignment(
                        source_zone="Attic", target_zone="Office_P", envelope_class="roof", area=60.0, share=1.0
                    ),
                ),
            ),
            ExcludedZone(zone="Plenum", multiplier=1, floor_area=20.0, role="excluded", reason="return plenum"),
        ),
        "small_group_merges": (
            SmallGroupMerge(
                key=("storage", "perimeter"),
                into_key=("office", "perimeter"),
                share=5.0 / CONDITIONED_AREA,
                distance=0.25,
            ),
        ),
        "not_represented": (
            NotRepresented(
                feature="Daylighting controls",
                effect="dims lights with daylight",
                object_type="Daylighting:Controls",
                objects=("DC1",),
                affected_zones=("Office_P",),
                affected_groups=(group_name(("office", "perimeter")),),
            ),
        ),
        "unattributed_energy": {"NaturalGas": 1.0e6},
        "building": BuildingBlock(conditioned_floor_area=CONDITIONED_AREA, storey_ratio=1.0),
    }
    data.update(update)
    return ReductionReport(**data)


ALL_ZONES = ("Attic", "Office_C", "Office_P", "Plenum", "Store_P")


def messages(report: ReductionReport, **kwargs: Any) -> list[str]:
    return check_report_invariants(report, **kwargs)


def numbers(found: list[str]) -> set[int]:
    return {int(text.split()[1]) for text in found}


# --- the valid report ------------------------------------------------------------------------------


def test_valid_report_holds_every_invariant() -> None:
    report = make_report()
    assert (
        messages(
            report,
            zone_names=ALL_ZONES,
            zone_roles={"Attic": "attic", "Plenum": "excluded"},
            conditioned_floor_area=CONDITIONED_AREA,
            set_parameters=[(None, "BuildingGeometry.NumStoreys")],
            expected_not_represented=report.not_represented,
        )
        == []
    )
    raise_for_invariants(report)


def test_schema_version_is_1_0() -> None:
    assert SCHEMA_VERSION == "1.0"
    assert make_report().schema_version == "1.0"


def test_rule_ids_are_the_derivation_table() -> None:
    assert {"area.share", "gain.density", "geometry.storeys", "efficiency.rated", "zone.attic"} <= RULE_IDS
    assert all("." in rule for rule in RULE_IDS)


def test_arrays_are_sorted_whatever_the_input_order() -> None:
    report = make_report()
    shuffled = make_report(
        groups=tuple(reversed(report.groups)),
        pre_threshold_groups=tuple(reversed(report.pre_threshold_groups)),
        parameters=tuple(reversed(report.parameters)),
        excluded_zones=tuple(reversed(report.excluded_zones)),
    )
    assert io.dumps(shuffled) == io.dumps(report)
    assert [g.key for g in report.groups] == sorted(g.key for g in report.groups)
    assert [z.zone for z in report.excluded_zones] == ["Attic", "Plenum"]
    assert [m.zone for m in report.groups[1].members] == ["Office_P", "Store_P"]


def test_options_mapping_is_written_sorted() -> None:
    options = ReductionOptions(space_use_mapping={"b": "x", "a": "y"})
    first = make_report(reproducibility=make_report().reproducibility.model_copy(update={"options": options}))
    block = Reproducibility.model_validate(first.reproducibility.model_dump())
    assert list(json.loads(io.dumps(block))["options"]["space_use_mapping"]) == ["a", "b"]


def test_report_round_trips_with_profiles() -> None:
    report = make_report()
    text = io.dumps(report)
    again = ReductionReport.model_validate_json(text)
    assert io.dumps(again) == text
    assert again == report
    data = json.loads(text)
    profile = data["groups"][0]["ledger"]["heating_setpoint"]["weighted"]
    assert profile["encoding"] == "base64-float64-le"
    assert profile["length"] == HOURS
    assert "timestamp" not in text


def test_reproducibility_current_reads_installed_versions() -> None:
    block = Reproducibility.current(
        energyplus_version=(24, 2, 0),
        model_sha256=SHA,
        results_sha256=SHA,
        weather_sha256=None,
        options=ReductionOptions(),
    )
    assert block.energyplus == "24.2.0"
    assert block.archetypal
    assert block.epinterface
    assert block.idfkit


def test_reproducibility_refuses_bad_hashes() -> None:
    with pytest.raises(ValidationError):
        Reproducibility(
            archetypal="1",
            epinterface="1",
            idfkit="1",
            energyplus="24.2.0",
            model_sha256="xyz",
            results_sha256=SHA,
            options=ReductionOptions(),
        )


def test_reader_accepts_every_1_x_file() -> None:
    data = json.loads(io.dumps(make_report()))
    data["schema_version"] = "1.7"
    data["a_field_added_in_1_7"] = {"anything": 1}
    data["groups"][0]["another_new_field"] = 3
    report = ReductionReport.model_validate(data)
    assert report.schema_version == "1.7"
    assert check_schema_version(report) == []


@pytest.mark.parametrize("version", ["2.0", "0.9", "1", "1.0.0.0", "v1.0", "1.01"])
def test_reader_refuses_other_major_versions(version: str) -> None:
    data = json.loads(io.dumps(make_report()))
    data["schema_version"] = version
    with pytest.raises(ValidationError):
        ReductionReport.model_validate(data)


def test_gather_not_represented_fills_groups_and_sorts() -> None:
    report = make_report()
    zone_groups = {m.zone: g.name for g in report.groups for m in g.members}
    found = gather_not_represented(
        [
            NotRepresented(feature="Z feature", effect="e", affected_zones=("Store_P", "Office_C")),
            NotRepresented(feature="A feature", effect="e", affected_zones=("Attic",), source="envelope"),
            NotRepresented(feature="Z feature", effect="e", affected_zones=("Store_P", "Office_C")),
        ],
        zone_groups,
    )
    assert [entry.feature for entry in found] == ["A feature", "Z feature"]
    assert found[0].affected_groups == ()
    assert found[1].affected_groups == tuple(sorted({zone_groups["Store_P"], zone_groups["Office_C"]}))


def test_group_name() -> None:
    assert group_name(("office", "core")) == "office / core"
    assert group_name(()) == "building"


# --- each invariant broken -------------------------------------------------------------------------


def test_invariant_1_zone_missing_or_twice() -> None:
    report = make_report()
    assert numbers(check_accounting(report, zone_names=(*ALL_ZONES, "Lost_zone"))) == {1}
    doubled = make_report(
        excluded_zones=(
            *report.excluded_zones,
            ExcludedZone(zone="Office_C", multiplier=2, floor_area=20.0, role="excluded", reason="?"),
        )
    )
    found = check_accounting(doubled)
    assert found
    assert numbers(found) == {1}
    assert numbers(messages(doubled)) >= {1}


def test_invariant_1_attic_role() -> None:
    report = make_report()
    assert numbers(check_accounting(report, zone_roles={"Attic": "basement"})) == {1}
    assert numbers(check_accounting(report, zone_roles={"Office_P": "attic"})) == {1}


def test_invariant_1_group_members_match_ledger() -> None:
    report = make_report()
    group = report.groups[0]
    wrong = group.model_copy(update={"members": (*group.members, member("Store_P"))})
    found = check_accounting(report.model_copy(update={"groups": (wrong, *report.groups[1:])}))
    assert numbers(found) == {1}


def test_invariant_2_shares() -> None:
    report = make_report()
    group = report.groups[0]
    wrong = group.model_copy(update={"floor_area_share": group.floor_area_share + 1e-6})
    found = check_area(report.model_copy(update={"groups": (wrong, *report.groups[1:])}))
    assert numbers(found) == {2}


def test_invariant_2_conditioned_area() -> None:
    report = make_report()
    assert numbers(check_area(report, conditioned_floor_area=CONDITIONED_AREA + 1.0)) == {2}
    building = BuildingBlock(conditioned_floor_area=CONDITIONED_AREA + 1.0, storey_ratio=1.0)
    assert numbers(check_area(report.model_copy(update={"building": building}))) == {2}
    group = report.groups[0]
    wrong = group.model_copy(update={"floor_area": group.floor_area + 1.0})
    assert numbers(check_area(report.model_copy(update={"groups": (wrong, *report.groups[1:])}))) == {2}


def test_invariant_3_unknown_rule_duplicate_and_missing() -> None:
    report = make_report()
    unknown = Parameter(group=None, path="BuildingGeometry.Height", value=3.0, rule="made.up")
    assert numbers(check_parameters(make_report(parameters=(*report.parameters, unknown)))) == {3}
    twice = make_report(parameters=(*report.parameters, report.parameters[0]))
    assert numbers(check_parameters(twice)) == {3}
    orphan = Parameter(group="no such group", path="X", value=1, rule="area.share")
    assert numbers(check_parameters(make_report(parameters=(*report.parameters, orphan)))) == {3}
    assert numbers(check_parameters(report, set_parameters=[(None, "BuildingGeometry.Height")])) == {3}
    assert numbers(check_parameters(report, set_parameters=[("office / core", "Space.Lighting.PowerDensity")])) == {3}


def test_invariant_4_feature_dropped() -> None:
    report = make_report()
    dropped = NotRepresented(feature="Exterior lights", effect="lights outside", object_type="Exterior:Lights")
    assert numbers(check_not_represented(report, expected=[dropped])) == {4}
    # Affected groups are filled by the report, so an expected entry matches without them.
    bare = report.not_represented[0].model_copy(update={"affected_groups": ()})
    assert check_not_represented(report, expected=[bare]) == []


def test_invariant_4_unknown_group_or_zone() -> None:
    report = make_report()
    entry = report.not_represented[0]
    bad_group = entry.model_copy(update={"affected_groups": ("nowhere",)})
    assert numbers(check_not_represented(make_report(not_represented=(bad_group,)))) == {4}
    bad_zone = entry.model_copy(update={"affected_zones": ("Ghost",)})
    assert numbers(check_not_represented(make_report(not_represented=(bad_zone,)))) == {4}


def test_invariant_5_pre_threshold_ledgers_must_cover_the_groups() -> None:
    report = make_report()
    missing = make_report(pre_threshold_groups=report.pre_threshold_groups[:-1])
    assert numbers(check_mergeable(missing)) == {5}


def test_invariant_5_finest_key() -> None:
    report = make_report()
    first = report.pre_threshold_groups[0]
    coarse = first.model_copy(update={"key": (first.key[0],)})
    found = check_mergeable(
        report.model_copy(update={"pre_threshold_groups": (coarse, *report.pre_threshold_groups[1:])})
    )
    assert numbers(found) == {5}
    wrong_key = first.model_copy(update={"key": ("lab", first.key[1])})
    found = check_mergeable(
        report.model_copy(update={"pre_threshold_groups": (wrong_key, *report.pre_threshold_groups[1:])})
    )
    assert numbers(found) == {5}


def test_invariant_5_ledger_totals_must_add_up() -> None:
    report = make_report()
    first = report.pre_threshold_groups[0]
    heavier = first.model_copy(update={"ledger": first.ledger.model_copy(update={"unheated_area": 7.0})})
    found = check_mergeable(
        report.model_copy(update={"pre_threshold_groups": (heavier, *report.pre_threshold_groups[1:])})
    )
    assert numbers(found) == {5}


def test_invariant_5_merged_distinctions() -> None:
    options = ReductionOptions(layout=Layout.SINGLE_ZONE)
    report = make_report()
    single = report_group((), ("Office_C", "Office_P", "Store_P"))
    finest = tuple(sorted(p.key for p in report.pre_threshold_groups))
    reproducibility = report.reproducibility.model_copy(update={"options": options})
    good = make_report(
        reproducibility=reproducibility,
        groups=(single,),
        parameters=(),
        small_group_merges=(),
        not_represented=(),
        merged_distinctions=(MergedDistinction(into_key=(), from_keys=finest, lost=("space_use", "exposure")),),
    )
    assert check_mergeable(good) == []
    assert check_report_invariants(good) == []
    missing = good.model_copy(update={"merged_distinctions": ()})
    assert numbers(check_mergeable(missing)) == {5}
    wrong = MergedDistinction(into_key=("office",), from_keys=finest, lost=("exposure",))
    assert numbers(check_mergeable(good.model_copy(update={"merged_distinctions": (wrong,)}))) == {5}
    unknown = MergedDistinction(into_key=(), from_keys=(("lab", "core"),), lost=("space_use", "exposure"))
    assert numbers(check_mergeable(good.model_copy(update={"merged_distinctions": (unknown,)}))) == {5}


def test_invariant_6_reproducibility_block() -> None:
    report = make_report()
    block = report.reproducibility.model_copy(update={"idfkit": ""})
    assert numbers(check_reproducible(report.model_copy(update={"reproducibility": block}))) == {6}
    block = report.reproducibility.model_copy(update={"results_sha256": "ABC"})
    assert numbers(check_reproducible(report.model_copy(update={"reproducibility": block}))) == {6}


def test_invariant_6_unsorted_arrays_are_not_reproducible() -> None:
    report = make_report()
    unsorted = report.model_copy(update={"excluded_zones": tuple(reversed(report.excluded_zones))})
    assert numbers(check_reproducible(unsorted)) == {6}


def test_invariant_7_schema_version() -> None:
    report = make_report()
    assert numbers(check_schema_version(report.model_copy(update={"schema_version": "2.0"}))) == {7}
    assert numbers(check_schema_version(report.model_copy(update={"schema_version": "one"}))) == {7}


def test_raise_for_invariants() -> None:
    report = make_report()
    with pytest.raises(ReductionError, match="invariant 1"):
        raise_for_invariants(report, zone_names=(*ALL_ZONES, "Lost_zone"))


# --- the published schema --------------------------------------------------------------------------


def test_schema_equals_the_committed_file() -> None:
    committed = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    assert report_json_schema() == committed


def test_schema_describes_the_written_file() -> None:
    schema = report_json_schema()
    assert schema["$id"].endswith("/schemas/reduction-report-1.0.json")
    written = json.loads(io.dumps(make_report()))
    assert set(schema["properties"]) == set(written)
    assert "base64-float64-le" in json.dumps(schema)  # the profile encoding is documented
    assert "NotRepresented" in schema["$defs"]


def test_schema_validates_a_written_file(tmp_path: Path) -> None:
    jsonschema = pytest.importorskip("jsonschema")
    schema = report_json_schema()
    jsonschema.Draft202012Validator.check_schema(schema)
    _, path = io.write(make_report(), make_report(), tmp_path, "office")
    validator = jsonschema.Draft202012Validator(schema)
    validator.validate(json.loads(path.read_text(encoding="utf-8")))
    broken = json.loads(path.read_text(encoding="utf-8"))
    broken["schema_version"] = "2.0"
    assert not validator.is_valid(broken)


def test_schema_command_writes_the_schema(tmp_path: Path) -> None:
    target = tmp_path / "schemas" / "report.json"
    assert main(["--schema", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == (ROOT / SCHEMA_PATH).read_text(encoding="utf-8")


def test_schema_command_without_option_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "--schema" in capsys.readouterr().out


# --- real reductions (once reduce exists) ----------------------------------------------------------


@pytest.mark.parametrize("fixture", ["three_zone", "ten_zone_multipliers", "ten_zone_explicit", "bar_building"])
def test_fixture_reductions_hold_every_invariant(fixture: str, tmp_path: Path) -> None:
    reduce = getattr(importlib.import_module("archetypal.reduction"), "reduce", None)
    if reduce is None:
        pytest.skip("archetypal.reduction.reduce does not exist yet (T059)")
    model = FIXTURES / "models" / f"{fixture}.idf"
    results = FIXTURES / "models" / f"{fixture}.sql"
    reduction = reduce(model, results)
    report: ReductionReport = reduction.report
    from idfkit.simulation import SQLResult  # noqa: PLC0415 - only needed once reduce exists

    from archetypal.reduction._sql_tables import read_zones  # noqa: PLC0415

    # The results upper-case zone names; the accounting check compares names case-insensitively.
    zone_names = [row.name for row in read_zones(SQLResult(results))]
    assert check_report_invariants(report, zone_names=zone_names) == []
    first, _ = reduction.write(tmp_path / "a", fixture)
    second, _ = reduce(model, results).write(tmp_path / "b", fixture)
    assert first.read_bytes() == second.read_bytes()
    report_a = io.report_path_for(first).read_bytes()
    report_b = io.report_path_for(second).read_bytes()
    assert report_a == report_b
    jsonschema = pytest.importorskip("jsonschema")
    jsonschema.Draft202012Validator(report_json_schema()).validate(json.loads(report_a))
