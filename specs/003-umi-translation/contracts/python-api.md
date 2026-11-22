# Contract: public Python interface for UMI translation

The names spec 003 adds. They are fully typed (pyright strict) and documented with Google
docstrings. Spec 001's `translate` command and `reduce --to umi` are thin wrappers over them
(001 research R14).

```python
from archetypal import read_umi, write_umi
from archetypal.umi import (
    to_umi,
    UmiImport,
    UmiExport,
    TranslationReport,
    Loss,
    LossKind,
    Note,
    NoteKind,
    diff_umi,
    diff_archetypes,
    UmiDiff,
    ArchetypeDiff,
    CORRESPONDENCE,
    FieldMapping,
    Relevance,
    MappingStatus,
)
from archetypal.errors import UmiFormatError, UmiValidationError, LossyTranslationError
```

## `read_umi`

```python
def read_umi(
    path: str | os.PathLike[str],
    *,
    strict: bool = False,
    skip_invalid_templates: bool = False,
) -> UmiImport: ...
```

- **Returns** one archetype per building template, in template order, each with core and
  perimeter groups and unset shares (research R4), plus the loss report.
- **Raises:**
  - `UmiFormatError` for a refused dialect or a broken reference;
  - `UmiValidationError` listing every completeness and range problem with its JSON pointer,
    unless `skip_invalid_templates` is set (then affected templates are skipped and reported);
  - `LossyTranslationError` in strict mode when `losses` is not empty.
- **Never writes files.** `UmiImport.write(directory)` does.
- A library with no templates returns no archetypes. Its report lists every component as
  unused and says no template was found.

## `write_umi` and `to_umi`

```python
ArchetypeLike = Reduction | Archetype  # Reduction from spec 002; Archetype = UP-2 model


def to_umi(archetypes: Sequence[ArchetypeLike], *, strict: bool = False) -> UmiExport: ...


def write_umi(
    archetypes: Sequence[ArchetypeLike],
    path: str | os.PathLike[str],
    *,
    strict: bool = False,
    overwrite: bool = False,
) -> TranslationReport: ...
```

- **One building template per archetype**, named after the archetype. Duplicate names get
  ` #2`, … and are reported.
- **Layouts other than core/perimeter** are merged first: exactly through 002's `merge` for a
  `Reduction`, approximately for a bare archetype (research R12).
- **`write_umi`** writes the library at `path` and `<stem>.loss.json` beside it, and returns
  the report. It refuses existing files unless `overwrite`.
- **Raises:**
  - `InputError` for an empty sequence, or for an archetype with more than two groups and
    unset shares;
  - `LossyTranslationError` in strict mode, with nothing written.
- **Deterministic:** equal inputs give byte-identical files (FR-012).

## `diff_umi` and `diff_archetypes`

```python
def diff_umi(original: str | os.PathLike[str], result: str | os.PathLike[str], *, rel_tol: float = 1e-4) -> UmiDiff: ...
def diff_archetypes(a: Archetype, b: Archetype, *, rel_tol: float = 0.0) -> ArchetypeDiff: ...
```

These compare field by field after resolving references, and are used for round trips (US3).
They raise `UmiFormatError` when either library cannot be read.

## Guarantees tested

| Guarantee | Spec |
|---|---|
| `read_umi` on every test-set library succeeds; every archetype validates as epinterface's model | SC-001 |
| Every written library passes `tools/basilisk-check` | SC-002 |
| `diff_umi(lib, write(read(lib)))` has no `S` difference above 0.01 % that is not in the reports | SC-003 |
| `diff_archetypes(a, read(write(a)))` is empty apart from reported losses (core/perimeter archetypes) | SC-004 |
| Every Basilisk field is in `CORRESPONDENCE` | SC-005 |
| Every difference found by the audit is in a report | SC-006 |
| Strict mode fails if and only if `losses` is not empty | SC-006a |
| 100 templates read and written in under 5 s | SC-007 |
