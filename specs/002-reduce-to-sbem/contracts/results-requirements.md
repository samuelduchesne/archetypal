# Contract: simulation results reduction needs (FR-002)

The detailed model's annual run must write an EnergyPlus SQLite file that holds everything
below. This table and the `RESULTS_REQUIREMENTS` constant describe the same list; a unit test
asserts they agree.

## Run conditions

| Condition | Required |
|---|---|
| EnergyPlus version | 22.1 to idfkit's latest (R3) |
| Run period | One annual weather-file run period. Design days may also be present. |
| `Output:SQLite` | `SimpleAndTabular` |
| `Output:Table:SummaryReports` | `AllSummary` |

## Output variables and meters

| Item | Key | Frequency | Used for |
|---|---|---|---|
| `Zone Air System Sensible Heating Energy` | every zone | Hourly | delivered heating (FR-022) |
| `Zone Air System Sensible Cooling Energy` | every zone | Hourly | delivered cooling (FR-022) |
| `Fan Electricity Energy`, `Fan Air Mass Flow Rate` | every fan | Hourly | fan energy and air volume (FR-022a) |
| `System Node Mass Flow Rate` | each zone's air inlet nodes | Hourly | attributing air-loop fans to zones (FR-022a) |
| `Site Outdoor Air Drybulb Temperature` | Environment | Hourly | efficiency's dependence on outdoor temperature (FR-022) |
| `Zone Mechanical Ventilation Standard Density Volume Flow Rate` | every zone | Hourly | outdoor air (FR-019) |
| `Site Mains Water Temperature` | Environment | Hourly | hot water (FR-021) |
| `Water Use Equipment Hot Water Volume` | every `WaterUse:Equipment` | Hourly | hot water (FR-021) |
| Meters `Heating:<fuel>`, `Cooling:<fuel>`, `Fans:Electricity`, `Pumps:Electricity`, `HeatRejection:<fuel>`, `WaterSystems:<fuel>` | — | Hourly | consumed energy (FR-022), peaks (FR-027) |

An item that does not apply to the model is not required. For example, a model with no
`WaterUse:Equipment` needs no hot-water outputs.

## Tables read (written by the settings above)

- **SQLite tables:** `Zones`, `Surfaces`, `Constructions`, `ConstructionLayers`, `Materials`,
  `NominalPeople`, `NominalLighting`, `NominalElectricEquipment`, `NominalGasEquipment`,
  `NominalHotWaterEquipment`, `NominalSteamEquipment`, `NominalOtherEquipment`,
  `NominalBaseboardHeaters`, `NominalInfiltration`, `NominalVentilation`, `Simulations`,
  `EnvironmentPeriods`, `Time`.
- **Tabular reports:**
  - Envelope Summary (Opaque Exterior, Exterior Fenestration);
  - Annual Building Utility Performance Summary (End Uses);
  - Equipment Summary, for rated efficiencies (R12).

## On failure

`MissingResults` lists each missing item, with:

- the `Output:Variable` or `Output:Meter` object to add, in IDF syntax;
- a pointer to `reduce(..., simulate=True)`.
