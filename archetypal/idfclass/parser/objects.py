"""
Core object classes for IDF representation.

IDFObject: Thin wrapper around a dict with attribute access.
IDFCollection: Indexed collection of IDFObjects with O(1) lookup.
"""

from __future__ import annotations

import re
from typing import Any, Iterator, TYPE_CHECKING

if TYPE_CHECKING:
    from .document import IDFDocument

# Field name conversion patterns
_FIELD_NAME_PATTERN = re.compile(r"[^a-zA-Z0-9]+")


def to_python_name(idf_name: str) -> str:
    """Convert IDF field name to Python-friendly name.

    'Direction of Relative North' -> 'direction_of_relative_north'
    'X Origin' -> 'x_origin'
    """
    return _FIELD_NAME_PATTERN.sub("_", idf_name.lower()).strip("_")


def to_idf_name(python_name: str) -> str:
    """Convert Python name back to IDF-style name.

    'direction_of_relative_north' -> 'Direction of Relative North'
    """
    return " ".join(word.capitalize() for word in python_name.split("_"))


class IDFObject:
    """
    Lightweight wrapper around a dict representing an EnergyPlus object.

    Uses __slots__ for memory efficiency - each object is ~200 bytes.
    Provides attribute access to fields via __getattr__/__setattr__.

    Attributes:
        _type: The IDF object type (e.g., "Zone", "Material")
        _name: The object's name (first field)
        _data: Dict of field_name -> value
        _schema: Optional schema dict for validation
        _document: Reference to parent document (for reference resolution)
        _field_order: Ordered list of field names from schema
    """

    __slots__ = ("_type", "_name", "_data", "_schema", "_document", "_field_order")

    def __init__(
        self,
        obj_type: str,
        name: str,
        data: dict[str, Any] | None = None,
        schema: dict | None = None,
        document: "IDFDocument | None" = None,
        field_order: list[str] | None = None,
    ):
        object.__setattr__(self, "_type", obj_type)
        object.__setattr__(self, "_name", name)
        object.__setattr__(self, "_data", data if data is not None else {})
        object.__setattr__(self, "_schema", schema)
        object.__setattr__(self, "_document", document)
        object.__setattr__(self, "_field_order", field_order)

    @property
    def name(self) -> str:
        """The object's name."""
        return self._name

    @name.setter
    def name(self, value: str) -> None:
        """Set the object's name."""
        object.__setattr__(self, "_name", value)

    @property
    def key(self) -> str:
        """The object type (alias for eppy compatibility)."""
        return self._type

    @property
    def Name(self) -> str:
        """The object's name (eppy compatibility - capitalized)."""
        return self._name

    @Name.setter
    def Name(self, value: str) -> None:
        """Set the object's name (eppy compatibility)."""
        object.__setattr__(self, "_name", value)

    @property
    def fieldnames(self) -> list[str]:
        """List of field names (eppy compatibility)."""
        if self._field_order:
            return ["Name"] + list(self._field_order)
        return ["Name"] + list(self._data.keys())

    @property
    def fieldvalues(self) -> list[Any]:
        """List of field values in order (eppy compatibility)."""
        if self._field_order:
            return [self._name] + [self._data.get(f) for f in self._field_order]
        return [self._name] + list(self._data.values())

    @property
    def theidf(self) -> "IDFDocument | None":
        """Reference to parent document (eppy compatibility)."""
        return self._document

    def __getattr__(self, key: str) -> Any:
        """Get field value by attribute name."""
        if key.startswith("_"):
            raise AttributeError(key)

        # Try exact match first
        data = object.__getattribute__(self, "_data")
        if key in data:
            return data[key]

        # Try lowercase version
        key_lower = key.lower()
        if key_lower in data:
            return data[key_lower]

        # Try python name conversion
        python_key = to_python_name(key)
        if python_key in data:
            return data[python_key]

        # Field not found - return None (eppy behavior)
        return None

    def __setattr__(self, key: str, value: Any) -> None:
        """Set field value by attribute name."""
        if key.startswith("_"):
            object.__setattr__(self, key, value)
        else:
            # Normalize key to python style
            python_key = to_python_name(key)
            self._data[python_key] = value

    def __getitem__(self, key: str | int) -> Any:
        """Get field value by name or index."""
        if isinstance(key, int):
            if key == 0:
                return self._name
            if self._field_order and 0 < key <= len(self._field_order):
                field_name = self._field_order[key - 1]
                return self._data.get(field_name)
            raise IndexError(f"Field index {key} out of range")
        return getattr(self, key)

    def __setitem__(self, key: str | int, value: Any) -> None:
        """Set field value by name or index."""
        if isinstance(key, int):
            if key == 0:
                self._name = value
            elif self._field_order and 0 < key <= len(self._field_order):
                field_name = self._field_order[key - 1]
                self._data[field_name] = value
            else:
                raise IndexError(f"Field index {key} out of range")
        else:
            setattr(self, key, value)

    def __repr__(self) -> str:
        return f"{self._type}('{self._name}')"

    def __str__(self) -> str:
        return f"{self._type}: {self._name}"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, IDFObject):
            return NotImplemented
        return (
            self._type == other._type
            and self._name == other._name
            and self._data == other._data
        )

    def __hash__(self) -> int:
        return hash((self._type, self._name))

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary representation."""
        return {"name": self._name, **self._data}

    def get(self, key: str, default: Any = None) -> Any:
        """Get field value with default."""
        value = getattr(self, key)
        return value if value is not None else default

    def get_field_idd(self, field_name: str) -> dict | None:
        """Get IDD/schema info for a field (eppy compatibility)."""
        if not self._schema:
            return None
        inner = self._schema.get("patternProperties", {}).get(".*", {})
        return inner.get("properties", {}).get(to_python_name(field_name))

    def getfieldidd(self, field_name: str) -> dict | None:
        """Alias for get_field_idd (eppy compatibility)."""
        return self.get_field_idd(field_name)

    def getfieldidd_item(self, field_name: str, item: str) -> Any:
        """Get specific item from field IDD info (eppy compatibility)."""
        field_idd = self.get_field_idd(field_name)
        if field_idd:
            return field_idd.get(item)
        return None

    def copy(self) -> "IDFObject":
        """Create a copy of this object."""
        return IDFObject(
            obj_type=self._type,
            name=self._name,
            data=dict(self._data),
            schema=self._schema,
            document=None,  # Don't copy document reference
            field_order=self._field_order,
        )


class IDFCollection:
    """
    Indexed collection of IDFObjects with O(1) lookup by name.

    Provides list-like iteration and dict-like access by name.

    Attributes:
        _type: The object type this collection holds
        _by_name: Dict mapping uppercase names to objects
        _items: Ordered list of objects
    """

    __slots__ = ("_type", "_by_name", "_items")

    def __init__(self, obj_type: str):
        self._type = obj_type
        self._by_name: dict[str, IDFObject] = {}
        self._items: list[IDFObject] = []

    def add(self, obj: IDFObject) -> IDFObject:
        """
        Add an object to the collection.

        Args:
            obj: The IDFObject to add

        Returns:
            The added object

        Raises:
            DuplicateObjectError: If an object with the same name exists
        """
        from .exceptions import DuplicateObjectError

        key = obj.name.upper() if obj.name else ""
        if key and key in self._by_name:
            raise DuplicateObjectError(self._type, obj.name)

        if key:
            self._by_name[key] = obj
        self._items.append(obj)
        return obj

    def remove(self, obj: IDFObject) -> None:
        """Remove an object from the collection."""
        key = obj.name.upper() if obj.name else ""
        if key in self._by_name:
            del self._by_name[key]
        if obj in self._items:
            self._items.remove(obj)

    def __getitem__(self, key: str | int) -> IDFObject:
        """Get object by name or index."""
        if isinstance(key, int):
            return self._items[key]
        result = self._by_name.get(key.upper())
        if result is None:
            raise KeyError(f"No {self._type} with name '{key}'")
        return result

    def __iter__(self) -> Iterator[IDFObject]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, key: str | IDFObject) -> bool:
        if isinstance(key, IDFObject):
            return key in self._items
        return key.upper() in self._by_name

    def __bool__(self) -> bool:
        return len(self._items) > 0

    def __repr__(self) -> str:
        return f"IDFCollection({self._type}, count={len(self._items)})"

    def get(self, name: str, default: IDFObject | None = None) -> IDFObject | None:
        """Get object by name with default."""
        return self._by_name.get(name.upper(), default)

    def first(self) -> IDFObject | None:
        """Get the first object or None."""
        return self._items[0] if self._items else None

    def to_list(self) -> list[IDFObject]:
        """Convert to list."""
        return list(self._items)

    def to_dict(self) -> list[dict[str, Any]]:
        """Convert all objects to list of dicts (eppy compatibility)."""
        return [obj.to_dict() for obj in self._items]

    def filter(self, predicate: callable) -> list[IDFObject]:
        """Filter objects by predicate function."""
        return [obj for obj in self._items if predicate(obj)]
