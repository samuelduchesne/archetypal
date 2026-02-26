import functools
from operator import add
from typing import TYPE_CHECKING

from validator_collection import validators

from archetypal.template.constructions.opaque_construction import OpaqueConstruction

if TYPE_CHECKING:
    import idfkit


class InternalMass:
    """InternalMass class."""

    def __init__(self, surface_name, construction, total_area_exposed_to_zone):
        """Create an InternalMass object."""
        self.surface_name = surface_name
        self.construction = construction
        self.total_area_exposed_to_zone = total_area_exposed_to_zone

    @property
    def surface_name(self):
        """Get or set the surface name [string]."""
        return self._surface_name

    @surface_name.setter
    def surface_name(self, value):
        self._surface_name = validators.string(value, minimum_length=1, maximum_length=100)

    @property
    def construction(self) -> OpaqueConstruction:
        """Get or set the construction."""
        return self._construction

    @construction.setter
    def construction(self, value):
        assert isinstance(value, OpaqueConstruction), (
            f"Input value error for {value}. construction must be of type " f"{OpaqueConstruction}, not {type(value)}."
        )
        self._construction = value

    @property
    def total_area_exposed_to_zone(self):
        """Get or set the total area exposed to Zone [m2]."""
        return self._total_area_exposed_to_zone

    @total_area_exposed_to_zone.setter
    def total_area_exposed_to_zone(self, value):
        self._total_area_exposed_to_zone = validators.float(value, minimum=0)

    @classmethod
    def from_zone(cls, zone_obj, doc: "idfkit.Document" = None):
        """Create InternalMass from a zone idfkit object.

        Args:
            zone_obj: The Zone idfkit object.
            doc (idfkit.Document): The idfkit Document for lookups.

        Returns:
            InternalMass: The internal mass construction for the zone.
        """
        zone_name = zone_obj.name if hasattr(zone_obj, "name") else str(zone_obj)

        # Find InternalMass objects assigned to this zone
        internal_mass_objs = []
        if doc is not None and "InternalMass" in doc:
            for obj in doc["InternalMass"].values():
                obj_zone = getattr(obj, "zone_or_zonelist_name", "")
                if obj_zone == zone_name:
                    internal_mass_objs.append(obj)

        area = 0  # initialize area
        mass_opaque_constructions = []  # collect internal mass objects

        for int_obj in internal_mass_objs:
            mass_opaque_constructions.append(
                OpaqueConstruction.from_idf_object(int_obj, doc=doc, Category="Internal Mass")
            )
            area += float(getattr(int_obj, "surface_area", 0))

        # If one or more constructions, combine them into one.
        if mass_opaque_constructions:
            construction = functools.reduce(add, mass_opaque_constructions)
        else:
            return cls.generic_internalmass_from_zone(zone_obj)
        return cls(f"{zone_name} InternalMass", construction, area)

    @classmethod
    def generic_internalmass_from_zone(cls, zone_obj):
        """Create an InternalMass object with generic construction and 0 floor area.

        Args:
            zone_obj: A zone idfkit object or ZoneDefinition.
        """
        zone_name = zone_obj.name if hasattr(zone_obj, "name") else getattr(zone_obj, "Name", str(zone_obj))
        construction = OpaqueConstruction.generic_internalmass()
        return cls(
            surface_name=f"{zone_name} InternalMass",
            total_area_exposed_to_zone=0,
            construction=construction,
        )

    def duplicate(self):
        """Get a copy of self."""
        return self.__copy__()

    def mapping(self):
        """Get a dict based on the object properties, useful for dict repr."""
        return {
            "surface_name": self.surface_name,
            "construction": self.construction,
            "total_area_exposed_to_zone": self.total_area_exposed_to_zone,
        }

    def __copy__(self):
        """Get a copy of self."""
        return self.__class__(**self.mapping())

    def __eq__(self, other):
        """Assert self equals to other."""
        return isinstance(other, InternalMass) and self.__key__() == other.__key__()

    def __key__(self):
        """Get a tuple of attributes. Useful for hashing and comparing."""
        return tuple(self.mapping().values())
