# Contract: the public Python interface, errors and removed names

## Public interface

```python
import archetypal

archetypal.__version__
from archetypal import reduce, merge, compare, Layout, ReductionOptions  # spec 002
from archetypal.errors import (
    ArchetypalError,
    InputError,
    UnsupportedFeatureError,
    LossyTranslationError,
    NotComparableError,
    OptionalDependencyError,
    RemovedInArchetypal3Error,
)
from archetypal import read_umi, write_umi  # spec 003 (R14)
from archetypal.reduction import Reduction, RESULTS_REQUIREMENTS, schedule_compact  # spec 002
from archetypal.comparison import ComparisonResult, AcceptanceTargets  # spec 002
from archetypal.umi import to_umi, UmiImport, UmiExport, TranslationReport  # spec 003, and the rest of its contract
```

The full list is in [../data-model.md](../data-model.md), Public interface. Everything is
typed for pyright strict (FR-009, SC-005) and documented with Google docstrings.

## Errors (FR-010)

The hierarchy of [research R8](../research.md#r8--errors). Every constructor takes the input at
fault first:

```python
class ArchetypalError(Exception):
    def __init__(self, subject: str | os.PathLike[str], message: str) -> None: ...
```

`str(error)` starts with the subject: `"models/office.idf: no conditioned zones"`.

## Removed v2 names (FR-016)

```python
>>> from archetypal import IDF
RemovedInArchetypal3Error: archetypal.IDF was removed in archetypal 3.
Use idfkit.load_idf (idfkit) instead.
See https://samuelduchesne.github.io/archetypal/how-to/migrate-from-v2/#archetypalidf
```

- Raised for every `name` and `module` row of `REMOVED`, by attribute access, `from … import`
  and `import archetypal.<module>`.
- `RemovedInArchetypal3Error` derives from `ArchetypalError`, `ImportError` and
  `AttributeError`, so `except ImportError` in v2-era code still catches it.
- No removed name works as an alias, in any 3.x release.

## Import-time behaviour (FR-006)

`import archetypal` reads no environment variable, creates no file or folder, and adds no
logging handler other than a `NullHandler` on archetypal's own logger.
