"""References in UMI libraries: pre-scan, resolution and id assignment (spec 003, T012, R1, R13)."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast, get_args

import pytest
from pydantic import BaseModel

from archetypal.errors import UmiFormatError
from archetypal.umi import _format, _refs

if TYPE_CHECKING:
    from collections.abc import Sequence

    from archetypal.errors import Problem

UMI = Path(__file__).parents[2] / "fixtures" / "umi"
SAMPLES = {
    "B2": UMI / "BostonTemplateLibrary_2.json",
    "ND": UMI / "BostonTemplateLibrary_nodup.json",
    "UZ": UMI / "umi_samples_BostonTemplateLibrary.json",
}
# Keys of Basilisk at `5cce24e8` that B2 and ND, written by an older Basilisk, do not have:
# research R2's three, plus hot water's `CoefficientOfPerformance` and the opaque materials'
# `DesignStrength` and `ModulusOfElasticity`.
NEW_KEYS = {
    "AdvancedModel",
    "UseAdvancedModel",
    "FuelType",
    "CoefficientOfPerformance",
    "DesignStrength",
    "ModulusOfElasticity",
}

Json = dict[str, object]


def load(path: Path) -> Json:
    return cast("Json", json.loads(path.read_text(encoding="utf-8-sig")))


def rules(problems: list[Problem]) -> list[tuple[str, str]]:
    return [(p.rule, p.pointer) for p in problems]


def week_library(days: Sequence[object], *, day_id: str = "1") -> Json:
    """A library with one day schedule and one week schedule whose days are `days`."""
    return {
        "DaySchedules": [{"$id": day_id, "Values": [1.0] * 24, "Name": "On"}],
        "WeekSchedules": [{"$id": "2", "Days": list(days), "Name": "Week"}],
    }


# --- Pre-scan ----------------------------------------------------------------------------


def test_duplicate_id() -> None:
    doc = week_library([{"$ref": "2"}] * 7, day_id="2")
    assert rules(_refs.scan_references(doc)) == [("refs.duplicate-id", "/WeekSchedules/0")]


def test_id_not_first() -> None:
    doc: Json = {"DaySchedules": [{"Name": "On", "$id": "1"}]}
    assert rules(_refs.scan_references(doc)) == [("refs.id-not-first", "/DaySchedules/0")]


def test_id_not_a_string() -> None:
    doc: Json = {"DaySchedules": [{"$id": 1, "Name": "On"}]}
    assert rules(_refs.scan_references(doc)) == [("refs.id-not-string", "/DaySchedules/0")]


def test_ref_not_a_string() -> None:
    doc = week_library([{"$ref": 1}] + [{"$ref": "1"}] * 6)
    assert rules(_refs.scan_references(doc)) == [("refs.ref-not-string", "/WeekSchedules/0/Days/0")]


def test_extra_keys_beside_ref() -> None:
    doc = week_library([{"$ref": "1", "Name": "On"}] + [{"$ref": "1"}] * 6)
    assert rules(_refs.scan_references(doc)) == [("refs.ref-extra-keys", "/WeekSchedules/0/Days/0")]


def test_dangling_ref() -> None:
    doc = week_library([{"$ref": "1"}] * 6 + [{"$ref": "99"}])
    assert rules(_refs.scan_references(doc)) == [("refs.dangling", "/WeekSchedules/0/Days/6")]


def test_forward_ref() -> None:
    doc: Json = {
        "WeekSchedules": [{"$id": "2", "Days": [{"$ref": "1"}] * 7, "Name": "Week"}],
        "DaySchedules": [{"$id": "1", "Values": [1.0] * 24, "Name": "On"}],
    }
    problems = _refs.scan_references(doc)
    assert {p.rule for p in problems} == {"refs.forward"}
    assert [p.pointer for p in problems] == [f"/WeekSchedules/0/Days/{i}" for i in range(7)]


def test_problems_are_format_problems_with_messages() -> None:
    doc = week_library([{"$ref": "1"}] * 6 + [{"$ref": "99"}])
    (problem,) = _refs.scan_references(doc)
    assert problem.template is None
    assert '"99"' in problem.message


def test_json_pointer_escapes_keys() -> None:
    doc: Json = {"Odd/Key~": [{"$ref": "1"}]}
    assert rules(_refs.scan_references(doc)) == [("refs.dangling", "/Odd~1Key~0/0")]


def test_document_must_be_an_object() -> None:
    assert rules(_refs.scan_references([])) == [("format.not-object", "")]


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_samples_pass_the_pre_scan(name: str) -> None:
    assert _refs.scan_references(load(SAMPLES[name])) == []


def test_edge_dangling_ref() -> None:
    problems = _refs.scan_references(load(UMI / "edge" / "dangling_ref.json"))
    assert rules(problems) == [("refs.dangling", "/ZoneLoads/0/OccupancySchedule")]


def test_edge_forward_ref() -> None:
    problems = _refs.scan_references(load(UMI / "edge" / "forward_ref.json"))
    assert rules(problems) == [
        ("refs.forward", "/BuildingTemplates/0/Core"),
        ("refs.forward", "/BuildingTemplates/0/Perimeter"),
    ]


# --- Resolution --------------------------------------------------------------------------


def is_reference(annotation: object) -> bool:
    """Whether a field annotation admits a library component (a reference in the file)."""
    if isinstance(annotation, type):
        return issubclass(annotation, _format.LibraryComponent)
    return any(is_reference(arg) for arg in cast("tuple[object, ...]", get_args(annotation)))


def references(model: BaseModel) -> list[tuple[str, object]]:
    """Every reference field of a model and the models nested in it, with its value."""
    found: list[tuple[str, object]] = []
    for name, value in model:
        if name == "advanced_model":  # Basilisk's optional structural model
            continue
        items = cast("tuple[object, ...]", value) if isinstance(value, tuple) else (value,)
        reference = is_reference(type(model).model_fields[name].annotation)
        for item in items:
            if reference:
                found.append((f"{type(model).__name__}.{name}", item))
            if isinstance(item, BaseModel):
                found.extend(references(item))
    return found


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_samples_resolve(name: str) -> None:
    result = _refs.resolve(load(SAMPLES[name]), SAMPLES[name])
    library = result.library
    assert isinstance(library, _format.UmiLibrary)
    assert len(library.building_templates) == 4
    for template in library.building_templates:
        for key, value in references(template):
            # Structure is optional (research R3); every other reference is an object.
            assert value is not None or key == "BuildingTemplate.structure", key


def test_references_are_the_collection_objects() -> None:
    library = _refs.resolve(load(SAMPLES["B2"]), "B2").library
    template = library.building_templates[0]
    assert template.core is not None
    assert any(template.core is zone for zone in library.zones)
    assert template.windows is not None
    assert any(template.windows is window for window in library.window_settings)
    schedule = library.year_schedules[0].parts[0].schedule
    assert any(schedule is week for week in library.week_schedules)


def test_window_materials_resolve_to_glazing_or_gas() -> None:
    library = _refs.resolve(load(SAMPLES["B2"]), "B2").library
    materials = [layer.material for c in library.window_constructions for layer in c.layers]
    assert {type(m) for m in materials} <= {_format.GlazingMaterial, _format.GasMaterial}
    assert any(isinstance(m, _format.GasMaterial) for m in materials)


def windows_in_collection(doc: Json) -> Json:
    """v2's order: window settings defined in `WindowSettings`, written before the templates."""
    templates = cast("list[Json]", doc["BuildingTemplates"])
    defined: list[Json] = []
    for template in templates:
        windows = cast("Json", template["Windows"])
        if "$id" in windows:
            defined.append(windows)
            template["Windows"] = {"$ref": windows["$id"]}
    reordered = {key: value for key, value in doc.items() if key not in {"BuildingTemplates", "WindowSettings"}}
    reordered["WindowSettings"] = defined
    reordered["BuildingTemplates"] = templates
    return reordered


def test_window_settings_inline_and_in_collection_both_resolve() -> None:
    inline = load(SAMPLES["B2"])
    collection = windows_in_collection(copy.deepcopy(inline))
    assert _refs.scan_references(collection) == []
    first = _refs.resolve(inline, "inline").library
    second = _refs.resolve(collection, "collection").library
    assert [t.windows for t in first.building_templates] == [t.windows for t in second.building_templates]
    assert all(t.windows is not None for t in second.building_templates)
    assert {w.name for w in second.window_settings} == {w.name for w in first.window_settings}


def test_resolve_refuses_reference_problems() -> None:
    with pytest.raises(UmiFormatError) as caught:
        _refs.resolve(load(UMI / "edge" / "dangling_ref.json"), "dangling_ref.json")
    assert rules(caught.value.problems) == [("refs.dangling", "/ZoneLoads/0/OccupancySchedule")]
    assert caught.value.subject == "dangling_ref.json"


def test_resolve_refuses_a_reference_of_the_wrong_class() -> None:
    doc = week_library([{"$ref": "1"}] * 7)
    doc["YearSchedules"] = [{"$id": "3", "Parts": [{"FromDay": 1, "FromMonth": 1, "Schedule": {"$ref": "1"}}]}]
    with pytest.raises(UmiFormatError) as caught:
        _refs.resolve(doc, "lib")
    assert rules(caught.value.problems) == [("refs.wrong-class", "/YearSchedules/0/Parts/0/Schedule")]


def test_resolve_refuses_values_that_do_not_convert() -> None:
    doc: Json = {"DaySchedules": [{"$id": "1", "Values": "high", "Name": "On"}]}
    with pytest.raises(UmiFormatError) as caught:
        _refs.resolve(doc, "lib")
    assert rules(caught.value.problems) == [("format.value", "/DaySchedules/0/Values")]


def test_explicit_null_reference_is_kept_for_validation() -> None:
    # A null reference is a completeness problem (research R3), not a format problem.
    library = _refs.resolve(load(UMI / "edge" / "missing_reference.json"), "lib").library
    assert library.zone_loads[0].lights_availability_schedule is None


def test_defaulted_and_unknown_keys_are_recorded() -> None:
    result = _refs.resolve(load(SAMPLES["B2"]), "B2")
    assert "/DomesticHotWaterSettings/0/FuelType" in result.defaulted
    assert "/StructureDefinitions/0/AdvancedModel" in result.defaulted
    assert result.unknown_keys == ()
    uz = _refs.resolve(load(SAMPLES["UZ"]), "UZ")
    unknown = dict(uz.unknown_keys)
    assert unknown["/GasMaterials/0/GasType"] == 0
    assert "/OpaqueMaterials/0/Life" in unknown


def test_missing_collection_is_empty_and_defaulted() -> None:
    result = _refs.resolve({"DaySchedules": []}, "lib")
    assert result.library.zones == ()
    assert "/Zones" in result.defaulted
    assert "/DaySchedules" not in result.defaulted


# --- Writing: id assignment --------------------------------------------------------------


def ids_and_refs(value: object, out: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Every `$id` and `$ref` of a JSON value, in document order."""
    if isinstance(value, dict):
        obj = cast("Json", value)
        for key, item in obj.items():
            if key in {"$id", "$ref"}:
                out.append((key, cast("str", item)))
            else:
                ids_and_refs(item, out)
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            ids_and_refs(item, out)
    return out


def test_ids_are_numbered_in_document_order_and_refs_point_back() -> None:
    dumped = _refs.dump_library(_refs.resolve(load(SAMPLES["B2"]), "B2").library)
    seen: list[str] = []
    for kind, value in ids_and_refs(dumped, []):
        if kind == "$id":
            assert value == str(len(seen) + 1)
            seen.append(value)
        else:
            assert value in seen


def test_component_is_defined_once_then_referred_to() -> None:
    day = _format.DaySchedule(values=(1.0,) * 24, name="On")  # pyright: ignore[reportCallIssue]
    week = _format.WeekSchedule(days=(day,) * 7, name="Week")  # pyright: ignore[reportCallIssue]
    dumped = _refs.dump_library(_format.UmiLibrary(day_schedules=(day,), week_schedules=(week,)))  # pyright: ignore[reportCallIssue]
    days = cast("list[Json]", dumped["DaySchedules"])
    weeks = cast("list[Json]", dumped["WeekSchedules"])
    assert days[0]["$id"] == "1"
    assert next(iter(days[0])) == "$id"
    assert weeks[0]["$id"] == "2"
    assert weeks[0]["Days"] == [{"$ref": "1"}] * 7


def test_component_outside_its_collection_is_defined_at_first_use() -> None:
    day = _format.DaySchedule(values=(0.0,) * 24, name="Off")  # pyright: ignore[reportCallIssue]
    week = _format.WeekSchedule(days=(day,) * 7, name="Week")  # pyright: ignore[reportCallIssue]
    dumped = _refs.dump_library(_format.UmiLibrary(week_schedules=(week,)))  # pyright: ignore[reportCallIssue]
    days = cast("list[Json]", cast("list[Json]", dumped["WeekSchedules"])[0]["Days"])
    assert days[0]["$id"] == "2"
    assert days[1:] == [{"$ref": "2"}] * 6


def test_templates_have_no_id_and_windows_are_defined_inline() -> None:
    dumped = _refs.dump_library(_refs.resolve(load(SAMPLES["ND"]), "ND").library)
    templates = cast("list[Json]", dumped["BuildingTemplates"])
    assert all("$id" not in t for t in templates)
    assert "$id" in cast("Json", templates[0]["Windows"])
    assert all(set(cast("Json", w)) == {"$ref"} for w in cast("list[object]", dumped["WindowSettings"]))


def drop_new_keys(value: object) -> object:
    if isinstance(value, dict):
        return {k: drop_new_keys(v) for k, v in cast("Json", value).items() if k not in NEW_KEYS}
    if isinstance(value, list):
        return [drop_new_keys(v) for v in cast("list[object]", value)]
    return value


def renumber(value: object, ids: dict[str, str]) -> object:
    """Number the `$id`s `"1"`, `"2"`, … in document order and follow them in `$ref`s."""
    if isinstance(value, dict):
        out: Json = {}
        for key, item in cast("Json", value).items():
            if key == "$id":
                out[key] = ids.setdefault(cast("str", item), str(len(ids) + 1))
            elif key == "$ref":
                out[key] = ids[cast("str", item)]
            else:
                out[key] = renumber(item, ids)
        return out
    if isinstance(value, list):
        return [renumber(item, ids) for item in cast("list[object]", value)]
    return value


def test_written_like_basilisk() -> None:
    # B2 was written by Basilisk: reading and writing it gives the same JSON, keys in
    # the same order, apart from the fields Basilisk added since (written with their defaults,
    # the structural model's construction systems with ids of their own). B2's own ids are not
    # in document order, so both sides are renumbered before comparing.
    original = load(SAMPLES["B2"])
    dumped = _refs.dump_library(_refs.resolve(original, "B2").library)
    assert json.dumps(renumber(drop_new_keys(dumped), {})) == json.dumps(renumber(original, {}))


def test_new_fields_are_written_with_basilisk_defaults() -> None:
    dumped = _refs.dump_library(_refs.resolve(load(SAMPLES["ND"]), "ND").library)
    hot_water = cast("list[Json]", dumped["DomesticHotWaterSettings"])[0]
    assert hot_water["FuelType"] == 2
    structure = cast("list[Json]", dumped["StructureDefinitions"])[0]
    assert structure["UseAdvancedModel"] is False
    beams = cast("Json", cast("Json", cast("Json", structure["AdvancedModel"])["ConstructionSystems"])["Beams"])
    assert next(iter(beams)) == "$id"
    assert beams["ConstructionSystemType"] == "RectangularSolid"


@pytest.mark.parametrize("name", sorted(SAMPLES))
def test_written_library_resolves_to_an_equal_library(name: str) -> None:
    # ND defines its window settings in the collection, before the templates (v2's order);
    # written again, they are inline in the templates (Basilisk's order).
    library = _refs.resolve(load(SAMPLES[name]), name).library
    dumped = _refs.dump_library(library)
    assert _refs.scan_references(dumped) == []
    assert _refs.resolve(dumped, "again").library == library
