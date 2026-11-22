# Data model: archetypal 3 foundation and migration from v2

**Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

Spec 001 holds no physics. Its entities describe the package's surface, the record of what v2
had, and the documentation's structure. The archetype, reports and ledgers are spec 002's
(see [its data model](../002-reduce-to-sbem/data-model.md)) and spec 003's.

## RemovedCapability

One row per public v2 name, module, command or option that archetypal 3 does not provide
(FR-016, FR-017, R7). The table `REMOVED` in `src/archetypal/_removed.py` is the only source:
import errors, rejected options, the migration guide's table and `docs/reference/removed.md`
are generated from it.

| Field | Type | Rule |
|---|---|---|
| `kind` | `Literal["name", "module", "command", "option"]` | |
| `v2_path` | `str` | As a v2 user writes it: `archetypal.IDF`, `archetypal.idfclass`, `archetypal transition`, `archetypal reduce --all_zones`. Unique. |
| `replacement` | `Replacement \| None` | `None` only when `reason` says why there is none. |
| `reason` | `str` | Always set: why it was removed, in one sentence. |
| `frequent_task` | `FrequentTask \| None` | Links the row to a before/after example (FR-018). |

`Replacement`: `package` (`Literal["archetypal", "idfkit", "epinterface"]`), `target` (the
name, module or command to use), `docs_url` (the page that documents it).

`FrequentTask` (FR-018): `reduce-to-umi`, `edit-umi-library`, `open-and-simulate`,
`read-results`, `upgrade-version`, `evaluate-schedule`.

**Validation (unit tests).**

- Every entry of `tests/data/v2_surface.json` is either in `REMOVED` or in the v3 public
  interface (SC-003).
- Every `module` row has a stub module that raises; every `name` row raises through
  `archetypal.__getattr__`; every `command` and `option` row is rejected by the command line
  (SC-007).
- Every `FrequentTask` has exactly one before/after example in the migration guide, and its
  "after" block runs (FR-018, SC-004).

## V2Surface

The committed inventory `tests/data/v2_surface.json`, written by `verification/v2_surface.py`
in an environment with `archetypal==2.18.11` (R7).

| Field | Type |
|---|---|
| `archetypal_version` | `str` (`"2.18.11"`) |
| `modules` | `list[str]`, public modules |
| `names` | `list[str]`, `module.name` for each public name a module defines or lists in `__all__` |
| `commands` | `list[str]` |
| `options` | `list[str]`, `command --long-name` with short aliases |

Regenerated only by the script; a test checks the file's `archetypal_version`.

## ExitStatus

The command line's exit statuses (FR-014, R6).

| Value | Name | When |
|---|---|---|
| 0 | `SUCCESS` | Every model processed; no loss or approximation reported. |
| 1 | `FAILURE` | Nothing written: invalid input, every model failed, or an unexpected error. |
| 2 | `USAGE` | click's usage errors, including a removed v2 option or command (FR-013). |
| 3 | `PARTIAL_FAILURE` | Some models failed; the output holds the others, and the summary and reports name the failures. |
| 4 | `SUCCESS_WITH_LOSSES` | Every model processed; at least one loss or approximation reported (002 `not_represented`, 003 loss report). |

When both 3 and 4 apply, 3 wins: a failure matters more than a loss.

## RunSummary

What a command prints to stderr after its work (FR-014). Built from the reports, never stored.

| Field | Type |
|---|---|
| `models_ok`, `models_failed` | `int` |
| `failures` | `list[(model path, error class, message)]` |
| `losses`, `approximations` | `int`, from the reports |
| `outputs`, `reports` | `list[Path]` |
| `status` | `ExitStatus` |

## DocsPage

Every Markdown file under `docs/` (FR-022, SC-008, R5).

| Field | Type | Rule |
|---|---|---|
| `path` | `Path` | Under `docs/`. |
| `diataxis` | `Literal["tutorial", "how-to", "reference", "explanation"]` | Front matter; exactly one. |
| folder | — | `tutorials/`, `how-to/`, `reference/`, `explanation/` must match `diataxis`; `docs/index.md` is exempt and tagged `explanation`. |
| examples | — | Python blocks run by `pytest-markdown-docs`; `console` blocks run by `tests/docs/` (FR-024). A block that must not run is fenced `text`, never silently skipped. |

## Public interface

The names and commands documented in the reference (FR-007). At M1:

- **From 002:** `reduce`, `merge`, `compare`, `Layout`, `ReductionOptions`, `Reduction`,
  `ComparisonResult`, `AcceptanceTargets`, `RESULTS_REQUIREMENTS`.
- **From 003:** the UMI read and write functions and the loss report (names from 003's plan,
  R14).
- **From 001:** the errors of R8; `__version__`.
- **Commands:** `archetypal reduce`, `merge`, `compare`, `translate`.

Everything else is private: modules prefixed with `_`, or listed as internal in the API
reference. The interface may change between milestones, with a changelog entry; it is stable
from v3.0.0 (constitution VI, C-18).
