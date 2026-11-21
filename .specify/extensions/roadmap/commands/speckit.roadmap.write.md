---
description: Create or amend the project spec roadmap after the constitution — capturing spec-specific decisions, outcomes, constraints, and the intent of specs not yet written so they are not lost.
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

Produce or amend a durable **spec roadmap** at the configured path (default
`.specify/memory/roadmap.md`). The roadmap is a project-level governance artifact,
beside the constitution, that captures the WHY — decisions, technology choices,
intended outcomes, constraints — and a ledger of planned specs with their scope,
dependencies, and lifecycle status. Its purpose is to prevent loss of
constitution-phase and grilling discussion, **especially** for specs that will not
be written until weeks or months later.

This command is **self-detecting**: if the roadmap does not exist, create it from
the template; if it exists, amend it non-destructively and bump its version.

## Operating Constraints

- **Non-destructive (Constitution Principle III).** Never overwrite user-authored
  content. On amend, preserve existing entries and prose; add or restatus, do not
  clobber. Superseded content is struck through or marked, never deleted.
- **No fabrication (Principle VI).** Harvested context PRE-FILLS proposed content,
  but you MUST confirm with the user, not silently assume. Ask for genuine gaps;
  never invent goals, outcomes, or decisions to fill space. Unknowns become Open
  Questions or `needs-info` / `undecided` entries.
- **Reference, don't author, external artifacts.** Link ADRs (`governed-by:`) and
  PRDs (`addresses:`) when present; never write ADR or PRD files.

## Outline

1. Run `{SCRIPT}` from the repo root and parse its JSON: `roadmap_path`,
   `roadmap_exists`, `adr_dir`, `adr_present`, `prd_globs`. All paths are relative
   to the repo root. (The loader substitutes the correct platform-specific `load-config`
   path from this command's `scripts:` frontmatter.) If the script fails, abort and relay
   its error.

2. **Harvest existing context** (read, in priority order — do not re-ask what these
   already answer):
   - `.specify/memory/constitution.md` — the principles just established.
   - Detected ADRs under `adr_dir` (if `adr_present`) — record `governed-by:`
     pointers; do not re-litigate settled decisions.
   - Detected PRD(s) matching `prd_globs` — harvest goals/outcomes/scope; record
     `addresses:` pointers.
   - **Live session context** — if this command runs in the same session as the
     constitution or a grilling/brainstorming discussion, that discussion is
     already available; harvest it rather than re-asking.
   - **Prior persistent context** — handover files and memory (`.specify/memory/`,
     any handover store, `MEMORY.md`) from earlier sessions.

3. **Determine the interaction mode.** If you are running interactively with a user,
   use the elicitation loop below. If you are running **non-interactively** (a
   delegated agent, a hook with no human channel, or `$ARGUMENTS` signals
   unattended): do NOT block waiting for answers — fill what harvested context
   supports and record every genuine gap as an Open Question or a `needs-info` /
   `undecided` ledger entry, then report the gaps prominently. Never fabricate to
   avoid asking.

4. **Branch on `roadmap_exists`:**

   **If it does NOT exist (create):**
   - Load `.specify/extensions/roadmap/templates/roadmap-template.md` as the
     structure.
   - Pre-fill Vision & End States, Constraints & Decisions, and the Planned Specs
     ledger from harvested context.
   - For each genuine gap, in interactive mode ask the user focused, structured
     questions (in the style of `/speckit.clarify` — a small number of targeted
     questions, not a freeform dump): end states/vision, the set of planned specs
     and rough sequencing, scope in/out per spec, intended outcomes,
     constraints/decisions, and open questions. In non-interactive mode, record the
     gaps per step 3.
   - In interactive mode, present the harvested + proposed content for the user to
     confirm or correct before writing.
   - Write the roadmap to `roadmap_path` at **version 1.0.0**, ratified today, with
     a completed Sync Impact Report.

   **If it DOES exist (amend):**
   - Read the current roadmap. **Integrity check first (FR-011a):** confirm it has the
     required structure — a Sync Impact Report comment, the expected sections, and a
     `**Version**: X.Y.Z | **Ratified**: … | **Last Amended**: …` footer. If it is
     unparseable, hand-corrupted, or missing required structure, **STOP**: report
     exactly what is wrong and PROPOSE a corrected version for the user to approve —
     do NOT overwrite or further corrupt the file. Only proceed once the structure is
     sound (or the user approves the proposed correction).
   - Ask the user only about the **delta** — new specs, status transitions, new
     decisions/constraints, scope changes, resolved or new open questions. Do not
     re-run full elicitation.
   - Apply the changes non-destructively: add or restatus entries; mark superseded
     content (strike through / annotate) rather than deleting it. Re-running with no
     new input MUST NOT duplicate or corrupt content (idempotent — FR-011).
   - **Bump the version** per these roadmap-specific semver rules:
     - **MAJOR** — direction/governance change: removing or redefining a Vision /
       End-State, or reversing a constraint/decision that invalidates existing
       entries.
     - **MINOR** — structural additions: a new planned spec, a new
       constraint/decision, a new Open Question, or a material scope change.
     - **PATCH** — status transitions and wording/clarifications (the common case).
     - If the bump type is ambiguous, state your reasoning before finalizing.
   - Update the Sync Impact Report and the `**Last Amended**` date.

5. **Report** to the user: created vs amended, the version (and bump rationale if
   amended), the spec entries and their statuses, and any Open Questions /
   `needs-info` items still requiring resolution.

## Ledger entry rules

Each Planned Specs entry uses the template skeleton. Required fields: heading
(`NNN — title`), `status`, `description`, `outcome`, `scope (in)`. Recommended:
`scope (out)`, `depends on`, `notes`. Optional: `governed by`, `addresses`,
`spec dir`. Status vocabulary (lifecycle): `undecided` · `needs-info` · `planned` ·
`specced` · `in-progress` · `implemented` · `verified` · `deferred` · `abandoned`.

For `undecided` / `needs-info` / `deferred` / `abandoned` entries, the `outcome` and
`scope (in)` fields MAY be recorded as not-yet-defined (e.g. `_to be defined_`) —
these statuses legitimately precede or forgo full definition. All other statuses
require the MUST fields.
