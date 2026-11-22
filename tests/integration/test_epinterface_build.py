"""epinterface builds and simulates each fixture's archetype without modification (spec 002 T063, FR-003).

Each fixture model is reduced with its committed results; the archetype is written and read
back, then given to the fork's `Model.from_archetype` on a shoebox drawn from the archetype's
own geometry characteristics (storeys, conditioned floor area, facade area by orientation). The
shoebox and the weather are the only things the test supplies: the archetype itself is used as
it is. EnergyPlus
must finish the annual run with no severe error, and epinterface's results must be complete.

Each run's severe-error count and wall time are printed (`pytest -s` shows them) for the
coordinator's record of FR-003.
"""

from __future__ import annotations

import math
import re
import time
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable

    from epinterface.geometry import ShoeboxGeometry
    from epinterface.sbem.archetype import Archetype

    from archetypal.reduction import Reduction

pytestmark = pytest.mark.energyplus

FIXTURES = ("three_zone", "bar_building", "ten_zone_multipliers", "ten_zone_explicit")
_SEVERE = re.compile(r"\*\*\s*Severe\s*\*\*")


@pytest.fixture(scope="module")
def weather_zip() -> Path:
    """Return the weather epinterface ships with (Boston Logan, TMYx).

    epinterface sizes with the `Winter Extreme` and `Summer Extreme` weather-file condition
    periods of a climate.onebuilding.org `.ddy` file; the `.ddy` file EnergyPlus ships for
    the fixtures' Chicago weather has design days only, so epinterface would request zone
    sizing without a design environment. FR-003 is about building and simulating the
    archetype, which any climate shows.
    """
    from epinterface.data import DefaultEPWZipPath  # noqa: PLC0415

    return Path(DefaultEPWZipPath)


def shoebox(archetype: Archetype) -> ShoeboxGeometry:
    """Return a shoebox with the archetype's storeys, floor area and facade proportions.

    The footprint is the conditioned floor area over the storeys; its sides are in the ratio of
    the north to the east facade area, and the floor-to-floor height gives the north facade's
    area. Core/perimeter zoning is used whenever a group is a core group.
    """
    from epinterface.geometry import ShoeboxGeometry  # noqa: PLC0415

    geometry = archetype.Geometry
    storeys = geometry.Storeys or 1
    area = geometry.ConditionedFloorArea
    assert area is not None
    facade = geometry.FacadeAreaPerFloorArea or {}
    north, east = facade.get("N", 0.0), facade.get("E", 0.0)
    footprint = area / storeys
    width = math.sqrt(footprint * north / east) if north > 0 and east > 0 else math.sqrt(footprint)
    depth = footprint / width
    height = north * area / (storeys * width) if north > 0 else 3.0
    # A core only when the archetype has one: a perimeter-only archetype gives every zone a facade.
    zoning = "core/perim" if any(g.Exposure == "core" for g in archetype.Groups) else "by_storey"
    return ShoeboxGeometry(
        x=0.0, y=0.0, w=width, d=depth, h=height, num_stories=storeys, zoning=zoning, perim_depth=min(4.5, depth / 3)
    )


@pytest.mark.parametrize("fixture", FIXTURES)
def test_epinterface_builds_and_simulates(
    fixture: str,
    reduced: Callable[..., Reduction],
    weather_zip: Path,
    tmp_path: Path,
) -> None:
    from epinterface.sbem.builder import Model  # noqa: PLC0415

    from archetypal.reduction import Reduction  # noqa: PLC0415

    archetype_path, _ = reduced(fixture).write(tmp_path / "archetype", fixture)
    archetype = Reduction.read(archetype_path).archetype

    model = Model.from_archetype(archetype, shoebox(archetype), Weather=weather_zip)  # pyright: ignore[reportUnknownMemberType]
    start = time.perf_counter()
    result = model.run(weather_dir=tmp_path / "weather", eplus_parent_dir=tmp_path)
    elapsed = time.perf_counter() - start
    result.sql.close()

    severe = len(_SEVERE.findall(result.err_text))
    print(f"\nFR-003 {fixture}: {len(archetype.Groups)} groups, {severe} severe errors, {elapsed:.1f} s")
    assert severe == 0, result.err_text
    assert "EnergyPlus Completed Successfully" in result.err_text
    assert result.energy_and_peak.notna().all()  # pyright: ignore[reportUnknownMemberType]
