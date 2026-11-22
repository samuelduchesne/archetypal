"""UMI dialects: detection by shape, the Archsim key map and refused files (spec 003, T049, R2)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from archetypal.errors import UmiFormatError
from archetypal.umi import dialects, read_umi
from archetypal.umi.report import LossKind, NoteKind

if TYPE_CHECKING:
    from archetypal.umi.dialects import RawLibrary

UMI = Path(__file__).parents[2] / "fixtures" / "umi"
EDGE = UMI / "edge"
B2 = UMI / "BostonTemplateLibrary_2.json"
ND = UMI / "BostonTemplateLibrary_nodup.json"
UZ = UMI / "umi_samples_BostonTemplateLibrary.json"
ARCHSIM = EDGE / "archsim_dialect.json"

Json = dict[str, object]


def objects(raw: RawLibrary, collection: str) -> list[Json]:
    return cast("list[Json]", raw.document[collection])


# --- Detection -----------------------------------------------------------------------------


@pytest.mark.parametrize("path", [B2, ND], ids=["B2", "ND"])
def test_boston_libraries_are_core_json_before_2023(path: Path) -> None:
    raw = dialects.load(path)
    assert raw.dialect == dialects.CORE_JSON_PRE_2023
    assert raw.lost == ()


@pytest.mark.parametrize("marker", ["AdvancedModel", "UseAdvancedModel", "FuelType"])
def test_a_2023_field_makes_current_core_json(tmp_path: Path, marker: str) -> None:
    document = cast("Json", json.loads(B2.read_text(encoding="utf-8-sig")))
    if marker == "FuelType":
        cast("list[Json]", document["DomesticHotWaterSettings"])[0]["FuelType"] = 2
    else:
        document["StructureDefinitions"] = [{"$id": "s1", marker: {} if marker == "AdvancedModel" else True}]
    path = tmp_path / "current.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    assert dialects.load(path).dialect == dialects.CORE_JSON


def test_detect_reads_the_shape_alone() -> None:
    assert dialects.detect({"OpaqueMaterials": [{"$id": "1", "Comment": "x"}]}) == dialects.ARCHSIM_JSON
    assert dialects.detect({"OpaqueMaterials": [{"$id": "1", "Comments": "x"}]}) == dialects.CORE_JSON_PRE_2023
    assert dialects.detect({"StructureDefinitions": [{"UseAdvancedModel": False}]}) == dialects.CORE_JSON


def test_hash_is_of_the_bytes_read() -> None:
    import hashlib  # noqa: PLC0415 - only here

    assert dialects.load(UZ).sha256 == hashlib.sha256(UZ.read_bytes()).hexdigest()


# --- The Archsim key map ----------------------------------------------------------------------


@pytest.mark.parametrize("path", [UZ, ARCHSIM], ids=["UZ", "archsim_dialect"])
def test_archsim_libraries_are_detected(path: Path) -> None:
    assert dialects.load(path).dialect == dialects.ARCHSIM_JSON


def test_archsim_keys_are_mapped_to_core_keys() -> None:
    raw = dialects.load(ARCHSIM)
    gas = objects(raw, "GasMaterials")[0]
    assert gas["Type"] == "ARGON"
    assert "GasType" not in gas
    glazing = objects(raw, "GlazingMaterials")[0]
    assert glazing["Category"] == "Uncoated"
    assert "Type" not in glazing
    assert glazing["DataSource"] == "archetypal test fixture"
    for material in objects(raw, "OpaqueMaterials"):
        assert "Comment" not in material
        assert "Comments" in material
        assert "Type" not in material
        assert "Category" in material


@pytest.mark.parametrize(("gas_type", "name"), [(0, "AIR"), (1, "ARGON"), (2, "KRYPTON"), (3, "XENON"), (4, "SF6")])
def test_gas_type_numbers(gas_type: int, name: str) -> None:
    document: Json = {"GasMaterials": [{"$id": "1", "GasType": gas_type, "Type": "Gas", "Life": 1, "Name": "G"}]}
    raw = dialects.from_document(document, "lib.json", sha256="0" * 64)
    assert objects(raw, "GasMaterials")[0]["Type"] == name


def test_archsim_keys_without_a_core_counterpart_are_lost() -> None:
    raw = dialects.load(ARCHSIM)
    keys = {pointer.rsplit("/", 1)[1] for pointer, _ in raw.lost}
    assert {"Life", "EmbodiedEnergyStdDev", "EmbodiedCarbonStdDev", "PhaseChange", "Optical"} <= keys
    assert "/GasMaterials/0/Life" in {pointer for pointer, _ in raw.lost}
    # Mapped keys are not lost.
    assert not keys & {"Comment", "GasType", "Type"}
    for collection in ("GasMaterials", "GlazingMaterials", "OpaqueMaterials"):
        for item in objects(raw, collection):
            assert not set(item) & keys


def test_reading_an_archsim_library_reports_its_lost_keys() -> None:
    result = read_umi(ARCHSIM)
    assert result.report.source.dialect == dialects.ARCHSIM_JSON
    lost = {loss.location for loss in result.report.losses if loss.kind is LossKind.LOST}
    assert "/GasMaterials/0/Life" in lost
    assert "/OpaqueMaterials/0/PhaseChange" in lost
    assert "/GlazingMaterials/0/Optical" in lost


def test_reading_a_pre_2023_library_notes_each_defaulted_field() -> None:
    result = read_umi(B2)
    assert result.report.source.dialect == dialects.CORE_JSON_PRE_2023
    defaulted = {note.location for note in result.report.notes if note.kind is NoteKind.DEFAULTED}
    assert "/DomesticHotWaterSettings/0/FuelType" in defaulted
    assert "/StructureDefinitions/0/AdvancedModel" in defaulted
    assert not any(loss.location.endswith("/FuelType") and loss.kind is LossKind.LOST for loss in result.report.losses)


# --- Refused files --------------------------------------------------------------------------------


def test_legacy_xml_is_refused_naming_the_dialect() -> None:
    with pytest.raises(UmiFormatError) as caught:
        dialects.load(EDGE / "legacy.xml")
    assert (
        "Legacy UMI XML library is not supported; open and save it in UMI to convert it to JSON" in caught.value.message
    )
    assert caught.value.subject.endswith("legacy.xml")


def test_other_xml_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "core.xml"
    path.write_text('<?xml version="1.0"?>\n<Library><OpaqueMaterials/></Library>\n', encoding="utf-8")
    with pytest.raises(UmiFormatError, match="XML"):
        dialects.load(path)


def test_a_umi_project_is_refused_naming_the_library_to_extract(tmp_path: Path) -> None:
    path = tmp_path / "project.umi"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("BostonTemplateLibrary.json", B2.read_bytes())
        archive.writestr("model.3dm", b"")
    with pytest.raises(UmiFormatError) as caught:
        dialects.load(path)
    assert "BostonTemplateLibrary.json" in caught.value.message
    assert "extract" in caught.value.message


def test_malformed_json_is_a_format_error(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text('{"OpaqueMaterials": [', encoding="utf-8")
    with pytest.raises(UmiFormatError) as caught:
        dialects.load(path)
    assert caught.value.problems
    assert caught.value.problems[0].rule == "format.json"


@pytest.mark.parametrize("text", ['{"Materials": []}', "[]", '"library"'])
def test_anything_else_is_refused_naming_the_missing_marker(tmp_path: Path, text: str) -> None:
    path = tmp_path / "other.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(UmiFormatError) as caught:
        dialects.load(path)
    assert "BuildingTemplates" in caught.value.message


def test_a_missing_file_is_a_format_error(tmp_path: Path) -> None:
    with pytest.raises(UmiFormatError, match="cannot be read"):
        dialects.load(tmp_path / "absent.json")
