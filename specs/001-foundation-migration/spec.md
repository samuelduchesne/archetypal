# Feature Specification: archetypal 3 foundation and migration from v2

**Feature Branch**: `claude/admiring-meitner-1f43qk` (spec 001 in the roadmap)

**Created**: 2026-11-21

**Status**: Draft

**Input**: Roadmap entry 001 (roadmap 1.2.2): "What a user gets when they install archetypal 3:
a small package built on epinterface and idfkit, with v2's general EnergyPlus toolkit removed,
a documentation site organised by Diátaxis, and a guide for v2 users." Governed by constitution
1.3.0 (purpose, Principles I, III, V, VI) and roadmap decisions C-01, C-04, C-06, C-07, C-08,
C-09, C-10.

## Why this exists

archetypal v2 grew into two things at once: a general toolkit for EnergyPlus models (reading
and editing models, running simulations, upgrading versions, reading results, evaluating
schedules, editing geometry) and a tool for building archetypes (reducing a detailed model to
an archetype and writing UMI template libraries). The first half is now done better by idfkit,
and the archetype data model by epinterface (roadmap C-01, C-02). Keeping both halves would
leave users with two toolkits that disagree and maintainers with code that predates strict
typing (C-04).

v3 is therefore smaller: it is where archetypes are created, translated and codified for
application, and nothing else (constitution, purpose). Specs 002 and 003 define what v3 does
with archetypes. This spec defines **what a user gets when they install it**:

- **One coherent package.** A user sees one set of commands and one public programming
  interface covering reduction (002) and UMI translation (003), not the leftovers of v2.
- **No second EnergyPlus toolkit.** Installing archetypal 3 brings idfkit and epinterface,
  not a private copy of what they do, so the install stays small (constitution III).
- **A safe path from v2.** archetypal has users who script against v2. A major version that
  removes most of the package is only acceptable if every removed capability is named, its
  replacement is shown, and v2 stays installable for those who cannot move yet (C-08).
- **Documentation that can be trusted.** v2's documentation mixes tutorials, reference and
  explanation and has drifted from the code. v3 starts with a site organised by Diátaxis and
  kept in sync with the code (constitution VI, C-09).

This spec is not a release on its own: v3.0 ships only when 001, 002 and 003 are all done
(C-10).

## Clarifications

### Session 2026-11-21

- Q: In what file format does the reduce command write an SBEM archetype, so that the merge
  and compare commands and other tools can read it back? → A: epinterface's own serialisation
  of its model, one file per archetype; reports are written as separate files beside it.
- Q: In what form are the reduction and loss reports written? → A: One structured,
  machine-readable file per report, plus a short human-readable summary printed by the command.
- Q: For how long after v3.0 does the v2.x line receive security fixes? → A: 12 months after
  v3.0 or until v3.1 ships (restoring TABULA), whichever is later.
- Q: How is it checked that a v2 user can follow the migration guide? → A: No user study:
  migration is developed without user feedback. The guide is checked by running its examples
  (SC-004) and by the coverage check against v2 (SC-003); the moderated test is removed.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reduce a model to a UMI library with archetypal 3 (Priority: P1)

A modeller who used `archetypal reduce` in v2 installs archetypal 3 and does the same job: give
it one or more detailed EnergyPlus models and a weather file, and get a UMI template library.
Under the hood this is reduction (spec 002) followed by translation (spec 003), but the
modeller runs one command and gets one library plus the reports both steps produce.

**Why this priority**: This is v2's core workflow (C-10). If it is missing or harder in v3,
v3 is a regression and no other part of this spec matters.

**Independent Test**: On a fresh machine, install archetypal 3, run the documented command on
a reference model with a weather file, and open the library it writes in UMI's library code.
Repeat from a Python script with the documented programming interface; both routes give the
same library.

**Acceptance Scenarios**:

1. **Given** a fresh environment with a supported Python version, **When** the user installs
   archetypal 3, **Then** the `archetypal` command is available and lists its commands with a
   one-line description each.
2. **Given** a detailed model and a weather file, **When** the user runs the reduce command and
   asks for a UMI library, **Then** they get a UMI template library with one building template
   per model, plus the reduction report (spec 002) and the loss report (spec 003).
3. **Given** the same inputs, **When** the user asks for an SBEM archetype instead, **Then**
   they get the archetype and the reduction report, without the UMI step.
4. **Given** a v2-style invocation of `archetypal reduce` that uses only arguments v3 still
   accepts, **When** the user runs it, **Then** it produces a UMI library as in v2.
5. **Given** a v2 invocation that uses an option v3 removed, **When** the user runs it,
   **Then** the command stops before doing any work, names the option, and says what replaces
   it or why it is gone.

---

### User Story 2 - Move a v2 script to v3 (Priority: P1)

A developer has scripts written against archetypal v2: they open models with
`archetypal.IDF`, simulate them, read results, use `UmiTemplateLibrary`, or call the data
portal. They read the migration guide, find each name they use, and either rewrite the call
against archetypal 3, idfkit or epinterface, or learn that it has no replacement and why. If
they cannot migrate yet, they stay on v2.

**Why this priority**: Without this, upgrading breaks every v2 script with no explanation, and
users would pin v2 indefinitely, which defeats the rewrite (C-08).

**Independent Test**: Take every public name exported by archetypal 2.18 and every command and
option of its command line; check that each appears in the migration guide with a replacement
or an explicit "no replacement" and its reason. Rewrite the v2 tutorial's examples by following
only the guide and check that they run.

**Acceptance Scenarios**:

1. **Given** a v2 script that imports a name archetypal 3 removed, **When** it runs against
   archetypal 3, **Then** the error says the name was removed in archetypal 3 and points to the
   migration guide.
2. **Given** any public v2 name or command, **When** the developer looks it up in the
   migration guide, **Then** they find what replaces it (in archetypal 3, idfkit or
   epinterface), with a before/after example for each frequently used one, or a statement that
   there is no replacement and why.
3. **Given** a project that cannot move yet, **When** its maintainer pins archetypal below 3,
   **Then** v2 still installs and works, and the guide says how long v2 receives security
   fixes.

---

### User Story 3 - Learn and look things up in the documentation (Priority: P2)

A newcomer wants to learn what archetypal does and get a first result; an experienced user
wants the exact options of a command or the meaning of a report field; a researcher wants to
understand why a reduction conserves what it does. Each finds a page written for that need.

**Why this priority**: The constitution requires documentation in sync with the code and
organised by Diátaxis (VI). The site's structure is set here so that 002 and 003 add pages to
it rather than inventing their own.

**Independent Test**: Follow the tutorial from a fresh install to a written UMI library without
help. Pick public names and commands at random and find each in the reference. Check that every
page belongs to exactly one Diátaxis kind.

**Acceptance Scenarios**:

1. **Given** the documentation site, **When** a reader opens it, **Then** they see four
   sections: tutorials, how-to guides, reference and explanation.
2. **Given** any public name or command of archetypal 3, **When** the reader searches the
   reference, **Then** they find it, and its description matches the installed version.
3. **Given** a change that alters public behaviour, **When** it is merged, **Then** the
   documentation describing that behaviour changed in the same pull request, and every example
   in the documentation still runs.

---

### Edge Cases

- A user runs archetypal 3 on Python 3.9 or 3.13 or later: the installer refuses with a clear
  message about supported versions, rather than installing a package that fails at import
  (C-07).
- A user has both v2 code and archetypal 3 in mind and upgrades by accident: the first removed
  name they touch gives the migration-guide error, not an obscure import failure.
- A user passes a directory or a pattern of models to the reduce command, as v2 allowed: every
  matching model is reduced; a directory with no models is an error that names the directory.
- One model among several fails to reduce: the other models still produce their templates,
  the failure is reported with the model's name and reason, and the command exits with a
  status that signals partial failure. A library is never written with a failed model silently
  missing.
- The output file already exists: it is not overwritten unless the user asks.
- A user relied on v2 writing data, cache, log and image folders in the working directory: v3
  writes only the files the user asked for; the guide says so.
- A user's v2 workflow needs EnergyPlus model upgrades (v2 `transition`): it is not in v3; the
  guide points to idfkit's version migration.
- A user's v2 workflow used the TABULA data portal: v3.0 has no replacement (TABULA comes back
  as a reader in spec 004); the guide says so and suggests staying on v2 for that until then.
  v2 keeps receiving security fixes at least until v3.1 is released (FR-020).

## Requirements *(mandatory)*

### Functional Requirements

**Package and installation**

- **FR-001**: archetypal 3 MUST install from the public package index on Python 3.10, 3.11
  and 3.12, on Linux, macOS and Windows, and MUST refuse to install on other Python versions
  (C-07).
- **FR-002**: archetypal 3 MUST NOT contain its own implementation of what idfkit provides:
  reading, writing and editing EnergyPlus models; running simulations; upgrading model
  versions; reading simulation results; evaluating schedules; editing geometry. Where it needs
  these, it MUST use idfkit (constitution I, roadmap C-01).
- **FR-003**: archetypal 3 MUST depend on epinterface for the archetype data model (SBEM) and
  MUST NOT define a second archetype data model (constitution II, C-02).
- **FR-004**: archetypal 3 MUST NOT bundle third-party code or data that duplicates its
  dependencies (v2 bundled a copy of geomeppy), and any data it ships MUST record its source
  and licence (C-15).
- **FR-005**: Dependencies needed only for optional features MUST be optional extras, so the
  default install contains only what reduction and UMI translation need (constitution III).
- **FR-006**: Importing archetypal 3 or running a command MUST NOT create files or folders,
  change global logging, or read settings from the environment beyond what the user
  explicitly passes. Files are written only where the user asks.

**Public surface**

- **FR-007**: archetypal 3 MUST have a single, documented public programming interface: the
  names listed in the reference. Anything else is private and may change without notice.
- **FR-008**: The public interface MUST cover what specs 002 and 003 deliver: reducing a
  detailed model to an archetype at a chosen layout, merging an archetype to a coarser layout,
  comparing an archetype with its detailed model, reading a UMI library, writing a UMI
  library, and reading the reduction and loss reports.
- **FR-009**: Every public name MUST carry complete type information that a type checker can
  use (constitution VI).
- **FR-010**: Errors MUST be specific to the cause (invalid input, unsupported model feature,
  failed reduction, lossy translation in strict mode, missing dependency for an optional
  feature) so that a script can handle each one, and every message MUST name the input at
  fault.

**Command line**

- **FR-011**: archetypal 3 MUST provide an `archetypal` command whose sub-commands cover the
  same workflows as FR-008: reduce, merge to a coarser layout, compare, and translate between
  UMI and SBEM.
- **FR-012**: The `reduce` command MUST keep its v2 name and the v2 form "models in, weather
  file, output path", and MUST accept several models, directories or patterns, each model
  becoming one archetype (one building template in a UMI library). It MUST let the user choose
  the output: an SBEM archetype, or a UMI template library (the v2 result). An SBEM archetype
  is written in epinterface's own serialisation of its model, one file per archetype, so
  epinterface and tools built on it read it without archetypal; its reports are separate files
  beside it. The merge, compare and translate commands read archetypes in that same form.
- **FR-013**: Every v2 option or command that v3 does not keep MUST be rejected with a message
  naming it and its replacement or the reason it is gone (scenario 1.5), rather than being
  silently ignored. This applies to at least: `transition`, `--ep_version`, the reduce
  command's `-v`/`--version` (EnergyPlus upgrade), `--all_zones`, `--cache-responses` and the data, logs, images and
  cache folder options. v3 MUST keep this behaviour for every 3.x release.
- **FR-014**: Every command MUST write the reports defined by specs 002 and 003 next to its
  output, each as one structured, machine-readable file that a script can load without
  archetypal, and MUST print a short human-readable summary of them (counts of losses and
  approximations, failed models, where the report files are). It MUST exit with distinct statuses for success, success with losses reported,
  partial failure (some models failed) and failure.
- **FR-015**: Commands MUST NOT overwrite an existing output unless the user asks.

**Migration from v2**

- **FR-016**: Importing a public v2 name that archetypal 3 removed (at least `IDF`,
  `UmiTemplateLibrary`, `BuildingTemplate`, `EnergyPlusVersion`, `Settings`, `settings`,
  `config`, `clear_cache`, `parallel_process`, `dataportal`, `utils`) MUST raise an error that
  says it was removed in archetypal 3 and gives the address of the migration guide. These
  names MUST NOT be kept as working aliases: nothing from v2 is carried as is (C-04).
- **FR-017**: The migration guide MUST list every public name, module, command and option of
  archetypal 2.18 and give, for each, its replacement in archetypal 3, idfkit or epinterface, or
  state that it has none and why.
- **FR-018**: For each frequent v2 task (reduce models to a UMI library, open and edit a UMI
  library, open and simulate a model, read results, upgrade a model's version, evaluate a
  schedule), the guide MUST give a before/after example, and every "after" example MUST run as
  part of the test suite.
- **FR-019**: The guide MUST state which v2 behaviours change in results, not only in names:
  at least, that reduction results differ from v2's because the method was rewritten (spec
  002), and where to find the evidence that v3 is more correct (spec 002, success criteria).
- **FR-020**: v2 MUST remain installable by pinning `archetypal<3`, MUST be maintained on a
  `v2.x` branch that receives security fixes only, for 12 months after v3.0 or until v3.1
  (which restores TABULA, spec 004) is released, whichever is later. The guide MUST state that
  policy and its end date (C-08).
- **FR-021**: Before v3.0 is released, a final v2 release MUST announce v3 and link to the
  migration guide in its documentation and its release notes, so that v2 users learn of the
  change before upgrading.

**Documentation**

- **FR-022**: The documentation site MUST have four sections, tutorials, how-to guides,
  reference and explanation, and every page MUST belong to exactly one of them (constitution
  VI, C-09).
- **FR-023**: At v3.0 the site MUST contain at least: a tutorial from install to a first UMI
  library; the migration guide (how-to); a reference of every public name and every command
  and option, generated from the code so it cannot drift; and an explanation of what
  archetypal is for and where it sits in the stack (archetypal, epinterface, idfkit). Specs 002
  and 003 add their own pages to the same structure.
- **FR-024**: Every example in the documentation MUST run as part of the test suite, and a
  change to public behaviour MUST update the documentation in the same pull request
  (constitution VI).
- **FR-025**: v2's documentation MUST stay available for the v2.x line, separately from v3's,
  and v3's site MUST link to it.
- **FR-026**: The project's changelog MUST record v3.0 as a major release with a summary of
  removals and a link to the migration guide (Keep a Changelog, constitution VI).

### Key Entities

- **Public interface**: the set of names and commands archetypal 3 documents and promises to
  keep stable within 3.x; everything else is private.
- **Removed capability**: a v2 name, module, command or option that archetypal 3 does not
  provide, with its replacement (or "none") and the reason.
- **Migration guide**: the how-to guide that maps every removed capability to its replacement,
  with runnable before/after examples for frequent tasks.
- **Maintenance line (v2.x)**: the branch and releases of archetypal 2 that receive only
  security fixes after v3.0.
- **Archetype file**: one SBEM archetype stored in epinterface's own serialisation; archetypal
  adds no format of its own around it. Its reduction report is a separate file beside it.
- **Report file**: one reduction or loss report, stored as a structured, machine-readable
  file beside the output it describes; the command line prints only a summary of it.
- **Documentation site**: the user-facing pages, organised into Diátaxis's four kinds and kept
  in sync with the code.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: On a fresh environment with each supported Python version and operating system,
  installing archetypal 3 and running the tutorial to a UMI library succeeds in 100 % of runs
  in automated checks.
- **SC-002**: A default install of archetypal 3 contains no package that duplicates idfkit
  (eppy, geomeppy or its dependencies, esoreader, energy_pandas or an equivalent) and installs
  fewer packages than archetypal 2.18 on the same Python version.
- **SC-003**: 100 % of archetypal 2.18's public names, modules, commands and options appear in
  the migration guide with a replacement or a stated reason; checked automatically against the
  v2 package.
- **SC-004**: 100 % of the documentation's code examples and before/after "after" examples
  run without error on every change.
- **SC-005**: 100 % of public names carry complete type information, checked by a type
  checker in strict mode on every change.
- **SC-006**: Importing archetypal 3 and running any command leaves no file or folder behind
  other than the outputs the user asked for, checked automatically.
- **SC-007**: Every removed v2 option or name tried in an automated check produces the
  migration-guide error, never a generic failure.
- **SC-008**: Every documentation page is tagged with exactly one Diátaxis kind, checked
  automatically.

## Assumptions

- epinterface is published on the public package index and uses idfkit rather than
  archetypal or eppy before v3.0 is released (UP-1, UP-3). Without UP-3 no v3 release can
  ship, because a published package cannot depend on a git repository.
- The supported Python versions are bounded by epinterface (3.10 to 3.12) and widen when it
  does (C-07).
- "Duplicates idfkit" is judged against idfkit's capabilities at the time of v3.0; if idfkit
  lacks something archetypal needs, it is added to idfkit upstream rather than kept in
  archetypal (constitution I).
- v2 capabilities with no home in the v3 stack and no planned spec (for example v2's plotting
  helpers, the zone adjacency graph, the OpenEI, NREL and Statistics Canada portal requests)
  are removed without replacement; the guide states this. TABULA returns as a reader in spec
  004 (v3.1).
- The reduce command keeps the name `reduce` because it is how v2 users know the workflow;
  its default output is a UMI template library, as in v2 (scenario 1.4), and SBEM is chosen
  explicitly.
- Running several models in parallel is a convenience of the reduce command, not batch
  simulation orchestration, which stays out of scope (C-06).
- The documentation site's build tooling and hosting are planning decisions; this spec fixes
  only its structure and the guarantees it gives readers.
