"""Translate UMI template libraries to and from SBEM archetypes (spec 003).

UMI libraries are read and written in the JSON form of Basilisk, the library UMI reads them
with. The format model and the reference handling are private (roadmap C-02).

- `read_umi` reads a library into SBEM archetypes, one per building template, and returns
  them with a `TranslationReport` as a `UmiImport`.
- `to_umi` translates SBEM archetypes (or spec 002's reductions) into one library, returned
  with its report as a `UmiExport`; `write_umi` also writes the library and its loss report.
- `CORRESPONDENCE` is the field-by-field table between UMI and SBEM that drives the
  translation.
"""

from __future__ import annotations

from archetypal.umi.correspondence import CORRESPONDENCE, FieldMapping, MappingStatus, Relevance
from archetypal.umi.read import UmiImport, read_umi
from archetypal.umi.report import Loss, LossKind, Note, NoteKind, TranslationReport
from archetypal.umi.write import UmiExport, to_umi, write_umi

__all__ = [
    "CORRESPONDENCE",
    "FieldMapping",
    "Loss",
    "LossKind",
    "MappingStatus",
    "Note",
    "NoteKind",
    "Relevance",
    "TranslationReport",
    "UmiExport",
    "UmiImport",
    "read_umi",
    "to_umi",
    "write_umi",
]
