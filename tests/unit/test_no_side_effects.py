"""Importing archetypal or running a command has no side effects (FR-006, SC-006, research R10)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import pytest

# Run in a fresh interpreter: record every environment read and the root logger's handlers
# around `import archetypal`, and print them as JSON.
_PROBE = r"""
import json
import logging
import os

reads = []


class RecordingEnviron(type(os.environ)):
    def __getitem__(self, key):
        reads.append(key)
        return super().__getitem__(key)

    def __contains__(self, key):
        reads.append(key)
        return super().__contains__(key)

    def get(self, key, default=None):
        reads.append(key)
        return super().get(key, default)


original = os.environ
os.environ = RecordingEnviron(
    original._data, original.encodekey, original.decodekey, original.encodevalue, original.decodevalue
)
root_before = list(logging.getLogger().handlers)

import archetypal

own = logging.getLogger("archetypal")
print(json.dumps({
    "reads": [k for k in reads if str(k).startswith("ARCHETYPAL")],
    "root_unchanged": logging.getLogger().handlers == root_before,
    "own_handlers": [type(h).__name__ for h in own.handlers],
    "version": archetypal.__version__,
}))
"""


def _tree(root: Path) -> set[tuple[str, int]]:
    return {(p.relative_to(root).as_posix(), p.stat().st_size if p.is_file() else -1) for p in root.rglob("*")}


def test_import_has_no_side_effects(tmp_path: Path) -> None:
    home = tmp_path / "home"
    work = tmp_path / "work"
    tmp = tmp_path / "tmp"
    for folder in (home, work, tmp):
        folder.mkdir()
    env = {
        **os.environ,
        "HOME": str(home),
        "USERPROFILE": str(home),
        "TMPDIR": str(tmp),
        "TEMP": str(tmp),
        "TMP": str(tmp),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local" / "share"),
        "XDG_STATE_HOME": str(home / ".local" / "state"),
        "ARCHETYPAL_CACHE": str(home / "cache"),
        "ARCHETYPAL_DATA": str(home / "data"),
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    before = _tree(tmp_path)

    completed = subprocess.run(  # noqa: S603 - our own interpreter and a fixed script
        [sys.executable, "-c", _PROBE], cwd=work, env=env, capture_output=True, text=True, check=True, timeout=60
    )

    assert _tree(tmp_path) == before
    probe = json.loads(completed.stdout)
    assert probe["reads"] == []
    assert probe["root_unchanged"] is True
    assert probe["own_handlers"] == ["NullHandler"]
    assert probe["version"]
    assert completed.stderr == ""


# --- Running a command (spec 001, US1: T029) ------------------------------------------------------

_FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _invoke(args: list[str]) -> int:
    from click.testing import CliRunner  # noqa: PLC0415

    from archetypal.cli import main  # noqa: PLC0415

    return CliRunner().invoke(main, args, catch_exceptions=False).exit_code


def test_commands_write_only_their_outputs_and_reports(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, cli_reductions: list[tuple[str, str]]
) -> None:
    import logging  # noqa: PLC0415

    del cli_reductions
    home, work = tmp_path / "home", tmp_path / "work"
    for folder in (home, work):
        folder.mkdir()
    for name, value in (("HOME", home), ("USERPROFILE", home), ("TMPDIR", tmp_path / "tmp")):
        monkeypatch.setenv(name, str(value))
    (tmp_path / "tmp").mkdir()
    monkeypatch.chdir(work)
    models = _FIXTURES / "models"
    root_before = list(logging.getLogger().handlers)
    own_before = list(logging.getLogger("archetypal").handlers)
    before = _tree(tmp_path)

    sql = ["--results", str(models / "bar_building.sql")]
    assert _invoke(["reduce", str(models / "bar_building.idf"), *sql, "-o", "lib.json"]) == 4
    assert _invoke(["reduce", str(models / "bar_building.idf"), *sql, "--to", "sbem", "-o", "sbem"]) == 4
    merged = ["merge", "sbem/bar_building.sbem.json", "--layout", "single-zone", "-o", "merged/bar.sbem.json"]
    assert _invoke(merged) in {0, 4}
    detailed, archetype = models / "ten_zone_multipliers.sql", models / "ten_zone_explicit.sql"
    assert _invoke(["compare", str(detailed), str(archetype), "--json", "comparison.json"]) == 0
    assert _invoke(["translate", str(_FIXTURES / "umi" / "BostonTemplateLibrary_2.json"), "-o", "boston"]) == 4

    added = {path for path, _ in _tree(tmp_path) - before}
    boston = {p for p in added if p.startswith("work/boston/")}
    assert added - boston == {
        "work/lib.json",
        "work/lib.loss.json",
        "work/lib.bar_building.report.json",
        "work/sbem",
        "work/sbem/bar_building.sbem.json",
        "work/sbem/bar_building.report.json",
        "work/merged",
        "work/merged/bar.sbem.json",
        "work/merged/bar.report.json",
        "work/comparison.json",
        "work/boston",
    }
    assert all(p.endswith((".sbem.json", ".loss.json")) for p in boston)
    assert logging.getLogger().handlers == root_before
    assert logging.getLogger("archetypal").handlers == own_before
