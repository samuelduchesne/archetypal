"""Compare the default install of archetypal 2 and archetypal 3 (SC-002, research R12).

Resolves, with `uv pip compile` for Python 3.12, archetypal 2.18.10 (the last archetypal 2
release on PyPI) and the archetypal 3 of this checkout. The checkout is resolved as a local
path requirement, so `uv` applies its `[tool.uv.sources]` (the SBEM fork of epinterface).
Both counts include archetypal itself. Prints both package lists and counts, and exits with
status 1 when archetypal 3's count is not smaller.

```console
$ python verification/install_size.py
```

Needs `uv` on `PATH` and network access to PyPI and GitHub.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

V2_REQUIREMENT = "archetypal==2.18.10"
PYTHON_VERSION = "3.12"
ROOT = Path(__file__).resolve().parent.parent

_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)")


def resolve(requirement: str, python_version: str) -> list[str]:
    """Return the pinned lines `uv pip compile` gives for one requirement, sorted by name."""
    uv = shutil.which("uv")
    if uv is None:
        msg = "uv is not on PATH"
        raise RuntimeError(msg)
    with tempfile.TemporaryDirectory() as tmp:
        infile = Path(tmp) / "requirements.in"
        infile.write_text(requirement + "\n", encoding="utf-8")
        result = subprocess.run(  # noqa: S603
            [
                uv,
                "pip",
                "compile",
                "--quiet",
                "--no-header",
                "--no-annotate",
                "--python-version",
                python_version,
                str(infile),
            ],
            check=True,
            capture_output=True,
            text=True,
        )
    lines = [line.strip() for line in result.stdout.splitlines()]
    pins = [line for line in lines if line and not line.startswith("#")]
    return sorted(pins, key=_canonical)


def _canonical(line: str) -> str:
    match = _NAME.match(line)
    name = match.group(1) if match else line
    return re.sub(r"[-_.]+", "-", name).lower()


def main(argv: list[str] | None = None) -> int:
    """Resolve both installs, print them and return 0 when archetypal 3's is smaller."""
    parser = argparse.ArgumentParser(description="Compare archetypal 2 and 3 install sizes.")
    parser.add_argument("--python-version", default=PYTHON_VERSION)
    parser.add_argument("--project", type=Path, default=ROOT, help="archetypal 3 checkout")
    args = parser.parse_args(argv)

    v3_requirement = f"archetypal @ {args.project.resolve().as_uri()}"
    v2 = resolve(V2_REQUIREMENT, args.python_version)
    v3 = resolve(v3_requirement, args.python_version)

    for label, requirement, pins in (
        ("archetypal 2", V2_REQUIREMENT, v2),
        ("archetypal 3", v3_requirement, v3),
    ):
        print(f"## {label} ({requirement}), Python {args.python_version}: {len(pins)} packages")
        for pin in pins:
            print(f"  {pin}")
        print()

    smaller = len(v3) < len(v2)
    verdict = "PASS" if smaller else "FAIL"
    print(f"{verdict}: archetypal 2 = {len(v2)} packages, archetypal 3 = {len(v3)} packages")
    return 0 if smaller else 1


if __name__ == "__main__":
    sys.exit(main())
