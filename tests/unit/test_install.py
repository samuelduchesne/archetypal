"""The default install carries no duplicate of a dependency, and the wheel ships no data (FR-002, FR-004, R12)."""

from __future__ import annotations

import re
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
# What archetypal 2 used (or bundled) and idfkit or epinterface now provide: geomeppy and its dependencies.
FORBIDDEN = ("eppy", "geomeppy", "esoreader", "energy_pandas", "pyclipper", "pypoly2tri", "transforms3d", "shapely")
# Files a wheel may hold inside the package: code and the typing marker. Anything else is data.
CODE_SUFFIXES = (".py", ".pyi")
CODE_NAMES = ("py.typed",)
_OFFLINE_HINTS = (
    "failed to fetch",
    "error sending request",
    "dns error",
    "connection refused",
    "network is unreachable",
    "could not connect",
    "tcp connect error",
    "offline",
)
_REQUIREMENT = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)==", re.MULTILINE)

pytestmark = pytest.mark.timeout(300)


def _normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _run_uv(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    """Run uv, skipping the test when uv is missing or the network is not reachable."""
    uv = shutil.which("uv")
    if uv is None:
        pytest.skip("uv is not installed")
    result = subprocess.run([uv, *args], cwd=cwd, capture_output=True, text=True, check=False)  # noqa: S603
    if result.returncode != 0 and any(hint in result.stderr.lower() for hint in _OFFLINE_HINTS):
        pytest.skip(f"offline: uv {args[0]} could not reach the package index")
    assert result.returncode == 0, result.stderr
    return result


def resolved_packages(requirements: str) -> set[str]:
    """Return the normalized names pinned in `uv pip compile` output."""
    return {_normalize(name) for name in _REQUIREMENT.findall(requirements)}


def data_files(names: list[str]) -> list[str]:
    """Return the wheel entries that are neither code, the typing marker nor wheel metadata."""
    return [
        name
        for name in names
        if not name.endswith("/")
        and ".dist-info/" not in name
        and not name.endswith(CODE_SUFFIXES)
        and name.rsplit("/", 1)[-1] not in CODE_NAMES
    ]


def test_resolved_packages_parses_compile_output() -> None:
    text = "# via archetypal\nidfkit==1.3.0rc2\n    # via archetypal\nEnergy_Pandas==0.4\n"
    assert resolved_packages(text) == {"idfkit", "energy-pandas"}


def test_data_files_keeps_only_data() -> None:
    names = ["archetypal/", "archetypal/__init__.py", "archetypal/py.typed", "archetypal/data/a.csv"]
    names.append("archetypal-3.0.0.dist-info/METADATA")
    assert data_files(names) == ["archetypal/data/a.csv"]


def test_default_install_has_no_duplicates() -> None:
    # idfkit is pinned as >=1.3.0rc2 (1.3.0 is not released): the explicit pre-release pin lets uv pick it.
    result = _run_uv("pip", "compile", "pyproject.toml", "--python-version", "3.12", "--no-header", "--quiet", cwd=ROOT)
    found = resolved_packages(result.stdout) & {_normalize(name) for name in FORBIDDEN}
    assert not found, f"the default install contains {sorted(found)}"


def test_wheel_contains_no_data_files(tmp_path: Path) -> None:
    _run_uv("build", "--wheel", "--out-dir", str(tmp_path), "--quiet", cwd=ROOT)
    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1, wheels
    with zipfile.ZipFile(wheels[0]) as wheel:
        extra = data_files(wheel.namelist())
    assert not extra, f"the wheel ships data files: {extra}"
