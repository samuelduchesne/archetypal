"""The public interface: each public module's `__all__` (spec 001, US1: T035; FR-007, FR-008).

The lists are data-model.md's "Public interface", as specs 002 and 003 implement it. The diff
functions of `archetypal.umi` (003 US3, T061) join its list when they are written.
"""

from __future__ import annotations

import importlib

import pytest

PUBLIC: dict[str, set[str]] = {
    "archetypal": {
        "__version__",
        "reduce",
        "merge",
        "compare",
        "Layout",
        "ReductionOptions",
        "read_umi",
        "write_umi",
    },
    "archetypal.reduction": {"reduce", "merge", "Reduction", "RESULTS_REQUIREMENTS", "schedule_compact"},
    "archetypal.comparison": {"compare", "ComparisonResult", "ComparisonRow", "AcceptanceTargets", "MetricKind"},
    "archetypal.umi": {
        "read_umi",
        "write_umi",
        "to_umi",
        "UmiImport",
        "UmiExport",
        "TranslationReport",
        "Loss",
        "LossKind",
        "Note",
        "NoteKind",
        "CORRESPONDENCE",
        "FieldMapping",
        "Relevance",
        "MappingStatus",
    },
    "archetypal.errors": {
        "ArchetypalError",
        "InputError",
        "UnsupportedFeatureError",
        "LossyTranslationError",
        "LossReport",
        "NotComparableError",
        "OptionalDependencyError",
        "RemovedInArchetypal3Error",
        "ReductionError",
        "NoConditionedZones",
        "MissingResults",
        "ModelResultsMismatch",
        "UnsupportedEnergyPlusVersion",
        "UmiFormatError",
        "UmiValidationError",
        "Problem",
    },
}


@pytest.mark.parametrize("module", sorted(PUBLIC))
def test_all_is_the_public_interface(module: str) -> None:
    loaded = importlib.import_module(module)
    assert set(loaded.__all__) == PUBLIC[module]
    for name in loaded.__all__:
        assert getattr(loaded, name) is not None


def test_the_command_line_module_exports_only_its_entry_point() -> None:
    from archetypal import cli  # noqa: PLC0415

    assert cli.__all__ == ["main"]
