"""Every documentation page belongs to exactly one Diátaxis kind (SC-008, contracts/docs-site.md)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

DOCS = Path(__file__).resolve().parents[2] / "docs"
KIND_FOLDERS = {
    "tutorial": "tutorials",
    "how-to": "how-to",
    "reference": "reference",
    "explanation": "explanation",
}
_FRONT_MATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
_TAG = re.compile(r"^diataxis:\s*(.*?)\s*$", re.MULTILINE)


def diataxis_tags(text: str) -> list[str]:
    """Return the values of every `diataxis:` key in the page's front matter."""
    match = _FRONT_MATTER.match(text)
    if match is None:
        return []
    return [value.strip("'\"") for value in _TAG.findall(match.group(1))]


def check_page(relative: Path, text: str) -> str | None:
    """Return why the page breaks the tag rules, or None when it follows them."""
    tags = diataxis_tags(text)
    if len(tags) != 1:
        return f"{relative}: front matter needs exactly one `diataxis:` key, found {len(tags)}"
    kind = tags[0]
    if kind not in KIND_FOLDERS:
        return f"{relative}: `diataxis: {kind}` is not one of {', '.join(KIND_FOLDERS)}"
    if relative == Path("index.md"):
        return None if kind == "explanation" else f"{relative}: the home page must be tagged `explanation`"
    folder = relative.parts[0] if len(relative.parts) > 1 else None
    if folder != KIND_FOLDERS[kind]:
        return f"{relative}: tagged `{kind}`, so it belongs under `{KIND_FOLDERS[kind]}/`"
    return None


# docs/examples/ holds the tutorial's files and their SOURCES.md, which the site excludes.
PAGES = sorted(page for page in DOCS.rglob("*.md") if page.relative_to(DOCS).parts[0] != "examples")


def test_docs_have_pages() -> None:
    assert (DOCS / "index.md") in PAGES


@pytest.mark.parametrize("page", PAGES, ids=[str(p.relative_to(DOCS)) for p in PAGES])
def test_page_has_one_kind_in_its_folder(page: Path) -> None:
    problem = check_page(page.relative_to(DOCS), page.read_text(encoding="utf-8"))
    assert problem is None, problem


@pytest.mark.parametrize(
    ("relative", "text", "expected"),
    [
        ("index.md", "---\ndiataxis: explanation\n---\n# Home\n", None),
        ("index.md", "---\ndiataxis: reference\n---\n", "home page"),
        ("how-to/index.md", "---\ndiataxis: how-to\n---\n", None),
        ("reference/api.md", "---\ndiataxis: 'reference'\n---\n", None),
        ("tutorials/first.md", "# No front matter\n", "found 0"),
        ("tutorials/first.md", "---\ndiataxis: tutorial\ndiataxis: how-to\n---\n", "found 2"),
        ("explanation/about.md", "---\ndiataxis: discussion\n---\n", "is not one of"),
        ("reference/about.md", "---\ndiataxis: explanation\n---\n", "belongs under `explanation/`"),
        ("stray.md", "---\ndiataxis: reference\n---\n", "belongs under `reference/`"),
    ],
)
def test_check_page_rules(relative: str, text: str, expected: str | None) -> None:
    problem = check_page(Path(relative), text)
    if expected is None:
        assert problem is None
    else:
        assert problem is not None
        assert expected in problem
