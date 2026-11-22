"""Round trips without silent change (spec 003 T058, US3; SC-003, SC-004).

Scenario 1: each library of the UMI test set is read and written back; `diff_umi` between the
original and the result has no simulation-relevant (`S`) difference above 0.01 % that the
reports do not list. The `S` fields still waiting for an upstream item are checked on their own,
per field group, and marked `xfail(strict=True)` for the libraries that use them, so each test
flips when its fields land.

Scenario 2: a core/perimeter archetype written to UMI and read back equals the original, apart
from the first write's losses: for the archetypes read from the test set, for spec 002's fixture
reductions, and as a hypothesis property over generated core/perimeter archetypes.
"""

from __future__ import annotations

import importlib.util
import sys
import tempfile
from functools import cache
from pathlib import Path
from typing import TYPE_CHECKING, Any

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from archetypal.umi import CORRESPONDENCE, MappingStatus, diff_archetypes, diff_umi, read_umi, to_umi

if TYPE_CHECKING:
    from collections.abc import Callable

    from epinterface.sbem.archetype import Archetype

    from archetypal.reduction import Reduction
    from archetypal.umi.diff import Difference, UmiDiff
    from archetypal.umi.read import UmiImport
    from archetypal.umi.write import UmiExport

    from ...umi import audit
else:
    _path = Path(__file__).parents[2] / "umi" / "audit.py"
    _spec = importlib.util.spec_from_file_location("audit", _path)
    audit = importlib.util.module_from_spec(_spec)
    sys.modules["audit"] = audit
    _spec.loader.exec_module(audit)

LIBRARIES = {path.name: path for path in audit.TEST_SET}
WITH_TEMPLATES = [name for name in LIBRARIES if name != "no_templates.json"]

# The UMI keys whose SBEM field waits for UP-9: the airflow-network, zone-mixing and
# interior-window settings, and the ventilation's airflow-network switch.
UP9_KEYS = frozenset(row.umi_key for row in CORRESPONDENCE if row.status is MappingStatus.UPSTREAM and row.upstream == "UP-9")
UP9_REASON = (
    "UP-9: the SBEM fork has no airflow-network, zone-mixing or interior-window settings "
    "(WindowSettings.Afn*, ZoneMixing*, IsVirtualPartition, Type; ZoneVentilation.Afn), and these "
    "samples set AfnWindowAvailability and ZoneMixingAvailabilitySchedule to occupancy schedules"
)
R7_REASON = (
    "R7: part boundaries inside a month are projected to one representative week "
    "(schedule.months), which conserves the month's sum but not each hour"
)


def _is_up9(difference: Difference) -> bool:
    for place in (difference.location, *difference.via):
        parent, _, key = place.rpartition("/")
        if key in UP9_KEYS and (key != "Type" or "/Windows" in parent or parent.startswith("/WindowSettings")):
            return True
    return False


@cache
def _round_trip(name: str) -> tuple[UmiImport, UmiExport, UmiDiff]:
    """Read a library, write it back and diff the two (once per session)."""
    path = LIBRARIES[name]
    imported = read_umi(path)
    exported = to_umi(imported.archetypes)
    written = Path(tempfile.mkdtemp()) / name
    written.write_text(exported.text, encoding="utf-8")
    return imported, exported, diff_umi(path, written)


def _beyond_simulation(diff: UmiDiff) -> list[Difference]:
    return [d for d in diff.beyond() if d.relevance == "S"]


# --- Scenario 1 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("name", WITH_TEMPLATES)
def test_every_simulation_difference_is_within_tolerance_or_reported(name: str) -> None:
    imported, exported, diff = _round_trip(name)
    losses = [*imported.report.losses, *exported.report.losses]
    unreported = [d for d in _beyond_simulation(diff) if not any(audit.explains(loss, d) for loss in losses)]
    assert unreported == []


def _expect(reason: str, *names: str) -> list[Any]:
    return [
        pytest.param(name, marks=pytest.mark.xfail(strict=True, reason=reason)) if name in names else name
        for name in WITH_TEMPLATES
    ]


def _inert(difference: Difference, imported: UmiImport) -> bool:
    """An internal-mass construction with no exposed area: it changes nothing simulated.

    SBEM holds no internal mass for an exposed area of 0, so the construction is dropped on
    reading (`mass.internal`, reported) and another one written back, with the same zero area.
    """
    return any(
        loss.rule == "mass.internal"
        and loss.location.endswith("/InternalMassConstruction")
        and audit.explains(loss, difference)
        for loss in imported.report.losses
    )


@pytest.mark.parametrize("name", _expect(R7_REASON, "misaligned_parts.json"))
def test_simulation_values_survive_the_round_trip(name: str) -> None:
    """Every `S` field SBEM holds comes back within 0.01 % (SC-003)."""
    imported, _, diff = _round_trip(name)
    changed = [d.location for d in _beyond_simulation(diff) if not _is_up9(d) and not _inert(d, imported)]
    assert changed == []


@pytest.mark.parametrize("name", _expect(UP9_REASON, *audit.SAMPLES))
def test_airflow_network_and_zone_mixing_settings_survive_the_round_trip(name: str) -> None:
    """The window settings UP-9 leaves out: they flip to passing when SBEM holds them."""
    _, _, diff = _round_trip(name)
    assert [d.location for d in _beyond_simulation(diff) if _is_up9(d)] == []


def test_the_samples_lose_only_the_up9_window_settings_on_the_way_back() -> None:
    """Besides components no template uses and Archsim-era keys, B2 loses only UP-9 fields."""
    imported, exported, _ = _round_trip("BostonTemplateLibrary_2.json")
    rules = {(loss.rule, loss.upstream) for loss in imported.report.losses}
    assert rules == {("library.unused", None), ("window.settings", "UP-9")}
    assert exported.report.losses == []


# --- Scenario 2 ------------------------------------------------------------------------------------


def _read_back(items: list[Any]) -> tuple[UmiExport, tuple[Archetype, ...]]:
    exported = to_umi(items)
    path = Path(tempfile.mkdtemp()) / "library.json"
    path.write_text(exported.text, encoding="utf-8")
    return exported, read_umi(path).archetypes


@pytest.mark.parametrize("name", WITH_TEMPLATES)
def test_archetypes_read_from_umi_come_back_unchanged(name: str) -> None:
    imported, exported, _ = _round_trip(name)
    _, again = _read_back(list(imported.archetypes))
    for original, back in zip(imported.archetypes, again, strict=True):
        diff = diff_archetypes(original, back)
        unexplained = [d for d in diff.differences if not any(audit.explains(f, d) for f in exported.report.losses)]
        assert unexplained == [], original.Name


@pytest.mark.parametrize("fixture", ["three_zone", "bar_building"])
def test_a_reduction_comes_back_apart_from_the_first_writes_losses(
    fixture: str, reduced: Callable[..., Reduction], tmp_path: Path
) -> None:
    result = audit.audit_archetypes([reduced(fixture)], tmp_path, fixture)
    assert result.problems == []
    assert result.differences > 0  # the reduction's simple glazing, setbacks and geometry do not survive


@pytest.fixture(scope="module")
def office() -> Archetype:
    return read_umi(LIBRARIES["BostonTemplateLibrary_nodup.json"]).archetypes[0]


def _replace(model: Any, path: str, value: object) -> Any:
    head, _, rest = path.partition(".")
    return model.model_copy(update={head: value if not rest else _replace(getattr(model, head), rest, value)})


_FIELDS = {
    "Operations.SpaceUse.Lighting.PowerDensity": st.floats(0.0, 30.0),
    "Operations.SpaceUse.Equipment.PowerDensity": st.floats(0.0, 50.0),
    "Operations.SpaceUse.Occupancy.PeopleDensity": st.floats(0.01, 0.5),
    "Envelope.Infiltration.AirChangesPerHour": st.floats(0.0, 3.0),
    "Operations.HVAC.Ventilation.FreshAirPerPerson": st.floats(0.0, 0.02),
    "Operations.HVAC.Ventilation.FreshAirPerFloorArea": st.floats(0.0, 0.003),
    "Envelope.Assemblies.InternalMassExposedAreaPerArea": st.floats(0.1, 3.0),
}


@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(core=st.fixed_dictionaries(_FIELDS), perimeter=st.fixed_dictionaries(_FIELDS))
def test_generated_core_perimeter_archetypes_come_back(
    office: Archetype, core: dict[str, float], perimeter: dict[str, float]
) -> None:
    groups = []
    for group in office.Groups:
        zone = group.Zone.model_copy(update={"Name": f"{group.Name} zone"})
        for path, value in (core if group.Name == "core" else perimeter).items():
            zone = _replace(zone, path, value)
        groups.append(group.model_copy(update={"Zone": zone}))
    archetype = office.model_copy(update={"Groups": groups})
    exported, (back,) = _read_back([archetype])
    diff = diff_archetypes(archetype, back)
    unexplained = [d for d in diff.differences if not any(audit.explains(f, d) for f in exported.report.losses)]
    assert unexplained == []
