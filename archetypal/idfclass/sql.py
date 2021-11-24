"""sql module."""

from datetime import timedelta
from sqlite3 import connect
from typing import List, Literal, Sequence, Union

import pandas as pd
from energy_pandas import EnergyDataFrame
from pandas import to_datetime
from path import Path

_REPORTING_FREQUENCIES = Literal[
    "HVAC System Timestep",
    "Zone Timestep",
    "Hourly",
    "Daily",
    "Monthly",
    "Run Period",
]


class Sql:
    _reporting_frequencies = (
        "HVAC System Timestep",
        "Zone Timestep",
        "Hourly",
        "Daily",
        "Monthly",
        "Run Period",
    )

    def __init__(self, file_path):
        """Initialize SQLiteResult"""
        assert Path(file_path).exists(), "No file was found at {}".format(file_path)
        self._file_path = file_path

        # values to be computed as soon as they are requested
        self._available_outputs = None
        self._zone_info = None
        self._environment_periods = None

    @property
    def file_path(self):
        """Get the path to the .sql file."""
        return self._file_path

    @property
    def available_outputs(self):
        """Get a list of strings for available timeseries outputs that can be requested.

        Any of these outputs when input to data_collections_by_output_name will
        yield a result with data collections.
        """
        if not self._available_outputs:
            self._available_outputs = self._extract_available_outputs()
        return self._available_outputs

    @property
    def zone_info(self):
        """Get a list of strings for available timeseries outputs that can be requested.

        Any of these outputs when input to data_collections_by_output_name will
        yield a result with data collections.
        """
        if not self._zone_info:
            self._zone_info = self._extract_zone_info()
        return self._zone_info

    @property
    def environment_periods(self):
        """Get a list of environment periods for the simulation run periods.

        EnvironmentType: An enumeration of the environment type. (1 = Design Day,
            2 = Design Run Period, 3 = Weather Run Period).
        """
        if not self._environment_periods:
            self._environment_periods = self._extract_environment_periods()
        return self._environment_periods

    def _extract_available_outputs(self) -> List:
        """Extract the list of all available outputs from the SQLite file."""
        with connect(self.file_path) as conn:
            cols = "ReportDataDictionaryIndex, IndexGroup, KeyValue, Name, Units, ReportingFrequency"
            query = f"SELECT {cols} FROM ReportDataDictionary"
            header_rows = pd.read_sql(query, conn)
        return list(sorted(set(header_rows["Name"])))

    def collect_output_by_name(
        self,
        variable_or_meter: Union[str, Sequence],
        reporting_frequency: Union[_REPORTING_FREQUENCIES] = "Hourly",
    ) -> EnergyDataFrame:
        """Get an EnergyDataFrame for a specified meter or variable.

        Args:
            variable_or_meter (str or list): The name of an EnergyPlus output meter or
                variable to be retrieved from the SQLite result file. This can also be an
                array of output names for which all data collections should be retrieved.
            reporting_frequency (str):

        Returns:
            EnergyDataFrame: An EnergyDataFrame with the variable_or_meter as columns.
        """
        reporting_frequency = reporting_frequency.title()
        assert (
            reporting_frequency in Sql._reporting_frequencies
        ), f"reporting_frequency is not one of {Sql._reporting_frequencies}"
        with connect(self.file_path) as conn:
            cols = "ReportDataDictionaryIndex, IndexGroup, KeyValue, Name, Units, ReportingFrequency"
            if isinstance(variable_or_meter, str):  # assume it's a single output
                query = f"""
                        SELECT {cols} 
                        FROM ReportDataDictionary 
                        WHERE Name=@output_name 
                        AND ReportingFrequency=@reporting_frequency;
                        """
                header_rows = pd.read_sql(
                    query,
                    conn,
                    params={
                        "output_name": variable_or_meter,
                        "reporting_frequency": reporting_frequency,
                    },
                )
            elif len(variable_or_meter) == 1:  # assume it's a list
                query = f"""
                        SELECT {cols} 
                        FROM ReportDataDictionary 
                        WHERE Name=@output_name 
                        AND ReportingFrequency=@reporting_frequency;
                        """
                header_rows = pd.read_sql(
                    query,
                    conn,
                    params={
                        "output_name": variable_or_meter[0],
                        "reporting_frequency": reporting_frequency,
                    },
                )
            else:  # assume it is a list of outputs
                query = f"""
                        SELECT {cols} 
                        FROM ReportDataDictionary 
                        WHERE Name IN {tuple(variable_or_meter)}
                        AND ReportingFrequency=@reporting_frequency;"""
                header_rows = pd.read_sql(
                    query,
                    conn,
                    params={
                        "reporting_frequency": reporting_frequency,
                    },
                )
            # if nothing was found, return an empty DataFrame
            if len(header_rows) == 0:
                return EnergyDataFrame([])
            else:
                header_rows.set_index("ReportDataDictionaryIndex", inplace=True)

            # extract all data of the relevant type from ReportData
            rel_indices = tuple(header_rows.index.to_list())
            if len(rel_indices) == 1:
                data = pd.read_sql(
                    """SELECT rd.Value,
                              rd.ReportDataDictionaryIndex, 
                              t.Month,
                              t.Day,
                              t.Hour,
                              t.Minute,
                              t.Interval
                    FROM ReportData as rd 
                            LEFT JOIN Time As t ON rd.TimeIndex = t.TimeIndex 
                    WHERE ReportDataDictionaryIndex=? ORDER BY t.TimeIndex 
                    AND (IFNULL(t.WarmupFlag, 0) = @warmup_flag);""",
                    conn,
                    params=[rel_indices[0], 0],
                )
            else:
                data = pd.read_sql(
                    f"""SELECT rd.Value,
                              rd.ReportDataDictionaryIndex,
                              t.Month,
                              t.Day,
                              t.Hour,
                              t.Minute,
                              t.Interval
                    FROM ReportData as rd
                            LEFT JOIN Time As t ON rd.TimeIndex = t.TimeIndex
                    WHERE ReportDataDictionaryIndex IN {tuple(rel_indices)}
                    AND (IFNULL(t.WarmupFlag, 0) = @warmup_flag)
                    ORDER BY rd.ReportDataDictionaryIndex, t.TimeIndex;""",
                    conn,
                    params={"warmup_flag": 0},
                )
            # Join the header_rows on ReportDataDictionaryIndex
            data = data.join(
                header_rows[["IndexGroup", "KeyValue", "Name"]],
                on="ReportDataDictionaryIndex",
            )

            # Pivot the data so that ["Name", "KeyValue"] becomes the column MultiIndex.
            data = data.pivot(
                index=["Month", "Day", "Hour", "Minute", "Interval"],
                columns=["IndexGroup", "KeyValue", "Name"],
                values="Value",
            )

            # reset the index to prepare the DatetimeIndex
            date_time_names = data.index.names
            data.reset_index(inplace=True)
            index = to_datetime(
                {
                    "year": 2018,
                    "month": data.Month,
                    "day": data.Day,
                    "hour": data.Hour,
                    "minute": data.Minute,
                }
            )
            # Adjust timeindex by timedelta
            index -= data["Interval"].apply(lambda x: timedelta(minutes=x))
            index = pd.DatetimeIndex(index, freq="infer")
            # get data
            data = data.drop(columns=date_time_names)
            data.index = index

            # Create the EnergyDataFrame and set the units using dict
            data = EnergyDataFrame(data)
            data.units = header_rows.set_index("Name")["Units"].to_dict()

        return data

    def _extract_zone_info(self):
        """Extract the Zones table from the SQLite file."""
        with connect(self.file_path) as conn:
            query = "SELECT * from Zones"
            df = pd.read_sql(query, conn).set_index("ZoneIndex")
        return df

    def _extract_environment_periods(self):
        with connect(self.file_path) as conn:
            query = "SELECT * from EnvironmentPeriods"
            df = pd.read_sql(query, conn).set_index("EnvironmentPeriodIndex")
        return df
