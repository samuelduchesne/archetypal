---
diataxis: how-to
---

# How to reduce a detailed model to an SBEM archetype

A detailed EnergyPlus model describes one building zone by zone; an SBEM archetype describes
it as a few zone groups that epinterface can turn back into a model. `archetypal.reduce` makes
the archetype from the model and the results of its annual run, with a report of every
simplification. This guide reduces a model with existing results or with a single run, checks
the report, and chooses the layout, the small-group threshold and the space uses. It assumes
the model is an EnergyPlus 22.1 or later `.idf` or `.epJSON` file.

## Reduce with existing results

Pass the model and the SQLite output of its annual run. `reduce` returns a `Reduction`, which
holds the fork's `Archetype` and the report:

```python
from archetypal import reduce

reduction = reduce("three_zone.idf", "three_zone.sql")

for group in reduction.archetype.Groups:
    print(f"{group.Name:24} {group.Exposure:10} {group.FloorAreaShare:.2f}")
```

```text
Conference / perimeter   perimeter  0.38
Office / core            core       0.24
Office / perimeter       perimeter  0.38
```

`reduce` writes nothing. Write the archetype and its report with `Reduction.write`:

```python
from archetypal import reduce

reduction = reduce("three_zone.idf", "three_zone.sql")
archetype_path, report_path = reduction.write("archetypes", "office")
```

This writes `archetypes/office.sbem.json` and `archetypes/office.report.json`. Equal inputs
give byte-identical files. `write` refuses to replace existing files; pass `overwrite=True`
to replace them. Read both back with `Reduction.read`:

```python
from archetypal.reduction import Reduction

reduction = Reduction.read("office.sbem.json")
print(reduction.archetype.Name, len(reduction.report.groups))
```

The results must hold the outputs that [Results requirements](../reference/results-requirements.md)
lists, from a run of the same model. `reduce` checks them before doing any work and raises
`ModelResultsMismatch` when the results come from another model, or
`UnsupportedEnergyPlusVersion` for a release older than 22.1.

## Reduce without results

When the results lack outputs, `reduce` raises `MissingResults`, which lists each missing
output as the IDF object to add:

```python
from archetypal import reduce
from archetypal.errors import MissingResults

try:
    reduce("three_zone.idf")
except MissingResults as error:
    print(*error.missing[:3], sep="\n")
```

```text
Output:Variable,*,Zone Air System Sensible Heating Energy,Hourly;
Output:Variable,*,Zone Air System Sensible Cooling Energy,Hourly;
Output:Variable,*,Heating Coil Heating Energy,Hourly;
```

Add them to the model and run it again, or let `reduce` run it once. With `simulate=True`,
it copies the model, adds every missing output and runs EnergyPlus through idfkit with the
weather file you give:

<!-- example: needs-energyplus -->
```python
from archetypal import reduce

reduction = reduce("three_zone.idf", simulate=True, weather="chicago.epw")
print(reduction.report.reproducibility.weather_sha256 is not None)
```

The run needs EnergyPlus; pass `energyplus=` an `idfkit.simulation.EnergyPlusConfig` to pick
an installation. Its results are cached, so reducing the same model and weather again does
not run EnergyPlus a second time. A failed run raises `ReductionError` with EnergyPlus's
message.

## Check the report

The report says, for each group, which zones it was formed from, and lists the zones left
out of every group. Attics and basements are left out with their role; their assumptions go to
the archetype's `Attic` and `Basement`, and their envelope to the groups of the zones below or
above them:

```python
from archetypal import reduce

reduction = reduce("ten_zone_multipliers.idf", "ten_zone_multipliers.sql")
report = reduction.report

for group in report.groups:
    print(group.name, [(member.zone, member.multiplier) for member in group.members])
for zone in report.excluded_zones:
    print(f"{zone.zone:16} {zone.role:10} {zone.floor_area * zone.multiplier:8.1f}")
```

```text
use:G_Core / core [('G_Core', 1), ('Top_Core', 1), ('Typical_Core', 10)]
use:G_Core / perimeter [('G_Perimeter', 1), ('Top_Perimeter', 1), ('Typical_Perimeter', 10)]
Attic            attic         600.0
Basement         basement      600.0
G_Plenum         excluded      600.0
Typical_Plenum   excluded     6000.0
```

Then read what the archetype does not represent. Each entry of `not_represented` names a
feature of the model and, when its effect was folded into another value, the SBEM field that
carries it:

```python
from archetypal import reduce

reduction = reduce("three_zone.idf", "three_zone.sql")
for entry in reduction.report.not_represented:
    print(entry.feature, "->", entry.folded_into)
```

```text
Design-day schedule profiles -> None
Infiltration response to weather -> Zone.Envelope.Infiltration.FlowPerExteriorSurfaceArea
Infiltration response to weather -> Zone.Envelope.Infiltration.FlowPerExteriorSurfaceArea
Radiant, latent and lost parts of internal gains -> None
Radiant, latent and lost parts of internal gains -> None
Radiant, latent and lost parts of internal gains -> None
```

Every value reduction set in the archetype is in `parameters`, with the rule that produced it.
To see where a value came from, look it up by its field path:

```python
from archetypal import reduce

reduction = reduce("three_zone.idf", "three_zone.sql")
for parameter in reduction.report.parameters:
    if parameter.path.endswith("Heating.SystemCOP"):
        print(parameter.group, parameter.value, parameter.rule)
```

```text
Conference / perimeter 0.8 efficiency.delivered_over_consumed
Office / core 0.8 efficiency.delivered_over_consumed
Office / perimeter 0.8 efficiency.delivered_over_consumed
```

[Reduction report](../reference/reduction-report.md) describes every field, and
[About reduction](../explanation/reduction.md) explains each rule.

## Choose a layout

The layout decides how many zone groups the archetype has. Each layout keeps some of the two
distinctions reduction makes between conditioned zones, their space use and their exposure:

| `Layout` | Groups | Use it when |
|---|---|---|
| `SPACE_USE_EXPOSURE` (default) | one per space use and exposure | you want the archetype closest to the model |
| `SPACE_USE` | one per space use | the facade matters less than what the spaces are used for |
| `CORE_PERIMETER` | one per exposure | a tool needs core and perimeter only, such as a UMI template |
| `SINGLE_ZONE` | one for the building | you need one zone definition, for a stock model or a quick estimate |

Pass the layout in `ReductionOptions`:

```python
from archetypal import Layout, ReductionOptions, reduce

options = ReductionOptions(layout=Layout.CORE_PERIMETER)
reduction = reduce("three_zone.idf", "three_zone.sql", options=options)
print([group.Name for group in reduction.archetype.Groups])
```

```text
['core', 'perimeter']
```

Coarser layouts lose distinctions but conserve the same totals: gains, envelope, airflows,
hot water and energy add up over the merged zones. If you may need several layouts, reduce
once at the default and merge the result instead: `merge` gives the same archetype as
reducing again, without the model or its results. See
[How to merge an archetype to a coarser layout](merge-an-archetype.md).

## Choose the small-group threshold

A group whose share of conditioned floor area is below the threshold is merged into the most
similar group of the same exposure (or, in a layout without exposure, the most similar group).
The default threshold is 5 %. Raise it to drop groups too small to matter; set it to `0` to
keep every group. A small group with no group to merge into is kept:

```python
from archetypal import Layout, ReductionOptions, reduce

options = ReductionOptions(layout=Layout.SPACE_USE, small_group_threshold=0.4)
reduction = reduce("three_zone.idf", "three_zone.sql", options=options)
print([group.Name for group in reduction.archetype.Groups])
for merge in reduction.report.small_group_merges:
    print(merge.key, "->", merge.into_key, f"{merge.share:.2f}")
```

```text
['Office']
('Conference',) -> ('Office',) 0.38
```

The threshold applies once, to the groups of the layout you ask for, and the report lists every
merge in `small_group_merges`.

## Supply the space uses

Reduction finds each zone's space use from the space types declared in the model (`Space`
objects' space type, EnergyPlus 9.6 and later). Zones without one are grouped with the zones
whose loads, schedules and thermostat settings are the same, under a label made from the first
zone's name, such as `use:G_Core`. To name space uses yourself, or to override what the model
says, map zone names to labels:

```python
from archetypal import ReductionOptions, reduce

offices = ["G_Perimeter", "G_Core", "Typical_Perimeter", "Typical_Core", "Top_Perimeter", "Top_Core"]
options = ReductionOptions(space_use_mapping=dict.fromkeys(offices, "Office"))
reduction = reduce("ten_zone_multipliers.idf", "ten_zone_multipliers.sql", options=options)
print([group.Name for group in reduction.archetype.Groups])
```

```text
['Office / core', 'Office / perimeter']
```

The mapping may name some zones only; the others keep the space use reduction finds. A zone
name the model does not have raises `ValueError`. Each group member's `space_use_source` in the
report says what decided its space use: `user`, `space_type` or `signature`.

## Get a schedule as `Schedule:Compact`

SBEM holds schedules as days, weeks and months. To use one in an EnergyPlus model, convert it
with `schedule_compact`, which gives the `Schedule:Compact` object as IDF text, without loss:

```python
from archetypal import reduce
from archetypal.reduction import schedule_compact

reduction = reduce("three_zone.idf", "three_zone.sql")
occupancy = reduction.archetype.Groups[0].Zone.Operations.SpaceUse.Occupancy.Schedule
print(schedule_compact(occupancy).splitlines()[1])
```

```text
  Conference / perimeter occupancy,  !- Name
```

## Check the archetype against the model

An archetype is ready to use once its simulation reproduces the detailed model's energy use.
Build and simulate it with epinterface, then compare both results with `archetypal.compare`:
see [How to check that an archetype reproduces its building](compare-results.md).
