"""The table of removed v2 capabilities (data-model.md, RemovedCapability) and its message."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import pytest

from archetypal import _removed
from archetypal._removed import REMOVED, RemovedCapability, Replacement, raise_removed
from archetypal.errors import RemovedInArchetypal3Error

if TYPE_CHECKING:
    from collections.abc import Sequence

# A row without a replacement must say why: its reason states there is no replacement.
_NO_REPLACEMENT = re.compile(r"\bno\b.*\b(replacement|equivalent)\b", re.IGNORECASE)
_PREFIX = {"name": "archetypal.", "module": "archetypal.", "command": "archetypal ", "option": "archetypal "}


def table_problems(rows: Sequence[RemovedCapability]) -> list[str]:
    """Return every rule of data-model.md that the rows break."""
    problems: list[str] = []
    seen: set[str] = set()
    for row in rows:
        if row.v2_path in seen:
            problems.append(f"{row.v2_path}: duplicate v2_path")
        seen.add(row.v2_path)
        if not row.v2_path.startswith(_PREFIX[row.kind]):
            problems.append(f"{row.v2_path}: a {row.kind} row starts with {_PREFIX[row.kind]!r}")
        if not row.reason.strip():
            problems.append(f"{row.v2_path}: empty reason")
        if row.replacement is None and not _NO_REPLACEMENT.search(row.reason):
            problems.append(f"{row.v2_path}: no replacement and the reason does not say why")
    return problems


def test_removed_table_follows_the_data_model() -> None:
    assert table_problems(REMOVED) == []


_IDF = RemovedCapability(
    kind="name",
    v2_path="archetypal.IDF",
    replacement=Replacement(package="idfkit", target="idfkit.load_idf", docs_url="https://idfkit.example/load"),
    reason="idfkit reads and edits EnergyPlus models.",
    frequent_task="open-and-simulate",
)
_SETTINGS = RemovedCapability(
    kind="name",
    v2_path="archetypal.settings",
    replacement=None,
    reason="archetypal 3 has no global settings, so there is no replacement.",
    frequent_task=None,
)


def test_the_check_catches_broken_rows() -> None:
    no_why = RemovedCapability(kind="name", v2_path="archetypal.x", replacement=None, reason="Gone.")
    bad_prefix = RemovedCapability(kind="command", v2_path="transition", replacement=None, reason="No replacement.")
    problems = table_problems([_IDF, _IDF, no_why, bad_prefix])
    assert any("duplicate" in p for p in problems)
    assert any("does not say why" in p for p in problems)
    assert any("starts with" in p for p in problems)
    assert table_problems([_IDF, _SETTINGS]) == []


def test_reason_is_always_set() -> None:
    with pytest.raises(ValueError, match="reason"):
        RemovedCapability(kind="name", v2_path="archetypal.x", replacement=None, reason=" ")


def test_raise_removed_builds_the_contract_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_removed, "REMOVED", (_IDF, _SETTINGS))
    with pytest.raises(RemovedInArchetypal3Error) as info:
        raise_removed("archetypal.IDF")
    assert str(info.value) == (
        "archetypal.IDF was removed in archetypal 3.\n"
        "Use idfkit.load_idf (idfkit) instead.\n"
        "See https://samuelduchesne.github.io/archetypal/how-to/migrate-from-v2/#archetypalidf"
    )
    assert isinstance(info.value, ImportError)


def test_raise_removed_without_replacement_gives_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(_removed, "REMOVED", (_IDF, _SETTINGS))
    with pytest.raises(RemovedInArchetypal3Error) as info:
        raise_removed("archetypal.settings")
    text = str(info.value)
    assert text.startswith("archetypal.settings was removed in archetypal 3.\n")
    assert _SETTINGS.reason in text
    assert text.endswith("#archetypalsettings")


def test_raise_removed_rejects_unknown_paths() -> None:
    with pytest.raises(LookupError, match=r"archetypal\.not_a_row"):
        raise_removed("archetypal.not_a_row")


@pytest.mark.parametrize(
    ("heading", "anchor"),
    [
        ("archetypal.IDF", "archetypalidf"),
        ("archetypal reduce --all_zones", "archetypal-reduce-all_zones"),
        ("archetypal.umi.UmiTemplateLibrary", "archetypalumiumitemplatelibrary"),
    ],
)
def test_anchor_matches_the_docs_slugs(heading: str, anchor: str) -> None:
    assert _removed.anchor(heading) == anchor
