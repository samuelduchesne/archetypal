"""archetypal ZoneDefinition module."""

import collections
import sqlite3
import time
from typing import List, Optional

from eppy.bunch_subclass import BadEPFieldError, EpBunch
from pydantic import BaseModel, Field
from sigfig import round
from validator_collection import validators

from archetypal.template.conditioning import ZoneConditioning
from archetypal.template.constructions.internal_mass import InternalMass
from archetypal.template.constructions.opaque_construction import OpaqueConstruction
from archetypal.template.dhw import DomesticHotWaterSetting
from archetypal.template.load import ZoneLoad
from archetypal.template.umi_base import UmiBase
from archetypal.template.ventilation import VentilationSetting
from archetypal.template.window_setting import WindowSetting
from archetypal.template.zone_construction_set import ZoneConstructionSet
from archetypal.utils import log, settings


class ZoneDefinition(BaseModel):
    """Zone settings class.

    .. image:: ../images/template/zoneinfo-zone.png

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
    area (float):
    volume (float):
    occupants (float):
    **kwargs:
    """
    _CREATED_OBJECTS = []

    Name: str
    Constructions: ZoneConstructionSet = None
    Loads: ZoneLoad = None
    Conditioning: ZoneConditioning = None
    Ventilation: VentilationSetting = None
    DomesticHotWater: DomesticHotWaterSetting = None
    DaylightMeshResolution: float = Field(1, ge=0)
    DaylightWorkplaneHeight: float = Field(0.8, ge=0)
    InternalMassConstruction: OpaqueConstruction = None
    InternalMassExposedPerFloorArea: float = Field(1.05, ge=0)
    Windows: WindowSetting = None
    area: float = Field(1, ge=0)
    volume: float = Field(1, ge=0)
    occupants: float = Field(1, ge=0)
    is_part_of_conditioned_floor_area: bool = True
    is_part_of_total_floor_area: bool = True
    multiplier: float = Field(1, ge=1)
    zone_surfaces: List[Optional[EpBunch]] = []
    is_core = False

    def to_dict(self):
        """Return ZoneDefinition dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Conditioning"] = self.Conditioning.to_ref()
        data_dict["Constructions"] = self.Constructions.to_ref()
        data_dict["DaylightMeshResolution"] = round(self.DaylightMeshResolution, 2)
        data_dict["DaylightWorkplaneHeight"] = round(self.DaylightWorkplaneHeight, 2)
        data_dict["DomesticHotWater"] = self.DomesticHotWater.to_ref()
        data_dict["InternalMassConstruction"] = self.InternalMassConstruction.to_ref()
        data_dict["InternalMassExposedPerFloorArea"] = round(
            self.InternalMassExposedPerFloorArea, 3
        )
        data_dict["Loads"] = self.Loads.to_ref()
        data_dict["Ventilation"] = self.Ventilation.to_ref()
        data_dict["Category"] = self.Category
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_dict(
        cls,
        data,
        zone_conditionings,
        zone_construction_sets,
        domestic_hot_water_settings,
        opaque_constructions,
        zone_loads,
        ventilation_settings,
        **kwargs,
    ):
        """Create a ZoneDefinition from a dictionary.

        Args:
            data (dict): The python dictionary.
            zone_conditionings (dict): A dictionary of ZoneConditioning objects with
                their id as keys.
            zone_construction_sets (dict): A dictionary of ZoneConstructionSet
                objects with their id as keys.
            domestic_hot_water_settings (dict): A dictionary of DomesticHotWaterSetting
                objects with their id as keys.
            opaque_constructions (dict): A dictionary of OpaqueConstruction objects
                with their id as keys.
            zone_loads (dict): A dictionary of ZoneLoad objects with their id as
                keys.
            ventilation_settings (dict): A dictionary of ZoneConditioning objects with
                their id as keys.
            **kwargs: keywords passed to the constructor.

        .. code-block:: python

            {
              "$id": "175",
              "Conditioning": {
                "$ref": "165"
              },
              "Constructions": {
                "$ref": "168"
              },
              "DaylightMeshResolution": 1.0,
              "DaylightWorkplaneHeight": 0.8,
              "DomesticHotWater": {
                "$ref": "159"
              },
              "InternalMassConstruction": {
                "$ref": "54"
              },
              "InternalMassExposedPerFloorArea": 1.05,
              "Loads": {
                "$ref": "172"
              },
              "Ventilation": {
                "$ref": "162"
              },
              "Category": "Office Spaces",
              "Comments": null,
              "DataSource": "MIT_SDL",
              "Name": "B_Off_0"
            }
        """
        _id = data.pop("$id")

        conditioning = zone_conditionings[data.pop("Conditioning")["$ref"]]
        construction_set = zone_construction_sets[data.pop("Constructions")["$ref"]]
        domestic_hot_water_setting = domestic_hot_water_settings[
            data.pop("DomesticHotWater")["$ref"]
        ]
        internal_mass_construction = opaque_constructions[
            data.pop("InternalMassConstruction")["$ref"]
        ]
        zone_load = zone_loads[data.pop("Loads")["$ref"]]
        ventilation_setting = ventilation_settings[data.pop("Ventilation")["$ref"]]

        return cls(
            id=_id,
            Conditioning=conditioning,
            Constructions=construction_set,
            DomesticHotWater=domestic_hot_water_setting,
            InternalMassConstruction=internal_mass_construction,
            Loads=zone_load,
            Ventilation=ventilation_setting,
            **data,
            **kwargs,
        )

    @classmethod
    def from_epbunch(cls, ep_bunch, construct_parents=True, **kwargs):
        """Create a Zone object from an eppy 'ZONE' epbunch.

        Args:
            ep_bunch (eppy.bunch_subclass.EpBunch): The Zone EpBunch.
            construct_parents (bool): If False, skips construction of parents objects
                such as Constructions, Conditioning, etc.
        """
        assert (
            ep_bunch.key.lower() == "zone"
        ), f"Expected a `ZONE` epbunch, got {ep_bunch.key}"
        start_time = time.time()
        log('Constructing :class:`Zone` for zone "{}"'.format(ep_bunch.Name))

        def calc_zone_area(zone_ep):
            """Get zone area from simulation sql file."""
            with sqlite3.connect(zone_ep.theidf.sql_file) as conn:
                sql_query = """
                    SELECT t.Value 
                    FROM TabularDataWithStrings t 
                    WHERE TableName='Zone Summary' and ColumnName='Area' and RowName=?
                """
                (res,) = conn.execute(sql_query, (zone_ep.Name.upper(),)).fetchone()
            return float(res)

        def calc_zone_volume(zone_ep):
            """Get zone volume from simulation sql file."""
            with sqlite3.connect(zone_ep.theidf.sql_file) as conn:
                sql_query = (
                    "SELECT CAST(t.Value AS float) FROM TabularDataWithStrings t "
                    "WHERE TableName='Zone Summary' and ColumnName='Volume' and "
                    "RowName=?"
                )
                (res,) = conn.execute(sql_query, (zone_ep.Name.upper(),)).fetchone()
            return float(res)

        def calc_zone_occupants(zone_ep):
            """Get zone occupants from simulation sql file."""
            with sqlite3.connect(zone_ep.theidf.sql_file) as conn:
                sql_query = (
                    "SELECT CAST(t.Value AS float) FROM TabularDataWithStrings t "
                    "WHERE TableName='Average Outdoor Air During Occupied Hours' and ColumnName='Nominal Number of Occupants' and RowName=?"
                )

                fetchone = conn.execute(sql_query, (zone_ep.Name.upper(),)).fetchone()
                (res,) = fetchone or (0,)
            return res

        def calc_is_part_of_conditioned_floor_area(zone_ep):
            """Return True if zone is part of the conditioned floor area."""
            with sqlite3.connect(zone_ep.theidf.sql_file) as conn:
                sql_query = (
                    "SELECT t.Value FROM TabularDataWithStrings t WHERE "
                    "TableName='Zone Summary' and ColumnName='Conditioned (Y/N)' "
                    "and RowName=?"
                    ""
                )
                res = conn.execute(sql_query, (zone_ep.Name.upper(),)).fetchone()
            return "Yes" in res

        def calc_is_part_of_total_floor_area(zone_ep):
            """Return True if zone is part of the total floor area."""
            with sqlite3.connect(zone_ep.theidf.sql_file) as conn:
                sql_query = (
                    "SELECT t.Value FROM TabularDataWithStrings t WHERE "
                    "TableName='Zone Summary' and ColumnName='Part of "
                    "Total Floor Area (Y/N)' and RowName=?"
                )
                res = conn.execute(sql_query, (zone_ep.Name.upper(),)).fetchone()
            return "Yes" in res

        def calc_multiplier(zone_ep):
            """Get the zone multiplier from simulation sql."""
            with sqlite3.connect(zone_ep.theidf.sql_file) as conn:
                sql_query = (
                    "SELECT t.Value FROM TabularDataWithStrings t WHERE "
                    "TableName='Zone Summary' and "
                    "ColumnName='Multipliers' and RowName=?"
                )
                (res,) = conn.execute(sql_query, (zone_ep.Name.upper(),)).fetchone()
            return int(float(res))

        def is_core(zone_ep):
            # if all surfaces don't have boundary condition == "Outdoors"
            iscore = True
            for s in zone_ep.zonesurfaces:
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

        name = ep_bunch.Name
        zone = cls(
            Name=name,
            Category=ep_bunch.theidf.name,
            area=calc_zone_area(ep_bunch),
            volume=calc_zone_volume(ep_bunch),
            occupants=calc_zone_occupants(ep_bunch),
            is_part_of_conditioned_floor_area=calc_is_part_of_conditioned_floor_area(
                ep_bunch
            ),
            is_part_of_total_floor_area=calc_is_part_of_total_floor_area(ep_bunch),
            multiplier=calc_multiplier(ep_bunch),
            zone_surfaces=ep_bunch.zonesurfaces,
            is_core=is_core(ep_bunch),
            **kwargs,
        )

        if construct_parents:
            zone.Constructions = ZoneConstructionSet.from_zone(zone, **kwargs)
            zone.Conditioning = ZoneConditioning.from_zone(zone, ep_bunch, **kwargs)
            zone.Ventilation = VentilationSetting.from_zone(zone, ep_bunch, **kwargs)
            zone.DomesticHotWater = DomesticHotWaterSetting.from_zone(
                ep_bunch, **kwargs
            )
            zone.Loads = ZoneLoad.from_zone(zone, ep_bunch, **kwargs)
            internal_mass_from_zone = InternalMass.from_zone(ep_bunch)
            zone.InternalMassConstruction = internal_mass_from_zone.construction
            zone.InternalMassExposedPerFloorArea = (
                internal_mass_from_zone.total_area_exposed_to_zone
            )
            zone.Windows = WindowSetting.from_zone(zone, **kwargs)

        log(
            'completed Zone "{}" constructor in {:,.2f} seconds'.format(
                ep_bunch.Name, time.time() - start_time
            )
        )
        return zone

    def combine(self, other, weights=None, allow_duplicates=False):
        """Combine two ZoneDefinition objects together.

        Args:
            other (ZoneDefinition): The other object.
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
        if not self and not other:
            return None
        elif self == other:
            area = 1 if self.area + other.area == 2 else self.area + other.area
            volume = (
                1 if self.volume + other.volume == 2 else self.volume + other.volume
            )
            new_obj = self.duplicate()
            new_obj.area = area
            new_obj.volume = volume
            return new_obj
        elif not self or not other:
            new_obj = (self or other).duplicate()
            return new_obj

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
            Ventilation=VentilationSetting.combine(self.Ventilation, other.Ventilation),
            Windows=WindowSetting.combine(self.Windows, other.Windows, weights),
            DaylightMeshResolution=self.float_mean(
                other, "DaylightMeshResolution", weights=weights
            ),
            DaylightWorkplaneHeight=self.float_mean(
                other, "DaylightWorkplaneHeight", weights
            ),
            DomesticHotWater=DomesticHotWaterSetting.combine(
                self.DomesticHotWater, other.DomesticHotWater
            ),
            InternalMassConstruction=OpaqueConstruction.combine(
                self.InternalMassConstruction, other.InternalMassConstruction
            ),
            InternalMassExposedPerFloorArea=self.float_mean(
                other, "InternalMassExposedPerFloorArea", weights
            ),
            Loads=ZoneLoad.combine(self.Loads, other.Loads, weights),
        )
        new_obj = ZoneDefinition(**meta, **new_attr)

        # transfer aggregated values [volume, area, occupants] to new combined zone
        new_obj.volume = self.volume + other.volume
        new_obj.area = self.area + other.area
        new_obj.occupants = self.occupants + other.occupants

        if new_attr["Windows"]:  # Could be None
            new_attr["Windows"].area = new_obj.area

        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def validate(self):
        """Validate object and fill in missing values."""
        if self.InternalMassConstruction is None:
            internal_mass = InternalMass.generic_internalmass_from_zone(self)
            self.InternalMassConstruction = internal_mass.construction
            self.InternalMassExposedPerFloorArea = (
                internal_mass.total_area_exposed_to_zone
            )
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

    def mapping(self, validate=False):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate (bool): If True, try to validate object before returning the
                mapping.
        """
        if validate:
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
            area=self.area,
            volume=self.volume,
            occupants=self.occupants,
            is_part_of_conditioned_floor_area=self.is_part_of_conditioned_floor_area,
            is_part_of_total_floor_area=self.is_part_of_total_floor_area,
            multiplier=self.multiplier,
            zone_surfaces=self.zone_surfaces,
            is_core=self.is_core,
        )

    def __add__(self, other):
        """Return a combination of self and other."""
        return ZoneDefinition.combine(self, other)

    def __hash__(self):
        """Return the hash value of self."""
        return hash(self.id)

    def __eq__(self, other):
        """Assert self is equivalent to other."""
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

    def __copy__(self):
        """Return a copy of self."""
        return self.__class__(**self.mapping(validate=False))

    @property
    def children(self):
        return (
            self.Conditioning,
            self.Constructions,
            self.DomesticHotWater,
            self.InternalMassConstruction,
            self.Loads,
            self.Ventilation,
        )


def resolve_obco(ep_bunch):
    """Resolve the outside boundary condition of a surface.

    Args:
        ep_bunch (EpBunch): The surface for which we are identifying the boundary
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
    obc = ep_bunch.Outside_Boundary_Condition

    if obc.upper() == "ZONE":
        name = ep_bunch.Outside_Boundary_Condition_Object
        adj_zone = ep_bunch.theidf.getobject("ZONE", name)
        return None, adj_zone

    elif obc.upper() == "SURFACE":
        obco = ep_bunch.get_referenced_object("Outside_Boundary_Condition_Object")
        adj_zone = obco.theidf.getobject("ZONE", obco.Zone_Name)
        return obco, adj_zone
    else:
        return None, None


def is_core(zone):
    """Return true if zone is a core zone.

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
