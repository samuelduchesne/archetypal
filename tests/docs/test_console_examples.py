"""Every `console` block in the docs runs, and shows the output its commands give (FR-024, R5).

Each `$ archetypal ...` line of a block runs in a fresh temporary folder that holds a copy of
`tests/docs/examples/` (when it exists). Lines after a command, up to the next `$` line, are the
output the page shows; when there are any, they must match what the command prints.
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
EXAMPLES = Path(__file__).resolve().parent / "examples"
PROMPT = "$ "
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

    @property
    def id(self) -> str:
        """Name the command by page and line, for test ids."""
        return f"{self.page}:{self.line}"


def parse_console_blocks(text: str, page: str) -> list[ConsoleCommand]:
    """Return the `archetypal` commands of every `console` block in a page, with their shown output."""
    commands: list[ConsoleCommand] = []
    for block in _CONSOLE_BLOCK.finditer(text):
        first_line = text.count("\n", 0, block.start("body")) + 1
        current: tuple[int, str] | None = None
        output: list[str] = []
        for offset, raw in enumerate(block.group("body").splitlines()):
            if raw.startswith(PROMPT):
                if current is not None:
                    commands.append(_command(page, current, output))
                command = raw[len(PROMPT) :].strip()
                current = (first_line + offset, command) if command.split(" ", 1)[0] == "archetypal" else None
                output = []
            elif current is not None:
                output.append(raw)
        if current is not None:
            commands.append(_command(page, current, output))
    return commands


def _command(page: str, current: tuple[int, str], output: list[str]) -> ConsoleCommand:
    lines = [line.rstrip() for line in output]
    while lines and not lines[-1]:
        lines.pop()
    return ConsoleCommand(page=page, line=current[0], command=current[1], output=tuple(lines))


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


COMMANDS = collect_commands()


@pytest.mark.timeout(120)
@pytest.mark.parametrize("example", COMMANDS, ids=[c.id for c in COMMANDS])
def test_console_example(example: ConsoleCommand, tmp_path: Path) -> None:
    if EXAMPLES.is_dir():
        shutil.copytree(EXAMPLES, tmp_path, dirs_exist_ok=True)
    argv = [_archetypal_executable(), *shlex.split(example.command)[1:]]
    result = subprocess.run(argv, cwd=tmp_path, capture_output=True, text=True, check=False)  # noqa: S603
    assert result.returncode == 0, f"{example.id}: `{example.command}` failed:\n{result.stdout}{result.stderr}"
    if example.output:
        shown = [line.rstrip() for line in (result.stdout + result.stderr).rstrip().splitlines()]
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
        "~~~console",
        "$ archetypal compare a b",
        "  same",
        "~~~",
    ])
    commands = parse_console_blocks(page, "how-to/x.md")
    assert [(c.line, c.command, c.output) for c in commands] == [
        (3, "archetypal reduce model.idf weather.epw out", ("Wrote out/model.json",)),
        (8, "archetypal --help", ()),
        (15, "archetypal compare a b", ("  same",)),
    ]
    assert commands[0].id == "how-to/x.md:3"


def test_parse_ignores_pages_without_console_blocks() -> None:
    assert parse_console_blocks("# Title\n\n```bash\n$ archetypal x\n```\n", "index.md") == []
