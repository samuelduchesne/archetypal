"""The translation report: losses versus notes, summary, deterministic JSON, strict mode (spec 003 T014)."""

from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from archetypal.errors import LossyTranslationError
from archetypal.umi.correspondence import LIBRARY_RULES, UPSTREAM_ITEMS, rule_ids
from archetypal.umi.report import (
    NOTHING_LOST,
    SCHEMA_PATH,
    Findings,
    Loss,
    LossKind,
    Note,
    NoteKind,
    SourceInfo,
    TranslationReport,
    main,
    report_json_schema,
)

ROOT = Path(__file__).resolve().parents[3]
ROADMAP = ROOT / ".specify" / "memory" / "roadmap.md"
SOURCE = SourceInfo(
    path="B2.json", sha256="0" * 64, dialect="core-json-pre-2023", archetypal="3.0.0", epinterface="1.5.0"
)


def loss(subject: str = "B_Off_0", location: str = "/BuildingTemplates/0/PartitionRatio", **changes: object) -> Loss:
    fields: dict[str, object] = {
        "kind": LossKind.LOST,
        "subject": subject,
        "location": location,
        "value": 0.35,
        "rule": "building.partition_ratio",
        "reason": "SBEM has no partition ratio yet",
        "upstream": "UP-9",
    }
    return Loss.model_validate(fields | changes)


def note(subject: str = "B_Off_0", location: str = "/DomesticHotWaterSettings/0/IsOn") -> Note:
    return Note(
        kind=NoteKind.DEFAULTED,
        subject=subject,
        location=location,
        value=True,
        rule="format.basilisk_default",
        reason="absent from the file; Basilisk's default used",
    )


def report(losses: list[Loss] | None = None, notes: list[Note] | None = None, **changes: object) -> TranslationReport:
    fields: dict[str, object] = {
        "direction": "umi_to_sbem",
        "source": SOURCE,
        "subjects": ["B_Off_0", "B_Res_0"],
        "losses": losses or [],
        "notes": notes or [],
    }
    return TranslationReport.model_validate(fields | changes)


def test_schema_version_and_directions() -> None:
    assert report().schema_version == "1.0"
    assert report(direction="sbem_to_umi").direction == "sbem_to_umi"
    with pytest.raises(ValidationError):
        report(direction="umi_to_umi")
    with pytest.raises(ValidationError):
        report(schema_version="2.0")


def test_summary_is_nothing_lost_iff_no_losses() -> None:
    assert report().summary == NOTHING_LOST == "Nothing was lost."
    assert report(notes=[note()]).summary == NOTHING_LOST, "notes are not losses"
    assert report(losses=[loss()]).summary != NOTHING_LOST


def test_summary_counts_losses_by_kind() -> None:
    losses = [
        loss(),
        loss(location="/a"),
        loss("B_Res_0", kind=LossKind.APPROXIMATE, rule="wwr.uniform", upstream=None),
        loss("", "/Zones/3", kind=LossKind.UNUSED, rule="library.unused", upstream=None),
    ]
    assert (
        report(losses=losses).summary
        == "4 values lost (2 lost, 1 approximate, 1 unused) in 2 templates and the library."
    )
    assert report(losses=[loss()]).summary == "1 value lost (1 lost) in 1 template."
    assert report(losses=[loss()], direction="sbem_to_umi").summary == "1 value lost (1 lost) in 1 archetype."
    assert report(losses=losses[3:]).summary == "1 value lost (1 unused) in the library."


def test_losses_and_notes_are_sorted_by_subject_then_location() -> None:
    losses = [
        loss("b", "/2"),
        loss("a", "/9"),
        loss("b", "/1"),
        loss("", "/0", kind=LossKind.UNUSED, rule="library.unused"),
    ]
    notes = [note("z", "/1"), note("a", "/2"), note("a", "/1")]
    built = report(losses=losses, notes=notes)
    assert [(item.subject, item.location) for item in built.losses] == [
        ("", "/0"),
        ("a", "/9"),
        ("b", "/1"),
        ("b", "/2"),
    ]
    assert [(item.subject, item.location) for item in built.notes] == [("a", "/1"), ("a", "/2"), ("z", "/1")]


def test_equal_reports_give_byte_identical_json() -> None:
    losses = [loss("b", "/2"), loss("a", "/1", value=[1.0, {"x": None}])]
    first = report(losses=losses, notes=[note("b"), note("a")]).to_json()
    second = report(losses=list(reversed(losses)), notes=[note("a"), note("b")]).to_json()
    assert first == second
    assert first.endswith("}\n")
    assert first.splitlines()[1] == '  "schema_version": "1.0",'


@pytest.mark.parametrize("value", [0.1 + 0.2, 1e-17, 1 / 3, 123456789.123456789, -2.5e300])
def test_floats_keep_repr_precision(value: float) -> None:
    text = report(losses=[loss(value=value)]).to_json()
    assert repr(value) in text
    assert json.loads(text)["losses"][0]["value"] == value


def test_json_round_trip() -> None:
    built = report(losses=[loss(replacement=0.3)], notes=[note()])
    assert TranslationReport.from_json(built.to_json()) == built
    data = json.loads(built.to_json())
    assert data["summary"] == built.summary
    assert list(data) == ["schema_version", "direction", "source", "subjects", "losses", "notes", "summary"]


def test_reading_refuses_a_summary_that_does_not_match() -> None:
    data = json.loads(report(losses=[loss()]).to_json())
    data["summary"] = NOTHING_LOST
    with pytest.raises(ValidationError, match="does not match"):
        TranslationReport.model_validate(data)


def test_unknown_fields_are_refused() -> None:
    with pytest.raises(ValidationError):
        report(extra=1)


def test_report_and_entries_are_frozen() -> None:
    built = report(losses=[loss()])
    with pytest.raises(ValidationError):
        built.direction = "sbem_to_umi"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        built.losses[0].value = 1  # type: ignore[misc]


@pytest.mark.parametrize("rule_id", sorted(rule_ids() | LIBRARY_RULES))
def test_loss_accepts_table_and_library_rules(rule_id: str) -> None:
    assert loss(rule=rule_id).rule == rule_id


def test_loss_refuses_an_unknown_rule() -> None:
    with pytest.raises(ValidationError, match="neither a rule"):
        loss(rule="no.such_rule")


def test_note_rule_is_free() -> None:
    assert note().rule == "format.basilisk_default"


def test_upstream_is_a_roadmap_item() -> None:
    items = set(re.findall(r"^- \*\*(UP-\d+) —", ROADMAP.read_text(encoding="utf-8"), flags=re.MULTILINE))
    assert items >= UPSTREAM_ITEMS
    for item in sorted(UPSTREAM_ITEMS):
        assert loss(upstream=item).upstream == item
    for bad in ("UP-99", "UP9", "up-9", ""):
        with pytest.raises(ValidationError):
            loss(upstream=bad)


# --- strict mode (FR-011a, SC-006a) ---------------------------------------------------------------


def test_strict_mode_fails_iff_losses_are_not_empty() -> None:
    report().raise_for_losses("B2.json")
    report(notes=[note()]).raise_for_losses("B2.json")  # notes never fail strict mode
    lossy = report(losses=[loss()], notes=[note()])
    with pytest.raises(LossyTranslationError) as caught:
        lossy.raise_for_losses("B2.json")
    assert caught.value.report is lossy
    assert caught.value.subject == "B2.json"
    assert lossy.summary in str(caught.value)


def test_lossless() -> None:
    assert report(notes=[note()]).lossless
    assert not report(losses=[loss()]).lossless


# --- the published schema -------------------------------------------------------------------------


def test_schema_equals_the_committed_file() -> None:
    committed = json.loads((ROOT / SCHEMA_PATH).read_text(encoding="utf-8"))
    assert report_json_schema() == committed


def test_schema_describes_the_written_file() -> None:
    schema = report_json_schema()
    assert schema["$id"].endswith("/schemas/translation-report-1.0.json")
    assert set(schema["required"]) == set(json.loads(report().to_json()))
    assert schema["$defs"]["LossKind"]["enum"] == [kind.value for kind in LossKind]
    assert schema["$defs"]["NoteKind"]["enum"] == [kind.value for kind in NoteKind]


def test_schema_command_writes_the_schema(tmp_path: Path) -> None:
    target = tmp_path / "schemas" / "report.json"
    assert main(["--schema", str(target)]) == 0
    assert target.read_text(encoding="utf-8") == (ROOT / SCHEMA_PATH).read_text(encoding="utf-8")


def test_schema_command_without_option_prints_help(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 2
    assert "--schema" in capsys.readouterr().out


def test_source_info_current_names_installed_versions() -> None:
    source = SourceInfo.current("some/dir/B2.json", sha256="a" * 64, dialect="core-json")
    assert source.path == "B2.json"
    assert source.archetypal
    assert source.epinterface
    assert SourceInfo.current().path is None
    with pytest.raises(ValidationError):
        SourceInfo(sha256="xyz", archetypal="1", epinterface="1")


def test_unset_fields_are_noted_once_per_component() -> None:
    findings = Findings()
    component = SimpleNamespace(Category=None, Cost=None, Density=2000.0)
    findings.unset(component, ("Category", "Cost", "Density"), "office", "perimeter.Envelope", "construction.sets")
    [note] = findings.notes
    assert (note.kind, note.location, note.value) == (NoteKind.DEFAULTED, "perimeter.Envelope", ["Category", "Cost"])
    findings.unset(component, ("Density",), "office", "perimeter.Envelope", "construction.sets")
    assert len(findings.notes) == 1
