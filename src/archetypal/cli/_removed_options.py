"""The v2 options and commands archetypal 3 rejects by name (FR-013, research R6).

Each `command` and `option` row of `archetypal._removed.REMOVED` becomes a hidden click option
or command. Its callback raises a usage error (exit status 2) with the row's message, before
any work: options are eager, so they are handled while the command line is parsed, before a
required argument is checked or a sub-command is run. The message names the option as typed
and gives its replacement or the reason it is gone.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import click

from archetypal._removed import REMOVED, RemovedCapability, raise_removed
from archetypal.errors import RemovedInArchetypal3Error

if TYPE_CHECKING:
    from collections.abc import Callable

__all__ = ["removed_command", "removed_options", "removed_rows", "usage_error"]


def removed_rows(command: str) -> list[RemovedCapability]:
    """Return the `option` rows of a command, such as `archetypal reduce`.

    Args:
        command: The command path, `archetypal` for the group.

    Returns:
        The rows whose `v2_path` is the command followed by one flag.
    """
    return [row for row in REMOVED if row.kind == "option" and row.v2_path.rpartition(" ")[0] == command]


def _spelling(row: RemovedCapability) -> str:
    """Return the row as v2 wrote it, short flags first: `archetypal reduce -z/--all_zones`."""
    if row.kind != "option" or not row.aliases:
        return row.v2_path
    command, _, flag = row.v2_path.rpartition(" ")
    return f"{command} {'/'.join((*row.aliases, flag))}"


def usage_error(row: RemovedCapability, ctx: click.Context | None) -> click.UsageError:
    """Return the usage error of a removed option or command.

    Args:
        row: The row of `REMOVED`.
        ctx: The click context, for the usage line.

    Returns:
        The error, whose message is the row's migration message.
    """
    try:
        raise_removed(row.v2_path)
    except RemovedInArchetypal3Error as error:
        message = f"{_spelling(row)} {error.message}"
    else:  # pragma: no cover - raise_removed always raises
        message = row.v2_path
    return click.UsageError(message, ctx)


def _rejecter(row: RemovedCapability) -> Callable[[click.Context, click.Parameter, Any], None]:
    def reject(ctx: click.Context, param: click.Parameter, value: Any) -> None:  # noqa: ANN401 - click's callback
        del param
        if value:
            raise usage_error(row, ctx)

    return reject


def removed_options(command: str) -> list[click.Option]:
    """Return a hidden, eager option for each removed flag of a command.

    Every option is a flag: a value given after it in v2 style is left to the parser, which
    never gets to use it because the callback stops the command first.

    Args:
        command: The command path, `archetypal` for the group.

    Returns:
        The options, in `REMOVED` order.
    """
    options: list[click.Option] = []
    for row in removed_rows(command):
        flag = row.v2_path.rpartition(" ")[2]
        name = "removed_" + flag.lstrip("-").replace("-", "_")
        options.append(
            click.Option(
                [*row.aliases, flag, name],
                is_flag=True,
                hidden=True,
                is_eager=True,
                expose_value=False,
                callback=_rejecter(row),
            )
        )
    return options


def removed_command(name: str) -> click.Command:
    """Return the hidden command of a removed v2 command, such as `transition`.

    It accepts any argument and the removed options of that command, and rejects itself.

    Args:
        name: The command's name.

    Returns:
        The command.

    Raises:
        LookupError: The command is not a `command` row of `REMOVED`.
    """
    path = f"archetypal {name}"
    rows = [row for row in REMOVED if row.kind == "command" and row.v2_path == path]
    if not rows:
        msg = f"{path} is not a removed v2 command"
        raise LookupError(msg)
    row = rows[0]

    def callback(args: tuple[str, ...]) -> None:
        del args
        raise usage_error(row, click.get_current_context())

    return click.Command(
        name,
        callback=callback,
        params=[*removed_options(path), click.Argument(["args"], nargs=-1, type=click.UNPROCESSED)],
        hidden=True,
        add_help_option=False,
        context_settings={"ignore_unknown_options": True, "allow_extra_args": True},
        help=f"Removed in archetypal 3: {row.reason}",
    )
