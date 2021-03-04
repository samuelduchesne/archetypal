################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import logging as lg
import math
import sqlite3
from enum import Enum

import pandas as pd
from deprecation import deprecated
from sigfig import round

import archetypal
from archetypal import log, settings, timeit
from archetypal.template import UmiBase, UmiSchedule, UniqueName
from archetypal.utils import reduce
import numpy as np


class DimmingTypes(Enum):
    Continuous = 0
    Off = 1
    Stepped = 2

    def __lt__(self, other):
        return self._value_ < other._value_

    def __gt__(self, other):
        return self._value_ > other._value_


class ZoneLoad(UmiBase):
    """Zone Loads

    Important:
        Please note that the calculation of the equipment power density will sum
        up the electric equipment objects as well as the gas equipment objects.

    .. image:: ../images/template/zoneinfo-loads.png
    """

    def __init__(
        self,
        DimmingType=DimmingTypes.Continuous,
        EquipmentAvailabilitySchedule=None,
        EquipmentPowerDensity=0,
        IlluminanceTarget=500,
        LightingPowerDensity=0,
        LightsAvailabilitySchedule=None,
        OccupancySchedule=None,
        IsEquipmentOn=True,
        IsLightingOn=True,
        IsPeopleOn=True,
        PeopleDensity=0,
        **kwargs,
    ):
        """Initialize a new ZoneLoad object

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
            **kwargs: Other keywords passed to the parent constructor :class:`UmiBase`.
        """
        super(ZoneLoad, self).__init__(**kwargs)
        self.DimmingType = DimmingTypes(DimmingType)
        self.EquipmentAvailabilitySchedule = EquipmentAvailabilitySchedule
        self.EquipmentPowerDensity = EquipmentPowerDensity
        self.IlluminanceTarget = IlluminanceTarget
        self.LightingPowerDensity = LightingPowerDensity
        self.LightsAvailabilitySchedule = LightsAvailabilitySchedule
        self.OccupancySchedule = OccupancySchedule
        self.IsEquipmentOn = IsEquipmentOn
        self.IsLightingOn = IsLightingOn
        self.IsPeopleOn = IsPeopleOn
        self.PeopleDensity = PeopleDensity

        self._belongs_to_zone = kwargs.get("zone", None)

    @property
    def EquipmentPowerDensity(self):
        if math.isnan(self._EquipmentPowerDensity):
            return self._EquipmentPowerDensity
        return round(float(self._EquipmentPowerDensity), decimals=3)

    @EquipmentPowerDensity.setter
    def EquipmentPowerDensity(self, value):
        self._EquipmentPowerDensity = value

    @property
    def IlluminanceTarget(self):
        return float(self._IlluminanceTarget)

    @IlluminanceTarget.setter
    def IlluminanceTarget(self, value):
        self._IlluminanceTarget = value

    @property
    def LightingPowerDensity(self):
        if math.isnan(self._LightingPowerDensity):
            return self._LightingPowerDensity
        return round(float(self._LightingPowerDensity), decimals=3)

    @LightingPowerDensity.setter
    def LightingPowerDensity(self, value):
        self._LightingPowerDensity = value

    @property
    def PeopleDensity(self):
        if math.isnan(self._PeopleDensity):
            return self._PeopleDensity
        return round(float(self._PeopleDensity), decimals=3)

    @PeopleDensity.setter
    def PeopleDensity(self, value):
        self._PeopleDensity = value

    def __add__(self, other):
        """
        Args:
            other (Zone):
        """
        return self.combine(other)

    def __hash__(self):
        return hash(
            (self.__class__.__name__, getattr(self, "Name", None), self.DataSource)
        )

    def __eq__(self, other):
        if not isinstance(other, ZoneLoad):
            return NotImplemented
        else:
            return all(
                [
                    self.DimmingType == other.DimmingType,
                    self.EquipmentAvailabilitySchedule
                    == other.EquipmentAvailabilitySchedule,
                    self.EquipmentPowerDensity == other.EquipmentPowerDensity,
                    self.IlluminanceTarget == other.IlluminanceTarget,
                    self.LightingPowerDensity == other.LightingPowerDensity,
                    self.LightsAvailabilitySchedule == other.LightsAvailabilitySchedule,
                    self.OccupancySchedule == other.OccupancySchedule,
                    self.IsEquipmentOn == other.IsEquipmentOn,
                    self.IsLightingOn == other.IsLightingOn,
                    self.IsPeopleOn == other.IsPeopleOn,
                    self.PeopleDensity == other.PeopleDensity,
                ]
            )

    @classmethod
    @deprecated(
        deprecated_in="1.3.1",
        removed_in="1.5",
        current_version=archetypal.__version__,
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
        zl = cls(*args, **kwargs)

        cool_schd = kwargs.get("EquipmentAvailabilitySchedule", None)
        zl.EquipmentAvailabilitySchedule = zl.get_ref(cool_schd)
        heat_schd = kwargs.get("LightsAvailabilitySchedule", None)
        zl.LightsAvailabilitySchedule = zl.get_ref(heat_schd)
        mech_schd = kwargs.get("OccupancySchedule", None)
        zl.OccupancySchedule = zl.get_ref(mech_schd)

        return zl

    def to_json(self):
        """Convert class properties to dict"""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["DimmingType"] = self.DimmingType.value
        data_dict[
            "EquipmentAvailabilitySchedule"
        ] = self.EquipmentAvailabilitySchedule.to_dict()
        data_dict["EquipmentPowerDensity"] = round(self.EquipmentPowerDensity, 3)
        data_dict["IlluminanceTarget"] = round(self.IlluminanceTarget, 3)
        data_dict["LightingPowerDensity"] = round(self.LightingPowerDensity, 3)
        data_dict[
            "LightsAvailabilitySchedule"
        ] = self.LightsAvailabilitySchedule.to_dict()
        data_dict["OccupancySchedule"] = self.OccupancySchedule.to_dict()
        data_dict["IsEquipmentOn"] = self.IsEquipmentOn
        data_dict["IsLightingOn"] = self.IsLightingOn
        data_dict["IsPeopleOn"] = self.IsPeopleOn
        data_dict["PeopleDensity"] = round(self.PeopleDensity, 3)
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    @classmethod
    @timeit
    def from_zone(cls, zone, **kwargs):
        """
        Args:
            zone (ZoneDefinition): zone to gets information from
        """
        # If Zone is not part of total area, it should not have a ZoneLoad object.
        if not zone._is_part_of_total_floor_area:
            return None

        # Get schedule index for different loads and create ZoneLoad arguments
        # Verify if Equipment in zone

        # create database connection with sqlite3
        with sqlite3.connect(str(zone.idf.sql_file)) as conn:
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
                """Computes schedule with quantity for nominal equipment
                series"""
                sched = series["ScheduleIndex"]
                sql_query = (
                    "select t.ScheduleName, t.ScheduleType as M from "
                    "Schedules t where ScheduleIndex=?"
                )
                sched_name, sched_type = c.execute(sql_query, (int(sched),)).fetchone()
                level_ = float(series["DesignLevel"])
                if level_ > 0:
                    return UmiSchedule(
                        Name=sched_name,
                        idf=zone.idf,
                        Type=sched_type,
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
                """Computes schedule with quantity for nominal equipment
                series"""
                sched = series["NumberOfPeopleScheduleIndex"]
                sql_query = (
                    "select t.ScheduleName, t.ScheduleType as M from "
                    "Schedules t where ScheduleIndex=?"
                )
                sched_name, sched_type = c.execute(sql_query, (int(sched),)).fetchone()
                return UmiSchedule(
                    Name=sched_name,
                    idf=zone.idf,
                    Type=sched_type,
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
            zone=zone,
            DimmingType=_resolve_dimming_type(zone),
            EquipmentAvailabilitySchedule=EquipmentAvailabilitySchedule,
            EquipmentPowerDensity=EquipmentPowerDensity,
            IlluminanceTarget=_resolve_illuminance_target(zone),
            LightingPowerDensity=LightingPowerDensity,
            LightsAvailabilitySchedule=LightsAvailabilitySchedule,
            OccupancySchedule=OccupancySchedule,
            IsEquipmentOn=EquipmentPowerDensity > 0,
            IsLightingOn=LightingPowerDensity > 0,
            IsPeopleOn=PeopleDensity > 0,
            PeopleDensity=PeopleDensity,
            idf=zone.idf,
            Category=zone.idf.name,
            **kwargs,
        )
        return z_load

    def combine(self, other, weights=None):
        """Combine two ZoneLoad objects together.

        Args:
            other (ZoneLoad):
            weights (list-like, optional): A list-like object of len 2. If None,
                the volume of the zones for which self and other belongs is
                used.

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

        incoming_load_data = self.__dict__.copy()
        incoming_load_data.pop("Name")

        meta = self._get_predecessors_meta(other)

        if not weights:
            zone_weight = settings.zone_weight
            weights = [
                getattr(self._belongs_to_zone, str(zone_weight)),
                getattr(other._belongs_to_zone, str(zone_weight)),
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
                quantity=True,
            ),
            EquipmentPowerDensity=self._float_mean(
                other, "EquipmentPowerDensity", weights
            ),
            IlluminanceTarget=self._float_mean(other, "IlluminanceTarget", weights),
            LightingPowerDensity=self._float_mean(
                other, "LightingPowerDensity", weights
            ),
            LightsAvailabilitySchedule=UmiSchedule.combine(
                self.LightsAvailabilitySchedule,
                other.LightsAvailabilitySchedule,
                quantity=True,
            ),
            OccupancySchedule=UmiSchedule.combine(
                self.OccupancySchedule,
                other.OccupancySchedule,
                quantity=True,
            ),
            IsEquipmentOn=any([self.IsEquipmentOn, other.IsEquipmentOn]),
            IsLightingOn=any([self.IsLightingOn, other.IsLightingOn]),
            IsPeopleOn=any([self.IsPeopleOn, other.IsPeopleOn]),
            PeopleDensity=self._float_mean(other, "PeopleDensity", weights),
        )

        new_obj = self.__class__(
            **meta, **new_attr, idf=self.idf, allow_duplicates=self._allow_duplicates
        )
        new_obj._belongs_to_zone = self._belongs_to_zone
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

    def mapping(self):
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

    def get_ref(self, ref):
        """Get item matching reference id.

        Args:
            ref:
        """
        return next(
            iter(
                [value for value in ZoneLoad.CREATED_OBJECTS if value.id == ref["$ref"]]
            ),
            None,
        )


def _resolve_dimming_type(zone):
    """Resolves the dimming type for the Zone object"""
    # First, retrieve the list of Daylighting objects for this zone. Uses the eppy
    # `getreferingobjs` method.
    ep_obj = zone._epbunch
    possible_ctrls = ep_obj.getreferingobjs(
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


def _resolve_illuminance_target(zone):
    """Resolves the illuminance target for the Zone object"""
    # First, retrieve the list of Daylighting objects for this zone. Uses the eppy
    # `getreferingobjs` method.
    ep_obj = zone._epbunch
    possible_ctrls = ep_obj.getreferingobjs(
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
