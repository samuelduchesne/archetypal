---
diataxis: how-to
---

# How to check that an archetype reproduces its building

An archetype is only useful if it uses energy the way the detailed model does. To check it,
simulate both on the same weather and compare their results with `archetypal.compare`: you get
total site energy, every end use by fuel and the peak heating and cooling demand, with their
difference and whether it meets the acceptance targets. This guide assumes you already have
both SQLite result files.

## Simulate both models the same way

`compare` refuses results that are not comparable, so run both models with:

- the same weather file and run period;
- the same timesteps per hour (`Timestep`);
- the same tabular unit system (`OutputControl:Table:Style`);
- the `Heating:<fuel>` and `Cooling:<fuel>` meters (`Output:Meter`) at the same reporting
  frequency: every zone timestep, hourly or daily;
- `Output:SQLite` with `SimpleAndTabular`, and `Output:Table:SummaryReports` with
  `AllSummary`.

If the detailed model has pumps or heat rejection, its results also need their meters
(`Pumps:<fuel>`, `HeatRejection:<fuel>`) and the energy its HVAC equipment delivered
(`Zone Ideal Loads Supply Air Total Heating/Cooling Energy`, `Heating Coil Heating Energy`,
`Cooling Coil Total Cooling Energy`, `Baseboard Total Heating Energy`, `Zone Radiant HVAC
Heating/Cooling Energy`, for each object present), at the same frequency: pumps and heat
rejection are split between heating and cooling as a reduction splits them. A reduction also
charges service-hot-water pumps to hot water, from delivery the results do not hold; the
comparison splits them between heating and cooling, so in a building with such pumps the
detailed rows with pumps run slightly high. Results written for a reduction already have all
of these.

## Compare the results

Pass the detailed model's results first, then the archetype's:

```python
from archetypal import compare

result = compare("detailed.sql", "archetype.sql")

for row in result.rows:
    print(f"{row.metric:40} {row.detailed:10.2f} {row.archetype:10.2f} {row.units:3} {row.within_target}")
```

```text
Total site energy                             14.87      15.14 GJ  True
Interior Lighting: Electricity                 1.47       2.06 GJ  False
Exterior Lighting: Electricity                 1.21       1.21 GJ  True
Interior Equipment: Electricity                4.32       4.32 GJ  True
Cooling: District Cooling                      0.02       0.02 GJ  None
Heating: District Heating Water                7.86       7.53 GJ  None
Heating, with pumps and heat rejection         7.86       7.53 GJ  True
Cooling, with pumps and heat rejection         0.02       0.02 GJ  None
Peak heating demand                        32449.54   32347.99 W   True
Peak cooling demand                         1605.25    1862.15 W   None
```

Either argument may also be an open `idfkit.simulation.SQLResult`.

## Read the verdict

Each row gives both values, `difference` (archetype minus detailed) and `relative` (the
difference over the detailed value). Read `within_target` as follows:

- `True` or `False`: the row was judged against its `target`.
- `None` with a `target`: the quantity is too small to judge. An end use must be at least 5 %
  of the detailed model's total site energy, and a peak at least 10 % of the larger of its two
  peaks.
- `None` without a `target`: the row is reported but never judged. Pumps and heat rejection
  have no counterpart in an archetype. Heating and cooling as reported are judged in their
  *with pumps and heat rejection* rows, where each interval's pump and heat-rejection energy
  is added to the mode the zones were in.

To act on the outcome, check `passed` and list the `failures`:

```python
from archetypal import compare

result = compare("detailed.sql", "archetype.sql")
if not result.passed:
    for row in result.failures:
        print(f"{row.metric}: {row.relative:+.1%}, target ±{row.target:.0%}")
```

```text
Interior Lighting: Electricity: +40.1%, target ±10%
```

A failure points to the archetype parameter to look at first: here, the lighting power
density.

## Change the targets

The defaults are the project's acceptance targets: ±5 % on total site energy, ±10 % on each
end use and ±15 % on each peak. For a screening study, loosen them with `AcceptanceTargets`:

```python
from archetypal import compare
from archetypal.comparison import AcceptanceTargets

screening = AcceptanceTargets(end_use=0.5, peak=0.25)
result = compare("detailed.sql", "archetype.sql", targets=screening)
assert result.passed
```

## Check the weather file too

The results name their weather file but do not contain it. To make sure both runs used a
particular file, pass it as `weather`; `compare` refuses either run if it names another
file, and keeps the file's SHA-256 for your records:

<!-- example: needs-energyplus -->
```python
from archetypal import compare

result = compare("detailed.sql", "archetype.sql", weather="weather.epw")
print(result.weather_sha256)
```

## When the results cannot be compared

`compare` raises `NotComparableError` when the runs differ in weather, run period, units,
timestep or meter reporting frequency, or when a result lacks what the comparison reads. The
error names every difference at once, in `differences`:

```python
from archetypal import compare
from archetypal.errors import NotComparableError

try:
    compare("detailed.sql", "other-period.sql")
except NotComparableError as error:
    for difference in error.differences:
        print(difference)
```

```text
run period: 03-15 00:00 to 03-29 00:00 (336 hours, starting on a Wednesday) for detailed.sql, 03-29 00:00 to 04-12 00:00 (336 hours, starting on a Wednesday) for other-period.sql
```

Run the model named in the message again with the other run's setting; the comparison has no
option to override a refusal, because peak demand and the end uses would not mean the same
thing.

For every field of the result, see the
[`archetypal.comparison` reference](../reference/api/reduction.md#comparison).
