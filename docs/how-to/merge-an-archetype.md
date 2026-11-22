---
diataxis: how-to
---

# How to merge an archetype to a coarser layout

A reduction at the default layout keeps one zone group per space use and exposure. A study
often needs fewer groups: one per exposure for a UMI template, or one for the whole building.
`archetypal.merge` regroups an existing reduction without the model or its results, and gives
the same archetype and report as reducing the model again at the coarser layout.

## Merge a reduction in memory

Pass the reduction and the target `Layout`:

```python
from archetypal import Layout, merge, reduce

reduction = reduce("three_zone.idf", "three_zone.sql")
core_perimeter = merge(reduction, Layout.CORE_PERIMETER)

for group in core_perimeter.report.groups:
    print(f"{group.name:12} {group.floor_area_share:.3f}")
```

```text
core         0.240
perimeter    0.760
```

The result is a `Reduction` like the one `reduce` returns. Write it with
`core_perimeter.write(directory, name)`.

## Merge from files, without the model

`merge` reads only the report, so a reduction read back from disk is enough. `Reduction.read`
takes the archetype file and reads `<name>.report.json` beside it:

```python
from archetypal import Layout, merge
from archetypal.reduction import Reduction

reduction = Reduction.read("office.sbem.json")  # reads office.report.json too
single = merge(reduction, Layout.SINGLE_ZONE)
single.write(".", "office_single")
print([group.name for group in single.report.groups])
```

```text
['building']
```

Keep the report with the archetype: without it, `Reduction.read` raises `ReductionError`,
and so does `merge`.

## Choose a target the source can reach

The report keeps every ledger at the finest key (space use, exposure), so `merge` reaches
any layout that is not strictly finer than the source's:

| Source layout | Targets `merge` accepts |
|---|---|
| `SPACE_USE_EXPOSURE` | all four layouts |
| `SPACE_USE` | `SPACE_USE`, `CORE_PERIMETER`, `SINGLE_ZONE` |
| `CORE_PERIMETER` | `CORE_PERIMETER`, `SPACE_USE`, `SINGLE_ZONE` |
| `SINGLE_ZONE` | `SINGLE_ZONE` |

`SPACE_USE` and `CORE_PERIMETER` reach each other, although neither is finer. A strictly
finer target raises `ReductionError`; reduce the model again instead:

```python
from archetypal import Layout, merge
from archetypal.errors import ReductionError
from archetypal.reduction import Reduction

core_perimeter = merge(Reduction.read("office.sbem.json"), Layout.CORE_PERIMETER)
try:
    merge(core_perimeter, Layout.SPACE_USE_EXPOSURE)
except ReductionError as error:
    print(error)
```

```text
merge: layout 'space_use_exposure' is strictly finer than the reduction's 'core_perimeter'; reduce the model again to reach it
```

## See which groups were merged

`report.merged_distinctions` lists, for each resulting group, the finest keys it holds and the
distinctions the layout lost:

```python
from archetypal import Layout, merge
from archetypal.reduction import Reduction

merged = merge(Reduction.read("office.sbem.json"), Layout.CORE_PERIMETER)
for entry in merged.report.merged_distinctions:
    print(entry.into_key, entry.from_keys, entry.lost)
```

```text
('core',) (('Office', 'core'),) ('space_use',)
('perimeter',) (('Conference', 'perimeter'), ('Office', 'perimeter')) ('space_use',)
```

## Change the small-group threshold

`merge` applies the small-group threshold once, to the target layout's groups. It keeps the
source's threshold unless you pass `small_group_threshold`:

```python
from archetypal import Layout, merge
from archetypal.reduction import Reduction

merged = merge(Reduction.read("office.sbem.json"), Layout.SPACE_USE, small_group_threshold=0.4)
for entry in merged.report.small_group_merges:
    print(entry.key, "->", entry.into_key, f"{entry.share:.2f}")
```

```text
('Conference',) -> ('Office',) 0.38
```

The threshold used is recorded with the layout in `report.reproducibility.options`, so the
merged report says how to reproduce it from the model.

To choose the layout before reducing, see [How to reduce a model](reduce-a-model.md). For
every field of the report, see the [reduction report reference](../reference/reduction-report.md).
