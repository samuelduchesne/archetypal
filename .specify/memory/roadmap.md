<!--
SYNC IMPACT REPORT
==================
Version change: (none) → 1.0.0
Bump rationale: initial roadmap, harvested from the v3 design conversation (2026-11-21) and
constitution 1.2.0.

Changes this revision:
  - Added specs 001–007 (v3.0: 001–003; v3.1: 004–005; v3.2: 006–007) and 008 (undecided)
  - Recorded decisions C-01 … C-09
  - Recorded upstream prerequisites UP-1 … UP-5
  - Recorded open questions Q1 … Q5

Specs affected: 001–008
Open questions added/resolved: Q1–Q5 added; none resolved

Notes: No ADRs (docs/adr/ absent) and no PRD detected. Decisions live inline as C-xx.
The upstream items are pull requests to other repositories (epinterface, idfkit); they are not
archetypal specs, but specs that depend on them cannot be marked implemented until they are
released (constitution, Development Workflow).
-->

# archetypal — Spec Roadmap

Living, non-binding map of the specs planned for archetypal v3. It is **not a commitment to
order or scope**. It captures the decisions, technology choices, outcomes and constraints from
the v3 design conversation so they are not lost before the spec that needs them is written.
Specs are scoped and clarified when they are actually started. Foundation: the project
[constitution](constitution.md) (1.2.0).

Status legend (lifecycle): **undecided** · **needs-info** · **planned** · **specced** ·
**in-progress** · **implemented** · **verified** · **deferred** · **abandoned**.

---

## Vision & End States

- **archetypal is where building archetypes are created, translated, and codified for
  application**, and nothing more. General EnergyPlus work lives in idfkit; the archetype data
  model and EnergyPlus generation live in epinterface.
- A modeller can turn a detailed EnergyPlus model into an SBEM archetype with separate core and
  perimeter zones, and can see evidence that the reduction is faithful to the original.
- UMI users can bring their template libraries into SBEM and back, and are told exactly what, if
  anything, did not survive the trip.
- Archetypes can be created from published sources (TABULA/EPISCOPE, ASHRAE 90.1 vintages)
  without hand-entering values.
- The rules that assign an archetype to a real building (use × vintage × region × …) are
  written down as shareable rule sets, and archetype libraries can be checked for completeness
  and plausibility.
- Installing archetypal no longer brings a general EnergyPlus toolkit with it: v2's EnergyPlus
  layer is gone, and the user-facing documentation (Diátaxis) always matches the code.

## Constraints & Decisions

- **C-01 — Stack:** archetypal depends on epinterface, which depends on idfkit. archetypal never
  reimplements what either provides; missing capabilities are added upstream by pull request.
  *Constitution I.*
- **C-02 — One data model:** epinterface's SBEM is the only archetype data model. UMI becomes a
  translator; v2's UMI template classes (`archetypal/template/`) are not carried into v3 as a
  model. Chosen over keeping UMI as a second model (two models to keep in sync) and over a new
  neutral model (yet another standard). *Constitution II.*
- **C-03 — Core/perimeter lives upstream:** epinterface's `Model` holds a single zone
  definition. Rather than add a building-level wrapper in archetypal, we extend epinterface to
  support separate core and perimeter zone components ourselves and contribute it by pull
  request (UP-2).
- **C-04 — Reduction is rewritten, not ported:** both the reduction workflow (`reduce`) and
  the aggregation of zone properties (`combine`) are specified afresh for v3. v2's behaviour is
  evidence, not a requirement. Aggregated schedules are expressed as EnergyPlus
  `Schedule:Compact` objects. The rewrite aims to be more correct and faster than v2, and must
  show it (Q1). *Constitution IV, V.*
- **C-05 — Calibration is out of scope for now:** no calibration against metered data in v3.
  *Constitution III.*
- **C-06 — Out of scope:** simulation orchestration and batch runs, building geometry and
  GIS-to-model generation, district energy networks, Modelica output. *Constitution III.*
- **C-07 — Platform and tooling:** Python 3.10–3.12 (bounded by epinterface), uv, Keep a
  Changelog, semantic versioning. *Constitution VI.*
- **C-08 — v2 lifecycle:** v2 moves to a `v2.x` maintenance branch for security fixes only.
  Open PR #554 (moving v2 onto idfkit) is superseded by v3, which removes the code it ports.
- **C-09 — Documentation:** user-facing documentation follows Diátaxis and is updated in the
  same pull request as the behaviour it describes. *Constitution VI.*

## Upstream Prerequisites

Not archetypal specs. Pull requests to other repositories that archetypal specs depend on.

- **UP-1 — epinterface uses idfkit instead of archetypal/eppy.** Removes the circular
  dependency (epinterface currently pins `archetypal==2.18.10`). A draft PR is open.
- **UP-2 — epinterface `Model` supports separate core and perimeter zones**, plus whatever
  building-level fields the UMI field mapping shows are missing (Q2). Built by us, contributed
  by PR.
- **UP-3 — epinterface is published on PyPI.** A package on PyPI cannot depend on a git
  repository, so no v3 release can ship before this.
- **UP-4 — epinterface's heavy dependencies become optional extras** (Prisma, geopandas,
  ladybug). Desirable, not blocking; keeps archetypal's install small (C-06, constitution III).
- **UP-5 — idfkit: `Schedule:Compact` creation aware of day types** (weekday, weekend,
  holiday). Optional; only if spec 002's plan shows idfkit is the right home for it.

## Planned Specs

### v3.0 — the narrowest useful release

### 001 — archetypal 3 foundation and migration from v2  [status: planned]

- **Description:** What a user gets when they install archetypal 3: a small package built on
  epinterface and idfkit, with v2's general EnergyPlus toolkit removed, a documentation site
  organised by Diátaxis, and a guide for v2 users.
- **Outcome:** `pip install archetypal` (3.x) pulls in no EnergyPlus toolkit of its own; every
  v2 capability that was removed points the user to its idfkit or epinterface replacement; v2
  remains installable from its maintenance line.
- **Scope (in):** the package's public surface and command line as a whole; removal of v2
  modules that duplicate idfkit (EnergyPlus model handling, simulation, transitions, result
  readers, schedules, data portal, vendored geomeppy); v2 → v3 migration guide; documentation
  site structure; v2 maintenance branch.
- **Scope (out):** reduction and translation behaviour themselves (002, 003).
- **Depends on:** UP-1, UP-3
- **Governed by:** C-01, C-07, C-08, C-09
- **Notes:** Ordered first because 002 and 003 need somewhere to live, but it can be specified
  alongside them. Whether the `reduce` command keeps its v2 name and arguments is a question for
  this spec.

### 002 — Reduce a detailed EnergyPlus model to an SBEM archetype  [status: planned]

- **Description:** Turn a detailed, multizone EnergyPlus model (and the results of simulating
  it) into one SBEM archetype with a core zone and a perimeter zone, describing what is
  conserved and why.
- **Outcome:** a modeller reduces any supported EnergyPlus model to an SBEM archetype and gets
  evidence that it is faithful to the original, by the definition settled in Q1.
- **Scope (in):** which zones count as core and which as perimeter; how every archetype
  parameter (envelope, internal loads, conditioning, ventilation, domestic hot water, schedules)
  relates to the detailed model; how zone multipliers and non-conditioned zones count; what the
  reduction conserves; schedules expressed as `Schedule:Compact`; how correctness is
  demonstrated on reference buildings; the matching explanation page in the docs.
- **Scope (out):** algorithms and code structure (the plan's job, C-04); calibration (C-05);
  generating EnergyPlus from the archetype (epinterface).
- **Depends on:** 001, UP-1, UP-2
- **Governed by:** C-02, C-03, C-04
- **Notes:** The spec states the *what* and *why* of reduction, not the *how*, so that
  `/speckit-plan` can design the rewrite freely. Evidence gathered from v2 for the spec's
  motivation: perimeter aggregation includes core zones; zone multipliers are applied by
  duplication, which skews pairwise averaging; weighting rules differ by parameter without a
  stated reason; core detection ignores horizontal surfaces; schedule handling is slow (#3).
  Related v2 issues: #383 (small core floor plates), #390 (DHW too large), #66/#123/#127
  (conditioning and COP accuracy).

### 003 — Translate UMI template libraries to and from SBEM  [status: planned]

- **Description:** Read a UMI template library (JSON) into SBEM archetypes, and write SBEM
  archetypes out as a UMI template library, so existing UMI libraries keep their value.
- **Outcome:** a UMI library survives a round trip, or the user receives a report of exactly
  which fields could not be represented (constitution II).
- **Scope (in):** the field-by-field correspondence between UMI and SBEM; what is lost in
  each direction and how the user is told; UMI library-level concerns (shared components,
  naming, duplicates such as #459).
- **Scope (out):** UMI templates as editable Python objects (C-02); other formats (008).
- **Depends on:** 001, UP-2
- **Governed by:** C-02
- **Notes:** The field mapping done for this spec also decides what UP-2 must add to
  epinterface (Q2).

### v3.1 — create from published sources

### 004 — Archetypes from TABULA/EPISCOPE  [status: planned]

- **Description:** Create SBEM archetypes from the TABULA/EPISCOPE residential typologies.
- **Outcome:** a user selects a country, building type and age band and gets an SBEM
  archetype whose values trace back to the TABULA source.
- **Scope (in):** which TABULA data are used and how each maps to SBEM; provenance of every
  value; behaviour when data are missing.
- **Scope (out):** scraping the TABULA web tool as v2 did.
- **Depends on:** 001
- **Notes:** TABULA has no API; the stable source is the published workbook. Licensing to be
  confirmed (Q4).

### 005 — Archetypes from ASHRAE 90.1 vintages  [status: planned]

- **Description:** Create SBEM archetypes from the ASHRAE 90.1 / PNNL prototype buildings by
  vintage and climate zone.
- **Outcome:** a user selects a prototype, vintage and climate zone and gets an SBEM archetype
  whose values trace back to the source.
- **Scope (in):** which prototypes and vintages; whether values come from the standard's tables
  or from reducing the prototype models with 002; provenance.
- **Depends on:** 001; possibly 002
- **Notes:** Whether this is "read the tables" or "reduce the prototypes" is open and belongs
  to this spec.

### v3.2 — apply

### 006 — Rules for assigning archetypes to buildings  [status: planned]

- **Description:** Write down, as shareable rule sets, how a building's attributes (use,
  vintage, region, size, …) select an archetype and its components, using epinterface's
  composer.
- **Outcome:** a rule set and a table of buildings produce a building-to-archetype assignment
  that is reproducible and explains each choice, including what happens when attributes are
  missing.
- **Scope (in):** what a rule set expresses; fallbacks for missing attributes; how rule sets
  are shared and versioned.
- **Scope (out):** geometry and GIS processing (C-06).
- **Depends on:** 001; epinterface composer

### 007 — Archetype library quality checks  [status: planned]

- **Description:** Check an archetype library for completeness and physical plausibility
  (for example U-values, internal load densities, EUI against benchmarks) before it is used.
- **Outcome:** a user runs the checks on a library and gets a report of what is missing or
  implausible, with the reason for each finding.
- **Scope (in):** which checks; where the plausible ranges come from.
- **Depends on:** 001

### Later

### 008 — More translators (ClimateStudio, CityGML Energy ADE)  [status: undecided]

- **Description:** Additional translators between SBEM and other archetype formats.
- **Outcome:** _to be defined_
- **Scope (in):** _to be defined_
- **Notes:** epinterface already reads ClimateStudio templates, so a ClimateStudio translator
  may belong there rather than here. CityGML Energy ADE has no archetype-library standard yet.

## Open Questions

- **Q1 — What makes a reduction correct?** Parameter-faithful (each archetype value is the
  right physical aggregate of the detailed model), energy-faithful (the simulated archetype
  reproduces the detailed model's results within a tolerance), or both. If energy-faithful:
  which results (annual end uses, peak loads), what tolerance, and which reference buildings.
  Blocks the acceptance criteria of 002.
- **Q2 — Which UMI building-level fields must SBEM represent?** Structure and thermal mass,
  window settings, partition ratio, lifespan and metadata: each is either already in SBEM, added
  by UP-2, or dropped by v3. Settled by the field mapping in 003.
- **Q3 — How are changes to the shared SBEM model coordinated** with epinterface's maintainer,
  so archetypal is not broken by schema changes it did not plan for?
- **Q4 — Licensing of published sources** (TABULA, and any building-stock data used by 006)
  for redistribution of derived archetypes.
- **Q5 — Coordination with the epinterface authors** on scope: epinterface already has a
  composer and a ClimateStudio reader; confirm which of "apply" (006) and translators (008)
  belong in archetypal.

## Cross-Cutting Notes

- **Reference buildings** used to verify transformations (constitution IV) are shared across
  002, 003 and 005; choosing them once avoids each spec inventing its own.
- **Provenance** (where each archetype value came from) appears in 002, 004 and 005; it should
  mean the same thing in each.
- **Explanation pages** in the documentation carry the physical rules of each transformation
  (constitution VI), so every create or translate spec owns one.

---

**Version**: 1.0.0 | **Ratified**: 2026-11-21 | **Last Amended**: 2026-11-21
