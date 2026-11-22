# Stand-in diagnosis: why the fixture archetypes missed SC-001 to SC-003

This page explains the differences the stand-in smoke run found between the unit fixtures'
detailed runs and their archetypes' runs, separates the defects from what SBEM and the shoebox
cannot hold, and records what was fixed.

Run: `uv run python verification/report.py --run --stand-in tests/fixtures/models/<name>.idf`.
The run reduces at the default layout (space use × exposure), builds the archetype with the
fork's builder at the pinned commit (`dee8d34`) and simulates both models on epinterface's
bundled weather (Boston Logan, TMYx). Stand-in results are a smoke test, not evidence.

## Results before and after

Relative difference, archetype against detailed model. Judged rows only (SC-002: end uses of at
least 5 % of total site energy; SC-003: peaks of at least 10 % of the larger peak). Heating and
cooling are judged with pumps and heat rejection added.

| Fixture | Metric | Before | After | Target |
|---|---|---:|---:|---|
| three_zone | Total site energy | +2.0 % | +3.4 % | ±5 % |
| | Heating | +4.2 % | +7.1 % | ±10 % |
| | Cooling | +3.7 % | +3.7 % | ±10 % |
| | Peak heating | **−19.8 %** | +14.0 % | ±15 % |
| | Peak cooling | −5.6 % | −5.6 % | ±15 % |
| | SC-001 / SC-002 / SC-003 | pass / pass / **fail** | pass / pass / pass | |
| bar_building | Total site energy | **+17.4 %** | **+10.7 %** | ±5 % |
| | Interior lighting | **+108 %** | **+108 %** (limitation, quantified) | ±10 % |
| | Exterior lighting | **−100 %** | **−100 %** (limitation, quantified) | ±10 % |
| | Heating | +0.7 % | −6.9 % | ±10 % |
| | Cooling | **+96.5 %** | **+67.9 %** | ±10 % |
| | Peak heating | +2.9 % | −5.4 % | ±15 % |
| | Peak cooling | **+34.1 %** | **+23.9 %** | ±15 % |
| ten_zone_multipliers | Total site energy | **−14.2 %** | **−17.0 %** | ±5 % |
| | Water systems | **+59.2 %** | −0.3 % | ±10 % |
| | Heating | −0.2 % | +6.8 % | ±10 % |
| | Cooling | **−72.4 %** | **−72.8 %** (limitation, listed) | ±10 % |
| | Peak heating | **−48.0 %** | +6.5 % | ±15 % |
| | Peak cooling | **+160 %** | **+149 %** (limitation, listed) | ±15 % |

`three_zone` now meets SC-001 to SC-003. What remains for the other two fixtures is what the
archetype cannot hold; each item is now listed in the report's `not_represented[]`, with its
size where the results give it.

## How the differences were traced

Each difference was followed through the same chain: the detailed model's totals, the
reduction's ledger, the archetype's fields, and the archetype run's outputs. The archetype runs
were repeated with one field changed at a time, and both runs were repeated with extra hourly
outputs (ideal-loads sensible, latent, outdoor-air, economiser and heat-recovery terms; coil
sensible and latent energy; outdoor-air flow and economiser status) and with the *Sensible Heat
Gain Summary*, *Envelope Summary* and *Zone Summary* tables side by side.

The steps that agree for all three fixtures: conditioned floor area, window area, UA and
area × SHGC (within 0.2 %), opaque area and UA of the conditioned zones (within 6 %; the
excluded basement and attic of `ten_zone_multipliers` aside), lighting, equipment and people
densities, outdoor-air flow, setpoint profiles, and the conservation checks of SC-005. The differences come from the steps below.

## Defects, fixed

### 1. Hot-water efficiency divided by the wrong heat (ten_zone_multipliers, water systems +59 %)

The fixture draws 60 °C water (`Hot Water Supply Temperature Schedule`) to reach 43 °C
(`Target Temperature Schedule`). The hot-water module computes the heat with the 60 °C supply
temperature, and the archetype's `DHW.WaterSupplyTemperature` is 60.2 °C. The efficiency module
computed the delivered heat with the 43 °C target instead, so the hot-water `SystemCOP` was
128 GJ ÷ 228 GJ = 0.56 rather than 204 GJ ÷ 228 GJ = 0.90. The archetype then delivered the
60 °C heat (204.6 GJ) at the 43 °C efficiency: 204.6 ÷ 0.56 = 363 GJ against 228 GJ. The ratio
of the two temperature rises, (60 − 14.8) ÷ (43 − 14.8) = 1.60, is the whole difference.

Fix: `efficiency.building_energy` takes the hot-water module's heat
(`hotwater.hot_water_totals`, supply temperature, else target). After: −0.3 %.
Tests: `test_hot_water_delivered_heat_uses_the_hot_water_supply_temperature` and
`test_archetype_hot_water_gives_back_the_detailed_consumption` (volume × rise × ρc ÷ efficiency
over the groups equals the `WaterSystems` meter within 1 %).

### 2. Ideal-loads capacity left to epinterface's autosizing (three_zone peak heating −20 %, ten_zone −48 %)

The peak is the first hour after the night setback (15.6 → 21 °C at 06:00, outdoor −15 °C).
The archetype's hourly heating had a flat top at 27.1 kW delivered, the sum of the three
ideal-loads capacities epinterface autosized (13.5 + 2.2 + 11.4 kW). The detailed PTAC coils
were sized at 44.8 kW and delivered 33.9 kW in that hour, so they were not limiting.

The archetype left the ideal loads' limit types at the fork's default,
`LimitFlowRateAndCapacity` autosized. With R19's supply-air limits (the setpoint ± the
detailed model's annual effective supply temperature difference, here about 24 °C heating and
21–22 °C cooling) those autosized flows and capacities describe no equipment of the detailed
model: they follow from epinterface's own design days and sizing factor at temperatures chosen
to reproduce the annual air volume. Removing only the capacity limit (`LimitFlowRate`) gave
−6.5 % for `three_zone` but left `ten_zone_multipliers` at −45 %: there the autosized heating
air flow binds during the morning recovery. Removing both limits on cooling made the ideal
loads' economiser draw unbounded outdoor air (fans +1700 %).

Fix: `to_sbem.IDEAL_LOADS_LIMITS`, set with the supply-air limits (rule
`fans.effective_supply_delta`): heating `NoLimit` (its air volume is then load ÷ (ρ·cp·Δ), the
volume R19 reproduces), cooling `LimitFlowRate` (autosized flow, which bounds the economiser's
outdoor air), no capacity limit. After: `three_zone` +14.0 %, `ten_zone_multipliers` +6.5 %.
The unclipped `three_zone` peak is higher than the detailed one because the detailed PTAC's
supply air is itself limited to 40 °C at its design flow. Heating energy rises by 3 points
(`three_zone`) and 7 points (`ten_zone_multipliers`): the recovery energy the clipped archetype
left unmet.
Test: `test_ideal_loads_capacity_is_not_autosized`. The UMI writer now records as lost an unset
limit value that the limit type does not use (UMI has no unset value; Basilisk's default comes
back), which the UMI round-trip audit asked for.

### 3. The verification shoebox drew a core for an all-perimeter archetype (bar_building cooling)

`verification/report.py` (and `tests/integration/test_epinterface_build.py`) chose
core/perimeter zoning whenever any group had an exposure. `bar_building` reduces to one group,
all perimeter (share 1). The shoebox then had a 208 m² windowless core (29 % of the floor) with
the perimeter's loads, which needed cooling all year while the perimeter zones needed heating.
Against the detailed run without daylighting, cooling was +52 % and heating +9 % with the
core; +30 % and +1 % without it.

Fix: core/perimeter zoning only when a group is a core group; otherwise one zone per storey (or
one per group). Test: `test_shoebox_draws_a_core_only_for_a_core_group`.

## Limitations, now quantified in the report

### Daylighting (bar_building interior lighting +108 %)

Both bar zones dim their lights with daylight (split flux, continuous, minimum 30 % power). The
archetype's lighting follows the undimmed schedule. Simulating the detailed model with its
`Daylighting:Controls` and reference points removed gives 84.74 GJ of interior lighting, exactly
the archetype's: daylighting explains 100 % of the +108 %. It also explains part of the cooling
difference: removing it from the detailed model raises cooling from 50.9 to 65.6 GJ.

The report's `Daylighting controls` entry now gives the energy daylight saved, from the
*Lighting Summary*: for each `Lights` object in a daylit zone,
`Consumption · (scheduled hours − full-load hours) ÷ full-load hours` (45.4 GJ on the fixture's
own results, 44.1 GJ on the stand-in weather). Test: `test_daylighting_saving_is_quantified`.

The fork at the pinned commit can dim lights with daylight (UP-9, `LightingComponent`
`DimmingType`, `IlluminanceTarget`, `DaylightWorkplaneHeight`). Mapping the detailed model's
controls to it is a follow-up, not a defect: the shoebox's reference point (the zone centre) and
zones differ from the detailed ones, so its saving would need its own check.

### Exterior lights (bar_building exterior lighting −100 %)

Already listed with their energy, 31.39 GJ (*Lighting Summary*). Without them the archetype's
total site energy would be compared with 329.4 GJ instead of 360.8 GJ.

### Ground temperatures (bar_building cooling +30 % after the fixes above)

The detailed model sets `Site:GroundTemperature:BuildingSurface` (18.2–22.5 °C). epinterface
derives its own from the archetype's thermostat and the weather file (16.6–24.4 °C): colder in
winter, warmer in summer. `bar_building` has an uninsulated slab (about 2.6 kW/K with the
inside film), so the summer ground cools the detailed model much more. Giving the archetype run
the detailed ground temperatures brings its cooling from +30 % to +6 % and its heating from
+1 % to −12 % (one zone per storey, against the detailed run without daylighting); the heating
then shows the load cancellation between the north and south zones that one zone adds.

SBEM has no ground-temperature field, so the report now lists `Ground temperatures` with the
conductance of the ground-contact surfaces they drive, W/K (2.64 kW/K for `bar_building`).
Test: `test_ground_temperatures_are_listed`.

### Air-side control of a central VAV system (ten_zone_multipliers cooling −73 %, peak cooling +149 %)

The fixture's VAV system supplies air at 16 °C reset to 12.8 °C, reheats at the terminals
(minimum flow 30 %), and economises with differential dry-bulb control held to the mixed-air
setpoint, a 23.9 °C high limit and heat-recovery bypass. The efficiency divides the chiller's
consumption by the coil energy (2143 GJ, cooling coil total), and the archetype's ideal loads
are meant to deliver that energy again. They deliver 779 GJ: the zones' sensible cooling is
similar (1844 GJ against 2202 GJ), but the ideal loads supply air only as cold as each zone
needs and economise up to the zone temperature, so outdoor air provides about 1130 GJ of it
for free. The detailed coil keeps cooling 100 % outdoor air down to the supply setpoint.
With the archetype's economiser switched off, cooling is −34 % and peak cooling +27 %: the
economiser accounts for about half of the energy difference and most of the peak one.

The peak cooling hour (21 August, noon, outdoor 23.7 °C, after a weekend with the zones at
29 °C) is the ideal loads' economiser drawing humid outdoor air at its autosized flow and
drying it to the template's minimum supply humidity ratio (0.0077 kg/kg): 2.2 GJ of the hour's
2.5 GJ is outdoor-air latent cooling.

Neither the reduction nor the archetype can hold this control: SBEM's conditioning is ideal
loads. The report now lists `Air-side control of central air systems` for every
`AirLoopHVAC`, with the zones it serves. Its size is the difference above, which only the
archetype run gives. Test: `test_air_side_control_of_central_systems_is_listed`. Possible
follow-ups: attribute the cooling efficiency to the zones' loads rather than to coil energy for
air-loop zones, or carry the detailed supply-air temperature as the ideal loads' limit and
correct the specific fan power for the volume that changes.

### Smaller items

- `ten_zone_multipliers` heating electricity (the heat pumps, 21.6 GJ) is folded into the gas
  system's efficiency (SBEM holds one fuel per mode); listed as `Secondary fuels of heating`.
  Judged with distribution, heating is +6.8 %.
- `ten_zone_multipliers` fans +22 % (not judged: 2.5 % of total site energy) follow the ideal
  loads' air volume, which the economiser raises.
- The stand-in's detailed models size on Chicago design days and run on Boston weather; the
  archetype sizes on Boston's extreme weeks. With the capacity limits removed this no longer
  affects the peaks.

## Files changed

- `src/archetypal/reduction/efficiency.py`: hot-water heat from the hot-water module.
- `src/archetypal/reduction/to_sbem.py`: `IDEAL_LOADS_LIMITS`.
- `src/archetypal/reduction/features.py`: daylighting saving, ground temperatures, air loops.
- `src/archetypal/umi/rules/conditioning.py`: an unused unset limit is recorded as lost.
- `verification/report.py`, `tests/integration/test_epinterface_build.py`: shoebox zoning.
- `tests/unit/test_stand_in_diagnosis.py` (new), `tests/unit/test_features.py` (expected rows).

No change to the fork was needed: its builder honoured every archetype field checked
(supply-air limits, limit types, specific fan power, EIR slope, heat-recovery effectiveness,
mechanical-ventilation schedule, economiser, infiltration schedule, window ratios by
orientation).
