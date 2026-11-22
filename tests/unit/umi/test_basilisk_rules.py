"""The Python port of tools/basilisk-check's checks 1, 3 and 4 (spec 003, T023, research R15)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from ...umi import basilisk_rules
else:
    # tests/umi is not a package (tests/unit/umi already owns the name `umi`, and site-packages
    # may hold a `tests` package), so the module is loaded from its file.
    _path = Path(__file__).parents[2] / "umi" / "basilisk_rules.py"
    _spec = importlib.util.spec_from_file_location("basilisk_rules", _path)
    basilisk_rules = importlib.util.module_from_spec(_spec)
    sys.modules["basilisk_rules"] = basilisk_rules
    _spec.loader.exec_module(basilisk_rules)

UMI = Path(__file__).parents[2] / "fixtures" / "umi"
SAMPLES = ["BostonTemplateLibrary_2.json", "BostonTemplateLibrary_nodup.json", "umi_samples_BostonTemplateLibrary.json"]


def checks(path: Path, *, no_unused: bool = False) -> set[int]:
    return {failure.check for failure in basilisk_rules.check_file(path, no_unused=no_unused)}


@pytest.mark.parametrize("name", SAMPLES)
def test_samples_pass(name: str) -> None:
    assert basilisk_rules.check_file(UMI / name) == []


@pytest.mark.parametrize(
    "name",
    ["archsim_dialect", "misaligned_parts", "no_templates", "out_of_range", "shared_zone", "unused_components"],
)
def test_edge_cases_basilisk_accepts_pass(name: str) -> None:
    assert basilisk_rules.check_file(UMI / "edge" / f"{name}.json") == []


def test_dangling_ref_fails_check_1() -> None:
    failures = basilisk_rules.check_file(UMI / "edge" / "dangling_ref.json")
    assert {f.check for f in failures} == {1, 4}
    (first,) = (f for f in failures if f.check == 1)
    assert first.message.startswith("/ZoneLoads/0/OccupancySchedule/$ref:")
    assert any("OccupancySchedule is null" in f.message for f in failures if f.check == 4)


def test_forward_ref_fails_check_1() -> None:
    failures = basilisk_rules.check_file(UMI / "edge" / "forward_ref.json")
    assert {f.check for f in failures} == {1, 4}
    assert [f.message.split(":")[0] for f in failures if f.check == 1] == [
        "/BuildingTemplates/0/Core/$ref",
        "/BuildingTemplates/0/Perimeter/$ref",
    ]


def test_duplicate_names_fail_check_4() -> None:
    failures = basilisk_rules.check_file(UMI / "edge" / "duplicate_names.json")
    assert {f.check for f in failures} == {4}
    messages = " ".join(f.message for f in failures)
    assert 'name "Concrete"' in messages
    assert 'name "Clear 6mm"' in messages
    assert "GlazingMaterials and GasMaterials together" in messages
    assert 'name "Office"' in messages


def test_missing_reference_fails_check_4() -> None:
    failures = basilisk_rules.check_file(UMI / "edge" / "missing_reference.json")
    assert [(f.check, f.message) for f in failures] == [
        (4, 'ZoneLoads[0] "Office loads": LightsAvailabilitySchedule is null')
    ]


def test_unused_components_fail_check_3_only_when_asked() -> None:
    assert checks(UMI / "edge" / "no_templates.json") == set()
    failures = basilisk_rules.check_file(UMI / "edge" / "no_templates.json", no_unused=True)
    assert {f.check for f in failures} == {3}
    assert len(failures) == 22
    assert checks(UMI / "BostonTemplateLibrary_nodup.json", no_unused=True) == set()


def test_not_json_fails_check_1() -> None:
    assert checks(UMI / "edge" / "legacy.xml") == {1}


def test_component_reachable_but_not_in_its_collection_fails_check_3() -> None:
    # Basilisk's OrphanedComponents() misses a zone missing from `Zones` (research R15 (b)).
    text = (UMI / "edge" / "shared_zone.json").read_text(encoding="utf-8")
    library = basilisk_rules.parse(text)
    zones = library["Zones"]
    assert isinstance(zones, list)
    templates = library["BuildingTemplates"]
    assert isinstance(templates, list)
    template = templates[0]
    assert isinstance(template, dict)
    template["Core"] = zones.pop()
    template["Perimeter"] = {"$ref": template["Core"]["$id"]}  # pyright: ignore[reportIndexIssue, reportArgumentType, reportUnknownArgumentType]
    failures = basilisk_rules.check_library(library)
    assert {f.check for f in failures} == {3}
    assert "is not in Zones" in failures[0].message


def test_orphaned_component_fails_check_3() -> None:
    # A year schedule defined inline in a zone's loads and in no collection.
    text = (UMI / "edge" / "shared_zone.json").read_text(encoding="utf-8")
    library = basilisk_rules.parse(text)
    years = library["YearSchedules"]
    assert isinstance(years, list)
    year = years[0]
    assert isinstance(year, dict)
    loads = library["ZoneLoads"]
    assert isinstance(loads, list)
    first = loads[0]
    assert isinstance(first, dict)
    library["YearSchedules"] = years[1:]
    rest = [v for k, v in first.items() if k != "OccupancySchedule"]
    assert rest
    failures = basilisk_rules.check_library(library)
    assert 3 in {f.check for f in failures}
    assert any("OrphanedComponents() lists YearSchedule" in f.message for f in failures)


def test_format_matches_the_harness() -> None:
    failure = basilisk_rules.Failure(1, "/X: problem")
    assert str(failure) == "check 1 refs: /X: problem"
