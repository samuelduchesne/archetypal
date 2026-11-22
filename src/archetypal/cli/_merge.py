"""`archetypal merge`: merge an SBEM archetype to a coarser layout, without the model (002's `merge`)."""

from __future__ import annotations

from pathlib import Path

import click

from archetypal.cli._reduce import LAYOUTS
from archetypal.cli._summary import RunSummary, count_reduction
from archetypal.errors import InputError

__all__ = ["merge_command"]

ARCHETYPE_SUFFIX = ".sbem.json"


def _stem(path: Path) -> str:
    """Return the name of `<name>.sbem.json`, or refuse another file name."""
    if not path.name.endswith(ARCHETYPE_SUFFIX):
        raise InputError(path, f"is not an SBEM archetype file; its name must end with {ARCHETYPE_SUFFIX}")
    return path.name.removesuffix(ARCHETYPE_SUFFIX)


@click.command("merge", short_help="Merge an SBEM archetype to a coarser layout.")
@click.argument("archetype", type=click.Path(exists=True, dir_okay=False, path_type=Path))
@click.option(
    "--layout", type=click.Choice(LAYOUTS, case_sensitive=False), required=True, help="The coarser layout to merge to."
)
@click.option(
    "-o",
    "--output",
    type=click.Path(dir_okay=False, path_type=Path),
    help="The merged archetype, <name>.sbem.json (default: <name>-<layout>.sbem.json beside ARCHETYPE).",
)
@click.option(
    "--threshold",
    type=click.FloatRange(0.0, 1.0, max_open=True),
    help="Small-group threshold of the merged groups (default: the reduction's).",
)
@click.option("--force", is_flag=True, help="Overwrite existing outputs and reports.")
@click.pass_context
def merge_command(
    ctx: click.Context,
    archetype: Path,
    layout: str,
    output: Path | None,
    threshold: float | None,
    force: bool,
) -> None:
    """Merge an SBEM archetype to a coarser layout, from its reduction report.

    ARCHETYPE is a <name>.sbem.json file written by `archetypal reduce --to sbem`, with its
    <name>.report.json beside it. The merged archetype is written with its own report beside it.
    """
    name = _stem(archetype)
    if output is None:
        output = archetype.with_name(f"{name}-{layout.casefold()}{ARCHETYPE_SUFFIX}")
    target = _stem(output)
    for path in (output, output.with_name(f"{target}.report.json")):
        if path.exists() and not force:
            raise InputError(path, "already exists; pass --force to replace it")

    from archetypal.reduction import Reduction, merge  # noqa: PLC0415 - imports epinterface only when run
    from archetypal.reduction.options import Layout  # noqa: PLC0415

    merged = merge(
        Reduction.read(archetype), Layout(layout.replace("-", "_").casefold()), small_group_threshold=threshold
    )
    written, report = merged.write(output.parent, target, overwrite=force)
    losses, approximations = count_reduction(merged.report)
    summary = RunSummary(
        models_ok=1, losses=losses, approximations=approximations, outputs=[written], reports=[report], verb="merged"
    )
    summary.echo()
    ctx.exit(summary.status)
