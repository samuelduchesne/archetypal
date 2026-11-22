# Quickstart: validating spec 001

Runnable scenarios that show spec 001 works. Each names what it proves. Contracts:
[cli.md](contracts/cli.md), [python-api.md](contracts/python-api.md),
[docs-site.md](contracts/docs-site.md).

## Prerequisites

- uv and git.
- A checkout of `v3` (or of `main` from M1), then `make install`.
- Scenario 5 needs EnergyPlus 24.2; scenario 7 needs a clean machine per OS (CI).

## 1. The project is the template's (research R1)

```bash
uvx cruft check            # linked to project-kit-cookiecutter
make check                 # lock, pre-commit (ruff), pyright strict, deptry, idfkit check
```

**Expected:** cruft reports the project up to date with its recorded template commit (or
lists only the edits of R1); every check passes.

## 2. Unit tier in two minutes (R3)

```bash
uv run pytest
```

**Expected:** passes in under 120 s; the 15 slowest tests are listed.

## 3. Removed names and options (FR-013, FR-016, SC-003, SC-007)

```bash
uv run python -c "from archetypal import IDF"
uv run archetypal transition model.idf
uv run archetypal reduce model.idf -w w.epw --all_zones
uv run pytest tests/unit/test_removed.py
```

**Expected:** each command fails with the migration message naming the item and its
replacement (status 2 for the command line); the tests confirm every entry of
`tests/data/v2_surface.json` is covered.

## 4. No side effects (FR-006, SC-006)

```bash
uv run pytest tests/unit/test_no_side_effects.py
```

**Expected:** importing archetypal and running every command leaves only the requested
outputs; the root logger is untouched.

## 5. v2's core workflow (US1, FR-012, FR-014)

```bash
uv run archetypal reduce examples/office.idf -w examples/chicago.epw -o lib.json
echo $?
```

**Expected:** `lib.json` (one building template), `lib.office.report.json` and
`lib.loss.json` beside it; a summary on stderr; status 0, or 4 when losses are reported.
`--to sbem` writes `office.sbem.json` and its report instead.

## 6. Documentation (FR-022–FR-024, SC-004, SC-008)

```bash
make docs-test                                   # mkdocs build -s
uv run pytest --markdown-docs docs/ tests/docs/  # every example runs
uv run pytest tests/unit/test_docs_tags.py       # one Diátaxis kind per page
```

**Expected:** all pass.

## 7. Fresh install on every platform (FR-001, SC-001, SC-002)

Run by `.github/workflows/tutorial.yml` on milestone tags and weekly: for Python 3.10–3.12 on
Linux, macOS and Windows, install the tag from git into a clean environment and follow the
tutorial to a UMI library. `verification/install_size.py` then compares package counts with
archetypal 2.18.11.

**Expected:** all nine runs pass; on Python 3.13 the install is refused with the supported
range; v3 installs fewer packages than v2 and none of the banned duplicates.
