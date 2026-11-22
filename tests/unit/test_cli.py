"""The `archetypal` command (spec 001, US1: T025; contracts/cli.md).

The commands run in-process with click's `CliRunner` on the committed fixture models and their
results, so no EnergyPlus is needed. Reductions come from the session cache of
`tests/conftest.py` (`reduced`) through `cli_reductions` (`tests/unit/conftest.py`), which
stands in for the one function of `archetypal.cli._reduce` that reduces a model; one test runs
the real reduction.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from archetypal.cli import main

if TYPE_CHECKING:
    from collections.abc import Callable

MODELS = Path(__file__).resolve().parents[1] / "fixtures" / "models"
WEATHER = Path(__file__).resolve().parents[1] / "fixtures" / "weather" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
UMI = Path(__file__).resolve().parents[1] / "fixtures" / "umi" / "BostonTemplateLibrary_2.json"
# The two fast fixtures (about a second each to reduce, once per session).
FAST = ("bar_building", "three_zone")


def results_args(*names: str) -> list[str]:
    """Return `--results <fixture>.sql` for each fixture, in order."""
    return [arg for name in names for arg in ("--results", str(MODELS / f"{name}.sql"))]


def run(*args: str | Path) -> tuple[int, str, str]:
    """Run `archetypal ARGS` and return the exit code, stdout and stderr."""
    result = runner().invoke(main, [str(a) for a in args], catch_exceptions=False)
    return result.exit_code, result.stdout, result.stderr


def runner() -> CliRunner:
    """Return a runner that keeps stderr apart from stdout (click 8.1 and 8.2+)."""
    try:
        return CliRunner(mix_stderr=False)  # pyright: ignore[reportCallIssue]
    except TypeError:  # click 8.2 always keeps them apart
        return CliRunner()


# --- the group (scenario 1.1) -------------------------------------------------------------------


def test_archetypal_alone_lists_the_commands_with_one_line_each() -> None:
    code, out, _ = run()
    assert code == 0
    lines = {line.split()[0]: line for line in out.splitlines() if line.startswith("  ") and line.split()}
    for command in ("reduce", "merge", "compare", "translate"):
        assert command in lines
        assert len(lines[command].split()) > 1, f"{command} has no description"
    assert "transition" not in lines


def test_version_names_archetypal_idfkit_and_epinterface() -> None:
    code, out, _ = run("--version")
    assert code == 0
    words = [line.split()[0] for line in out.splitlines()]
    assert words == ["archetypal", "idfkit", "epinterface"]


def test_log_level_adds_a_handler_for_the_command_only(tmp_path: Path, cli_reductions: list[tuple[str, str]]) -> None:
    import logging  # noqa: PLC0415

    del cli_reductions
    before = list(logging.getLogger("archetypal").handlers)
    model = MODELS / "bar_building.idf"
    code, _, _ = run(
        "--log-level", "debug", "reduce", model, *results_args("bar_building"), "--to", "sbem", "-o", tmp_path
    )
    assert code in {0, 4}
    assert logging.getLogger("archetypal").handlers == before


def test_removed_v2_cli_names_raise_the_migration_error() -> None:
    from archetypal.errors import RemovedInArchetypal3Error  # noqa: PLC0415

    with pytest.raises(RemovedInArchetypal3Error, match=r"archetypal\.cli\.CliConfig"):
        exec("from archetypal.cli import CliConfig", {})  # noqa: S102
    from archetypal import cli  # noqa: PLC0415

    with pytest.raises(RemovedInArchetypal3Error, match="archetypal reduce"):
        _ = cli.reduce  # pyright: ignore[reportAttributeAccessIssue]


# --- reduce: models (FR-012) ----------------------------------------------------------------------


def test_reduce_expands_directories_and_globs_sorted(tmp_path: Path, cli_reductions: list[tuple[str, str]]) -> None:
    folder = tmp_path / "models"
    folder.mkdir()
    for name in ("three_zone", "bar_building"):
        shutil.copyfile(MODELS / f"{name}.idf", folder / f"{name}.idf")
    (folder / "notes.txt").write_text("not a model", encoding="utf-8")
    out = tmp_path / "out"
    code, _, err = run("reduce", folder, *results_args("bar_building", "three_zone"), "--to", "sbem", "-o", out)
    assert code in {0, 4}, err
    assert [stem for stem, _ in cli_reductions] == ["bar_building", "three_zone"]

    cli_reductions.clear()
    code, _, err = run("reduce", str(folder / "*.idf"), *results_args(*FAST), "--to", "sbem", "-o", out, "--force")
    assert code in {0, 4}, err
    assert [stem for stem, _ in cli_reductions] == ["bar_building", "three_zone"]


def test_reduce_refuses_an_empty_directory_naming_it(tmp_path: Path, cli_reductions: list[tuple[str, str]]) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    code, _, err = run("reduce", empty, "-w", WEATHER, "-o", tmp_path / "lib.json")
    assert code == 1
    assert str(empty) in err
    assert cli_reductions == []
    assert not (tmp_path / "lib.json").exists()


def test_reduce_refuses_a_pattern_that_matches_nothing(tmp_path: Path, cli_reductions: list[tuple[str, str]]) -> None:
    pattern = str(tmp_path / "*.idf")
    code, _, err = run("reduce", pattern, "-w", WEATHER, "-o", tmp_path / "lib.json")
    assert code == 1
    assert pattern in err
    assert cli_reductions == []


def test_reduce_needs_weather_without_results(tmp_path: Path, cli_reductions: list[tuple[str, str]]) -> None:
    code, _, err = run("reduce", MODELS / "bar_building.idf", "-o", tmp_path / "lib.json")
    assert code == 2
    assert "--weather" in err
    assert cli_reductions == []


def test_reduce_needs_one_results_file_per_model(tmp_path: Path, cli_reductions: list[tuple[str, str]]) -> None:
    models = [MODELS / f"{name}.idf" for name in FAST]
    code, _, err = run("reduce", *models, *results_args("bar_building"), "-o", tmp_path / "lib.json")
    assert code == 2
    assert "--results" in err
    assert cli_reductions == []


# --- reduce --to sbem (scenario 1.3) ---------------------------------------------------------------


def test_to_sbem_writes_an_archetype_and_report_per_model_that_merge_reads(
    tmp_path: Path, cli_reductions: list[tuple[str, str]]
) -> None:
    models = [MODELS / f"{name}.idf" for name in FAST]
    out = tmp_path / "archetypes"
    code, _, err = run("reduce", *models, *results_args(*FAST), "--to", "sbem", "-o", out)
    assert code == 4, err  # the fixtures have features SBEM cannot hold
    assert sorted(p.name for p in out.iterdir()) == [
        "bar_building.report.json",
        "bar_building.sbem.json",
        "three_zone.report.json",
        "three_zone.sbem.json",
    ]
    assert {layout for _, layout in cli_reductions} == {"space_use_exposure"}
    report = json.loads((out / "three_zone.report.json").read_text(encoding="utf-8"))
    assert report["reproducibility"]["options"]["layout"] == "space_use_exposure"

    merged = tmp_path / "merged" / "three_zone.sbem.json"
    code, _, err = run("merge", out / "three_zone.sbem.json", "--layout", "single-zone", "-o", merged)
    assert code in {0, 4}, err
    assert merged.is_file()
    assert (merged.parent / "three_zone.report.json").is_file()


def test_to_sbem_follows_layout_and_threshold(tmp_path: Path, cli_reductions: list[tuple[str, str]]) -> None:
    model = MODELS / "bar_building.idf"
    args = ("--to", "sbem", "--layout", "core-perimeter", "--threshold", "0.1", "-o", tmp_path)
    code, _, err = run("reduce", model, *results_args("bar_building"), *args)
    assert code in {0, 4}, err
    assert cli_reductions == [("bar_building", "core_perimeter")]


# --- reduce --to umi (scenario 1.2) ----------------------------------------------------------------


def test_to_umi_writes_one_library_with_a_template_per_model_and_the_reports(
    tmp_path: Path, cli_reductions: list[tuple[str, str]], save_library: Callable[[Path], Path | None]
) -> None:
    models = [MODELS / f"{name}.idf" for name in FAST]
    library = tmp_path / "campus.json"
    code, _, err = run("reduce", *models, *results_args(*FAST), "-o", library)
    assert code == 4, err
    save_library(library)
    assert sorted(p.name for p in tmp_path.iterdir()) == [
        "campus.bar_building.report.json",
        "campus.json",
        "campus.loss.json",
        "campus.three_zone.report.json",
    ]
    assert {layout for _, layout in cli_reductions} == {"core_perimeter"}
    data = json.loads(library.read_text(encoding="utf-8"))
    assert [t["Name"] for t in data["BuildingTemplates"]] == list(FAST)
    loss = json.loads((tmp_path / "campus.loss.json").read_text(encoding="utf-8"))
    assert loss["subjects"] == list(FAST)
    assert "campus.loss.json" in err
    assert "2 models reduced" in err


def test_to_umi_is_the_default_with_v2s_output_name(
    tmp_path: Path, cli_reductions: list[tuple[str, str]], monkeypatch: pytest.MonkeyPatch
) -> None:
    del cli_reductions
    monkeypatch.chdir(tmp_path)
    code, _, err = run("reduce", MODELS / "bar_building.idf", *results_args("bar_building"))
    assert code == 4, err
    assert (tmp_path / "myumitemplate.json").is_file()
    assert (tmp_path / "myumitemplate.loss.json").is_file()
    assert (tmp_path / "myumitemplate.bar_building.report.json").is_file()


def test_layout_with_to_umi_is_refused(tmp_path: Path, cli_reductions: list[tuple[str, str]]) -> None:
    model = MODELS / "bar_building.idf"
    code, _, err = run(
        "reduce", model, *results_args("bar_building"), "--layout", "space-use", "-o", tmp_path / "l.json"
    )
    assert code == 2
    assert "--layout" in err
    assert "core-perimeter" in err
    assert cli_reductions == []
    assert list(tmp_path.iterdir()) == []


# --- overwriting (FR-015) --------------------------------------------------------------------------


def test_an_existing_output_is_not_overwritten_without_force(
    tmp_path: Path, cli_reductions: list[tuple[str, str]]
) -> None:
    library = tmp_path / "lib.json"
    library.write_text("keep me", encoding="utf-8")
    model = MODELS / "bar_building.idf"
    code, _, err = run("reduce", model, *results_args("bar_building"), "-o", library)
    assert code == 1
    assert str(library) in err
    assert "--force" in err
    assert library.read_text(encoding="utf-8") == "keep me"
    assert cli_reductions == []  # refused before any work
    assert sorted(p.name for p in tmp_path.iterdir()) == ["lib.json"]

    code, _, err = run("reduce", model, *results_args("bar_building"), "-o", library, "--force")
    assert code == 4, err
    assert json.loads(library.read_text(encoding="utf-8"))["BuildingTemplates"]


def test_an_existing_report_is_not_overwritten_without_force(
    tmp_path: Path, cli_reductions: list[tuple[str, str]]
) -> None:
    del cli_reductions
    (tmp_path / "bar_building.report.json").write_text("keep me", encoding="utf-8")
    model = MODELS / "bar_building.idf"
    code, _, _ = run("reduce", model, *results_args("bar_building"), "--to", "sbem", "-o", tmp_path)
    assert code == 1
    assert not (tmp_path / "bar_building.sbem.json").exists()


# --- the real reduction, once ------------------------------------------------------------------------


def test_reduce_runs_the_real_reduction(tmp_path: Path) -> None:
    model = MODELS / "bar_building.idf"
    code, _, err = run("reduce", model, *results_args("bar_building"), "--to", "sbem", "-o", tmp_path)
    assert code == 4, err
    assert (tmp_path / "bar_building.sbem.json").is_file()


# --- translate and compare (FR-011) ------------------------------------------------------------------


def test_translate_umi_to_sbem_and_back(tmp_path: Path, save_library: Callable[[Path], Path | None]) -> None:
    folder = tmp_path / "sbem"
    code, _, err = run("translate", UMI, "-o", folder)
    assert code == 4, err
    written = sorted(p.name for p in folder.iterdir())
    assert "BostonTemplateLibrary_2.loss.json" in written
    archetypes = sorted(folder.glob("*.sbem.json"))
    assert archetypes

    library = tmp_path / "back.json"
    code, _, err = run("translate", folder, "-o", library)
    assert code in {0, 4}, err
    save_library(library)
    assert (tmp_path / "back.loss.json").is_file()
    templates = json.loads(library.read_text(encoding="utf-8"))["BuildingTemplates"]
    assert len(templates) == len(archetypes)


def test_translate_strict_writes_nothing_on_loss(tmp_path: Path) -> None:
    folder = tmp_path / "sbem"
    code, _, err = run("translate", UMI, "-o", folder, "--strict")
    assert code == 1
    assert "lost" in err
    assert not folder.exists()


def test_translate_refuses_to_overwrite_without_force(tmp_path: Path) -> None:
    folder = tmp_path / "sbem"
    assert run("translate", UMI, "-o", folder)[0] == 4
    code, _, err = run("translate", UMI, "-o", folder)
    assert code == 1
    assert "--force" in err
    assert run("translate", UMI, "-o", folder, "--force")[0] == 4


def test_compare_prints_the_table_and_writes_json(tmp_path: Path) -> None:
    detailed, archetype = MODELS / "ten_zone_multipliers.sql", MODELS / "ten_zone_explicit.sql"
    target = tmp_path / "comparison.json"
    code, out, err = run("compare", detailed, archetype, "--json", target)
    assert code == 0, err
    assert "Total site energy" in out
    data = json.loads(target.read_text(encoding="utf-8"))
    assert data["rows"][0]["metric"] == "Total site energy"
    code, _, err = run("compare", detailed, archetype, "--json", target)
    assert code == 1
    assert "--force" in err


def test_compare_refuses_incomparable_results(tmp_path: Path) -> None:
    del tmp_path
    comparison = Path(__file__).resolve().parents[1] / "fixtures" / "comparison"
    code, _, err = run("compare", comparison / "base.sql", comparison / "run_period.sql")
    assert code == 1
    assert "base.sql" in err
