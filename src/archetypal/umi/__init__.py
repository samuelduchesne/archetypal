"""Translate UMI template libraries to and from SBEM archetypes (spec 003).

UMI libraries are read and written in the JSON form of Basilisk, the library UMI reads them
with. The format model and the reference handling are private (roadmap C-02).

- `read_umi` reads a library into SBEM archetypes, one per building template, and returns
  them with a `TranslationReport` as a `UmiImport`.
- `CORRESPONDENCE` is the field-by-field table between UMI and SBEM that drives the
  translation.
"""

from __future__ import annotations

from archetypal.umi.correspondence import CORRESPONDENCE, FieldMapping, MappingStatus, Relevance
from archetypal.umi.read import UmiImport, read_umi
from archetypal.umi.report import Loss, LossKind, Note, NoteKind, TranslationReport

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
    "UmiImport",
    "read_umi",
]
