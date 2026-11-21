# Feature Specification: Translate UMI template libraries to and from SBEM

**Feature Branch**: `claude/admiring-meitner-1f43qk` (spec 003 in the roadmap)

**Created**: 2026-11-21

**Status**: Draft

**Input**: Roadmap entry 003 (roadmap 1.2.1): "Read a UMI template library (JSON) into SBEM
archetypes, and write SBEM archetypes out as a UMI template library, so existing UMI libraries
keep their value." Governed by constitution 1.3.0 (Principles II, IV) and roadmap decisions
C-02, C-10, C-11, C-13.

## Why this exists

UMI template libraries are how many urban modelling teams store their archetypes today. They
were built over years, often by hand, and UMI expects them in its own format. archetypal v3
moves to SBEM as its single archetype data model (roadmap C-02), so without a translator:

- existing UMI libraries would be stranded outside v3, and
- v3 could not deliver v2's core workflow, "reduce a detailed model and get a UMI template
  library" (roadmap C-10).

A translator is only trustworthy if it is honest about what it loses. UMI and SBEM will not
describe a building identically. UMI holds exactly two zones per building (core and perimeter).
SBEM today holds a single zone definition per model; v3 archetypes will hold several zone groups
once our upstream change to epinterface lands (roadmap C-03, C-11, UP-2). Some fields are also
expected to exist on only one side; the field correspondence this spec requires (FR-009) is what
establishes which. Constitution II requires every translation to state what it loses; this spec defines
what "survives the trip" means and how the user is told when something does not.

## Clarifications

### Session 2026-11-21

- Q: When reading a UMI library, where do the core and perimeter floor-area shares come from,
  given that a UMI template does not store them? → A: Nowhere fixed: the archetype is read with
  a "core/perimeter by geometry" layout whose shares are set by the building's geometry when it
  is applied, as UMI does. On writing, fixed shares are dropped and reported as lost.
- Q: When an archetype with several zone groups is written to UMI without its reduction report
  (edited, or built another way), how is it merged to core/perimeter? → A: From its current
  groups; where report data is missing (for example delivered and consumed energy for
  efficiencies), floor-area weighting is used instead and each such parameter is listed in the
  loss report as approximate.
- Q: How is an archetype with only a perimeter group written to UMI, which needs both a core and
  a perimeter zone definition? → A: The perimeter definition is used for the core zone too, and
  the loss report states that the core definition was copied, not derived from core zones.
- Q: When reading or writing loses information, does translation still succeed? → A: Yes by
  default, with the loss report; a strict mode makes any loss an error and writes no output.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Write an archetype as a UMI template library (Priority: P1)

A modeller has reduced a detailed model to an SBEM archetype (spec 002) and needs it in UMI. They
write one or more archetypes to a UMI template library file that UMI opens without errors.
Archetypes with more than two zone groups are first merged to core and perimeter, using the
same rules as spec 002, and the modeller is told which distinctions that merge removed.

**Why this priority**: it completes v2's core workflow in v3 (roadmap C-10). Without it v3.0
cannot ship.

**Independent Test**: reduce each reference building (spec 002) to its default layout, write
it to UMI, and open the file in UMI; check that each building template's values equal those of
the same archetype merged to core/perimeter, and that the loss report lists the merged groups.

**Acceptance Scenarios**:

1. **Given** an SBEM archetype with core and perimeter groups only, **When** the modeller
   writes it to UMI, **Then** they get a UMI template library containing one building template
   whose values equal the archetype's, and a loss report that lists the archetype's floor-area
   shares (FR-006a) and each SBEM field that UMI cannot hold.
2. **Given** an archetype with several zone groups, **When** it is written to UMI, **Then** the
   building template equals the archetype merged to core/perimeter (spec 002, FR-010), and the
   loss report lists the groups that were merged and the archetype's floor-area shares, which
   UMI does not store.
3. **Given** several archetypes that share components (the same construction, the same
   schedule), **When** they are written to one library, **Then** each shared component appears
   once in the library and every building template refers to it.

---

### User Story 2 - Bring an existing UMI library into SBEM (Priority: P1)

A team has a UMI template library built over years. They read it into SBEM archetypes, one per
building template, so they can use v3's capabilities on it (generate EnergyPlus models with
epinterface, check it, assign it to buildings). They receive a report of anything in the
library that could not be represented.

**Why this priority**: it keeps existing libraries usable; without it, adopting v3 means
abandoning them.

**Independent Test**: read each library in the UMI test set into SBEM and check that every
building template produced an archetype, that each archetype is valid SBEM, and that every
field of the library is either represented or listed in the report.

**Acceptance Scenarios**:

1. **Given** a valid UMI template library, **When** it is read, **Then** each building template
   becomes one SBEM archetype with a core and a perimeter zone group in the "core/perimeter by
   geometry" layout (no fixed floor-area shares), carrying the library's
   descriptive information (name, authors, country, climate zone, construction years, data
   source, comments, lifespan).
2. **Given** a library in which two materials share a name but differ in thickness or other
   properties (issue #459), **When** it is read, **Then** both are kept as distinct components
   and the report notes the name collision.
3. **Given** a library that is invalid (a building template refers to a component that does not
   exist, or a required field is missing), **When** it is read, **Then** reading stops, names
   each problem and where it is, and produces no archetypes.

---

### User Story 3 - Round trip without silent change (Priority: P2)

A library maintainer reads a UMI library into SBEM and writes it back, for example after
checking or editing it in v3. They need confidence that the trip itself changed nothing they
did not intend.

**Why this priority**: it is how users verify the translator and how the project proves it
meets constitution II; the stories above deliver value on their own.

**Independent Test**: for each library in the UMI test set, read then write it; compare the
original and result field by field.

**Acceptance Scenarios**:

1. **Given** a UMI library, **When** it is read into SBEM and written back to UMI, **Then**
   every value that affects simulation results is equal to the original within numerical
   tolerance, and every difference of any kind is listed in the round-trip report.
2. **Given** an SBEM archetype with core and perimeter groups only, **When** it is written to
   UMI and read back, **Then** the resulting archetype equals the original, except for the
   SBEM fields listed as lost in the first write.

---

### Edge Cases

- **A multi-group archetype without its reduction report** (edited, or not produced by spec
  002): it is still written; the merge to core/perimeter uses its current groups and
  floor-area weighting where report data is missing, and the loss report marks those
  parameters as approximate (FR-006).

- **Library with no building templates** (components only): reading produces no archetypes and
  says so; the components are not lost silently but listed as unused.
- **Unused components** (defined but referenced by no building template): reported as unused;
  not carried into SBEM.
- **Schedules**: UMI expresses schedules as year, week and day schedules; SBEM archetypes from
  spec 002 use `Schedule:Compact`. Both directions must reproduce the same hourly values for
  every day type.
- **A value outside SBEM's allowed range** (for example a negative conductivity in a
  hand-edited library): reading stops for that building template, names the value, and
  continues with the others only if the user asked to skip invalid templates.
- **An archetype with a perimeter group only** (no core, for example a narrow bar building):
  written to UMI with the perimeter definition used for the core zone too, because the template
  may later be applied to buildings that do have a core; the loss report states that the core
  definition was copied, not derived (FR-006b).
- **Duplicate building template names** in one library: reading keeps both and reports the
  duplication; writing never produces duplicate names.
- **UMI library versions**: libraries written by older UMI releases are read where their format
  can be identified; unsupported versions are refused with a message naming the version.

## Requirements *(mandatory)*

### Functional Requirements

**Reading UMI**

- **FR-001**: Users MUST be able to read a UMI template library file into SBEM archetypes, one
  archetype per building template.
- **FR-002**: Each archetype read from UMI MUST have two zone groups, core and perimeter, in the
  "core/perimeter by geometry" layout: their floor-area shares are not fixed by the archetype
  but set by the building's geometry when it is applied, as in UMI. It MUST carry the template's
  structure, window settings, partition ratio, default window-to-wall ratio and descriptive
  fields.
- **FR-003**: Reading MUST keep components that share a name but differ in any property as
  distinct components, and report the collision.
- **FR-004**: Reading MUST validate the library (references resolve, required fields present,
  values in range) before producing any archetype, and report every problem with its location.

**Writing UMI**

- **FR-005**: Users MUST be able to write one or more SBEM archetypes to a single UMI template
  library file that UMI opens without errors.
- **FR-006**: An archetype with more than two zone groups MUST be merged to core/perimeter
  using spec 002's rules (FR-010 of spec 002) before writing, and the merge MUST be reported as
  a loss. When the archetype's reduction report is not available, the merge MUST start from the
  archetype's current groups and use floor-area weighting for any parameter whose spec 002 rule
  needs report data (for example efficiencies, which need delivered and consumed energy); each
  such parameter MUST be listed in the loss report as approximate.
- **FR-006a**: Writing MUST drop an archetype's fixed floor-area shares, because UMI derives
  them from each building's geometry, and MUST report them as lost.
- **FR-006b**: An archetype with only a perimeter group MUST be written with its perimeter
  definition used for the core zone as well, and the loss report MUST state that the core
  definition was copied from the perimeter rather than derived from core zones.
- **FR-007**: Components shared by several archetypes MUST appear once in the written library;
  component names in the written library MUST be unique.
- **FR-008**: Schedules MUST be written in UMI's year, week and day form, reproducing the same
  hourly values for every day type as the archetype's schedules.

**Mapping and loss** (roadmap C-13)

- **FR-009**: The translator MUST define a field-by-field correspondence between UMI and SBEM,
  covering every UMI field. It MUST be published as reference documentation.
- **FR-010**: Every UMI field that affects simulation results MUST map to an SBEM field.
  Descriptive fields MUST map to SBEM's metadata and environmental fields. Where a UMI field
  that affects simulation has no SBEM counterpart, the gap MUST be raised upstream (UP-2) and,
  until it is closed, reported as lost on every read.
- **FR-011**: Every read and write MUST produce a loss report listing each value that could not
  be represented in the target, the building template or archetype it belongs to, and why.
  An empty report MUST say explicitly that nothing was lost.
- **FR-011a**: By default, a read or write that loses information MUST still succeed and
  report the loss. Users MUST be able to request a strict mode in which any loss is an error:
  no output is produced and the loss report states what would have been lost.
- **FR-012**: Translation MUST be deterministic: the same input always produces the same
  output file and report.

**Documentation** (constitution VI)

- **FR-013**: The user-facing documentation MUST include a how-to guide for reading a UMI
  library and for writing archetypes to UMI, reference for the field correspondence (FR-009),
  and an explanation of what is lost in each direction and why.

### Key Entities

- **UMI template library**: a file holding building templates and the components they share
  (materials, constructions, schedules, settings for loads, conditioning, ventilation, hot
  water, windows, structure).
- **Building template**: UMI's description of one archetype: a core zone, a perimeter zone,
  structure, window settings and descriptive information.
- **SBEM archetype**: as defined in spec 002: zone groups and building-level characteristics.
  An archetype read from UMI uses the "core/perimeter by geometry" layout, in which the core
  and perimeter shares are set by the building's geometry rather than stored.
- **Field correspondence**: the published mapping between every UMI field and its SBEM
  counterpart, or the reason it has none.
- **Loss report**: the record of a read or write: everything not represented, merges performed,
  name collisions, unused components.
- **UMI test set**: the UMI libraries used to verify the translator: the libraries in the
  project's test data, plus libraries produced by writing the spec 002 reference set.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 % of libraries in the UMI test set are read without error, and every one of
  their building templates becomes a valid SBEM archetype.
- **SC-002**: 100 % of libraries written by the translator open in UMI without errors or
  warnings about the file.
- **SC-003**: For every library in the UMI test set, a read-then-write round trip reproduces
  every simulation-relevant value within 0.01 % relative difference, and every other
  difference is listed in the round-trip report.
- **SC-004**: For every spec 002 reference building, writing the core/perimeter archetype to UMI
  and reading it back reproduces the archetype exactly, apart from fields reported as lost.
- **SC-005**: Every UMI field appears in the published field correspondence (100 % coverage).
- **SC-006**: No loss goes unreported: in an audit comparing inputs and outputs field by field
  for the whole test set, every difference found appears in the corresponding report.
- **SC-006a**: In strict mode, every read or write in the test set whose loss report is not
  empty fails and produces no output, and every one whose report is empty succeeds.
- **SC-007**: Reading or writing a library of 100 building templates takes under 5 seconds on a
  typical laptop.

## Assumptions

- UMI's current template library format is the target for writing; older formats are read where
  identifiable (edge cases).
- UMI requires both a core and a perimeter zone definition in each building template, and
  applies the core definition only to buildings whose geometry has a core (FR-006b).
- epinterface supports zone groups and the fields required by C-13 (upstream UP-2) before this
  spec is implemented.
- UMI templates are not offered as editable Python objects (roadmap C-02); editing happens on
  the SBEM archetype.
- "Typical laptop" has the same meaning as in spec 002.
- Out of scope: other formats (roadmap 008), generating EnergyPlus models (epinterface), and the
  reduction itself (spec 002).
