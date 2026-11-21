<!--
SYNC IMPACT REPORT
==================
Version change: [OLD] → [NEW]
Bump rationale: [MAJOR|MINOR|PATCH] — [one line: what changed and why this bump]

Changes this revision:
  - [Added spec NNN — title]
  - [Status: NNN planned → in-progress]
  - [Decision recorded: C-0N / linked ADR-NNNN]
  - [Scope changed on NNN: ...]

Specs affected: [list of NNN ids touched, or "none"]
Open questions added/resolved: [list, or "none"]

Notes: [anything a future reader needs to understand this revision]
-->

# [PROJECT_NAME] — Spec Roadmap

Living, non-binding map of the specs planned for [PROJECT_NAME]. It is **not a
commitment to order or scope** — it captures the spec-specific discussion,
decisions, technology choices, outcomes, and constraints surfaced during the
constitution and grilling phases so they are not lost before the spec that needs
them is written. Specs are scoped and clarified when they are actually started.
Foundations: the project [constitution](constitution.md)[ and any detected PRD].

Status legend (lifecycle): **undecided** · **needs-info** · **planned** ·
**specced** · **in-progress** · **implemented** · **verified** · **deferred** ·
**abandoned**.

---

## Vision & End States

<!-- The big-picture goals and outcomes this project is driving toward.
     Harvested from the constitution / PRD / session; confirmed with the user. -->

- [End state 1 — what "done" looks like at the project level]
- [End state 2]

## Constraints & Decisions

<!-- Cross-cutting constraints and the durable "why". Lightweight, non-ADR notes
     live inline here. Formal decisions link out: governed-by: ADR-NNNN.
     Each gets a stable id (C-01, C-02, ...) so spec entries can reference it. -->

- **C-01 — [constraint or decision title]:** [statement]. [rationale]
  [_See ADR-NNNN_ if a formal record exists.]
- **C-02 — [...]:** [...]

## Planned Specs

<!-- THE LEDGER. The spine of the roadmap. Optional grouping headers (###) may
     organize entries by theme/phase (e.g. "Core platform", "Cross-cutting").
     Each entry follows the skeleton below.
     MUST: heading, status, description, outcome, scope-in.
     SHOULD: scope-out, depends-on, notes.
     MAY: governed-by, addresses, spec-dir. -->

### 001 — [Spec Title]  [status: planned]

- **Description:** [what this spec is — one or two scannable sentences]
- **Outcome:** [the end state it delivers / what "done" looks like — the debrief
  checks the implementation against this]
- **Scope (in):** [what is included]
- **Scope (out):** [explicit non-goals]
- **Depends on:** [NNN, NNN — or "none"]
- **Governed by:** [ADR-NNNN, C-0N — or omit]
- **Addresses:** [PRD goal/section pointer — or omit]
- **Spec dir:** [specs/001-.../ — set once the spec exists; otherwise omit]
- **Notes:** [free prose — the why, grilling residue, risks, open threads]

### 002 — [Spec Title]  [status: undecided]

- **Description:** [...]
- **Outcome:** [...]
- **Scope (in):** [...]
- **Notes:** [why this is still undecided / what would move it to planned]

## Open Questions

<!-- Unresolved items not yet attached to a specific spec. Feeds 'needs-info'
     and 'undecided' entries. Resolve into the ledger as decisions firm up. -->

- [Q1 — open question + what evidence/decision would resolve it]
- [Q2]

## Cross-Cutting Notes

<!-- Architecture-level notes that span multiple specs. -->

- [Note spanning several specs]

---

**Version**: [VERSION] | **Ratified**: [RATIFICATION_DATE] | **Last Amended**: [LAST_AMENDED_DATE]
