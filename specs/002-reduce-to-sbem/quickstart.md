# Quickstart: validating reduction

Runnable scenarios that show spec 002 works end to end. Each names the requirement it proves.
API details are in [contracts/python-api.md](contracts/python-api.md). Report fields are in
[data-model.md](data-model.md).

## Prerequisites

- uv, and a checkout of the `v3` line.
- `make install`: creates the environment and installs the pre-commit hooks.
- Scenarios 6 and 7 also need EnergyPlus 24.2, found by idfkit through `ENERGYPLUS_DIR` or
  `PATH`.

## 1. Quality gates and the unit tier (every push)

```bash
make check                 # uv lock --locked, pre-commit (ruff, ban on untyped idfkit lookups), pyright strict, idfkit check, deptry
uv run pytest              # default selection: unit tier only
```

**Expected:**

- every check passes, including `idfkit check --since 22.1` with no C001–C006 findings and no
  pyright "unknown type" errors;
- pytest reports its 15 slowest tests and finishes in **under 120 s**. The session hook fails
  the run otherwise.

## 2. Reduce a fixture model (US1, FR-001, FR-004, FR-014, SC-006)

```python
from archetypal import reduce

r = reduce("tests/fixtures/models/ten_zone_multipliers.idf", "tests/fixtures/models/ten_zone_multipliers.sql")
paths = r.write("out", "ten_zone")
```

**Expected:**

- `out/ten_zone.sbem.json` and `out/ten_zone.report.json` exist;
- the archetype loads with epinterface alone (`model_validate_json`);
- group shares sum to 1;
- every zone appears once in the report (groups or excluded, plenum included);
- running it again gives byte-identical files (FR-005).

## 3. Missing results are named (FR-002, FR-029)

Call `reduce` on the fixture model without results.

**Expected:** `MissingResults` lists each missing output in IDF syntax and suggests
`simulate=True`. No file is written.

## 4. Coarser layouts and merging (US2, FR-009–FR-011, SC-007)

```python
from archetypal import Layout, ReductionOptions, merge, reduce

fine = reduce(model, results)
direct = reduce(model, results, options=ReductionOptions(layout=Layout.CORE_PERIMETER))
assert merge(fine, Layout.CORE_PERIMETER).archetype == direct.archetype
```

**Expected:**

- two groups, core and perimeter;
- `report.merged_distinctions` lists the space uses that were merged;
- on the bar-building fixture (no core zones), one perimeter group and a report note.

## 5. Conservation (SC-005)

Run `uv run pytest tests/unit/test_conservation.py`. These are property tests on synthetic
ledgers plus the fixture models.

**Expected:** every total in FR-014–FR-019, FR-021, FR-022 and FR-022a matches the detailed model
within 0.1 %, and exactly where the detailed total is 0.

## 6. Single run and generation by epinterface (FR-002, FR-003)

```bash
uv run pytest -m energyplus
```

**Expected:**

- `reduce(model, simulate=True, weather=epw)` runs EnergyPlus once;
- the archetype builds and simulates through epinterface without modification.

## 7. Reference evidence (SC-001–SC-004, SC-008)

```bash
uv run python verification/report.py --fetch    # downloads the reference set (checksummed)
uv run pytest -m reference                       # weekly workflow / before a release
```

**Expected:** a table per building with:

- total site energy within ±5 %;
- significant end uses within ±10 %, fans on their own and pumps and heat rejection added to
  the heating and cooling they serve (SC-002);
- significant peaks within ±15 %;
- v3 core/perimeter error below v2's baseline for the set and for ≥ 90 % of buildings;
- the largest building reduced in under 10 s, and the set at least 10× faster than v2.

## 8. Documentation

```bash
make docs-test             # mkdocs build -s; code examples in the how-to pages run in CI
```

**Expected:** the explanation, how-to and reference pages listed in plan.md build without
warnings.
