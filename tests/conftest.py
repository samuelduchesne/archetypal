"""Shared test configuration: test tiers, the unit-tier time budget and hypothesis profiles."""

from __future__ import annotations

import os
import re
import shutil
import time
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from hypothesis import settings

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence

# The unit tier (the default selection) must finish within this many seconds of wall-clock time.
UNIT_TIER_BUDGET_S = 120.0
# Marker expression of the default selection, as set by `addopts` in pyproject.toml.
DEFAULT_SELECTION = "not energyplus and not reference"
# Per-test timeouts for the slower tiers (seconds; 0 disables the timeout).
TIER_TIMEOUTS_S = {"energyplus": 600, "reference": 0}

settings.register_profile("ci", max_examples=50, deadline=timedelta(milliseconds=500))
settings.register_profile("dev", max_examples=100, deadline=timedelta(milliseconds=500))
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "ci" if os.environ.get("CI") else "dev"))

_session_start: dict[str, float] = {}


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add `--write-libraries DIR`: tests that write a UMI library also save it under DIR."""
    parser.addoption(
        "--write-libraries",
        metavar="DIR",
        default=None,
        help="save every UMI library a test writes under DIR, for tools/basilisk-check (spec 003, research R15)",
    )


@pytest.fixture
def save_library(request: pytest.FixtureRequest) -> Callable[[Path], Path | None]:
    """Return a function that copies a written UMI library under `--write-libraries DIR`.

    Every test that writes a UMI library passes the written file to this function. Without the
    option it does nothing and returns `None`; with it, the file is copied to DIR under a name
    made from the test's id and the file name, so libraries from different tests never clash,
    and the copy's path is returned.
    """
    option: str | None = request.config.getoption("--write-libraries")
    test_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", request.node.nodeid).strip("_")

    def save(path: Path) -> Path | None:
        if option is None:
            return None
        directory = Path(option)
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"{test_id}__{path.name}"
        shutil.copyfile(path, target)
        return target

    return save


def pytest_sessionstart(session: pytest.Session) -> None:
    """Record when the session starts."""
    _session_start["t"] = time.perf_counter()


def pytest_collection_modifyitems(config: pytest.Config, items: Sequence[pytest.Item]) -> None:
    """Give tests of the slower tiers their tier's timeout instead of the unit default."""
    for item in items:
        for marker, timeout in TIER_TIMEOUTS_S.items():
            if item.get_closest_marker(marker) is not None and item.get_closest_marker("timeout") is None:
                item.add_marker(pytest.mark.timeout(timeout))


def pytest_sessionfinish(session: pytest.Session, exitstatus: int) -> None:
    """Fail the default selection when it takes longer than the unit-tier budget."""
    start = _session_start.get("t")
    if start is None or session.config.getoption("markexpr") != DEFAULT_SELECTION:
        return
    elapsed = time.perf_counter() - start
    if elapsed > UNIT_TIER_BUDGET_S:
        reporter = session.config.pluginmanager.get_plugin("terminalreporter")
        if reporter is not None:
            reporter.write_line(
                f"Unit tier took {elapsed:.1f} s, over its {UNIT_TIER_BUDGET_S:.0f} s budget.", red=True
            )
        session.exitstatus = pytest.ExitCode.TESTS_FAILED
