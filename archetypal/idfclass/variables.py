"""EnergyPlus variables module."""

import pandas as pd
from geomeppy.patches import EpBunch

from archetypal.energypandas import EnergyDataFrame
from archetypal.reportdata import ReportData


class Variable:
    def __init__(self, idf, variable: (dict or EpBunch)):
        """Initialize a Meter object"""
        self._idf = idf
        self._values = None
        if isinstance(variable, dict):
            self._key = variable.pop("key").upper()
            self._epobject = self._idf.anidfobject(key=self._key, **variable)
        elif isinstance(variable, EpBunch):
            self._key = variable.key
            self._epobject = variable
        else:
            raise TypeError()

    def __repr__(self):
        """returns the string representation of an EpBunch"""
        return self._epobject.__str__()

    def values(self, units=None, normalize=False, sort_values=False):
        """Returns the Variable as a time-series (:class:`EnergySeries`). Data is
        retrieved from the sql file. It is possible to convert the time-series to
        another unit, e.g.: "J" to "kWh".

        Args:
            units (str): Convert original values to another unit. The original unit
                is detected automatically and a dimensionality check is performed.
            normalize (bool): Normalize between 0 and 1.
            sort_values (bool): If True, values are sorted (default ascending=True)

        Returns:
            EnergySeries: The time-series object.
        """
        if self._values is None:
            if self._epobject not in self._idf.idfobjects[self._epobject.key]:
                self._idf.addidfobject(self._epobject)
                self._idf.simulate()
            report = ReportData.from_sqlite(
                sqlite_file=self._idf.sql_file,
                table_name=self._epobject.Variable_Name,
                environment_type=1 if self._idf.design_day else 3,
            )
            self._values = report
        return EnergyDataFrame.from_reportdata(
            self._values,
            name=self._epobject.Variable_Name,
            normalize=normalize,
            sort_values=sort_values,
            to_units=units,
        )


class VariableGroup:
    def __init__(self, idf, variables_dict: dict):
        self._idf = idf
        self._properties = {}

        for i, variable in variables_dict.items():
            variable_name = (
                variable["Variable_Name"].replace(":", "__").replace(" ", "_")
            )
            self._properties[variable_name] = Variable(idf, variable)
            setattr(self, variable_name, self._properties[variable_name])

    def __getitem__(self, variable_name):
        """Get item by key."""
        return self._properties[variable_name]


class Variables:
    """Class attributes representing available rdd variables"""

    def __init__(self, idf):
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
            "\;.*", ""
        )
        for key, group in variables.groupby("key"):
            variable_dict = group.T.to_dict()
            setattr(
                self,
                key.replace(":", "").replace(" ", "_"),
                VariableGroup(self._idf, variable_dict),
            )
