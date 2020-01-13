################################################################################
# Module: archetypal.template
# Description:
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import collections
import math

import numpy as np
from archetypal import float_round, ReportData, log, timeit, settings
from archetypal.template import UmiBase, Unique, UmiSchedule, UniqueName


class ZoneConditioning(UmiBase, metaclass=Unique):
    """HVAC settings for the zone

    .. image:: ../images/template/zoninfo-conditioning.png
    """

    def __init__(
        self,
        CoolingCoeffOfPerf=1,
        CoolingLimitType="NoLimit",
        CoolingSetpoint=26,
        CoolingSchedule=None,
        EconomizerType="NoEconomizer",
        HeatRecoveryEfficiencyLatent=0.65,
        HeatRecoveryEfficiencySensible=0.7,
        HeatRecoveryType="None",
        HeatingCoeffOfPerf=1,
        HeatingLimitType="NoLimit",
        HeatingSetpoint=20,
        HeatingSchedule=None,
        IsCoolingOn=True,
        IsHeatingOn=True,
        IsMechVentOn=True,
        MaxCoolFlow=100,
        MaxCoolingCapacity=100,
        MaxHeatFlow=100,
        MaxHeatingCapacity=100,
        MinFreshAirPerArea=0,
        MinFreshAirPerPerson=0.00944,
        MechVentSchedule=None,
        **kwargs,
    ):
        """Initialize a new :class:`ZoneConditioning` object.

        Args:
            CoolingCoeffOfPerf (float): Performance factor of the cooling system.
                This value is used to calculate the total cooling energy use by
                dividing the cooling load by the COP. The COP of the zone shared with all zones
                and refers to the COP of the entire building.
            CoolingLimitType (str): The input must be either LimitFlowRate,
                LimitCapacity, LimitFlowRateAndCapacity or NoLimit.
            CoolingSetpoint (float): The temperature above which the zone heating is
                turned on. Here, we take the mean value over the year.
            CoolingSchedule (UmiSchedule): The availability schedule for space
                cooling in this zone. If the value is 0, cooling is not available,
                and cooling is not supplied to the zone.
            EconomizerType (str): Specifies if there is an outdoor air
                economizer. The choices are: NoEconomizer, DifferentialDryBulb,
                or DifferentialEnthalpy. For the moment, the EconomizerType is
                applied for the entire building (every zone with the same
                EconomizerType). Moreover, since UMI does not support all Economizer
                Types, some assumptions are made:

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
                  default value for the efficiency (=0.65).
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
            HeatingSchedule (UmiSchedule): The availability schedule for space
                heating in this zone. If the value is 0, heating is not available,
                and heating is not supplied to the zone.
            IsCoolingOn (bool): Whether or not cooling is available.
            IsHeatingOn (bool): Whether or not heating is available.
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
            MechVentSchedule (UmiSchedule): The availability schedule of the
                mechanical ventilation. If the value is 0, the mechanical ventilation is
                not available and air flow is not requested.
            **kwargs: Other arguments passed to the base class
                :class:`archetypal.template.UmiBase`
        """
        super(ZoneConditioning, self).__init__(**kwargs)
        self.MechVentSchedule = MechVentSchedule
        self.HeatingSchedule = HeatingSchedule
        self.CoolingSchedule = CoolingSchedule
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

        self._belongs_to_zone = kwargs.get("zone", None)

    def __add__(self, other):
        return self.combine(other)

    def __hash__(self):
        return hash((self.__class__.__name__, self.Name, self.DataSource))

    def __eq__(self, other):
        if not isinstance(other, ZoneConditioning):
            return False
        else:
            return all(
                [
                    self.CoolingCoeffOfPerf == other.CoolingCoeffOfPerf,
                    self.CoolingLimitType == other.CoolingLimitType,
                    self.CoolingSetpoint == other.CoolingSetpoint,
                    self.CoolingSchedule == other.CoolingSchedule,
                    self.EconomizerType == other.EconomizerType,
                    self.HeatRecoveryEfficiencyLatent
                    == other.HeatRecoveryEfficiencyLatent,
                    self.HeatRecoveryEfficiencySensible
                    == other.HeatRecoveryEfficiencySensible,
                    self.HeatRecoveryType == other.HeatRecoveryType,
                    self.HeatingCoeffOfPerf == other.HeatingCoeffOfPerf,
                    self.HeatingLimitType == other.HeatingLimitType,
                    self.HeatingSetpoint == other.HeatingSetpoint,
                    self.HeatingSchedule == other.HeatingSchedule,
                    self.IsCoolingOn == other.IsCoolingOn,
                    self.IsHeatingOn == other.IsHeatingOn,
                    self.IsMechVentOn == other.IsMechVentOn,
                    self.MaxCoolFlow == other.MaxCoolFlow,
                    self.MaxCoolingCapacity == other.MaxCoolingCapacity,
                    self.MaxHeatFlow == other.MaxHeatFlow,
                    self.MaxHeatingCapacity == other.MaxHeatingCapacity,
                    self.MinFreshAirPerArea == other.MinFreshAirPerArea,
                    self.MinFreshAirPerPerson == other.MinFreshAirPerPerson,
                    self.MechVentSchedule == other.MechVentSchedule,
                ]
            )

    @classmethod
    def from_json(cls, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        zc = cls(*args, **kwargs)

        cool_schd = kwargs.get("CoolingSchedule", None)
        zc.CoolingSchedule = zc.get_ref(cool_schd)
        heat_schd = kwargs.get("HeatingSchedule", None)
        zc.HeatingSchedule = zc.get_ref(heat_schd)
        mech_schd = kwargs.get("MechVentSchedule", None)
        zc.MechVentSchedule = zc.get_ref(mech_schd)
        return zc

    def to_json(self):
        """Convert class properties to dict"""
        data_dict = collections.OrderedDict()

        data_dict["$id"] = str(self.id)
        data_dict["CoolingSchedule"] = self.CoolingSchedule.to_dict()
        data_dict["CoolingCoeffOfPerf"] = self.CoolingCoeffOfPerf
        data_dict["CoolingSetpoint"] = (
            self.CoolingSetpoint if not math.isnan(self.CoolingSetpoint) else 26
        )
        data_dict["CoolingLimitType"] = self.CoolingLimitType
        data_dict["EconomizerType"] = self.EconomizerType
        data_dict["HeatingCoeffOfPerf"] = self.HeatingCoeffOfPerf
        data_dict["HeatingLimitType"] = self.HeatingLimitType
        data_dict["HeatingSchedule"] = self.HeatingSchedule.to_dict()
        data_dict["HeatingSetpoint"] = (
            self.HeatingSetpoint if not math.isnan(self.HeatingSetpoint) else 20
        )
        data_dict["HeatRecoveryEfficiencyLatent"] = self.HeatRecoveryEfficiencyLatent
        data_dict[
            "HeatRecoveryEfficiencySensible"
        ] = self.HeatRecoveryEfficiencySensible
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
        data_dict["Name"] = UniqueName(self.Name)

        return data_dict

    @classmethod
    @timeit
    def from_zone(cls, zone):
        """
        Args:
            zone (archetypal.template.zone.Zone): zone to gets information from
        """
        # First create placeholder object.
        name = zone.Name + "_ZoneConditioning"
        z_cond = cls(
            Name=name,
            zone=zone,
            idf=zone.idf,
            Category=zone.idf.building_name(use_idfname=True),
        )

        z_cond._set_thermostat_setpoints(zone)

        z_cond._set_zone_cops(zone)

        z_cond._set_heat_recovery(zone)

        z_cond._set_mechanical_ventilation(zone)

        z_cond._set_economizer(zone)

        return z_cond

    def _set_economizer(self, zone):
        """Set economizer parameters

        Todo:
            - Here EconomizerType is for the entire building, try to do it for
              each zone.
            - Fix typo in DifferentialEnthalpy (extra h) when issue is resolved
              at Basilisk project:
              https://github.com/MITSustainableDesignLab/basilisk/issues/32

        Args:
            zone (Zone): The zone object.
        """
        # Economizer
        controllers_in_idf = zone.idf.idfobjects["Controller:OutdoorAir".upper()]
        self.EconomizerType = "NoEconomizer"  # default value

        for object in controllers_in_idf:
            if object.Economizer_Control_Type == "NoEconomizer":
                self.EconomizerType = "NoEconomizer"
            elif object.Economizer_Control_Type == "DifferentialEnthalphy":
                self.EconomizerType = "DifferentialEnthalphy"
            elif object.Economizer_Control_Type == "DifferentialDryBulb":
                self.EconomizerType = "DifferentialDryBulb"
            elif object.Economizer_Control_Type == "FixedDryBulb":
                self.EconomizerType = "DifferentialDryBulb"
            elif object.Economizer_Control_Type == "FixedEnthalpy":
                self.EconomizerType = "DifferentialEnthalphy"
            elif object.Economizer_Control_Type == "ElectronicEnthalpy":
                self.EconomizerType = "DifferentialEnthalphy"
            elif object.Economizer_Control_Type == "FixedDewPointAndDryBulb":
                self.EconomizerType = "DifferentialDryBulb"
            elif object.Economizer_Control_Type == "DifferentialDryBulbAndEnthalpy":
                self.EconomizerType = "DifferentialEnthalphy"

    def _set_mechanical_ventilation(self, zone):
        """Iterate on 'Controller:MechanicalVentilation' objects to find the
        'DesignSpecifactionOutdoorAirName' for the zone.

        Todo:
            - Get mechanical sizing by zone.

        Args:
            zone (Zone): The zone object.
        """
        if not zone.idf.idfobjects["Controller:MechanicalVentilation".upper()]:
            IsMechVentOn = False
            MinFreshAirPerArea = 0  # use defaults
            MinFreshAirPerPerson = 0
            MechVentSchedule = UmiSchedule.constant_schedule(idf=zone.idf)
        else:
            design_spe_outdoor_air_name = ""
            for object in zone.idf.idfobjects[
                "Controller:MechanicalVentilation".upper()
            ]:
                if zone.Name in object.fieldvalues:
                    indice_zone = [
                        k for k, s in enumerate(object.fieldvalues) if s == zone.Name
                    ][0]
                    design_spe_outdoor_air_name = object.fieldvalues[indice_zone + 1]

                    if object.Availability_Schedule_Name != "":
                        MechVentSchedule = UmiSchedule(
                            Name=object.Availability_Schedule_Name, idf=zone.idf
                        )
                    else:
                        MechVentSchedule = UmiSchedule.constant_schedule(idf=zone.idf)
                    break
            # If 'DesignSpecifactionOutdoorAirName', MechVent is ON, and gets
            # the minimum fresh air (per person and area)
            if design_spe_outdoor_air_name != "":
                IsMechVentOn = True
                design_spe_outdoor_air = zone.idf.getobject(
                    "DesignSpecification:OutdoorAir".upper(),
                    design_spe_outdoor_air_name,
                )
                MinFreshAirPerPerson = (
                    design_spe_outdoor_air.Outdoor_Air_Flow_per_Person
                )
                # If MinFreshAirPerPerson NOT a number, MinFreshAirPerPerson=0
                try:
                    MinFreshAirPerPerson = float(MinFreshAirPerPerson)
                except:
                    MinFreshAirPerPerson = 0
                MinFreshAirPerArea = (
                    design_spe_outdoor_air.Outdoor_Air_Flow_per_Zone_Floor_Area
                )
                # If MinFreshAirPerArea NOT a number, MinFreshAirPerArea=0
                try:
                    MinFreshAirPerArea = float(MinFreshAirPerArea)
                except:
                    MinFreshAirPerArea = 0
            else:
                IsMechVentOn = False
                MinFreshAirPerPerson = 0
                MinFreshAirPerArea = 0
                MechVentSchedule = UmiSchedule.constant_schedule(idf=zone.idf)

        self.IsMechVentOn = IsMechVentOn
        self.MinFreshAirPerArea = MinFreshAirPerArea
        self.MinFreshAirPerPerson = MinFreshAirPerPerson
        self.MechVentSchedule = MechVentSchedule

    def _set_zone_cops(self, zone):
        """
        Todo:
            - Make this method zone-independent.

        Args:
            zone (Zone):
        """
        # COPs (heating and cooling)

        # Heating
        heating_meters = (
            "Heating:Electricity",
            "Heating:Gas",
            "Heating:DistrictHeating",
        )
        heating_cop = self._get_cop(
            zone,
            energy_in_list=heating_meters,
            energy_out_variable_name=(
                "Air System Total Heating Energy",
                "Zone Ideal Loads Zone Total Heating Energy",
            ),
        )
        # Cooling
        cooling_meters = (
            "Cooling:Electricity",
            "Cooling:Gas",
            "Cooling:DistrictCooling",
        )
        cooling_cop = self._get_cop(
            zone,
            energy_in_list=cooling_meters,
            energy_out_variable_name=(
                "Air System Total Cooling Energy",
                "Zone Ideal Loads Zone Total Cooling Energy",
            ),
        )

        # Capacity limits (heating and cooling)
        zone_size = zone.sql["ZoneSizes"][
            zone.sql["ZoneSizes"]["ZoneName"] == zone.Name.upper()
        ]
        # Heating
        HeatingLimitType, heating_cap, heating_flow = self._get_design_limits(
            zone, zone_size, load_name="Heating"
        )
        # Cooling
        CoolingLimitType, cooling_cap, cooling_flow = self._get_design_limits(
            zone, zone_size, load_name="Cooling"
        )

        self.HeatingLimitType = HeatingLimitType
        self.MaxHeatingCapacity = heating_cap
        self.MaxHeatFlow = heating_flow
        self.CoolingLimitType = CoolingLimitType
        self.MaxCoolingCapacity = cooling_cap
        self.MaxCoolFlow = cooling_flow

        self.CoolingCoeffOfPerf = cooling_cop
        self.HeatingCoeffOfPerf = heating_cop

        # If cop calc == infinity, COP = 1 because we need a value in json file.
        if heating_cop == float("infinity"):
            self.HeatingCoeffOfPerf = 1
        if cooling_cop == float("infinity"):
            self.CoolingCoeffOfPerf = 1

    def _set_thermostat_setpoints(self, zone):
        """Sets the thermostat settings and schedules for this zone.

        Thermostat Setpoints:
            - CoolingSetpoint (float):
            - HeatingSetpoint (float):
            - HeatingSchedule (UmiSchedule):
            - CoolingSchedule (UmiSchedule):

        Args:
            zone (Zone): The zone object.
        """
        # Set Thermostat set points
        # Heating and Cooling set points and schedules
        self.HeatingSetpoint, self.HeatingSchedule, self.CoolingSetpoint, self.CoolingSchedule = self._get_setpoint_and_scheds(
            zone
        )

        # If HeatingSetpoint == nan, means there is no heat or cold input,
        # therefore system is off.
        if math.isnan(self.HeatingSetpoint):
            self.IsHeatingOn = False
        else:
            self.IsHeatingOn = True
        if math.isnan(self.CoolingSetpoint):
            self.IsCoolingOn = False
        else:
            self.IsCoolingOn = True

    def _set_heat_recovery(self, zone):
        """Sets the heat recovery parameters for this zone.

        Heat Recovery Parameters:
            - HeatRecoveryEfficiencyLatent (float): The latent heat recovery
              effectiveness.
            - HeatRecoveryEfficiencySensible (float): The sensible heat recovery
              effectiveness.
            - HeatRecoveryType (str): 'None', 'Sensible' or 'Enthalpy'.
            - comment (str): A comment to append to the class comment attribute.

        Args:
            zone (Zone): The Zone object.
        """
        from itertools import chain

        # Todo: Implement loop that detects HVAC linked to Zone; than parse heat
        #  recovery. Needs to happen when a zone has a ZoneHVAC:IdealLoadsAirSystem
        # connections = zone._epbunch.getreferingobjs(
        #     iddgroups=["Zone HVAC Equipment Connections"], fields=["Zone_Name"]
        # )
        # nodes = [
        #     con.get_referenced_object("Zone_Air_Inlet_Node_or_NodeList_Name")
        #     for con in connections
        # ]

        # get possible heat recovery objects from idd
        heat_recovery_objects = zone.idf.getiddgroupdict()["Heat Recovery"]

        # get possible heat recovery objects from this idf
        heat_recovery_in_idf = list(
            chain.from_iterable(
                zone.idf.idfobjects[key.upper()] for key in heat_recovery_objects
            )
        )

        # Set defaults
        HeatRecoveryEfficiencyLatent = 0.7
        HeatRecoveryEfficiencySensible = 0.65
        HeatRecoveryType = "None"
        comment = ""

        # iterate over those objects. If the list is empty, it will simply pass.
        for object in heat_recovery_in_idf:

            if object.key.upper() == "HeatExchanger:AirToAir:FlatPlate".upper():
                # Do HeatExchanger:AirToAir:FlatPlate

                nsaot = object.Nominal_Supply_Air_Outlet_Temperature
                nsait = object.Nominal_Supply_Air_Inlet_Temperature
                n2ait = object.Nominal_Secondary_Air_Inlet_Temperature
                HeatRecoveryEfficiencySensible = (nsaot - nsait) / (n2ait - nsait)
                # Hypotheses: HeatRecoveryEfficiencySensible - 0.05
                HeatRecoveryEfficiencyLatent = HeatRecoveryEfficiencySensible - 0.05
                HeatRecoveryType = "Enthalpy"
                comment = (
                    "HeatRecoveryEfficiencySensible was calculated "
                    "using this formula: (Supply Air Outlet T°C -; "
                    "Supply Air Inlet T°C)/(Secondary Air Inlet T°C - "
                    "Supply Air Inlet T°C)"
                )

            elif (
                object.key.upper() == "HeatExchanger:AirToAir:SensibleAndLatent".upper()
            ):
                # Do HeatExchanger:AirToAir:SensibleAndLatent

                HeatRecoveryEfficiencyLatent, HeatRecoveryEfficiencySensible = self._get_recoverty_effectiveness(
                    object, zone
                )
                HeatRecoveryType = "Enthalpy"

                comment = (
                    "HeatRecoveryEfficiencies were calculated using "
                    "simulation hourly values and averaged. Only values"
                    " > 0 were used in the average calculation."
                )

            elif object.key.upper() == "HeatExchanger:Desiccant:BalancedFlow".upper():
                # Do HeatExchanger:Dessicant:BalancedFlow
                # Use default values
                HeatRecoveryEfficiencyLatent = 0.7
                HeatRecoveryEfficiencySensible = 0.65
                HeatRecoveryType = "Enthalpy"

            elif (
                object.key.upper() == "HeatExchanger:Desiccant:BalancedFlow"
                ":PerformanceDataType1".upper()
            ):
                # This is not an actual HeatExchanger, pass
                pass
            else:
                msg = 'Heat exchanger object "{}" is not ' "implemented".format(object)
                raise NotImplementedError(msg)

        self.HeatRecoveryEfficiencyLatent = HeatRecoveryEfficiencyLatent
        self.HeatRecoveryEfficiencySensible = HeatRecoveryEfficiencySensible
        self.HeatRecoveryType = HeatRecoveryType
        self.Comments += comment

    @staticmethod
    def _get_recoverty_effectiveness(object, zone):
        """
        Args:
            object:
            zone:
        """
        rd = ReportData.from_sql_dict(zone.sql)
        effectiveness = (
            rd.filter_report_data(
                name=(
                    "Heat Exchanger Sensible Effectiveness",
                    "Heat Exchanger Latent Effectiveness",
                )
            )
            .loc[lambda x: x.Value > 0]
            .groupby(["KeyValue", "Name"])
            .Value.mean()
            .unstack(level=-1)
        )
        HeatRecoveryEfficiencySensible = effectiveness.loc[
            object.Name.upper(), "Heat Exchanger Sensible " "Effectiveness"
        ]
        HeatRecoveryEfficiencyLatent = effectiveness.loc[
            object.Name.upper(), "Heat Exchanger Latent Effectiveness"
        ]
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
                zone_size[zone_size["LoadType"] == load_name]["UserDesLoad"].values[0]
                / zone.area,
                3,
            )
            flow = (
                zone_size[zone_size["LoadType"] == load_name]["UserDesFlow"].values[0]
                / zone.area
            )
            LimitType = "LimitFlowRateAndCapacity"
        except:
            cap = 100
            flow = 100
            LimitType = "NoLimit"
        return LimitType, cap, flow

    @classmethod
    def _get_cop(cls, zone, energy_in_list, energy_out_variable_name):
        """Calculates COP for heating or cooling systems

        Args:
            zone (archetypal.template.zone.Zone): zone to gets information from
            energy_in_list (str or tuple): list of the energy sources for a
                system (e.g. [Heating:Electricity, Heating:Gas] for heating
                system)
            energy_out_variable_name (str or tuple): Name of the output in the
                sql for the energy given to the zone from the system (e.g. 'Air
                System Total Heating Energy')
        """
        from archetypal import ReportData

        rd = ReportData.from_sql_dict(zone.sql)
        energy_out = rd.filter_report_data(name=tuple(energy_out_variable_name))
        energy_in = rd.filter_report_data(name=tuple(energy_in_list))

        # zone_to_hvac = {zone.Zone_Name: [
        #     zone.get_referenced_object(
        #         'Zone_Conditioning_Equipment_List_Name
        #         ').get_referenced_object(
        #         fieldname) for fieldname in zone.get_referenced_object(
        #         'Zone_Conditioning_Equipment_List_Name').fieldnames if
        #     zone.get_referenced_object(
        #         'Zone_Conditioning_Equipment_List_Name
        #         ').get_referenced_object(
        #         fieldname) is not None
        # ]
        #     for zone in zone.idf.idfobjects[
        #         'ZoneHVAC:EquipmentConnections'.upper()]
        # }

        outs = energy_out.groupby("KeyValue").Value.sum()
        ins = energy_in.Value.sum()

        cop = float_round(outs.sum() / ins, 3)

        return cop

    def _get_setpoint_and_scheds(self, zone):
        """Gets temperature set points from sql EnergyPlus output and associated
        schedules.

        Args:
            zone (archetypal.template.zone.Zone): zone to gets information from
        """
        # Load the ReportData and filter *variable_output_name* and group by
        # zone name (*KeyValue*). Return annual average.
        variable_output_name = "Zone Thermostat Heating Setpoint Temperature"
        h_array = (
            ReportData.from_sql_dict(zone.sql)
            .filter_report_data(name=variable_output_name, keyvalue=zone.Name.upper())
            .loc[:, ["TimeIndex", "Value"]]
            .set_index("TimeIndex")
            .Value.values
        )

        heating_sched = UmiSchedule.from_values(
            Name=zone.Name + "_Heating_Schedule",
            values=(h_array > 0).astype(int),
            schTypeLimitsName="Fraction",
            idf=zone.idf,
        )

        variable_output_name = "Zone Thermostat Cooling Setpoint Temperature"
        c_array = (
            ReportData.from_sql_dict(zone.sql)
            .filter_report_data(name=variable_output_name, keyvalue=zone.Name.upper())
            .loc[:, ["TimeIndex", "Value"]]
            .set_index("TimeIndex")
            .Value.values
        )
        cooling_sched = UmiSchedule.from_values(
            Name=zone.Name + "_Cooling_Schedule",
            values=(c_array > 0).astype(int),
            schTypeLimitsName="Fraction",
            idf=zone.idf,
        )
        if np.all(c_array == 0):
            c_mean = np.NaN
        else:
            c_mean = c_array.mean()
        if np.all(h_array == 0):
            h_mean = np.NaN
        else:
            h_mean = h_array.mean()
        return h_mean, heating_sched, c_mean, cooling_sched

    def combine(self, other, weights=None):
        """Combine two ZoneConditioning objects together.

        Args:
            other (ZoneConditioning): The other ZoneConditioning object to
                combine with.
            weights (list-like, optional): A list-like object of len 2. If None,
                the volume of the zones for which self and other belongs is
                used.
        Returns:
            (ZoneConditioning): the combined ZoneConditioning object.
        """
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

        a = self._float_mean(other, "CoolingCoeffOfPerf", weights)
        b = self._str_mean(other, "CoolingLimitType")
        c = self._float_mean(other, "CoolingSetpoint", weights)
        d = self._str_mean(other, "EconomizerType")
        e = self._float_mean(other, "HeatRecoveryEfficiencyLatent", weights)
        f = self._float_mean(other, "HeatRecoveryEfficiencySensible", weights)
        g = self._str_mean(other, "HeatRecoveryType")
        h = self._float_mean(other, "HeatingCoeffOfPerf", weights)
        i = self._str_mean(other, "HeatingLimitType")
        j = self._float_mean(other, "HeatingSetpoint", weights)
        k = any((self.IsCoolingOn, other.IsCoolingOn))
        l = any((self.IsHeatingOn, other.IsHeatingOn))
        m = any((self.IsMechVentOn, other.IsMechVentOn))
        n = self._float_mean(other, "MaxCoolFlow", weights)
        o = self._float_mean(other, "MaxCoolingCapacity", weights)
        p = self._float_mean(other, "MaxHeatFlow", weights)
        q = self._float_mean(other, "MaxHeatingCapacity", weights)
        r = self._float_mean(other, "MinFreshAirPerArea", weights)
        s = self._float_mean(other, "MinFreshAirPerPerson", weights)
        t = self.HeatingSchedule.combine(other.HeatingSchedule, weights)
        u = self.CoolingSchedule.combine(other.CoolingSchedule, weights)
        v = self.MechVentSchedule.combine(other.MechVentSchedule, weights)

        # create a new object with the previous attributes
        new_obj = self.__class__(
            **meta,
            CoolingCoeffOfPerf=a,
            CoolingLimitType=b,
            CoolingSetpoint=c,
            EconomizerType=d,
            HeatRecoveryEfficiencyLatent=e,
            HeatRecoveryEfficiencySensible=f,
            HeatRecoveryType=g,
            HeatingCoeffOfPerf=h,
            HeatingLimitType=i,
            HeatingSetpoint=j,
            IsCoolingOn=k,
            IsHeatingOn=l,
            IsMechVentOn=m,
            MaxCoolFlow=n,
            MaxCoolingCapacity=o,
            MaxHeatFlow=p,
            MaxHeatingCapacity=q,
            MinFreshAirPerArea=r,
            MinFreshAirPerPerson=s,
            HeatingSchedule=t,
            CoolingSchedule=u,
            MechVentSchedule=v,
        )
        new_obj._predecessors.extend(self.predecessors + other.predecessors)
        return new_obj
