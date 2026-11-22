# Sources of the documentation's example files

The tutorial [Your first UMI library](../tutorials/first-umi-library.md) downloads these files
from the repository at a milestone tag. Each one is a byte-for-byte copy of a test fixture
under `tests/fixtures/`, whose `SOURCES.md` records how it was made; the SHA-256 below lets you
check a copy against its fixture.

| File | Copy of | SHA-256 |
|---|---|---|
| `three_zone.idf` | `tests/fixtures/models/three_zone.idf` | `a821d65d8963d46cd69a61a63bff17b902a68914df7587186262cda9cbc7f07b` |
| `three_zone.sql` | `tests/fixtures/models/three_zone.sql` | `9c3a8c00b0f9087f2de899f980bf6106ea53b76e75627fe58185d9ac04ac4a0b` |
| `chicago.epw` | `tests/fixtures/weather/USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw` | `c7d4efcf93ba316a1d874352e743df5cf137ba5c0e3459eb2dc4b5442d5b7f5c` |

## `three_zone.idf`: the model

A three-zone office in the style of the DOE commercial prototypes (perimeter and core zones,
office and conference space types, a packaged terminal air conditioner per zone), written as an
EnergyPlus 24.2 IDF by `tests/fixtures/regenerate.py` (spec 002, task T028). The script builds
the model in code with idfkit; it is not one of the DOE prototype files. The zones are
`Core`, `North_Perimeter` and `South_Perimeter`, with the HVAC and features listed for
`three_zone` in `tests/fixtures/SOURCES.md`.

Source: archetypal's own repository. Licence: MIT, as archetypal (`LICENSE`).

## `three_zone.sql`: its results

The SQLite output of one annual run of `three_zone.idf` with EnergyPlus 24.2.0 and
`chicago.epw` (hourly reporting, 4 timesteps per hour, design days for sizing only), made by the
same script. The script keeps a cut-down copy: the tables and tabular reports that reduction
reads, and only the report variables and meters of
`specs/002-reduce-to-sbem/contracts/results-requirements.md` that apply to the model, which is
what spec 002's reduction needs.

Source: archetypal's own repository, generated with EnergyPlus. Licence: MIT, as archetypal
(`LICENSE`).

## `chicago.epw`: the weather

Chicago O'Hare International Airport, TMY3 (WMO 725300): the file
`USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw` of the `WeatherData/` folder of the
EnergyPlus 24.2.0 installation, renamed and otherwise unchanged.

Source: the U.S. Department of Energy / NREL TMY3 data set, distributed with EnergyPlus.
Licence: the TMY3 data are in the public domain; EnergyPlus distributes them under its
BSD-3-Clause-style licence (`LICENSE.txt` of the installation).
