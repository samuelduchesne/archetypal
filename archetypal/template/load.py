import collections

from archetypal.template import UmiBase, Unique


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
        """
        Args:
            *args:
            DimmingType:
            EquipmentAvailabilitySchedule:
            EquipmentPowerDensity:
            IlluminanceTarget:
            LightingPowerDensity:
            LightsAvailabilitySchedule:
            OccupancySchedule:
            IsEquipmentOn:
            IsLightingOn:
            IsPeopleOn:
            PeopleDensity:
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
            zone (archetypal.template.zone.Zone):
        """
        # todo: to finish
        name = zone.Name + "_ZoneLoad"
        z_load = cls(Name=name)
        return z_load