---
diataxis: reference
---

# Command line

The `archetypal` command and its four sub-commands. Each sub-command wraps a public function:
`reduce` wraps `archetypal.reduce` and `archetypal.write_umi`, `merge` wraps `archetypal.merge`,
`compare` wraps `archetypal.compare`, and `translate` wraps `archetypal.read_umi` and
`archetypal.write_umi` (see the [Python API](api.md)). The options below are generated from the
code.

## Exit statuses

| Status | Name | When |
|---|---|---|
| 0 | `SUCCESS` | Every model was processed, and no loss or approximation was reported. |
| 1 | `FAILURE` | Nothing was written: an input is invalid, an output exists without `--force`, every model failed, a strict translation would lose something, or an unexpected error occurred. |
| 2 | `USAGE` | The command line is wrong, or it uses a removed archetypal 2 option or command. |
| 3 | `PARTIAL_FAILURE` | Some models failed. The output holds the others; the summary and the reports name the failures. |
| 4 | `SUCCESS_WITH_LOSSES` | Every model was processed, and at least one loss or approximation was reported. |

When both 3 and 4 apply, the status is 3.

## Summary and reports

After its work, a command prints a summary to stderr: the models processed and failed, each
failure with its error, the losses and approximations reported, and the paths it wrote. The
reports are written beside the output:

| Command | Reports |
|---|---|
| `reduce --to umi -o lib.json` | `lib.<model>.report.json` per model ([reduction report](reduction-report.md)) and `lib.loss.json` ([translation report](translation-report.md)). A failed model is a `skipped_template` loss of `lib.loss.json`. |
| `reduce --to sbem` | `<model>.report.json` beside each `<model>.sbem.json`. |
| `merge` | `<name>.report.json` beside the merged `<name>.sbem.json`. |
| `translate` | `<library stem>.loss.json`, in the output folder (UMI to SBEM) or beside the library (SBEM to UMI). |
| `compare` | None; `--json` writes the comparison table. |

A loss is a reduction report's `not_represented` entry with no `folded_into`, or a translation
report's loss of any kind except `approximate`. An approximation is a `not_represented` entry
with `folded_into`, or an `approximate` loss.

No command overwrites an existing file without `--force`. No command writes any file other
than its outputs and reports.

## Removed options

The archetypal 2 command `transition` and the options listed in
[Removed v2 capabilities](removed.md) are recognised, short flags included, and rejected with
status 2 before any work. The message names the option and its replacement.

## Commands

::: mkdocs-click
    :module: archetypal.cli
    :command: main
    :prog_name: archetypal
    :depth: 1
    :style: table
    :list_subcommands: true
