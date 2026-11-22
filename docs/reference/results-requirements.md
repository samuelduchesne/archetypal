---
diataxis: reference
---

# Results requirements

The simulation results `archetypal.reduce` reads from the detailed model's annual run. The
table of outputs is generated from `archetypal.reduction.RESULTS_REQUIREMENTS`, the constant
that also writes the messages of `MissingResults` and the outputs added by the single run
(`reduce(..., simulate=True)`).

## Run conditions

| Condition | Required |
|---|---|
| EnergyPlus version | 22.1 to the latest release idfkit supports |
| Run period | One annual weather-file run period; design days may also be present |
| `Output:SQLite` | `SimpleAndTabular` |
| `Output:Table:SummaryReports` | `AllSummary` |

## Output variables and meters

Every item is hourly. An item that does not apply to the model is not required: a model with
no `WaterUse:Equipment` needs no hot-water outputs, and one without baseboards needs no
`Baseboard Total Heating Energy`. "Every heating coil" means every `Coil:Heating:*` object, and
"every cooling coil" every `Coil:Cooling:*` object except the `Coil:Cooling:DX:CurveFit:*`
performance objects and thermal-storage coils. A meter written `<fuel>` is needed for each
fuel the model uses. The output object is what to add to the model; `*` requests every key.

<!-- results-requirements -->

## Tables read

The run settings above write these, so they need no output object:

- SQLite tables: `Zones`, `Surfaces`, `Constructions`, `ConstructionLayers`, `Materials`,
  `NominalPeople`, `NominalLighting`, `NominalElectricEquipment`, `NominalGasEquipment`,
  `NominalHotWaterEquipment`, `NominalSteamEquipment`, `NominalOtherEquipment`,
  `NominalBaseboardHeaters`, `NominalInfiltration`, `NominalVentilation`, `Simulations`,
  `EnvironmentPeriods`, `Time`;
- tabular reports: Envelope Summary (Opaque Exterior, Exterior Fenestration), Annual Building
  Utility Performance Summary (End Uses), and Equipment Summary for rated efficiencies.

## When results are missing

`reduce` raises `MissingResults`. The error lists each missing item with the `Output:Variable`
or `Output:Meter` object to add, in IDF syntax, and suggests `simulate=True`, which runs the
model once with every missing output. Results of a run without its weather-file run period
(`SimulationControl` with `Run Simulation for Weather File Run Periods` set to `No`, as in many
EnergyPlus example files) are missing too; the single run sets it to `Yes` (see
[How to reduce a model](../how-to/reduce-a-model.md#reduce-without-results)).
