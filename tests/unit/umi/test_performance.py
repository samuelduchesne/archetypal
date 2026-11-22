"""Speed of reading and writing (spec 003 T065, SC-007).

A library of 100 building templates, made from B2 by renaming its four templates, is read in
under 3 s and written in under 3 s: SC-007's 5 s on a typical laptop, with a margin for slow CI.
"""

from __future__ import annotations

import copy
import json
import time
from pathlib import Path
from typing import Any

import pytest

from archetypal.umi import read_umi, write_umi

B2 = Path(__file__).parents[2] / "fixtures" / "umi" / "BostonTemplateLibrary_2.json"
TEMPLATES = 100
BUDGET_S = 3.0


def library_of(count: int) -> dict[str, Any]:
    """B2 with `count` templates: copies of its four, renamed, sharing their components."""
    document = json.loads(B2.read_text(encoding="utf-8"))
    originals = document["BuildingTemplates"]
    templates = []
    for index in range(count):
        template = copy.deepcopy(originals[index % len(originals)])
        windows = template["Windows"]
        if index >= len(originals) and "$id" in windows:
            template["Windows"] = {"$ref": windows["$id"]}  # defined once, by the first copy
        template["Name"] = f"{template['Name']} {index:03d}"
        templates.append(template)
    document["BuildingTemplates"] = templates
    return document


@pytest.fixture(scope="module")
def hundred(tmp_path_factory: pytest.TempPathFactory) -> Path:
    path = tmp_path_factory.mktemp("performance") / "hundred.json"
    path.write_text(json.dumps(library_of(TEMPLATES)), encoding="utf-8")
    return path


@pytest.mark.timeout(30)
def test_100_templates_read_and_write_within_budget(hundred: Path, tmp_path: Path) -> None:
    start = time.perf_counter()
    imported = read_umi(hundred)
    read_s = time.perf_counter() - start
    assert len(imported.archetypes) == TEMPLATES

    start = time.perf_counter()
    write_umi(imported.archetypes, tmp_path / "written.json")
    write_s = time.perf_counter() - start

    assert read_s < BUDGET_S, f"reading took {read_s:.2f} s"
    assert write_s < BUDGET_S, f"writing took {write_s:.2f} s"
