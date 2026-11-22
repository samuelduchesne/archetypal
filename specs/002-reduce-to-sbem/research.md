# Research: Reduce a detailed EnergyPlus model to an SBEM archetype

**Plan**: [plan.md](plan.md) | **Spec**: [spec.md](spec.md) | **Date**: 2026-11-21

This file settles every open point in the plan's Technical Context. Each entry gives the
decision, why it was chosen and what else was considered. Facts about idfkit and epinterface
come from reading their installed source on 2026-11-21:

- **idfkit 1.3.0rc2**, tag `v1.3.0-rc.2` (repo `github.com/idfkit/idfkit`).
- **epinterface 1.5.0**, the latest release, equal to `main`.

Where a fact was checked by running code, the entry says so.

## Findings that shape the plan

Six facts drive most of the decisions below.

1. **epinterface cannot be installed alongside archetypal 3 today.** It pins
   `archetypal==2.18.10`, and every SBEM component module imports `archetypal.idfclass.IDF` at
   import time (for its `add_to_idf` methods). The fix is UP-1, which the roadmap already lists;
   it must also leave `epinterface.sbem.components` importable without archetypal, eppy or a
   generated Prisma client. Checked by reading `pyproject.toml` and the component modules.
   Upstream is not expected to accept it for a long time, so UP-1, like every epinterface
   item, is released in the SBEM fork (roadmap C-17; R17).
2. **epinterface declares `requires-python = ">=3.10,<3.13"`.** archetypal 3 is therefore
   bounded to 3.10–3.12 (constitution VI, C-07).
3. **epinterface has no archetype file format.** There is no save or load function, no file
   extension and no schema version. The only stores are a Prisma SQLite database, an Excel
   workbook and YAML component maps. Every component is a pydantic v2 model with
   `extra="forbid"`, so `model_dump_json` / `model_validate_json` round-trips losslessly
   (checked on `YearComponent`).
4. **SBEM's schedule model is coarse.**
   - `YearComponent` holds one `WeekComponent` per month.
   - A week holds seven `DayComponent`s, each with 24 hourly values.
   - There are no holiday or design-day slots and no arbitrary date ranges.
   - Infiltration has no schedule at all.
5. **idfkit 1.3.0rc2's `Schedule:Year` evaluation fails on every model loaded from a file.**
   `ValueError: invalid literal for int() with base 10: '1.0'` in `idfkit/schedules/year.py`.
   Reproduced here with a minimal IDF; it passes only for objects built in code with integer
   fields. Schedule evaluation also costs about 55 ms per schedule-year (pure Python, one
   datetime per step).
6. **Neither package reduces a model.** idfkit reads, evaluates, simulates and parses.
   epinterface describes and builds a shoebox. Grouping, aggregation and conservation are all
   archetypal's, which is what spec 002 assigns to it.

## R1 — Where static quantities come from: the EnergyPlus SQLite output

**Decision.** Read every quantity EnergyPlus itself computes from the results' SQLite file,
through `idfkit.simulation.SQLResult` (static tables through the typed wrappers of R18):

| Quantity | SQLite table |
|---|---|
| Zone floor area, volume, `Multiplier`, `ListMultiplier`, part-of-total-area flag | `Zones` |
| Surface class, area, azimuth, tilt, outside boundary condition, zone, construction | `Surfaces` |
| Layer order, thickness, conductivity, density, specific heat | `Constructions`, `ConstructionLayers`, `Materials` |
| Installed internal gains, with design level, schedule and radiant/latent/lost fractions, whatever the input method | `NominalPeople`, `NominalLighting`, `NominalElectricEquipment`, `NominalGasEquipment`, `NominalHotWaterEquipment`, `NominalSteamEquipment`, `NominalOtherEquipment`, `NominalBaseboardHeaters` |
| Design infiltration and simple ventilation | `NominalInfiltration`, `NominalVentilation` |
| Per-surface U-factor with films, SHGC and visible transmittance | tabular *Envelope Summary* (Opaque Exterior, Exterior Fenestration) |

Read the model itself (through idfkit's typed accessors, R18) only for what the SQLite file does not hold:

- schedules and their definitions;
- thermostat controls;
- `WaterUse:Equipment`;
- outdoor-air and heat-recovery equipment;
- `Space`/`SpaceList` space types.

**Rationale.**

- **The figures are exactly what EnergyPlus simulated.**
  - Floor areas follow EnergyPlus's own rules (the spec's edge case asks for "zone floor areas
    as EnergyPlus computed them").
  - Multipliers are already resolved (FR-012).
  - Loads are normalised across every input method (W, W/m², W/person) and every EnergyPlus
    release. idfkit leaves both to the caller: field names change between releases
    (`watts_per_zone_floor_area` became `watts_per_floor_area` in 24.1), and 26.2 adds
    `*:Definition` objects.
  - U-factors include the orientation-dependent films. idfkit's own thermal module uses one
    fixed film pair for every surface.
- **No geometry is reimplemented.** idfkit's zone helpers read only `BuildingSurface:Detailed`
  and ignore multipliers. EnergyPlus's tables cover the simplified surface types and
  F-factor/C-factor ground constructions too.
- **Heat capacity (FR-017) comes straight from `Materials`.** idfkit's thermal module does not
  read density or specific heat at all.
- **Constitution I is respected.** Result parsing is idfkit's; archetypal only queries.

**Alternatives considered.**

- *Compute everything from the model with idfkit geometry and thermal functions.* Rejected:
  - it ignores multipliers;
  - it misses simplified surfaces and orientation-dependent films;
  - it ties archetypal to every release's field names;
  - it rebuilds what EnergyPlus already computed, which breaks the spirit of constitution I.
- *Parse the `.eio` file.* Rejected: a text format with no parser in idfkit; the SQLite tables
  carry the same data.

**To verify during implementation.**

- Ground-contact surfaces appear in *Envelope Summary* with a usable heat-loss figure. If not,
  take the U-value from `Constructions` plus F/C-factor objects and record the rule.
- The `Nominal*` tables are present from 22.1 onwards.

## R2 — Simulation results reduction needs (FR-002)

**Decision.** Reduction needs one annual EnergyPlus run of the detailed model that wrote
`Output:SQLite` with `SimpleAndTabular` and these outputs:

| Output | Frequency | Used by |
|---|---|---|
| Tabular `AllSummary` (Envelope Summary, Annual Building Utility Performance, Input Verification) | — | R1, FR-027 |
| `Zone Air System Sensible Heating Energy`, `Zone Air System Sensible Cooling Energy` (per zone) | Hourly | FR-022 delivered energy, hour by hour for R12's attribution and temperature dependence |
| `Fan Electricity Energy` and `Fan Air Mass Flow Rate` (per fan) | Hourly | FR-022a fan energy and air volume (R19) |
| `System Node Mass Flow Rate` (each zone's air inlet nodes) | Hourly | FR-022a: attributing an air loop's fans to the zones it serves (R19) |
| `Site Outdoor Air Drybulb Temperature` | Hourly | FR-022 temperature dependence (R12) |
| End-use meters by fuel (`Heating:*`, `Cooling:*`, `Fans:Electricity`, `Pumps:Electricity`, `HeatRejection:*`, `WaterSystems:*`) | Hourly | FR-022 consumed energy, FR-027 peaks |
| `Zone Mechanical Ventilation Standard Density Volume Flow Rate` (per zone) | Hourly | FR-019 outdoor-air total and profile |
| `Site Mains Water Temperature` | Hourly | FR-021 |
| `Water Use Equipment Hot Water Volume` (per equipment) | Hourly | FR-021 volume and profile |

The list is a typed constant in the package (`RESULTS_REQUIREMENTS`), so code, error messages
and documentation come from one source. When the user's results lack an item, reduction names
it (FR-029).

If the user asks, and EnergyPlus is installed, archetypal copies the model, adds the missing
output objects and runs it once with `idfkit.simulation.simulate`, using idfkit's
`SimulationCache`. Batches are never run (constitution III).

**Rationale.**

- These quantities depend on how the HVAC actually operated, which only a simulation knows.
- Hourly mechanical outdoor air captures DCV, economiser and minimum-OA logic that would
  otherwise mean re-implementing EnergyPlus controls.
- Run-period totals are enough for seasonal efficiencies.

**Alternatives considered.**

- *Derive outdoor air from `DesignSpecification:OutdoorAir` × occupancy schedules.* Rejected:
  reimplements controller logic and is wrong for VAV minimum OA and DCV.
- *Ask for "Schedule Value" outputs to avoid evaluating schedules.* Rejected as the default
  (R5): it would force a new simulation for almost every existing model. It is kept as the
  fallback if R5's performance budget fails.

## R3 — Supported EnergyPlus versions (FR-029)

**Decision.** Accept models and results from EnergyPlus **22.1 up to the latest version the
installed idfkit bundles** (26.2 at 1.3.0rc2). Refuse anything older with a message pointing
to `idfkit.migration.migrate`, as the spec's edge case asks.

The reference set runs on **EnergyPlus 24.2**, the newest version whose meters epinterface
1.5.0 maps.

**Rationale.**

- epinterface 1.5.0 maps meters for majors 22–24.
- The DOE prototypes are published for current releases.
- The SQLite tables of R1 are stable over this range.
- A narrower range than idfkit's full 8.9–26.2 keeps the test matrix honest.

**Alternative considered.** *Everything idfkit reads (8.9+).* Rejected: untested ranges would
be claimed as supported.

## R4 — Space-use classification (FR-007)

**Decision.**

1. **User mapping.** A `dict[str, str]` from zone name to space-use label, or a callable.
2. **Declared space types.** `Space.space_type` from EnergyPlus 9.6+. A zone takes its spaces'
   type when all agree; mixed spaces fall through to tier 3 and the report says so.
3. **Signature.** For each zone, build a canonical signature of everything that drives its
   loads:
   - each gain type's density (installed total ÷ floor area), rounded to 6 significant figures;
   - each gain's schedule, as a digest of its evaluated hourly values rounded to 6 decimal
     places;
   - the heating and cooling setpoint schedule digests;
   - the outdoor-air rate per area and per person.

   Zones with equal signatures share a space use. The label is the lexicographically smallest
   zone name in the class, prefixed `use:`.

Classification sorts zones by name first and never depends on model order.

**Rationale.**

- Rounding before hashing tolerates the numerical noise the spec mentions while staying
  deterministic and order-free.
- Comparing evaluated values, not schedule names, groups zones whose schedules are copies
  under different names.

**Alternatives considered.**

- *Clustering with a distance threshold (k-means, hierarchical).* Rejected: the result depends
  on parameters and is harder to explain.
- *Zone-name heuristics.* Rejected: brittle and silent.

## R5 — Schedules: evaluation, representative days and output form (FR-015, FR-018, FR-019, FR-021, FR-023)

**Decision.**

- **Evaluation.**
  - Evaluate each distinct schedule once with `idfkit.schedules.values` (hourly), memoised by
    name.
  - Use the calendar of the source run period: the year whose 1 January falls on the
    `RunPeriod` start weekday, with holidays from `RunPeriodControl:SpecialDays`.
  - Hold the results as `numpy` arrays.
- **Aggregation.** A group's conserved hourly profile is
  Σ(member installed total × member schedule) in float64, summed in sorted zone order. Its
  schedule is that profile divided by the group's installed total.
- **Representative days.** Project each 8760 profile onto SBEM's form: for each month and
  weekday, the mean over that month's days of that weekday, holidays included.
  - The projection is linear, so the monthly energy of the source calendar is conserved
    exactly.
  - Merging projected profiles weighted by totals equals projecting the merged profile, so
    FR-010 holds through the archetype alone.
- **Output.**
  - **SBEM:** the archetype carries `YearComponent`s, since SBEM has no `Schedule:Compact`.
  - **`Schedule:Compact` (FR-023):** archetypal also emits each group schedule as text with
    `Through: <month end>` and `For: Monday … Sunday` blocks. Spec 003 (UMI) and the report
    use it, and it is the form idfkit's UP-5 would generate. When SBEM gains holiday and
    design-day slots (UP-2), the projection adds `For: Holiday`, `SummerDesignDay` and
    `WinterDesignDay` without a format change.
  - **Not represented:** holiday distinctions and design-day profiles are listed in the report
    (FR-026) until then. Design days matter little to epinterface, because it conditions with
    ideal loads.
- **Prerequisite.** idfkit's `Schedule:Year` parsing bug must be fixed upstream before
  release (**UP-6**). Until then a temporary bridge normalises the four month and day fields
  to `int` on a copy of the object before evaluation. The bridge is tracked against UP-6 and
  removed when it lands (constitution I).
- **Performance.**
  - At about 55 ms per schedule, a model with 150 distinct schedules spends about 8 s
    evaluating, too close to SC-008's 10 s.
  - Memoisation already counts each schedule once.
  - A benchmark test fails if the largest reference model exceeds 7 s for evaluation.
  - If it does, the upstream route is a faster day-profile evaluation in idfkit (added to
    UP-5's scope). The local fallback is R2's "Schedule Value" outputs.

**Rationale.** It keeps schedule evaluation in idfkit (constitution I), conserves annual
totals exactly and makes merging commute with reducing.

**Alternatives considered.**

- *Peak-normalised "max" schedules (v2's approach).* Rejected: conserves neither total nor
  profile.
- *Keep 8760 arrays in the archetype.* Rejected: SBEM cannot hold them.
- *Evaluate schedules in archetypal.* Rejected: constitution I.

## R6 — Envelope and thermal mass per group (FR-016, FR-017, FR-024)

**Decision.**

- **Classes.** Classify each heat-transfer surface into the spec's classes:
  - exterior wall;
  - roof;
  - exposed floor;
  - ground floor and ground wall;
  - window;
  - interior (partition or interzone).

  The class follows from `ClassName`, tilt and outside boundary condition in the `Surfaces`
  table: wall if 60° ≤ tilt ≤ 120°, roof if tilt < 60°, floor if tilt > 120°.
- **Conserved per class.** Area and UA (Σ net area × U with films) per class, area by
  orientation (eight 45° sectors from azimuth), and for windows Σ A·SHGC and Σ A·VT by
  orientation.
- **SBEM assemblies.** SBEM wants layered assemblies in fixed slots (`Facade`, `FlatRoof`,
  `ExternalFloor`, `GroundSlab`, `GroundWall`, `Partition`, `FloorCeiling`, …). For each class,
  archetypal synthesises an **equivalent three-layer construction**:
  1. split every source construction at its most resistive layer;
  2. inner mass layer = area-weighted heat capacity inside that layer;
  3. insulation = the resistance that reproduces UA ÷ A with epinterface's films;
  4. outer mass layer = capacity outside that layer.

  This conserves UA and heat capacity exactly, keeps where the mass sits, and states the rule.
- **Internal mass.** `InternalMass` surfaces conserve Σ area × capacity through
  `InternalMassAssembly` and `InternalMassExposedAreaPerArea`.
- **Windows.** `GlazingConstructionSimpleComponent(UValue = ΣUA/ΣA, SHGF = ΣA·SHGC/ΣA,
  TVis = ΣA·VT/ΣA)`.
- **Orientation.** Areas and ratios by orientation are the FR-024 geometry characteristics.
  SBEM has one `wwr`, so per-orientation fields are an UP-2 requirement. Until UP-2 lands, the
  archetype carries the overall ratio and the report carries the orientation split as "not
  represented".
- **Storeys** (FR-024). The number of storeys is the conditioned floor area divided by the
  floor area of the lowest level: the conditioned zones whose `Zones.MinimumZ` is within
  0.1 m of the lowest, multipliers applied. The archetype takes the ratio rounded to the
  nearest integer (at least 1); the report keeps the unrounded ratio. Dividing areas, rather
  than counting levels, stays right when one typical floor is drawn with a zone multiplier.
- **Excluded zones.** An excluded zone's envelope (FR-013) is assigned to the conditioned
  zones it shares interzone surfaces with, in proportion to shared area. The report records
  the assignment.

**Rationale.** Conservation is exact by construction, and the rule is explainable on one page
(FR-030).

**Alternatives considered.**

- *Pick the dominant construction.* Rejected: conserves neither UA nor capacity.
- *Average layer by layer.* Rejected: layers do not align between constructions.

## R7 — Exposure (FR-006)

**Decision.** A conditioned zone is *perimeter* if any of its surfaces is a wall
(60°–120° tilt) with outside boundary `Outdoors`, or carries a window. Otherwise it is *core*.

Roofs, exposed floors and ground contact never decide exposure.

Surfaces come from the `Surfaces` table, so simplified geometry is covered.

**Rationale.** It is the spec's definition, applied to EnergyPlus's resolved surfaces.

## R8 — Conditioned or not, attics and basements (FR-013)

**Decision.**

- **Conditioned.** A zone is conditioned if it has a `ZoneControl:Thermostat` with a setpoint
  that enables heating or cooling at any hour of the year, or if equipment delivers heating or
  cooling to it (R2 outputs not zero). That covers zones conditioned only by transfer, such
  as some plenums.
- **Attic.** An unconditioned zone whose surfaces include a roof and a floor adjacent to a
  conditioned zone, and no exterior wall over 50 % of its envelope area.
- **Basement.** An unconditioned zone with ground-contact walls or floor and a ceiling
  adjacent to a conditioned zone.
- **Mapping.**
  - Attics and basements map to SBEM's `AtticAssumptions` / `BasementAssumptions` and the
    attic and basement assemblies.
  - Plenums and crawlspaces are excluded and listed with their floor area.
  - Their envelope follows R6.

**Rationale.** Explicit geometric rules, with every decision visible in the report.

## R9 — Infiltration and mechanical ventilation (FR-018, FR-019)

**Decision.**

- **Infiltration.**
  - Conserve Σ design flow from `NominalInfiltration`, and its hourly profile (design flow ×
    schedule, R5).
  - SBEM's `InfiltrationComponent` has no schedule, so it carries the annual-mean flow as
    `FlowPerExteriorSurfaceArea` (method `Flow/ExteriorArea`) with the flow-weighted mean
    coefficients.
  - The profile, and differences between members' wind and temperature coefficients, go into
    the report as not represented.
  - A schedule field is an UP-2 requirement.
- **Outdoor air.**
  - Conserve Σ hourly outdoor airflow from R2's output.
  - SBEM's `FreshAirPerFloorArea` = peak hourly flow ÷ group area, `FreshAirPerPerson` = 0,
    and the ventilation `Schedule` = hourly flow ÷ peak (R5). Their product reproduces the
    hourly profile.
  - Heat recovery and economiser come from the model's `HeatExchanger:AirToAir:*` objects and
    `Controller:OutdoorAir`, attributed to zones through their air loops.
  - SBEM's `HRV` and `Economizer` are categories, so the group takes the category serving the
    largest share of outdoor airflow. The airflow-weighted effectiveness goes in the report,
    and a numeric effectiveness field is an UP-2 requirement.

**Rationale.** Totals are conserved exactly where SBEM can hold them. Where it cannot, the
loss is named, as FR-026 demands.

## R10 — Thermostats (FR-020)

**Decision.**

- Read `ZoneControl:Thermostat` and its setpoint objects (`ThermostatSetpoint:*`) with idfkit,
  and evaluate them per R5.
- A zone is heated (or cooled) when its setpoint for that mode is within 5–35 °C at some hour;
  setpoints outside that range disable the mode.
- The group setpoint is the floor-area-weighted mean of the heated (cooled) members, hour by
  hour, then projected.
- The report records the share of floor area not heated or not cooled.

**Rationale.** It is the spec's rule. The 5–35 °C band reflects how EnergyPlus models disable
a mode in practice (for example a −100 °C heating setpoint), and is stated in the report.

## R11 — Domestic hot water (FR-021)

**Decision.**

- **Totals.** For each `WaterUse:Equipment`, take the hot-water volume from R2's hourly output
  and the target temperature from its schedule. Mains temperature comes from R2.
- **Zone attribution.**
  - Equipment with a zone is that zone's.
  - Equipment without one is allocated to zones in proportion to their occupant-hours (the use
    that drives DHW in the prototypes).
  - The report states the rule and the result.
- **SBEM fields.**
  - SBEM's `WaterUseComponent.FlowRatePerPerson` = annual volume ÷ (group occupant-days) and
    `Schedule` = the volume profile (R5).
  - `DHWComponent.WaterSupplyTemperature` = annual-mean mains + volume-weighted mean
    temperature rise.
  - `WaterTemperatureInlet` = annual-mean mains.
  - System and distribution COP come from R12.

**Rationale.** Volume and heating energy are conserved. Occupancy-driven allocation fixes the
v2 defect behind #390, where building-level DHW was multiplied into every zone.

## R12 — Conditioning efficiency (FR-022)

**Decision.**

- **Inputs.** Delivered heating and cooling per zone come from R2's hourly outputs. Consumed
  energy by fuel and mode comes from the hourly end-use meters.
- **Attribution.** Each hour's consumed energy is attributed to zones in proportion to that
  hour's delivered energy in the same mode (heating-mode meters to heating delivery, cooling
  to cooling). Hours with consumption but no delivery (standby, pilot lights) are summed and
  reported, not attributed.
- **Fans** are not folded: they are their own quantity, specific fan power (R19, FR-022a).
- **Pumps and heat rejection.**
  - These support conditioning but SBEM has no end use for them.
  - Each hour's energy is split between heating and cooling by the hour's delivered modes and
    folded into that mode's `DistributionCOP`.
  - SC-002 compares them the same way: added to the heating and cooling end uses they serve.
- **Group efficiency.**
  - Delivered ÷ consumed, by mode.
  - `SystemCOP` comes from the primary meters and `DistributionCOP` from the folded parts.
  - `Fuel` is the mode's dominant fuel by consumed energy; other fuels' shares go in the report.
- **Dependence on outdoor temperature** (FR-022, with UP-8).
  - The model is linear in the energy input ratio, the inverse of COP:
    `consumed_h = (a + b·(T_h − T_ref))·delivered_h`, with `T_h` the hour's outdoor dry-bulb
    temperature and `T_ref` a fixed reference (the group's delivered-weighted mean outdoor
    temperature in that mode).
  - `a` and `b` are fitted by least squares under the constraint that the annual consumed
    energy is reproduced exactly. `SystemCOP` is then `1/a` at `T_ref`, and `b` becomes the
    UP-8 slope.
  - The fit needs only additive sums (Σd, Σd·T, Σd², Σd²·T, Σd²·T², Σc, Σc·d, Σc·d·T), which
    the ledger carries, so merging refits exactly.
  - Equipment whose efficiency does not depend on temperature (boilers, resistance) gives
    `b ≈ 0`, and a constant COP, as today.
  - Until UP-8 is released, only `SystemCOP` is written and the slope is reported as not
    represented (FR-026).
- **Merging.** The report carries each group's delivered and consumed energy by fuel, so
  merging recomputes efficiencies exactly (FR-010).
- **No delivery.** A group with no delivery in a mode takes the efficiency of the equipment
  serving it. That is the rated COP or efficiency of the air loop's or zone equipment's
  coil, from the tabular *Equipment Summary*.

**Rationale.** Energy is conserved by fuel, which is what FR-022 states, and every fold is
named. A constant seasonal COP is exact on the year but misplaces consumption in time: a heat
pump's consumption is highest in the coldest hours, which is also where peak demand (SC-003)
is measured. The linear energy input ratio is the simplest form that captures this, and the
constraint keeps the annual total exact.

**Alternatives considered.** EnergyPlus performance curves (biquadratic in temperatures, plus
part load): more faithful, but they need the real system's sizing, which ideal loads do not
have. That belongs to the possible future spec on HVAC templates (roadmap 009).

## R19 — Fan energy (FR-022a)

Numbered after R18 so earlier references stay valid; it extends R12.

**Decision.**

- **What the archetype carries** (UP-8):
  - `SpecificFanPower`, the fan energy per volume of air moved, in W/(m³/s);
  - the ideal loads' maximum heating and minimum cooling supply-air temperatures.

  epinterface then reports a fan end use equal to `SpecificFanPower` × the ideal loads' hourly
  supply air volume.
- **Attribution in the detailed model.**
  - A zone equipment fan (unit heater, fan coil, PTAC) belongs to its zone.
  - An air loop's fan energy and air volume go to the zones the loop serves, in proportion to
    each hour's mass flow through each zone's air inlet nodes.
  - Air volume is the fan's mass flow divided by standard air density, matching the ideal
    loads' standard-density volume.
- **Group value.** `SpecificFanPower = Σ fan energy ÷ Σ air volume` over the group's zones.
  Both sums are in the ledger, so merging is exact and `SpecificFanPower × detailed volume`
  reproduces the detailed fan energy exactly (SC-005).
- **Air volume in the archetype.**
  - Ideal loads without flow limits supply air at their supply-temperature limit and vary the
    flow, and never less than the outdoor air.
  - Reduction sets each limit from the detailed model's effective supply temperature
    difference in that mode: `ΔT = Σ delivered ÷ (ρ·c_p·Σ volume in that mode's hours)`,
    added to the heating setpoint (subtracted from the cooling setpoint).
  - With the same delivered energy, the archetype then moves the same air volume, so it
    reproduces the fan energy.
- **What is still lost.** Air moved when there is neither a load nor outdoor-air demand (a
  constant-volume fan recirculating) has no counterpart in ideal loads. The report gives the
  share of detailed air volume in such hours, and the comparison gives the volume ratio, so a
  fan end-use difference can be traced to it.
- **Before UP-8.** The fan energy is folded into `DistributionCOP` as before, and the fan end
  use is listed as not represented (FR-026). SC-002 cannot be met for fans until UP-8 is
  released.

**Rationale.** Specific fan power is the standard, physically meaningful descriptor of fan
energy. Tying the archetype's air volume to delivered energy, through supply temperatures
taken from the detailed model, makes it reproduce fan energy without modelling the air system
itself.

**Alternatives considered.**
- Fan energy per unit of delivered heating and cooling: exact on the year, but it misses fan
  energy in ventilation-only hours and has no physical meaning a modeller can check.
- Fan power per floor area on an operating schedule: simple, but wrong for variable-volume
  systems, whose power follows the load.
- Real fan objects in the archetype: needs air systems, which is roadmap 009.

## R13 — Comparison (FR-027, FR-028)

**Decision.**

- **End uses.** Compare from each run's SQLite file: the tabular *Annual Building Utility
  Performance Summary* End Uses table, by fuel. For the archetype, fans come from epinterface's
  fan end use (R19). On the detailed side, pumps and heat rejection are added to heating and
  cooling, split by each hour's delivered modes as in R12, before comparing (SC-002).
- **Peak demand.** Peak heating and cooling demand is the maximum, over the run period, of the
  summed heating (and cooling) end-use meters at the common reporting frequency.
- **Refusal.** Refuse when any of these differ:
  - weather file (location and data source from the `Simulations` and `EnvironmentPeriods`
    tables, plus an EPW SHA-256 when the user passes the file);
  - run-period dates;
  - unit system;
  - timestep;
  - meter reporting frequency.

**Rationale.** Uses only parsed results (idfkit) and EnergyPlus's own end-use categories.

## R14 — Archetype and report files

**Decision.**

- **Archetype file.** The archetype is written as epinterface's pydantic JSON
  (`model_dump_json`, indented, keys in model order) of the UP-2 multi-group archetype object.
  The file is `<name>.sbem.json`, readable by the SBEM fork alone, and by upstream epinterface
  only if it uses no field the fork adds (the file records the fork's schema version). This is what spec 001's
  clarification calls "epinterface's own serialisation".
- **Report file.** The report is a separate JSON file, `<name>.report.json`, validated by a
  published JSON Schema generated from archetypal's pydantic models. It carries:
  - `schema_version`;
  - archetypal, epinterface, idfkit and EnergyPlus versions;
  - SHA-256 of the model, results and weather files;
  - the options chosen.
- **Determinism.** Floats are written with `repr` precision, collections in sorted order, and
  there is no timestamp. Two runs give byte-identical files (FR-005).
- **Upstream.** Asking epinterface for official `save`/`load` helpers with a schema version is
  part of UP-2's scope; archetypal switches to them when they exist.

**Rationale.** No format is invented for the archetype, and provenance lives in archetypal's
report.

**Alternative considered.** *Wrap the archetype in an archetypal envelope.* Rejected: the file
would no longer be plain SBEM that epinterface can read without archetypal.

## R15 — Project structure, tooling and lint rules

**Decision.** Adopt the **project-kit-cookiecutter** Python template (commit `73646700cea8`),
linked with cruft. These are the template answers:

| Question | Answer | Why |
|---|---|---|
| `layout` | `src` | Published package; tests run against the installed package. |
| `minimum_python_version` | `3.10` | Constitution VI. |
| `development_python_version` | `3.12` | Highest version epinterface allows. |
| `type_checker` | `pyright` (strict) | Constitution VI; idfkit is pyright-strict clean. |
| `include_py_typed`, `include_github_actions`, `codecov`, `deptry`, `changelog`, `mkdocs` | yes | Typed public library, CI, dependency hygiene, Keep a Changelog, Diátaxis docs site. |
| `publish_to_pypi` | yes | v3 ships to PyPI once upstream epinterface has released what it uses (roadmap UP-3, C-18). The publish workflow stays in place, unused; until then each milestone is a git tag (`v3.0.0aN`). |
| `dockerfile`, `devcontainer`, `dvc` | no | Library, no deployment; no large data tracked in git. |
| `agent_instructions` / `agent_profile` | `claude` / `full` | Matches how the project is developed. |
| `open_source_license` | MIT | Unchanged from v2. |

These edits follow generation and are visible in the cruft diff:

- `requires-python = ">=3.10,<3.13"` and classifiers trimmed to 3.10–3.12;
- the tox `envlist` and CI matrix trimmed to 3.10–3.12;
- added test markers and the time budget (R16);
- added ruff rules (below).

**Ruff.** The template's rule set is kept as is: YTT, S, DTZ, LOG, PIE, PT, RET, TC, PTH, B, A,
C4, T10, SIM, I, C90, E, W, F, PGH, UP, RUF, TRY, PERF, FURB. Line length is 120, with preview
formatting and `future-annotations`. Added:

- **`D` with `convention = "google"`:** every public object documented (constitution VI). Off
  in `tests/`.
- **`NPY`:** numpy-specific correctness.
- **`PL` (pylint) with `max-args = 8`:** keeps function signatures in check on a domain with
  many parameters.

**Rationale.** It is the standard the user asked for. The additions serve constitution VI and
the numerical core.

**Where v3 lives.** The v2 tree (flat `archetypal/`, poetry, vendored `geomeppy`) and v3's
`src/archetypal/` cannot share a branch. v3 is developed on a `v3` integration branch cut from
`main`. Its first commit applies the template and removes the v2 tree, which stays on `v2.x`
(spec 001, FR-020). Whichever of 001 and 002 is implemented first performs this step; the other
reuses it.

## R16 — Tests and the two-minute rule

**Decision.** There are three tiers, selected by pytest markers registered in `pyproject.toml`
(pytest `strict = true` rejects unknown markers).

| Tier | Marker | Needs | Runs | Budget |
|---|---|---|---|---|
| Unit | none (default) | Python only: small IDF fixtures and recorded SQLite results committed under `tests/fixtures/` | every push, all Python versions | **≤ 120 s wall-clock for the whole tier**; ≤ 5 s per test |
| Integration | `energyplus` | EnergyPlus 24.2 | every PR, one Python version | ≤ 10 min |
| Reference | `reference` | EnergyPlus 24.2, DOE prototypes, v2 in a separate env | weekly, manual dispatch, and before a release | none (SC-001–SC-008 evidence) |

The 120 s budget is enforced, not just hoped for:

- `pytest-timeout` sets 5 s per unit test.
- A `conftest.py` hook (`pytest_sessionfinish`) fails the session when the default selection
  exceeds 120 s.
- `--durations=15` is always reported, so the slowest tests are visible in CI.

These keep the unit tier fast:

- Fixtures are tiny: a three-zone and a ten-zone model with zone multipliers, a plenum and DHW.
  Their SQLite results are cut down to the R2 outputs, a few MB each. They are regenerated by
  `tests/fixtures/regenerate.py` (EnergyPlus needed) and committed.
- Property-based tests (`hypothesis`) cover order invariance (FR-007), merging equal to direct
  reduction (FR-010) and conservation (SC-005) on synthetic zone ledgers with no I/O. They use
  a `ci` profile capped at 50 examples and a 500 ms deadline.
- No unit test runs EnergyPlus, downloads anything or evaluates a full-size model.

**Rationale.** It meets the user's general rule, keeps physics checks fast enough to run on
every push, and reserves the slow evidence for its own workflow.

## R17 — Dependencies (constitution III)

| Dependency | Range | Justification |
|---|---|---|
| `epinterface`, resolved to the maintained fork | declared `>=X,<Y` (X = first version with UP-1 and UP-2; Y = next upstream minor); `[tool.uv.sources]` pins a fork git tag | SBEM data model, the only archetype model (C-02), from the maintained fork (roadmap C-17). |
| `idfkit` | `>=1.3,<2` (`>=1.3.0rc2` until 1.3.0 is final) | Model reading, schedules, SQLite results, simulation. Zero runtime dependencies. |
| `numpy` | `>=1.26` | 8760-hour profiles and float64 sums. Already pulled in by epinterface's pandas, but used directly, so declared (deptry). |
| `pydantic` | `>=2.9,<3` | Report models and JSON Schema. Already required by epinterface, but used directly, so declared. |

Development group: `pytest`, `pytest-timeout`, `pytest-cov`, `hypothesis`, `pyright`, `ruff`,
`deptry`, `pre-commit`, `tox-uv`, `mkdocs-material`, `mkdocstrings[python]`.

No pandas import in archetypal. The command line (`click` or similar) is spec 001's decision.

**Compatibility.** idfkit has no dependencies, so it cannot conflict. epinterface 1.5.0's exact
pins (`click==8.1.7`, `pandas<2.3`, `packaging<25` via archetypal 2.18.10) and undeclared
`PyYAML` must be loosened or fixed. Those changes are folded into UP-1 and UP-4 (see the
upstream table in plan.md), released in the fork.

**Why a fork.** Upstream epinterface is not expected to accept our pull requests for a long
time, and its releases pin `archetypal==2.18.10`, so archetypal 3 cannot depend on them in
the same environment. The fork keeps the distribution and import names and is installed through a uv
git source, so archetypal's code and declared dependency are the same whichever provides
`epinterface`; switching back when upstream catches up deletes one `[tool.uv.sources]`
entry. The fork is not published on PyPI, so archetypal 3 cannot be published there before
upstream releases these changes (roadmap UP-3). The alternative, carrying the SBEM extensions inside archetypal,
was rejected (roadmap C-17).

## R18 — idfkit's typed interface first

**Decision.** archetypal reads models only through idfkit's statically typed interface.

1. **Typing the document.** The loaded document is narrowed once, in `sources.py`, with
   `idfkit.versioned.as_version(doc, since="22.1")`. Its type is then `IDFDocumentSince22_1`,
   the union of the release document types R3 supports. The range follows idfkit as it adds
   releases, with no list to maintain.
2. **Reading objects.** Objects are read through the typed accessors:
   - snake_case properties where idfkit has them (`doc.zones`, `doc.spaces`,
     `doc.run_periods`, `doc.schedule_compacts`, `doc.schedule_years`,
     `doc.zone_control_thermostats`, `doc.water_use_equipments`);
   - otherwise a **literal** key (`doc["ThermostatSetpoint:DualSetpoint"]`,
     `doc["Controller:OutdoorAir"]`), which is overloaded and returns a typed collection.

   Fields are typed attributes: `Space.space_type: str | None`,
   `RunPeriod.day_of_week_for_start_day: Literal[...] | None`,
   `ZoneControlThermostat.control_1_object_type: Literal[...]`, and so on. Extensible fields
   are typed groups, for example `ScheduleYear.schedule_weeks[i].start_month: int`.
3. **Forbidden in `src/`:**
   - `get_collection`;
   - indexing with a non-literal string;
   - `collections` and `objects_by_type`;
   - `get_referenced_object`, `schedules_dict` and `get_zone_surfaces` (each returns untyped
     `IDFObject`s);
   - `getattr` on idfkit objects.
4. **Following references** (a thermostat's setpoint object, a schedule name of unknown type):
   look the name up in typed collections.
   - `_schedules.py` builds one typed index
     `dict[str, AnySchedule]` from the per-type accessors, where
     `AnySchedule = ScheduleCompact | ScheduleYear | ScheduleConstant | ScheduleFile | …`.
   - Thermostats dispatch on `control_n_object_type`, a `Literal`, with `match`, so pyright
     checks every case.
5. **Fields that differ between releases.** Narrow with `as_version(doc, (IDFDocumentV22_1,
   …))` or `as_version(doc, since=...)` around the read, never `isinstance`. A probe under
   pyright strict (1.1.408) confirmed that `Lights.watts_per_floor_area` is a type error on the
   22.1+ union, as it should be. Loads come from the SQLite tables anyway (R1), so reduction
   needs no such narrowing today.
6. **Enforcement.** Three checks run in `make check` and pre-commit:
   - **`idfkit check`**, configured in `[tool.idfkit.check]` with `since = "22.1"` and
     `extend-select = ["C004"]`. It reports object types or choice values that differ between
     releases (C001, C002), any literal `get_collection` (C003, C004) and `add()` types no
     target accepts (C006).
   - **pyright strict**, with `reportUnknownMemberType` and `reportUnknownVariableType` as
     errors. An untyped `IDFObject` leaking in fails the build.
   - **A `pygrep` pre-commit hook** banning the names listed in item 3 under `src/`.

**Where idfkit is not yet typed, archetypal wraps it in one place and asks upstream.**

| idfkit API | Returns | archetypal's bridge | Upstream |
|---|---|---|---|
| `SQLResult.query(sql)` (EnergyPlus static tables: `Zones`, `Surfaces`, `Constructions`, `ConstructionLayers`, `Materials`, `Nominal*`) | `list[tuple[object, ...]]` | `_sql_tables.py`: one frozen dataclass per table (`ZoneRow`, `SurfaceRow`, `NominalLoadRow`, …), converted and checked at the boundary. No other module calls `query`. | **UP-7**: typed readers for these tables in idfkit. archetypal switches to them and deletes `_sql_tables.py`. |
| `idfkit.schedules.values(schedule: IDFObject, …)` | `list[float]` | None needed: typed schedule objects are `IDFObject`s. | UP-5 (faster day profiles) |
| `ScheduleYear.schedule_weeks[i].start_month`, typed `int` | `'1.0'` at run time in 1.3.0rc2 | `_bridges.py` (UP-6) | **UP-6**: also makes the typed field honour its declared type. |

**Rationale.**

- The user asked for idfkit's strongly typed interface wherever possible.
- With the typed interface, pyright catches misspelt object types, fields missing from a
  release and unhandled choice values when the code is written, not when a user's model fails.
- Concentrating the untyped boundary in `_sql_tables.py` and `_bridges.py` keeps the rest of
  the package strict, and each bridge has a named upstream exit (constitution I).

**Alternatives considered.**

- *`get_collection` with string names from a table.* Rejected: untyped, and the user ruled it
  out.
- *`load_idf(..., as_type=IDFDocumentV24_2)`.* Rejected: types one release and refuses the
  rest of R3's range.
- *Read loads from the typed model instead of SQLite.* Rejected: R1's reasons still hold
  (multipliers, input-method normalisation, renames across releases). The typed SQLite
  readers of UP-7 give both properties.

## R20 — Features SBEM cannot express (FR-026)

Numbered after R19 so earlier references stay valid.

**Decision.**

- archetypal keeps an explicit table, `UNSUPPORTED_FEATURES`, of EnergyPlus object types with
  an effect SBEM cannot hold, each with the parameter its effect is folded into, or none. It
  starts with:
  - daylighting (`Daylighting:Controls`, `Daylighting:ReferencePoint`);
  - window shading (`WindowShadingControl`, `WindowMaterial:Shade`, `WindowMaterial:Blind`);
  - exterior shading (`Shading:*`);
  - gains with no SBEM counterpart (`ElectricEquipment:ITE:AirCooled`,
    `SwimmingPool:Indoor`, `Refrigeration:*`);
  - exterior lights and equipment (`Exterior:Lights`, `Exterior:FuelEquipment`);
  - earth tubes, cooling towers serving process loads and `ZoneAirMassFlowConservation`.
- Each entry is read with a literal key through idfkit's typed interface (R18). Any object
  found is listed in `not_represented[]` with the zones it affects and, where results give
  it, its annual energy.
- Features already handled elsewhere (fans before UP-8, orientation, infiltration schedule,
  heat-recovery effectiveness, holidays) are recorded by the module that folds them.
- The table is extended whenever a reference building shows an unlisted feature; the
  reference tier fails when a building's site energy has an end use the archetype cannot
  produce and no entry explains it.

**Rationale.** FR-026 forbids silent drops. A table keeps every decision visible and testable,
and reading each type by literal key respects R18.

**Alternatives considered.** *List every object type in the model and subtract what reduction
reads.* Rejected: it needs `objects_by_type` or `collections`, which R18 bans, and would flag
hundreds of irrelevant types (output requests, simulation controls).

## Spec feedback

Points raised for `/speckit-analyze` (constitution V: the plan satisfies the spec, it does
not rewrite it):

- ~~**F-1 — SC-002 and end uses SBEM cannot produce.**~~ **Resolved (2026-11-21).**
  epinterface conditions with ideal loads, so an archetype reported no fan, pump or
  heat-rejection end use, and fans failed SC-002 by construction. Now:
  - FR-022a and R19 give SBEM a fan end use through specific fan power (UP-8);
  - SC-002 adds pumps and heat rejection to the heating and cooling they serve;
  - FR-022 and R12 add the dependence of efficiency on outdoor temperature (UP-8).
- ~~**F-2 — FR-023 says schedules are "expressed as `Schedule:Compact`", but SBEM stores
  `YearComponent`s.**~~ **Resolved (2026-11-22, `/speckit-analyze`).** FR-023 now asks for a
  form that converts without loss to `Schedule:Compact`, conserves monthly energy (what R5's
  projection guarantees) and lists the day types the archetype cannot hold until UP-2.
