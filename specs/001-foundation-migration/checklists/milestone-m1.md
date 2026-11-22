# Milestone M1 checklist: archetypal 3 foundation

**Purpose**: Record the evidence for M1's success criteria as each is checked
**Feature**: [spec.md](../spec.md)

## SC-002: install size and duplicates

- [x] archetypal 3 installs fewer packages than archetypal 2 on the same Python version.
  - Date: 2026-11-22
  - Command: `uv run python verification/install_size.py` (`uv pip compile`, Python 3.12, uv
    0.11.32)
  - archetypal 2.18.10 (last v2 release; 2.18.11 does not exist): **109 packages**
  - archetypal 3 (this checkout, epinterface from the fork at `dee8d343` via
    `[tool.uv.sources]`): **25 packages**
  - Both counts include archetypal itself. Result: PASS.
- [x] The archetypal 3 resolution contains none of `eppy`, `geomeppy`, `esoreader`,
  `energy_pandas`, `pyclipper`, `pypoly2tri`, `transforms3d` or `shapely`; the archetypal 2
  resolution contains `eppy`, `esoreader`, `energy-pandas`, `pyclipper`, `pypoly2tri`,
  `transforms3d` and `shapely`.

archetypal 3's resolution (2026-11-22): annotated-types, anyio, archetypal, certifi, click,
epinterface, h11, httpcore, httpx, idfkit, idna, networkx, numpy, pandas, pydantic,
pydantic-core, pydantic-settings, python-dateutil, python-dotenv, pytz, pyyaml, tqdm,
typing-extensions, typing-inspection, tzdata.

Because v3's count is smaller, no UP-4 note was needed for SC-002.

## Quickstart scenarios and quality gates (2026-11-22)

Run on Linux, Python 3.12, EnergyPlus 24.2 (`ENERGYPLUS_DIR=/usr/local/EnergyPlus-24-2-0`),
.NET 8. `examples/office.idf` and `examples/chicago.epw` do not exist: the scenarios that name
them were run with `docs/examples/three_zone.idf` and `docs/examples/chicago.epw` (the
tutorial's files), and the quickstarts now name those files.

### Commands

| Command | Result | Time |
|---|---|---|
| `make check` (lock, pre-commit, pyright, idfkit check, deptry, Basilisk field list, `mkdocs build -s`, Diátaxis tags) | pass | 52 s |
| `make docs-test` | pass | 4 s |
| `uv run pytest` (default tier) | pass: 3039 passed, 3 skipped, 5 xfailed; under the 120 s budget | 95 s |
| `uv run pytest -m energyplus` | pass: 10 passed | 155–179 s |
| `uv run pytest --markdown-docs docs/` | pass: 33 passed | 24 s |
| `uv run pytest --markdown-docs docs/ tests/docs/` (CI's docs-examples job) | pass: 37 passed | 28 s |
| `uv run mkdocs build -s` | pass | 4 s |
| `uvx cruft check` | pass: up to date | 1 s |

Fixed on the way: the tutorial's console example showed 86 losses where the command now
reports 85 (autosized ideal-loads limits are no longer written); a pyright "partially unknown"
error in `tests/unit/test_stand_in_diagnosis.py`; and `pytest --markdown-docs docs/
tests/docs/` failed to collect because `docs/conftest.py` and `tests/conftest.py` share a
module name (now `--import-mode=importlib`).

### Spec 001

| Scenario | Outcome |
|---|---|
| 1. The project is the template's | pass (`cruft check` up to date, `make check` passes) |
| 2. Unit tier in two minutes | pass (95 s, 15 slowest listed) |
| 3. Removed names and options | pass (`from archetypal import IDF` raises `RemovedInArchetypal3Error`; `transition` and `reduce --all_zones` exit 2 with the migration message; 443 tests pass) |
| 4. No side effects | pass (2 passed) |
| 5. v2's core workflow | pass (`lib.json` with one template, `lib.three_zone.report.json`, `lib.loss.json`, status 4; `--to sbem` writes `three_zone.sbem.json` and its report) |
| 6. Documentation | pass (see Commands) |
| 7. Fresh install on every platform | not runnable here: needs a pushed milestone tag and clean Linux, macOS and Windows machines (`tutorial.yml`) |

### Spec 002

| Scenario | Outcome |
|---|---|
| 1. Quality gates and the unit tier | pass |
| 2. Reduce a fixture model | pass (both files written, epinterface loads the archetype, shares sum to 1, all 10 zones once including plenums, two runs byte-identical) |
| 3. Missing results are named | pass (`MissingResults` lists 15 outputs in IDF syntax and suggests `simulate=True`) |
| 4. Coarser layouts and merging | pass (`merge` equals a direct core/perimeter reduction; `merged_distinctions` lists the merged space uses; bar building gives one perimeter group) |
| 5. Conservation | pass (22 passed) |
| 6. Single run and generation by epinterface | pass (`-m energyplus`, 10 passed) |
| 7. Reference evidence | not runnable here: the reference models are published for EnergyPlus 22.1/23.1 and need EnergyPlus's transition programs to migrate, which are not installed; `-m reference` skips each building with that reason |
| 8. Documentation | pass |

### Spec 003

| Scenario | Outcome |
|---|---|
| 1. Read the sample libraries | pass (four `*.sbem.json` with `core` and `perimeter` groups and unset shares, `BostonTemplateLibrary_2.loss.json` with 8 losses marked `UP-9` and 29 unused components, status 4; `test_read.py` 29 passed) |
| 2. Write archetypes to UMI | pass (`lib.json` with one template and `lib.loss.json`; `test_write.py` 25 passed) |
| 3. UMI's own code reads every written library | pass (15 libraries written by the tests and the scenario 2 library: one "ok" each, status 0) |
| 4. Round trips and the audit | pass for the unit tests (43 passed, 4 xfailed as documented); the reference round trip is not runnable here, for the reason of 002 scenario 7 |
| 5. Strict mode | pass (status 1, no `out2/`, message lists the 37 values that would be lost) |
| 6. Invalid libraries | pass (71 passed) |
| 7. Correspondence, determinism and speed | pass (correspondence, serialise and performance tests pass; `make docs-test` passes) |

Not run, by design: the GitHub release and tag of `v3.0.0a1` (001 T056), which the
coordinator does once 001–003 are verified.
