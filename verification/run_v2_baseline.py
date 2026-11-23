r"""Reduce every reference building with archetypal 2 and record its errors and run time.

This is the v2 baseline for SC-004 (accuracy) and SC-008 (speed) of spec 002. It must run in
a separate environment with archetypal 2 installed, never in the archetypal 3 environment.
2.18.10 is the last archetypal 2 release on PyPI. Either:

```console
$ uv run --no-project --python 3.11 --with archetypal==2.18.10 --with "eppy<0.5.68" \
      python -I verification/run_v2_baseline.py --cache ~/.cache/archetypal/reference-set
```

or with a dedicated virtual environment:

```console
$ uv venv -p 3.11 /tmp/v2 && uv pip install -p /tmp/v2/bin/python "archetypal==2.18.10" "eppy<0.5.68"
$ /tmp/v2/bin/python -I verification/run_v2_baseline.py --cache ~/.cache/archetypal/reference-set
```

`eppy<0.5.68` is required: archetypal 2.18.10 allows `eppy>=0.5.63,<0.6`, but eppy 0.5.68
(January 2026) added an `idfabsname` attribute that archetypal 2's `IDF` never sets, so every
`IDF.savecopy` fails inside v2's simulation threads, v2 swallows the error and the reduction
then fails on a missing SQLite file. eppy 0.5.63 works.

Fetch the set first (`verification/report.py --fetch`, which needs no archetypal at all).

What archetypal 2 needs from EnergyPlus (read from archetypal 2.18.10's code):

- `import archetypal` reads `ENERGYPLUS_VERSION` (dash-separated, default `9-2-0`) and the
  command-line module asks for that installed EnergyPlus when imported. This script sets it to
  `--energyplus-version` (default: the set's `energyplus_version`, 24.2) before importing.
- v2 looks for EnergyPlus in `/usr/local/EnergyPlus*` (Linux), `C:\EnergyPlus*` (Windows) or
  `/Applications/EnergyPlus*` (macOS), or in `ENERGYPLUS_LOCATION`. It runs the simulation with
  the executable of `ENERGYPLUS_VERSION`.
- To read a model, v2 needs the IDD of the model's own version. It finds IDDs in
  `<install>/PreProcess/IDFVersionUpdater/*.idd`, or, when that folder is missing (as in
  slim Docker images), only the install's own `Energy+.idd`. A model older than
  `ENERGYPLUS_VERSION` is upgraded with the transition programs of that same folder.
- The prototypes are published for EnergyPlus 22.1 (commercial) and 23.1 (residential). So
  either give v2 an EnergyPlus 24.2 install that has `PreProcess/IDFVersionUpdater` (the full
  installer has it), or migrate the models to 24.2 first (the same migrated models v3
  reduces) and pass their folder with `--models-dir`. Without either, every building fails
  with `InvalidEnergyPlusVersion`, which this script records.
- v2 cannot reduce a model with `Space` objects (EnergyPlus 9.6+): eppy lists them among a
  zone's surfaces and v2 fails on their missing `Surface_Type` (`BadEPFieldError`). The
  prototypes have none, and the transition programs do not add any.
- v2 always simulates: its reduction runs an annual EnergyPlus simulation with SQLite output,
  then reads the results. This script times the simulation apart from the rest, so SC-008 can
  compare reduction time without simulation.

Each building runs in its own subprocess (with a timeout), from a scratch working directory,
because importing archetypal 2 writes `data/`, `logs/` and `cache/` folders in the current
directory and because a failure must not stop the set. The reduction itself is v2's
`UmiTemplateLibrary.template_complexity_reduction` step by step, unchanged except for the
timers, followed by v2's own library post-processing and `save`.

Output: a JSON file (default `<cache>/v2_baseline/results.json`) with the machine, the
versions, and one record per building: status, error type and message, the times of each step,
the number of zones, and the path of the UMI template library v2 wrote.
"""

from __future__ import annotations

import argparse
import importlib
import importlib.metadata
import json
import os
import platform
import subprocess
import sys
import time
import traceback
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10: the same parser, as the tomli package (a dependency of pytest there)
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

HERE = Path(__file__).resolve().parent
DEFAULT_SET = HERE / "reference_set.toml"


def default_cache() -> Path:
    """Same cache folder as `report.py --fetch`."""
    env = os.environ.get("ARCHETYPAL_REFERENCE_CACHE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cache" / "archetypal" / "reference-set"


def dash(version: str) -> str:
    """Return an EnergyPlus version as v2 wants it: `24.2` -> `24-2-0`."""
    parts = version.replace("-", ".").split(".")
    parts += ["0"] * (3 - len(parts))
    return "-".join(parts[:3])


def file_version(idf: Path) -> str | None:
    """Return the `Version` of an IDF file, read as text (no archetypal needed)."""
    text = idf.read_text(errors="replace")
    lines = [line.split("!")[0].strip() for line in text.splitlines()]
    joined = " ".join(line for line in lines if line)
    marker = joined.lower().find("version,")
    if marker < 0:
        return None
    return joined[marker + len("version,") :].split(";")[0].strip()


# --------------------------------------------------------------------------------------------
# Worker: one building, in its own process.
# --------------------------------------------------------------------------------------------


class V2SimulationError(RuntimeError):
    """archetypal 2's simulation ended without an SQLite file."""

    def __init__(self) -> None:
        """Explain the usual cause."""
        super().__init__("v2's simulation produced no SQLite file (see its log; check eppy<0.5.68)")


def _v2(module: str, name: str) -> Any:
    """Import `name` from archetypal 2's `module` (untyped, and unknown to the v3 type checker)."""
    return getattr(importlib.import_module(module), name)


def _load(idf_path: Path, epw: Path, ep_version: str) -> Any:  # archetypal 2 is untyped
    """Open the model as `template_complexity_reduction` does and prepare it for simulation."""
    idf = _v2("archetypal.idfclass", "IDF")(
        str(idf_path),
        epw=str(epw),
        verbose=False,
        nolimit=True,
        keep_data_err=False,
        readvars=False,
        annual=True,
        as_version=ep_version,
    )
    idf._outputs.add_umi_template_outputs()
    for daylight in idf.idfobjects["RunPeriodControl:DaylightSavingTime".upper()]:
        idf.removeidfobject(daylight)
    for run_period in idf.idfobjects["RunPeriod".upper()]:
        run_period.Day_of_Week_for_Start_Day = "Monday"
        run_period.Apply_Weekend_Holiday_Rule = "No"
        run_period.Use_Weather_File_Holidays_and_Special_Days = "No"
        run_period.Use_Weather_File_Daylight_Saving_Period = "No"
    for day in idf.idfobjects["RunPeriodControl:SpecialDays".upper()]:
        idf.removeidfobject(day)
    return idf


def _simulate(idf: Any) -> None:
    """Run v2's annual simulation and check that it produced results."""
    idf.simulate()
    if idf.sql_file is None:
        # v2 runs EnergyPlus in threads and only logs their exceptions.
        raise V2SimulationError


def _reduce(idf: Any, name: str) -> Any:
    """Build the BuildingTemplate and the library, as `from_idf_files` does."""
    template = _v2("archetypal.template.building_template", "BuildingTemplate").from_idf(idf, annual=True)
    library = _v2("archetypal.umi_template", "UmiTemplateLibrary")(name)
    library.BuildingTemplates = [template]
    library.unique_components(exceptions=None)
    library.update_components_list(exceptions=None)
    return library


def reduce_one(idf_path: Path, epw: Path, out_json: Path, ep_version: str) -> dict[str, Any]:
    """Reduce one model with archetypal 2 and return a result record.

    The steps are `UmiTemplateLibrary.from_idf_files` -> `template_complexity_reduction`,
    unchanged except for the timers around each one.
    """
    os.environ["ENERGYPLUS_VERSION"] = ep_version
    times: dict[str, float] = {}
    record: dict[str, Any] = {"status": "error", "times_s": times}
    start = time.perf_counter()
    stage = "import"
    try:
        t = time.perf_counter()
        importlib.import_module("archetypal")  # only once ENERGYPLUS_VERSION is set
        times["import"] = time.perf_counter() - t
        record["archetypal_version"] = importlib.metadata.version("archetypal")
        record["eppy_version"] = importlib.metadata.version("eppy")

        stage, t = "load", time.perf_counter()
        idf = _load(idf_path, epw, ep_version)
        times["load"] = time.perf_counter() - t
        record["zones"] = len(idf.idfobjects["ZONE"])

        stage, t = "simulate", time.perf_counter()
        try:
            _simulate(idf)
        finally:
            times["simulate"] = time.perf_counter() - t

        stage, t = "reduce", time.perf_counter()
        library = _reduce(idf, out_json.stem)
        times["reduce"] = time.perf_counter() - t

        stage, t = "save", time.perf_counter()
        out_json.parent.mkdir(parents=True, exist_ok=True)
        library.save(path_or_buf=str(out_json))
        times["save"] = time.perf_counter() - t
        record["template"] = str(out_json)
        record["status"] = "ok"
    except BaseException as exc:
        record["stage"] = stage
        record["error_type"] = f"{type(exc).__module__}.{type(exc).__name__}"
        record["error"] = str(exc)[:2000]
        record["traceback"] = traceback.format_exc()[-4000:]
    times["total"] = time.perf_counter() - start
    # v3 is timed with archetypal already imported: leave out v2's import (one per process) too.
    times["total_excluding_simulation"] = times["total"] - times.get("simulate", 0.0) - times.get("import", 0.0)
    return record


# --------------------------------------------------------------------------------------------
# Driver: the whole set.
# --------------------------------------------------------------------------------------------


def machine() -> dict[str, Any]:
    """Describe the machine the baseline ran on (spec 002, Assumptions)."""
    return {
        "platform": platform.platform(),
        "processor": platform.processor() or platform.machine(),
        "cpu_count": os.cpu_count(),
        "python": platform.python_version(),
    }


def run_set(args: argparse.Namespace) -> int:
    """Reduce every selected building in a subprocess and write the results file."""
    with args.set.open("rb") as f:
        reference: dict[str, Any] = tomllib.load(f)  # pyright: ignore[reportUnknownMemberType]
    ep_version = dash(args.energyplus_version or reference.get("energyplus_version", "24.2"))
    cache = args.cache or default_cache()
    models_dir = args.models_dir or cache / "models"
    out_dir = (args.out.parent if args.out else cache / "v2_baseline").resolve()
    out = args.out or out_dir / "results.json"
    work = out_dir / "work"
    work.mkdir(parents=True, exist_ok=True)

    buildings = reference["building"]
    if args.only:
        wanted = set(args.only)
        buildings = [b for b in buildings if b["id"] in wanted]
        missing = wanted - {b["id"] for b in buildings}
        if missing:
            print(f"unknown building ids: {sorted(missing)}", file=sys.stderr)
            return 2

    results: list[dict[str, Any]] = []
    for b in buildings:
        idf = (models_dir / f"{b['id']}.idf").resolve()
        epw = (cache / "weather" / f"{b['climate_zone']}.epw").resolve()
        rec: dict[str, Any] = {"id": b["id"], "model": str(idf), "weather": str(epw)}
        if not idf.exists() or not epw.exists():
            rec |= {"status": "missing", "error": f"model or weather file not found ({idf}, {epw})"}
        else:
            rec["model_version"] = file_version(idf)
            cmd = [
                sys.executable,
                "-I",
                str(Path(__file__).resolve()),
                "--worker",
                str(idf),
                str(epw),
                str(out_dir / "templates" / f"{b['id']}.json"),
                ep_version,
            ]
            bdir = work / b["id"]
            bdir.mkdir(parents=True, exist_ok=True)
            t = time.perf_counter()
            try:
                proc = subprocess.run(  # noqa: S603 - runs this script with this interpreter
                    cmd, check=False, cwd=bdir, capture_output=True, text=True, timeout=args.timeout
                )
                lines = [line for line in proc.stdout.splitlines() if line.startswith("{")]
                if lines:
                    rec |= json.loads(lines[-1])
                else:
                    rec |= {
                        "status": "error",
                        "error_type": "worker crashed",
                        "error": (proc.stderr or proc.stdout)[-2000:],
                        "returncode": proc.returncode,
                    }
            except subprocess.TimeoutExpired:
                rec |= {"status": "timeout", "error": f"no result after {args.timeout} s"}
            rec["wall_s"] = time.perf_counter() - t
        results.append(rec)
        print(
            f"{rec['status']:8} {b['id']:24} {rec.get('wall_s', 0):8.1f} s  {rec.get('error_type', '')}"
            f" {str(rec.get('error', ''))[:120]}",
            flush=True,
        )

    ok = [r for r in results if r["status"] == "ok"]
    summary = {
        "buildings": len(results),
        "ok": len(ok),
        "failed": len(results) - len(ok),
        "total_s": sum(r["times_s"]["total"] for r in ok),
        "total_excluding_simulation_s": sum(r["times_s"]["total_excluding_simulation"] for r in ok),
    }
    payload: dict[str, Any] = {
        "energyplus_version": ep_version,
        "machine": machine(),
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "summary": summary,
        "results": results,
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"\n{summary['ok']}/{summary['buildings']} reduced; results in {out}")
    return 0 if summary["failed"] == 0 else 1


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] == "--worker":
        idf, epw, out_json, ep_version = argv[1:5]
        print(json.dumps(reduce_one(Path(idf), Path(epw), Path(out_json), ep_version)))
        return 0

    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--set", type=Path, default=DEFAULT_SET, help="reference-set TOML file")
    parser.add_argument("--cache", type=Path, default=None, help="cache folder of report.py --fetch")
    parser.add_argument(
        "--models-dir",
        type=Path,
        default=None,
        help="folder of <building id>.idf models (default <cache>/models); "
        "point it at the models migrated to the EnergyPlus version",
    )
    parser.add_argument(
        "--energyplus-version", default=None, help="EnergyPlus version v2 uses, e.g. 24.2 (default: the set's)"
    )
    parser.add_argument("--only", nargs="+", default=None, metavar="ID", help="building ids to run")
    parser.add_argument("--timeout", type=float, default=3600, help="seconds per building")
    parser.add_argument("--out", type=Path, default=None, help="results JSON file")
    return run_set(parser.parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
