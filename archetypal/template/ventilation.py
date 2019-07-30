################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

import archetypal
from archetypal import log
from archetypal.template import UmiBase, Unique


def resolve_temp(temp, idf):
    """Resolve the temperature. If a float is passed, simply return it. If a str
    is passed, get the schedule and return the mean value.

    Args:
        temp (float or str):
        idf (IDF): the idf object
    """
    if isinstance(temp, float):
        return temp
    elif isinstance(temp, str):
        sched = archetypal.UmiSchedule(Name=temp, idf=idf)
        return sched.values.mean()


class VentilationSetting(UmiBase, metaclass=Unique):
    """Zone Ventilation Settings

    .. image:: ../images/template/zoneinfo-ventilation.png
    """

    def __init__(self, NatVentSchedule=None, ScheduledVentilationSchedule=None,
                 Afn=False, Infiltration=0.1, IsBuoyancyOn=True,
                 IsInfiltrationOn=True, IsNatVentOn=False,
                 IsScheduledVentilationOn=False, IsWindOn=False,
                 NatVentMaxOutdoorAirTemp=30, NatVentMaxRelHumidity=90,
                 NatVentMinOutdoorAirTemp=0, NatVentZoneTempSetpoint=18,
                 ScheduledVentilationAch=0.6, ScheduledVentilationSetpoint=18,
                 **kwargs):
        """Initialize a new VentilationSetting (for zone) object

        Args:
            NatVentSchedule (UmiSchedule, optional): The name of the schedule
                (Day | Week | Year) which ultimately modifies the Opening Area
                value (see previous field). In its current implementation, any
                value greater than 0 will consider, value above The schedule
                values must be any positive number between 0 and 1 as a
                fraction.
            ScheduledVentilationSchedule (UmiSchedule, optional): The name of
                the schedule (Schedules Tab) that modifies the maximum design
                volume flow rate. This fraction is between 0.0 and 1.0.
            Afn (bool):
            Infiltration (float): Infiltration rate in ACH
            IsBuoyancyOn (bool): If True, simulation takes into account the
                stack effect in the infiltration calculation
            IsInfiltrationOn (bool): If yes, there is heat transfer between the
                building and the outside caused by infiltration
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
            **kwargs:
        """
        super(VentilationSetting, self).__init__(**kwargs)
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

        self._belongs_to_zone = kwargs.get('zone', None)

    def __add__(self, other):
        return self.combine(other)

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
    def from_zone(cls, zone):
        """
        Todo:
            - Refactor :func:`do_infiltration`, :func:`do_natural_ventilation`
              and :func:`do_scheduled_ventilation` to use the
              :class:`ReportData` in order to completely remove core.py.

        Args:
            zone (archetypal.template.zone.Zone): zone to gets information from
        """

        name = zone.Name + "_VentilationSetting"

        df = {"a": zone.sql}
        ni_df = archetypal.nominal_infiltration(df)
        sched_df = archetypal.nominal_mech_ventilation(df)
        nat_df = archetypal.nominal_nat_ventilation(df)
        index = ("a", zone.Name.upper())

        # Do infiltration
        Infiltration, IsInfiltrationOn = \
            do_infiltration(index, ni_df, zone)

        # Do natural ventilation
        IsNatVentOn, IsWindOn, IsBuoyancyOn, NatVentMaxOutdoorAirTemp, \
        NatVentMaxRelHumidity, NatVentMinOutdoorAirTemp, NatVentSchedule, \
        NatVentZoneTempSetpoint = \
            do_natural_ventilation(index, nat_df, zone)

        # Do scheduled ventilation
        ScheduledVentilationSchedule, IsScheduledVentilationOn, \
        ScheduledVentilationAch, ScheduledVentilationSetpoint = \
            do_scheduled_ventilation(index, sched_df, zone)

        z_vent = cls(Name=name, zone=zone,
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
                     idf=zone.idf)
        return z_vent

    def combine(self, other, weights=None):
        """Combine two VentilationSetting objects together.

        Args:
            other (VentilationSetting):
            weights (list-like, optional): A list-like object of len 2. If None,
                the volume of the zones for which self and other belongs is
                used.

        Returns:
            (VentilationSetting): the combined VentilationSetting object.
        """
        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = 'Cannot combine %s with %s' % (self.__class__.__name__,
                                                 other.__class__.__name__)
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        meta = self._get_predecessors_meta(other)

        if not weights:
            log('using zone volume as weighting factor in "{}" '
                'combine.'.format(self.__class__.__name__))
            weights = [self._belongs_to_zone.volume,
                       other._belongs_to_zone.volume]
        a = self.NatVentSchedule.combine(other.NatVentSchedule, weights)
        # a = self._float_mean(other, 'NatVentSchedule', weights)
        b = self.ScheduledVentilationSchedule.combine(
            other.ScheduledVentilationSchedule, weights)
        # b = self._float_mean(other, 'ScheduledVentilationSchedule', weights)
        c = any((self.Afn, other.Afn))
        d = self._float_mean(other, 'Infiltration', weights)
        e = any((self.IsBuoyancyOn, other.IsBuoyancyOn))
        f = any((self.IsInfiltrationOn, other.IsInfiltrationOn))
        g = any((self.IsNatVentOn, other.IsNatVentOn))
        h = any((self.IsScheduledVentilationOn, other.IsScheduledVentilationOn))
        i = any((self.IsWindOn, other.IsWindOn))
        j = self._float_mean(other, 'NatVentMaxOutdoorAirTemp', weights)
        k = self._float_mean(other, 'NatVentMaxRelHumidity', weights)
        l = self._float_mean(other, 'NatVentMinOutdoorAirTemp', weights)
        m = self._float_mean(other, 'NatVentZoneTempSetpoint', weights)
        n = self._float_mean(other, 'ScheduledVentilationAch', weights)
        o = self._float_mean(other, 'ScheduledVentilationSetpoint', weights)

        attr = dict(NatVentSchedule=a, ScheduledVentilationSchedule=b, Afn=c,
                    Infiltration=d, IsBuoyancyOn=e, IsInfiltrationOn=f,
                    IsNatVentOn=g, IsScheduledVentilationOn=h, IsWindOn=i,
                    NatVentMaxOutdoorAirTemp=j, NatVentMaxRelHumidity=k,
                    NatVentMinOutdoorAirTemp=l, NatVentZoneTempSetpoint=m,
                    ScheduledVentilationAch=n, ScheduledVentilationSetpoint=o)

        # create a new object with the previous attributes
        new_obj = self.__class__(**meta, **attr)
        new_obj._predecessors.extend(self.predecessors + other.predecessors)
        return new_obj


def do_infiltration(index, inf_df, zone):
    """Gets infiltration information of the zone

    Args:
        index (tuple): Zone name
        inf_df (dataframe): Dataframe with infiltration information for each
            zone
        zone (archetypal.template.zone.Zone): zone to gets information from
    """
    if not inf_df.empty:
        try:
            Infiltration = inf_df.loc[index, 'ACH - Air Changes per Hour']
            IsInfiltrationOn = any(inf_df.loc[index, 'Name'])
        except:
            Infiltration = 0
            IsInfiltrationOn = False
    else:
        Infiltration = 0
        IsInfiltrationOn = False
    return Infiltration, IsInfiltrationOn


def do_natural_ventilation(index, nat_df, zone):
    """Gets natural ventilation information of the zone

    Args:
        index (tuple): Zone name
        nat_df:
        zone (archetypal.template.zone.Zone): zone to gets information from
    """
    if not nat_df.empty:
        try:
            IsNatVentOn = any(nat_df.loc[index, "Name"])
            schedule_name_ = nat_df.loc[index, "Schedule Name"]
            NatVentSchedule = archetypal.UmiSchedule(Name=schedule_name_,
                                                     idf=zone.idf)
            NatVentMaxRelHumidity = 90  # todo: not sure if it is being used
            NatVentMaxOutdoorAirTemp = resolve_temp(nat_df.loc[
                                                        index, "Maximum "
                                                               "Outdoor "
                                                               "Temperature{"
                                                               "C}/Schedule"],
                                                    zone.idf)
            NatVentMinOutdoorAirTemp = resolve_temp(nat_df.loc[
                                                        index, "Minimum "
                                                               "Outdoor "
                                                               "Temperature{"
                                                               "C}/Schedule"],
                                                    zone.idf)
            NatVentZoneTempSetpoint = resolve_temp(nat_df.loc[
                                                       index, "Minimum Indoor "
                                                              "Temperature{"
                                                              "C}/Schedule"],
                                                   zone.idf)
        except:
            # todo: For some reason, a ZoneVentilation:WindandStackOpenArea
            #  'Opening Area Fraction Schedule Name' is read as Constant-0.0
            #  in the nat_df. For the mean time, a zone containing such an
            #  object will revert to defaults (below).
            IsNatVentOn = False
            NatVentSchedule = archetypal.UmiSchedule.constant_schedule()
            NatVentMaxRelHumidity = 90
            NatVentMaxOutdoorAirTemp = 30
            NatVentMinOutdoorAirTemp = 0
            NatVentZoneTempSetpoint = 18

    else:
        IsNatVentOn = False
        NatVentSchedule = archetypal.UmiSchedule.constant_schedule()
        NatVentMaxRelHumidity = 90
        NatVentMaxOutdoorAirTemp = 30
        NatVentMinOutdoorAirTemp = 0
        NatVentZoneTempSetpoint = 18

    # Is Wind ON
    if not zone.idf.idfobjects[
        'ZoneVentilation:WindandStackOpenArea'.upper()].list1:
        IsWindOn = False
        IsBuoyancyOn = False
    else:
        try:
            equ_b = nat_df.loc[
                index, "Equation B - Temperature Term Coefficient {1/C}"]
            if equ_b != 0:
                IsBuoyancyOn = True
            equ_w = nat_df.loc[
                index, "Equation C - Velocity Term Coefficient {s/m}"]
            if equ_w != 0:
                IsWindOn = True
        except:
            IsWindOn = False
            IsBuoyancyOn = False

    return IsNatVentOn, IsWindOn, IsBuoyancyOn, NatVentMaxOutdoorAirTemp, \
           NatVentMaxRelHumidity, NatVentMinOutdoorAirTemp, NatVentSchedule, \
           NatVentZoneTempSetpoint


def do_scheduled_ventilation(index, scd_df, zone):
    """Gets schedule ventilation information of the zone

    Args:
        index (tuple): Zone name
        scd_df:
        zone (archetypal.template.zone.Zone): zone to gets information from
    """
    if not scd_df.empty:
        try:
            IsScheduledVentilationOn = any(scd_df.loc[index, "Name"])
            schedule_name_ = scd_df.loc[index, "Schedule Name"]
            ScheduledVentilationSchedule = archetypal.UmiSchedule(
                Name=schedule_name_, idf=zone.idf)
            ScheduledVentilationAch = scd_df.loc[
                index, 'ACH - Air Changes per Hour']
            ScheduledVentilationSetpoint = resolve_temp(scd_df.loc[index,
                                                                   'Minimum '
                                                                   'Indoor '
                                                                   'Temperature{'
                                                                   'C}/Schedule'],
                                                        zone.idf)
        except:
            ScheduledVentilationSchedule = \
                archetypal.UmiSchedule.constant_schedule(hourly_value=0)
            IsScheduledVentilationOn = False
            ScheduledVentilationAch = 0
            ScheduledVentilationSetpoint = 18
    else:
        ScheduledVentilationSchedule = \
            archetypal.UmiSchedule.constant_schedule(hourly_value=0)
        IsScheduledVentilationOn = False
        ScheduledVentilationAch = 0
        ScheduledVentilationSetpoint = 18
    return ScheduledVentilationSchedule, IsScheduledVentilationOn, \
           ScheduledVentilationAch, ScheduledVentilationSetpoint
