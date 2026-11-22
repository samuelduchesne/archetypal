# Feature Specification: Reduce a detailed EnergyPlus model to an SBEM archetype

**Feature Branch**: `claude/admiring-meitner-1f43qk` (spec 002 in the roadmap)

**Created**: 2026-11-21

**Status**: Draft

**Input**: Roadmap entry 002 (roadmap 1.2.0): "Turn a detailed, multizone EnergyPlus model (and
the results of simulating it) into one SBEM archetype made of zone groups (by space use and
exposure), describing what is conserved and why." Governed by constitution 1.3.0 (Principles
II, IV, V) and roadmap decisions C-02, C-03, C-04, C-11, C-12.

## Why this exists

Urban and stock-scale energy studies cannot simulate every building in full detail. They rely on
**archetypes**: compact descriptions of a building type that can be simulated quickly and
assigned to thousands of buildings. The best source for an archetype is often a detailed model
that someone has already built and trusted, such as a standard prototype or a project model.

Reduction turns that detailed model into an archetype. Its value depends entirely on one thing:
**the archetype must behave like the building it came from.** If a reduction silently mixes
operating rooms with corridors, inflates hot water use, or misstates how efficient the plant is,
every building the archetype is applied to inherits the error.

archetypal v2 offered reduction, but only to two zones (core and perimeter), with aggregation
rules that varied by parameter without a stated reason, known defects (perimeter averages that
included core zones, zone multipliers that skewed averages, roofs ignored when deciding
exposure), and slow schedule handling. Users reported oversized hot water use (#390), wrong
conditioning efficiencies (#66, #123, #127) and implausible small cores (#383). v3 specifies
reduction afresh: what it preserves, why, and how anyone can confirm it did.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reduce a detailed model to an archetype (Priority: P1)

A building energy modeller has a detailed EnergyPlus model of a building type (for example a
hospital prototype) and the results of simulating it. They reduce it to an SBEM archetype. The
archetype keeps one zone group per combination of space use and exposure (for example "patient
rooms, perimeter", "operating rooms, core", "corridors, core"), each with its share of the
floor area, its envelope, its internal loads and schedules, its ventilation, hot water and
conditioning. Alongside the archetype they receive a reduction report that shows, for every
group, which detailed zones it came from and how each value was derived.

**Why this priority**: this is the capability v3 exists for and the one v2 users rely on
(roadmap C-10). Every other story builds on it.

**Independent Test**: reduce each building in the reference set and check that the archetype
is valid SBEM, that every conserved total matches the detailed model, and that the report
accounts for every detailed zone.

**Acceptance Scenarios**:

1. **Given** a detailed model with simulation results, **When** the modeller reduces it,
   **Then** they receive an SBEM archetype whose zone groups' floor-area shares sum to 100 % of
   the conditioned floor area and a report listing every detailed zone in exactly one group or
   in the list of excluded zones, with the reason.
2. **Given** a model in which operating rooms and corridors have different internal loads and
   schedules, **When** it is reduced with the default layout, **Then** they end up in different
   zone groups.
3. **Given** a model with zone multipliers (for example one typical floor multiplied by 10),
   **When** it is reduced, **Then** its groups, floor areas and every conserved total of FR-014
   to FR-021 agree within 0.1 % with reducing the same building modelled with every floor drawn
   explicitly. Parameters derived from simulation results (FR-022, FR-022a) may differ by as
   much as the two simulations do.
4. **Given** the same inputs, **When** the reduction is run twice, **Then** both archetypes and
   reports are identical.

---

### User Story 2 - Choose how coarse the archetype is (Priority: P2)

The modeller needs a simpler archetype than the default: by space use only, core/perimeter only
(the layout UMI requires), or a single zone. They choose the layout and receive an archetype
with that many groups, plus a report of what merging cost them (which distinctions were lost).

**Why this priority**: core/perimeter is required to keep v2's workflow of producing UMI
template libraries (spec 003, roadmap C-10), and many stock studies want the smallest archetype
that is still faithful.

**Independent Test**: reduce a reference building directly to core/perimeter, and separately
reduce it to the default layout and then merge to core/perimeter; the two archetypes must
match.

**Acceptance Scenarios**:

1. **Given** a detailed model, **When** the modeller asks for the core/perimeter layout,
   **Then** the archetype has two zone groups, core and perimeter (one, when the building has
   no core zones; see scenario 3), and the report lists the space-use distinctions that were
   merged.
2. **Given** an archetype at the default layout, **When** it is merged to a coarser layout,
   **Then** the result equals reducing the detailed model directly to that coarser layout
   (merging and reducing follow the same rules; roadmap C-11).
3. **Given** a building with no core zones (for example a narrow bar building), **When** the
   core/perimeter layout is requested, **Then** the archetype has a perimeter group only and
   the report says so.

---

### User Story 3 - Confirm the archetype behaves like the building (Priority: P3)

Having simulated both the detailed model and the archetype, the modeller wants to know how
closely the archetype reproduces the building: annual energy by end use and fuel, and peak
heating and cooling demand. They provide both sets of results and receive a comparison that
states each difference and whether it is within the project's acceptance targets.

**Why this priority**: it turns "faithful" from a claim into evidence (constitution IV), and it
is how the project itself proves v3 is more correct than v2. It depends on stories 1 and 2.

**Independent Test**: for a reference building, supply the detailed and archetype results and
check that the comparison reports each end use and peak, and flags any difference outside the
targets in SC-001 to SC-003.

**Acceptance Scenarios**:

1. **Given** results for a detailed model and its archetype, **When** the modeller compares
   them, **Then** they see, for total site energy, each end use and annual peak heating
   and cooling demand, the two values, their difference, and whether it is within target.
2. **Given** results that cover different weather files or run periods, **When** the modeller
   compares them, **Then** the comparison refuses and explains why the results are not
   comparable.

---

### Edge Cases

- **Model with no conditioned zones**: reduction stops and explains that an archetype needs
  conditioned floor area.
- **Missing simulation results** that reduction needs (for example zone floor areas as
  EnergyPlus computed them, sizing results or delivered heating and cooling): reduction states
  which results are missing and how to obtain them, and produces no archetype.
- **Unconditioned zones** (plenums, attics, crawlspaces, unconditioned basements): they never
  become zone groups. Where SBEM has a matching building-level assumption (attic, basement)
  they map to it; otherwise they are listed in the report as excluded, with their floor area.
  Their envelope is not dropped (FR-013): a plenum's roof and exterior walls are carried by the
  groups of the conditioned zones it serves.
- **A space use covering a very small share of floor area** (below the small-group threshold):
  it is merged into the most similar group of the same exposure, and the report says so.
- **A group with no delivered heating or cooling** (for example a core group in a hot climate):
  its efficiency for that mode cannot be derived from results (FR-022).
- **Zones with identical names in different storeys, zone lists and group multipliers**: each
  zone counts exactly as many times as EnergyPlus counts it.
- **A detailed model feature SBEM cannot express** (for example a specific HVAC topology,
  daylighting controls, or an internal gain type with no SBEM counterpart): its effect is
  carried into the nearest SBEM parameter where a conservation rule allows it, and otherwise
  listed in the report as not represented. Nothing is dropped silently.
- **Unsupported EnergyPlus version**: reduction states which versions are supported and that
  the model can be migrated with idfkit first.
- **Interrupted or partial inputs** (a model whose zones do not match its results): reduction
  refuses and names the mismatched zones.

## Requirements *(mandatory)*

### Functional Requirements

**Inputs and outputs**

- **FR-001**: Users MUST be able to reduce a detailed EnergyPlus model, together with the
  results of simulating it, to one SBEM archetype.
- **FR-002**: Reduction MUST declare which simulation results it needs. When results are
  missing and EnergyPlus is available, users MUST be able to have the detailed model simulated
  once, through idfkit, as part of the reduction; archetypal does not orchestrate batches of
  simulations (constitution III).
- **FR-003**: Every archetype produced MUST be valid SBEM as defined by epinterface, so that
  epinterface can generate an EnergyPlus model from it without modification.
- **FR-004**: Every reduction MUST produce a reduction report alongside the archetype
  (see Key Entities).
- **FR-005**: Reduction MUST be deterministic: the same model and results always produce the
  same archetype and report.

**Zone groups and layouts** (roadmap C-11)

- **FR-006**: Each conditioned detailed zone MUST be classified by **exposure**: *perimeter* if
  it has at least one exterior wall or window facing the outdoors, *core* otherwise. Roofs,
  exposed floors and ground contact do not decide exposure; their areas and heat loss are
  conserved as envelope quantities of whichever group the zone belongs to.
- **FR-007**: Each conditioned detailed zone MUST be classified by **space use**, using, in
  order of precedence: (1) a mapping supplied by the user; (2) space types declared in the
  model; (3) zones whose internal loads, schedules and thermostat settings are the same are
  treated as one space use. "The same" MUST tolerate numerical rounding, and the resulting
  classification MUST NOT depend on the order in which zones appear in the model. The report
  MUST state which source decided each zone's space use.
- **FR-008**: The default layout MUST form one zone group per combination of space use and
  exposure present in the model.
- **FR-009**: Users MUST be able to choose a coarser layout: by space use only, core/perimeter
  only, or a single zone.
- **FR-010**: A coarser layout MUST give the same archetype whether it is produced directly from
  the detailed model or by merging a finer archetype (one set of rules for forming and merging
  groups).
- **FR-011**: A group whose floor-area share is below a small-group threshold MUST be merged
  into the most similar group of the same exposure (or, in a layout without exposure, the most
  similar group). The threshold MUST be applied once, to the groups of the requested layout
  formed from the detailed zones, never to the groups of an intermediate finer layout; merging a
  finer archetype therefore starts from its groups before thresholding, which the archetype's
  report MUST retain (FR-010). A small group with no other group to merge into is kept. The
  threshold MUST be adjustable by the user, defaults to 5 % of conditioned floor area, and every
  such merge MUST appear in the report.
- **FR-012**: Every detailed zone MUST count exactly as many times as EnergyPlus counts it
  (zone multipliers and list multipliers included).
- **FR-013**: Unconditioned zones MUST NOT become zone groups. Attics and basements MUST map to
  SBEM's corresponding building-level assumptions where they exist; any other unconditioned
  zone MUST be listed in the report as excluded, with its floor area. The envelope of an
  excluded zone (for example a plenum's roof and exterior walls) MUST be carried by the groups
  of the conditioned zones it is adjacent to and conserved under FR-016, and the report MUST
  state the assignment.

**What reduction conserves** (constitution IV, roadmap C-12)

Each rule below names the quantity a group conserves relative to the detailed zones it is made
of. An intensity in the archetype (per floor area, per envelope area) is the conserved total
divided by the group's matching basis.

- **FR-014 — Floor area**: each group's floor area MUST equal the sum of its zones' floor areas;
  shares MUST sum to 100 % of conditioned floor area.
- **FR-015 — Internal gains**: for occupancy, lighting, equipment and every other internal gain
  type SBEM represents, each group MUST conserve the installed total (people, watts) and the
  hourly total over the year (installed total × schedule). Where the detailed model defines a
  split between sensible, latent, radiant and convected parts, each group MUST conserve the
  annual energy of each part; a single group fraction cannot also conserve the installed split
  when member zones run on different schedules, so the installed split is not conserved.
- **FR-016 — Envelope**: for each envelope element class (exterior walls, roofs, exposed floors,
  ground-contact surfaces, windows), each group MUST conserve the element area and its heat
  loss coefficient (area × thermal transmittance). For windows, it MUST additionally conserve
  area by orientation, the solar heat gain admitted (area × solar heat gain coefficient) and
  the visible light admitted (area × visible transmittance), by orientation.
- **FR-017 — Thermal mass**: each group MUST conserve the heat capacity of its envelope
  constructions and of its internal mass.
- **FR-018 — Infiltration**: each group MUST conserve the total design infiltration airflow and
  its hourly profile (design airflow × schedule). Where member zones' infiltration responds
  differently to weather (wind and temperature coefficients), the difference in realised
  airflow MUST be listed in the report as not represented (FR-026).
- **FR-019 — Mechanical ventilation**: each group MUST conserve the total outdoor airflow and its
  hourly profile, and the presence and effectiveness of heat recovery and economiser control
  weighted by the airflow they apply to.
- **FR-020 — Thermostat settings**: heating and cooling setpoints have no conserved total; each
  group's setpoint schedule MUST be the floor-area-weighted mean of its zones', and the report
  MUST state that this rule is representative rather than conserving. Only zones heated (or
  cooled) enter the heating (or cooling) mean; a zone with no thermostat for a mode, or with a
  setpoint that disables it, does not, and the report MUST state the share of the group's floor
  area that is not heated or not cooled.
- **FR-021 — Domestic hot water**: each group MUST conserve the total hot water use (volume and
  hourly profile) of its zones and the energy needed to heat it: the group's supply temperature
  MUST be the mains temperature plus the volume-weighted mean of its zones' temperature rise
  above mains. Hot water attached to the building as a whole MUST be allocated to groups in
  proportion to the use that drives it, and the report MUST state the allocation.
- **FR-022 — Conditioning efficiency**: each group's heating and cooling efficiencies MUST be
  the effective seasonal values that reproduce, for the heating and cooling energy delivered to
  its zones in the detailed simulation, the energy consumed to deliver it, by fuel. Merging
  groups MUST conserve both delivered and consumed energy (the merged efficiency is total
  delivered over total consumed), so the report MUST carry each group's delivered and consumed
  energy by fuel (FR-010). Where a group receives no delivered heating (or cooling), its
  efficiency for that mode MUST be taken from the equipment serving it, and any consumption not
  attributable to delivered energy (standby, pilot lights) MUST be listed in the report.
  Fan energy is not folded into these efficiencies: it is carried by FR-022a. Where the
  detailed model's efficiency depends on outdoor temperature (heat pumps, air-cooled
  chillers), the group's efficiency MUST carry that dependence, and still reproduce the
  annual consumed energy by fuel exactly.
- **FR-022a — Fan energy**: each group MUST carry the fan energy of its zones as its own
  quantity, as energy per volume of air moved (specific fan power), so that the archetype
  reports a fan end use. The group's fan energy and air volume in the detailed simulation MUST
  both be conserved, and merged like FR-022's totals. The air volume the archetype moves MUST
  follow from the same delivered energy and supply-air temperatures as the detailed model, so
  that the archetype's fan energy matches the detailed model's.
- **FR-023 — Schedules**: every schedule in the archetype MUST be expressed as an EnergyPlus
  `Schedule:Compact` that keeps the day types present in the source (weekdays, weekends,
  holidays, design days) and reproduces the conserved hourly profile of FR-015, FR-018,
  FR-019 and FR-021.
- **FR-024 — Geometry characteristics**: the archetype MUST carry the geometric characteristics
  needed to simulate it: floor-area share of each group, envelope and window areas by
  orientation relative to floor area, and number of storeys. These describe the building;
  reduction does not generate geometry (constitution III).

**Provenance, loss and evidence**

- **FR-025**: For every zone group, the report MUST list the detailed zones it was formed from
  and, for every archetype parameter, the conservation rule that produced it.
- **FR-026**: The report MUST list every feature of the detailed model that the archetype does
  not represent, and, where its effect was folded into another parameter, which one.
- **FR-027**: Users MUST be able to compare the simulation results of a detailed model and of its
  archetype, and receive, for total site energy, each end use by fuel that EnergyPlus reports
  (heating, cooling, interior and exterior lighting, interior equipment, fans, pumps, heat
  rejection, refrigeration, service hot water and any other) and annual peak heating and
  cooling demand, both values, the difference and whether it meets the acceptance targets.
- **FR-028**: The comparison MUST refuse results that are not comparable (different weather,
  run period, reporting units, or timestep and reporting frequency, on which peak demand
  depends) and say why.

**Errors**

- **FR-029**: Reduction MUST stop with an explanation, and produce no archetype, when the model
  has no conditioned zones, when required results are missing, when model and results do not
  match, or when the EnergyPlus version is not supported.

**Documentation** (constitution VI)

- **FR-030**: The user-facing documentation MUST include an explanation page stating what
  reduction conserves and why (FR-014 to FR-024), a how-to guide for reducing a model and
  choosing a layout, and reference for the reduction report.

### Key Entities

- **Detailed model**: a multizone EnergyPlus model of one building, as built by its author.
- **Simulation results**: the outputs of simulating the detailed model (or the archetype) for a
  given weather file and run period.
- **Zone group**: a set of detailed zones that share a space use and an exposure, described by
  one SBEM zone definition and its share of the conditioned floor area. Not to be confused with
  EnergyPlus's `ZoneGroup` object (a zone list with a multiplier), which is unrelated.
- **Layout**: the rule that decides how zones are grouped: space use × exposure (default), space
  use only, core/perimeter, or single zone.
- **Archetype**: the SBEM description of the building: its zone groups and building-level
  characteristics (geometry characteristics, attic and basement assumptions).
- **Reduction report**: the record of a reduction: each group's source zones, each parameter's
  rule, excluded zones, merged small groups, the source of each space-use classification, and
  what was not represented. It also records what is needed to reproduce the reduction: the
  versions of archetypal, EnergyPlus and epinterface, identifiers of the model, results and
  weather file used, and the options chosen (layout, threshold, space-use mapping).
- **Reference set**: the buildings on which reduction is verified: the DOE/PNNL commercial
  prototype buildings (all building types) in at least three climate zones (hot, mixed, cold),
  plus at least one residential model (roadmap C-12).

## Success Criteria *(mandatory)*

### Measurable Outcomes

Across the reference set, with each detailed model and its archetype simulated with the same
weather and run period:

- **SC-001**: Total annual site energy of the archetype is within ±5 % of the detailed model's
  for every building.
- **SC-002**: Each end use reported in FR-027 is within ±10 % for every building where that end
  use is at least 5 % of total site energy. Fans are compared as their own end use (FR-022a).
  Pumps and heat rejection have no counterpart in the archetype: they are added to the heating
  and cooling end uses they serve, in proportion to that service, before comparing.
- **SC-003**: Annual peak heating and cooling demand are each within ±15 % for every building
  where that peak is at least 10 % of the larger of the building's two peaks.
- **SC-004**: v3's error on SC-001 to SC-003, with v3 reduced to the core/perimeter layout that
  v2 produces, is smaller than v2's on the same buildings, for the set as a whole (mean
  absolute relative error) and for at least 90 % of individual buildings. Comparing at the
  same layout isolates the aggregation rules from the finer zoning. This is what "more correct
  than v2" means.
- **SC-005**: Every conserved total named in FR-014 to FR-019, FR-021, FR-022 and FR-022a
  matches the detailed model within 0.1 % (exactly, where the detailed total is zero) for
  every building and every layout.
- **SC-006**: 100 % of reference buildings reduce without error at every layout, and 100 % of
  detailed zones are accounted for in each report.
- **SC-007**: Reducing directly to a coarser layout and merging a finer archetype to it give
  archetypes whose parameters agree within 0.1 % for every reference building.
- **SC-008**: Excluding simulation time, reducing the largest reference building takes under
  10 seconds on a typical laptop, and reducing the whole reference set is at least 10 times
  faster than v2.

The targets in SC-001 to SC-003 may be tightened or adjusted during clarification once a v2
baseline has been measured, but none may be removed (roadmap C-12).

## Assumptions

- The detailed model is in an EnergyPlus version that idfkit reads; older models are migrated
  with idfkit before reduction.
- epinterface supports archetypes with several zone groups (UP-2) before this spec is
  implemented. Until upstream accepts it, that support comes from the maintained fork archetypal
  depends on (roadmap C-17), which is not published on PyPI; publishing archetypal 3 there
  waits for upstream (UP-3).
- The residential reference model is the DOE residential prototype (single-family detached);
  further residential models may be added.
- "Typical laptop" in SC-008 means a recent four-core machine; the plan fixes the benchmark
  machine and records it.
- The default small-group threshold of 5 % balances keeping distinct space uses against
  producing groups too small to matter; it is adjustable (FR-011).
- Out of scope: generating an EnergyPlus model from the archetype (epinterface), writing UMI
  template libraries (spec 003), calibration against measured data (roadmap C-05), and running
  simulations other than the single optional run in FR-002.
