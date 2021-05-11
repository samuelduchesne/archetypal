"""archetypal ZoneDefinition module."""

import collections
import sqlite3
import time

from eppy.bunch_subclass import BadEPFieldError
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


class ZoneDefinition(UmiBase):
    """Zone settings class.

    .. image:: ../images/template/zoneinfo-zone.png
    """

    __slots__ = (
        "_internal_mass_exposed_per_floor_area",
        "_constructions",
        "_loads",
        "_conditioning",
        "_ventilation",
        "_domestic_hot_water",
        "_windows",
        "_occupants",
        "_daylight_mesh_resolution",
        "_daylight_workplane_height",
        "_internal_mass_construction",
        "_is_part_of_conditioned_floor_area",
        "_is_part_of_total_floor_area",
        "_zone_surfaces",
        "_volume",
        "_multiplier",
        "_area",
        "_is_core",
    )

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
        area=1,
        volume=1,
        occupants=1,
        is_part_of_conditioned_floor_area=True,
        is_part_of_total_floor_area=True,
        multiplier=1,
        zone_surfaces=None,
        is_core=False,
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
            area (float):
            volume (float):
            occupants (float):
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

        self.Windows = Windows  # This is not used in to_dict()

        if zone_surfaces is None:
            zone_surfaces = []
        self.zone_surfaces = zone_surfaces
        self.area = area
        self.volume = volume
        self.occupants = occupants
        self.is_part_of_conditioned_floor_area = is_part_of_conditioned_floor_area
        self.is_part_of_total_floor_area = is_part_of_total_floor_area
        self.multiplier = multiplier
        self.is_core = is_core

    @property
    def Constructions(self):
        """Get or set the ZoneConstructionSet object."""
        return self._constructions

    @Constructions.setter
    def Constructions(self, value):
        if value is not None:
            assert isinstance(value, ZoneConstructionSet), (
                f"Input value error. Constructions must be of "
                f"type {ZoneConstructionSet}, not {type(value)}."
            )
        self._constructions = value

    @property
    def Loads(self):
        """Get or set the ZoneLoad object."""
        return self._loads

    @Loads.setter
    def Loads(self, value):
        if value is not None:
            assert isinstance(value, ZoneLoad), (
                f"Input value error. Loads must be of "
                f"type {ZoneLoad}, not {type(value)}."
            )
        self._loads = value

    @property
    def Conditioning(self):
        """Get or set the ZoneConditioning object."""
        return self._conditioning

    @Conditioning.setter
    def Conditioning(self, value):
        if value is not None:
            assert isinstance(value, ZoneConditioning), (
                f"Input value error. Conditioning must be of "
                f"type {ZoneConditioning}, not {type(value)}."
            )
        self._conditioning = value

    @property
    def Ventilation(self):
        """Get or set the VentilationSetting object."""
        return self._ventilation

    @Ventilation.setter
    def Ventilation(self, value):
        if value is not None:
            assert isinstance(value, VentilationSetting), (
                f"Input value error. Ventilation must be of "
                f"type {VentilationSetting}, not {type(value)}."
            )
        self._ventilation = value

    @property
    def DomesticHotWater(self):
        """Get or set the DomesticHotWaterSetting object."""
        return self._domestic_hot_water

    @DomesticHotWater.setter
    def DomesticHotWater(self, value):
        if value is not None:
            assert isinstance(value, DomesticHotWaterSetting), (
                f"Input value error. DomesticHotWater must be of "
                f"type {DomesticHotWaterSetting}, not {type(value)}."
            )
        self._domestic_hot_water = value

    @property
    def DaylightMeshResolution(self):
        """Get or set the daylight mesh resolution [m]."""
        return self._daylight_mesh_resolution

    @DaylightMeshResolution.setter
    def DaylightMeshResolution(self, value):
        self._daylight_mesh_resolution = validators.float(value, minimum=0)

    @property
    def DaylightWorkplaneHeight(self):
        """Get or set the DaylightWorkplaneHeight [m]."""
        return self._daylight_workplane_height

    @DaylightWorkplaneHeight.setter
    def DaylightWorkplaneHeight(self, value):
        self._daylight_workplane_height = validators.float(value, minimum=0)

    @property
    def InternalMassConstruction(self):
        """Get or set the internal mass construction object."""
        return self._internal_mass_construction

    @InternalMassConstruction.setter
    def InternalMassConstruction(self, value):
        if value is not None:
            assert isinstance(value, OpaqueConstruction), (
                f"Input value error. InternalMassConstruction must be of "
                f"type {OpaqueConstruction}, not {type(value)}."
            )
        self._internal_mass_construction = value

    @property
    def InternalMassExposedPerFloorArea(self):
        """Get or set the internal mass exposed per floor area [-]."""
        return self._internal_mass_exposed_per_floor_area

    @InternalMassExposedPerFloorArea.setter
    def InternalMassExposedPerFloorArea(self, value):
        self._internal_mass_exposed_per_floor_area = validators.float(value, minimum=0)

    @property
    def Windows(self):
        """Get or set the WindowSetting object."""
        return self._windows

    @Windows.setter
    def Windows(self, value):
        if value is not None:
            assert isinstance(value, WindowSetting), (
                f"Input value error. Windows must be of "
                f"type {WindowSetting}, not {type(value)}."
            )
        self._windows = value

    @property
    def occupants(self):
        """Get or set the number of occupants in the zone."""
        return self._occupants

    @occupants.setter
    def occupants(self, value):
        self._occupants = value

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

    @property
    def is_core(self):
        """Get or set if the zone is a core zone [bool]."""
        return self._is_core

    @is_core.setter
    def is_core(self, value):
        assert isinstance(value, bool), value
        self._is_core = value

    @property
    def multiplier(self):
        """Get or set the zone multiplier.

        Note: Zone multiplier is designed as a “multiplier” for floor
        area, zone loads, and energy consumed by internal gains.
        """
        return self._multiplier

    @multiplier.setter
    def multiplier(self, value):
        self._multiplier = validators.integer(value, minimum=1)

    @property
    def is_part_of_conditioned_floor_area(self):
        """Get or set is part of conditioned area [bool]."""
        return self._is_part_of_conditioned_floor_area

    @is_part_of_conditioned_floor_area.setter
    def is_part_of_conditioned_floor_area(self, value):
        assert isinstance(value, bool)
        self._is_part_of_conditioned_floor_area = value

    @property
    def is_part_of_total_floor_area(self):
        """Get or set is part od the total building floor area [bool]."""
        return self._is_part_of_total_floor_area

    @is_part_of_total_floor_area.setter
    def is_part_of_total_floor_area(self, value):
        assert isinstance(value, bool)
        self._is_part_of_total_floor_area = value

    @property
    def zone_surfaces(self):
        """Get or set the list of surfaces for this zone."""
        return self._zone_surfaces

    @zone_surfaces.setter
    def zone_surfaces(self, value):
        self._zone_surfaces = validators.iterable(value, allow_empty=True)

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
                    "SELECT t.Value FROM TabularDataWithStrings t "
                    "WHERE TableName='Zone Summary' and ColumnName='Volume' and "
                    "RowName=?"
                )
                (res,) = conn.execute(sql_query, (zone_ep.Name.upper(),)).fetchone()
            return float(res)

        def calc_zone_occupants(zone_ep):
            """Get zone occupants from simulation sql file."""
            with sqlite3.connect(zone_ep.theidf.sql_file) as conn:
                sql_query = (
                    "SELECT t.Value FROM TabularDataWithStrings t "
                    "WHERE TableName='Average Outdoor Air During Occupied Hours' and ColumnName='Nominal Number of Occupants' and RowName=?"
                )

                fetchone = conn.execute(sql_query, (zone_ep.Name.upper(),)).fetchone()
                (res,) = fetchone or (0,)
            return float(res)

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
        if not self.InternalMassConstruction:
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

    def mapping(self, validate=True):
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
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

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
