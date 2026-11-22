"""The migration guide lists every removed capability and has one example per frequent task.

FR-017, FR-018, scenario 2.2. The guide's table is generated from `REMOVED` by the MkDocs hook
`docs/hooks/removed.py`; this test renders the page through the same hook.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import TYPE_CHECKING, get_args

import pytest

from archetypal._removed import REMOVED, FrequentTask, row_anchor

if TYPE_CHECKING:
    from types import ModuleType

    from archetypal._removed import RemovedCapability

ROOT = Path(__file__).resolve().parents[2]
GUIDE = ROOT / "docs" / "how-to" / "migrate-from-v2.md"
REFERENCE = ROOT / "docs" / "reference" / "removed.md"
HOOK = ROOT / "docs" / "hooks" / "removed.py"
TASKS: tuple[str, ...] = get_args(FrequentTask)
_FENCE = re.compile(r"^(`{3,})[ \t]*(\w*)[^\n]*\n.*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)


def load_hook() -> ModuleType:
    """Import the MkDocs hook from its file, as MkDocs does."""
    spec = importlib.util.spec_from_file_location("docs_hooks_removed", HOOK)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def rendered(page: Path) -> str:
    """Return the page's Markdown after the hook has inserted the generated table."""
    expanded: str = load_hook().expand(page.read_text(encoding="utf-8"))
    return expanded


def row_line(text: str, row: RemovedCapability) -> str | None:
    """Return the table line of a row, found by its anchor."""
    marker = f'id="{row_anchor(row.v2_path)}"'
    return next((line for line in text.splitlines() if marker in line and line.startswith("|")), None)


def task_section(text: str, task: str) -> str:
    """Return the guide's section whose heading carries the id `task`."""
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("#") and f"{{#{task}}}" in line)
    level = len(lines[start]) - len(lines[start].lstrip("#"))
    end = next(
        (
            i
            for i in range(start + 1, len(lines))
            if lines[i].startswith("#") and len(lines[i]) - len(lines[i].lstrip("#")) <= level
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def fences(section: str) -> list[str]:
    """Return the language of every fenced code block in a section."""
    return [match.group(2) for match in _FENCE.finditer(section)]


@pytest.fixture(scope="module")
def guide() -> str:
    return rendered(GUIDE)


@pytest.mark.parametrize("page", [GUIDE, REFERENCE], ids=["guide", "reference"])
def test_page_has_the_generated_table(page: Path) -> None:
    hook = load_hook()
    assert hook.PLACEHOLDER in page.read_text(encoding="utf-8")
    assert hook.PLACEHOLDER not in rendered(page)


@pytest.mark.parametrize("row", REMOVED, ids=[r.v2_path for r in REMOVED])
def test_every_row_is_in_the_guide_table(guide: str, row: RemovedCapability) -> None:
    line = row_line(guide, row)
    assert line is not None, f"{row.v2_path}: not in the guide's table"
    assert f"`{row.v2_path}`" in line
    if row.replacement is None:
        assert row.reason in line
    else:
        assert f"`{row.replacement.target}`" in line
        assert row.replacement.docs_url in line


@pytest.mark.parametrize("task", TASKS)
def test_every_frequent_task_has_one_before_and_after(guide: str, task: str) -> None:
    assert fences(task_section(guide, task)) == ["text", "python"], f"{task}: needs one `text` then one `python` block"


@pytest.mark.parametrize("task", TASKS)
def test_every_frequent_task_is_linked_from_a_row(task: str) -> None:
    assert any(row.frequent_task == task for row in REMOVED)


@pytest.mark.parametrize("row", [r for r in REMOVED if r.frequent_task], ids=lambda r: r.v2_path)
def test_linked_rows_point_to_their_example(guide: str, row: RemovedCapability) -> None:
    line = row_line(guide, row)
    assert line is not None
    assert f"(#{row.frequent_task})" in line


def test_section_helpers() -> None:
    page = "\n".join([
        "## Tasks",
        "### Read results {#read-results}",
        "```text",
        "old",
        "```",
        "````python",
        "new",
        "````",
        "### Next {#next}",
        "```python",
        "other",
        "```",
    ])
    assert fences(task_section(page, "read-results")) == ["text", "python"]
    assert fences(task_section(page, "next")) == ["python"]


def test_row_anchors_are_unique() -> None:
    anchors = [row_anchor(row.v2_path) for row in REMOVED]
    assert len(set(anchors)) == len(anchors)
    assert row_anchor("archetypal.Settings") == "archetypalsettings"
    assert row_anchor("archetypal.settings") == "archetypalsettings_1"
