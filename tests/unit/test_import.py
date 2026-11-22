"""The package imports."""

from __future__ import annotations

import importlib


def test_package_imports() -> None:
    module = importlib.import_module("archetypal")
    assert module.__name__ == "archetypal"
