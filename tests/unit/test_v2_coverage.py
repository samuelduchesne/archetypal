"""Every public name, module, command and option of archetypal 2 is in archetypal 3 or in `REMOVED`.

`tests/data/v2_surface.json` is written by `verification/v2_surface.py` from the archetypal 2
release (spec 001, SC-003, research R7, data-model.md V2Surface).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TypedDict

import pytest

from archetypal._removed import REMOVED

SURFACE_PATH = Path(__file__).resolve().parents[1] / "data" / "v2_surface.json"

# The archetypal 2 release the surface was taken from. The spec names 2.18.11, but the last
# release on PyPI is 2.18.10 (no 2.18.11 was ever published), so the surface records 2.18.10.
V2_VERSION = "2.18.10"

# The archetypal 3 interface a v2 entry may be kept in (data-model.md, Public interface;
# contracts/cli.md). `archetypal.cli` is private but present: it implements the command line.
V3_NAMES = frozenset(
    f"archetypal.{name}"
    for name in ("__version__", "reduce", "merge", "compare", "Layout", "ReductionOptions", "read_umi", "write_umi")
)
V3_MODULES = frozenset({
    "archetypal",
    "archetypal.cli",
    "archetypal.comparison",
    "archetypal.errors",
    "archetypal.reduction",
    "archetypal.umi",
})
V3_COMMANDS = frozenset(f"archetypal {c}" for c in ("reduce", "merge", "compare", "translate"))
V3_OPTIONS = frozenset({
    "archetypal --version",
    "archetypal --log-level",
    "archetypal --debug",
    "archetypal reduce --output",
    "archetypal reduce --weather",
    "archetypal reduce --parallel",
})


class V2Surface(TypedDict):
    """The fields of data-model.md, V2Surface."""

    archetypal_version: str
    modules: list[str]
    names: list[str]
    commands: list[str]
    options: list[str]


def load_surface() -> V2Surface:
    """Read the committed v2 surface."""
    data: V2Surface = json.loads(SURFACE_PATH.read_text(encoding="utf-8"))
    return data


def option_key(option: str) -> str:
    """Return an option as `REMOVED` writes it: the command, then its last (long) flag.

    `archetypal reduce -z/--all_zones` gives `archetypal reduce --all_zones`.
    """
    command, _, flags = option.rpartition(" ")
    return f"{command} {flags.split('/')[-1]}"


def uncovered(surface: V2Surface) -> list[str]:
    """Return every v2 entry that is neither in archetypal 3 nor in `REMOVED`."""
    removed = {row.v2_path for row in REMOVED}
    missing = [n for n in surface["names"] if n not in removed and n not in V3_NAMES]
    missing += [m for m in surface["modules"] if m not in removed and m not in V3_MODULES]
    missing += [c for c in surface["commands"] if c not in removed and c not in V3_COMMANDS]
    missing += [o for o in surface["options"] if option_key(o) not in removed and option_key(o) not in V3_OPTIONS]
    return missing


def test_surface_is_from_the_last_v2_release() -> None:
    assert load_surface()["archetypal_version"] == V2_VERSION


def test_surface_is_not_empty() -> None:
    surface = load_surface()
    assert "archetypal.IDF" in surface["names"]
    assert "archetypal.idfclass" in surface["modules"]
    assert "archetypal transition" in surface["commands"]
    assert "archetypal reduce -z/--all_zones" in surface["options"]


def test_every_v2_entry_is_kept_or_removed() -> None:
    assert uncovered(load_surface()) == []


def test_removed_rows_do_not_shadow_the_v3_interface() -> None:
    kept = V3_NAMES | V3_MODULES | V3_COMMANDS | V3_OPTIONS
    assert [row.v2_path for row in REMOVED if row.v2_path in kept] == []


def test_every_removed_row_comes_from_v2() -> None:
    surface = load_surface()
    known = {*surface["names"], *surface["modules"], *surface["commands"], *map(option_key, surface["options"])}
    assert [row.v2_path for row in REMOVED if row.v2_path not in known] == []


@pytest.mark.parametrize(
    ("option", "key"),
    [
        ("archetypal reduce -z/--all_zones", "archetypal reduce --all_zones"),
        ("archetypal --data-folder", "archetypal --data-folder"),
        ("archetypal transition -y", "archetypal transition -y"),
    ],
)
def test_option_key(option: str, key: str) -> None:
    assert option_key(option) == key


def test_the_check_finds_a_missing_entry() -> None:
    surface: V2Surface = {
        "archetypal_version": V2_VERSION,
        "modules": ["archetypal", "archetypal.not_listed"],
        "names": ["archetypal.__version__", "archetypal.NotListed"],
        "commands": ["archetypal reduce", "archetypal not-listed"],
        "options": ["archetypal reduce -o/--output", "archetypal -x/--not-listed"],
    }
    assert uncovered(surface) == [
        "archetypal.NotListed",
        "archetypal.not_listed",
        "archetypal not-listed",
        "archetypal -x/--not-listed",
    ]
