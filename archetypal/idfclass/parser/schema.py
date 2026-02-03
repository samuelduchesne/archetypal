"""
EpJSON Schema loader and manager.

Handles loading and caching of Energy+.schema.epJSON files
for different EnergyPlus versions.
"""

from __future__ import annotations

import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from .exceptions import SchemaNotFoundError


class EpJSONSchema:
    """
    Wrapper around Energy+.schema.epJSON providing easy access to object definitions.

    The schema contains:
    - Object definitions with field types, defaults, constraints
    - Reference lists (object-list) for cross-object validation
    - Legacy IDD info for IDF field ordering

    Attributes:
        version: The EnergyPlus version tuple
        _raw: The raw schema dict
        _properties: Object definitions
    """

    __slots__ = ("version", "_raw", "_properties", "_reference_lists", "_object_lists")

    def __init__(self, version: tuple[int, int, int], schema_data: dict):
        self.version = version
        self._raw = schema_data
        self._properties = schema_data.get("properties", {})

        # Build reference indexes
        self._reference_lists: dict[str, list[str]] = {}
        self._object_lists: dict[str, set[str]] = {}
        self._build_reference_indexes()

    def _build_reference_indexes(self) -> None:
        """Build indexes for reference and object lists."""
        for obj_type, obj_schema in self._properties.items():
            # Check if this object provides names for any reference lists
            name_info = obj_schema.get("name", {})
            if "reference" in name_info:
                for ref_list in name_info["reference"]:
                    if ref_list not in self._reference_lists:
                        self._reference_lists[ref_list] = []
                    self._reference_lists[ref_list].append(obj_type)

            # Find fields that reference object lists
            pattern_props = obj_schema.get("patternProperties", {})
            inner = next(iter(pattern_props.values()), {}) if pattern_props else {}
            props = inner.get("properties", {})
            for field_name, field_schema in props.items():
                if "object_list" in field_schema:
                    for obj_list in field_schema["object_list"]:
                        if obj_list not in self._object_lists:
                            self._object_lists[obj_list] = set()
                        self._object_lists[obj_list].add(f"{obj_type}.{field_name}")

    def get_object_schema(self, obj_type: str) -> dict | None:
        """Get the full schema for an object type."""
        return self._properties.get(obj_type)

    def get_inner_schema(self, obj_type: str) -> dict | None:
        """Get the inner schema (inside patternProperties) for an object type."""
        obj_schema = self.get_object_schema(obj_type)
        if not obj_schema:
            return None
        pattern_props = obj_schema.get("patternProperties", {})
        # The pattern key varies (e.g., ".*", "^.*\\S.*$") - get the first one
        for key in pattern_props:
            return pattern_props[key]
        return None

    def get_field_schema(self, obj_type: str, field_name: str) -> dict | None:
        """Get schema for a specific field of an object type."""
        inner = self.get_inner_schema(obj_type)
        if not inner:
            return None
        return inner.get("properties", {}).get(field_name)

    def get_field_names(self, obj_type: str) -> list[str]:
        """Get ordered list of field names for an object type (from legacy_idd)."""
        obj_schema = self.get_object_schema(obj_type)
        if not obj_schema:
            return []
        legacy = obj_schema.get("legacy_idd", {})
        fields = legacy.get("fields", [])
        # First field is 'name', return the rest
        return fields[1:] if fields else []

    def get_all_field_names(self, obj_type: str) -> list[str]:
        """Get all field names including 'name'."""
        obj_schema = self.get_object_schema(obj_type)
        if not obj_schema:
            return []
        legacy = obj_schema.get("legacy_idd", {})
        return legacy.get("fields", [])

    def get_required_fields(self, obj_type: str) -> list[str]:
        """Get list of required field names for an object type."""
        inner = self.get_inner_schema(obj_type)
        if not inner:
            return []
        return inner.get("required", [])

    def get_field_default(self, obj_type: str, field_name: str) -> Any:
        """Get default value for a field."""
        field_schema = self.get_field_schema(obj_type, field_name)
        if field_schema:
            return field_schema.get("default")
        return None

    def get_field_type(self, obj_type: str, field_name: str) -> str | None:
        """Get the type of a field ('number', 'string', 'integer', 'array')."""
        field_schema = self.get_field_schema(obj_type, field_name)
        if not field_schema:
            return None

        # Handle anyOf (e.g., number OR "Autocalculate")
        if "anyOf" in field_schema:
            for sub in field_schema["anyOf"]:
                if sub.get("type") in ("number", "integer"):
                    return sub["type"]
            return "string"

        return field_schema.get("type")

    def get_field_object_list(self, obj_type: str, field_name: str) -> list[str] | None:
        """Get the object_list(s) that a field references."""
        field_schema = self.get_field_schema(obj_type, field_name)
        if field_schema:
            return field_schema.get("object_list")
        return None

    def is_reference_field(self, obj_type: str, field_name: str) -> bool:
        """Check if a field is a reference to another object."""
        return self.get_field_object_list(obj_type, field_name) is not None

    def get_types_providing_reference(self, ref_list: str) -> list[str]:
        """Get object types that provide names for a reference list."""
        return self._reference_lists.get(ref_list, [])

    def get_object_memo(self, obj_type: str) -> str | None:
        """Get the memo/description for an object type."""
        obj_schema = self.get_object_schema(obj_type)
        if obj_schema:
            return obj_schema.get("memo")
        return None

    def is_extensible(self, obj_type: str) -> bool:
        """Check if an object type has extensible fields."""
        obj_schema = self.get_object_schema(obj_type)
        if obj_schema:
            return "extensible_size" in obj_schema
        return False

    def get_extensible_size(self, obj_type: str) -> int | None:
        """Get the extensible group size for an object type."""
        obj_schema = self.get_object_schema(obj_type)
        if obj_schema:
            return obj_schema.get("extensible_size")
        return None

    @property
    def object_types(self) -> list[str]:
        """Get list of all object types in the schema."""
        return list(self._properties.keys())

    def __contains__(self, obj_type: str) -> bool:
        """Check if an object type exists in the schema."""
        return obj_type in self._properties

    def __len__(self) -> int:
        """Return number of object types."""
        return len(self._properties)


class SchemaManager:
    """
    Manages loading and caching of EpJSON schemas for different versions.

    Searches for schemas in:
    1. Bundled schemas directory (shipped with archetypal)
    2. EnergyPlus installation directories
    """

    # Common EnergyPlus installation paths by platform
    _INSTALL_PATHS = {
        "linux": ["/usr/local/EnergyPlus-{v}", "/opt/EnergyPlus-{v}"],
        "darwin": ["/Applications/EnergyPlus-{v}"],
        "win32": [
            "C:\\EnergyPlusV{v}",
            "C:\\EnergyPlus-{v}",
            os.path.expandvars("$LOCALAPPDATA\\EnergyPlusV{v}"),
        ],
    }

    def __init__(self, bundled_schema_dir: Path | None = None):
        """
        Initialize the schema manager.

        Args:
            bundled_schema_dir: Path to directory with bundled schema files.
                               If None, uses default location.
        """
        if bundled_schema_dir is None:
            # Default: schemas directory next to this file
            bundled_schema_dir = Path(__file__).parent / "schemas"

        self._bundled_dir = bundled_schema_dir
        self._cache: dict[tuple[int, int, int], EpJSONSchema] = {}

    @lru_cache(maxsize=8)
    def get_schema(self, version: tuple[int, int, int]) -> EpJSONSchema:
        """
        Load and return schema for a specific version.

        Args:
            version: EnergyPlus version tuple (major, minor, patch)

        Returns:
            EpJSONSchema for the requested version

        Raises:
            SchemaNotFoundError: If schema cannot be found
        """
        if version in self._cache:
            return self._cache[version]

        schema_path = self._find_schema_file(version)
        with open(schema_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        schema = EpJSONSchema(version, data)
        self._cache[version] = schema
        return schema

    def _find_schema_file(self, version: tuple[int, int, int]) -> Path:
        """
        Find the schema file for a version.

        Searches in bundled directory first, then EnergyPlus installations.
        """
        searched = []

        # Try bundled schemas first
        bundled_paths = self._get_bundled_paths(version)
        for path in bundled_paths:
            searched.append(str(path))
            if path.exists():
                return path

        # Try EnergyPlus installation
        install_paths = self._get_install_paths(version)
        for path in install_paths:
            searched.append(str(path))
            if path.exists():
                return path

        raise SchemaNotFoundError(version, searched)

    def _get_bundled_paths(self, version: tuple[int, int, int]) -> list[Path]:
        """Get potential bundled schema paths for a version."""
        paths = []
        v = version

        # Various naming conventions
        patterns = [
            f"Energy+.schema.epJSON",  # Direct in version dir
            f"V{v[0]}-{v[1]}-{v[2]}/Energy+.schema.epJSON",
            f"v{v[0]}.{v[1]}.{v[2]}/Energy+.schema.epJSON",
            f"v{v[0]}_{v[1]}_{v[2]}/Energy+.schema.epJSON",
        ]

        for pattern in patterns:
            paths.append(self._bundled_dir / pattern)

        return paths

    def _get_install_paths(self, version: tuple[int, int, int]) -> list[Path]:
        """Get potential EnergyPlus installation schema paths."""
        import sys

        platform = sys.platform
        paths = []
        v = version

        # Get base paths for this platform
        base_patterns = self._INSTALL_PATHS.get(
            platform, self._INSTALL_PATHS.get("linux", [])
        )

        version_formats = [
            f"{v[0]}-{v[1]}-{v[2]}",
            f"{v[0]}.{v[1]}.{v[2]}",
            f"{v[0]}-{v[1]}",
        ]

        for base_pattern in base_patterns:
            for v_fmt in version_formats:
                base_path = Path(base_pattern.format(v=v_fmt))
                paths.append(base_path / "Energy+.schema.epJSON")

        return paths

    def get_available_versions(self) -> list[tuple[int, int, int]]:
        """Get list of versions with available schemas."""
        versions = set()

        # Check bundled
        if self._bundled_dir.exists():
            for item in self._bundled_dir.iterdir():
                if item.is_dir():
                    version = self._parse_version_from_dirname(item.name)
                    if version:
                        versions.add(version)

        # Check installed EnergyPlus versions
        import sys

        platform = sys.platform
        base_patterns = self._INSTALL_PATHS.get(
            platform, self._INSTALL_PATHS.get("linux", [])
        )

        for pattern in base_patterns:
            # Look for existing directories matching the pattern
            parent = Path(pattern.split("{v}")[0])
            if parent.exists():
                for item in parent.iterdir():
                    if item.is_dir() and "EnergyPlus" in item.name:
                        version = self._parse_version_from_dirname(item.name)
                        if version:
                            schema_path = item / "Energy+.schema.epJSON"
                            if schema_path.exists():
                                versions.add(version)

        return sorted(versions)

    @staticmethod
    def _parse_version_from_dirname(dirname: str) -> tuple[int, int, int] | None:
        """Parse version tuple from directory name."""
        import re

        # Match patterns like "9-2-0", "9.2.0", "V9-2-0", "EnergyPlus-9-2-0"
        match = re.search(r"(\d+)[-._](\d+)[-._]?(\d+)?", dirname)
        if match:
            major = int(match.group(1))
            minor = int(match.group(2))
            patch = int(match.group(3)) if match.group(3) else 0
            return (major, minor, patch)
        return None

    def clear_cache(self) -> None:
        """Clear the schema cache."""
        self._cache.clear()
        self.get_schema.cache_clear()


# Global schema manager instance
_schema_manager: SchemaManager | None = None


def get_schema_manager() -> SchemaManager:
    """Get the global schema manager instance."""
    global _schema_manager
    if _schema_manager is None:
        _schema_manager = SchemaManager()
    return _schema_manager


def get_schema(version: tuple[int, int, int]) -> EpJSONSchema:
    """Convenience function to get schema for a version."""
    return get_schema_manager().get_schema(version)
