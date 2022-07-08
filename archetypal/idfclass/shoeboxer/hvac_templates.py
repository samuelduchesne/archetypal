"""HVAC Templates Module."""
from typing import Literal


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
            Maximum_Heating_Supply_Air_Temperature="",
            Minimum_Cooling_Supply_Air_Temperature="",
            Maximum_Heating_Supply_Air_Humidity_Ratio="",
            Minimum_Cooling_Supply_Air_Humidity_Ratio="",
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
            Design_Specification_Outdoor_Air_Object_Name=f"'{zone.Name}' Outdoor Air",
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
            key="HVACTEMPLATE:ZONE:PTHP",
            Zone_Name=zone.Name,
            Template_Thermostat_Name=stat.Name,
            Cooling_Supply_Air_Flow_Rate="autosize",
            Heating_Supply_Air_Flow_Rate="autosize",
            No_Load_Supply_Air_Flow_Rate="",
            Zone_Heating_Sizing_Factor="",
            Zone_Cooling_Sizing_Factor="",
            Outdoor_Air_Method="Flow/Person",
            Outdoor_Air_Flow_Rate_per_Person="0.00944",
            Outdoor_Air_Flow_Rate_per_Zone_Floor_Area="0.0",
            Outdoor_Air_Flow_Rate_per_Zone=0.0,
            System_Availability_Schedule_Name="",
            Supply_Fan_Operating_Mode_Schedule_Name="",
            Supply_Fan_Placement="DrawThrough",
            Supply_Fan_Total_Efficiency="0.7",
            Supply_Fan_Delta_Pressure="75",
            Supply_Fan_Motor_Efficiency="0.9",
            Cooling_Coil_Type="SingleSpeedDX",
            Cooling_Coil_Availability_Schedule_Name="",
            Cooling_Coil_Gross_Rated_Total_Capacity="autosize",
            Cooling_Coil_Gross_Rated_Sensible_Heat_Ratio="autosize",
            Cooling_Coil_Gross_Rated_COP=zoneDefinition.Conditioning.CoolingCoeffOfPerf,
            Heat_Pump_Heating_Coil_Type="SingleSpeedDXHeatPump",
            Heat_Pump_Heating_Coil_Availability_Schedule_Name="",
            Heat_Pump_Heating_Coil_Gross_Rated_Capacity="autosize",
            Heat_Pump_Heating_Coil_Gross_Rated_COP=zoneDefinition.Conditioning.HeatingCoeffOfPerf,
            Heat_Pump_Heating_Minimum_Outdoor_DryBulb_Temperature=-8.0,
            Heat_Pump_Defrost_Maximum_Outdoor_DryBulb_Temperature=5.0,
            Heat_Pump_Defrost_Strategy="ReverseCycle",
            Heat_Pump_Defrost_Control="Timed",
            Heat_Pump_Defrost_Time_Period_Fraction=0.058333,
            Supplemental_Heating_Coil_Type="Electric",
            Supplemental_Heating_Coil_Availability_Schedule_Name="",
            Supplemental_Heating_Coil_Capacity="autosize",
            Supplemental_Heating_Coil_Maximum_Outdoor_DryBulb_Temperature=21.0,
            Supplemental_Gas_Heating_Coil_Efficiency="0.8",
            Supplemental_Gas_Heating_Coil_Parasitic_Electric_Load="0.0",
            Dedicated_Outdoor_Air_System_Name="",
            Zone_Cooling_Design_Supply_Air_Temperature_Input_Method="SupplyAirTemperature",
            Zone_Cooling_Design_Supply_Air_Temperature=14.0,
            Zone_Cooling_Design_Supply_Air_Temperature_Difference=11.11,
            Zone_Heating_Design_Supply_Air_Temperature_Input_Method="SupplyAirTemperature",
            Zone_Heating_Design_Supply_Air_Temperature=50.0,
            Zone_Heating_Design_Supply_Air_Temperature_Difference=30.0,
            Design_Specification_Outdoor_Air_Object_Name="",
            Design_Specification_Zone_Air_Distribution_Object_Name="",
            Baseboard_Heating_Type="None",
            Baseboard_Heating_Availability_Schedule_Name="",
            Baseboard_Heating_Capacity="autosize",
            Capacity_Control_Method="None",
        )


class BaseboardHeatingSystem(HVACTemplate):
    """For baseboard heating systems with optional hot water boiler."""

    REQUIRED = ["HVACTemplate:Thermostat", "HVACTemplate:Zone:BaseboardHeat"]
    OPTIONAL = ["HVACTemplate:Plant:HotWaterLoop", "HVACTemplate:Plant:Boiler"]

    def __init__(
        self,
        Baseboard_Heating_Type: Literal["HotWater", "Electric"] = "HotWater",
        Boiler_Type: Literal[
            "DistrictHotWater", "HotWaterBoiler", "CondensingHotWaterBoiler"
        ] = "DistrictHotWater",
    ):
        super(BaseboardHeatingSystem, self).__init__()
        self.Baseboard_Heating_Type = Baseboard_Heating_Type
        self.Boiler_Type = Boiler_Type

    def create_from(
        self,
        zone,
        zoneDefinition,
    ):
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
            Baseboard_Heating_Type=self.Baseboard_Heating_Type,
            Baseboard_Heating_Availability_Schedule_Name="",
            Baseboard_Heating_Capacity="autosize",
            Dedicated_Outdoor_Air_System_Name="",
            Outdoor_Air_Method="Flow/Person",
            Outdoor_Air_Flow_Rate_per_Person="0.00944",
            Outdoor_Air_Flow_Rate_per_Zone_Floor_Area="0.0",
            Outdoor_Air_Flow_Rate_per_Zone=0.0,
        )

        if self.Baseboard_Heating_Type == "HotWater":
            idf.newidfobject(
                key="HVACTEMPLATE:PLANT:HOTWATERLOOP",
                Name="HotWaterLoop",
                Pump_Schedule_Name="",
                Pump_Control_Type="Intermittent",
                Hot_Water_Plant_Operation_Scheme_Type="Default",
                Hot_Water_Plant_Equipment_Operation_Schemes_Name="",
                Hot_Water_Setpoint_Schedule_Name="",
                Hot_Water_Design_Setpoint="82.0",
                Hot_Water_Pump_Configuration="ConstantFlow",
                Hot_Water_Pump_Rated_Head="179352",
                Hot_Water_Setpoint_Reset_Type="None",
                Hot_Water_Setpoint_at_Outdoor_DryBulb_Low="82.2",
                Hot_Water_Reset_Outdoor_DryBulb_Low="-6.7",
                Hot_Water_Setpoint_at_Outdoor_DryBulb_High="65.6",
                Hot_Water_Reset_Outdoor_DryBulb_High="10.0",
                Hot_Water_Pump_Type="SinglePump",
                Supply_Side_Bypass_Pipe="Yes",
                Demand_Side_Bypass_Pipe="Yes",
                Fluid_Type="Water",
                Loop_Design_Delta_Temperature="11.0",
                Maximum_Outdoor_Dry_Bulb_Temperature="",
                Load_Distribution_Scheme="SequentialLoad",
            )
            idf.newidfobject(
                key="HVACTEMPLATE:PLANT:BOILER",
                Name="PlantBoiler",
                Boiler_Type=self.Boiler_Type,
                Capacity="autosize",
                Efficiency="0.8",
                Fuel_Type="",
                Priority="",
                Sizing_Factor=1.0,
                Minimum_Part_Load_Ratio=0.0,
                Maximum_Part_Load_Ratio=1.1,
                Optimum_Part_Load_Ratio=1.0,
                Water_Outlet_Upper_Temperature_Limit=100.0,
            )


HVACTemplates = {
    "BaseboardHeatingSystemHotWater": BaseboardHeatingSystem(
        Baseboard_Heating_Type="HotWater"
    ),
    "BaseboardHeatingSystemElectric": BaseboardHeatingSystem(
        Baseboard_Heating_Type="Electric"
    ),
    "SimpleIdealLoadsSystem": SimpleIdealLoadsSystem(),
    "PTHP": PTHP(),
}
