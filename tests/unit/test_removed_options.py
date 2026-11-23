"""Removed v2 options and commands are named and rejected before any work (FR-013, SC-007, scenario 1.5).

Each `command` and `option` row of `REMOVED` (contracts/cli.md, "Rejected v2 options and
commands") must exit with status 2 and a message that names it and gives its replacement or
the reason it is gone. The options are tried with every spelling v2 had, short flags included.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from archetypal._removed import REMOVED, RemovedCapability
from archetypal.cli import main

MODELS = Path(__file__).resolve().parents[1] / "fixtures" / "models"
ROWS = [row for row in REMOVED if row.kind in {"command", "option"}]
# Every spelling, as (row, flag typed); a command row is typed as its command.
SPELLINGS = [
    (row, flag)
    for row in ROWS
    for flag in ((row.v2_path.split()[-1], *row.aliases) if row.kind == "option" else (row.v2_path.split()[-1],))
]


def run(args: list[str]) -> tuple[int, str]:
    try:
        runner = CliRunner(mix_stderr=False)  # pyright: ignore[reportCallIssue]
    except TypeError:  # click 8.2 always keeps stderr apart
        runner = CliRunner()
    result = runner.invoke(main, args, catch_exceptions=False)
    return result.exit_code, result.stderr


def invocation(row: RemovedCapability, flag: str, model: Path) -> list[str]:
    """Return a v2-style command line that uses the row's option or command."""
    words = row.v2_path.split()[1:]
    if row.kind == "command":
        return [*words, str(model)]
    command = words[:-1]
    if command == ["reduce"]:
        return ["reduce", str(model), flag, "-w", "weather.epw"]
    if command == ["transition"]:
        return ["transition", flag, str(model)]
    return [flag, "reduce", str(model)]


def test_the_contract_rows_and_short_flags_are_in_removed() -> None:
    paths = {row.v2_path: row for row in ROWS}
    for path in (
        "archetypal transition",
        "archetypal --ep_version",
        "archetypal reduce --version",
        "archetypal reduce --all_zones",
        "archetypal --cache-responses",
        "archetypal --data-folder",
        "archetypal --logs-folder",
        "archetypal --imgs-folder",
        "archetypal --cache-folder",
        "archetypal --log-file",
        "archetypal --silent",
        "archetypal --log-name",
        "archetypal --log-filename",
    ):
        assert path in paths
    assert paths["archetypal reduce --version"].aliases == ("-v",)
    assert paths["archetypal reduce --all_zones"].aliases == ("-z",)
    assert paths["archetypal --cache-responses"].aliases == ("-c",)
    assert paths["archetypal --log-file"].aliases == ("-l",)
    assert paths["archetypal --silent"].aliases == ("-s",)


@pytest.mark.parametrize(("row", "flag"), SPELLINGS, ids=[f"{r.v2_path}[{f}]" for r, f in SPELLINGS])
def test_rejected_with_status_2_naming_it_and_its_replacement(
    row: RemovedCapability, flag: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from archetypal.cli import _reduce  # noqa: PLC0415

    def no_work(*args: object) -> object:
        pytest.fail(f"{row.v2_path}: work started before the option was rejected ({args})")

    monkeypatch.setattr(_reduce, "_reduce_one", no_work)
    monkeypatch.chdir(tmp_path)
    code, err = run(invocation(row, flag, MODELS / "bar_building.idf"))
    assert code == 2
    assert flag in err
    assert row.v2_path.split()[-1] in err
    if row.replacement is not None:
        assert row.replacement.target in err
    else:
        assert row.reason in err
    assert list(tmp_path.iterdir()) == []


def test_transition_is_hidden_from_the_command_list() -> None:
    result = CliRunner().invoke(main, ["--help"])
    assert "transition" not in result.output
    assert "--all_zones" not in CliRunner().invoke(main, ["reduce", "--help"]).output


@pytest.mark.parametrize(
    "args",
    [
        ["--data-folder=/tmp/x", "reduce", "m.idf"],
        ["--ep_version=9-2-0", "reduce", "m.idf"],
        ["reduce", "--version=9-2-0", "m.idf"],
    ],
)
def test_a_removed_option_with_its_value_attached_gets_the_migration_message(args: list[str]) -> None:
    from click.testing import CliRunner  # noqa: PLC0415

    from archetypal.cli import main  # noqa: PLC0415

    result = CliRunner().invoke(main, args)
    assert result.exit_code == 2
    assert "does not take a value" not in result.output
    assert "removed" in result.output.casefold() or "archetypal 3" in result.output.casefold()
