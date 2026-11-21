<!--
SYNC IMPACT REPORT
==================
Version change: 1.2.2 → 1.3.0
Bump rationale: MINOR — new upstream prerequisite UP-6; UP-1, UP-2, UP-4 and UP-5 scope
expanded from the 002 plan's research; UP-3 recorded as met.

Changes this revision:
  - UP-1: also requires SBEM components importable without archetypal, eppy or Prisma, and
    PyYAML declared
  - UP-2: adds the SBEM fields the 002 plan found missing (orientation ratios, infiltration
    schedule, heat-recovery effectiveness, holiday and design-day slots, save/load helpers)
  - UP-3: met (epinterface 1.0.0–1.5.0 on PyPI)
  - UP-4: also loosens exact pins (click, pandas)
  - UP-5: also a faster day-profile evaluation if 002's benchmark needs it
  - UP-6 (new): idfkit Schedule:Year evaluation fix
  - 002: plan written (specs/002-reduce-to-sbem/plan.md)

Specs affected: 002 (and 001, 003 through UP-1/UP-2)
Open questions added/resolved: none

Previous revision (1.2.2):
Version change: 1.2.1 → 1.2.2
Bump rationale: PATCH — status transition (003 planned → specced).

Changes this revision:
  - 003: status specced; spec dir specs/003-umi-translation/

Specs affected: 003
Open questions added/resolved: none

Previous revision (1.2.1):
Version change: 1.2.0 → 1.2.1
Bump rationale: PATCH — status transition (002 planned → specced) and a note on writing order.

Changes this revision:
  - 002: status specced; spec dir specs/002-reduce-to-sbem/
  - 001: notes record that it is written after 002 and 003

Specs affected: 001, 002
Open questions added/resolved: none

Previous revision (1.2.0):
Version change: 1.1.0 → 1.2.0
Bump rationale: MINOR — open questions Q1–Q6 resolved into decisions C-11 … C-16; C-03
broadened from core/perimeter to zone groups (amends 002, 003 and UP-2 without invalidating
them); 008 narrowed to CityGML Energy ADE.

Changes this revision:
  - C-03 redefined: an archetype is a set of zone groups; core/perimeter is one layout (Q6)
  - Added C-11 (zone groups and layouts), C-12 (reduction correctness, Q1), C-13 (UMI fields,
    Q2), C-14 (SBEM change coordination, Q3), C-15 (source licensing, Q4), C-16 (composer and
    ClimateStudio stay in epinterface, Q5)
  - UP-2 broadened to zone groups; 002 and 003 scope updated; 006 and 008 updated
  - Open questions Q1–Q6 marked resolved

Specs affected: 002, 003, 004, 006, 008
Open questions added/resolved: Q1–Q6 resolved; none added

Previous revision (1.1.0):
Version change: 1.0.0 → 1.1.0
Bump rationale: MINOR — C-04 broadened from reduction to all of v3; new decision C-10 (no
release regresses v2's core capability); new open question Q6; UP-4 note made precise.

Changes this revision:
  - C-04: "reduction is rewritten" → "nothing from v2 is ported as is" (constitution 1.3.0, V)
  - Added C-10: v3.0 ships only with 001, 002 and 003 together
  - UP-4: ladybug is used only to read EPW ground temperatures
  - Added Q6: archetype zone layouts richer than core/perimeter
  - 001 notes: 001 is not a release on its own

Specs affected: 001, 002, 003
Open questions added/resolved: Q6 added; none resolved

Previous revision (1.0.0, 2026-11-21): initial roadmap with specs 001–008, decisions
C-01 … C-09, upstream prerequisites UP-1 … UP-5 and open questions Q1 … Q5, harvested from the
v3 design conversation and constitution 1.2.0.

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
- **C-03 — An archetype is a set of zone groups, defined upstream:** epinterface's `Model`
  holds a single zone definition. We extend epinterface (UP-2) so that an archetype holds
  several zone groups, each with its own zone definition and its share of the building's floor
  area. Core/perimeter is one layout among others (C-11). Built by us and contributed by pull
  request rather than wrapped in archetypal.
  ~~Revision 1.0.0: separate core and perimeter zone components only.~~
- **C-04 — Nothing from v2 is ported as is:** every v3 capability is specified and written
  afresh to v3's standards (strict typing, tests, documentation). v2 predates strict typing and
  current tooling; its code may be read to understand past behaviour, never copied in. This
  includes the reduction workflow (`reduce`) and the aggregation of zone properties
  (`combine`). Aggregated schedules are expressed as EnergyPlus `Schedule:Compact` objects. The
  reduction rewrite aims to be more correct and faster than v2, and must show it (C-12).
  *Constitution IV, V.*
  ~~Revision 1.0.0 limited this decision to reduction.~~
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
- **C-10 — No release regresses v2's core capability:** v2's core workflow is "reduce a
  detailed EnergyPlus model and get a UMI template library". v3.0 ships only when 001, 002 and
  003 are all implemented, so a v3.0 user can still do that (reduce to SBEM, then write UMI
  JSON). The spec numbers order the writing, not separate releases.
- **C-11 — Zone groups and layouts** *(resolves Q6)*: reduction groups the detailed model's
  zones by **space use** and by **exposure** (perimeter or core), so a hospital keeps operating
  rooms, patient rooms and corridors apart. This is the default layout. Merging groups follows
  the same conservation rules as forming them, so a coarser layout (down to core/perimeter, as
  UMI requires) is a further reduction of a finer one, never a separate method. Each group
  records the detailed zones it came from. How space use is recognised in a detailed model,
  and how small groups are handled, belong to spec 002.
- **C-12 — What makes a reduction correct** *(resolves Q1)*: both parameter-faithful and
  energy-faithful.
  - *Parameter-faithful:* every archetype parameter is derived by a stated physical rule that
    names the quantity it conserves (for example installed lighting power, envelope heat-loss
    coefficient, outdoor airflow, thermal capacitance, floor area), so an intensity is the
    conserved total divided by the basis it applies to.
  - *Energy-faithful:* on a reference set, the simulated archetype is compared with the
    simulated detailed model. Initial targets: total annual site energy within ±5 %; each major
    end use (heating, cooling, interior lighting, interior equipment, fans, service hot water)
    within ±10 %; annual peak heating and cooling demand within ±15 %. v3 must also have a
    smaller error than v2 on the same set, which is what "more correct" means.
  - *Reference set:* the DOE/PNNL commercial prototype buildings (all building types) in at
    least three climate zones (hot, mixed, cold), plus at least one residential model.
  - Spec 002's clarification may tighten or adjust a target once a v2 baseline is measured, but
    may not drop one. The comparison exercises the whole chain (reduction, then epinterface's
    model generation), which is the chain users rely on.
- **C-13 — UMI fields** *(resolves Q2)*: every UMI field that affects simulation results
  (structure and thermal mass, window settings, partition ratio, among others) must be
  representable in SBEM; where it is not, UP-2 adds it. Descriptive fields (names, comments,
  lifespan, embodied-carbon data) map to SBEM's metadata and environmental fields. Nothing is
  dropped silently. The field-by-field mapping is part of spec 003.
- **C-14 — Coordinating changes to SBEM** *(resolves Q3)*: archetypal pins epinterface to a
  compatible version range; every SBEM change archetypal needs is made upstream by our own pull
  request; archetypal's test suite also runs against epinterface's development branch so a
  breaking change is seen before it is released. archetypal uses only SBEM's public model.
- **C-15 — Licensing of published sources** *(resolves Q4)*: archetypal ships readers, not
  copies of source data, unless the source's licence explicitly allows redistribution. Every
  derived archetype records its source and that source's licence in its provenance. Data under
  non-commercial licences (for example EUBUCCO, CC BY-NC) is never bundled.
- **C-16 — The composer and ClimateStudio stay in epinterface** *(resolves Q5)*: archetypal does
  not build a second composer. Spec 006 delivers rule sets for epinterface's composer and the
  means to author, test and share them; anything the composer lacks is added upstream.
  epinterface already reads ClimateStudio templates, so that translator stays there.

## Upstream Prerequisites

Not archetypal specs. Pull requests to other repositories that archetypal specs depend on.

- **UP-1 — epinterface uses idfkit instead of archetypal/eppy.** Removes the circular
  dependency (epinterface currently pins `archetypal==2.18.10`). A draft PR is open. It must
  also leave `epinterface.sbem.components` importable without archetypal, eppy or a generated
  Prisma client, and declare PyYAML (imported by `sbem/builder.py`, undeclared in 1.5.0).
  *Blocking for 002.*
- **UP-2 — epinterface `Model` holds several zone groups** (zone definition plus floor-area
  share, C-03), plus whatever simulation-relevant fields the UMI field mapping shows are missing
  (C-13). Built by us, contributed by PR. The 002 plan's research adds: envelope and window
  ratios by orientation, an infiltration schedule, numeric heat-recovery effectiveness,
  holiday and design-day slots in `WeekComponent`, and save/load helpers with a schema version.
  Zone groups block 002; each added field does not (its loss is reported until it lands).
  ~~Revision 1.0.0: separate core and perimeter zones only.~~
- **UP-3 — epinterface is published on PyPI.** A package on PyPI cannot depend on a git
  repository, so no v3 release can ship before this. **Met:** releases 1.0.0–1.5.0 are on PyPI
  (checked 2026-11-21).
- **UP-4 — epinterface's heavy dependencies become optional extras** (Prisma, geopandas,
  ladybug). Desirable, not blocking; keeps archetypal's install small (C-06, constitution III).
  ladybug-core is used once, in `sbem/builder.py`, to read monthly ground temperatures from the
  EPW file; idfkit's weather module is the likely replacement, which would drop the dependency
  rather than make it optional. Also loosen 1.5.0's exact pins (`click==8.1.7`,
  `pandas<2.3`), which would otherwise constrain every archetypal user.
- **UP-5 — idfkit: `Schedule:Compact` creation aware of day types** (weekday, weekend,
  holiday). Optional; only if spec 002's plan shows idfkit is the right home for it. The 002
  plan adds: a faster day-profile schedule evaluation, needed only if 002's performance
  benchmark (about 55 ms per schedule-year in 1.3.0rc2) misses its budget.
- **UP-6 — idfkit: `Schedule:Year` evaluation fails on loaded models.** In 1.3.0rc2,
  `schedules/year.py` calls `int('1.0')` on month and day fields parsed as floats, so every
  `Schedule:Year` read from a file raises `ValueError`. Fix before idfkit 1.3.0 final. 002
  bridges it temporarily (plan, Complexity Tracking). *Blocking for 002's release.*

## Planned Specs

### v3.0 — the narrowest useful release

### 001 — archetypal 3 foundation and migration from v2  [status: specced]

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
- **Notes:** Not a release on its own (C-10): it ships together with 002 and 003 as v3.0.
  Written after 002 and 003: its public surface and command line describe what those specs
  deliver, so writing it first would mean guessing at them. The `reduce` command keeps its v2
  name and form and defaults to a UMI library (spec FR-012).
- **Spec dir:** specs/001-foundation-migration/

### 002 — Reduce a detailed EnergyPlus model to an SBEM archetype  [status: specced]

- **Description:** Turn a detailed, multizone EnergyPlus model (and the results of simulating
  it) into one SBEM archetype made of zone groups (by space use and exposure, C-11), describing
  what is conserved and why.
- **Outcome:** a modeller reduces any supported EnergyPlus model to an SBEM archetype, at the
  default layout or a coarser one down to core/perimeter, and gets evidence that it is faithful
  to the original by the criteria in C-12.
- **Scope (in):** how space use and exposure are recognised and zones grouped; how groups are
  merged into coarser layouts; the geometric characteristics the archetype must carry to be
  simulated (floor-area shares, envelope and window areas by orientation, storeys); how every
  archetype
  parameter (envelope, internal loads, conditioning, ventilation, domestic hot water, schedules)
  relates to the detailed model; how zone multipliers and non-conditioned zones count; what the
  reduction conserves; schedules expressed as `Schedule:Compact`; how correctness is
  demonstrated on reference buildings; the matching explanation page in the docs.
- **Scope (out):** algorithms and code structure (the plan's job, C-04); calibration (C-05);
  generating EnergyPlus from the archetype (epinterface).
- **Depends on:** 001, UP-1, UP-2, UP-6
- **Governed by:** C-02, C-03, C-04, C-11, C-12
- **Spec dir:** specs/002-reduce-to-sbem/ (plan written; research.md raises spec feedback F-1
  on SC-002 and F-2 on FR-023 for `/speckit-analyze`)
- **Notes:** The spec states the *what* and *why* of reduction, not the *how*, so that
  `/speckit-plan` can design the rewrite freely. Evidence gathered from v2 for the spec's
  motivation: perimeter aggregation includes core zones; zone multipliers are applied by
  duplication, which skews pairwise averaging; weighting rules differ by parameter without a
  stated reason; core detection ignores horizontal surfaces; schedule handling is slow (#3).
  Related v2 issues: #383 (small core floor plates), #390 (DHW too large), #66/#123/#127
  (conditioning and COP accuracy).

### 003 — Translate UMI template libraries to and from SBEM  [status: specced]

- **Description:** Read a UMI template library (JSON) into SBEM archetypes, and write SBEM
  archetypes out as a UMI template library, so existing UMI libraries keep their value.
- **Outcome:** a UMI library survives a round trip, or the user receives a report of exactly
  which fields could not be represented (constitution II).
- **Scope (in):** the field-by-field correspondence between UMI and SBEM (C-13); writing an
  archetype with more than two zone groups to UMI by first merging it to core/perimeter
  (C-11), and reporting that merge as a loss; what is lost in each direction and how the user
  is told; UMI library-level concerns (shared components,
  naming, duplicates such as #459).
- **Scope (out):** UMI templates as editable Python objects (C-02); other formats (008).
- **Depends on:** 001, UP-2
- **Governed by:** C-02, C-11, C-13
- **Spec dir:** specs/003-umi-translation/
- **Notes:** The field mapping done for this spec also decides what UP-2 must add to
  epinterface (C-13).

### v3.1 — create from published sources

### 004 — Archetypes from TABULA/EPISCOPE  [status: planned]

- **Description:** Create SBEM archetypes from the TABULA/EPISCOPE residential typologies.
- **Outcome:** a user selects a country, building type and age band and gets an SBEM
  archetype whose values trace back to the TABULA source.
- **Scope (in):** which TABULA data are used and how each maps to SBEM; provenance of every
  value; behaviour when data are missing.
- **Scope (out):** scraping the TABULA web tool as v2 did.
- **Depends on:** 001
- **Notes:** TABULA has no API; the stable source is the published workbook. Licensing per
  C-15: archetypal reads the workbook, and bundles derived data only if its licence allows.

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
- **Governed by:** C-15, C-16

### 007 — Archetype library quality checks  [status: planned]

- **Description:** Check an archetype library for completeness and physical plausibility
  (for example U-values, internal load densities, EUI against benchmarks) before it is used.
- **Outcome:** a user runs the checks on a library and gets a report of what is missing or
  implausible, with the reason for each finding.
- **Scope (in):** which checks; where the plausible ranges come from.
- **Depends on:** 001

### Later

### 008 — Translate to and from CityGML Energy ADE  [status: undecided]

- **Description:** A translator between SBEM archetypes and CityGML Energy ADE, the city-scale
  data standard.
- **Outcome:** _to be defined_
- **Scope (in):** _to be defined_
- **Notes:** Undecided because CityGML Energy ADE has no archetype-library standard yet; revisit
  when its 3.0 version settles one. ClimateStudio was dropped from this entry: that translator
  stays in epinterface (C-16).

## Open Questions

None open. Resolved in revision 1.2.0:

- ~~Q1 — What makes a reduction correct?~~ → C-12
- ~~Q2 — Which UMI building-level fields must SBEM represent?~~ → C-13
- ~~Q3 — How are changes to the shared SBEM model coordinated?~~ → C-14
- ~~Q4 — Licensing of published sources~~ → C-15
- ~~Q5 — Which of "apply" and the translators belong in archetypal?~~ → C-16
- ~~Q6 — Can an archetype hold more than a core and a perimeter zone?~~ → C-03, C-11

## Cross-Cutting Notes

- **Reference buildings** used to verify transformations (constitution IV) are shared across
  002, 003 and 005, and defined once in C-12.
- **Provenance** (where each archetype value came from) appears in 002, 004 and 005; it should
  mean the same thing in each.
- **Explanation pages** in the documentation carry the physical rules of each transformation
  (constitution VI), so every create or translate spec owns one.

---

**Version**: 1.3.0 | **Ratified**: 2026-11-21 | **Last Amended**: 2026-11-21
