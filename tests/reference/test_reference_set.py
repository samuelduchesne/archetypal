"""Spec 002's success criteria over the reference set (T082; quickstart scenario 7).

The evidence is produced by `verification/report.py --run`, which, for each of the 49 reference
buildings, simulates the migrated model with EnergyPlus 24.2, reduces it at every layout, builds
and simulates each archetype with epinterface and compares both results. This module checks the
results file it writes against SC-001 to SC-007 (SC-008 is `test_performance.py`):

- SC-006: every building reduces at every layout, and every zone is in a group or excluded;
- SC-005: every conserved total within 0.1 % at every layout;
- SC-007: merging the finest archetype to each coarser layout equals reducing directly (0.1 %);
- SC-001 to SC-003: total site energy, significant end uses and significant peaks within target,
  at the default layout;
- SC-004: at core/perimeter, v3's error is below v2's for the set and for 90 % of buildings.

The results are looked for at `$ARCHETYPAL_REFERENCE_RESULTS_JSON`, else
`<reference cache>/results/results.json` (`$ARCHETYPAL_REFERENCE_CACHE`, by default
`~/.cache/archetypal/reference-set`). The prototypes are published for EnergyPlus 22.1 and 23.1:
without the migrated models (`report.py --migrate`, which needs EnergyPlus's transition
programs) or without the results, every test is skipped, saying which step is missing.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn

import pytest

if TYPE_CHECKING:
    from verification import report
else:
    _path = Path(__file__).resolve().parents[2] / "verification" / "report.py"
    _spec = importlib.util.spec_from_file_location("reference_report", _path)
    report = importlib.util.module_from_spec(_spec)
    sys.modules["reference_report"] = report
    _spec.loader.exec_module(report)

pytestmark = pytest.mark.reference

REFERENCE = report.load_set(report.DEFAULT_SET)
BUILDINGS = [b["id"] for b in REFERENCE["building"]]


def results_path() -> Path:
    """The results file `report.py --run` wrote."""
    env = os.environ.get("ARCHETYPAL_REFERENCE_RESULTS_JSON")
    return Path(env).expanduser() if env else report.default_results(report.default_cache())


def _missing(reason: str) -> NoReturn:
    """Skip a test whose evidence is missing; fail it where the evidence is required (the CI tier)."""
    if os.environ.get("ARCHETYPAL_REFERENCE_REQUIRED"):
        pytest.fail(reason)
    pytest.skip(reason)


@cache
def results() -> dict[str, Any]:
    """The reference results, or skip with the step that is missing."""
    cache_dir = report.default_cache()
    path = results_path()
    if not path.is_file():
        migrated = cache_dir / "migrated"
        if not migrated.is_dir() or not any(migrated.glob("*.idf")):
            _missing(
                f"no migrated reference models in {migrated}: the prototypes are published for EnergyPlus "
                "22.1/23.1 and must be migrated to 24.2 first (verification/report.py --fetch --migrate, which "
                "needs EnergyPlus's transition programs), then run (--run)"
            )
        _missing(f"no reference results at {path}: run verification/report.py --run")
    payload: dict[str, Any] = json.loads(path.read_text())
    if payload.get("kind") != "reference":
        pytest.skip(f"{path} holds {payload.get('kind')} results, which are not reference evidence")
    return payload


def record(building: str) -> dict[str, Any]:
    """The results record of one building; fails when the run did not reach it."""
    by_id = {r["id"]: r for r in results()["buildings"]}
    assert building in by_id, f"{building} is missing from the results: rerun report.py --run"
    return by_id[building]


def test_the_reference_set_has_49_buildings() -> None:
    assert len(BUILDINGS) == 49


def test_the_results_cover_the_whole_set_and_are_current() -> None:
    payload = results()
    assert sorted(r["id"] for r in payload["buildings"]) == sorted(BUILDINGS)
    assert payload["reference_set_sha256"] == report.sha256_file(report.DEFAULT_SET), "the set changed since the run"
    migrated = report.default_cache() / "migrated"
    for r in payload["buildings"]:
        model = migrated / f"{r['id']}.idf"
        if model.is_file():
            assert r["model_sha256"] == report.sha256_file(model), (
                f"{r['id']}: the migrated model changed since the run"
            )


@pytest.mark.parametrize("building", BUILDINGS)
def test_sc006_reduces_at_every_layout_and_accounts_for_every_zone(building: str) -> None:
    r = record(building)
    assert r["status"] in {"reduced", "ok", "compared_partly"}, f"{r.get('stage')}: {r.get('error')}"
    assert sorted(r["layouts"]) == sorted(report.LAYOUTS)
    for layout, entry in r["layouts"].items():
        zones = entry["sc006"]
        assert zones["passed"], f"{layout}: missing {zones['missing']}, counted twice {zones['counted_twice']}"


@pytest.mark.parametrize("building", BUILDINGS)
def test_sc005_conserved_totals_within_0_1_percent(building: str) -> None:
    for layout, entry in record(building)["layouts"].items():
        check = entry["sc005"]
        assert check["layout_totals"]["passed"], f"{layout}: {check['layout_totals']['failures']}"
        assert check["detailed_anchors"]["passed"], f"{layout}: {check['detailed_anchors']['failures']}"


@pytest.mark.parametrize("building", BUILDINGS)
def test_sc007_merging_equals_reducing_directly(building: str) -> None:
    for layout, entry in record(building)["layouts"].items():
        if layout == report.DEFAULT_LAYOUT:
            continue
        check = entry["sc007"]
        assert check["passed"], f"{layout}: {check['differences']} differences, such as {check['examples']}"


@pytest.mark.parametrize("building", BUILDINGS)
@pytest.mark.parametrize("criterion", ["SC-001", "SC-002", "SC-003"])
def test_sc001_to_sc003_archetype_reproduces_the_building(building: str, criterion: str) -> None:
    entry = record(building)["layouts"][report.DEFAULT_LAYOUT]
    assert "comparison_error" not in entry, entry.get("comparison_error")
    verdict = entry["sc"][criterion]
    if verdict is None:
        pytest.skip(f"{criterion} judges nothing for {building} (no quantity is large enough)")
    failures = [
        f"{row['metric']}: {row['relative']:+.1%} (target ±{row['target']:.0%})"
        for row in entry["comparison"]["rows"]
        if row["within_target"] is False
    ]
    assert verdict, "; ".join(failures)


def test_sc004_more_correct_than_v2_at_core_perimeter() -> None:
    sc004 = results()["set"]["SC-004"]
    if not sc004.get("buildings"):
        pytest.skip(
            "no v2 baseline compared: run verification/run_v2_baseline.py in an archetypal 2 environment, "
            "then report.py --run again"
        )
    assert sc004["v3_mare"] < sc004["v2_mare"], f"v3 {sc004['v3_mare']:.1%} is not below v2 {sc004['v2_mare']:.1%}"
    assert sc004["share_better"] >= report.SC004_SHARE, f"v3 is better on only {sc004['share_better']:.0%} of buildings"
