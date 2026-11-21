# speckit-roadmap

A [GitHub Spec Kit](https://github.com/github/spec-kit) extension that adds a **spec
roadmap** to the workflow: written after the constitution, and reviewed before and after
each spec is implemented.

```
constitution → ROADMAP → specify → plan → tasks → [brief] → implement → [debrief]
                 │                              read-only       read-only
            roadmap.write                   roadmap.sync — reconcile on demand
```

## Why

The constitution records your project's principles. The constitution *phase* — the
discussion, grilling, and prototyping around it — produces a lot more: technology choices,
intended outcomes, scope decisions, constraints, and the rough shape of specs you won't
write for a while.

That material normally has nowhere to go. It's lost between the constitution and the first
spec, and especially before specs you write later. By the time you start spec 007, whatever
you decided about it earlier is gone — so you re-derive it, or contradict it.

The roadmap holds onto it. It's a living, project-level file next to the constitution that
records what each planned spec is for, what's in and out of scope, what it depends on, and
which decisions govern it — including specs that don't exist yet. When you start one,
`roadmap.brief` shows you what you'd decided; after you build it, `roadmap.debrief` checks
the result against that.

## Commands

| Command | When | What it does |
|---------|------|--------------|
| `speckit.roadmap.write` | after `/speckit.constitution` (hook) | Create or amend the roadmap. Pulls from the constitution, ADRs, PRDs, the current session, and prior notes; asks about gaps; writes a versioned roadmap with a changelog. Detects create vs. amend automatically. |
| `speckit.roadmap.brief` | before `/speckit.implement` (hook) | Read-only. Surfaces the roadmap's record for the spec you're about to build (outcome, scope, governing decisions, dependencies) and flags anything that has already drifted. |
| `speckit.roadmap.debrief` | after `/speckit.implement` (hook) | Read-only. Compares what you built against the roadmap entry; classifies any drift; proposes marking the entry `verified`. |
| `speckit.roadmap.sync` | on demand | Read-only. Reconciles the whole roadmap against the specs on disk: orphans, phantom entries, status drift, broken dependencies. |

`brief`, `debrief`, and `sync` are read-only — they write a report and *propose* changes.
Only `write` edits the roadmap, and it never deletes content (superseded entries are marked,
and every change is recorded in the roadmap's changelog).

## The roadmap file

`.specify/memory/roadmap.md` (configurable), next to the constitution, with semantic
versioning and a Sync Impact Report changelog like the constitution uses. It contains:

- **Vision & End States** — project-level goals.
- **Constraints & Decisions** — the "why", inline, with links out to ADRs when they exist.
- **Planned Specs** — the ledger. Each entry has a status, description, outcome, scope, and
  optional dependency / decision / PRD pointers. Statuses: `undecided`, `needs-info`,
  `planned`, `specced`, `in-progress`, `implemented`, `verified`, `deferred`, `abandoned`.
- **Open Questions** and **Cross-Cutting Notes**.

The roadmap *links* to ADRs (`governed-by:`) and PRDs (`addresses:`) when present; it doesn't
write them.

## Install

This extension isn't in the spec-kit community catalog yet, so install it directly from this
repository.

From the Git repository:

```bash
specify extension add --from https://github.com/srobroek/speckit-roadmap
specify extension enable roadmap
```

From a local checkout (for development):

```bash
git clone https://github.com/srobroek/speckit-roadmap
specify extension add ./speckit-roadmap --dev --force
specify extension enable roadmap
```

If you're developing this extension *inside* a spec-kit project, install from a copy of the
source rather than the repo root — installing a directory into its own
`.specify/extensions/` will recurse.

Requires spec-kit `>= 0.11.6`.

## Configuration

Copy `config-template.yml` to `.specify/extensions/roadmap/roadmap-config.yml` and edit.
Everything is optional; `SPECKIT_ROADMAP_*` environment variables override the file.

| Key | Default | Meaning |
|-----|---------|---------|
| `roadmap.path` | `.specify/memory/roadmap.md` | Where the roadmap lives |
| `adr.dir` | `docs/adr/` | ADR directory to detect and link (ignored if absent) |
| `prd.globs` | common PRD filenames | Patterns for detecting PRDs to reference |
| `report.max_findings` | `50` | Max findings in a review report |

## How it's built

- **Scripts vs. judgment.** The one shipped script, `load-config` (bash + PowerShell), only
  resolves config and paths — it's deterministic and unit-tested (Bats + Pester, plus a
  bash/PowerShell output-parity test). Everything that requires judgment — elicitation, drift
  detection, review reasoning — lives in the command bodies, which are checked by using them,
  not by unit tests.
- **Cross-platform.** Both `load-config` implementations produce the same output; CI runs the
  bash tests on Linux and macOS and the PowerShell tests on Windows.
- **Self-hosted.** This extension was built with spec-kit and reviewed against its own
  roadmap. See `specs/` and `.specify/memory/roadmap.md`.

## Development

```bash
bats tests/bash/load-config.bats
bats tests/parity/parity.bats
pwsh -NoProfile -Command "Invoke-Pester -Path tests/powershell/load-config.Tests.ps1"
```

## License

Apache-2.0. See [LICENSE](LICENSE).
