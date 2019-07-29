################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal.template import UmiBase, Unique, UmiSchedule
from archetypal import log


class ZoneLoad(UmiBase, metaclass=Unique):
    """Zone Loads

    .. image:: ../images/template/zoneinfo-loads.png
    """

    def __init__(self, *args,
                 DimmingType='Continuous',
                 EquipmentAvailabilitySchedule=None,
                 EquipmentPowerDensity=12,
                 IlluminanceTarget=500,
                 LightingPowerDensity=12,
                 LightsAvailabilitySchedule=None,
                 OccupancySchedule=None,
                 IsEquipmentOn=True,
                 IsLightingOn=True,
                 IsPeopleOn=True,
                 PeopleDensity=0.2,
                 **kwargs):
        """Initialize a new ZoneLoad object

        Args:
            *args:
            DimmingType (str): Different types to dim the lighting to respect
                the IlluminanceTraget and taking into account the daylight
                illuminance: * If `Continuous` : the overhead lights dim
                continuously and

                    linearly from (maximum electric power, maximum light output)
                    to (minimum electric power, minimum light output) as the
                    daylight illuminance increases. The lights stay on at the
                    minimum point with further increase in the daylight
                    illuminance

                * If `Stepped`: the electric power input and light output vary
                      in discrete, equally spaced steps

                * If `Off`: Lights switch off completely when the minimum
                      dimming point is reached
            EquipmentAvailabilitySchedule (UmiSchedule, optional): The name of
                the schedule (Day | Week | Year) that modifies the design level
                parameter for electric equipment.
            EquipmentPowerDensity (float): Equipment Power Density in the zone
                (W/m²)
            IlluminanceTarget (float): Number of lux to be respected in the zone
            LightingPowerDensity (float): Lighting Power Density in the zone
                (W/m²)
            LightsAvailabilitySchedule (UmiSchedule, optional): The name of the
                schedule (Day | Week | Year) that modifies the design level
                parameter for lighting.
            OccupancySchedule (UmiSchedule, optional): The name of the schedule
                (Day | Week | Year) that modifies the number of people parameter
                for electric equipment.
            IsEquipmentOn (bool): If True, heat gains from Equipment are taken
                into account for the zone's load calculation
            IsLightingOn (bool): If True, heat gains from Lights are taken into
                account for the zone's load calculation
            IsPeopleOn (bool): If True, heat gains from People are taken into
                account for the zone's load calculation
            PeopleDensity (float): Density of people in the zone (people/m²)
            **kwargs:
        """
        super(ZoneLoad, self).__init__(*args, **kwargs)
        self.DimmingType = DimmingType
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

        self._belongs_to_zone = kwargs.get('zone', None)

    def __add__(self, other):
        """
        Args:
            other (Zone):
        """
        return self.combine(other)

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        zl = cls(*args, **kwargs)

        cool_schd = kwargs.get('EquipmentAvailabilitySchedule', None)
        zl.EquipmentAvailabilitySchedule = zl.get_ref(cool_schd)
        heat_schd = kwargs.get('LightsAvailabilitySchedule', None)
        zl.LightsAvailabilitySchedule = zl.get_ref(heat_schd)
        mech_schd = kwargs.get('OccupancySchedule', None)
        zl.OccupancySchedule = zl.get_ref(mech_schd)

        return zl

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["DimmingType"] = self.DimmingType
        data_dict["EquipmentAvailabilitySchedule"] = \
            self.EquipmentAvailabilitySchedule.to_dict()
        data_dict["EquipmentPowerDensity"] = self.EquipmentPowerDensity
        data_dict["IlluminanceTarget"] = self.IlluminanceTarget
        data_dict["LightingPowerDensity"] = self.LightingPowerDensity
        data_dict["LightsAvailabilitySchedule"] = \
            self.LightsAvailabilitySchedule.to_dict()
        data_dict["OccupancySchedule"] = self.OccupancySchedule.to_dict()
        data_dict["IsEquipmentOn"] = self.IsEquipmentOn
        data_dict["IsLightingOn"] = self.IsLightingOn
        data_dict["IsPeopleOn"] = self.IsPeopleOn
        data_dict["PeopleDensity"] = self.PeopleDensity
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_zone(cls, zone):
        """
        Args:
            zone (archetypal.template.zone.Zone): zone to gets information from
        """

        # Get schedule index for different loads and creates ZoneLoad arguments
        # Verifies if Equipment in zone
        if zone.sql['NominalElectricEquipment'][
            zone.sql['NominalElectricEquipment']['ObjectName'].str.contains(
                zone.Name.upper())].empty:
            EquipmentAvailabilitySchedule = UmiSchedule.constant_schedule(
                idf=zone.idf)
            EquipmentPowerDensity = 0.0
        else:
            schedule_equipment_index = zone.sql['NominalElectricEquipment'][
                zone.sql['NominalElectricEquipment']['ObjectName'].str.contains(
                    zone.Name.upper())]['ScheduleIndex'].iloc[0]
            EquipmentAvailabilitySchedule = \
                UmiSchedule(Name=zone.sql['Schedules']['ScheduleName'].iloc[
                    schedule_equipment_index - 1], idf=zone.idf)
            EquipmentPowerDensity = zone.sql['NominalElectricEquipment'][
                                        zone.sql['NominalElectricEquipment'][
                                            'ObjectName'].str.contains(
                                            zone.Name.upper())][
                                        'DesignLevel'].iloc[0] / zone.area
        # Verifies if Lights in zone
        if zone.sql['NominalLighting'][
            zone.sql['NominalLighting']['ObjectName'].str.contains(
                zone.Name.upper())].empty:
            LightsAvailabilitySchedule = UmiSchedule.constant_schedule(
                idf=zone.idf)
            LightingPowerDensity = 0.0
        else:
            schedule_light_index = zone.sql['NominalLighting'][
                zone.sql['NominalLighting']['ObjectName'].str.contains(
                    zone.Name.upper())]['ScheduleIndex'].iloc[0]
            LightsAvailabilitySchedule = UmiSchedule(
                Name=zone.sql['Schedules']['ScheduleName'].iloc[
                    schedule_light_index - 1], idf=zone.idf)
            LightingPowerDensity = zone.sql['NominalLighting'][
                                       zone.sql['NominalLighting'][
                                           'ObjectName'].str.contains(
                                           zone.Name.upper())][
                                       'DesignLevel'].iloc[0] / zone.area
        # Verifies if People in zone
        if zone.sql['NominalPeople'][
            zone.sql['NominalPeople']['ObjectName'].str.contains(
                zone.Name.upper())].empty:
            OccupancySchedule = UmiSchedule.constant_schedule(
                idf=zone.idf)
            PeopleDensity = 0.0
        else:
            schedule_people_index = zone.sql['NominalPeople'][
                zone.sql['NominalPeople']['ObjectName'].str.contains(
                    zone.Name.upper())]['NumberOfPeopleScheduleIndex'].iloc[0]
            OccupancySchedule = UmiSchedule(
                Name=zone.sql['Schedules']['ScheduleName'].iloc[
                    schedule_people_index - 1], idf=zone.idf)
            PeopleDensity = zone.sql['NominalPeople'][
                                zone.sql['NominalPeople'][
                                    'ObjectName'].str.contains(
                                    zone.Name.upper())]['NumberOfPeople'].iloc[
                                0] / zone.area

        name = zone.Name + "_ZoneLoad"
        z_load = cls(Name=name, zone=zone,
                     DimmingType='Continuous',
                     EquipmentAvailabilitySchedule=EquipmentAvailabilitySchedule,
                     EquipmentPowerDensity=EquipmentPowerDensity,
                     IlluminanceTarget=500,
                     LightingPowerDensity=LightingPowerDensity,
                     LightsAvailabilitySchedule=LightsAvailabilitySchedule,
                     OccupancySchedule=OccupancySchedule,
                     IsEquipmentOn=EquipmentPowerDensity > 0,
                     IsLightingOn=LightingPowerDensity > 0,
                     IsPeopleOn=PeopleDensity > 0,
                     PeopleDensity=PeopleDensity,
                     idf=zone.idf)
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
        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = 'Cannot combine %s with %s' % (self.__class__.__name__,
                                                 other.__class__.__name__)
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        incoming_load_data = self.__dict__.copy()
        incoming_load_data.pop('Name')

        # the new object's name
        name = '+'.join([self.Name, other.Name])

        if not weights:
            log('using zone volume as weighting factor in "{}" '
                'combine.'.format(self.__class__.__name__))
            weights = [self._belongs_to_zone.volume,
                       other._belongs_to_zone.volume]

        attr = dict(DimmingType=self._str_mean(other, 'DimmingType'),
                    EquipmentAvailabilitySchedule=
                    self.EquipmentAvailabilitySchedule.combine(
                        other.EquipmentAvailabilitySchedule),
                    EquipmentPowerDensity=
                    self._float_mean(other,
                                     'EquipmentPowerDensity', weights),
                    IlluminanceTarget=
                    self._float_mean(other,
                                     'IlluminanceTarget', weights),
                    LightingPowerDensity=
                    self._float_mean(other,
                                     'LightingPowerDensity', weights),
                    LightsAvailabilitySchedule=
                    self.LightsAvailabilitySchedule.combine(
                        other.LightsAvailabilitySchedule, weights),
                    OccupancySchedule=self.OccupancySchedule.combine(
                        other.OccupancySchedule, weights),
                    IsEquipmentOn=any(
                        [self.IsEquipmentOn, other.IsEquipmentOn]),
                    IsLightingOn=any([self.IsLightingOn, other.IsLightingOn]),
                    IsPeopleOn=any([self.IsPeopleOn, other.IsPeopleOn]),
                    PeopleDensity=
                    self._float_mean(other,
                                     'PeopleDensity', weights))

        new_obj = self.__class__(Name=name, **attr)
        new_obj._belongs_to_zone = self._belongs_to_zone

        return new_obj
