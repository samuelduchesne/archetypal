# Quickstart: validating spec 003

Runnable scenarios that show spec 003 works. Contracts:
[python-api.md](contracts/python-api.md), [translation-report.md](contracts/translation-report.md),
[umi-file.md](contracts/umi-file.md).

## Prerequisites

- A checkout of `v3` with 001's foundation and 002 in place, then `make install`.
- The SBEM fork release with UP-2 (zone groups, unset shares). UP-9 is needed only for
  scenario 4's full pass.
- .NET 8 SDK for scenario 3 (CI always has it).
- Spec 001's command line (its Phase 3) for the `archetypal …` steps of scenarios 1, 2 and 5;
  until then, run their pytest steps only.

## 1. Read the sample libraries (US2, SC-001)

```bash
uv run archetypal translate tests/fixtures/umi/BostonTemplateLibrary_2.json -o out/
uv run pytest tests/unit/umi/test_read.py
```

**Expected:** four `*.sbem.json` files and `BostonTemplateLibrary_2.loss.json` in `out/`, each
archetype with `core` and `perimeter` groups and no fixed shares. The report lists every field
waiting for UP-9 as `lost` with `"upstream": "UP-9"`. Status 4 (success with losses).

## 2. Write archetypes to UMI (US1)

```bash
uv run archetypal reduce examples/office.idf -w examples/chicago.epw -o lib.json
uv run pytest tests/unit/umi/test_write.py
```

**Expected:** `lib.json` with one building template, equal to the archetype merged to
core/perimeter; `lib.loss.json` lists the merged groups and the dropped shares. Two archetypes
sharing a construction give one construction in the library.

## 3. UMI's own code reads every written library (SC-002)

```bash
uv run pytest tests/unit/umi --write-libraries out/libraries
dotnet run --project tools/basilisk-check -- out/libraries/*.json
```

**Expected:** exit status 0, and one "ok" line per file.

## 4. Round trips and the audit (US3, SC-003, SC-004, SC-006)

```bash
uv run pytest tests/unit/umi/test_round_trip.py tests/unit/umi/test_audit.py
uv run pytest -m reference tests/reference/test_umi_round_trip.py
```

**Expected:** no unreported difference. Every simulation-relevant value is within 0.01 % once
UP-9 is released. Until then, those fields appear in the reports as lost, and SC-003 is
marked expected-to-fail with that reason.

## 5. Strict mode (FR-011a, SC-006a)

```bash
uv run archetypal translate tests/fixtures/umi/BostonTemplateLibrary_2.json -o out2/ --strict
echo $?
```

**Expected:** status 1, no file in `out2/`, and the message lists what would have been lost.
A library whose translation loses nothing succeeds in strict mode.

## 6. Invalid libraries (FR-004, edge cases)

```bash
uv run pytest tests/unit/umi/test_validation.py
```

**Expected:** each edge-case fixture fails with every problem named by JSON pointer (dangling
and forward references, missing schedule, out-of-range value). With
`skip_invalid_templates=True`, only the bad templates are skipped and reported. Legacy XML
is refused naming the format.

## 7. Correspondence, determinism and speed (FR-009, FR-012, SC-005, SC-007)

```bash
uv run pytest tests/unit/umi/test_correspondence.py tests/unit/umi/test_determinism.py tests/unit/umi/test_performance.py
make docs-test
```

**Expected:** every Basilisk field is in the table, and the generated reference page builds.
Two writes give identical bytes. 100 templates are read and written in under 5 s.
