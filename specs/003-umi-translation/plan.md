# Implementation Plan: Translate UMI template libraries to and from SBEM

**Branch**: `claude/admiring-meitner-1f43qk` (spec 003) | **Date**: 2026-11-22 |
**Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/003-umi-translation/spec.md`

## Summary

The translator moves archetypes between UMI template libraries (Basilisk's JSON) and SBEM
archetypes, in both directions, with a loss report for each translation.

**Reading** (UMI → SBEM):

1. Identify the dialect from the file's shape. UMI libraries have no version number.
2. Resolve `$id`/`$ref` in two passes, rejecting dangling and forward references, which
   Basilisk silently turns into `null`.
3. Validate everything, collecting every problem.
4. Turn each building template into one archetype with `core` and `perimeter` groups whose
   floor-area shares are unset, because the building's geometry sets them, as in UMI.

**Writing** (SBEM → UMI):

1. Merge any other layout to core/perimeter: exactly through 002's `merge` when the reduction
   is available, approximately (and reported) when it is not.
2. Convert each archetype to UMI components.
3. Share equal components and rename clashing names.
4. Serialise in Basilisk's own order, with `$id`s numbered in document order, never rounding.

**Correspondence.** One table, `CORRESPONDENCE`, lists every Basilisk field with its SBEM
counterpart, conversion rule, conserved quantity and status. It drives the code (rules are
registered by id), the coverage test against Basilisk's own field list, and the published
reference page.

**The upstream gap.** The research found that SBEM lacks about a third of UMI's
simulation-relevant fields: window settings, layered windows, partition ratio,
natural-ventilation limits, scheduled ventilation, conditioning limits and availability,
daylighting, adiabatic flags, and archetype metadata. They become **UP-9** in the SBEM fork
(roadmap C-13). Until each lands, every read reports it as lost. Converting simple glazing to
an equivalent UMI glass layer uses EnergyPlus's simple-glazing model, requested from idfkit as
**UP-10** and bridged meanwhile.

**Checks.** Every written library is loaded by Basilisk's own code in CI (a small .NET harness
that adds the reference checks Basilisk lacks). A field-by-field audit proves that no loss
goes unreported.

All decisions and their evidence are in [research.md](research.md).

## Technical Context

**Language/Version**: Python 3.10–3.12 (001 research R9). C# / .NET 8 for the CI-only
Basilisk harness (research R15).

**Primary Dependencies** (none new; 002 research R17):
- epinterface, from the SBEM fork with UP-2, and UP-9 for full fidelity;
- pydantic v2 (the private UMI format model, the report);
- numpy (schedule evaluation and projection, reused from 002);
- idfkit `>=1.3,<2`, for `idfkit.thermal` window properties only (research R8), through its
  typed interface.

**Storage**: files only.
- Reading: a UMI library JSON in; `<name>.sbem.json` per template and
  `<library>.loss.json` out.
- Writing: archetypes in; `<library>.json` and `<library>.loss.json` out.

**Testing**: pytest tiers from 001 (research R3). Unit tier ≤ 120 s, including the audit on
fixtures and the performance test. A `reference` marker covers 002's 49 buildings. A
`basilisk` CI job runs the .NET harness. Hypothesis property tests cover the inverse rules.

**Target Platform**: Linux, macOS and Windows; pure Python. The Basilisk harness runs on
Ubuntu CI only.

**Project Type**: Python library (public API). Spec 001 owns the `translate` command and
`reduce --to umi`.

**Performance Goals**: read or write 100 templates in < 5 s (SC-007), with an internal budget
of 3 s. A library is parsed once; schedules are evaluated only for misaligned year parts.

**Constraints**:
- deterministic, byte-identical output (FR-012);
- no rounding on write;
- no unreported difference (SC-006);
- no UMI object model exposed (roadmap C-02);
- no reimplementation of idfkit or epinterface (constitution I);
- .NET never a package dependency (constitution III).

**Scale/Scope**:
- 17 UMI collections, 20 classes, about 200 serialised fields;
- UMI test set: 3 sample libraries, about 10 edge-case fixtures, and 49 libraries written
  from 002's reference set.

No item is left as NEEDS CLARIFICATION. Every unknown is resolved in research.md: R1–R19,
plus spec feedback F-1 to F-5 for `/speckit-analyze`.

## Constitution Check

*GATE: checked before Phase 0 and re-checked after Phase 1 design.*

| Principle | Check | Status |
|---|---|---|
| **I. Archetypes, not EnergyPlus** | Window U, SHGC and VT come from `idfkit.thermal` (R8). Schedule projection reuses 002's module, which evaluates through idfkit. Every SBEM gap is closed upstream: UP-2 (unset shares, heat-recovery effectiveness), UP-9 (UMI fields, two epinterface defects) and UP-10 (idfkit's simple-glazing equivalent layer). One temporary bridge, `_bridges.equivalent_glazing_layer`, is tracked against UP-10 and removed when it is released. | Pass (bridge recorded below) |
| **II. One archetype data model** | SBEM is the only archetype model. The pydantic models of Basilisk's classes are a private parsing and serialising layer: never returned, never edited, never stored (roadmap C-02). Every translation states what it loses (`TranslationReport`), and the audit (R16) proves a round trip reproduces its input or reports each difference. | Pass |
| **III. Small and focused** | No new runtime dependency. .NET is used only by a CI tool outside the package. | Pass |
| **IV. Physically correct and verifiable** | Every conversion rule names what it conserves (data-model, conversion rules): annual hot-water volume, consumed energy, carbon per volume, monthly schedule sums, window properties. They are verified on the UMI test set and 002's reference set against SC-001–SC-007. | Pass. SC-003 needs UP-9's `S` fields (spec feedback F-5). |
| **V. What and why before how** | All "how" is here and in research.md. v2's UMI classes are read as evidence only; their rounding and week alignment are explicitly not kept (R7, R13). | Pass |
| **VI. Dependable public library** | Typed public API (contracts/python-api.md), Google docstrings, the published report schema and correspondence page generated from code, docs in the same pull request (below). | Pass |

**Gate result: PASS.** The one exception is the UP-10 bridge, recorded in Complexity Tracking.

### Documentation this plan adds (constitution VI, FR-013)

Written with `/project-kit:diataxis` (roadmap C-19). Each section's index lists its pages.

| Page | Diátaxis kind | Content |
|---|---|---|
| `docs/how-to/read-a-umi-library.md` | How-to | Read a library, read the loss report, skip invalid templates, use strict mode. |
| `docs/how-to/write-archetypes-to-umi.md` | How-to | Write one or several archetypes, with or without their reductions; check a round trip with `diff_umi`. |
| `docs/reference/umi-correspondence.md` | Reference | Every UMI field and its SBEM counterpart, rule, conserved quantity and status, generated from `CORRESPONDENCE`. |
| `docs/reference/translation-report.md` | Reference | Every field of the loss report, generated from its JSON Schema. |
| `docs/reference/api/umi.md` | Reference | mkdocstrings page for `archetypal.umi`. |
| `docs/explanation/umi-translation.md` | Explanation | What each direction loses and why: two zones, shares set by geometry, windows, thermostats, hot water per person, schedules by month, and what waits for UP-9. |

Every code example in these pages runs in CI against the fixtures (001 contract docs-site).

## Upstream dependencies (constitution: Development Workflow)

"Released" means released by the SBEM fork for epinterface items (roadmap C-17). Blocking
follows roadmap C-20: 003 is marked implemented only when every item marked yes (bridged or
not) is released; building and tagging 003 in M1 needs only UP-2.

| Item | Repository | What | Blocks "implemented"? |
|---|---|---|---|
| UP-2 | epinterface | Zone groups, now also **unset floor-area shares** meaning "set by geometry" (research R4); numeric heat-recovery effectiveness (sensible and latent); holiday and design-day slots; orientation ratios. | Yes: zone groups and unset shares, which also block building 003. The rest: not a dependency (losses reported). |
| UP-9 (new) | epinterface | SBEM fields for UMI (research R6): layered glazing, window settings, partition ratio, natural-ventilation limits, scheduled ventilation, mechanical-ventilation schedule, ideal-loads limits, heating and cooling availability, daylighting, adiabatic flags, archetype metadata, structure, environmental and schedule metadata. Also fixes `fractional_year_sum`'s weekday count and `Provider="Both"`. | Yes, all fields: the `S` fields for SC-003, the `L` and `D` fields for FR-010 (descriptive fields MUST map to SBEM). Not for building or tagging 003: until each lands, its loss is reported. |
| UP-10 (new) | idfkit | The equivalent single glazing layer of a simple-glazing window, from EnergyPlus's simple window model. | Yes; bridged by `_bridges.equivalent_glazing_layer` meanwhile (Complexity Tracking). |
| UP-3 | epinterface | Upstream PyPI release. | Not a dependency; it gates only v3's PyPI release (C-18). |

The roadmap is updated with UP-9, UP-10 and UP-2's unset shares, and C-13 now points to UP-9.

## Project Structure

### Documentation (this feature)

```text
specs/003-umi-translation/
├── plan.md              # This file
├── research.md          # Phase 0: R1–R19, spec feedback F-1–F-5
├── data-model.md        # Phase 1: pipelines, correspondence, rules, report, errors
├── quickstart.md        # Phase 1: validation scenarios
├── contracts/
│   ├── python-api.md          # read_umi, write_umi, to_umi, diff_*, guarantees
│   ├── translation-report.md  # the loss report file
│   └── umi-file.md            # what written UMI files look like
├── checklists/requirements.md
└── tasks.md             # Phase 2 (/speckit-tasks; not created here)
```

### Source Code (repository root, `v3` line)

```text
src/archetypal/
├── __init__.py              # adds read_umi, write_umi to the public re-exports
├── errors.py                # 001's hierarchy, extended: UmiFormatError, UmiValidationError (InputError)
├── reduction/
│   └── ledger.py            # 002's; 003 adds GroupLedger.approximate_from_group (R12)
└── umi/
    ├── __init__.py          # read_umi, write_umi, to_umi, UmiImport, UmiExport, diff_*, CORRESPONDENCE
    ├── _format.py           # private pydantic models of Basilisk Core classes, enums, defaults (R1)
    ├── _refs.py             # $id/$ref pre-scan and resolution; writer id assignment (R1, R13)
    ├── dialects.py          # dialect detection and the Archsim key map (R2)
    ├── validate.py          # completeness and range problems (R3)
    ├── correspondence.py    # FieldMapping, CORRESPONDENCE, the @rule registry (R5)
    ├── rules/               # one module per UMI area, each rule registered by id
    │   ├── materials.py     #   materials, constructions, layers, environmental (R11)
    │   ├── windows.py       #   layered ↔ simple via idfkit.thermal (R8)  ← load the idfkit skill
    │   ├── schedules.py     #   year parts ↔ monthly weeks; 002 projection for misaligned parts (R7)
    │   ├── loads.py         #   gains, internal mass (R10)
    │   ├── conditioning.py  #   thermostat, COP, fuels, mechanical ventilation (R9, R10)
    │   ├── ventilation.py   #   infiltration, natural ventilation (R10)
    │   ├── hotwater.py      #   per area ↔ per person, DHW system (R10)
    │   └── building.py      #   template ↔ archetype: groups, shares, WWR, metadata (R4, R12)
    ├── read.py              # UMI → SBEM orchestration, collision renaming (R4, R11)
    ├── write.py             # layout merge, perimeter/core copy, sharing, naming (R12, R13)
    ├── serialise.py         # Basilisk-ordered, deterministic JSON writer (R13)
    ├── report.py            # TranslationReport, Loss, Note, JSON Schema (R14)
    ├── diff.py              # diff_umi, diff_archetypes (R16)
    └── _bridges.py          # equivalent_glazing_layer (until UP-10), with its removal condition

tools/basilisk-check/        # .NET 8 console harness: reference scan, FromJson, orphans, ToJson,
                             #   names, required refs; --list-fields (R15). Not part of the package.

tests/
├── fixtures/umi/            # B2, ND, UZ, and edge-case libraries (R18)
├── data/basilisk_fields.json# every Basilisk Core field, from the harness (R5)
├── umi/basilisk_rules.py    # the harness's checks in Python, for local runs without .NET
├── unit/umi/                # rules, read, write, validation, correspondence, audit, determinism,
│                            #   performance, report schema
└── reference/test_umi_round_trip.py   # SC-004, SC-006 on 002's reference set

docs/
├── how-to/{read-a-umi-library,write-archetypes-to-umi}.md
├── reference/{umi-correspondence,translation-report}.md, reference/api/umi.md
└── explanation/umi-translation.md
```

**Structure decision.** A `umi` subpackage beside 002's `reduction`, in the src-layout
library generated by `/project-kit:new-project` (001 research R1).

- Conversion rules live in `rules/`, one module per UMI area, so each correspondence row has
  one home and the registry can check coverage.
- The one change to 002's code, `approximate_from_group`, sits in `reduction/ledger.py`,
  because merging rules belong to reduction (roadmap C-11).
- The Basilisk harness is a tool outside the package: it checks outputs, it is not library
  code.

### Tooling configuration

The project, layout and shared tooling come from 001's plan (roadmap C-19). 002 adds the idfkit
checks. 003 adds (research R15, R19):

- **CI.**
  - A `basilisk` job in `main.yml`: Ubuntu, `actions/setup-dotnet` 8.0, Basilisk checked out
    at `5cce24e8`. It writes libraries from the unit fixtures, runs `tools/basilisk-check` on
    them, and compares `--list-fields` with `tests/data/basilisk_fields.json`.
  - `reference.yml` also runs the harness on the 49 written reference libraries.
- **make.** `make check` runs the field-list comparison when `dotnet` is installed; CI always
  runs it.
- **Agents.** Whoever writes `umi/rules/windows.py` (the only module importing idfkit) loads
  `/idfkit:developing-with-idfkit` first. Docs pages are written with `/project-kit:diataxis`.

## Complexity Tracking

| Exception | Why needed | Simpler alternative rejected because |
|---|---|---|
| Temporary bridge `umi/_bridges.equivalent_glazing_layer` (EnergyPlus's simple window model, giving one glazing layer from U, SHGC and VT) | Writing 002's archetypes to UMI, the M1 workflow (roadmap C-10), needs a UMI window, and UMI has no simple-glazing material. idfkit does not yet offer this. | Inventing a multi-layer unit is not unique and claims layers no one specified. Waiting for UP-10 blocks M1. The bridge is one function, tested against EnergyPlus's own results for the same U/SHGC/VT, and removed when UP-10 is released (a test fails once idfkit offers it, as a reminder). |
| Private pydantic models mirroring Basilisk's classes | Reading and writing about 200 fields with pyright strict needs a typed model of the file. | Plain dicts are untyped (constitution VI). Exposing the models as API would recreate v2's UMI object model, which roadmap C-02 removes. Kept private, they are a file schema, not a second archetype model (constitution II). |
