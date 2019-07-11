################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal.template import UmiBase, Unique, UmiSchedule


class ZoneLoad(UmiBase, metaclass=Unique):
    """
    $id, Category, Comments, DataSource, DimmingType,
    EquipmentAvailabilitySchedule.$ref, EquipmentPowerDensity,
    IlluminanceTarget, IsEquipmentOn, IsLightingOn, IsPeopleOn,
    LightingPowerDensity, LightsAvailabilitySchedule.$ref, Name,
    OccupancySchedule.$ref, PeopleDensity
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
                illuminance:
                * If `Continuous` : the overhead lights dim continuously and
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

        a = 1
        # Get schedule index for different loads and creates ZoneLoad arguments
        # Verifies if Equipment in zone
        if zone.sql['NominalElectricEquipment'][
            zone.sql['NominalElectricEquipment']['ObjectName'].str.contains(
                zone.Name.upper())].empty:
            EquipmentAvailabilitySchedule = None
            EquipmentPowerDensity = 0.0
        else:
            schedule_equipment_index = zone.sql['NominalElectricEquipment'][
                zone.sql['NominalElectricEquipment']['ObjectName'].str.contains(
                    zone.Name.upper())]['ScheduleIndex'].iloc[0]
            EquipmentAvailabilitySchedule = \
                UmiSchedule(Name=zone.sql['Schedules']['ScheduleName'].iloc[
                    schedule_equipment_index - 1], idf=zone.idf)
            EquipmentPowerDensity = zone.sql['NominalElectricEquipment'][
                zone.sql['NominalElectricEquipment']['ObjectName'].str.contains(
                    zone.Name.upper())]['DesignLevel'].iloc[0] / zone.area
        # Verifies if Lights in zone
        if zone.sql['NominalLighting'][
            zone.sql['NominalLighting']['ObjectName'].str.contains(
                zone.Name.upper())].empty:
            LightsAvailabilitySchedule = None
            LightingPowerDensity = 0.0
        else:
            schedule_light_index = zone.sql['NominalLighting'][
                zone.sql['NominalLighting']['ObjectName'].str.contains(
                    zone.Name.upper())]['ScheduleIndex'].iloc[0]
            LightsAvailabilitySchedule = UmiSchedule(
                Name=zone.sql['Schedules']['ScheduleName'].iloc[
                    schedule_light_index - 1], idf=zone.idf)
            LightingPowerDensity = zone.sql['NominalLighting'][
                zone.sql['NominalLighting']['ObjectName'].str.contains(
                    zone.Name.upper())]['DesignLevel'].iloc[0] / zone.area
        # Verifies if People in zone
        if zone.sql['NominalPeople'][
            zone.sql['NominalPeople']['ObjectName'].str.contains(
                zone.Name.upper())].empty:
            OccupancySchedule = None
            PeopleDensity = 0.0
        else:
            schedule_people_index = zone.sql['NominalPeople'][
                zone.sql['NominalPeople']['ObjectName'].str.contains(
                    zone.Name.upper())]['NumberOfPeopleScheduleIndex'].iloc[0]
            OccupancySchedule = UmiSchedule(
                Name=zone.sql['Schedules']['ScheduleName'].iloc[
                    schedule_people_index - 1], idf=zone.idf)
            PeopleDensity = zone.sql['NominalPeople'][
                zone.sql['NominalPeople']['ObjectName'].str.contains(
                    zone.Name.upper())]['NumberOfPeople'].iloc[0] / zone.area

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
                     PeopleDensity=PeopleDensity)
        return z_load
