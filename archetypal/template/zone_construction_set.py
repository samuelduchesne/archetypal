"""archetypal ZoneConstructionSet."""

import collections
import logging as lg
from typing import TYPE_CHECKING, ClassVar

from validator_collection import validators

from archetypal.template.constructions.opaque_construction import OpaqueConstruction
from archetypal.template.umi_base import UmiBase
from archetypal.utils import log, reduce, timeit

if TYPE_CHECKING:
    from archetypal.template import ZoneDefinition


class ZoneConstructionSet(UmiBase):
    """ZoneConstructionSet class."""

    _CREATED_OBJECTS: ClassVar[list["ZoneConstructionSet"]] = []

    __slots__ = (
        "_facade",
        "_ground",
        "_partition",
        "_roof",
        "_slab",
        "_is_facade_adiabatic",
        "_is_ground_adiabatic",
        "_is_partition_adiabatic",
        "_is_roof_adiabatic",
        "_is_slab_adiabatic",
        "_area",
        "_volume",
    )

    def __init__(
        self,
        Name,
        Facade=None,
        Ground=None,
        Partition=None,
        Roof=None,
        Slab=None,
        IsFacadeAdiabatic=False,
        IsGroundAdiabatic=False,
        IsPartitionAdiabatic=False,
        IsRoofAdiabatic=False,
        IsSlabAdiabatic=False,
        area=1,
        volume=1,
        **kwargs,
    ):
        """Create a ZoneConstructionSet object.

        Args:
            Name (str): Name of the object. Must be Unique.
            Facade (OpaqueConstruction): The OpaqueConstruction object representing
                a facade.
            Ground (OpaqueConstruction): The OpaqueConstruction object representing
                a ground floor.
            Partition (OpaqueConstruction): The OpaqueConstruction object representing
                a partition wall.
            Roof (OpaqueConstruction): The OpaqueConstruction object representing
                a roof.
            Slab (OpaqueConstruction): The OpaqueConstruction object representing
                a slab.
            IsFacadeAdiabatic (bool): If True, surface is adiabatic.
            IsGroundAdiabatic (bool): If True, surface is adiabatic.
            IsPartitionAdiabatic (bool): If True, surface is adiabatic.
            IsRoofAdiabatic (bool): If True, surface is adiabatic.
            IsSlabAdiabatic (bool): If True, surface is adiabatic.
            **kwargs:
        """
        super().__init__(Name, **kwargs)
        self.Slab = Slab
        self.IsSlabAdiabatic = IsSlabAdiabatic
        self.Roof = Roof
        self.IsRoofAdiabatic = IsRoofAdiabatic
        self.Partition = Partition
        self.IsPartitionAdiabatic = IsPartitionAdiabatic
        self.Ground = Ground
        self.IsGroundAdiabatic = IsGroundAdiabatic
        self.Facade = Facade
        self.IsFacadeAdiabatic = IsFacadeAdiabatic
        self.area = area
        self.volume = volume

        # Only at the end append self to _CREATED_OBJECTS
        self._CREATED_OBJECTS.append(self)

    @property
    def Facade(self):
        """Get or set the Facade OpaqueConstruction."""
        return self._facade

    @Facade.setter
    def Facade(self, value):
        if value is not None:
            assert isinstance(value, OpaqueConstruction), (
                f"Input value error for {value}. Facade must be" f" an OpaqueConstruction, not a {type(value)}"
            )
        self._facade = value

    @property
    def Ground(self):
        """Get or set the Ground OpaqueConstruction."""
        return self._ground

    @Ground.setter
    def Ground(self, value):
        if value is not None:
            assert isinstance(value, OpaqueConstruction), (
                f"Input value error for {value}. Ground must be" f" an OpaqueConstruction, not a {type(value)}"
            )
        self._ground = value

    @property
    def Partition(self):
        """Get or set the Partition OpaqueConstruction."""
        return self._partition

    @Partition.setter
    def Partition(self, value):
        if value is not None:
            assert isinstance(value, OpaqueConstruction), (
                f"Input value error for {value}. Partition must be" f" an OpaqueConstruction, not a {type(value)}"
            )
        self._partition = value

    @property
    def Roof(self):
        """Get or set the Roof OpaqueConstruction."""
        return self._roof

    @Roof.setter
    def Roof(self, value):
        if value is not None:
            assert isinstance(value, OpaqueConstruction), (
                f"Input value error for {value}. Roof must be" f" an OpaqueConstruction, not a {type(value)}"
            )
        self._roof = value

    @property
    def Slab(self):
        """Get or set the Slab OpaqueConstruction."""
        return self._slab

    @Slab.setter
    def Slab(self, value):
        if value is not None:
            assert isinstance(value, OpaqueConstruction), (
                f"Input value error for {value}. Slab must be" f" an OpaqueConstruction, not a {type(value)}"
            )
        self._slab = value

    @property
    def IsFacadeAdiabatic(self):
        """Get or set is facade adiabatic [bool]."""
        return self._is_facade_adiabatic

    @IsFacadeAdiabatic.setter
    def IsFacadeAdiabatic(self, value):
        assert isinstance(value, bool), (
            f"Input value error for {value}. " f"IsFacadeAdiabatic must be of type bool, " f"not {type(value)}."
        )
        self._is_facade_adiabatic = value

    @property
    def IsGroundAdiabatic(self):
        """Get or set is ground adiabatic [bool]."""
        return self._is_ground_adiabatic

    @IsGroundAdiabatic.setter
    def IsGroundAdiabatic(self, value):
        assert isinstance(value, bool), (
            f"Input value error for {value}. " f"IsGroundAdiabatic must be of type bool, " f"not {type(value)}."
        )
        self._is_ground_adiabatic = value

    @property
    def IsPartitionAdiabatic(self):
        """Get or set is partition adiabatic [bool]."""
        return self._is_partition_adiabatic

    @IsPartitionAdiabatic.setter
    def IsPartitionAdiabatic(self, value):
        assert isinstance(value, bool), (
            f"Input value error for {value}. " f"IsPartitionAdiabatic must be of type bool, " f"not {type(value)}."
        )
        self._is_partition_adiabatic = value

    @property
    def IsRoofAdiabatic(self):
        """Get or set is roof adiabatic [bool]."""
        return self._is_roof_adiabatic

    @IsRoofAdiabatic.setter
    def IsRoofAdiabatic(self, value):
        assert isinstance(value, bool), (
            f"Input value error for {value}. " f"IsRoofAdiabatic must be of type bool, " f"not {type(value)}."
        )
        self._is_roof_adiabatic = value

    @property
    def IsSlabAdiabatic(self):
        """Get or set is slab adiabatic [bool]."""
        return self._is_slab_adiabatic

    @IsSlabAdiabatic.setter
    def IsSlabAdiabatic(self, value):
        assert isinstance(value, bool), (
            f"Input value error for {value}. " f"IsSlabAdiabatic must be of type bool, " f"not {type(value)}."
        )
        self._is_slab_adiabatic = value

    @property
    def area(self):
        """Get or set the area of the zone [m²]."""
        return self._area

    @area.setter
    def area(self, value):
        self._area = validators.float(value, minimum=0)

    @property
    def volume(self):
        """Get or set the volume of the zone [m³]."""
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = validators.float(value, minimum=0)

    @classmethod
    @timeit
    def from_zone(cls, zone: "ZoneDefinition", **kwargs):
        """Create a ZoneConstructionSet from a ZoneDefinition object.

        Args:
            zone (ZoneDefinition): The zone object.
        """
        name = zone.Name + "_ZoneConstructionSet"
        # dispatch surfaces
        facade, ground, partition, roof, slab = [], [], [], [], []
        zonesurfaces = zone.zone_surfaces
        for surf in zonesurfaces:
            disp_surf = SurfaceDispatcher(surf, zone).resolved_surface
            if disp_surf:
                if disp_surf.Category == "Facade":
                    if zone.is_part_of_conditioned_floor_area:
                        facade.append(disp_surf)
                elif disp_surf.Category == "Ground":
                    ground.append(disp_surf)
                elif disp_surf.Category == "Partition":
                    partition.append(disp_surf)
                elif disp_surf.Category == "Roof":
                    roof.append(disp_surf)
                elif disp_surf.Category == "Slab":
                    slab.append(disp_surf)
                else:
                    msg = f'Surface Type "{disp_surf.Surface_Type}" is not known, this method is not' " implemented"
                    raise NotImplementedError(msg)

        # Returning a set() for each groups of Constructions.

        facades = set(facade)
        facade = reduce(OpaqueConstruction.combine, facades) if facades else None
        grounds = set(ground)
        ground = reduce(OpaqueConstruction.combine, grounds) if grounds else None
        partitions = set(partition)
        partition = reduce(OpaqueConstruction.combine, partitions) if partitions else None
        roofs = set(roof)
        roof = reduce(OpaqueConstruction.combine, roofs) if roofs else None
        slabs = set(slab)
        slab = reduce(OpaqueConstruction.combine, slabs) if slabs else None

        z_set = cls(
            Facade=facade,
            Ground=ground,
            Partition=partition,
            Roof=roof,
            Slab=slab,
            Name=name,
            zone=zone,
            Category=zone.DataSource,
            **kwargs,
        )
        return z_set

    @classmethod
    def from_dict(cls, data, opaque_constructions, **kwargs):
        """Create a ZoneConstructionSet from a dictionary.

        Args:
            data (dict): The python dictionary.
            opaque_constructions (dict): A dictionary of OpaqueConstruction with their
                id as keys.
            **kwargs: keywords passed parent constructor.

        .. code-block:: python

            {
              "$id": "168",
              "Facade": {
                "$ref": "35"
              },
              "Ground": {
                "$ref": "42"
              },
              "Partition": {
                "$ref": "48"
              },
              "Roof": {
                "$ref": "39"
              },
              "Slab": {
                "$ref": "45"
              },
              "IsFacadeAdiabatic": false,
              "IsGroundAdiabatic": false,
              "IsPartitionAdiabatic": false,
              "IsRoofAdiabatic": false,
              "IsSlabAdiabatic": false,
              "Category": "Office Spaces",
              "Comments": null,
              "DataSource": "MIT_SDL",
              "Name": "B_Off_0 constructions"
            }
        """
        _id = data.pop("$id")
        facade = opaque_constructions[data.pop("Facade")["$ref"]]
        ground = opaque_constructions[data.pop("Ground")["$ref"]]
        partition = opaque_constructions[data.pop("Partition")["$ref"]]
        roof = opaque_constructions[data.pop("Roof")["$ref"]]
        slab = opaque_constructions[data.pop("Slab")["$ref"]]
        return cls(
            id=_id,
            Facade=facade,
            Ground=ground,
            Partition=partition,
            Roof=roof,
            Slab=slab,
            **data,
            **kwargs,
        )

    def combine(self, other, weights=None, **kwargs):
        """Combine two ZoneConstructionSet objects together.

        Args:
            other (ZoneConstructionSet):
            kwargs: keywords passed to constructor.

        Returns:
            (ZoneConstructionSet): the combined ZoneConstructionSet object.
        """
        # Check if other is None. Simply return self
        if not self and not other:
            return None
        elif self == other:
            area = 1 if self.area + other.area == 2 else self.area + other.area
            volume = 1 if self.volume + other.volume == 2 else self.volume + other.volume
            new_obj = self.duplicate()
            new_obj.area = area
            new_obj.volume = volume
            return new_obj
        elif not self or not other:
            new_obj = (self or other).duplicate()
            return new_obj

        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = f"Cannot combine {self.__class__.__name__} with {other.__class__.__name__}"
            raise NotImplementedError(msg)

        meta = self._get_predecessors_meta(other)

        # create a new object with the combined attributes
        new_obj = self.__class__(
            Slab=OpaqueConstruction.combine(self.Slab, other.Slab),
            IsSlabAdiabatic=any([self.IsSlabAdiabatic, other.IsSlabAdiabatic]),
            Roof=OpaqueConstruction.combine(self.Roof, other.Roof),
            IsRoofAdiabatic=any([self.IsRoofAdiabatic, other.IsRoofAdiabatic]),
            Partition=OpaqueConstruction.combine(self.Partition, other.Partition),
            IsPartitionAdiabatic=any([self.IsPartitionAdiabatic, other.IsPartitionAdiabatic]),
            Ground=OpaqueConstruction.combine(self.Ground, other.Ground),
            IsGroundAdiabatic=any([self.IsGroundAdiabatic, other.IsGroundAdiabatic]),
            Facade=OpaqueConstruction.combine(self.Facade, other.Facade),
            IsFacadeAdiabatic=any([self.IsFacadeAdiabatic, other.IsFacadeAdiabatic]),
            area=1 if self.area + other.area == 2 else self.area + other.area,
            volume=1 if self.volume + other.volume == 2 else self.volume + other.volume,
            **meta,
            **kwargs,
            allow_duplicates=self.allow_duplicates,
        )
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def to_dict(self):
        """Return ZoneConstructionSet dictionary representation."""
        self.validate()
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Facade"] = {"$ref": str(self.Facade.id)}
        data_dict["Ground"] = {"$ref": str(self.Ground.id)}
        data_dict["Partition"] = {"$ref": str(self.Partition.id)}
        data_dict["Roof"] = {"$ref": str(self.Roof.id)}
        data_dict["Slab"] = {"$ref": str(self.Slab.id)}
        data_dict["IsFacadeAdiabatic"] = self.IsFacadeAdiabatic
        data_dict["IsGroundAdiabatic"] = self.IsGroundAdiabatic
        data_dict["IsPartitionAdiabatic"] = self.IsPartitionAdiabatic
        data_dict["IsRoofAdiabatic"] = self.IsRoofAdiabatic
        data_dict["IsSlabAdiabatic"] = self.IsSlabAdiabatic
        data_dict["Category"] = self.Category
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def validate(self):
        """Validate object and fill in missing values."""
        for attr in ["Slab", "Roof", "Partition", "Ground", "Facade"]:
            if getattr(self, attr) is None:
                # First try to get one from another zone that has the attr
                zone = next(
                    iter(
                        filter(
                            lambda x: getattr(x, attr, None) is not None,
                            ZoneConstructionSet._CREATED_OBJECTS,
                        )
                    ),
                    None,
                )
                if zone:
                    setattr(self, attr, getattr(zone, attr))
                else:
                    # If not, default to a generic construction for last resort.
                    setattr(self, attr, OpaqueConstruction.generic())
                log(
                    f"While validating {self}, the required attribute "
                    f"'{attr}' was filled "
                    f"with {getattr(self, attr)}",
                    lg.DEBUG,
                )
        return self

    def mapping(self, validate=False):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
            self.validate()

        return {
            "Facade": self.Facade,
            "Ground": self.Ground,
            "Partition": self.Partition,
            "Roof": self.Roof,
            "Slab": self.Slab,
            "IsFacadeAdiabatic": self.IsFacadeAdiabatic,
            "IsGroundAdiabatic": self.IsGroundAdiabatic,
            "IsPartitionAdiabatic": self.IsPartitionAdiabatic,
            "IsRoofAdiabatic": self.IsRoofAdiabatic,
            "IsSlabAdiabatic": self.IsSlabAdiabatic,
            "Category": self.Category,
            "Comments": self.Comments,
            "DataSource": self.DataSource,
            "Name": self.Name,
        }

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

    def __key__(self):
        """Get a tuple of attributes. Useful for hashing and comparing."""
        return (
            self.Slab,
            self.IsSlabAdiabatic,
            self.Roof,
            self.IsRoofAdiabatic,
            self.Partition,
            self.IsPartitionAdiabatic,
            self.Ground,
            self.IsGroundAdiabatic,
            self.Facade,
            self.IsFacadeAdiabatic,
        )

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other:
        """
        return self.combine(other)

    def __hash__(self):
        """Return the hash value of self."""
        return hash(self.id)

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, ZoneConstructionSet):
            return NotImplemented
        else:
            return self.__key__() == other.__key__()

    def __copy__(self):
        """Get copy of self."""
        return self.__class__(**self.mapping(validate=False))

    @property
    def children(self):
        return self.Facade, self.Ground, self.Partition, self.Roof, self.Slab


class SurfaceDispatcher:
    """Surface dispatcher class."""

    __slots__ = ("surf", "zone", "_dispatch")

    def __init__(self, surf, zone):
        """Initialize a surface dispatcher object."""
        self.surf = surf
        self.zone = zone

        # dispatch map
        self._dispatch = {
            ("Wall", "Outdoors"): self._do_facade,
            ("Floor", "Ground"): self._do_ground,
            ("Floor", "Outdoors"): self._do_ground,
            ("Floor", "Foundation"): self._do_ground,
            ("Floor", "OtherSideCoefficients"): self._do_ground,
            ("Floor", "GroundSlabPreprocessorAverage"): self._do_ground,
            ("Floor", "Surface"): self._do_slab,
            ("Floor", "Adiabatic"): self._do_slab,
            ("Floor", "Zone"): self._do_slab,
            ("Wall", "Adiabatic"): self._do_partition,
            ("Wall", "Surface"): self._do_partition,
            ("Wall", "Zone"): self._do_partition,
            ("Wall", "Ground"): self._do_basement,
            ("Wall", "GroundFCfactorMethod"): self._do_basement,
            ("Roof", "Outdoors"): self._do_roof,
            ("Roof", "Zone"): self._do_roof,
            ("Roof", "Surface"): self._do_roof,
            ("Ceiling", "Adiabatic"): self._do_slab,
            ("Ceiling", "Surface"): self._do_slab,
            ("Ceiling", "Zone"): self._do_slab,
        }

    @property
    def resolved_surface(self):
        """Generate a resolved surface. Yields value."""
        if self.surf.key.upper() not in ["INTERNALMASS", "WINDOWSHADINGCONTROL"]:
            a, b = (
                self.surf["Surface_Type"].capitalize(),
                self.surf["Outside_Boundary_Condition"],
            )
            try:
                return self._dispatch[a, b](self.surf)
            except KeyError as e:
                raise NotImplementedError(
                    f"surface '{self.surf.Name}' in zone '{self.zone.Name}' not supported by surface dispatcher "
                    f"with keys {e}"
                ) from e

    @staticmethod
    def _do_facade(surf):
        log(
            f'surface "{surf.Name}" assigned as a Facade',
            lg.DEBUG,
            name=surf.theidf.name,
        )
        oc = OpaqueConstruction.from_epbunch(surf.theidf.getobject("Construction".upper(), surf.Construction_Name))
        oc.area = surf.area
        oc.Category = "Facade"
        return oc

    @staticmethod
    def _do_ground(surf):
        log(
            f'surface "{surf.Name}" assigned as a Ground',
            lg.DEBUG,
            name=surf.theidf.name,
        )
        oc = OpaqueConstruction.from_epbunch(surf.get_referenced_object("Construction_Name"))
        oc.area = surf.area
        oc.Category = "Ground"
        return oc

    @staticmethod
    def _do_partition(surf):
        the_construction = surf.theidf.getobject("Construction".upper(), surf.Construction_Name)
        if the_construction:
            oc = OpaqueConstruction.from_epbunch(the_construction)
            oc.area = surf.area
            oc.Category = "Partition"
            log(
                f'surface "{surf.Name}" assigned as a Partition',
                lg.DEBUG,
                name=surf.theidf.name,
            )
            return oc
        else:
            # we might be in a situation where the construction does not exist in the
            # file. For example, this can happen when the construction is defined as
            # "Air Wall", which is a construction type internal to EnergyPlus.
            return None

    @staticmethod
    def _do_roof(surf):
        log(
            f'surface "{surf.Name}" assigned as a Roof',
            lg.DEBUG,
            name=surf.theidf.name,
        )
        oc = OpaqueConstruction.from_epbunch(surf.theidf.getobject("Construction".upper(), surf.Construction_Name))
        oc.area = surf.area
        oc.Category = "Roof"
        return oc

    @staticmethod
    def _do_slab(surf):
        log(
            f'surface "{surf.Name}" assigned as a Slab',
            lg.DEBUG,
            name=surf.theidf.name,
        )
        oc = OpaqueConstruction.from_epbunch(surf.theidf.getobject("Construction".upper(), surf.Construction_Name))
        oc.area = surf.area
        oc.Category = "Slab"
        return oc

    @staticmethod
    def _do_basement(surf):
        log(
            f'surface "{surf.Name}" ignored because basement facades are not supported',
            lg.WARNING,
            name=surf.theidf.name,
        )
        oc = None
        return oc
