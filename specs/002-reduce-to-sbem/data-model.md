# Data model: Reduce a detailed EnergyPlus model to an SBEM archetype

**Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

These are the entities reduction works with, in pipeline order. Field types are Python types.
Units are SI throughout:

- areas in m²;
- power in W;
- energy in J (EnergyPlus's unit, so no conversion error);
- airflow in m³/s;
- U in W/m²K, heat capacity in J/K.

`Profile` is a float64 numpy array with one value per hour of the source run period (8760, or
8784 in a leap year).

## Pipeline and states

```text
SourceData ──inventory──▶ ZoneRecord[] ──classify──▶ ClassifiedZone[]
   │                                                    │
   │ (refuse: FR-029)                         group (layout, threshold)
   ▼                                                    ▼
ReductionError                              GroupLedger[] ──to_sbem──▶ Archetype (epinterface)
                                                 │
                                                 └──────────────────▶ ReductionReport
merge(Archetype, ReductionReport, layout) ─▶ regroup the report's pre-threshold ledgers ─▶ same path
```

A reduction either finishes all stages or raises a `ReductionError` before writing anything.
No partial archetype is ever produced (FR-029).

## SourceData

The inputs, checked.

| Field | Type | Notes |
|---|---|---|
| `model` | idfkit `AnyIDFDocument` | Loaded with `idfkit.load_idf`/`load_epjson`. |
| `results` | idfkit `SQLResult` | From the SQLite file of the detailed run. |
| `energyplus_version` | `tuple[int, int, int]` | From the model's `Version` and the results' `Simulations` table; the two must agree. |
| `run_period` | `RunPeriodInfo` | Start and end dates, start weekday, calendar year chosen per R5, holidays. |
| `model_sha256`, `results_sha256`, `weather_sha256` | `str`, `str`, `str \| None` | For the report's reproducibility block. |

**Validation, before any other work** (each raises a `ReductionError` subclass):

- the version is within 22.1 up to idfkit's latest (R3);
- every item in `RESULTS_REQUIREMENTS` is present (`MissingResults` names each missing item and
  how to obtain it);
- the model's zone names equal the results' `Zones` names (`ModelResultsMismatch` names the
  difference);
- at least one zone is conditioned (`NoConditionedZones`).

## ZoneRecord

One per EnergyPlus zone, as EnergyPlus counts it.

| Field | Type | Source |
|---|---|---|
| `name` | `str` | `Zones.ZoneName` |
| `multiplier` | `int` | `Zones.Multiplier × Zones.ListMultiplier` (FR-012) |
| `floor_area` | `float` | `Zones.FloorArea` (one copy) |
| `volume` | `float` | `Zones.Volume` |
| `surfaces` | `tuple[SurfaceRecord, ...]` | `Surfaces` table, with envelope figures from tabular Envelope Summary |
| `gains` | `tuple[GainRecord, ...]` | `Nominal*` tables |
| `infiltration` | `tuple[AirflowRecord, ...]` | `NominalInfiltration` |
| `outdoor_air` | `Profile` | R2 hourly output |
| `thermostat` | `ThermostatRecord \| None` | Model (R10) |
| `hot_water` | `tuple[HotWaterRecord, ...]` | Model and R2 outputs, after R11 allocation |
| `delivered` | `dict[Mode, float]` | R2 run-period outputs |
| `space_type` | `str \| None` | `Space.space_type` when all of the zone's spaces agree |

Supporting records:

- **`SurfaceRecord`**: name, class (R6), net area, azimuth, tilt, boundary, U with films,
  heat capacity (Σ ρ·c·d of its layers); for windows also SHGC and VT.
- **`GainRecord`**: kind (`people`, `lights`, `electric`, `gas`, `hot_water_equipment`,
  `steam`, `other`, `baseboard`), design level (W, or people for occupancy), schedule name, and
  radiant, latent and lost fractions.
- **`AirflowRecord`**: design flow, schedule name, and the four coefficients.
- **`ThermostatRecord`**: heating and cooling setpoint schedule names.
- **`HotWaterRecord`**: volume `Profile`, target-temperature schedule name, allocation share.

**Invariant.** Every total a zone contributes is multiplied by `multiplier` exactly once, at
ledger creation (`GroupLedger.from_zone`). Nothing upstream of that applies a multiplier.

## ClassifiedZone

| Field | Type | Rule |
|---|---|---|
| `zone` | `ZoneRecord` | |
| `conditioned` | `bool` | R8 |
| `role` | `Literal["conditioned", "attic", "basement", "excluded"]` | R8 |
| `exposure` | `Literal["perimeter", "core"]` | R7 (conditioned zones only) |
| `space_use` | `str` | R4 |
| `space_use_source` | `Literal["user", "space_type", "signature"]` | FR-007 report requirement |

## Layout and ReductionOptions

- **`Layout`** is a `StrEnum`. Each member gives a group key:

  | Member | Group key |
  |---|---|
  | `SPACE_USE_EXPOSURE` (default) | (space use, exposure) |
  | `SPACE_USE` | space use |
  | `CORE_PERIMETER` | exposure |
  | `SINGLE_ZONE` | one key |

  Layouts form a partial order by coarseness. `merge` refuses a target that is not coarser
  than or equal to the source layout.
- **`ReductionOptions`** is a frozen pydantic model with these fields:
  - `layout: Layout = Layout.SPACE_USE_EXPOSURE`;
  - `small_group_threshold: float = 0.05`, a share of conditioned floor area in [0, 1);
  - `space_use_mapping: Mapping[str, str] | None = None`.

## GroupLedger: the conserved totals

The ledger is the heart of reduction. Its fields are **sums**, never averages, so merging two
ledgers is field-wise addition. That is associative and commutative, which makes FR-010 and
SC-007 hold by construction.

| Field | Type | Conserves (FR) |
|---|---|---|
| `members` | `tuple[str, ...]` (sorted) | FR-025 provenance |
| `floor_area` | `float` | FR-014 |
| `envelope` | `dict[EnvelopeClass, EnvelopeTotals]` | FR-016, FR-017 |
| `window_by_orientation` | `dict[Orientation, WindowTotals]` | FR-016, FR-024 |
| `internal_mass_capacity` | `float` | FR-017 |
| `gains` | `dict[GainKind, GainTotals]` | FR-015 |
| `infiltration` | `AirflowTotals` | FR-018 |
| `outdoor_air` | `AirflowTotals` + `hrv_weighted`, `economiser_weighted` | FR-019 |
| `heating_setpoint`, `cooling_setpoint` | `WeightedProfile` | FR-020 (area-weighted, heated/cooled members only) |
| `unheated_area`, `uncooled_area` | `float` | FR-020 report |
| `hot_water` | `HotWaterTotals` | FR-021 |
| `energy` | `dict[Mode, EnergyTotals]` | FR-022 |
| `excluded_envelope` | `tuple[EnvelopeAssignment, ...]` | FR-013 |

The total types:

- **`EnvelopeTotals`**: `area`, `ua` (Σ A·U), `capacity_inner`, `capacity_outer`, and
  `area_by_orientation: dict[Orientation, float]`.
- **`WindowTotals`**: `area`, `ua`, `a_shgc` (Σ A·SHGC), `a_vt` (Σ A·VT).
- **`GainTotals`**:
  - `installed` (W or people);
  - `hourly: Profile`, which is installed × schedule, summed;
  - `radiant`, `latent`, `lost`: annual energy of each part (FR-015).
- **`AirflowTotals`**: `design_flow` and `hourly: Profile`; infiltration also carries the four
  flow-weighted coefficient sums.
- **`WeightedProfile`**: `weight` (Σ area) and `weighted: Profile` (Σ area × setpoint). The
  value is `weighted / weight`.
- **`HotWaterTotals`**: `volume: Profile` and `heat: Profile` (Σ volume × temperature rise),
  from which the mean rise follows.
- **`EnergyTotals`**: `delivered` and `consumed_by_fuel: dict[Fuel, float]`, plus
  `distribution_by_fuel` (fans, pumps and heat rejection folded per R12), `unattributed`
  (FR-022 standby) and `rated_efficiency: float | None` (used only when `delivered == 0`).

**Operations.**

- `GroupLedger.from_zone(ClassifiedZone, schedules)` builds a ledger, applying the zone's
  multiplier.
- `a + b` merges two ledgers. Members are unioned; every total is added.

## Grouping and thresholding (FR-008–FR-011)

1. Build one ledger per conditioned zone, then sum ledgers by the layout's group key. Keys are
   sorted, so the order is deterministic.
2. **Pre-threshold groups** are kept for the report (FR-011).
3. **Threshold.** While any group's floor-area share is below the threshold and another
   eligible group exists (same exposure where the layout has exposure), merge the smallest
   group into its **most similar** eligible group.
   - *Similarity* is the Euclidean distance between the groups' intensity vectors, each
     component scaled by the building-wide value:
     - gain densities;
     - annual gain hours;
     - setpoint means;
     - outdoor air per area;
     - hot water per area.
   - Ties are broken by group key.
   - Each merge is recorded.
4. **Merging an archetype.** `merge` starts from the report's pre-threshold ledgers for the
   source layout, regroups them by the target key, and applies step 3 once.

## Derivation rules: ledger → SBEM (FR-025)

Each SBEM parameter is produced by exactly one named rule. The report records the rule's
identifier for every parameter.

| SBEM field | Rule id | Formula |
|---|---|---|
| Group floor-area share | `area.share` | `floor_area / Σ floor_area` |
| `OccupancyComponent.PeopleDensity` | `gain.density` | `gains[people].installed / floor_area` |
| `Lighting/EquipmentComponent.PowerDensity` | `gain.density` | `installed / floor_area`. Equipment sums electric, gas, steam, hot-water and other gains; per-kind fuel goes in the report. |
| Each gain's `Schedule` | `schedule.normalised` | `project(hourly / installed)` (R5) |
| `ThermostatComponent.Heating/CoolingSchedule` | `setpoint.area_mean` | `project(weighted / weight)` |
| Assemblies (`Facade`, `FlatRoof`, `ExternalFloor`, `GroundSlab`, `GroundWall`) | `envelope.equivalent` | Three-layer construction with `U = ua / area` and capacities (R6) |
| `Partition`, `FloorCeiling` | `envelope.equivalent` | Same rule on interior classes |
| `InternalMassAssembly`, `InternalMassExposedAreaPerArea` | `mass.internal` | R6 |
| `Window` (U, SHGF, TVis) | `window.area_weighted` | `ua/area`, `a_shgc/area`, `a_vt/area` |
| `InfiltrationComponent` | `airflow.mean_per_exterior_area` | Annual-mean flow ÷ exterior area; flow-weighted coefficients |
| `VentilationComponent.FreshAirPerFloorArea`, `Schedule` | `airflow.peak_per_area` | Peak hourly flow ÷ area; `project(hourly / peak)`. Peak × fraction schedule reproduces the hourly profile, so the total is conserved. |
| `HRV`, `Economizer` | `airflow.dominant_category` | Category with the largest airflow share |
| `WaterUseComponent.FlowRatePerPerson`, `Schedule` | `dhw.volume_per_person` | Annual volume ÷ occupant-days; `project(volume profile)` |
| `DHWComponent` temperatures | `dhw.mains_plus_rise` | Mean mains + `heat / volume` |
| `ThermalSystemComponent` (`Fuel`, `SystemCOP`, `DistributionCOP`) | `efficiency.delivered_over_consumed` | R12; or `efficiency.rated` when delivered is 0 |
| Attic and basement assumptions | `zone.attic`, `zone.basement` | R8 |

**Validation.** The result must validate as epinterface's archetype model (FR-003). A
validation failure is a bug, raised as `ReductionError` with epinterface's message. It is never
silenced.

## ReductionReport

A pydantic model whose JSON Schema is published (contract:
[contracts/reduction-report.md](contracts/reduction-report.md)).

| Field | Content |
|---|---|
| `schema_version` | `"1.0"` |
| `reproducibility` | archetypal, epinterface, idfkit and EnergyPlus versions; SHA-256 of model, results and weather; `ReductionOptions` |
| `groups[]` | key, members (with multipliers), floor area and share, space-use sources, the group's ledger totals |
| `pre_threshold_groups[]` | ledgers before thresholding (FR-011; input to `merge`) |
| `parameters[]` | (group, SBEM field path, value, rule id) for every parameter |
| `excluded_zones[]` | name, floor area, role, reason, envelope assignment |
| `small_group_merges[]` | merged key, into key, share, distance |
| `not_represented[]` | feature, affected groups, magnitude, the parameter it was folded into (or none) |
| `merged_distinctions[]` | for a coarser layout: the space-use or exposure distinctions lost (US2) |
| `unattributed_energy` | standby and pilot consumption by fuel (FR-022) |

## ComparisonResult (FR-027, FR-028)

| Field | Type |
|---|---|
| `rows[]` | `metric` (total site, end use × fuel, peak heating, peak cooling), `detailed`, `archetype`, `difference`, `relative`, `target`, `within_target: bool \| None` (None where the SC-002/SC-003 significance thresholds exclude the metric) |
| `targets` | `AcceptanceTargets` (defaults: SC-001 5 %, SC-002 10 % above a 5 % share, SC-003 15 % above a 10 % share) |
| `comparable` | always true on a returned result; otherwise `NotComparableError` lists the differing items |
