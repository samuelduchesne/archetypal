"""The UMI to SBEM field correspondence and its rule registry (spec 003 T013, SC-005)."""

from __future__ import annotations

import importlib
import json
import pkgutil
import re
import typing
from collections import Counter
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from epinterface.sbem import components as sbem_components
from epinterface.sbem.archetype import Archetype
from epinterface.sbem.components.zones import ZoneComponent
from pydantic import BaseModel

from archetypal.umi import correspondence
from archetypal.umi.correspondence import (
    CORRESPONDENCE,
    LIBRARY_RULES,
    RULE_MODULES,
    UPSTREAM_ITEMS,
    MappingStatus,
    Relevance,
    Rule,
    declare_rule,
    get_rule,
    mapping,
    mappings_for,
    registered_rules,
    rule,
    rule_ids,
)

if TYPE_CHECKING:
    from archetypal.umi.correspondence import FieldMapping

ROOT = Path(__file__).resolve().parents[3]
BASILISK_FIELDS = ROOT / "tests" / "data" / "basilisk_fields.json"
ROADMAP = ROOT / ".specify" / "memory" / "roadmap.md"


def basilisk_fields() -> set[tuple[str, str]]:
    listed: dict[str, list[str]] = json.loads(BASILISK_FIELDS.read_text(encoding="utf-8"))
    return {(cls, key) for cls, keys in listed.items() for key in keys}


def roadmap_items() -> set[str]:
    return set(re.findall(r"^- \*\*(UP-\d+) —", ROADMAP.read_text(encoding="utf-8"), flags=re.MULTILINE))


def _models(annotation: object) -> list[type[BaseModel]]:
    """The pydantic models inside an annotation (through Optional, list, Annotated, ...)."""
    if isinstance(annotation, type) and issubclass(annotation, BaseModel):
        return [annotation]
    return [model for arg in typing.get_args(annotation) for model in _models(arg)]


def _sbem_classes() -> dict[str, type[BaseModel]]:
    modules = [
        importlib.import_module(f"{sbem_components.__name__}.{name}")
        for name in ("envelope", "materials", "operations", "schedules", "space_use", "systems", "zones")
    ]
    return {
        attribute: value
        for module in modules
        for attribute, value in vars(module).items()
        if isinstance(value, type) and issubclass(value, BaseModel) and attribute.endswith("Component")
    }


SBEM_CLASSES = _sbem_classes()


def resolves(path: str) -> bool:
    """Whether an SBEM path names a field, walking `model_fields` from the path's root."""
    head, *rest = path.split(".")
    if head == "archetype":
        models: list[type[BaseModel]] = [Archetype]
    elif head in SBEM_CLASSES:
        models = [SBEM_CLASSES[head]]
    else:
        models = [ZoneComponent]
        rest = [head, *rest]
    if not rest:
        return False
    for segment in rest:
        fields = [model.model_fields[segment] for model in models if segment in model.model_fields]
        if not fields:
            return False
        models = [model for field in fields for model in _models(field.annotation)]
    return True


# --- SC-005: completeness against Basilisk --------------------------------------------------------


def test_every_basilisk_field_has_a_row() -> None:
    rows = {(row.umi_class, row.umi_key) for row in CORRESPONDENCE}
    assert basilisk_fields() - rows == set()


def test_no_row_for_a_field_basilisk_does_not_serialise() -> None:
    rows = {(row.umi_class, row.umi_key) for row in CORRESPONDENCE}
    assert rows - basilisk_fields() == set()


def test_shared_fields_are_listed_under_their_declaring_class() -> None:
    assert mapping("LibraryComponent", "Name").rule == "names.component"
    assert mapping("MaterialBase", "Conductivity").status is MappingStatus.EXACT
    with pytest.raises(KeyError):
        mapping("OpaqueMaterial", "Conductivity")


# --- data-model.md invariants ---------------------------------------------------------------------


def test_each_field_appears_exactly_once() -> None:
    counts = Counter((row.umi_class, row.umi_key) for row in CORRESPONDENCE)
    assert [field for field, count in counts.items() if count > 1] == []


@pytest.mark.parametrize("row", CORRESPONDENCE, ids=lambda row: f"{row.umi_class}.{row.umi_key}")
def test_row_is_consistent(row: FieldMapping) -> None:
    assert isinstance(row.relevance, Relevance)
    assert isinstance(row.status, MappingStatus)
    assert row.rule
    assert row.note.strip()
    if row.status in {MappingStatus.EXACT, MappingStatus.CONVERTED}:
        assert row.sbem_paths, "exact and converted fields name at least one SBEM path"
    else:
        assert row.sbem_paths == (), "upstream and none fields name no SBEM path"
    if row.status is MappingStatus.UPSTREAM:
        assert row.upstream is not None, "upstream fields name a UP item"
    if row.upstream is not None:
        assert row.upstream in UPSTREAM_ITEMS
        assert row.upstream in row.note


@pytest.mark.parametrize(
    "path", sorted({path for row in CORRESPONDENCE for path in row.sbem_paths}), ids=lambda path: path
)
def test_sbem_path_resolves_on_epinterface(path: str) -> None:
    assert resolves(path), f"{path} is not a field of epinterface's SBEM model"


def test_resolver_rejects_unknown_paths() -> None:
    assert not resolves("Operations.SpaceUse.Lighting.NoSuchField")
    assert not resolves("archetype.NoSuchField")
    assert not resolves("ConstructionMaterialComponent")


def test_upstream_items_are_roadmap_items() -> None:
    items = roadmap_items()
    assert {"UP-1", "UP-9", "UP-10"} <= items
    assert items >= UPSTREAM_ITEMS
    assert {row.upstream for row in CORRESPONDENCE if row.upstream} <= items


UP9_NOT_ADDED = [
    ("ZoneVentilation", "Afn"),
    ("WindowSettings", "AfnDischargeC"),
    ("WindowSettings", "AfnTempSetpoint"),
    ("WindowSettings", "AfnWindowAvailability"),
    ("WindowSettings", "IsVirtualPartition"),
    ("WindowSettings", "IsZoneMixingOn"),
    ("WindowSettings", "Type"),
    ("WindowSettings", "ZoneMixingAvailabilitySchedule"),
    ("WindowSettings", "ZoneMixingDeltaTemperature"),
    ("WindowSettings", "ZoneMixingFlowRate"),
]
"""R6's fields the fork's UP-9 does not add: interior windows, zone mixing, airflow network."""


def test_fields_up9_does_not_add_stay_lost_naming_up9() -> None:
    """FR-002, FR-010: the fields UP-9 left out are still lost with UP-9."""
    upstream = {(row.umi_class, row.umi_key) for row in CORRESPONDENCE if row.upstream == "UP-9"}
    assert upstream == set(UP9_NOT_ADDED)
    for cls, key in UP9_NOT_ADDED:
        row = mapping(cls, key)
        assert row.status is MappingStatus.UPSTREAM, (cls, key)
    assert mapping("ZoneConditioning", "HeatRecoveryEfficiencySensible").upstream == "UP-2"


def test_fields_up9_adds_are_mapped() -> None:
    """T070: R6's fields that the fork's UP-9 added map to SBEM paths."""
    for cls, key in [
        ("BuildingTemplate", "PartitionRatio"),
        ("ZoneLoads", "IlluminanceTarget"),
        ("WindowSettings", "OperableArea"),
        ("ZoneVentilation", "ScheduledVentilationAch"),
        ("ZoneConditioning", "MaxHeatingCapacity"),
        ("StructureInformation", "MassRatios"),
        ("DaySchedule", "Category"),
        ("GlazingMaterial", "SolarTransmittance"),
        ("WindowConstruction", "Layers"),
        ("ZoneConstructions", "IsFacadeAdiabatic"),
        ("MaterialBase", "EmbodiedEnergy"),
        ("ConstructionBase", "AssemblyCarbon"),
        ("BuildingTemplate", "YearFrom"),
    ]:
        row = mapping(cls, key)
        assert row.status in {MappingStatus.EXACT, MappingStatus.CONVERTED}, (cls, key)
        assert row.sbem_paths, (cls, key)
    assert mapping("WindowConstruction", "Layers").status is MappingStatus.EXACT  # both directions exact


def test_conversion_rules_of_data_model_are_used() -> None:
    expected = {
        "dhw.per_person",
        "cop.system",
        "material.carbon_per_m3",
        "schedule.months",
        "thermostat.constant",
        "window.layers",
        "vent.provider",
        "wwr.uniform",
    }
    assert expected <= rule_ids()


def test_library_rules_are_not_table_rules() -> None:
    assert LIBRARY_RULES.isdisjoint(rule_ids())


def test_every_rule_has_an_owning_module() -> None:
    assert {rule_id.split(".", 1)[0] for rule_id in rule_ids()} <= set(RULE_MODULES)


def test_mappings_for_returns_the_rule_rows_in_order() -> None:
    rows = mappings_for("cop.system")
    assert [(row.umi_class, row.umi_key) for row in rows] == [
        ("DomesticHotWaterSettings", "CoefficientOfPerformance"),
        ("ZoneConditioning", "HeatingCoeffOfPerf"),
        ("ZoneConditioning", "CoolingCoeffOfPerf"),
    ]
    assert mappings_for("no.such_rule") == ()


# --- the registry ---------------------------------------------------------------------------------


def test_registered_rules_equal_table_rules() -> None:
    """data-model.md: the set of `rule` values equals the set of registered rules."""
    assert set(registered_rules()) == rule_ids()


def test_every_owning_module_is_a_public_rules_module() -> None:
    """The registry's auto-import loads every module `RULE_MODULES` names; `_common` owns no prefix."""
    rules = importlib.import_module("archetypal.umi.rules")
    public = {module.name for module in pkgutil.iter_modules(rules.__path__) if not module.name.startswith("_")}
    assert set(RULE_MODULES.values()) == public
    assert "_common" not in RULE_MODULES.values()


def test_shared_module_registers_no_rule() -> None:
    functions = [
        function
        for registered in registered_rules().values()
        for function in (registered.to_sbem, registered.to_umi)
        if function is not None
    ]
    assert all(function.__module__ != "archetypal.umi.rules._common" for function in functions)


def test_registered_rules_live_in_their_owning_module() -> None:
    for rule_id, registered in registered_rules().items():
        owner = f"archetypal.umi.rules.{RULE_MODULES[rule_id.split('.', 1)[0]]}"
        for function in (registered.to_sbem, registered.to_umi):
            if function is not None:
                assert function.__module__ == owner, (rule_id, function)


@pytest.fixture
def empty_registry(monkeypatch: pytest.MonkeyPatch) -> dict[str, Rule]:
    registry: dict[str, Rule] = {}
    monkeypatch.setattr(correspondence, "_REGISTRY", registry)
    return registry


def test_rule_decorator_registers_both_directions(empty_registry: dict[str, Rule]) -> None:
    @rule("cop.system", to="sbem")
    def system_cop(cop: float) -> tuple[float, float]:
        return cop, 1.0

    @rule("cop.system", to="umi")
    def umi_cop(system: float, distribution: float) -> float:
        return system * distribution

    registered = empty_registry["cop.system"]
    assert (registered.to_sbem, registered.to_umi) == (system_cop, umi_cop)
    assert system_cop(3.0) == (3.0, 1.0)  # the decorator returns the function unchanged
    assert get_rule("cop.system") is registered
    assert registered.mappings == mappings_for("cop.system")


def test_rule_with_one_direction(empty_registry: dict[str, Rule]) -> None:
    @rule("window.layers", to="sbem")
    def simple(layers: list[object]) -> float:
        return float(len(layers))

    assert empty_registry["window.layers"].to_umi is None


def test_rule_refuses_an_id_not_in_the_table(empty_registry: dict[str, Rule]) -> None:
    with pytest.raises(ValueError, match="not named by any row"):
        rule("no.such_rule", to="sbem")
    with pytest.raises(ValueError, match="not named by any row"):
        declare_rule("no.such_rule")
    assert empty_registry == {}


def test_rule_refuses_a_second_function_for_one_direction(empty_registry: dict[str, Rule]) -> None:
    @rule("dhw.per_person", to="sbem")
    def first(value: float) -> float:
        return value

    def second(value: float) -> float:
        return value

    with pytest.raises(ValueError, match="already has a to_sbem function"):
        rule("dhw.per_person", to="sbem")(second)
    assert empty_registry["dhw.per_person"].to_sbem is first
    rule("dhw.per_person", to="sbem")(first)  # registering the same definition again is harmless


def test_declare_rule_registers_a_rule_without_functions(empty_registry: dict[str, Rule]) -> None:
    declared = declare_rule("building.partition_ratio")
    assert declared == Rule("building.partition_ratio")
    assert declare_rule("building.partition_ratio") is declared
    assert empty_registry == {"building.partition_ratio": declared}


def test_get_rule_raises_for_an_unregistered_rule(empty_registry: dict[str, Rule]) -> None:
    with pytest.raises(KeyError):
        get_rule("wwr.uniform")


def test_registry_view_is_read_only() -> None:
    view = registered_rules()
    with pytest.raises(TypeError):
        view["x"] = Rule("x")  # type: ignore[index]
