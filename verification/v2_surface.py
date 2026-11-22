"""List the public surface of archetypal 2 and write `tests/data/v2_surface.json`.

Run it with the Python of a separate environment that has archetypal 2 installed (spec 001,
research R7, data-model.md V2Surface), never in the archetypal 3 development environment:

```console
$ uv venv -p 3.11 /tmp/v2 && uv pip install -p /tmp/v2/bin/python "archetypal==2.18.10"
$ /tmp/v2/bin/python verification/v2_surface.py tests/data/v2_surface.json
```

The surface holds:

- `modules`: every importable module of the package whose dotted path has no part starting
  with an underscore;
- `names`: `module.name` for each name a module defines at its top level (a function, a class
  or an assignment, including inside `if` and `try` blocks) or lists in `__all__`, without a
  leading underscore (dunder names listed in `__all__` are kept);
- `commands`: `archetypal <command>` for each command of the click group;
- `options`: `archetypal [<command>] <option>` for each option of the group and its commands,
  short aliases first and joined with `/`, such as `archetypal reduce -z/--all_zones`. click's
  own `-h/--help` is left out: archetypal 3 has it too.

Importing archetypal 2 writes folders in the working directory, so the script imports it from
a temporary directory.
"""

from __future__ import annotations

import argparse
import ast
import importlib
import json
import os
import pkgutil
import sys
import tempfile
from importlib.metadata import version
from pathlib import Path
from types import ModuleType
from typing import Any

PACKAGE = "archetypal"


def _defined_names(tree: ast.Module) -> set[str]:
    names: set[str] = set()

    def visit(body: list[ast.stmt]) -> None:
        for node in body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    names.update(t.id for t in ast.walk(target) if isinstance(t, ast.Name))
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
                names.add(node.target.id)
            elif isinstance(node, ast.If):
                visit(node.body)
                visit(node.orelse)
            elif isinstance(node, ast.Try):
                visit(node.body)
                for handler in node.handlers:
                    visit(handler.body)
                visit(node.orelse)
                visit(node.finalbody)

    visit(tree.body)
    return names


def public_names(module: ModuleType) -> list[str]:
    """Return the public names a module defines or lists in `__all__`."""
    source = Path(module.__file__ or "")
    defined = _defined_names(ast.parse(source.read_text(encoding="utf-8"))) if source.is_file() else set()
    listed = set(getattr(module, "__all__", ()))
    public = {n for n in defined if not n.startswith("_")} | {n for n in listed if not n.startswith("_") or n.endswith("__")}
    return sorted(public - {"__all__"})


def public_modules() -> list[ModuleType]:
    """Import and return every public module of the package."""
    package = importlib.import_module(PACKAGE)
    modules = [package]
    for info in pkgutil.walk_packages(package.__path__, prefix=f"{PACKAGE}."):
        if any(part.startswith("_") for part in info.name.split(".")):
            continue
        modules.append(importlib.import_module(info.name))
    return sorted(modules, key=lambda m: m.__name__)


def _option_label(param: Any) -> str:
    flags = [*param.opts, *param.secondary_opts]
    shorts = sorted(f for f in flags if not f.startswith("--"))
    longs = sorted(f for f in flags if f.startswith("--"))
    return "/".join(shorts + longs)


def click_surface(group: Any) -> tuple[list[str], list[str]]:
    """Return the commands and options of a click group."""
    import click

    commands: list[str] = []
    options: list[str] = []

    def add_options(prefix: str, command: Any) -> None:
        for param in command.params:
            if isinstance(param, click.Option) and "--help" not in param.opts:
                options.append(f"{prefix} {_option_label(param)}")

    add_options(PACKAGE, group)
    for name in sorted(group.commands):
        commands.append(f"{PACKAGE} {name}")
        add_options(f"{PACKAGE} {name}", group.commands[name])
    return commands, sorted(options)


def surface() -> dict[str, Any]:
    """Return the public surface of the installed archetypal."""
    modules = public_modules()
    names = sorted(f"{m.__name__}.{n}" for m in modules for n in public_names(m))
    cli = importlib.import_module(f"{PACKAGE}.cli")
    commands, options = click_surface(cli.cli)
    return {
        "archetypal_version": version(PACKAGE),
        "modules": [m.__name__ for m in modules],
        "names": names,
        "commands": commands,
        "options": options,
    }


def main() -> None:
    """Write the surface to the path given on the command line."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("output", type=Path, help="where to write the JSON file")
    output = parser.parse_args().output.resolve()
    with tempfile.TemporaryDirectory() as scratch:
        os.chdir(scratch)
        sys.path = [p for p in sys.path if Path(p or ".").resolve() != Path(__file__).resolve().parent]
        data = surface()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"archetypal {data['archetypal_version']}: " + ", ".join(f"{len(data[k])} {k}" for k in ("modules", "names", "commands", "options")))


if __name__ == "__main__":
    main()
