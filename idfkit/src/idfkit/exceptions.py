"""Custom exceptions for idfkit."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .objects import IDFObject


class IdfKitError(Exception):
    """Base exception for all idfkit errors."""

    pass


# Alias for backwards compatibility
ParseError = IdfKitError


class SchemaNotFoundError(IdfKitError):
    """Raised when the EpJSON schema file cannot be found."""

    def __init__(self, version: tuple[int, int, int], searched_paths: list[str] | None = None):
        self.version = version
        self.searched_paths = searched_paths or []
        version_str = f"{version[0]}.{version[1]}.{version[2]}"
        msg = f"Could not find Energy+.schema.epJSON for EnergyPlus {version_str}"
        if searched_paths:
            msg += f"\nSearched in: {', '.join(searched_paths)}"
        super().__init__(msg)


class DuplicateObjectError(IdfKitError):
    """Raised when attempting to add an object with a duplicate name."""

    def __init__(self, obj_type: str, name: str):
        self.obj_type = obj_type
        self.name = name
        super().__init__(f"Duplicate {obj_type} object with name '{name}'")


class UnknownObjectTypeError(IdfKitError):
    """Raised when an unknown object type is encountered."""

    def __init__(self, obj_type: str):
        self.obj_type = obj_type
        super().__init__(f"Unknown object type: '{obj_type}'")


class InvalidFieldError(IdfKitError):
    """Raised when an invalid field is accessed or set."""

    def __init__(self, obj_type: str, field_name: str, available_fields: list[str] | None = None):
        self.obj_type = obj_type
        self.field_name = field_name
        self.available_fields = available_fields
        msg = f"Invalid field '{field_name}' for object type '{obj_type}'"
        if available_fields:
            msg += f"\nAvailable fields: {', '.join(available_fields[:10])}"
            if len(available_fields) > 10:
                msg += f" ... and {len(available_fields) - 10} more"
        super().__init__(msg)


class VersionNotFoundError(IdfKitError):
    """Raised when version cannot be detected from file."""

    def __init__(self, filepath: str):
        self.filepath = filepath
        super().__init__(f"Could not detect EnergyPlus version in file: {filepath}")


class DanglingReferenceError(IdfKitError):
    """Raised when an object references a non-existent object."""

    def __init__(self, source: "IDFObject", field: str, target: str):
        self.source = source
        self.field = field
        self.target = target
        super().__init__(
            f"Object {source._type}:'{source.name}' field '{field}' "
            f"references non-existent object '{target}'"
        )


class ValidationFailedError(IdfKitError):
    """Raised when validation fails."""

    def __init__(self, errors: list):
        self.errors = errors
        msg = f"Validation failed with {len(errors)} error(s):\n"
        for i, err in enumerate(errors[:5], 1):
            msg += f"  {i}. {err}\n"
        if len(errors) > 5:
            msg += f"  ... and {len(errors) - 5} more errors"
        super().__init__(msg)
