---
diataxis: how-to
---

# How to read a UMI template library into SBEM archetypes

A UMI template library holds building templates that took years to build; reading it into
SBEM archetypes lets you generate EnergyPlus models from them with epinterface. This guide
reads a library with `archetypal.read_umi`, checks what the translation lost, and handles
libraries that are invalid or must translate without loss. It assumes you have the library's
`.json` file.

## Read the library

Pass the library file to `read_umi`. It returns one archetype per building template, in
template order, and the report of the translation:

```python
from archetypal import read_umi

result = read_umi("BostonTemplateLibrary.json")

for archetype in result.archetypes:
    print(archetype.Name, [group.Name for group in archetype.Groups])
print(result.report.summary)
```

```text
B_Off_0 ['core', 'perimeter']
B_Ret_0 ['core', 'perimeter']
B_Res_0_Masonry ['core', 'perimeter']
B_Res_0_WoodFrame ['core', 'perimeter']
37 values lost (8 lost, 29 unused) in 4 templates and the library.
```

Each archetype has a `core` and a `perimeter` zone group, built from the template's `Core`
and `Perimeter` zone definitions. Their floor-area shares are unset (`None`): as in UMI, the
building's geometry sets them when the archetype is applied.

`read_umi` writes nothing. To keep the result, write it to a directory:

```python
from archetypal import read_umi

result = read_umi("BostonTemplateLibrary.json")
result.write("archetypes")
```

This writes `<archetype name>.sbem.json` for each archetype and
`BostonTemplateLibrary.loss.json`, the report. It refuses to replace existing files; pass
`overwrite=True` to replace them.

If the file is a `.umi` project, extract the library's `.json` file from it first (a `.umi`
file is a zip archive). A legacy XML library must be opened and saved in UMI, which converts
it to JSON. `read_umi` refuses both with `UmiFormatError` and says which.

## Check what the translation lost

The report lists in `losses` every value SBEM does not represent, and in `notes` the
assumptions that lose nothing. Each loss names the template (`subject`), the place in the
library as a JSON pointer (`location`), the value, the rule of the correspondence table and,
when SBEM lacks the field, the upstream item that will add it:

```python
from collections import Counter

from archetypal import read_umi

result = read_umi("BostonTemplateLibrary.json")
print(Counter((loss.kind, loss.rule) for loss in result.report.losses).most_common(5))

for loss in result.report.losses:
    if loss.rule == "building.metadata" and loss.location.endswith("/Lifespan"):
        print(loss.subject, loss.location, loss.value, loss.upstream)
```

Look at the kinds first:

- `lost` and `approximate`: a value SBEM cannot hold (a window's zone-mixing or
  airflow-network settings, a value outside SBEM's range) or holds only approximately (a month
  whose schedule changes part-way, a window of more than four panes reduced to simple glazing).
  Those with `upstream: "UP-9"` are the window settings the fork's UP-9 left out.
- `renamed`: two components of one kind shared a name with different content, or two
  templates shared a name. The later one keeps both, renamed with ` #2`, ` #3`, … in file order.
- `unused`: a component no template uses. It is not translated.

The report is empty of losses only when nothing was lost; its summary then reads
"Nothing was lost.". [Translation report](../reference/translation-report.md) describes every
field, and [UMI correspondence](../reference/umi-correspondence.md) lists what each UMI field
becomes.

## Fix or skip invalid templates

`read_umi` validates the whole library before producing any archetype. A broken reference (a
`$ref` to a missing or later `$id`) raises `UmiFormatError`; a null required reference, a day
without 24 values, year parts that leave a gap or overlap, or a value outside its SBEM range
raises `UmiValidationError`. Both list every problem with its JSON pointer and the template it
affects:

```python
from archetypal import read_umi
from archetypal.errors import UmiValidationError

try:
    result = read_umi("BostonTemplateLibrary.json")
except UmiValidationError as error:
    for problem in error.problems:
        print(problem.pointer, problem.template, problem.rule, problem.message)
```

Fix the library at each pointer and read it again. If you only need the valid templates, skip
the others instead:

```python
from archetypal import read_umi

result = read_umi("BostonTemplateLibrary.json", skip_invalid_templates=True)
```

Each skipped template appears in the report as a `skipped_template` loss that carries its
problems. Broken references are never skipped: they make the whole file unreadable.

## Require a lossless translation

When an archetype must hold everything the library holds, use strict mode. It translates the
whole library, then raises `LossyTranslationError` if `losses` is not empty; the error carries
the report, so you can see what would have been lost:

```python
from archetypal import read_umi
from archetypal.errors import LossyTranslationError

try:
    result = read_umi("BostonTemplateLibrary.json", strict=True)
except LossyTranslationError as error:
    print(error.report.summary)
```

Notes never fail strict mode. A library whose templates use zone mixing or an airflow network
always fails it: SBEM has no field for either.
