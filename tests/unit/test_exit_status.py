"""The command's exit statuses and summary (spec 001, US1: T026; data-model.md ExitStatus; FR-014)."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from archetypal.cli import main
from archetypal.cli._summary import ExitStatus, Failure, RunSummary

if TYPE_CHECKING:
    from collections.abc import Callable

    from archetypal.reduction import Reduction
    from archetypal.reduction.options import ReductionOptions

MODELS = Path(__file__).resolve().parents[1] / "fixtures" / "models"
SQL = str(MODELS / "bar_building.sql")


def run(*args: str | Path) -> tuple[int, str]:
    """Run `archetypal ARGS` and return the exit code and stderr."""
    try:
        runner = CliRunner(mix_stderr=False)  # pyright: ignore[reportCallIssue]
    except TypeError:  # click 8.2 always keeps stderr apart
        runner = CliRunner()
    result = runner.invoke(main, [str(a) for a in args], catch_exceptions=False)
    return result.exit_code, result.stderr


@pytest.fixture
def broken(tmp_path: Path) -> Path:
    """A model file that `cli_reductions` fails to reduce."""
    path = tmp_path / "models" / "broken.idf"
    path.parent.mkdir()
    shutil.copyfile(MODELS / "bar_building.idf", path)
    return path


# --- the status itself ------------------------------------------------------------------------------


def test_values_follow_the_data_model() -> None:
    assert [(s.name, int(s)) for s in ExitStatus] == [
        ("SUCCESS", 0),
        ("FAILURE", 1),
        ("USAGE", 2),
        ("PARTIAL_FAILURE", 3),
        ("SUCCESS_WITH_LOSSES", 4),
    ]


@pytest.mark.parametrize(
    ("ok", "failed", "losses", "approximations", "status"),
    [
        (2, 0, 0, 0, ExitStatus.SUCCESS),
        (2, 0, 3, 0, ExitStatus.SUCCESS_WITH_LOSSES),
        (2, 0, 0, 1, ExitStatus.SUCCESS_WITH_LOSSES),
        (1, 1, 0, 0, ExitStatus.PARTIAL_FAILURE),
        (1, 1, 5, 2, ExitStatus.PARTIAL_FAILURE),  # 3 wins over 4
        (0, 2, 0, 0, ExitStatus.FAILURE),
    ],
)
def test_status_from_the_summary(ok: int, failed: int, losses: int, approximations: int, status: ExitStatus) -> None:
    failures = [Failure(Path(f"m{i}.idf"), "ReductionError", "boom") for i in range(failed)]
    summary = RunSummary(models_ok=ok, failures=failures, losses=losses, approximations=approximations)
    assert summary.models_failed == failed
    assert summary.status is status


def test_summary_names_failures_counts_and_reports() -> None:
    summary = RunSummary(
        models_ok=1,
        failures=[Failure(Path("b.idf"), "NoConditionedZones", "b.idf: no conditioned zones")],
        losses=3,
        approximations=2,
        outputs=[Path("lib.json")],
        reports=[Path("lib.a.report.json"), Path("lib.loss.json")],
    )
    text = summary.render()
    assert "1 model reduced, 1 failed" in text
    assert "b.idf" in text
    assert "NoConditionedZones" in text
    assert "3 losses" in text
    assert "2 approximations" in text
    assert "lib.loss.json" in text


# --- through the command ------------------------------------------------------------------------------


def test_exit_0_without_loss(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reduced: Callable[..., Reduction]) -> None:
    from archetypal.cli import _reduce  # noqa: PLC0415
    from archetypal.reduction import Reduction  # noqa: PLC0415

    def lossless(model: Path, results: Path | None, weather: Path | None, options: ReductionOptions) -> Reduction:
        del results, weather
        reduction = reduced(model.stem, options)
        return Reduction(reduction.archetype, reduction.report.model_copy(update={"not_represented": ()}))

    monkeypatch.setattr(_reduce, "_reduce_one", lossless)
    code, err = run("reduce", MODELS / "bar_building.idf", "--results", SQL, "--to", "sbem", "-o", tmp_path)
    assert code == ExitStatus.SUCCESS, err
    assert "0 losses" in err


def test_exit_4_with_a_loss_reported(tmp_path: Path, cli_reductions: list[tuple[str, str]]) -> None:
    del cli_reductions
    code, err = run("reduce", MODELS / "bar_building.idf", "--results", SQL, "-o", tmp_path / "lib.json")
    assert code == ExitStatus.SUCCESS_WITH_LOSSES, err


def test_exit_3_when_one_of_two_models_fails(
    tmp_path: Path, broken: Path, cli_reductions: list[tuple[str, str]]
) -> None:
    del cli_reductions
    library = tmp_path / "lib.json"
    code, err = run("reduce", MODELS / "bar_building.idf", broken, "--results", SQL, "--results", SQL, "-o", library)
    assert code == ExitStatus.PARTIAL_FAILURE  # 3 wins over the losses' 4
    assert str(broken) in err
    assert "NoConditionedZones" in err
    templates = json.loads(library.read_text(encoding="utf-8"))["BuildingTemplates"]
    assert [t["Name"] for t in templates] == ["bar_building"]
    loss = json.loads((tmp_path / "lib.loss.json").read_text(encoding="utf-8"))
    skipped = [entry for entry in loss["losses"] if entry["kind"] == "skipped_template"]
    assert [entry["subject"] for entry in skipped] == ["broken"]
    assert "NoConditionedZones" in json.dumps(skipped)
    assert not (tmp_path / "lib.broken.report.json").exists()
    assert (tmp_path / "lib.bar_building.report.json").is_file()


def test_exit_3_with_sbem_writes_the_others(tmp_path: Path, broken: Path, cli_reductions: list[tuple[str, str]]) -> None:
    del cli_reductions
    out = tmp_path / "out"
    code, err = run(
        "reduce", MODELS / "bar_building.idf", broken, "--results", SQL, "--results", SQL, "--to", "sbem", "-o", out
    )
    assert code == ExitStatus.PARTIAL_FAILURE
    assert "broken" in err
    assert sorted(p.name for p in out.iterdir()) == ["bar_building.report.json", "bar_building.sbem.json"]


def test_exit_1_when_every_model_fails_and_nothing_is_written(
    tmp_path: Path, broken: Path, cli_reductions: list[tuple[str, str]]
) -> None:
    del cli_reductions
    out = tmp_path / "out"
    out.mkdir()
    code, err = run("reduce", broken, "--results", SQL, "-o", out / "lib.json")
    assert code == ExitStatus.FAILURE
    assert str(broken) in err
    assert list(out.iterdir()) == []


def test_exit_2_for_a_usage_error(tmp_path: Path) -> None:
    code, err = run("reduce", MODELS / "bar_building.idf", "--results", SQL, "--to", "csv", "-o", tmp_path)
    assert code == ExitStatus.USAGE
    assert "--to" in err
    code, _ = run("no-such-command")
    assert code == ExitStatus.USAGE


def test_exit_1_for_an_unexpected_error_and_debug_shows_the_traceback(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from archetypal.cli import _reduce  # noqa: PLC0415

    def explode(*args: object) -> Reduction:
        del args
        msg = "something unexpected"
        raise RuntimeError(msg)

    monkeypatch.setattr(_reduce, "_reduce_one", explode)
    args = ("reduce", MODELS / "bar_building.idf", "--results", SQL, "-o", tmp_path / "lib.json")
    code, err = run(*args)
    assert code == ExitStatus.FAILURE
    assert "RuntimeError" in err
    assert "something unexpected" in err
    assert "Traceback" not in err
    code, err = run("--debug", *args)
    assert code == ExitStatus.FAILURE
    assert "Traceback" in err
