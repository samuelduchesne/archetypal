---
diataxis: how-to
---

# How to migrate from archetypal 2

archetypal 3 keeps the archetype half of archetypal 2 and hands the rest to idfkit and
epinterface, so most v2 scripts stop at their first import. This guide shows you how to move a
v2 script to archetypal 3: install it, find the replacement of each name you use, and rewrite
the six tasks v2 scripts do most often.

Every removed name raises `RemovedInArchetypal3Error`, whose message names the replacement and
links to its row in this guide:

```text
>>> from archetypal import IDF
RemovedInArchetypal3Error: archetypal.IDF was removed in archetypal 3.
Use idfkit.load_idf (idfkit) instead.
See https://samuelduchesne.github.io/archetypal/how-to/migrate-from-v2/#archetypalidf
```

The error is an `ImportError`, so `except ImportError` in a v2 script still catches it. It is
not an `AttributeError`: `hasattr(archetypal, "IDF")` raises it instead of returning `False`.

## Install archetypal 3 from git

Until v3.0.0 is on PyPI, archetypal 3 is installed from its git repository, together with the
fork of epinterface it depends on: the epinterface releases on PyPI do not have the SBEM
changes archetypal 3 needs, and they require archetypal 2. Install both in a new environment,
so that your v2 environment keeps working while you migrate; [How to install archetypal
3](install.md) gives the commands.

## Find the replacement of each name

Look up each archetypal name, module, command and option your script uses in the tables below.
Each row gives what to use instead, in archetypal 3, idfkit or epinterface, or why nothing
replaces it. Rows linked to an example are rewritten in full in the next section.

<!-- removed-capabilities -->

## Rewrite the frequent tasks

Each task shows the archetypal 2 code first, as text because it does not run with archetypal
3, then the code that does the same work today. The examples read `model.idf`, `weather.epw`
and the other files they name from the current folder; replace them with your own.

### Reduce models to a UMI library {#reduce-to-umi}

archetypal 2 reduced each model to a building template inside `UmiTemplateLibrary`. archetypal
3 reduces each model to an SBEM archetype, then writes the archetypes as one UMI library, one
building template per model, merged to the core and perimeter groups UMI expects.

```text
from archetypal import UmiTemplateLibrary

library = UmiTemplateLibrary.from_idf_files(["office.idf", "school.idf"], weather="weather.epw", name="campus")
library.save("campus.json")
```

<!-- example: skip TODO(001-US1): archetypal.reduce (spec 002) and archetypal.write_umi (spec 003) are not written yet -->

```python
from archetypal import reduce, write_umi

reductions = [reduce(model, weather="weather.epw", simulate=True) for model in ("office.idf", "school.idf")]
report = write_umi(reductions, "campus.json")
print(len(report.losses), "losses; see campus.loss.json")
```

`reduce` simulates each model once, with the outputs reduction needs; pass `results=` with the
SQLite output of an annual run you already have to skip that run. `write_umi` writes
`campus.loss.json` beside the library, listing what the UMI format cannot hold. From the command
line, `archetypal reduce office.idf school.idf -w weather.epw -o campus.json` does the same.

### Open and edit a UMI library {#edit-umi-library}

A UMI library now reads into SBEM archetypes, which you edit as epinterface models and write
back.

```text
from archetypal import UmiTemplateLibrary

library = UmiTemplateLibrary.open("campus.json")
library.BuildingTemplates[0].Name = "Office 2020"
library.save("campus-edited.json")
```

<!-- example: skip TODO(001-US1): archetypal.read_umi and archetypal.write_umi (spec 003) are not written yet -->

```python
from archetypal import read_umi, write_umi

imported = read_umi("campus.json")
office, *others = imported.archetypes
renamed = office.model_copy(update={"Name": "Office 2020"})
write_umi([renamed, *others], "campus-edited.json")
```

`read_umi` returns one archetype per building template, in the library's order, and
`imported.report` lists what the translation could not carry over.

### Open and simulate a model {#open-and-simulate}

idfkit reads, edits and simulates EnergyPlus models.

```text
from archetypal import IDF

idf = IDF("model.idf", epw="weather.epw", design_day=True)
idf.simulate()
```

<!-- example: needs-energyplus -->

```python
from idfkit import load_idf
from idfkit.simulation import simulate

model = load_idf("model.idf")
with simulate(model, "weather.epw", design_day=True, output_dir="run") as result:
    result.raise_for_status()
    print(result.errors.summary())
```

idfkit finds the installed EnergyPlus by itself, and `raise_for_status` raises when EnergyPlus
failed. Drop `output_dir` to run in a temporary folder that is deleted when the `with` block
ends. Use `annual=True` for an annual run.

### Read simulation results {#read-results}

idfkit reads results from EnergyPlus's SQLite output, by variable and key.

```text
from archetypal.reportdata import ReportData

data = ReportData.from_sqlite("eplusout.sql", table_name="Zone Mean Air Temperature")
```

<!-- example: needs-energyplus -->

```python
from idfkit.simulation import SQLResult

with SQLResult("eplusout.sql") as sql:
    temperature = sql.get_timeseries("Zone Mean Air Temperature", "Office", frequency="Hourly")
    print(temperature.units, max(temperature.values))
```

Name the zone with the second argument when a variable is reported for several keys; the
error lists the keys otherwise. After a run, `result.sql` gives the same reader.

### Upgrade a model to a newer EnergyPlus version {#upgrade-version}

idfkit upgrades models with EnergyPlus's own transition programs, which come with EnergyPlus.

```text
from archetypal import IDF

idf = IDF("legacy.idf")
idf.upgrade("24-2-0")
idf.save()
```

<!-- example: needs-energyplus needs-transition -->

```python
from idfkit import load_idf, save_idf
from idfkit.migration import migrate
from idfkit.simulation import find_energyplus

energyplus = find_energyplus()
report = migrate(load_idf("legacy.idf"), target_version=energyplus.version, energyplus=energyplus)
save_idf(report.migrated_model, "upgraded.idf")
```

`migrate` never changes the model it is given and refuses to go backwards. Save the result
under a new name, as above: unlike archetypal 2, nothing overwrites the original file.

### Evaluate a schedule {#evaluate-schedule}

idfkit evaluates every EnergyPlus schedule type without running a simulation.

```text
from archetypal import IDF
from archetypal.schedule import Schedule

idf = IDF("model.idf")
occupancy = Schedule.from_epbunch(idf.getobject("SCHEDULE:COMPACT", "Office Occupancy"))
hourly = occupancy.all_values
```

```python
from datetime import datetime

from idfkit import load_idf
from idfkit.schedules import evaluate, values

model = load_idf("model.idf")
occupancy = model["Schedule:Compact"]["Office Occupancy"]
print(evaluate(occupancy, datetime(2024, 1, 8, 10, 0)))  # 1.0: a Monday at 10:00
hourly = values(occupancy, year=2024)
print(len(hourly))  # 8784 hours in 2024
```

## Expect different reduction results

Reduction was rewritten, so an archetype from archetypal 3 does not match the building template
archetypal 2 made from the same model, even at the core and perimeter layout. archetypal 2's
rules varied by parameter and had known defects: perimeter averages included core zones, zone
multipliers skewed averages, and roofs were ignored when deciding exposure.

The evidence that archetypal 3 is closer to the detailed model is in the success criteria of
[spec 002](https://github.com/samuelduchesne/archetypal/blob/v3/specs/002-reduce-to-sbem/spec.md#measurable-outcomes):
annual site energy, energy by end use and peak demand compared against each reference
building, and against archetypal 2 on the same buildings. To check a model of your own,
simulate it and its archetype, then compare the two runs with `archetypal.compare`.

## Expect only the files you ask for

archetypal 2 created `data`, `logs`, `images` and `cache` folders in the working directory.
archetypal 3 creates none: it writes the outputs you name and their reports, nothing else, and
reads no environment variable. If a script read files from those folders, give it explicit
paths instead.

## Keep archetypal 2 where you still need it

archetypal 2 stays installable with `pip install "archetypal<3"`. It is maintained on the
`v2.x` branch, which receives security fixes only, for 12 months after v3.0.0 is released on
PyPI, or until the TABULA reader of archetypal 3 is released on PyPI, whichever is later. The
end date is set when v3.0.0 is released.

Stay on archetypal 2 for anything archetypal 3 does not replace yet, the TABULA data portal in
particular. Its documentation remains on
[Read the Docs](https://archetypal.readthedocs.io/en/v2.x/).
