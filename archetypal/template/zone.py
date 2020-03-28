################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import functools
import logging as lg
import math
import random
import time

import numpy as np
from archetypal import log, timeit, settings
from archetypal.template import (
    Unique,
    UmiBase,
    ZoneConditioning,
    ZoneLoad,
    VentilationSetting,
    DomesticHotWaterSetting,
    OpaqueConstruction,
    WindowSetting,
    CREATED_OBJECTS,
    UniqueName,
)
from archetypal.utils import reduce
from eppy.bunch_subclass import BadEPFieldError
from geomeppy.geom.polygons import Polygon3D


class Zone(UmiBase):
    """Class containing HVAC settings: Conditioning, Domestic Hot Water, Loads,
    Ventilation, adn Consructions

    .. image:: ../images/template/zoneinfo-zone.png
    """

    _cache = {}

    def __init__(
        self,
        Conditioning=None,
        Constructions=None,
        DomesticHotWater=None,
        Loads=None,
        Ventilation=None,
        Windows=None,
        InternalMassConstruction=None,
        InternalMassExposedPerFloorArea=1.05,
        DaylightMeshResolution=1,
        DaylightWorkplaneHeight=0.8,
        **kwargs
    ):
        """Initialize :class:`Zone` object.

        Args:
            Conditioning (ZoneConditioning): Conditioning of the zone defined
                with heating/cooling and mechanical ventilation parameters (see
                :class:`ZoneConditioning`)
            Constructions (ZoneConstructionSet):
            DomesticHotWater (archetypal.template.dhw.DomesticHotWaterSetting):
            Loads (ZoneLoad): Loads of the zone defined with the lights,
                equipment and occupancy parameters (see :class:`ZoneLoad`)
            Ventilation (VentilationSetting): Ventilation settings of the zone
                defined with the infiltration rate and natural ventilation
                parameters (see :class:`VentilationSetting`)
            Windows (WindowSetting): The WindowSetting object associated with
                this zone.
            InternalMassConstruction (archetypal.OpaqueConstruction):
            InternalMassExposedPerFloorArea:
            DaylightMeshResolution (float):
            DaylightWorkplaneHeight (float):
            **kwargs:
        """
        super(Zone, self).__init__(**kwargs)

        self.Ventilation = Ventilation
        self.Loads = Loads
        self.Conditioning = Conditioning
        self.Constructions = Constructions
        self.DaylightMeshResolution = DaylightMeshResolution
        self.DaylightWorkplaneHeight = DaylightWorkplaneHeight
        self.DomesticHotWater = DomesticHotWater
        self.InternalMassConstruction = InternalMassConstruction
        self.InternalMassExposedPerFloorArea = InternalMassExposedPerFloorArea

        self.Windows = Windows  # This is not used in to_json()

        self._epbunch = kwargs.get("epbunch", None)
        self._zonesurfaces = kwargs.get("zonesurfaces", None)
        self._area = kwargs.get("area", None)
        self._volume = kwargs.get("volume", None)

        self._cache[hash(self)] = self
        CREATED_OBJECTS[hash(self)] = self

    def __add__(self, other):
        """
        Args:
            other (Zone):
        """
        # create the new merged zone from self
        return self.combine(other)

    def __hash__(self):
        return hash((self.Name, id(self.idf)))

    def __eq__(self, other):
        if not isinstance(other, Zone):
            return False
        else:
            return all(
                [
                    self.Conditioning == other.Conditioning,
                    self.Constructions == other.Constructions,
                    self.DomesticHotWater == other.DomesticHotWater,
                    self.Loads == other.Loads,
                    self.Ventilation == other.Ventilation,
                    self.Windows == other.Windows,
                    self.InternalMassConstruction == other.InternalMassConstruction,
                    self.InternalMassExposedPerFloorArea
                    == other.InternalMassExposedPerFloorArea,
                    self.DaylightMeshResolution == other.DaylightMeshResolution,
                    self.DaylightWorkplaneHeight == other.DaylightWorkplaneHeight,
                ]
            )

    @property
    def area(self):
        """Calculates the floor surface area of the zone

        Returns (float): zone's area in m²
        """
        if self._area is None:
            zone_surfs = self.zonesurfaces(
                exclude=["INTERNALMASS", "WINDOWSHADINGCONTROL"]
            )
            floors = [s for s in zone_surfs if s.Surface_Type.upper() == "FLOOR"]
            area = sum([floor.area for floor in floors])
            return area
        else:
            return self._area

    @property
    def volume(self):
        """Calculates the volume of the zone

        Returns (float): zone's volume in m³
        """
        if not self._volume:
            zone_surfs = self.zonesurfaces(
                exclude=["INTERNALMASS", "WINDOWSHADINGCONTROL"]
            )

            vol = self.get_volume_from_surfs(zone_surfs)

            if self._epbunch.Multiplier == "":
                multiplier = 1
            else:
                multiplier = float(self._epbunch.Multiplier)
            # multiply to volume by the zone multiplier.
            return vol * multiplier
        else:
            return self._volume

    def zonesurfaces(self, exclude=None):
        """Returns list of surfaces belonging to this zone. Optionally filter
        surface types.

        Args:
            exclude (list): exclude surface types, e.g.: ["INTERNALMASS",
                "WINDOWSHADINGCONTROL"]. Object key must be in capital letters.
        """
        if exclude is None:
            exclude = []
        if self._zonesurfaces is None:
            return [
                surf
                for surf in self._epbunch.zonesurfaces
                if surf.key.upper() not in exclude
            ]
        else:
            return [
                surf for surf in self._zonesurfaces if surf.key.upper() not in exclude
            ]

    @property
    def is_core(self):
        return is_core(self._epbunch)

    @property
    def is_part_of_conditioned_floor_area(self):
        return is_part_of_conditioned_floor_area(self)

    @staticmethod
    def get_volume_from_surfs(zone_surfs):
        """Calculate the volume of a zone only and only if the surfaces are such
        that you can find a point inside so that you can connect every vertex to
        the point without crossing a face.

        Adapted from: https://stackoverflow.com/a/19125446

        Args:
            zone_surfs (list): List of zone surfaces (EpBunch)
        """
        vol = 0
        for surf in zone_surfs:
            polygon_d = Polygon3D(surf.coords)  # create Polygon3D from surf
            n = len(polygon_d.vertices_list)
            v2 = polygon_d[0]
            x2 = v2.x
            y2 = v2.y
            z2 = v2.z

            for i in range(1, n - 1):
                v0 = polygon_d[i]
                x0 = v0.x
                y0 = v0.y
                z0 = v0.z
                v1 = polygon_d[i + 1]
                x1 = v1.x
                y1 = v1.y
                z1 = v1.z
                # Add volume of tetrahedron formed by triangle and origin
                vol += math.fabs(
                    x0 * y1 * z2
                    + x1 * y2 * z0
                    + x2 * y0 * z1
                    - x0 * y2 * z1
                    - x1 * y0 * z2
                    - x2 * y1 * z0
                )
        return vol / 6.0

    def _conditioning(self):
        """run _conditioning and return id"""
        self.Conditioning = ZoneConditioning.from_idf(Name=random.randint(1, 999999))

    @timeit
    def _internalmassconstruction(self):
        """Group internal walls into a ThermalMass object for this Zone"""

        oc = []
        for surface in self.zonesurfaces(exclude=["WINDOWSHADINGCONTROL"]):
            # for surf_type in self.idf.idd_index['ref2names'][
            # 'AllHeatTranSurfNames']:
            if surface.key.upper() == "INTERNALMASS":
                oc.append(OpaqueConstruction.from_epbunch(surface))
                self.InternalMassExposedPerFloorArea = (
                    float(surface.Surface_Area) / self.area
                )
        if not oc:
            # Todo: Create Equivalent InternalMassConstruction from
            #  partitions. For now, creating dummy InternalMass

            mat = self.idf.add_object(
                ep_object="Material".upper(),
                Name="Wood 6inch",
                Roughness="MediumSmooth",
                Thickness=0.15,
                Conductivity=0.12,
                Density=540,
                Specific_Heat=1210,
                Thermal_Absorptance=0.7,
                Visible_Absorptance=0.7,
            )

            cons = self.idf.add_object(
                ep_object="Construction".upper(),
                save=False,
                Name="InteriorFurnishings",
                Outside_Layer="Wood 6inch",
            )

            internal_mass = "{}_InternalMass".format(self.Name)
            cons.Name = internal_mass + "_construction"
            new_epbunch = self.idf.add_object(
                ep_object="InternalMass".upper(),
                save=False,
                Name=internal_mass,
                Construction_Name=cons.Name,
                Zone_or_ZoneList_Name=self.Name,
                Surface_Area=1,
            )

            oc.append(OpaqueConstruction.from_epbunch(new_epbunch, idf=self.idf))
            self.InternalMassExposedPerFloorArea = 0

        if self.InternalMassExposedPerFloorArea is None:
            self.InternalMassExposedPerFloorArea = 0

        from operator import add

        return functools.reduce(add, oc)

    def _loads(self):
        """run loads and return id"""
        self.Loads = ZoneLoad(Name=str(random.randint(1, 999999)))

    def _ventilation(self):
        self.Ventilation = VentilationSetting(Name=str(random.randint(1, 999999)))

    def _constructions(self):
        """run construction sets and return id"""
        set_name = "_".join([self.Name, "constructions"])
        self.Constructions = ZoneConstructionSet.from_idf(
            Zone_Names=self.Zone_Names, sql=self.sql, Name=set_name, idf=self.idf
        )

    def _domestichotwater(self):
        """run domestic hot water and return id"""
        self.DomesticHotWater = DomesticHotWaterSetting(
            Name=str(random.randint(1, 999999))
        )

    def to_json(self):
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Conditioning"] = self.Conditioning.to_dict()
        data_dict["Constructions"] = self.Constructions.to_dict()
        data_dict["DaylightMeshResolution"] = self.DaylightMeshResolution
        data_dict["DaylightWorkplaneHeight"] = self.DaylightWorkplaneHeight
        data_dict["DomesticHotWater"] = self.DomesticHotWater.to_dict()
        data_dict["InternalMassConstruction"] = self.InternalMassConstruction.to_dict()
        data_dict[
            "InternalMassExposedPerFloorArea"
        ] = self.InternalMassExposedPerFloorArea
        data_dict["Loads"] = self.Loads.to_dict()
        data_dict["Ventilation"] = self.Ventilation.to_dict()
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        zone = cls(*args, **kwargs)

        ref = kwargs.get("Conditioning", None)
        zone.Conditioning = zone.get_ref(ref)
        ref = kwargs.get("Constructions", None)
        zone.Constructions = zone.get_ref(ref)
        ref = kwargs.get("DomesticHotWater", None)
        zone.DomesticHotWater = zone.get_ref(ref)
        ref = kwargs.get("InternalMassConstruction", None)
        zone.InternalMassConstruction = zone.get_ref(ref)
        ref = kwargs.get("Loads", None)
        zone.Loads = zone.get_ref(ref)
        ref = kwargs.get("Ventilation", None)
        zone.Ventilation = zone.get_ref(ref)

        return zone

    @classmethod
    def from_zone_epbunch(cls, zone_ep, sql):
        """Create a Zone object from an eppy 'ZONE' epbunch.

        Args:
            zone_ep (eppy.bunch_subclass.EpBunch): The Zone EpBunch.
            sql (dict): The sql dict for this IDF object.
        """
        cached = cls.get_cached(zone_ep.Name, zone_ep.theidf)
        if cached:
            return cached
        start_time = time.time()
        log('\nConstructing :class:`Zone` for zone "{}"'.format(zone_ep.Name))
        name = zone_ep.Name
        zone = cls(
            Name=name,
            idf=zone_ep.theidf,
            sql=sql,
            Category=zone_ep.theidf.building_name(use_idfname=True),
        )

        zone._epbunch = zone_ep
        zone._zonesurfaces = zone_ep.zonesurfaces

        zone.Constructions = ZoneConstructionSet.from_zone(zone)
        zone.Conditioning = ZoneConditioning.from_zone(zone)
        zone.Ventilation = VentilationSetting.from_zone(zone)
        zone.DomesticHotWater = DomesticHotWaterSetting.from_zone(zone)
        zone.Loads = ZoneLoad.from_zone(zone)
        zone.InternalMassConstruction = zone._internalmassconstruction()
        zone.Windows = WindowSetting.from_zone(zone)

        log(
            'completed Zone "{}" constructor in {:,.2f} seconds'.format(
                zone_ep.Name, time.time() - start_time
            )
        )
        return zone

    @classmethod
    def get_cached(cls, name, idf):
        """Retrieve the cached object by Name and idf name. If not, returns
        None.

        Args:
            name (str): The name of the object in the cache.
            idf (IDF): The :class:`IDF` object.
        """
        try:
            cached = cls._cache[hash((name, id(idf)))]
        except KeyError:
            return None
        else:
            return cached

    def combine(self, other, weights=None):
        """
        Args:
            other (Zone):
            weights (list-like, optional): A list-like object of len 2. If None,
                the volume of the zones for which self and other belongs is
                used.

        Returns:
            (Zone): the combined Zone object.
        """
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

        incoming_zone_data = self.__dict__.copy()
        incoming_zone_data.pop("Name")

        meta = self._get_predecessors_meta(other)

        if not weights:
            zone_weight = settings.zone_weight
            weights = [
                getattr(self, str(zone_weight)),
                getattr(other, str(zone_weight)),
            ]
            log(
                'using zone {} "{}" as weighting factor in "{}" '
                "combine.".format(
                    zone_weight,
                    " & ".join(list(map(str, map(int, weights)))),
                    self.__class__.__name__,
                )
            )

        attr = dict(
            Conditioning=self.Conditioning.combine(other.Conditioning, weights),
            Constructions=self.Constructions.combine(other.Constructions, weights),
            Ventilation=self.Ventilation.combine(other.Ventilation, weights),
            Windows=None
            if self.Windows is None or other.Windows is None
            else self.Windows.combine(other.Windows, weights),
            DaylightMeshResolution=self._float_mean(
                other, "DaylightMeshResolution", weights=weights
            ),
            DaylightWorkplaneHeight=self._float_mean(
                other, "DaylightWorkplaneHeight", weights
            ),
            DomesticHotWater=self.DomesticHotWater.combine(
                other.DomesticHotWater, weights
            ),
            InternalMassConstruction=self.InternalMassConstruction.combine(
                other.InternalMassConstruction, weights
            ),
            InternalMassExposedPerFloorArea=self._float_mean(
                other, "InternalMassExposedPerFloorArea", weights
            ),
            Loads=self.Loads.combine(other.Loads, weights),
        )
        new_obj = self.__class__(**meta, **attr)
        new_obj._volume = self.volume + other.volume
        new_obj._area = self.area + other.area
        attr["Conditioning"]._belongs_to_zone = new_obj
        attr["Constructions"]._belongs_to_zone = new_obj
        attr["Ventilation"]._belongs_to_zone = new_obj
        attr["DomesticHotWater"]._belongs_to_zone = new_obj
        if attr["Windows"]:
            attr["Windows"]._belongs_to_zone = new_obj
        new_obj._predecessors.extend(self.predecessors + other.predecessors)
        return new_obj


def resolve_obco(this):
    """Resolve the outside boundary condition of a surface and return the other
    SURFACE epbunch and, if possible, the ZONE epbunch.

    Args:
        this (EpBunch): The surface for which we are identifying the boundary
            object.

    Returns:
        (EpBunch, EpBunch): A tuple of:

            EpBunch: The other surface EpBunch: The other zone

    Notes:
        Info on the Outside Boundary Condition Object of a surface of type
        BuildingSurface:Detailed:

        Non-blank only if the field `Outside Boundary Condition` is *Surface*,
        *Zone*, *OtherSideCoefficients* or *OtherSideConditionsModel*. If
        Surface, specify name of corresponding surface in adjacent zone or
        specify current surface name for internal partition separating like
        zones. If Zone, specify the name of the corresponding zone and the
        program will generate the corresponding interzone surface. If
        Foundation, specify the name of the corresponding Foundation object and
        the program will calculate the heat transfer appropriately. If
        OtherSideCoefficients, specify name of
        SurfaceProperty:OtherSideCoefficients. If OtherSideConditionsModel,
        specify name of SurfaceProperty:OtherSideConditionsModel.
    """

    # other belongs to which zone?
    # for key in this.getfieldidd_item('Outside_Boundary_Condition_Object',
    #                                  'validobjects'):

    obc = this.Outside_Boundary_Condition

    if obc.upper() == "ZONE":
        name = this.Outside_Boundary_Condition_Object
        adj_zone = this.theidf.getobject("ZONE", name)
        return None, adj_zone

    elif obc.upper() == "SURFACE":
        obco = this.get_referenced_object("Outside_Boundary_Condition_Object")
        adj_zone = obco.theidf.getobject("ZONE", obco.Zone_Name)
        return obco, adj_zone
    else:
        return None, None


def surface_dispatcher(surf, zone):
    """
    Args:
        surf (EpBunch):
        zone (EpBunch):
    """
    dispatch = {
        ("Wall", "Outdoors"): ZoneConstructionSet._do_facade,
        ("Floor", "Ground"): ZoneConstructionSet._do_ground,
        ("Floor", "Outdoors"): ZoneConstructionSet._do_ground,
        ("Floor", "Foundation"): ZoneConstructionSet._do_ground,
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


def label_surface(row):
    """Takes a boundary and returns its corresponding umi-Category

    Args:
        row:
    """
    # Floors
    if row["Surface_Type"] == "Floor":
        if row["Outside_Boundary_Condition"] == "Surface":
            return "Interior Floor"
        if row["Outside_Boundary_Condition"] == "Ground":
            return "Ground Floor"
        if row["Outside_Boundary_Condition"] == "Outdoors":
            return "Exterior Floor"
        if row["Outside_Boundary_Condition"] == "Adiabatic":
            return "Interior Floor"
        else:
            return "Other"

    # Roofs & Ceilings
    if row["Surface_Type"] == "Roof":
        return "Roof"
    if row["Surface_Type"] == "Ceiling":
        return "Interior Floor"
    # Walls
    if row["Surface_Type"] == "Wall":
        if row["Outside_Boundary_Condition"] == "Surface":
            return "Partition"
        if row["Outside_Boundary_Condition"] == "Outdoors":
            return "Facade"
        if row["Outside_Boundary_Condition"] == "Adiabatic":
            return "Partition"
    return "Other"


def type_surface(row):
    """Takes a boundary and returns its corresponding umi-type

    Args:
        row:
    """

    # Floors
    if row["Surface_Type"] == "Floor":
        if row["Outside_Boundary_Condition"] == "Surface":
            return 3  # umi defined
        if row["Outside_Boundary_Condition"] == "Ground":
            return 2  # umi defined
        if row["Outside_Boundary_Condition"] == "Outdoors":
            return 4  # umi defined
        if row["Outside_Boundary_Condition"] == "Adiabatic":
            return 5
        else:
            return ValueError('Cannot find Construction Type for "{}"'.format(row))

    # Roofs & Ceilings
    elif row["Surface_Type"] == "Roof":
        return 1
    elif row["Surface_Type"] == "Ceiling":
        return 3
    # Walls
    elif row["Surface_Type"] == "Wall":
        if row["Outside_Boundary_Condition"] == "Surface":
            return 5  # umi defined
        if row["Outside_Boundary_Condition"] == "Outdoors":
            return 0  # umi defined
        if row["Outside_Boundary_Condition"] == "Adiabatic":
            return 5  # umi defined
    else:
        raise ValueError('Cannot find Construction Type for "{}"'.format(row))


def zone_information(df):
    """Each zone_loads is summarized in a simple set of statements

    Args:
        df:

    Returns:
        df

    References:
        * ` Zone Loads Information

        < https://bigladdersoftware.com/epx/docs/8-3/output-details-and
        -examples/eplusout.eio.html#zone_loads-information>`_
    """
    df = get_from_tabulardata(df)
    tbstr = df[
        (df.ReportName == "Initialization Summary")
        & (df.TableName == "Zone Information")
    ].reset_index()
    # Ignore Zone that are not part of building area
    pivoted = tbstr.pivot_table(
        index=["RowName"],
        columns="ColumnName",
        values="Value",
        aggfunc=lambda x: " ".join(x),
    )

    return pivoted.loc[pivoted["Part of Total Building Area"] == "Yes", :]


def get_from_tabulardata(sql):
    """Returns a DataFrame from the 'TabularDataWithStrings' table.

    Args:
        sql (dict):

    Returns:
        (pandas.DataFrame)
    """
    tab_data_wstring = sql["TabularDataWithStrings"]
    tab_data_wstring.index.names = ["Index"]

    # strip whitespaces
    tab_data_wstring.Value = tab_data_wstring.Value.str.strip()
    tab_data_wstring.RowName = tab_data_wstring.RowName.str.strip()
    return tab_data_wstring


def is_core(zone):
    """

    Args:
        zone (eppy.bunch_subclass.EpBunch): The Zone object.

    Returns:
        (bool): Whether the zone is a core zone or not.
    """
    # if all surfaces don't have boundary condition == "Outdoors"
    iscore = True
    for s in zone.zonesurfaces:
        try:
            if (abs(int(s.tilt)) < 180) & (abs(int(s.tilt)) > 0):
                obc = s.Outside_Boundary_Condition.lower()
                if obc == "outdoors":
                    iscore = False
                    break
        except BadEPFieldError:
            pass  # pass surfaces that don't have an OBC,
            # eg. InternalMass
    return iscore


def is_part_of_conditioned_floor_area(zone):
    """Returns True if Zone epbunch has :attr:`Part_of_Total_Floor_Area` == "YES"

    Args:
        zone (Zone): The Zone object.
    """
    return zone._epbunch.Part_of_Total_Floor_Area.upper() != "NO"


def iscore(row):
    """Helps to group by core and perimeter zones. If any of "has `core` in
    name" and "ExtGrossWallArea == 0" is true, will consider zone_loads as core,
    else as perimeter.

    Todo:
        * assumes a basement zone_loads will be considered as a core zone_loads
          since no ext wall area for basements.

    Args:
        row (pandas.Series): a row

    Returns:
        str: 'Core' or 'Perimeter'
    """
    if any(
        [
            "core" in row["Zone Name"].lower(),
            float(row["Exterior Gross Wall Area {m2}"]) == 0,
        ]
    ):
        # We look for the string `core` in the Zone_Name
        return "Core"
    elif row["Part of Total Building Area"] == "No":
        return np.NaN
    elif "plenum" in row["Zone Name"].lower():
        return np.NaN
    else:
        return "Perimeter"


class ZoneConstructionSet(UmiBase, metaclass=Unique):
    """Zone-specific :class:`Construction` ids"""

    def __init__(
        self,
        *args,
        Zone_Names=None,
        Slab=None,
        IsSlabAdiabatic=False,
        Roof=None,
        IsRoofAdiabatic=False,
        Partition=None,
        IsPartitionAdiabatic=False,
        Ground=None,
        IsGroundAdiabatic=False,
        Facade=None,
        IsFacadeAdiabatic=False,
        **kwargs
    ):
        """
        Args:
            *args:
            Zone_Names:
            Slab (OpaqueConstruction):
            IsSlabAdiabatic (bool):
            Roof (OpaqueConstruction):
            IsRoofAdiabatic (bool):
            Partition (OpaqueConstruction):
            IsPartitionAdiabatic (bool):
            Ground (OpaqueConstruction):
            IsGroundAdiabatic (bool):
            Facade (OpaqueConstruction):
            IsFacadeAdiabatic (bool):
            **kwargs:
        """
        super(ZoneConstructionSet, self).__init__(*args, **kwargs)
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

        self.Zone_Names = Zone_Names
        self._belongs_to_zone = kwargs.get("zone", None)

    def __add__(self, other):
        """Overload + to implement self.combine.

        Args:
            other:
        """
        return self.combine(other)

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name, self.DataSource))

    def __eq__(self, other):
        if not isinstance(other, ZoneConstructionSet):
            return False
        else:
            return all(
                [
                    self.Zone_Names == other.Zone_Names,
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

    def combine(self, other, weights=None):
        """Append other to self. Return self + other as a new object.

        Args:
            other (ZoneConstructionSet):
            weights:

        Returns:
            (ZoneConstructionSet): the combined ZoneConstructionSet object.
        """
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
            Slab=self.Slab.combine(other.Slab, [self.Slab.area, other.Slab.area]),
            IsSlabAdiabatic=any([self.IsSlabAdiabatic, other.IsSlabAdiabatic]),
            Roof=self.Roof.combine(other.Roof, [self.Roof.area, other.Roof.area]),
            IsRoofAdiabatic=any([self.IsRoofAdiabatic, other.IsRoofAdiabatic]),
            Partition=self.Partition.combine(
                other.Partition, [self.Partition.area, other.Partition.area]
            ),
            IsPartitionAdiabatic=any(
                [self.IsPartitionAdiabatic, other.IsPartitionAdiabatic]
            ),
            Ground=self.Ground.combine(
                other.Ground, [self.Ground.area, other.Ground.area]
            ),
            IsGroundAdiabatic=any([self.IsGroundAdiabatic, other.IsGroundAdiabatic]),
            Facade=self.Facade.combine(
                other.Facade, [self.Facade.area, other.Facade.area]
            ),
            IsFacadeAdiabatic=any([self.IsFacadeAdiabatic, other.IsFacadeAdiabatic]),
        )
        new_obj = self.__class__(**meta, **new_attr)
        new_obj._predecessors.extend(self.predecessors + other.predecessors)
        return new_obj

    @classmethod
    def from_json(cls, *args, **kwargs):
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

    def to_json(self):
        """Convert class properties to dict"""
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

    @classmethod
    @timeit
    def from_zone(cls, zone):
        """
        Args:
            zone (Zone):
        """
        name = zone.Name + "_ZoneConstructionSet"
        # dispatch surfaces
        facade, ground, partition, roof, slab = [], [], [], [], []
        zonesurfaces = zone._zonesurfaces
        for surf in zonesurfaces:
            for disp_surf in surface_dispatcher(surf, zone):
                if disp_surf:
                    if disp_surf.Surface_Type == "Facade":
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
            facade = OpaqueConstruction.generic(idf=zone.idf)
        grounds = set(ground)
        if grounds:
            ground = reduce(OpaqueConstruction.combine, grounds)
        else:
            ground = OpaqueConstruction.generic(idf=zone.idf)
        partitions = set(partition)
        if partitions:
            partition = reduce(OpaqueConstruction.combine, partitions)
        else:
            partition = OpaqueConstruction.generic(idf=zone.idf)
        roofs = set(roof)
        if roofs:
            roof = reduce(OpaqueConstruction.combine, roofs)
        else:
            roof = OpaqueConstruction.generic(idf=zone.idf)
        slabs = set(slab)
        if slabs:
            slab = reduce(OpaqueConstruction.combine, slabs)
        else:
            slab = OpaqueConstruction.generic(idf=zone.idf)

        z_set = cls(
            Facade=facade,
            Ground=ground,
            Partition=partition,
            Roof=roof,
            Slab=slab,
            Name=name,
            zone=zone,
            idf=zone.idf,
            Category=zone.idf.building_name(use_idfname=True),
        )
        return z_set

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
        oc = OpaqueConstruction.from_epbunch(
            surf.theidf.getobject("Construction".upper(), surf.Construction_Name)
        )
        oc.area = surf.area
        oc.Surface_Type = "Facade"
        return oc
