"""The `archetypal` command (spec 001, contracts/cli.md; FR-011 to FR-015).

Each command is a thin wrapper over a public function of spec 002 or 003: `reduce` over
`archetypal.reduce` and `archetypal.write_umi`, `merge` over `archetypal.merge`, `compare`
over `archetypal.compare` and `translate` over `archetypal.read_umi` and `archetypal.write_umi`.
The functions are imported when a command runs, so `archetypal --help` and the rejection of a
removed v2 option do no work.

Exit statuses (`_summary.ExitStatus`): 0 success, 1 failure, 2 usage error, 3 partial
failure, 4 success with losses. The command's modules are private; `main` is the entry point.
"""

from __future__ import annotations

import logging
import traceback
from importlib.metadata import PackageNotFoundError, version
from typing import Any

import click

from archetypal.cli._compare import compare_command
from archetypal.cli._merge import merge_command
from archetypal.cli._reduce import reduce_command
from archetypal.cli._removed_options import removed_command, removed_options
from archetypal.cli._summary import ExitStatus
from archetypal.cli._translate import translate_command
from archetypal.errors import ArchetypalError

__all__ = ["main"]

_LOGGER = "archetypal"
_LEVELS = ("debug", "info", "warning", "error")


def _version(distribution: str) -> str:
    try:
        return version(distribution)
    except PackageNotFoundError:
        return "not installed"


def _print_version(ctx: click.Context, param: click.Parameter, value: bool) -> None:  # noqa: FBT001 - click's callback
    del param
    if not value or ctx.resilient_parsing:
        return
    for distribution in ("archetypal", "idfkit", "epinterface"):
        click.echo(f"{distribution} {_version(distribution)}")
    ctx.exit(0)


class _Group(click.Group):
    """The command group: lists commands in the order they were added, and handles errors.

    An archetypal error ends the command with status 1 and its message, which names the input
    at fault. Any other error does too, with its class; `--debug` shows its traceback instead.
    """

    def list_commands(self, ctx: click.Context) -> list[str]:
        """Return the commands in the order they were added (reduce, merge, compare, translate)."""
        del ctx
        return list(self.commands)

    def invoke(self, ctx: click.Context) -> Any:  # noqa: ANN401 - click's signature
        """Run the sub-command, turning its errors into exit statuses."""
        try:
            return super().invoke(ctx)
        except (click.ClickException, click.exceptions.Exit, click.Abort):
            raise
        except ArchetypalError as error:
            click.echo(f"Error: {error}", err=True)
            ctx.exit(ExitStatus.FAILURE)
        except Exception as error:
            if ctx.meta.get("archetypal.debug"):
                click.echo(traceback.format_exc(), err=True, nl=False)
            else:
                click.echo(
                    f"Error: unexpected {type(error).__name__}: {error} (run with --debug for the traceback)", err=True
                )
            ctx.exit(ExitStatus.FAILURE)


@click.group(
    cls=_Group,
    invoke_without_command=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    params=removed_options("archetypal"),
)
@click.option(
    "--version",
    is_flag=True,
    expose_value=False,
    is_eager=True,
    callback=_print_version,
    help="Show archetypal's version, then idfkit's and epinterface's, and exit.",
)
@click.option(
    "--log-level",
    type=click.Choice(_LEVELS, case_sensitive=False),
    default="warning",
    show_default=True,
    help="Log messages of this level and above to stderr.",
)
@click.option("-d", "--debug", is_flag=True, help="Show the traceback of an unexpected error.")
@click.pass_context
def main(ctx: click.Context, log_level: str, debug: bool) -> None:  # noqa: FBT001 - click passes flags as booleans
    """Create, translate and codify building energy archetypes on SBEM.

    Exit statuses: 0 success, 1 failure, 2 usage error, 3 some models failed, 4 success with
    losses or approximations reported.
    """
    ctx.meta["archetypal.debug"] = debug
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())
        ctx.exit(0)
    handler = logging.StreamHandler(click.get_text_stream("stderr"))
    handler.setFormatter(logging.Formatter("%(levelname)s %(name)s: %(message)s"))
    logger = logging.getLogger(_LOGGER)
    previous = logger.level
    logger.addHandler(handler)
    logger.setLevel(log_level.upper())

    def restore() -> None:
        logger.removeHandler(handler)
        logger.setLevel(previous)

    ctx.call_on_close(restore)


main.add_command(reduce_command)
main.add_command(merge_command)
main.add_command(compare_command)
main.add_command(translate_command)
main.add_command(removed_command("transition"))


def __getattr__(name: str) -> Any:  # noqa: ANN401 - PEP 562
    """Raise the migration error for a name of archetypal 2's `archetypal.cli` (FR-016).

    Args:
        name: The attribute looked up on the module.

    Raises:
        RemovedInArchetypal3Error: `name` is a removed v2 name, such as `CliConfig`.
        AttributeError: `name` is anything else.
    """
    from archetypal._removed import REMOVED, raise_removed  # noqa: PLC0415 - only when a lookup fails

    v2_path = f"{__name__}.{name}"
    if any(row.v2_path == v2_path and row.kind == "name" for row in REMOVED):
        raise_removed(v2_path)
    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)
