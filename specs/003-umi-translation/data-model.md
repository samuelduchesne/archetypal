# Data model: Translate UMI template libraries to and from SBEM

**Plan**: [plan.md](plan.md) | **Research**: [research.md](research.md)

Units are SI unless a field says otherwise. "Archetype" is the multi-group SBEM model of UP-2
(002 data-model). UMI keys are Basilisk's JSON keys; SBEM paths are relative to one zone group
(`Operations.SpaceUse.Lighting.PowerDensity`) or to the archetype (`archetype.…`) for
building-level fields.

## Pipelines and states

```text
read_umi(path)
  raw JSON ──dialect (R2)──▶ RawLibrary ──refs (R1)──▶ UmiLibrary (private pydantic, resolved)
     │                                                     │
     └─ UmiFormatError                         validate (R3) ──▶ UmiValidationError
                                                           │
                                     per template: to_sbem rules (CORRESPONDENCE)
                                                           ▼
                                   Archetype × n  +  TranslationReport ──strict?──▶ LossyTranslationError
                                                           │
                                                 UmiImport.write(dir)

write_umi(items, path)
  Reduction | Archetype ──layout? (R12)──▶ core/perimeter Archetype
                     merge (002) or approximate merge
                                   │
                    per archetype: to_umi rules (CORRESPONDENCE)
                                   ▼
            UMI components ──share/rename (R13)──▶ UmiLibrary ──serialise──▶ text
                                   │                                         │
                          TranslationReport ──strict?──▶ LossyTranslationError
                                                                             ▼
                                                     <stem>.json + <stem>.loss.json
```

Nothing is written until the whole translation succeeds, and nothing at all in strict mode
when `losses` is not empty.

## Private format model (`archetypal.umi._format`)

One frozen pydantic v2 model per Basilisk Core class, named after it: `GasMaterial`,
`GlazingMaterial`, `OpaqueMaterial`, `MaterialLayer`, `OpaqueConstruction`,
`WindowConstruction`, `StructureInformation`, `MassRatio`, `DaySchedule`, `WeekSchedule`,
`YearSchedule`, `YearSchedulePart`, `DomesticHotWaterSettings`, `ZoneVentilation`,
`ZoneConditioning`, `ZoneConstructions`, `ZoneLoads`, `ZoneDefinition`, `WindowSettings`,
`BuildingTemplate`, and `UmiLibrary` (the 17 collections).

- **Aliases.** Fields are snake_case, with Basilisk's keys as aliases.
- **Defaults.** Basilisk's effective defaults (research R1); the reader records which fields
  were absent.
- **References.** Resolved objects after reading. On writing, the serialiser emits `$id` and
  `$ref` (R13).
- **Enums** are `IntEnum`s with Basilisk's values:
  - `FuelType` 0–13;
  - `IdealSystemLimit`, `EconomizerType`, `HeatRecoveryType`, `DimmingType`, `ShadingType`,
    `WindowType`;
  - `DomesticHotWaterFuelType`.
- **Visibility.** Not exported, not documented as API, and never returned (roadmap C-02).

## FieldMapping and CORRESPONDENCE (FR-009, SC-005)

```python
class Relevance(StrEnum):
    SIMULATION = "S"
    LIFE_CYCLE = "L"
    DESCRIPTIVE = "D"


class MappingStatus(StrEnum):
    EXACT = "exact"
    CONVERTED = "converted"
    UPSTREAM = "upstream"
    NONE = "none"


@dataclass(frozen=True)
class FieldMapping:
    umi_class: str  # "ZoneLoads"
    umi_key: str  # "LightingPowerDensity"
    relevance: Relevance
    sbem_paths: tuple[str, ...]  # empty when status is UPSTREAM or NONE
    rule: str  # rule id, registered in archetypal.umi.rules
    status: MappingStatus
    upstream: str | None  # "UP-9", "UP-2" when status is UPSTREAM
    note: str  # conserved quantity, or why there is no counterpart
```

`CORRESPONDENCE: tuple[FieldMapping, ...]` covers every field of
`tests/data/basilisk_fields.json`. Its invariants:

- each (class, key) appears exactly once;
- `status` `exact` or `converted` has at least one SBEM path;
- `upstream` has a UP item;
- the set of `rule` values equals the set of registered rules.

### Correspondence by UMI class (summary; the table in code is complete)

Status abbreviations: **E** exact, **C** converted, **U** upstream (item), **N** none.

| UMI class | Fields and SBEM targets | Status |
|---|---|---|
| `LibraryComponent` | `Name` → the receiving component's `Name` (naming rules below). `Category`, `Comments`, `DataSource` → `Category`, `Comment`, `DataSource` of the receiving component; on schedules: U (UP-9). | E / U |
| `OpaqueMaterial` | `Conductivity`, `Density`, `SpecificHeat`, `SolarAbsorptance`, `VisibleAbsorptance` → same names. `ThermalEmittance` → `ThermalAbsorptance`. `Roughness` → `Roughness` (6 keywords). | E |
| | `Cost` → `Cost` (`RateUnit="m3"`). `EmbodiedCarbon` → `EmbodiedCarbon × Density` per m³ (`material.carbon_per_m3`). | C |
| | `EmbodiedEnergy`, `Transport*`, `Substitution*`, `MoistureDiffusionResistance`, `DesignStrength`, `ModulusOfElasticity` | U (UP-9) |
| `GlazingMaterial`, `GasMaterial`, `WindowConstruction` | Layers → UP-9 layered window (`window.layers`). Layers it cannot hold: U, SHGC and VT via idfkit (bridge `simple_from_layers`, approximate, reported under `window.layers`). | U / C |
| `MaterialLayer` | `Thickness` → `Thickness`; list position → `LayerOrder`. | E |
| `OpaqueConstruction` | `Layers` → `Layers`. `Assembly*`, `Disassembly*` → U (UP-9). | E / U |
| `StructureInformation`, `MassRatio` | everything | U (UP-9) |
| `DaySchedule` | `Values[0..23]` → `Hour_00…Hour_23`. `Type` → `Type` (`schedule.type`). | E |
| `WeekSchedule` | `Days[0..6]` → `Monday…Sunday`. | E |
| `YearSchedule`, `YearSchedulePart` | Parts → `January…December` (`schedule.months`: exact when month-aligned, else projected, R7). | E / C |
| `DomesticHotWaterSettings` | `FlowRatePerFloorArea` → `WaterUse.FlowRatePerPerson` (`dhw.per_person`, conserves annual volume). `WaterSchedule` → `WaterUse.Schedule`. | C / E |
| | `WaterSupplyTemperature`, `WaterTemperatureInlet` → `DHW.*`. `IsOn` → `DHW.IsOn`. | E |
| | `CoefficientOfPerformance` → `DHW.SystemCOP` (`DistributionCOP = 1`). `FuelType` → `DHW.FuelType` (fuel table). | C |
| `ZoneVentilation` | `Infiltration`, `IsInfiltrationOn` → `Envelope.Infiltration.AirChangesPerHour`, `.IsOn` (`CalculationMethod="AirChanges/Hour"`). | E |
| | `IsNatVentOn` → `HVAC.Ventilation.Provider` (`vent.provider`). `NatVentSchedule` → `HVAC.Ventilation.Schedule`. | C / E |
| | `NatVent*` limits, `IsWindOn`, `IsBuoyancyOn`, `Afn`, `IsScheduledVentilationOn`, `ScheduledVentilation*` | U (UP-9) |
| `ZoneConditioning` | `HeatingSetpoint`, `CoolingSetpoint` → `Thermostat.Heating/CoolingSchedule`, constant (`thermostat.constant`). `IsHeatingOn`, `IsCoolingOn` → `ConditioningSystems.Heating/Cooling` set or `None`. | C |
| | `HeatingCoeffOfPerf`, `CoolingCoeffOfPerf` → `ThermalSystem.SystemCOP` (`DistributionCOP = 1`, `cop.system`). `HeatingFuelType`, `CoolingFuelType` → `ThermalSystem.Fuel` (fuel table). | C |
| | `IsMechVentOn` → `Ventilation.Provider`. `MinFreshAirPerArea`, `MinFreshAirPerPerson` → `Ventilation.FreshAirPerFloorArea`, `.FreshAirPerPerson`. `EconomizerType` → `Economizer`. `HeatRecoveryType` → `HRV`. | E / C |
| | `HeatRecoveryEfficiencySensible`, `…Latent` | U (UP-2) |
| | `HeatingSchedule`, `CoolingSchedule` (availability), `MechVentSchedule`, `*LimitType`, `Max*Flow`, `Max*Capacity` | U (UP-9) |
| `ZoneConstructions` | `Facade`, `Roof`, `Slab`, `Ground`, `Partition` → `Envelope.Assemblies.FacadeAssembly`, `FlatRoofAssembly`, `FloorCeilingAssembly`, `GroundSlabAssembly`, `PartitionAssembly`. | E |
| | `Is*Adiabatic` | U (UP-9) |
| `ZoneLoads` | `PeopleDensity`, `LightingPowerDensity`, `EquipmentPowerDensity` → `Occupancy.PeopleDensity`, `Lighting.PowerDensity`, `Equipment.PowerDensity`. Their schedules → each `Schedule`. `Is*On` → `IsOn`. `DimmingType` → `Lighting.DimmingType`. | E |
| | `IlluminanceTarget` | U (UP-9) |
| `ZoneDefinition` | `InternalMassConstruction`, `InternalMassExposedPerFloorArea` → `Assemblies.InternalMassAssembly`, `InternalMassExposedAreaPerArea` (`mass.internal`: 0 means none). | E |
| | `DaylightMeshResolution`, `DaylightWorkplaneHeight` | U (UP-9) |
| `WindowSettings` | `Construction` → each group's `Envelope.Window` (R8). The other 15 fields → U (UP-9). | E / U |
| `BuildingTemplate` | `Core`, `Perimeter` → groups `core`, `perimeter`, shares unset (R4). `DefaultWindowToWallRatio` → UP-2's window ratio per orientation, all equal (`wwr.uniform`). | E / C |
| | `PartitionRatio`, `Structure`, `Lifespan`, `YearFrom`, `YearTo`, `Country`, `ClimateZone`, `Authors`, `AuthorEmails`, `Version` | U (UP-9) |

### Conversion rules (each conserves the quantity named)

| Rule id | UMI → SBEM | SBEM → UMI | Conserves |
|---|---|---|---|
| `dhw.per_person` | `q_p = q_a × Σ s(h) / (365 × ρ_p)` | `q_a = q_p × 365 × ρ_p / Σ s(h)` | Annual hot-water volume per m² |
| `cop.system` | `SystemCOP = COP`, `DistributionCOP = 1` | `COP = SystemCOP × DistributionCOP` | Consumed energy for given delivered energy |
| `material.carbon_per_m3` | `C_m3 = C_kg × ρ` | `C_kg = C_m3 / ρ` (refused for ρ = 0) | Embodied carbon per unit volume |
| `schedule.months` | Month-aligned: copy; misaligned: 002 projection | 12 months → parts, merged when equal | Monthly sum (exact for aligned) |
| `thermostat.constant` | Constant temperature schedules | Max (heating) / min (cooling) | Occupied setpoint; setback hours reported |
| `window.layers` | Layer by layer to UP-9's layered window; layers it cannot hold (more than 4 panes, panes and gases not alternating) go through the bridge `simple_from_layers` (idfkit U/SHGC/VT, approximate) | Layered window back layer by layer; simple glazing through the bridge `equivalent_layer` (EnergyPlus simple-glazing model, until UP-10) | Layers exactly; through a bridge, U, SHGC, VT (approximate) |
| `building.partition_ratio` | `PartitionAreaPerFloorArea = 2 × PartitionRatio` (the ratio is partition wall area per floor area; SBEM counts both faces) | `PartitionRatio = PartitionAreaPerFloorArea / 2`, from the perimeter group | Partition face area |
| `vent.provider` | (mech, nat) → None/Natural/Mechanical/Both | inverse | Both switches |
| `wwr.uniform` | Same ratio on every orientation | Facade-area-weighted mean; loss if orientations differ | Window area for a given facade |

### Fuel table

| UMI `FuelType` | SBEM `FuelType` (systems) | Loss |
|---|---|---|
| Electricity | Electricity | |
| NaturalGas | NaturalGas | |
| PropaneGas | Propane | |
| FuelOil1, FuelOil2 | FuelOil | which oil (on read) |
| Diesel, Gasoline, Coal | same | |
| OtherFuel1, OtherFuel2 | CustomFuel | which (on read); written as OtherFuel1 |
| Steam | Steam | |
| DistrictCooling | ChilledWater | |
| DistrictHeating | Steam (substitute) | lost on read |
| None (0) | range problem when the system is on | |
| — | WoodPellets → OtherFuel1 | lost on write |

Hot water: UMI `Electricity`, `NaturalGas` and `Oil` map to SBEM `Electricity`, `NaturalGas`
and `FuelOil`. SBEM `Propane` and `Steam` have no UMI counterpart and are written as
`NaturalGas` with a loss. `Unset` is a range problem.

### Names of components without a one-to-one counterpart

| UMI component | Named from (writing) | Read back into |
|---|---|---|
| `ZoneDefinition` | the group's `ZoneComponent.Name` | `ZoneComponent.Name`, `ZoneOperationsComponent.Name`, `ZoneEnvelopeComponent.Name` |
| `ZoneLoads` | `ZoneSpaceUseComponent.Name` | same, plus `Occupancy/Lighting/Equipment` names `"{name} occupancy"`, … |
| `ZoneConditioning` | `ZoneHVACComponent.Name` | same, plus `Thermostat`, `ConditioningSystems`, `ThermalSystem` (`"{name} heating"`, `"{name} cooling"`), `Ventilation` |
| `ZoneVentilation` | `InfiltrationComponent.Name` | same |
| `DomesticHotWaterSettings` | `DHWComponent.Name` | `DHWComponent.Name`, `WaterUseComponent.Name` |
| `ZoneConstructions` | `EnvelopeAssemblyComponent.Name` | same |
| `WindowSettings` | the perimeter window's name + `" settings"` | (building-level, UP-9) |

Reading derives sub-component names by the rules above, and writing recovers the UMI name from
the parent, so names survive both round trips.

## TranslationReport (FR-011, FR-011a)

A pydantic model whose JSON Schema is published
([contracts/translation-report.md](contracts/translation-report.md)).

| Field | Type | Content |
|---|---|---|
| `schema_version` | `str` | `"1.0"` |
| `direction` | `Literal["umi_to_sbem", "sbem_to_umi"]` | |
| `source` | `SourceInfo` | path, SHA-256, dialect (reading), archetypal and epinterface versions |
| `subjects` | `list[str]` | templates read or archetypes written, in order |
| `losses` | `list[Loss]` | sorted by subject, then location |
| `notes` | `list[Note]` | same order |
| `summary` | `str` | `"Nothing was lost."` when `losses` is empty, else counts by kind |

```python
class LossKind(StrEnum):
    LOST = "lost"
    APPROXIMATE = "approximate"
    MERGED = "merged"
    COPIED = "copied"
    SHARE_DROPPED = "share_dropped"
    RENAMED = "renamed"
    UNUSED = "unused"
    SKIPPED_TEMPLATE = "skipped_template"


class Loss(BaseModel, frozen=True):
    kind: LossKind
    subject: str  # template or archetype name ("" for library-level, e.g. unused)
    location: str  # JSON pointer (UMI side) or field path (SBEM side)
    value: JsonValue  # the value not represented
    replacement: JsonValue | None
    rule: str  # rule id, or "library.unused", "names.collision", …
    reason: str
    upstream: str | None  # UP item when the gap is upstream


class NoteKind(StrEnum):
    DEFAULTED = "defaulted"
    ASSUMED = "assumed"
    UNKNOWN_KEY = "unknown_key"


class Note(BaseModel, frozen=True):
    kind: NoteKind
    subject: str
    location: str
    value: JsonValue
    rule: str
    reason: str
```

**Invariants.**

- Strict mode fails if and only if `losses` is not empty.
- Every `Loss.rule` names a registered rule or a library-level rule.
- Every `upstream` value is a roadmap UP item.
- Floats in `value` are written with `repr` precision.

## Results

```python
@dataclass(frozen=True)
class UmiImport:
    archetypes: tuple[Archetype, ...]  # template order
    report: TranslationReport

    def write(self, directory: str | os.PathLike[str], *, overwrite: bool = False) -> tuple[Path, ...]:
        ...
        # <archetype>.sbem.json per archetype + <library stem>.loss.json


@dataclass(frozen=True)
class UmiExport:
    text: str  # the library JSON
    report: TranslationReport

    def write(self, path: str | os.PathLike[str], *, overwrite: bool = False) -> tuple[Path, Path]: ...
```

## UmiDiff (US3, SC-003, SC-006)

| Field | Type |
|---|---|
| `differences[]` | `location` (JSON pointer in the original), `relevance` (S/L/D), `original`, `result`, `relative` (`None` for non-numeric) |
| `within_tolerance` | `bool`: no `S` difference above `rel_tol` |
| `rel_tol` | `float` (default 1e-4, SC-003) |

`ArchetypeDiff` is the same over SBEM field paths.

## Errors (extending 001's hierarchy, 001 research R8)

```text
ArchetypalError
├── InputError
│   ├── UmiFormatError         dialect refused, malformed JSON, reference rules (R1, R2)
│   └── UmiValidationError     completeness and range problems; .problems: list[Problem]
└── LossyTranslationError      strict mode; .report: TranslationReport (001)
```

`Problem` holds the JSON pointer, the template (if any), the rule broken and the message. The
subject of each error is the library path, or the archetype name for writing.
