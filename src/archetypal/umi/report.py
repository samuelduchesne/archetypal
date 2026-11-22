"""The translation report: what a UMI translation lost, and what it assumed (FR-011, FR-011a).

`TranslationReport` separates **losses** (anything the target does not represent) from
**notes** (assumptions and defaults that lose nothing). Strict mode fails if and only if
`losses` is not empty (`TranslationReport.raise_for_losses`). The report's JSON is
deterministic: losses and notes sorted by subject then location, floats at `repr` precision,
two-space indent and a final newline (FR-012).

Run `python -m archetypal.umi.report --schema [PATH]` to write the published JSON Schema,
by default `docs/schemas/translation-report-1.0.json`.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from enum import Enum
from importlib import metadata
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal, cast

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    JsonValue,
    computed_field,
    field_validator,
    model_validator,
)

from archetypal.errors import LossyTranslationError
from archetypal.umi.correspondence import LIBRARY_RULES, UPSTREAM_ITEMS, rule_ids

if TYPE_CHECKING:
    import os
    from collections.abc import Iterable

    from pydantic import ModelWrapValidatorHandler

if sys.version_info >= (3, 11):
    from enum import StrEnum
else:  # pragma: no cover - Python 3.10 has no StrEnum

    class StrEnum(str, Enum):
        """A `str` enum whose `str()` is its value, as Python 3.11's `enum.StrEnum`."""

        def __str__(self) -> str:
            """Return the member's value."""
            return str(self.value)


__all__ = [
    "NOTHING_LOST",
    "SCHEMA_ID",
    "SCHEMA_PATH",
    "SCHEMA_VERSION",
    "Direction",
    "Findings",
    "Loss",
    "LossKind",
    "Note",
    "NoteKind",
    "SourceInfo",
    "TranslationReport",
    "report_json_schema",
]

SCHEMA_VERSION = "1.0"
"""The version of the report's file format."""

NOTHING_LOST = "Nothing was lost."
"""The summary of a report without losses."""

SCHEMA_PATH = Path("docs/schemas/translation-report-1.0.json")
"""Where the published JSON Schema lives, relative to the repository root."""

SCHEMA_ID = "https://samuelduchesne.github.io/archetypal/schemas/translation-report-1.0.json"
"""The `$id` of the published JSON Schema."""

Direction = Literal["umi_to_sbem", "sbem_to_umi"]
"""Which way a translation went."""

_UPSTREAM_PATTERN = re.compile(r"^UP-\d+$")


class LossKind(StrEnum):
    """What kind of information a translation lost."""

    LOST = "lost"
    """The target has no place for the value."""
    APPROXIMATE = "approximate"
    """The value is represented, but only approximately."""
    MERGED = "merged"
    """Several values became one (zone groups merged into core and perimeter)."""
    COPIED = "copied"
    """A value was copied to a place the source did not define (the perimeter copied to core)."""
    SHARE_DROPPED = "share_dropped"
    """A floor-area share was dropped (UMI has none)."""
    RENAMED = "renamed"
    """A component was renamed to keep names unique."""
    UNUSED = "unused"
    """A component no template uses was not translated."""
    SKIPPED_TEMPLATE = "skipped_template"
    """An invalid template was skipped."""


class NoteKind(StrEnum):
    """What kind of assumption a translation made."""

    DEFAULTED = "defaulted"
    """A field absent from the file took Basilisk's default."""
    ASSUMED = "assumed"
    """An SBEM field that UMI lacks was filled by a stated rule."""
    UNKNOWN_KEY = "unknown_key"
    """The file has a key Basilisk does not know; it was ignored."""


class _Frozen(BaseModel):
    """Base of the report's models: frozen, no unknown fields."""

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)


class SourceInfo(_Frozen):
    """What was translated, and by which versions.

    Attributes:
        path: The library read or written, or `None` when there is no file.
        sha256: The SHA-256 of the library read, or `None` when writing.
        dialect: The UMI dialect read, or `None` when writing.
        archetypal: The version of archetypal.
        epinterface: The version of epinterface.
    """

    path: str | None = None
    sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    dialect: str | None = None
    archetypal: str
    epinterface: str

    @classmethod
    def current(
        cls,
        path: str | os.PathLike[str] | None = None,
        *,
        sha256: str | None = None,
        dialect: str | None = None,
    ) -> SourceInfo:
        """Describe a source with the installed versions of archetypal and epinterface.

        Args:
            path: The library read or written; only its name is kept.
            sha256: The SHA-256 of the library read.
            dialect: The UMI dialect read.
        """
        return cls(
            path=None if path is None else Path(path).name,
            sha256=sha256,
            dialect=dialect,
            archetypal=_version("archetypal"),
            epinterface=_version("epinterface"),
        )


def _version(distribution: str) -> str:
    """Return an installed distribution's version, or `"unknown"`."""
    try:
        return metadata.version(distribution)
    except metadata.PackageNotFoundError:  # pragma: no cover - both are dependencies
        return "unknown"


def _check_upstream(value: str | None) -> str | None:
    """Accept only an upstream item that UMI translation depends on."""
    if value is not None and value not in UPSTREAM_ITEMS:
        msg = f"{value!r} is not one of the upstream items {sorted(UPSTREAM_ITEMS)}"
        raise ValueError(msg)
    return value


class Loss(_Frozen):
    """One piece of information the target does not represent.

    Attributes:
        kind: What kind of loss.
        subject: The template or archetype; `""` for the whole library.
        location: A JSON pointer into the UMI file on the UMI side; on the SBEM side a dotted
            field path prefixed by the group (`perimeter.Operations.HVAC.Ventilation.DCV`) or
            `archetype.`.
        value: The value not represented.
        replacement: What replaced it, if anything.
        rule: The rule of `CORRESPONDENCE`, or a library-level rule (`LIBRARY_RULES`).
        reason: Why it was lost, in one sentence.
        upstream: The upstream item that closes the gap, when the gap is upstream.
    """

    kind: LossKind
    subject: str
    location: str
    value: JsonValue
    replacement: JsonValue = None
    rule: str
    reason: str
    upstream: str | None = Field(default=None, pattern=_UPSTREAM_PATTERN.pattern)

    @field_validator("rule")
    @classmethod
    def _known_rule(cls, value: str) -> str:
        if value not in LIBRARY_RULES and value not in rule_ids():
            msg = f"{value!r} is neither a rule of CORRESPONDENCE nor a library-level rule"
            raise ValueError(msg)
        return value

    @field_validator("upstream")
    @classmethod
    def _known_upstream(cls, value: str | None) -> str | None:
        return _check_upstream(value)


class Note(_Frozen):
    """One assumption or default that loses nothing.

    Attributes:
        kind: What kind of note.
        subject: The template or archetype; `""` for the whole library.
        location: Where, as for `Loss.location`.
        value: The value assumed or defaulted.
        rule: The rule that made the assumption, for example `format.basilisk_default`.
        reason: Why, in one sentence.
    """

    kind: NoteKind
    subject: str
    location: str
    value: JsonValue
    rule: str
    reason: str


def _order(entry: Loss | Note) -> tuple[str, str, str, str, str]:
    """Sort key: subject, then location, then kind, rule and value for a total order."""
    return (entry.subject, entry.location, entry.kind.value, entry.rule, json.dumps(entry.value, sort_keys=True))


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


class TranslationReport(_Frozen):
    """Everything a translation lost, and every assumption it made.

    Losses and notes are kept sorted by subject, then location, whatever order they are given in.
    The summary is derived from the losses.

    Attributes:
        schema_version: The file format's version, `"1.0"`.
        direction: Which way the translation went.
        source: What was translated, and by which versions.
        subjects: The templates read or archetypes written, in order.
        losses: What the target does not represent.
        notes: Assumptions and defaults that lose nothing.
    """

    model_config = ConfigDict(
        title="TranslationReport",
        json_schema_serialization_defaults_required=True,
        json_schema_extra={"$schema": "https://json-schema.org/draft/2020-12/schema", "$id": SCHEMA_ID},
    )

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    direction: Direction
    source: SourceInfo
    subjects: list[str] = Field(default_factory=list[str])
    losses: list[Loss] = Field(default_factory=list[Loss])
    notes: list[Note] = Field(default_factory=list[Note])

    @field_validator("losses")
    @classmethod
    def _sort_losses(cls, value: list[Loss]) -> list[Loss]:
        return sorted(value, key=_order)

    @field_validator("notes")
    @classmethod
    def _sort_notes(cls, value: list[Note]) -> list[Note]:
        return sorted(value, key=_order)

    @model_validator(mode="wrap")
    @classmethod
    def _check_summary(cls, data: Any, handler: ModelWrapValidatorHandler[TranslationReport]) -> TranslationReport:
        """Accept a `summary` key on input only when it matches the losses."""
        given: object = None
        if isinstance(data, dict) and "summary" in data:
            fields: dict[str, Any] = dict(data)  # pyright: ignore[reportUnknownArgumentType]
            given = fields.pop("summary")
            data = fields
        report = handler(data)
        if given is not None and given != report.summary:
            msg = f"summary {given!r} does not match the losses: {report.summary!r}"
            raise ValueError(msg)
        return report

    @computed_field
    @property
    def summary(self) -> str:
        """`"Nothing was lost."` when there are no losses, else the losses counted by kind."""
        if not self.losses:
            return NOTHING_LOST
        counts = Counter(loss.kind for loss in self.losses)
        by_kind = ", ".join(f"{counts[kind]} {kind.value}" for kind in LossKind if counts[kind])
        subjects = {loss.subject for loss in self.losses}
        noun = "template" if self.direction == "umi_to_sbem" else "archetype"
        named = len(subjects - {""})
        places = [_plural(named, noun)] if named else []
        if "" in subjects:
            places.append("the library")
        lost = "value lost" if len(self.losses) == 1 else "values lost"
        return f"{len(self.losses)} {lost} ({by_kind}) in {' and '.join(places)}."

    @property
    def lossless(self) -> bool:
        """Whether nothing was lost (notes do not count)."""
        return not self.losses

    def raise_for_losses(self, subject: str | os.PathLike[str]) -> None:
        """Apply strict mode: raise if and only if something was lost.

        Args:
            subject: The library or archetype being translated, for the error message.

        Raises:
            LossyTranslationError: `losses` is not empty; the error carries this report.
        """
        if self.losses:
            raise LossyTranslationError(subject, self.summary, self)

    def to_json(self) -> str:
        """Return the report as deterministic JSON: two-space indent and a final newline."""
        return json.dumps(self.model_dump(mode="json"), indent=2, ensure_ascii=False, allow_nan=False) + "\n"

    @classmethod
    def from_json(cls, text: str | bytes) -> TranslationReport:
        """Read a report written by `to_json`."""
        return cls.model_validate_json(text)


@dataclass
class Findings:
    """The losses and notes a translation step collects, before they go into a `TranslationReport`.

    Attributes:
        losses: What the target does not represent.
        notes: Assumptions and defaults that lose nothing.
    """

    losses: list[Loss] = field(default_factory=list[Loss])
    notes: list[Note] = field(default_factory=list[Note])

    def lose(
        self,
        kind: LossKind,
        subject: str,
        location: str,
        value: JsonValue,
        rule_id: str,
        reason: str,
        *,
        replacement: JsonValue = None,
        upstream: str | None = None,
    ) -> None:
        """Record a loss."""
        self.losses.append(
            Loss(
                kind=kind,
                subject=subject,
                location=location,
                value=value,
                replacement=replacement,
                rule=rule_id,
                reason=reason,
                upstream=upstream,
            )
        )

    def unset(self, component: object, keys: Iterable[str], subject: str, location: str, rule_id: str) -> None:
        """Note the fields of an SBEM component that are unset (`None`) and that writing fills.

        UMI needs a value where SBEM leaves a field unset, so writing puts Basilisk's default
        there, and reading the library back gives that value instead of `None`. One note at the
        component lists the fields.
        """
        unset = [key for key in keys if getattr(component, key, 0) is None]
        if unset:
            self.notes.append(
                Note(
                    kind=NoteKind.DEFAULTED,
                    subject=subject,
                    location=location,
                    value=cast("JsonValue", unset),
                    rule=rule_id,
                    reason="SBEM leaves these fields unset; UMI needs a value, so Basilisk's default is written",
                )
            )

    def assume(self, subject: str, location: str, value: JsonValue, rule_id: str, reason: str) -> None:
        """Record that a value the source lacks was filled by a stated rule."""
        self.notes.append(
            Note(kind=NoteKind.ASSUMED, subject=subject, location=location, value=value, rule=rule_id, reason=reason)
        )


def report_json_schema() -> dict[str, Any]:
    """Return the JSON Schema of the report file, as published."""
    return TranslationReport.model_json_schema(mode="serialization")


def _schema_text() -> str:
    """Return the published schema's text: two-space indent, ASCII, final newline."""
    return json.dumps(report_json_schema(), indent=2, ensure_ascii=True) + "\n"


def main(argv: list[str] | None = None) -> int:
    """Write the report's JSON Schema (`python -m archetypal.umi.report --schema [PATH]`)."""
    parser = argparse.ArgumentParser(
        prog="python -m archetypal.umi.report", description="Write the translation report's JSON Schema."
    )
    parser.add_argument(
        "--schema",
        nargs="?",
        const=str(SCHEMA_PATH),
        metavar="PATH",
        help=f"write the JSON Schema to PATH (default {SCHEMA_PATH})",
    )
    args = parser.parse_args(argv)
    if args.schema is None:
        parser.print_help()
        return 2
    path = Path(args.schema)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_schema_text(), encoding="utf-8")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
