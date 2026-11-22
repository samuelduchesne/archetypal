"""Writing SBEM archetypes as one UMI template library (spec 003 T041, US1; research R12, R13).

One building template per archetype, named after it. Layouts other than core and perimeter are
merged first; shares are dropped and reported; a single group is written as both `Core` and
`Perimeter`. Components are shared by content, clashing names get ` #2`, and only components a
template reaches are written. `write_umi` writes the library and `<stem>.loss.json` only after
the whole translation succeeds.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest
from epinterface.sbem.archetype import Archetype, AtticAssumptions, ZoneGroup

from archetypal.errors import InputError, LossyTranslationError
from archetypal.reduction.report import MergedDistinction
from archetypal.umi import UmiExport, read_umi, to_umi
from archetypal.umi._refs import resolve
from archetypal.umi.report import LossKind, TranslationReport
from archetypal.umi.write import write_umi

if TYPE_CHECKING:
    from collections.abc import Callable

    from epinterface.sbem.components.zones import ZoneComponent

    from archetypal.umi._format import UmiLibrary

    from ...umi import basilisk_rules
else:
    _path = Path(__file__).parents[2] / "umi" / "basilisk_rules.py"
    _spec = importlib.util.spec_from_file_location("basilisk_rules", _path)
    basilisk_rules = importlib.util.module_from_spec(_spec)
    sys.modules["basilisk_rules"] = basilisk_rules
    _spec.loader.exec_module(basilisk_rules)

B2 = Path(__file__).parents[2] / "fixtures" / "umi" / "BostonTemplateLibrary_2.json"


@pytest.fixture(scope="module")
def b2() -> tuple[Archetype, ...]:
    return read_umi(B2).archetypes


@pytest.fixture
def office(b2: tuple[Archetype, ...]) -> Archetype:
    return b2[0]


def replace(model: Any, path: str, value: object) -> Any:
    """Return a copy of a pydantic model with the field at a dotted path replaced."""
    head, _, rest = path.partition(".")
    if not rest:
        return model.model_copy(update={head: value})
    return model.model_copy(update={head: replace(getattr(model, head), rest, value)})


def with_groups(archetype: Archetype, *groups: tuple[str, ZoneComponent, float | None, str | None]) -> Archetype:
    return Archetype.model_validate({
        "Name": archetype.Name,
        "Geometry": archetype.Geometry,
        "Groups": [
            {"Name": name, "Zone": zone, "FloorAreaShare": share, "Exposure": exposure}
            for name, zone, share, exposure in groups
        ],
    })


def library(export: UmiExport) -> UmiLibrary:
    return resolve(json.loads(export.text), "written").library


def losses(report: TranslationReport, kind: LossKind) -> list[Any]:
    return [loss for loss in report.losses if loss.kind is kind]


def assert_basilisk_accepts(text: str) -> None:
    failures = basilisk_rules.check_text(text, no_unused=True)
    assert failures == [], "\n".join(map(str, failures))


@pytest.fixture
def keep(tmp_path: Path, save_library: Callable[[Path], Path | None]) -> Callable[[UmiExport], None]:
    """Save an exported library under `--write-libraries DIR`, for tools/basilisk-check."""

    def save(export: UmiExport) -> None:
        path = tmp_path / "library.json"
        path.write_text(export.text, encoding="utf-8")
        save_library(path)

    return save


# --- Scenario 1: a core/perimeter archetype -------------------------------------------------


def test_core_perimeter_archetype_gives_one_equal_template(office: Archetype) -> None:
    zone = office.Groups[1].Zone
    archetype = with_groups(office, ("core", zone, 0.3, "core"), ("perimeter", zone, 0.7, "perimeter"))
    export = to_umi([archetype])
    (template,) = library(export).building_templates
    assert template.name == office.Name
    perimeter = template.perimeter
    assert perimeter is not None
    assert perimeter.loads is not None
    assert perimeter.conditioning is not None
    space_use = zone.Operations.SpaceUse
    assert perimeter.loads.lighting_power_density == space_use.Lighting.PowerDensity
    assert perimeter.loads.people_density == space_use.Occupancy.PeopleDensity
    assert perimeter.conditioning.min_fresh_air_per_area == zone.Operations.HVAC.Ventilation.FreshAirPerFloorArea
    assert template.default_window_to_wall_ratio == office.Geometry.WindowToWallRatio["N"]  # pyright: ignore[reportOptionalSubscript]
    dropped = losses(export.report, LossKind.SHARE_DROPPED)
    assert sorted(loss.value for loss in dropped) == [0.3, 0.7]
    assert export.report.direction == "sbem_to_umi"
    assert export.report.subjects == [office.Name]
    assert_basilisk_accepts(export.text)


def test_sbem_only_fields_are_reported(office: Archetype) -> None:
    archetype = office.model_copy(update={"Attic": AtticAssumptions(UseFraction=0.5, Conditioned=True)})
    report = to_umi([archetype]).report
    assert any(loss.location == "archetype.Attic" for loss in report.losses)


def test_unset_shares_are_not_a_loss(office: Archetype) -> None:
    assert losses(to_umi([office]).report, LossKind.SHARE_DROPPED) == []


def test_every_fixture_archetype_writes_a_library_basilisk_accepts(
    b2: tuple[Archetype, ...], keep: Callable[[UmiExport], None]
) -> None:
    export = to_umi(b2)
    keep(export)
    assert [template.name for template in library(export).building_templates] == [a.Name for a in b2]
    assert_basilisk_accepts(export.text)


# --- Scenario 2: a reduction ----------------------------------------------------------------------


def test_reduction_at_core_perimeter_lists_merged_groups(office: Archetype) -> None:
    distinctions = (
        MergedDistinction(into_key=("core",), from_keys=(("office", "core"),), lost=("space_use",)),
        MergedDistinction(
            into_key=("perimeter",),
            from_keys=(("office", "perimeter"), ("retail", "perimeter")),
            lost=("space_use",),
        ),
    )
    reduction = SimpleNamespace(archetype=office, report=SimpleNamespace(merged_distinctions=distinctions))
    report = to_umi([reduction]).report  # pyright: ignore[reportArgumentType]
    merged = losses(report, LossKind.MERGED)
    assert len(merged) == 1
    assert merged[0].value == [["office", "perimeter"], ["retail", "perimeter"]]
    assert merged[0].location == "perimeter"


def test_reduction_with_several_groups_is_merged_by_002() -> None:
    reduction_module = pytest.importorskip("archetypal.reduction")
    if not hasattr(reduction_module, "merge"):
        pytest.skip("spec 002's merge (T070) is not implemented yet")
    pytest.skip("needs a fixture reduction; covered once 002's merge exists")  # pragma: no cover


# --- Scenario 3: sharing ----------------------------------------------------------------------------


def test_two_archetypes_share_equal_components(office: Archetype) -> None:
    other = replace(office, "Name", "Other office")
    one = json.loads(to_umi([office]).text)
    two = json.loads(to_umi([office, other]).text)
    for collection in ("OpaqueConstructions", "OpaqueMaterials", "YearSchedules", "Zones", "WindowSettings"):
        assert len(two[collection]) == len(one[collection]), collection
    assert len(two["BuildingTemplates"]) == 2


def test_same_name_different_content_is_renamed(office: Archetype, keep: Callable[[UmiExport], None]) -> None:
    brighter = replace(office, "Name", "Brighter office")
    zone = replace(brighter.Groups[0].Zone, "Operations.SpaceUse.Lighting.PowerDensity", 30.0)
    brighter = with_groups(brighter, ("core", zone, None, "core"), ("perimeter", zone, None, "perimeter"))
    export = to_umi([office, brighter])
    keep(export)
    loads = {item.name: item for item in library(export).zone_loads}
    name = office.Groups[0].Zone.Operations.SpaceUse.Name
    assert loads[name].lighting_power_density == office.Groups[0].Zone.Operations.SpaceUse.Lighting.PowerDensity
    assert loads[f"{name} #2"].lighting_power_density == 30.0
    renamed = losses(export.report, LossKind.RENAMED)
    assert any(loss.value == name and loss.replacement == f"{name} #2" for loss in renamed)
    assert all(loss.rule == "names.collision" for loss in renamed)
    assert_basilisk_accepts(export.text)


def test_duplicate_archetype_names_get_a_suffix(office: Archetype) -> None:
    export = to_umi([office, office])
    names = [template.name for template in library(export).building_templates]
    assert names == [office.Name, f"{office.Name} #2"]
    assert export.report.subjects == names
    assert any(
        loss.kind is LossKind.RENAMED and loss.replacement == f"{office.Name} #2" for loss in export.report.losses
    )


def test_only_reachable_components_are_written(b2: tuple[Archetype, ...]) -> None:
    text = to_umi(b2[:1]).text
    assert basilisk_rules.check_text(text, no_unused=True) == []


# --- Single groups (FR-006b) -------------------------------------------------------------------------


@pytest.mark.parametrize("exposure", ["perimeter", "core"])
def test_single_group_is_written_once_for_both(
    office: Archetype, exposure: str, keep: Callable[[UmiExport], None]
) -> None:
    archetype = with_groups(office, (exposure, office.Groups[1].Zone, None, exposure))
    export = to_umi([archetype])
    keep(export)
    document = json.loads(export.text)
    template = document["BuildingTemplates"][0]
    assert template["Core"] == {"$ref": template["Core"]["$ref"]}
    assert template["Perimeter"] == template["Core"]
    assert len(document["Zones"]) == 1
    copied = losses(export.report, LossKind.COPIED)
    assert len(copied) == 1
    assert copied[0].rule == "layout.core_copied"
    assert_basilisk_accepts(export.text)


# --- Errors and files ------------------------------------------------------------------------------------


def test_empty_sequence_is_refused() -> None:
    with pytest.raises(InputError, match="no archetype"):
        to_umi([])


def test_more_than_two_unweighted_groups_are_refused(office: Archetype) -> None:
    zone = office.Groups[0].Zone
    groups = [
        ZoneGroup.model_validate({"Name": name, "Zone": zone, "FloorAreaShare": None, "Exposure": exposure})
        for name, exposure in (("a", "core"), ("b", "perimeter"), ("c", None))
    ]
    with pytest.raises(InputError, match="unweighted"):
        to_umi([Archetype.model_construct(Name="unweighted", Groups=groups)])


def test_write_umi_writes_the_library_and_its_loss_report(
    office: Archetype, tmp_path: Path, save_library: Callable[[Path], Path | None]
) -> None:
    path = tmp_path / "offices.json"
    report = write_umi([office], path)
    save_library(path)
    assert path.read_text(encoding="utf-8") == to_umi([office]).text
    loss_file = tmp_path / "offices.loss.json"
    assert TranslationReport.from_json(loss_file.read_text(encoding="utf-8")) == report
    assert report.source.path == "offices.json"
    assert basilisk_rules.check_file(path, no_unused=True) == []


def test_write_umi_is_exported_from_the_package() -> None:
    import archetypal  # noqa: PLC0415 - the lazy name is what is tested

    assert archetypal.write_umi is write_umi


def test_existing_files_are_refused_unless_overwrite(office: Archetype, tmp_path: Path) -> None:
    path = tmp_path / "offices.json"
    path.write_text("keep", encoding="utf-8")
    with pytest.raises(InputError, match="exists"):
        write_umi([office], path)
    assert path.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "offices.loss.json").exists()
    write_umi([office], path, overwrite=True)
    assert path.read_text(encoding="utf-8") != "keep"


def test_existing_loss_report_is_refused(office: Archetype, tmp_path: Path) -> None:
    (tmp_path / "offices.loss.json").write_text("keep", encoding="utf-8")
    with pytest.raises(InputError, match="exists"):
        write_umi([office], tmp_path / "offices.json")
    assert not (tmp_path / "offices.json").exists()


def test_strict_mode_raises_and_writes_nothing(office: Archetype, tmp_path: Path) -> None:
    path = tmp_path / "offices.json"
    with pytest.raises(LossyTranslationError) as error:
        write_umi([office], path, strict=True)
    assert error.value.report.losses
    assert list(tmp_path.iterdir()) == []


def test_export_write(office: Archetype, tmp_path: Path) -> None:
    export = to_umi([office])
    written = export.write(tmp_path / "lib.json")
    assert written == (tmp_path / "lib.json", tmp_path / "lib.loss.json")
    assert written[0].read_bytes() == export.text.encode("utf-8")
