# Contract: public Python API for reduction and comparison

These are the public names spec 002 adds to `archetypal`. All are fully typed (pyright
strict) and documented with Google-style docstrings. Spec 001 owns the command line; its
`reduce`, `merge` and `compare` commands are thin wrappers over these functions.

```python
from archetypal import reduce, merge, compare, Layout, ReductionOptions
from archetypal.reduction import RESULTS_REQUIREMENTS, Reduction
from archetypal.comparison import ComparisonResult, AcceptanceTargets
from archetypal.errors import (
    ArchetypalError, ReductionError, NoConditionedZones, MissingResults,
    ModelResultsMismatch, UnsupportedEnergyPlusVersion, NotComparableError,
)
```

## `reduce`

```python
def reduce(
    model: str | os.PathLike[str] | AnyIDFDocument,   # narrowed internally with as_version(since="22.1")
    results: str | os.PathLike[str] | SQLResult | None = None,
    *,
    options: ReductionOptions = ReductionOptions(),
    weather: str | os.PathLike[str] | None = None,
    simulate: bool = False,
    energyplus: EnergyPlusConfig | None = None,
) -> Reduction: ...
```

- **`model`** may be any idfkit document. Reduction narrows it with
  `idfkit.versioned.as_version(doc, since="22.1")`. A document from an older release raises
  `UnsupportedEnergyPlusVersion`, pointing to `idfkit.migration.migrate`.
- **`results`** is the SQLite output of an annual run that meets `RESULTS_REQUIREMENTS`.
- **When `results` is `None` or incomplete:**
  - If `simulate=False`, reduction raises `MissingResults`. The exception lists each missing
    item and how to obtain it.
  - If `simulate=True`, archetypal copies the model, adds the missing outputs, and runs it once
    with `idfkit.simulation.simulate(..., cache=SimulationCache())`. That run needs `weather`.
- **Raises:** `UnsupportedEnergyPlusVersion`, `ModelResultsMismatch`, `NoConditionedZones` and
  `MissingResults`. Each is raised before any work is kept (FR-029).
- **Deterministic:** equal inputs give equal `Reduction`s and byte-identical files (FR-005).

## `Reduction`

```python
@dataclass(frozen=True)
class Reduction:
    archetype: epinterface.sbem.<Archetype>   # the UP-2 multi-group model
    report: ReductionReport

    def write(self, directory: str | os.PathLike[str], name: str, *, overwrite: bool = False) -> tuple[Path, Path]:
        """Write <name>.sbem.json and <name>.report.json; refuse to overwrite unless asked."""

    @classmethod
    def read(cls, archetype_path: str | os.PathLike[str], report_path: str | os.PathLike[str] | None = None) -> Reduction: ...
```

## `merge`

```python
def merge(reduction: Reduction, layout: Layout, *, small_group_threshold: float | None = None) -> Reduction: ...
```

- It uses the report's pre-threshold ledgers.
- It raises `ReductionError` when the target layout is not coarser than or equal to the
  source's, or when the report is missing.
- **Guarantee:** `merge(reduce(m, r, options=o), L)` equals
  `reduce(m, r, options=o.model_copy(update={"layout": L}))`, with parameters within 0.1 %
  (SC-007). Ledgers add exactly, so the result is normally identical.

## `compare`

```python
def compare(
    detailed: str | os.PathLike[str] | SQLResult,
    archetype: str | os.PathLike[str] | SQLResult,
    *,
    targets: AcceptanceTargets = AcceptanceTargets(),
    weather: str | os.PathLike[str] | None = None,
) -> ComparisonResult: ...
```

It raises `NotComparableError` naming every difference in weather, run period, units,
timestep or reporting frequency (FR-028).

## `RESULTS_REQUIREMENTS`

`RESULTS_REQUIREMENTS: tuple[ResultRequirement, ...]` is a constant. It is the single source
for error messages, for the outputs added in the single run, and for
[results-requirements.md](results-requirements.md).

## Stability

These names are public. They become stable under semantic versioning at the first PyPI
release (constitution 1.5.0, VI; roadmap C-18). Until then they may change between milestone
tags, with each change recorded in the changelog. Everything else
in `archetypal.reduction.*` is private: modules not re-exported are prefixed or listed as
internal in the API reference.
