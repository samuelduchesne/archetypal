"""archetypal ZoneLoad."""

import collections
import logging as lg
import math
import sqlite3
from enum import Enum

import numpy as np
import pandas as pd
from sigfig import round
from validator_collection import checkers, validators

from archetypal import settings
from archetypal.template.schedule import UmiSchedule
from archetypal.template.umi_base import UmiBase
from archetypal.utils import log, reduce, timeit


class DimmingTypes(Enum):
    """DimmingType class."""

    Continuous = 0
    Off = 1
    Stepped = 2

    def __lt__(self, other):
        """Assert if self is lower then other."""
        return self._value_ < other._value_

    def __gt__(self, other):
        """Assert if self is greater then other."""
        return self._value_ > other._value_


class ZoneLoad(UmiBase):
    """Zone Loads.

    Important:
        Please note that the calculation of the equipment power density will sum
        up the electric equipment objects as well as the gas equipment objects.

    .. image:: ../images/template/zoneinfo-loads.png
    """

    __slots__ = (
        "_dimming_type",
        "_equipment_availability_schedule",
        "_lights_availability_schedule",
        "_occupancy_schedule",
        "_equipment_power_density",
        "_illuminance_target",
        "_lighting_power_density",
        "_people_density",
        "_is_equipment_on",
        "_is_lighting_on",
        "_is_people_on",
        "_area",
        "_volume",
    )

    def __init__(
        self,
        Name,
        EquipmentPowerDensity=0,
        EquipmentAvailabilitySchedule=None,
        LightingPowerDensity=0,
        LightsAvailabilitySchedule=None,
        PeopleDensity=0,
        OccupancySchedule=None,
        IsEquipmentOn=True,
        IsLightingOn=True,
        IsPeopleOn=True,
        DimmingType=DimmingTypes.Continuous,
        IlluminanceTarget=500,
        area=1,
        volume=1,
        **kwargs,
    ):
        """Initialize a new ZoneLoad object.

        Args:
            DimmingType (int): Different types to dim the lighting to respect the
                IlluminanceTarget and taking into account the daylight illuminance:
                    - Continuous = 0, the overhead lights dim continuously and
                      linearly from (maximum electric power, maximum light output) to (
                      minimum electric power, minimum light output) as the daylight
                      illuminance increases. The lights stay on at the minimum point
                      with further increase in the daylight illuminance.
                    - Off = 1, Lights switch off completely when the minimum
                      dimming point is reached.
                    - Stepped = 2, the electric power input and light output vary
                      in discrete, equally spaced steps.
            EquipmentAvailabilitySchedule (UmiSchedule): The name of
                the schedule (Day | Week | Year) that modifies the design level
                parameter for electric equipment.
            EquipmentPowerDensity (float): Equipment Power Density in the zone
                (W/m²).
            IlluminanceTarget (float): Number of lux to be respected in the zone
            LightingPowerDensity (float): Lighting Power Density in the zone
                (W/m²).
            LightsAvailabilitySchedule (UmiSchedule): The name of the
                schedule (Day | Week | Year) that modifies the design level
                parameter for lighting.
            OccupancySchedule (UmiSchedule): The name of the schedule
                (Day | Week | Year) that modifies the number of people parameter
                for electric equipment.
            IsEquipmentOn (bool): If True, heat gains from Equipment are taken
                into account for the zone's load calculation.
            IsLightingOn (bool): If True, heat gains from Lights are taken into
                account for the zone's load calculation.
            IsPeopleOn (bool): If True, heat gains from People are taken into
                account for the zone's load calculation.
            PeopleDensity (float): Density of people in the zone (people/m²).
            area (float): The floor area assiciated to this zone load object.
            **kwargs: Other keywords passed to the parent constructor :class:`UmiBase`.
        """
        super(ZoneLoad, self).__init__(Name, **kwargs)

        self.EquipmentPowerDensity = EquipmentPowerDensity
        self.EquipmentAvailabilitySchedule = EquipmentAvailabilitySchedule
        self.LightingPowerDensity = LightingPowerDensity
        self.LightsAvailabilitySchedule = LightsAvailabilitySchedule
        self.PeopleDensity = PeopleDensity
        self.OccupancySchedule = OccupancySchedule
        self.IsEquipmentOn = IsEquipmentOn
        self.IsLightingOn = IsLightingOn
        self.IsPeopleOn = IsPeopleOn
        self.DimmingType = DimmingTypes(DimmingType)
        self.IlluminanceTarget = IlluminanceTarget
        self.area = area
        self.volume = volume

    @property
    def DimmingType(self):
        """Get or set the dimming type.

        Hint:
            To set the value an int or a string is supported.
            Choices are (<DimmingTypes.Continuous: 0>, <DimmingTypes.Off: 1>,
            <DimmingTypes.Stepped: 2>)
        """
        return self._dimming_type

    @DimmingType.setter
    def DimmingType(self, value):
        if checkers.is_string(value):
            assert DimmingTypes[value], (
                f"Input value error for '{value}'. "
                f"Expected one of {tuple(a for a in DimmingTypes)}"
            )
            self._dimming_type = DimmingTypes[value]
        elif checkers.is_numeric(value):
            assert DimmingTypes[value], (
                f"Input value error for '{value}'. "
                f"Expected one of {tuple(a for a in DimmingTypes)}"
            )
            self._dimming_type = DimmingTypes(value)
        elif isinstance(value, DimmingTypes):
            self._dimming_type = value
        else:
            raise ValueError(f"Could not set DimmingType with value '{value}'")

    @property
    def EquipmentAvailabilitySchedule(self):
        """Get or set the equipment availability schedule."""
        return self._equipment_availability_schedule

    @EquipmentAvailabilitySchedule.setter
    def EquipmentAvailabilitySchedule(self, value):
        if value is not None:
            assert isinstance(value, UmiSchedule), (
                f"Input value error for '{value}'. Value must be of type '"
                f"{UmiSchedule}', not {type(value)}"
            )
            # set quantity on schedule as well
            value.quantity = self.EquipmentPowerDensity
        self._equipment_availability_schedule = value

    @property
    def EquipmentPowerDensity(self):
        """Get or set the equipment power density [W/m²]."""
        return self._equipment_power_density

    @EquipmentPowerDensity.setter
    def EquipmentPowerDensity(self, value):
        self._equipment_power_density = validators.float(
            value, minimum=0, allow_empty=True
        )

    @property
    def IlluminanceTarget(self):
        """Get or set the illuminance target [lux]."""
        return self._illuminance_target

    @IlluminanceTarget.setter
    def IlluminanceTarget(self, value):
        self._illuminance_target = validators.float(value, minimum=0)

    @property
    def LightingPowerDensity(self):
        """Get or set the lighting power density [W/m²]."""
        return self._lighting_power_density

    @LightingPowerDensity.setter
    def LightingPowerDensity(self, value):
        self._lighting_power_density = validators.float(
            value, minimum=0, allow_empty=True
        )

    @property
    def LightsAvailabilitySchedule(self) -> UmiSchedule:
        """Get or set the lights availability schedule."""
        return self._lights_availability_schedule

    @LightsAvailabilitySchedule.setter
    def LightsAvailabilitySchedule(self, value):
        if value is not None:
            assert isinstance(value, UmiSchedule), (
                f"Input value error for '{value}'. Value must be of type '"
                f"{UmiSchedule}', not {type(value)}"
            )
            # set quantity on schedule as well
            value.quantity = self.LightingPowerDensity
        self._lights_availability_schedule = value

    @property
    def OccupancySchedule(self) -> UmiSchedule:
        """Get or set the occupancy schedule."""
        return self._occupancy_schedule

    @OccupancySchedule.setter
    def OccupancySchedule(self, value):
        if value is not None:
            assert isinstance(value, UmiSchedule), (
                f"Input value error for '{value}'. Value must be if type '"
                f"{UmiSchedule}', not {type(value)}"
            )
            # set quantity on schedule as well
            value.quantity = self.PeopleDensity
        self._occupancy_schedule = value

    @property
    def PeopleDensity(self):
        """Get or set the people density [ppl/m²]."""
        return self._people_density

    @PeopleDensity.setter
    def PeopleDensity(self, value):
        self._people_density = validators.float(value, minimum=0)

    @property
    def IsEquipmentOn(self):
        """Get or set the use of equipment [bool]."""
        return self._is_equipment_on

    @IsEquipmentOn.setter
    def IsEquipmentOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsEquipmentOn must "
            f"be a boolean, not a {type(value)}"
        )
        self._is_equipment_on = value

    @property
    def IsLightingOn(self):
        """Get or set the use of lighting [bool]."""
        return self._is_lighting_on

    @IsLightingOn.setter
    def IsLightingOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsLightingOn must "
            f"be a boolean, not a {type(value)}"
        )
        self._is_lighting_on = value

    @property
    def IsPeopleOn(self):
        """Get or set people [bool]."""
        return self._is_people_on

    @IsPeopleOn.setter
    def IsPeopleOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsPeopleOn must "
            f"be a boolean, not a {type(value)}"
        )
        self._is_people_on = value

    @property
    def area(self):
        """Get or set the floor area of the zone associated to this zone load [m²]."""
        return self._area

    @area.setter
    def area(self, value):
        self._area = validators.float(value, minimum=0)

    @property
    def volume(self):
        """Get or set the volume of the zone associated to this zone load [m³]."""
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = validators.float(value, minimum=0)

    @classmethod
    def from_dict(cls, data, schedules, **kwargs):
        """Create a ZoneLoad from a dictionary.

        Args:
            data (dict): A python dictionary with the structure shown bellow.
            schedules (dict): A python dictionary of UmiSchedules with their id as keys.
            **kwargs: keywords passed to parent constructors.

        .. code-block:: python

            {
              "$id": "172",
              "DimmingType": 1,
              "EquipmentAvailabilitySchedule": {
                "$ref": "147"
              },
              "EquipmentPowerDensity": 8.0,
              "IlluminanceTarget": 500.0,
              "LightingPowerDensity": 12.0,
              "LightsAvailabilitySchedule": {
                "$ref": "146"
              },
              "OccupancySchedule": {
                "$ref": "145"
              },
              "IsEquipmentOn": true,
              "IsLightingOn": true,
              "IsPeopleOn": true,
              "PeopleDensity": 0.055,
              "Category": "Office Spaces",
              "Comments": null,
              "DataSource": "MIT_SDL",
              "Name": "B_Off_0 loads"
            },
        """
        _id = data.pop("$id")
        return cls(
            id=_id,
            EquipmentAvailabilitySchedule=schedules[
                data.pop("EquipmentAvailabilitySchedule")["$ref"]
            ],
            LightsAvailabilitySchedule=schedules[
                data.pop("LightsAvailabilitySchedule")["$ref"]
            ],
            OccupancySchedule=schedules[data.pop("OccupancySchedule")["$ref"]],
            **data,
            **kwargs,
        )

    @classmethod
    @timeit
    def from_zone(cls, zone, zone_ep, **kwargs):
        """Create a ZoneLoad object from a :class:`ZoneDefinition`.

        Args:
            zone_ep:
            zone (ZoneDefinition): zone to gets information from
            kwargs: keywords passed to the parent constructor.
        """
        # If Zone is not part of total area, it should not have a ZoneLoad object.
        if not zone._is_part_of_total_floor_area:
            return None

        # Get schedule index for different loads and create ZoneLoad arguments
        # Verify if Equipment in zone

        # create database connection with sqlite3
        with sqlite3.connect(str(zone_ep.theidf.sql_file)) as conn:
            sql_query = "select ifnull(ZoneIndex, null) from Zones where ZoneName=?"
            t = (zone.Name.upper(),)
            c = conn.cursor()
            c.execute(sql_query, t)
            (zone_index,) = c.fetchone()

            sql_query = "select t.* from NominalElectricEquipment t where ZoneIndex=?"
            nominal_elec = pd.read_sql(sql_query, conn, params=(zone_index,))

            sql_query = "select t.* from NominalGasEquipment t where ZoneIndex=?"
            nominal_gas = pd.read_sql(sql_query, conn, params=(zone_index,))

            def get_schedule(series):
                """Compute the schedule with quantity for nominal equipment series."""
                sched = series["ScheduleIndex"]
                sql_query = (
                    "select t.ScheduleName, t.ScheduleType as M from "
                    "Schedules t where ScheduleIndex=?"
                )
                sched_name, sched_type = c.execute(sql_query, (int(sched),)).fetchone()
                level_ = float(series["DesignLevel"])
                if level_ > 0:
                    return UmiSchedule.from_epbunch(
                        zone_ep.theidf.schedules_dict[sched_name.upper()],
                        quantity=level_,
                    )

            schedules = []
            if not nominal_elec.empty:
                # compute schedules series
                elec_scds = nominal_elec.apply(get_schedule, axis=1).to_list()
                elec_scds = list(filter(None, elec_scds))
                schedules.extend(elec_scds)

            if not nominal_gas.empty:
                # compute schedules series
                gas_scds = nominal_gas.apply(get_schedule, axis=1).to_list()
                gas_scds = list(filter(None, gas_scds))
                schedules.extend(gas_scds)

            if schedules:
                EquipmentAvailabilitySchedule = reduce(
                    UmiSchedule.combine,
                    schedules,
                    quantity=True,
                )
                EquipmentPowerDensity = (
                    EquipmentAvailabilitySchedule.quantity / zone.area
                )
            else:
                EquipmentAvailabilitySchedule = None
                EquipmentPowerDensity = np.NaN

            # Verifies if Lights in zone
            sql_query = "select t.* from NominalLighting t where ZoneIndex=?"
            nominal_lighting = pd.read_sql(sql_query, conn, params=(zone_index,))

            lighting_schedules = []
            if not nominal_lighting.empty:
                # compute schedules series
                light_scds = nominal_lighting.apply(get_schedule, axis=1)
                lighting_schedules.extend(light_scds)

            if lighting_schedules:
                LightsAvailabilitySchedule = reduce(
                    UmiSchedule.combine,
                    lighting_schedules,
                    quantity=True,
                )
                LightingPowerDensity = LightsAvailabilitySchedule.quantity / zone.area
            else:
                LightsAvailabilitySchedule = None
                LightingPowerDensity = np.NaN

            # Verifies if People in zone

            def get_schedule(series):
                """Compute schedule with quantity for nominal equipment series."""
                sched = series["NumberOfPeopleScheduleIndex"]
                sql_query = (
                    "select t.ScheduleName, t.ScheduleType as M from "
                    "Schedules t where ScheduleIndex=?"
                )
                sched_name, sched_type = c.execute(sql_query, (int(sched),)).fetchone()
                return UmiSchedule.from_epbunch(
                    zone_ep.theidf.schedules_dict[sched_name.upper()],
                    quantity=series["NumberOfPeople"],
                )

            sql_query = "select t.* from NominalPeople t where ZoneIndex=?"
            nominal_people = pd.read_sql(sql_query, conn, params=(zone_index,))

            occupancy_schedules = []
            if not nominal_people.empty:
                # compute schedules series
                occ_scds = nominal_people.apply(get_schedule, axis=1)
                occupancy_schedules.extend(occ_scds)

            if occupancy_schedules:
                OccupancySchedule = reduce(
                    UmiSchedule.combine,
                    occupancy_schedules,
                    quantity=lambda x: sum(obj.quantity for obj in x),
                )
                PeopleDensity = OccupancySchedule.quantity / zone.area
            else:
                OccupancySchedule = None
                PeopleDensity = np.NaN

        name = zone.Name + "_ZoneLoad"
        z_load = cls(
            Name=name,
            DimmingType=_resolve_dimming_type(zone, zone_ep),
            EquipmentAvailabilitySchedule=EquipmentAvailabilitySchedule,
            EquipmentPowerDensity=EquipmentPowerDensity,
            IlluminanceTarget=_resolve_illuminance_target(zone, zone_ep),
            LightingPowerDensity=LightingPowerDensity,
            LightsAvailabilitySchedule=LightsAvailabilitySchedule,
            OccupancySchedule=OccupancySchedule,
            IsEquipmentOn=EquipmentPowerDensity > 0,
            IsLightingOn=LightingPowerDensity > 0,
            IsPeopleOn=PeopleDensity > 0,
            PeopleDensity=PeopleDensity,
            Category=zone.DataSource,
            area=zone.area,
            volume=zone.volume,
            **kwargs,
        )
        return z_load

    def combine(self, other, weights=None):
        """Combine two ZoneLoad objects together. Returns a new object.

        Args:
            other (ZoneLoad): The other ZoneLoad object.
            weights (list-like, optional): A list-like object of len 2. If None,
                the `settings.zone_weight` of the objects is used.

        Returns:
            (ZoneLoad): the combined ZoneLoad object.
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
            DimmingType=max(self.DimmingType, other.DimmingType),
            EquipmentAvailabilitySchedule=UmiSchedule.combine(
                self.EquipmentAvailabilitySchedule,
                other.EquipmentAvailabilitySchedule,
                weights=[self.area, other.area],
                quantity=True,
            ),
            EquipmentPowerDensity=self.float_mean(
                other, "EquipmentPowerDensity", weights
            ),
            IlluminanceTarget=self.float_mean(other, "IlluminanceTarget", weights),
            LightingPowerDensity=self.float_mean(
                other, "LightingPowerDensity", weights
            ),
            LightsAvailabilitySchedule=UmiSchedule.combine(
                self.LightsAvailabilitySchedule,
                other.LightsAvailabilitySchedule,
                weights=[self.area, other.area],
                quantity=True,
            ),
            OccupancySchedule=UmiSchedule.combine(
                self.OccupancySchedule,
                other.OccupancySchedule,
                weights=[self.area, other.area],
                quantity=True,
            ),
            IsEquipmentOn=any([self.IsEquipmentOn, other.IsEquipmentOn]),
            IsLightingOn=any([self.IsLightingOn, other.IsLightingOn]),
            IsPeopleOn=any([self.IsPeopleOn, other.IsPeopleOn]),
            PeopleDensity=self.float_mean(other, "PeopleDensity", weights),
        )

        new_obj = self.__class__(
            **meta, **new_attr, allow_duplicates=self.allow_duplicates
        )
        new_obj.area = self.area + other.area
        new_obj.volume = self.volume + other.volume
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def validate(self):
        """Validate object and fill in missing values."""
        if not self.DimmingType:
            self.DimmingType = DimmingTypes.Continuous
        if not self.EquipmentAvailabilitySchedule:
            self.EquipmentAvailabilitySchedule = UmiSchedule.constant_schedule()
        if not self.EquipmentPowerDensity:
            self.EquipmentPowerDensity = 0
        if not self.IlluminanceTarget:
            self.IlluminanceTarget = 500
        if not self.LightingPowerDensity:
            self.LightingPowerDensity = 0
        if not self.LightsAvailabilitySchedule:
            self.LightsAvailabilitySchedule = UmiSchedule.constant_schedule()
        if not self.OccupancySchedule:
            self.OccupancySchedule = UmiSchedule.constant_schedule()
        if not self.IsEquipmentOn:
            self.IsEquipmentOn = False
        if not self.IsLightingOn:
            self.IsLightingOn = False
        if not self.IsPeopleOn:
            self.IsPeopleOn = False
        if not self.PeopleDensity:
            self.PeopleDensity = 0
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
            DimmingType=self.DimmingType,
            EquipmentAvailabilitySchedule=self.EquipmentAvailabilitySchedule,
            EquipmentPowerDensity=self.EquipmentPowerDensity,
            IlluminanceTarget=self.IlluminanceTarget,
            LightingPowerDensity=self.LightingPowerDensity,
            LightsAvailabilitySchedule=self.LightsAvailabilitySchedule,
            OccupancySchedule=self.OccupancySchedule,
            IsEquipmentOn=self.IsEquipmentOn,
            IsLightingOn=self.IsLightingOn,
            IsPeopleOn=self.IsPeopleOn,
            PeopleDensity=self.PeopleDensity,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def to_dict(self):
        """Return ZoneLoad dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["DimmingType"] = self.DimmingType.value
        data_dict[
            "EquipmentAvailabilitySchedule"
        ] = self.EquipmentAvailabilitySchedule.to_ref()
        data_dict["EquipmentPowerDensity"] = (
            round(self.EquipmentPowerDensity, 3)
            if not math.isnan(self.EquipmentPowerDensity)
            else 0
        )
        data_dict["IlluminanceTarget"] = round(self.IlluminanceTarget, 3)
        data_dict["LightingPowerDensity"] = (
            round(self.LightingPowerDensity, 3)
            if not math.isnan(self.LightingPowerDensity)
            else 0
        )
        data_dict[
            "LightsAvailabilitySchedule"
        ] = self.LightsAvailabilitySchedule.to_ref()
        data_dict["OccupancySchedule"] = self.OccupancySchedule.to_ref()
        data_dict["IsEquipmentOn"] = self.IsEquipmentOn
        data_dict["IsLightingOn"] = self.IsLightingOn
        data_dict["IsPeopleOn"] = self.IsPeopleOn
        data_dict["PeopleDensity"] = (
            round(self.PeopleDensity, 3) if not math.isnan(self.PeopleDensity) else 0
        )
        data_dict["Category"] = self.Category
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    def to_epbunch(self, idf, zone_name):
        """Convert the zone load to epbunch given an idf model and a zone name.

        Args:
            idf (IDF): The idf model. epbunches will be added to this model.
            zone_name (str): The name of the zone in the idf model.

        .. code-block:: python

            People,
                People Perim,             !- Name
                Perim,                    !- Zone or ZoneList Name
                B_Off_Y_Occ,              !- Number of People Schedule Name
                People/Area,              !- Number of People Calculation Method
                ,                         !- Number of People
                0.055,                    !- People per Zone Floor Area
                ,                         !- Zone Floor Area per Person
                0.3,                      !- Fraction Radiant
                AUTOCALCULATE,            !- Sensible Heat Fraction
                PerimPeopleActivity,      !- Activity Level Schedule Name
                3.82e-08,                 !- Carbon Dioxide Generation Rate
                No,                       !- Enable ASHRAE 55 Comfort Warnings
                ZoneAveraged,             !- Mean Radiant Temperature Calculation Type
                ,                         !- Surface NameAngle Factor List Name
                PerimWorkEfficiency,      !- Work Efficiency Schedule Name
                DynamicClothingModelASHRAE55,    !- Clothing Insulation Calculation Method
                ,                         !- Clothing Insulation Calculation Method Schedule Name
                ,                         !- Clothing Insulation Schedule Name
                PerimAirVelocity,         !- Air Velocity Schedule Name
                AdaptiveASH55;            !- Thermal Comfort Model 1 Type

            Lights,
                Perim General lighting,    !- Name
                Perim,                    !- Zone or ZoneList Name
                B_Off_Y_Lgt,              !- Schedule Name
                Watts/Area,               !- Design Level Calculation Method
                ,                         !- Lighting Level
                12,                       !- Watts per Zone Floor Area
                ,                         !- Watts per Person
                0,                        !- Return Air Fraction
                0.42,                     !- Fraction Radiant
                0.18,                     !- Fraction Visible
                1,                        !- Fraction Replaceable
                ;                         !- EndUse Subcategory

            ElectricEquipment,
                Perim Equipment 1,        !- Name
                Perim,                    !- Zone or ZoneList Name
                B_Off_Y_Plg,              !- Schedule Name
                Watts/Area,               !- Design Level Calculation Method
                ,                         !- Design Level
                8,                        !- Watts per Zone Floor Area
                ,                         !- Watts per Person
                0,                        !- Fraction Latent
                0.2,                      !- Fraction Radiant
                0,                        !- Fraction Lost
                ;                         !- EndUse Subcategory

        Returns:
            EpBunch: The EpBunch object added to the idf model.
        """
        people = idf.newidfobject(
            "PEOPLE",
            Name=self.Name,
            Zone_or_ZoneList_Name=zone_name,
            Number_of_People_Schedule_Name=self.OccupancySchedule.to_epbunch(idf).Name,
            Number_of_People_Calculation_Method="People/Area",
            People_per_Zone_Floor_Area=self.PeopleDensity,
            Fraction_Radiant=0.3,
            Sensible_Heat_Fraction="AUTOCALCULATE",
            Activity_Level_Schedule_Name=idf.newidfobject(
                "SCHEDULE:CONSTANT", Name="PeopleActivity", Hourly_Value=125.28
            ).Name,
            Carbon_Dioxide_Generation_Rate=3.82e-08,
            Enable_ASHRAE_55_Comfort_Warnings="No",
            Mean_Radiant_Temperature_Calculation_Type="ZoneAveraged",
            Work_Efficiency_Schedule_Name=idf.newidfobject(
                "SCHEDULE:CONSTANT", Name="WorkEfficiency", Hourly_Value=0
            ).Name,
            Clothing_Insulation_Calculation_Method="DynamicClothingModelASHRAE55",
            Air_Velocity_Schedule_Name=idf.newidfobject(
                "SCHEDULE:CONSTANT", Name="AirVelocity", Hourly_Value=0.2
            ).Name,
        )
        lights = idf.newidfobject(
            key="LIGHTS",
            Name=self.Name,
            Zone_or_ZoneList_Name=zone_name,
            Schedule_Name=self.LightsAvailabilitySchedule.to_epbunch(idf).Name,
            Design_Level_Calculation_Method="Watts/Area",
            Watts_per_Zone_Floor_Area=self.LightingPowerDensity,
            Return_Air_Fraction=0,
            Fraction_Radiant=0.42,
            Fraction_Visible=0.18,
            Fraction_Replaceable=1,
        )
        equipment = idf.newidfobject(
            "ELECTRICEQUIPMENT",
            Name=self.Name,
            Zone_or_ZoneList_Name=zone_name,
            Schedule_Name=self.EquipmentAvailabilitySchedule.to_epbunch(idf).Name,
            Design_Level_Calculation_Method="Watts/Area",
            Watts_per_Zone_Floor_Area=self.EquipmentPowerDensity,
            Fraction_Latent=0,
            Fraction_Radiant=0.2,
            Fraction_Lost=0,
        )
        return people, lights, equipment

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(
            **self.mapping(validate=False), area=self.area, volume=self.volume
        )

    def __add__(self, other):
        """Combine self and other."""
        return self.combine(other)

    def __hash__(self):
        """Return the hash value of self."""
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __key__(self):
        """Get a tuple of attributes. Useful for hashing and comparing."""
        return (
            self.DimmingType,
            self.EquipmentAvailabilitySchedule,
            self.EquipmentPowerDensity,
            self.IlluminanceTarget,
            self.LightingPowerDensity,
            self.LightsAvailabilitySchedule,
            self.OccupancySchedule,
            self.IsEquipmentOn,
            self.IsLightingOn,
            self.IsPeopleOn,
            self.PeopleDensity,
        )

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, ZoneLoad):
            return NotImplemented
        else:
            return self.__key__() == other.__key__()


def _resolve_dimming_type(zone, zone_ep):
    """Resolve the dimming type for the Zone object.

    Args:
        zone_ep:
    """
    # First, retrieve the list of Daylighting objects for this zone. Uses the eppy
    # `getreferingobjs` method.
    possible_ctrls = zone_ep.getreferingobjs(
        iddgroups=["Daylighting"], fields=["Zone_Name"]
    )
    # Then, if there are controls
    if possible_ctrls:
        # Filter only the "Daylighting:Controls"
        ctrls = [
            ctrl
            for ctrl in possible_ctrls
            if ctrl.key.upper() == "Daylighting:Controls".upper()
        ]
        ctrl_types = [ctrl["Lighting_Control_Type"] for ctrl in ctrls]

        # There should only be one control per zone. A set of controls should return 1.
        if len(set(ctrl_types)) == 1:
            dimming_type, *_ = set(ctrl_types)
            if dimming_type.lower() not in ["continuous", "stepped"]:
                raise ValueError(
                    f"A dimming type of type '{dimming_type}' for zone '{zone.Name}' is not yet supported in UMI"
                )
            else:
                log(f"Dimming type for zone '{zone.Name}' set to '{dimming_type}'")
                return DimmingTypes[dimming_type]  # Return first element
        else:
            raise ValueError(
                "Could not resolve more than one dimming types for Zone {}. "
                "Make sure there is only one".format(zone.Name)
            )
    else:
        # Else, there are no dimming controls => set to "Off".
        log(
            "No dimming type found for zone {}. Setting as Off".format(zone.Name),
            lg.DEBUG,
        )
        return DimmingTypes.Off


def _resolve_illuminance_target(zone, zone_ep):
    """Resolve the illuminance target for the Zone object.

    Args:
        zone_ep:
    """
    # First, retrieve the list of Daylighting objects for this zone. Uses the eppy
    # `getreferingobjs` method.
    possible_ctrls = zone_ep.getreferingobjs(
        iddgroups=["Daylighting"], fields=["Zone_Name"]
    )
    # Then, if there are controls
    if possible_ctrls:
        # Filter only the "Daylighting:Controls"
        ctrls = [
            ctrl
            for ctrl in possible_ctrls
            if ctrl.key.upper() == "Daylighting:Controls".upper()
        ]
        ctrl_types = [
            ctrl["Illuminance_Setpoint_at_Reference_Point_1"] for ctrl in ctrls
        ]

        # There should only be one control per zone. A set of controls should return 1.
        if len(set(ctrl_types)) == 1:
            dimming_type = next(iter(set(ctrl_types)))
            log(f"Illuminance target for zone '{zone.Name}' set to '{dimming_type}'")
            return float(dimming_type)  # Return first element
        else:
            raise ValueError(
                "Could not resolve more than one illuminance targets for Zone {}. "
                "Make sure there is only one".format(zone.Name)
            )
    else:
        # Else, there are no dimming controls => set to "Off".
        log(
            "No illuminance target found for zone {}. Setting to default 500 "
            "lux".format(zone.Name),
            lg.DEBUG,
        )
        return 500
