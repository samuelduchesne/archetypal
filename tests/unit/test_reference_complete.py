"""The built site's reference documents every public name and every command and option (US3, scenario 2).

The site is built once per module (`mkdocs build` into a temporary folder, about 3 s), then:

- every name in the `__all__` of a public module has an entry generated from its docstring by
  mkdocstrings (an anchor `<module>.<name>`) in a reference page; `__version__`, a string that
  cannot carry a docstring, is named as `archetypal.__version__` instead;
- every visible command of the `archetypal` group has its section in the command-line page,
  and that section shows each of its visible options (every spelling, short flags included)
  and arguments.

The removed archetypal 2 options and the `transition` command are hidden, so they are not
required here; `docs/reference/removed.md` lists them.
"""

from __future__ import annotations

import importlib
from html.parser import HTMLParser
from pathlib import Path
from typing import TYPE_CHECKING

import click
import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator

ROOT = Path(__file__).resolve().parents[2]
PUBLIC_MODULES = ("archetypal", "archetypal.reduction", "archetypal.comparison", "archetypal.umi", "archetypal.errors")
NO_DOCSTRING = {"__version__"}
"""Public names that are plain values: they are named in the reference rather than documented."""
_HEADINGS = {"h1", "h2", "h3", "h4", "h5", "h6"}


class _Page(HTMLParser):
    """Collect a page's anchors, and its `<code>` texts and text per section (heading id)."""

    def __init__(self) -> None:
        super().__init__()
        self.ids: set[str] = set()
        self.code: dict[str, set[str]] = {}
        self.text: dict[str, list[str]] = {}
        self._section = ""
        self._code_depth = 0
        self._code: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        anchor = dict(attrs).get("id")
        if anchor:
            self.ids.add(anchor)
            if tag in _HEADINGS:
                self._section = anchor
        if tag == "code":
            self._code_depth += 1
            if self._code_depth == 1:
                self._code = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "code" and self._code_depth:
            self._code_depth -= 1
            if not self._code_depth:
                self.code.setdefault(self._section, set()).add("".join(self._code).strip())

    def handle_data(self, data: str) -> None:
        if self._code_depth:
            self._code.append(data)
        self.text.setdefault(self._section, []).append(data)


def _parse(path: Path) -> _Page:
    page = _Page()
    page.feed(path.read_text(encoding="utf-8"))
    return page


@pytest.fixture(scope="module")
def reference(tmp_path_factory: pytest.TempPathFactory) -> dict[str, _Page]:
    """Build the site once into a temporary folder; return its reference pages by URL path."""
    from mkdocs.commands.build import build  # noqa: PLC0415 - only this module needs mkdocs
    from mkdocs.config import load_config  # noqa: PLC0415

    site = tmp_path_factory.mktemp("site")
    build(load_config(str(ROOT / "mkdocs.yml"), site_dir=str(site)))
    pages = {
        page.parent.relative_to(site).as_posix(): _parse(page) for page in (site / "reference").rglob("index.html")
    }
    assert pages, "the built site has no reference pages"
    return pages


def _public_names() -> Iterator[tuple[str, str]]:
    for module in PUBLIC_MODULES:
        for name in importlib.import_module(module).__all__:
            yield module, name


def _visible_commands() -> Iterator[tuple[str, click.Command]]:
    from archetypal.cli import main  # noqa: PLC0415

    yield "archetypal", main
    for name, command in main.commands.items():
        if not command.hidden:
            yield f"archetypal-{name}", command


PUBLIC_NAMES = list(_public_names())
COMMANDS = list(_visible_commands())


@pytest.mark.parametrize(("module", "name"), PUBLIC_NAMES, ids=[f"{m}.{n}" for m, n in PUBLIC_NAMES])
def test_public_name_is_in_the_reference(reference: dict[str, _Page], module: str, name: str) -> None:
    if name in NO_DOCSTRING:
        found = [path for path, page in reference.items() if f"{module}.{name}" in set().union(*page.code.values())]
        assert found, f"`{module}.{name}` is named in no reference page"
        return
    documented = [
        path
        for path, page in reference.items()
        if any(anchor.startswith("archetypal.") and anchor.rsplit(".", 1)[-1] == name for anchor in page.ids)
    ]
    assert documented, f"`{module}.{name}` has no entry generated from its docstring in any reference page"


@pytest.mark.parametrize(("section", "command"), COMMANDS, ids=[s for s, _ in COMMANDS])
def test_command_and_options_are_in_the_reference(
    reference: dict[str, _Page], section: str, command: click.Command
) -> None:
    page = reference.get("reference/cli")
    assert page is not None, "the command-line reference page is missing"
    assert section in page.ids, f"`{section.replace('-', ' ')}` has no section in the command-line reference"
    code = page.code.get(section, set())
    text = "".join(page.text.get(section, []))
    for param in command.params:
        if getattr(param, "hidden", False):
            continue
        if isinstance(param, click.Argument):
            assert param.human_readable_name in text, f"{section}: argument {param.human_readable_name} is not shown"
            continue
        for spelling in [*param.opts, *param.secondary_opts]:
            assert spelling in code, f"{section}: option `{spelling}` is not in the command-line reference"


def test_page_parser_collects_sections() -> None:
    page = _Page()
    page.feed(
        '<h2 id="a">A</h2><p><code>-x</code> and <code><span>--long</span></code></p>'
        '<h3 id="b">B</h3><p>Usage: b [OPTIONS] FILE</p><div id="archetypal.umi.Loss"></div>'
    )
    assert page.code == {"a": {"-x", "--long"}}
    assert "FILE" in "".join(page.text["b"])
    assert "archetypal.umi.Loss" in page.ids
