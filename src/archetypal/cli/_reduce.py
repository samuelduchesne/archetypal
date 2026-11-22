"""`archetypal reduce`: models in, weather file, one UMI library or SBEM archetypes out (FR-012).

Each model is reduced once (spec 002's `reduce`, simulating it once when no results are
given) and written:

- `--to umi` (the default, v2's result): every model at the core/perimeter layout UMI needs,
  written as one library by spec 003's `to_umi`, with `<stem>.<model>.report.json` (002) per
  model and `<stem>.loss.json` (003) beside it. A model that failed is listed in the loss
  report as a `skipped_template` loss, and in the summary.
- `--to sbem`: `<model>.sbem.json` and `<model>.report.json` per model (002's `Reduction.write`).

Nothing is written when an output exists and `--force` is not given, or when every model
fails. `-p N` reduces up to N models at once in separate processes.
"""

from __future__ import annotations

import glob
import multiprocessing
import os
import traceback
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import click

from archetypal.cli._removed_options import removed_options
from archetypal.cli._summary import Failure, RunSummary, count_reduction, count_translation
from archetypal.errors import ArchetypalError, InputError

if TYPE_CHECKING:
    from collections.abc import Sequence

    from archetypal.reduction import Reduction
    from archetypal.reduction.options import ReductionOptions

__all__ = ["expand_models", "reduce_command"]

MODEL_SUFFIXES = (".idf", ".epjson")
"""The model files a directory or pattern expands to (case-insensitive)."""
UMI_DEFAULT = Path("myumitemplate.json")
"""The library `--to umi` writes without `--output`, as archetypal 2 did."""
LAYOUTS = ("space-use-exposure", "space-use", "core-perimeter", "single-zone")
"""`--layout`'s values: 002's layouts, spelt with hyphens."""


def expand_models(arguments: Sequence[str]) -> list[Path]:
    """Expand model arguments into model files.

    A file is kept as given. A directory gives its `*.idf` and `*.epJSON` files, and a glob
    pattern its matching model files, each sorted by name. Arguments keep their order, so that
    `--results` can follow it; a model given twice is kept once.

    Args:
        arguments: Files, directories or glob patterns.

    Returns:
        The model files.

    Raises:
        InputError: A directory holds no model, or a pattern matches none.
    """
    models: list[Path] = []
    for argument in arguments:
        path = Path(argument)
        if path.is_file():
            found = [path]
        elif path.is_dir():
            found = sorted(p for p in path.iterdir() if p.is_file() and p.suffix.casefold() in MODEL_SUFFIXES)
            if not found:
                raise InputError(path, "holds no model; give a folder with .idf or .epJSON files")
        else:
            found = sorted(
                Path(p) for p in glob.glob(argument, recursive=True) if Path(p).suffix.casefold() in MODEL_SUFFIXES
            )
            if not found:
                raise InputError(argument, "matches no model file (.idf or .epJSON)")
        models += [m for m in found if m not in models]
    return models


def _reduce_one(model: Path, results: Path | None, weather: Path | None, options: ReductionOptions) -> Reduction:
    """Reduce one model with spec 002's `reduce`, simulating it once when a weather file is given."""
    from archetypal.reduction import reduce  # noqa: PLC0415 - imports epinterface only when a command runs

    return reduce(model, results, options=options, weather=weather, simulate=weather is not None)


@dataclass(frozen=True)
class _Job:
    model: Path
    results: Path | None
    weather: Path | None
    options: ReductionOptions


def _run(job: _Job) -> Reduction | tuple[Failure, str]:
    """Reduce one model; an error becomes a failure with its traceback (for `--debug`)."""
    try:
        return _reduce_one(job.model, job.results, job.weather, job.options)
    except ArchetypalError as error:
        return Failure(job.model, type(error).__name__, str(error)), traceback.format_exc()
    except Exception as error:  # noqa: BLE001 - one model's unexpected error must not lose the others
        return Failure(job.model, type(error).__name__, str(error) or repr(error)), traceback.format_exc()


def _run_all(jobs: Sequence[_Job], parallel: int) -> list[Reduction | tuple[Failure, str]]:
    workers = (os.cpu_count() or 1) if parallel == -1 else parallel
    if workers <= 1 or len(jobs) <= 1:
        return [_run(job) for job in jobs]
    context = multiprocessing.get_context("spawn")  # the same on every OS, and safe with threads
    with ProcessPoolExecutor(max_workers=min(workers, len(jobs)), mp_context=context) as pool:
        return list(pool.map(_run, jobs))


def _refuse_existing(paths: Sequence[Path], force: bool) -> None:  # noqa: FBT001
    if force:
        return
    for path in paths:
        if path.exists():
            raise InputError(path, "already exists; pass --force to replace it")


def _check_unique(models: Sequence[Path]) -> None:
    seen: dict[str, Path] = {}
    for model in models:
        if model.stem in seen:
            raise InputError(model, f"has the same name as {seen[model.stem]}; their outputs would collide")
        seen[model.stem] = model


@click.command(
    "reduce",
    short_help="Reduce detailed models to a UMI library or SBEM archetypes.",
    params=removed_options("archetypal reduce"),
)
@click.argument("models", nargs=-1, required=True, metavar="MODELS...")
@click.option(
    "-w",
    "--weather",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="EPW file for the single simulation of each model without --results.",
)
@click.option(
    "-o",
    "--output",
    type=click.Path(path_type=Path),
    help="UMI library file (default myumitemplate.json), or folder for SBEM archetypes (default: here).",
)
@click.option(
    "--to",
    "target",
    type=click.Choice(["umi", "sbem"]),
    default="umi",
    show_default=True,
    help="umi: one library, one building template per model, at core/perimeter. sbem: one archetype per model.",
)
@click.option(
    "--results",
    multiple=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
    help="SQLite results of a model's annual run, once per model in the same order; skips the simulation.",
)
@click.option(
    "--layout",
    type=click.Choice(LAYOUTS, case_sensitive=False),
    help="How zones are grouped (--to sbem only; default space-use-exposure).",
)
@click.option(
    "--threshold",
    type=click.FloatRange(0.0, 1.0, max_open=True),
    default=0.05,
    show_default=True,
    help="Share of conditioned floor area under which a group is merged into its most similar one.",
)
@click.option(
    "-p", "--parallel", type=int, default=1, show_default=True, help="Models processed at once; -1 uses every core."
)
@click.option("--force", is_flag=True, help="Overwrite existing outputs and reports.")
@click.pass_context
def reduce_command(  # noqa: PLR0913 - one argument per option of the contract
    ctx: click.Context,
    models: tuple[str, ...],
    weather: Path | None,
    output: Path | None,
    target: str,
    results: tuple[Path, ...],
    layout: str | None,
    threshold: float,
    parallel: int,
    force: bool,  # noqa: FBT001
) -> None:
    """Reduce detailed EnergyPlus models to one UMI library or to SBEM archetypes.

    MODELS are IDF or epJSON files, directories or glob patterns. Each model is simulated once
    with --weather, unless --results gives its SQLite results, then reduced. With --to umi
    (the default) every model becomes one building template of the library, with
    <stem>.<model>.report.json for each model and <stem>.loss.json beside the library. With
    --to sbem each model becomes <model>.sbem.json with <model>.report.json beside it.
    """
    if target == "umi" and layout is not None:
        msg = "--layout is refused with --to umi: a UMI library needs the core-perimeter layout"
        raise click.UsageError(msg, ctx)
    if parallel == 0 or parallel < -1:
        msg = f"{parallel} is not a number of models; give 1 or more, or -1 for every core"
        raise click.BadParameter(msg, ctx, param_hint="'-p' / '--parallel'")
    found = expand_models(models)
    if results and len(results) != len(found):
        msg = f"--results gives {len(results)} files for {len(found)} models; give one per model, in order"
        raise click.UsageError(msg, ctx)
    if weather is None and not results:
        msg = "--weather is required to simulate models that have no --results"
        raise click.UsageError(msg, ctx)
    _check_unique(found)

    from archetypal.reduction.options import Layout, ReductionOptions  # noqa: PLC0415 - only when a command runs

    if target == "umi":
        chosen = Layout.CORE_PERIMETER
        output = UMI_DEFAULT if output is None else output
        planned = [output, _loss_path(output), *(_umi_report(output, m) for m in found)]
    else:
        chosen = Layout(layout.replace("-", "_").casefold()) if layout else Layout.SPACE_USE_EXPOSURE
        output = Path() if output is None else output
        planned = [output / f"{m.stem}{suffix}" for m in found for suffix in (".sbem.json", ".report.json")]
    _refuse_existing(planned, force)

    options = ReductionOptions(layout=chosen, small_group_threshold=threshold)
    jobs = [_Job(m, results[i] if results else None, weather, options) for i, m in enumerate(found)]
    outcomes = _run_all(jobs, parallel)

    summary = RunSummary()
    done: list[tuple[Path, Reduction]] = []
    for job, outcome in zip(jobs, outcomes, strict=True):
        if isinstance(outcome, tuple):
            failure, trace = outcome
            summary.failures.append(failure)
            if ctx.meta.get("archetypal.debug"):
                click.echo(trace, err=True, nl=False)
        else:
            done.append((job.model, outcome))
    summary.models_ok = len(done)
    if done:
        if target == "umi":
            _write_umi(output, done, summary, force=force)
        else:
            _write_sbem(output, done, summary, force=force)
    summary.echo()
    ctx.exit(summary.status)


def _loss_path(library: Path) -> Path:
    return library.with_name(f"{library.stem}.loss.json")


def _umi_report(library: Path, model: Path) -> Path:
    return library.with_name(f"{library.stem}.{model.stem}.report.json")


def _write_sbem(folder: Path, done: Sequence[tuple[Path, Reduction]], summary: RunSummary, *, force: bool) -> None:
    for model, reduction in done:
        archetype, report = reduction.write(folder, model.stem, overwrite=force)
        summary.outputs.append(archetype)
        summary.reports.append(report)
        losses, approximations = count_reduction(reduction.report)
        summary.losses += losses
        summary.approximations += approximations


def _write_umi(library: Path, done: Sequence[tuple[Path, Reduction]], summary: RunSummary, *, force: bool) -> None:
    from archetypal import io  # noqa: PLC0415 - only when a command runs
    from archetypal.umi import Loss, LossKind, TranslationReport, UmiExport, to_umi  # noqa: PLC0415

    export = to_umi([reduction for _, reduction in done])
    losses, approximations = count_translation(export.report)
    for _, reduction in done:
        more_losses, more_approximations = count_reduction(reduction.report)
        losses += more_losses
        approximations += more_approximations
    if summary.failures:
        failed = [
            Loss(
                kind=LossKind.SKIPPED_TEMPLATE,
                subject=failure.model.stem,
                location="",
                value=[f"{failure.error}: {failure.message}"],
                rule="validation.skipped",
                reason="The model could not be reduced, so the library has no building template for it.",
            )
            for failure in summary.failures
        ]
        fields = {name: getattr(export.report, name) for name in TranslationReport.model_fields}
        report = TranslationReport(**{**fields, "losses": [*export.report.losses, *failed]})
        export = UmiExport(text=export.text, report=report)
    written, loss = export.write(library, overwrite=force)
    summary.outputs.append(written)
    for model, reduction in done:
        summary.reports.append(io.write_model(reduction.report, _umi_report(library, model), overwrite=force))
    summary.reports.append(loss)
    summary.losses += losses
    summary.approximations += approximations
