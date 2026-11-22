"""Reference-set evidence for spec 002 (reduce to SBEM).

Only `--fetch` is implemented so far: it downloads every archive and weather file listed in
`verification/reference_set.toml`, checks their SHA-256, extracts each building's model and
weather file and checks theirs. Tabulating SC-001 to SC-008 and writing the evidence page
(task T081) come later.

```console
$ uv run python verification/report.py --fetch
$ uv run python verification/report.py --fetch --cache /data/reference-set
```

Files land in the cache folder (default `~/.cache/archetypal/reference-set`, or
`$ARCHETYPAL_REFERENCE_CACHE`), never in the repository:

- `archives/<archive id>.zip` and `weather/<station>.zip`: the downloads;
- `models/<building id>.idf`: each building's model, as published (EnergyPlus 22.1 or 23.1);
- `weather/<climate zone>.epw`: each climate zone's weather file.

A file already in the cache with the right hash is not downloaded again. A hash mismatch is an
error: the publisher changed the file, and the reference set must be updated deliberately.

The script uses the standard library only, so it also runs with a bare `python3`.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib  # pyright: ignore[reportMissingTypeStubs]  # Python 3.11+

HERE = Path(__file__).resolve().parent
DEFAULT_SET = HERE / "reference_set.toml"
CHUNK = 1 << 20


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


def load_set(path: Path) -> dict[str, Any]:
    """Read the reference-set file."""
    with path.open("rb") as f:
        data: dict[str, Any] = tomllib.load(f)  # pyright: ignore[reportUnknownMemberType]
    return data


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


def main(argv: list[str] | None = None) -> int:
    """Command-line entry point."""
    parser = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    parser.add_argument("--fetch", action="store_true", help="download and check the reference set")
    parser.add_argument("--set", type=Path, default=DEFAULT_SET, help="reference-set TOML file")
    parser.add_argument("--cache", type=Path, default=None, help="cache folder for downloads")
    args = parser.parse_args(argv)

    if not args.fetch:
        parser.error("only --fetch is implemented so far (the SC-001-SC-008 tables are task T081)")

    cache = args.cache or default_cache()
    outcomes = fetch(load_set(args.set), cache)
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


if __name__ == "__main__":
    sys.exit(main())
