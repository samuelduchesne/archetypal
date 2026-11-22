# Contract: the `archetypal` command

Spec 001 owns the command line (FR-011–FR-015). Each command is a thin wrapper over a public
function of spec 002 or 003; its options map one to one to that function's arguments. The
reference page `docs/reference/cli.md` is generated from the code with `mkdocs-click`.

## Group

```text
archetypal [--version] [--log-level LEVEL] [-d/--debug] COMMAND ...
```

- `--version`: archetypal's version, then idfkit's and epinterface's.
- `--log-level`: `debug`, `info`, `warning` (default) or `error`, to stderr.
- `-d/--debug`: show the traceback of an unexpected error.

`archetypal` alone lists the commands with a one-line description each (US1 scenario 1).

## `reduce`

```text
archetypal reduce MODELS... -w/--weather EPW [-o/--output PATH] [--to umi|sbem]
                  [--results SQL ...] [--layout LAYOUT] [--threshold SHARE]
                  [-p/--parallel N] [--force]
```

| Option | Default | Meaning |
|---|---|---|
| `MODELS...` | required | IDF or epJSON files, directories or glob patterns; expanded and sorted. A directory with no model is an error naming it. |
| `-w/--weather` | required when any model has no `--results` | EPW file for the single simulation of each such model (002 FR-002). v2's default path into an EnergyPlus install is not kept. |
| `-o/--output` | `myumitemplate.json` with `--to umi` (v2's default); the current directory with `--to sbem` | UMI library file, or folder for SBEM archetypes. |
| `--to` | `umi` | `umi`: one library, one building template per model, at the core/perimeter layout UMI requires. `sbem`: one `<model>.sbem.json` per model. |
| `--results` | none | One SQLite file per model, in the same order; skips the simulation. |
| `--layout` | `space-use-exposure` (`--to sbem`) | 002's layouts. Refused with `--to umi`, which needs `core-perimeter`. |
| `--threshold` | `0.05` | 002's small-group threshold. |
| `-p/--parallel` | `1` | Models processed at once. `-1` uses every core, as in v2. |
| `--force` | off | Overwrite existing outputs (FR-015). |

Reports, written beside the output:

- `--to sbem`: `<model>.report.json` beside each `<model>.sbem.json` (002's `Reduction.write`),
  the pair `merge` reads back.
- `--to umi`: `<stem>.<model>.report.json` (002) for each model, where `<stem>` is the
  library's file name without `.json`, and `<stem>.loss.json` (003).

## `merge`, `compare`, `translate`

```text
archetypal merge ARCHETYPE --layout LAYOUT [-o PATH] [--threshold SHARE] [--force]
archetypal compare DETAILED_SQL ARCHETYPE_SQL [--weather EPW] [--json PATH]
archetypal translate SOURCE -o PATH [--strict] [--force]
```

- `merge` reads `<name>.sbem.json` and its `<name>.report.json` (002's `merge`).
- `compare` prints the comparison table; `--json` also writes it (002's `compare`).
- `translate` goes UMI → SBEM when `SOURCE` is a UMI library, and SBEM → UMI when it is an
  SBEM archetype or a folder of them (003).
  - UMI → SBEM: `PATH` is a folder; it receives `<template>.sbem.json` per building template
    and `<library stem>.loss.json` (003's `UmiImport.write`).
  - SBEM → UMI: `PATH` is the library file; `<stem>.loss.json` is written beside it (003's
    `write_umi`).
  - `--strict` turns any loss into an error: status 1, nothing written (003's
    `LossyTranslationError`).

## Exit statuses and summary

As in [../data-model.md](../data-model.md), ExitStatus and RunSummary: 0 success, 1 failure,
2 usage, 3 partial failure, 4 success with losses. The summary goes to stderr; outputs and
reports are the only files written (FR-006).

## Rejected v2 options and commands (FR-013)

Each is accepted by the parser so that it can be named, then rejected with status 2 before any
work. The message names it and gives its replacement or reason, from `REMOVED`.

| v2 | Message gist |
|---|---|
| `archetypal transition` | Use `idfkit.migration.migrate`. |
| `--ep_version` | archetypal no longer runs a chosen EnergyPlus; idfkit finds the installed one. |
| `reduce -v` / `reduce --version` | Upgrade models with `idfkit.migration.migrate` before reducing. |
| `reduce -z` / `--all_zones` | Replaced by `--layout`; every conditioned zone is always counted. |
| `-c/--cache-responses` | The data portal is removed (TABULA returns in spec 004). |
| `--data-folder`, `--logs-folder`, `--imgs-folder`, `--cache-folder` | archetypal 3 writes only the outputs you ask for. |
| `-l/--log-file`, `-s/--silent`, `--log-name`, `--log-filename` | Use `--log-level` and redirect stderr. |

This behaviour is kept in every 3.x release.
