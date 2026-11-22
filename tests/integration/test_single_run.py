"""The single EnergyPlus run of `reduce(..., simulate=True)` (spec 002 T062, FR-002, quickstart 6).

Reducing `three_zone.idf` without results, with `simulate=True` and the fixture's weather,
runs EnergyPlus once and gives the archetype that reducing with the committed results gives.
The committed results come from the same model, weather and EnergyPlus release, with only the
outputs reduction reads kept, so the two archetypes agree to round-off.
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import TYPE_CHECKING, cast

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction import Reduction

pytestmark = pytest.mark.energyplus

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
FIXTURE_MODELS = FIXTURES / "models"
WEATHER = FIXTURES / "weather" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
REL_TOL = 1e-6
"""Relative tolerance between the two archetypes' numbers (round-off of separate runs)."""


def _differences(a: object, b: object, path: str = "") -> list[str]:
    """Return where two JSON values differ, numbers compared within `REL_TOL`."""
    if isinstance(a, dict) and isinstance(b, dict):
        left, right = cast("dict[str, object]", a), cast("dict[str, object]", b)
        if left.keys() != right.keys():
            return [f"{path}: keys {sorted(left)} != {sorted(right)}"]
        return [d for key in left for d in _differences(left[key], right[key], f"{path}/{key}")]
    if isinstance(a, list) and isinstance(b, list):
        left_items, right_items = cast("list[object]", a), cast("list[object]", b)
        if len(left_items) != len(right_items):
            return [f"{path}: {len(left_items)} items != {len(right_items)}"]
        pairs = zip(left_items, right_items, strict=True)
        return [d for i, (x, y) in enumerate(pairs) for d in _differences(x, y, f"{path}/{i}")]
    if isinstance(a, float | int) and isinstance(b, float | int) and not isinstance(a, bool):
        return [] if math.isclose(a, b, rel_tol=REL_TOL, abs_tol=1e-9) else [f"{path}: {a} != {b}"]
    return [] if a == b else [f"{path}: {a!r} != {b!r}"]


@pytest.fixture(scope="module")
def single_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Reduction, int]:
    """Reduce `three_zone.idf` with `simulate=True`, counting the EnergyPlus runs.

    The simulation cache is pointed at an empty folder, so EnergyPlus really runs.
    """
    import idfkit.simulation  # noqa: PLC0415
    import idfkit.simulation.cache  # noqa: PLC0415

    from archetypal import reduce  # noqa: PLC0415

    calls: list[object] = []
    original = idfkit.simulation.simulate

    def counting(*args: object, **kwargs: object) -> object:
        calls.append(args)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    patch = pytest.MonkeyPatch()
    patch.setattr(idfkit.simulation, "simulate", counting)
    cache = tmp_path_factory.mktemp("cache")
    patch.setattr(idfkit.simulation.cache, "default_simulation_cache_dir", lambda: cache)
    try:
        reduction = reduce(FIXTURE_MODELS / "three_zone.idf", simulate=True, weather=WEATHER)
    finally:
        patch.undo()
    return reduction, len(calls)


def test_runs_energyplus_once(single_run: tuple[Reduction, int]) -> None:
    _, runs = single_run
    assert runs == 1


def test_same_archetype_as_with_committed_results(
    single_run: tuple[Reduction, int], reduced: Callable[..., Reduction]
) -> None:
    from_run, _ = single_run
    committed = reduced("three_zone")
    differences = _differences(
        json.loads(from_run.archetype.model_dump_json()), json.loads(committed.archetype.model_dump_json())
    )
    assert not differences, "\n".join(differences[:20])


def test_report_records_the_weather(single_run: tuple[Reduction, int]) -> None:
    from_run, _ = single_run
    assert from_run.report.reproducibility.weather_sha256 is not None
    assert from_run.report.reproducibility.energyplus == "24.2.0"
