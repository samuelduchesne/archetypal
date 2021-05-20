class Outputs:
    """Handles preparation of EnergyPlus outputs. Different instance methods
    allow to chain methods together and to add predefined bundles of outputs in
    one go.

    Examples:
        >>> from archetypal import IDF
        >>> idf = IDF(prep_outputs=False)  # True be default
        >>> idf.outputs.add_output_control().add_umi_ouputs(
        >>> ).add_profile_gas_elect_ouputs().apply()
    """

    def __init__(self, idf):
        """Initialize an outputs object.

        Args:
            idf (IDF): the IDF object for wich this outputs object is created.
        """
        self.idf = idf
        self._outputs = []

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
        if isinstance(outputs, list):
            self._outputs.extend(outputs)
        return self

    def add_basics(self):
        """Adds the summary report and the sql file to the idf outputs"""
        return (
            self.add_summary_report()
            .add_output_control()
            .add_sql()
            .add_schedules()
            .add_meter_variables()
        )

    def add_schedules(self):
        """Adds Schedules object"""
        outputs = [{"key": "Output:Schedules".upper(), **dict(Key_Field="Hourly")}]

        self._outputs.extend(outputs)
        return self

    def add_meter_variables(self, format="IDF"):
        """Generate .mdd file at end of simulation. This file (from the
        Output:VariableDictionary, regular; and Output:VariableDictionary,
        IDF; commands) shows all the report meters along with their “availability”
        for the current input file. A user must first run the simulation (at least
        semi-successfully) before the available output meters are known. This output
        file is available in two flavors: regular (listed as they are in the Input
        Output Reference) and IDF (ready to be copied and pasted into your Input File).

        Args:
            format (str): Choices are "IDF" and "regul

        Returns:
            Outputs: self
        """
        outputs = [dict(key="Output:VariableDictionary".upper(), Key_Field=format)]
        self._outputs.extend(outputs)
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
                **dict(Report_1_Name=summary),
            }
        ]

        self._outputs.extend(outputs)
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
        output = {"key": "Output:SQLite".upper(), **dict(Option_Type=sql_output_style)}

        self._outputs.extend([output])
        return self

    def add_output_control(self, output_control_table_style="CommaAndHTML"):
        """Sets the `OutputControl:Table:Style` object.

        Args:
            output_control_table_style (str): Choices are: Comma, Tab, Fixed,
                HTML, XML, CommaAndHTML, TabAndHTML, XMLAndHTML, All
        Returns:
            Outputs: self
        """
        outputs = [
            {
                "key": "OutputControl:Table:Style".upper(),
                **dict(Column_Separator=output_control_table_style),
            }
        ]

        self._outputs.extend(outputs)
        return self

    def add_umi_template_outputs(self):
        """Adds the necessary outputs in order to create an UMI template."""
        # list the outputs here
        outputs = [
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Air System Total Heating Energy",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Air System Total Cooling Energy",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Zone Ideal Loads Zone Total Cooling Energy",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Zone Ideal Loads Zone Total Heating Energy",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Zone Thermostat Heating Setpoint Temperature",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Zone Thermostat Cooling Setpoint Temperature",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Heat Exchanger Total Heating Rate",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Heat Exchanger Sensible Effectiveness",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Heat Exchanger Latent Effectiveness",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Water Heater Heating Energy",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Air System Outdoor Air Minimum Flow Fraction",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "OUTPUT:METER",
                **dict(
                    Key_Name="HeatRejection:EnergyTransfer",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Heating:EnergyTransfer", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Cooling:EnergyTransfer", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(
                    Key_Name="Heating:DistrictHeating", Reporting_Frequency="hourly"
                ),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Heating:Electricity", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Heating:Gas", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(
                    Key_Name="Cooling:DistrictCooling", Reporting_Frequency="hourly"
                ),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Cooling:Electricity", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Cooling:Electricity", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Cooling:Gas", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(
                    Key_Name="WaterSystems:EnergyTransfer", Reporting_Frequency="hourly"
                ),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Fans:Electricity", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Pumps:Electricity", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(
                    Key_Name="Refrigeration:Electricity", Reporting_Frequency="hourly"
                ),
            },
            {
                "key": "OUTPUT:METER",
                **dict(
                    Key_Name="Refrigeration:EnergyTransfer",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Meter".upper(),
                **dict(
                    Key_Name="HeatingCoils:EnergyTransfer",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Meter".upper(),
                **dict(
                    Key_Name="Baseboard:EnergyTransfer",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Meter".upper(),
                **dict(
                    Key_Name="HeatRejection:Electricity",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Meter".upper(),
                **dict(
                    Key_Name="CoolingCoils:EnergyTransfer",
                    Reporting_Frequency="hourly",
                ),
            },
        ]

        self._outputs.extend(outputs)
        return self

    def add_dxf(self):
        outputs = [
            {
                "key": "Output:Surfaces:Drawing".upper(),
                **dict(Report_Type="DXF", Report_Specifications_1="ThickPolyline"),
            }
        ]
        self._outputs.extend(outputs)
        return self

    def add_umi_ouputs(self):
        """Adds the necessary outputs in order to return the same energy profile
        as in UMI.
        """
        # list the outputs here
        outputs = [
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Air System Total Heating Energy",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Air System Total Cooling Energy",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Zone Ideal Loads Zone Total Cooling Energy",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Zone Ideal Loads Zone Total Heating Energy",
                    Reporting_Frequency="hourly",
                ),
            },
            {
                "key": "Output:Variable".upper(),
                **dict(
                    Variable_Name="Water Heater Heating Energy",
                    Reporting_Frequency="hourly",
                ),
            },
        ]

        self._outputs.extend(outputs)
        return self

    def add_profile_gas_elect_ouputs(self):
        """Adds the following meters: Electricity:Facility, Gas:Facility,
        WaterSystems:Electricity, Heating:Electricity, Cooling:Electricity
        """
        # list the outputs here
        outputs = [
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Electricity:Facility", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Gas:Facility", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(
                    Key_Name="WaterSystems:Electricity", Reporting_Frequency="hourly"
                ),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Heating:Electricity", Reporting_Frequency="hourly"),
            },
            {
                "key": "OUTPUT:METER",
                **dict(Key_Name="Cooling:Electricity", Reporting_Frequency="hourly"),
            },
        ]
        self._outputs.extend(outputs)
        return self

    def apply(self):
        """Applies the outputs to the idf model. Modifies the model by calling
        :meth:`~archetypal.idfclass.idf.IDF.newidfobject`"""
        for output in self._outputs:
            self.idf.newidfobject(**output)
        return self
