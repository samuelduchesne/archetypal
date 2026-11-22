"""Run the documentation's Python examples (FR-024, SC-004) with `pytest --markdown-docs docs/`.

Every `python` block runs in a fresh temporary folder that holds the example files the pages
name: `model.idf` (a one-zone office at EnergyPlus 24.2 with an `Office Occupancy` schedule),
`legacy.idf` (the same kind of model at EnergyPlus 22.1) and, when EnergyPlus is installed,
`weather.epw` and `eplusout.sql` (the results of a design-day run of `model.idf`). It also
holds the comparison fixtures of the unit tests (spec 002, T078): `detailed.sql` and
`archetype.sql` (two comparable runs of the bar building, the second with more lighting power)
and `other-period.sql` (a run of the same building over another fortnight).

An HTML comment on the line before a block changes how it runs:

- `<!-- example: needs-energyplus -->` marks the block `energyplus`: it runs in the
  EnergyPlus tier (`-m energyplus`), like the integration tests, not in the default selection.
- `<!-- example: needs-energyplus needs-transition -->` also skips it, with the reason, when
  EnergyPlus's transition programs (`PreProcess/IDFVersionUpdater`) are not installed.
- `<!-- example: skip TODO(<spec>): <reason> -->` skips it with that reason, so the skip shows
  in the test report; it is kept for an example whose functions are not written yet.
"""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Iterator, Sequence

_DIRECTIVE = re.compile(r"^<!--\s*example:\s*(?P<body>.*?)\s*-->\s*$")
_ENERGYPLUS_VERSION = (24, 2, 0)
_WEATHER = "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3"
_COMPARISON = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "comparison"
_COMPARISON_FILES = {"detailed.sql": "base.sql", "archetype.sql": "lights.sql", "other-period.sql": "run_period.sql"}
EXAMPLE_FILES = ("model.idf", "legacy.idf", "weather.epw", "eplusout.sql", *_COMPARISON_FILES)


def _directive(item: pytest.Item) -> str | None:
    """Return the `example:` directive on the line before the item's fence, if any."""
    start_line: int | None = getattr(item, "start_line", None)
    path: Path | None = getattr(item, "path", None)
    if start_line is None or path is None or path.suffix != ".md":
        return None
    lines = path.read_text(encoding="utf-8").splitlines()
    index = start_line - 2  # start_line is the fence's 1-based line number
    while index >= 0 and not lines[index].strip():
        index -= 1
    match = _DIRECTIVE.match(lines[index].strip()) if index >= 0 else None
    return None if match is None else match.group("body")


def _energyplus_dir() -> Path | None:
    from idfkit.exceptions import EnergyPlusNotFoundError  # noqa: PLC0415
    from idfkit.simulation import find_energyplus  # noqa: PLC0415

    try:
        return Path(find_energyplus(version=_ENERGYPLUS_VERSION).install_dir)
    except EnergyPlusNotFoundError:
        return None


def pytest_collection_modifyitems(config: pytest.Config, items: Sequence[pytest.Item]) -> None:
    """Apply each block's `example:` directive."""
    del config
    for item in items:
        body = _directive(item)
        if body is None:
            continue
        words = body.split()
        if words and words[0] == "skip":
            item.add_marker(pytest.mark.skip(reason=body.removeprefix("skip").strip()))
            continue
        if "needs-energyplus" in words:
            item.add_marker(pytest.mark.energyplus)
            item.add_marker(pytest.mark.timeout(300))
        if "needs-transition" in words:
            home = _energyplus_dir()
            if home is None or not (home / "PreProcess" / "IDFVersionUpdater").is_dir():
                item.add_marker(pytest.mark.skip(reason="EnergyPlus's transition programs are not installed"))


def _write_model(path: Path, version: tuple[int, int, int]) -> None:
    from idfkit import (  # noqa: PLC0415
        ZoningScheme,
        create_block,
        footprint_rectangle,
        new_document,
        save_idf,
        set_default_constructions,
    )

    doc = new_document(version=version)
    create_block(
        doc,
        name="Office",
        footprint=footprint_rectangle(width=20.0, depth=10.0),
        floor_to_floor=3.0,
        zoning=ZoningScheme.BY_STOREY,
    )
    doc.add(
        "Material",
        "Concrete",
        roughness="MediumRough",
        thickness=0.2,
        conductivity=1.4,
        density=2240.0,
        specific_heat=900.0,
    )
    doc.add("Construction", "Default Wall", outside_layer="Concrete")
    set_default_constructions(doc, construction_name="Default Wall")
    doc.add("ScheduleTypeLimits", "Fraction", lower_limit_value=0.0, upper_limit_value=1.0, numeric_type="Continuous")
    rules = ["Through: 12/31", "For: Weekdays", "Until: 08:00", "0.0", "Until: 18:00", "1.0", "Until: 24:00", "0.0"]
    rules += ["For: AllOtherDays", "Until: 24:00", "0.0"]
    doc.add(
        "Schedule:Compact",
        "Office Occupancy",
        schedule_type_limits_name="Fraction",
        data=[{"field": rule} for rule in rules],
    )
    doc.add("Output:SQLite", option_type="SimpleAndTabular")
    doc.add("Output:Variable", key_value="*", variable_name="Zone Mean Air Temperature", reporting_frequency="Hourly")
    save_idf(doc, path)


def _simulate(folder: Path, home: Path) -> None:
    from idfkit import load_idf  # noqa: PLC0415
    from idfkit.simulation import simulate  # noqa: PLC0415
    from idfkit.weather import DesignDayManager  # noqa: PLC0415

    weather = home / "WeatherData"
    shutil.copyfile(weather / f"{_WEATHER}.epw", folder / "weather.epw")
    model = load_idf(folder / "model.idf")
    DesignDayManager(weather / f"{_WEATHER}.ddy").apply_to_model(model)
    model.save(folder / "model.idf")
    run = folder / "run"
    with simulate(model, folder / "weather.epw", design_day=True, output_dir=run, output_suffix="L") as result:
        result.raise_for_status()
        if result.sql_path is None:
            pytest.fail("the example run wrote no SQLite output")
        shutil.copyfile(result.sql_path, folder / "eplusout.sql")
    shutil.rmtree(run)


@pytest.fixture(scope="session")
def example_files(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Write the example files once per session and return their folder."""
    folder = tmp_path_factory.mktemp("examples")
    _write_model(folder / "model.idf", _ENERGYPLUS_VERSION)
    _write_model(folder / "legacy.idf", (22, 1, 0))
    for name, fixture in _COMPARISON_FILES.items():
        shutil.copyfile(_COMPARISON / fixture, folder / name)
    home = _energyplus_dir()
    if home is not None:
        _simulate(folder, home)
    return folder


@pytest.fixture(autouse=True)
def in_example_folder(example_files: Path, tmp_path: Path) -> Iterator[Path]:
    """Run each block in its own temporary folder holding a copy of the example files."""
    shutil.copytree(example_files, tmp_path, dirs_exist_ok=True)
    previous = Path.cwd()
    os.chdir(tmp_path)
    try:
        yield tmp_path
    finally:
        os.chdir(previous)
