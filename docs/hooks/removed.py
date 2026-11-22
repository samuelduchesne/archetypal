"""MkDocs hook: render `REMOVED` as the removed-capability tables (spec 001, research R7).

The migration guide (`how-to/migrate-from-v2.md`) and the reference page
(`reference/removed.md`) each hold the placeholder line `PLACEHOLDER`. This hook replaces it
with tables generated from `archetypal._removed.REMOVED`, so neither page mirrors the table by
hand (contracts/docs-site.md, rule 3). Each row carries the anchor that the migration error's
URL points to.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from archetypal._removed import REMOVED, row_anchor

if TYPE_CHECKING:
    from collections.abc import Iterable

    from archetypal._removed import RemovedCapability

PLACEHOLDER = "<!-- removed-capabilities -->"
GUIDE = "how-to/migrate-from-v2.md"

_SECTIONS: tuple[tuple[str, str], ...] = (
    ("Names", "What `from archetypal import ...` gave in archetypal 2."),
    ("Modules", "Importing any of these modules raises the migration error."),
    ("Commands and options", "The `archetypal` command rejects these, naming the replacement."),
    ("Names inside modules", "Every public name of the removed modules."),
)


def _section(row: RemovedCapability) -> str:
    if row.kind == "module":
        return "Modules"
    if row.kind in {"command", "option"}:
        return "Commands and options"
    return "Names" if row.v2_path.count(".") == 1 else "Names inside modules"


def _row(row: RemovedCapability, guide_link: str) -> str:
    v2 = f'<span id="{row_anchor(row.v2_path)}"></span>`{row.v2_path}`'
    if row.replacement is None:
        instead = "No replacement"
    else:
        instead = f"[`{row.replacement.target}`]({row.replacement.docs_url}) ({row.replacement.package})"
    if row.frequent_task is not None:
        instead += f", see [the example]({guide_link}#{row.frequent_task})"
    return f"| {v2} | {instead} | {row.reason.replace('|', '&#124;')} |"


def render(rows: Iterable[RemovedCapability], *, guide_link: str = "", level: int = 3) -> str:
    """Return the removed capabilities as Markdown tables, one per kind.

    Args:
        rows: The rows to render, normally `REMOVED`.
        guide_link: The path from the page to the migration guide; empty on the guide itself.
        level: The heading level of each table's title.

    Returns:
        The Markdown text.
    """
    by_section: dict[str, list[RemovedCapability]] = {title: [] for title, _ in _SECTIONS}
    for row in rows:
        by_section[_section(row)].append(row)
    parts: list[str] = []
    for title, intro in _SECTIONS:
        if not by_section[title]:
            continue
        parts += [
            f"{'#' * level} {title}",
            "",
            intro,
            "",
            "| archetypal 2 | Use instead | Why |",
            "|---|---|---|",
            *(_row(row, guide_link) for row in sorted(by_section[title], key=lambda r: r.v2_path.lower())),
            "",
        ]
    return "\n".join(parts)


def expand(markdown: str, *, guide_link: str = "") -> str:
    """Replace the placeholder line of a page with the generated tables.

    Args:
        markdown: The page's Markdown.
        guide_link: The path from the page to the migration guide; empty on the guide itself.

    Returns:
        The page with the tables in place of `PLACEHOLDER`, or unchanged without it.
    """
    if PLACEHOLDER not in markdown:
        return markdown
    return markdown.replace(PLACEHOLDER, render(REMOVED, guide_link=guide_link))


def on_page_markdown(markdown: str, page: Any, **_: Any) -> str:
    """Insert the tables into the pages that ask for them (MkDocs event)."""
    src_uri: str = page.file.src_uri
    if src_uri == GUIDE:
        return expand(markdown)
    depth = src_uri.count("/")
    return expand(markdown, guide_link="../" * depth + GUIDE)
