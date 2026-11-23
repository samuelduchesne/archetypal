"""Reference-set evidence for spec 002 (reduce to SBEM): SC-001 to SC-008.

Four steps, each its own option, run in this order:

```console
$ uv run python verification/report.py --fetch      # download and check the set
$ uv run python verification/report.py --migrate    # migrate each model to EnergyPlus 24.2
$ uv run python verification/report.py --run        # simulate, reduce, compare: results JSON
$ uv run python verification/report.py --write-page # results JSON -> the evidence page
```

`--stand-in MODEL.idf` (repeatable) runs the same pipeline on any EnergyPlus 24.2 model instead
of the migrated set, on epinterface's bundled weather; `--stand-in tests/fixtures/models/three_zone.idf`
exercises every code path without the reference set. Stand-in results are a smoke test, never
evidence: `--write-page` refuses them unless `--page` names another file.

**Fetch.** Downloads every archive and weather file listed in `verification/reference_set.toml`,
checks their SHA-256, extracts each building's model and weather file and checks theirs. Files
land in the cache folder (default `~/.cache/archetypal/reference-set`, or
`$ARCHETYPAL_REFERENCE_CACHE`), never in the repository:

- `archives/<archive id>.zip` and `weather/<station>.zip`: the downloads;
- `models/<building id>.idf`: each building's model, as published (EnergyPlus 22.1 or 23.1);
- `weather/<climate zone>.epw`: each climate zone's weather file.

A file already in the cache with the right hash is not downloaded again. A hash mismatch is an
error: the publisher changed the file, and the reference set must be updated deliberately.
`--fetch` uses the standard library only, so it also runs with a bare `python3`.

**Migrate.** Migrates each model with `idfkit.migration.migrate` to the set's EnergyPlus version
(24.2), into `migrated/<building id>.idf`. idfkit runs EnergyPlus's transition programs
(`PreProcess/IDFVersionUpdater/Transition-V*`). An EnergyPlus installed without them cannot
migrate: the step then names the missing programs, migrates nothing and exits with status 3.

**Run.** For each migrated building (or stand-in):

1. the detailed model is simulated once with EnergyPlus 24.2 through `idfkit.simulation.simulate`
   and a `SimulationCache`, with every output of `RESULTS_REQUIREMENTS` added (research R2);
2. it is reduced at every layout (timed: SC-008), each zone is accounted for (SC-006), the
   conserved totals are checked (SC-005) and merging the finest reduction to each coarser layout
   is compared with reducing directly (SC-007);
3. each archetype is built by epinterface's builder (`Model.from_archetype` on a shoebox drawn
   from the archetype's own geometry) and simulated with the same weather, run period, timestep
   and tabular units as the detailed run;
4. both results are compared with `archetypal.compare` (FR-028 comparability, and the rows of the
   SQLite files as written). An ideal-loads archetype's SQLite file holds *delivered* heating and
   cooling, not consumed fuel, and no fan energy: epinterface computes those afterwards (delivered
   energy times the energy input ratio, specific fan power times supply air volume; research
   R13 and R19). The judged rows therefore take the archetype's end uses from epinterface's
   post-processing and its peaks from the hourly delivered energy times the same energy input
   ratio, with the detailed side read by `archetypal.comparison` unchanged;
5. the migrated model and the detailed results are copied to `<cache>/results/<id>/`
   (`<id>.idf`, `<id>.sql`), where the reference tests look for them;
6. with a v2 baseline (`verification/run_v2_baseline.py`), each v2 template is read with
   `archetypal.read_umi`, simulated the same way at the core/perimeter shoebox, and compared
   (SC-004).

The results JSON (default `<cache>/results/results.json`) records the benchmark machine
(`BENCHMARK`, spec Assumptions) and every value the page shows.

**Write page.** Renders `docs/explanation/reference-evidence.md` from the results JSON; without
results it writes the page stating that the evidence is pending.
"""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import json
import math
import os
import platform
import re
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import warnings
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, cast

if sys.version_info >= (3, 11):
    import tomllib
else:  # Python 3.10: the same parser, as the tomli package (a dependency of pytest there)
    import tomli as tomllib  # pyright: ignore[reportMissingImports]

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DEFAULT_SET = HERE / "reference_set.toml"
DEFAULT_PAGE = ROOT / "docs" / "explanation" / "reference-evidence.md"
CHUNK = 1 << 20
RESULTS_SCHEMA = 1
NO_TRANSITION_PROGRAMS = 3

BENCHMARK: dict[str, Any] = {
    "description": (
        "a recent laptop-class computer (x86-64 or arm64) with at least four CPU cores and 8 GB of "
        "memory, running Linux, macOS or Windows with no other heavy load"
    ),
    "min_cpus": 4,
    "min_memory_gb": 8.0,
}
"""The benchmark machine of SC-008 (spec 002, Assumptions: "the plan fixes the benchmark machine")."""

RTOL = 1e-3
"""SC-005 and SC-007: 0.1 %."""
LARGEST_BUDGET_S = 10.0
"""SC-008: the largest building reduces in under 10 s."""
SCHEDULE_BUDGET_S = 7.0
"""Research R5: the largest building's schedules evaluate in at most 7 s."""
SPEEDUP = 10.0
"""SC-008: the set reduces at least 10 times faster than v2."""
SC004_SHARE = 0.9
"""SC-004: v3 beats v2 on at least 90 % of buildings."""

LAYOUTS = ("space_use_exposure", "space_use", "core_perimeter", "single_zone")
DEFAULT_LAYOUT = "space_use_exposure"
SC004_LAYOUT = "core_perimeter"


class FetchError(RuntimeError):
    """A download failed or a file does not match its recorded SHA-256."""


@dataclass(frozen=True)
class Outcome:
    """What happened to one building or weather file."""

    name: str
    path: Path | None
    error: str | None = None


def default_cache() -> Path:
    """Return the cache folder: `$ARCHETYPAL_REFERENCE_CACHE` or `~/.cache/archetypal/reference-set`."""
    env = os.environ.get("ARCHETYPAL_REFERENCE_CACHE")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".cache" / "archetypal" / "reference-set"


def default_results(cache: Path) -> Path:
    """Return the default results JSON in the cache."""
    return cache / "results" / "results.json"


def load_set(path: Path) -> dict[str, Any]:
    """Read the reference-set file."""
    with path.open("rb") as f:
        data: dict[str, Any] = tomllib.load(f)  # pyright: ignore[reportUnknownMemberType]
    return data


def parse_version(text: str) -> tuple[int, int, int]:
    """Return `24.2` or `24.2.0` as `(24, 2, 0)`."""
    parts = [int(p) for p in text.replace("-", ".").split(".")]
    parts += [0] * (3 - len(parts))
    return (parts[0], parts[1], parts[2])


# ============================================================================================
# Fetch (standard library only)
# ============================================================================================


def sha256_file(path: Path) -> str:
    """Return the SHA-256 of a file, read in chunks."""
    h = hashlib.sha256()
    with path.open("rb") as f:
        while chunk := f.read(CHUNK):
            h.update(chunk)
    return h.hexdigest()


def download(url: str, dest: Path, sha256: str, user_agent: str) -> Path:
    """Download `url` to `dest` unless a file with the right hash is already there."""
    if dest.exists() and sha256_file(dest) == sha256:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    part = dest.with_name(dest.name + ".part")
    if not url.startswith("https://"):
        msg = f"refusing a non-HTTPS URL: {url}"
        raise FetchError(msg)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})  # noqa: S310 - HTTPS checked
    try:
        with urllib.request.urlopen(request, timeout=120) as response, part.open("wb") as out:  # noqa: S310
            while chunk := response.read(CHUNK):
                out.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        part.unlink(missing_ok=True)
        msg = f"cannot download {url}: {exc}"
        raise FetchError(msg) from exc
    actual = sha256_file(part)
    if actual != sha256:
        part.unlink(missing_ok=True)
        msg = f"{url}: SHA-256 {actual} does not match the recorded {sha256}"
        raise FetchError(msg)
    part.replace(dest)
    return dest


def extract(archive: Path, member: str, dest: Path, sha256: str) -> Path:
    """Extract one member of a zip to `dest` and check its hash."""
    if dest.exists() and sha256_file(dest) == sha256:
        return dest
    dest.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as zf:
        data = zf.read(member)
    actual = hashlib.sha256(data).hexdigest()
    if actual != sha256:
        msg = f"{archive.name}:{member}: SHA-256 {actual} does not match the recorded {sha256}"
        raise FetchError(msg)
    dest.write_bytes(data)
    return dest


def fetch(reference: dict[str, Any], cache: Path) -> list[Outcome]:
    """Download and check the whole set; return one outcome per building and weather file."""
    agent = reference.get("user_agent", "archetypal-verification")
    archives = {a["id"]: a for a in reference["archive"]}
    archive_paths: dict[str, Path | FetchError] = {}
    outcomes: list[Outcome] = []

    for w in reference.get("weather", []):
        name = f"weather {w['climate_zone']}"
        try:
            zpath = download(w["url"], cache / "weather" / Path(w["url"]).name, w["sha256"], agent)
            epw = extract(zpath, w["member"], cache / "weather" / f"{w['climate_zone']}.epw", w["member_sha256"])
            outcomes.append(Outcome(name, epw))
        except FetchError as exc:
            outcomes.append(Outcome(name, None, str(exc)))

    for b in reference["building"]:
        aid = b["archive"]
        if aid not in archive_paths:
            a = archives[aid]
            try:
                archive_paths[aid] = download(a["url"], cache / "archives" / f"{aid}.zip", a["sha256"], agent)
            except FetchError as exc:
                archive_paths[aid] = exc
        apath = archive_paths[aid]
        if isinstance(apath, FetchError):
            outcomes.append(Outcome(b["id"], None, str(apath)))
            continue
        try:
            model = extract(apath, b["member"], cache / "models" / f"{b['id']}.idf", b["sha256"])
            outcomes.append(Outcome(b["id"], model))
        except (FetchError, KeyError) as exc:
            outcomes.append(Outcome(b["id"], None, str(exc)))
    return outcomes


def run_fetch(reference: dict[str, Any], cache: Path) -> int:
    """`--fetch`: download and check the set, print one line per file."""
    outcomes = fetch(reference, cache)
    failed = [o for o in outcomes if o.error]
    for o in outcomes:
        print(f"{'FAIL' if o.error else 'ok  '} {o.name}: {o.error or o.path}")
    weather = [o for o in outcomes if o.name.startswith("weather ")]
    buildings = [o for o in outcomes if not o.name.startswith("weather ")]
    print(
        f"\n{sum(not o.error for o in buildings)}/{len(buildings)} buildings and "
        f"{sum(not o.error for o in weather)}/{len(weather)} weather files fetched and checked in {cache}"
    )
    return 1 if failed else 0


# ============================================================================================
# Migrate
# ============================================================================================


def file_version(idf: Path) -> tuple[int, int, int] | None:
    """Return the `Version` of an IDF file, read as text."""
    text = idf.read_text(errors="replace")
    joined = " ".join(line.split("!")[0].strip() for line in text.splitlines())
    marker = joined.lower().find("version,")
    if marker < 0:
        return None
    return parse_version(joined[marker + len("version,") :].split(";")[0].strip())


def missing_transition_programs(
    install_dir: Path, source: tuple[int, int, int], target: tuple[int, int, int]
) -> tuple[Path, list[str]]:
    """Return the transition folder and the `Transition-V*` programs of the chain it lacks."""
    from idfkit.migration import plan_migration_chain  # noqa: PLC0415 - not needed by --fetch

    updater = install_dir / "PreProcess" / "IDFVersionUpdater"
    missing: list[str] = []
    for a, b in plan_migration_chain(source=source, target=target):
        pattern = f"Transition-V{a[0]}-{a[1]}-*-to-V{b[0]}-{b[1]}-*"
        if not updater.is_dir() or not any(updater.glob(pattern)):
            missing.append(f"Transition-V{a[0]}-{a[1]}-{a[2]}-to-V{b[0]}-{b[1]}-{b[2]}")
    return updater, missing


def run_migrate(reference: dict[str, Any], cache: Path) -> int:
    """`--migrate`: migrate every fetched model to the set's EnergyPlus version."""
    from idfkit import load_idf  # noqa: PLC0415
    from idfkit.migration import migrate  # noqa: PLC0415
    from idfkit.simulation import find_energyplus  # noqa: PLC0415

    target = parse_version(reference.get("energyplus_version", "24.2"))
    models = cache / "models"
    out_dir = cache / "migrated"
    paths = [(b["id"], models / f"{b['id']}.idf") for b in reference["building"]]
    absent = [bid for bid, p in paths if not p.exists()]
    if absent:
        print(f"{len(absent)} models are not fetched ({', '.join(absent[:5])}...): run --fetch first", file=sys.stderr)
        return 1
    try:
        config = find_energyplus(version=target)
    except Exception as exc:
        print(f"EnergyPlus {'.'.join(map(str, target[:2]))} not found: {exc}", file=sys.stderr)
        return NO_TRANSITION_PROGRAMS
    sources = sorted({v for _, p in paths if (v := file_version(p)) is not None and v[:2] != target[:2]})
    lacking: dict[str, None] = {}
    updater = Path(config.install_dir) / "PreProcess" / "IDFVersionUpdater"
    for source in sources:
        updater, missing = missing_transition_programs(Path(config.install_dir), source, target)
        lacking.update(dict.fromkeys(missing))
    if lacking:
        print(
            f"Cannot migrate: the EnergyPlus {config.version[0]}.{config.version[1]} at {config.install_dir} has no "
            f"transition programs for the reference models' versions "
            f"({', '.join('.'.join(map(str, s[:2])) for s in sources)} -> {target[0]}.{target[1]}).\n"
            f"Missing from {updater}:\n  " + "\n  ".join(lacking) + "\n"
            "These programs ship with the full EnergyPlus installer (PreProcess/IDFVersionUpdater) and are "
            "absent from slim installs. Install them, then run --migrate again. Nothing was migrated, and "
            "--run, the reference tests and the evidence page stay pending until the set is migrated.",
            file=sys.stderr,
        )
        return NO_TRANSITION_PROGRAMS

    failed = 0
    out_dir.mkdir(parents=True, exist_ok=True)
    for bid, path in paths:
        dest = out_dir / f"{bid}.idf"
        try:
            report = migrate(load_idf(path), target_version=target, energyplus=config)
            report.migrated_model.save(dest)
            steps = len(report.steps)
            print(f"ok   {bid}: {steps} steps -> {dest}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {bid}: {type(exc).__name__}: {exc}")
    print(f"\n{len(paths) - failed}/{len(paths)} models migrated to {target[0]}.{target[1]} in {out_dir}")
    return 1 if failed else 0


# ============================================================================================
# Machine
# ============================================================================================


def _cpu_model() -> str:
    try:
        for line in Path("/proc/cpuinfo").read_text().splitlines():
            if line.lower().startswith(("model name", "hardware", "cpu model")):
                return line.split(":", 1)[1].strip()
    except OSError:
        pass
    if sys.platform == "darwin":
        try:
            return subprocess.run(
                ["/usr/sbin/sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True, check=False
            ).stdout.strip()
        except OSError:
            pass
    return platform.processor() or platform.machine()


def _memory_gb() -> float | None:
    if sys.platform == "win32":
        return _windows_memory_gb()
    try:
        pages = os.sysconf("SC_PHYS_PAGES")
        size = os.sysconf("SC_PAGE_SIZE")
    except (ValueError, OSError, AttributeError):
        return None
    return round(pages * size / 1024**3, 1)


def _windows_memory_gb() -> float | None:
    """Physical memory on Windows, which has no `os.sysconf` (`GlobalMemoryStatusEx`)."""
    import ctypes  # noqa: PLC0415 - Windows only

    class MemoryStatus(ctypes.Structure):
        _fields_: ClassVar = [
            ("dwLength", ctypes.c_ulong),
            ("dwMemoryLoad", ctypes.c_ulong),
            ("ullTotalPhys", ctypes.c_ulonglong),
            ("ullAvailPhys", ctypes.c_ulonglong),
            ("ullTotalPageFile", ctypes.c_ulonglong),
            ("ullAvailPageFile", ctypes.c_ulonglong),
            ("ullTotalVirtual", ctypes.c_ulonglong),
            ("ullAvailVirtual", ctypes.c_ulonglong),
            ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
        ]

    status = MemoryStatus()
    status.dwLength = ctypes.sizeof(MemoryStatus)
    windll = getattr(ctypes, "windll", None)
    if windll is None or not windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
        return None
    return round(status.ullTotalPhys / 1024**3, 1)


def _git_commit() -> str | None:
    try:
        out = subprocess.run(  # noqa: S603 - fixed command
            ["git", "-C", str(ROOT), "rev-parse", "HEAD"],  # noqa: S607 - git from PATH
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return None
    return out.stdout.strip() or None


def machine() -> dict[str, Any]:
    """Describe the machine the run is timed on, and whether it meets `BENCHMARK`."""
    cpus = os.cpu_count()
    memory = _memory_gb()
    # Unknown memory leaves the benchmark unknown rather than failing it.
    meets = None if memory is None else (cpus or 0) >= BENCHMARK["min_cpus"] and memory >= BENCHMARK["min_memory_gb"]
    return {
        "platform": platform.platform(),
        "cpu": _cpu_model(),
        "cpu_count": cpus,
        "memory_gb": memory,
        "python": platform.python_version(),
        "meets_benchmark": meets,
    }


def versions() -> dict[str, str | None]:
    """The versions of the packages the run used."""
    import importlib.metadata  # noqa: PLC0415

    out: dict[str, str | None] = {}
    for name in ("archetypal", "epinterface", "idfkit"):
        try:
            out[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:  # noqa: PERF203 - three packages
            out[name] = None
    out["git_commit"] = _git_commit()
    return out


# ============================================================================================
# Run: detailed simulation, reduction, archetype simulation, comparison
# ============================================================================================

_FUEL_COLUMNS = {
    "Electricity": "Electricity",
    "NaturalGas": "Natural Gas",
    "Propane": "Propane",
    "FuelOil": "Fuel Oil No 2",
    "Coal": "Coal",
    "Gasoline": "Gasoline",
    "Diesel": "Diesel",
    "Steam": "District Heating Steam",
    "ChilledWater": "District Cooling",
    "WoodPellets": "Other Fuel 1",
    "CustomFuel": "Other Fuel 1",
}
"""epinterface's fuels as the End Uses table names them, when the detailed model uses no match."""

_EP_END_USES = {
    "Lighting": "Interior Lighting",
    "Equipment": "Interior Equipment",
    "Fans": "Fans",
    "Heating": "Heating",
    "Cooling": "Cooling",
    "Domestic Hot Water": "Water Systems",
}
"""epinterface's end uses as the End Uses table names them."""

_TO_UNITS = {"GJ": 3.6e-3, "MJ": 3.6, "kWh": 1.0, "kBtu": 3.412141633}
"""kWh in each tabular energy unit."""

_TABLE_UNITS = {"none": None, "jtokwh": "kWh", "jtomj": "MJ", "jtogj": "GJ", "inchpound": "kBtu"}


@dataclass
class Building:
    """One building to run: its id, migrated model and weather."""

    id: str
    model: Path
    epw: Path
    weather_zip: Path
    climate_zone: str | None = None
    building_type: str | None = None


def _ddy_with_extremes(ddy_text: str) -> str:
    """Return a `.ddy` with the `Summer Extreme` and `Winter Extreme` weather-file periods epinterface sizes with.

    EnergyPlus's TMY3 `.ddy` files carry design days only; the periods themselves are in the EPW
    header (`TYPICAL/EXTREME PERIODS`), so naming them is enough.
    """
    lines = [ddy_text.rstrip(), ""]
    for name, kind, day in (
        ("Summer Extreme", "SummerExtreme", "SummerDesignDay"),
        ("Winter Extreme", "WinterExtreme", "WinterDesignDay"),
    ):
        if re.search(rf"^\s*{name}\s*[,;]", ddy_text, re.MULTILINE):
            continue
        lines += [
            "SizingPeriod:WeatherFileConditionType,",
            f"  {name},                  !- Name",
            f"  {kind},                  !- Period Selection",
            f"  {day},                   !- Day of Week for Start Day",
            "  Yes,                     !- Use Weather File Daylight Saving Period",
            "  Yes;                     !- Use Weather File Rain and Snow Indicators",
            "",
        ]
    return "\n".join(lines) + "\n"


def epinterface_weather(source_zip: Path, dest_dir: Path) -> tuple[Path, Path]:
    """Return a weather zip epinterface can size with, and its EPW, both under `dest_dir`.

    The zip holds the source's EPW unchanged and its `.ddy` with the extreme periods added.
    """
    dest_dir.mkdir(parents=True, exist_ok=True)
    out = dest_dir / source_zip.name
    with zipfile.ZipFile(source_zip) as zf:
        names = zf.namelist()
        epw_name = next(n for n in names if n.lower().endswith(".epw"))
        ddy_name = next(n for n in names if n.lower().endswith(".ddy"))
        epw_bytes = zf.read(epw_name)
        ddy_text = zf.read(ddy_name).decode("latin-1")
    epw = dest_dir / Path(epw_name).name
    if not epw.exists() or epw.read_bytes() != epw_bytes:
        epw.write_bytes(epw_bytes)
    if not out.exists():
        with zipfile.ZipFile(out, "w") as zf:
            zf.writestr(Path(epw_name).name, epw_bytes)
            zf.writestr(Path(ddy_name).name, _ddy_with_extremes(ddy_text).encode("latin-1"))
    return out, epw


def reference_buildings(reference: dict[str, Any], cache: Path, only: Sequence[str] = ()) -> list[Building]:
    """Return the migrated buildings of the set (raises if none is migrated)."""
    weather = {w["climate_zone"]: w for w in reference.get("weather", [])}
    out: list[Building] = []
    for b in reference["building"]:
        if only and b["id"] not in only:
            continue
        model = cache / "migrated" / f"{b['id']}.idf"
        w = weather[b["climate_zone"]]
        source_zip = cache / "weather" / Path(w["url"]).name
        if not model.exists() or not source_zip.exists():
            continue
        wzip, epw = epinterface_weather(source_zip, cache / "epinterface-weather")
        out.append(Building(b["id"], model, epw, wzip, b["climate_zone"], b.get("building_type")))
    return out


def stand_in_buildings(models: Sequence[Path], cache: Path) -> list[Building]:
    """Return stand-in buildings on epinterface's bundled weather (Boston Logan, TMYx)."""
    from epinterface.data import DefaultEPWZipPath  # noqa: PLC0415

    wzip, epw = epinterface_weather(Path(DefaultEPWZipPath), cache / "epinterface-weather")
    return [Building(p.stem, p.resolve(), epw, wzip) for p in models]


# --- detailed run -----------------------------------------------------------------------------


def simulate_detailed(doc: Any, epw: Path, cache: Any) -> Path:
    """Simulate a copy of the model with every output reduction needs; return its SQLite file.

    Sub-hourly heating and cooling meters are dropped from the copy so that both runs' meters share
    the hourly frequency `RESULTS_REQUIREMENTS` asks for (FR-028).
    """
    from idfkit.simulation import simulate  # noqa: PLC0415

    from archetypal.reduction.requirements import add_missing_outputs, single_run_facts  # noqa: PLC0415
    from archetypal.reduction.sources import model_facts  # noqa: PLC0415

    model = doc.copy()
    for meter in list(model["Output:Meter"]):
        name = str(meter.key_name).casefold()
        if name.startswith(("heating:", "cooling:")) and str(meter.reporting_frequency).casefold() in {
            "timestep",
            "detailed",
        }:
            model.removeidfobject(meter)
    add_missing_outputs(model, single_run_facts(model_facts(model, ())))
    result = simulate(model, epw, cache=cache)
    result.raise_for_status()
    if result.sql_path is None:
        msg = "the detailed run wrote no SQLite file"
        raise RuntimeError(msg)
    return Path(result.sql_path)


# --- reduction checks ---------------------------------------------------------------------------


def flatten(model: object, prefix: str = "") -> dict[str, float]:
    """Every additive total of a ledger as `path -> value`; a profile counts as its sum."""
    import numpy as np  # noqa: PLC0415
    from pydantic import BaseModel  # noqa: PLC0415

    out: dict[str, float] = {}
    if isinstance(model, BaseModel):
        for name in type(model).model_fields:
            if name in {"members", "excluded_envelope"}:
                continue
            out.update(flatten(getattr(model, name), f"{prefix}{name}."))
    elif isinstance(model, dict):
        for key, value in cast("dict[str, object]", model).items():
            out.update(flatten(value, f"{prefix}{key}."))
    elif isinstance(model, np.ndarray):
        out[prefix.rstrip(".")] = float(np.sum(model))  # pyright: ignore[reportUnknownArgumentType]
    elif isinstance(model, (int, float)) and not isinstance(model, bool):
        out[prefix.rstrip(".")] = float(model)
    return out


def _relative(actual: float, expected: float) -> float:
    """Relative difference; 0 when both are 0, infinite when only the expected total is 0."""
    if expected == 0.0:
        return 0.0 if actual == 0.0 else math.inf
    return abs(actual - expected) / abs(expected)


def _worst(pairs: Mapping[str, tuple[float, float]]) -> dict[str, Any]:
    """Summarise `name -> (actual, expected)` against 0.1 %."""
    rel = {k: _relative(a, e) for k, (a, e) in pairs.items()}
    failures = sorted(k for k, r in rel.items() if r > RTOL)
    worst = max(rel.values(), default=0.0)
    return {
        "totals": len(pairs),
        "max_relative": None if math.isinf(worst) else worst,
        "failures": failures[:20],
        "passed": not failures,
    }


@dataclass
class Detailed:
    """What the reduction checks read from the detailed model directly."""

    zone_names: frozenset[str]
    conditioned_area: float
    meters_by_fuel: dict[str, float]
    fan_meter: float
    hot_water_volume: float
    schedule_seconds: float
    zones: int


def read_detailed(model: Path, results: Path) -> Detailed:
    """Read the detailed model's own totals: zones, conditioned area, meters, hot water."""
    from archetypal.reduction.classify import classify  # noqa: PLC0415
    from archetypal.reduction.inventory import build_inventory  # noqa: PLC0415
    from archetypal.reduction.schedules import ScheduleEvaluator  # noqa: PLC0415
    from archetypal.reduction.sources import load_sources  # noqa: PLC0415

    sources = load_sources(model, results)
    try:
        start = time.perf_counter()
        evaluate = ScheduleEvaluator(sources.model, sources.run_period.calendar)
        for name in schedule_names(sources.model):
            evaluate(name)
        schedule_seconds = time.perf_counter() - start
        zones = classify(build_inventory(sources, evaluate), evaluate)
        sql = sources.results
        meters: dict[str, float] = {}
        fan = 0.0
        hot_water = 0.0
        for info in sql.list_variables():
            if info.frequency != "Hourly":
                continue
            end_use, _, fuel = info.name.partition(":")
            if info.is_meter and end_use in {"Heating", "Cooling", "WaterSystems", "Pumps", "HeatRejection"}:
                meters[fuel] = meters.get(fuel, 0.0) + _series_sum(sql, info.name, "*")
            elif info.is_meter and info.name == "Fans:Electricity":
                fan = _series_sum(sql, info.name, "*")
            elif not info.is_meter and info.name == "Water Use Equipment Hot Water Volume":
                hot_water += _series_sum(sql, info.name, info.key_value)
        area = math.fsum(z.zone.floor_area * z.zone.multiplier for z in zones if z.role == "conditioned")
        names = frozenset(str(z.name).casefold() for z in sources.model["Zone"])
        return Detailed(names, area, meters, fan, hot_water, schedule_seconds, len(names))
    finally:
        sources.results.close()


def schedule_names(doc: Any) -> list[str]:
    """Every schedule of the model a reduction may evaluate."""
    kinds = ("Schedule:Compact", "Schedule:Year", "Schedule:Constant", "Schedule:File")
    return [str(o.name) for kind in kinds for o in doc[kind]]


def _series_sum(sql: Any, name: str, key: str) -> float:
    (series,) = sql.get_timeseries_many([(name, key, "Hourly")], environment="annual")
    return math.fsum(float(v) for v in series.values)


def check_conservation(reduction: Any, finest_totals: Mapping[str, float], detailed: Detailed) -> dict[str, Any]:
    """SC-005 for one layout: the groups hold the finest totals and the detailed model's anchors.

    Two checks, each within 0.1 % (exactly where the expected total is 0): every additive total of
    the groups' ledgers equals the same total at the finest layout before the small-group threshold
    (all of FR-014 to FR-022a, layout by layout), and the anchors read from the detailed model
    directly (conditioned floor area, conditioning meters by fuel, fan meter, hot water volume)
    are in the groups.
    """
    from archetypal.reduction.ledger import GroupLedger  # noqa: PLC0415

    building = sum((g.ledger for g in reduction.report.groups), GroupLedger())
    totals = flatten(building)
    layout_pairs = {k: (totals.get(k, 0.0), v) for k, v in finest_totals.items()}
    layout_pairs |= {k: (v, 0.0) for k, v in totals.items() if k not in finest_totals and v != 0.0}

    anchors: dict[str, tuple[float, float]] = {"floor_area": (building.floor_area, detailed.conditioned_area)}
    archetype_area = reduction.archetype.Geometry.ConditionedFloorArea or 0.0
    anchors["Geometry.ConditionedFloorArea"] = (archetype_area, detailed.conditioned_area)
    in_groups: dict[str, float] = {}
    for energy in building.energy.values():
        for values in (energy.consumed_by_fuel, energy.distribution_by_fuel, energy.unattributed):
            for fuel, value in values.items():
                in_groups[fuel] = in_groups.get(fuel, 0.0) + value
    for fuel in set(in_groups) | set(detailed.meters_by_fuel):
        anchors[f"energy.{fuel}"] = (in_groups.get(fuel, 0.0), detailed.meters_by_fuel.get(fuel, 0.0))
    unattributed_fans = math.fsum(
        n.magnitude or 0.0 for n in reduction.report.not_represented if n.feature == "Fans serving no conditioned zone"
    )
    anchors["fans.energy"] = (building.fans.energy + unattributed_fans, detailed.fan_meter)
    anchors["hot_water.volume"] = (float(building.hot_water.volume.sum()), detailed.hot_water_volume)

    layout = _worst(layout_pairs)
    anchor = _worst(anchors)
    return {"layout_totals": layout, "detailed_anchors": anchor, "passed": layout["passed"] and anchor["passed"]}


def check_zones(reduction: Any, detailed: Detailed) -> dict[str, Any]:
    """SC-006: every detailed zone is in exactly one group or excluded, with a reason."""
    members = [m.casefold() for g in reduction.report.groups for m in g.ledger.members]
    excluded = [z.zone.casefold() for z in reduction.report.excluded_zones]
    accounted = members + excluded
    missing = sorted(detailed.zone_names - set(accounted))
    twice = sorted({z for z in accounted if accounted.count(z) > 1})
    return {
        "zones": len(detailed.zone_names),
        "in_groups": len(members),
        "excluded": len(excluded),
        "missing": missing[:20],
        "counted_twice": twice[:20],
        "passed": not missing and not twice,
    }


def _json_differences(a: Any, b: Any, path: str, out: list[tuple[str, float | None]]) -> None:
    """Collect `(path, relative difference or None for a structural one)` beyond 0.1 %."""
    if isinstance(a, dict) and isinstance(b, dict):
        for key in sorted(set(a) | set(b)):  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            if key not in a or key not in b:
                out.append((f"{path}.{key}", None))
            else:
                _json_differences(a[key], b[key], f"{path}.{key}", out)
    elif isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):  # pyright: ignore[reportUnknownArgumentType]
            out.append((path, None))
            return
        for i, (x, y) in enumerate(zip(a, b, strict=True)):  # pyright: ignore[reportUnknownArgumentType, reportUnknownVariableType]
            _json_differences(x, y, f"{path}[{i}]", out)
    elif isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        rel = _relative(float(a), float(b))
        if rel > RTOL:
            out.append((path, None if math.isinf(rel) else rel))
    elif a != b:
        out.append((path, None))


def check_merge(merged: Any, direct: Any) -> dict[str, Any]:
    """SC-007: the merged and the direct archetypes, and their report parameters, agree within 0.1 %."""
    found: list[tuple[str, float | None]] = []
    _json_differences(
        merged.archetype.model_dump(mode="json"), direct.archetype.model_dump(mode="json"), "archetype", found
    )
    mp = {(p.group, p.path): p.value for p in merged.report.parameters}
    dp = {(p.group, p.path): p.value for p in direct.report.parameters}
    _json_differences(
        {f"{g}:{p}": v for (g, p), v in mp.items()}, {f"{g}:{p}": v for (g, p), v in dp.items()}, "parameters", found
    )
    numeric = [r for _, r in found if r is not None]
    return {
        "differences": len(found),
        "max_relative": max(numeric, default=0.0),
        "examples": [p for p, _ in found[:10]],
        "passed": not found,
    }


# --- archetype run -------------------------------------------------------------------------------


def shoebox(archetype: Any) -> Any:
    """A shoebox with the archetype's storeys, floor area and facade proportions.

    The footprint is the conditioned floor area over the storeys; its sides are in the ratio of
    the north to the east facade area, and the floor-to-floor height gives the north facade's
    area. Core/perimeter zoning is used whenever a group is a core group. The same rule as
    `tests/integration/test_epinterface_build.py`.
    """
    from epinterface.geometry import ShoeboxGeometry  # noqa: PLC0415

    geometry = archetype.Geometry
    storeys = geometry.Storeys or 1
    area = geometry.ConditionedFloorArea
    if area is None:
        msg = f"archetype {archetype.Name!r} has no conditioned floor area to draw a shoebox from"
        raise ValueError(msg)
    facade: dict[str, float] = geometry.FacadeAreaPerFloorArea or {}
    north, east = facade.get("N", 0.0), facade.get("E", 0.0)
    footprint = area / storeys
    width = math.sqrt(footprint * north / east) if north > 0 and east > 0 else math.sqrt(footprint)
    depth = footprint / width
    height = north * area / (storeys * width) if north > 0 else 3.0
    # A core only when the archetype has one: a perimeter-only archetype gives every zone a facade.
    zoning = "core/perim" if any(g.Exposure == "core" for g in archetype.Groups) else "by_storey"
    return ShoeboxGeometry(
        x=0.0,
        y=0.0,
        w=width,
        d=depth,
        h=height,
        num_stories=storeys,
        zoning=zoning,
        perim_depth=min(4.5, depth / 3, width / 3),
    )


def align_settings(archetype_doc: Any, detailed_doc: Any) -> None:
    """Give the archetype's model the detailed run's run period, timestep and tabular units (FR-028)."""
    timestep = next(iter(detailed_doc["Timestep"]), None)
    if timestep is not None:
        for t in archetype_doc["Timestep"]:
            t.number_of_timesteps_per_hour = timestep.number_of_timesteps_per_hour
    source = next(iter(detailed_doc["RunPeriod"]), None)
    target = next(iter(archetype_doc["RunPeriod"]), None)
    if source is not None and target is not None:
        for name in (
            "begin_month",
            "begin_day_of_month",
            "begin_year",
            "end_month",
            "end_day_of_month",
            "end_year",
            "day_of_week_for_start_day",
            "use_weather_file_holidays_and_special_days",
            "use_weather_file_daylight_saving_period",
            "apply_weekend_holiday_rule",
        ):
            setattr(target, name, getattr(source, name))
    style = next(iter(detailed_doc["OutputControl:Table:Style"]), None)
    if style is not None:
        for s in archetype_doc["OutputControl:Table:Style"]:
            s.unit_conversion = style.unit_conversion
    sqlite = next(iter(detailed_doc["Output:SQLite"]), None)
    if sqlite is not None:
        for s in archetype_doc["Output:SQLite"]:
            s.unit_conversion_for_tabular_data = sqlite.unit_conversion_for_tabular_data


@dataclass
class ArchetypeRun:
    """An archetype simulated through epinterface: its SQLite file and epinterface's energy."""

    sql: Path
    end_uses_kwh: dict[str, float]
    fuels: dict[str, str]
    heating_peak_w: float
    cooling_peak_w: float
    area: float
    seconds: float


def simulate_archetype(
    archetype: Any, geometry: Any, building: Building, detailed_doc: Any, cache: Any, work: Path
) -> ArchetypeRun:
    """Build the archetype with epinterface's builder, simulate it like the detailed model, post-process it."""
    import numpy as np  # noqa: PLC0415
    from epinterface.sbem.builder import Model, SimulationPathConfig  # noqa: PLC0415
    from idfkit.simulation import SQLResult, simulate  # noqa: PLC0415

    start = time.perf_counter()
    model = Model.from_archetype(archetype, geometry, Weather=building.weather_zip)  # pyright: ignore[reportUnknownMemberType]
    config = SimulationPathConfig(output_dir=work, weather_dir=building.weather_zip.parent / "epinterface")
    doc = model.build(config)
    align_settings(doc, detailed_doc)
    result = simulate(doc, building.epw, cache=cache)
    result.raise_for_status()
    if result.sql_path is None:
        msg = "the archetype run wrote no SQLite file"
        raise RuntimeError(msg)
    sql = SQLResult(result.sql_path)
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", category=Warning)  # pandas' performance warnings in epinterface
            series = model.standard_results_postprocess(sql, ep_version_major=doc.version[0])
            energy = cast("Any", series.loc["Energy", "End Uses"])  # pyright: ignore[reportUnknownMemberType]
        area = float(model.total_conditioned_area)
        end_uses = {str(m): float(energy.loc[m].sum()) * area for m in energy.index.get_level_values(0).unique()}  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType, reportUnknownVariableType]
        systems = model.Zone.Operations.HVAC.ConditioningSystems
        fuels = {
            "Heating": systems.Heating.Fuel if systems.Heating is not None else "Electricity",
            "Cooling": systems.Cooling.Fuel if systems.Cooling is not None else "Electricity",
            "Domestic Hot Water": model.Zone.Operations.DHW.FuelType,
        }
        t_out = np.asarray(
            sql.get_timeseries(
                "Site Outdoor Air Drybulb Temperature", "Environment", "Hourly", environment="annual"
            ).values,
            dtype=float,
        )
        peaks: dict[str, float] = {}
        for mode, system in (("Heating", systems.Heating), ("Cooling", systems.Cooling)):
            delivered = np.zeros_like(t_out)
            for info in sql.list_variables():
                if (
                    info.is_meter
                    and info.frequency == "Hourly"
                    and info.name.startswith(f"{mode}:")
                    and not info.name.endswith("EnergyTransfer")
                ):
                    values = sql.get_timeseries(info.name, "*", "Hourly", environment="annual").values
                    delivered += np.asarray(values, dtype=float)
            eir = system.energy_input_ratio(t_out) if system is not None else np.ones_like(t_out)
            peaks[mode] = (
                float(np.asarray(delivered * eir, dtype=np.float64).max(initial=0.0)) / 3600.0
            )  # J per hour -> W
    finally:
        sql.close()
    return ArchetypeRun(
        sql=Path(result.sql_path),
        end_uses_kwh=end_uses,
        fuels=fuels,
        heating_peak_w=peaks["Heating"],
        cooling_peak_w=peaks["Cooling"],
        area=area,
        seconds=time.perf_counter() - start,
    )


def _fuel_column(sbem_fuel: str, detailed_fuels: Iterable[str]) -> str:
    """The End Uses column of an epinterface fuel: the detailed model's matching fuel when unique."""
    from archetypal.reduction.to_sbem import _sbem_fuel  # pyright: ignore[reportPrivateUsage]  # noqa: PLC0415

    matches = sorted({f for f in detailed_fuels if _sbem_fuel(f) == sbem_fuel})
    if len(matches) == 1:
        return matches[0]
    return _FUEL_COLUMNS.get(sbem_fuel, sbem_fuel)


def consumed_run(archetype_raw: Any, run: ArchetypeRun, detailed_run: Any) -> Any:
    """The archetype's results as epinterface reports them, in the comparison's form.

    End uses come from epinterface's post-processing (heating and cooling consumed, fans), in the
    detailed run's tabular unit; peaks are hourly delivered heating and cooling times the same energy
    input ratio. Weather, run period, timestep and frequency stay those of the archetype's SQLite file.
    """
    units = detailed_run.units
    if units not in _TO_UNITS:
        msg = f"tabular energy unit {units!r} is not one this report converts epinterface's kWh to"
        raise ValueError(msg)
    factor = _TO_UNITS[units]
    detailed_fuels = [fuel for _, fuel in detailed_run.end_uses]
    end_uses: dict[tuple[str, str], float] = {}
    for meter, kwh in run.end_uses_kwh.items():
        if kwh == 0.0:
            continue
        if meter not in _EP_END_USES:
            msg = f"epinterface reports an end use {meter!r} this report does not map"
            raise ValueError(msg)
        fuel = _fuel_column(run.fuels.get(meter, "Electricity"), detailed_fuels)
        key = (_EP_END_USES[meter], fuel)
        end_uses[key] = end_uses.get(key, 0.0) + kwh * factor
    return dataclasses.replace(
        archetype_raw,
        total_site=math.fsum(end_uses.values()),
        end_uses=end_uses,
        peaks={"Heating": run.heating_peak_w, "Cooling": run.cooling_peak_w},
        to_heating={},
        to_cooling={},
    )


def _dict(value: object) -> dict[str, Any]:
    """`value` when it is a dict, else an empty one (for optional parts of a results record)."""
    return cast("dict[str, Any]", value) if isinstance(value, dict) else {}


def _row_dict(row: Any) -> dict[str, Any]:
    return {f.name: getattr(row, f.name) for f in dataclasses.fields(row)}


def compare_runs(detailed_sql: Path, run: ArchetypeRun, epw: Path) -> dict[str, Any]:
    """Compare the detailed run with an archetype run: raw SQLite rows and the judged rows."""
    from idfkit.simulation import SQLResult  # noqa: PLC0415

    from archetypal import compare  # noqa: PLC0415
    from archetypal.comparison import AcceptanceTargets  # noqa: PLC0415
    from archetypal.comparison import _rows as comparison_rows  # pyright: ignore[reportPrivateUsage]  # noqa: PLC0415
    from archetypal.comparison.results import read_run  # noqa: PLC0415

    raw = compare(detailed_sql, run.sql, weather=epw)  # refuses incomparable runs (FR-028)
    targets = AcceptanceTargets()
    runs: list[Any] = []
    for path in (detailed_sql, run.sql):
        sql = SQLResult(path)
        try:
            runs.append(read_run(sql, str(path)))
        finally:
            sql.close()
    detailed_run, archetype_raw = runs
    judged = comparison_rows(detailed_run, consumed_run(archetype_raw, run, detailed_run), targets)
    return {
        "units": detailed_run.units,
        "weather_sha256": raw.weather_sha256,
        "raw_rows": [_row_dict(r) for r in raw.rows],
        "rows": [_row_dict(r) for r in judged],
        "archetype_area_m2": run.area,
        "simulation_s": run.seconds,
    }


def sc_verdicts(rows: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """SC-001 to SC-003 for one comparison: `True`, `False`, or `None` when nothing is judged."""

    def verdict(kinds: set[str]) -> bool | None:
        judged = [r["within_target"] for r in rows if r["kind"] in kinds and r["within_target"] is not None]
        return None if not judged else all(judged)

    return {
        "SC-001": verdict({"total_site"}),
        "SC-002": verdict({"end_use", "end_use_with_distribution"}),
        "SC-003": verdict({"peak"}),
        "mare": mean_abs_relative_error(rows),
    }


def judged_metrics(rows: Sequence[Mapping[str, Any]]) -> dict[str, float]:
    """`metric -> |relative|` of every row SC-001 to SC-003 judge."""
    return {
        r["metric"]: abs(r["relative"]) for r in rows if r["within_target"] is not None and r["relative"] is not None
    }


def mean_abs_relative_error(rows: Sequence[Mapping[str, Any]]) -> float | None:
    """SC-004's error: the mean absolute relative error over the judged rows."""
    errors = list(judged_metrics(rows).values())
    return math.fsum(errors) / len(errors) if errors else None


# --- one building ------------------------------------------------------------------------------


def run_building(building: Building, cache_dir: Path, v2_record: Mapping[str, Any] | None) -> dict[str, Any]:  # noqa: PLR0915 - one step per success criterion
    """Run every step for one building; never raises, records each failure."""
    from idfkit import load_idf  # noqa: PLC0415
    from idfkit.simulation import SimulationCache  # noqa: PLC0415

    from archetypal.reduction import merge, reduce  # noqa: PLC0415
    from archetypal.reduction.options import Layout, ReductionOptions  # noqa: PLC0415

    record: dict[str, Any] = {
        "id": building.id,
        "climate_zone": building.climate_zone,
        "type": building.building_type,
        "model": str(building.model),
        "model_sha256": sha256_file(building.model),
        "weather": building.epw.name,
        "status": "error",
        "layouts": {},
    }
    cache = SimulationCache(cache_dir=cache_dir / "simulations")
    work = cache_dir / "work" / building.id
    stage = "load"
    try:
        doc = load_idf(building.model)
        stage = "simulate detailed"
        start = time.perf_counter()
        detailed_sql = simulate_detailed(doc, building.epw, cache)
        record["detailed_simulation_s"] = time.perf_counter() - start
        export = cache_dir / "results" / building.id  # where tests/reference/ looks for model and results
        export.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(building.model, export / f"{building.id}.idf")
        shutil.copyfile(detailed_sql, export / f"{building.id}.sql")
        stage = "read detailed"
        detailed = read_detailed(building.model, detailed_sql)
        record["zones"] = detailed.zones
        record["conditioned_area_m2"] = detailed.conditioned_area
        record["schedule_evaluation_s"] = detailed.schedule_seconds

        reductions: dict[str, Any] = {}
        for name in LAYOUTS:
            stage = f"reduce {name}"
            layout = Layout(name)
            start = time.perf_counter()
            reductions[name] = reduce(
                building.model, detailed_sql, options=ReductionOptions(layout=layout), weather=building.epw
            )
            record["layouts"][name] = {
                "reduce_s": time.perf_counter() - start,
                "groups": len(reductions[name].report.groups),
            }
        finest = reductions[DEFAULT_LAYOUT]
        from archetypal.reduction.ledger import GroupLedger  # noqa: PLC0415

        finest_totals = flatten(sum((g.ledger for g in finest.report.pre_threshold_groups), GroupLedger()))
        for name, reduction in reductions.items():
            entry = record["layouts"][name]
            stage = f"check {name}"
            entry["sc005"] = check_conservation(reduction, finest_totals, detailed)
            entry["sc006"] = check_zones(reduction, detailed)
            if name != DEFAULT_LAYOUT:
                entry["sc007"] = check_merge(merge(finest, Layout(name)), reduction)
        record["status"] = "reduced"

        geometries: dict[str, Any] = {}
        for name, reduction in reductions.items():
            stage = f"simulate archetype {name}"
            entry = record["layouts"][name]
            try:
                geometries[name] = shoebox(reduction.archetype)
                run = simulate_archetype(reduction.archetype, geometries[name], building, doc, cache, work / name)
                entry["comparison"] = compare_runs(detailed_sql, run, building.epw)
                entry["sc"] = sc_verdicts(entry["comparison"]["rows"])
            except Exception as exc:
                entry["comparison_error"] = f"{type(exc).__name__}: {exc}"[:2000]
        record["status"] = "ok" if all("sc" in record["layouts"][n] for n in LAYOUTS) else "compared_partly"

        if v2_record is not None:
            stage = "v2 baseline"
            record["v2"] = run_v2(v2_record, geometries.get(SC004_LAYOUT), building, doc, detailed_sql, cache, work)
    except Exception as exc:
        record["stage"] = stage
        record["error"] = f"{type(exc).__name__}: {exc}"[:2000]
    return record


def run_v2(
    v2_record: Mapping[str, Any],
    geometry: Any,
    building: Building,
    doc: Any,
    detailed_sql: Path,
    cache: Any,
    work: Path,
) -> dict[str, Any]:
    """SC-004 and SC-008 inputs from v2: its timing, and its template simulated and compared."""
    out: dict[str, Any] = {
        "status": v2_record.get("status"),
        "reduce_s": _dict(v2_record.get("times_s")).get("total_excluding_simulation"),
    }
    template = v2_record.get("template")
    if v2_record.get("status") != "ok" or not template:
        out["error"] = v2_record.get("error")
        return out
    if geometry is None:
        out["error"] = "no core/perimeter shoebox (the v3 core/perimeter reduction failed)"
        return out
    try:
        from archetypal import read_umi  # noqa: PLC0415

        archetype = read_umi(template).archetypes[0]
        run = simulate_archetype(archetype, geometry, building, doc, cache, work / "v2")
        out["comparison"] = compare_runs(detailed_sql, run, building.epw)
        out["sc"] = sc_verdicts(out["comparison"]["rows"])
    except Exception as exc:
        out["error"] = f"{type(exc).__name__}: {exc}"[:2000]
    return out


# --- the set -----------------------------------------------------------------------------------


def _fraction(values: Sequence[bool | None]) -> dict[str, Any]:
    judged = [v for v in values if v is not None]
    return {"passed": sum(judged), "judged": len(judged), "all": bool(judged) and all(judged)}


def _benchmark_verdict(meets: object) -> str:
    """How the evidence page states whether the machine meets the benchmark (unknown memory aside)."""
    if meets is None:
        return "may meet (its memory is unknown)"
    return "meets" if meets else "does **not** meet"


def summarise(records: Sequence[Mapping[str, Any]], machine_info: Mapping[str, Any], expected: int) -> dict[str, Any]:
    """SC-001 to SC-008 for the set, from the per-building records."""
    out: dict[str, Any] = {"buildings": len(records), "expected": expected}
    # The criteria hold "for every building": one never compared (its run or comparison failed)
    # fails them, while a criterion its comparison did not judge (an end use too small) is left out.
    default = [r["layouts"].get(DEFAULT_LAYOUT, {}).get("sc") for r in records]
    for sc in ("SC-001", "SC-002", "SC-003"):
        out[sc] = _fraction([cast("dict[str, Any]", d).get(sc) if isinstance(d, dict) else False for d in default])
        out[sc]["all"] = out[sc]["all"] and len(records) == expected

    sc004: list[bool] = []
    v3_errors: list[float] = []
    v2_errors: list[float] = []
    for r in records:
        v3 = r["layouts"].get(SC004_LAYOUT, {}).get("sc", {}).get("mare")
        v2 = _dict(_dict(r.get("v2")).get("sc")).get("mare")
        if v3 is not None and v2 is not None:
            v3_errors.append(v3)
            v2_errors.append(v2)
            sc004.append(v3 < v2)
        elif v2 is not None:  # v2 reduced and compared this building, v3 did not: not better
            sc004.append(False)
    if sc004:
        v3_mean, v2_mean = math.fsum(v3_errors) / len(v3_errors), math.fsum(v2_errors) / len(v2_errors)
        share = sum(sc004) / len(sc004)
        out["SC-004"] = {
            "buildings": len(sc004),
            "v3_mare": v3_mean,
            "v2_mare": v2_mean,
            "share_better": share,
            "all": v3_mean < v2_mean and share >= SC004_SHARE,
        }
    else:
        out["SC-004"] = {"buildings": 0, "all": None, "pending": "no v2 baseline compared"}

    def layouts_pass(r: Mapping[str, Any], key: str, skip_default: bool = False) -> bool:
        items = [(n, e) for n, e in r["layouts"].items() if not (skip_default and n == DEFAULT_LAYOUT)]
        return len(r["layouts"]) == len(LAYOUTS) and all(e.get(key, {}).get("passed") for _, e in items)

    reduced = [r for r in records if r["status"] in {"reduced", "ok", "compared_partly"}]
    out["SC-005"] = _fraction([layouts_pass(r, "sc005") for r in reduced] + [False] * (len(records) - len(reduced)))
    out["SC-006"] = _fraction([layouts_pass(r, "sc006") for r in reduced] + [False] * (len(records) - len(reduced)))
    out["SC-007"] = _fraction(
        [layouts_pass(r, "sc007", skip_default=True) for r in reduced] + [False] * (len(records) - len(reduced))
    )
    for sc in ("SC-005", "SC-006", "SC-007"):
        out[sc]["all"] = out[sc]["all"] and len(records) == expected

    timed = [r for r in reduced if DEFAULT_LAYOUT in r["layouts"]]
    sc008: dict[str, Any] = {"meets_benchmark": machine_info.get("meets_benchmark")}
    if timed:
        largest = max(timed, key=lambda r: (r.get("zones", 0), r.get("conditioned_area_m2", 0.0)))
        sc008 |= {
            "largest": largest["id"],
            "largest_reduce_s": largest["layouts"][DEFAULT_LAYOUT]["reduce_s"],
            "largest_schedule_s": largest.get("schedule_evaluation_s"),
            "set_reduce_s": math.fsum(r["layouts"][DEFAULT_LAYOUT]["reduce_s"] for r in timed),
        }
        sc008["largest_ok"] = sc008["largest_reduce_s"] < LARGEST_BUDGET_S
        sc008["schedule_ok"] = (sc008["largest_schedule_s"] or 0.0) <= SCHEDULE_BUDGET_S
        pairs = [
            (r["layouts"][DEFAULT_LAYOUT]["reduce_s"], r["v2"]["reduce_s"])
            for r in timed
            if _dict(r.get("v2")).get("reduce_s") is not None
        ]
        if pairs:
            v3_total, v2_total = math.fsum(p[0] for p in pairs), math.fsum(p[1] for p in pairs)
            sc008 |= {"v2_buildings": len(pairs), "v3_paired_s": v3_total, "v2_paired_s": v2_total}
            sc008["speedup"] = v2_total / v3_total if v3_total > 0 else None
    speed = sc008.get("speedup")
    sc008["all"] = (
        None
        if speed is None or not machine_info.get("meets_benchmark")
        else bool(sc008["largest_ok"] and speed >= SPEEDUP)
    )
    out["SC-008"] = sc008
    return out


def load_v2(path: Path | None) -> dict[str, dict[str, Any]]:
    """Read the v2 baseline (`run_v2_baseline.py`), by building id; empty when absent."""
    if path is None or not path.exists():
        return {}
    data = json.loads(path.read_text())
    return {r["id"]: r for r in data.get("results", [])}


def run_set(args: argparse.Namespace, reference: dict[str, Any], cache: Path) -> int:
    """`--run`: every step for every building; write the results JSON."""
    if args.stand_in:
        buildings = stand_in_buildings([Path(p) for p in args.stand_in], cache)
        kind = "stand-in"
        expected = len(buildings)
    else:
        buildings = reference_buildings(reference, cache, args.only or ())
        kind = "reference"
        expected = len(args.only) if args.only else len(reference["building"])
        if not buildings:
            print(
                f"No migrated reference model in {cache / 'migrated'}: run --fetch and --migrate first "
                "(--migrate needs EnergyPlus's transition programs). Nothing was run.",
                file=sys.stderr,
            )
            return 1
    v2 = load_v2(args.v2_results or cache / "v2_baseline" / "results.json") if kind == "reference" else {}
    results_path: Path = args.results or (
        cache / "results" / "stand-in.json" if kind == "stand-in" else default_results(cache)
    )
    machine_info = machine()
    records: list[dict[str, Any]] = []
    for building in buildings:
        start = time.perf_counter()
        record = run_building(building, cache, v2.get(building.id))
        record["wall_s"] = time.perf_counter() - start
        records.append(record)
        default = record["layouts"].get(DEFAULT_LAYOUT, {})
        sc = default.get("sc", {})
        print(
            f"{record['status']:16} {building.id:28} {record['wall_s']:7.1f} s  "
            + " ".join(f"{k}={v}" for k, v in sc.items() if k.startswith("SC"))
            + (f"  {record.get('stage')}: {record.get('error')}" if record.get("error") else ""),
            flush=True,
        )
    payload = {
        "schema": RESULTS_SCHEMA,
        "kind": kind,
        "created": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "energyplus_version": reference.get("energyplus_version", "24.2"),
        "reference_set_sha256": sha256_file(args.set),
        "benchmark": BENCHMARK,
        "machine": machine_info,
        "versions": versions(),
        "set": summarise(records, machine_info, expected),
        "buildings": records,
    }
    results_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.write_text(json.dumps(payload, indent=2, default=_json_default) + "\n")
    print(f"\nresults ({kind}) in {results_path}")
    return 0 if all(r["status"] == "ok" for r in records) else 1


def _json_default(value: object) -> object:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    msg = f"not JSON serialisable: {type(value).__name__}"
    raise TypeError(msg)


# ============================================================================================
# Evidence page
# ============================================================================================

_PAGE_HEAD = """---
diataxis: explanation
---

# About the reference evidence: does reduction keep a building's energy use?

<!-- Generated by verification/report.py --write-page from the reference results. Do not edit by hand. -->

"""

_PAGE_WHY = """\
Reduction conserves totals by construction, but an archetype is only useful if it also uses
energy the way its building does once EnergyPlus runs it. Spec 002 states what "the way its
building does" means as eight success criteria and checks them on a fixed reference set, not on
examples chosen afterwards. This page explains what that evidence is and how to read it;
[About reduction](reduction.md) explains the rules being tested, and
[How to check that an archetype reproduces its building](../how-to/compare-results.md) shows how
to make the same comparison for your own model.

## Why a fixed set of public buildings

The reference set is the 16 DOE commercial prototype buildings in a hot (2A, Tampa), a mixed (4A,
New York) and a cold (6A, Rochester, Minnesota) climate, plus the DOE single-family house: 49
models, chosen before any result was known so that the outcome cannot steer the choice. They
are public and checksummed in `verification/reference_set.toml`, so anyone can repeat the run.
The prototypes range from 6 zones (stand-alone retail, fast-food restaurant, the house) to 119 (the
outpatient clinic), and from packaged single-zone units to central plants with chillers and
boilers. That spread is what strains reduction's aggregation rules.

## What is measured

Each detailed model is simulated once with EnergyPlus 24.2, reduced at each of the four layouts,
and each archetype is built and simulated by epinterface with the same weather, run period,
timestep and units. Three questions follow.

- **Does the archetype use the same energy?** Total site energy within ±5 % (SC-001), each end use
  that is at least 5 % of the total within ±10 % (SC-002), and peak heating and cooling within
  ±15 % (SC-003), at the default layout.
- **Is it better than archetypal 2?** At the core/perimeter layout v2 produces, v3's mean
  absolute relative error on those quantities is below v2's, for the set and for at least 90 %
  of buildings (SC-004).
- **Is reduction itself sound?** Every conserved total within 0.1 % at every layout (SC-005);
  every building reduced and every zone accounted for (SC-006); merging and reducing directly
  agree within 0.1 % (SC-007); and the largest building reduces in under 10 seconds, the set at
  least 10 times faster than v2 (SC-008).

## Why the archetype's energy comes from epinterface

An archetype is simulated with ideal loads: EnergyPlus reports the heat and cooling *delivered*
to its zones, and no fans. epinterface turns that into consumed energy afterwards, multiplying
each hour's delivered energy by the system's energy input ratio and adding fan energy from the
specific fan power and the supply air volume. Comparing the archetype's raw SQLite file with the
detailed model's would therefore set delivered heat against burnt gas. The judged values take
the archetype's end uses from epinterface's post-processing and its peaks from the same hourly
product; the detailed side, and the check that both runs are comparable, are those of
`archetypal.compare`. The results file keeps both versions of every row.

## Why timings name a machine

"Under 10 seconds on a typical laptop" means nothing without the laptop. The benchmark machine
is fixed as {benchmark}. The reference run is timed on the machine it runs on, that machine is
recorded with the results, and SC-008 is judged only when it meets those minimums. A slower
machine does not make the criterion fail; it leaves it unjudged.

"""

_PAGE_PENDING = """\
## Results

!!! warning "Results pending"
    The reference set has not been run yet, so this page reports no numbers. The prototypes are
    published for EnergyPlus 22.1 (commercial) and 23.1 (residential); they must be migrated to
    24.2 with EnergyPlus's transition programs before they can be reduced and simulated, and the
    machine that built this page has EnergyPlus 24.2 without those programs. The pipeline itself
    is in place and has run end to end on the test fixtures, which are not evidence.

When the set is migrated, `verification/report.py --run` writes the results and
`--write-page` replaces this section with a table per success criterion and one row per
building. Until then, spec 002 is not shown to meet SC-001 to SC-008, and nothing here should be
read as saying it does.
"""


def _fmt(value: float | None, spec: str = ".1%") -> str:
    return "n/a" if value is None else format(value, spec)


def _mark(value: bool | None) -> str:
    return {True: "pass", False: "**fail**", None: "not judged"}[value]


def _row_relative(rows: Sequence[Mapping[str, Any]], kind: str, end_use: str | None = None) -> float | None:
    for r in rows:
        if r["kind"] == kind and (end_use is None or r["end_use"] == end_use):
            return r["relative"]
    return None


def render_results(payload: Mapping[str, Any]) -> str:
    """The results section of the page, from a results JSON."""
    s = payload["set"]
    m = payload["machine"]
    v = payload["versions"]
    lines = [
        "## Results",
        "",
        f"Run on {payload['created']} with EnergyPlus {payload['energyplus_version']}, archetypal "
        f"{v.get('archetypal')} (commit `{(v.get('git_commit') or 'unknown')[:12]}`), "
        f"epinterface {v.get('epinterface')} "
        f"and idfkit {v.get('idfkit')}, on {m['cpu']} ({m['cpu_count']} CPUs, {m['memory_gb']} GB, {m['platform']}); "
        f"this machine {_benchmark_verdict(m.get('meets_benchmark'))} the benchmark. "
        f"{s['buildings']} of {s['expected']} buildings ran.",
        "",
        "| Criterion | Target | Outcome |",
        "|---|---|---|",
    ]

    def frac(key: str) -> str:
        f = s[key]
        return f"{f['passed']}/{f['judged']} buildings pass: {_mark(f['all'] if f['judged'] else None)}"

    lines += [
        f"| SC-001 total site energy | ±5 % | {frac('SC-001')} |",
        f"| SC-002 significant end uses | ±10 % | {frac('SC-002')} |",
        f"| SC-003 significant peaks | ±15 % | {frac('SC-003')} |",
    ]
    sc4 = s["SC-004"]
    if sc4.get("buildings"):
        lines.append(
            f"| SC-004 better than v2 | lower error, ≥ 90 % of buildings | v3 {_fmt(sc4['v3_mare'])} vs v2 "
            f"{_fmt(sc4['v2_mare'])} mean error, better on {_fmt(sc4['share_better'], '.0%')} of "
            f"{sc4['buildings']}: {_mark(sc4['all'])} |"
        )
    else:
        lines.append("| SC-004 better than v2 | lower error, ≥ 90 % of buildings | pending: no v2 baseline compared |")
    lines += [
        f"| SC-005 conserved totals | 0.1 % at every layout | {frac('SC-005')} |",
        f"| SC-006 reduced, zones accounted | 100 % | {frac('SC-006')} |",
        f"| SC-007 merge equals direct | 0.1 % | {frac('SC-007')} |",
    ]
    sc8 = s["SC-008"]
    if "largest" in sc8:
        speed = sc8.get("speedup")
        lines.append(
            f"| SC-008 speed | < 10 s largest, ≥ 10 times v2 | {sc8['largest']}: {sc8['largest_reduce_s']:.1f} s "
            f"(schedules {_fmt(sc8.get('largest_schedule_s'), '.1f')} s); "
            f"{'speed-up ' + format(speed, '.0f') + ' times' if speed else 'no v2 timing'}: {_mark(sc8['all'])} |"
        )
    else:
        lines.append("| SC-008 speed | < 10 s largest, ≥ 10 times v2 | no building reduced |")
    lines += [
        "",
        "### Per building",
        "",
        "Relative differences of the archetype at the default layout (space use and exposure); "
        "SC-005 to SC-007 over every layout.",
        "",
        "| Building | Zones | Reduce (s) | Total | Heating | Cooling | Peak heat | Peak cool "
        "| SC-001 to 003 | SC-005 to 007 |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for r in payload["buildings"]:
        d = r["layouts"].get(DEFAULT_LAYOUT, {})
        rows: list[dict[str, Any]] = _dict(d.get("comparison")).get("rows", [])
        sc = d.get("sc", {})
        checks = all(
            e.get(k, {}).get("passed", k == "sc007") for e in r["layouts"].values() for k in ("sc005", "sc006", "sc007")
        ) and len(r["layouts"]) == len(LAYOUTS)
        verdicts = "/".join(_mark(sc.get(k)) for k in ("SC-001", "SC-002", "SC-003")) if sc else r.get("error", "error")
        lines.append(
            f"| {r['id']} | {r.get('zones', '')} | {_fmt(d.get('reduce_s'), '.2f')} | "
            f"{_fmt(_row_relative(rows, 'total_site'), '+.1%')} | "
            f"{_fmt(_row_relative(rows, 'end_use_with_distribution', 'Heating'), '+.1%')} | "
            f"{_fmt(_row_relative(rows, 'end_use_with_distribution', 'Cooling'), '+.1%')} | "
            f"{_fmt(_row_relative(rows, 'peak', 'Heating'), '+.1%')} | "
            f"{_fmt(_row_relative(rows, 'peak', 'Cooling'), '+.1%')} | {verdicts} | {_mark(checks)} |"
        )
    lines += [
        "",
        "Every row of every comparison, at every layout and for v2, is in the results file, with the "
        "raw rows of the SQLite files beside the judged ones.",
        "",
    ]
    return "\n".join(lines)


def render_page(payload: Mapping[str, Any] | None) -> str:
    """The whole evidence page; `None` gives the page stating that results are pending."""
    head = _PAGE_HEAD + _PAGE_WHY.replace("{benchmark}", BENCHMARK["description"])
    return head + (_PAGE_PENDING if payload is None else render_results(payload))


def run_write_page(args: argparse.Namespace, cache: Path) -> int:
    """`--write-page`: render the page from the results JSON, or the pending page."""
    page: Path = args.page or DEFAULT_PAGE
    # With --stand-in, the page shows the stand-in results --run wrote beside the reference ones.
    stand_in = cache / "results" / "stand-in.json" if getattr(args, "stand_in", None) else None
    results: Path = args.results or stand_in or default_results(cache)
    payload: dict[str, Any] | None = None
    if args.pending:
        payload = None
    elif results.exists():
        payload = json.loads(results.read_text())
        if payload is not None and payload.get("kind") != "reference" and page.resolve() == DEFAULT_PAGE.resolve():
            print(
                f"{results} holds {payload.get('kind')} results, which are not evidence; "
                "pass --page to render them elsewhere.",
                file=sys.stderr,
            )
            return 1
    else:
        print(f"no results at {results}: writing the page stating that results are pending")
    page.parent.mkdir(parents=True, exist_ok=True)
    page.write_text(render_page(payload))
    print(f"wrote {page}")
    return 0


# ============================================================================================
# Entry point
# ============================================================================================


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--fetch", action="store_true", help="download and check the reference set")
    parser.add_argument("--migrate", action="store_true", help="migrate the fetched models to EnergyPlus 24.2")
    parser.add_argument("--run", action="store_true", help="simulate, reduce and compare; write the results JSON")
    parser.add_argument("--write-page", action="store_true", help="write the evidence page from the results JSON")
    parser.add_argument("--set", type=Path, default=DEFAULT_SET, help="reference-set TOML file")
    parser.add_argument("--cache", type=Path, default=None, help="cache folder for downloads and runs")
    parser.add_argument(
        "--stand-in", action="append", metavar="MODEL", help="run on this EnergyPlus 24.2 model instead (repeatable)"
    )
    parser.add_argument("--only", nargs="+", metavar="ID", help="run these reference buildings only")
    parser.add_argument("--results", type=Path, default=None, help="results JSON to write or read")
    parser.add_argument("--v2-results", type=Path, default=None, help="v2 baseline JSON (run_v2_baseline.py)")
    parser.add_argument(
        "--page", type=Path, default=None, help=f"page to write (default {DEFAULT_PAGE.relative_to(ROOT)})"
    )
    parser.add_argument("--pending", action="store_true", help="with --write-page: write the pending page")
    args = parser.parse_args(argv)
    if args.stand_in and not args.run:
        args.run = True
    if not (args.fetch or args.migrate or args.run or args.write_page):
        parser.error("choose at least one of --fetch, --migrate, --run, --write-page")

    cache = args.cache or default_cache()
    reference = load_set(args.set)
    for wanted, step in (
        (args.fetch, lambda: run_fetch(reference, cache)),
        (args.migrate, lambda: run_migrate(reference, cache)),
        (args.run, lambda: run_set(args, reference, cache)),
        (args.write_page, lambda: run_write_page(args, cache)),
    ):
        if wanted:
            status = step()
            if status:
                return status
    return 0


if __name__ == "__main__":
    sys.exit(main())
