"""EnergyPlus variables module."""
import logging
from typing import Iterable

import pandas as pd
from energy_pandas import EnergyDataFrame
from geomeppy.patches import EpBunch

from archetypal.idfclass.extensions import bunch2db
from archetypal.reportdata import ReportData
from archetypal.utils import log


class Variable:
    """Variable class.

    Holds values for a specific Variable.
    """

    def __init__(self, idf, variable: (dict or EpBunch)):
        """Initialize a Meter object."""
        self._idf = idf
        if isinstance(variable, dict):
            self._key = variable.pop("key").upper()
            self._epobject = self._idf.anidfobject(key=self._key, **variable)
        elif isinstance(variable, EpBunch):
            self._key = variable.key
            self._epobject = variable
        else:
            raise TypeError()

    def __repr__(self):
        """Return a representation of self."""
        return self._epobject.__str__()

    def values(
        self,
        units=None,
        reporting_frequency="Hourly",
        environment_type=None,
        normalize=False,
        sort_values=False,
    ):
        """Return the Variable as a time-series (:class:`EnergySeries`).

        Can return an :class:`EnergyDataFrame` with multiple columns.

        Specify the reporting_frequency such as "Hourly" or "Monthly".
        It is possible to convert the time-series to another unit, e.g.: "J" to "kWh".

        Data is retrieved from the sql file.

        Args:
            units (str): Convert original values to another unit. The original unit
                is detected automatically and a dimensionality check is performed.
            reporting_frequency (str): Timestep, Hourly, Daily, Monthly,
                RunPeriod, Environment, Annual or Detailed. Default "Hourly".
            environment_type (int): The environment type (1 = Design Day, 2 = Design
                Run Period, 3 = Weather Run Period).
            normalize (bool): Normalize between 0 and 1.
            sort_values (bool): If True, values are sorted (default ascending=True).

        Returns:
            EnergyDataFrame: The time-series object.
        """
        self._epobject.Reporting_Frequency = reporting_frequency.lower()
        if self._epobject not in self._idf.idfobjects[self._epobject.key]:
            self._idf.addidfobject(self._epobject)
            self._idf.simulate()
        if environment_type is None:
            if self._idf.design_day:
                environment_type = 1
            elif self._idf.annual:
                environment_type = 3
            else:
                # the environment_type is specified by the simulationcontrol.
                try:
                    for ctrl in self._idf.idfobjects["SIMULATIONCONTROL"]:
                        if (
                            ctrl.Run_Simulation_for_Weather_File_Run_Periods.lower()
                            == "yes"
                        ):
                            environment_type = 3
                        else:
                            environment_type = 1
                except (KeyError, IndexError, AttributeError):
                    reporting_frequency = 3
        report = ReportData.from_sqlite(
            sqlite_file=self._idf.sql_file,
            table_name=self._epobject.Variable_Name,
            environment_type=environment_type,
            reporting_frequency=bunch2db[reporting_frequency],
        )
        if report.empty:
            log(
                f"The variable is empty for environment_type `{environment_type}`. "
                f"Try another environment_type (1, 2 or 3) or specify IDF.annual=True "
                f"and rerun the simulation.",
                level=logging.WARNING,
            )
        return EnergyDataFrame.from_reportdata(
            report,
            name=self._epobject.Variable_Name,
            normalize=normalize,
            sort_values=sort_values,
            to_units=units,
        )


class VariableGroup:
    """A class for sub variable groups (Output:Variable)."""

    def __init__(self, idf, variables_dict: dict):
        """Initialize VariableGroup."""
        self._idf = idf
        self._properties = {}

        for i, variable in variables_dict.items():
            variable_name = self.normalize_output_name(variable["Variable_Name"])
            self._properties[variable_name] = Variable(idf, variable)
            setattr(self, variable_name, self._properties[variable_name])

    def normalize_output_name(self, variable):
        return variable.replace(":", "__").replace(" ", "_")

    def __getitem__(self, variable_name):
        """Get item by key."""
        return self._properties[variable_name]

    def collect_by_output_name(
        self,
        output_name,
        reporting_frequency="Hourly",
        units=None,
        environment_type=None,
        normalize=False,
        sort_values=False,
    ):
        """

        Args:
            output_name: The name of an EnergyPlus output to be retrieved from the SQLite result file. This can also
                be an array of output names for which all data collections should be retrieved.

        Returns:

        """
        if isinstance(output_name, str):  # assume one output
            output_name = self.normalize_output_name(output_name)
            try:
                out = self[output_name].values(
                    units=units,
                    reporting_frequency=reporting_frequency,
                    environment_type=environment_type,
                    normalize=normalize,
                    sort_values=sort_values,
                )
            except KeyError:
                log(f"{output_name} not available as an output for this model.")
                out = EnergyDataFrame([])
            return out
        elif isinstance(output_name, Iterable):
            output_values = {}
            for an_output_name in output_name:
                try:
                    out = self[self.normalize_output_name(an_output_name)].values(
                        units=units,
                        reporting_frequency=reporting_frequency,
                        environment_type=environment_type,
                        normalize=normalize,
                        sort_values=sort_values,
                    )
                except KeyError:
                    log(f"{output_name} not available as an output for this model.")
                else:
                    output_values[an_output_name] = out
            if not output_values:
                return EnergyDataFrame([])
            else:
                return pd.concat(
                    output_values, axis=1, names=["OutputVariable", "Key_Name"]
                )


class Variables:
    """Lists available variables in the IDF model.

    Once simulated at least once, he IDF.variables attribute is populated with
    variable categories  and each category is populated with all the available
    variables.

    Example:
        For example, to retrieve the "Zone Operative Temperature" variable, simply call

        .. code-block::

            >>> from archetypal import IDF
            >>> idf = IDF()  # load an actual idf file here
            >>> idf.variables.OutputVariable.Zone_Operative_Temperature.values()

    Hint:
        Available meters are read from the .mdd file
    """

    OutputVariable = VariableGroup  # Placeholder for variables

    def __init__(self, idf):
        """Initialize MeterGroup."""
        self._idf = idf

        rdd, *_ = self._idf.simulation_dir.files("*.rdd")

        if not rdd:
            raise FileNotFoundError
        variables = pd.read_csv(
            rdd,
            skiprows=2,
            names=["key", "Key_Value", "Variable_Name", "Reporting_Frequency"],
        )
        variables.Reporting_Frequency = variables.Reporting_Frequency.str.replace(
            r"\;.*", ""
        )
        for key, group in variables.groupby("key"):
            variable_dict = group.T.to_dict()
            setattr(
                self,
                key.replace(":", "").replace(" ", "_"),
                VariableGroup(self._idf, variable_dict),
            )
