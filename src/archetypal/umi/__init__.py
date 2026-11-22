"""Translate UMI template libraries to and from SBEM archetypes (spec 003).

UMI libraries are read and written in the JSON form of Basilisk, the library UMI reads them
with. The format model and the reference handling are private (roadmap C-02).

- `read_umi` reads a library into SBEM archetypes, one per building template, and returns
  them with a `TranslationReport` as a `UmiImport`.
- `to_umi` translates SBEM archetypes (or spec 002's reductions) into one library, returned
  with its report as a `UmiExport`; `write_umi` also writes the library and its loss report.
- `diff_umi` compares two libraries field by field, and `diff_archetypes` two SBEM
  archetypes: the round-trip check of US3. Every difference carries its location, relevance,
  both values and its relative size.
- `CORRESPONDENCE` is the field-by-field table between UMI and SBEM that drives the
  translation.

Errors are in `archetypal.errors`: `UmiFormatError`, `UmiValidationError` and
`LossyTranslationError` (strict mode).
"""

from __future__ import annotations

from archetypal.umi.correspondence import CORRESPONDENCE, FieldMapping, MappingStatus, Relevance
from archetypal.umi.diff import ArchetypeDiff, UmiDiff, diff_archetypes, diff_umi
from archetypal.umi.read import UmiImport, read_umi
from archetypal.umi.report import Loss, LossKind, Note, NoteKind, TranslationReport
from archetypal.umi.write import UmiExport, to_umi, write_umi

__all__ = [
    "CORRESPONDENCE",
    "ArchetypeDiff",
    "FieldMapping",
    "Loss",
    "LossKind",
    "MappingStatus",
    "Note",
    "NoteKind",
    "Relevance",
    "TranslationReport",
    "UmiDiff",
    "UmiExport",
    "UmiImport",
    "diff_archetypes",
    "diff_umi",
    "read_umi",
    "to_umi",
    "write_umi",
]
