---
description: Read-only post-implementation review — check the implemented spec against its roadmap entry's outcome and scope, classify any drift, and propose marking the entry verified.
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

After implementing a spec, check whether what was built matches what the roadmap said it
should deliver — its **outcome** and **scope** — classify any drift, and propose the next
status. Catch divergence at the moment it happens, and distinguish "the implementation is
wrong" from "the roadmap is stale."

## Operating Constraints

- **STRICTLY READ-ONLY.** Do not modify the roadmap, the spec, or implementation files. The
  only output is a review report that **proposes** changes; never apply them.
- **Constitution authority.** A `governed-by` constraint/ADR violation is automatically a
  🎯 Must-Address finding.
- **No new judgment in scripts.** Reuses the already-tested `load-config` and core
  `check-prerequisites`; adds no deterministic logic of its own.

## Outline

1. Run `{SCRIPT}` from the repo root (the loader substitutes the correct platform-specific
   `load-config` path from this command's `scripts:` frontmatter); parse `roadmap_path`,
   `roadmap_exists`, `adr_dir`, `adr_present`. Resolve the active feature via the core
   `.specify/scripts/bash/check-prerequisites.sh --json --paths-only` script.

2. **Graceful preconditions:**
   - If `roadmap_exists` is false → report that and suggest `/speckit.roadmap.write`. Stop.
   - If no active feature resolves → ask which spec to debrief (do not guess).

3. **Match the implemented spec to its ledger entry** (spec-dir → title → number,
   tolerating numbering drift). If none matches → report the spec is not on the roadmap and
   suggest adding it; stop. If the match is **ambiguous** → list candidates and ask.

4. **Read the inputs to compare**: the matched entry (outcome, scope in/out, `governed-by`),
   `spec.md`, and the **implemented artifacts referenced by the spec's scope/tasks** (keep
   the review bounded — do not scan the whole repository).

5. **Classify drift** (each finding gets a severity 🎯/💡/🤔):
   - **outcome-miss** — the implementation does not deliver the entry's stated outcome. A
     *partial* implementation is an outcome-miss; name the unmet portion.
   - **scope-creep** — built into `scope (out)` or beyond `scope (in)`.
   - **constraint-violation** — breaks a `governed-by` constraint/ADR → always 🎯 Must-Address.
   - **roadmap-stale** — the implementation is correct but the entry no longer reflects what
     was actually decided; the **roadmap** is wrong, not the spec. Classify it this way and
     propose amending the roadmap via `/speckit.roadmap.write`; do NOT report the
     implementation as defective.

6. **Write the report** to `FEATURE_DIR/roadmap-reviews/debrief-{timestamp}.md` using
   `.specify/extensions/roadmap/templates/review-report-template.md` (kind =
   "Post-Implementation Debrief"): Surfaced Context, classified Findings table, Findings
   Summary (capped at the configured `max_findings`; aggregate overflow), a verdict
   (✅ PROCEED / ⚠️ PROCEED WITH UPDATES / 🛑 RETHINK), and Recommended Actions. Create
   `roadmap-reviews/` if needed; never overwrite a prior report.

7. **Propose the status transition** in Recommended Actions: propose `verified` **only when
   the outcome is met AND there are no 🎯 Must-Address findings**; otherwise do not propose
   verified (note a lesser status or none). Instruction only — applied via
   `/speckit.roadmap.write`.

8. **Report** the verdict and the report path to the user.
