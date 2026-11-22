---

description: "Tasks for spec 002: reduce a detailed EnergyPlus model to an SBEM archetype"
---

# Tasks: Reduce a detailed EnergyPlus model to an SBEM archetype

**Input**: design documents in `specs/002-reduce-to-sbem/`: [plan.md](plan.md),
[spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md).

**Agent skills** (roadmap C-19; spec 001 research R4):

- before writing or changing any module or test that imports `idfkit`, load
  `/idfkit:developing-with-idfkit` and read the smallest reference page that covers the task;
- write and revise every page under `docs/` with `/project-kit:diataxis` (name the mode,
  brief the `project-kit:editor` agent, run the mode's checklist, wire the nav).

**Documentation**: each story carries its own pages, to land in the same pull request as its
code (constitution VI).

**Tests**: included. Constitution VI requires public behaviour to be tested, the spec gives an
independent test for each story, and spec 001's research R3 fixes the three test tiers (002's
use of them: research R16). Within each
story, write the tests first and see them fail before implementing.

**Organisation**: by user story, so each story can be built, tested and shown on its own.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel with the other [P] tasks of its phase (different files, no
  dependency on an unfinished task).
- **[Story]**: the user story the task serves (US1, US2, US3).
- Paths are relative to the root of the `v3` branch (spec 001, research R1–R2), unless a task
  names the SBEM fork (`samuelduchesne/epinterface`, roadmap C-17) or idfkit.

## Path conventions

Single library in src layout (plan.md, Project Structure): `src/archetypal/`, `tests/`,
`verification/`, `docs/`.

---

## Phase 1: Setup (what 002 adds to spec 001's foundation)

**Purpose**: spec 001's foundation is the project every spec is built in (generated with
`/project-kit:new-project`, shared tooling, test tiers, errors, docs site; 001 research R13).
002 adds only its own gates.

- [X] T001 Confirm spec 001's foundation tasks are done on the `v3` branch: project generated
  and linked with cruft, `v2.x` cut, shared tooling and test tiers (001 R1–R3, R9),
  `CLAUDE.md` skill rules (001 R4), docs checks (001 R5), `src/archetypal/errors.py` (001 R8).
  Do not repeat any of it here.
- [X] T002 [P] Add `[tool.idfkit.check]` to `pyproject.toml` (`paths = ["src"]`, `since =
  "22.1"`, `extend-select = ["C004"]`, `fail-on = "warning"`) and run `idfkit check` from
  the `check` target of `Makefile` and as a local hook in `.pre-commit-config.yaml` (research
  R18).
- [X] T003 [P] Add a `pygrep` hook to `.pre-commit-config.yaml` that fails on
  `get_collection`, `.collections`, `objects_by_type`, `get_referenced_object`,
  `schedules_dict` and `get_zone_surfaces` in `src/` (research R18, item 3).
- [X] T004 [P] Edit `.github/workflows/main.yml`: an `integration` job on pull requests
  (EnergyPlus 24.2, Python 3.12, `-m energyplus`); a required job that runs the unit tier
  against the SBEM fork's development branch; a weekly job against upstream epinterface's
  `main`, allowed to fail and reported (roadmap C-14).
- [X] T005 [P] Add `.github/workflows/reference.yml`: weekly, `workflow_dispatch` and on tags
  `v3.*`, running `uv run pytest -m reference` with EnergyPlus 24.2 and uploading
  `verification/` output (plan.md, Tooling configuration).
- [X] T006 [P] Create `src/archetypal/reduction/__init__.py` and
  `src/archetypal/comparison/__init__.py` with module docstrings only, and the test folders
  `tests/integration/`, `tests/reference/`, `tests/fixtures/models/`.
- [X] T007 [P] Add reduction to SBEM to the `Unreleased` section of `CHANGELOG.md`. Docs nav
  entries are added with each page, never ahead of it (001 research R5).

**Checkpoint**: `make check` and `uv run pytest` pass on the empty package.

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: what every story needs: the fork prerequisites, errors, options, typed access to
models and results, schedules, deterministic files and test fixtures.

**⚠️ No user-story work starts before this phase is complete.**

### Upstream prerequisites (SBEM fork, roadmap C-17)

- [X] T008 In the SBEM fork, on topic branch `up-1`, implement UP-1: depend on idfkit instead
  of `archetypal==2.18.10`, make `epinterface.sbem.components` importable without archetypal,
  eppy or a generated Prisma client, and declare PyYAML. Merge it into the fork's `main` and
  open the same change as a pull request upstream.
- [X] T009 In the SBEM fork, on topic branch `up-2`, implement UP-2's blocking part: an
  archetype with several zone groups, each a zone definition with its floor-area share, plus
  building-level geometry characteristics and attic and basement assumptions. Merge into the
  fork's `main` and open it upstream.
- [ ] T010 Tag the fork (`vX.Y.Z.post1`), set `[tool.uv.sources]` in `pyproject.toml` to that
  tag and the `epinterface` lower bound to X, run `uv lock`, and record the tag in
  `CHANGELOG.md`.
- [X] T011 [P] Draft the idfkit issues for UP-6 (`Schedule:Year` fields parsed as `'1.0'`,
  typed `start_month: int` not honoured) and UP-7 (typed readers for the static SQLite
  tables) in `specs/002-reduce-to-sbem/upstream/idfkit-issues.md`, for the user to file.

### Tests for the foundation

- [X] T012 [P] Test 002's errors in `tests/unit/test_errors.py`: each derives from 001's
  `InputError` or `ArchetypalError` and starts its message with the input at fault;
  `MissingResults` lists items and suggests `simulate=True`; `UnsupportedEnergyPlusVersion`
  names the supported range and `idfkit.migration.migrate`.
- [X] T013 [P] Test options in `tests/unit/test_options.py`: `Layout` coarseness order
  (`SPACE_USE_EXPOSURE` ≤ `SPACE_USE`, `CORE_PERIMETER` ≤ `SINGLE_ZONE`; `SPACE_USE` and
  `CORE_PERIMETER` not comparable; `Layout.is_strictly_finer(a, b)`, which `merge` uses);
  `small_group_threshold` "a share of conditioned floor area in [0, 1)" is enforced;
  `ReductionOptions` is frozen.
- [X] T014 [P] Test the static-table rows in `tests/unit/test_sql_tables.py` against the
  committed fixture SQLite files: one typed row per record, types converted and checked at the
  boundary, a clear error on an unexpected column type.
- [X] T015 [P] Test `RESULTS_REQUIREMENTS` in `tests/unit/test_requirements.py`: it lists
  exactly the rows of `contracts/results-requirements.md` (parse the Markdown table); the
  check on a fixture with outputs removed names each one, with its `Output:Variable` or
  `Output:Meter` IDF text; items that do not apply (no `WaterUse:Equipment`) are not required.
- [X] T016 [P] Test sources in `tests/unit/test_sources.py`: a 9.6 document raises
  `UnsupportedEnergyPlusVersion`; model and results with different zone names raise
  `ModelResultsMismatch` naming the difference; model and results versions must agree;
  SHA-256 of model, results and weather are recorded.
- [X] T017 [P] Test schedules in `tests/unit/test_schedules.py`: the run-period calendar
  starts on the `RunPeriod` start weekday and marks `RunPeriodControl:SpecialDays`;
  evaluation is memoised by name; projection onto month × weekday conserves each month's
  energy exactly and is linear (projecting a weighted sum equals the weighted sum of
  projections, a hypothesis property); the public `schedule_compact(year)` returns a
  `Schedule:Compact` with one `Through:` per run of equal months and `For:` blocks Monday to
  Sunday, which idfkit evaluates to the same hourly values as the `YearComponent`, for every
  schedule of a committed fixture archetype (FR-023, contracts/python-api.md).
- [X] T018 [P] Test the UP-6 bridge in `tests/unit/test_bridges.py`: a `Schedule:Year` loaded
  from a file evaluates after normalisation, the original object is not modified, and a
  marked test fails once the installed idfkit no longer needs the bridge (reminder to remove
  it).
- [X] T019 [P] Test deterministic files in `tests/unit/test_io.py`: UTF-8, two-space indent,
  floats as shortest round-trip `repr`, base64 little-endian float64 profiles with their
  length, no timestamp, byte-identical output on repeat, and `write` refusing to overwrite
  unless asked.

### Implementation of the foundation

- [X] T020 [P] Extend `src/archetypal/errors.py` (spec 001, research R8): `ReductionError`
  under `InputError`, with `NoConditionedZones`, `MissingResults`, `ModelResultsMismatch`,
  `UnsupportedEnergyPlusVersion`; and `NotComparableError` under `ArchetypalError`. Each
  takes the input at fault first (plan.md, Source Code; contracts/python-api.md).
- [X] T021 [P] Implement `src/archetypal/reduction/options.py`: `Layout` `StrEnum` with members
  `SPACE_USE_EXPOSURE` (default), `SPACE_USE`, `CORE_PERIMETER`, `SINGLE_ZONE`, a group-key
  function per member and a partial order by coarseness; `ReductionOptions`, a frozen
  pydantic model with `layout: Layout = Layout.SPACE_USE_EXPOSURE`, `small_group_threshold:
  float = 0.05` ("a share of conditioned floor area in [0, 1)"), and `space_use_mapping:
  Mapping[str, str] | None = None` (data-model.md, Layout and ReductionOptions).
- [X] T022 [P] Implement `src/archetypal/reduction/_bridges.py`:
  `normalise_schedule_year(obj) -> ScheduleYear` returning a copy whose start and end month and
  day fields are `int`, with its removal condition (UP-6) in the docstring (plan.md,
  Complexity Tracking).
- [X] T023 [P] Implement `src/archetypal/reduction/_sql_tables.py`: frozen dataclasses
  `ZoneRow`, `SurfaceRow`, `ConstructionRow`, `ConstructionLayerRow`, `MaterialRow`,
  `NominalLoadRow` (one shape for every `Nominal*` gain table, with its kind),
  `NominalInfiltrationRow`, `NominalVentilationRow`, `SimulationRow`, `EnvironmentPeriodRow`,
  and one reader per table over `SQLResult.query`. This is the only module that calls
  `query` (research R18; removal condition UP-7).
- [X] T024 Implement `src/archetypal/reduction/requirements.py`: `ResultRequirement`
  (item, key, frequency, used for, IDF text, applies-to predicate), the constant
  `RESULTS_REQUIREMENTS` with every row of `contracts/results-requirements.md`, and
  `check_results(source) -> tuple[ResultRequirement, ...]` returning the missing items
  (research R2).
- [X] T025 Implement `src/archetypal/reduction/sources.py`: `RunPeriodInfo` and `SourceData`
  (fields of data-model.md, SourceData); loading from a path or document with
  `idfkit.load_idf`/`load_epjson`, narrowing with `as_version(doc, since="22.1")`, reading
  results with `SQLResult`; validation in the order of data-model.md (version, results
  requirements, zone names, then conditioned zones later in classify); SHA-256 of each file
  (research R3, R18).
- [X] T026 Implement `src/archetypal/reduction/schedules.py`: the `Profile` alias (float64
  array, 8760 or 8784 values); a typed `AnySchedule` index built from the per-type accessors
  (`doc.schedule_compacts`, `doc.schedule_years`, `doc.schedule_constants`,
  `doc.schedule_files`, …); evaluation through `idfkit.schedules.values` at hourly resolution
  on the run-period calendar, memoised by name, with `Schedule:Year` passed through
  `_bridges.normalise_schedule_year`; `project(profile)` onto SBEM's month × weekday
  representative days; conversion to epinterface `YearComponent`/`WeekComponent`/
  `DayComponent`; and the public `schedule_compact(year, *, name=None)`, turning any
  `YearComponent` into `Schedule:Compact` text (research R5, FR-023).
- [X] T027 [P] Implement `src/archetypal/io.py`: deterministic JSON writing and reading for
  `<name>.sbem.json` (epinterface's `model_dump_json`, indented, keys in model order) and
  `<name>.report.json`, with the encoding rules of `contracts/reduction-report.md`
  (research R14).
- [X] T028 Build the unit fixtures in `tests/fixtures/models/` and the script that regenerates
  their results, `tests/fixtures/regenerate.py` (needs EnergyPlus 24.2; not run in the unit
  tier):
  - `three_zone.idf`: one core and two perimeter zones, two space uses;
  - `ten_zone_multipliers.idf`: a typical floor with `Zone` multiplier 10 and a `ZoneList`
    multiplier, a return plenum, an attic, `WaterUse:Equipment` with and without a zone, an
    air loop with a fan, heat recovery and an economiser, a heat-pump coil and a boiler;
  - `ten_zone_explicit.idf`: the same building with every floor drawn (acceptance scenario 3
    of US1);
  - `bar_building.idf`: perimeter zones only (US2 scenario 3), with `Daylighting:Controls` and
    `Exterior:Lights` for R20;

  each with a `.sql` result cut down to the R2 outputs, a few MB each, committed.

**Checkpoint**: the foundation's unit tests pass; `make check` is clean.

---

## Phase 3: User Story 1 — Reduce a detailed model to an archetype (Priority: P1) 🎯 MVP

**Goal**: `reduce(model, results)` returns a valid SBEM archetype at the default layout
(space use × exposure) and a reduction report that accounts for every zone and every
parameter.

**Independent test**: reduce each fixture; the archetype validates with epinterface alone,
every conserved total matches the detailed model within 0.1 % (exactly when 0), and the report
accounts for every zone (spec US1, SC-005, SC-006).

### Tests for User Story 1 (write first, see them fail)

- [ ] T029 [P] [US1] Test inventory in `tests/unit/test_inventory.py`: one `ZoneRecord` per
  zone of the fixture; `multiplier` = `Zones.Multiplier × Zones.ListMultiplier`; floor areas
  are one copy; `space_type` set only when all the zone's spaces agree.
- [ ] T030 [P] [US1] Test classification in `tests/unit/test_classify.py`: exposure is
  perimeter only for an outdoor wall (60°–120° tilt) or a window, never for a roof, exposed
  floor or ground contact (FR-006); conditioned, attic, basement and excluded roles follow R8;
  space use follows the three tiers of FR-007 and records its source; a hypothesis property
  shuffles zone order and checks the classification is unchanged; rounding noise below 6
  significant figures does not split a space use.
- [ ] T031 [P] [US1] Test the ledger in `tests/unit/test_ledger.py` with hypothesis on
  synthetic ledgers: `+` is associative and commutative, members are a sorted union, every
  total is a sum, and `from_zone` applies the multiplier exactly once.
- [ ] T032 [P] [US1] Test the envelope in `tests/unit/test_envelope.py`: surface classes by
  tilt and boundary; eight 45° orientation sectors; the equivalent three-layer construction
  reproduces UA ÷ A with epinterface's films and the inner and outer heat capacities exactly;
  windows conserve area, UA, Σ A·SHGC and Σ A·VT by orientation; a plenum's roof and walls go
  to the zones it shares interzone surfaces with, in proportion to shared area (FR-013).
- [ ] T033 [P] [US1] Test airflow in `tests/unit/test_airflow.py`: infiltration conserves
  design flow and hourly profile and carries the flow-weighted coefficients; ventilation's
  peak × fraction schedule reproduces the hourly profile; HRV and economiser take the
  category with the largest outdoor-air share (FR-018, FR-019).
- [ ] T034 [P] [US1] Test thermostats in `tests/unit/test_thermostats.py`: only members with a
  setpoint within 5–35 °C at some hour enter a mode's area-weighted mean; the unheated and
  uncooled area shares are reported (FR-020).
- [ ] T035 [P] [US1] Test hot water in `tests/unit/test_hotwater.py`: volume and heat (volume ×
  rise) are conserved; equipment without a zone is allocated by occupant-hours; supply
  temperature is mean mains plus the volume-weighted rise (FR-021).
- [ ] T036 [P] [US1] Test efficiency in `tests/unit/test_efficiency.py`: hourly attribution of
  consumption to delivery by mode; pumps and heat rejection folded into `DistributionCOP`;
  standby reported as unattributed; the constrained linear fit reproduces annual consumption
  exactly and gives `b ≈ 0` for a boiler; refitting from merged sums equals fitting the merged
  hours; a group with no delivery takes the rated efficiency from *Equipment Summary*
  (FR-022, R12).
- [ ] T037 [P] [US1] Test fans in `tests/unit/test_fans.py`: zone-equipment fans belong to
  their zone; air-loop fans are split by hourly inlet-node mass flow; specific fan power ×
  detailed volume = detailed fan energy; the effective supply ΔT per mode follows R19; the
  share of volume without demand is reported (FR-022a).
- [ ] T038 [P] [US1] Test grouping in `tests/unit/test_grouping.py` at the default layout: one
  group per (space use, exposure); groups below the threshold merge into the most similar
  group of the same exposure, smallest first, ties broken by key; a small group with nothing
  to merge into is kept; pre-threshold groups are kept at the finest key (FR-008, FR-011).
- [ ] T039 [P] [US1] Test conversion in `tests/unit/test_to_sbem.py`: every derivation rule of
  data-model.md produces its SBEM field from a synthetic ledger; the archetype validates as the
  fork's multi-group model; every set leaf field has a `parameters[]` entry with its rule id;
  the number of storeys is right for `ten_zone_multipliers` (one typical floor × 10) and
  `three_zone` (R6, FR-024).
- [ ] T040 [P] [US1] Test the report in `tests/unit/test_report.py`: invariants 1–7 of
  `contracts/reduction-report.md` on the fixture reductions, and the published JSON Schema
  validates the written file.
- [ ] T041 [P] [US1] Write the conservation suite `tests/unit/test_conservation.py` (quickstart
  scenario 5): every total of FR-014–FR-019, FR-021, FR-022 and FR-022a matches the detailed
  model within 0.1 %, and exactly where the detailed total is 0, on synthetic ledgers
  (hypothesis) and on the fixtures.
- [ ] T042 [P] [US1] Write the end-to-end tests `tests/unit/test_reduce.py`: acceptance
  scenarios 1, 2 and 4 of US1 (shares sum to 100 %, every zone in one group or excluded with
  a reason; operating rooms and corridors apart; two runs byte-identical); each FR-029 refusal
  writes no file; quickstart scenarios 2 and 3.
- [ ] T043 [P] [US1] Write `tests/unit/test_multipliers.py`: acceptance scenario 3 of US1,
  comparing `ten_zone_multipliers` with `ten_zone_explicit`: groups, floor areas and every
  FR-014–FR-021 total within 0.1 %; FR-022 and FR-022a values compared only within the
  difference of the two simulations.
- [ ] T044 [P] [US1] Write `tests/unit/test_features.py`: on `bar_building`, the daylighting
  controls and exterior lights of the fixture appear in `not_represented[]` with the zones they
  affect, and exterior lights with their annual energy; on `three_zone`, no entry comes from
  `UNSUPPORTED_FEATURES` (FR-026, R20).

### Implementation for User Story 1

- [ ] T045 [US1] Implement `src/archetypal/reduction/inventory.py`: `ZoneRecord` (with `min_z`),
  `SurfaceRecord`, `GainRecord`, `AirflowRecord`, `ThermostatRecord`, `HotWaterRecord` with
  the fields and sources of data-model.md (ZoneRecord); built from `_sql_tables` rows, the
  tabular Envelope Summary (U with films, SHGC, VT) and the typed model (`doc.spaces`,
  `doc.zone_control_thermostats`, `doc.water_use_equipments`). No multiplier is applied here.
- [ ] T046 [US1] Implement exposure and roles in `src/archetypal/reduction/classify.py`:
  `ClassifiedZone`; exposure per R7; conditioned per R8 (thermostat setpoint enabling a mode at
  any hour, or non-zero delivered energy); attic and basement per R8's geometric rules;
  `NoConditionedZones` when no zone is conditioned.
- [ ] T047 [US1] Implement space use in `src/archetypal/reduction/classify.py`: user mapping,
  then `Space.space_type`, then the signature of R4 (gain densities to 6 significant figures,
  schedule digests of values rounded to 6 decimals, setpoint digests, outdoor air per area and
  per person); label `use:<smallest zone name>`; zones sorted by name first;
  `space_use_source` recorded.
- [ ] T048 [US1] Implement `src/archetypal/reduction/ledger.py`: `EnvelopeTotals`,
  `WindowTotals`, `GainTotals`, `AirflowTotals`, `WeightedProfile`, `HotWaterTotals`,
  `EnergyTotals` (with `eir_sums`), `FanTotals`, and `GroupLedger` with every field of
  data-model.md (GroupLedger); `GroupLedger.from_zone(zone, schedules)` applying the
  multiplier once; `__add__` as field-wise addition. The module calls the per-domain
  functions of T049–T054 to fill each field.
- [ ] T049 [P] [US1] Implement `src/archetypal/reduction/envelope.py`: surface classes and
  orientation sectors (R6), per-class area, UA and inner/outer capacity, window totals by
  orientation, internal mass, excluded-zone envelope assignment, and
  `equivalent_construction(totals)`, which returns a three-layer epinterface assembly
  reproducing UA and both capacities.
- [ ] T050 [P] [US1] Implement `src/archetypal/reduction/airflow.py`: infiltration totals and
  coefficient sums from `NominalInfiltration`; outdoor-air totals from the hourly output;
  HRV and economiser attribution through each air loop's `HeatExchanger:AirToAir:*` and
  `Controller:OutdoorAir`, read with literal keys (R9, R18).
- [ ] T051 [P] [US1] Implement `src/archetypal/reduction/thermostats.py`: setpoint schedules
  by dispatching with `match` on the `Literal` `control_n_object_type` of
  `ZoneControl:Thermostat`; the 5–35 °C band; heated and cooled weighted profiles (R10).
- [ ] T052 [P] [US1] Implement `src/archetypal/reduction/hotwater.py`: volume and heat
  profiles per `WaterUse:Equipment`; allocation of zoneless equipment by occupant-hours,
  recorded for the report (R11).
- [ ] T053 [P] [US1] Implement `src/archetypal/reduction/efficiency.py`: hourly attribution of
  `Heating:*` and `Cooling:*` meters to zones by delivered energy; pumps and heat rejection
  split by the hour's delivered modes into the distribution share; unattributed consumption;
  the additive `eir_sums`; `fit_eir(sums) -> (a, b, t_ref)` by constrained least squares with
  the annual consumption exact; rated efficiency from *Equipment Summary* for a mode with no
  delivery (R12).
- [ ] T054 [P] [US1] Implement `src/archetypal/reduction/fans.py`: fan energy and
  standard-density air volume per zone (zone-equipment fans to their zone, air-loop fans by
  hourly inlet-node mass flow), per-mode volume and delivered energy, volume without demand;
  `specific_fan_power` and `effective_supply_delta` (R19).
- [ ] T055 [P] [US1] Implement `src/archetypal/reduction/features.py`: the
  `UNSUPPORTED_FEATURES` table of research R20 (object type, what it does, the parameter its
  effect is folded into or none), read with literal keys only (R18), and
  `find_unsupported(source) -> tuple[NotRepresented, ...]` with affected zones and, where the
  results give it, annual energy.
- [ ] T056 [US1] Implement `src/archetypal/reduction/grouping.py` for the default layout:
  ledgers summed by group key in sorted key order; pre-threshold groups kept at the finest key
  (space use, exposure) whatever the layout; the threshold
  loop with the similarity distance of data-model.md (gain densities, annual gain hours,
  setpoint means, outdoor air per area, hot water per area, each scaled by the building-wide
  value), merges recorded (FR-008, FR-011).
- [ ] T057 [US1] Implement `src/archetypal/reduction/to_sbem.py`: one function per SBEM
  component following the derivation table of data-model.md, each returning its value and rule
  id; until UP-8 is released, fans are folded into `DistributionCOP` and the fan end use and the
  efficiency slope are recorded as not represented (R12, R19); until UP-2's extra fields are
  released, per-orientation ratios, the infiltration schedule, numeric HRV effectiveness and
  holiday and design-day profiles are recorded as not represented (R5, R6, R9). Set the number
  of storeys by rule `geometry.storeys` (R6) and record the unrounded ratio in the report's
  `building` block. Validate the result as the fork's archetype model and raise `ReductionError`
  with epinterface's message on failure.
- [ ] T058 [US1] Implement `src/archetypal/reduction/report.py`: pydantic models for
  `ReductionReport` with every field of data-model.md (ReductionReport), `schema_version =
  "1.0"`, the `building` block, `not_represented[]` gathered from the folding modules and
  `features.find_unsupported`, ledgers serialised with base64 profiles, and
  `report_json_schema()` returning the published JSON Schema.
- [ ] T059 [US1] Implement `reduce()` and `Reduction` in `src/archetypal/reduction/__init__.py`
  with the signature of `contracts/python-api.md`: load and validate sources, inventory,
  classify, group, build ledgers, convert, build the report; raise before keeping any work
  (FR-029); `Reduction.write(directory, name, *, overwrite=False)` and `Reduction.read(...)`
  through `io.py`; export `RESULTS_REQUIREMENTS`.
- [ ] T060 [US1] Implement the single run for `reduce(..., simulate=True)` in
  `src/archetypal/reduction/requirements.py`: copy the model, add the missing outputs from
  `RESULTS_REQUIREMENTS`, run once with `idfkit.simulation.simulate(...,
  cache=SimulationCache())`, require `weather` (FR-002).
- [ ] T061 [US1] Re-export `reduce`, `Layout`, `ReductionOptions` and the errors from
  `src/archetypal/__init__.py`, export `Reduction`, `RESULTS_REQUIREMENTS` and
  `schedule_compact` from `src/archetypal/reduction/__init__.py`, and mark every other module
  of `archetypal.reduction` private
  (contracts/python-api.md, Stability).
- [ ] T062 [P] [US1] Write `tests/integration/test_single_run.py` (`@pytest.mark.energyplus`):
  `reduce(model, simulate=True, weather=epw)` on `three_zone.idf` runs EnergyPlus once and
  produces the same archetype as reducing with the committed results (quickstart scenario 6).
- [ ] T063 [P] [US1] Write `tests/integration/test_epinterface_build.py`
  (`@pytest.mark.energyplus`): epinterface builds and simulates each fixture's archetype
  without modification (FR-003).
- [ ] T064 [P] [US1] Write `docs/explanation/reduction.md`: what reduction conserves and why
  (FR-014–FR-024), exposure and space use, representative days, equivalent constructions,
  specific fan power and the temperature-dependent COP, and what SBEM cannot hold (FR-030).
- [ ] T065 [P] [US1] Write `docs/how-to/reduce-a-model.md`: reduce with existing results or
  with the single run, choose the threshold, supply a space-use mapping; its code examples run
  against the unit fixtures.
- [ ] T066 [P] [US1] Generate `docs/reference/reduction-report.md` from `report_json_schema()`
  and `docs/reference/results-requirements.md` from `RESULTS_REQUIREMENTS`, and add
  `docs/reference/api/reduction.md` (mkdocstrings for `archetypal.reduction`).

**Checkpoint**: US1 is complete and testable alone; quickstart scenarios 1, 2, 3, 5 and 6 pass.

---

## Phase 4: User Story 2 — Choose how coarse the archetype is (Priority: P2)

**Goal**: coarser layouts (space use only, core/perimeter, single zone), directly or by
merging a finer archetype, with the same result either way.

**Independent test**: reduce a fixture directly to core/perimeter, and separately reduce it to
the default layout and merge; the archetypes match (spec US2, SC-007).

### Tests for User Story 2

- [ ] T067 [P] [US2] Extend `tests/unit/test_grouping.py`: each layout's group keys; threshold
  applied once to the requested layout's groups, never to an intermediate layout's;
  pre-threshold groups stay at the finest key under every layout;
  `merged_distinctions` has one entry per resulting group with `into_key`, sorted `from_keys`
  and `lost`; the bar building at
  core/perimeter gives a perimeter group only with a report note (US2 scenarios 1 and 3).
- [ ] T068 [P] [US2] Write `tests/unit/test_merge.py`: a hypothesis property that
  `merge(reduce(m, r, options=o), L)` equals `reduce(m, r,
  options=o.model_copy(update={"layout": L}))` within 0.1 % for every pair of layouts where `L`
  is not strictly finer, including `SPACE_USE` → `CORE_PERIMETER` (FR-010, SC-007, spec 003);
  `merge` refuses a strictly finer target and a reduction without a report; merging works from
  files read back with `Reduction.read` (quickstart scenario 4).

### Implementation for User Story 2

- [ ] T069 [US2] Extend `src/archetypal/reduction/grouping.py` with the `SPACE_USE`,
  `CORE_PERIMETER` and `SINGLE_ZONE` keys, the eligibility rule without exposure ("the most
  similar group"), and the list of merged distinctions (FR-009, FR-011).
- [ ] T070 [US2] Implement `merge(reduction, layout, *, small_group_threshold=None)` in
  `src/archetypal/reduction/__init__.py`: rebuild ledgers from the report's
  `pre_threshold_groups` (always at the finest key), refuse a strictly finer target, regroup by
  the target key, threshold once, convert and report through
  the same path as `reduce` (data-model.md, Grouping and thresholding, step 4).
- [ ] T071 [US2] Make `Reduction.read` in `src/archetypal/reduction/__init__.py` restore full
  ledgers, profiles included, from `<name>.report.json` (by default beside
  `<name>.sbem.json`, the name stripped of `.sbem.json`), so `merge` works without the model
  (report invariant 5).
- [ ] T072 [US2] Re-export `merge` from `src/archetypal/__init__.py`.
- [ ] T073 [P] [US2] Write `docs/how-to/merge-an-archetype.md` and add choosing a layout to
  `docs/how-to/reduce-a-model.md`; code examples run against the unit fixtures.

**Checkpoint**: US1 and US2 both pass alone; quickstart scenario 4 passes.

---

## Phase 5: User Story 3 — Confirm the archetype behaves like the building (Priority: P3)

**Goal**: `compare(detailed, archetype)` reports each end use, total site energy and peaks
with their difference and whether they meet the targets, and refuses incomparable results.

**Independent test**: compare a fixture's detailed results with its archetype's; every end use
and peak is reported and flagged against SC-001–SC-003; mismatched runs are refused (spec US3).

### Tests for User Story 3

- [ ] T074 [P] [US3] Write `tests/unit/test_comparison.py` on committed result fixtures: rows
  for total site energy, every end use by fuel of FR-027 and both peaks; `within_target` is
  `None` where SC-002's 5 % share or SC-003's 10 % peak rule excludes the metric; pumps and
  heat rejection are added to heating and cooling by hourly delivered mode before comparing
  (SC-002); fans are compared on their own; pumps and heat rejection still appear as
  reported, with `within_target = None`, and heating and cooling appear both as reported and
  with them added (data-model.md, ComparisonResult; FR-027).
- [ ] T075 [P] [US3] Extend `tests/unit/test_comparison.py` with refusals: different weather,
  run period, unit system, timestep or reporting frequency each raise `NotComparableError`
  naming every difference (FR-028, US3 scenario 2).

### Implementation for User Story 3

- [ ] T076 [US3] Implement `src/archetypal/comparison/results.py`: end uses by fuel from the
  *Annual Building Utility Performance Summary*; peaks as the maximum of summed heating and
  cooling meters at the common frequency; the pump and heat-rejection allocation of R13;
  comparability checks from the `Simulations` and `EnvironmentPeriods` tables and the optional
  EPW SHA-256 (R13).
- [ ] T077 [US3] Implement `compare()`, `ComparisonResult` and `AcceptanceTargets` (defaults:
  SC-001 5 %, SC-002 10 % above a 5 % share, SC-003 15 % above a 10 % share) in
  `src/archetypal/comparison/__init__.py` with the signature of `contracts/python-api.md`, and
  re-export `compare` from `src/archetypal/__init__.py`.
- [ ] T078 [P] [US3] Write `docs/how-to/compare-results.md` and add `archetypal.comparison` to
  `docs/reference/api/reduction.md` (created by T066; create it if US3 lands first); code
  examples run against the unit fixtures.

**Checkpoint**: all three stories pass alone.

---

## Phase 6: Reference evidence (SC-001–SC-008)

**Purpose**: the measured proof that reduction meets its targets and beats v2 (constitution
IV). Depends on US1–US3.

- [ ] T079 [P] Write `verification/reference_set.toml`: the 16 DOE commercial prototypes in a
  hot, a mixed and a cold climate zone, plus the DOE residential single-family prototype, with
  download URLs and SHA-256 (49 buildings; spec, Reference set).
- [ ] T080 [P] Write `verification/run_v2_baseline.py`: in a separate environment with
  `archetypal<3`, reduce each reference building with v2 and record its errors and run time
  (SC-004, SC-008).
- [ ] T081 Write `verification/report.py`: `--fetch` downloads and checks the set; tabulates
  SC-001–SC-008 per building and for the set; writes the evidence page used by the docs; fixes
  and records the benchmark machine (spec, Assumptions).
- [ ] T082 Write `tests/reference/test_reference_set.py` (`@pytest.mark.reference`): reduce
  every building at every layout without error and account for every zone (SC-006); conserved
  totals within 0.1 % (SC-005); direct and merged layouts within 0.1 % (SC-007); simulate
  detailed and archetype and assert SC-001–SC-003; compare with the v2 baseline at
  core/perimeter (SC-004).
- [ ] T083 [P] Write `tests/reference/test_performance.py` (`@pytest.mark.reference`): the
  largest reference building reduces in under 10 s excluding simulation and evaluates its
  schedules in at most 7 s (R5); the set reduces at least 10 times faster than v2 (SC-008).
  If the schedule budget fails, file the faster evaluation under UP-5 before falling back to
  R2's "Schedule Value" outputs.

**Checkpoint**: quickstart scenario 7 passes, except SC-002 for fans until Phase 7 is done.

---

## Phase 7: Upstream follow-ups (each when its fork tag or idfkit release exists)

**Purpose**: replace each "not represented" entry and each bridge as its upstream item is
released (constitution I). Each task is independent of the others.

- [ ] T084 In the SBEM fork, on topic branch `up-8`, implement UP-8: `SpecificFanPower` and
  ideal-loads maximum heating and minimum cooling supply-air temperatures on
  `ThermalSystemComponent` or the zone's conditioning, a fan end use equal to specific fan
  power × hourly supply air volume, and an energy input ratio linear in outdoor temperature;
  tag the fork, open it upstream, and update `[tool.uv.sources]`.
- [ ] T085 After T084, write specific fan power, supply-air temperature limits and the
  efficiency slope in `src/archetypal/reduction/to_sbem.py` (rules `fans.energy_per_volume`,
  `fans.effective_supply_delta`, `efficiency.eir_linear`), stop folding fans into
  `DistributionCOP`, remove those `not_represented` entries, and update
  `tests/unit/test_to_sbem.py` and `tests/unit/test_conservation.py`.
- [ ] T086 In the SBEM fork, implement UP-2's extra fields (per-orientation envelope and window
  ratios, infiltration schedule, numeric heat-recovery effectiveness (sensible and latent),
  holiday and design-day slots in `WeekComponent`, save and load helpers with a schema
  version), one topic branch each; tag the fork and open each upstream.
- [ ] T087 After T086, for each field released, write it in
  `src/archetypal/reduction/to_sbem.py`, add holiday and design-day blocks to
  `schedule_compact` in `src/archetypal/reduction/schedules.py`, switch `io.py` to the
  fork's save and load helpers, and remove the matching `not_represented` entries and tests.
- [ ] T088 [P] When idfkit releases UP-6, delete `src/archetypal/reduction/_bridges.py` and
  `tests/unit/test_bridges.py`, and raise the idfkit lower bound in `pyproject.toml`.
- [ ] T089 [P] When idfkit releases UP-7, replace `src/archetypal/reduction/_sql_tables.py`
  with idfkit's typed readers, delete it and `tests/unit/test_sql_tables.py`, and raise the
  idfkit lower bound.

**Checkpoint**: SC-002 holds for fans; spec 002 can be marked implemented (plan.md, Upstream
dependencies).

---

## Phase 8: Polish and cross-cutting concerns

- [ ] T090 [P] Complete the `Unreleased` section of `CHANGELOG.md`: added functions, the report
  file, the results requirements, and each "not represented" item that waits on an upstream
  item.
- [ ] T091 Run every quickstart scenario, `make check` and the unit tier's time budget, and fix
  what fails.
- [ ] T092 Mark 002 implemented in `.specify/memory/roadmap.md` once SC-001–SC-008 hold and its
  blocking items are released (plan.md, Upstream dependencies; roadmap C-20): UP-1, UP-2's zone
  groups and UP-8 by the fork, and UP-6 and UP-7 by idfkit (T088, T089 done); milestone M1
  (`v3.0.0aN`) waits for 001 and 003 (roadmap C-18).

---

## Dependencies and execution order

### Phases

- **Setup (1)**: after spec 001's foundation (T001).
- **Foundational (2)**: after Setup. Blocks every story. T008–T010 (the fork) block only the
  tasks that import epinterface (T026's conversion to `YearComponent`, T039, T049, T057); the
  rest can start while the fork work is under way.
- **US1 (3)**: after Foundational.
- **US2 (4)**: after US1's grouping, ledger, report and `reduce` (T048, T056, T058, T059).
- **US3 (5)**: after Foundational only. Its unit tests use committed results; it is
  independent of US1 and US2 and can be built in parallel with them.
- **Reference evidence (6)**: after US1, US2 and US3.
- **Upstream follow-ups (7)**: each task when its upstream item exists; T085 after T084, T087
  after T086.
- **Polish (8)**: after Phases 3–7; T092 last.

### Within each story

- Tests first, failing.
- `inventory` → `classify` → domain modules (`envelope`, `airflow`, `thermostats`, `hotwater`,
  `efficiency`, `fans`, `features`) → `ledger` → `grouping` → `to_sbem` and `report` → `reduce`.
- T049–T055 are separate files and can run in parallel once T045 and the ledger types of T048
  exist; T048's `from_zone` is finished after them.

### Parallel opportunities

- Setup: T002–T007, after T001.
- Foundational: T011–T019 (tests), then T020–T023 and T027.
- US1: T029–T044 (tests), T049–T055 (domain modules), T062–T063 (integration tests), T064–T066
  (docs).
- US3 alongside US1 and US2.
- Phase 6: T079, T080, T083.
- Phase 7: T088 and T089, whenever idfkit releases.
- Docs: T073 in US2 and T078 in US3, alongside their implementation tasks.

## Parallel example: User Story 1

```text
# Tests, all at once:
T029 tests/unit/test_inventory.py      T036 tests/unit/test_efficiency.py
T030 tests/unit/test_classify.py       T037 tests/unit/test_fans.py
T031 tests/unit/test_ledger.py         T038 tests/unit/test_grouping.py
T032 tests/unit/test_envelope.py       T039 tests/unit/test_to_sbem.py
T033 tests/unit/test_airflow.py        T040 tests/unit/test_report.py
T034 tests/unit/test_thermostats.py    T041 tests/unit/test_conservation.py
T035 tests/unit/test_hotwater.py       T042 tests/unit/test_reduce.py, T043 test_multipliers.py
T044 tests/unit/test_features.py

# After T045 and T048's totals types, the domain modules:
T049 envelope.py  T050 airflow.py  T051 thermostats.py
T052 hotwater.py  T053 efficiency.py  T054 fans.py  T055 features.py
```

## Implementation strategy

### MVP: User Story 1

1. Spec 001's foundation, then Setup and Foundational, including the fork's UP-1 and UP-2 tag.
2. User Story 1, with fans folded into `DistributionCOP` until UP-8.
3. **Stop and validate**: quickstart scenarios 1, 2, 3, 5 and 6. The result already replaces
   v2's reduction at the default layout.

### Incremental delivery

1. US1: reduction at the default layout (MVP).
2. US2: coarser layouts and merging; core/perimeter feeds spec 003 (UMI).
3. US3: comparison; can be built alongside US1 and US2.
4. Reference evidence: SC-001–SC-008 measured, v2 baseline included.
5. Upstream follow-ups as the fork and idfkit release; UP-8 completes SC-002 for fans.
6. Polish; 002 joins milestone M1 with 001 and 003.

Each step ships with its documentation pages (constitution VI).

### Notes

- Each task's tests fail before its implementation.
- Commit after each task or logical group.
- No task publishes to PyPI (roadmap C-18).
