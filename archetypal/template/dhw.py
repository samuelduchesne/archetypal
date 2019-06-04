################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal.template import Unique, UmiBase


class DomesticHotWaterSetting(UmiBase, metaclass=Unique):
    """
    $id, Category, Comments, DataSource, FlowRatePerFloorArea, IsOn, Name,
    WaterSchedule.$ref, WaterSupplyTemperature, WaterTemperatureInlet
    """

    def __init__(self, IsOn=True, WaterSchedule=None,
                 FlowRatePerFloorArea=-0.03, WaterSupplyTemperature=65,
                 WaterTemperatureInlet=10, **kwargs):
        """
        Args:
            IsOn (bool):
            WaterSchedule (archetypal.template.schedule.YearSchedule):
            FlowRatePerFloorArea (float):
            WaterSupplyTemperature (float):
            WaterTemperatureInlet (float):
            **kwargs:
        """
        super(DomesticHotWaterSetting, self).__init__(**kwargs)
        self.FlowRatePerFloorArea = FlowRatePerFloorArea
        self.IsOn = IsOn
        self.WaterSupplyTemperature = WaterSupplyTemperature
        self.WaterTemperatureInlet = WaterTemperatureInlet
        self.WaterSchedule = WaterSchedule

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        dhws = cls(*args, **kwargs)
        wat_sch = kwargs.get('WaterSchedule', None)
        dhws.WaterSchedule = dhws.get_ref(wat_sch)
        return dhws

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["FlowRatePerFloorArea"] = self.FlowRatePerFloorArea
        data_dict["IsOn"] = self.IsOn
        data_dict["WaterSchedule"] = self.WaterSchedule.to_dict()
        data_dict["WaterSupplyTemperature"] = self.WaterSupplyTemperature
        data_dict["WaterTemperatureInlet"] = self.WaterTemperatureInlet
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_epbunch(cls, zone):
        # Todo: Create DHW settings fom epbunch
        """
        Args:
            zone (EpBunch):
        """
        pass

    @classmethod
    def from_zone(cls, zone):
        """
        Args:
            zone (Zone):
        """
        # todo: to finish
        name = zone.Name + "_DHW"
        z_dhw = cls(Name=name)
        return z_dhw
