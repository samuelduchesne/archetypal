"""Every `console` block in the docs runs, and shows the output its commands give (FR-024, R5).

The `$ archetypal ...` lines of a page run in order, in one fresh temporary folder per page that
holds a copy of `docs/examples/` (the tutorial's files) and of `tests/docs/examples/` (when it
exists), so a later command sees the files an earlier one wrote, as it does for a reader. Other
`$` lines (`pip`, `curl`, ...) are not run. Lines after a command, up to the next `$` line, are
the output the page shows; when there are any, they must match what the command prints (on
Windows, with its paths written with `/`).

A command must end with status 0, unless the line before the block's fence is
`<!-- console: exit-status N -->`: then every command of that block must end with status N
(4, for example, for a reduction that reports losses).
"""

from __future__ import annotations

import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / "docs"
EXAMPLES = (DOCS / "examples", Path(__file__).resolve().parent / "examples")
PROMPT = "$ "
_STATUS = re.compile(r"^<!--\s*console:\s*exit-status\s+(?P<status>\d+)\s*-->\s*$")
_CONSOLE_BLOCK = re.compile(
    r"^(?P<fence>`{3,}|~{3,})[ \t]*console\b[^\n]*\n(?P<body>.*?)^(?P=fence)[ \t]*$", re.MULTILINE | re.DOTALL
)


@dataclass(frozen=True)
class ConsoleCommand:
    """One `$ archetypal ...` line of a page and the output the page shows after it."""

    page: str
    line: int
    command: str
    output: tuple[str, ...]
    status: int = 0

    @property
    def id(self) -> str:
        """Name the command by page and line, for test ids."""
        return f"{self.page}:{self.line}"


def parse_console_blocks(text: str, page: str) -> list[ConsoleCommand]:
    """Return the `archetypal` commands of every `console` block in a page, with their shown output."""
    commands: list[ConsoleCommand] = []
    for block in _CONSOLE_BLOCK.finditer(text):
        first_line = text.count("\n", 0, block.start("body")) + 1
        status = _block_status(text[: block.start()])
        current: tuple[int, str] | None = None
        output: list[str] = []
        for offset, raw in enumerate(block.group("body").splitlines()):
            if raw.startswith(PROMPT):
                if current is not None:
                    commands.append(_command(page, current, output, status))
                command = raw[len(PROMPT) :].strip()
                current = (first_line + offset, command) if command.split(" ", 1)[0] == "archetypal" else None
                output = []
            elif current is not None:
                output.append(raw)
        if current is not None:
            commands.append(_command(page, current, output, status))
    return commands


def _block_status(before: str) -> int:
    """Return the exit status the `console: exit-status` comment before a block names, or 0."""
    lines = [line.strip() for line in before.splitlines() if line.strip()]
    match = _STATUS.match(lines[-1]) if lines else None
    return 0 if match is None else int(match.group("status"))


def _command(page: str, current: tuple[int, str], output: list[str], status: int) -> ConsoleCommand:
    lines = [line.rstrip() for line in output]
    while lines and not lines[-1]:
        lines.pop()
    return ConsoleCommand(page=page, line=current[0], command=current[1], output=tuple(lines), status=status)


def collect_commands() -> list[ConsoleCommand]:
    """Return every `archetypal` command shown in a `console` block under `docs/`."""
    commands: list[ConsoleCommand] = []
    for page in sorted(DOCS.rglob("*.md")):
        commands.extend(parse_console_blocks(page.read_text(encoding="utf-8"), str(page.relative_to(DOCS))))
    return commands


def _archetypal_executable() -> str:
    script = Path(sys.executable).parent / ("archetypal.exe" if sys.platform == "win32" else "archetypal")
    found = str(script) if script.exists() else shutil.which("archetypal")
    if found is None:
        pytest.fail("the `archetypal` command is not installed in this environment")
    return found


def _posix(line: str) -> str:
    """Write Windows paths with `/`, as the pages show them."""
    return line.replace("\\", "/") if sys.platform == "win32" else line


COMMANDS = collect_commands()
PAGES: dict[str, list[ConsoleCommand]] = {}
for _command_of_page in COMMANDS:
    PAGES.setdefault(_command_of_page.page, []).append(_command_of_page)


@pytest.mark.timeout(120)
@pytest.mark.parametrize("page", list(PAGES), ids=list(PAGES))
def test_console_example(page: str, tmp_path: Path) -> None:
    for examples in EXAMPLES:
        if examples.is_dir():
            shutil.copytree(examples, tmp_path, dirs_exist_ok=True)
    executable = _archetypal_executable()
    for example in PAGES[page]:
        argv = [executable, *shlex.split(example.command)[1:]]
        result = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, check=False)  # noqa: S603
        printed = f"{result.stdout}{result.stderr}"
        assert result.returncode == example.status, (
            f"{example.id}: `{example.command}` ended with status {result.returncode}, not {example.status}:\n{printed}"
        )
        if example.output:
            shown = [_posix(line.rstrip()) for line in printed.rstrip().splitlines()]
            assert tuple(shown) == example.output, f"{example.id}: the page shows other output than the command gives"


def test_collection_works_without_console_blocks() -> None:
    assert all(isinstance(command, ConsoleCommand) for command in COMMANDS)


def test_parse_console_blocks() -> None:
    page = "\n".join([
        "# Page",
        "```console",
        "$ archetypal reduce model.idf weather.epw out",
        "Wrote out/model.json",
        "",
        "$ ls out",
        "model.json",
        "$ archetypal --help  ",
        "```",
        "",
        "```python",
        "print('$ archetypal not console')",
        "```",
        "<!-- console: exit-status 4 -->",
        "~~~console",
        "$ archetypal compare a b",
        "  same",
        "~~~",
    ])
    commands = parse_console_blocks(page, "how-to/x.md")
    assert [(c.line, c.command, c.output, c.status) for c in commands] == [
        (3, "archetypal reduce model.idf weather.epw out", ("Wrote out/model.json",), 0),
        (8, "archetypal --help", (), 0),
        (16, "archetypal compare a b", ("  same",), 4),
    ]
    assert commands[0].id == "how-to/x.md:3"


def test_parse_ignores_pages_without_console_blocks() -> None:
    assert parse_console_blocks("# Title\n\n```bash\n$ archetypal x\n```\n", "index.md") == []
