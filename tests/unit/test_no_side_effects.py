"""Importing archetypal has no side effects (FR-006, SC-006, research R10)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

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
    return {(str(p.relative_to(root)), p.stat().st_size if p.is_file() else -1) for p in root.rglob("*")}


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
