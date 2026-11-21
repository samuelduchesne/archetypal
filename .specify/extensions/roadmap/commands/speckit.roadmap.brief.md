---
description: Read-only pre-implementation briefing — surface what the roadmap expects for the spec about to be implemented (outcome, scope, governing decisions, dependencies) and flag pre-implementation drift.
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

Before implementing a spec, surface everything the roadmap records about it so the
implementation is grounded in the decisions, outcomes, and constraints captured earlier —
especially decisions made during the constitution/grilling phase that predate this spec —
and flag any way the spec has already drifted from what the roadmap anticipated.

## Operating Constraints

- **STRICTLY READ-ONLY.** Do not modify the roadmap, the spec, or any other file. The
  only output is a briefing report written under the active feature's
  `roadmap-reviews/` directory.
- **Do not mutate status.** If the entry should move to `in-progress`, **instruct** the
  user to do so via `/speckit.roadmap.write`; never write the status yourself.
- **No new judgment in scripts.** This command reuses the already-tested `load-config`
  and core `check-prerequisites`; it adds no deterministic logic of its own.

## Outline

1. Run `{SCRIPT}` from the repo root (the loader substitutes the correct
   platform-specific `load-config` path from this command's `scripts:` frontmatter);
   parse `roadmap_path`, `roadmap_exists`, `adr_dir`, `adr_present`. Resolve the active
   feature via the core `.specify/scripts/bash/check-prerequisites.sh --json --paths-only`
   script.

2. **Graceful preconditions:**
   - If `roadmap_exists` is false → report that no roadmap exists and suggest
     `/speckit.roadmap.write`. Stop.
   - If no active feature can be resolved → ask the user which spec to brief (do not
     guess).

3. **Match the active spec to its ledger entry**, in this order (tolerating the known
   drift between roadmap entry numbers and `specs/NNN-*` directory numbers):
   1. by `spec dir:` pointer in an entry,
   2. else by title similarity,
   3. else by number.
   If no entry matches → report that the spec is not on the roadmap and suggest adding it
   via `/speckit.roadmap.write`. Stop (do not invent an entry). If the match is
   **ambiguous** (multiple plausible entries, e.g. similar titles) → list the candidates
   and ask the user which entry to brief; do not guess.

4. **Surface the entry's recorded intent** into the report's *Surfaced Context* section:
   description, outcome, scope (in/out), `depends-on` (and the **current status of each
   dependency** — flag any that are `abandoned` or missing), `governed-by`
   decisions/constraints (resolve `ADR-NNNN` pointers only if `adr_present`; otherwise
   note them as unresolved links), `addresses` PRD pointer, and related Open Questions /
   Cross-Cutting Notes.

5. **Detect pre-implementation drift** and record each as a finding: does the spec as
   written still match what the entry anticipated (outcome, scope, governing
   constraints)? Classify findings with the severity vocabulary 🎯 Must-Address /
   💡 Recommendation / 🤔 Question.

6. **Write the report** to `FEATURE_DIR/roadmap-reviews/brief-{timestamp}.md` using
   `.specify/extensions/roadmap/templates/review-report-template.md` as the structure
   (kind = "Pre-Implementation Brief"). Include the Surfaced Context, Findings table,
   Findings Summary, a verdict (✅ PROCEED / ⚠️ PROCEED WITH UPDATES / 🛑 RETHINK), and
   Recommended Actions. Create the `roadmap-reviews/` directory if needed; never
   overwrite a prior report (the timestamp keeps each distinct).

7. **Recommend the status transition** to `in-progress` in the Recommended Actions
   (instruction only — "apply via `/speckit.roadmap.write`"). Do not apply it.

8. **Report** the verdict and the report path to the user.
