"""Validation of UMI libraries before translation (spec 003, T050, R3, FR-004)."""

from __future__ import annotations

import copy
import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

from archetypal.errors import Problem, UmiFormatError, UmiValidationError
from archetypal.umi import dialects, read_umi
from archetypal.umi._refs import resolve
from archetypal.umi.report import LossKind
from archetypal.umi.validate import LibraryIndex, validate

if TYPE_CHECKING:
    from collections.abc import Callable

UMI = Path(__file__).parents[2] / "fixtures" / "umi"
EDGE = UMI / "edge"
BASE = EDGE / "unused_components.json"  # valid, one template "Office"

Json = dict[str, object]


def base() -> Json:
    return cast("Json", json.loads(BASE.read_text(encoding="utf-8")))


def items(document: Json, collection: str) -> list[Json]:
    return cast("list[Json]", document[collection])


def problems_of(document: Json) -> list[Problem]:
    raw = dialects.from_document(document, "lib.json", sha256="0" * 64)
    library = resolve(raw.document, "lib.json").library
    return validate(LibraryIndex(library, raw.document))


def where(problems: list[Problem]) -> set[tuple[str, str | None]]:
    return {(problem.pointer, problem.template) for problem in problems}


def by_name(document: Json, collection: str, name: str) -> tuple[int, Json]:
    for index, item in enumerate(items(document, collection)):
        if item.get("Name") == name:
            return index, item
    raise KeyError(name)


# --- The fixtures -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [
        UMI / "BostonTemplateLibrary_2.json",
        UMI / "BostonTemplateLibrary_nodup.json",
        UMI / "umi_samples_BostonTemplateLibrary.json",
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
    ],
    ids=lambda path: path.stem,
)
def test_valid_libraries_have_no_problem(path: Path) -> None:
    raw = dialects.load(path)
    library = resolve(raw.document, path).library
    assert validate(LibraryIndex(library, raw.document)) == []


@pytest.mark.parametrize(
    ("name", "pointers"),
    [
        ("dangling_ref", {"/ZoneLoads/0/OccupancySchedule"}),
        ("forward_ref", {"/BuildingTemplates/0/Core", "/BuildingTemplates/0/Perimeter"}),
    ],
)
def test_broken_references_are_format_errors(name: str, pointers: set[str]) -> None:
    with pytest.raises(UmiFormatError) as caught:
        read_umi(EDGE / f"{name}.json")
    assert not isinstance(caught.value, UmiValidationError)
    assert {problem.pointer for problem in caught.value.problems} == pointers


def test_missing_reference_names_pointer_and_template() -> None:
    with pytest.raises(UmiValidationError) as caught:
        read_umi(EDGE / "missing_reference.json")
    problems = caught.value.problems
    assert where(problems) == {("/ZoneLoads/0/LightsAvailabilitySchedule", "Office")}
    assert problems[0].rule == "required-reference"
    assert "/ZoneLoads/0/LightsAvailabilitySchedule" in str(caught.value)


def test_out_of_range_names_pointer_and_template() -> None:
    with pytest.raises(UmiValidationError) as caught:
        read_umi(EDGE / "out_of_range.json")
    assert where(caught.value.problems) == {("/OpaqueMaterials/2/Conductivity", "Bad office")}


def test_skip_invalid_templates_reads_the_others() -> None:
    result = read_umi(EDGE / "out_of_range.json", skip_invalid_templates=True)
    assert [archetype.Name for archetype in result.archetypes] == ["Office"]
    skipped = [loss for loss in result.report.losses if loss.kind is LossKind.SKIPPED_TEMPLATE]
    assert [(loss.subject, loss.location, loss.rule) for loss in skipped] == [
        ("Bad office", "/BuildingTemplates/0", "validation.skipped")
    ]
    assert "/OpaqueMaterials/2/Conductivity" in json.dumps(skipped[0].value)
    assert result.report.subjects == ["Office"]


def test_format_problems_are_never_skipped() -> None:
    with pytest.raises(UmiFormatError):
        read_umi(EDGE / "dangling_ref.json", skip_invalid_templates=True)


def test_duplicate_names_are_not_problems() -> None:
    raw = dialects.load(EDGE / "duplicate_names.json")
    library = resolve(raw.document, "duplicate_names.json").library
    assert validate(LibraryIndex(library, raw.document)) == []


# --- Every problem is collected ----------------------------------------------------------------


def test_every_problem_is_collected_before_raising(tmp_path: Path) -> None:
    document = base()
    items(document, "ZoneLoads")[0]["OccupancySchedule"] = None
    items(document, "ZoneConditionings")[0]["MinFreshAirPerArea"] = 0.5
    index, _ = by_name(document, "OpaqueMaterials", "Concrete")
    items(document, "OpaqueMaterials")[index]["SpecificHeat"] = 10.0
    path = tmp_path / "many.json"
    path.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(UmiValidationError) as caught:
        read_umi(path)
    assert {problem.pointer for problem in caught.value.problems} == {
        "/ZoneLoads/0/OccupancySchedule",
        "/ZoneConditionings/0/MinFreshAirPerArea",
        f"/OpaqueMaterials/{index}/SpecificHeat",
    }


# --- Completeness -----------------------------------------------------------------------------

Mutation = tuple[str, int, str]  # collection, index, key set to null

REQUIRED: list[Mutation] = [
    *(("BuildingTemplates", 0, key) for key in ("Core", "Perimeter", "Windows")),
    *(
        ("Zones", 1, key)
        for key in (
            "Conditioning",
            "Constructions",
            "DomesticHotWater",
            "InternalMassConstruction",
            "Loads",
            "Ventilation",
        )
    ),
    *(("ZoneConstructionSets", 0, key) for key in ("Facade", "Ground", "Partition", "Roof", "Slab")),
    *(
        ("ZoneLoads", 0, key)
        for key in ("OccupancySchedule", "LightsAvailabilitySchedule", "EquipmentAvailabilitySchedule")
    ),
    *(("ZoneConditionings", 0, key) for key in ("HeatingSchedule", "CoolingSchedule", "MechVentSchedule")),
    *(("VentilationSettings", 0, key) for key in ("NatVentSchedule", "ScheduledVentilationSchedule")),
    ("DomesticHotWaterSettings", 0, "WaterSchedule"),
]


@pytest.mark.parametrize(("collection", "index", "key"), REQUIRED, ids=str)
def test_required_references(collection: str, index: int, key: str) -> None:
    document = base()
    items(document, collection)[index][key] = None
    if key == "Windows":  # the template defines its window settings inline; the collection refers to them
        document["WindowSettings"] = []
    problems = problems_of(document)
    pointer = f"/{collection}/{index}/{key}"
    assert (pointer, "Office") in where(problems)
    assert all(problem.rule == "required-reference" for problem in problems if problem.pointer == pointer)


@pytest.mark.parametrize(
    "key",
    ["AfnWindowAvailability", "ShadingSystemAvailabilitySchedule", "ZoneMixingAvailabilitySchedule", "Construction"],
)
def test_window_settings_references(key: str) -> None:
    document = base()
    windows = cast("Json", items(document, "BuildingTemplates")[0]["Windows"])
    windows[key] = None
    assert ("/BuildingTemplates/0/Windows/" + key, "Office") in where(problems_of(document))


def test_layer_material_is_required() -> None:
    document = base()
    index, construction = by_name(document, "OpaqueConstructions", "Insulated wall")
    cast("list[Json]", construction["Layers"])[0]["Material"] = None
    assert (f"/OpaqueConstructions/{index}/Layers/0/Material", "Office") in where(problems_of(document))


def test_week_needs_seven_days() -> None:
    document = base()
    _, week = by_name(document, "WeekSchedules", "Office week")
    days = cast("list[object]", week["Days"])
    days[3] = None
    problems = problems_of(document)
    assert ("/WeekSchedules/1/Days/3", "Office") in where(problems)
    del days[3]
    assert ("/WeekSchedules/1/Days", "Office") in where(problems_of(document))


def test_year_part_needs_a_week() -> None:
    document = base()
    _, year = by_name(document, "YearSchedules", "Office")
    cast("list[Json]", year["Parts"])[0]["Schedule"] = None
    assert ("/YearSchedules/1/Parts/0/Schedule", "Office") in where(problems_of(document))


def test_day_needs_24_values() -> None:
    document = base()
    _, day = by_name(document, "DaySchedules", "Office day")
    day["Values"] = [1.0] * 23
    problems = problems_of(document)
    assert ("/DaySchedules/1/Values", "Office") in where(problems)


def _parts(*ranges: tuple[int, int, int, int]) -> Callable[[Json], None]:
    def change(document: Json) -> None:
        _, year = by_name(document, "YearSchedules", "Office")
        first = cast("list[Json]", year["Parts"])[0]
        year["Parts"] = [
            {**copy.deepcopy(first), "FromMonth": fm, "FromDay": fd, "ToMonth": tm, "ToDay": td}
            for fm, fd, tm, td in ranges
        ]

    return change


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (_parts((1, 1, 6, 30), (7, 2, 12, 31)), "07-01"),  # a gap
        (_parts((1, 1, 7, 1), (7, 1, 12, 31)), "07-01"),  # an overlap
        (_parts((1, 1, 12, 30)), "12-31"),  # the year's end not covered
        (_parts((0, 0, 12, 31)), "date"),  # Basilisk's default 0 is no date
    ],
    ids=["gap", "overlap", "end", "invalid-date"],
)
def test_year_parts_cover_the_year_once(change: Callable[[Json], None], fragment: str) -> None:
    document = base()
    change(document)
    problems = [problem for problem in problems_of(document) if problem.pointer == "/YearSchedules/1/Parts"]
    assert problems
    assert problems[0].rule == "year-coverage"
    assert any(fragment in problem.message for problem in problems)


def test_a_part_ending_on_29_february_is_accepted() -> None:
    document = base()
    _parts((1, 1, 2, 29), (3, 1, 12, 31))(document)
    assert problems_of(document) == []


# --- Range ---------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("collection", "name", "key", "value"),
    [
        ("OpaqueMaterials", "Concrete", "Conductivity", -1.0),
        ("OpaqueMaterials", "Concrete", "Density", -1.0),
        ("OpaqueMaterials", "Concrete", "SolarAbsorptance", 1.5),
        ("OpaqueMaterials", "Concrete", "ThermalEmittance", -0.1),
        ("OpaqueMaterials", "Concrete", "SpecificHeat", 50.0),
        ("OpaqueMaterials", "Concrete", "Roughness", "Bumpy"),
        ("ZoneLoads", "Office loads", "LightingPowerDensity", -1.0),
        ("ZoneConditionings", "Office conditioning", "HeatingCoeffOfPerf", 0.0),
        ("ZoneConditionings", "Office conditioning", "MinFreshAirPerPerson", 0.2),
        ("VentilationSettings", "Office ventilation", "Infiltration", -0.1),
        ("DomesticHotWaterSettings", "Office hot water", "WaterSupplyTemperature", 5.0),
        ("Zones", "Office perimeter", "InternalMassExposedPerFloorArea", -1.0),
    ],
)
def test_range_problems(collection: str, name: str, key: str, value: object) -> None:
    document = base()
    index, item = by_name(document, collection, name)
    item[key] = value
    assert (f"/{collection}/{index}/{key}", "Office") in where(problems_of(document))


def test_layer_thickness_must_be_positive() -> None:
    document = base()
    index, construction = by_name(document, "OpaqueConstructions", "Insulated wall")
    cast("list[Json]", construction["Layers"])[0]["Thickness"] = 0.0
    assert (f"/OpaqueConstructions/{index}/Layers/0/Thickness", "Office") in where(problems_of(document))


def test_window_to_wall_ratio_is_a_fraction() -> None:
    document = base()
    items(document, "BuildingTemplates")[0]["DefaultWindowToWallRatio"] = 1.2
    assert ("/BuildingTemplates/0/DefaultWindowToWallRatio", "Office") in where(problems_of(document))


def test_fraction_schedules_stay_within_0_and_1() -> None:
    document = base()
    _, day = by_name(document, "DaySchedules", "Office day")
    day["Values"] = [2.0] * 24
    assert ("/DaySchedules/1/Values", "Office") in where(problems_of(document))


def test_unused_components_are_not_validated() -> None:
    document = base()
    _, brick = by_name(document, "OpaqueMaterials", "Brick")
    brick["Conductivity"] = -1.0
    assert problems_of(document) == []


def test_a_component_shared_by_two_templates_names_both() -> None:
    document = base()
    templates = items(document, "BuildingTemplates")
    second = copy.deepcopy(templates[0])
    second["Name"] = "Office 2"
    second["Windows"] = {"$ref": cast("Json", templates[0]["Windows"])["$id"]}
    templates.append(second)
    items(document, "ZoneLoads")[0]["PeopleDensity"] = -1.0
    assert {template for pointer, template in where(problems_of(document)) if pointer.startswith("/ZoneLoads")} == {
        "Office",
        "Office 2",
    }


def test_a_gas_energyplus_lacks_is_a_window_layers_problem() -> None:
    document = cast("Json", json.loads((UMI / "BostonTemplateLibrary_2.json").read_text(encoding="utf-8")))
    gas = items(document, "GasMaterials")[0]
    gas["Type"] = gas["Name"] = "SMOKE"
    problems = [problem for problem in problems_of(document) if problem.pointer == "/GasMaterials/0/Type"]
    assert problems
    assert {problem.rule for problem in problems} == {"window.layers"}


@pytest.mark.parametrize(
    ("collection", "name", "key"),
    [
        ("OpaqueMaterials", "Concrete", "Conductivity"),
        ("OpaqueMaterials", "Concrete", "Density"),
        ("OpaqueMaterials", "Concrete", "SpecificHeat"),
        ("ZoneLoads", "Office loads", "LightingPowerDensity"),
        ("VentilationSettings", "Office ventilation", "Infiltration"),
    ],
)
@pytest.mark.parametrize("value", [math.nan, math.inf])
def test_non_finite_numbers_are_range_problems(collection: str, name: str, key: str, value: float) -> None:
    document = base()
    index, item = by_name(document, collection, name)
    item[key] = value
    assert (f"/{collection}/{index}/{key}", "Office") in where(problems_of(document))
