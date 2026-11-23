# Feature Specification: Archetypes from TABULA/EPISCOPE

**Feature Branch**: `claude/admiring-meitner-1f43qk` (spec 004 in the roadmap)

**Created**: 2026-11-23

**Status**: Draft

**Input**: Roadmap entry 004 (roadmap 1.11.1, milestone M2): "Create SBEM archetypes from the
TABULA/EPISCOPE residential typologies." Outcome: "a user selects a country, building type and
age band and gets an SBEM archetype whose values trace back to the TABULA source." Governed by
constitution 1.5.0 (Principles I, II, IV) and roadmap decisions C-02, C-04, C-15.

## Why this exists

TABULA/EPISCOPE (two IEE projects led by Institut Wohnen und Umwelt, IWU) published residential
building typologies for 20 European countries: for each country, building size class and
construction period, an example building with its envelope areas, U-values, air change rates
and heating and hot-water systems, in its existing state and after two levels of refurbishment.
They are the most widely used common basis for residential stock models in Europe.

archetypal 2 reached TABULA by scraping its web tool, which broke whenever the site changed and
returned whatever the page showed, with no record of where a value came from. The stable source
is the workbook IWU publishes, which holds every building and every building-system combination
the web tool shows. This spec turns a TABULA building into an SBEM archetype (roadmap C-02) in
which every value says where it came from, and states what a one-zone seasonal model can and
cannot tell an hourly simulation.

Two facts shape it:

- **TABULA is a seasonal, one-zone energy balance** (TABULA common calculation method, after
  EN ISO 13790), with standard boundary conditions (20 °C, 3 W/m² internal gains, a use air
  change of 0.4 1/h). It has no schedules, no occupants and no hourly weather. An SBEM archetype
  needs all three. What TABULA gives must be carried over exactly; what it does not give must be
  supplied, and said to be supplied.
- **The data's terms of use require attribution and do not address redistribution.** IWU's
  rules allow use in software "by third parties", on condition that "IEE Projects TABULA +
  EPISCOPE (www.episcope.eu) is visibly mentioned as the source". Under roadmap C-15,
  archetypal therefore ships a reader, not the data.

## Clarifications

### Session 2026-11-23

Both answers rest on a 54-building experiment (7 countries, single- and multi-family houses,
old and recent construction periods, variants 1 and 3): one-zone EnergyPlus models built
directly from TABULA's values, compared with TABULA's own seasonal method on the same weather
file and with TABULA's published figures (`experiments/sc004/`).

- Q: How is an hourly simulation of a TABULA archetype judged against TABULA's heating need
  (SC-004)? → A: Within ±25 % of TABULA's method recomputed on the simulation's own weather
  file (53 of 54 buildings passed; 44 of 54 at ±15 %). The difference from TABULA's
  published figure is reported, split into a climate part and a method part, but does not
  pass or fail: TABULA's national climates are 1 to 4.5 K colder than 2011–2025 weather files,
  so against the published figure only 38 of 54 passed at ±25 %, a test of the weather file
  rather than of archetypal.
- Q: TABULA multiplies heat losses by a temperature-reduction factor (0.8 to 0.95) for partial
  and intermittent heating. How does the archetype carry it? → A: The archetype heats to
  TABULA's internal temperature (20 °C); the factor is recorded in the provenance, like the
  national adaptation factors, for users to apply to results. Keeping 20 °C agreed best with
  TABULA's method on the same weather (median −6 %); an equivalent constant lower set-point
  under-predicted poorly insulated houses by 12 to 26 %.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Get an archetype for a country, building type and age band (Priority: P1)

A stock modeller studying German single-family houses built between 1958 and 1968 asks for
that TABULA building in its existing state. They receive one SBEM archetype, ready to simulate
or to translate to UMI, and a provenance record that names, for every archetype value, the
TABULA field it came from or the assumption that supplied it.

**Why this priority**: this is the roadmap's outcome. Everything else refines it.

**Independent Test**: with the workbook available, request one building (country, size class,
construction period, variant) and check that the archetype validates as SBEM, that its
envelope, ventilation and system values equal the workbook's, and that every value appears in
the provenance record.

**Acceptance Scenarios**:

1. **Given** the TABULA workbook, **When** the user asks for Germany, single-family house,
   1958–1968, existing state, **Then** they get one SBEM archetype whose transmission and
   ventilation heat transfer coefficients equal those TABULA computes for that building (SC-002).
2. **Given** the same request, **When** the user reads the provenance record, **Then** each
   archetype value names its TABULA field (sheet, column and building code) or the documented
   assumption that supplied it, and the record names the source, its version and the
   attribution TABULA requires (FR-012).
3. **Given** a request for refurbishment variant 2 or 3 of the same building, **When** the
   archetype is created, **Then** only the values TABULA changes between variants differ.

---

### User Story 2 - Browse what TABULA offers before choosing (Priority: P2)

A modeller does not know a country's construction-period bands or which size classes it covers.
They list what is available for a country (size classes, construction periods, variants, and
the heating and hot-water systems TABULA pairs with each building) and pick from that list.

**Why this priority**: bands differ by country (from 4 in Cyprus and Greece to 12 in Germany),
so a user cannot guess them. Without listing, User Story 1 fails on its first try.

**Independent Test**: list one country and check that every listed combination can be created
(User Story 1) and that no combination the workbook holds is missing from the list.

**Acceptance Scenarios**:

1. **Given** the workbook, **When** the user lists Germany, **Then** they see its size
   classes, its construction periods with their year ranges, the variants each building has,
   and the system combinations available for each.
2. **Given** a combination the workbook does not hold (for example a size class a country does
   not define), **When** the user asks for it, **Then** they are told it does not exist and are
   shown the nearest available choices.

---

### User Story 3 - Create a whole country's typology at once (Priority: P3)

A modeller wants every TABULA building of a country, or of several countries, as archetypes:
the starting set for a stock model.

**Why this priority**: valuable, but a loop over User Story 1; it adds only reporting across
many buildings.

**Independent Test**: create every building of one country and check that the count matches the
listing (User Story 2) and that each archetype passes User Story 1's checks.

**Acceptance Scenarios**:

1. **Given** the workbook, **When** the user creates all buildings of a country, **Then** they
   get one archetype per building and variant, each with its provenance, and one summary of
   every assumption made across the set.
2. **Given** a building whose data are incomplete, **When** the set is created, **Then** that
   building is reported with what is missing (FR-009) and the others are still created.

---

### User Story 4 - Know how far an hourly simulation is from TABULA's figure (Priority: P3)

A modeller wants to know whether simulating the archetype reproduces the heating need TABULA
publishes for that building, and why it may not.

**Why this priority**: the archetype is meant for hourly simulation, while TABULA's figures
come from a seasonal method. Users compare the two; the comparison must be stated, not left
to them.

**Independent Test**: for a set of reference buildings, simulate each archetype under TABULA's
boundary conditions and compare its annual heating need with TABULA's (SC-004).

**Acceptance Scenarios**:

1. **Given** an archetype and a weather file for its country, **When** it is simulated with
   TABULA's boundary conditions, **Then** the user can read its annual heating need next to
   TABULA's published value and the difference, with the method differences that explain it
   listed.

### Edge Cases

- **The workbook is absent.** Nothing is created; the user is told where the workbook is
  published, how to fetch it, and that archetypal does not ship it (FR-002).
- **The workbook differs from the one archetypal was verified against** (another release, a
  local edit). It is refused unless the user explicitly accepts an unverified workbook, in which
  case every provenance record says so (FR-003).
- **A field is blank, zero where it cannot be, or a placeholder** in the workbook. The value is
  never invented silently: FR-009 decides between refusing the building and an assumption.
- **A building has no window area by orientation**, only a total. The total is kept; its split
  is an assumption, recorded as such.
- **A building's floor or roof borders an unheated space** (cellar, attic). TABULA represents it
  with an adjustment factor on the element's U-value. The transmission it allows is conserved,
  and the buffer space it stands for is reported as not represented (FR-007).
- **A building-system combination uses a carrier or generator SBEM cannot represent.** The
  closest representable choice is made and the difference reported, or the system is refused
  under FR-009.
- **A country in TABULA's web tool but not in the workbook** (Bosnia and Herzegovina, added
  2017). It is not offered; listing says so.
- **Rows that are not part of a national typology** (the workbook also holds example and
  demonstration buildings). They are not offered as typology buildings.

## Requirements *(mandatory)*

### Functional Requirements

**Source**

- **FR-001**: The source MUST be IWU's published TABULA workbooks (`tabula-calculator.xlsx`
  for buildings and building-system combinations, `tabula-values.xlsx` for code lists and
  constant tables), read as published. The TABULA web tool MUST NOT be queried (roadmap 004,
  scope out).
- **FR-002**: archetypal MUST NOT ship the workbooks or data derived from them, because their
  terms of use require attribution and do not grant redistribution (roadmap C-15). Users MUST be
  able to fetch the workbooks from their published location with one command, or point
  archetypal at copies they already have.
- **FR-003**: Every workbook read MUST be identified (published file, release date, checksum).
  A workbook that is not one archetypal has been verified against MUST be refused unless the
  user accepts it explicitly, and then every archetype made from it MUST record that it is
  unverified.

**Selection**

- **FR-004**: Users MUST be able to list, for any country in the workbook, its size classes,
  construction periods (with year ranges), refurbishment variants and the building-system
  combinations TABULA pairs with each building.
- **FR-005**: Users MUST be able to create an archetype by country, size class, construction
  period and variant (default: existing state), and optionally a building-system combination
  (default: the one TABULA gives first for that building); and to create every building of one
  or more countries in one request.

**Mapping** *(constitution IV: what is conserved, and how each output relates to its inputs)*

- **FR-006**: The archetype MUST be one zone group covering the building's reference floor
  area, because TABULA describes a building as one zone. Its geometry (floor area, storeys,
  ceiling height, envelope element areas, window areas by orientation) MUST come from the
  workbook, in TABULA's reference (external) dimensions.
- **FR-007**: The archetype MUST conserve the building's transmission heat transfer
  coefficient as TABULA computes it: per envelope element, area × U-value × adjustment factor,
  plus the thermal-bridging surcharge on the envelope area. An adjustment factor below 1 (an
  element bordering an unheated space) MUST be folded into the element's construction so the
  coefficient is kept, and the unheated space it stands for MUST be reported as not represented.
- **FR-008**: The archetype MUST conserve, from the workbook:
  - the ventilation heat transfer coefficient (infiltration and use air change rates, on
    TABULA's ventilation reference volume) and any ventilation heat recovery;
  - window areas, U-values and solar energy transmittance by orientation;
  - the internal heat gains per floor area;
  - the heating set-point temperature;
  - the hot-water energy need per floor area;
  - for the chosen building-system combination, the delivered energy per energy carrier for
    heating and hot water, through system efficiencies derived from TABULA's expenditure
    factors and its storage and distribution losses.
- **FR-009**: When the workbook lacks a value the archetype needs, archetypal MUST either refuse
  the building, naming the missing value, or use a documented assumption, never a silent
  default. Values SBEM needs that TABULA never has (occupancy and its schedules, lighting and
  equipment split of the internal gains, cooling, schedules of the set-points) MUST be supplied
  as documented assumptions that keep TABULA's annual totals (FR-008), and MUST be marked as
  assumptions in the provenance record.
- **FR-010**: Two TABULA factors describe how the building is used, not the building, and MUST
  NOT change the archetype: the temperature-reduction factor for partial and intermittent
  heating (the archetype heats to TABULA's internal temperature, FR-008), and the national
  adaptation factors that scale calculated demand to typical measured consumption. Both MUST be
  recorded in the provenance record so users can apply them to results.
- **FR-011**: Every SBEM field set from TABULA, and every TABULA field read, MUST appear in a
  published correspondence that states the rule linking them (copy, unit conversion, derived,
  assumption), in the manner of spec 003's UMI field correspondence.

**Provenance**

- **FR-012**: Every archetype MUST carry a provenance record that:
  - names the source as TABULA requires ("IEE Projects TABULA + EPISCOPE (www.episcope.eu)"),
    the workbook file, release date and checksum, and its terms of use;
  - gives the TABULA building code and variant, and system code where used;
  - names, for every archetype value, its TABULA field(s) and rule, or the assumption that
    supplied it.
- **FR-013**: The provenance record MUST travel with the archetype: written alongside it and
  kept when the archetype is translated (for example to UMI, spec 003), where the target format
  allows.

**Behaviour**

- **FR-014**: Creation MUST be deterministic: the same workbook and request always give the same
  archetype and provenance, byte for byte.
- **FR-015**: Creating a set (User Story 3) MUST NOT stop at the first building that cannot be
  created: it MUST create the others and report each failure with its reason.
- **FR-016**: The user-facing documentation MUST include a how-to guide for creating TABULA
  archetypes (fetching the workbook, listing, creating), a reference of the field
  correspondence (FR-011), and an explanation page of what a TABULA archetype represents and
  what it cannot (one zone, seasonal method, assumptions), with the attribution TABULA requires.

### Key Entities *(include if feature involves data)*

- **TABULA workbook**: IWU's published files; identified by name, release date and checksum.
  Holds the buildings, the building-system combinations, code lists and constant tables.
- **TABULA building**: one row of a national typology, identified by its building code
  (country, region, size class, construction period, dataset) and variant (1 existing state,
  2 usual refurbishment, 3 advanced refurbishment).
- **Building-system combination**: a TABULA building paired with a heating and hot-water system
  code, with its generator expenditure factors, storage and distribution losses and energy
  carriers.
- **TABULA archetype**: the SBEM archetype created from one building, variant and system
  combination.
- **Provenance record**: per archetype, the source identification, codes, and the origin of
  every value (TABULA field and rule, or assumption).
- **Field correspondence**: the published table linking TABULA fields to SBEM fields, with the
  rule for each.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 100 % of the typology buildings in the verified workbook (every country, size
  class, construction period and variant) either become a valid SBEM archetype or are refused
  with the missing values named; none fails without a reason.
- **SC-002**: For every archetype created, its transmission and ventilation heat transfer
  coefficients, window solar aperture by orientation, internal gains, set-point and hot-water
  need equal TABULA's within 0.1 % (relative).
- **SC-003**: Recomputing TABULA's seasonal heating need from the archetype's own values with
  TABULA's method reproduces the value TABULA publishes for that building within 1 % for
  every archetype created, showing that nothing that drives the balance was lost.
- **SC-004**: For a fixed reference set of TABULA buildings, chosen before results are known
  and covering several countries, size classes and variants, the archetype simulated with
  TABULA's boundary conditions has an annual heating need within ±25 % of TABULA's seasonal
  method recomputed on the same weather file, for every building in the set. For each
  building, the difference from TABULA's published figure is also reported, split into its
  climate part (TABULA's method on the weather file against the published figure) and its
  method part (the simulation against TABULA's method on the weather file); it does not pass
  or fail.
- **SC-005**: 100 % of archetype values appear in the provenance record with a TABULA source or a
  named assumption; 100 % of TABULA fields read and SBEM fields set appear in the field
  correspondence.
- **SC-006**: Creating a single archetype takes under 2 seconds, and a whole country's typology
  under 1 minute, on a typical laptop once the workbook is available locally.
- **SC-007**: A user new to TABULA can list a country and create the archetype they want in
  under 5 minutes by following the how-to guide.

## Assumptions

- The verified source is `tabula-calculator.xlsx` (published 2016-07-15, information sheet dated
  2016-07-20) and `tabula-values.xlsx` (2016-09-06), downloaded from
  https://episcope.eu/communication/download/. The data have not changed since 2015-10-02; a
  later release would be verified like a new source (FR-003). The 222 MB master workbook
  (`TABULA.xlsm`) is not needed: the calculator holds every building-system combination the web
  tool shows.
- The workbook covers 20 countries (AT, BE, BG, CY, CZ, DE, DK, ES, FR, GB, GR, HU, IE, IT, NL,
  NO, PL, RS, SE, SI), four size classes (single-family house, terraced house, multi-family
  house, apartment block) and three variants.
- TABULA's terms of use ("Rules for Usage of the TABULA 'Building Typology' Approach") allow use
  in software by third parties with visible attribution, and ask users to report their use.
  Attribution is met by FR-012 and the documentation (FR-016); reporting archetypal's use to IWU
  is a project task, outside this spec.
- SBEM, through the fork (roadmap C-17), holds what FR-006 to FR-008 need: per-orientation
  window ratios, numeric heat-recovery effectiveness and unset floor-area shares come with UP-2.
  Any other gap the plan finds is closed upstream (constitution I), not in archetypal.
- Weather is not part of an archetype. The simulations of SC-004 use a representative weather
  file per country, chosen by the plan; TABULA's own seasonal climate data are recorded in the
  provenance, not converted to hourly weather. Recomputing TABULA's method on a weather file
  takes the heating days as the days whose mean outdoor temperature is below TABULA's base
  temperature (12 °C), as TABULA does.
- Translating a TABULA archetype to UMI is spec 003's job and needs nothing from this spec
  beyond the provenance record (FR-013).

## Out of scope

- Scraping or querying the TABULA web tool (roadmap 004).
- Shipping TABULA data or derived archetypes with archetypal (roadmap C-15, FR-002).
- Non-residential buildings: TABULA covers residential buildings only.
- Calibrating archetypes to measured consumption (roadmap C-05); FR-010 records TABULA's
  adaptation factors without applying them.
- Other typologies or national datasets (ASHRAE 90.1 vintages are spec 005).
