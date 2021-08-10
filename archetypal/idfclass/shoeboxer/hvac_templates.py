"""HVAC Templates Module."""


class HVACTemplate:
    """Allows for the specification of simple zone thermostats and HVAC systems with
    automatically generated node names.
    """

    def create_from(self, zone, zoneDefinition):
        """Create HVAC Template from zone and from zoneDefinition.

        Args:
            zone (EpBunch):
            zoneDefinition (ZoneDefinition):
        """
        pass


class SimpleIdealLoadsSystem(HVACTemplate):
    """For a simple ideal loads system for sizing and loads oriented simulations."""

    REQUIRED = ["HVACTemplate:Thermostat", "HVACTemplate:Zone:BaseboardHeat"]
    OPTIONAL = []

    def create_from(self, zone, zoneDefinition):
        """Create SimpleIdealLoadsSystem.

        Args:
            zone (EpBunch): The zone EpBunch object.
            zoneDefinition (ZoneDefinition): The archetypal template ZoneDefinition
                object.
        """
        idf = zone.theidf
        stat = idf.newidfobject(
            "HVACTEMPLATE:THERMOSTAT",
            Name=f"Zone {zone.Name} Thermostat",
            Constant_Heating_Setpoint=zoneDefinition.Conditioning.HeatingSetpoint,
            Constant_Cooling_Setpoint=zoneDefinition.Conditioning.CoolingSetpoint,
        )
        idf.newidfobject(
            key="HVACTEMPLATE:ZONE:IDEALLOADSAIRSYSTEM",
            Zone_Name=zone.Name,
            Template_Thermostat_Name=stat.Name,
            System_Availability_Schedule_Name="",
            Maximum_Heating_Supply_Air_Temperature="50",
            Minimum_Cooling_Supply_Air_Temperature="13",
            Maximum_Heating_Supply_Air_Humidity_Ratio="0.0156",
            Minimum_Cooling_Supply_Air_Humidity_Ratio="0.0077",
            Heating_Limit=zoneDefinition.Conditioning.HeatingLimitType.name,
            Maximum_Heating_Air_Flow_Rate=zoneDefinition.Conditioning.MaxHeatFlow,
            Maximum_Sensible_Heating_Capacity=zoneDefinition.Conditioning.MaxHeatingCapacity,
            Cooling_Limit=zoneDefinition.Conditioning.CoolingLimitType.name,
            Maximum_Cooling_Air_Flow_Rate=zoneDefinition.Conditioning.MaxCoolFlow,
            Maximum_Total_Cooling_Capacity=zoneDefinition.Conditioning.MaxCoolingCapacity,
            Heating_Availability_Schedule_Name="",
            Cooling_Availability_Schedule_Name="",
            Dehumidification_Control_Type="ConstantSensibleHeatRatio",
            Cooling_Sensible_Heat_Ratio="0.7",
            Dehumidification_Setpoint=60.0,
            Humidification_Control_Type="None",
            Humidification_Setpoint=30.0,
            Outdoor_Air_Method="Sum",
            Outdoor_Air_Flow_Rate_per_Person=zoneDefinition.Conditioning.MinFreshAirPerPerson,
            Outdoor_Air_Flow_Rate_per_Zone_Floor_Area=zoneDefinition.Conditioning.MinFreshAirPerArea,
            Outdoor_Air_Flow_Rate_per_Zone=0.0,
            Design_Specification_Outdoor_Air_Object_Name=f"Zone {zone.Name} Outdoor Air",
            Demand_Controlled_Ventilation_Type="None",
            Outdoor_Air_Economizer_Type=zoneDefinition.Conditioning.EconomizerType.name,
            Heat_Recovery_Type=zoneDefinition.Conditioning.HeatRecoveryType.name,
            Sensible_Heat_Recovery_Effectiveness=zoneDefinition.Conditioning.HeatRecoveryEfficiencySensible,
            Latent_Heat_Recovery_Effectiveness=zoneDefinition.Conditioning.HeatRecoveryEfficiencyLatent,
        )


class PTHP(HVACTemplate):
    """For packaged terminal air-to-air heat pump (PTHP) systems."""

    REQUIRED = ["HVACTemplate:Thermostat", "HVACTemplate:Zone:PTHP"]
    OPTIONAL = []

    def create_from(self, zone, zoneDefinition):
        idf = zone.theidf
        stat = idf.newidfobject(
            "HVACTEMPLATE:THERMOSTAT",
            Name=f"Zone {zone.Name} Thermostat",
            Constant_Heating_Setpoint=zoneDefinition.Conditioning.HeatingSetpoint,
            Constant_Cooling_Setpoint=zoneDefinition.Conditioning.CoolingSetpoint,
        )
        idf.newidfobject(
            "HVACTEMPLATE:ZONE:PTHP",
            Zone_Name=zone.Name,
            Template_Thermostat_Name=stat.Name,
            Cooling_Coil_Gross_Rated_COP=zoneDefinition.Conditioning.CoolingCoeffOfPerf,
            Heating_Coil_Gross_Rated_COP=zoneDefinition.Conditioning.HeatingCoeffOfPerf,
        )


class BaseboardHeatingSystem(HVACTemplate):
    """For baseboard heating systems with optional hot water boiler."""

    REQUIRED = ["HVACTemplate:Thermostat", "HVACTemplate:Zone:BaseboardHeat"]
    OPTIONAL = ["HVACTemplate:Plant:HotWaterLoop", "HVACTemplate:Plant:Boiler"]

    def create_from(self, zone, zoneDefinition):
        """Create the hvac template from the Zone EpBunch and the ZoneDefiniion."""
        idf = zone.theidf
        stat = idf.newidfobject(
            "HVACTEMPLATE:THERMOSTAT",
            Name=f"Zone {zone.Name} Thermostat",
            Constant_Heating_Setpoint=zoneDefinition.Conditioning.HeatingSetpoint,
            Constant_Cooling_Setpoint=zoneDefinition.Conditioning.CoolingSetpoint,
        )
        idf.newidfobject(
            key="HVACTEMPLATE:ZONE:BASEBOARDHEAT",
            Zone_Name=zone.Name,
            Template_Thermostat_Name=stat.Name,
            Zone_Heating_Sizing_Factor="",
            Baseboard_Heating_Type="HotWater",
            Baseboard_Heating_Availability_Schedule_Name="",
            Baseboard_Heating_Capacity="autosize",
            Dedicated_Outdoor_Air_System_Name="",
            Outdoor_Air_Method="Flow/Person",
            Outdoor_Air_Flow_Rate_per_Person="0.00944",
            Outdoor_Air_Flow_Rate_per_Zone_Floor_Area="0.0",
            Outdoor_Air_Flow_Rate_per_Zone=0.0,
        )


HVACTemplates = {
    "BaseboardHeatingSystem": BaseboardHeatingSystem(),
    "SimpleIdealLoadsSystem": SimpleIdealLoadsSystem(),
    "PTHP": PTHP(),
}
