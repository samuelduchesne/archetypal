"""UMI round trips over spec 002's reference set (spec 003 T066; SC-002, SC-004, SC-006).

For each of the 49 reference buildings (`verification/reference_set.toml`), the building is
reduced from its model and simulation results, its core/perimeter archetype is written with
`write_umi`, read back, and `diff_archetypes` must find nothing apart from reported losses
(SC-004). The audit of `tests/unit/umi/test_audit.py` then runs on the library written
(SC-006). With `--write-libraries DIR` each library is saved under DIR for
`tools/basilisk-check` (SC-002, `.github/workflows/reference.yml`).

Reducing needs each building's model in EnergyPlus 24.2 and its results. The prototypes are
published for EnergyPlus 22.1 and 23.1, and migrating them needs EnergyPlus's transition
programs, so the inputs are looked for, in order, in:

1. `$ARCHETYPAL_REFERENCE_RESULTS/<id>/`;
2. `verification/results/<id>/` (committed results);
3. `<reference cache>/results/<id>/` (`$ARCHETYPAL_REFERENCE_CACHE`, by default
   `~/.cache/archetypal/reference-set`, where `verification/report.py --fetch` puts the models).

Each folder holds the migrated model, `<id>.idf` (or `in.idf`), and its results,
`eplusout.sql` (or `<id>.sql`). A building without them is skipped, saying so.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
import tomllib  # pyright: ignore[reportMissingTypeStubs]  # Python 3.11+

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..umi import audit
else:
    _path = Path(__file__).parents[1] / "umi" / "audit.py"
    _spec = importlib.util.spec_from_file_location("audit", _path)
    audit = importlib.util.module_from_spec(_spec)
    sys.modules["audit"] = audit
    _spec.loader.exec_module(audit)

pytestmark = pytest.mark.reference

ROOT = Path(__file__).resolve().parents[2]
REFERENCE_SET = ROOT / "verification" / "reference_set.toml"
SKIP_REASON = (
    "no EnergyPlus 24.2 model and results for {id}: the reference models are published for "
    "EnergyPlus 22.1/23.1 and cannot be migrated or simulated here without EnergyPlus's "
    "transition programs; put them in one of the folders this module's docstring lists"
)


def _buildings() -> list[str]:
    with REFERENCE_SET.open("rb") as file:
        reference: dict[str, Any] = tomllib.load(file)  # pyright: ignore[reportUnknownMemberType]
    return [building["id"] for building in reference["building"]]


def _cache() -> Path:
    env = os.environ.get("ARCHETYPAL_REFERENCE_CACHE")
    return Path(env).expanduser() if env else Path.home() / ".cache" / "archetypal" / "reference-set"


def _folders(building: str) -> list[Path]:
    folders: list[Path] = []
    env = os.environ.get("ARCHETYPAL_REFERENCE_RESULTS")
    if env:
        folders.append(Path(env).expanduser() / building)
    folders += [ROOT / "verification" / "results" / building, _cache() / "results" / building]
    return folders


def inputs(building: str) -> tuple[Path, Path] | None:
    """The migrated model and results of a reference building, or `None` when there are none."""
    for folder in _folders(building):
        models = [folder / f"{building}.idf", folder / "in.idf"]
        results = [folder / "eplusout.sql", folder / f"{building}.sql"]
        model = next((path for path in models if path.is_file()), None)
        sql = next((path for path in results if path.is_file()), None)
        if model is not None and sql is not None:
            return model, sql
    return None


BUILDINGS = _buildings()


def test_the_reference_set_has_49_buildings() -> None:
    assert len(BUILDINGS) == 49


@pytest.mark.parametrize("building", BUILDINGS)
def test_a_reference_building_round_trips_through_umi(
    building: str, tmp_path: Path, save_library: Callable[[Path], Path | None]
) -> None:
    found = inputs(building)
    if found is None:
        pytest.skip(SKIP_REASON.format(id=building))
    from archetypal.reduction import reduce  # noqa: PLC0415 - imports epinterface, only when used
    from archetypal.umi import write_umi  # noqa: PLC0415

    model, results = found
    reduction = reduce(model, results)

    # SC-004: written and read back, the archetype is unchanged apart from reported losses.
    archetype_audit = audit.audit_archetypes([reduction], tmp_path, building)
    assert archetype_audit.problems == []

    # SC-006: the audit of the UMI test set, on the library written.
    library = tmp_path / "written" / f"{building}.json"
    write_umi([reduction], library)
    save_library(library)  # SC-002: checked by tools/basilisk-check in the reference workflow
    library_audit = audit.audit_library(library, tmp_path)
    assert library_audit.problems == []
