---
diataxis: how-to
---

# How to write SBEM archetypes to a UMI template library

UMI reads building templates from a template library, so archetypes built or edited in SBEM
must be written in that form before UMI can use them. This guide writes one or several
archetypes, or spec 002's reductions, with `archetypal.write_umi`, reads the loss report and
uses strict mode. It assumes you hold the archetypes in Python, read from `.sbem.json` files,
from a UMI library or returned by a reduction.

## Write one library from several archetypes

Pass the archetypes and the library's path to `write_umi`. It writes one building template
per archetype, in the order given, and returns the report of the translation:

```python
from archetypal import read_umi, write_umi

archetypes = read_umi("BostonTemplateLibrary.json").archetypes
report = write_umi(archetypes, "library.json")
print(report.summary)
```

```text
Nothing was lost.
```

Beside `library.json`, `write_umi` writes `library.loss.json`, the same report as JSON. It
writes both files only after the whole translation has succeeded, and it refuses to replace
either; pass `overwrite=True` to replace them.

Each template is named after its archetype. Components the archetypes share, such as a
construction or a schedule, are written once. Two archetypes with the same name, or two
components of one kind with the same name and different content, keep their content: the later
one is renamed with ` #2`, ` #3`, … and the report lists the renaming.

To get the library's text without writing a file, call `to_umi` instead. It takes the same
archetypes and returns a `UmiExport` with the `text` and the `report`; its `write(path)` method
writes both files later:

```python
from archetypal import read_umi
from archetypal.umi import to_umi

archetypes = read_umi("BostonTemplateLibrary.json").archetypes
export = to_umi(archetypes)
export.write("library.json", overwrite=True)
```

## Write archetypes that have more than core and perimeter groups

A UMI template has exactly two zone definitions, `Core` and `Perimeter`, so `write_umi` merges
other layouts to core and perimeter first. How it merges depends on what you give it:

- **A reduction** (spec 002's `Reduction`) is merged with spec 002's `merge` at the
  core/perimeter layout, from the ledgers its report keeps. The result is what reducing the
  detailed model directly to that layout gives. Pass the reduction itself, not its
  `archetype`.
- **A bare archetype** is merged approximately, weighting its groups by their floor-area
  shares. Densities, setpoints, outdoor air and hot water merge exactly with their schedules,
  by the same derivations as spec 002's reduction;
  the envelope, the window, infiltration and the efficiencies need surface areas or energies
  the archetype does not hold, so they are floor-area weighted and reported as `approximate`
  wherever the groups differ.
- **An archetype with one group** is written as both `Core` and `Perimeter`, as one shared zone
  definition, and the report says the zone definition was copied.

An archetype with more than two groups and unset floor-area shares cannot be weighted.
`write_umi` refuses it with `InputError`, naming the archetype: set its shares, or write its
reduction instead.

## Read the loss report

The report lists in `losses` every value the library does not represent, and in `notes` the
defaults and assumptions that lose nothing. Each loss names the archetype (`subject`), the SBEM
field path (`location`, starting with the group), the value, what replaced it and the rule:

```python
from collections import Counter

from archetypal import read_umi, write_umi

report = write_umi(read_umi("BostonTemplateLibrary.json").archetypes, "library.json")
print(Counter((loss.kind, loss.rule) for loss in report.losses))
for loss in report.losses:
    print(loss.subject, loss.location, loss.kind, loss.rule)
```

Look at the kinds first:

- `approximate`: the value is written in another form. A simple-glazing window, which UMI
  lacks, is written as the single glazing layer EnergyPlus derives from its U, SHGC and visible
  transmittance; a layered window is written as its layers, losing nothing. An approximate
  merge adds the parameters it weighted.
- `share_dropped`: a group's floor-area share. UMI templates have none; the building's geometry
  sets the split when the template is used. Unset shares are not a loss.
- `merged` and `copied`: groups merged to core and perimeter, and a single group written twice.
- `lost`: an SBEM field UMI has no place for, such as attic and basement assumptions, a
  thermostat setback or per-orientation window-to-wall ratios.
- `renamed`: a name changed to keep names unique.

[Translation report](../reference/translation-report.md) describes every field of the report.

## Require a lossless translation

When the library must hold everything the archetypes hold, use strict mode. `write_umi`
translates every archetype, then raises `LossyTranslationError` if `losses` is not empty and
writes nothing. The error carries the report:

```python
from archetypal import read_umi, write_umi
from archetypal.errors import LossyTranslationError

archetypes = read_umi("BostonTemplateLibrary.json").archetypes
try:
    write_umi(archetypes, "library.json", strict=True)
except LossyTranslationError as error:
    print(error.report.summary)
```

Notes never fail strict mode. An archetype read from a UMI library passes it, since its layered
windows are written back layer by layer. An archetype with simple glazing, which is what a
reduction gives, always fails it: the window is written as one equivalent glazing layer.

## Check a round trip with `diff_umi`

To see what a library loses on its way through SBEM, read it, write it back and compare the
two files with `diff_umi`. It matches building templates by name and their components through
each template, compares year schedules by their hourly values over the reference year, and
returns every difference located by JSON pointer in the original library:

```python
from archetypal import read_umi, write_umi
from archetypal.umi import diff_umi

imported = read_umi("BostonTemplateLibrary.json")
write_umi(imported.archetypes, "round-trip.json")
diff = diff_umi("BostonTemplateLibrary.json", "round-trip.json")
print(diff.within_tolerance)
for difference in diff.beyond():
    if difference.relevance == "S":
        print(difference.subject, difference.location, difference.via[-1], difference.relative)
```

```text
False
B_Off_0 /YearSchedules/8/Parts /BuildingTemplates/0/Windows/AfnWindowAvailability 1.0
B_Ret_0 /YearSchedules/15/Parts /BuildingTemplates/1/Windows/AfnWindowAvailability 1.0
B_Res_0_Masonry /YearSchedules/1/Parts /BuildingTemplates/2/Windows/AfnWindowAvailability 0.7
B_Res_0_WoodFrame /YearSchedules/1/Parts /BuildingTemplates/2/Windows/AfnWindowAvailability 0.7
```

Each difference has a `relevance` (`S` for a value the simulation reads, `L` for life cycle,
`D` for descriptive), the `original` and `result` values, and a `relative` size, `None` when
the values are not numbers. `via` lists the reference fields through which the value was
reached, from the template down. `within_tolerance` is false when a simulation value differs by
more than `rel_tol`, 0.01 % by default; `beyond()` returns the differences above it.

Every difference should appear in a report. Compare each one with the losses of
`imported.report` (reading) and of the report `write_umi` returned (writing): a loss explains a
difference when it names the same template and its `location` is the difference's location, a
parent of it, or one of its `via` fields. Here each difference is the airflow-network window
availability schedule, which SBEM cannot hold yet, and `imported.report` lists it as lost with
`"upstream": "UP-9"`.

`diff_archetypes(a, b)` does the same for two SBEM archetypes, located by field path
(`perimeter.Operations.SpaceUse.Lighting.PowerDensity`). Use it for the other direction: write
an archetype, read the library back and compare.
