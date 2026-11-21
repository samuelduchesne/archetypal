---
description: Read-only reconciliation — detect drift between the roadmap ledger and the specs on disk (orphans, phantom entries, status drift, dependency contradictions, superseded ADRs).
scripts:
  sh: .specify/extensions/roadmap/scripts/bash/load-config.sh
  ps: .specify/extensions/roadmap/scripts/powershell/load-config.ps1
---

## User Input

```text
$ARGUMENTS
```

You **MUST** consider the user input before proceeding (if not empty).

## Goal

Reconcile the whole roadmap ledger against reality — the `specs/` directories on disk and,
when present, the ADRs — to keep the roadmap honest across all specs. This is a manual,
on-demand, project-wide check (unlike the per-spec brief/debrief hooks).

## Operating Constraints

- **STRICTLY READ-ONLY.** The only output is a reconciliation report that **proposes** fixes;
  never apply them.
- **No new judgment in scripts.** Reuses the already-tested `load-config`; enumerates `specs/`
  by plain directory listing (no new script, no brittle parsing).

## Outline

1. Run `{SCRIPT}` from the repo root (the loader substitutes the correct platform-specific
   `load-config` path from this command's `scripts:` frontmatter); parse `roadmap_path`,
   `roadmap_exists`, `adr_dir`, `adr_present`.

2. **Graceful preconditions:** if `roadmap_exists` is false → report that and suggest
   `/speckit.roadmap.write`; stop. If `specs/` is empty or absent → note "no specs on disk"
   (pre-commitment entries are still fine) and continue.

3. Read the roadmap ledger. Enumerate the spec directories on disk by listing `specs/*/`.

4. **Reconcile the WHOLE ledger, with STATUS as the pivot** for disk-existence expectations:
   - `undecided` / `needs-info` / `planned` (pre-commitment) → **no** spec dir expected. If a
     dir exists → **status-lagging** (suggest advancing to `specced` / `in-progress`).
   - `specced` / `in-progress` / `implemented` / `verified` (lifecycle) → a non-empty spec dir
     expected. If the dir is absent OR effectively empty → **phantom-entry**. "Effectively
     empty" = a cheap signal: `spec.md` missing or still the unfilled template (do NOT deep-scan
     content — this avoids false-flagging a freshly created spec dir). **Exception:** an entry
     with NO `spec dir:` pointer is a *process/bootstrap entry* (work not delivered as a
     numbered spec) — report it as an informational "process entry", NOT a phantom.
   - `deferred` / `abandoned` (off-ramp) → dir optional; if present with recent activity →
     **abandoned-but-active** (flag for review).
   - **orphan-spec** — a `specs/NNN-*/` dir with no matching ledger entry → suggest adding it.
   - **dependency-contradiction** — an entry `depends-on` a reference that, resolved against
     the ledger's own entries, is missing or `abandoned`.
   - **superseded-ADR** — an entry `governed-by` an ADR marked superseded (only when
     `adr_present`).

5. **Write the report** to `.specify/memory/roadmap-sync-{timestamp}.md` (roadmap-level, not
   per-feature) using `.specify/extensions/roadmap/templates/review-report-template.md`
   (kind = "Roadmap Sync"). Group findings by divergence type, with a per-type count summary
   at the top, capped at the configured `max_findings` (aggregate any overflow). Include a
   verdict and Recommended Actions. Never overwrite a prior report.

6. **Propose** reconciling actions (add orphan to roadmap, advance status, investigate
   phantom, resolve dependency, supersede entry) as instructions only — apply via
   `/speckit.roadmap.write`. Report the verdict and report path to the user.
