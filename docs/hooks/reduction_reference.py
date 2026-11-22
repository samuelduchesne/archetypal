"""MkDocs hook: generate the reduction reference pages (spec 002 T066, FR-002, FR-025, FR-030).

Two reference pages hold a placeholder line that this hook replaces at build time, so neither
page mirrors its source by hand (contracts/docs-site.md, rule 3):

- `reference/reduction-report.md` (`REPORT_PLACEHOLDER`): one table per object of the report,
  generated from `archetypal.reduction.report.report_json_schema()`, and the rule ids from
  `RULE_IDS`, and the schema's `$id` (`SCHEMA_ID_PLACEHOLDER`);
- `reference/results-requirements.md` (`REQUIREMENTS_PLACEHOLDER`): the output variables and
  meters, generated from `archetypal.reduction.RESULTS_REQUIREMENTS`.

Field descriptions come from the `Attributes:` section of each model's docstring, which the
JSON Schema carries as the object's description.
"""

from __future__ import annotations

import re
from typing import Any

from archetypal.reduction import RESULTS_REQUIREMENTS
from archetypal.reduction.report import RULE_IDS, SCHEMA_ID, report_json_schema

REPORT_PLACEHOLDER = "<!-- reduction-report-schema -->"
REQUIREMENTS_PLACEHOLDER = "<!-- results-requirements -->"
SCHEMA_ID_PLACEHOLDER = "<!-- reduction-report-schema-id -->"

_ROOT = "ReductionReport"
_ATTRIBUTE = re.compile(r"^    (\w+): (.*)$")


def _cell(text: str) -> str:
    """Return text safe inside a Markdown table cell."""
    return text.replace("|", "&#124;").replace("\n", " ")


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


def _summary(description: str) -> str:
    """Return the first paragraph of a docstring, on one line."""
    return " ".join(description.split("\n\n", 1)[0].split())


def _anchor(name: str) -> str:
    return name.lower()


def _type(spec: dict[str, Any], inline: dict[str, dict[str, Any]]) -> str:  # noqa: PLR0911 - one branch per JSON Schema form
    """Return a property's JSON type as the page shows it.

    Objects defined inline (without a `$ref`) and carrying a title are collected in `inline`
    so that they get their own table.
    """
    if "$ref" in spec:
        name = spec["$ref"].rsplit("/", 1)[-1]
        return "any JSON value" if name == "JsonValue" else f"[{name}](#{_anchor(name)})"
    if "anyOf" in spec:
        return " or ".join(_type(option, inline) for option in spec["anyOf"])
    if "const" in spec:
        return f'`"{spec["const"]}"`'
    if "enum" in spec:
        return " or ".join(f'`"{value}"`' for value in spec["enum"])
    kind = spec.get("type")
    if kind == "array":
        return f"array of {_type(spec['items'], inline)}"
    if kind == "object" and "properties" in spec and "title" in spec:
        inline.setdefault(spec["title"], spec)
        return f"[{spec['title']}](#{_anchor(spec['title'])})"
    if kind == "object" and isinstance(spec.get("additionalProperties"), dict):
        keys = spec.get("propertyNames", {}).get("enum")
        key_text = " or ".join(f'`"{k}"`' for k in keys) if keys else "string"
        return f"object from {key_text} to {_type(spec['additionalProperties'], inline)}"
    if kind is None:
        return "any JSON value"
    text = str(kind)
    if "pattern" in spec:
        text += f" matching `{spec['pattern']}`"
    return text


def _default(name: str, spec: dict[str, Any], required: set[str]) -> str:
    import json  # noqa: PLC0415 - only for defaults

    if "default" in spec:
        return f"`{json.dumps(spec['default'])}`"
    return "required" if name in required else "—"


def _object_table(name: str, definition: dict[str, Any], level: int, inline: dict[str, dict[str, Any]]) -> list[str]:
    description = definition.get("description", "")
    docs = attribute_docs(description)
    required = set(definition.get("required", ()))
    lines = [f"{'#' * level} {name}", "", _summary(description), ""]
    lines += ["| Field | Type | Default | Description |", "|---|---|---|---|"]
    for field, spec in definition["properties"].items():
        text = docs.get(field) or " ".join(spec.get("description", "").split())
        lines.append(
            f"| `{field}` | {_cell(_type(spec, inline))} | {_default(field, spec, required)} | {_cell(text)} |"
        )
    return [*lines, ""]


def render_report(schema: dict[str, Any], *, level: int = 3) -> str:
    """Return the report's objects, enumerations and rule ids as Markdown.

    Args:
        schema: The report's JSON Schema, as `report_json_schema()` returns it.
        level: The heading level of each object's title.

    Returns:
        The Markdown text.
    """
    definitions: dict[str, Any] = {_ROOT: schema, **schema["$defs"]}
    objects = [_ROOT, *sorted(n for n, d in schema["$defs"].items() if "properties" in d)]
    enums = sorted(n for n, d in schema["$defs"].items() if "enum" in d)
    inline: dict[str, dict[str, Any]] = {}
    parts: list[str] = [f"{'#' * (level - 1)} Objects", ""]
    for name in objects:
        parts += _object_table(name, definitions[name], level, inline)
    for name in sorted(set(inline) - set(objects)):
        parts += _object_table(name, inline[name], level, inline)
    parts += [f"{'#' * (level - 1)} Enumerations", ""]
    for name in enums:
        values = ", ".join(f'`"{v}"`' for v in definitions[name]["enum"])
        parts += [f"{'#' * level} {name}", "", _summary(definitions[name].get("description", "")), "", values, ""]
    parts += [
        f"{'#' * (level - 1)} Rule ids",
        "",
        "Every entry of `parameters` names one of these rules:",
        "",
        *(f"- `{rule}`" for rule in sorted(RULE_IDS)),
        "",
    ]
    return "\n".join(parts)


def render_requirements() -> str:
    """Return `RESULTS_REQUIREMENTS` as a Markdown table, with the output object to add."""
    rows = [
        f"| `{r.item}` | {r.kind} | {_cell(r.key)} | {r.frequency} | {_cell(r.used_for)} | `{_cell(r.idf_text)}` |"
        for r in RESULTS_REQUIREMENTS
    ]
    header = ["| Item | Kind | Key | Frequency | Used for | Output object |", "|---|---|---|---|---|---|"]
    return "\n".join([*header, *rows, ""])


def expand(markdown: str) -> str:
    """Replace the placeholder lines of a page with the generated tables.

    Args:
        markdown: The page's Markdown.

    Returns:
        The page with each placeholder replaced, or unchanged without one.
    """
    if REPORT_PLACEHOLDER in markdown:
        markdown = markdown.replace(REPORT_PLACEHOLDER, render_report(report_json_schema()))
    if REQUIREMENTS_PLACEHOLDER in markdown:
        markdown = markdown.replace(REQUIREMENTS_PLACEHOLDER, render_requirements())
    return markdown.replace(SCHEMA_ID_PLACEHOLDER, f"`{SCHEMA_ID}`")


def on_page_markdown(markdown: str, **_: Any) -> str:
    """Insert the generated tables into the pages that ask for them (MkDocs event)."""
    return expand(markdown)
