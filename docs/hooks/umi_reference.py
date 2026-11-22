"""MkDocs hook: generate the UMI translation reference pages (spec 003 T039, FR-009, FR-013).

Two reference pages hold a placeholder line that this hook replaces at build time, so neither
page mirrors its source by hand (contracts/docs-site.md, rule 3):

- `reference/umi-correspondence.md` (`CORRESPONDENCE_PLACEHOLDER`): one table per UMI class,
  generated from `archetypal.umi.correspondence.CORRESPONDENCE`;
- `reference/translation-report.md` (`REPORT_PLACEHOLDER`): one table per object of the loss
  report, generated from the published JSON Schema `docs/schemas/translation-report-1.0.json`.

The meanings of enumeration members (relevance, status, loss and note kinds) come from the
member docstrings in the source, read with `ast`, so they stay with the code that defines them.
"""

from __future__ import annotations

import ast
import inspect
import itertools
import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any

from archetypal.umi.correspondence import CORRESPONDENCE, MappingStatus, Relevance
from archetypal.umi.report import LossKind, NoteKind

if TYPE_CHECKING:
    from collections.abc import Iterable
    from enum import Enum

    from archetypal.umi.correspondence import FieldMapping

CORRESPONDENCE_PLACEHOLDER = "<!-- umi-correspondence -->"
REPORT_PLACEHOLDER = "<!-- translation-report-schema -->"
SCHEMA = Path(__file__).resolve().parents[1] / "schemas" / "translation-report-1.0.json"

# The report's objects, in the order the page lists them, and the enumerations they use.
_OBJECTS: tuple[str, ...] = ("TranslationReport", "SourceInfo", "Loss", "Note")
_ENUMS: dict[str, type[Enum]] = {"LossKind": LossKind, "NoteKind": NoteKind}
_ATTRIBUTE = re.compile(r"^    (\w+): (.*)$")


def _cell(text: str) -> str:
    """Return text safe inside a Markdown table cell."""
    return text.replace("|", "&#124;").replace("\n", " ")


def member_docs(enum: type[Enum]) -> dict[str, str]:
    """Return the docstring of each member of an enumeration, by value, read from its source."""
    definition = ast.parse(inspect.getsource(enum)).body[0]
    if not isinstance(definition, ast.ClassDef):
        msg = f"{enum.__name__} is not defined by a class statement"
        raise TypeError(msg)
    docs: dict[str, str] = {}
    for statement, following in itertools.pairwise(definition.body):
        if (
            isinstance(statement, ast.Assign)
            and isinstance(statement.targets[0], ast.Name)
            and isinstance(following, ast.Expr)
            and isinstance(following.value, ast.Constant)
            and isinstance(following.value.value, str)
        ):
            name = statement.targets[0].id
            docs[str(enum[name].value)] = " ".join(following.value.value.split())
    return docs


def _enum_table(enum: type[Enum], header: str) -> list[str]:
    docs = member_docs(enum)
    return [
        f"| {header} | Meaning |",
        "|---|---|",
        *(f"| `{member.value}` | {_cell(docs.get(str(member.value), ''))} |" for member in enum),
        "",
    ]


# --- The field correspondence ---------------------------------------------------------------------


def _correspondence_row(row: FieldMapping) -> str:
    paths = "<br>".join(f"`{path}`" for path in row.sbem_paths) or "—"
    upstream = row.upstream or "—"
    return (
        f"| `{row.umi_key}` | {row.relevance.value} | {paths} | `{row.rule}` | {row.status.value} | "
        f"{upstream} | {_cell(row.note)} |"
    )


def render_correspondence(rows: Iterable[FieldMapping], *, level: int = 3) -> str:
    """Return the correspondence as Markdown: the legends, then one table per UMI class.

    Args:
        rows: The rows to render, normally `CORRESPONDENCE`. Classes appear in the order of
            their first row; rows keep their order within a class.
        level: The heading level of each class's title.

    Returns:
        The Markdown text.
    """
    by_class: dict[str, list[FieldMapping]] = {}
    for row in rows:
        by_class.setdefault(row.umi_class, []).append(row)
    parts = [
        f"{'#' * (level - 1)} Relevance",
        "",
        *_enum_table(Relevance, "Code"),
        f"{'#' * (level - 1)} Status",
        "",
        *_enum_table(MappingStatus, "Status"),
        f"{'#' * (level - 1)} Fields by UMI class",
        "",
    ]
    for umi_class, class_rows in by_class.items():
        parts += [
            f"{'#' * level} {umi_class}",
            "",
            "| UMI key | Relevance | SBEM fields | Rule | Status | Upstream | Note |",
            "|---|---|---|---|---|---|---|",
            *(_correspondence_row(row) for row in class_rows),
            "",
        ]
    return "\n".join(parts)


# --- The report schema ----------------------------------------------------------------------------


def attribute_docs(description: str) -> dict[str, str]:
    """Return the `Attributes:` entries of a Google-style docstring, by attribute name."""
    docs: dict[str, str] = {}
    current: str | None = None
    in_attributes = False
    for line in description.splitlines():
        if line.strip() == "Attributes:":
            in_attributes = True
            continue
        if not in_attributes:
            continue
        match = _ATTRIBUTE.match(line)
        if match:
            current = str(match.group(1))
            docs[current] = str(match.group(2)).strip()
        elif current is not None and line.startswith("        "):
            docs[current] += " " + line.strip()
        elif line.strip():
            break
    return docs


def _ref_name(ref: str) -> str:
    return ref.rsplit("/", 1)[-1]


def _type(spec: dict[str, Any]) -> str:
    """Return a property's JSON type as the page shows it."""
    if "$ref" in spec:
        name = _ref_name(spec["$ref"])
        return "any JSON value" if name == "JsonValue" else f"[{name}](#{name.lower()})"
    if "anyOf" in spec:
        return " or ".join(_type(option) for option in spec["anyOf"])
    if "const" in spec:
        return f'`"{spec["const"]}"`'
    if "enum" in spec:
        return " or ".join(f'`"{value}"`' for value in spec["enum"])
    if spec.get("type") == "array":
        return f"array of {_type(spec['items'])}"
    kind = str(spec.get("type", "any JSON value"))
    if "pattern" in spec:
        kind += f" matching `{spec['pattern']}`"
    return kind


def _default(name: str, spec: dict[str, Any], required: set[str]) -> str:
    if "default" in spec:
        return f"`{json.dumps(spec['default'])}`"
    return "required" if name in required else "—"


def _object_table(name: str, definition: dict[str, Any], level: int) -> list[str]:
    title = " ".join(definition["description"].split("\n\n", 1)[0].split())
    docs = attribute_docs(definition["description"])
    required = set(definition.get("required", ()))
    lines = [f"{'#' * level} {name}", "", title, ""]
    lines += ["| Field | Type | Default | Description |", "|---|---|---|---|"]
    for field, spec in definition["properties"].items():
        description = docs.get(field) or " ".join(spec.get("description", "").split())
        if spec.get("readOnly"):
            description += " Derived on writing; ignored on reading."
        lines.append(f"| `{field}` | {_cell(_type(spec))} | {_default(field, spec, required)} | {_cell(description)} |")
    return [*lines, ""]


def render_report(schema: dict[str, Any], *, level: int = 3) -> str:
    """Return the report's objects and enumerations as Markdown tables.

    Args:
        schema: The published JSON Schema of the report.
        level: The heading level of each object's title.

    Returns:
        The Markdown text.
    """
    definitions: dict[str, Any] = {"TranslationReport": schema, **schema["$defs"]}
    parts: list[str] = [f"{'#' * (level - 1)} Objects", ""]
    for name in _OBJECTS:
        parts += _object_table(name, definitions[name], level)
    parts += [f"{'#' * (level - 1)} Kinds", ""]
    for name, enum in _ENUMS.items():
        listed = definitions[name]["enum"]
        if listed != [member.value for member in enum]:
            msg = f"{name} in {SCHEMA.name} differs from archetypal.umi.report.{name}; regenerate the schema"
            raise ValueError(msg)
        parts += [f"{'#' * level} {name}", "", " ".join(definitions[name]["description"].split()), ""]
        parts += _enum_table(enum, "Value")
    return "\n".join(parts)


def load_schema() -> dict[str, Any]:
    """Return the published JSON Schema of the report."""
    schema: dict[str, Any] = json.loads(SCHEMA.read_text(encoding="utf-8"))
    return schema


def expand(markdown: str) -> str:
    """Replace the placeholder lines of a page with the generated tables.

    Args:
        markdown: The page's Markdown.

    Returns:
        The page with each placeholder replaced, or unchanged without one.
    """
    if CORRESPONDENCE_PLACEHOLDER in markdown:
        markdown = markdown.replace(CORRESPONDENCE_PLACEHOLDER, render_correspondence(CORRESPONDENCE))
    if REPORT_PLACEHOLDER in markdown:
        markdown = markdown.replace(REPORT_PLACEHOLDER, render_report(load_schema()))
    return markdown


def on_page_markdown(markdown: str, **_: Any) -> str:
    """Insert the generated tables into the pages that ask for them (MkDocs event)."""
    return expand(markdown)
