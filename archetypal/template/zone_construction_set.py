import collections
import logging as lg

from deprecation import deprecated

from archetypal import __version__, log, reduce, timeit
from archetypal.template import OpaqueConstruction, UmiBase, UniqueName


class ZoneConstructionSet(UmiBase):
    """Zone-specific :class:`Construction` ids"""

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
        **kwargs,
    ):
        """
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
        super(ZoneConstructionSet, self).__init__(Name, **kwargs)
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
        self._belongs_to_zone = kwargs.get("zone", None)

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other:
        """
        return self.combine(other)

    def __hash__(self):
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __eq__(self, other):
        if not isinstance(other, ZoneConstructionSet):
            return NotImplemented
        else:
            return all(
                [
                    self.Slab == other.Slab,
                    self.IsSlabAdiabatic == other.IsSlabAdiabatic,
                    self.Roof == other.Roof,
                    self.IsRoofAdiabatic == other.IsRoofAdiabatic,
                    self.Partition == other.Partition,
                    self.IsPartitionAdiabatic == other.IsPartitionAdiabatic,
                    self.Ground == other.Ground,
                    self.IsGroundAdiabatic == other.IsGroundAdiabatic,
                    self.Facade == other.Facade,
                    self.IsFacadeAdiabatic == other.IsFacadeAdiabatic,
                ]
            )

    @classmethod
    @timeit
    def from_zone(cls, zone, **kwargs):
        """
        Args:
            zone (ZoneDefinition):
        """
        name = zone.Name + "_ZoneConstructionSet"
        # dispatch surfaces
        facade, ground, partition, roof, slab = [], [], [], [], []
        zonesurfaces = zone._zonesurfaces
        for surf in zonesurfaces:
            for disp_surf in surface_dispatcher(surf, zone):
                if disp_surf:
                    if disp_surf.Surface_Type == "Facade":
                        if zone.is_part_of_conditioned_floor_area:
                            facade.append(disp_surf)
                    elif disp_surf.Surface_Type == "Ground":
                        ground.append(disp_surf)
                    elif disp_surf.Surface_Type == "Partition":
                        partition.append(disp_surf)
                    elif disp_surf.Surface_Type == "Roof":
                        roof.append(disp_surf)
                    elif disp_surf.Surface_Type == "Slab":
                        slab.append(disp_surf)
                    else:
                        msg = (
                            'Surface Type "{}" is not known, this method is not'
                            " implemented".format(disp_surf.Surface_Type)
                        )
                        raise NotImplementedError(msg)

        # Returning a set() for each groups of Constructions.

        facades = set(facade)
        if facades:
            facade = reduce(OpaqueConstruction.combine, facades)
        else:
            facade = None
        grounds = set(ground)
        if grounds:
            ground = reduce(OpaqueConstruction.combine, grounds)
        else:
            ground = None
        partitions = set(partition)
        if partitions:
            partition = reduce(OpaqueConstruction.combine, partitions)
        else:
            partition = None
        roofs = set(roof)
        if roofs:
            roof = reduce(OpaqueConstruction.combine, roofs)
        else:
            roof = None
        slabs = set(slab)
        if slabs:
            slab = reduce(OpaqueConstruction.combine, slabs)
        else:
            slab = None

        z_set = cls(
            Facade=facade,
            Ground=ground,
            Partition=partition,
            Roof=roof,
            Slab=slab,
            Name=name,
            zone=zone,
            idf=zone.idf,
            Category=zone.idf.name,
            **kwargs,
        )
        return z_set

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=__version__,
        details="Use from_dict function instead",
    )
    def from_json(cls, *args, **kwargs):
        return cls.from_dict(*args, **kwargs)

    @classmethod
    def from_dict(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        zc = cls(*args, **kwargs)

        ref = kwargs.get("Facade", None)
        zc.Facade = zc.get_ref(ref)

        ref = kwargs.get("Ground", None)
        zc.Ground = zc.get_ref(ref)

        ref = kwargs.get("Partition", None)
        zc.Partition = zc.get_ref(ref)

        ref = kwargs.get("Roof", None)
        zc.Roof = zc.get_ref(ref)

        ref = kwargs.get("Slab", None)
        zc.Slab = zc.get_ref(ref)

        return zc

    def combine(self, other, weights=None, **kwargs):
        """Append other to self. Return self + other as a new object.

        Args:
            other (ZoneConstructionSet):
            weights:

        Returns:
            (ZoneConstructionSet): the combined ZoneConstructionSet object.
        """
        # Check if other is None. Simply return self
        if not other:
            return self

        if not self:
            return other
        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = "Cannot combine %s with %s" % (
                self.__class__.__name__,
                other.__class__.__name__,
            )
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        if not weights:
            weights = [self._belongs_to_zone.volume, other._belongs_to_zone.volume]
            log(
                'using zone volume "{}" as weighting factor in "{}" '
                "combine.".format(
                    " & ".join(list(map(str, map(int, weights)))),
                    self.__class__.__name__,
                )
            )

        meta = self._get_predecessors_meta(other)
        new_attr = dict(
            Slab=OpaqueConstruction.combine(self.Slab, other.Slab),
            IsSlabAdiabatic=any([self.IsSlabAdiabatic, other.IsSlabAdiabatic]),
            Roof=OpaqueConstruction.combine(self.Roof, other.Roof),
            IsRoofAdiabatic=any([self.IsRoofAdiabatic, other.IsRoofAdiabatic]),
            Partition=OpaqueConstruction.combine(self.Partition, other.Partition),
            IsPartitionAdiabatic=any(
                [self.IsPartitionAdiabatic, other.IsPartitionAdiabatic]
            ),
            Ground=OpaqueConstruction.combine(self.Ground, other.Ground),
            IsGroundAdiabatic=any([self.IsGroundAdiabatic, other.IsGroundAdiabatic]),
            Facade=OpaqueConstruction.combine(self.Facade, other.Facade),
            IsFacadeAdiabatic=any([self.IsFacadeAdiabatic, other.IsFacadeAdiabatic]),
        )
        new_obj = self.__class__(**meta, **new_attr, idf=self.idf, **kwargs)
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def to_json(self):
        """Convert class properties to dict"""
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
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    def validate(self):
        for attr in ["Slab", "Roof", "Partition", "Ground", "Facade"]:
            if getattr(self, attr) is None:
                # First try to get one from another zone that has the attr
                zone = next(
                    iter(
                        filter(
                            lambda x: getattr(x, attr, None) is not None,
                            UmiBase.CREATED_OBJECTS,
                        )
                    ),
                    None,
                )
                if zone:
                    setattr(self, attr, getattr(zone, attr))
                else:
                    # If not, default to a generic construction for last resort.
                    setattr(self, attr, OpaqueConstruction.generic(idf=self.idf))
                log(
                    f"While validating {self}, the required attribute "
                    f"'{attr}' was filled "
                    f"with {getattr(self, attr)}",
                    lg.DEBUG,
                )
        return self

    @staticmethod
    def _do_facade(surf):
        """
        Args:
            surf (EpBunch):
        """
        log(
            'surface "%s" assigned as a Facade' % surf.Name,
            lg.DEBUG,
            name=surf.theidf.name,
        )
        oc = OpaqueConstruction.from_epbunch(
            surf.theidf.getobject("Construction".upper(), surf.Construction_Name)
        )
        oc.area = surf.area
        oc.Surface_Type = "Facade"
        oc.Category = oc.Surface_Type
        return oc

    @staticmethod
    def _do_ground(surf):
        """
        Args:
            surf (EpBunch):
        """
        log(
            'surface "%s" assigned as a Ground' % surf.Name,
            lg.DEBUG,
            name=surf.theidf.name,
        )
        oc = OpaqueConstruction.from_epbunch(
            surf.theidf.getobject("Construction".upper(), surf.Construction_Name)
        )
        oc.area = surf.area
        oc.Surface_Type = "Ground"
        oc.Category = oc.Surface_Type
        return oc

    @staticmethod
    def _do_partition(surf):
        """
        Args:
            surf (EpBunch):
        """
        the_construction = surf.theidf.getobject(
            "Construction".upper(), surf.Construction_Name
        )
        if the_construction:
            oc = OpaqueConstruction.from_epbunch(the_construction)
            oc.area = surf.area
            oc.Surface_Type = "Partition"
            oc.Category = oc.Surface_Type
            log(
                'surface "%s" assigned as a Partition' % surf.Name,
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
        """
        Args:
            surf (EpBunch):
        """
        log(
            'surface "%s" assigned as a Roof' % surf.Name,
            lg.DEBUG,
            name=surf.theidf.name,
        )
        oc = OpaqueConstruction.from_epbunch(
            surf.theidf.getobject("Construction".upper(), surf.Construction_Name)
        )
        oc.area = surf.area
        oc.Surface_Type = "Roof"
        oc.Category = oc.Surface_Type
        return oc

    @staticmethod
    def _do_slab(surf):
        """
        Args:
            surf (EpBunch):
        """
        log(
            'surface "%s" assigned as a Slab' % surf.Name,
            lg.DEBUG,
            name=surf.theidf.name,
        )
        oc = OpaqueConstruction.from_epbunch(
            surf.theidf.getobject("Construction".upper(), surf.Construction_Name)
        )
        oc.area = surf.area
        oc.Surface_Type = "Slab"
        oc.Category = oc.Surface_Type
        return oc

    @staticmethod
    def _do_basement(surf):
        """
        Args:
            surf (EpBunch):
        """
        log(
            'surface "%s" ignored because basement facades are not supported'
            % surf.Name,
            lg.WARNING,
            name=surf.theidf.name,
        )
        oc = None
        return oc

    def mapping(self):
        self.validate()

        return dict(
            Facade=self.Facade,
            Ground=self.Ground,
            Partition=self.Partition,
            Roof=self.Roof,
            Slab=self.Slab,
            IsFacadeAdiabatic=self.IsFacadeAdiabatic,
            IsGroundAdiabatic=self.IsGroundAdiabatic,
            IsPartitionAdiabatic=self.IsPartitionAdiabatic,
            IsRoofAdiabatic=self.IsRoofAdiabatic,
            IsSlabAdiabatic=self.IsSlabAdiabatic,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def get_ref(self, ref):
        """Get item matching reference id.

        Args:
            ref:
        """
        return next(
            iter(
                [
                    value
                    for value in ZoneConstructionSet.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )


def surface_dispatcher(surf, zone):
    """
    Args:
        surf (EpBunch):
        zone (ZoneDefinition):
    """
    dispatch = {
        ("Wall", "Outdoors"): ZoneConstructionSet._do_facade,
        ("Floor", "Ground"): ZoneConstructionSet._do_ground,
        ("Floor", "Outdoors"): ZoneConstructionSet._do_ground,
        ("Floor", "Foundation"): ZoneConstructionSet._do_ground,
        ("Floor", "OtherSideCoefficients"): ZoneConstructionSet._do_ground,
        ("Floor", "GroundSlabPreprocessorAverage"): ZoneConstructionSet._do_ground,
        ("Floor", "Surface"): ZoneConstructionSet._do_slab,
        ("Floor", "Adiabatic"): ZoneConstructionSet._do_slab,
        ("Floor", "Zone"): ZoneConstructionSet._do_slab,
        ("Wall", "Adiabatic"): ZoneConstructionSet._do_partition,
        ("Wall", "Surface"): ZoneConstructionSet._do_partition,
        ("Wall", "Zone"): ZoneConstructionSet._do_partition,
        ("Wall", "Ground"): ZoneConstructionSet._do_basement,
        ("Roof", "Outdoors"): ZoneConstructionSet._do_roof,
        ("Roof", "Zone"): ZoneConstructionSet._do_roof,
        ("Roof", "Surface"): ZoneConstructionSet._do_roof,
        ("Ceiling", "Adiabatic"): ZoneConstructionSet._do_slab,
        ("Ceiling", "Surface"): ZoneConstructionSet._do_slab,
        ("Ceiling", "Zone"): ZoneConstructionSet._do_slab,
    }
    if surf.key.upper() not in ["INTERNALMASS", "WINDOWSHADINGCONTROL"]:
        a, b = surf["Surface_Type"].capitalize(), surf["Outside_Boundary_Condition"]
        try:
            yield dispatch[a, b](surf)
        except KeyError as e:
            raise NotImplementedError(
                "surface '%s' in zone '%s' not supported by surface dispatcher "
                "with keys %s" % (surf.Name, zone.Name, e)
            )
