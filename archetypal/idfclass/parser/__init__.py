"""
Archetypal IDF Parser - A high-performance, schema-validated parser for EnergyPlus files.

This module provides a complete replacement for eppy with:
- O(1) object lookups by name
- Schema validation from Energy+.schema.epJSON
- Support for both IDF and epJSON formats
- Streaming parser for large files
- Reference graph for dependency tracking

Version: 3.0.0

Example:
    >>> from archetypal.idfclass.parser import IDF
    >>> idf = IDF("model.idf", epw="weather.epw")
    >>> print(len(idf.zones))
    >>> idf.simulate()
"""

__all__ = [
    # Main IDF class
    "IDF",
    # Core classes
    "IDFObject",
    "IDFCollection",
    "IDFDocument",
    # Schema
    "EpJSONSchema",
    "SchemaManager",
    "get_schema",
    # Parsers
    "parse_idf",
    "parse_epjson",
    "get_idf_version",
    # Writers
    "write_idf",
    "write_epjson",
    "convert_idf_to_epjson",
    "convert_epjson_to_idf",
    # Validation
    "ValidationError",
    "ValidationResult",
    "validate_document",
    # Exceptions
    "ParserError",
    "SchemaNotFoundError",
    "DuplicateObjectError",
    "UnknownObjectTypeError",
    "InvalidFieldError",
    "VersionNotFoundError",
    # Reference graph
    "ReferenceGraph",
]

from .objects import IDFObject, IDFCollection
from .document import IDFDocument
from .schema import EpJSONSchema, SchemaManager, get_schema
from .idf_parser import parse_idf, get_idf_version
from .epjson_parser import parse_epjson
from .writers import write_idf, write_epjson, convert_idf_to_epjson, convert_epjson_to_idf
from .validation import ValidationError, ValidationResult, validate_document
from .exceptions import (
    ParserError,
    SchemaNotFoundError,
    DuplicateObjectError,
    UnknownObjectTypeError,
    InvalidFieldError,
    VersionNotFoundError,
)
from .references import ReferenceGraph
from .idf_model import IDF
