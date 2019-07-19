################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections

from archetypal import float_round, ReportData
from archetypal.template import UmiBase, Unique


class ZoneConditioning(UmiBase, metaclass=Unique):
    """HVAC settings for the zone

    .. image:: ../images/template/zoninfo-conditioning.png
    """

    def __init__(self, CoolingCoeffOfPerf=None, CoolingLimitType='NoLimit',
                 CoolingSetpoint=26, EconomizerType='NoEconomizer',
                 HeatRecoveryEfficiencyLatent=0.65,
                 HeatRecoveryEfficiencySensible=0.7, HeatRecoveryType='None',
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
                dividing the cooling load by the COP. The COP is of each zone is
                equal, and refer to the COP of the entire building.
            CoolingLimitType (str): The input must be either LimitFlowRate,
                LimitCapacity, LimitFlowRateAndCapacity or NoLimit.
            CoolingSetpoint (float): The temperature above which zone heating is
                turned on. Here, we take the mean value over the year.
            EconomizerType (str): Specifies if there is an outdoor air
                economizer. The choices are: NoEconomizer, DifferentialDryBulb,
                or DifferentialEnthalpy. For the moment, the EconomizerType is
                applied for the entire building (every zone with the same
                EconomizerType). Moreover, some hypotheses are done knowing
                there is more EconomizerType existing in EnergyPlus than in UMI:

                - If 'NoEconomizer' in EnergyPlus, EconomizerType='NoEconomizer'
                - If 'DifferentialEnthalpy' in EnergyPlus,EconomizerType =
                  'DifferentialEnthalpy'
                - If 'DifferentialDryBulb' in EnergyPlus, EconomizerType =
                  'DifferentialDryBulb'
                - If 'FixedDryBulb' in EnergyPlus, EconomizerType =
                  'DifferentialDryBulb'
                - If 'FixedEnthalpy' in EnergyPlus, EconomizerType =
                  'DifferentialEnthalpy'
                - If 'ElectronicEnthalpy' in EnergyPlus, EconomizerType =
                  'DifferentialEnthalpy'
                - If 'FixedDewPointAndDryBulb' in EnergyPlus, EconomizerType =
                  'DifferentialDryBulb'
                - If 'DifferentialDryBulbAndEnthalpy' in EnergyPlus,
                  EconomizerType = 'DifferentialEnthalpy'
            HeatRecoveryEfficiencyLatent (float): The latent heat recovery
                effectiveness, where effectiveness is defined as the change in
                supply humidity ratio divided by the difference in entering
                supply and relief air humidity ratios. The default is 0.65.

                - If the HeatExchanger is an AirToAir FlatPlate,
                  HeatRecoveryEfficiencyLatent = HeatRecoveryEfficiencySensible
                  - 0.05
                - If the HeatExchanger is an AirToAir SensibleAndLatent, we
                  suppose that HeatRecoveryEfficiencyLatent = Latent
                  Effectiveness at 100% Heating Air Flow
                - If the HeatExchanger is a Desiccant BalancedFlow, we use the
                  default value for the efficiency (=0.65)
            HeatRecoveryEfficiencySensible (float): The sensible heat recovery
                effectiveness, where effectiveness is defined as the change in
                supply temperature divided by the difference in entering supply
                and relief air temperatures. The default is 0.70.

                - If the HeatExchanger is an AirToAir FlatPlate,
                  HeatRecoveryEfficiencySensible = (Supply Air Outlet T°C -
                  Supply Air Inlet T°C)/(Secondary Air Inlet T°C - Supply Air
                  Inlet T°C)
                - If the HeatExchanger is an AirToAir SensibleAndLatent, we
                  suppose that HeatRecoveryEfficiencySensible = Sensible
                  Effectiveness at 100% Heating Air Flow
                - If the HeatExchanger is a Desiccant BalancedFlow, we use the
                  default value for the efficiency (=0.70)
            HeatRecoveryType (str): Select from *None*, *Sensible*, or
                *Enthalpy*. None means that there is no heat recovery. Sensible
                means that there is sensible heat recovery whenever the zone
                exhaust air temperature is more favorable than the outdoor air
                temperature. Enthalpy means that there is latent and sensible
                heat recovery whenever the zone exhaust air enthalpy is more
                favorable than the outdoor air enthalpy. The default is None
            HeatingCoeffOfPerf (float): Efficiency of heating system. The COP is
                of each zone is equal, and refer to the COP of the entire
                building.
            HeatingLimitType (str): The input must be either LimitFlowRate,
                LimitCapacity, LimitFlowRateAndCapacity or NoLimit.
            HeatingSetpoint (float): The temperature below which zone heating is
                turned on. Here, we take the mean value over the year.
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
            zone (archetypal.template.zone.Zone): zone to gets information from
        """
        name = zone.Name + "_ZoneConditioning"

        # Thermostat setpoints
        # Heating setpoint
        heating_setpoint = cls._get_setpoint(zone,
                                             'Zone Thermostat Heating '
                                             'Setpoint Temperature')
        # Cooling setpoint
        cooling_setpoint = cls._get_setpoint(zone,
                                             'Zone Thermostat Cooling '
                                             'Setpoint Temperature')

        # If setpoint equal to zero, conditionning is off
        if heating_setpoint == 0:
            IsHeatingOn = False
        else:
            IsHeatingOn = True
        if cooling_setpoint == 0:
            IsCoolingOn = False
        else:
            IsCoolingOn = True

        # COPs (heating and cooling)
        # Heating
        heating_in_list = ['Heating:Electricity', 'Heating:Gas',
                           'Heating:DistrictHeating']
        heating_cop = cls._get_cop(zone, energy_in_list=heating_in_list,
                                   energy_out_variable_name='Air System Total '
                                                            'Heating Energy')
        # Cooling
        cooling_in_list = ['Cooling:Electricity', 'Cooling:Gas',
                           'Cooling:DistrictCooling']
        cooling_cop = cls._get_cop(zone, energy_in_list=cooling_in_list,
                                   energy_out_variable_name='Air System Total '
                                                            'Cooling Energy')

        # Capacity limits (heating and cooling)
        zone_size = zone.sql['ZoneSizes'][
            zone.sql['ZoneSizes']['ZoneName'] == zone.Name.upper()]
        # Heating
        HeatingLimitType, heating_cap, heating_flow = cls._get_design_limits(
            zone, zone_size, load_name='Heating')
        # Cooling
        CoolingLimitType, cooling_cap, cooling_flow = cls._get_design_limits(
            zone, zone_size, load_name='Cooling')

        # Heat recovery system
        HeatRecoveryEfficiencyLatent, HeatRecoveryEfficiencySensible, \
        HeatRecoveryType, comment = cls._get_heat_recovery(zone)

        # Mechanical Ventilation
        # Iterate on 'Controller:MechanicalVentilation' objects to find the
        # 'DesignSpecifactionOutdoorAirName' for the zone
        if not zone.idf.idfobjects['Controller:MechanicalVentilation'.upper()]:
            IsMechVentOn = False
            MinFreshAirPerPerson = 0
            MinFreshAirPerArea = 0
        else:
            design_spe_outdoor_air_name = ''
            for object in zone.idf.idfobjects[
                'Controller:MechanicalVentilation'.upper()]:
                if zone.Name in object.fieldvalues:
                    indice_zone = \
                        [k for k, s in enumerate(object.fieldvalues) if
                         s == zone.Name][
                            0]
                    design_spe_outdoor_air_name = object.fieldvalues[
                        indice_zone + 1]
                    break
            # If 'DesignSpecifactionOutdoorAirName', MechVent is ON, and gets
            # the
            # minimum fresh air (per person and area)
            if design_spe_outdoor_air_name != '':
                IsMechVentOn = True
                design_spe_outdoor_air = zone.idf.getobject(
                    'DesignSpecification:OutdoorAir'.upper(),
                    design_spe_outdoor_air_name)
                MinFreshAirPerPerson = \
                    design_spe_outdoor_air.Outdoor_Air_Flow_per_Person
                # If MinFreshAirPerPerson NOT a number, MinFreshAirPerPerson=0
                try:
                    MinFreshAirPerPerson = float(MinFreshAirPerPerson)
                except:
                    MinFreshAirPerPerson = 0
                MinFreshAirPerArea = \
                    design_spe_outdoor_air.Outdoor_Air_Flow_per_Zone_Floor_Area
                # If MinFreshAirPerArea NOT a number, MinFreshAirPerArea=0
                try:
                    MinFreshAirPerArea = float(MinFreshAirPerArea)
                except:
                    MinFreshAirPerArea = 0
            else:
                IsMechVentOn = False
                MinFreshAirPerPerson = 0
                MinFreshAirPerArea = 0

        # Economizer
        # Todo: Here EconomizerType is for the entire building, try to do it
        #  for each zone
        EconomizerType = 'NoEconomizer'
        for object in zone.idf.idfobjects['Controller:OutdoorAir'.upper()]:
            if object.Economizer_Control_Type == 'NoEconomizer':
                continue
            elif object.Economizer_Control_Type == 'DifferentialEnthalpy':
                EconomizerType = 'DifferentialEnthalpy'
                break
            elif object.Economizer_Control_Type == 'DifferentialDryBulb':
                EconomizerType = 'DifferentialDryBulb'
                break
            elif object.Economizer_Control_Type == 'FixedDryBulb':
                EconomizerType = 'DifferentialDryBulb'
                break
            elif object.Economizer_Control_Type == 'FixedEnthalpy':
                EconomizerType = 'DifferentialEnthalpy'
                break
            elif object.Economizer_Control_Type == 'ElectronicEnthalpy':
                EconomizerType = 'DifferentialEnthalpy'
                break
            elif object.Economizer_Control_Type == 'FixedDewPointAndDryBulb':
                EconomizerType = 'DifferentialDryBulb'
                break
            elif object.Economizer_Control_Type == \
                    'DifferentialDryBulbAndEnthalpy':
                EconomizerType = 'DifferentialEnthalpy'
                break

        z_cond = cls(Name=name, zone=zone, CoolingCoeffOfPerf=cooling_cop,
                     CoolingLimitType=CoolingLimitType,
                     CoolingSetpoint=cooling_setpoint,
                     EconomizerType=EconomizerType,
                     HeatRecoveryEfficiencyLatent=HeatRecoveryEfficiencyLatent,
                     HeatRecoveryEfficiencySensible=HeatRecoveryEfficiencySensible,
                     HeatRecoveryType=HeatRecoveryType,
                     HeatingCoeffOfPerf=heating_cop,
                     HeatingLimitType=HeatingLimitType,
                     HeatingSetpoint=cooling_setpoint, IsCoolingOn=IsCoolingOn,
                     IsHeatingOn=IsHeatingOn,
                     IsMechVentOn=IsMechVentOn, MaxCoolFlow=cooling_flow,
                     MaxCoolingCapacity=cooling_cap,
                     MaxHeatFlow=heating_flow, MaxHeatingCapacity=heating_cap,
                     MinFreshAirPerArea=MinFreshAirPerArea,
                     MinFreshAirPerPerson=MinFreshAirPerPerson,
                     comment=comment)

        return z_cond

    @classmethod
    def _get_heat_recovery(cls, zone):
        """Returns the heat recovery parameters for this zone.

        Args:
            zone (Zone): The Zone object.

        Returns:
            4-tuple: heat recovery parameters:
                - HeatRecoveryEfficiencyLatent (float): The latent heat recovery
                  effectiveness.
                - HeatRecoveryEfficiencySensible (float): The sensible heat
                  recovery effectiveness.
                - HeatRecoveryType (str): 'None', 'Sensible' or 'Enthalpy'.
                - comment (str): A comment to append to the class comment
                  attribute.
        """
        from itertools import chain
        # get possible heat recovery objects from idd
        heat_recovery_objects = zone.idf.getiddgroupdict()['Heat Recovery']

        # get possible heat recovery objects from this idf
        heat_recovery_in_idf = list(chain.from_iterable(
            zone.idf.idfobjects[key.upper()] for key in heat_recovery_objects))

        # Set defaults
        HeatRecoveryEfficiencyLatent = 0.7
        HeatRecoveryEfficiencySensible = 0.65
        HeatRecoveryType = 'None'
        comment = ''

        # iterate over those objects. If the list is empty, it will simply pass.
        for object in heat_recovery_in_idf:

            if object.key.upper() == 'HeatExchanger:AirToAir:FlatPlate'.upper():
                # Do HeatExchanger:AirToAir:FlatPlate

                nsaot = object.Nominal_Supply_Air_Outlet_Temperature
                nsait = object.Nominal_Supply_Air_Inlet_Temperature
                n2ait = object.Nominal_Secondary_Air_Inlet_Temperature
                HeatRecoveryEfficiencySensible = (
                        (nsaot - nsait) / (n2ait - nsait))
                # Hypotheses: HeatRecoveryEfficiencySensible - 0.05
                HeatRecoveryEfficiencyLatent = \
                    HeatRecoveryEfficiencySensible - 0.05
                HeatRecoveryType = 'Enthalpy'
                comment = 'HeatRecoveryEfficiencySensible was calculated ' \
                          'using this formula: (Supply Air Outlet T°C -; ' \
                          'Supply Air Inlet T°C)/(Secondary Air Inlet T°C - ' \
                          'Supply Air Inlet T°C)'

            elif object.key.upper() == \
                    'HeatExchanger:AirToAir:SensibleAndLatent'.upper():
                # Do HeatExchanger:AirToAir:SensibleAndLatent

                HeatRecoveryEfficiencyLatent, \
                HeatRecoveryEfficiencySensible \
                    = cls._get_recoverty_effectiveness(object, zone)
                HeatRecoveryType = 'Enthalpy'

                comment = 'HeatRecoveryEfficiencies were calculated using ' \
                          'simulation hourly values and averaged. Only values' \
                          ' > 0 were used in the average calculation.'

            elif object.key.upper() == \
                    'HeatExchanger:Desiccant:BalancedFlow'.upper():
                # Do HeatExchanger:Dessicant:BalancedFlow
                # Use default values
                HeatRecoveryEfficiencyLatent = 0.7
                HeatRecoveryEfficiencySensible = 0.65
                HeatRecoveryType = 'Enthalpy'

            elif object.key.upper() == \
                    'HeatExchanger:Desiccant:BalancedFlow' \
                    ':PerformanceDataType1'.upper():
                # This is not an actual HeatExchanger, pass
                pass
            else:
                msg = 'Heat exchanger object "{}" is not ' \
                      'implemented'.format(object)
                raise NotImplementedError(msg)

        return HeatRecoveryEfficiencyLatent, HeatRecoveryEfficiencySensible, \
               HeatRecoveryType, comment

    @classmethod
    def _get_recoverty_effectiveness(cls, object, zone):
        """
        Args:
            object:
            zone:
        """
        rd = ReportData.from_sql(zone.sql)
        effectiveness = rd.filter_report_data(
            name=('Heat Exchanger Sensible Effectiveness',
                  'Heat Exchanger Latent Effectiveness')).loc[
            lambda x: x.Value > 0].groupby(
            ['KeyValue', 'Name']).Value.mean().unstack(level=-1)
        HeatRecoveryEfficiencySensible = effectiveness.loc[
            object.Name.upper(), 'Heat Exchanger Sensible ' \
                                 'Effectiveness']
        HeatRecoveryEfficiencyLatent = effectiveness.loc[
            object.Name.upper(), 'Heat Exchanger Latent Effectiveness']
        return HeatRecoveryEfficiencyLatent, HeatRecoveryEfficiencySensible

    @classmethod
    def _get_design_limits(cls, zone, zone_size, load_name):
        """Gets design limits for heating and cooling systems

        Args:
            zone (archetypal.template.zone.Zone): zone to gets information from
            zone_size (df): Dataframe from the sql EnergyPlus outpout, with the
                sizing of the heating and cooling systems
            load_name (str): 'Heating' or 'Cooling' depending on what system we
                want to characterize
        """
        try:
            cap = round(
                zone_size[zone_size['LoadType'] == load_name][
                    'UserDesLoad'].values[
                    0] / zone.area, 3)
            flow = \
                zone_size[zone_size['LoadType'] == load_name][
                    'UserDesFlow'].values[
                    0] / zone.area
            LimitType = 'LimitFlowRateAndCapacity'
        except:
            cap = 100
            flow = 100
            LimitType = 'NoLimit'
        return LimitType, cap, flow

    @classmethod
    def _get_cop(cls, zone, energy_in_list, energy_out_variable_name):
        """Calculates COP for heating or cooling systems

        Args:
            zone (archetypal.template.zone.Zone): zone to gets information from
            energy_in_list (list): list of the energy sources for a system (e.g.
                [Heating:Electricity, Heating:Gas] for heating system)
            energy_out_variable_name (str): Name of the output in the sql for
                the energy given to the zone from the system (e.g. 'Air System
                Total Heating Energy')
        """
        energy_out_idx = zone.sql['ReportDataDictionary'][
            zone.sql['ReportDataDictionary'][
                'Name'] == energy_out_variable_name].index
        energy_out = zone.sql['ReportData'][
            zone.sql['ReportData']['ReportDataDictionaryIndex'].isin(
                energy_out_idx)]['Value'].sum()
        energy_in_idx = zone.sql['ReportDataDictionary'][
            zone.sql['ReportDataDictionary']['Name'].isin(
                energy_in_list)].index
        energy_in = zone.sql['ReportData'][
            zone.sql['ReportData']['ReportDataDictionaryIndex'].isin(
                energy_in_idx)]['Value'].sum()
        cop = float_round(energy_out / energy_in,
                          3)
        return cop

    @classmethod
    def _get_setpoint(cls, zone, variable_output_name):
        """Gets temperature setpoints from sql EnergyPlus output

        Args:
            zone (archetypal.template.zone.Zone): zone to gets information from
            variable_output_name (str): Name of the output in the sql for the
                zone setpoint (e.g. 'Zone Thermostat Heating Setpoint
                Temperature')
        """
        setpoints_idx = zone.sql['ReportDataDictionary'][
            zone.sql['ReportDataDictionary']['Name'] == variable_output_name]
        setpoint_idx = setpoints_idx[
            setpoints_idx['KeyValue'].str.contains(zone.Name.upper())].index
        setpoint = float_round(zone.sql['ReportData'][zone.sql['ReportData'][
                                                          'ReportDataDictionaryIndex'] ==
                                                      setpoint_idx.tolist()[0]][
                                   'Value'].mean(), 3)
        return setpoint

    def combine(self, other):
        """Combine two ZoneConditioning objects together.

        Args:
            other (ZoneConditioning):
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
