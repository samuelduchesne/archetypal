from __future__ import annotations

from collections.abc import Iterable
from typing import Literal

from archetypal.idfclass.end_use_balance import EndUseBalance
from archetypal.idfclass.extensions import get_name_attribute


class Outputs:
    """Handles preparation of EnergyPlus outputs. Different instance methods
    allow to chain methods together and to add predefined bundles of outputs in
    one go. `.apply()` is required at the end to apply the outputs to the IDF model.

    Examples:
        >>> from archetypal import IDF
        >>> idf = IDF(prep_outputs=False)  # True be default
        >>> idf.outputs.add_output_control().add_umi_outputs(
        >>> ).add_profile_gas_elect_outputs().apply()
    """

    REPORTING_FREQUENCIES = ("Annual", "Monthly", "Daily", "Hourly", "Timestep")
    COOLING = (
        "Zone Ideal Loads Supply Air Total Cooling Energy",
        "Zone Ideal Loads Zone Sensible Cooling Energy",
        "Zone Ideal Loads Zone Latent Cooling Energy",
    )
    HEATING = (
        "Zone Ideal Loads Supply Air Total Heating Energy",
        "Zone Ideal Loads Zone Sensible Heating Energy",
        "Zone Ideal Loads Zone Latent Heating Energy",
    )
    LIGHTING = (
        "Zone Lights Electric Energy",
        "Zone Lights Total Heating Energy",
    )
    ELECTRIC_EQUIP = (
        "Zone Electric Equipment Electricity Energy",
        "Zone Electric Equipment Total Heating Energy",
        "Zone Electric Equipment Radiant Heating Energy",
        "Zone Electric Equipment Convective Heating Energy",
        "Zone Electric Equipment Latent Gain Energy",
    )
    GAS_EQUIP = (
        "Zone Gas Equipment NaturalGas Energy",
        "Zone Gas Equipment Total Heating Energy",
        "Zone Gas Equipment Radiant Heating Energy",
        "Zone Gas Equipment Convective Heating Energy",
        "Zone Gas Equipment Latent Gain Energy",
    )
    HOT_WATER = (
        "Water Use Equipment Zone Sensible Heat Gain Energy",
        "Water Use Equipment Zone Latent Gain Energy",
    )
    PEOPLE_GAIN = (
        "Zone People Total Heating Energy",
        "Zone People Sensible Heating Energy",
        "Zone People Latent Gain Energy",
    )
    SOLAR_GAIN = ("Zone Windows Total Transmitted Solar Radiation Energy",)
    INFIL_GAIN = (
        "Zone Infiltration Total Heat Gain Energy",
        "Zone Infiltration Sensible Heat Gain Energy",
        "Zone Infiltration Latent Heat Gain Energy",
        "AFN Zone Infiltration Sensible Heat Gain Energy",
        "AFN Zone Infiltration Latent Heat Gain Energy",
    )
    INFIL_LOSS = (
        "Zone Infiltration Total Heat Loss Energy",
        "Zone Infiltration Sensible Heat Loss Energy",
        "Zone Infiltration Latent Heat Loss Energy",
        "AFN Zone Infiltration Sensible Heat Loss Energy",
        "AFN Zone Infiltration Latent Heat Loss Energy",
    )
    VENT_LOSS = (
        "Zone Ideal Loads Zone Total Heating Energy",
        "Zone Ideal Loads Zone Sensible Heating Energy",
        "Zone Ideal Loads Zone Latent Heating Energy",
    )
    VENT_GAIN = (
        "Zone Ideal Loads Zone Total Cooling Energy",
        "Zone Ideal Loads Zone Sensible Cooling Energy",
        "Zone Ideal Loads Zone Latent Cooling Energy",
    )
    NAT_VENT_GAIN = (
        "Zone Ventilation Total Heat Gain Energy",
        "Zone Ventilation Sensible Heat Gain Energy",
        "Zone Ventilation Latent Heat Gain Energy",
        "AFN Zone Ventilation Sensible Heat Gain Energy",
        "AFN Zone Ventilation Latent Heat Gain Energy",
    )
    NAT_VENT_LOSS = (
        "Zone Ventilation Total Heat Loss Energy",
        "Zone Ventilation Sensible Heat Loss Energy",
        "Zone Ventilation Latent Heat Loss Energy",
        "AFN Zone Ventilation Sensible Heat Loss Energy",
        "AFN Zone Ventilation Latent Heat Loss Energy",
    )
    OPAQUE_ENERGY_FLOW = ("Surface Average Face Conduction Heat Transfer Energy",)
    WINDOW_LOSS = ("Surface Window Heat Loss Energy",)
    WINDOW_GAIN = ("Surface Window Heat Gain Energy",)

    def __init__(
        self,
        idf,
        variables=(),
        meters=(),
        outputs=None,
        reporting_frequency="Monthly",
        include_sqlite=True,
        include_html=True,
        unit_conversion=None,
    ):
        """Initialize an outputs object.

        Args:
            idf (IDF): the IDF object for wich this outputs object is created.
        """
        self.idf = idf
        self.reporting_frequency = reporting_frequency
        self.output_variables = {a.Variable_Name for a in idf.idfobjects["Output:Variable".upper()]}
        self.output_meters = {
            (get_name_attribute(a), a.Reporting_Frequency) for a in idf.idfobjects["Output:Meter".upper()]
        }
        self.other_outputs = outputs

        self.output_variables += tuple((v, reporting_frequency) for v in variables)
        self.output_meters += tuple((m, reporting_frequency) for m in meters)
        self.other_outputs += tuple(outputs or ())
        self.include_sqlite = include_sqlite
        self.include_html = include_html
        self.unit_conversion = unit_conversion

    @property
    def unit_conversion(self):
        return self._unit_conversion

    @unit_conversion.setter
    def unit_conversion(self, value):
        if not value:
            value = "None"
        assert value in ["None", "JtoKWH", "JtoMJ", "JtoGJ", "InchPound"]
        for obj in self.idf.idfobjects["OutputControl:Table:Style".upper()]:
            obj.Unit_Conversion = value
        self._unit_conversion = value

    @property
    def include_sqlite(self):
        """Get or set a boolean for whether a SQLite report should be generated."""
        return self._include_sqlite

    @include_sqlite.setter
    def include_sqlite(self, value):
        value = bool(value)
        if value:
            self.add_sql().apply()
        else:
            # if False, try to remove sql, if exists.
            for obj in self.idf.idfobjects["Output:SQLite".upper()]:
                self.idf.removeidfobject(obj)
        self._include_sqlite = value

    @property
    def include_html(self):
        """Get or set a boolean for whether an HTML report should be generated."""
        return self._include_html

    @include_html.setter
    def include_html(self, value):
        value = bool(value)
        if value:
            self.add_output_control().apply()
        else:
            # if False, try to remove sql, if exists.
            for obj in self.idf.idfobjects["OutputControl:Table:Style".upper()]:
                obj.Column_Separator = "Comma"
        self._include_html = value

    @property
    def output_variables(self) -> tuple:
        """Get or set a tuple of EnergyPlus simulation output variables."""
        return tuple(sorted(self._output_variables))

    @output_variables.setter
    def output_variables(self, value):
        if value is not None:
            assert not isinstance(value, (str, bytes)), f"Expected list or tuple. Got {type(value)}."
            values = []
            # for each element
            for output in value:
                if isinstance(output, tuple):
                    values.append(output)
                else:
                    values.append((output, self.reporting_frequency))
            value = set(values)
        else:
            value = ()
        self._output_variables = value

    @property
    def output_meters(self):
        """Get or set a tuple of EnergyPlus simulation output meters."""
        return tuple(sorted(self._output_meters))

    @output_meters.setter
    def output_meters(self, value):
        if value is not None:
            assert not isinstance(value, (str, bytes)), f"Expected list or tuple. Got {type(value)}."
            values = []
            for output in value:
                if isinstance(output, tuple):
                    values.append(output)
                else:
                    values.append((output, self.reporting_frequency))
            value = set(values)
        else:
            value = set()
        self._output_meters = value

    @property
    def other_outputs(self):
        """Get or set a list of outputs."""
        return self._other_outputs

    @other_outputs.setter
    def other_outputs(self, value):
        if value is not None:
            assert all(isinstance(item, dict) for item in value), f"Expected list of dict. Got {type(value)}."
            values = []
            for output in value:
                values.append(output)
            value = values
        else:
            value = []
        self._other_outputs = value

    @property
    def reporting_frequency(self):
        """Get or set the reporting frequency of outputs.

        Choose from the following:

        * Annual
        * Monthly
        * Daily
        * Hourly
        * Timestep
        """
        return self._reporting_frequency

    @reporting_frequency.setter
    def reporting_frequency(self, value):
        value = value.title()
        assert (
            value in self.REPORTING_FREQUENCIES
        ), f"reporting_frequency {value} is not recognized.\nChoose from the following:\n{self.REPORTING_FREQUENCIES}"
        self._reporting_frequency = value

    def add_custom(self, outputs):
        """Add custom-defined outputs as a list of objects.

        Examples:
            >>> outputs = IDF().outputs
            >>> to_add = dict(
            >>>       key= "OUTPUT:METER",
            >>>       Key_Name="Electricity:Facility",
            >>>       Reporting_Frequency="hourly",
            >>> )
            >>> outputs.add_custom([to_add]).apply()

        Args:
            outputs (list, bool): Pass a list of ep-objects defined as dictionary. See
                examples. If a bool, ignored.

        Returns:
            Outputs: self
        """
        assert isinstance(outputs, Iterable), "outputs must be some sort of iterable"
        for output in outputs:
            if "meter" in output["key"].lower():
                self._output_meters.add((output["Key_Name"], output["Reporting_Frequency"].title()))
            elif "variable" in output["key"].lower():
                self._output_variables.add((output["Variable_Name"], output["Reporting_Frequency"].title()))
            else:
                self._other_outputs.append(output)
        return self

    def add_basics(self):
        """Adds the summary report and the sql file to the idf outputs"""
        return self.add_summary_report().add_output_control().add_schedules().add_meter_variables()

    def add_schedules(self):
        """Adds Schedules object"""
        outputs = [{"key": "Output:Schedules".upper(), **{"Key_Field": "Hourly"}}]
        for output in outputs:
            self._other_outputs.append(output)
        return self

    def add_meter_variables(self, key_field: Literal["IDF", "regular"] = "IDF"):
        """Generate .mdd file at end of simulation. This file (from the
        Output:VariableDictionary, regular; and Output:VariableDictionary,
        IDF; commands) shows all the report meters along with their “availability”
        for the current input file. A user must first run the simulation (at least
        semi-successfully) before the available output meters are known. This output
        file is available in two flavors: regular (listed as they are in the Input
        Output Reference) and IDF (ready to be copied and pasted into your Input File).

        Args:
            key_field (str): Choices are IDF, regular

        Returns:
            Outputs: self
        """
        outputs = [{"key": "Output:VariableDictionary".upper(), "Key_Field": key_field}]
        for output in outputs:
            self._other_outputs.append(output)
        return self

    def add_summary_report(self, summary="AllSummary"):
        """Adds the Output:Table:SummaryReports object.

        Args:
            summary (str): Choices are AllSummary, AllMonthly,
                AllSummaryAndMonthly, AllSummaryAndSizingPeriod,
                AllSummaryMonthlyAndSizingPeriod,
                AnnualBuildingUtilityPerformanceSummary,
                InputVerificationandResultsSummary,
                SourceEnergyEndUseComponentsSummary, ClimaticDataSummary,
                EnvelopeSummary, SurfaceShadowingSummary, ShadingSummary,
                LightingSummary, EquipmentSummary, HVACSizingSummary,
                ComponentSizingSummary, CoilSizingDetails, OutdoorAirSummary,
                SystemSummary, AdaptiveComfortSummary, SensibleHeatGainSummary,
                Standard62.1Summary, EnergyMeters, InitializationSummary,
                LEEDSummary, TariffReport, EconomicResultSummary,
                ComponentCostEconomicsSummary, LifeCycleCostReport,
                HeatEmissionsSummary,
        Returns:
            Outputs: self
        """
        outputs = [
            {
                "key": "Output:Table:SummaryReports".upper(),
                **{"Report_1_Name": summary},
            }
        ]
        for output in outputs:
            self._other_outputs.append(output)
        return self

    def add_sql(self, sql_output_style="SimpleAndTabular"):
        """Adds the `Output:SQLite` object. This object will produce an sql file
        that contains the simulation results in a database format. See
        `eplusout.sql
        <https://bigladdersoftware.com/epx/docs/9-2/output-details-and
        -examples/eplusout-sql.html#eplusout.sql>`_ for more details.

        Args:
            sql_output_style (str): The *Simple* option will include all of the
                predefined database tables as well as time series related data.
                Using the *SimpleAndTabular* choice adds database tables related
                to the tabular reports that are already output by EnergyPlus in
                other formats.
        Returns:
            Outputs: self
        """
        outputs = [{"key": "Output:SQLite".upper(), **{"Option_Type": sql_output_style}}]

        for output in outputs:
            self._other_outputs.append(output)
        return self

    def add_output_control(self, output_control_table_style="CommaAndHTML"):
        """Sets the `OutputControl:Table:Style` object.

        Args:
            output_control_table_style (str): Choices are: Comma, Tab, Fixed,
                HTML, XML, CommaAndHTML, TabAndHTML, XMLAndHTML, All
        Returns:
            Outputs: self
        """
        assert output_control_table_style in [
            "Comma",
            "Tab",
            "Fixed",
            "HTML",
            "XML",
            "CommaAndHTML",
            "TabAndHTML",
            "XMLAndHTML",
            "All",
        ]
        outputs = [
            {
                "key": "OutputControl:Table:Style".upper(),
                **{"Column_Separator": output_control_table_style},
            }
        ]

        for output in outputs:
            self._other_outputs.append(output)
        return self

    def add_umi_template_outputs(self, reporting_frequency="Hourly"):
        """Adds the necessary outputs in order to create an UMI template.

        Note:
            The reporting frequency must be 'Hourly' for archetypal to convert IDF
            models to UMI templates. Set to 'None' to use the reporting frequency of
            the Outputs object.
        """
        # list the outputs here
        variables = [
            "Air System Outdoor Air Minimum Flow Fraction",
            "Air System Total Cooling Energy",
            "Air System Total Heating Energy",
            "Heat Exchanger Latent Effectiveness",
            "Heat Exchanger Sensible Effectiveness",
            "Heat Exchanger Total Heating Rate",
            "Water Heater Heating Energy",
            "Zone Ideal Loads Zone Total Cooling Energy",
            "Zone Ideal Loads Zone Total Heating Energy",
            "Zone Thermostat Cooling Setpoint Temperature",
            "Zone Thermostat Heating Setpoint Temperature",
        ]
        for output in variables:
            self._output_variables.add((output, reporting_frequency or self.reporting_frequency))

        meters = [
            "Baseboard:EnergyTransfer",
            "Cooling:DistrictCooling",
            "Cooling:Electricity",
            "Cooling:Electricity",
            "Cooling:EnergyTransfer",
            "Cooling:Gas",
            "CoolingCoils:EnergyTransfer",
            "Fans:Electricity",
            "HeatRejection:Electricity",
            "HeatRejection:EnergyTransfer",
            "Heating:DistrictHeating",
            "Heating:Electricity",
            "Heating:EnergyTransfer",
            "Heating:Gas",
            "HeatingCoils:EnergyTransfer",
            "Pumps:Electricity",
            "Refrigeration:Electricity",
            "Refrigeration:EnergyTransfer",
            "WaterSystems:EnergyTransfer",
        ]
        for meter in meters:
            self._output_meters.add((meter, self.reporting_frequency))
        return self

    def add_dxf(self):
        outputs = [
            {
                "key": "Output:Surfaces:Drawing".upper(),
                **{"Report_Type": "DXF", "Report_Specifications_1": "ThickPolyline"},
            }
        ]
        for output in outputs:
            self._other_outputs.append(output)
        return self

    def add_umi_outputs(self):
        """Adds the necessary outputs in order to return the same energy profile
        as in UMI.
        """
        # list the outputs here
        outputs = [
            "Air System Total Heating Energy",
            "Air System Total Cooling Energy",
            "Zone Ideal Loads Zone Total Cooling Energy",
            "Zone Ideal Loads Zone Total Heating Energy",
            "Water Heater Heating Energy",
        ]
        for output in outputs:
            self._output_variables.add((output, self.reporting_frequency))
        return self

    def add_sensible_heat_gain_summary_components(self):
        hvac_input_sensible_air_heating = [
            "Zone Air Heat Balance System Air Transfer Rate",
            "Zone Air Heat Balance System Convective Heat Gain Rate",
        ]
        hvac_input_sensible_air_cooling = [
            "Zone Air Heat Balance System Air Transfer Rate",
            "Zone Air Heat Balance System Convective Heat Gain Rate",
        ]

        hvac_input_heated_surface_heating = [
            "Zone Radiant HVAC Heating Energy",
            "Zone Ventilated Slab Radiant Heating Energy",
        ]

        hvac_input_cooled_surface_cooling = [
            "Zone Radiant HVAC Cooling Energy",
            "Zone Ventilated Slab Radiant Cooling Energy",
        ]
        people_sensible_heat_addition = ["Zone People Sensible Heating Energy"]

        lights_sensible_heat_addition = ["Zone Lights Total Heating Energy"]

        equipment_sensible_heat_addition_and_equipment_sensible_heat_removal = [
            "Zone Electric Equipment Radiant Heating Energy",
            "Zone Gas Equipment Radiant Heating Energy",
            "Zone Steam Equipment Radiant Heating Energy",
            "Zone Hot Water Equipment Radiant Heating Energy",
            "Zone Other Equipment Radiant Heating Energy",
            "Zone Electric Equipment Convective Heating Energy",
            "Zone Gas Equipment Convective Heating Energy",
            "Zone Steam Equipment Convective Heating Energy",
            "Zone Hot Water Equipment Convective Heating Energy",
            "Zone Other Equipment Convective Heating Energy",
        ]

        window_heat_addition_and_window_heat_removal = ["Zone Windows Total Heat Gain Energy"]

        interzone_air_transfer_heat_addition_and_interzone_air_transfer_heat_removal = [
            "Zone Air Heat Balance Interzone Air Transfer Rate"
        ]

        infiltration_heat_addition_and_infiltration_heat_removal = ["Zone Air Heat Balance Outdoor Air Transfer Rate"]

        tuple(
            map(
                self._output_variables.add,
                zip(hvac_input_sensible_air_heating, (self.reporting_frequency,)),
            )
        )
        tuple(
            map(
                self._output_variables.add,
                zip(hvac_input_sensible_air_cooling, (self.reporting_frequency,)),
            )
        )
        tuple(
            map(
                self._output_variables.add,
                zip(hvac_input_heated_surface_heating, (self.reporting_frequency,)),
            )
        )
        tuple(
            map(
                self._output_variables.add,
                zip(hvac_input_cooled_surface_cooling, (self.reporting_frequency,)),
            )
        )
        tuple(
            map(
                self._output_variables.add,
                zip(people_sensible_heat_addition, (self.reporting_frequency,)),
            )
        )
        tuple(
            map(
                self._output_variables.add,
                zip(lights_sensible_heat_addition, (self.reporting_frequency,)),
            )
        )
        tuple(
            map(
                self._output_variables.add,
                zip(
                    equipment_sensible_heat_addition_and_equipment_sensible_heat_removal,
                    (self.reporting_frequency,),
                ),
            )
        )
        tuple(
            map(
                self._output_variables.add,
                zip(
                    window_heat_addition_and_window_heat_removal,
                    (self.reporting_frequency,),
                ),
            )
        )
        tuple(
            map(
                self._output_variables.add,
                zip(
                    interzone_air_transfer_heat_addition_and_interzone_air_transfer_heat_removal,
                    (self.reporting_frequency,),
                ),
            )
        )
        tuple(
            map(
                self._output_variables.add,
                zip(
                    infiltration_heat_addition_and_infiltration_heat_removal,
                    (self.reporting_frequency,),
                ),
            )
        )

        # The Opaque Surface Conduction and Other Heat Addition and Opaque Surface Conduction and Other Heat Removal
        # columns are also calculated on an timestep basis as the negative value of the other removal and gain columns
        # so that the total for the timestep sums to zero. These columns are derived strictly from the other columns.

    def add_end_use_balance_components(self):
        version = str(self.idf.file_version)
        for group in [
            EndUseBalance.get_keys("HVAC_MODE", version=version),
            EndUseBalance.get_keys("HVAC_INPUT_SENSIBLE", version=version),
            EndUseBalance.get_keys("HVAC_INPUT_HEATED_SURFACE", version=version),
            EndUseBalance.get_keys("HVAC_INPUT_COOLED_SURFACE", version=version),
            EndUseBalance.get_keys("LIGHTING", version=version),
            EndUseBalance.get_keys("EQUIP_GAINS", version=version),
            EndUseBalance.get_keys("PEOPLE_GAIN", version=version),
            EndUseBalance.get_keys("SOLAR_GAIN", version=version),
            EndUseBalance.get_keys("INFIL_GAIN", version=version),
            EndUseBalance.get_keys("INFIL_LOSS", version=version),
            EndUseBalance.get_keys("VENTILATION_LOSS", version=version),
            EndUseBalance.get_keys("VENTILATION_GAIN", version=version),
            EndUseBalance.get_keys("NAT_VENT_GAIN", version=version),
            EndUseBalance.get_keys("NAT_VENT_LOSS", version=version),
            EndUseBalance.get_keys("OPAQUE_ENERGY_FLOW", version=version),
            EndUseBalance.get_keys("OPAQUE_ENERGY_STORAGE", version=version),
            EndUseBalance.get_keys("WINDOW_LOSS", version=version),
            EndUseBalance.get_keys("WINDOW_GAIN", version=version),
            EndUseBalance.get_keys("HRV_LOSS", version=version),
            EndUseBalance.get_keys("HRV_GAIN", version=version),
            EndUseBalance.get_keys("AIR_SYSTEM", version=version),
        ]:
            for item in group:
                self._output_variables.add((item, "Hourly"))
        return self

    def add_load_balance_components(self):
        for group in [
            self.COOLING,
            self.HEATING,
            self.LIGHTING,
            self.ELECTRIC_EQUIP,
            self.GAS_EQUIP,
            self.HOT_WATER,
            self.PEOPLE_GAIN,
            self.SOLAR_GAIN,
            self.INFIL_GAIN,
            self.INFIL_LOSS,
            self.VENT_LOSS,
            self.VENT_GAIN,
            self.NAT_VENT_GAIN,
            self.NAT_VENT_LOSS,
            self.OPAQUE_ENERGY_FLOW,
            self.WINDOW_LOSS,
            self.WINDOW_GAIN,
        ]:
            for item in group:
                self._output_variables.add((item, "Hourly"))

    def add_profile_gas_elect_outputs(self):
        """Adds the following meters: Electricity:Facility, Gas:Facility,
        WaterSystems:Electricity, Heating:Electricity, Cooling:Electricity
        """
        # list the outputs here
        outputs = [
            "Electricity:Facility",
            "Gas:Facility",
            "WaterSystems:Electricity",
            "Heating:Electricity",
            "Cooling:Electricity",
        ]
        for output in outputs:
            self._output_meters.add((output, self.reporting_frequency))
        return self

    def add_hvac_energy_use(self):
        """Add outputs for HVAC energy use when detailed systems are assigned.

        This includes a range of outputs for different pieces of equipment,
        which is meant to catch all energy-consuming parts of a system.
        (eg. chillers, boilers, coils, humidifiers, fans, pumps).
        """
        outputs = [
            "Baseboard Electricity Energy",
            "Boiler NaturalGas Energy",
            "Chiller Electricity Energy",
            "Chiller Heater System Cooling Electricity Energy",
            "Chiller Heater System Heating Electricity Energy",
            "Cooling Coil Electricity Energy",
            "Cooling Tower Fan Electricity Energy",
            "District Cooling Chilled Water Energy",
            "District Heating Hot Water Energy",
            "Evaporative Cooler Electricity Energy",
            "Fan Electricity Energy",
            "Heating Coil Electricity Energy",
            "Heating Coil NaturalGas Energy",
            "Heating Coil Total Heating Energy",
            "Hot_Water_Loop_Central_Air_Source_Heat_Pump Electricity Consumption",
            "Humidifier Electricity Energy",
            "Pump Electricity Energy",
            "VRF Heat Pump Cooling Electricity Energy",
            "VRF Heat Pump Crankcase Heater Electricity Energy",
            "VRF Heat Pump Defrost Electricity Energy",
            "VRF Heat Pump Heating Electricity Energy",
            "Zone VRF Air Terminal Cooling Electricity Energy",
            "Zone VRF Air Terminal Heating Electricity Energy",
        ]
        for output in outputs:
            self._output_variables.add((output, self.reporting_frequency))

    def apply(self):
        """Applies the outputs to the idf model. Modifies the model by calling
        :meth:`~archetypal.idfclass.idf.IDF.newidfobject`"""
        for variable, reporting_frequency in self.output_variables:
            self.idf.newidfobject(
                key="Output:Variable".upper(),
                **{"Variable_Name": variable, "Reporting_Frequency": reporting_frequency},
            )
        for meter, reporting_frequency in self.output_meters:
            self.idf.newidfobject(
                key="Output:Meter".upper(),
                **{"Key_Name": meter, "Reporting_Frequency": reporting_frequency},
            )
        for output in self.other_outputs:
            key = output.pop("key", None)
            if key:
                output["key"] = key.upper()
            self.idf.newidfobject(**output)
        return self

    def __repr__(self):
        variables = "OutputVariables:\n {}".format("\n ".join(map(str, self.output_variables)))
        meters = "OutputMeters:\n {}".format("\n ".join(map(str, self.output_meters)))
        outputs = "Outputs:\n {}".format("\n ".join(a["key"] for a in self.other_outputs))
        return "\n".join([variables, meters, outputs])
