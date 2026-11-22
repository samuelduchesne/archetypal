"""Reading UMI libraries into SBEM archetypes (spec 003, T051, US2, R4, R11, R14)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest
from epinterface.sbem.archetype import Archetype

import archetypal
from archetypal.errors import InputError, LossyTranslationError, UmiValidationError
from archetypal.umi import TranslationReport, UmiImport, read_umi
from archetypal.umi.report import LossKind

if TYPE_CHECKING:
    from archetypal.umi.report import Loss

UMI = Path(__file__).parents[2] / "fixtures" / "umi"
EDGE = UMI / "edge"
B2 = UMI / "BostonTemplateLibrary_2.json"
SAMPLES = [B2, UMI / "BostonTemplateLibrary_nodup.json", UMI / "umi_samples_BostonTemplateLibrary.json"]
READABLE = [
    *SAMPLES,
    *(
        EDGE / f"{name}.json"
        for name in (
            "archsim_dialect",
            "duplicate_names",
            "misaligned_parts",
            "no_templates",
            "shared_zone",
            "unused_components",
        )
    ),
]

Json = dict[str, object]


def template_names(path: Path) -> list[str]:
    document = cast("Json", json.loads(path.read_text(encoding="utf-8-sig")))
    return [cast("str", template["Name"]) for template in cast("list[Json]", document["BuildingTemplates"])]


def losses(result: UmiImport, kind: LossKind) -> list[Loss]:
    return [loss for loss in result.report.losses if loss.kind is kind]


@pytest.fixture(scope="module")
def b2() -> UmiImport:
    return read_umi(B2)


# --- Scenario 1: one archetype per template, core and perimeter by geometry ---------------------


def test_one_archetype_per_template_in_order(b2: UmiImport) -> None:
    assert [archetype.Name for archetype in b2.archetypes] == template_names(B2)
    assert len(b2.archetypes) == 4
    assert b2.report.subjects == template_names(B2)


def test_core_and_perimeter_groups_with_unset_shares(b2: UmiImport) -> None:
    for archetype in b2.archetypes:
        assert [(group.Name, group.Exposure, group.FloorAreaShare) for group in archetype.Groups] == [
            ("core", "core", None),
            ("perimeter", "perimeter", None),
        ]


def test_descriptive_fields_are_lost_until_up9(b2: UmiImport) -> None:
    metadata = [loss for loss in b2.report.losses if loss.rule == "building.metadata"]
    assert metadata
    assert all(loss.upstream == "UP-9" for loss in metadata)
    assert all(loss.location.startswith("/BuildingTemplates/") for loss in metadata)


def test_window_to_wall_ratio_on_every_orientation(b2: UmiImport) -> None:
    for archetype in b2.archetypes:
        assert archetype.Geometry.WindowToWallRatio is not None
        ratios = set(archetype.Geometry.WindowToWallRatio.values())
        assert len(ratios) == 1


def test_report_source(b2: UmiImport) -> None:
    source = b2.report.source
    assert b2.report.direction == "umi_to_sbem"
    assert source.path == B2.name
    assert source.sha256 == hashlib.sha256(B2.read_bytes()).hexdigest()
    assert source.dialect == "core-json-pre-2023"
    assert source.archetypal == archetypal.__version__


@pytest.mark.parametrize("path", READABLE, ids=lambda path: path.stem)
def test_every_archetype_validates_as_epinterface_model(path: Path) -> None:
    result = read_umi(path)
    for archetype in result.archetypes:
        again = Archetype.model_validate_json(archetype.model_dump_json())
        assert again == archetype


def test_reading_is_deterministic() -> None:
    first, second = read_umi(B2), read_umi(B2)
    assert first.report.to_json() == second.report.to_json()
    assert [a.model_dump_json() for a in first.archetypes] == [a.model_dump_json() for a in second.archetypes]


def test_shared_zone_gives_equal_groups() -> None:
    (archetype,) = read_umi(EDGE / "shared_zone.json").archetypes
    core, perimeter = archetype.Groups
    assert core.Zone == perimeter.Zone


def test_misaligned_parts_are_approximate_in_march_and_october() -> None:
    result = read_umi(EDGE / "misaligned_parts.json")
    months = {
        cast("dict[str, object]", loss.value)["month"]
        for loss in losses(result, LossKind.APPROXIMATE)
        if loss.rule == "schedule.months"
    }
    assert months == {"March", "October"}


def test_window_settings_and_layers_are_reported(b2: UmiImport) -> None:
    rules = {loss.rule for loss in b2.report.losses}
    assert "window.simple_from_layers" in rules


def test_upstream_fields_without_a_function_are_reported_from_the_table() -> None:
    result = read_umi(EDGE / "unused_components.json")
    rules = {loss.rule for loss in result.report.losses}
    # The template's window settings differ from Basilisk's defaults on IsShadingSystemOn.
    assert "window.settings" in rules
    assert any(loss.location == "/BuildingTemplates/0/Windows/IsShadingSystemOn" for loss in result.report.losses)


# --- Scenario 2: name collisions -------------------------------------------------------------------


def test_duplicate_names_keep_both_components_and_templates() -> None:
    result = read_umi(EDGE / "duplicate_names.json")
    assert [archetype.Name for archetype in result.archetypes] == ["Office", "Office #2"]
    renamed = {(str(loss.value), str(loss.replacement)) for loss in losses(result, LossKind.RENAMED)}
    assert ("Concrete", "Concrete #2") in renamed
    assert ("Clear 6mm", "Clear 6mm #2") in renamed
    assert ("Office", "Office #2") in renamed
    assert all(loss.rule == "names.collision" for loss in losses(result, LossKind.RENAMED))
    materials = {
        (layer.ConstructionMaterial.Name, layer.ConstructionMaterial.Conductivity)
        for archetype in result.archetypes
        for group in archetype.Groups
        for assembly in (
            group.Zone.Envelope.Assemblies.FacadeAssembly,
            group.Zone.Envelope.Assemblies.FloorCeilingAssembly,
            group.Zone.Envelope.Assemblies.FlatRoofAssembly,
            group.Zone.Envelope.Assemblies.GroundSlabAssembly,
            group.Zone.Envelope.Assemblies.PartitionAssembly,
        )
        for layer in assembly.Layers
    }
    assert ("Concrete", 1.95) in materials
    assert ("Concrete #2", 1.4) in materials


# --- Scenario 3: invalid libraries -----------------------------------------------------------------


def test_invalid_library_raises_and_returns_nothing() -> None:
    result: UmiImport | None = None
    with pytest.raises(UmiValidationError):
        result = read_umi(EDGE / "missing_reference.json")
    assert result is None


# --- Unused components and empty libraries ---------------------------------------------------------


def test_no_templates_lists_every_component_as_unused() -> None:
    result = read_umi(EDGE / "no_templates.json")
    assert result.archetypes == ()
    unused = losses(result, LossKind.UNUSED)
    assert len(unused) == 22
    assert all(loss.rule == "library.unused" and loss.subject == "" for loss in unused)
    assert all("no building template" in loss.reason for loss in unused)


def test_unused_components_are_listed() -> None:
    result = read_umi(EDGE / "unused_components.json")
    assert len(result.archetypes) == 1
    assert {str(loss.value) for loss in losses(result, LossKind.UNUSED)} == {"Brick", "Brick wall", "Half on"}


def test_boston_library_unused_components() -> None:
    assert len(losses(read_umi(B2), LossKind.UNUSED)) == 29


# --- Writing the result, strict mode ------------------------------------------------------------------


def test_read_umi_writes_no_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    read_umi(B2)
    assert list(tmp_path.iterdir()) == []


def test_write_gives_one_file_per_archetype_and_the_loss_report(b2: UmiImport, tmp_path: Path) -> None:
    written = b2.write(tmp_path)
    names = sorted(path.name for path in written)
    expected = sorted([*(f"{name}.sbem.json" for name in template_names(B2)), "BostonTemplateLibrary_2.loss.json"])
    assert names == expected
    report = TranslationReport.from_json((tmp_path / "BostonTemplateLibrary_2.loss.json").read_text(encoding="utf-8"))
    assert report == b2.report
    first = Archetype.model_validate_json((tmp_path / f"{template_names(B2)[0]}.sbem.json").read_text(encoding="utf-8"))
    assert first == b2.archetypes[0]


def test_write_refuses_existing_files(b2: UmiImport, tmp_path: Path) -> None:
    b2.write(tmp_path)
    with pytest.raises(InputError, match="already exists"):
        b2.write(tmp_path)
    assert b2.write(tmp_path, overwrite=True)


def test_strict_mode_raises_when_something_is_lost() -> None:
    with pytest.raises(LossyTranslationError) as caught:
        read_umi(B2, strict=True)
    assert cast("TranslationReport", caught.value.report).losses


def test_read_umi_is_exported() -> None:
    assert archetypal.read_umi is read_umi
    assert "read_umi" in archetypal.__all__
