"""EnergyPlus meters module."""

import inspect
import logging

import pandas as pd
from energy_pandas import EnergySeries
from eppy.bunch_subclass import BadEPFieldError
from geomeppy.patches import EpBunch
from tabulate import tabulate

from archetypal.idfclass.extensions import bunch2db
from archetypal.reportdata import ReportData


class Meter:
    """Meter class.

    Holds values for a specific Meter.
    """

    def __init__(self, idf, meter: (dict or EpBunch)):
        """Initialize a Meter object."""
        self._idf = idf
        if isinstance(meter, dict):
            self._key = meter.pop("key").upper()
            self._epobject = self._idf.anidfobject(key=self._key, **meter)
        elif isinstance(meter, EpBunch):
            self._key = meter.key
            self._epobject = meter
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
        ascending=False,
        agg_func="sum",
    ):
        """Return the Meter as a time-series (:class:`EnergySeries`).

        Data is retrieved from the sql file. It is possible to convert the
        time-series to another unit, e.g.: "J" to "kWh".

        Args:
            units (str): Convert original values to another unit. The original unit
                is detected automatically and a dimensionality check is performed.
            reporting_frequency (str): Timestep, Hourly, Daily, Monthly,
                RunPeriod, Environment, Annual or Detailed. Default "Hourly".
            environment_type (int): The environment type (1 = Design Day, 2 = Design
                Run Period, 3 = Weather Run Period).
            normalize (bool): Normalize between 0 and 1.
            sort_values (bool): If True, values are sorted (default ascending=True)
            ascending (bool): If True and `sort_values` is True, values are sorted in
                ascending order.
            agg_func: #Todo: Document

        Returns:
            EnergySeries: The time-series object.
        """
        self._epobject.Reporting_Frequency = reporting_frequency.lower()
        if self._epobject not in self._idf.idfobjects[self._epobject.key]:
            self._idf.addidfobject(self._epobject)
            self._idf.simulate()
        try:
            key_name = self._epobject.Key_Name
        except BadEPFieldError:
            key_name = self._epobject.Name  # Backwards compatibility
        if environment_type is None:
            if self._idf.design_day:
                environment_type = 1
            elif self._idf.annual:
                environment_type = 3
            else:
                # the environment_type is specified by the simulationcontrol.
                try:
                    for ctrl in self._idf.idfobjects["SIMULATIONCONTROL"]:
                        if ctrl.Run_Simulation_for_Weather_File_Run_Periods.lower() == "yes":
                            environment_type = 3
                        else:
                            environment_type = 1
                except (KeyError, IndexError, AttributeError):
                    reporting_frequency = 3
        report = ReportData.from_sqlite(
            sqlite_file=self._idf.sql_file,
            table_name=key_name,
            environment_type=environment_type,
            reporting_frequency=bunch2db[reporting_frequency],
        )
        if report.empty:
            logging.error(
                f"The variable is empty for environment_type `{environment_type}`. "
                f"Try another environment_type (1, 2 or 3) or specify IDF.annual=True "
                f"and rerun the simulation."
            )
        return EnergySeries.from_reportdata(
            report,
            to_units=units,
            name=key_name,
            normalize=normalize,
            sort_values=sort_values,
            ascending=ascending,
            agg_func=agg_func,
        )


class MeterGroup:
    """A class for sub meter groups (Output:Meter vs Output:Meter:Cumulative)."""

    def __init__(self, idf, meters_dict: dict):
        """Initialize MeterGroup."""
        self._idf = idf
        self._properties = {}

        for i, meter in meters_dict.items():
            meter_name = meter["Key_Name"].replace(":", "__").replace(" ", "_")
            self._properties[meter_name] = Meter(idf, meter)
            setattr(self, meter_name, self._properties[meter_name])

    def __getitem__(self, meter_name):
        """Get item by key."""
        return self._properties[meter_name]

    def __repr__(self):
        """Return a representation of all available meters."""
        # getmembers() returns all the
        # members of an object
        members = []
        for i in inspect.getmembers(self):

            # to remove private and protected
            # functions
            if not i[0].startswith("_"):

                # To remove other methods that
                # do not start with an underscore
                if not inspect.ismethod(i[1]):
                    members.append(i)

        return f"{len(members)} available meters"


class Meters:
    """Lists available meters in the IDF model.

    Once simulated at least once, the IDF.meters attribute is populated with meters
    categories ("Output:Meter" or "Output:Meter:Cumulative") and each category is
    populated with all the available meters.

    Example:
        For example, to retrieve the WaterSystems:MainsWater meter, simply call

        .. code-block::

            >>> from archetypal import IDF
            >>> idf = IDF()  # load an actual idf file here
            >>> idf.meters.OutputMeter.WaterSystems__MainsWater.values()

    Hint:
        Available meters are read from the .mdd file
    """

    OutputMeter = MeterGroup  # placeholder for OutputMeters

    def __init__(self, idf):
        """Initialize Meter."""
        self._idf = idf

        try:
            mdd, *_ = self._idf.simulation_dir.files("*.mdd")
        except ValueError:
            mdd, *_ = self._idf.simulate().simulation_dir.files("*.mdd")
        if not mdd:
            raise FileNotFoundError
        meters = pd.read_csv(
            mdd, skiprows=2, names=["key", "Key_Name", "Reporting_Frequency"]
        )
        meters.Reporting_Frequency = meters.Reporting_Frequency.str.replace(r"\;.*", "")
        for key, group in meters.groupby("key"):
            meters_dict = group.T.to_dict()
            setattr(
                self,
                key.replace(":", "").replace(" ", "_"),
                MeterGroup(self._idf, meters_dict),
            )

    def __repr__(self):
        """Tabulate all available meters."""
        # getmembers() returns all the
        # members of an object
        members = []
        for i in inspect.getmembers(self):

            # to remove private and protected
            # functions
            if not i[0].startswith("_"):

                # To remove other methods that
                # do not start with an underscore
                if not inspect.ismethod(i[1]):
                    members.append(i)
        return tabulate(members, headers=("Available subgroups", "Preview"))
