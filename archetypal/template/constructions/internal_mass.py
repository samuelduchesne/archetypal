import functools
from operator import add

from validator_collection import validators

from archetypal.template.constructions.opaque_construction import OpaqueConstruction


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
        self._surface_name = validators.string(
            value, minimum_length=1, maximum_length=100
        )

    @property
    def construction(self) -> OpaqueConstruction:
        """Get or set the construction."""
        return self._construction

    @construction.setter
    def construction(self, value):
        assert isinstance(value, OpaqueConstruction), (
            f"Input value error for {value}. construction must be of type "
            f"{OpaqueConstruction}, not {type(value)}."
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
    def from_zone(cls, zone_epbunch):
        """Create InternalMass from ZoneDefinition and Zone EpBunch.

        Args:
            zone_epbunch (EpBunch): The Zone EpBunch object.

        Returns:
            Construction: The internal mass construction for the zone
            None: if no internal mass defined for zone.
        """
        internal_mass_objs = zone_epbunch.getreferingobjs(
            iddgroups=["Thermal Zones and Surfaces"], fields=["Zone_or_ZoneList_Name"]
        )

        area = 0  # initialize area
        mass_opaque_constructions = []  # collect internal mass objects

        # Looping over possible InternalMass objects
        # This InternalMass object (int_obj) is assigned to self,
        # then create object and append to list. There could be more then
        # one.
        for int_obj in internal_mass_objs:
            if int_obj.key.upper() == "INTERNALMASS":
                mass_opaque_constructions.append(
                    OpaqueConstruction.from_epbunch(int_obj, Category="Internal Mass")
                )
                area += float(int_obj.Surface_Area)

        # If one or more constructions, combine them into one.
        if mass_opaque_constructions:
            # Combine elements and assign the aggregated Surface Area
            construction = functools.reduce(add, mass_opaque_constructions)
        else:
            # No InternalMass object assigned to this Zone, then return Zone and set
            # floor area to 0
            return cls.generic_internalmass_from_zone(zone_epbunch)
        return cls(f"{zone_epbunch.Name} InternalMass", construction, area)

    @classmethod
    def generic_internalmass_from_zone(cls, zone_epbunch):
        """Create an InternalMass object with generic construction and 0 floor area.

        Args:
            zone_epbunch (EpBunch): A ZoneDefinition object.
        """
        construction = OpaqueConstruction.generic_internalmass()
        return cls(
            surface_name=f"{zone_epbunch.Name} InternalMass",
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

    def to_epbunch(self, idf, zone_name):
        """Create an `INTERNALMASS` EpBunch given an idf model and a zone name.

        Args:
            idf (IDF): An idf model to add the EpBunch in.
            zone_name (str): The name of the zone for this InternamMass object.

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        construction = self.construction.to_epbunch(idf)
        internal_mass = idf.newidfobject(
            key="INTERNALMASS",
            Name=self.surface_name,
            Construction_Name=construction.Name,
            Zone_or_ZoneList_Name=zone_name,
            Surface_Area=self.total_area_exposed_to_zone,
        )
        return internal_mass

    def __copy__(self):
        """Get a copy of self."""
        return self.__class__(**self.mapping())

    def __eq__(self, other):
        """Assert self equals to other."""
        return isinstance(other, InternalMass) and self.__key__() == other.__key__()

    def __key__(self):
        """Get a tuple of attributes. Useful for hashing and comparing."""
        return tuple(self.mapping().values())
