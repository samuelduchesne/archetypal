# Implementation Plan: Reduce a detailed EnergyPlus model to an SBEM archetype

**Branch**: `claude/admiring-meitner-1f43qk` (spec 002) | **Date**: 2026-11-21 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/002-reduce-to-sbem/spec.md`

## Summary

Reduction reads a detailed EnergyPlus model and its simulation results and produces one SBEM
archetype plus a reduction report.

**Steps.**

1. **Read.** archetypal reads what EnergyPlus computed (floor areas, multipliers, surfaces,
   U-factors, installed loads, delivered and consumed energy) from the results' SQLite file
   through idfkit. It reads schedules, thermostats, hot water and air-side equipment from the
   model through idfkit's **strongly typed interface**: the document is narrowed to the
   supported releases with `as_version(doc, since="22.1")`, then read with typed accessors
   only, never `get_collection` (research R18).
2. **Group.** It classifies each conditioned zone by exposure and space use, and forms zone
   groups for the chosen layout.
3. **Ledger.** For each group it keeps a **ledger** of conserved totals: areas, UA, heat
   capacity, installed gains, hourly profiles, airflows, hot water, delivered and consumed
   energy by fuel, and fan energy and air volume.
4. **Convert.** It turns each ledger into epinterface SBEM components. Intensity = conserved
   total ÷ basis. Schedules become representative days per month. Envelopes become equivalent
   three-layer constructions.

**Merging.** Merging works on ledgers, so a coarser layout is the same computation whether it
starts from the detailed model or from a finer archetype's report.

**Comparison.** A separate function compares two sets of results (detailed model and
archetype) by end use and peak.

**Tooling.** The project uses the project-kit-cookiecutter template: src layout, uv, ruff,
pyright strict, MkDocs. The unit test tier must finish within two minutes.

All decisions and their evidence are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.10–3.12 (`requires-python = ">=3.10,<3.13"`, bounded by
epinterface; research R15, R17).

**Primary Dependencies**:
- epinterface, from the maintained fork (roadmap C-17): declared as `epinterface>=X` and
  resolved to a fork tag through `[tool.uv.sources]`; SBEM data model, first fork tag with
  UP-1 and UP-2;
- idfkit `>=1.3,<2` (model I/O, schedule evaluation, SQLite and tabular results, single
  simulation run), used through its typed interface only (R18);
- numpy;
- pydantic v2 (research R17).

**Storage**: files only. The archetype is `<name>.sbem.json` (epinterface's pydantic JSON) and
the report is `<name>.report.json` (archetypal's JSON Schema); research R14.

**Testing**: pytest with markers `energyplus` and `reference`; pytest-timeout; hypothesis;
pytest-cov. The unit tier must take ≤ 120 s, enforced by a session hook; research R16.

**Target Platform**: Linux, macOS and Windows; pure Python. EnergyPlus 24.2 is needed only for
the optional single run (FR-002) and the integration and reference tiers.

**Project Type**: Python library (public API). Spec 001 owns the command line that wraps it.

**Performance Goals**:
- reduce the largest reference building in < 10 s excluding simulation (SC-008);
- the whole reference set at least 10× faster than v2.

Internal budget: schedule evaluation ≤ 7 s on the largest model (R5).

**Constraints**:
- deterministic, byte-identical output (FR-005);
- conserved totals within 0.1 % (SC-005);
- no reimplementation of idfkit or epinterface capabilities (constitution I);
- no simulation batches (constitution III).

**Scale/Scope**:
- reference set: 16 DOE commercial prototypes × 3 climate zones + 1 residential prototype,
  i.e. 49 buildings;
- largest model: the hospital and large-office prototypes, with tens of zones and roughly 150
  schedules.

No item is left as NEEDS CLARIFICATION. Every unknown is resolved in research.md: R1–R20, plus
spec feedback F-1 and F-2 (both resolved).

## Constitution Check

*GATE: checked before Phase 0 and re-checked after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| **I. Archetypes, not EnergyPlus** | Model I/O, schedule evaluation, SQLite and tabular parsing, simulation and migration are all idfkit calls, made through its typed interface (R18). The SBEM model and its JSON are epinterface's, from the maintained fork archetypal depends on (constitution 1.5.0, I; roadmap C-17), which carries only changes also offered upstream. Geometry is not recomputed: EnergyPlus's `Zones` and `Surfaces` tables are read (R1). Gaps go upstream: UP-1, UP-2, UP-4, UP-5, UP-6, UP-7, UP-8. There are two temporary bridges, both tracked and removed when their upstream item is released: normalising `Schedule:Year` month and day fields to `int` until UP-6, and typed row wrappers over `SQLResult.query` until UP-7. | Pass (bridges recorded below) |
| **II. One archetype data model** | The output is SBEM only. The ledger is internal working state, not a second archetype model: it is never written as an archetype, and only its totals appear in the report (needed for FR-010 and FR-022). | Pass |
| **III. Small and focused** | Four runtime dependencies, each justified (R17). There is at most one simulation run, on request. No geometry generation (FR-024 carries ratios only). No calibration. | Pass |
| **IV. Physically correct and verifiable** | Each SBEM parameter is tied to a conservation rule (data-model.md, "Derivation rules"). The reference tier measures SC-001–SC-008 against stated targets, including v2's baseline (SC-004). | Pass. Spec feedback F-1 (SC-002 and fan end uses) is resolved by FR-022a and UP-8. |
| **V. What and why before how** | All "how" lives here and in research.md. No v2 code is carried over; v2 is read only to run the SC-004 baseline in a separate environment. | Pass |
| **VI. Dependable public library** | Strict pyright, with unknown-type reports as errors so no untyped idfkit object leaks in, and `idfkit check` (R18); py.typed, ruff with `D` (Google docstrings), public behaviour tested, docs in the same PR (below), Python 3.10–3.12, uv, Keep a Changelog. | Pass |

**Gate result: PASS.** The only exceptions are the temporary bridges for UP-6 and UP-7,
recorded in Complexity Tracking.

### Documentation this plan adds (constitution VI, FR-030)

| Page | Diátaxis kind | Content |
|---|---|---|
| `docs/explanation/reduction.md` | Explanation | What reduction conserves and why: FR-014–FR-024, exposure and space use, representative days, equivalent constructions, what SBEM cannot hold, specific fan power and the temperature-dependent COP. |
| `docs/how-to/reduce-a-model.md` | How-to | Reduce a model with existing results, or with the single run; choose a layout and threshold; supply a space-use mapping. |
| `docs/how-to/merge-an-archetype.md` | How-to | Merge an archetype to a coarser layout. |
| `docs/how-to/compare-results.md` | How-to | Compare detailed and archetype results. |
| `docs/reference/reduction-report.md` | Reference | Every field of the report, generated from its JSON Schema. |
| `docs/reference/results-requirements.md` | Reference | The EnergyPlus outputs reduction needs, generated from `RESULTS_REQUIREMENTS`. |
| `docs/reference/api/reduction.md` | Reference | mkdocstrings page for `archetypal.reduction` and `archetypal.comparison`. |

Every code example in these pages runs in CI against the unit fixtures (docs-test job).

## Upstream dependencies (constitution: Development Workflow)

Spec 002 cannot be marked implemented until the blocking items are released. The main
epinterface repository is not expected to accept our pull requests for a long time, so every
epinterface item is built and released in the SBEM fork (roadmap C-17) and offered upstream
as a pull request. "Released" below means released by the fork; the upstream merge is not a
dependency. A fork release is a git tag; the fork is not published on PyPI. This changes who
releases, not what 002 needs, so no blocking status changes, except UP-3, which now gates
only v3's PyPI release.

"Blocking" follows roadmap C-20: 002 is marked implemented only when every item marked yes
(bridged or not) is released. Items marked "not a dependency" never hold 002 back.

| Item | Repository | What | Blocks "implemented"? |
|---|---|---|---|
| UP-1 | epinterface | Depend on idfkit instead of `archetypal==2.18.10`. `sbem.components` must be importable without archetypal, eppy or a generated Prisma client, and PyYAML must be declared. | Yes |
| UP-2 | epinterface | Several zone groups per archetype. It also adds these fields, which this plan's research showed are missing: per-orientation envelope and window ratios (FR-024), an infiltration schedule (FR-018), numeric heat-recovery effectiveness, sensible and latent (FR-019; spec 003 maps both), holiday and design-day slots in `WeekComponent` (FR-023), and save/load helpers with a schema version (R14). | Zone groups: yes. Each extra field: not a dependency (until it lands, its loss is reported under FR-026). Unset floor-area shares (spec 003): not a dependency; 002 always sets shares. |
| UP-3 | epinterface | Upstream releases on PyPI what archetypal uses (UP-1 and the SBEM fields). The fork is not published (C-17). | Not a dependency; it gates only v3's PyPI release (C-18) |
| UP-4 | epinterface | Heavy dependencies become optional (Prisma, geopandas, ladybug), and exact pins are loosened (`click==8.1.7`, `pandas<2.3`). | Not a dependency (install size and conflicts) |
| UP-5 | idfkit | Day-type-aware `Schedule:Compact` creation. Now also a faster day-profile evaluation if the R5 benchmark fails. | Not a dependency |
| UP-6 (new) | idfkit | Fix `Schedule:Year` evaluation on loaded models (`int('1.0')` in `schedules/year.py`) before 1.3.0 final, so the typed `schedule_weeks[i].start_month: int` really is an `int`. | Yes; bridged meanwhile |
| UP-7 (new) | idfkit | Typed readers for EnergyPlus's static SQLite tables (`Zones`, `Surfaces`, `Constructions`, `ConstructionLayers`, `Materials`, `Nominal*`), in place of raw `SQLResult.query` rows. | Yes; bridged by `_sql_tables.py` meanwhile |
| UP-8 (new) | epinterface | SBEM energy conversion beyond a constant COP, still on ideal loads: a specific fan power and ideal-loads supply-air temperature limits, with fans reported as their own end use; and a COP that depends on outdoor temperature (R12, R19). | Yes (SC-002's fan target). Reduction is built without it: fans are folded into `DistributionCOP` and reported as not represented until it lands. |

The roadmap is updated with UP-6, UP-7 and UP-8 and the broader UP-2 and UP-5 scope. UP-3 is
open: it gates only v3's PyPI release (roadmap C-18).

## Project Structure

### Documentation (this feature)

```text
specs/002-reduce-to-sbem/
├── plan.md              # This file
├── research.md          # Phase 0: decisions R1–R20, spec feedback F-1 and F-2 (resolved)
├── data-model.md        # Phase 1: entities, ledger, derivation rules, pipeline states
├── quickstart.md        # Phase 1: validation scenarios
├── contracts/
│   ├── python-api.md          # public functions and types
│   ├── reduction-report.md    # report file contract (fields, invariants)
│   └── results-requirements.md# EnergyPlus outputs reduction needs
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root, `v3` line)

```text
src/archetypal/
├── __init__.py              # public re-exports: reduce, merge, compare, Layout, ReductionOptions, errors
├── py.typed
├── errors.py                # 001's hierarchy (001 R8), extended: ReductionError (NoConditionedZones, MissingResults,
│                            #   ModelResultsMismatch, UnsupportedEnergyPlusVersion), NotComparableError
├── io.py                    # write/read <name>.sbem.json and <name>.report.json (deterministic JSON)
├── reduction/
│   ├── __init__.py          # reduce(), merge(), Layout, ReductionOptions, RESULTS_REQUIREMENTS
│   ├── options.py           # Layout enum, ReductionOptions (threshold, mapping, layout)
│   ├── requirements.py      # RESULTS_REQUIREMENTS; check results; add outputs and run once via idfkit
│   ├── sources.py           # SourceData: as_version(doc, since="22.1") + SQLResult; version and model/results matching
│   ├── _sql_tables.py       # typed frozen rows over SQLResult.query (bridge until UP-7); the only caller of query()
│   ├── inventory.py         # ZoneRecord per zone from the Zones, Surfaces and Nominal* tables
│   ├── classify.py          # exposure (R7), conditioned/attic/basement (R8), space use (R4)
│   ├── grouping.py          # layouts, small-group threshold, merge plan (FR-008–FR-011)
│   ├── ledger.py            # GroupLedger: conserved totals; add/merge (associative, commutative)
│   ├── schedules.py         # typed AnySchedule index from per-type accessors; evaluation via idfkit (memoised),
│   │                        #   projection, Schedule:Compact text (R5, R18)
│   ├── envelope.py          # surface classes, UA, capacity, equivalent constructions (R6)
│   ├── airflow.py           # infiltration, outdoor air, HRV/economiser (R9)
│   ├── thermostats.py       # FR-020 (R10)
│   ├── hotwater.py          # FR-021 (R11)
│   ├── efficiency.py        # FR-022: seasonal COP, outdoor-temperature slope (R12)
│   ├── fans.py              # FR-022a: specific fan power, supply-air temperatures (R19)
│   ├── features.py          # FR-026: UNSUPPORTED_FEATURES table, read by literal keys (R20)
│   ├── to_sbem.py           # ledger → epinterface components (one function per SBEM component)
│   ├── report.py            # ReductionReport pydantic models, JSON Schema
│   └── _bridges.py          # temporary upstream bridges (UP-6), each with its removal condition
└── comparison/
    ├── __init__.py          # compare(), ComparisonResult, AcceptanceTargets
    └── results.py           # end uses, peaks, comparability checks (R13)

tests/
├── conftest.py              # markers, 120 s session budget hook, hypothesis profiles
├── fixtures/
│   ├── models/              # three_zone, ten_zone_multipliers, ten_zone_explicit, bar_building
│   │                        #   (.idf + .sql results, R2 outputs only)
│   └── regenerate.py        # rebuild fixture results (needs EnergyPlus; not run in the unit tier)
├── unit/                    # default tier: one module per source module, plus property tests
├── integration/             # @pytest.mark.energyplus: single-run path, epinterface builds the archetype
└── reference/               # @pytest.mark.reference: SC-001–SC-008 on the reference set

verification/
├── reference_set.toml       # prototype list, climate zones, download URLs and SHA-256
├── run_v2_baseline.py       # SC-004 baseline, run in a separate env with archetypal<3
└── report.py                # tabulates SC-001–SC-008 evidence for the docs

docs/
├── explanation/reduction.md
├── how-to/{reduce-a-model,merge-an-archetype,compare-results}.md
└── reference/{reduction-report,results-requirements}.md, reference/api/reduction.md
```

**Structure decision.** This is a single library in src layout, generated from the
project-kit-cookiecutter template by `/project-kit:new-project` and linked with cruft (spec
001, research R1). The `reduction` and
`comparison` subpackages keep the public surface small; the internal modules mirror the
spec's requirement groups, so each FR has one home. `verification/` sits outside the package
because it is project evidence, not library code. The v2 tree moves to `v2.x`; spec 001 owns that
move, the shared tooling and the command line.

### Tooling configuration

The project, its layout and its shared tooling come from spec 001's plan (roadmap C-19; 001
research R1–R5, R9): generated with `/project-kit:new-project`, strict pyright with unknown
types as errors, ruff with docstrings, three test tiers with a two-minute unit budget, CI on
Linux, macOS and Windows, milestones as pre-releases that skip the publish job. Agents load
`/idfkit:developing-with-idfkit` before writing code that imports idfkit, and write docs pages
with `/project-kit:diataxis`.

002 adds (R15, R16, R18):

- **`[tool.idfkit.check]`:** `paths = ["src"]`, `since = "22.1"`, `extend-select = ["C004"]`,
  `fail-on = "warning"`, run by `make check` and a local pre-commit hook.
- **`.pre-commit-config.yaml`:** a `pygrep` hook banning `get_collection`, `.collections`,
  `objects_by_type`, `get_referenced_object`, `schedules_dict` and `get_zone_surfaces` under
  `src/`.
- **CI:**
  - an `integration` job (EnergyPlus 24.2, Python 3.12, `-m energyplus`) on pull requests;
  - `reference.yml` (weekly, `workflow_dispatch` and milestone tags), running
    `-m reference`;
  - unit tests against the SBEM fork's development branch, required, and a weekly job against
    upstream epinterface's `main`, allowed to fail but reported (roadmap C-14).
- **Releases** (roadmap C-18): 002 ends in milestone M1, cut once 001–003 are verified.

## Complexity Tracking

| Exception | Why needed | Simpler alternative rejected because |
|---|---|---|
| Temporary bridge `_sql_tables.py` (typed frozen rows over `SQLResult.query` for the static tables) | idfkit has no typed reader for these tables, and R1 depends on them. | Calling `query` throughout the code spreads untyped `tuple[object, ...]` rows and breaks R18. Reading loads from the model instead loses multipliers and normalisation (R1). The wrapper is one module, removed when UP-7 is released. |
| Temporary bridge `_bridges.normalise_schedule_year` (normalises a copy of `Schedule:Year` month and day fields to `int` before idfkit evaluates it) | idfkit 1.3.0rc2 fails on every `Schedule:Year` loaded from an EnergyPlus 9.0–22.1 file (research finding 5). Reduction must handle them; the prototypes use them. | Writing our own `Schedule:Year` evaluator duplicates idfkit (constitution I). Waiting for the fix blocks all development. The bridge is a few lines, tested, and removed when UP-6 is released (a test fails once idfkit's version includes the fix, as a reminder). |
