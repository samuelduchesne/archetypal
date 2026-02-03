"""
IDFDocument - The main container for an EnergyPlus model.

Provides:
- Typed access to object collections
- Reference tracking for O(1) dependency lookups
- On-demand validation
- Support for both IDF and epJSON formats
"""

from __future__ import annotations

import re
from copy import deepcopy
from pathlib import Path
from typing import Any, Iterator, TYPE_CHECKING

from .objects import IDFObject, IDFCollection, to_python_name
from .references import ReferenceGraph
from .exceptions import (
    DuplicateObjectError,
    UnknownObjectTypeError,
    VersionNotFoundError,
)

if TYPE_CHECKING:
    from .schema import EpJSONSchema


# Common object type mappings for attribute access
_PYTHON_TO_IDF = {
    "zones": "Zone",
    "materials": "Material",
    "material_nomass": "Material:NoMass",
    "material_airgap": "Material:AirGap",
    "constructions": "Construction",
    "building_surfaces": "BuildingSurface:Detailed",
    "fenestration_surfaces": "FenestrationSurface:Detailed",
    "internal_mass": "InternalMass",
    "shading_surfaces": "Shading:Site:Detailed",
    "shading_building": "Shading:Building:Detailed",
    "shading_zone": "Shading:Zone:Detailed",
    "schedules_compact": "Schedule:Compact",
    "schedules_constant": "Schedule:Constant",
    "schedules_file": "Schedule:File",
    "schedules_year": "Schedule:Year",
    "schedules_week_daily": "Schedule:Week:Daily",
    "schedules_day_interval": "Schedule:Day:Interval",
    "schedules_day_hourly": "Schedule:Day:Hourly",
    "schedules_day_list": "Schedule:Day:List",
    "schedule_type_limits": "ScheduleTypeLimits",
    "people": "People",
    "lights": "Lights",
    "electric_equipment": "ElectricEquipment",
    "gas_equipment": "GasEquipment",
    "hot_water_equipment": "HotWaterEquipment",
    "infiltration": "ZoneInfiltration:DesignFlowRate",
    "ventilation": "ZoneVentilation:DesignFlowRate",
    "thermostats": "ThermostatSetpoint:DualSetpoint",
    "hvac_templates": "HVACTemplate:Zone:IdealLoadsAirSystem",
    "ideal_loads": "ZoneHVAC:IdealLoadsAirSystem",
    "sizing_zone": "Sizing:Zone",
    "sizing_system": "Sizing:System",
    "output_variables": "Output:Variable",
    "output_meters": "Output:Meter",
    "output_table_summary": "Output:Table:SummaryReports",
    "simulation_control": "SimulationControl",
    "run_period": "RunPeriod",
    "building": "Building",
    "global_geometry_rules": "GlobalGeometryRules",
    "site_location": "Site:Location",
    "sizing_parameters": "Sizing:Parameters",
    "timestep": "Timestep",
    "version": "Version",
    "window_material_simple": "WindowMaterial:SimpleGlazingSystem",
    "window_material_glazing": "WindowMaterial:Glazing",
    "window_material_gas": "WindowMaterial:Gas",
    "construction_window": "Construction",
}

# Inverse mapping
_IDF_TO_PYTHON = {v.upper(): k for k, v in _PYTHON_TO_IDF.items()}


class IDFDocument:
    """
    Main container for an EnergyPlus model.

    Attributes:
        version: The EnergyPlus version tuple (major, minor, patch)
        filepath: Path to the source file (if loaded from file)
        _collections: Dict of object_type -> IDFCollection
        _schema: EpJSONSchema for validation and field info
        _references: ReferenceGraph for dependency tracking
    """

    __slots__ = (
        "version",
        "filepath",
        "_collections",
        "_schema",
        "_references",
        "_schedules_cache",
    )

    def __init__(
        self,
        version: tuple[int, int, int] | None = None,
        schema: "EpJSONSchema | None" = None,
        filepath: Path | str | None = None,
    ):
        """
        Initialize an IDFDocument.

        Args:
            version: EnergyPlus version tuple
            schema: EpJSONSchema for validation
            filepath: Source file path
        """
        self.version = version or (23, 2, 0)
        self.filepath = Path(filepath) if filepath else None
        self._schema = schema
        self._collections: dict[str, IDFCollection] = {}
        self._references = ReferenceGraph()
        self._schedules_cache: dict[str, IDFObject] | None = None

    # -------------------------------------------------------------------------
    # Collection Access
    # -------------------------------------------------------------------------

    def __getitem__(self, obj_type: str) -> IDFCollection:
        """
        Get collection by object type name.

        Examples:
            doc["Zone"]
            doc["BuildingSurface:Detailed"]
        """
        key = obj_type
        if key not in self._collections:
            self._collections[key] = IDFCollection(obj_type)
        return self._collections[key]

    def __getattr__(self, name: str) -> IDFCollection:
        """
        Get collection by Python-style attribute name.

        Examples:
            doc.zones  # -> Zone collection
            doc.building_surfaces  # -> BuildingSurface:Detailed collection
        """
        if name.startswith("_"):
            raise AttributeError(name)

        # Check the mapping
        obj_type = _PYTHON_TO_IDF.get(name)
        if obj_type:
            return self[obj_type]

        # Try as-is with different cases
        for key in self._collections:
            if key.lower().replace(":", "_").replace(" ", "_") == name.lower():
                return self._collections[key]

        # Return empty collection for unknown types
        return self[name]

    def __contains__(self, obj_type: str) -> bool:
        """Check if document has objects of a type."""
        return obj_type in self._collections and len(self._collections[obj_type]) > 0

    def __iter__(self) -> Iterator[str]:
        """Iterate over object type names."""
        return iter(self._collections)

    def __len__(self) -> int:
        """Return total number of objects."""
        return sum(len(c) for c in self._collections.values())

    # -------------------------------------------------------------------------
    # Object Access (eppy compatibility)
    # -------------------------------------------------------------------------

    @property
    def idfobjects(self) -> dict[str, IDFCollection]:
        """
        Dict-like access to all object collections (eppy compatibility).

        Returns a view that allows access like idf.idfobjects["ZONE"]
        """
        return _IDFObjectsView(self)

    def getobject(self, obj_type: str, name: str) -> IDFObject | None:
        """
        Get a specific object by type and name.

        Args:
            obj_type: Object type (e.g., "Zone")
            name: Object name

        Returns:
            IDFObject or None if not found
        """
        collection = self._collections.get(obj_type)
        if collection:
            return collection.get(name)
        return None

    def getiddgroupdict(self) -> dict[str, list[str]]:
        """Get dict of object groups (eppy compatibility)."""
        # This would require IDD group info from schema
        # For now, return a simplified version
        groups: dict[str, list[str]] = {}
        for obj_type in self._collections:
            # Simple grouping by first part of name
            parts = obj_type.split(":")
            group = parts[0] if len(parts) > 1 else "Miscellaneous"
            if group not in groups:
                groups[group] = []
            groups[group].append(obj_type)
        return groups

    # -------------------------------------------------------------------------
    # Object Manipulation
    # -------------------------------------------------------------------------

    def add(
        self,
        obj_type: str,
        name: str,
        data: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> IDFObject:
        """
        Add a new object to the document.

        Args:
            obj_type: Object type (e.g., "Zone")
            name: Object name
            data: Field data as dict
            **kwargs: Additional field values

        Returns:
            The created IDFObject
        """
        # Merge data and kwargs
        field_data = dict(data) if data else {}
        field_data.update(kwargs)

        # Get schema info
        obj_schema = None
        field_order = None
        if self._schema:
            obj_schema = self._schema.get_object_schema(obj_type)
            field_order = self._schema.get_field_names(obj_type)

        # Create object
        obj = IDFObject(
            obj_type=obj_type,
            name=name,
            data=field_data,
            schema=obj_schema,
            document=self,
            field_order=field_order,
        )

        # Add to collection
        self[obj_type].add(obj)

        # Index references
        self._index_object_references(obj)

        # Invalidate schedules cache
        if obj_type.upper().startswith("SCHEDULE"):
            self._schedules_cache = None

        return obj

    def newidfobject(self, obj_type: str, **kwargs: Any) -> IDFObject:
        """
        Create a new object (eppy compatibility).

        The 'Name' kwarg becomes the object name if provided.
        """
        name = kwargs.pop("Name", kwargs.pop("name", ""))
        return self.add(obj_type, name, **kwargs)

    def addidfobject(self, obj: IDFObject) -> IDFObject:
        """Add an existing IDFObject to the document."""
        # Set document reference
        object.__setattr__(obj, "_document", self)

        # Add to collection
        self[obj._type].add(obj)

        # Index references
        self._index_object_references(obj)

        return obj

    def addidfobjects(self, objects: list[IDFObject]) -> list[IDFObject]:
        """Add multiple objects to the document."""
        return [self.addidfobject(obj) for obj in objects]

    def removeidfobject(self, obj: IDFObject) -> None:
        """Remove an object from the document."""
        obj_type = obj._type

        if obj_type in self._collections:
            self._collections[obj_type].remove(obj)

        # Remove from reference graph
        self._references.unregister(obj)

        # Invalidate caches
        if obj_type.upper().startswith("SCHEDULE"):
            self._schedules_cache = None

    def removeidfobjects(self, objects: list[IDFObject]) -> None:
        """Remove multiple objects from the document."""
        for obj in objects:
            self.removeidfobject(obj)

    def copyidfobject(self, obj: IDFObject, new_name: str | None = None) -> IDFObject:
        """Create a copy of an object with optional new name."""
        new_obj = obj.copy()
        if new_name:
            new_obj.name = new_name
        return self.addidfobject(new_obj)

    def rename(self, obj_type: str, old_name: str, new_name: str) -> None:
        """
        Rename an object and update all references.

        Args:
            obj_type: Object type
            old_name: Current name
            new_name: New name
        """
        obj = self.getobject(obj_type, old_name)
        if not obj:
            raise KeyError(f"No {obj_type} named '{old_name}'")

        # Update all objects that reference this one
        referencing = self._references.get_referencing_with_fields(old_name)
        for ref_obj, field_name in referencing:
            if getattr(ref_obj, field_name, "").upper() == old_name.upper():
                setattr(ref_obj, field_name, new_name)

        # Update the name index in the collection
        collection = self._collections[obj_type]
        old_key = old_name.upper()
        if old_key in collection._by_name:
            del collection._by_name[old_key]
        collection._by_name[new_name.upper()] = obj

        # Update the object itself
        obj.name = new_name

    # -------------------------------------------------------------------------
    # Reference Graph
    # -------------------------------------------------------------------------

    def _index_object_references(self, obj: IDFObject) -> None:
        """Index all references in an object."""
        if not self._schema:
            return

        obj_type = obj._type
        for field_name in self._schema.get_field_names(obj_type):
            if self._schema.is_reference_field(obj_type, field_name):
                value = obj._data.get(field_name)
                if value and isinstance(value, str):
                    self._references.register(obj, field_name, value)

    def get_referencing(self, name: str) -> set[IDFObject]:
        """Get all objects that reference a given name."""
        return self._references.get_referencing(name)

    def get_references(self, obj: IDFObject) -> set[str]:
        """Get all names that an object references."""
        return self._references.get_references(obj)

    # -------------------------------------------------------------------------
    # Schedules (common access pattern)
    # -------------------------------------------------------------------------

    @property
    def schedules_dict(self) -> dict[str, IDFObject]:
        """
        Get dict mapping schedule names to schedule objects.

        This is a cached property for fast schedule lookup.
        """
        if self._schedules_cache is None:
            self._schedules_cache = self._build_schedules_dict()
        return self._schedules_cache

    def _build_schedules_dict(self) -> dict[str, IDFObject]:
        """Build the schedules lookup dict."""
        schedules: dict[str, IDFObject] = {}
        schedule_types = [
            "Schedule:Year",
            "Schedule:Compact",
            "Schedule:File",
            "Schedule:Constant",
            "Schedule:Day:Hourly",
            "Schedule:Day:Interval",
            "Schedule:Day:List",
            "Schedule:Week:Daily",
            "Schedule:Week:Compact",
        ]

        for sched_type in schedule_types:
            if sched_type in self._collections:
                for sched in self._collections[sched_type]:
                    if sched.name:
                        schedules[sched.name.upper()] = sched

        return schedules

    def get_schedule(self, name: str) -> IDFObject | None:
        """Get a schedule by name (case-insensitive)."""
        return self.schedules_dict.get(name.upper())

    def get_used_schedules(self) -> set[str]:
        """
        Get names of schedules actually used in the model.

        Uses the reference graph for O(1) lookup per schedule.
        """
        used = set()
        for name in self.schedules_dict:
            if self._references.is_referenced(name):
                used.add(name)
        return used

    # -------------------------------------------------------------------------
    # Surfaces (common access pattern)
    # -------------------------------------------------------------------------

    def getsurfaces(self, surface_type: str | None = None) -> list[IDFObject]:
        """
        Get building surfaces, optionally filtered by type.

        Args:
            surface_type: Filter by surface type ("wall", "floor", "roof", "ceiling")

        Returns:
            List of surface objects
        """
        surfaces = list(self["BuildingSurface:Detailed"])

        if surface_type:
            surface_type_upper = surface_type.upper()
            surfaces = [
                s
                for s in surfaces
                if getattr(s, "surface_type", "").upper() == surface_type_upper
            ]

        return surfaces

    def get_zone_surfaces(self, zone_name: str) -> list[IDFObject]:
        """Get all surfaces belonging to a zone."""
        return list(self._references.get_referencing(zone_name))

    # -------------------------------------------------------------------------
    # Iteration
    # -------------------------------------------------------------------------

    @property
    def all_objects(self) -> Iterator[IDFObject]:
        """Iterate over all objects in the document."""
        for collection in self._collections.values():
            yield from collection

    def objects_by_type(self) -> Iterator[tuple[str, IDFCollection]]:
        """Iterate over (type, collection) pairs."""
        for obj_type, collection in self._collections.items():
            if collection:
                yield obj_type, collection

    # -------------------------------------------------------------------------
    # Copying
    # -------------------------------------------------------------------------

    def copy(self) -> "IDFDocument":
        """Create a deep copy of the document."""
        new_doc = IDFDocument(
            version=self.version,
            schema=self._schema,
            filepath=self.filepath,
        )

        for obj in self.all_objects:
            new_obj = obj.copy()
            new_doc.addidfobject(new_obj)

        return new_doc

    # -------------------------------------------------------------------------
    # String Representation
    # -------------------------------------------------------------------------

    def __repr__(self) -> str:
        version_str = f"{self.version[0]}.{self.version[1]}.{self.version[2]}"
        return f"IDFDocument(version={version_str}, objects={len(self)})"

    def __str__(self) -> str:
        lines = [repr(self), ""]
        for obj_type, collection in sorted(self._collections.items()):
            if collection:
                lines.append(f"  {obj_type}: {len(collection)} objects")
        return "\n".join(lines)


class _IDFObjectsView:
    """
    Dict-like view for idfobjects access (eppy compatibility).

    Allows: idf.idfobjects["ZONE"], idf.idfobjects["Zone"], etc.
    """

    __slots__ = ("_doc",)

    def __init__(self, doc: IDFDocument):
        self._doc = doc

    def __getitem__(self, key: str) -> IDFCollection:
        # Try exact match first
        if key in self._doc._collections:
            return self._doc._collections[key]

        # Try case-insensitive match
        key_upper = key.upper()
        for obj_type in self._doc._collections:
            if obj_type.upper() == key_upper:
                return self._doc._collections[obj_type]

        # Return empty collection
        return self._doc[key]

    def __contains__(self, key: str) -> bool:
        key_upper = key.upper()
        for obj_type in self._doc._collections:
            if obj_type.upper() == key_upper:
                return len(self._doc._collections[obj_type]) > 0
        return False

    def __iter__(self) -> Iterator[str]:
        return iter(self._doc._collections)

    def keys(self) -> list[str]:
        return list(self._doc._collections.keys())

    def values(self) -> list[IDFCollection]:
        return list(self._doc._collections.values())

    def items(self) -> list[tuple[str, IDFCollection]]:
        return list(self._doc._collections.items())
