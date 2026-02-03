"""
Archetypal IDF Parser - A high-performance, schema-validated parser for EnergyPlus files.

This module re-exports from eppy-plus and provides additional archetypal-specific
functionality like the IDF class with simulation support.

Example:
    >>> from archetypal.idfclass.parser import IDF
    >>> idf = IDF("model.idf", epw="weather.epw")
    >>> print(len(idf.zones))
    >>> idf.simulate()
"""

__all__ = [
    # Main IDF class (archetypal-specific)
    "IDF",
    # Core classes (from eppy-plus)
    "IDFObject",
    "IDFCollection",
    "IDFDocument",
    # Schema
    "EpJSONSchema",
    "SchemaManager",
    "get_schema",
    # High-level functions
    "load_idf",
    "load_epjson",
    "new_document",
    # Parsers
    "parse_idf",
    "parse_epjson",
    "get_idf_version",
    # Writers
    "write_idf",
    "write_epjson",
    # Validation
    "ValidationError",
    "ValidationResult",
    "validate_document",
    # Exceptions
    "EppyPlusError",
    "ParseError",
    "SchemaNotFoundError",
    "DuplicateObjectError",
    "UnknownObjectTypeError",
    "VersionNotFoundError",
    # Reference graph
    "ReferenceGraph",
]

# Re-export everything from eppy-plus
from eppy_plus import (
    # Core classes
    IDFObject,
    IDFCollection,
    IDFDocument,
    # Schema
    EpJSONSchema,
    SchemaManager,
    get_schema,
    # High-level functions
    load_idf,
    load_epjson,
    new_document,
    # Parsers
    parse_idf,
    parse_epjson,
    get_idf_version,
    # Writers
    write_idf,
    write_epjson,
    # Validation
    ValidationError,
    ValidationResult,
    validate_document,
    # Exceptions
    EppyPlusError,
    ParseError,
    SchemaNotFoundError,
    DuplicateObjectError,
    UnknownObjectTypeError,
    VersionNotFoundError,
    # Reference graph
    ReferenceGraph,
)

# Keep archetypal-specific IDF class
from .idf_model import IDF
