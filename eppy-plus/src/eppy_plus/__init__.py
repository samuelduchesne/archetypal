"""
eppy-plus: A fast, modern EnergyPlus IDF/epJSON parser.

This package provides high-performance parsing and manipulation of EnergyPlus
input files (IDF and epJSON formats), with O(1) lookups and reference tracking.

Basic usage:
    from eppy_plus import load_idf, load_epjson

    # Load an IDF file
    model = load_idf("building.idf")

    # Access objects
    zones = model["Zone"]
    zone = zones["MyZone"]

    # Find references
    surfaces = model.get_referencing("MyZone")

    # Write back
    model.save("modified.idf")
"""

from __future__ import annotations

__version__ = "0.1.0"

# Core classes
from .document import IDFDocument
from .objects import IDFObject, IDFCollection

# Parsing functions
from .idf_parser import parse_idf, get_idf_version, IDFParser
from .epjson_parser import parse_epjson

# Writing functions
from .writers import write_idf, write_epjson

# Schema access
from .schema import EpJSONSchema, SchemaManager, get_schema, get_schema_manager

# Reference graph
from .references import ReferenceGraph

# Validation
from .validation import validate_document, ValidationError, ValidationResult

# Geometry utilities
from .geometry import Vector3D, Polygon3D

# Exceptions
from .exceptions import (
    EppyPlusError,
    ParseError,
    SchemaNotFoundError,
    ValidationFailedError,
    DuplicateObjectError,
    UnknownObjectTypeError,
    VersionNotFoundError,
)


def load_idf(path: str, version: tuple[int, int, int] | None = None) -> IDFDocument:
    """
    Load an IDF file and return an IDFDocument.

    Args:
        path: Path to the IDF file
        version: Optional version override (major, minor, patch)

    Returns:
        Parsed IDFDocument

    Example:
        model = load_idf("building.idf")
        print(f"Loaded {len(model)} objects")
    """
    from pathlib import Path
    return parse_idf(Path(path), version=version)


def load_epjson(path: str, version: tuple[int, int, int] | None = None) -> IDFDocument:
    """
    Load an epJSON file and return an IDFDocument.

    Args:
        path: Path to the epJSON file
        version: Optional version override (major, minor, patch)

    Returns:
        Parsed IDFDocument

    Example:
        model = load_epjson("building.epJSON")
        print(f"Loaded {len(model)} objects")
    """
    from pathlib import Path
    return parse_epjson(Path(path), version=version)


def new_document(version: tuple[int, int, int] = (24, 1, 0)) -> IDFDocument:
    """
    Create a new empty IDFDocument.

    Args:
        version: EnergyPlus version (default: 24.1.0)

    Returns:
        Empty IDFDocument with schema loaded

    Example:
        model = new_document()
        model.add("Zone", "MyZone", {"x_origin": 0, "y_origin": 0})
    """
    schema = get_schema(version)
    return IDFDocument(version=version, schema=schema)


__all__ = [
    # Version
    "__version__",
    # Core classes
    "IDFDocument",
    "IDFObject",
    "IDFCollection",
    # High-level functions
    "load_idf",
    "load_epjson",
    "new_document",
    # Parsing
    "parse_idf",
    "parse_epjson",
    "get_idf_version",
    "IDFParser",
    # Writing
    "write_idf",
    "write_epjson",
    # Schema
    "EpJSONSchema",
    "SchemaManager",
    "get_schema",
    "get_schema_manager",
    # References
    "ReferenceGraph",
    # Validation
    "validate_document",
    "ValidationError",
    "ValidationResult",
    # Geometry
    "Vector3D",
    "Polygon3D",
    # Exceptions
    "EppyPlusError",
    "ParseError",
    "SchemaNotFoundError",
    "ValidationFailedError",
    "DuplicateObjectError",
    "UnknownObjectTypeError",
    "VersionNotFoundError",
]
