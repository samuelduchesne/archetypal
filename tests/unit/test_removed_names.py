"""Using a removed v2 name or module raises the migration error (FR-016, SC-007, scenario 2.1).

`RemovedInArchetypal3Error` is an `ImportError`. CPython does not let it also derive from
`AttributeError`, so `hasattr(archetypal, "IDF")` raises it instead of returning `False`.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest

import archetypal
from archetypal._removed import MIGRATION_GUIDE_URL, REMOVED, row_anchor
from archetypal.errors import RemovedInArchetypal3Error

SRC = Path(archetypal.__file__).resolve().parent

# The 12 top-level modules of archetypal 2 that archetypal 3 replaces with a raising stub (R7).
STUB_MODULES = (
    "dataportal",
    "eplus_interface",
    "idfclass",
    "plot",
    "reportdata",
    "schedule",
    "simple_glazing",
    "tabulardata",
    "template",
    "umi_template",
    "utils",
    "zone_graph",
)

# Rows reached from the package itself: `archetypal.X` and `from archetypal import X`.
TOP_LEVEL = [r.v2_path for r in REMOVED if r.kind in {"name", "module"} and r.v2_path.count(".") == 1]
MODULES = [r.v2_path for r in REMOVED if r.kind == "module"]
NESTED_NAMES = [r.v2_path for r in REMOVED if r.kind == "name" and r.v2_path.count(".") > 1]


def _forget(module: str) -> None:
    """Drop a module and its children from `sys.modules`, so the next import runs it again."""
    for loaded in [m for m in sys.modules if m == module or m.startswith(f"{module}.")]:
        del sys.modules[loaded]


def _guide_section(v2_path: str) -> str:
    return f"{MIGRATION_GUIDE_URL}#{row_anchor(v2_path)}"


def test_the_spec_names_are_removed() -> None:
    required = {
        "IDF",
        "UmiTemplateLibrary",
        "BuildingTemplate",
        "EnergyPlusVersion",
        "Settings",
        "settings",
        "config",
        "clear_cache",
        "parallel_process",
        "dataportal",
        "utils",
    }
    assert {f"archetypal.{n}" for n in required} <= set(TOP_LEVEL)


@pytest.mark.parametrize("v2_path", TOP_LEVEL)
def test_attribute_access_raises(v2_path: str) -> None:
    name = v2_path.removeprefix("archetypal.")
    with pytest.raises(RemovedInArchetypal3Error) as info:
        getattr(archetypal, name)
    assert info.value.subject == v2_path
    assert _guide_section(v2_path) in str(info.value)


@pytest.mark.parametrize("v2_path", TOP_LEVEL)
def test_from_import_raises(v2_path: str) -> None:
    name = v2_path.removeprefix("archetypal.")
    _forget(v2_path)
    with pytest.raises(RemovedInArchetypal3Error) as info:
        exec(f"from archetypal import {name}", {})  # noqa: S102
    assert MIGRATION_GUIDE_URL in str(info.value)
    assert isinstance(info.value, ImportError)


@pytest.mark.parametrize("v2_path", MODULES)
def test_importing_a_removed_module_raises(v2_path: str) -> None:
    _forget(v2_path)
    with pytest.raises(RemovedInArchetypal3Error) as info:
        importlib.import_module(v2_path)
    assert MIGRATION_GUIDE_URL in str(info.value)


@pytest.mark.parametrize("v2_path", MODULES)
def test_importing_a_removed_module_names_that_module(v2_path: str) -> None:
    for statement in (f"import {v2_path}", f"importlib.import_module({v2_path!r})"):
        _forget("archetypal." + v2_path.split(".")[1])
        with pytest.raises(RemovedInArchetypal3Error) as info:
            exec(statement, {"importlib": importlib})  # noqa: S102
        assert info.value.subject == v2_path, statement
        assert _guide_section(v2_path) in str(info.value)


def test_from_a_nested_removed_module_names_that_module() -> None:
    _forget("archetypal.idfclass")
    with pytest.raises(RemovedInArchetypal3Error) as info:
        exec("from archetypal.idfclass.sql import Sql", {})  # noqa: S102
    assert info.value.subject == "archetypal.idfclass.sql"


def test_an_unknown_child_of_a_removed_module_names_the_nearest_row() -> None:
    _forget("archetypal.template")
    with pytest.raises(RemovedInArchetypal3Error) as info:
        importlib.import_module("archetypal.template.materials.not_a_v2_module")
    assert info.value.subject == "archetypal.template.materials"


@pytest.mark.parametrize("v2_path", MODULES)
def test_every_module_row_has_a_stub(v2_path: str) -> None:
    top = v2_path.split(".")[1]
    assert top in STUB_MODULES, f"{v2_path}: no stub module for archetypal.{top}"


@pytest.mark.parametrize("module", STUB_MODULES)
def test_stub_is_two_lines_calling_raise_removed(module: str) -> None:
    stub = SRC / f"{module}.py"
    assert stub.is_file()
    assert "raise_removed(__name__)" in stub.read_text(encoding="utf-8")
    assert f"archetypal.{module}" in MODULES


@pytest.mark.parametrize("v2_path", NESTED_NAMES)
def test_nested_names_live_in_a_removed_module(v2_path: str) -> None:
    module = v2_path.rpartition(".")[0]
    assert module in MODULES or module == "archetypal.cli", f"{v2_path}: its module {module} is not removed"


def test_other_names_raise_attribute_error() -> None:
    with pytest.raises(AttributeError, match="not_a_v2_name"):
        _ = archetypal.not_a_v2_name  # type: ignore[attr-defined]
    assert not hasattr(archetypal, "not_a_v2_name")


def test_kept_names_still_work() -> None:
    assert isinstance(archetypal.__version__, str)
    importlib.import_module("archetypal.errors")
