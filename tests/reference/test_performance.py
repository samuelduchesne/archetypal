"""Reduction speed on the reference set (T083; SC-008, research R5).

- The largest reference building (most zones) reduces in under 10 s excluding simulation, timed
  here on its migrated model and the detailed results `verification/report.py --run` exported to
  `<reference cache>/results/<id>/` (`<id>.idf`, `<id>.sql`).
- Its schedules evaluate in at most 7 s (R5). If this fails, file the faster evaluation under UP-5
  before falling back to R2's "Schedule Value" outputs.
- The whole set reduces at least 10 times faster than archetypal 2 (`run_v2_baseline.py`), from
  the times in the results file.

Timings mean something only on the benchmark machine (`report.BENCHMARK`); on a smaller machine
the tests are skipped, as they are without the migrated models, the results or the v2 baseline.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

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


def _require_benchmark_machine() -> None:
    info = report.machine()
    if not info["meets_benchmark"]:
        pytest.skip(
            f"this machine ({info['cpu_count']} CPUs, {info['memory_gb']} GB) is below the benchmark machine: "
            f"{report.BENCHMARK['description']}"
        )


def _results() -> dict[str, Any]:
    env = os.environ.get("ARCHETYPAL_REFERENCE_RESULTS_JSON")
    path = Path(env).expanduser() if env else report.default_results(report.default_cache())
    if not path.is_file():
        pytest.skip(
            f"no reference results at {path}: migrate the set (verification/report.py --fetch --migrate, which "
            "needs EnergyPlus's transition programs) and run it (--run)"
        )
    payload: dict[str, Any] = json.loads(path.read_text())
    if payload.get("kind") != "reference":
        pytest.skip(f"{path} holds {payload.get('kind')} results, which are not reference evidence")
    return payload


def _largest() -> tuple[str, Path, Path]:
    """The largest reference building by zone count, with its migrated model and detailed results."""
    cache_dir = report.default_cache()
    candidates: list[tuple[int, str, Path, Path]] = []
    for building in REFERENCE["building"]:
        folder = cache_dir / "results" / building["id"]
        model, sql = folder / f"{building['id']}.idf", folder / f"{building['id']}.sql"
        if model.is_file() and sql.is_file():
            zones = sum(1 for line in model.read_text(errors="replace").splitlines() if line.strip().lower() == "zone,")
            candidates.append((zones, building["id"], model, sql))
    if len(candidates) < len(REFERENCE["building"]):
        pytest.skip(
            f"{len(REFERENCE['building']) - len(candidates)} reference buildings have no migrated model and "
            f"results in {cache_dir / 'results'}: run verification/report.py --migrate and --run first"
        )
    _, building_id, model, sql = max(candidates)
    return building_id, model, sql


def test_the_largest_building_reduces_in_under_10_s() -> None:
    _require_benchmark_machine()
    building_id, model, sql = _largest()
    from archetypal.reduction import reduce  # noqa: PLC0415 - imports epinterface, only when used

    reduce(model, sql)  # warm imports and caches once, as a user's second reduction would
    start = time.perf_counter()
    reduce(model, sql)
    elapsed = time.perf_counter() - start
    print(f"\nSC-008 {building_id}: reduced in {elapsed:.2f} s")
    assert elapsed < report.LARGEST_BUDGET_S, f"{building_id} took {elapsed:.1f} s"


def test_the_largest_building_evaluates_its_schedules_in_7_s() -> None:
    _require_benchmark_machine()
    building_id, model, sql = _largest()
    detailed = report.read_detailed(model, sql)
    print(f"\nR5 {building_id}: schedules evaluated in {detailed.schedule_seconds:.2f} s")
    assert detailed.schedule_seconds <= report.SCHEDULE_BUDGET_S, (
        f"{building_id}: {detailed.schedule_seconds:.1f} s; file the faster evaluation under UP-5 "
        "before falling back to R2's 'Schedule Value' outputs"
    )


def test_the_set_reduces_10_times_faster_than_v2() -> None:
    payload = _results()
    if not payload["machine"].get("meets_benchmark"):
        pytest.skip("the results were timed on a machine below the benchmark machine")
    sc008 = payload["set"]["SC-008"]
    if sc008.get("speedup") is None:
        pytest.skip("no v2 timing in the results: run verification/run_v2_baseline.py, then report.py --run again")
    print(f"\nSC-008: {sc008['speedup']:.1f} times faster than v2 over {sc008['v2_buildings']} buildings both reduced")
    assert sc008["speedup"] >= report.SPEEDUP, f"only {sc008['speedup']:.1f} times faster than v2"
