"""Tests for deterministic archetype and report files, `archetypal.io` (spec 002, T019)."""

from __future__ import annotations

import base64
import json
import math
import re
from typing import TYPE_CHECKING

import numpy as np
import pytest
from epinterface.sbem.archetype import ARCHETYPE_SCHEMA_VERSION
from epinterface.sbem.archetype import Archetype as SbemArchetype
from hypothesis import given
from hypothesis import strategies as st
from pydantic import BaseModel

from archetypal import io
from archetypal.errors import InputError, ReductionError
from archetypal.io import EncodedProfile
from archetypal.reduction.grouping import Group as ZoneGroupLedger
from archetypal.reduction.ledger import EnvelopeTotals, GroupLedger
from archetypal.reduction.options import Layout
from archetypal.reduction.schedules import RunPeriodCalendar
from archetypal.reduction.to_sbem import BuildingFacts, to_archetype

if TYPE_CHECKING:
    from pathlib import Path


class Group(BaseModel):
    """A stand-in for a report entry."""

    zeta: float
    alpha: str
    profile: EncodedProfile | None = None


class Report(BaseModel):
    """A stand-in for `ReductionReport`, with fields deliberately out of alphabetical order."""

    schema_version: str = "1.0.0"
    name: str
    groups: list[Group]
    tolerance: float = 1e-7


class Archetype(BaseModel):
    """A stand-in for the epinterface archetype."""

    Name: str
    Area: float
    Notes: str = "Café façade"


def _report() -> Report:
    profile = EncodedProfile.from_values(np.linspace(0.0, 1.0, 8760))
    return Report(name="Office", groups=[Group(zeta=0.1 + 0.2, alpha="b", profile=profile), Group(zeta=1.0, alpha="a")])


def test_dumps_rules() -> None:
    text = io.dumps(_report())
    assert text.endswith("}\n")
    assert '\n  "name": "Office"' in text  # two-space indent
    assert '\n    {\n      "zeta"' in text
    # keys in model order, not sorted
    data = json.loads(text)
    assert list(data) == ["schema_version", "name", "groups", "tolerance"]
    assert list(data["groups"][0]) == ["zeta", "alpha", "profile"]
    # floats as shortest round-trip repr
    assert '"zeta": 0.30000000000000004' in text
    assert '"zeta": 1.0' in text
    assert '"tolerance": 1e-07' in text
    # arrays keep the order the model gives (the report builder sorts them)
    assert [g["alpha"] for g in data["groups"]] == ["b", "a"]


def test_non_ascii_is_written_as_utf8(tmp_path: Path) -> None:
    archetype_path, _ = io.write(Archetype(Name="A", Area=1.5), _report(), tmp_path, "office")
    raw = archetype_path.read_bytes()
    assert "Café façade".encode() in raw
    assert b"\\u00e9" not in raw


def test_non_finite_floats_are_refused() -> None:
    with pytest.raises(ValueError, match="finite"):
        io.dumps(Group(zeta=math.nan, alpha="a"))


def test_no_timestamp_and_byte_identical_on_repeat(tmp_path: Path) -> None:
    first = io.write(Archetype(Name="A", Area=2.0), _report(), tmp_path / "one", "office")
    second = io.write(Archetype(Name="A", Area=2.0), _report(), tmp_path / "two", "office")
    for a, b in zip(first, second, strict=True):
        assert a.read_bytes() == b.read_bytes()
    report_text = first[1].read_text(encoding="utf-8")
    assert not re.search(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", report_text)


def test_write_names_and_overwrite(tmp_path: Path) -> None:
    archetype_path, report_path = io.write(Archetype(Name="A", Area=2.0), _report(), tmp_path, "office")
    assert archetype_path == tmp_path / "office.sbem.json"
    assert report_path == tmp_path / "office.report.json"

    with pytest.raises(InputError, match=r"office\.sbem\.json.*overwrite=True"):
        io.write(Archetype(Name="B", Area=3.0), _report(), tmp_path, "office")
    assert json.loads(archetype_path.read_text(encoding="utf-8"))["Name"] == "A"

    io.write(Archetype(Name="B", Area=3.0), _report(), tmp_path, "office", overwrite=True)
    assert json.loads(archetype_path.read_text(encoding="utf-8"))["Name"] == "B"


def test_write_refuses_before_writing_either_file(tmp_path: Path) -> None:
    (tmp_path / "office.report.json").write_text("{}", encoding="utf-8")
    with pytest.raises(InputError, match=r"office\.report\.json"):
        io.write(Archetype(Name="A", Area=2.0), _report(), tmp_path, "office")
    assert not (tmp_path / "office.sbem.json").exists()


@pytest.mark.parametrize("name", ["", "a/b", "..", "office.sbem.json"])
def test_write_refuses_a_bad_name(tmp_path: Path, name: str) -> None:
    with pytest.raises(InputError):
        io.write(Archetype(Name="A", Area=2.0), _report(), tmp_path, name)


def test_read_round_trip(tmp_path: Path) -> None:
    archetype, report = Archetype(Name="A", Area=2.5), _report()
    archetype_path, report_path = io.write(archetype, report, tmp_path, "office")

    got_archetype, got_report = io.read(Archetype, Report, archetype_path)
    assert got_archetype == archetype
    assert got_report == report
    assert io.read(Archetype, Report, archetype_path, report_path) == (archetype, report)
    assert io.dumps(got_report) == report_path.read_text(encoding="utf-8")


def test_read_without_report_raises(tmp_path: Path) -> None:
    archetype_path, report_path = io.write(Archetype(Name="A", Area=2.5), _report(), tmp_path, "office")
    report_path.unlink()
    with pytest.raises(ReductionError, match=r"office\.report\.json"):
        io.read(Archetype, Report, archetype_path)


def test_report_path_for() -> None:
    assert io.report_path_for("dir/office.sbem.json").as_posix() == "dir/office.report.json"
    assert io.report_path_for("dir/office.json").as_posix() == "dir/office.report.json"


def test_profile_encoding_layout() -> None:
    values = np.array([0.0, 1.5, -2.25, 1e300])
    encoded = EncodedProfile.from_values(values)
    assert encoded.encoding == "base64-float64-le"
    assert encoded.length == 4
    raw = base64.b64decode(encoded.data)
    assert raw == values.astype("<f8").tobytes()
    np.testing.assert_array_equal(encoded.to_array(), values)
    assert encoded.to_array().dtype == np.float64


def test_profile_8760_round_trips_through_json() -> None:
    values = np.random.default_rng(0).random(8760)
    group = Group(zeta=1.0, alpha="a", profile=EncodedProfile.from_values(values))
    back = Group.model_validate_json(io.dumps(group))
    assert back.profile is not None
    np.testing.assert_array_equal(back.profile.to_array(), values)
    assert back.profile.length == 8760


def test_profile_length_mismatch_is_refused() -> None:
    encoded = EncodedProfile.from_values([1.0, 2.0])
    with pytest.raises(ValueError, match="length"):
        EncodedProfile(encoding="base64-float64-le", length=3, data=encoded.data)


def test_profile_non_finite_refused() -> None:
    with pytest.raises(ValueError, match="finite"):
        EncodedProfile.from_values([1.0, math.inf])


@given(st.lists(st.floats(allow_nan=False, allow_infinity=False), max_size=50))
def test_float_repr_round_trip(values: list[float]) -> None:
    class Floats(BaseModel):
        values: list[float]

    text = io.dumps(Floats(values=values))
    assert json.loads(text)["values"] == values
    for v in values:
        assert repr(v) in text


# --- the SBEM fork's archetype files (UP-2 save/load helpers, T087) ---------------------------------


def _sbem_archetype() -> SbemArchetype:
    def totals(area: float, u: float) -> EnvelopeTotals:
        return EnvelopeTotals(area=area, ua=area * u, capacity_inner=1e5 * area, capacity_outer=1e5 * area)

    ledger = GroupLedger(
        members=("Zone 1",),
        floor_area=100.0,
        envelope={
            "exterior_wall": totals(120.0, 0.4),
            "roof": totals(100.0, 0.2),
            "ground_floor": totals(100.0, 0.3),
            "floor_ceiling": totals(50.0, 1.5),
        },
    )
    facts = BuildingFacts(calendar=RunPeriodCalendar(year=2023), storey_ratio=1.0)
    groups = [ZoneGroupLedger(key=("office",), ledger=ledger)]
    return to_archetype(groups, Layout.SPACE_USE, facts, name="tiny").archetype


def test_an_sbem_archetype_is_written_with_the_forks_helper(tmp_path: Path) -> None:
    archetype = _sbem_archetype()

    archetype_path, _ = io.write(archetype, _report(), tmp_path, "tiny")
    again = io.write_model(archetype, tmp_path / "again.sbem.json")

    text = archetype_path.read_text(encoding="utf-8")
    assert text == archetype.to_json()
    assert again.read_bytes() == archetype_path.read_bytes()
    assert json.loads(text)["SchemaVersion"] == ARCHETYPE_SCHEMA_VERSION
    assert io.read_model(SbemArchetype, archetype_path) == archetype
    assert io.read(SbemArchetype, Report, archetype_path)[0] == SbemArchetype.load(archetype_path)


def test_an_sbem_archetype_of_an_unknown_schema_version_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "future.sbem.json"
    data = json.loads(_sbem_archetype().to_json())
    data["SchemaVersion"] = "9.0"
    path.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ReductionError, match=r"9\.0"):
        io.read_model(SbemArchetype, path)
