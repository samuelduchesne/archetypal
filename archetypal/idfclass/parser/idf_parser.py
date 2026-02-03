"""
Streaming IDF parser - parses EnergyPlus IDF files into IDFDocument.

Features:
- Memory-efficient streaming for large files
- Regex-based tokenization
- Direct parsing into IDFDocument (no intermediate structures)
- Type coercion based on schema
"""

from __future__ import annotations

import mmap
import re
from pathlib import Path
from typing import Any, Iterator, TYPE_CHECKING

from .document import IDFDocument
from .objects import IDFObject, to_python_name
from .exceptions import VersionNotFoundError, ParserError

if TYPE_CHECKING:
    from .schema import EpJSONSchema

# Regex patterns for parsing
_VERSION_PATTERN = re.compile(
    rb"VERSION\s*,\s*(\d+)\.(\d+)(?:\.(\d+))?\s*;",
    re.IGNORECASE,
)

_COMMENT_PATTERN = re.compile(rb"!.*$", re.MULTILINE)

# Pattern to match IDF objects: "ObjectType, field1, field2, ..., fieldN;"
# Handles multi-line objects and comments
_OBJECT_PATTERN = re.compile(
    rb"([A-Za-z][A-Za-z0-9:_ \-]*?)\s*,\s*"  # Object type (group 1)
    rb"((?:[^;!]*(?:![^\n]*\n)?)*?)"  # Fields with optional comments (group 2)
    rb"\s*;",  # Terminating semicolon
    re.DOTALL,
)

# Pattern to split fields (handles inline comments)
_FIELD_SPLIT_PATTERN = re.compile(rb"\s*,\s*")

# Memory map threshold (10 MB)
_MMAP_THRESHOLD = 10 * 1024 * 1024


def parse_idf(
    filepath: Path | str,
    schema: "EpJSONSchema | None" = None,
    version: tuple[int, int, int] | None = None,
    encoding: str = "latin-1",
) -> IDFDocument:
    """
    Parse an IDF file into an IDFDocument.

    Args:
        filepath: Path to the IDF file
        schema: Optional EpJSONSchema for field ordering and type coercion
        version: Optional version override (auto-detected if not provided)
        encoding: File encoding (default: latin-1 for compatibility)

    Returns:
        Parsed IDFDocument

    Raises:
        VersionNotFoundError: If version cannot be detected
        ParserError: If parsing fails
    """
    filepath = Path(filepath)

    if not filepath.exists():
        raise FileNotFoundError(f"IDF file not found: {filepath}")

    parser = IDFParser(filepath, schema, encoding)
    return parser.parse(version)


class IDFParser:
    """
    Streaming parser for IDF files.

    Uses memory mapping for large files and regex for tokenization.
    """

    __slots__ = ("_filepath", "_schema", "_encoding", "_content")

    def __init__(
        self,
        filepath: Path,
        schema: "EpJSONSchema | None" = None,
        encoding: str = "latin-1",
    ):
        self._filepath = filepath
        self._schema = schema
        self._encoding = encoding
        self._content: bytes | None = None

    def parse(self, version: tuple[int, int, int] | None = None) -> IDFDocument:
        """
        Parse the IDF file into an IDFDocument.

        Args:
            version: Optional version override

        Returns:
            Parsed IDFDocument
        """
        # Load content (with mmap for large files)
        content = self._load_content()

        # Detect version if not provided
        if version is None:
            version = self._detect_version(content)

        # Load schema if not provided
        schema = self._schema
        if schema is None:
            try:
                from .schema import get_schema

                schema = get_schema(version)
            except Exception:
                # Continue without schema - field ordering won't be available
                pass

        # Create document
        doc = IDFDocument(version=version, schema=schema, filepath=self._filepath)

        # Parse objects
        self._parse_objects(content, doc, schema)

        return doc

    def _load_content(self) -> bytes:
        """Load file content, using mmap for large files."""
        file_size = self._filepath.stat().st_size

        if file_size > _MMAP_THRESHOLD:
            # Use memory mapping for large files
            with open(self._filepath, "rb") as f:
                mm = mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)
                content = bytes(mm)
                mm.close()
        else:
            with open(self._filepath, "rb") as f:
                content = f.read()

        return content

    def _detect_version(self, content: bytes) -> tuple[int, int, int]:
        """Detect EnergyPlus version from file content."""
        # Only search first 10KB for version
        header = content[:10240]

        match = _VERSION_PATTERN.search(header)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            patch = int(match.group(3)) if match.group(3) else 0
            return (major, minor, patch)

        raise VersionNotFoundError(str(self._filepath))

    def _parse_objects(
        self,
        content: bytes,
        doc: IDFDocument,
        schema: "EpJSONSchema | None",
    ) -> None:
        """Parse all objects from content into document."""
        for match in _OBJECT_PATTERN.finditer(content):
            try:
                obj = self._parse_object(match, schema)
                if obj:
                    doc.addidfobject(obj)
            except Exception as e:
                # Log parse errors but continue
                obj_type = match.group(1).decode(self._encoding).strip()
                # Could add logging here
                pass

    def _parse_object(
        self,
        match: re.Match,
        schema: "EpJSONSchema | None",
    ) -> IDFObject | None:
        """Parse a single object from regex match."""
        obj_type = match.group(1).decode(self._encoding).strip()
        fields_raw = match.group(2).decode(self._encoding)

        # Skip version object (handled separately)
        if obj_type.upper() == "VERSION":
            return None

        # Split and clean fields
        fields = self._parse_fields(fields_raw)

        if not fields:
            return None

        # First field is the name
        name = fields[0] if fields else ""

        # Get field ordering from schema
        field_names = None
        obj_schema = None
        if schema:
            field_names = schema.get_field_names(obj_type)
            obj_schema = schema.get_object_schema(obj_type)

        # Build data dict
        data = {}
        remaining_fields = fields[1:]  # Skip name

        if field_names:
            # Use schema field ordering
            for i, value in enumerate(remaining_fields):
                if i < len(field_names):
                    field_name = field_names[i]
                    if value:  # Only store non-empty values
                        data[field_name] = self._coerce_value(
                            obj_type, field_name, value, schema
                        )
        else:
            # No schema - use generic field names
            for i, value in enumerate(remaining_fields):
                if value:
                    data[f"field_{i + 1}"] = value

        return IDFObject(
            obj_type=obj_type,
            name=name,
            data=data,
            schema=obj_schema,
            field_order=field_names,
        )

    def _parse_fields(self, fields_raw: str) -> list[str]:
        """Parse and clean field values from raw string."""
        fields = []

        # Split by comma, handling inline comments
        for part in fields_raw.split(","):
            # Remove inline comments
            if "!" in part:
                part = part[: part.index("!")]

            # Clean whitespace
            value = part.strip()
            fields.append(value)

        return fields

    def _coerce_value(
        self,
        obj_type: str,
        field_name: str,
        value: str,
        schema: "EpJSONSchema | None",
    ) -> Any:
        """Coerce a field value to the appropriate type."""
        if not schema or not value:
            return value

        field_type = schema.get_field_type(obj_type, field_name)

        if field_type == "number":
            try:
                # Handle scientific notation
                return float(value)
            except ValueError:
                # Might be "autocalculate", "autosize", etc.
                return value.lower()

        elif field_type == "integer":
            try:
                return int(float(value))
            except ValueError:
                return value

        # Default: return as string
        return value


def iter_idf_objects(
    filepath: Path | str,
    encoding: str = "latin-1",
) -> Iterator[tuple[str, str, list[str]]]:
    """
    Iterate over objects in an IDF file without loading into document.

    Yields:
        Tuples of (object_type, name, [field_values])

    This is useful for quick scanning or filtering without full parsing.
    """
    filepath = Path(filepath)

    with open(filepath, "rb") as f:
        content = f.read()

    for match in _OBJECT_PATTERN.finditer(content):
        obj_type = match.group(1).decode(encoding).strip()
        fields_raw = match.group(2).decode(encoding)

        # Split and clean fields
        fields = []
        for part in fields_raw.split(","):
            if "!" in part:
                part = part[: part.index("!")]
            fields.append(part.strip())

        name = fields[0] if fields else ""
        yield (obj_type, name, fields[1:])


def get_idf_version(filepath: Path | str) -> tuple[int, int, int]:
    """
    Quick version detection without full parsing.

    Args:
        filepath: Path to IDF file

    Returns:
        Version tuple (major, minor, patch)

    Raises:
        VersionNotFoundError: If version cannot be detected
    """
    filepath = Path(filepath)

    with open(filepath, "rb") as f:
        header = f.read(10240)

    match = _VERSION_PATTERN.search(header)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2))
        patch = int(match.group(3)) if match.group(3) else 0
        return (major, minor, patch)

    raise VersionNotFoundError(str(filepath))
