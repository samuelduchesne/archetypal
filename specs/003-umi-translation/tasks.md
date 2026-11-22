---

description: "Tasks for spec 003: translate UMI template libraries to and from SBEM"
---

# Tasks: Translate UMI template libraries to and from SBEM

**Input**: design documents in `specs/003-umi-translation/`: [plan.md](plan.md),
[spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md).

**Agent skills** (roadmap C-19; spec 001 research R4):

- before writing or changing `src/archetypal/umi/rules/windows.py`, its test, or
  `verification/umi/simple_glazing.py` (the only code here that imports `idfkit`), load
  `/idfkit:developing-with-idfkit` and read the smallest reference page that covers the task
  (`idfkit.thermal`, `idfkit.simulation`);
- write and revise every page under `docs/` with `/project-kit:diataxis` (name the mode,
  brief the `project-kit:editor` agent, run the mode's checklist, wire the nav).

**Documentation**: each story carries its own pages, to land in the same pull request as its
code (constitution VI).

**Tests**: included. Constitution VI requires public behaviour to be tested, the spec gives an
independent test for each story, and its success criteria are automated checks
(SC-001–SC-007, research R16, R18). Within each story, write the tests first and see them fail
before implementing.

**Organisation**: by user story, so each story can be built, tested and shown on its own. The
conversion rules serve both directions, so they are foundational: every rule and its inverse
exist before either story starts, and the correspondence test (SC-005) needs them all.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel with the other [P] tasks of its phase (different files, no
  dependency on an unfinished task).
- **[Story]**: the user story the task serves (US1 write, US2 read, US3 round trip).
- Paths are relative to the root of the `v3` branch (spec 001, research R1–R2), unless a task
  names the SBEM fork (`samuelduchesne/epinterface`, roadmap C-17), idfkit, or Basilisk.

## Path conventions

Single library in src layout (plan.md, Project Structure): `src/archetypal/umi/`,
`tests/unit/umi/`, `tests/umi/`, `tests/fixtures/umi/`, `tests/data/`, `verification/umi/`,
`tools/basilisk-check/`, `docs/`.

---

## Phase 1: Setup (what 003 adds to specs 001 and 002)

**Purpose**: confirm the foundation 003 builds on, build the Basilisk harness first (research
R15: its claims are not yet verified), and collect the UMI test set.

- [ ] T001 Confirm on the `v3` branch that spec 001's foundation (Phases 1–2: shared tooling,
  test tiers, docs checks, `src/archetypal/errors.py`) and spec 002's pieces 003 calls are
  done: `reduction/schedules.py` projection (002 T026), `reduction/ledger.py` (002 T048),
  `Layout` (002 T021) with the `CORE_PERIMETER` key (002 T069), `merge(reduction, layout)`
  (002 T070), which reaches core/perimeter from any layout, and the `Reduction` type (002
  T059). Create `src/archetypal/umi/__init__.py` and `src/archetypal/umi/rules/__init__.py`
  with module docstrings only, and the folders `tests/unit/umi/`, `tests/umi/`,
  `tests/fixtures/umi/edge/`, `tests/data/umi/`, `verification/umi/`.
- [ ] T002 Write the .NET 8 harness in `tools/basilisk-check/` (research R15):
  - `fetch-basilisk.sh` clones `github.com/MITSustainableDesignLab/basilisk` into
    `tools/basilisk-check/.basilisk/` and checks out commit `5cce24e8`;
  - `basilisk-check.csproj` targets `net8.0` and compiles Basilisk's `Core/**/*.cs` from that
    checkout (Core itself targets the end-of-life `net7`);
  - `Program.cs` takes library paths and, for each, runs: (1) the raw-JSON reference scan of
    research R1 (`$id` first key and unique; `$ref` a string, alone in its object, pointing to
    an id seen earlier); (2) `Library.FromJson`; (3) `OrphanedComponents()` empty and
    `ToJson()` succeeds; (4) names non-null and unique per collection, glazing and gas
    materials together, building-template names unique, and every required reference of
    research R3 non-null;
  - prints `ok <file>` per passing file; exits 0 when all pass, else with status 10 + the
    number of the first failed check, naming the file and the problem;
  - `README.md` says how to run it locally.
- [ ] T003 Verify research R15's claims with the harness and record the results: run it on
  `BostonTemplateLibrary_2.json`, `BostonTemplateLibrary_nodup.json` and the library inside
  `umi_samples.umi` (all in `tests/input_data/umi_samples/` on `v2.x`), and on a hand-made
  library with a dangling and a forward `$ref`. Confirm that (a) `FromJson` alone turns both
  references into `null`; (b) `OrphanedComponents()` flags referenced-but-missing components
  only; (c) B2 and UZ load with their 29 unused components; (d) the build works on Linux
  without `net7`. Replace "Not verified yet" in `specs/003-umi-translation/research.md` R15
  with what was found. If a claim is wrong, amend research.md, data-model.md and
  contracts/umi-file.md before starting Phase 2.
- [ ] T004 Add a `--list-fields` mode to `tools/basilisk-check/Program.cs` that lists, by
  reflection, every serialised member of every Basilisk Core class as JSON
  `{"<Class>": ["<Key>", …]}` (classes sorted, keys in serialisation order), and commit its
  output as `tests/data/basilisk_fields.json` (research R5).
- [ ] T005 [P] Copy the UMI sample libraries into `tests/fixtures/umi/`:
  `BostonTemplateLibrary_2.json` (B2), `BostonTemplateLibrary_nodup.json` (ND), and
  `BostonTemplateLibrary.json` extracted from `umi_samples.umi` as
  `umi_samples_BostonTemplateLibrary.json` (UZ). Add `tests/fixtures/umi/README.md` giving
  each file's origin, dialect (research R2) and SHA-256.
- [ ] T006 [P] Write the edge-case fixtures by hand in `tests/fixtures/umi/edge/` (research
  R18), each with one or two templates and a top-of-README line stating the expected outcome:
  `dangling_ref.json`; `forward_ref.json`; `missing_reference.json` (a `ZoneLoads` whose
  `LightingSchedule` is `null`); `duplicate_names.json` (two `OpaqueMaterials` named alike
  with different conductivity, a glazing and a gas material named alike, two templates named
  alike); `shared_zone.json` (a template whose `Core` and `Perimeter` are one zone
  definition, as written for a perimeter-only archetype); `misaligned_parts.json` (a year
  schedule whose parts end on 15 March and 15 October); `out_of_range.json` (a negative
  conductivity used only by the first of two templates); `no_templates.json`;
  `unused_components.json`; `archsim_dialect.json` (materials carrying `GasType`, `Life` and
  `Comment`); `legacy.xml` (a `<LibSerializable>` root).
- [X] T007 [P] Tooling (research R15, R19):
  - add a `basilisk` job to `.github/workflows/main.yml` on every pull request: Ubuntu,
    `actions/setup-dotnet` 8.0, `tools/basilisk-check/fetch-basilisk.sh`, then
    `uv run pytest tests/unit/umi --write-libraries out/libraries`, then
    `dotnet run --project tools/basilisk-check -- out/libraries/*.json`, then
    `dotnet run --project tools/basilisk-check -- --list-fields | diff - tests/data/basilisk_fields.json`;
  - in `Makefile`, make `check` run the same field-list comparison only when
    `command -v dotnet` succeeds;
  - in `tests/conftest.py`, add the `--write-libraries DIR` option: every test that writes a
    UMI library also saves it under DIR;
  - add `tools/basilisk-check/.basilisk/`, `bin/` and `obj/` to `.gitignore`.

**Checkpoint**: the harness builds and passes B2, ND and UZ; R15 is verified; `make check`
passes.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: the upstream prerequisite, the errors, the private format model, references,
the correspondence table and every conversion rule in both directions, and the loss report.

**⚠️ No user-story work starts before this phase is complete.**

### Upstream prerequisites

- [ ] T008 In the SBEM fork, on topic branch `up-2-unset-shares`, extend UP-2 (research R4):
  a zone group's floor-area share may be `None`, meaning "set by the building's geometry";
  the validator accepts either every share set (summing to 1) or every share `None`; the
  shoebox builder takes core and perimeter areas from `w`, `d` and `perim_depth` when shares
  are unset (`sbem/builder.py:913-914`). Merge into the fork's `main`, include it in the next
  fork tag (with 002's T009–T010 if not yet tagged), update `[tool.uv.sources]`, and open it
  upstream.
- [X] T009 [P] Draft the idfkit issue for UP-10 (an `equivalent_glazing_layer(u, shgc, vt)`
  in `idfkit.thermal`, from the Engineering Reference "Window Calculation Module: Simple
  Window Model") in `specs/003-umi-translation/upstream/idfkit-issues.md`, for the user to
  file.

### Tests for the foundation (write first, see them fail)

- [X] T010 [P] Test the errors in `tests/unit/umi/test_errors.py`: `UmiFormatError` and
  `UmiValidationError` derive from `InputError`; `UmiValidationError.problems` is a
  `list[Problem]`, each with `pointer` (a JSON pointer), `template` (`str | None`), `rule` and
  `message`; the error's message lists every problem; its subject is the library path.
- [ ] T011 [P] Test the private format model in `tests/unit/umi/test_format.py`: one frozen
  model per Basilisk Core class listed in data-model.md, plus `UmiLibrary`; snake_case fields
  with Basilisk's keys as aliases; an absent key takes Basilisk's effective default and is
  recorded as defaulted; enums are `IntEnum`s with Basilisk's values (`FuelType` 0–13,
  `IdealSystemLimit`, `EconomizerType`, `HeatRecoveryType`, `DimmingType`, `ShadingType`,
  `WindowType`, `DomesticHotWaterFuelType`); every class and key of
  `tests/data/basilisk_fields.json` has a model field; nothing in `_format` is exported from
  `archetypal.umi`.
- [ ] T012 [P] Test references in `tests/unit/umi/test_refs.py` (research R1): the pre-scan
  rejects, each as a format problem with its JSON pointer, a duplicate `$id`, an `$id` that
  is not the first key, a non-string `$ref`, extra keys beside `$ref`, a dangling `$ref` and
  a forward `$ref`; resolution returns objects, never `None`; window settings defined inline
  in a template and in the `WindowSettings` collection both resolve; the writer's id
  assignment numbers `"1"`, `"2"`, … in document order, defines each component at first
  occurrence and refers back with `{"$ref": id}` afterwards.
- [ ] T013 [P] Test the correspondence in `tests/unit/umi/test_correspondence.py` (SC-005):
  every (class, key) of `tests/data/basilisk_fields.json` is in `CORRESPONDENCE`; and its
  invariants, verbatim from data-model.md: "each (class, key) appears exactly once; `status`
  `exact` or `converted` has at least one SBEM path; `upstream` has a UP item; the set of
  `rule` values equals the set of registered rules". Also: each SBEM path resolves on
  epinterface's model by walking `model_fields`; each `upstream` value is a UP item of
  `.specify/memory/roadmap.md`.
- [ ] T014 [P] Test the report in `tests/unit/umi/test_report.py` (FR-011, R14):
  `schema_version` is `"1.0"`; `direction` is `"umi_to_sbem"` or `"sbem_to_umi"`; `summary`
  is `"Nothing was lost."` if and only if `losses` is empty, else counts by kind; losses and
  notes are sorted by `subject`, then `location`; floats keep `repr` precision; equal reports
  give byte-identical JSON; every `Loss.rule` is a registered rule or one of `library.unused`,
  `names.collision`, `layout.merged`, `layout.share_dropped`, `layout.core_copied`,
  `validation.skipped`; every `upstream` is a roadmap UP item; the generated JSON Schema equals
  the committed `docs/schemas/translation-report-1.0.json`.
- [ ] T015 [P] Test the material rules in `tests/unit/umi/test_rules_materials.py` (R11):
  `material.carbon_per_m3` (`C_m3 = C_kg × ρ`, inverse `C_kg = C_m3 / ρ`, refused for ρ = 0);
  `ThermalEmittance` ↔ `ThermalAbsorptance`; `Roughness` outside EnergyPlus's six keywords is
  a range problem; SBEM `Type` from `Category` when it names one of the 12 types
  (case-insensitive), else `Other` and noted; `TemperatureCoefficientThermalConductivity` set
  to 0 and noted; layers keep order and thickness; the five construction-set slots of R11's
  table are filled on reading (noted) and listed as lost on writing when they differ; a
  hypothesis property that each rule composed with its inverse is the identity within 1e-12
  relative.
- [ ] T016 [P] Test the schedule rules in `tests/unit/umi/test_rules_schedules.py` (R7):
  days are Monday first; a month covered by one year part is copied exactly; a month split by
  part boundaries is projected with 002's projection, conserving the month's sum over the
  reference year (non-leap, starting on Monday), and is listed as approximate; writing merges
  consecutive equal months into one part ending on each month's last day, February on the
  29th; `Type` `Fraction`, `Temperature` and `AnyNumber` map by name, anything else to
  `AnyNumber` with a note; one UMI schedule in several roles gives one SBEM year per role,
  all with the UMI name; holiday and design-day slots that differ from the days they replace
  are lost on writing.
- [ ] T017 [P] Test the window rules in `tests/unit/umi/test_rules_windows.py` (R8):
  `window.simple_from_layers` on every window construction of B2 and UZ equals
  `idfkit.thermal.calculate_u_value`, `calculate_shgc` and `calculate_visible_transmittance`
  on the same layers; per-layer properties are listed as lost and U, SHGC, VT as approximate;
  `window.equivalent_layer` returns, for each case of `tests/data/umi/simple_glazing_energyplus.json`,
  the layer recorded there, and the U, SHGC and VT EnergyPlus computed for that layer match the
  targets within the tolerance stated in the test; reading gives both groups the template's
  window; writing uses the perimeter window and lists a different core window as lost; a test
  fails, naming T072, as soon as `idfkit.thermal` offers an equivalent-layer function.
- [ ] T018 [P] Test the load rules in `tests/unit/umi/test_rules_loads.py` (R10): densities,
  schedules, `Is*On` and `DimmingType` map exactly; reading sets `MetabolicRate` to 1.2 met
  with a note, writing lists a non-default value as lost; internal-mass ratio 0 means no
  internal mass (both or neither); `IlluminanceTarget` is lost with `upstream: "UP-9"`.
- [ ] T019 [P] Test the conditioning rules in `tests/unit/umi/test_rules_conditioning.py`
  (R9, R10): `thermostat.constant` (constant schedules on reading; heating maximum and cooling
  minimum on writing, with setback hours listed as lost with their count and mean difference);
  `IsHeatingOn = false` gives `Heating = None`, cooling likewise; `cop.system` (`SystemCOP =
  COP`, `DistributionCOP = 1`; writing `COP = SystemCOP × DistributionCOP`, split lost when
  `DistributionCOP ≠ 1`); every row of data-model.md's fuel table, including its losses;
  fresh air above SBEM's 0.05 cap is a range problem; `EconomizerType` and `HeatRecoveryType`
  map by name; heat-recovery effectiveness is lost with `upstream: "UP-2"`; availability
  schedules are lost unless every value is 1; a `DCV` other than `NoDCV` is lost on writing.
- [ ] T020 [P] Test the ventilation rules in `tests/unit/umi/test_rules_ventilation.py` (R10):
  `Infiltration` ↔ `AirChangesPerHour` with `CalculationMethod = "AirChanges/Hour"`; unused
  coefficients noted (constant 1, others 0); another method is lost on writing with its value;
  attic and basement infiltration filled from the main value (noted) and lost on writing when
  they differ; `vent.provider` maps (mechanical, natural) to `None`, `Natural`, `Mechanical`,
  `Both` and back; `NatVentSchedule` ↔ `Ventilation.Schedule`.
- [ ] T021 [P] Test the hot-water rules in `tests/unit/umi/test_rules_hotwater.py` (R10):
  `dhw.per_person` is `q_p = q_a × Σ s(h) / (365 × ρ_p)` with inverse
  `q_a = q_p × 365 × ρ_p / Σ s(h)`, conserving annual volume per m²; `ρ_p = 0` or people off
  is a range problem on reading and a loss on writing; COP as in `cop.system`; UMI
  `Electricity`, `NaturalGas`, `Oil` ↔ SBEM `Electricity`, `NaturalGas`, `FuelOil`; SBEM
  `Propane` and `Steam` written as `NaturalGas` with a loss; `Unset` is a range problem;
  temperatures map exactly.
- [ ] T022 [P] Test the building rules in `tests/unit/umi/test_rules_building.py` (R4, R11,
  R13): a template gives groups `core` and `perimeter` with every share `None`, equal when
  both reference one zone definition; `wwr.uniform` (one ratio on every orientation on
  reading; facade-area-weighted mean on writing, lost when orientations differ); each
  template-level field of R6's table is lost with `upstream: "UP-9"`; the naming rules of
  data-model.md ("Names of components without a one-to-one counterpart") hold in both
  directions.
- [ ] T023 [P] Port the harness's checks 1 and 4 and the orphan check to Python in
  `tests/umi/basilisk_rules.py`, and test it in `tests/unit/umi/test_basilisk_rules.py`: B2,
  ND and UZ pass; `dangling_ref.json` and `forward_ref.json` fail check 1;
  `duplicate_names.json` fails check 4.

### Implementation of the foundation

- [X] T024 [P] Extend `src/archetypal/errors.py` (001 research R8): `Problem` (frozen
  dataclass: `pointer`, `template`, `rule`, `message`), `UmiFormatError(InputError)` and
  `UmiValidationError(InputError)` with `.problems: list[Problem]`, with Google docstrings.
- [ ] T025 [P] Implement `src/archetypal/umi/_format.py` (R1): the frozen pydantic v2 models
  of data-model.md ("Private format model") with aliases, Basilisk's effective defaults (its
  `[DefaultValue]`, else its initialiser), a record of defaulted fields, and the `IntEnum`s.
  Mark the module private (`__all__ = []`, a docstring stating roadmap C-02).
- [ ] T026 Implement `src/archetypal/umi/_refs.py` (R1, R13): the pre-scan over the raw JSON
  in file order, resolution into the models of T025, and the writer's id assignment.
- [ ] T027 [P] Implement `src/archetypal/umi/correspondence.py` (R5): `Relevance`,
  `MappingStatus`, `FieldMapping` as in data-model.md, the `@rule(id)` registry (each rule
  holds its UMI → SBEM and SBEM → UMI functions, either may be absent), and `CORRESPONDENCE`
  with one row per field of `tests/data/basilisk_fields.json`, following data-model.md's
  correspondence table; `note` states the conserved quantity or why there is no counterpart.
- [ ] T028 [P] Implement `src/archetypal/umi/report.py` (R14): `TranslationReport`,
  `SourceInfo`, `Loss`, `LossKind`, `Note`, `NoteKind` exactly as in data-model.md; the
  summary; deterministic JSON (sorted, `repr` floats, two-space indent, final newline); a
  `python -m archetypal.umi.report --schema` entry that writes
  `docs/schemas/translation-report-1.0.json`, and commit that file.
- [ ] T029 [P] Implement `src/archetypal/umi/rules/materials.py` (R11): rules for materials,
  layers, constructions, construction sets and environmental fields, registered by id.
- [ ] T030 [P] Implement `src/archetypal/umi/rules/schedules.py` (R7): `schedule.months`,
  `schedule.type` and day and week copying, calling 002's
  `archetypal.reduction.schedules` for evaluation and projection (no second evaluator).
- [ ] T031 [P] Implement `src/archetypal/umi/_bridges.py`: `equivalent_glazing_layer(u, shgc,
  vt)` returning thickness, conductivity, solar and visible transmittance and reflectances by
  the Engineering Reference's simple window model, with a docstring stating its removal
  condition: "delete when idfkit releases UP-10 (T072)".
- [ ] T032 After T031, write `verification/umi/simple_glazing.py`: for a grid of 12 (U, SHGC,
  VT) cases spanning single to triple glazing, build one-window models with idfkit, one with
  `WindowMaterial:SimpleGlazingSystem` and one with the bridge's layer, run EnergyPlus 24.2
  through `idfkit.simulation`, read U, SHGC and VT from the Envelope Summary fenestration
  table, and write inputs, layers and results to
  `tests/data/umi/simple_glazing_energyplus.json`. Commit the file.
- [ ] T033 Implement `src/archetypal/umi/rules/windows.py` (R8): `window.simple_from_layers`
  (an in-memory idfkit `Construction` with `WindowMaterial:Glazing` and `WindowMaterial:Gas`
  through typed constructors only, no `get_collection`; then `idfkit.thermal`) and
  `window.equivalent_layer` (through `_bridges`), plus window placement.
- [ ] T034 [P] Implement `src/archetypal/umi/rules/loads.py` (R10).
- [ ] T035 [P] Implement `src/archetypal/umi/rules/conditioning.py` (R9, R10), with the fuel
  table of data-model.md as one constant.
- [ ] T036 [P] Implement `src/archetypal/umi/rules/ventilation.py` (R10).
- [ ] T037 [P] Implement `src/archetypal/umi/rules/hotwater.py` (R10).
- [ ] T038 [P] Implement `src/archetypal/umi/rules/building.py` (R4, R11, R13): template ↔
  archetype groups and shares, `wwr.uniform`, metadata, and the naming rules.
- [ ] T039 Generate the two reference pages with `/project-kit:diataxis` (reference mode):
  `docs/reference/umi-correspondence.md` built from `CORRESPONDENCE` at docs build time by
  `docs/scripts/gen_umi_correspondence.py` (never hand-written), and
  `docs/reference/translation-report.md` from `docs/schemas/translation-report-1.0.json`;
  wire both into the reference section's index and nav (FR-009, FR-013).

**Checkpoint**: T010–T023 pass; every Basilisk field has a correspondence row and every rule
is registered.

---

## Phase 3: User Story 1 — Write an archetype as a UMI template library (Priority: P1) 🎯 MVP

**Goal**: one or more SBEM archetypes, or 002 reductions, become one UMI library that
Basilisk loads, with a loss report (FR-005–FR-008, FR-011, FR-011a, FR-012).

**Independent test**: reduce each fixture building to its default layout, write it to UMI,
run `tools/basilisk-check` on the file, and check that the template equals the archetype
merged to core/perimeter and that the report lists the merged groups and dropped shares.

### Tests for User Story 1 (write first, see them fail)

- [ ] T040 [P] [US1] Test the approximate merge in `tests/unit/umi/test_approximate_merge.py`
  (R12): `GroupLedger.approximate_from_group(group, floor_area)` rebuilds gains and their
  profiles, setpoints, outdoor air and its profile, and hot water so that merging them equals
  002's `merge` of the matching `Reduction` for those parameters; envelope U and capacity,
  efficiencies, infiltration and the window are floor-area weighted and each is listed as
  `approximate`; an archetype with more than two groups and unset shares raises `InputError`
  naming it.
- [ ] T041 [P] [US1] Test writing in `tests/unit/umi/test_write.py`: scenario 1 (a
  core/perimeter archetype gives one template whose values equal the archetype's; the report
  lists the shares as `share_dropped` and every SBEM-only field); scenario 2 (a `Reduction`
  with several groups gives the template of `merge(reduction, Layout.CORE_PERIMETER)`, with
  one `merged` loss per merged group carrying its pre-merge keys); scenario 3 (two archetypes
  sharing a construction and a schedule give one of each); perimeter-only and core-only
  archetypes write one shared `ZoneDefinition` with a `copied` loss (FR-006b); duplicate
  archetype names and one name used for different content get ` #2` with a `renamed` loss;
  only components reachable from a template are written; an empty sequence raises
  `InputError`; an existing file is refused unless `overwrite`; strict mode raises
  `LossyTranslationError` and writes nothing; the report is written as `<stem>.loss.json`.
- [ ] T042 [P] [US1] Test the file form in `tests/unit/umi/test_serialise.py`: each of rules
  1–7 of contracts/umi-file.md is one test; `MinFreshAirPerArea = 0.0003` is written as
  `0.0003` (no rounding, R13); writing the same input twice gives identical bytes (FR-012);
  every written library passes `tests/umi/basilisk_rules.py`.

### Implementation for User Story 1

- [ ] T043 [US1] Add `GroupLedger.approximate_from_group(group, floor_area)` to
  `src/archetypal/reduction/ledger.py` (R12): the floor area is the group's share × 1 m²;
  rules needing report data use floor-area weighting and return the list of approximated
  parameters.
- [ ] T044 [US1] Implement `src/archetypal/umi/write.py` (R12, R13): normalise each item's
  layout (002's `merge` for a `Reduction`, the approximate merge for a bare archetype, the
  perimeter or core copy), convert each archetype with the registered SBEM → UMI rules,
  assemble the library by content key (canonical JSON without `Name`), share equal components,
  rename clashing names in order of first appearance, keep only reachable components, and
  build the report.
- [ ] T045 [US1] Implement `src/archetypal/umi/serialise.py` (R13, contracts/umi-file.md): the
  17 collections in Basilisk's order, components sorted by name, ids from `_refs`, window
  settings inline at first use, templates without `$id`, enums as integers, integer fields as
  integers, shortest round-trip floats, two-space indentation, `\n`, UTF-8 without BOM, final
  newline.
- [ ] T046 [US1] Add `to_umi`, `write_umi` and `UmiExport` (contracts/python-api.md) in
  `src/archetypal/umi/write.py`, re-exported from `src/archetypal/umi/__init__.py`, and
  `write_umi` from `src/archetypal/__init__.py`. `write_umi` writes the library and
  `<stem>.loss.json` only after the whole translation succeeds (to temporary files, then
  renamed), refuses existing files unless `overwrite`, and in strict mode raises before
  writing.
- [ ] T047 [P] [US1] Write `docs/how-to/write-archetypes-to-umi.md` with `/project-kit:diataxis`
  (how-to): write one or several archetypes, with or without their reductions, read the loss
  report, use strict mode. Code examples run against the fixtures in CI.
- [ ] T048 [US1] Add `docs/reference/api/umi.md` (mkdocstrings page for `archetypal.umi`) and
  wire it into the API reference nav.

**Checkpoint**: the pytest and harness steps of quickstart scenarios 2 and 3 pass (their
`archetypal` command steps wait for 001's Phase 3); the `basilisk` CI job is green.

---

## Phase 4: User Story 2 — Bring an existing UMI library into SBEM (Priority: P1)

**Goal**: every building template of a UMI library becomes a valid SBEM archetype, after
validation that names every problem, with a loss report (FR-001–FR-004, FR-011, FR-011a).

**Independent test**: read each library of the UMI test set; every template gives an
archetype that validates as epinterface's model, and every field is represented or listed in
the report.

### Tests for User Story 2 (write first, see them fail)

- [ ] T049 [P] [US2] Test dialects in `tests/unit/umi/test_dialects.py` (R2): B2 and ND are
  `core-json-pre-2023`, with a `defaulted` note per absent field; a library carrying
  `AdvancedModel` is `core-json`; UZ reads through the Archsim key map (`Comment` →
  `Comments`, `GasType` 0–4 → `AIR`, `ARGON`, `KRYPTON`, `XENON`, `SF6`, material `Type` →
  `Category`), with `Life`, `EmbodiedEnergyStdDev`, `PhaseChange` and `Optical` listed as
  lost; `legacy.xml` is refused with "Legacy UMI XML library is not supported; open and save
  it in UMI to convert it to JSON"; a `.umi` zip is refused naming the library file to
  extract; anything else is refused naming the missing marker.
- [ ] T050 [P] [US2] Test validation in `tests/unit/umi/test_validation.py` (R3, FR-004):
  every problem is collected before raising one `UmiValidationError`; each edge fixture yields
  its problems with their JSON pointers; every required reference of R3's list, 24 values per
  day, and year parts covering 1 January–31 December without gap or overlap; range problems
  from the SBEM field constraints and plausibility rules; with `skip_invalid_templates=True`,
  `out_of_range.json` reads its second template and reports the first as
  `skipped_template`; format problems are never skipped; duplicate names are not problems.
- [ ] T051 [P] [US2] Test reading in `tests/unit/umi/test_read.py`: scenario 1 (B2 gives four
  archetypes in template order, each with `core` and `perimeter` groups and unset shares;
  descriptive fields are lost with `upstream: "UP-9"` until T070); scenario 2
  (`duplicate_names.json` keeps both components and both templates, the second named ` #2`,
  with a `names.collision` loss); scenario 3 (an invalid library raises and returns no
  archetypes); `no_templates.json` returns no archetypes and lists every component as
  `unused`; `unused_components.json` lists them as `unused`; every archetype read from the
  fixtures validates as epinterface's model (SC-001); `UmiImport.write(dir)` writes
  `<name>.sbem.json` per archetype and `<library stem>.loss.json`; strict mode raises
  `LossyTranslationError` when `losses` is not empty.

### Implementation for User Story 2

- [ ] T052 [P] [US2] Implement `src/archetypal/umi/dialects.py` (R2): detection by shape and
  the Archsim key map.
- [ ] T053 [P] [US2] Implement `src/archetypal/umi/validate.py` (R3): completeness and range
  problems, each a `Problem` with its pointer, template and rule.
- [ ] T054 [US2] Implement `src/archetypal/umi/read.py` (R4, R11): dialect → references →
  validation → per template, the registered UMI → SBEM rules → archetype; collision
  renaming; unused components; the report with `source` (path, SHA-256, dialect, archetypal
  and epinterface versions).
- [ ] T055 [US2] Add `read_umi` and `UmiImport` (contracts/python-api.md) in
  `src/archetypal/umi/read.py`, re-exported from `src/archetypal/umi/__init__.py`, and
  `read_umi` from `src/archetypal/__init__.py`. `read_umi` never writes files.
- [ ] T056 [P] [US2] Write `docs/how-to/read-a-umi-library.md` with `/project-kit:diataxis`
  (how-to): read a library, read the loss report, skip invalid templates, use strict mode.

**Checkpoint**: quickstart scenario 6 and the pytest step of scenario 1 pass (its `archetypal
translate` step waits for 001's Phase 3); spec 001's `translate` command can be
built (001 research R14).

---

## Phase 5: User Story 3 — Round trip without silent change (Priority: P2)

**Goal**: read-then-write and write-then-read change nothing that is not reported (SC-003,
SC-004, SC-006, SC-006a).

**Independent test**: for each library of the UMI test set, read then write it and compare
with `diff_umi`; every difference is in a report.

### Tests for User Story 3 (write first, see them fail)

- [ ] T057 [P] [US3] Test the diffs in `tests/unit/umi/test_diff.py` (R16): `diff_umi`
  matches components by name and type and schedules by hourly values over the reference year;
  each difference carries `location`, `relevance`, `original`, `result` and `relative`
  (`None` for non-numeric); `within_tolerance` is false only for an `S` difference above
  `rel_tol` (default 1e-4); absolute differences below 1e-12 are equal; an unreadable library
  raises `UmiFormatError`; `diff_archetypes` compares SBEM field paths.
- [ ] T058 [P] [US3] Test round trips in `tests/unit/umi/test_round_trip.py`: scenario 1 on
  every fixture library (every `S` value within 0.01 % or reported); the `S` fields waiting
  for UP-9 are marked `xfail(strict=True, reason="UP-9")` per field group, so each flips when
  its field lands; scenario 2 (a core/perimeter archetype written and read back equals the
  original apart from the first write's losses), also as a hypothesis property over generated
  core/perimeter archetypes.
- [ ] T059 [P] [US3] Write the audit in `tests/unit/umi/test_audit.py` (SC-006, R16): for each
  fixture library, read it, write it back, translate each archetype the other way too, diff
  the results, and assert that every difference appears in a loss of the matching report by
  subject and location, and that every loss matches a difference or a value with no
  counterpart; an unreported difference fails with its location.
- [ ] T060 [P] [US3] Test strict mode in `tests/unit/umi/test_strict.py` (SC-006a): over the
  test set, every read and write whose `losses` is not empty fails and writes nothing, and
  every one whose `losses` is empty succeeds, in both directions.

### Implementation for User Story 3

- [ ] T061 [US3] Implement `src/archetypal/umi/diff.py` (R16): `UmiDiff`, `ArchetypeDiff`,
  `diff_umi(original, result, *, rel_tol=1e-4)` and `diff_archetypes(a, b, *, rel_tol=0.0)`.
- [ ] T062 [US3] Re-export the diffs from `src/archetypal/umi/__init__.py` and make its
  `__all__` exactly the names of contracts/python-api.md's import block.
- [ ] T063 [P] [US3] Write `docs/explanation/umi-translation.md` with `/project-kit:diataxis`
  (explanation): what each direction loses and why: two zones, shares set by geometry,
  windows, thermostats, hot water per person, schedules by month and the Monday-aligned week,
  and what waits for UP-9.
- [ ] T064 [P] [US3] Add "Check a round trip with `diff_umi`" to
  `docs/how-to/write-archetypes-to-umi.md`.

**Checkpoint**: quickstart scenario 4 passes, with SC-003's UP-9 fields expected to fail, and
`tests/unit/umi/test_strict.py` passes (scenario 5's command form waits for 001's Phase 3).

---

## Phase 6: Checks across stories (SC-002, SC-004, SC-006, SC-007)

- [ ] T065 [P] Write `tests/unit/umi/test_performance.py`: a library of 100 templates built
  from B2 by renaming is read in under 3 s and written in under 3 s (SC-007's 5 s, with a
  margin for slow CI).
- [ ] T066 [P] Write `tests/reference/test_umi_round_trip.py` (`@pytest.mark.reference`): for
  each of 002's 49 reference buildings, the core/perimeter archetype is written with
  `write_umi`, read back, and `diff_archetypes` is empty apart from reported losses (SC-004);
  the audit of T059 runs on the 49 libraries (SC-006); the libraries are saved under
  `--write-libraries`.
- [ ] T067 Extend `.github/workflows/reference.yml` to run `tools/basilisk-check` on the 49
  libraries written by T066 (SC-002).

**Checkpoint**: quickstart scenario 7 passes; the reference workflow is green.

---

## Phase 7: Upstream follow-ups (each when its fork tag or idfkit release exists)

**Purpose**: replace each upstream loss and the bridge as its item is released (constitution
I). T068 and T069 are independent; T070 follows T068 field by field.

- [ ] T068 In the SBEM fork, implement UP-9's simulation fields (research R6), one topic
  branch each: `up-9-layered-glazing`, `up-9-window-settings`, `up-9-partition-ratio`,
  `up-9-natvent-limits`, `up-9-scheduled-ventilation`, `up-9-mechvent-schedule`,
  `up-9-ideal-loads-limits`, `up-9-availability`, `up-9-daylighting`, `up-9-adiabatic`; and
  the two defect fixes, `up-9-fractional-year-sum` (weekday count,
  `sbem/components/schedules.py:634`) and `up-9-provider-both`
  (`sbem/components/operations.py:311`). Each field is written to EnergyPlus by the fork's
  builder. Tag the fork, update `[tool.uv.sources]`, and open each upstream.
- [ ] T069 [P] In the SBEM fork, implement UP-9's life-cycle and descriptive fields
  (archetype metadata, structure, environmental fields on materials and assemblies, schedule
  metadata), one topic branch each; tag and open upstream. Not blocking.
- [ ] T070 After each UP-9 field is released (T068, T069): change its rows in
  `src/archetypal/umi/correspondence.py` from `upstream` to `exact` or `converted`, map it in
  the matching `src/archetypal/umi/rules/` module (for layered glazing, both directions
  exact), remove its losses, update its rule test, and remove its `xfail` in
  `tests/unit/umi/test_round_trip.py`.
- [ ] T071 After 002's T086 releases UP-2's numeric heat-recovery effectiveness and holiday
  and design-day slots: map `HeatRecoveryEfficiencySensible` and `…Latent` in
  `src/archetypal/umi/rules/conditioning.py`, write holiday and design-day slots' losses only
  when they differ, and update the rows and tests.
- [ ] T072 [P] When idfkit releases UP-10: call its function from
  `src/archetypal/umi/rules/windows.py`, delete `src/archetypal/umi/_bridges.py` and the
  reminder test of T017, raise the idfkit lower bound in `pyproject.toml`, and remove the
  bridge row from plan.md's Complexity Tracking.

**Checkpoint**: SC-003 holds without `xfail`, every UP-9 field is mapped, and the bridge is
gone; 003 can be marked implemented (plan.md, Upstream dependencies; roadmap C-20).

---

## Phase 8: Polish and cross-cutting concerns

- [ ] T073 [P] Complete the `Unreleased` section of `CHANGELOG.md`: `read_umi`, `write_umi`,
  `to_umi`, the diffs, the loss report file, and each loss that waits on UP-9 or UP-10.
- [ ] T074 Run every quickstart scenario, `make check`, `make docs-test` and the unit tier's
  time budget, and fix what fails.
- [ ] T075 Mark 003 implemented in `.specify/memory/roadmap.md` once SC-001–SC-007 hold and its
  blocking items are released (plan.md, Upstream dependencies; roadmap C-20): UP-2's zone
  groups and unset shares and every UP-9 field by the fork (T068–T070 done), and UP-10 by
  idfkit (T072 done). Milestone M1 (`v3.0.0aN`) needs only 003's success criteria met on the
  tag, with UP-9's fields reported as lost and SC-003's `xfail`s explained in the changelog
  (roadmap C-18).

---

## Dependencies and execution order

### Phases

- **Setup (1)**: after spec 001's foundation and the 002 pieces named in T001. T002 → T003 →
  T004; T005–T007 in parallel with them.
- **Foundational (2)**: after Setup (T004's field list and T005–T006's fixtures). Blocks every
  story. T008 (the fork) blocks only the tasks that build archetypes (T022, T038 onward); the
  format, references, correspondence and report can start while it is under way. T026 after
  T025; T032 after T031; T033 after T031–T032; T039 after T027–T028.
- **US1 (3)** and **US2 (4)**: both after Foundational, independent of each other, and can be
  built in parallel. US1 is the MVP (roadmap C-10).
- **US3 (5)**: after US1 and US2 (it composes both directions).
- **Checks across stories (6)**: after US3; T066 also needs 002's reference set (002 Phase 6).
- **Upstream follow-ups (7)**: each task when its upstream item exists; T070 after T068 or
  T069, field by field; T071 after 002's T086.
- **Polish (8)**: after Phases 3–6; T075 last, after T068–T070 and T072.
- **Spec 001**: its `translate` command and `reduce --to umi` (001 Phase 3) can start once
  T046 and T055 are done.

### Within each story

- Tests first, failing.
- US1: `ledger.approximate_from_group` → `write` → `serialise` → `to_umi`/`write_umi` → docs.
- US2: `dialects` and `validate` → `read` → `read_umi` → docs.
- US3: `diff` → exports → docs.

### Parallel opportunities

- Setup: T005–T007 alongside T002–T004.
- Foundational: T010–T023 (tests); then T024, T025, T027–T031, T034–T038.
- US1 and US2 entirely in parallel after Foundational; within each, all its test tasks, and
  its docs alongside its implementation.
- US3: T057–T060, then T063–T064 alongside T061.
- Phase 6: T065 and T066.
- Phase 7: T069 and T072, whenever released.

## Parallel example: Foundational

```text
# Tests, all at once:
T010 tests/unit/umi/test_errors.py           T017 tests/unit/umi/test_rules_windows.py
T011 tests/unit/umi/test_format.py           T018 tests/unit/umi/test_rules_loads.py
T012 tests/unit/umi/test_refs.py             T019 tests/unit/umi/test_rules_conditioning.py
T013 tests/unit/umi/test_correspondence.py   T020 tests/unit/umi/test_rules_ventilation.py
T014 tests/unit/umi/test_report.py           T021 tests/unit/umi/test_rules_hotwater.py
T015 tests/unit/umi/test_rules_materials.py  T022 tests/unit/umi/test_rules_building.py
T016 tests/unit/umi/test_rules_schedules.py  T023 tests/umi/basilisk_rules.py

# Then the rule modules, all at once:
T029 rules/materials.py   T030 rules/schedules.py   T034 rules/loads.py
T035 rules/conditioning.py   T036 rules/ventilation.py   T037 rules/hotwater.py
T038 rules/building.py
```

## Parallel example: User Stories 1 and 2

```text
# Developer A (US1):            # Developer B (US2):
T040 test_approximate_merge.py  T049 test_dialects.py
T041 test_write.py              T050 test_validation.py
T042 test_serialise.py          T051 test_read.py
T043 → T044 → T045 → T046       T052, T053 → T054 → T055
T047, T048                      T056
```

## Implementation strategy

### MVP: User Story 1

1. Spec 001's foundation and 002's merge, then Setup (the harness first) and Foundational,
   including the fork's unset shares.
2. User Story 1: write archetypes to UMI.
3. **Stop and validate**: the pytest and harness steps of quickstart scenarios 2 and 3. With
   002, this delivers v2's core workflow, "reduce a detailed model and get a UMI template
   library" (roadmap C-10).

### Incremental delivery

1. US1: writing (MVP).
2. US2: reading; unblocks 001's `translate` command.
3. US3: round trips, the audit and strict mode.
4. Checks across stories: performance and the 49 reference libraries in Basilisk.
5. Upstream follow-ups as the fork and idfkit release; UP-9's simulation fields complete
   SC-003.
6. Polish; 003 joins milestone M1 with 001 and 002.

Each step ships with its documentation pages (constitution VI).

### Notes

- Each task's tests fail before its implementation.
- Commit after each task or logical group.
- No task publishes to PyPI (roadmap C-18).
- .NET is never a package dependency (constitution III); without it, `tests/umi/basilisk_rules.py`
  runs the same checks locally.
