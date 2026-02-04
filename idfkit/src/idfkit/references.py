"""
Reference graph for tracking object dependencies.

Provides O(1) lookups for:
- What objects reference a given name?
- What names does an object reference?
- Validation of reference integrity
"""

from __future__ import annotations

from collections import defaultdict
from typing import TYPE_CHECKING, Iterator

if TYPE_CHECKING:
    from .objects import IDFObject


class ReferenceGraph:
    """
    Tracks object references for instant dependency queries.

    The graph maintains two indexes:
    - _referenced_by: name -> set of objects that reference it
    - _references: object -> set of names it references

    This enables O(1) lookups for common operations like:
    - Finding all surfaces in a zone
    - Finding all objects using a construction
    - Detecting dangling references
    """

    __slots__ = ("_referenced_by", "_references", "_object_lists")

    def __init__(self):
        # name (uppercase) -> set of (object, field_name) tuples that reference it
        self._referenced_by: dict[str, set[tuple[IDFObject, str]]] = defaultdict(set)
        # object -> set of (name_uppercase, field_name) tuples it references
        self._references: dict[IDFObject, set[tuple[str, str]]] = defaultdict(set)
        # object_list name -> set of object types that provide names for it
        self._object_lists: dict[str, set[str]] = defaultdict(set)

    def register_object_list(self, list_name: str, obj_type: str) -> None:
        """Register that an object type provides names for an object-list."""
        self._object_lists[list_name].add(obj_type)

    def register(self, obj: IDFObject, field_name: str, referenced_name: str) -> None:
        """
        Register that an object references another name.

        Args:
            obj: The object that contains the reference
            field_name: The field that contains the reference
            referenced_name: The name being referenced
        """
        if not referenced_name:
            return

        name_upper = referenced_name.upper()
        self._referenced_by[name_upper].add((obj, field_name))
        self._references[obj].add((name_upper, field_name))

    def unregister(self, obj: IDFObject) -> None:
        """Remove all reference tracking for an object."""
        if obj in self._references:
            # Remove from referenced_by
            for name_upper, field_name in self._references[obj]:
                if name_upper in self._referenced_by:
                    self._referenced_by[name_upper].discard((obj, field_name))
                    if not self._referenced_by[name_upper]:
                        del self._referenced_by[name_upper]
            del self._references[obj]

        # Also remove any references TO this object
        obj_name_upper = obj.name.upper() if obj.name else ""
        if obj_name_upper in self._referenced_by:
            del self._referenced_by[obj_name_upper]

    def get_referencing(self, name: str) -> set[IDFObject]:
        """
        O(1): Get all objects that reference a given name.

        Args:
            name: The name to look up

        Returns:
            Set of IDFObjects that reference this name
        """
        refs = self._referenced_by.get(name.upper(), set())
        return {obj for obj, _ in refs}

    def get_referencing_with_fields(self, name: str) -> set[tuple[IDFObject, str]]:
        """
        O(1): Get all (object, field_name) pairs that reference a given name.

        Args:
            name: The name to look up

        Returns:
            Set of (IDFObject, field_name) tuples
        """
        return self._referenced_by.get(name.upper(), set()).copy()

    def get_references(self, obj: IDFObject) -> set[str]:
        """
        O(1): Get all names that an object references.

        Args:
            obj: The object to look up

        Returns:
            Set of names (uppercase) that this object references
        """
        refs = self._references.get(obj, set())
        return {name for name, _ in refs}

    def get_references_with_fields(self, obj: IDFObject) -> set[tuple[str, str]]:
        """
        O(1): Get all (name, field_name) pairs that an object references.

        Args:
            obj: The object to look up

        Returns:
            Set of (name, field_name) tuples
        """
        return self._references.get(obj, set()).copy()

    def is_referenced(self, name: str) -> bool:
        """Check if a name is referenced by any object."""
        return name.upper() in self._referenced_by

    def get_dangling_references(
        self, valid_names: set[str]
    ) -> Iterator[tuple[IDFObject, str, str]]:
        """
        Find all references to non-existent objects.

        Args:
            valid_names: Set of valid object names (uppercase)

        Yields:
            Tuples of (source_object, field_name, referenced_name)
        """
        valid_upper = {n.upper() for n in valid_names}

        for obj, refs in self._references.items():
            for name_upper, field_name in refs:
                if name_upper not in valid_upper:
                    yield (obj, field_name, name_upper)

    def clear(self) -> None:
        """Clear all reference tracking."""
        self._referenced_by.clear()
        self._references.clear()
        self._object_lists.clear()

    def __len__(self) -> int:
        """Return total number of references tracked."""
        return sum(len(refs) for refs in self._references.values())

    def stats(self) -> dict[str, int]:
        """Return statistics about the reference graph."""
        return {
            "total_references": len(self),
            "objects_with_references": len(self._references),
            "names_referenced": len(self._referenced_by),
            "object_lists": len(self._object_lists),
        }
