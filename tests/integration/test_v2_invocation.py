"""The v2-style invocation of `archetypal reduce` (spec 001, US1: T028; scenario 1.4, R6).

`archetypal reduce model.idf -w weather.epw -o lib.json` simulates the model once, reduces it
to the core/perimeter layout UMI needs and writes one UMI library, equal to the one written
through the Python functions (`reduce` with `simulate=True`, then `write_umi`). This is the
independent test of user story 1.
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

pytestmark = pytest.mark.energyplus

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"
WEATHER = FIXTURES / "weather" / "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
MODEL = "bar_building"


@pytest.fixture(scope="module")
def v2_run(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, int, int, str]:
    """Run the v2-style command in a fresh folder with an empty simulation cache.

    Returns the folder, the exit code, the number of EnergyPlus runs and stderr.
    """
    import idfkit.simulation  # noqa: PLC0415
    import idfkit.simulation.cache  # noqa: PLC0415

    from archetypal.cli import main  # noqa: PLC0415

    folder = tmp_path_factory.mktemp("v2")
    shutil.copyfile(FIXTURES / "models" / f"{MODEL}.idf", folder / "model.idf")
    shutil.copyfile(WEATHER, folder / "weather.epw")
    calls: list[object] = []
    original = idfkit.simulation.simulate

    def counting(*args: object, **kwargs: object) -> object:
        calls.append(args)
        return original(*args, **kwargs)  # type: ignore[arg-type]

    patch = pytest.MonkeyPatch()
    patch.setattr(idfkit.simulation, "simulate", counting)
    patch.setattr(idfkit.simulation.cache, "default_simulation_cache_dir", lambda: folder / ".cache")
    patch.chdir(folder)
    try:
        try:
            runner = CliRunner(mix_stderr=False)  # pyright: ignore[reportCallIssue]
        except TypeError:  # click 8.2 always keeps stderr apart
            runner = CliRunner()
        result = runner.invoke(
            main, ["reduce", "model.idf", "-w", "weather.epw", "-o", "lib.json"], catch_exceptions=False
        )
    finally:
        patch.undo()
    shutil.rmtree(folder / ".cache", ignore_errors=True)
    return folder, result.exit_code, len(calls), result.stderr


def test_simulates_once_and_writes_a_library(v2_run: tuple[Path, int, int, str]) -> None:
    folder, code, runs, err = v2_run
    assert code == 4, err  # the model has features SBEM cannot hold, reported as losses
    assert runs == 1
    assert sorted(p.name for p in folder.iterdir() if p.suffix == ".json") == [
        "lib.json",
        "lib.loss.json",
        "lib.model.report.json",
    ]
    report = json.loads((folder / "lib.model.report.json").read_text(encoding="utf-8"))
    assert report["reproducibility"]["options"]["layout"] == "core_perimeter"
    templates = json.loads((folder / "lib.json").read_text(encoding="utf-8"))["BuildingTemplates"]
    assert [t["Name"] for t in templates] == ["model"]


def test_same_library_as_the_python_route(
    v2_run: tuple[Path, int, int, str], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import idfkit.simulation.cache  # noqa: PLC0415

    from archetypal import Layout, ReductionOptions, reduce, write_umi  # noqa: PLC0415

    folder, _, _, _ = v2_run
    monkeypatch.setattr(idfkit.simulation.cache, "default_simulation_cache_dir", lambda: tmp_path / ".cache")
    monkeypatch.chdir(folder)  # the same model path, so the report records the same source
    options = ReductionOptions(layout=Layout.CORE_PERIMETER)
    reduction = reduce("model.idf", weather="weather.epw", simulate=True, options=options)
    write_umi([reduction], tmp_path / "lib.json")
    assert (tmp_path / "lib.json").read_bytes() == (folder / "lib.json").read_bytes()


def test_parallel_reduces_in_separate_processes(tmp_path: Path) -> None:
    """`-p 2` gives the files one process gives (integration tier: it starts processes)."""
    from archetypal.cli import main  # noqa: PLC0415

    models = FIXTURES / "models"
    names = ("bar_building", "three_zone")
    args = [str(models / f"{n}.idf") for n in names]
    for name in names:
        args += ["--results", str(models / f"{name}.sql")]
    serial = CliRunner().invoke(main, ["reduce", *args, "-o", str(tmp_path / "serial.json")])
    parallel = CliRunner().invoke(main, ["reduce", *args, "-o", str(tmp_path / "parallel.json"), "-p", "2"])
    assert serial.exit_code == parallel.exit_code == 4, parallel.output
    assert (tmp_path / "serial.json").read_bytes() == (tmp_path / "parallel.json").read_bytes()
    every_core = CliRunner().invoke(main, ["reduce", *args, "--to", "sbem", "-o", str(tmp_path / "all"), "-p", "-1"])
    assert every_core.exit_code == 4, every_core.output
    assert len(list((tmp_path / "all").glob("*.sbem.json"))) == len(names)
