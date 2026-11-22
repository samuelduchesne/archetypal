"""`archetypal compare`: compare an archetype's results with the detailed model's (002's `compare`)."""

from __future__ import annotations

import dataclasses
import json
from pathlib import Path

import click

from archetypal.errors import InputError

__all__ = ["compare_command"]


def _number(value: float | None, percent: bool = False) -> str:
    if value is None:
        return "-"
    return f"{value:+.1%}" if percent else f"{value:.4g}"


@click.command("compare", short_help="Compare an archetype's results with the detailed model's.")
@click.argument("detailed_sql", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.argument("archetype_sql", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--weather",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="The weather file both runs should have used; each result is checked against it.",
)
@click.option(
    "--json", "json_path", type=click.Path(dir_okay=False, path_type=Path), help="Also write the comparison as JSON."
)
@click.option("--force", is_flag=True, help="Overwrite an existing --json file.")
def compare_command(
    detailed_sql: Path,
    archetype_sql: Path,
    weather: Path | None,
    json_path: Path | None,
    force: bool,
) -> None:
    """Compare the results of a detailed model and of its archetype.

    DETAILED_SQL and ARCHETYPE_SQL are EnergyPlus SQLite results. The table gives total site
    energy, each end use by fuel and the peak heating and cooling demand, with both values,
    their difference and whether it is within its acceptance target.
    """
    if json_path is not None and json_path.exists() and not force:
        raise InputError(json_path, "already exists; pass --force to replace it")

    from archetypal.comparison import compare  # noqa: PLC0415 - only when run

    result = compare(detailed_sql, archetype_sql, weather=weather)
    header = ("Metric", "Units", "Detailed", "Archetype", "Relative", "Target", "Within")
    rows = [
        (
            row.metric,
            row.units,
            _number(row.detailed),
            _number(row.archetype),
            _number(row.relative, percent=True),
            "-" if row.target is None else f"{row.target:.0%}",
            {True: "yes", False: "NO", None: "-"}[row.within_target],
        )
        for row in result.rows
    ]
    widths = [max(len(str(cells[i])) for cells in (header, *rows)) for i in range(len(header))]
    for cells in (header, *rows):
        click.echo("  ".join(str(cell).ljust(width) for cell, width in zip(cells, widths, strict=True)).rstrip())
    if json_path is not None:
        json_path.parent.mkdir(parents=True, exist_ok=True)
        data = dataclasses.asdict(result)
        json_path.write_text(json.dumps(data, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    failures = len(result.failures)
    click.echo(f"{len(result.rows)} rows compared, {failures} outside their target.", err=True)
    if json_path is not None:
        click.echo(f"Written:\n  {json_path}", err=True)
