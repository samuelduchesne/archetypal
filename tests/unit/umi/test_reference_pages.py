"""The UMI reference pages are generated from their sources (spec 003 T039, FR-009, FR-013).

`docs/reference/umi-correspondence.md` and `docs/reference/translation-report.md` hold a
placeholder that the MkDocs hook `docs/hooks/umi_reference.py` replaces at build time; these
tests render the pages through the same hook.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from archetypal.umi.correspondence import CORRESPONDENCE, MappingStatus, Relevance
from archetypal.umi.report import SCHEMA_PATH, LossKind, NoteKind, report_json_schema

if TYPE_CHECKING:
    from types import ModuleType

ROOT = Path(__file__).resolve().parents[3]
HOOK = ROOT / "docs" / "hooks" / "umi_reference.py"
CORRESPONDENCE_PAGE = ROOT / "docs" / "reference" / "umi-correspondence.md"
REPORT_PAGE = ROOT / "docs" / "reference" / "translation-report.md"
MKDOCS = ROOT / "mkdocs.yml"


@pytest.fixture(scope="module")
def hook() -> ModuleType:
    """Import the MkDocs hook from its file, as MkDocs does."""
    spec = importlib.util.spec_from_file_location("docs_hooks_umi_reference", HOOK)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _section(text: str, heading: str) -> str:
    """Return the text under a `### heading`, up to the next heading."""
    start = text.index(f"\n### {heading}\n")
    end = text.find("\n#", start + 1)
    return text[start : end if end != -1 else len(text)]


def test_pages_are_wired_into_the_site() -> None:
    config = MKDOCS.read_text(encoding="utf-8")
    assert "docs/hooks/umi_reference.py" in config
    assert "reference/umi-correspondence.md" in config
    assert "reference/translation-report.md" in config
    index = (ROOT / "docs" / "reference" / "index.md").read_text(encoding="utf-8")
    assert "(umi-correspondence.md)" in index
    assert "(translation-report.md)" in index


def test_pages_hold_only_the_placeholder_not_the_tables(hook: ModuleType) -> None:
    """The tables are never hand-written: each page holds its placeholder and no table line."""
    for page, placeholder in [
        (CORRESPONDENCE_PAGE, hook.CORRESPONDENCE_PLACEHOLDER),
        (REPORT_PAGE, hook.REPORT_PLACEHOLDER),
    ]:
        text = page.read_text(encoding="utf-8")
        assert text.count(placeholder) == 1
        assert not any(line.startswith("|") for line in text.splitlines())


def test_hook_reads_the_published_schema(hook: ModuleType) -> None:
    assert hook.SCHEMA == ROOT / SCHEMA_PATH
    assert hook.load_schema() == json.loads(json.dumps(report_json_schema()))


def test_correspondence_page_lists_every_row(hook: ModuleType) -> None:
    text = hook.expand(CORRESPONDENCE_PAGE.read_text(encoding="utf-8"))
    assert hook.CORRESPONDENCE_PLACEHOLDER not in text
    for row in CORRESPONDENCE:
        lines = [line for line in _section(text, row.umi_class).splitlines() if line.startswith(f"| `{row.umi_key}` |")]
        assert len(lines) == 1, (row.umi_class, row.umi_key)
        line = lines[0]
        assert f"`{row.rule}`" in line
        assert f"| {row.status.value} |" in line
        assert f"| {row.relevance.value} |" in line
        assert all(f"`{path}`" in line for path in row.sbem_paths)
        assert (row.upstream or "—") in line
    table_lines = [line for line in text.splitlines() if line.startswith("| `") and line.count("|") == 8]
    assert len(table_lines) == len(CORRESPONDENCE)


def test_correspondence_page_explains_every_code(hook: ModuleType) -> None:
    text = hook.expand(CORRESPONDENCE_PAGE.read_text(encoding="utf-8"))
    for member in (*Relevance, *MappingStatus):
        assert f"| `{member.value}` | " in text
    assert hook.member_docs(MappingStatus)["upstream"].startswith("No SBEM field yet")


def test_report_page_lists_every_field_and_kind(hook: ModuleType) -> None:
    text = hook.expand(REPORT_PAGE.read_text(encoding="utf-8"))
    assert hook.REPORT_PLACEHOLDER not in text
    schema = report_json_schema()
    definitions = {"TranslationReport": schema, **schema["$defs"]}
    for name in ("TranslationReport", "SourceInfo", "Loss", "Note"):
        section = _section(text, name)
        for field in definitions[name]["properties"]:
            assert f"| `{field}` |" in section, (name, field)
    for enum in (LossKind, NoteKind):
        section = _section(text, enum.__name__)
        docs = hook.member_docs(enum)
        for member in enum:
            assert f"| `{member.value}` | {docs[member.value]} |" in section


def test_report_page_refuses_a_stale_schema(hook: ModuleType) -> None:
    schema = report_json_schema()
    schema["$defs"]["LossKind"]["enum"] = ["lost"]
    with pytest.raises(ValueError, match="regenerate the schema"):
        hook.render_report(schema)


def test_attribute_docs_reads_continuation_lines(hook: ModuleType) -> None:
    description = "Title.\n\nAttributes:\n    a: First\n        continued.\n    b: Second.\n"
    assert hook.attribute_docs(description) == {"a": "First continued.", "b": "Second."}


def test_rendering_is_deterministic(hook: ModuleType) -> None:
    assert hook.render_correspondence(CORRESPONDENCE) == hook.render_correspondence(CORRESPONDENCE)
    assert hook.render_report(hook.load_schema()) == hook.render_report(hook.load_schema())
