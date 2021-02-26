################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import functools
import math
import sqlite3
import time
from operator import add

import numpy as np
from deprecation import deprecated
from eppy.bunch_subclass import BadEPFieldError
from geomeppy.geom.polygons import Polygon3D
from sigfig import round

from archetypal import __version__, log, settings
from archetypal.template import (
    DomesticHotWaterSetting,
    OpaqueConstruction,
    UmiBase,
    UniqueName,
    VentilationSetting,
    WindowSetting,
    ZoneConditioning,
    ZoneConstructionSet,
    ZoneLoad,
)


class InternalMass(object):
    """Class handles the creation of InternalMass constructions from
    :class:`ZoneDefinition`."""

    @classmethod
    def from_zone(cls, zone, **kwargs):
        """

        Args:
            zone (ZoneDefinition): A ZoneDefinition object.
            **kwargs:

        Returns:
            Construction: The internal mass construction for the zone
            None: if no internal mass defined for zone.
        """
        internal_mass_objs = zone._epbunch.getreferingobjs(
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
            zone.InternalMassExposedPerFloorArea = float(area) / zone.area
            return functools.reduce(add, mass_opaque_constructions)
        else:
            # No InternalMass object assigned to this Zone, then return Zone and set
            # floor area to 0
            zone.InternalMassExposedPerFloorArea = 0
            return None

    @classmethod
    def generic_internalmass_from_zone(cls, zone):
        """Assign a generic internal mass with InternalMassExposedPerFloorArea = 0 to zone.

        Also set it to the self.InternalMassConstruction attribute.

        Args:
            zone (ZoneDefinition): A ZoneDefinition object.
        """
        zone.InternalMassConstruction = OpaqueConstruction.generic_internalmass(
            idf=zone.idf
        )
        zone.InternalMassExposedPerFloorArea = 0


class ZoneDefinition(UmiBase):
    """Class containing HVAC settings: Conditioning, Domestic Hot Water, Loads,
    Ventilation, adn Constructions

    .. image:: ../images/template/zoneinfo-zone.png
    """

    def __init__(
        self,
        Name,
        Constructions=None,
        Loads=None,
        Conditioning=None,
        Ventilation=None,
        DomesticHotWater=None,
        DaylightMeshResolution=1,
        DaylightWorkplaneHeight=0.8,
        InternalMassConstruction=None,
        InternalMassExposedPerFloorArea=1.05,
        Windows=None,
        **kwargs,
    ):
        """Initialize :class:`Zone` object.

        Args:
            Name (str): Name of the object. Must be Unique.
            Constructions (ZoneConstructionSet):
            Loads (ZoneLoad): Loads of the zone defined with the lights,
                equipment and occupancy parameters (see :class:`ZoneLoad`)
            Conditioning (ZoneConditioning): Conditioning of the zone defined
                with heating/cooling and mechanical ventilation parameters (see
                :class:`ZoneConditioning`)
            Ventilation (VentilationSetting): Ventilation settings of the zone
                defined with the infiltration rate and natural ventilation
                parameters (see :class:`VentilationSetting`)
            DomesticHotWater (archetypal.template.dhw.DomesticHotWaterSetting):
            DaylightMeshResolution (float):
            DaylightWorkplaneHeight (float):
            InternalMassConstruction (archetypal.OpaqueConstruction):
            InternalMassExposedPerFloorArea:
            Windows (WindowSetting): The WindowSetting object associated with
                this zone.
            **kwargs:
        """
        super(ZoneDefinition, self).__init__(Name, **kwargs)

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
        self._area = None
        self._volume = None
        self._occupants = None
        self._is_part_of_conditioned_floor_area = None
        self._is_part_of_total_floor_area = None
        self._multiplier = None

    @property
    def InternalMassExposedPerFloorArea(self):
        return float(self._InternalMassExposedPerFloorArea)

    @InternalMassExposedPerFloorArea.setter
    def InternalMassExposedPerFloorArea(self, value):
        self._InternalMassExposedPerFloorArea = value

    def __add__(self, other):
        """
        Args:
            other (ZoneDefinition):
        """
        # create the new merged zone from self
        return ZoneDefinition.combine(self, other)

    def __hash__(self):
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __eq__(self, other):
        if not isinstance(other, ZoneDefinition):
            return NotImplemented
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
    def occupants(self):
        if self._occupants is None:
            with sqlite3.connect(self.idf.sql_file) as conn:
                sql_query = (
                    "SELECT t.Value FROM TabularDataWithStrings t "
                    "WHERE TableName='Average Outdoor Air During Occupied Hours' and ColumnName='Nominal Number of Occupants' and RowName=?"
                )

                fetchone = conn.execute(sql_query, (self.Name.upper(),)).fetchone()
                (res,) = fetchone or (0,)
            self._occupants = float(res)
        return self._occupants

    @occupants.setter
    def occupants(self, value):
        self._occupants = value

    @property
    def area(self):
        if self._area is None:
            with sqlite3.connect(self.idf.sql_file) as conn:
                sql_query = """
                    SELECT t.Value 
                    FROM TabularDataWithStrings t 
                    WHERE TableName='Zone Summary' and ColumnName='Area' and RowName=?
                """
                (res,) = conn.execute(sql_query, (self.Name.upper(),)).fetchone()
            self._area = float(res)
        return self._area

    @area.setter
    def area(self, value):
        self._area = value

    @property
    def volume(self):
        """Calculates the volume of the zone

        Returns (float): zone's volume in m³
        """
        if self._volume is None:
            with sqlite3.connect(self.idf.sql_file) as conn:
                sql_query = (
                    "SELECT t.Value FROM TabularDataWithStrings t "
                    "WHERE TableName='Zone Summary' and ColumnName='Volume' and RowName=?"
                )
                (res,) = conn.execute(sql_query, (self.Name.upper(),)).fetchone()
            self._volume = float(res)
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = value

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
            self._zonesurfaces = [surf for surf in self._epbunch.zonesurfaces]
        return [surf for surf in self._zonesurfaces if surf.key.upper() not in exclude]

    @property
    def is_core(self):
        return is_core(self._epbunch)

    @property
    def multiplier(self):
        """Zone multipliers are designed as a “multiplier” for floor area,
        zone loads, and energy consumed by internal gains.
        """
        if self._multiplier is None:
            with sqlite3.connect(self.idf.sql_file) as conn:
                sql_query = "SELECT t.Value FROM TabularDataWithStrings t WHERE TableName='Zone Summary' and ColumnName='Multipliers' and RowName=?"
                (res,) = conn.execute(sql_query, (self.Name.upper(),)).fetchone()
            self._multiplier = int(float(res))
        return self._multiplier

    @multiplier.setter
    def multiplier(self, value):
        self._multiplier = value

    @property
    def is_part_of_conditioned_floor_area(self):
        """Returns True if zone is conditioned"""
        if self._is_part_of_conditioned_floor_area is None:
            with sqlite3.connect(self.idf.sql_file) as conn:
                sql_query = (
                    "SELECT t.Value FROM TabularDataWithStrings t WHERE TableName='Zone Summary' and ColumnName='Conditioned (Y/N)' and RowName=?"
                    ""
                )
                res = conn.execute(sql_query, (self.Name.upper(),)).fetchone()
            self._is_part_of_conditioned_floor_area = "Yes" in res
        return self._is_part_of_conditioned_floor_area

    @property
    def is_part_of_total_floor_area(self):
        """Returns True if zone is part of the total floor area"""
        if self._is_part_of_total_floor_area is None:
            with sqlite3.connect(self.idf.sql_file) as conn:
                sql_query = "SELECT t.Value FROM TabularDataWithStrings t WHERE TableName='Zone Summary' and ColumnName='Part of Total Floor Area (Y/N)' and RowName=?"
                res = conn.execute(sql_query, (self.Name.upper(),)).fetchone()
            self._is_part_of_total_floor_area = "Yes" in res
        return self._is_part_of_total_floor_area

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

    def to_json(self):
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Conditioning"] = self.Conditioning.to_dict()
        data_dict["Constructions"] = self.Constructions.to_dict()
        data_dict["DaylightMeshResolution"] = round(self.DaylightMeshResolution, 2)
        data_dict["DaylightWorkplaneHeight"] = round(self.DaylightWorkplaneHeight, 2)
        data_dict["DomesticHotWater"] = self.DomesticHotWater.to_dict()
        data_dict["InternalMassConstruction"] = self.InternalMassConstruction.to_dict()
        data_dict["InternalMassExposedPerFloorArea"] = round(
            self.InternalMassExposedPerFloorArea, 2
        )
        data_dict["Loads"] = self.Loads.to_dict()
        data_dict["Ventilation"] = self.Ventilation.to_dict()
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

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
    def from_dict(
        cls,
        Conditioning,
        Constructions,
        DomesticHotWater,
        InternalMassConstruction,
        Loads,
        Ventilation,
        *args,
        **kwargs,
    ):
        """
        Args:
            *args:
            **kwargs:
        """
        Conditioning = cls.get_classref(Conditioning)
        Constructions = cls.get_classref(Constructions)
        DomesticHotWater = cls.get_classref(DomesticHotWater)
        InternalMassConstruction = cls.get_classref(InternalMassConstruction)
        Loads = cls.get_classref(Loads)
        Ventilation = cls.get_classref(Ventilation)
        zone = cls(
            *args,
            Conditioning=Conditioning,
            Constructions=Constructions,
            DomesticHotWater=DomesticHotWater,
            InternalMassConstruction=InternalMassConstruction,
            Loads=Loads,
            Ventilation=Ventilation,
            **kwargs,
        )

        return zone

    @classmethod
    def from_zone_epbunch(cls, zone_ep, construct_parents=True, **kwargs):
        """Create a Zone object from an eppy 'ZONE' epbunch.

        Args:
            zone_ep (eppy.bunch_subclass.EpBunch): The Zone EpBunch.
            construct_parents (bool): If False, skips construction of parents objects
                such as Constructions, Conditioning, etc.
        """
        start_time = time.time()
        log('Constructing :class:`Zone` for zone "{}"'.format(zone_ep.Name))
        name = zone_ep.Name
        zone = cls(
            Name=name,
            idf=zone_ep.theidf,
            Category=zone_ep.theidf.name,
            **kwargs,
        )

        zone._epbunch = zone_ep
        zone._zonesurfaces = zone_ep.zonesurfaces

        if construct_parents:
            zone.Constructions = ZoneConstructionSet.from_zone(zone, **kwargs)
            zone.Conditioning = ZoneConditioning.from_zone(zone, **kwargs)
            zone.Ventilation = VentilationSetting.from_zone(zone, **kwargs)
            zone.DomesticHotWater = DomesticHotWaterSetting.from_zone(zone, **kwargs)
            zone.Loads = ZoneLoad.from_zone(zone, **kwargs)
            zone.InternalMassConstruction = InternalMass.from_zone(zone, **kwargs)
            zone.Windows = WindowSetting.from_zone(zone, **kwargs)

        log(
            'completed Zone "{}" constructor in {:,.2f} seconds'.format(
                zone_ep.Name, time.time() - start_time
            )
        )
        return zone

    def combine(self, other, weights=None, allow_duplicates=False):
        """
        Args:
            other (ZoneDefinition):
            weights (list-like, optional): A list-like object of len 2. If None,
                the volume of the zones for which self and other belongs is
                used.

        Todo:
            Create Equivalent InternalMassConstruction from partitions when combining
            zones.

        Returns:
            (ZoneDefinition): the combined Zone object.
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

        new_attr = dict(
            Conditioning=ZoneConditioning.combine(
                self.Conditioning, other.Conditioning, weights
            ),
            Constructions=ZoneConstructionSet.combine(
                self.Constructions, other.Constructions, weights
            ),
            Ventilation=VentilationSetting.combine(
                self.Ventilation, other.Ventilation, weights
            ),
            Windows=WindowSetting.combine(self.Windows, other.Windows, weights),
            DaylightMeshResolution=self._float_mean(
                other, "DaylightMeshResolution", weights=weights
            ),
            DaylightWorkplaneHeight=self._float_mean(
                other, "DaylightWorkplaneHeight", weights
            ),
            DomesticHotWater=DomesticHotWaterSetting.combine(
                self.DomesticHotWater, other.DomesticHotWater, weights
            ),
            InternalMassConstruction=OpaqueConstruction.combine(
                self.InternalMassConstruction, other.InternalMassConstruction
            ),
            InternalMassExposedPerFloorArea=self._float_mean(
                other, "InternalMassExposedPerFloorArea", weights
            ),
            Loads=ZoneLoad.combine(self.Loads, other.Loads, weights),
        )
        new_obj = ZoneDefinition(**meta, **new_attr, idf=self.idf)

        # transfer aggregated values [volume, area, occupants] to new combined zone
        new_obj.volume = self.volume + other.volume
        new_obj.area = self.area + other.area
        new_obj.occupants = self.occupants + other.occupants

        if new_attr["Conditioning"]:  # Could be None
            new_attr["Conditioning"]._belongs_to_zone = new_obj
        if new_attr["Constructions"]:  # Could be None
            new_attr["Constructions"]._belongs_to_zone = new_obj
        if new_attr["Ventilation"]:  # Could be None
            new_attr["Ventilation"]._belongs_to_zone = new_obj
        if new_attr["DomesticHotWater"]:  # Could be None
            new_attr["DomesticHotWater"]._belongs_to_zone = new_obj
        if new_attr["Windows"]:  # Could be None
            new_attr["Windows"]._belongs_to_zone = new_obj

        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def validate(self):
        """Validate object and fill in missing values."""
        if not self.InternalMassConstruction:
            InternalMass.generic_internalmass_from_zone(self)
            log(
                f"While validating {self}, the required attribute "
                f"'InternalMassConstruction' was filled "
                f"with {self.InternalMassConstruction} and the "
                f"'InternalMassExposedPerFloorArea' set to"
                f" {self.InternalMassExposedPerFloorArea}"
            )

        if self.Conditioning is None:
            self.Conditioning = ZoneConditioning(Name="Unconditioned Zone")

        return self

    def mapping(self):
        self.validate()

        return dict(
            Conditioning=self.Conditioning,
            Constructions=self.Constructions,
            DaylightMeshResolution=self.DaylightMeshResolution,
            DaylightWorkplaneHeight=self.DaylightWorkplaneHeight,
            DomesticHotWater=self.DomesticHotWater,
            InternalMassConstruction=self.InternalMassConstruction,
            InternalMassExposedPerFloorArea=self.InternalMassExposedPerFloorArea,
            Windows=self.Windows,
            Loads=self.Loads,
            Ventilation=self.Ventilation,
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
                    for value in ZoneDefinition.CREATED_OBJECTS
                    if value.id == ref["$ref"]
                ]
            ),
            None,
        )


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
                if obc in ["outdoors", "ground"]:
                    iscore = False
                    break
        except BadEPFieldError:
            pass  # pass surfaces that don't have an OBC,
            # eg. InternalMass
    return iscore


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
