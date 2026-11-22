"""`archetypal translate`: UMI library to SBEM archetypes, or SBEM archetypes to a UMI library (003)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click

from archetypal.cli._summary import RunSummary, count_translation
from archetypal.errors import InputError

if TYPE_CHECKING:
    from archetypal.umi.write import ArchetypeLike

__all__ = ["translate_command"]

ARCHETYPE_SUFFIX = ".sbem.json"
REPORT_SUFFIX = ".report.json"


def _read_archetype(path: Path) -> ArchetypeLike:
    """Read an SBEM archetype; with its reduction report beside it, read it as a reduction.

    003 merges a reduction to core and perimeter exactly, through 002's `merge`, and a bare
    archetype approximately.
    """
    from epinterface.sbem.archetype import Archetype  # noqa: PLC0415 - only when run

    from archetypal import io  # noqa: PLC0415
    from archetypal.reduction import Reduction  # noqa: PLC0415

    report = path.with_name(path.name.removesuffix(ARCHETYPE_SUFFIX) + REPORT_SUFFIX)
    if report.is_file():
        return Reduction.read(path, report)
    return io.read_model(Archetype, path)


def _sbem_sources(source: Path) -> list[Path] | None:
    """Return the archetype files of an SBEM source, or `None` for a UMI library."""
    if source.is_dir():
        found = sorted(source.glob(f"*{ARCHETYPE_SUFFIX}"))
        if not found:
            raise InputError(source, f"holds no SBEM archetype (*{ARCHETYPE_SUFFIX})")
        return found
    if source.name.endswith(ARCHETYPE_SUFFIX):
        return [source]
    return None


@click.command("translate", short_help="Translate a UMI library to SBEM archetypes, or back.")
@click.argument("source", type=click.Path(exists=True, path_type=Path))
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    required=True,
    help="Folder for the SBEM archetypes (from UMI), or the UMI library file (from SBEM).",
)
@click.option("--strict", is_flag=True, help="Fail, writing nothing, when anything would be lost.")
@click.option("--force", is_flag=True, help="Overwrite existing outputs and reports.")
@click.pass_context
def translate_command(
    ctx: click.Context,
    source: Path,
    output: Path,
    strict: bool,
    force: bool,
) -> None:
    """Translate between UMI template libraries and SBEM archetypes.

    A UMI library SOURCE gives one <template>.sbem.json per building template in the OUTPUT
    folder, with <library stem>.loss.json. An SBEM archetype SOURCE, or a folder of them, gives
    one UMI library at OUTPUT with <stem>.loss.json beside it. With --strict, any loss is an
    error and nothing is written.
    """
    from archetypal.umi import read_umi, to_umi  # noqa: PLC0415 - only when run

    archetypes = _sbem_sources(source)
    if archetypes is None:
        imported = read_umi(source, strict=strict)
        written = imported.write(output, overwrite=force)
        outputs, reports, report = list(written[:-1]), [written[-1]], imported.report
        count, noun = len(imported.archetypes), "template"
    else:
        export = to_umi([_read_archetype(path) for path in archetypes], strict=strict)
        library, loss = export.write(output, overwrite=force)
        outputs, reports, report = [library], [loss], export.report
        count, noun = len(archetypes), "archetype"
    losses, approximations = count_translation(report)
    summary = RunSummary(
        models_ok=count,
        losses=losses,
        approximations=approximations,
        outputs=outputs,
        reports=reports,
        verb="translated",
        noun=noun,
    )
    summary.echo()
    ctx.exit(summary.status)
