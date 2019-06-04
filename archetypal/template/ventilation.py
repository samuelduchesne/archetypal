################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal.template import UmiBase, Unique


class VentilationSetting(UmiBase, metaclass=Unique):
    """
    $id, Afn, Infiltration, IsBuoyancyOn, IsInfiltrationOn, IsNatVentOn,
    IsScheduledVentilationOn, IsWindOn, NatVentMaxOutdoorAirTemp,
    NatVentMaxRelHumidity, NatVentMinOutdoorAirTemp, NatVentSchedule.$ref,
    NatVentZoneTempSetpoint, ScheduledVentilationAch,
    ScheduledVentilationSchedule.$ref, ScheduledVentilationSetpoint
    """

    def __init__(self, *args, NatVentSchedule=None,
                 ScheduledVentilationSchedule=None,
                 Afn=False, Infiltration=0.1, IsBuoyancyOn=True,
                 IsInfiltrationOn=True,
                 IsNatVentOn=False,
                 IsScheduledVentilationOn=False, IsWindOn=False,
                 NatVentMaxOutdoorAirTemp=30,
                 NatVentMaxRelHumidity=90, NatVentMinOutdoorAirTemp=0,
                 NatVentZoneTempSetpoint=18, ScheduledVentilationAch=0.6,
                 ScheduledVentilationSetpoint=18, **kwargs):
        """
        Args:
            *args:
            NatVentSchedule:
            ScheduledVentilationSchedule:
            Afn:
            Infiltration:
            IsBuoyancyOn:
            IsInfiltrationOn:
            IsNatVentOn:
            IsScheduledVentilationOn:
            IsWindOn:
            NatVentMaxOutdoorAirTemp:
            NatVentMaxRelHumidity:
            NatVentMinOutdoorAirTemp:
            NatVentZoneTempSetpoint:
            ScheduledVentilationAch:
            ScheduledVentilationSetpoint:
            **kwargs:
        """
        super(VentilationSetting, self).__init__(*args, **kwargs)
        self.Afn = Afn
        self.Infiltration = Infiltration
        self.IsBuoyancyOn = IsBuoyancyOn
        self.IsInfiltrationOn = IsInfiltrationOn
        self.IsNatVentOn = IsNatVentOn
        self.IsScheduledVentilationOn = IsScheduledVentilationOn
        self.IsWindOn = IsWindOn
        self.NatVentMaxOutdoorAirTemp = NatVentMaxOutdoorAirTemp
        self.NatVentMaxRelHumidity = NatVentMaxRelHumidity
        self.NatVentMinOutdoorAirTemp = NatVentMinOutdoorAirTemp
        self.NatVentZoneTempSetpoint = NatVentZoneTempSetpoint
        self.ScheduledVentilationAch = ScheduledVentilationAch
        self.ScheduledVentilationSetpoint = ScheduledVentilationSetpoint

        self.ScheduledVentilationSchedule = ScheduledVentilationSchedule
        self.NatVentSchedule = NatVentSchedule

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        vs = cls(*args, **kwargs)
        vent_sch = kwargs.get('ScheduledVentilationSchedule', None)
        vs.ScheduledVentilationSchedule = vs.get_ref(vent_sch)
        nat_sch = kwargs.get('NatVentSchedule', None)
        vs.NatVentSchedule = vs.get_ref(nat_sch)
        return vs

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["Afn"] = self.Afn
        data_dict["IsBuoyancyOn"] = self.IsBuoyancyOn
        data_dict["Infiltration"] = self.Infiltration
        data_dict["IsInfiltrationOn"] = self.IsInfiltrationOn
        data_dict["IsNatVentOn"] = self.IsNatVentOn
        data_dict["IsScheduledVentilationOn"] = self.IsScheduledVentilationOn
        data_dict["NatVentMaxRelHumidity"] = self.NatVentMaxRelHumidity
        data_dict["NatVentMaxOutdoorAirTemp"] = self.NatVentMaxOutdoorAirTemp
        data_dict["NatVentMinOutdoorAirTemp"] = self.NatVentMinOutdoorAirTemp
        data_dict["NatVentSchedule"] = self.NatVentSchedule.to_dict()
        data_dict["NatVentZoneTempSetpoint"] = self.NatVentZoneTempSetpoint
        data_dict["ScheduledVentilationAch"] = self.ScheduledVentilationAch
        data_dict["ScheduledVentilationSchedule"] = \
            self.ScheduledVentilationSchedule.to_dict()
        data_dict["ScheduledVentilationSetpoint"] = \
            self.ScheduledVentilationSetpoint
        data_dict["IsWindOn"] = self.IsWindOn
        data_dict["Category"] = self.Category
        data_dict["Comments"] = self.Comments
        data_dict["DataSource"] = self.DataSource
        data_dict["Name"] = self.Name

        return data_dict

    @classmethod
    def from_epbunch(cls, zone):
        # todo: create zone ventilation settings from epbunch
        """
        Args:
            zone (EpBunch):
        """
        pass

    @classmethod
    def from_zone(cls, zone):
        """
        Args:
            zone (archetypal.template.zone.Zone):
        """
        # todo: to finish
        name = zone.Name + "_VentilationSetting"
        z_vent = cls(Name=name)
        return z_vent
