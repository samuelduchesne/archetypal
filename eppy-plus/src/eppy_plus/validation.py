"""
On-demand validation system for IDF documents.

Provides validation against EpJSON schema without requiring
eager validation during parsing.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    from .document import IDFDocument
    from .objects import IDFObject
    from .schema import EpJSONSchema


class Severity(Enum):
    """Validation issue severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ValidationError:
    """
    Represents a validation issue.

    Attributes:
        severity: Issue severity (ERROR, WARNING, INFO)
        obj_type: Object type where issue was found
        obj_name: Object name where issue was found
        field: Field name where issue was found (if applicable)
        message: Human-readable description
        code: Machine-readable error code
    """

    severity: Severity
    obj_type: str
    obj_name: str
    field: str | None
    message: str
    code: str

    def __str__(self) -> str:
        location = f"{self.obj_type}:'{self.obj_name}'"
        if self.field:
            location += f".{self.field}"
        return f"[{self.severity.value.upper()}] {location}: {self.message}"


@dataclass
class ValidationResult:
    """
    Result of document validation.

    Attributes:
        errors: List of validation errors
        warnings: List of validation warnings
        info: List of informational messages
    """

    errors: list[ValidationError]
    warnings: list[ValidationError]
    info: list[ValidationError]

    @property
    def is_valid(self) -> bool:
        """True if there are no errors."""
        return len(self.errors) == 0

    @property
    def total_issues(self) -> int:
        """Total number of issues found."""
        return len(self.errors) + len(self.warnings) + len(self.info)

    def __str__(self) -> str:
        lines = [f"Validation: {len(self.errors)} errors, {len(self.warnings)} warnings"]
        for err in self.errors[:10]:
            lines.append(f"  {err}")
        if len(self.errors) > 10:
            lines.append(f"  ... and {len(self.errors) - 10} more errors")
        return "\n".join(lines)

    def __bool__(self) -> bool:
        return self.is_valid


def validate_document(
    doc: "IDFDocument",
    schema: "EpJSONSchema | None" = None,
    check_references: bool = True,
    check_required: bool = True,
    check_types: bool = True,
    check_ranges: bool = True,
    object_types: list[str] | None = None,
) -> ValidationResult:
    """
    Validate an IDF document against schema.

    Args:
        doc: The document to validate
        schema: Schema to validate against (uses doc's schema if not provided)
        check_references: Check reference integrity
        check_required: Check required fields
        check_types: Check field types
        check_ranges: Check numeric ranges
        object_types: Only validate these types (None = all)

    Returns:
        ValidationResult with all issues found
    """
    schema = schema or doc._schema

    errors: list[ValidationError] = []
    warnings: list[ValidationError] = []
    info: list[ValidationError] = []

    if schema is None:
        warnings.append(
            ValidationError(
                severity=Severity.WARNING,
                obj_type="Document",
                obj_name="",
                field=None,
                message="No schema available - skipping schema validation",
                code="W001",
            )
        )
        return ValidationResult(errors, warnings, info)

    # Determine which object types to validate
    types_to_check = object_types or list(doc._collections.keys())

    for obj_type in types_to_check:
        if obj_type not in doc._collections:
            continue

        for obj in doc[obj_type]:
            obj_errors = _validate_object(
                obj,
                schema,
                check_required=check_required,
                check_types=check_types,
                check_ranges=check_ranges,
            )

            for err in obj_errors:
                if err.severity == Severity.ERROR:
                    errors.append(err)
                elif err.severity == Severity.WARNING:
                    warnings.append(err)
                else:
                    info.append(err)

    # Check reference integrity
    if check_references:
        ref_errors = _validate_references(doc, schema)
        for err in ref_errors:
            if err.severity == Severity.ERROR:
                errors.append(err)
            elif err.severity == Severity.WARNING:
                warnings.append(err)

    return ValidationResult(errors, warnings, info)


def _validate_object(
    obj: "IDFObject",
    schema: "EpJSONSchema",
    check_required: bool = True,
    check_types: bool = True,
    check_ranges: bool = True,
) -> list[ValidationError]:
    """Validate a single object against schema."""
    errors: list[ValidationError] = []
    obj_type = obj._type
    obj_name = obj.name

    inner_schema = schema.get_inner_schema(obj_type)
    if not inner_schema:
        # Unknown object type
        errors.append(
            ValidationError(
                severity=Severity.WARNING,
                obj_type=obj_type,
                obj_name=obj_name,
                field=None,
                message=f"Unknown object type '{obj_type}'",
                code="W002",
            )
        )
        return errors

    properties = inner_schema.get("properties", {})
    required = set(inner_schema.get("required", []))

    # Check required fields
    if check_required:
        for field_name in required:
            value = obj._data.get(field_name)
            if value is None or value == "":
                errors.append(
                    ValidationError(
                        severity=Severity.ERROR,
                        obj_type=obj_type,
                        obj_name=obj_name,
                        field=field_name,
                        message=f"Required field '{field_name}' is missing",
                        code="E001",
                    )
                )

    # Check field types and ranges
    for field_name, value in obj._data.items():
        if value is None or value == "":
            continue

        field_schema = properties.get(field_name)
        if not field_schema:
            # Unknown field - could be extensible or error
            if not schema.is_extensible(obj_type):
                errors.append(
                    ValidationError(
                        severity=Severity.WARNING,
                        obj_type=obj_type,
                        obj_name=obj_name,
                        field=field_name,
                        message=f"Unknown field '{field_name}'",
                        code="W003",
                    )
                )
            continue

        # Check type
        if check_types:
            type_errors = _validate_field_type(obj, field_name, value, field_schema)
            errors.extend(type_errors)

        # Check range
        if check_ranges and isinstance(value, (int, float)):
            range_errors = _validate_field_range(obj, field_name, value, field_schema)
            errors.extend(range_errors)

    return errors


def _validate_field_type(
    obj: "IDFObject",
    field_name: str,
    value: Any,
    field_schema: dict,
) -> list[ValidationError]:
    """Validate field value type."""
    errors: list[ValidationError] = []

    # Handle anyOf (multiple valid types)
    if "anyOf" in field_schema:
        valid = False
        for sub_schema in field_schema["anyOf"]:
            if _value_matches_type(value, sub_schema):
                valid = True
                break
        if not valid:
            errors.append(
                ValidationError(
                    severity=Severity.ERROR,
                    obj_type=obj._type,
                    obj_name=obj.name,
                    field=field_name,
                    message=f"Value '{value}' does not match any valid type",
                    code="E002",
                )
            )
        return errors

    # Handle single type
    expected_type = field_schema.get("type")
    if expected_type and not _value_matches_type(value, field_schema):
        errors.append(
            ValidationError(
                severity=Severity.ERROR,
                obj_type=obj._type,
                obj_name=obj.name,
                field=field_name,
                message=f"Expected {expected_type}, got {type(value).__name__}",
                code="E003",
            )
        )

    # Check enum values
    if "enum" in field_schema:
        if value not in field_schema["enum"]:
            # Case-insensitive check for strings
            if isinstance(value, str):
                enum_lower = [str(e).lower() for e in field_schema["enum"]]
                if value.lower() not in enum_lower:
                    errors.append(
                        ValidationError(
                            severity=Severity.ERROR,
                            obj_type=obj._type,
                            obj_name=obj.name,
                            field=field_name,
                            message=f"Value '{value}' not in allowed values: {field_schema['enum']}",
                            code="E004",
                        )
                    )
            else:
                errors.append(
                    ValidationError(
                        severity=Severity.ERROR,
                        obj_type=obj._type,
                        obj_name=obj.name,
                        field=field_name,
                        message=f"Value '{value}' not in allowed values: {field_schema['enum']}",
                        code="E004",
                    )
                )

    return errors


def _value_matches_type(value: Any, schema: dict) -> bool:
    """Check if a value matches a type schema."""
    expected_type = schema.get("type")

    if expected_type == "number":
        return isinstance(value, (int, float))
    elif expected_type == "integer":
        return isinstance(value, int) or (isinstance(value, float) and value.is_integer())
    elif expected_type == "string":
        return isinstance(value, str)
    elif expected_type == "boolean":
        return isinstance(value, bool)
    elif expected_type == "array":
        return isinstance(value, list)
    elif expected_type == "object":
        return isinstance(value, dict)

    # Check enum
    if "enum" in schema:
        return value in schema["enum"] or (
            isinstance(value, str)
            and value.lower() in [str(e).lower() for e in schema["enum"]]
        )

    return True  # Unknown type - assume valid


def _validate_field_range(
    obj: "IDFObject",
    field_name: str,
    value: float | int,
    field_schema: dict,
) -> list[ValidationError]:
    """Validate numeric field range."""
    errors: list[ValidationError] = []

    # Check minimum
    if "minimum" in field_schema:
        if value < field_schema["minimum"]:
            errors.append(
                ValidationError(
                    severity=Severity.ERROR,
                    obj_type=obj._type,
                    obj_name=obj.name,
                    field=field_name,
                    message=f"Value {value} is below minimum {field_schema['minimum']}",
                    code="E005",
                )
            )

    # Check exclusive minimum
    if "exclusiveMinimum" in field_schema:
        if value <= field_schema["exclusiveMinimum"]:
            errors.append(
                ValidationError(
                    severity=Severity.ERROR,
                    obj_type=obj._type,
                    obj_name=obj.name,
                    field=field_name,
                    message=f"Value {value} must be greater than {field_schema['exclusiveMinimum']}",
                    code="E006",
                )
            )

    # Check maximum
    if "maximum" in field_schema:
        if value > field_schema["maximum"]:
            errors.append(
                ValidationError(
                    severity=Severity.ERROR,
                    obj_type=obj._type,
                    obj_name=obj.name,
                    field=field_name,
                    message=f"Value {value} is above maximum {field_schema['maximum']}",
                    code="E007",
                )
            )

    # Check exclusive maximum
    if "exclusiveMaximum" in field_schema:
        if value >= field_schema["exclusiveMaximum"]:
            errors.append(
                ValidationError(
                    severity=Severity.ERROR,
                    obj_type=obj._type,
                    obj_name=obj.name,
                    field=field_name,
                    message=f"Value {value} must be less than {field_schema['exclusiveMaximum']}",
                    code="E008",
                )
            )

    return errors


def _validate_references(
    doc: "IDFDocument",
    schema: "EpJSONSchema",
) -> list[ValidationError]:
    """Validate all object references."""
    errors: list[ValidationError] = []

    # Build set of all valid names
    valid_names: set[str] = set()
    for collection in doc._collections.values():
        for obj in collection:
            if obj.name:
                valid_names.add(obj.name.upper())

    # Check for dangling references
    for obj, field_name, target in doc._references.get_dangling_references(valid_names):
        errors.append(
            ValidationError(
                severity=Severity.ERROR,
                obj_type=obj._type,
                obj_name=obj.name,
                field=field_name,
                message=f"Reference to non-existent object '{target}'",
                code="E009",
            )
        )

    return errors
