"""The errors of spec 003: UmiFormatError, UmiValidationError and Problem (T010)."""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from archetypal.errors import InputError, Problem, UmiFormatError, UmiValidationError

PROBLEMS = [
    Problem(pointer="/Zones/2/Loads", template="Office", rule="required-reference", message="is null"),
    Problem(pointer="/DaySchedules/0/Values", template=None, rule="24-values", message="has 23 values"),
]


def test_umi_errors_derive_from_input_error() -> None:
    assert issubclass(UmiFormatError, InputError)
    assert issubclass(UmiValidationError, InputError)


def test_problem_fields() -> None:
    problem = PROBLEMS[0]
    assert problem.pointer.startswith("/")
    assert problem.template == "Office"
    assert problem.rule == "required-reference"
    assert problem.message == "is null"
    assert PROBLEMS[1].template is None


def test_problem_is_frozen() -> None:
    with pytest.raises(dataclasses.FrozenInstanceError):
        PROBLEMS[0].rule = "other"  # type: ignore[misc]


def test_validation_error_lists_every_problem() -> None:
    library = Path("libs") / "lib.json"
    error = UmiValidationError(library, PROBLEMS)
    assert isinstance(error.problems, list)
    assert error.problems == PROBLEMS
    assert all(isinstance(p, Problem) for p in error.problems)
    assert error.subject == str(library)
    text = str(error)
    assert text.startswith(str(library))
    for problem in PROBLEMS:
        assert problem.pointer in text
        assert problem.rule in text
        assert problem.message in text
    assert "Office" in text


def test_validation_error_copies_the_problems() -> None:
    problems = list(PROBLEMS)
    error = UmiValidationError("lib.json", problems)
    problems.clear()
    assert len(error.problems) == len(PROBLEMS)


def test_format_error_subject_and_problems() -> None:
    error = UmiFormatError("lib.json", "dangling $ref", [PROBLEMS[0]])
    assert str(error).startswith("lib.json: dangling $ref")
    assert "/Zones/2/Loads" in str(error)
    assert error.problems == [PROBLEMS[0]]
    assert UmiFormatError("lib.json", "not JSON").problems == []
