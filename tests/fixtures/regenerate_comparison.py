"""Rebuild the small result fixtures of the comparison tests (spec 002, tasks T074 and T075).

Each fixture is a two-week run of ``tests/fixtures/models/bar_building.idf`` (two zones, ideal
loads) with EnergyPlus 24.2, cut down to what ``archetypal.comparison`` reads and saved as
``tests/fixtures/comparison/<name>.sql``. ``base`` is the reference; every other fixture
changes one thing from it:

| Fixture | Change from ``base`` | Comparable with ``base``? |
|---|---|---|
| ``lights`` | lighting power density 14 W/m² instead of 10 | yes |
| ``weather`` | Duluth TMY3 instead of Chicago O'Hare TMY3 | no: weather |
| ``run_period`` | 29 March to 11 April instead of 15 to 28 March | no: run period |
| ``ip_units`` | tabular reports in inch-pound units | no: units |
| ``timestep`` | 6 timesteps per hour instead of 4 | no: timestep |
| ``frequency`` | meters reported every timestep instead of hourly | no: reporting frequency |
| ``everything`` | all five incomparable changes at once | no: all five |

Usage (needs EnergyPlus 24.2; not run by the test suite)::

    uv run python tests/fixtures/regenerate_comparison.py            # all fixtures
    uv run python tests/fixtures/regenerate_comparison.py base lights
"""

from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

from idfkit import load_idf
from idfkit.simulation import find_energyplus, simulate

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

    from idfkit import AnyIDFDocument

HERE = Path(__file__).resolve().parent
MODEL = HERE / "models" / "bar_building.idf"
OUT_DIR = HERE / "comparison"
CHICAGO = HERE / "weather" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
DULUTH_NAME = "USA_MN_Duluth.Intl.AP.727450_TMY3.epw"

KEEP_TABLES = (
    "Simulations",
    "EnvironmentPeriods",
    "Time",
    "ReportDataDictionary",
    "ReportData",
    "TabularData",
    "Strings",
    "StringTypes",
)
KEEP_REPORTS = ("AnnualBuildingUtilityPerformanceSummary", "InputVerificationandResultsSummary")
KEEP_VARIABLES = ("Zone Air System Sensible Heating Energy", "Zone Air System Sensible Cooling Energy")


def _run_period(doc: AnyIDFDocument, begin: tuple[int, int], end: tuple[int, int]) -> None:
    period = next(iter(doc["RunPeriod"]))
    period.begin_month, period.begin_day_of_month = begin
    period.end_month, period.end_day_of_month = end


def _lights(doc: AnyIDFDocument) -> None:
    next(iter(doc["Lights"])).watts_per_floor_area = 14.0


def _ip_units(doc: AnyIDFDocument) -> None:
    next(iter(doc["Output:SQLite"])).unit_conversion_for_tabular_data = "InchPound"
    next(iter(doc["OutputControl:Table:Style"])).unit_conversion = "InchPound"


def _timestep(doc: AnyIDFDocument) -> None:
    next(iter(doc["Timestep"])).number_of_timesteps_per_hour = 6


def _frequency(doc: AnyIDFDocument) -> None:
    for meter in doc["Output:Meter"]:
        meter.reporting_frequency = "Timestep"


def _later(doc: AnyIDFDocument) -> None:
    _run_period(doc, (3, 29), (4, 11))


def _everything(doc: AnyIDFDocument) -> None:
    _later(doc)
    _ip_units(doc)
    _timestep(doc)
    _frequency(doc)


# name -> (change to the model, uses Duluth weather)
VARIANTS: dict[str, tuple[Callable[[AnyIDFDocument], None], bool]] = {
    "base": (lambda _doc: None, False),
    "lights": (_lights, False),
    "weather": (lambda _doc: None, True),
    "run_period": (_later, False),
    "ip_units": (_ip_units, False),
    "timestep": (_timestep, False),
    "frequency": (_frequency, False),
    "everything": (_everything, True),
}


def trim_sql(src: Path, dst: Path) -> None:
    """Copy an EnergyPlus SQLite file keeping only what the comparison reads."""
    shutil.copyfile(src, dst)
    con = sqlite3.connect(dst)
    try:
        cur = con.cursor()
        for (name,) in cur.execute("SELECT name FROM sqlite_master WHERE type='view'").fetchall():
            if name != "TabularDataWithStrings":
                cur.execute(f'DROP VIEW "{name}"')
        for (name,) in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall():
            if name not in KEEP_TABLES:
                cur.execute(f'DROP TABLE "{name}"')
        marks = ",".join("?" for _ in KEEP_VARIABLES)
        cur.execute(
            f"DELETE FROM ReportDataDictionary WHERE IsMeter = 0 AND Name NOT IN ({marks})",  # noqa: S608
            KEEP_VARIABLES,
        )
        cur.execute(
            "DELETE FROM ReportData WHERE ReportDataDictionaryIndex NOT IN "
            "(SELECT ReportDataDictionaryIndex FROM ReportDataDictionary)"
        )
        marks = ",".join("?" for _ in KEEP_REPORTS)
        cur.execute(
            "DELETE FROM TabularData WHERE ReportNameIndex NOT IN "  # noqa: S608
            f"(SELECT StringIndex FROM Strings WHERE Value IN ({marks}))",
            KEEP_REPORTS,
        )
        cur.execute(
            "DELETE FROM Strings WHERE StringIndex NOT IN ("
            "SELECT ReportNameIndex FROM TabularData UNION SELECT ReportForStringIndex FROM TabularData "
            "UNION SELECT TableNameIndex FROM TabularData UNION SELECT RowNameIndex FROM TabularData "
            "UNION SELECT ColumnNameIndex FROM TabularData UNION SELECT UnitsIndex FROM TabularData)"
        )
        con.commit()
        cur.execute("VACUUM")
    finally:
        con.close()


def run(name: str) -> None:
    """Simulate one variant and write its cut-down results."""
    change, duluth = VARIANTS[name]
    doc = load_idf(MODEL)
    _run_period(doc, (3, 15), (3, 28))
    change(doc)
    weather = CHICAGO
    if duluth:
        weather = Path(find_energyplus(version=(24, 2, 0)).install_dir) / "WeatherData" / DULUTH_NAME
    OUT_DIR.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=f"comparison_{name}_") as tmp:
        result = simulate(doc, weather, output_dir=tmp, expand_objects=False, timeout=600)
        print(f"{name}: {result.errors.summary()}")
        if not result.success or result.errors.has_severe or result.sql_path is None:
            raise SystemExit(f"{name}: simulation failed; see the summary above")  # noqa: TRY003
        trim_sql(result.sql_path, OUT_DIR / f"{name}.sql")
    print(f"{name}: wrote comparison/{name}.sql ({(OUT_DIR / f'{name}.sql').stat().st_size / 1e3:.0f} kB)")


def main(argv: Sequence[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("names", nargs="*", help=f"fixtures to rebuild, among {', '.join(VARIANTS)} (default: all)")
    args = parser.parse_args(argv)
    names: list[str] = list(args.names) or list(VARIANTS)
    unknown = sorted(set(names) - set(VARIANTS))
    if unknown:
        parser.error(f"unknown fixture(s): {', '.join(unknown)}")
    for name in names:
        run(name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
