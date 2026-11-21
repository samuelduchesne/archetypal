# Changelog

All notable changes to this extension are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html). Releases are managed by
release-please from Conventional Commits.

## 0.1.0 (2026-06-24)


### Features

* initial release of speckit-roadmap extension (0.1.0) ([deb9126](https://github.com/srobroek/speckit-roadmap/commit/deb9126c2b726aa0fba61367dddf8ca20df1a3d7))


### Bug Fixes

* Windows-safe temp dir in Pester suite; split CI into parallel per-platform jobs ([db263fb](https://github.com/srobroek/speckit-roadmap/commit/db263fb102077e1c33e1afc7643ebd09567b0da5))

## 0.1.0 (2026-06-24)

Initial release.

### Features

- **`speckit.roadmap.write`** — create or amend the spec roadmap after the constitution
  (hook: `after_constitution`). Harvests the constitution, detected ADRs/PRDs, the current
  session, and prior notes; elicits genuine gaps; writes a semantically-versioned roadmap
  with a Sync Impact Report changelog. Self-detecting create vs. amend; non-destructive.
- **`speckit.roadmap.brief`** — read-only pre-implementation review (hook: `before_implement`).
  Surfaces the roadmap's record for the active spec and flags pre-implementation drift.
- **`speckit.roadmap.debrief`** — read-only post-implementation review (hook: `after_implement`).
  Classifies drift (outcome-miss / scope-creep / constraint-violation / roadmap-stale) and
  proposes marking the entry `verified` when the outcome is met and there are no blockers.
- **`speckit.roadmap.sync`** — read-only, on-demand reconciliation of the whole roadmap
  ledger against the specs on disk (orphans, phantom entries, status drift, dependency
  contradictions), using status as the pivot for what should exist.
- **`load-config`** (bash + PowerShell) — deterministic configuration resolver emitting a
  stable JSON contract, with full Bats/Pester coverage and a cross-platform parity test.
- Shared `review-report-template.md` used by all three review commands; `roadmap-template.md`
  for the roadmap artifact; `config-template.yml` for configuration.
