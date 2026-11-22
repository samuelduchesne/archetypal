"""The reduction reference pages are generated from their sources (spec 002 T066, FR-030).

`docs/reference/reduction-report.md` and `docs/reference/results-requirements.md` hold a
placeholder that the MkDocs hook `docs/hooks/reduction_reference.py` replaces at build time;
these tests render the pages through the same hook.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from archetypal.reduction import RESULTS_REQUIREMENTS
from archetypal.reduction.report import RULE_IDS, report_json_schema

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / "docs" / "hooks" / "reduction_reference.py"
REPORT_PAGE = ROOT / "docs" / "reference" / "reduction-report.md"
REQUIREMENTS_PAGE = ROOT / "docs" / "reference" / "results-requirements.md"


@pytest.fixture(scope="module")
def hook() -> ModuleType:
    """Import the MkDocs hook from its file, as MkDocs does."""
    spec = importlib.util.spec_from_file_location("docs_hooks_reduction_reference", HOOK)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pages_are_wired_into_the_site() -> None:
    config = (ROOT / "mkdocs.yml").read_text(encoding="utf-8")
    assert "docs/hooks/reduction_reference.py" in config
    assert "reference/reduction-report.md" in config
    assert "reference/results-requirements.md" in config


def test_pages_hold_the_placeholders_not_the_tables(hook: ModuleType) -> None:
    report = REPORT_PAGE.read_text(encoding="utf-8")
    requirements = REQUIREMENTS_PAGE.read_text(encoding="utf-8")
    assert hook.REPORT_PLACEHOLDER in report
    assert hook.REQUIREMENTS_PLACEHOLDER in requirements
    assert "| `schema_version` |" not in report
    assert "Output:Variable,*" not in requirements


def test_report_page_lists_every_object_field_and_rule(hook: ModuleType) -> None:
    page = hook.expand(REPORT_PAGE.read_text(encoding="utf-8"))
    schema = report_json_schema()
    assert hook.REPORT_PLACEHOLDER not in page
    assert hook.SCHEMA_ID_PLACEHOLDER not in page
    for name, definition in {"ReductionReport": schema, **schema["$defs"]}.items():
        if "properties" not in definition:
            continue
        assert f"\n### {name}\n" in page
        for field in definition["properties"]:
            assert f"| `{field}` |" in page
    for rule in RULE_IDS:
        assert f"- `{rule}`" in page


def test_requirements_page_lists_every_requirement(hook: ModuleType) -> None:
    page = hook.expand(REQUIREMENTS_PAGE.read_text(encoding="utf-8"))
    assert hook.REQUIREMENTS_PLACEHOLDER not in page
    for requirement in RESULTS_REQUIREMENTS:
        assert f"| `{requirement.item}` |" in page
        assert requirement.idf_text in page
