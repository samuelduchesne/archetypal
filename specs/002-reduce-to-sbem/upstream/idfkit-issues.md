# Draft idfkit issues for spec 002

Drafts for the maintainer to file on idfkit's issue tracker. Nothing here has been filed.

- [UP-6: `Schedule:Year` from a pre-22.2 file cannot be evaluated](#up-6)
- [UP-7: typed readers for the static SQLite tables](#up-7)

---

<a id="up-6"></a>

## UP-6 — `Schedule:Year` read from a pre-22.2 file cannot be evaluated

**Title:** `schedules.values()` raises `ValueError: invalid literal for int()` on any
`Schedule:Year` loaded from an EnergyPlus 9.0–22.1 file

**Roadmap item:** UP-6 (blocking for archetypal spec 002's release; bridged meanwhile).

### Summary

EnergyPlus schemas before 22.2 declare the four date fields of `Schedule:Year`
(`start_month`, `start_day`, `end_month`, `end_day`) as `number`; from 22.2 they are
`integer`. idfkit follows the schema, so a file of 9.0–22.1 loads them as `float` (`1.0`).
`idfkit/schedules/year.py`, `_parse_month_day`, then calls `int(str(value))`, which is
`int('1.0')`, and fails. Every `Schedule:Year` read from such a file cannot be evaluated.
Files of 22.2 and later, and objects built in memory, are not affected.

The typed stubs follow the schema too: `ScheduleYearScheduleWeeksGroup_v9_0_to_v22_1`
declares the four fields as `float`, while the current `ScheduleYearScheduleWeeksGroup`
declares `int`. EnergyPlus reads them as whole numbers in every release, so code typed for a
range of releases sees `int | float` for what is always a month or a day.

### Minimal reproduction

idfkit 1.3.0rc2, Python 3.13, no EnergyPlus needed.

```python
"""Schedule:Year read from a pre-22.2 IDF file cannot be evaluated."""

import tempfile
from pathlib import Path

import idfkit
from idfkit import load_idf
from idfkit.schedules import values

HALF = ",".join(["0.5"] * 24)
WEEK = ",".join(["Half"] * 12)
IDF = f"""Version,{{version}};
ScheduleTypeLimits,Fraction,0,1,Continuous;
Schedule:Day:Hourly,Half,Fraction,{HALF};
Schedule:Week:Daily,Week,{WEEK};
Schedule:Year,Year,Fraction,Week,1,1,12,31;
"""

print("idfkit", idfkit.__version__)
tmp = Path(tempfile.mkdtemp())
for version in ("9.2", "22.1", "22.2", "24.2"):
    path = tmp / f"year_{version}.idf"
    path.write_text(IDF.format(version=version))
    doc = load_idf(path)
    year = doc["Schedule:Year"]["Year"]
    start_month = year.schedule_weeks[0].start_month
    try:
        result = f"sum = {sum(values(year, document=doc, year=2023))}"
    except ValueError as exc:
        result = f"ValueError: {exc}"
    print(f"{version:>5}: start_month = {start_month!r:<4} -> {result}")
```

Output:

```text
idfkit 1.3.0rc2
  9.2: start_month = 1.0  -> ValueError: invalid literal for int() with base 10: '1.0'
 22.1: start_month = 1.0  -> ValueError: invalid literal for int() with base 10: '1.0'
 22.2: start_month = 1    -> sum = 4380.0
 24.2: start_month = 1    -> sum = 4380.0
```

### Expected vs actual

| | Expected | Actual (9.0–22.1 files) |
|---|---|---|
| `values(year, ...)` | 8760 values summing to 4380.0, as for 22.2+ | `ValueError: invalid literal for int() with base 10: '1.0'` |
| `year.schedule_weeks[0].start_month` | `1` (`int`) | `1.0` (`float`) |
| Declared type of `start_month` across releases | `int` | `float` for 9.0–22.1, `int` from 22.2 |

### Proposed fix

1. **Evaluator (minimum, before 1.3.0 final).** In `_parse_month_day`, accept numbers as
   well as strings: convert a whole-number `float` to `int` and refuse a fractional one
   (`1.5`) with a clear error, instead of going through `str()`.
2. **Typed fields (preferred).** Parse the four `Schedule:Year` date fields as `int` in
   every release, as EnergyPlus treats them, and declare them `int` in the versioned stubs,
   so that `schedule_weeks[i].start_month` is an `int` at run time whatever the file's
   release. The same applies to other month and day fields that older schemas declare as
   `number` (for example `RunPeriod` begin and end month and day, if affected).

### Why archetypal needs it

archetypal 3 (spec 002) reduces a detailed EnergyPlus model to an archetype and evaluates
every schedule through `idfkit.schedules` rather than its own evaluator. It accepts models
from EnergyPlus 22.1 onwards, so every 22.1 model with a `Schedule:Year` fails today. It
also uses idfkit's typed interface under pyright strict, and relies on `start_month` being
the `int` the stubs declare. Until this is fixed, archetypal keeps a small bridge that
converts the four fields to `int` on a copy of the object before evaluation, and removes it
when the fix is released.

---

<a id="up-7"></a>

## UP-7 — typed readers for EnergyPlus's static SQLite tables

**Title:** Typed readers on `SQLResult` for the static tables (`Zones`, `Surfaces`,
`Constructions`, `ConstructionLayers`, `Materials`, `Nominal*`)

**Roadmap item:** UP-7 (not blocking; bridged meanwhile).

### Summary

`SQLResult` has typed access to time series (`TimeSeriesResult`), tabular reports
(`TabularRow`), variables (`VariableInfo`) and environments (`EnvironmentInfo`). The
static tables EnergyPlus writes to `eplusout.sql` — zone geometry and multipliers, surfaces,
constructions and their layers, materials, and the nominal internal gains — are reachable
only through `SQLResult.query(sql)`, which returns `list[tuple[object, ...]]`. Each caller
must know the column order, write SQL, and cast every cell.

### Minimal reproduction

This is an API gap, not a failure. Reading zone floor areas and multipliers today:

```python
from idfkit.simulation import SQLResult

with SQLResult("eplusout.sql") as sql:
    rows = sql.query(
        "SELECT ZoneName, FloorArea, Volume, Multiplier, ListMultiplier, IsPartOfTotalArea "
        "FROM Zones"
    )
    for name, area, volume, mult, list_mult, in_total in rows:
        # every cell is `object`: a type checker accepts any use, and nothing checks it
        print(name, area * mult * list_mult)  # pyright strict: operator on "object"
```

### Expected vs actual

| | Expected | Actual (1.3.0rc2) |
|---|---|---|
| Zone rows | `list[ZoneInfo]`, frozen dataclasses with typed fields | `list[tuple[object, ...]]` from hand-written SQL |
| Column names | Python attributes, checked by the type checker | positions in a `SELECT` the caller writes |
| Release differences | handled once in idfkit | handled by each caller |

### Proposed API

Follow the existing `TabularRow` and `VariableInfo` pattern: one frozen, slotted dataclass
per table, with snake_case fields, and one method per table on `SQLResult`.

```python
@dataclass(frozen=True, slots=True)
class ZoneInfo:
    index: int
    name: str
    multiplier: int
    list_multiplier: int
    floor_area: float  # m2
    volume: float  # m3
    ceiling_height: float  # m
    is_part_of_total_area: bool
    # ... remaining Zones columns

@dataclass(frozen=True, slots=True)
class SurfaceInfo:
    index: int
    name: str
    class_name: str
    zone_index: int
    construction_index: int
    area: float  # m2, net
    gross_area: float
    azimuth: float  # degrees
    tilt: float  # degrees
    ext_bound_cond: int
    heat_transfer_surf: bool
    # ...

class SQLResult:
    def zones(self) -> list[ZoneInfo]: ...
    def surfaces(self) -> list[SurfaceInfo]: ...
    def constructions(self) -> list[ConstructionInfo]: ...
    def construction_layers(self) -> list[ConstructionLayerInfo]: ...
    def materials(self) -> list[MaterialInfo]: ...  # thickness, conductivity, density, specific heat
    def nominal_people(self) -> list[NominalPeopleInfo]: ...
    def nominal_lighting(self) -> list[NominalLoadInfo]: ...
    def nominal_electric_equipment(self) -> list[NominalLoadInfo]: ...
    # gas, hot water, steam, other equipment, baseboard heaters,
    # infiltration and ventilation alike
```

Notes:

- Index fields could be resolved to names (`zone_name`, `construction_name`) as a
  convenience, since most callers join on them.
- A table missing from an older database should raise a clear error naming the table and
  the EnergyPlus release that introduced it, or return an empty list; the choice is
  idfkit's.
- `query()` stays for everything else.

### Why archetypal needs it

archetypal's reduction (spec 002) takes every quantity EnergyPlus computes from the SQLite
output: zone floor areas with multipliers resolved, surface areas, azimuths and boundary
conditions, layer thermal properties including density and specific heat, and the internal
gains normalised across input methods and releases (`Nominal*` tables). It reads results
only through idfkit and only through typed interfaces (pyright strict). Today it wraps
`query()` in one private module of typed row classes. With these readers in idfkit, that
module is deleted, and every other idfkit user reading these tables gets the same typing.
