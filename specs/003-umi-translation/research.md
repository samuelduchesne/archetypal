# Research: Translate UMI template libraries to and from SBEM

**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md)

Phase 0 of the plan. Every decision gives its evidence, the rationale and the alternatives
rejected. Sources:

- **Basilisk** (`github.com/MITSustainableDesignLab/basilisk`, MIT), commit `5cce24e8` (tag
  `v0.2.2`), the library UMI uses to read template libraries. Paths such as `Core/Library.cs`
  are relative to it.
- **epinterface** 1.5.0 at commit `f414ccb`, the base of the SBEM fork (roadmap C-17). Paths
  such as `sbem/components/envelope.py` are relative to its package.
- **idfkit** 1.2.0 as installed (`idfkit.thermal`).
- The UMI libraries in `tests/input_data/umi_samples/`: `BostonTemplateLibrary_2.json` (**B2**),
  `BostonTemplateLibrary_nodup.json` (**ND**) and the `BostonTemplateLibrary.json` inside
  `umi_samples.umi` (**UZ**).
- archetypal v2's `archetypal/template/` and `umi_template.py`, as evidence of past behaviour
  only (constitution V).

## Findings that shape the plan

1. **Basilisk validates almost nothing.** `Library.FromJson` (`Core/Library.cs:82-85`) calls
   Newtonsoft with default settings. There are no required fields, no ranges, no check on the
   number of hourly values or week days. A `$ref` that points nowhere, or to an object defined
   later in the file, silently becomes `null`. Its only library rule, `OrphanedComponents()`
   (`Core/Library.cs:121-146`), runs when *saving*, and finds components that are referenced
   but missing from their collection, with two gaps found by the harness (R15): it misses a
   zone or structure definition missing from `Zones` or `StructureDefinitions`, and it lists a
   week's `null` day (a dangling day reference), its one reaction to a dangling reference. It
   does **not** flag components no template uses: B2 and
   UZ, both written by Basilisk, contain 29 of them. Basilisk's editor layer adds one more
   rule: names are unique and not null within each collection, glazing and gas materials
   together (`Controls/InterfaceModels/Library.cs:315-474`).
2. **There is no format version.** `BuildingTemplate.Version` is a per-template user field.
   Libraries differ by shape: the current Core JSON (newest fields `AdvancedModel`,
   `UseAdvancedModel`, hot-water `FuelType`), the same without those fields (B2, ND), the older
   Archsim-era JSON (UZ: `GasType`, `Life`, `Comment` on materials) and two XML forms.
3. **SBEM cannot hold a third of UMI's simulation-relevant fields.** epinterface 1.5.0 has no
   window settings (operable area, shading, zone mixing, airflow network), no partition ratio,
   no natural-ventilation limits, no scheduled ventilation, no mechanical-ventilation schedule,
   no heating or cooling limits, no daylighting parameters, no adiabatic-surface flags, no
   heating or cooling availability schedule, and windows are simple glazing only
   (`sbem/components/envelope.py:26-65`). It also has no archetype-level descriptive fields
   and no place for most life-cycle fields. Roadmap C-13 requires every simulation-relevant
   UMI field to be representable, so these become an upstream item (R6).
4. **SBEM nests by value and identifies by name.** `model_dump` repeats every schedule,
   material and construction wherever it is used, and epinterface's EnergyPlus writers skip a
   second object with a name already written (`sbem/components/schedules.py:148, 254, 430`).
   Two different components with one name therefore collapse silently into the first.
5. **Issue #459 does not arise in SBEM.** In both formats thickness belongs to the layer, not
   the material (`Core/MaterialLayer.cs`; `ConstructionLayerComponent.Thickness`), and
   epinterface names each EnergyPlus material `"{name}_{thickness}m"`
   (`sbem/components/envelope.py:178`). B2 uses 8 materials at several thicknesses; they
   translate without any collision. A true name collision (two different components with one
   name in one collection) is possible only in a hand-edited file.
6. **Units and meanings differ in five places:**
   - hot water per floor area and per hour in UMI, per person and per day in SBEM;
   - the thermostat as a scalar setpoint with an availability schedule in UMI, as temperature
     schedules in SBEM;
   - one coefficient of performance in UMI, a system and a distribution COP in SBEM;
   - material embodied carbon per kg and cost per m³ in UMI, both per one `RateUnit` in SBEM;
   - schedules over arbitrary date ranges in UMI, one week per calendar month in SBEM.

## R1 — Reading the UMI format

**Decision.**

- Basilisk at commit `5cce24e8` is the authority on the format (spec, Assumptions). Every
  Basilisk Core class is mirrored by an internal pydantic v2 model in
  `archetypal.umi._format`:
  - the JSON keys are aliases;
  - a missing key takes Basilisk's effective default, its `[DefaultValue]` if any, else the
    initialiser (Basilisk research §1.5), and is recorded as *defaulted*;
  - enums are `IntEnum`s with Basilisk's integer values.
  These models are a parsing layer, not an archetype model. They are private, never returned
  and never edited (roadmap C-02).
- References are resolved in two passes over the raw JSON (`archetypal.umi._refs`):
  1. A pre-scan walks the document in file order. It records each `$id`, which must be the
     first key of its object and unique. It checks that each `$ref` is a string, that the
     object holding it has no other key, and that the id was seen **earlier** in the file.
  2. Objects are built from the index, so a reference is an object, never `None`.
  A dangling or forward reference is a format problem (R3, `UmiFormatError`), not a silent
  `null` as in Basilisk.
- `BuildingTemplates` have no `$id`. Window settings may be defined inline in the first
  template that uses them (Basilisk's own order) or in the `WindowSettings` collection (v2's
  order); both are read.
- Collection keys are Basilisk's: `Zones`, `StructureDefinitions`, `VentilationSettings` and
  `ZoneConstructionSets`, not the class names. A missing collection is empty. An unknown key is
  ignored and noted.

**Rationale.** A typed model of the file gives pyright-checked access to every field, and the
pre-scan makes reference errors visible, which Basilisk does not.

**Alternatives considered.**

- *Read with plain dicts.* Rejected: untyped access defeats pyright strict (constitution VI).
- *Port v2's `template/` classes.* Rejected: roadmap C-02 and C-04. v2 also drops unknown keys
  silently and rounds on writing (R13).

## R2 — Dialects (edge case "UMI library versions")

**Decision.** The reader identifies the dialect from its shape, since no version number exists:

| Dialect | Recognised by | Outcome |
|---|---|---|
| Current Core JSON | JSON with the 17 collections; any of `AdvancedModel`, `UseAdvancedModel`, hot-water `FuelType` present | Read. |
| Current Core JSON, pre-2023 fields | As above with none of those fields (B2, ND) | Read. Each absent field takes Basilisk's default and is noted as defaulted. |
| Archsim-era JSON | Material objects carrying `GasType`, `Life` or `Comment` (UZ) | Read through a key map: `Comment` → `Comments`, `GasType` 0–4 → `AIR`, `ARGON`, `KRYPTON`, `XENON`, `SF6` (its `Type: "Gas"` is ignored, unlike Basilisk), material `Type` → `Category`. Keys with no Core counterpart (`Life`, `EmbodiedEnergyStdDev`, `PhaseChange`, `Optical`, …) are listed as lost. |
| Legacy XML (`<LibSerializable>`), Core XML, a `.umi` project | XML root, or a zip | Refused, naming the dialect: "Legacy UMI XML library is not supported; open and save it in UMI to convert it to JSON". For `.umi`, the message names the library file to extract. |
| Anything else | | Refused, naming the marker that was missing. |

The writer always writes the current Core JSON (Basilisk at the pinned commit).

**Rationale.** It reads every library found in the project's test data. The spec's "message
naming the version" names a dialect, since none has a version (spec feedback F-4).

**Alternative considered.** *Read only the current format.* Rejected: UZ is the sample shipped
with UMI projects and is the most likely older library in users' hands.

## R3 — Validation before translation (FR-004, edge cases)

**Decision.** Reading collects every problem of a kind before producing anything, then raises
one error that lists them all, each with a JSON pointer (`/Zones/2/Loads`) and the template
affected. Three kinds of problem:

1. **Format** (always fatal for the library): malformed JSON, duplicate `$id`, `$id` not first,
   a non-string `$ref`, extra keys beside `$ref`, a dangling or forward `$ref`, a JSON type
   that does not convert (Basilisk's own errors). Reference resolution raises these as one
   `UmiFormatError`, before completeness and range are checked, so they never appear inside
   an `UmiValidationError`.
2. **Completeness.** Required references, inferred from what Basilisk's editor dereferences
   and what UMI needs to build a model (Basilisk research §4.4), must not be null:
   - each layer's material;
   - the 7 days of a week;
   - each year part's week;
   - a template's `Core`, `Perimeter` and `Windows`;
   - the 6 references of a zone definition and the 5 of a construction set;
   - every schedule of loads (3), conditioning (3), ventilation (2), hot water (1) and window
     settings (3);
   - the window settings' construction.

   Also: 24 values in each day, and year parts that cover 1 January to 31 December with no
   gap or overlap.
3. **Range.** Every value must satisfy the constraint of the SBEM field it maps to (the
   epinterface field's `ge`/`le`), and the plausibility rules of the correspondence table
   (R5): a COP above 0 when heating or cooling is on, a supply temperature above the inlet
   temperature, absorptances and fractions in [0, 1], a specific heat of at least 100 J/kg·K,
   and so on.

Completeness and range problems are raised together as one `UmiValidationError`.
`skip_invalid_templates=True` makes them skip only the templates
they affect. Those templates are listed in the report and the others are read. Format
problems are never skipped. Duplicate names are not a problem; R11 handles them.

**Rationale.** FR-004 asks for every problem with its location before any archetype exists.
Basilisk checks none of this, so the translator must.

**Alternative considered.** *Rely on epinterface's validation of the result.* Rejected: its
messages name SBEM fields, not the UMI location the user must fix.

## R4 — The shape of an archetype read from UMI (FR-001, FR-002)

**Decision.**

- One building template gives one archetype of the multi-group SBEM model (UP-2), with two
  groups, `core` and `perimeter`, built from the template's `Core` and `Perimeter` zone
  definitions. When both reference the same zone definition (every template of every sample
  does), the two groups are equal.
- The groups' floor-area shares are **unset**: `None` for every group means "set by the
  building's geometry when the archetype is applied". This is the layout the spec calls "core/perimeter by
  geometry", and it is what epinterface's shoebox already does: core and perimeter areas come
  from `w`, `d` and `perim_depth` (`sbem/builder.py:913-914`). UP-2 must allow unset shares;
  this plan adds that to UP-2's scope (roadmap update).
- Building-level template fields go to the archetype's building-level fields (UP-2, UP-9):
  window settings, `DefaultWindowToWallRatio` (as the window-to-wall ratio of every
  orientation), `PartitionRatio`, the structure, and the descriptive fields (R11).
- The archetype is named after the template. Its file, when written, is `<name>.sbem.json`
  (002 research R14).

**Rationale.** It mirrors UMI's own semantics (clarification 1) and needs no invented shares.

**Alternative considered.** *Assume default shares (for example 30 % core).* Rejected by
clarification 1: a fixed share would be invented, not read.

## R5 — The field correspondence (FR-009, FR-010, SC-005)

**Decision.**

- `archetypal.umi.correspondence.CORRESPONDENCE` is a tuple of `FieldMapping` records, one per
  Basilisk Core field (data-model.md). Each names:
  - the UMI class and JSON key;
  - its relevance, `S` (simulation), `L` (life cycle) or `D` (descriptive);
  - the SBEM path or paths it maps to, or none;
  - the conversion rule's identifier;
  - its status: `exact`, `converted` (a stated conversion with a conserved quantity),
    `upstream` (no SBEM field yet; names the UP item), or `none` (no counterpart by design;
    states why).
- Each conversion is a function registered under its rule identifier (`@rule("dhw.per_person")`).
  A test checks that the table's rule identifiers and the registry are the same set, so the
  published table cannot drift from the code.
- Coverage is checked against Basilisk itself. `tools/basilisk-check --list-fields` lists every
  serialised member of every Core class by reflection. The list is committed as
  `tests/data/basilisk_fields.json`, and CI regenerates and compares it. A unit test requires
  every listed field to appear in `CORRESPONDENCE` (SC-005).
- The reference page `docs/reference/umi-correspondence.md` is generated from the table at
  build time, never written by hand (001 contract docs-site, rule 3).

**Rationale.** One table drives code, tests and documentation, so FR-009's published mapping
is always the implemented mapping.

**Alternative considered.** *A hand-written mapping document.* Rejected: it would drift, and
SC-005 could not be measured.

## R6 — What SBEM must add for UMI (C-13, FR-010): new upstream item UP-9

**Decision.** The field-by-field mapping shows that the following UMI fields have no SBEM home.
They are grouped into a new upstream item, **UP-9 — SBEM fields for UMI template libraries**,
built in the SBEM fork and offered upstream like UP-2 (roadmap C-14, C-17). UP-9 is split from
UP-2 because UP-2's zone groups block 002, while these fields block only 003's verification.

| UMI field(s) | Relevance | UP-9 addition |
|---|---|---|
| `WindowConstruction` layers (glazing and gas materials, thicknesses) | S | A layered glazing construction, as an alternative to simple glazing in the window slot |
| `WindowSettings`: `OperableArea`, `IsShadingSystemOn`, `ShadingSystemType`, `ShadingSystemSetpoint`, `ShadingSystemTransmittance`, `ShadingSystemAvailabilitySchedule`, `IsVirtualPartition`, `IsZoneMixingOn`, `ZoneMixingAvailabilitySchedule`, `ZoneMixingDeltaTemperature`, `ZoneMixingFlowRate`, `AfnDischargeC`, `AfnTempSetpoint`, `AfnWindowAvailability`, `Type` | S | A window-settings component at building level |
| `BuildingTemplate.PartitionRatio` | S | Partition area per floor area |
| `ZoneVentilation`: `NatVentMinOutdoorAirTemp`, `NatVentMaxOutdoorAirTemp`, `NatVentMaxRelHumidity`, `NatVentZoneTempSetpoint`, `IsWindOn`, `IsBuoyancyOn`, `Afn` | S | Natural-ventilation limits and switches (today fixed at 12/25 °C, `sbem/components/operations.py:333-336`) |
| `ZoneVentilation`: `IsScheduledVentilationOn`, `ScheduledVentilationAch`, `ScheduledVentilationSchedule`, `ScheduledVentilationSetpoint` | S | Scheduled ventilation |
| `ZoneConditioning.MechVentSchedule` | S | A schedule for mechanical outdoor air |
| `ZoneConditioning`: `HeatingLimitType`, `CoolingLimitType`, `MaxHeatFlow`, `MaxCoolFlow`, `MaxHeatingCapacity`, `MaxCoolingCapacity` | S | Ideal-loads limits (today always autosized) |
| `ZoneConditioning`: `HeatingSchedule`, `CoolingSchedule` (availability) | S | Heating and cooling availability schedules (R9) |
| `ZoneLoads.IlluminanceTarget`, `ZoneDefinition.DaylightMeshResolution`, `DaylightWorkplaneHeight` | S | Daylighting parameters |
| `ZoneConstructions.Is*Adiabatic` (5 flags) | S | Adiabatic flags per assembly |
| `BuildingTemplate`: `YearFrom`, `YearTo`, `Country`, `ClimateZone`, `Authors`, `AuthorEmails`, `Version`, `Lifespan`, `Name`, `Comments`, `DataSource`, `Category` | D, L | Archetype-level metadata |
| `StructureInformation` (`MassRatios`, `AdvancedModel`, assembly fields) | L | A structure component at building level |
| Material `EmbodiedEnergy`, `Transport*`, `Substitution*`, `MoistureDiffusionResistance`, `DesignStrength`, `ModulusOfElasticity`; construction `Assembly*`, `Disassembly*` | L, D | Environmental fields on materials and assemblies |
| Schedule `Comments`, `DataSource`, `Category` | D | Metadata on schedules |

Heat-recovery effectiveness, holiday and design-day slots and orientation ratios are already in
UP-2 (002 research). UP-9 also fixes two epinterface defects that would break conservation:

- `fractional_year_sum` counts weekdays as if every month began on a Tuesday
  (`sbem/components/schedules.py:634`), which skews the hot-water peak flow (R10);
- `Provider="Both"` gives mechanical ventilation only (`sbem/components/operations.py:311`).

**Blocking.** Until a field lands in a fork release, every read reports it as lost (FR-010),
with the UP item. The translator is built and tested without UP-9. 003 cannot be marked
implemented until UP-9's simulation-relevant (`S`) fields are released, because SC-003
measures them (spec feedback F-5). The `L` and `D` fields block it too, because FR-010
requires descriptive fields to map to SBEM (roadmap C-20); none of them blocks building 003.

**Rationale.** It follows C-13 and constitution I: the gap is closed in SBEM, not by a side
model in archetypal.

**Alternatives considered.**

- *Carry the missing fields in an archetypal sidecar file, read back on writing.* Rejected: a
  second archetype model (constitution II), and epinterface would not simulate what it holds.
- *Grow UP-2.* Rejected: UP-2 blocks 002, which needs none of these fields.

## R7 — Schedules (FR-008, edge case "Schedules")

**Decision.**

- **Calendar.** A UMI week's `Days[0..6]` are Monday to Sunday (Basilisk's week editor), the
  same order as SBEM's slots. Weeks align with calendar weekdays, as in EnergyPlus's
  `Schedule:Week:Daily`. v2 restarted the week at each part's start date; that behaviour is
  not kept (the explanation page states the convention).
- **UMI → SBEM.** For each month:
  - **Exact** when one year part covers the whole month: the month's `WeekComponent` is that
    part's week, and its days are the UMI days.
  - **Projected** when part boundaries fall inside the month. The schedule is evaluated hour by
    hour for the reference year, and the month is projected to one representative week with
    002's projection (002 research R5), which conserves the month's sum. The month and the
    days that used another week are listed as approximate.
- **SBEM → UMI.** Always exact, with no projection needed:
  - Consecutive months with equal weeks become one year part, ending on each month's last day,
    with February ending on 29 February.
  - Equal weeks and equal days are shared (R13).
  - Holiday and design-day slots (UP-2) that differ from the days they would replace are
    listed as lost, since UMI has none.
- **Type.** A UMI `Type` of `Fraction`, `Temperature` or `AnyNumber` maps to the SBEM day type
  of the same name. Any other value maps to `AnyNumber` and is noted. SBEM's year `Type` (the
  schedule's role) is set from the field the schedule fills (`Occupancy`, `Lighting`, and so
  on). One UMI schedule used in several roles becomes one SBEM year per role, all with the
  UMI name. Their content is equal, so epinterface's name-based deduplication is harmless.
- **Reference year.** A non-leap year starting on Monday, which is what v2 assumed for UMI.
  Monthly sums are taken over that calendar.

**Rationale.** Every sample schedule (13 single-part, 9 three-part, all month-aligned) reads
exactly. Misaligned parts are rare, but they are handled by conservation, not by truncation.

**Alternative considered.** *Pick the week covering most days of a misaligned month.*
Rejected: it changes the month's energy without bound and has no conservation statement
(constitution IV).

## R8 — Windows (FR-002, FR-005)

**Decision.**

- **UMI → SBEM.**
  - **With UP-9's layered glazing:** exact. Glazing layers, gas layers and thicknesses are
    copied.
  - **Until then (bridge):** the window is reduced to simple glazing.
    1. The UMI layers are built as an in-memory idfkit `Construction` with
       `WindowMaterial:Glazing` and `WindowMaterial:Gas`.
    2. `idfkit.thermal.calculate_u_value`, `calculate_shgc` and
       `calculate_visible_transmittance` give U, SHGC and VT.
    3. Every per-layer property is listed as lost. U, SHGC and VT are listed as approximate,
       naming idfkit's simplified method.
- **SBEM → UMI.**
  - A layered SBEM window is written as its layers (exact).
  - A simple-glazing window, which is what 002 produces, needs one equivalent glazing layer,
    since UMI has no simple-glazing material. That layer is computed with EnergyPlus's
    simple-glazing model (Engineering Reference, "Window Calculation Module: Simple Window
    Model"): U and SHGC give the layer's thickness, conductivity, solar transmittance and
    reflectances; VT gives its visible transmittance and reflectances.
  - idfkit has no such function. It is requested as **UP-10** (idfkit) and bridged meanwhile
    in `archetypal.umi._bridges.equivalent_glazing_layer`, removed when UP-10 is released.
  - The written layer reproduces U, SHGC and VT as EnergyPlus computes them. The loss report
    lists the window as written in a different form (approximate).
- **Placement.** UMI has one window per building template; SBEM has one per zone group.
  - Reading gives both groups the template's window.
  - Writing uses the perimeter group's window. A different core window is listed as lost.

**Rationale.** It is exact where SBEM allows it. The two-way conversion is EnergyPlus's own
model, so the simulated window is the same.

**Alternatives considered.**

- *Write an invented double-glazing unit matching U and SHGC.* Rejected: the solution is not
  unique, and it would claim layers no one specified.
- *Implement the conversion in archetypal permanently.* Rejected: an EnergyPlus computation
  belongs in idfkit (constitution I).

## R9 — Thermostats and availability

**Decision.**

- **UMI → SBEM.**
  - The heating temperature schedule is the scalar `HeatingSetpoint` in every hour, and cooling
    likewise.
  - `IsHeatingOn = false` gives `Heating = None` (epinterface's off), and cooling likewise.
  - The availability schedules (`HeatingSchedule`, `CoolingSchedule`) go to UP-9's
    availability schedules. Until UP-9, they are listed as lost unless every value is 1.
- **SBEM → UMI.**
  - `HeatingSetpoint` is the heating schedule's maximum, and `CoolingSetpoint` the cooling
    schedule's minimum: the occupied setpoints.
  - A schedule that is not constant (setbacks) cannot be written exactly. UMI holds one
    setpoint, so its hours below the maximum are listed as lost, with their count and mean
    difference.
  - With UP-9's availability schedules present, they are written; otherwise an always-on
    schedule is written.

**Rationale.**

- Read is exact once UP-9 lands. Write states the only representable form.
- Encoding "off" as an extreme setpoint in SBEM was rejected: epinterface averages the
  thermostat schedules into ground temperatures (`sbem/builder.py:916-952`), and 002 averages
  setpoints across zones. A sentinel value would corrupt both.

**Alternative considered.** *Write setbacks as availability 0.* Rejected: it turns a reduced
setpoint into no heating, overstating the change.

## R10 — Loads, ventilation, systems and hot water

Each rule states what it conserves (constitution IV). The full table is in data-model.md.

**Decision.**

- **Gains.** `PeopleDensity`, `LightingPowerDensity` and `EquipmentPowerDensity` map exactly.
  Their schedules follow R7. `Is*On` maps to `IsOn`. `DimmingType` maps by name. SBEM's
  `MetabolicRate` has no UMI field: reading sets epinterface's default (1.2 met) and notes it;
  writing lists a non-default value as lost.
- **Infiltration.** `Infiltration` (ACH) maps to `AirChangesPerHour` with `CalculationMethod =
  "AirChanges/Hour"` and `IsOn`. Reading notes the unused coefficients: constant 1, others 0.
  Writing an archetype whose method is not air changes per hour needs the building's volume,
  so it is listed as lost with the value kept in the report. Attic and basement infiltration
  are filled from the main value on reading (noted), and dropped on writing when they differ
  (lost).
- **Mechanical ventilation.**
  - `IsMechVentOn` and `IsNatVentOn` give `Provider`: `Mechanical`, `Natural`, `Both` or
    `None`.
  - `MinFreshAirPerArea` and `MinFreshAirPerPerson` map exactly. SBEM caps both at 0.05;
    above that is a range problem.
  - `EconomizerType` and `HeatRecoveryType` map by name. Effectiveness goes to UP-2's numeric
    field.
  - SBEM's `DCV` has no UMI field: a value other than `NoDCV` is lost on writing.
  - `NatVentSchedule` maps to `Ventilation.Schedule`, which epinterface uses only for natural
    ventilation.
- **Heating and cooling.** UMI's `HeatingCoeffOfPerf` maps to `SystemCOP`, with
  `DistributionCOP = 1`. Writing gives `SystemCOP × DistributionCOP`, which conserves consumed
  energy for given delivered energy; the split is listed as lost when `DistributionCOP ≠ 1`.
  Fuels map through a table (data-model.md). Several-to-one cases (`FuelOil1`/`FuelOil2` →
  `FuelOil`, `OtherFuel1`/`OtherFuel2` → `CustomFuel`) and fuels with no counterpart
  (`DistrictHeating` on read, `WoodPellets` on write) are listed as lost, with the fuel
  substituted.
- **Hot water.**
  - Annual volume is conserved. Let `s(h)` be the water schedule's hourly value over the
    reference year and `ρ_p` the people density. Then:
    ```text
    FlowRatePerPerson [m³/day/person] = FlowRatePerFloorArea [m³/h/m²] × Σ s(h) / (365 × ρ_p)
    ```
    Writing uses the inverse.
  - A zone with hot water but no people (`ρ_p = 0` or people off) cannot be represented: it is
    a range problem on reading and a loss on writing.
  - `CoefficientOfPerformance` maps to `SystemCOP` with `DistributionCOP = 1`. `FuelType` maps
    through the table; Basilisk's `Unset` is a range problem.
  - Inlet and supply temperatures map exactly.
- **Internal mass.** `InternalMassConstruction` and `InternalMassExposedPerFloorArea` map
  exactly. A ratio of 0 means no internal mass, as SBEM's validator requires (both or
  neither).

**Rationale.** Each conversion is exact or conserves a named annual total, and its inverse
recovers the input to floating-point precision, which SC-003's 0.01 % allows.

## R11 — Constructions, materials, metadata and names (FR-003)

**Decision.**

- **Construction sets.** `Facade`, `Roof`, `Slab`, `Ground` and `Partition` map to
  `FacadeAssembly`, `FlatRoofAssembly`, `FloorCeilingAssembly`, `GroundSlabAssembly` and
  `PartitionAssembly`. SBEM's other slots are filled on reading from their nearest UMI
  counterpart, each noted:

  | SBEM slot | Filled from |
  |---|---|
  | `AtticRoofAssembly` | Roof |
  | `AtticFloorAssembly` | Slab |
  | `ExternalFloorAssembly` | Slab |
  | `BasementCeilingAssembly` | Slab |
  | `GroundWallAssembly` | Ground |

  On writing, a slot that differs from the one it would be filled from is listed as lost.
- **Layers.** Layers keep their order (outside first) and thickness.
- **Materials.**
  - `ThermalEmittance` maps to `ThermalAbsorptance`. `Roughness` must be one of EnergyPlus's
    six keywords (range problem otherwise).
  - SBEM's required `Type` is taken from the material's `Category` when it names one of the 12
    types (case-insensitive), else set to `Other` and noted.
  - `TemperatureCoefficientThermalConductivity` is set to 0 and noted.
- **Environmental fields.** SBEM has one `RateUnit` for cost and carbon, so both are written
  per m³ (`RateUnit = "m3"`): `Cost` as is, and `EmbodiedCarbon` as kg CO₂/kg × density,
  inverted on writing. This conserves carbon per unit volume. The other life-cycle fields wait
  for UP-9 (R6).
- **Metadata.** `Category`, `Comments` and `DataSource` map to SBEM's `Category`, `Comment`
  and `DataSource` on the component that receives the UMI component (data-model.md). Where
  SBEM has no metadata (schedules), they wait for UP-9.
- **Names.**
  - SBEM components keep their UMI names.
  - When two different components of one SBEM kind would share a name (a hand-edited library;
    a UMI glazing and gas material with one name, which Basilisk's editor forbids but Core
    loads), the second and later get the suffix ` #2`, ` #3`, … in file order. The collision
    is reported.
  - Duplicate building-template names keep both archetypes, renamed the same way and
    reported.
  - This replaces the spec's thickness example (spec feedback F-2): thickness is never part of
    a material's identity (finding 5).

## R12 — Writing an archetype that does not have exactly core and perimeter (FR-006, FR-006a, FR-006b)

**Decision.**

- **With its reduction** (a `Reduction` from spec 002, which carries the report): the archetype
  is merged with 002's `merge(reduction, Layout.CORE_PERIMETER)`, so the result is exactly
  what reduction gives at that layout (002 SC-007). The merged groups are listed (kind
  `merged`) with their pre-merge keys, from 002's `merged_distinctions`.
- **Without its reduction** (an archetype edited by hand, or read from SBEM alone): the groups
  are merged with the same ledger arithmetic, starting from ledgers rebuilt from the groups'
  SBEM parameters by `GroupLedger.approximate_from_group(group, floor_area)`, a 003 addition to
  002's `reduction.ledger`. The floor area is the group's share times 1 m²; only ratios matter.
  - Rules that need only intensities and areas rebuild exactly: gains and their profiles,
    setpoints (area-weighted in 002), outdoor air and its profile, and hot water.
  - Rules that need report data are rebuilt by floor-area weighting, and each such parameter
    is listed as approximate (FR-006):
    - envelope U and capacity: surface areas per group are unknown;
    - efficiencies: delivered and consumed energy are unknown;
    - infiltration;
    - the window.
  - An archetype with more than two groups and unset shares cannot be weighted. It is refused
    with an `InputError` naming the archetype.
- **Shares.** Fixed shares are dropped and listed as lost, with their values (FR-006a). Unset
  shares are not a loss.
- **Perimeter only.** The perimeter group's zone definition is written for both `Core` and
  `Perimeter`, once, as one shared `ZoneDefinition`. The report states that the core was
  copied, not derived (FR-006b).
- **Core only** (a single-zone archetype from 002's `SINGLE_ZONE` layout): its zone definition
  becomes both, and the report states it, by the same rule.

**Rationale.** It reuses 002's merging, so a UMI template is a further reduction (roadmap
C-11). Rebuilding approximately states exactly which parameters lack data.

**Alternative considered.** *Refuse to write without the reduction.* Rejected by clarification 2.

## R13 — Sharing, naming, order and determinism (FR-007, FR-012)

**Decision.**

- **Assembly.** The writer turns each archetype into UMI components, then collects them into
  one library:
  - Each component has a content key: its canonical JSON without `Name`.
  - Components with the same name and the same content are one component, so shared
    constructions and schedules appear once (US1 scenario 3).
  - A name used for different content gets ` #2`, ` #3`, … in order of first appearance, and
    the renaming is reported. Names are unique per collection, glazing and gas together,
    which Basilisk's editor requires.
  - Same content under different names stays as separate components. Nothing is lost, and
    UMI accepts it.
- **Unused components.** Only components reachable from a building template are written, so
  the library has none that is unused. Basilisk does not require this (finding 1); it is the
  project's choice, so written libraries contain nothing unexplained (spec feedback F-3).
- **Names of UMI components with no SBEM counterpart** are derived from the SBEM component
  that holds their content, by one rule per class (data-model.md). Reading uses the inverse
  rule, so names survive a round trip.
- **File form, matching Basilisk's writer:**
  - the 17 collections in Basilisk's order;
  - within each collection, components sorted by name;
  - `$id`s assigned `"1"`, `"2"`, … in document order;
  - window settings defined inline in the first template that uses them, with the
    `WindowSettings` collection all `$ref`s;
  - templates without `$id`;
  - enums as integers;
  - two-space indentation, `\n`, UTF-8 without BOM.
- **Numbers** are written with Python's shortest round-trip `repr`, never rounded (v2 rounded
  `MinFreshAirPerArea` to 3 decimals, turning B2's 0.0003 into 0). Integer fields are written
  as integers.
- **Determinism.** No timestamps. Archetypes are taken in the order given, and everything else
  is sorted. The same input gives byte-identical files (FR-012).
- **Reading** keeps the library's order for archetypes (template order) and is equally
  deterministic.

**Rationale.** It follows Basilisk's own output, so UMI reads what it would read from Basilisk.

## R14 — The loss report and strict mode (FR-011, FR-011a, SC-006a)

**Decision.**

- **Model.** `TranslationReport` is a pydantic model with a published JSON Schema
  (contracts/translation-report.md). It holds:
  - `direction` (`umi_to_sbem` or `sbem_to_umi`);
  - the source and its SHA-256, the dialect read, and the archetypal and epinterface versions;
  - `losses[]`: everything not represented in the target;
  - `notes[]`: assumptions and defaults that lose nothing.
- **Loss kinds:** `lost`, `approximate`, `merged`, `copied`, `share_dropped`, `renamed`,
  `unused`, `skipped_template`.
- **Note kinds:** `defaulted` (a field absent from the file took Basilisk's default),
  `assumed` (an SBEM field UMI lacks, filled by a stated rule) and `unknown_key`.
- **Each loss** names:
  - the subject (template or archetype);
  - the source location (a JSON pointer on the UMI side, a field path on the SBEM side);
  - the value;
  - what replaced it, if anything;
  - the rule identifier and the reason;
  - the UP item where the gap is upstream.
- **An empty report** has `losses: []` and the summary "Nothing was lost." (FR-011).
- **Strict mode** (`strict=True`) runs the whole translation, then raises
  `LossyTranslationError` carrying the report if `losses` is not empty. Nothing is written.
  Notes never fail strict mode. This is the separation SC-006a needs: "loss report not empty"
  means `losses` is not empty.
- **Files.** Reading writes `<library stem>.loss.json` beside the archetypes. Writing writes
  `<library stem>.loss.json` beside the library, the name 001's command line expects.

**Rationale.** Separating losses from notes makes strict mode exact and the summary honest.

## R15 — Checking written libraries with Basilisk (SC-002)

**Decision.**

- **Harness.** `tools/basilisk-check/` is a small .NET 8 console program. It compiles
  Basilisk Core's sources from a checkout pinned at `5cce24e8` (Core targets the end-of-life
  `net7`; compiling its sources avoids that target). For each library file it:
  1. scans the raw JSON with R1's reference rules, which Basilisk does not check;
  2. loads with `Library.FromJson`;
  3. requires `OrphanedComponents()` to be empty and `ToJson()` to succeed;
  4. requires unique, non-null names per collection and non-null required references, as
     Basilisk's editor does.
  It exits 0 when all pass, or with a distinct status per failed check, naming the file and
  the problem.
- **CI job.** A `basilisk` job in `main.yml` on every pull request (Ubuntu,
  `actions/setup-dotnet` 8.0) runs the unit and fixture tests that write libraries into a
  folder, then runs the harness on every file. The reference workflow does the same for the
  libraries written from 002's reference set.
- **Dependency.** .NET is a CI and contributor tool only, never a runtime or test dependency
  of the package (constitution III). Without .NET, the same Python checks run locally from
  `tests/umi/basilisk_rules.py`, so most failures show up before CI.
- **Field list.** The harness's `--list-fields` mode produces `tests/data/basilisk_fields.json`
  (R5).

**Rationale.** Clarification 5 requires automatic checking on every change with Basilisk.
Basilisk alone passes files with dangling references, hence the extra checks.

**Verified on 2026-11-22** (task T003) with the harness built on Linux against commit
`5cce24e8`, on B2, ND, UZ, the edge fixtures of `tests/fixtures/umi/edge/` and five probe
libraries:

- **(a) `FromJson` turns dangling and forward references into `null`: confirmed.** It raises
  no error. In `dangling_ref.json` the loads' `OccupancySchedule` (`$ref` "99") loads as `null`;
  in `forward_ref.json` (`Zones` written after `BuildingTemplates`) the template's `Core` and
  `Perimeter` load as `null`. Only check 1 (the reference scan) and check 4 (required
  references) catch them.
- **(b) `OrphanedComponents()` flags referenced-but-missing components only: confirmed, with
  two exceptions.** It never lists unused components (`no_templates.json`: 22 unused, none
  listed). It lists a non-null component absent from its collection, such as a year schedule
  or material defined inline and nowhere else, and `ToJson()` then throws. But:
  - a zone definition (or structure definition) that a template references and that is
    missing from `Zones` (`StructureDefinitions`) is **not** listed:
    `BuildingTemplate.ReferencedComponents` yields what the zones reference, not the zones
    (`Core/BuildingTemplate.cs:57-67`). The harness's check 3 therefore also walks every
    template and requires each component it reaches to be in its collection;
  - a dangling reference in a week's `Days` **is** listed, as a `null` orphan, because
    `WeekSchedule.ReferencedComponents` returns `Days` unfiltered; every other class drops
    `null` references with `OfType`.
- **(c) B2 and UZ load with 29 unused components each: confirmed.** ND has none. All three
  pass the four checks: no null required reference, every day with 24 values, every week with 7
  days, every year covering 1/1 to 12/31, unique names. UZ's Archsim-era keys are ignored by
  Newtonsoft's default settings.
- **(d) The build works on Linux without `net7`: confirmed.** With only the .NET 8.0.428 SDK
  and the 8.0.34 runtime installed, Core's 51 source files compile unchanged into a `net8.0`
  program, with nullable checks and warnings as errors, against Newtonsoft.Json 13.0.1, Core's
  own pinned version.

Also confirmed: the editor's name rule builds one name dictionary per collection, glazing and
gas materials together, so a null or duplicate name throws there; building templates are not
keyed by name, so unique template names are this project's rule, not Basilisk's.

## R16 — Round trips and the audit (US3, SC-003, SC-004, SC-006)

**Decision.**

- **`diff_umi(original, result, *, rel_tol=1e-4)`** compares two UMI libraries field by field
  after resolving references. Components are matched by name and type, schedules by their
  hourly values over the reference year. It returns every difference with its JSON pointer
  and relevance. This is the round-trip report of US3. It is public, and used by the how-to
  guide.
- **`diff_archetypes(a, b, *, rel_tol=0.0)`** compares two SBEM archetypes field by field
  (SC-004).
- **The audit (SC-006)** is a test over the whole UMI test set:
  1. Read the library, then write it back (SC-003).
  2. Translate each archetype in the other direction too.
  3. Diff the results.
  4. Assert that every difference appears in a loss of the matching report, by subject and
     location, and that every loss corresponds to a difference or to a value with no
     counterpart.
  An unreported difference fails the test with its location.
- **SC-003's tolerance**, 0.01 % relative, is the default `rel_tol`. Values with an absolute
  difference below 1e-12 are equal.

**Rationale.** The audit makes "no loss goes unreported" a test, not a promise.

## R17 — Public interface (names for spec 001)

**Decision.** 001 research R14 waits for these names:

```python
from archetypal import read_umi, write_umi
from archetypal.umi import (
    to_umi,
    UmiImport,
    UmiExport,
    TranslationReport,
    Loss,
    LossKind,
    Note,
    diff_umi,
    diff_archetypes,
    CORRESPONDENCE,
)
from archetypal.errors import UmiFormatError, UmiValidationError, LossyTranslationError
```

- `read_umi(path, *, strict=False, skip_invalid_templates=False) -> UmiImport`. Its
  `archetypes` are in template order, with a `report` and `write(directory, overwrite=False)`.
- `write_umi(archetypes, path, *, strict=False, overwrite=False) -> TranslationReport`. It
  writes the library and its loss report and returns the report.
- `to_umi(archetypes, *, strict=False) -> UmiExport` is the same without writing: the library
  text and its report.
- `archetypes` items are `Reduction` (002) or bare SBEM archetypes (R12).

001's `translate` command and `reduce --to umi` call these. `--strict` maps to `strict`.
Status 4 (success with losses) is returned when `losses` is not empty (001 data-model,
ExitStatus).

## R18 — Tests, fixtures and the UMI test set

**Decision.**

- **UMI test set** (spec, Key Entities):
  - B2, ND and UZ, copied into `tests/fixtures/umi/` (UZ extracted from `umi_samples.umi`);
  - one small library per edge case, written by hand: dangling reference, forward reference,
    duplicate names, a perimeter-only template, misaligned year parts, an out-of-range value,
    no templates, unused components, the Archsim dialect, Legacy XML;
  - in the reference tier, the libraries written from 002's 49 reference buildings.
- **Tiers** follow 001's research R3:
  - **Unit** (default, within 120 s): every rule; reading and writing every fixture; the
    audit on the fixtures; determinism (write twice, compare bytes); `basilisk_rules`.
  - **Reference** (`-m reference`): SC-004 and SC-006 on the 49 written libraries.
  - **Basilisk** (CI job, R15): SC-002.
  - **Performance** (in the unit tier): a library of 100 templates built from B2 by renaming,
    read and written in under 5 s (SC-007), with a 3 s internal budget so a slow CI machine
    does not flake.
- **Property tests** (hypothesis):
  - SBEM → UMI → SBEM is the identity on core/perimeter archetypes, apart from reported
    losses;
  - every conversion rule composed with its inverse is the identity within 1e-12 relative.

**Rationale.** The samples are the only real libraries available; the edge-case fixtures make
each spec edge case a test.

## R19 — Tooling additions (roadmap C-19)

**Decision.** The project's tooling is 001's. 003 adds:

- the `basilisk` CI job and `tools/basilisk-check/` (R15);
- a check in `make check` that `tests/data/basilisk_fields.json` matches the pinned Basilisk,
  run only where `dotnet` exists, and always in CI.

No runtime dependency is added: pydantic, numpy, idfkit and epinterface are already
dependencies (002 research R17).

- **idfkit.** `archetypal.umi.windows` imports idfkit (R8), so whoever writes it loads
  `/idfkit:developing-with-idfkit` first. It uses typed constructors only, no
  `get_collection`, and 002's lint ban applies.
- **Documentation.** Every page is written with `/project-kit:diataxis` (plan, Documentation).

## Spec feedback

Points for `/speckit-analyze` (constitution V: the plan satisfies the spec and does not rewrite
it). **All five resolved on 2026-11-22** after the cross-spec analysis: the spec now uses the
suggested wording (FR-002, FR-007, FR-010, US2 scenario 2, the "Schedules" and "UMI library
versions" edge cases, and the assumptions, which list UP-9; roadmap C-20).

- **F-1 — FR-007's reason is wrong about Basilisk.** "Orphaned components (components no
  building template uses), which UMI's library code rejects" is not true: Basilisk rejects
  components that are referenced but missing from their collection, and its own files contain
  unused components (finding 1). The plan keeps the policy, writing no unused component, as a
  project choice (R13). Suggested wording: "The written library MUST contain only components
  that some building template uses, and no reference to a missing component."
- **F-2 — US2 scenario 2 cites issue #459 with an example that cannot occur.** Thickness
  belongs to the layer in UMI and SBEM, so a material used at several thicknesses is not a
  collision (finding 5). Suggested wording: "two different components with the same name (a
  hand-edited library)". FR-003 stands.
- **F-3 — The "unused components" edge case and FR-007 agree only with F-1's wording.**
- **F-4 — "Unsupported versions are refused with a message naming the version."** No UMI
  library has a version (finding 2). Suggested wording: "naming the format".
- **F-5 — SC-003 cannot pass until UP-9's simulation-relevant fields are released.** Until
  then those fields are reported as lost on every read (FR-010), and a read-then-write cannot
  reproduce them. This is consistent with the constitution (a spec is implemented only when its
  upstream changes are released), but the spec should list UP-9 among its assumptions next to
  UP-2. SC-002, SC-005, SC-006, SC-006a and SC-007 can pass without it.
