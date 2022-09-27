"""HVAC Templates Module.

TODO:
    -[] VAV AHU w/PFP Terminals
    -[] WSHP
    -[x] Packaged rooftop heat pump (PTHP)
    -[] Packaged rooftop AC + Furnace

"""
from typing import Literal, Optional


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


class VAVWithBoilersAndChillers(HVACTemplate):
    """For variable air volume systems with boilers and air-cooled chillers.

    - HVACTemplate:Thermostat
    - HVACTemplate:Zone:VAV or
    - HVACTemplate:Zone:VAV:FanPowered or
    - HVACTemplate:Zone:VAV:HeatAndCool
    - HVACTemplate:System:VAV
    - HVACTemplate:Plant:ChilledWaterLoop
    - HVACTemplate:Plant:HotWaterLoop
    - HVACTemplate:Plant:Chiller
    - HVACTemplate:Plant:Boiler
    """

    REQUIRED = ["HVACTemplate:Thermostat", "HVACTemplate:System:PackagedVAV"]
    OPTIONAL = []

    def __init__(
        self,
        Baseboard_Heating_Type: Literal["None", "HotWater", "Electric"] = "None",
        Boiler_Type: Literal[
            "DistrictHotWater", "HotWaterBoiler", "CondensingHotWaterBoiler"
        ] = "DistrictHotWater",
        Chiller_Type: Literal[
            "DistrictChilledWater",
            "ElectricCentrifugalChiller",
            "ElectricScrewChiller",
            "ElectricReciprocatingChiller",
        ] = "DistrictChilledWater",
        Condenser_Type: Literal[
            "AirCooled", "WaterCooled", "EvaporativelyCooled"
        ] = "AirCooled",
    ):
        """Initialize a VAV System with Chillers and Boilers.

        Args:
            Baseboard_Heating_Type (str): This field specifies the availability of
                thermostatically controlled baseboard heat in this zone.
            Boiler_Type (str): While EnergyPlus has a variety of boiler options,
                the choices for this field are: DistrictHotWater – District heating,
                HotWaterBoiler – Hot water boiler (non-condensing),
                CondensingHotWaterBoiler – Hot water boiler (condensing)
            Chiller_Type (str): While EnergyPlus has a variety of chiller options,
                the only choices currently for this field are: DistrictChilledWater,
                ElectricCentrifugalChiller, ElectricScrewChiller,
                ElectricReciprocatingChiller
            Condenser_Type (str): The choices for this field are: AirCooled,
                WaterCooled, EvaporativelyCooled. The default value is WaterCooled.
                If WaterCooled, then one HVACTemplate:Plant:Tower is created. Not
                applicable if Chiller Type is Purchased Chilled Water.
        """
        super(VAVWithBoilersAndChillers, self).__init__()
        self.Condenser_Type = Condenser_Type
        self.Chiller_Type = Chiller_Type
        self.Baseboard_Heating_Type = Baseboard_Heating_Type
        self.Boiler_Type = Boiler_Type

    def create_from(self, zone, zoneDefinition):
        """Create.

        Args:
            zone (EpBunch): The zone EpBunch object.
            zoneDefinition (ZoneDefinition): The archetypal template ZoneDefinition
                object.
        """
        idf = zone.theidf

        # For autosizing of AirLoopHVAC PACKAGEDVAV, a system sizing run must be done.
        # The "SimulationControl" object must have the field "Do System Sizing
        # Calculation" set to Yes.
        for sim_control in idf.idfobjects["SimulationControl".upper()]:
            sim_control.Do_System_Sizing_Calculation = "Yes"

        stat = idf.newidfobject(
            "HVACTEMPLATE:THERMOSTAT",
            Name=f"Zone {zone.Name} Thermostat",
            Constant_Heating_Setpoint=zoneDefinition.Conditioning.HeatingSetpoint,
            Constant_Cooling_Setpoint=zoneDefinition.Conditioning.CoolingSetpoint,
        )
        # https://bigladdersoftware.com/epx/docs/9-3/input-output-reference/group-hvac-templates.html#hvactemplatezonevav
        zone_vav = idf.newidfobject(
            key="HVACTEMPLATE:ZONE:VAV",
            Zone_Name=zone.Name,
            Template_VAV_System_Name="System:VAV",
            Template_Thermostat_Name=stat.Name,
            Supply_Air_Maximum_Flow_Rate="autosize",
            Zone_Heating_Sizing_Factor="",
            Zone_Cooling_Sizing_Factor="",
            Zone_Minimum_Air_Flow_Input_Method="Constant",
            Constant_Minimum_Air_Flow_Fraction="0.2",
            Fixed_Minimum_Air_Flow_Rate="",
            Minimum_Air_Flow_Fraction_Schedule_Name="",
            Outdoor_Air_Method="Sum",
            Outdoor_Air_Flow_Rate_per_Person=zoneDefinition.Conditioning.MinFreshAirPerPerson,
            Outdoor_Air_Flow_Rate_per_Zone_Floor_Area=zoneDefinition.Conditioning.MinFreshAirPerArea,
            Outdoor_Air_Flow_Rate_per_Zone=0.0,
            Reheat_Coil_Type="HotWater",
            Reheat_Coil_Availability_Schedule_Name="",
            Damper_Heating_Action="Reverse",
            Maximum_Flow_per_Zone_Floor_Area_During_Reheat="",
            Maximum_Flow_Fraction_During_Reheat="",
            Maximum_Reheat_Air_Temperature="",
            Design_Specification_Outdoor_Air_Object_Name_for_Control="",
            Supply_Plenum_Name="",
            Return_Plenum_Name="",
            Baseboard_Heating_Type=self.Baseboard_Heating_Type,
            Baseboard_Heating_Availability_Schedule_Name="",
            Baseboard_Heating_Capacity="autosize",
            Zone_Cooling_Design_Supply_Air_Temperature_Input_Method="SystemSupplyAirTemperature",
            Zone_Cooling_Design_Supply_Air_Temperature=12.8,
            Zone_Cooling_Design_Supply_Air_Temperature_Difference=11.11,
            Zone_Heating_Design_Supply_Air_Temperature_Input_Method="SupplyAirTemperature",
            Zone_Heating_Design_Supply_Air_Temperature=50.0,
            Zone_Heating_Design_Supply_Air_Temperature_Difference=30.0,
        )

        if len(idf.idfobjects["HVACTEMPLATE:SYSTEM:VAV"]) == 0:
            idf.newidfobject(
                key="HVACTEMPLATE:SYSTEM:VAV",
                Name="System:VAV",
                System_Availability_Schedule_Name="",
                Supply_Fan_Maximum_Flow_Rate="autosize",
                Supply_Fan_Minimum_Flow_Rate="autosize",
                Supply_Fan_Total_Efficiency="0.7",
                Supply_Fan_Delta_Pressure="1000",
                Supply_Fan_Motor_Efficiency="0.9",
                Supply_Fan_Motor_in_Air_Stream_Fraction="1.0",
                Cooling_Coil_Type="ChilledWater",
                Cooling_Coil_Availability_Schedule_Name="",
                Cooling_Coil_Setpoint_Schedule_Name="",
                Cooling_Coil_Design_Setpoint="12.8",
                Heating_Coil_Type="HotWater",
                Heating_Coil_Availability_Schedule_Name="",
                Heating_Coil_Setpoint_Schedule_Name="",
                Heating_Coil_Design_Setpoint="10.0",
                Gas_Heating_Coil_Efficiency="0.8",
                Gas_Heating_Coil_Parasitic_Electric_Load="0.0",
                Preheat_Coil_Type="None",
                Preheat_Coil_Availability_Schedule_Name="",
                Preheat_Coil_Setpoint_Schedule_Name="",
                Preheat_Coil_Design_Setpoint="7.2",
                Gas_Preheat_Coil_Efficiency="0.8",
                Gas_Preheat_Coil_Parasitic_Electric_Load="0.0",
                Maximum_Outdoor_Air_Flow_Rate="autosize",
                Minimum_Outdoor_Air_Flow_Rate="autosize",
                Minimum_Outdoor_Air_Control_Type="ProportionalMinimum",
                Minimum_Outdoor_Air_Schedule_Name="",
                Economizer_Type="NoEconomizer",
                Economizer_Lockout="NoLockout",
                Economizer_Upper_Temperature_Limit="",
                Economizer_Lower_Temperature_Limit="",
                Economizer_Upper_Enthalpy_Limit="",
                Economizer_Maximum_Limit_Dewpoint_Temperature="",
                Supply_Plenum_Name="",
                Return_Plenum_Name="",
                Supply_Fan_Placement="DrawThrough",
                Supply_Fan_PartLoad_Power_Coefficients="InletVaneDampers",
                Night_Cycle_Control="StayOff",
                Night_Cycle_Control_Zone_Name="",
                Heat_Recovery_Type="None",
                Sensible_Heat_Recovery_Effectiveness="0.70",
                Latent_Heat_Recovery_Effectiveness="0.65",
                Cooling_Coil_Setpoint_Reset_Type="None",
                Heating_Coil_Setpoint_Reset_Type="None",
                Dehumidification_Control_Type="None",
                Dehumidification_Control_Zone_Name="",
                Dehumidification_Setpoint=60.0,
                Humidifier_Type="None",
                Humidifier_Availability_Schedule_Name="",
                Humidifier_Rated_Capacity=1e-06,
                Humidifier_Rated_Electric_Power="autosize",
                Humidifier_Control_Zone_Name="",
                Humidifier_Setpoint=30.0,
                Sizing_Option="NonCoincident",
                Return_Fan="No",
                Return_Fan_Total_Efficiency="0.7",
                Return_Fan_Delta_Pressure="500",
                Return_Fan_Motor_Efficiency="0.9",
                Return_Fan_Motor_in_Air_Stream_Fraction="1.0",
                Return_Fan_PartLoad_Power_Coefficients="InletVaneDampers",
            )

            idf.newidfobject(
                key="HVACTEMPLATE:PLANT:CHILLEDWATERLOOP",
                Name="PLANT:CHILLEDWATERLOOP",
                Pump_Schedule_Name="",
                Pump_Control_Type="Intermittent",
                Chiller_Plant_Operation_Scheme_Type="Default",
                Chiller_Plant_Equipment_Operation_Schemes_Name="",
                Chilled_Water_Setpoint_Schedule_Name="",
                Chilled_Water_Design_Setpoint="6",
                Chilled_Water_Pump_Configuration="ConstantPrimaryNoSecondary",
                Primary_Chilled_Water_Pump_Rated_Head="179352",
                Secondary_Chilled_Water_Pump_Rated_Head="179352",
                Condenser_Plant_Operation_Scheme_Type="Default",
                Condenser_Equipment_Operation_Schemes_Name="",
                Condenser_Water_Temperature_Control_Type="",
                Condenser_Water_Setpoint_Schedule_Name="",
                Condenser_Water_Design_Setpoint="29.4",
                Condenser_Water_Pump_Rated_Head="179352",
                Chilled_Water_Setpoint_Reset_Type="OutdoorAirTemperatureReset",
                Chilled_Water_Setpoint_at_Outdoor_DryBulb_Low="12.2",
                Chilled_Water_Reset_Outdoor_DryBulb_Low="15.6",
                Chilled_Water_Setpoint_at_Outdoor_DryBulb_High="6.7",
                Chilled_Water_Reset_Outdoor_DryBulb_High="26.7",
                Chilled_Water_Primary_Pump_Type="SinglePump",
                Chilled_Water_Secondary_Pump_Type="SinglePump",
                Condenser_Water_Pump_Type="SinglePump",
                Chilled_Water_Supply_Side_Bypass_Pipe="Yes",
                Chilled_Water_Demand_Side_Bypass_Pipe="Yes",
                Condenser_Water_Supply_Side_Bypass_Pipe="Yes",
                Condenser_Water_Demand_Side_Bypass_Pipe="Yes",
                Fluid_Type="Water",
                Loop_Design_Delta_Temperature=8,
                Minimum_Outdoor_Dry_Bulb_Temperature="",
                Chilled_Water_Load_Distribution_Scheme="SequentialLoad",
                Condenser_Water_Load_Distribution_Scheme="SequentialLoad",
            )

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
                key="HVACTEMPLATE:PLANT:CHILLER",
                Name="PLANT:CHILLER",
                Chiller_Type=self.Chiller_Type,
                Capacity="autosize",
                Nominal_COP=zoneDefinition.Conditioning.CoolingCoeffOfPerf,
                Condenser_Type=self.Condenser_Type,
                Priority="",
                Sizing_Factor=1.0,
                Minimum_Part_Load_Ratio=0.0,
                Maximum_Part_Load_Ratio=1.0,
                Optimum_Part_Load_Ratio=1.0,
                Minimum_Unloading_Ratio=0.25,
                Leaving_Chilled_Water_Lower_Temperature_Limit=5.0,
            )

            if self.Condenser_Type == "WaterCooled":
                idf.newidfobject(
                    key="HVACTEMPLATE:PLANT:TOWER",
                    Name="CoolingTower",
                    Tower_Type="SingleSpeed",
                    High_Speed_Nominal_Capacity="autosize",
                    High_Speed_Fan_Power="autosize",
                    Low_Speed_Nominal_Capacity="autosize",
                    Low_Speed_Fan_Power="autosize",
                    Free_Convection_Capacity="autosize",
                    Priority="",
                    Sizing_Factor=1.0,
                )

            idf.newidfobject(
                key="HVACTEMPLATE:PLANT:BOILER",
                Name="PlantBoiler",
                Boiler_Type=self.Boiler_Type,
                Capacity="autosize",
                Efficiency=min(zoneDefinition.Conditioning.HeatingCoeffOfPerf, 1),
                Fuel_Type=zoneDefinition.Conditioning.HeatingFuelType,
                Priority="",
                Sizing_Factor=1.0,
                Minimum_Part_Load_Ratio=0.0,
                Maximum_Part_Load_Ratio=1.1,
                Optimum_Part_Load_Ratio=1.0,
                Water_Outlet_Upper_Temperature_Limit=100.0,
            )


class PackagedVAVWithDXCooling(HVACTemplate):
    """For packaged variable air volume systems using direct-expansion cooling.

    - HVACTemplate:Thermostat
    - HVACTemplate:Zone:VAV or
    - HVACTemplate:Zone:VAV:FanPowered or
    - HVACTemplate:Zone:VAV:HeatAndCool
    - HVACTemplate:System:PackagedVAV
    """

    REQUIRED = ["HVACTemplate:Thermostat", "HVACTemplate:System:PackagedVAV"]
    OPTIONAL = []

    def create_from(self, zone, zoneDefinition):
        """Create.

        Args:
            zone (EpBunch): The zone EpBunch object.
            zoneDefinition (ZoneDefinition): The archetypal template ZoneDefinition
                object.
        """
        idf = zone.theidf

        # For autosizing of AirLoopHVAC PACKAGEDVAV, a system sizing run must be done.
        # The "SimulationControl" object must have the field "Do System Sizing
        # Calculation" set to Yes.
        for sim_control in idf.idfobjects["SimulationControl".upper()]:
            sim_control.Do_System_Sizing_Calculation = "Yes"

        stat = idf.newidfobject(
            "HVACTEMPLATE:THERMOSTAT",
            Name=f"Zone {zone.Name} Thermostat",
            Constant_Heating_Setpoint=zoneDefinition.Conditioning.HeatingSetpoint,
            Constant_Cooling_Setpoint=zoneDefinition.Conditioning.CoolingSetpoint,
        )

        zone_vav = idf.newidfobject(
            key="HVACTEMPLATE:ZONE:VAV",
            Zone_Name=zone.Name,
            Template_VAV_System_Name="PackagedVAV",
            Template_Thermostat_Name=stat.Name,
            Supply_Air_Maximum_Flow_Rate="autosize",
            Zone_Heating_Sizing_Factor="",
            Zone_Cooling_Sizing_Factor="",
            Zone_Minimum_Air_Flow_Input_Method="Constant",
            Constant_Minimum_Air_Flow_Fraction="0.2",
            Fixed_Minimum_Air_Flow_Rate="",
            Minimum_Air_Flow_Fraction_Schedule_Name="",
            Outdoor_Air_Method="Sum",
            Outdoor_Air_Flow_Rate_per_Person=zoneDefinition.Conditioning.MinFreshAirPerPerson,
            Outdoor_Air_Flow_Rate_per_Zone_Floor_Area=zoneDefinition.Conditioning.MinFreshAirPerArea,
            Outdoor_Air_Flow_Rate_per_Zone=0.0,
            Reheat_Coil_Type="None",
            Reheat_Coil_Availability_Schedule_Name="",
            Damper_Heating_Action="Reverse",
            Maximum_Flow_per_Zone_Floor_Area_During_Reheat="",
            Maximum_Flow_Fraction_During_Reheat="",
            Maximum_Reheat_Air_Temperature="",
            Design_Specification_Outdoor_Air_Object_Name_for_Control="",
            Supply_Plenum_Name="",
            Return_Plenum_Name="",
            Baseboard_Heating_Type="None",
            Baseboard_Heating_Availability_Schedule_Name="",
            Baseboard_Heating_Capacity="autosize",
            Zone_Cooling_Design_Supply_Air_Temperature_Input_Method="SystemSupplyAirTemperature",
            Zone_Cooling_Design_Supply_Air_Temperature=12.8,
            Zone_Cooling_Design_Supply_Air_Temperature_Difference=11.11,
            Zone_Heating_Design_Supply_Air_Temperature_Input_Method="SupplyAirTemperature",
            Zone_Heating_Design_Supply_Air_Temperature=50.0,
            Zone_Heating_Design_Supply_Air_Temperature_Difference=30.0,
        )

        if len(idf.idfobjects["HVACTEMPLATE:SYSTEM:PACKAGEDVAV"]) == 0:
            idf.newidfobject(
                key="HVACTEMPLATE:SYSTEM:PACKAGEDVAV",
                Name=f"PackagedVAV",
                System_Availability_Schedule_Name="",
                Supply_Fan_Maximum_Flow_Rate="autosize",
                Supply_Fan_Minimum_Flow_Rate="autosize",
                Supply_Fan_Placement="DrawThrough",
                Supply_Fan_Total_Efficiency="0.7",
                Supply_Fan_Delta_Pressure="1000",
                Supply_Fan_Motor_Efficiency="0.9",
                Supply_Fan_Motor_in_Air_Stream_Fraction="1.0",
                Cooling_Coil_Type="TwoSpeedDX",
                Cooling_Coil_Availability_Schedule_Name="",
                Cooling_Coil_Setpoint_Schedule_Name="",
                Cooling_Coil_Design_Setpoint="12.8",
                Cooling_Coil_Gross_Rated_Total_Capacity="autosize",
                Cooling_Coil_Gross_Rated_Sensible_Heat_Ratio="autosize",
                Cooling_Coil_Gross_Rated_COP="3.0",
                Heating_Coil_Type="None",
                Heating_Coil_Availability_Schedule_Name="",
                Heating_Coil_Setpoint_Schedule_Name="",
                Heating_Coil_Design_Setpoint="10.0",
                Heating_Coil_Capacity="autosize",
                Gas_Heating_Coil_Efficiency="0.8",
                Gas_Heating_Coil_Parasitic_Electric_Load="0.0",
                Maximum_Outdoor_Air_Flow_Rate="autosize",
                Minimum_Outdoor_Air_Flow_Rate="autosize",
                Minimum_Outdoor_Air_Control_Type="ProportionalMinimum",
                Minimum_Outdoor_Air_Schedule_Name="",
                Economizer_Type="NoEconomizer",
                Economizer_Lockout="NoLockout",
                Economizer_Maximum_Limit_DryBulb_Temperature="",
                Economizer_Maximum_Limit_Enthalpy="",
                Economizer_Maximum_Limit_Dewpoint_Temperature="",
                Economizer_Minimum_Limit_DryBulb_Temperature="",
                Supply_Plenum_Name="",
                Return_Plenum_Name="",
                Supply_Fan_PartLoad_Power_Coefficients="InletVaneDampers",
                Night_Cycle_Control="StayOff",
                Night_Cycle_Control_Zone_Name="",
                Heat_Recovery_Type="None",
                Sensible_Heat_Recovery_Effectiveness="0.70",
                Latent_Heat_Recovery_Effectiveness="0.65",
                Cooling_Coil_Setpoint_Reset_Type="None",
                Heating_Coil_Setpoint_Reset_Type="None",
                Dehumidification_Control_Type="None",
                Dehumidification_Control_Zone_Name="",
                Dehumidification_Setpoint=60.0,
                Humidifier_Type="None",
                Humidifier_Availability_Schedule_Name="",
                Humidifier_Rated_Capacity=1e-06,
                Humidifier_Rated_Electric_Power="autosize",
                Humidifier_Control_Zone_Name="",
                Humidifier_Setpoint=30.0,
                Sizing_Option="NonCoincident",
                Return_Fan="No",
                Return_Fan_Total_Efficiency="0.7",
                Return_Fan_Delta_Pressure="500",
                Return_Fan_Motor_Efficiency="0.9",
                Return_Fan_Motor_in_Air_Stream_Fraction="1.0",
                Return_Fan_PartLoad_Power_Coefficients="InletVaneDampers",
            )


class PTHP(HVACTemplate):
    """For packaged terminal air-to-air heat pump (PTHP) systems.

    Each zone gets its own PTHP.
    """

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
            Outdoor_Air_Method="Sum",
            Outdoor_Air_Flow_Rate_per_Person=zoneDefinition.Conditioning.MinFreshAirPerPerson,
            Outdoor_Air_Flow_Rate_per_Zone_Floor_Area=zoneDefinition.Conditioning.MinFreshAirPerArea,
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
            Outdoor_Air_Method="Sum",
            Outdoor_Air_Flow_Rate_per_Person=zoneDefinition.Conditioning.MinFreshAirPerPerson,
            Outdoor_Air_Flow_Rate_per_Zone_Floor_Area=zoneDefinition.Conditioning.MinFreshAirPerArea,
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
                Efficiency=min(zoneDefinition.Conditioning.HeatingCoeffOfPerf, 1),
                Fuel_Type=zoneDefinition.Conditioning.HeatingFuelType,  # Not applicable if Boiler Type is DistrictHotWater
                Priority="",
                Sizing_Factor=1.0,
                Minimum_Part_Load_Ratio=0.0,
                Maximum_Part_Load_Ratio=1.1,
                Optimum_Part_Load_Ratio=1.0,
                Water_Outlet_Upper_Temperature_Limit=100.0,
            )


class WaterSourceHeatPumpWithTowerAndBoiler(HVACTemplate):
    """For water to air heat pumps with boiler and cooling tower.

    HVACTemplate:Thermostat
    HVACTemplate:Zone:WaterToAirHeatPump
    HVACTemplate:Plant:MixedWaterLoop
    HVACTemplate:Plant:Boiler
    HVACTemplate:Plant:Tower
    """

    REQUIRED = [
        "HVACTemplate:Thermostat",
        "HVACTemplate:Zone:WaterToAirHeatPump",
        "HVACTemplate:Plant:MixedWaterLoop",
        "HVACTemplate:Plant:Boiler",
        "HVACTemplate:Plant:Tower",
    ]
    OPTIONAL = []

    # TODO: Complete class


HVACTemplates = {
    "BaseboardHeatingSystemHotWater": BaseboardHeatingSystem(
        Baseboard_Heating_Type="HotWater"
    ),
    "BaseboardHeatingSystemElectric": BaseboardHeatingSystem(
        Baseboard_Heating_Type="Electric"
    ),
    "SimpleIdealLoadsSystem": SimpleIdealLoadsSystem(),
    "PTHP": PTHP(),
    "PackagedVAVWithDXCooling": PackagedVAVWithDXCooling(),
    "VAVWithDistrictHeatingCooling": VAVWithBoilersAndChillers(),
}
