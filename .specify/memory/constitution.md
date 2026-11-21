# archetypal Constitution

## Purpose and Place in the Stack

archetypal is where building archetypes are **created**, **translated**, and **codified for
application**.

It exists because the surrounding work now has owners: idfkit owns general EnergyPlus scripting,
and epinterface owns the SBEM archetype data model and the generation of EnergyPlus models from
it. Nobody owns the life of an archetype around them: deriving it from a detailed model or a
published source, moving it between the formats tools use, and stating the rules by which an
archetype is assigned to a real building. archetypal owns that, and only that.

```
archetypal    create · translate · apply
     ↓
epinterface   SBEM data model · composer · EnergyPlus generation
     ↓
idfkit        EnergyPlus I/O · simulation · results · weather · schedules
```

## Core Principles

### I. Archetypes, Not EnergyPlus

archetypal MUST NOT reimplement a capability that idfkit or epinterface provides: model I/O,
schema validation, simulation, result parsing, weather, geometry, schedule evaluation, or
EnergyPlus generation from SBEM.

When archetypal needs something those packages lack, the gap MUST be closed upstream by a pull
request (for example, separate core and perimeter zones in epinterface's `Model`). A local
workaround is allowed only as a temporary bridge that is tracked against the upstream change and
removed when it lands.

*Rationale:* v2 grew into a general EnergyPlus toolkit and duplicated what is now better done
elsewhere. Duplication splits users, bugs, and maintenance effort.

### II. One Archetype Data Model

SBEM, as defined by epinterface, is the single archetype data model. Every capability MUST read
or produce SBEM. Other formats (UMI JSON first; later ClimateStudio and CityGML Energy ADE) are
**translators** to and from SBEM, never parallel models maintained inside archetypal.

A translation MUST state what it loses. A round trip through a translator MUST either reproduce
its input or report exactly which fields could not be represented.

*Rationale:* two data models drift apart and must be kept in sync forever. A single model makes
every translator and every creation method compose with every other.

### III. Small and Focused

archetypal MUST stay a small library with a minimal dependency footprint. The following are out of
scope and MUST NOT be added without amending this constitution:

- simulation orchestration or batch running (idfkit's job);
- calibration against metered data;
- building geometry, or GIS-to-model generation;
- district energy networks;
- Modelica or other non-EnergyPlus engine output.

A new dependency MUST be justified in the plan that introduces it. A heavy or optional capability
MUST live behind an optional extra.

*Rationale:* users who only want to reduce or translate an archetype must not inherit a platform.

### IV. Physically Correct and Verifiable

Every transformation of building data (reduction, translation, derivation from a published source)
MUST state, in its specification, which physical quantities it conserves and how each output
parameter relates to the inputs it is derived from.

Correctness MUST be demonstrated, not asserted. Every transformation MUST be verified against
reference buildings with stated acceptance criteria. A claim that a new method is "more correct"
than a previous one MUST be backed by a comparison on those references.

*Rationale:* archetypes feed decisions about whole building stocks. An error in an aggregation
rule propagates silently into every building it is applied to.

### V. What and Why Before How

A specification (`spec.md`) describes **what** a capability does, **why** it exists, and how its
correctness will be judged. It MUST NOT prescribe algorithms, data structures, or code
organization. Those belong to the plan (`plan.md`), which MUST satisfy the specification and this
constitution.

Existing v2 behaviour is evidence for a specification, never a requirement of it. v3 capabilities
are specified afresh; v2 code is ported only where a plan shows it meets the specification.

*Rationale:* v3 rewrites reduction and aggregation. Fixing the "what" first keeps the rewrite from
reproducing v2's design by inertia.

### VI. A Dependable Public Library

- The public API MUST be fully typed and documented, and every public behaviour MUST be tested.
- User-facing documentation MUST always be in sync with the codebase. A change to public
  behaviour is not complete until the documentation describing it is updated in the same pull
  request. Its examples MUST run against the current release.
- User-facing documentation MUST follow the Diátaxis framework. Every page belongs to exactly one
  of four kinds, and its content serves that kind only:
  - **Tutorials** teach a newcomer by doing, through one guided, working path.
  - **How-to guides** solve one task for a user who already knows what they want.
  - **Reference** describes the API, data model and command line, completely and neutrally.
  - **Explanation** gives the why: concepts, physical assumptions and design decisions (for
    example, what a reduction conserves and why).
  A page that mixes kinds MUST be split.
- archetypal supports the Python versions its dependencies jointly support (3.10–3.12 at
  ratification, bounded by epinterface).
- The project uses uv for environments and builds, Keep a Changelog for `CHANGELOG.md`, and
  semantic versioning.
- A breaking change to the public API requires a MAJOR release and a migration note.

*Rationale:* archetypal is a dependency of other tools; they must be able to trust its contract.
Documentation that lags the code breaks that trust as surely as a bug does.

## Scope

archetypal v3 covers three activities:

- **Create:** derive an archetype from a detailed EnergyPlus model (reduction), and from published
  sources such as TABULA/EPISCOPE and ASHRAE 90.1 vintage tables.
- **Translate:** move archetypes between SBEM and other formats, starting with UMI template
  libraries (JSON).
- **Apply:** codify how archetypes are assigned to buildings, as rule sets for epinterface's
  composer, and check archetype libraries for completeness and plausibility.

Version 2 is kept on a `v2.x` maintenance branch that receives security fixes only.

## Development Workflow

- Work follows Spec Kit: constitution → roadmap → specify → clarify → plan → tasks → implement.
- The roadmap (`.specify/memory/roadmap.md`) records the planned specs, their order, and the
  decisions behind them. A spec that changes scope or reverses a recorded decision MUST update
  the roadmap.
- Every plan MUST pass a Constitution Check against Principles I–IV before tasks are generated,
  and record any justified exception.
- Every plan MUST name the user-facing documentation it adds or changes, with its Diátaxis kind,
  and its tasks MUST include those documentation updates.
- Upstream changes that a spec depends on (idfkit, epinterface) MUST be listed as dependencies of
  that spec, and the spec cannot be marked implemented until they are released.

## Governance

This constitution takes precedence over other project practices. Amendments are made by pull
request that edits this file, states the reason, and bumps the version:

- **MAJOR:** a principle is removed or redefined, or the scope boundary changes in a way that
  invalidates existing specs.
- **MINOR:** a principle or section is added, or guidance is materially expanded.
- **PATCH:** clarifications and wording that do not change meaning.

Reviewers verify compliance with this constitution on every pull request. Any exception MUST be
justified in the relevant plan and recorded there.

**Version**: 1.2.0 | **Ratified**: 2026-11-21 | **Last Amended**: 2026-11-21
