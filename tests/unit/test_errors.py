"""The error hierarchy of spec 001 (research R8) and its extensions by spec 002."""

from __future__ import annotations

import pickle
from dataclasses import dataclass
from pathlib import Path

import pytest

from archetypal.errors import (
    ArchetypalError,
    InputError,
    LossyTranslationError,
    MissingResults,
    ModelResultsMismatch,
    NoConditionedZones,
    NotComparableError,
    OptionalDependencyError,
    ReductionError,
    RemovedInArchetypal3Error,
    UmiFormatError,
    UmiValidationError,
    UnsupportedEnergyPlusVersion,
    UnsupportedFeatureError,
)


@dataclass(frozen=True)
class _Report:
    losses: tuple[str, ...]


# --- spec 001 (T013) -------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("cls", "parent"),
    [
        (InputError, ArchetypalError),
        (UnsupportedFeatureError, ArchetypalError),
        (LossyTranslationError, ArchetypalError),
        (NotComparableError, ArchetypalError),
        (OptionalDependencyError, ArchetypalError),
        (RemovedInArchetypal3Error, ArchetypalError),
        (ReductionError, InputError),
        (UmiFormatError, InputError),
        (UmiValidationError, InputError),
        (ArchetypalError, Exception),
    ],
)
def test_tree_of_research_r8(cls: type[Exception], parent: type[Exception]) -> None:
    assert issubclass(cls, parent)


def test_siblings_are_independent() -> None:
    assert not issubclass(UnsupportedFeatureError, InputError)
    assert not issubclass(LossyTranslationError, InputError)
    assert not issubclass(OptionalDependencyError, InputError)


def test_message_starts_with_the_subject() -> None:
    error = ArchetypalError("models/office.idf", "no conditioned zones")
    assert str(error) == "models/office.idf: no conditioned zones"
    assert error.subject == "models/office.idf"
    assert error.message == "no conditioned zones"


def test_subject_accepts_a_path() -> None:
    error = InputError(Path("models") / "office.idf", "malformed")
    assert error.subject == str(Path("models") / "office.idf")
    assert str(error).startswith(error.subject)


@pytest.mark.parametrize("cls", [ArchetypalError, InputError, UnsupportedFeatureError])
def test_simple_errors_start_with_their_subject(cls: type[ArchetypalError]) -> None:
    assert str(cls("zone 1", "why")).startswith("zone 1")


def test_lossy_translation_error_keeps_the_report() -> None:
    report = _Report(losses=("a", "b"))
    error = LossyTranslationError("lib.json", "2 losses in strict mode", report)
    assert error.report is report
    assert str(error).startswith("lib.json")


def test_removed_error_is_also_an_import_error() -> None:
    error = RemovedInArchetypal3Error("archetypal.IDF", "was removed in archetypal 3.")
    assert isinstance(error, ImportError)
    assert isinstance(error, ArchetypalError)
    assert str(error) == "archetypal.IDF was removed in archetypal 3."
    assert error.name == "archetypal.IDF"
    with pytest.raises(ImportError):
        raise error


def test_removed_error_cannot_also_be_an_attribute_error_on_cpython() -> None:
    # Deviation from 001 T013/T018: CPython refuses ImportError and AttributeError as bases of one
    # class ("multiple bases have instance lay-out conflict"). ImportError is kept, so
    # `from archetypal import IDF` keeps the error's message (an AttributeError would be replaced
    # by the interpreter's generic "cannot import name").
    with pytest.raises(TypeError, match="lay-out conflict"):
        type("Both", (ImportError, AttributeError), {})


def test_optional_dependency_error_names_the_extra() -> None:
    error = OptionalDependencyError("pandas", "tabula")
    assert str(error).startswith("pandas")
    assert "archetypal[tabula]" in str(error)
    assert error.extra == "tabula"


@pytest.mark.parametrize(
    "error",
    [
        ArchetypalError("a.idf", "why"),
        InputError("a.idf", "why"),
        LossyTranslationError("lib.json", "why", _Report(losses=())),
        OptionalDependencyError("pandas", "tabula"),
        RemovedInArchetypal3Error("archetypal.IDF", "was removed in archetypal 3."),
        NoConditionedZones("a.idf"),
        MissingResults("a.sql", ["Output:Meter,Electricity:Facility,Hourly;"]),
        ModelResultsMismatch("a.sql", ["zone CORE only in the model"]),
        UnsupportedEnergyPlusVersion("a.idf", "9.6", ("22.1", "25.2")),
        NotComparableError("a.sql", ["weather"]),
    ],
)
def test_errors_survive_pickling(error: ArchetypalError) -> None:
    copy = pickle.loads(pickle.dumps(error))  # noqa: S301 - round trip of our own object
    assert type(copy) is type(error)
    assert str(copy) == str(error)


# --- spec 002 (T012) -------------------------------------------------------------------------


def test_reduction_errors_derive_from_input_error() -> None:
    for cls in (NoConditionedZones, MissingResults, ModelResultsMismatch, UnsupportedEnergyPlusVersion):
        assert issubclass(cls, ReductionError)
        assert issubclass(cls, InputError)
    assert issubclass(NotComparableError, ArchetypalError)
    assert not issubclass(NotComparableError, InputError)


def test_no_conditioned_zones() -> None:
    error = NoConditionedZones("models/office.idf")
    assert str(error).startswith("models/office.idf: no conditioned zones")


def test_missing_results_lists_items_and_suggests_simulate() -> None:
    items = [
        "Output:Variable,*,Zone Mean Air Temperature,Hourly;",
        "Output:Meter,Electricity:Facility,Hourly;",
    ]
    error = MissingResults("runs/office.sql", items)
    text = str(error)
    assert text.startswith("runs/office.sql")
    for item in items:
        assert item in text
    assert "simulate=True" in text
    assert error.missing == tuple(items)


def test_model_results_mismatch_names_the_differences() -> None:
    error = ModelResultsMismatch("runs/office.sql", ["zone CORE is only in the model"])
    assert str(error).startswith("runs/office.sql")
    assert "zone CORE is only in the model" in str(error)
    assert error.differences == ("zone CORE is only in the model",)


def test_unsupported_version_names_range_and_migration() -> None:
    error = UnsupportedEnergyPlusVersion("old.idf", "9.6", ("22.1", "25.2"))
    text = str(error)
    assert text.startswith("old.idf")
    assert "9.6" in text
    assert "22.1" in text
    assert "25.2" in text
    assert "idfkit.migration.migrate" in text
    assert error.version == "9.6"
    assert error.supported == ("22.1", "25.2")


def test_not_comparable_names_every_difference() -> None:
    error = NotComparableError("detailed.sql", ["weather file", "timestep"])
    assert str(error).startswith("detailed.sql")
    assert "weather file" in str(error)
    assert "timestep" in str(error)
    assert error.differences == ("weather file", "timestep")
