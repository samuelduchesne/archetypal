# SC-004 experiment: hourly simulation against TABULA's seasonal method

Run on 2026-11-23 to decide spec 004's SC-004 band and how the archetype carries TABULA's
temperature-reduction factor (spec, Clarifications). It is evidence for a decision, not
archetypal code: the models are built directly from TABULA's values, not through archetypal.

## What was done

- **Buildings**: 54 TABULA typology buildings from `tabula-calculator.xlsx` (2016-07-15
  release): DE, FR, IT, SE, GB, PL and AT; single- and multi-family houses; an early and a
  late construction period; variants 1 (existing state) and 3 (advanced refurbishment)
  (`select.py`). Two Austrian variant-1 buildings failed to build and are left out.
- **Models** (`simulate.py`): one EnergyPlus 24.2 zone per building with TABULA's reference floor
  area and volume (2.5 m room height), one surface per envelope element with U = H/A from the
  workbook's transmission coefficients (adjustment factors and thermal bridging included;
  elements bordering unheated space unexposed to sun and wind), windows by orientation with
  TABULA's U and g × (1 − frame fraction) × shading factor, constant infiltration plus use air
  change, 3 W/m² constant gains, c_m = 45 Wh/(m²K) as internal mass, ideal-loads heating only.
  Each building ran twice: at TABULA's 20 °C, and at the constant set-point equivalent to its
  temperature-reduction factor, θ_e + F (θ_i − θ_e).
- **Weather** (`weather.json`): one TMYx 2011–2025 file per country.
- **TABULA's method** (`analyse.py`) is reproduced exactly from the workbook's own fields
  (largest difference 7e-16), then recomputed on each weather file: heating days are the days
  with a mean below 12 °C, solar radiation per orientation is EnergyPlus's incident radiation on
  the window surfaces over those days.

## Results (54 buildings)

| Comparison | Median | Mean abs. | 90th pct abs. | Max abs. | Within ±15 % | Within ±25 % |
|---|---|---|---|---|---|---|
| Climate: TABULA's method on the weather file vs TABULA's published value | −19.9 % | 20.4 % | 41.4 % | 44.6 % | 41 % | 74 % |
| Method: simulation at 20 °C vs TABULA's method (F = 1) on the same weather | −6.4 % | 8.8 % | 19.0 % | 28.1 % | 81 % | 98 % |
| Method: simulation at the reduced set-point vs TABULA's method (with F) on the same weather | −7.3 % | 10.9 % | 24.2 % | 28.2 % | 78 % | 89 % |
| Total: simulation at 20 °C vs TABULA's published value | −16.9 % | 19.1 % | 34.6 % | 41.2 % | 48 % | 70 % |
| Total: simulation at the reduced set-point vs TABULA's published value | −28.5 % | 27.8 % | 40.6 % | 53.9 % | 24 % | 37 % |

- TABULA's national climates are 1 to 4.5 K colder over the heating season than the 2011–2025
  weather files, and Sweden's counts 365 heating days: the published figure mostly measures the
  climate, hence SC-004 compares on the same weather.
- A constant reduced set-point shortens the heating season as well as lowering the temperature
  difference, so it reduces more than the factor does: old, poorly insulated houses came out
  12 to 26 % below TABULA's method. Hence the archetype keeps 20 °C and records the factor.

## Reproducing

Download the two workbooks (spec, Assumptions), dump the building sheet with `dump_rows.py`,
fetch the weather files named in `weather.json`, then run `select.py`, `simulate.py` and
`analyse.py`. The scripts hold the scratch paths used on the day. No TABULA data or per-building
results are committed here (roadmap C-15).
