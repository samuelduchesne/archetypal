"""Adapter module bridging idfkit objects to archetypal's template code.

This module provides compatibility between idfkit's API and the existing
patterns used in archetypal's template classes (originally designed for eppy).
"""

from __future__ import annotations

import re
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, Iterator

if TYPE_CHECKING:
    import idfkit


def _to_snake_case(name: str) -> str:
    """Convert CamelCase or space-separated field names to snake_case.

    Examples:
        'Zone Name' -> 'zone_name'
        'Conductivity' -> 'conductivity'
        'Solar_Absorptance' -> 'solar_absorptance'
    """
    # Replace spaces with underscores
    name = name.replace(" ", "_")
    # Insert underscore before uppercase letters (for CamelCase)
    name = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    return name.lower()


def _to_field_name(name: str) -> str:
    """Convert snake_case or CamelCase to IDF field name format.

    Examples:
        'zone_name' -> 'Zone Name'
        'Conductivity' -> 'Conductivity'
    """
    # Handle already camelCase or PascalCase
    if "_" not in name and name[0].isupper():
        return name
    # Convert snake_case to Title Case
    return " ".join(word.capitalize() for word in name.split("_"))


class IdfkitObject:
    """Wrapper providing epbunch-like interface for idfkit objects.

    This allows existing archetypal code patterns like:
        obj.Conductivity
        obj["Zone Name"]
        obj.Name

    To work with idfkit objects that use:
        obj.conductivity
        obj.zone_name
        obj.name
    """

    def __init__(self, obj: Any, adapter: IdfkitAdapter) -> None:
        """Initialize wrapper.

        Args:
            obj: The underlying idfkit object
            adapter: Parent IdfkitAdapter for accessing other objects
        """
        self._obj = obj
        self._adapter = adapter

    @property
    def Name(self) -> str:
        """Get object name (eppy compatibility)."""
        return self._obj.name

    @property
    def key(self) -> str:
        """Get object type name (eppy compatibility)."""
        return self._obj.type_name

    @property
    def theidf(self) -> IdfkitAdapter:
        """Get parent IDF adapter (eppy compatibility)."""
        return self._adapter

    def __getattr__(self, name: str) -> Any:
        """Allow attribute access to fields in various formats.

        Handles:
            obj.Conductivity -> obj.conductivity
            obj.Zone_Name -> obj.zone_name
        """
        if name.startswith("_"):
            raise AttributeError(name)

        snake_name = _to_snake_case(name)
        try:
            return getattr(self._obj, snake_name)
        except AttributeError:
            # Try exact name as fallback
            return getattr(self._obj, name)

    def __getitem__(self, key: str) -> Any:
        """Allow dict-style access to fields.

        Handles:
            obj["Zone Name"] -> obj.zone_name
            obj["Conductivity"] -> obj.conductivity
        """
        snake_name = _to_snake_case(key)
        try:
            return getattr(self._obj, snake_name)
        except AttributeError:
            return getattr(self._obj, key)

    def get_referenced_object(self, field_name: str) -> IdfkitObject | None:
        """Get object referenced by a field.

        Args:
            field_name: Name of the field containing the reference

        Returns:
            IdfkitObject wrapping the referenced object, or None if not found
        """
        ref_name = self[field_name]
        if not ref_name:
            return None

        # Use idfkit's reference tracking to find the referenced object
        # This requires knowing the target type, which we can infer from field metadata
        # For now, search common object types
        for obj_type in self._adapter._doc.object_types:
            try:
                ref_obj = self._adapter._doc[obj_type].get(ref_name)
                if ref_obj is not None:
                    return IdfkitObject(ref_obj, self._adapter)
            except (KeyError, TypeError):
                continue
        return None

    def __repr__(self) -> str:
        return f"IdfkitObject({self.key}: {self.Name})"


class IdfkitObjectCollection:
    """Collection of objects by type, providing eppy-like access."""

    def __init__(self, obj_type: str, adapter: IdfkitAdapter) -> None:
        self._obj_type = obj_type
        self._adapter = adapter

    def __iter__(self) -> Iterator[IdfkitObject]:
        """Iterate over all objects of this type."""
        collection = self._adapter._doc.get(self._obj_type, {})
        for obj in collection.values():
            yield IdfkitObject(obj, self._adapter)

    def __len__(self) -> int:
        collection = self._adapter._doc.get(self._obj_type, {})
        return len(collection)

    def __getitem__(self, name: str) -> IdfkitObject:
        """Get object by name."""
        obj = self._adapter._doc[self._obj_type][name]
        return IdfkitObject(obj, self._adapter)

    def get(self, name: str) -> IdfkitObject | None:
        """Get object by name, returning None if not found."""
        try:
            return self[name]
        except KeyError:
            return None


class IdfkitAdapter:
    """Adapter providing eppy-compatible interface for idfkit Document.

    This allows existing archetypal code patterns like:
        idf.idfobjects["ZONE"]
        idf.idfobjects["MATERIAL"]

    To work with idfkit documents that use:
        doc["Zone"]
        doc["Material"]
    """

    def __init__(self, doc: idfkit.Document) -> None:
        """Initialize adapter.

        Args:
            doc: idfkit Document object
        """
        self._doc = doc
        self._sql_path: Path | None = None

    @property
    def idfobjects(self) -> dict[str, IdfkitObjectCollection]:
        """Provide dict-like access to objects by type (eppy compatibility).

        Returns a proxy that handles type name normalization.
        """
        return _IdfObjectsProxy(self)

    @property
    def sql_file(self) -> Path | None:
        """Path to simulation SQL results file."""
        return self._sql_path

    @sql_file.setter
    def sql_file(self, path: Path | str | None) -> None:
        self._sql_path = Path(path) if path else None

    def getobject(self, obj_type: str, name: str) -> IdfkitObject | None:
        """Get a single object by type and name.

        Args:
            obj_type: Object type (e.g., "Zone", "Material")
            name: Object name

        Returns:
            IdfkitObject wrapper or None if not found
        """
        # Normalize type name (ZONE -> Zone)
        normalized_type = obj_type.title().replace(":", ":")
        try:
            obj = self._doc[normalized_type][name]
            return IdfkitObject(obj, self)
        except KeyError:
            return None

    def get_zone_surfaces(self, zone_name: str) -> list[IdfkitObject]:
        """Get all surfaces belonging to a zone.

        Args:
            zone_name: Name of the zone

        Returns:
            List of surface objects (BuildingSurface:Detailed, etc.)
        """
        surfaces = []
        surface_types = [
            "BuildingSurface:Detailed",
            "FenestrationSurface:Detailed",
            "Wall:Detailed",
            "RoofCeiling:Detailed",
            "Floor:Detailed",
        ]

        for surf_type in surface_types:
            collection = self._doc.get(surf_type, {})
            for surface in collection.values():
                if getattr(surface, "zone_name", None) == zone_name:
                    surfaces.append(IdfkitObject(surface, self))

        return surfaces

    def get_zone_fenestrations(self, zone_name: str) -> list[IdfkitObject]:
        """Get all fenestration surfaces (windows/doors) for a zone.

        Args:
            zone_name: Name of the zone

        Returns:
            List of fenestration surface objects
        """
        fenestrations = []
        zone_surfaces = self.get_zone_surfaces(zone_name)
        surface_names = {s.Name for s in zone_surfaces}

        fenestration_types = [
            "FenestrationSurface:Detailed",
            "Window",
            "Door",
            "GlazedDoor",
        ]

        for fen_type in fenestration_types:
            collection = self._doc.get(fen_type, {})
            for fen in collection.values():
                # Check if this fenestration is on a surface in our zone
                building_surface = getattr(fen, "building_surface_name", None)
                if building_surface in surface_names:
                    fenestrations.append(IdfkitObject(fen, self))

        return fenestrations

    @cached_property
    def object_types(self) -> list[str]:
        """List all object types present in the document."""
        return list(self._doc.keys())


class _IdfObjectsProxy:
    """Proxy for idfobjects access with type name normalization."""

    def __init__(self, adapter: IdfkitAdapter) -> None:
        self._adapter = adapter

    def __getitem__(self, obj_type: str) -> IdfkitObjectCollection:
        """Get collection of objects by type.

        Handles type name normalization:
            "ZONE" -> "Zone"
            "MATERIAL" -> "Material"
            "BUILDINGSURFACE:DETAILED" -> "BuildingSurface:Detailed"
        """
        # Normalize: UPPERCASE or lowercase to Title Case
        parts = obj_type.split(":")
        normalized = ":".join(part.title() for part in parts)
        return IdfkitObjectCollection(normalized, self._adapter)

    def get(self, obj_type: str) -> IdfkitObjectCollection | None:
        """Get collection, returning empty collection if type not found."""
        try:
            return self[obj_type]
        except KeyError:
            return None
