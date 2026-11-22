"""The form of the UMI files archetypal writes (spec 003 T042; contracts/umi-file.md, research R13).

Each of the contract's seven rules is one test, on the templates of the Boston library without
duplicate names (ND), serialised again from the format model.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from archetypal.umi import _format
from archetypal.umi._refs import resolve
from archetypal.umi.serialise import COLLECTIONS, library_of, serialise

if TYPE_CHECKING:
    from ...umi import basilisk_rules
else:
    _path = Path(__file__).parents[2] / "umi" / "basilisk_rules.py"
    _spec = importlib.util.spec_from_file_location("basilisk_rules", _path)
    basilisk_rules = importlib.util.module_from_spec(_spec)
    sys.modules["basilisk_rules"] = basilisk_rules
    _spec.loader.exec_module(basilisk_rules)

ND = Path(__file__).parents[2] / "fixtures" / "umi" / "BostonTemplateLibrary_nodup.json"
Json = dict[str, object]


@pytest.fixture(scope="module")
def templates() -> tuple[_format.BuildingTemplate, ...]:
    return resolve(json.loads(ND.read_text(encoding="utf-8")), ND).library.building_templates


@pytest.fixture(scope="module")
def text(templates: tuple[_format.BuildingTemplate, ...]) -> str:
    return serialise(templates)


@pytest.fixture(scope="module")
def document(text: str) -> Json:
    return cast("Json", json.loads(text))


def items(document: Json, collection: str) -> list[Json]:
    return cast("list[Json]", document[collection])


def walk(value: object) -> list[Json]:
    """Every object of a JSON value, in document order."""
    found: list[Json] = []
    if isinstance(value, dict):
        obj = cast("Json", value)
        found.append(obj)
        for item in obj.values():
            found.extend(walk(item))
    elif isinstance(value, list):
        for item in cast("list[object]", value):
            found.extend(walk(item))
    return found


# --- Rule 1: collections ------------------------------------------------------------------


def test_rule_1_all_collections_in_basilisk_order(document: Json) -> None:
    assert tuple(document) == COLLECTIONS
    assert len(COLLECTIONS) == 17


def test_components_are_sorted_by_name_templates_kept_in_order(
    document: Json, templates: tuple[_format.BuildingTemplate, ...]
) -> None:
    for collection in COLLECTIONS:
        if collection in {"BuildingTemplates", "WindowSettings"}:
            continue
        names = [cast("str", item["Name"]) for item in items(document, collection) if "$ref" not in item]
        assert names == sorted(names), collection
    assert [item["Name"] for item in items(document, "BuildingTemplates")] == [t.name for t in templates]


# --- Rule 2: references -------------------------------------------------------------------


def test_rule_2_ids_first_numbered_in_order_refs_backwards(document: Json) -> None:
    seen: list[str] = []
    for obj in walk(document):
        if "$id" in obj:
            assert next(iter(obj)) == "$id"
            seen.append(cast("str", obj["$id"]))
        elif "$ref" in obj:
            assert list(obj) == ["$ref"]
            assert obj["$ref"] in seen
    assert seen == [str(number) for number in range(1, len(seen) + 1)]


def test_rule_2_window_settings_inline_templates_without_id(document: Json) -> None:
    templates = items(document, "BuildingTemplates")
    assert all("$id" not in template for template in templates)
    assert "$id" in cast("Json", templates[0]["Windows"])
    assert all(list(item) == ["$ref"] for item in items(document, "WindowSettings"))


# --- Rule 3: nothing unused, nothing missing ---------------------------------------------------


def test_rule_3_every_component_reachable_and_listed(text: str) -> None:
    lib = basilisk_rules.Loaded(basilisk_rules.parse(text))
    assert basilisk_rules.orphan_check(lib, no_unused=True) == []


def test_unused_components_of_the_source_are_not_written(document: Json) -> None:
    source = cast("Json", json.loads(ND.read_text(encoding="utf-8")))
    assert len(items(document, "OpaqueMaterials")) <= len(items(source, "OpaqueMaterials"))


# --- Rule 4: names -------------------------------------------------------------------------------


def test_rule_4_names_unique_per_collection(document: Json) -> None:
    groups = {"GasMaterials": "window", "GlazingMaterials": "window"}
    names: dict[str, list[str]] = {}
    for collection in COLLECTIONS:
        defined = [item for item in items(document, collection) if "$ref" not in item]
        names.setdefault(groups.get(collection, collection), []).extend(cast("str", item["Name"]) for item in defined)
    for group, listed in names.items():
        assert all(listed), group
        assert len(listed) == len(set(listed)), group


def test_clashing_names_are_refused() -> None:
    a = _format.OpaqueMaterial(Name="Brick", Conductivity=1.0)
    b = _format.OpaqueMaterial(Name="Brick", Conductivity=2.0)
    layers = tuple(_format.MaterialLayer[_format.OpaqueMaterial](Material=m, Thickness=0.1) for m in (a, b))
    construction = _format.OpaqueConstruction(Name="Wall", Layers=layers)
    zone = _format.ZoneDefinition(Name="Zone", InternalMassConstruction=construction)
    template = _format.BuildingTemplate(Name="T", Core=zone, Perimeter=zone)
    with pytest.raises(ValueError, match="Brick"):
        library_of([template])


# --- Rule 5: completeness -------------------------------------------------------------------------


def test_rule_5_complete(text: str) -> None:
    lib = basilisk_rules.Loaded(basilisk_rules.parse(text))
    assert basilisk_rules.completeness_check(lib) == []


# --- Rule 6: values --------------------------------------------------------------------------------


def test_rule_6_enums_and_integer_fields_are_integers(document: Json) -> None:
    conditioning = next(item for item in items(document, "ZoneConditionings") if "$ref" not in item)
    for key in ("HeatingFuelType", "CoolingFuelType", "EconomizerType", "HeatRecoveryType", "HeatingLimitType"):
        assert type(conditioning[key]) is int, key
    year = next(item for item in items(document, "YearSchedules") if "$ref" not in item)
    part = cast("list[Json]", year["Parts"])[0]
    assert all(type(part[key]) is int for key in ("FromDay", "FromMonth", "ToDay", "ToMonth"))
    template = items(document, "BuildingTemplates")[0]
    assert type(template["Lifespan"]) is int


def test_rule_6_floats_are_never_rounded(text: str) -> None:
    assert '"MinFreshAirPerArea": 0.0003' in text
    assert '"MinFreshAirPerArea": 0.0' in text


def test_rule_6_every_basilisk_field_is_written(document: Json) -> None:
    template = items(document, "BuildingTemplates")[0]
    expected = [alias for _, alias in _format.BuildingTemplate.basilisk_keys()]
    assert list(template) == expected


def test_non_finite_floats_are_refused(templates: tuple[_format.BuildingTemplate, ...]) -> None:
    template = templates[0].model_copy(update={"default_window_to_wall_ratio": float("nan")})
    with pytest.raises(ValueError, match="finite"):
        serialise([template])


# --- Rule 7: bytes ----------------------------------------------------------------------------------


def test_rule_7_bytes(text: str) -> None:
    data = text.encode("utf-8")
    assert not data.startswith(b"\xef\xbb\xbf")
    assert "\r" not in text
    assert text.endswith("}\n")
    assert text.splitlines()[1].startswith('  "GasMaterials"')


def test_writing_twice_gives_identical_bytes(templates: tuple[_format.BuildingTemplate, ...], text: str) -> None:
    again = resolve(json.loads(ND.read_text(encoding="utf-8")), ND).library.building_templates
    assert serialise(again) == text
    assert serialise(templates) == text


def test_basilisk_rules_accept_the_library(text: str) -> None:
    failures = basilisk_rules.check_text(text, no_unused=True)
    assert failures == [], "\n".join(map(str, failures))
