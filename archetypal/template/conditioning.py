################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal.template import UmiBase, Unique, UmiSchedule


class ZoneConditioning(UmiBase, metaclass=Unique):
    """HVAC settings for the zone"""

    def __init__(self, CoolingCoeffOfPerf=None, CoolingLimitType='NoLimit',
                 CoolingSetpoint=26, EconomizerType='NoEconomizer',
                 HeatRecoveryEfficiencyLatent=0.65,
                 HeatRecoveryEfficiencySensible=0.7, HeatRecoveryType=None,
                 HeatingCoeffOfPerf=None, HeatingLimitType='NoLimit',
                 HeatingSetpoint=20, IsCoolingOn=True, IsHeatingOn=True,
                 IsMechVentOn=True, MaxCoolFlow=100, MaxCoolingCapacity=100,
                 MaxHeatFlow=100, MaxHeatingCapacity=100,
                 MinFreshAirPerArea=0, MinFreshAirPerPerson=0.00944,
                 **kwargs):
        """Initialize a new ZoneCondition object

        Args:
            CoolingCoeffOfPerf (float): Performance factor of cooling system.
                This value is used in deriving the total cooling energy use by
                dividing the cooling load by the COP.
            CoolingLimitType (str): The input must be either LimitFlowRate,
                LimitCapacity, LimitFlowRateAndCapacity or NoLimit.
            CoolingSetpoint (float): The temperature above which zone heating is
                turned on.
            EconomizerType (str): Specifies if there is an outdoor air
                economizer. The choices are: NoEconomizer, DifferentialDryBulb,
                or DifferentialEnthalpy.
            HeatRecoveryEfficiencyLatent (float): The latent heat recovery
                effectiveness, where effectiveness is defined as the change in
                supply humidity ratio divided by the difference in entering
                supply and relief air humidity ratios. The default is 0.65.
            HeatRecoveryEfficiencySensible (float): The sensible heat recovery
                effectiveness, where effectiveness is defined as the change in
                supply temperature divided by the difference in entering supply
                and relief air temperatures. The default is 0.70.
            HeatRecoveryType (str): Select from None, Sensible, or Enthalpy.
            HeatingCoeffOfPerf (float): Efficiency of heating system.
            HeatingLimitType (str): The input must be either LimitFlowRate,
                LimitCapacity, LimitFlowRateAndCapacity or NoLimit.
            HeatingSetpoint (float): The temperature below which zone heating is
                turned on.
            IsCoolingOn (bool): Whether or not this cooling is available.
            IsHeatingOn (bool): Whether or not this cooling is available.
            IsMechVentOn (bool): If True, an outdoor air quantity for use by the
                model is calculated.
            MaxCoolFlow (float): The maximum cooling supply air flow rate in
                cubic meters per second if Cooling Limit is set to LimitFlowRate
                or LimitFlowRateAndCapacity
            MaxCoolingCapacity (float): The maximum allowed total (sensible plus
                latent) cooling capacity in Watts per square meter.
            MaxHeatFlow (float): The maximum heating supply air flow rate in
                cubic meters per second if heating limit is set to LimitFlowRate
                or LimitFlowRateAndCapacity
            MaxHeatingCapacity (float): The maximum allowed sensible heating
                capacity in Watts if Heating Limit is set to LimitCapacity or
                LimitFlowRateAndCapacity
            MinFreshAirPerArea (flaot): The design outdoor air volume flow rate
                per square meter of floor area (units are m3/s-m2). This input
                is used if Outdoor Air Method is Flow/Area, Sum or Maximum
            MinFreshAirPerPerson (float): The design outdoor air volume flow
                rate per person for this zone in cubic meters per second per
                person. The default is 0.00944 (20 cfm per person).
            **kwargs: Other arguments passed to the base class
                :class:`archetypal.template.UmiBase`
        """
        super(ZoneConditioning, self).__init__(**kwargs)
        self.MechVentSchedule = None
        self.HeatingSchedule = None
        self.CoolingSchedule = None
        self.CoolingCoeffOfPerf = CoolingCoeffOfPerf
        self.CoolingLimitType = CoolingLimitType
        self.CoolingSetpoint = CoolingSetpoint
        self.EconomizerType = EconomizerType
        self.HeatRecoveryEfficiencyLatent = HeatRecoveryEfficiencyLatent
        self.HeatRecoveryEfficiencySensible = HeatRecoveryEfficiencySensible
        self.HeatRecoveryType = HeatRecoveryType
        self.HeatingCoeffOfPerf = HeatingCoeffOfPerf
        self.HeatingLimitType = HeatingLimitType
        self.HeatingSetpoint = HeatingSetpoint
        self.IsCoolingOn = IsCoolingOn
        self.IsHeatingOn = IsHeatingOn
        self.IsMechVentOn = IsMechVentOn
        self.MaxCoolFlow = MaxCoolFlow
        self.MaxCoolingCapacity = MaxCoolingCapacity
        self.MaxHeatFlow = MaxHeatFlow
        self.MaxHeatingCapacity = MaxHeatingCapacity
        self.MinFreshAirPerArea = MinFreshAirPerArea
        self.MinFreshAirPerPerson = MinFreshAirPerPerson

        self._belongs_to_zone = kwargs.get('zone', None)

    def __add__(self, other):
        return self.combine(other)

    @classmethod
    def from_idf(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        zc = ZoneConditioning(**kwargs)

        zc.MechVentSchedule = UmiSchedule.random_constant_schedule()
        zc.HeatingSchedule = UmiSchedule.random_constant_schedule()
        zc.CoolingSchedule = UmiSchedule.random_constant_schedule()
        return zc

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        zc = cls(*args, **kwargs)

        cool_schd = kwargs.get('CoolingSchedule', None)
        zc.CoolingSchedule = zc.get_ref(cool_schd)
        heat_schd = kwargs.get('HeatingSchedule', None)
        zc.HeatingSchedule = zc.get_ref(heat_schd)
        mech_schd = kwargs.get('MechVentSchedule', None)
        zc.MechVentSchedule = zc.get_ref(mech_schd)
        return zc

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["CoolingSchedule"] = self.CoolingSchedule.to_dict()
        data_dict["CoolingCoeffOfPerf"] = self.CoolingCoeffOfPerf
        data_dict["CoolingSetpoint"] = self.CoolingSetpoint
        data_dict["CoolingLimitType"] = self.CoolingLimitType
        data_dict["EconomizerType"] = self.EconomizerType
        data_dict["HeatingCoeffOfPerf"] = self.HeatingCoeffOfPerf
        data_dict["HeatingLimitType"] = self.HeatingLimitType
        data_dict["HeatingSchedule"] = self.HeatingSchedule.to_dict()
        data_dict["HeatingSetpoint"] = self.HeatingSetpoint
        data_dict[
            "HeatRecoveryEfficiencyLatent"] = self.HeatRecoveryEfficiencyLatent
        data_dict[
            "HeatRecoveryEfficiencySensible"] = \
            self.HeatRecoveryEfficiencySensible
        data_dict["HeatRecoveryType"] = self.HeatRecoveryType
        data_dict["IsCoolingOn"] = self.IsCoolingOn
        data_dict["IsHeatingOn"] = self.IsHeatingOn
        data_dict["IsMechVentOn"] = self.IsMechVentOn
        data_dict["MaxCoolFlow"] = self.MaxCoolFlow
        data_dict["MaxCoolingCapacity"] = self.MaxCoolingCapacity
        data_dict["MaxHeatFlow"] = self.MaxHeatFlow
        data_dict["MaxHeatingCapacity"] = self.MaxHeatingCapacity
        data_dict["MechVentSchedule"] = self.MechVentSchedule.to_dict()
        data_dict["MinFreshAirPerArea"] = self.MinFreshAirPerArea
        data_dict["MinFreshAirPerPerson"] = self.MinFreshAirPerPerson
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
        name = zone.Name + "_ZoneConditioning"

        z_cond = cls(Name=name, zone=zone)

        return z_cond

    def combine(self, other):
        """Combine two ZoneConditioning objects together.

        Args:
            other (ZoneConditioning):

        Returns:

        """
        # Check if other is the same type as self
        if not isinstance(other, self.__class__):
            msg = 'Cannot combine %s with %s' % (self.__class__.__name__,
                                                 other.__class__.__name__)
            raise NotImplementedError(msg)

        # Check if other is not the same as self
        if self == other:
            return self

        # the new object's name
        name = " + ".join([self.Name, other.Name])

        weights = [self._belongs_to_zone.volume,
                   other._belongs_to_zone.volume]
        a = self._float_mean(other, 'CoolingCoeffOfPerf', weights)
        b = self._str_mean(other, 'CoolingLimitType')
        c = self._float_mean(other, 'CoolingSetpoint', weights)
        d = self._str_mean(other, 'EconomizerType')
        e = self._float_mean(other, 'HeatRecoveryEfficiencyLatent', weights)
        f = self._float_mean(other, 'HeatRecoveryEfficiencySensible',
                             weights)
        g = self._str_mean(other, 'HeatRecoveryType')
        h = self._float_mean(other, 'HeatingCoeffOfPerf', weights)
        i = self._str_mean(other, 'HeatingLimitType')
        j = self._float_mean(other, 'HeatingSetpoint', weights)
        k = any((self.IsCoolingOn, other.IsCoolingOn))
        l = any((self.IsHeatingOn, other.IsHeatingOn))
        m = any((self.IsMechVentOn, other.IsMechVentOn))
        n = self._float_mean(other, 'MaxCoolFlow', weights)
        o = self._float_mean(other, 'MaxCoolingCapacity', weights)
        p = self._float_mean(other, 'MaxHeatFlow', weights)
        q = self._float_mean(other, 'MaxHeatingCapacity', weights)
        r = self._float_mean(other, 'MinFreshAirPerArea', weights)
        s = self._float_mean(other, 'MinFreshAirPerPerson', weights)

        attr = dict(CoolingCoeffOfPerf=a, CoolingLimitType=b, CoolingSetpoint=c,
                    EconomizerType=d, HeatRecoveryEfficiencyLatent=e,
                    HeatRecoveryEfficiencySensible=f, HeatRecoveryType=g,
                    HeatingCoeffOfPerf=h, HeatingLimitType=i, HeatingSetpoint=j,
                    IsCoolingOn=k, IsHeatingOn=l, IsMechVentOn=m, MaxCoolFlow=n,
                    MaxCoolingCapacity=o, MaxHeatFlow=p, MaxHeatingCapacity=q,
                    MinFreshAirPerArea=r, MinFreshAirPerPerson=s)

        # create a new object with the previous attributes
        new_obj = self.__class__(Name=name, **attr)
        return new_obj