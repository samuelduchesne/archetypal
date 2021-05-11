"""archetypal VentilationSetting."""

import collections
import logging as lg
from enum import Enum

import numpy as np
import pandas as pd
from sigfig import round
from validator_collection import checkers, validators

from archetypal.template.schedule import UmiSchedule
from archetypal.template.umi_base import UmiBase
from archetypal.utils import log, timeit, top, weighted_mean


def resolve_temp(temp, idf):
    """Resolve the temperature given a float or a string.

    If a float is passed, simply return it. If a str
    is passed, get the schedule and return the mean value.

    Args:
        temp (float or str):
        idf (IDF): the idf object
    """
    if isinstance(temp, float):
        return temp
    elif isinstance(temp, str):
        epbunch = idf.schedules_dict[temp.upper()]
        sched = UmiSchedule.from_epbunch(epbunch)
        return sched.all_values.mean()


class VentilationType(Enum):
    """EnergyPlus Ventilation Types for ZoneVentilation:DesignFlowrate.

    This alpha character string defines the type of ventilation as one of the
    following options: Natural, Exhaust, Intake, or Balanced. Natural ventilation is
    assumed to be air movement/exchange as a result of openings in the building
    façade and will not consume any fan energy. Values for fan pressure and
    efficiency for natural ventilation are ignored. For either Exhaust or Intake,
    values for fan pressure and efficiency define the fan electric consumption. For
    Natural and Exhaust ventilation, the conditions of the air entering the space are
    assumed to be equivalent to outside air conditions. For Intake and Balanced
    ventilation, an appropriate amount of fan heat is added to the entering air
    stream. For Balanced ventilation, both an intake fan and an exhaust fan are
    assumed to co-exist, both having the same flow rate and power consumption (using
    the entered values for fan pressure rise and fan total efficiency). Thus,
    the fan electric consumption for Balanced ventilation is twice that for the
    Exhaust or Intake ventilation types which employ only a single fan.
    """

    Natural = 0
    Intake = 1
    Exhaust = 2
    Balanced = 3


class VentilationSetting(UmiBase):
    """Zone Ventilation Settings.

    .. image:: ../images/template/zoneinfo-ventilation.png
    """

    __slots__ = (
        "_infiltration",
        "_is_infiltration_on",
        "_is_buoyancy_on",
        "_is_nat_vent_on",
        "_is_scheduled_ventilation_on",
        "_is_wind_on",
        "_natural_ventilation_max_outdoor_air_temp",
        "_natural_ventilation_max_relative_humidity",
        "_natural_ventilation_min_outdoor_air_temp",
        "_natural_ventilation_zone_setpoint_temp",
        "_scheduled_ventilation_ach",
        "_scheduled_ventilation_setpoint",
        "_scheduled_ventilation_schedule",
        "_nat_ventilation_schedule",
        "_ventilation_type",
        "_afn",
        "_area",
        "_volume",
    )

    def __init__(
        self,
        Name,
        Infiltration=0.1,
        IsInfiltrationOn=True,
        IsNatVentOn=False,
        NatVentSchedule=None,
        IsWindOn=False,
        IsBuoyancyOn=True,
        NatVentMaxOutdoorAirTemp=30,
        NatVentMaxRelHumidity=90,
        NatVentMinOutdoorAirTemp=0,
        NatVentZoneTempSetpoint=18,
        ScheduledVentilationAch=0.6,
        ScheduledVentilationSchedule=None,
        ScheduledVentilationSetpoint=18,
        IsScheduledVentilationOn=False,
        VentilationType=VentilationType.Exhaust,
        Afn=False,
        area=1,
        volume=1,
        **kwargs,
    ):
        """Initialize a new VentilationSetting (for zone) object.

        Args:
            NatVentSchedule (UmiSchedule): The name of the schedule
                (Day | Week | Year) which ultimately modifies the Opening Area
                value. In its current implementation, any
                value greater than 0 will consider an open window.
            ScheduledVentilationSchedule (UmiSchedule, optional): The name of
                the schedule (Schedules Tab) that modifies the maximum design
                volume flow rate. This fraction is between 0.0 and 1.0.
            Afn (bool): Todo: Not Used.
            Infiltration (float): Infiltration rate in ACH.
            IsBuoyancyOn (bool): If True, simulation takes into account the
                stack effect in the infiltration calculation
            IsInfiltrationOn (bool): If yes, there is heat transfer between the
                building and the outside caused by infiltration.
            IsNatVentOn (bool): If True, Natural ventilation (air
                movement/exchange as a result of openings in the building façade
                not consuming any fan energy).
            IsScheduledVentilationOn (bool): If True, Ventilation (flow of air
                from the outdoor environment directly into a thermal zone) is ON
            IsWindOn (bool): If True, simulation takes into account the wind
                effect in the infiltration calculation
            NatVentMaxOutdoorAirTemp (float): The outdoor temperature (in
                Celsius) above which ventilation is shut off. The minimum value
                for this field is -100.0°C and the maximum value is 100.0°C. The
                default value is 100.0°C if the field is left blank. This upper
                temperature limit is intended to avoid overheating a space,
                which could result in a cooling load.
            NatVentMaxRelHumidity (float): Defines the dehumidifying relative
                humidity setpoint, expressed as a percentage (0-100), for each
                timestep of the simulation.
            NatVentMinOutdoorAirTemp (float): The outdoor temperature (in
                Celsius) below which ventilation is shut off. The minimum value
                for this field is -100.0°C and the maximum value is 100.0°C. The
                default value is -100.0°C if the field is left blank. This lower
                temperature limit is intended to avoid overcooling a space,
                which could result in a heating load.
            NatVentZoneTempSetpoint (float):
            ScheduledVentilationAch (float): This factor, along with the Zone
                Volume, will be used to determine the Design Flow Rate.
            ScheduledVentilationSetpoint (float): The indoor temperature (in
                Celsius) below which ventilation is shutoff. The minimum value
                for this field is -100.0°C and the maximum value is 100.0°C. The
                default value is -100.0°C if the field is left blank. This lower
                temperature limit is intended to avoid overcooling a space and
                thus result in a heating load. For example, if the user
                specifies a minimum temperature of 20°C, ventilation is assumed
                to be available if the zone air temperature is above 20°C. If
                the zone air temperature drops below 20°C, then ventilation is
                automatically turned off.
            VentilationType (int): This alpha character string defines the type of
                ventilation as one of the following options: Natural, Exhaust,
                Intake, or Balanced. Natural ventilation is assumed to be air
                movement/exchange as a result of openings in the building façade and
                will not consume any fan energy. Values for fan pressure and
                efficiency for natural ventilation are ignored. For either Exhaust or
                Intake, values for fan pressure and efficiency define the fan
                electric consumption. For Natural and Exhaust ventilation,
                the conditions of the air entering the space are assumed to be
                equivalent to outside air conditions. For Intake and Balanced
                ventilation, an appropriate amount of fan heat is added to the entering
                air stream. For Balanced ventilation, both an intake fan and an
                exhaust fan are assumed to co-exist, both having the same flow rate
                and power consumption (using the entered values for fan pressure rise
                and fan total efficiency). Thus, the fan electric consumption for
                Balanced ventilation is twice that for the Exhaust or Intake
                ventilation types which employ only a single fan.
            **kwargs: keywords passed to the constructor.
        """
        super(VentilationSetting, self).__init__(Name, **kwargs)

        self.Infiltration = Infiltration
        self.IsInfiltrationOn = IsInfiltrationOn
        self.IsNatVentOn = IsNatVentOn
        self.NatVentSchedule = NatVentSchedule
        self.IsWindOn = IsWindOn
        self.IsBuoyancyOn = IsBuoyancyOn
        self.NatVentMaxOutdoorAirTemp = NatVentMaxOutdoorAirTemp
        self.NatVentMaxRelHumidity = NatVentMaxRelHumidity
        self.NatVentMinOutdoorAirTemp = NatVentMinOutdoorAirTemp
        self.NatVentZoneTempSetpoint = NatVentZoneTempSetpoint
        self.ScheduledVentilationAch = ScheduledVentilationAch
        self.ScheduledVentilationSetpoint = ScheduledVentilationSetpoint
        self.ScheduledVentilationSchedule = ScheduledVentilationSchedule
        self.IsScheduledVentilationOn = IsScheduledVentilationOn
        self.VentilationType = VentilationType
        self.Afn = Afn
        self.area = area
        self.volume = volume

    @property
    def NatVentSchedule(self):
        """Get or set the natural ventilation schedule.

        Hint:
            This schedule ultimately modifies the Opening Area value.
        """
        return self._nat_ventilation_schedule

    @NatVentSchedule.setter
    def NatVentSchedule(self, value):
        if value is not None:
            assert isinstance(value, UmiSchedule), (
                f"Input error with value {value}. NatVentSchedule must "
                f"be an UmiSchedule, not a {type(value)}"
            )
        self._nat_ventilation_schedule = value

    @property
    def ScheduledVentilationSchedule(self):
        """Get or set the scheduled ventilation schedule."""
        return self._scheduled_ventilation_schedule

    @ScheduledVentilationSchedule.setter
    def ScheduledVentilationSchedule(self, value):
        if value is not None:
            assert isinstance(value, UmiSchedule), (
                f"Input error with value {value}. ScheduledVentilationSchedule must "
                f"be an UmiSchedule, not a {type(value)}"
            )
            value.quantity = self.ScheduledVentilationAch
        self._scheduled_ventilation_schedule = value

    @property
    def Infiltration(self):
        """Get or set the infiltration air change rate [ach]."""
        return self._infiltration

    @Infiltration.setter
    def Infiltration(self, value):
        if value is None:
            value = 0
        value = validators.float(value, minimum=0)
        if value == 0:
            self.IsInfiltrationOn = False
        self._infiltration = value

    @property
    def IsInfiltrationOn(self):
        """Get or set the the infiltration [bool]."""
        return self._is_infiltration_on

    @IsInfiltrationOn.setter
    def IsInfiltrationOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsInfiltrationOn must "
            f"be an boolean, not a {type(value)}"
        )
        self._is_infiltration_on = value

    @property
    def IsBuoyancyOn(self):
        """Get or set the buoyancy boolean."""
        return self._is_buoyancy_on

    @IsBuoyancyOn.setter
    def IsBuoyancyOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsBuoyancyOn must "
            f"be an boolean, not a {type(value)}"
        )
        self._is_buoyancy_on = value

    @property
    def IsNatVentOn(self):
        """Get or set the natural ventilation [bool]."""
        return self._is_nat_vent_on

    @IsNatVentOn.setter
    def IsNatVentOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsNatVentOn must "
            f"be an boolean, not a {type(value)}"
        )
        self._is_nat_vent_on = value

    @property
    def IsScheduledVentilationOn(self):
        """Get or set the scheduled ventilation [bool]."""
        return self._is_scheduled_ventilation_on

    @IsScheduledVentilationOn.setter
    def IsScheduledVentilationOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsScheduledVentilationOn must "
            f"be an boolean, not a {type(value)}"
        )
        if value:
            assert (
                self.ScheduledVentilationAch > 0
                and self.ScheduledVentilationSchedule is not None
            ), (
                f"IsScheduledVentilationOn cannot be 'True' if ScheduledVentilationAch "
                f"is 0 or if ScheduledVentilationSchedule is None."
            )
        self._is_scheduled_ventilation_on = value

    @property
    def IsWindOn(self):
        """Get or set the wind effect [bool]."""
        return self._is_wind_on

    @IsWindOn.setter
    def IsWindOn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. IsWindOn must "
            f"be an boolean, not a {type(value)}"
        )
        self._is_wind_on = value

    @property
    def NatVentMaxOutdoorAirTemp(self):
        """Get or set the natural ventilation maximum outdoor air temperature [degC]."""
        return self._natural_ventilation_max_outdoor_air_temp

    @NatVentMaxOutdoorAirTemp.setter
    def NatVentMaxOutdoorAirTemp(self, value):
        self._natural_ventilation_max_outdoor_air_temp = validators.float(
            value, minimum=-100, maximum=100
        )

    @property
    def NatVentMaxRelHumidity(self):
        """Get or set the natural ventilation relative humidity setpoint [%]."""
        return self._natural_ventilation_max_relative_humidity

    @NatVentMaxRelHumidity.setter
    def NatVentMaxRelHumidity(self, value):
        self._natural_ventilation_max_relative_humidity = validators.float(
            value, minimum=0, maximum=100
        )

    @property
    def NatVentMinOutdoorAirTemp(self):
        """Get or set the natural ventilation minimum outdoor air temperature [degC]."""
        return self._natural_ventilation_min_outdoor_air_temp

    @NatVentMinOutdoorAirTemp.setter
    def NatVentMinOutdoorAirTemp(self, value):
        self._natural_ventilation_min_outdoor_air_temp = validators.float(
            value, minimum=-100, maximum=100
        )

    @property
    def NatVentZoneTempSetpoint(self):
        """Get or set the natural ventilation zone temperature setpoint [degC]."""
        return self._natural_ventilation_zone_setpoint_temp

    @NatVentZoneTempSetpoint.setter
    def NatVentZoneTempSetpoint(self, value):
        self._natural_ventilation_zone_setpoint_temp = validators.float(
            value,
            minimum=self.NatVentMinOutdoorAirTemp,
            maximum=self.NatVentMaxOutdoorAirTemp,
        )

    @property
    def ScheduledVentilationAch(self):
        """Get or set the scheduled ventilation air changes per hours [-]."""
        return self._scheduled_ventilation_ach

    @ScheduledVentilationAch.setter
    def ScheduledVentilationAch(self, value):
        if value is None:
            value = 0
        self._scheduled_ventilation_ach = validators.float(value, minimum=0)

    @property
    def ScheduledVentilationSetpoint(self):
        """Get or set the scheduled ventilation setpoint."""
        return self._scheduled_ventilation_setpoint

    @ScheduledVentilationSetpoint.setter
    def ScheduledVentilationSetpoint(self, value):
        self._scheduled_ventilation_setpoint = validators.float(
            value, minimum=-100, maximum=100
        )

    @property
    def VentilationType(self):
        """Get or set the ventilation type.

        Choices are (<VentilationType.Natural: 0>, <VentilationType.Intake: 1>,
        <VentilationType.Exhaust: 2>, <VentilationType.Balanced: 3>).
        """
        return self._ventilation_type

    @VentilationType.setter
    def VentilationType(self, value):
        if checkers.is_string(value):
            assert VentilationType[value], (
                f"Input value error for '{value}'. "
                f"Expected one of {tuple(a for a in VentilationType)}"
            )
            self._ventilation_type = VentilationType[value]
        elif checkers.is_numeric(value):
            assert VentilationType[value], (
                f"Input value error for '{value}'. "
                f"Expected one of {tuple(a for a in VentilationType)}"
            )
            self._ventilation_type = VentilationType(value)
        self._ventilation_type = value

    @property
    def Afn(self):
        """Get or set the use of the airflow network [bool]."""
        return self._afn

    @Afn.setter
    def Afn(self, value):
        assert isinstance(value, bool), (
            f"Input error with value {value}. Afn must "
            f"be an boolean, not a {type(value)}"
        )
        self._afn = value

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
    def from_dict(cls, data, schedules, **kwargs):
        """Create a VentilationSetting from a dictionary.

        Args:
            data (dict): The python dictionary.
            schedules (dict): A dictionary of UmiSchedules with their id as keys.
            **kwargs: keywords passed parent constructor.

        .. code-block:: python

            {
              "$id": "162",
              "Afn": false,
              "IsBuoyancyOn": true,
              "Infiltration": 0.35,
              "IsInfiltrationOn": true,
              "IsNatVentOn": false,
              "IsScheduledVentilationOn": false,
              "NatVentMaxRelHumidity": 80.0,
              "NatVentMaxOutdoorAirTemp": 26.0,
              "NatVentMinOutdoorAirTemp": 20.0,
              "NatVentSchedule": {
                "$ref": "151"
              },
              "NatVentZoneTempSetpoint": 22.0,
              "ScheduledVentilationAch": 0.6,
              "ScheduledVentilationSchedule": {
                "$ref": "151"
              },
              "ScheduledVentilationSetpoint": 22.0,
              "IsWindOn": false,
              "Category": "Office Spaces",
              "Comments": null,
              "DataSource": "MIT_SDL",
              "Name": "B_Off_0 ventilation"
            }
        """
        vent_sch = schedules[data.pop("ScheduledVentilationSchedule")["$ref"]]
        nat_sch = schedules[data.pop("NatVentSchedule")["$ref"]]
        _id = data.pop("$id")
        return cls(
            id=_id,
            ScheduledVentilationSchedule=vent_sch,
            NatVentSchedule=nat_sch,
            **data,
            **kwargs,
        )

    def to_dict(self):
        """Return VentilationSetting dictionary representation."""
        self.validate()  # Validate object before trying to get json format

        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Afn"] = self.Afn
        data_dict["IsBuoyancyOn"] = self.IsBuoyancyOn
        data_dict["Infiltration"] = round(self.Infiltration, 3)
        data_dict["IsInfiltrationOn"] = self.IsInfiltrationOn
        data_dict["IsNatVentOn"] = self.IsNatVentOn
        data_dict["IsScheduledVentilationOn"] = self.IsScheduledVentilationOn
        data_dict["NatVentMaxRelHumidity"] = round(self.NatVentMaxRelHumidity, 3)
        data_dict["NatVentMaxOutdoorAirTemp"] = round(self.NatVentMaxOutdoorAirTemp, 3)
        data_dict["NatVentMinOutdoorAirTemp"] = round(self.NatVentMinOutdoorAirTemp, 3)
        data_dict["NatVentSchedule"] = self.NatVentSchedule.to_ref()
        data_dict["NatVentZoneTempSetpoint"] = round(self.NatVentZoneTempSetpoint, 3)
        data_dict["ScheduledVentilationAch"] = round(self.ScheduledVentilationAch, 3)
        data_dict[
            "ScheduledVentilationSchedule"
        ] = self.ScheduledVentilationSchedule.to_ref()
        data_dict["ScheduledVentilationSetpoint"] = round(
            self.ScheduledVentilationSetpoint, 3
        )
        data_dict["IsWindOn"] = self.IsWindOn
        data_dict["Category"] = self.Category
        data_dict["Comments"] = validators.string(self.Comments, allow_empty=True)
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    @timeit
    def from_zone(cls, zone, zone_ep, **kwargs):
        """Create VentilationSetting from a zone object.

        Args:
            zone_ep:
            zone (template.zone.Zone): zone to gets information from
        """
        # If Zone is not part of Conditioned Area, it should not have a
        # VentilationSetting object.
        if not zone.is_part_of_total_floor_area:
            return None
        name = zone.Name + "_VentilationSetting"

        df = {"a": zone_ep.theidf.sql()}
        ni_df = nominal_infiltration(df)
        sched_df = nominal_mech_ventilation(df)
        nat_df = nominal_nat_ventilation(df)
        index = ("a", zone.Name.upper())

        # Do infiltration
        Infiltration, IsInfiltrationOn = do_infiltration(index, ni_df)

        # Do natural ventilation
        (
            IsNatVentOn,
            IsWindOn,
            IsBuoyancyOn,
            NatVentMaxOutdoorAirTemp,
            NatVentMaxRelHumidity,
            NatVentMinOutdoorAirTemp,
            NatVentSchedule,
            NatVentZoneTempSetpoint,
        ) = do_natural_ventilation(index, nat_df, zone, zone_ep)

        # Do scheduled ventilation
        (
            ScheduledVentilationSchedule,
            IsScheduledVentilationOn,
            ScheduledVentilationAch,
            ScheduledVentilationSetpoint,
        ) = do_scheduled_ventilation(index, sched_df, zone)

        z_vent = cls(
            Name=name,
            zone=zone,
            Infiltration=Infiltration,
            IsInfiltrationOn=IsInfiltrationOn,
            IsWindOn=IsWindOn,
            IsBuoyancyOn=IsBuoyancyOn,
            IsNatVentOn=IsNatVentOn,
            NatVentSchedule=NatVentSchedule,
            NatVentMaxRelHumidity=NatVentMaxRelHumidity,
            NatVentMaxOutdoorAirTemp=NatVentMaxOutdoorAirTemp,
            NatVentMinOutdoorAirTemp=NatVentMinOutdoorAirTemp,
            NatVentZoneTempSetpoint=NatVentZoneTempSetpoint,
            ScheduledVentilationSchedule=ScheduledVentilationSchedule,
            IsScheduledVentilationOn=IsScheduledVentilationOn,
            ScheduledVentilationAch=ScheduledVentilationAch,
            ScheduledVentilationSetpoint=ScheduledVentilationSetpoint,
            Category=zone.DataSource,
            **kwargs,
        )
        return z_vent

    def combine(self, other, **kwargs):
        """Combine VentilationSetting objects together.

        Args:
            other (VentilationSetting):
            kwargs: keywords passed to constructor.

        Returns:
            (VentilationSetting): the combined VentilationSetting object.
        """
        # Check if other is None. Simply return self or if other is not the same as self
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

        # create a new object with the combined attributes
        new_obj = self.__class__(
            NatVentSchedule=UmiSchedule.combine(
                self.NatVentSchedule, other.NatVentSchedule, [self.area, other.area]
            ),
            ScheduledVentilationSchedule=UmiSchedule.combine(
                self.ScheduledVentilationSchedule,
                other.ScheduledVentilationSchedule,
                weights=[self.volume, other.volume],
                quantity=True,
            ),
            Afn=any((self.Afn, other.Afn)),
            Infiltration=self.float_mean(
                other, "Infiltration", [self.area, other.area]
            ),
            IsBuoyancyOn=any((self.IsBuoyancyOn, other.IsBuoyancyOn)),
            IsInfiltrationOn=any((self.IsInfiltrationOn, other.IsInfiltrationOn)),
            IsNatVentOn=any((self.IsNatVentOn, other.IsNatVentOn)),
            IsScheduledVentilationOn=any(
                (self.IsScheduledVentilationOn, other.IsScheduledVentilationOn)
            ),
            IsWindOn=any((self.IsWindOn, other.IsWindOn)),
            NatVentMaxOutdoorAirTemp=self.float_mean(
                other, "NatVentMaxOutdoorAirTemp", [self.area, other.area]
            ),
            NatVentMaxRelHumidity=self.float_mean(
                other, "NatVentMaxRelHumidity", [self.area, other.area]
            ),
            NatVentMinOutdoorAirTemp=self.float_mean(
                other, "NatVentMinOutdoorAirTemp", [self.area, other.area]
            ),
            NatVentZoneTempSetpoint=self.float_mean(
                other, "NatVentZoneTempSetpoint", [self.area, other.area]
            ),
            ScheduledVentilationAch=self.float_mean(
                other, "ScheduledVentilationAch", [self.volume, other.volume]
            ),
            ScheduledVentilationSetpoint=self.float_mean(
                other, "ScheduledVentilationSetpoint", [self.area, other.area]
            ),
            area=1 if self.area + other.area == 2 else self.area + other.area,
            volume=1 if self.volume + other.volume == 2 else self.volume + other.volume,
            **meta,
            **kwargs,
            allow_duplicates=self.allow_duplicates,
        )
        new_obj.predecessors.update(self.predecessors + other.predecessors)
        return new_obj

    def validate(self):
        """Validate object and fill in missing values."""
        if not self.NatVentSchedule:
            self.NatVentSchedule = UmiSchedule.constant_schedule(
                value=0, Name="AlwaysOff", allow_duplicates=True
            )
        if not self.ScheduledVentilationSchedule:
            self.ScheduledVentilationSchedule = UmiSchedule.constant_schedule(
                value=0, Name="AlwaysOff", allow_duplicates=True
            )

        return self

    def mapping(self, validate=True):
        """Get a dict based on the object properties, useful for dict repr.

        Args:
            validate:
        """
        self.validate()

        return dict(
            Afn=self.Afn,
            IsBuoyancyOn=self.IsBuoyancyOn,
            Infiltration=self.Infiltration,
            IsInfiltrationOn=self.IsInfiltrationOn,
            IsNatVentOn=self.IsNatVentOn,
            IsScheduledVentilationOn=self.IsScheduledVentilationOn,
            NatVentMaxRelHumidity=self.NatVentMaxRelHumidity,
            NatVentMaxOutdoorAirTemp=self.NatVentMaxOutdoorAirTemp,
            NatVentMinOutdoorAirTemp=self.NatVentMinOutdoorAirTemp,
            NatVentSchedule=self.NatVentSchedule,
            NatVentZoneTempSetpoint=self.NatVentZoneTempSetpoint,
            ScheduledVentilationAch=self.ScheduledVentilationAch,
            ScheduledVentilationSchedule=self.ScheduledVentilationSchedule,
            ScheduledVentilationSetpoint=self.ScheduledVentilationSetpoint,
            IsWindOn=self.IsWindOn,
            Category=self.Category,
            Comments=self.Comments,
            DataSource=self.DataSource,
            Name=self.Name,
        )

    def duplicate(self):
        """Get copy of self."""
        return self.__copy__()

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
            self.NatVentSchedule,
            self.ScheduledVentilationSchedule,
            self.Afn,
            self.Infiltration,
            self.IsBuoyancyOn,
            self.IsInfiltrationOn,
            self.IsNatVentOn,
            self.IsScheduledVentilationOn,
            self.IsWindOn,
            self.NatVentMaxOutdoorAirTemp,
            self.NatVentMaxRelHumidity,
            self.NatVentMinOutdoorAirTemp,
            self.NatVentZoneTempSetpoint,
            self.ScheduledVentilationAch,
            self.ScheduledVentilationSetpoint,
        )

    def __eq__(self, other):
        """Assert self is equivalent to other."""
        if not isinstance(other, VentilationSetting):
            return NotImplemented
        else:
            return self.__key__() == other.__key__()

    def __copy__(self):
        """Create a copy of self."""
        return self.__class__(
            **self.mapping(validate=False), area=self.area, volume=self.volume
        )

    def to_epbunch(self, idf, zone_name, opening_area=0.0):
        """Convert self to the EpBunches given an idf model, a zone name.

        Notes:
            Note that attr:`IsInfiltrationOn`, attr:`IsScheduledVentilationOn` and
            attr:`IsNatVentOn` must be `True` for their respective EpBunch objects
            to be created.

        Args:
            idf (IDF): The idf model in which the EpBunch is created.
            zone_name (str): The zone name to associate this EpBunch.
            opening_area (float): The opening area exposed to outdoors (m2)
                in a zone.

        .. code-block::

            ZONEINFILTRATION:DESIGNFLOWRATE,
                Zone Infiltration,        !- Name
                Zone 1,                   !- Zone or ZoneList Name
                AlwaysOn,                 !- Schedule Name
                AirChanges/Hour,          !- Design Flow Rate Calculation Method
                ,                         !- Design Flow Rate
                ,                         !- Flow per Zone Floor Area
                ,                         !- Flow per Exterior Surface Area
                0.1,                      !- Air Changes per Hour
                1,                        !- Constant Term Coefficient
                0,                        !- Temperature Term Coefficient
                0,                        !- Velocity Term Coefficient
                0;                        !- Velocity Squared Term Coefficient

            ZONEVENTILATION:DESIGNFLOWRATE,
                 Zone 1 Ventilation,       !- Name
                 Zone 1,                   !- Zone or ZoneList Name
                 AlwaysOn,                 !- Schedule Name
                 AirChanges/Hour,          !- Design Flow Rate Calculation Method
                 ,                         !- Design Flow Rate
                 ,                         !- Flow Rate per Zone Floor Area
                 ,                         !- Flow Rate per Person
                 0.6,                      !- Air Changes per Hour
                 Exhaust,                  !- Ventilation Type
                 67,                       !- Fan Pressure Rise
                 0.7,                      !- Fan Total Efficiency
                 1,                        !- Constant Term Coefficient
                 0,                        !- Temperature Term Coefficient
                 0,                        !- Velocity Term Coefficient
                 0,                        !- Velocity Squared Term Coefficient
                 -100,                     !- Minimum Indoor Temperature
                 ,                         !- Minimum Indoor Temperature Schedule Name
                 100,                      !- Maximum Indoor Temperature
                 ,                         !- Maximum Indoor Temperature Schedule Name
                 -100,                     !- Delta Temperature
                 ,                         !- Delta Temperature Schedule Name
                 -100,                     !- Minimum Outdoor Temperature
                 ,                         !- Minimum Outdoor Temperature Schedule Name
                 100,                      !- Maximum Outdoor Temperature
                 ,                         !- Maximum Outdoor Temperature Schedule Name
                 40;                       !- Maximum Wind Speed)

            ZONEVENTILATION:WINDANDSTACKOPENAREA,
                ,                         !- Name
                ,                         !- Zone Name
                0,                        !- Opening Area
                ,                         !- Opening Area Fraction Schedule Name
                Autocalculate,            !- Opening Effectiveness
                0,                        !- Effective Angle
                0,                        !- Height Difference
                Autocalculate,            !- Discharge Coefficient for Opening
                -100,                     !- Minimum Indoor Temperature
                ,                         !- Minimum Indoor Temperature Schedule Name
                100,                      !- Maximum Indoor Temperature
                ,                         !- Maximum Indoor Temperature Schedule Name
                -100,                     !- Delta Temperature
                ,                         !- Delta Temperature Schedule Name
                -100,                     !- Minimum Outdoor Temperature
                ,                         !- Minimum Outdoor Temperature Schedule Name
                100,                      !- Maximum Outdoor Temperature
                ,                         !- Maximum Outdoor Temperature Schedule Name
                40;                       !- Maximum Wind Speed

        Returns:
            tuple: A 3-tuple of EpBunch objects added to the idf model.
        """
        if self.IsInfiltrationOn:
            infiltration_epbunch = idf.newidfobject(
                key="ZONEINFILTRATION:DESIGNFLOWRATE",
                Name=f"{zone_name} Infiltration",
                Zone_or_ZoneList_Name=zone_name,
                Schedule_Name=idf.newidfobject(
                    key="SCHEDULE:CONSTANT", Name="AlwaysOn", Hourly_Value=1
                ).Name,
                Design_Flow_Rate_Calculation_Method="AirChanges/Hour",
                Air_Changes_per_Hour=self.Infiltration,
                Constant_Term_Coefficient=1,
                Temperature_Term_Coefficient=0,
                Velocity_Term_Coefficient=0,
                Velocity_Squared_Term_Coefficient=0,
            )
        else:
            infiltration_epbunch = None
            log("No epbunch created since IsInfiltrationOn == False.")

        if self.IsScheduledVentilationOn:
            ventilation_epbunch = idf.newidfobject(
                key="ZONEVENTILATION:DESIGNFLOWRATE",
                Name=f"{zone_name} Ventilation",
                Zone_or_ZoneList_Name=zone_name,
                Schedule_Name=self.ScheduledVentilationSchedule.to_year_week_day()[
                    0
                ].Name,  # take the YearSchedule and get the name.
                Design_Flow_Rate_Calculation_Method="AirChanges/Hour",
                Design_Flow_Rate="",
                Flow_Rate_per_Zone_Floor_Area="",
                Flow_Rate_per_Person="",
                Air_Changes_per_Hour=self.ScheduledVentilationAch,
                Ventilation_Type=self.VentilationType.name,
                Fan_Pressure_Rise=67.0,
                Fan_Total_Efficiency=0.7,
                Constant_Term_Coefficient=1.0,
                Temperature_Term_Coefficient=0.0,
                Velocity_Term_Coefficient=0.0,
                Velocity_Squared_Term_Coefficient=0.0,
                Minimum_Indoor_Temperature=-100,
                Minimum_Indoor_Temperature_Schedule_Name="",
                Maximum_Indoor_Temperature=100.0,
                Maximum_Indoor_Temperature_Schedule_Name="",
                Delta_Temperature=-100.0,
                Delta_Temperature_Schedule_Name="",
                Minimum_Outdoor_Temperature=-100.0,
                Minimum_Outdoor_Temperature_Schedule_Name="",
                Maximum_Outdoor_Temperature=100.0,
                Maximum_Outdoor_Temperature_Schedule_Name="",
                Maximum_Wind_Speed=40.0,
            )
        else:
            ventilation_epbunch = None
            log("No epbunch created since IsScheduledVentilationOn == False.")

        if self.IsNatVentOn:
            natural_epbunch = idf.newidfobject(
                key="ZONEVENTILATION:WINDANDSTACKOPENAREA",
                Name=f"{zone_name} Natural Ventilation",
                Zone_Name=zone_name,
                Opening_Area=opening_area,
                Opening_Area_Fraction_Schedule_Name="",
                Opening_Effectiveness="Autocalculate",
                Effective_Angle=0.0,
                Height_Difference=1,
                Discharge_Coefficient_for_Opening="Autocalculate",
                Minimum_Indoor_Temperature=self.NatVentZoneTempSetpoint,
                Minimum_Indoor_Temperature_Schedule_Name="",
                Maximum_Indoor_Temperature=100.0,
                Maximum_Indoor_Temperature_Schedule_Name="",
                Delta_Temperature=-100.0,
                Delta_Temperature_Schedule_Name="",
                Minimum_Outdoor_Temperature=self.NatVentMinOutdoorAirTemp,
                Minimum_Outdoor_Temperature_Schedule_Name="",
                Maximum_Outdoor_Temperature=self.NatVentMaxOutdoorAirTemp,
                Maximum_Outdoor_Temperature_Schedule_Name="",
                Maximum_Wind_Speed=40.0,
            )
        else:
            natural_epbunch = None
            log("No epbunch created since IsNatVentOn == False.")

        return infiltration_epbunch, ventilation_epbunch, natural_epbunch


def do_infiltration(index, inf_df):
    """Get infiltration information of the zone.

    Args:
        index (tuple): Zone name
        inf_df (dataframe): Dataframe with infiltration information for each
            zone.
    """
    if not inf_df.empty:
        try:
            Infiltration = inf_df.loc[index, "ACH - Air Changes per Hour"]
            IsInfiltrationOn = any(inf_df.loc[index, "Name"])
        except Exception:
            Infiltration = 0
            IsInfiltrationOn = False
    else:
        Infiltration = 0
        IsInfiltrationOn = False
    return Infiltration, IsInfiltrationOn


def do_natural_ventilation(index, nat_df, zone, zone_ep):
    """Get natural ventilation information of the zone.

    Args:
        zone_ep:
        index (tuple): Zone name
        nat_df:
        zone (template.zone.Zone): zone to gets information from
    """
    if not nat_df.empty:
        try:
            IsNatVentOn = any(nat_df.loc[index, "Name"])
            schedule_name_ = nat_df.loc[index, "Schedule Name"]
            quantity = nat_df.loc[index, "Volume Flow Rate/Floor Area {m3/s/m2}"]
            if schedule_name_.upper() in zone.idf.schedules_dict:
                epbunch = zone.idf.schedules_dict[schedule_name_.upper()]
                NatVentSchedule = UmiSchedule.from_epbunch(epbunch, quantity=quantity)
            else:
                raise KeyError
        except KeyError:
            # todo: For some reason, a ZoneVentilation:WindandStackOpenArea
            #  'Opening Area Fraction Schedule Name' is read as Constant-0.0
            #  in the nat_df. For the mean time, a zone containing such an
            #  object will be turned on with an AlwaysOn schedule.
            IsNatVentOn = True
            NatVentSchedule = UmiSchedule.constant_schedule(allow_duplicates=True)
        except Exception:
            IsNatVentOn = False
            NatVentSchedule = UmiSchedule.constant_schedule(allow_duplicates=True)
        finally:
            try:
                NatVentMaxRelHumidity = 90  # todo: not sure if it is being used
                NatVentMaxOutdoorAirTemp = resolve_temp(
                    nat_df.loc[index, "Maximum Outdoor Temperature{C}/Schedule"],
                    zone_ep.theidf,
                )
                NatVentMinOutdoorAirTemp = resolve_temp(
                    nat_df.loc[index, "Minimum Outdoor Temperature{C}/Schedule"],
                    zone_ep.theidf,
                )
                NatVentZoneTempSetpoint = resolve_temp(
                    nat_df.loc[index, "Minimum Indoor Temperature{C}/Schedule"],
                    zone_ep.theidf,
                )
            except KeyError:
                # this zone is not in the nat_df. Revert to defaults.
                NatVentMaxRelHumidity = 90
                NatVentMaxOutdoorAirTemp = 30
                NatVentMinOutdoorAirTemp = 0
                NatVentZoneTempSetpoint = 18

    else:
        IsNatVentOn = False
        NatVentSchedule = UmiSchedule.constant_schedule(allow_duplicates=True)
        NatVentMaxRelHumidity = 90
        NatVentMaxOutdoorAirTemp = 30
        NatVentMinOutdoorAirTemp = 0
        NatVentZoneTempSetpoint = 18

    # Is Wind ON
    if not zone_ep.theidf.idfobjects[
        "ZoneVentilation:WindandStackOpenArea".upper()
    ].list1:
        IsWindOn = False
        IsBuoyancyOn = False
    else:
        IsWindOn = True
        IsBuoyancyOn = True

    return (
        IsNatVentOn,
        IsWindOn,
        IsBuoyancyOn,
        NatVentMaxOutdoorAirTemp,
        NatVentMaxRelHumidity,
        NatVentMinOutdoorAirTemp,
        NatVentSchedule,
        NatVentZoneTempSetpoint,
    )


def do_scheduled_ventilation(index, scd_df, zone):
    """Get schedule ventilation information of the zone.

    Args:
        index (tuple): Zone name
        scd_df:
        zone (template.zone.Zone): zone to gets information from
    """
    if not scd_df.empty:
        try:
            IsScheduledVentilationOn = any(scd_df.loc[index, "Name"])
            schedule_name_ = scd_df.loc[index, "Schedule Name"]
            epbunch = zone.idf.schedules_dict[schedule_name_.upper()]
            ScheduledVentilationSchedule = UmiSchedule.from_epbunch(epbunch)
            ScheduledVentilationAch = scd_df.loc[index, "ACH - Air Changes per Hour"]
            ScheduledVentilationSetpoint = resolve_temp(
                scd_df.loc[index, "Minimum Indoor Temperature{C}/Schedule"],
                zone.idf,
            )
        except Exception:
            ScheduledVentilationSchedule = UmiSchedule.constant_schedule(
                value=0, Name="AlwaysOff", allow_duplicates=True
            )
            IsScheduledVentilationOn = False
            ScheduledVentilationAch = 0
            ScheduledVentilationSetpoint = 18
    else:
        ScheduledVentilationSchedule = UmiSchedule.constant_schedule(
            value=0, Name="AlwaysOff", allow_duplicates=True
        )
        IsScheduledVentilationOn = False
        ScheduledVentilationAch = 0
        ScheduledVentilationSetpoint = 18
    return (
        ScheduledVentilationSchedule,
        IsScheduledVentilationOn,
        ScheduledVentilationAch,
        ScheduledVentilationSetpoint,
    )


def nominal_nat_ventilation(df):
    """Get the Nominal Natural Ventilation."""
    _nom_vent = nominal_ventilation(df)
    if _nom_vent.empty:
        return _nom_vent
    nom_natvent = (
        _nom_vent.reset_index()
        .set_index(["Archetype", "Zone Name"])
        .loc[
            lambda e: e["Fan Type {Exhaust;Intake;Natural}"].str.contains("Natural"), :
        ]
        if not _nom_vent.empty
        else None
    )
    return nom_natvent


def nominal_mech_ventilation(df):
    """Get the Nominal Mechanical Ventilation."""
    _nom_vent = nominal_ventilation(df)
    if _nom_vent.empty:
        return _nom_vent
    nom_vent = (
        _nom_vent.reset_index()
        .set_index(["Archetype", "Zone Name"])
        .loc[
            lambda e: ~e["Fan Type {Exhaust;Intake;Natural}"].str.contains("Natural"), :
        ]
        if not _nom_vent.empty
        else None
    )
    return nom_vent


def nominal_infiltration(df):
    """Get the Nominal Infiltration.

    References:
        * `Nominal Infiltration Table \
        <https://bigladdersoftware.com/epx/docs/8-9/output-details-and \
        -examples/eplusout-sql.html#nominalinfiltration-table>`_
    """
    df = get_from_tabulardata(df)
    report_name = "Initialization Summary"
    table_name = "ZoneInfiltration Airflow Stats Nominal"
    tbstr = df[
        (df.ReportName == report_name) & (df.TableName == table_name)
    ].reset_index()
    if tbstr.empty:
        log(
            "Table {} does not exist. "
            "Returning an empty DataFrame".format(table_name),
            lg.WARNING,
        )
        return pd.DataFrame([])

    tbpiv = tbstr.pivot_table(
        index=["Archetype", "RowName"],
        columns="ColumnName",
        values="Value",
        aggfunc=lambda x: " ".join(x),
    )
    tbpiv.replace({"N/A": np.nan}, inplace=True)
    return (
        tbpiv.reset_index()
        .groupby(["Archetype", "Zone Name"])
        .agg(lambda x: pd.to_numeric(x, errors="ignore").sum())
    )


def nominal_ventilation(df):
    """Nominal Ventilation.

    References:
        * `Nominal Ventilation Table \
        <https://bigladdersoftware.com/epx/docs/8-9/output-details-and \
        -examples/eplusout-sql.html#nominalventilation-table>`_
    """
    df = get_from_tabulardata(df)
    report_name = "Initialization Summary"
    table_name = "ZoneVentilation Airflow Stats Nominal"
    tbstr = df[
        (df.ReportName == report_name) & (df.TableName == table_name)
    ].reset_index()
    if tbstr.empty:
        log(
            "Table {} does not exist. "
            "Returning an empty DataFrame".format(table_name),
            lg.WARNING,
        )
        return pd.DataFrame([])
    tbpiv = tbstr.pivot_table(
        index=["Archetype", "RowName"],
        columns="ColumnName",
        values="Value",
        aggfunc=lambda x: " ".join(x),
    )

    tbpiv = tbpiv.replace({"N/A": np.nan}).apply(
        lambda x: pd.to_numeric(x, errors="ignore")
    )
    tbpiv = (
        tbpiv.reset_index()
        .groupby(["Archetype", "Zone Name", "Fan Type {Exhaust;Intake;Natural}"])
        .apply(nominal_ventilation_aggregation)
    )
    return tbpiv
    # .reset_index().groupby(['Archetype', 'Zone Name']).agg(
    # lambda x: pd.to_numeric(x, errors='ignore').sum())


def nominal_ventilation_aggregation(x):
    """Aggregate the ventilation objects whithin a single zone_loads name.

    Implies that .groupby(['Archetype', 'Zone Name']) is performed before calling
    this function).

    Args:
        x:

    Returns:
        A DataFrame with at least one entry per ('Archetype', 'Zone Name'),
        aggregated accordingly.
    """
    how_dict = {
        "Name": top(x["Name"], x, "Zone Floor Area {m2}"),
        "Schedule Name": top(x["Schedule Name"], x, "Zone Floor Area {m2}"),
        "Zone Floor Area {m2}": top(
            x["Zone Floor Area {m2}"], x, "Zone Floor Area {m2}"
        ),
        "# Zone Occupants": top(x["# Zone Occupants"], x, "Zone Floor Area {m2}"),
        "Design Volume Flow Rate {m3/s}": weighted_mean(
            x["Design Volume Flow Rate {m3/s}"], x, "Zone Floor Area {m2}"
        ),
        "Volume Flow Rate/Floor Area {m3/s/m2}": weighted_mean(
            x.filter(like="Volume Flow Rate/Floor Area").squeeze(axis=1),
            x,
            "Zone Floor Area {m2}",
        ),
        "Volume Flow Rate/person Area {m3/s/person}": weighted_mean(
            x.filter(like="Volume Flow Rate/person Area").squeeze(axis=1),
            x,
            "Zone Floor " "Area {m2}",
        ),
        "ACH - Air Changes per Hour": weighted_mean(
            x["ACH - Air Changes per Hour"], x, "Zone Floor Area {m2}"
        ),
        "Fan Pressure Rise {Pa}": weighted_mean(
            x["Fan Pressure Rise {Pa}"], x, "Zone Floor Area {m2}"
        ),
        "Fan Efficiency {}": weighted_mean(
            x["Fan Efficiency {}"], x, "Zone Floor Area {m2}"
        ),
        "Equation A - Constant Term Coefficient {}": top(
            x["Equation A - Constant Term Coefficient {}"], x, "Zone Floor Area {m2}"
        ),
        "Equation B - Temperature Term Coefficient {1/C}": top(
            x["Equation B - Temperature Term Coefficient {1/C}"],
            x,
            "Zone Floor Area {m2}",
        ),
        "Equation C - Velocity Term Coefficient {s/m}": top(
            x["Equation C - Velocity Term Coefficient {s/m}"], x, "Zone Floor Area {m2}"
        ),
        "Equation D - Velocity Squared Term Coefficient {s2/m2}": top(
            x["Equation D - Velocity Squared Term Coefficient {s2/m2}"],
            x,
            "Zone Floor Area {m2}",
        ),
        "Minimum Indoor Temperature{C}/Schedule": top(
            x["Minimum Indoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Maximum Indoor Temperature{C}/Schedule": top(
            x["Maximum Indoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Delta Temperature{C}/Schedule": top(
            x["Delta Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Minimum Outdoor Temperature{C}/Schedule": top(
            x["Minimum Outdoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Maximum Outdoor Temperature{C}/Schedule": top(
            x["Maximum Outdoor Temperature{C}/Schedule"], x, "Zone Floor Area {m2}"
        ),
        "Maximum WindSpeed{m/s}": top(
            x["Maximum WindSpeed{m/s}"], x, "Zone Floor Area {m2}"
        ),
    }
    try:
        df = pd.DataFrame(how_dict, index=range(0, 1))  # range should always be
        # one since we are trying to merge zones
    except Exception as e:
        log("{}".format(e))
    else:
        return df


def get_from_tabulardata(results):
    """Return a DataFrame from the 'TabularDataWithStrings' table.

    A MultiIndex is returned with names ['Archetype', 'Index'].
    """
    tab_data_wstring = pd.concat(
        [value["TabularDataWithStrings"] for value in results.values()],
        keys=results.keys(),
        names=["Archetype"],
    )
    tab_data_wstring.index.names = ["Archetype", "Index"]  #
    # strip whitespaces
    tab_data_wstring.Value = tab_data_wstring.Value.str.strip()
    tab_data_wstring.RowName = tab_data_wstring.RowName.str.strip()
    return tab_data_wstring
