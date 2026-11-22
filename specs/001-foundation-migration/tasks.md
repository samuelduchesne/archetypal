---

description: "Tasks for spec 001: archetypal 3 foundation and migration from v2"
---

# Tasks: archetypal 3 foundation and migration from v2

**Input**: design documents in `specs/001-foundation-migration/`: [plan.md](plan.md),
[spec.md](spec.md), [research.md](research.md), [data-model.md](data-model.md),
[contracts/](contracts/), [quickstart.md](quickstart.md).

**Agent skills** (roadmap C-19; research R4):

- generate the project with `/project-kit:new-project`; later template updates go through
  `/project-kit:upgrade-project`;
- before writing or changing any module or test that imports `idfkit`, load
  `/idfkit:developing-with-idfkit` and read the smallest reference page that covers the task;
- write and revise every page under `docs/` with `/project-kit:diataxis` (name the mode,
  brief the `project-kit:editor` agent, run the mode's checklist, wire the nav).

**Documentation**: each story carries its own pages, to land in the same pull request as its
code (constitution VI).

**Tests**: included. Constitution VI requires every public behaviour to be tested, and the
spec's success criteria are automated checks (SC-001–SC-008). Within each story, write the
tests first and see them fail before implementing.

**Order of work** (research R13): Phases 1 and 2 are the foundation every v3 spec is built
in; do them before any 002 or 003 code. Phases 3–5 wrap what 002 and 003 deliver, so they
come after those specs' public functions exist.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: can run in parallel with the other [P] tasks of its phase (different files, no
  dependency on an unfinished task).
- **[Story]**: the user story the task serves (US1, US2, US3).
- Paths are relative to the repository root on the `v3` branch (research R2), unless a task
  names `v2.x` or a scratch folder.

## Path conventions

The template's src layout (plan.md, Project Structure): `src/archetypal/`, `tests/`,
`verification/`, `docs/`.

---

## Phase 1: Setup (the generated project)

**Purpose**: generate the project, carry it onto the `v3` branch and set the shared tooling
(research R1–R4, R9).

- [ ] T001 Cut the `v2.x` branch from the `v2.18.11` release commit and push it. It keeps v2's
  poetry, Sphinx and Read the Docs setup and receives security fixes only (FR-020, R2, R11).
- [X] T002 Run `/project-kit:new-project` (Python) with a scratch folder outside the
  repository as the parent, and the answers of research R1, step 1: `project_name` archetypal,
  description "Create, translate and codify building energy archetypes on SBEM.", GitHub
  handle samuelduchesne, `layout` src, `minimum_python_version` 3.10,
  `development_python_version` 3.12, `type_checker` pyright, `publish_to_pypi` true,
  `dockerfile` false, `devcontainer` false, `agent_instructions` claude, `agent_profile` full,
  MIT. Ask the maintainer for the author name and email; confirm the preview before creating.
- [X] T003 After T002, cut `v3` from `main` and carry the generated tree onto it
  (research R1, step 3): remove `archetypal/`, `geomeppy/`, `docker/`, `Dockerfile`, `paper/`,
  `install_energyplus.sh`, `poetry.lock`, `tox.ini`, `.readthedocs.yml`, the Sphinx `docs/`
  and the v2 workflows; copy every generated file except `.git/`, `.specify/` and `.claude/`;
  keep the repository's `specs/`, `.specify/` and `.claude/`; put v2's `CHANGELOG.md` history
  below the template's header; keep the copyright holder and years of `LICENSE.md`; delete
  `src/archetypal/foo.py` and `tests/test_foo.py`. Commit as one change and check that
  `uvx cruft check` recognises the template link in `.cruft.json`.
- [X] T004 After T003, edit `pyproject.toml`: `requires-python = ">=3.10,<3.13"`;
  classifiers for 3.10–3.12 only; runtime dependencies `idfkit>=1.3,<2`, `click>=8.1,<9`,
  `pydantic>=2.9,<3`, `numpy>=1.26` (epinterface is added when the fork has its first tag,
  spec 002's fork tasks); development group additions `pytest-timeout`, `hypothesis`,
  `pytest-markdown-docs`, `mkdocs-click`; `uv lock` (research R3).
- [X] T005 After T004, configure ruff in `pyproject.toml`: keep the template's rule
  set, `line-length = 120`, preview format, `future-annotations`; add `D`
  (`pydocstyle.convention = "google"`), `NPY` and `PL` (`pylint.max-args = 8`); per-file ignores
  `tests/*` → `S101`, `D`, `PLR2004` (research R3).
- [X] T006 After T004, set `reportUnknownMemberType`, `reportUnknownVariableType` and
  `reportUnknownArgumentType` to `"error"` in `[tool.pyright]` of `pyproject.toml`, keeping
  `typeCheckingMode = "strict"` and `pythonVersion = "3.10"` (research R3, SC-005).
- [X] T007 After T004, configure pytest in `pyproject.toml`: `strict = true`,
  `testpaths = ["tests"]`, markers `energyplus: needs EnergyPlus 24.2` and `reference:
  reference-set evidence (slow)`, `addopts = "-m 'not energyplus and not reference'
  --durations=15"`, `timeout = 5` (research R3).
- [X] T008 Write `tests/conftest.py`: a `pytest_sessionfinish` hook that fails the default
  selection when it takes more than 120 s; hypothesis profiles `ci` (50 examples, 500 ms
  deadline) and `dev`; per-marker timeouts for `energyplus` (600 s) and `reference` (none)
  (research R3).
- [X] T009 [P] Edit `.github/workflows/main.yml` (research R9): run on pushes to `main` and
  `v3`; unit tests on Python 3.10, 3.11 and 3.12 on Ubuntu and 3.12 on macOS and Windows;
  coverage upload from Ubuntu 3.12; keep `quality` and `check-docs`; add a `docs-examples` job
  running `uv run pytest --markdown-docs docs/ tests/docs/`.
- [X] T010 [P] Edit `.github/workflows/on-release-main.yml` (research R2): the `publish` job
  runs only `if: ${{ !github.event.release.prerelease }}`; `deploy-docs` needs `set-version`
  only, so it runs for every published release and pre-release.
- [X] T011 [P] Add a "Skills to load" section to `CLAUDE.md` with the three rules of
  research R4 (idfkit code, docs pages, template upkeep), and the branch rules of R2.
- [X] T012 [P] Make the `check` target of `Makefile` also run the docs checks (`mkdocs
  build -s` and `tests/unit/test_docs_tags.py`) (research R5).

**Checkpoint**: `uvx cruft check`, `make check` and `uv run pytest` pass on the empty package
(quickstart scenarios 1 and 2).

---

## Phase 2: Foundational (blocking prerequisites)

**Purpose**: what every spec and story needs: errors, the package entry module, the removed
table's type, the docs site and its checks, the install checks.

**⚠️ No user-story work, and no 002 or 003 code, starts before this phase is complete.**

### Tests for the foundation

- [X] T013 [P] Test the error hierarchy in `tests/unit/test_errors.py`: the tree of
  research R8; every error takes the input at fault first and `str(error)` starts with it;
  `RemovedInArchetypal3Error` is also an `ImportError` and an `AttributeError`;
  `OptionalDependencyError` names the extra to install (FR-010).
- [X] T014 [P] Write `tests/unit/test_no_side_effects.py` for import: in a temporary working
  directory with `HOME`, `XDG_*` and `TMPDIR` pointed into it, `import archetypal` (in a
  subprocess) leaves the directory tree unchanged, reads no `ARCHETYPAL_*` variable, and
  leaves the root logger's handlers unchanged (FR-006, SC-006, R10).
- [X] T015 [P] Write `tests/unit/test_docs_tags.py`: every Markdown file under `docs/` has
  front matter `diataxis:` with exactly one of `tutorial`, `how-to`, `reference`,
  `explanation`, and sits in the matching folder (`tutorials/`, `how-to/`, `reference/`,
  `explanation/`); `docs/index.md` is tagged `explanation` (SC-008, contracts/docs-site.md).
- [X] T016 [P] Write `tests/unit/test_install.py`: resolve the default install with
  `uv pip compile pyproject.toml --python-version 3.12` and fail if it contains `eppy`,
  `geomeppy`, `esoreader`, `energy_pandas`, `pyclipper`, `pypoly2tri`, `transforms3d` or
  `shapely`; the wheel built by `uv build` contains no data files (FR-002, FR-004, SC-002,
  R12). Mark it to skip with a reason when offline.
- [X] T017 [P] Write `tests/unit/test_removed_table.py`: every `RemovedCapability`
  has a unique `v2_path`, a non-empty `reason`, and `replacement` set unless `reason` explains
  why there is none (data-model.md, RemovedCapability).

### Implementation of the foundation

- [X] T018 [P] Implement `src/archetypal/errors.py` with the hierarchy of research R8:
  `ArchetypalError(subject, message)`; `InputError`; `UnsupportedFeatureError`;
  `LossyTranslationError(subject, message, report)`, whose `.report` is the report of what
  would have been lost (typed as an object with `losses`, so 001 does not import 003);
  `NotComparableError`; `OptionalDependencyError(subject, extra)`;
  `RemovedInArchetypal3Error`, also deriving from `ImportError` and `AttributeError`. Spec 002
  adds `ReductionError` under `InputError`; spec 003 adds `UmiFormatError` and
  `UmiValidationError` under `InputError`.
- [X] T019 Implement `src/archetypal/__init__.py`: `__version__` from package metadata, a
  `NullHandler` on the `archetypal` logger and nothing else at import (FR-006, R10); leave room
  for the public re-exports of 002 and 003 and the module `__getattr__` of US2.
- [X] T020 [P] Implement `src/archetypal/_optional.py`: `require(module: str, extra: str)`
  importing a module or raising `OptionalDependencyError` naming the extra (FR-005, R12).
- [X] T021 [P] Implement `src/archetypal/_removed.py`: the `RemovedCapability`,
  `Replacement` and `FrequentTask` types with the fields of data-model.md (`kind:
  Literal["name", "module", "command", "option"]`, `v2_path` unique, `replacement: Replacement
  | None` "None only when reason says why there is none", `reason` "always set", `frequent_task:
  FrequentTask | None`), an empty `REMOVED` tuple filled by US1 and US2, and
  `raise_removed(v2_path: str) -> NoReturn` building the message of contracts/python-api.md.
- [X] T022 Configure `mkdocs.yml` for the Diátaxis site (research R5): Material with
  `navigation.indexes`; mkdocstrings over `src/archetypal`; `mkdocs-click`; nav starting with
  `index.md` only (sections are added with their first page, never empty). Set `site_url` and
  links to the v2 docs on Read the Docs (FR-025).
- [X] T023 Write `docs/index.md` with `/project-kit:diataxis` (explanation, tagged): what
  archetypal is for, where it sits with epinterface and idfkit, and a link to v2's docs
  (FR-023, FR-025). Remove the template's `docs/modules.md`; move `docs/changelog.md` to
  `docs/reference/changelog.md`, tagged reference (FR-026).
- [X] T024 Implement `tests/docs/test_console_examples.py`: for every `console` block
  in `docs/`, run each `$ archetypal …` line in a temporary folder holding the example files,
  and compare shown output when the block shows any (FR-024, R5).

**Checkpoint**: the foundation's tests pass; `make check` and `make docs-test` are clean. Spec
002's Setup (its T001) can start.

---

## Phase 3: User Story 1 — Reduce a model to a UMI library with archetypal 3 (Priority: P1) 🎯 MVP

**Goal**: the `archetypal` command does v2's core job (models and weather in, one UMI library
out) and the new ones (SBEM output, merge, compare, translate), with reports, a summary and
distinct exit statuses.

**Prerequisites**: spec 002's `reduce`, `merge` and `compare` (002 US1–US3) and spec 003's
`read_umi`, `write_umi` and `TranslationReport` (003 contracts/python-api.md; research R14).

**Independent test**: on a fresh environment, run the documented command on a reference model
with a weather file and open the library; the Python route gives the same library (spec US1).

### Tests for User Story 1

- [ ] T025 [P] [US1] Write `tests/unit/test_cli.py` with click's `CliRunner` and the 002
  fixtures (committed results, no EnergyPlus): `archetypal` alone lists `reduce`, `merge`,
  `compare`, `translate` with one line each (scenario 1.1); `reduce` expands directories and
  globs, sorted, and refuses an empty directory naming it; `--to sbem` writes one
  `<model>.sbem.json` per model and its `<model>.report.json` beside it, which `merge` reads
  back; `--to umi` writes one library with one
  building template per model, the reports `<stem>.<model>.report.json` and
  `<stem>.loss.json` (scenarios 1.2, 1.3); `--layout` with `--to umi` is refused; an existing
  output is not overwritten without `--force` (FR-015).
- [ ] T026 [P] [US1] Write `tests/unit/test_exit_status.py`: exit 0 with no loss; 4 with a
  loss reported; 3 when one of two models fails, with the failure named in the summary and the
  report and the library holding the other model; 1 when every model fails, with nothing
  written; 2 for a usage error; 3 wins over 4 (data-model.md, ExitStatus; FR-014).
- [ ] T027 [P] [US1] Write `tests/unit/test_removed_options.py`: each command and option
  in contracts/cli.md's "Rejected v2 options and commands" exits 2 before any work, and its
  message names it and its replacement or reason (scenario 1.5, FR-013, SC-007).
- [ ] T028 [P] [US1] Write `tests/integration/test_v2_invocation.py`
  (`@pytest.mark.energyplus`): `archetypal reduce model.idf -w weather.epw -o lib.json`
  simulates once, reduces to core/perimeter and writes a UMI library equal to the one written
  through the Python functions (scenario 1.4, US1 independent test).
- [ ] T029 [P] [US1] Extend `tests/unit/test_no_side_effects.py`: running every command
  on the fixtures leaves only the requested outputs and reports (FR-006, SC-006).

### Implementation for User Story 1

- [ ] T030 [P] [US1] Implement `src/archetypal/cli/_summary.py`: `ExitStatus` (`SUCCESS =
  0`, `FAILURE = 1`, `USAGE = 2`, `PARTIAL_FAILURE = 3`, `SUCCESS_WITH_LOSSES = 4`; "When both 3
  and 4 apply, 3 wins") and `RunSummary` (data-model.md), built from the reports and printed to
  stderr.
- [ ] T031 [US1] Implement the group in `src/archetypal/cli/__init__.py`: `main` with
  `--version` (archetypal, idfkit and epinterface versions), `--log-level` (configures a stderr
  handler for the command only) and `-d/--debug`; register the entry point `archetypal =
  "archetypal.cli:main"` in `pyproject.toml` (contracts/cli.md, Group).
- [ ] T032 [US1] Add the `command` and `option` rows of contracts/cli.md's rejected list to
  `REMOVED` in `src/archetypal/_removed.py`, and implement
  `src/archetypal/cli/_removed_options.py`: hidden click options and a hidden `transition`
  command built from those rows, each raising a usage error with the row's message before any
  work (FR-013, R6).
- [ ] T033 [US1] Implement `src/archetypal/cli/reduce.py` per contracts/cli.md: model
  expansion, `--weather`, `--output` defaults (`myumitemplate.json` for UMI), `--to`,
  `--results`, `--layout`, `--threshold`, `-p/--parallel` (separate processes, `-1` = every
  core), `--force`; `--to umi` reduces each model at core/perimeter and writes one library with
  003's writer; reports beside the output; summary and exit status from `_summary` (FR-012,
  FR-014, FR-015).
- [ ] T034 [P] [US1] Implement `src/archetypal/cli/merge.py`, `compare.py` and
  `translate.py` per contracts/cli.md, as thin wrappers over 002's `merge` and `compare` and
  003's read and write functions (`--strict` raises `LossyTranslationError`) (FR-011).
- [ ] T035 [US1] Re-export the top-level names of data-model.md (Public interface) from
  `src/archetypal/__init__.py`; keep `archetypal.reduction`, `archetypal.comparison`,
  `archetypal.umi` and `archetypal.errors` public with the names listed there; mark every other
  module private (FR-007, FR-008). A test compares each public module's `__all__` with that
  list.
- [ ] T036 [P] [US1] With `/project-kit:diataxis`, write `docs/reference/cli.md`
  (reference, generated by `mkdocs-click`, plus the exit-status table) and
  `docs/reference/api.md` (reference, mkdocstrings over the public interface), and add the
  Reference section to `mkdocs.yml` with its `index.md` (FR-023, US3 scenario 2).

**Checkpoint**: quickstart scenarios 4 and 5 pass.

---

## Phase 4: User Story 2 — Move a v2 script to v3 (Priority: P1)

**Goal**: every public v2 name, module, command and option is either in v3 or in `REMOVED`;
using a removed one gives the migration error; the guide covers every one, with runnable
before/after examples for frequent tasks.

**Independent test**: check every public name, command and option of archetypal 2.18.11
against the guide; rewrite the v2 tutorial's examples from the guide alone and run them (spec
US2).

### Tests for User Story 2

- [X] T037 [P] [US2] Write `tests/unit/test_v2_coverage.py`: every entry of
  `tests/data/v2_surface.json` is in `REMOVED` or in the public interface; the file's
  `archetypal_version` is `"2.18.11"` (SC-003, R7).
- [X] T038 [P] [US2] Write `tests/unit/test_removed_names.py`: for every `name` row,
  `from archetypal import <name>` and `archetypal.<name>` raise `RemovedInArchetypal3Error`
  with the guide's URL; for every `module` row, `import archetypal.<module>` raises it; every
  `module` row has a stub file under `src/archetypal/` (FR-016, SC-007, scenario 2.1).
- [X] T039 [P] [US2] Write `tests/unit/test_migration_guide.py`: every `REMOVED` row
  appears in `docs/how-to/migrate-from-v2.md`'s rendered table with its replacement or reason;
  every `FrequentTask` has exactly one before/after pair (FR-017, FR-018, scenario 2.2).

### Implementation for User Story 2

- [X] T040 [US2] Write `verification/v2_surface.py`: in a separate environment with
  `archetypal==2.18.11`, list public modules, every public name each defines or lists in
  `__all__`, every click command and option (with short aliases), and write
  `tests/data/v2_surface.json` with the fields of data-model.md (V2Surface). Run it and commit
  the file.
- [X] T041 [US2] Add a row to `REMOVED` in `src/archetypal/_removed.py` for every name and
  module of `tests/data/v2_surface.json` not in the public interface, with its replacement in
  archetypal 3, idfkit or epinterface, or its reason; link the six `FrequentTask`s
  (`reduce-to-umi`, `edit-umi-library`, `open-and-simulate`, `read-results`,
  `upgrade-version`, `evaluate-schedule`). Load `/idfkit:developing-with-idfkit` to name the
  idfkit replacements exactly.
- [X] T042 [US2] Add a module `__getattr__` (PEP 562) to `src/archetypal/__init__.py` that
  calls `raise_removed` for any `name` row of `REMOVED` and raises `AttributeError` otherwise
  (FR-016, R7).
- [X] T043 [P] [US2] Create the stub modules `src/archetypal/dataportal.py`,
  `eplus_interface.py`, `idfclass.py`, `plot.py`, `reportdata.py`, `schedule.py`,
  `simple_glazing.py`, `tabulardata.py`, `template.py`, `umi_template.py`, `utils.py`,
  `zone_graph.py`, each two lines calling `raise_removed(__name__)` (R7).
- [X] T044 [US2] Add a MkDocs hook `docs/hooks/removed.py` (registered in `mkdocs.yml`)
  that renders `REMOVED` as the table of `docs/how-to/migrate-from-v2.md` and as
  `docs/reference/removed.md`, so neither is written by hand (R7, contracts/docs-site.md rule
  3).
- [X] T045 [US2] With `/project-kit:diataxis`, write `docs/how-to/migrate-from-v2.md`
  (how-to, "How to migrate from archetypal 2"): install v3 from git with the fork and why
  (until v3.0.0); the generated table; before/after examples for the six frequent tasks, the
  "after" blocks runnable (load `/idfkit:developing-with-idfkit` for the idfkit ones); what
  changes in results and where 002's evidence is (FR-019); v3 writes only requested files;
  the v2 support policy with its end date left to fill at v3.0.0 (FR-020). Add the How-to
  section to `mkdocs.yml` with its `index.md`.
- [X] T046 [P] [US2] Add `docs/reference/removed.md` (reference, generated by the hook)
  to the Reference section.

**Checkpoint**: quickstart scenario 3 passes; SC-003 and SC-007 hold.

---

## Phase 5: User Story 3 — Learn and look things up in the documentation (Priority: P2)

**Goal**: a newcomer reaches a first UMI library from a fresh install; every public name and
command is in the reference; every page has one kind and every example runs.

**Independent test**: follow the tutorial from a fresh install to a written UMI library; pick
public names and commands at random and find each in the reference; check every page's kind
(spec US3).

### Tests for User Story 3

- [ ] T047 [P] [US3] Write `tests/unit/test_reference_complete.py`: every public name
  of the interface and every command and option of the `archetypal` group appears in the
  built site's reference pages (`mkdocs build` into a temporary folder) (US3 scenario 2).
- [X] T048 [P] [US3] Add `.github/workflows/tutorial.yml`: on `v3.*` tags and weekly,
  for Python 3.10–3.12 on Linux, macOS and Windows, install the tag from git into a clean
  environment and run the tutorial's `console` blocks; on Python 3.13, check that the install
  is refused with the supported range (FR-001, SC-001, edge case).

### Implementation for User Story 3

- [ ] T049 [US3] With `/project-kit:diataxis`, write `docs/tutorials/first-umi-library.md`
  (tutorial, "Your first UMI library"): install from git at the milestone tag (PyPI from
  v3.0.0), download the example DOE prototype model, its results and a weather file from the
  repository at that tag (source and licence stated, FR-004, C-15), reduce to a UMI library,
  open it. Execute it start to finish in a clean environment before merging. Add the Tutorials
  section to `mkdocs.yml` with its `index.md` (FR-023).
- [ ] T050 [P] [US3] Add the tutorial's example files under `docs/examples/` (model,
  results cut to 002's outputs, weather), each with its source and licence in
  `docs/examples/SOURCES.md` (FR-004, R12).
- [X] T051 [P] [US3] With `/project-kit:diataxis`, write `docs/how-to/install.md` ("How to
  install archetypal 3"): from git with the fork until v3.0.0 and why (roadmap C-17, C-18),
  then from PyPI; supported Python versions and platforms (FR-001).
- [X] T052 [P] [US3] With `/project-kit:diataxis`, write `docs/explanation/stack.md`
  (explanation, "About archetypal, epinterface and idfkit"): who does what, why v3 is smaller,
  why SBEM is the one data model. Add the Explanation section to `mkdocs.yml` with its
  `index.md` (FR-023).

**Checkpoint**: quickstart scenarios 6 and 7 pass; all four sections exist, each with real
pages (FR-022).

---

## Phase 6: Milestone M1 and the v2 lifecycle

**Purpose**: what 001 owns at milestone M1 and at the first PyPI release (research R2, R11,
R12; roadmap C-18).

- [ ] T053 Write `verification/install_size.py`: resolve archetypal 2.18.11 and the current
  v3 on Python 3.12 and print both package counts; record the result in the milestone
  checklist. If v3's is not smaller, raise it against UP-4 in the fork (SC-002, R12).
- [ ] T054 [P] Write the `3.0.0a1` section of `CHANGELOG.md`: added functions and
  commands, removed v2 capabilities with a link to the migration guide, installing from git
  (FR-026).
- [ ] T055 Run every quickstart scenario, `make check` and the unit budget, and fix what
  fails.
- [ ] T056 When 001, 002 and 003 are verified: merge `v3` into `main`, tag `v3.0.0a1` and
  publish it as a GitHub pre-release; check that the publish job is skipped and the docs are
  deployed (R2).
- [ ] T057 On `v2.x`, release `2.18.12`: a docs banner and README note inviting v2 users
  to try `v3.0.0a1` from git, linking the migration guide; switch Read the Docs' default
  version to `v2.x` (FR-025, R11).
- [ ] T058 At the publish point (UP-3 met, roadmap C-18): release a final v2 announcing v3
  in its notes and docs banner (FR-021); fill in the v2 support end date in the migration
  guide (FR-020); switch the install pages to PyPI; release v3.0.0 as a normal GitHub release
  so the publish job runs (FR-001).
- [ ] T059 At M1, record in `.specify/memory/roadmap.md` that 001's success criteria hold on
  the tag, except FR-001. Mark 001 implemented once its blocking items are released (plan.md,
  Upstream dependencies; roadmap C-20): UP-1 and UP-4 by the fork, and UP-3, through the
  v3.0.0 PyPI release (T058) on which FR-001 passes.

---

## Dependencies and execution order

### Phases

- **Setup (1)**: T001, then T002 → T003 → T004 → the rest.
- **Foundational (2)**: after Setup. Blocks every story and every 002 and 003 task.
- **US1 (3)**: after Foundational, and after 002's public functions (002 US1–US3) and 003's
  UMI functions exist.
- **US2 (4)**: after Foundational. T040 and T041 need nothing from 002 or 003; the
  "after" examples of T045 for reducing to UMI need US1.
- **US3 (5)**: T052 and T051 after Foundational; T049 after US1.
- **Milestone (6)**: after US1–US3 and after 002 and 003 are verified; T058 waits for UP-3.

### Within each story

- Tests first, failing.
- US1: T030 → T031 → T032 and T033 → T034 → T035 → T036.
- US2: T040 → T041 → T042 and T043 → T044 → T045 and T046.

### Parallel opportunities

- Setup: once T004 is done, T005–T007 one after another (same file, `pyproject.toml`), and
  T009–T012 in parallel with them.
- Foundational: every test task, then T018, T020, T021.
- US1: every test task; T030; T034 alongside T033; T036.
- US2: every test task; T043 alongside T042.
- US3: T047, T048, T050, T051, T052.
- US2 and the first half of US3 can run while 002 and 003 are being built; US1 waits for them.

## Parallel example: User Story 2

```text
# Tests, all at once:
T037 tests/unit/test_v2_coverage.py
T038   tests/unit/test_removed_names.py
T039   tests/unit/test_migration_guide.py

# After T041:
T042 src/archetypal/__init__.py      T043 src/archetypal/<12 removed modules>.py
```

## Implementation strategy

### Foundation first

1. Phases 1 and 2: the generated project, tooling, errors, docs site and checks. Stop and
   validate: quickstart scenarios 1 and 2. Spec 002 starts here.

### MVP: User Story 1

2. After 002 and 003 deliver their functions: the `archetypal` command. Stop and validate:
   quickstart scenario 5, v2's core workflow from the command line.

### Incremental delivery

3. US2 (can start before US1): removed names and the migration guide.
4. US3: tutorial, install page, explanation, complete reference.
5. Milestone M1 with 002 and 003; v3.0.0 on PyPI at the publish point.

Each step ships with its documentation pages (constitution VI). No task publishes to PyPI
before UP-3 (roadmap C-18).
