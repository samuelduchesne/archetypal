"""Field-by-field comparison of UMI libraries and SBEM archetypes (spec 003 T057, US3, research R16).

`diff_umi` matches building templates by name and their components through the template, and
compares year schedules by their hourly values over the reference year. Each difference has a
location (JSON pointer in the original), a relevance, both values and a relative difference
(`None` for non-numeric values). Values closer than 1e-12 are equal; `within_tolerance` is false
only for a simulation-relevant difference above `rel_tol` (default 1e-4). `diff_archetypes`
compares SBEM archetypes over field paths.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest

from archetypal.errors import UmiFormatError
from archetypal.umi import ArchetypeDiff, Relevance, UmiDiff, diff_archetypes, diff_umi, read_umi

if TYPE_CHECKING:
    from epinterface.sbem.archetype import Archetype

UMI = Path(__file__).parents[2] / "fixtures" / "umi"
B2 = UMI / "BostonTemplateLibrary_2.json"
Json = dict[str, Any]


@pytest.fixture(scope="module")
def b2_document() -> Json:
    return json.loads(B2.read_text(encoding="utf-8"))


@pytest.fixture
def document(b2_document: Json) -> Json:
    return copy.deepcopy(b2_document)


def save(tmp_path: Path, document: Json, name: str = "result.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(document), encoding="utf-8")
    return path


def by_id(document: Json, collection: str, identifier: str) -> tuple[int, Json]:
    for index, item in enumerate(document[collection]):
        if item.get("$id") == identifier:
            return index, item
    raise KeyError(identifier)


def test_a_library_equals_itself() -> None:
    diff = diff_umi(B2, B2)
    assert isinstance(diff, UmiDiff)
    assert diff.differences == ()
    assert diff.within_tolerance
    assert diff.rel_tol == 1e-4


def test_a_numeric_difference_carries_its_location_values_and_relative_size(document: Json, tmp_path: Path) -> None:
    document["ZoneLoads"][0]["LightingPowerDensity"] = 12.6
    diff = diff_umi(B2, save(tmp_path, document))
    [difference] = diff.differences
    assert difference.location == "/ZoneLoads/0/LightingPowerDensity"
    assert difference.relevance is Relevance.SIMULATION
    assert (difference.original, difference.result) == (12.0, 12.6)
    assert difference.relative == pytest.approx(0.6 / 12.6)
    assert difference.subject == "B_Off_0"
    assert not diff.within_tolerance


def test_a_difference_below_the_tolerance_is_listed_but_within_it(document: Json, tmp_path: Path) -> None:
    document["ZoneLoads"][0]["LightingPowerDensity"] = 12.0 * (1 + 5e-5)
    diff = diff_umi(B2, save(tmp_path, document))
    assert len(diff.differences) == 1
    assert diff.within_tolerance
    assert not diff_umi(B2, save(tmp_path, document), rel_tol=1e-5).within_tolerance


def test_differences_below_1e_12_are_equal(document: Json, tmp_path: Path) -> None:
    document["ZoneLoads"][0]["LightingPowerDensity"] = 12.0 + 1e-13
    assert diff_umi(B2, save(tmp_path, document)).differences == ()


def test_a_non_numeric_simulation_difference_is_never_within_tolerance(document: Json, tmp_path: Path) -> None:
    document["ZoneLoads"][0]["IsLightingOn"] = False
    diff = diff_umi(B2, save(tmp_path, document))
    [difference] = diff.differences
    assert difference.relative is None
    assert (difference.original, difference.result) == (True, False)
    assert not diff.within_tolerance


def test_descriptive_and_life_cycle_differences_keep_the_library_within_tolerance(
    document: Json, tmp_path: Path
) -> None:
    document["ZoneLoads"][0]["Comments"] = "edited"
    document["OpaqueMaterials"][0]["EmbodiedCarbon"] = 99.0
    diff = diff_umi(B2, save(tmp_path, document))
    relevance = {d.location: d.relevance for d in diff.differences}
    assert relevance["/ZoneLoads/0/Comments"] is Relevance.DESCRIPTIVE
    assert any(r is Relevance.LIFE_CYCLE for r in relevance.values())
    assert diff.within_tolerance


def test_schedules_compare_by_hourly_values_not_by_parts(document: Json, tmp_path: Path) -> None:
    occupancy = document["ZoneLoads"][0]["OccupancySchedule"]["$ref"]
    index, year = by_id(document, "YearSchedules", occupancy)
    [part] = year["Parts"]
    # The same week in two parts: the hourly values do not change.
    year["Parts"] = [
        {**part, "ToMonth": 6, "ToDay": 30},
        {**part, "FromMonth": 7, "FromDay": 1},
    ]
    assert diff_umi(B2, save(tmp_path, document)).differences == ()


def test_a_changed_hour_is_one_schedule_difference(document: Json, tmp_path: Path) -> None:
    occupancy = document["ZoneLoads"][0]["OccupancySchedule"]["$ref"]
    index, year = by_id(document, "YearSchedules", occupancy)
    week_id = year["Parts"][0]["Schedule"]["$ref"]
    _, week = by_id(document, "WeekSchedules", week_id)
    day_id = week["Days"][0]["$ref"]
    _, day = by_id(document, "DaySchedules", day_id)
    day["Values"] = [*day["Values"][:12], day["Values"][12] + 0.5, *day["Values"][13:]]
    diff = diff_umi(B2, save(tmp_path, document))
    schedule = [d for d in diff.differences if d.location == f"/YearSchedules/{index}/Parts"]
    assert schedule
    assert schedule[0].relevance is Relevance.SIMULATION
    assert schedule[0].relative is not None
    assert schedule[0].relative > 0
    # The schedule is reached through the fields that use it, from the template down.
    assert schedule[0].via[0].startswith("/BuildingTemplates/")


def test_a_renamed_component_is_matched_through_its_template(document: Json, tmp_path: Path) -> None:
    document["ZoneLoads"][0]["Name"] = "renamed loads"
    [difference] = diff_umi(B2, save(tmp_path, document)).differences
    assert difference.location == "/ZoneLoads/0/Name"
    assert difference.relevance is Relevance.DESCRIPTIVE
    assert (difference.original, difference.result) == ("B_Off_0 loads", "renamed loads")


def test_a_template_without_a_namesake_is_matched_by_place(document: Json, tmp_path: Path) -> None:
    document["BuildingTemplates"][1]["Name"] = "B_Ret_0 #2"
    [difference] = diff_umi(B2, save(tmp_path, document)).differences
    assert difference.location == "/BuildingTemplates/1/Name"
    assert difference.subject == "B_Ret_0 #2"
    assert (difference.original, difference.result) == ("B_Ret_0", "B_Ret_0 #2")


def test_a_missing_template_is_a_difference_with_no_result(document: Json, tmp_path: Path) -> None:
    removed = document["BuildingTemplates"].pop()  # B_Res_0_WoodFrame: its window settings are a $ref
    diff = diff_umi(B2, save(tmp_path, document))
    [missing] = [d for d in diff.differences if d.result is None and d.location == "/BuildingTemplates/3"]
    assert missing.original == removed["Name"]
    assert missing.relevance is Relevance.SIMULATION


@pytest.mark.parametrize("content", [b"not json", b"<UmiLibrary/>"])
def test_an_unreadable_library_raises(tmp_path: Path, content: bytes) -> None:
    bad = tmp_path / "bad.json"
    bad.write_bytes(content)
    with pytest.raises(UmiFormatError):
        diff_umi(B2, bad)
    with pytest.raises(UmiFormatError):
        diff_umi(bad, B2)


def test_a_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(UmiFormatError):
        diff_umi(B2, tmp_path / "absent.json")


# --- diff_archetypes ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def office() -> Archetype:
    return read_umi(B2).archetypes[0]


def test_an_archetype_equals_itself(office: Archetype) -> None:
    diff = diff_archetypes(office, office)
    assert isinstance(diff, ArchetypeDiff)
    assert diff.differences == ()
    assert diff.rel_tol == 0.0
    assert diff.within_tolerance


def test_archetype_differences_are_located_by_sbem_field_path(office: Archetype) -> None:
    perimeter = next(g for g in office.Groups if g.Name == "perimeter")
    lighting = perimeter.Zone.Operations.SpaceUse.Lighting
    changed_lighting = lighting.model_copy(update={"PowerDensity": lighting.PowerDensity * 2})
    space_use = perimeter.Zone.Operations.SpaceUse.model_copy(update={"Lighting": changed_lighting})
    operations = perimeter.Zone.Operations.model_copy(update={"SpaceUse": space_use})
    zone = perimeter.Zone.model_copy(update={"Operations": operations})
    groups = [g.model_copy(update={"Zone": zone}) if g is perimeter else g for g in office.Groups]
    other = office.model_copy(update={"Groups": groups, "Comment": "edited"})
    diff = diff_archetypes(office, other)
    by_location = {d.location: d for d in diff.differences}
    power = by_location["perimeter.Operations.SpaceUse.Lighting.PowerDensity"]
    assert power.relevance is Relevance.SIMULATION
    assert power.relative == pytest.approx(0.5)
    assert by_location["archetype.Comment"].relevance is Relevance.DESCRIPTIVE
    assert not diff.within_tolerance
    assert diff_archetypes(office, other, rel_tol=0.6).within_tolerance


def test_a_missing_group_is_a_difference(office: Archetype) -> None:
    other = office.model_copy(update={"Groups": office.Groups[:1]})
    diff = diff_archetypes(office, other)
    missing = [d for d in diff.differences if d.result is None and d.original == office.Groups[1].Name]
    assert missing
