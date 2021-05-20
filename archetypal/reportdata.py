""""""

import functools
import time
from sqlite3 import OperationalError

import numpy as np
from pandas import DataFrame, read_sql_query, to_numeric
from path import Path

from archetypal.utils import log


class ReportData(DataFrame):
    """Handles Report Variable Data and Report Meter Data"""

    ARCHETYPE = "Archetype"
    REPORTDATAINDEX = "ReportDataIndex"
    TIMEINDEX = "TimeIndex"
    REPORTDATADICTIONARYINDEX = "ReportDataDictionaryIndex"
    VALUE = "Value"
    ISMETER = "IsMeter"
    TYPE = "Type"
    INDEXGROUP = "IndexGroup"
    TIMESTEPTYPE = "TimestepType"
    KEYVALUE = "KeyValue"
    NAME = "Name"
    REPORTINGFREQUENCY = "ReportingFrequency"
    SCHEDULENAME = "ScheduleName"
    UNITS = "Units"

    @classmethod
    def from_sql_dict(cls, sql_dict):
        """Create from dictionary."""
        report_data = sql_dict["ReportData"]
        report_data["ReportDataDictionaryIndex"] = to_numeric(
            report_data["ReportDataDictionaryIndex"]
        )

        report_data_dict = sql_dict["ReportDataDictionary"]

        return cls(
            report_data.reset_index().join(
                report_data_dict, on=["ReportDataDictionaryIndex"]
            )
        )

    @classmethod
    def from_sqlite(
        cls,
        sqlite_file,
        table_name,
        warmup_flag=0,
        environment_type=3,
        reporting_frequency=None,
    ):
        """Read an EnergyPlus eplusout.sql file.

        Args:
            sqlite_file (str): The path of the sqlite3 file.
            table_name (str, optional): Filter results by a specific table name.
            warmup_flag (int): 1 during warmup, 0 otherwise. Defaults to 0.
            environment_type (int): An enumeration of the environment type. (1 = Design
                Day, 2 = Design Run Period, 3 = Weather Run Period) See the various
                SizingPeriod objects and the RunPeriod object for details.
            reporting_frequency (str, optional): "HVAC System Timestep",
                "Zone Timestep", "Hourly", "Daily", "Monthly", "Run Period".

        Examples:
            >>> ReportData.from_sqlite("eplusout.sql",
            >>>     table_name="Air System Total Heating Energy",
            >>>     warmup_flag=0,
            >>>     environment_type=1,
            >>> )

        Returns:
            ReportData: a :class:`ReportData` which is a subclass of :class:`DataFrame`.
        """
        if not isinstance(sqlite_file, str):
            raise TypeError("Please provide a str, not a {}".format(type(sqlite_file)))
        file = Path(sqlite_file)
        if not file.exists():
            raise FileNotFoundError("Could not find sql file {}".format(file.relpath()))

        import sqlite3

        # create database connection with sqlite3
        with sqlite3.connect(sqlite_file) as conn:
            # empty dict to hold all DataFrames
            all_tables = {}
            # Iterate over all tables in the report_tables list
            sql_query = f"""
            SELECT rd.ReportDataIndex,
                   rd.TimeIndex,
                   rd.ReportDataDictionaryIndex,
                   red.ReportExtendedDataIndex,
                   t.Month,
                   t.Day,
                   t.Hour,
                   t.Minute,
                   t.Dst,
                   t.Interval,
                   t.IntervalType,
                   t.SimulationDays,
                   t.DayType,
                   t.EnvironmentPeriodIndex,
                   t.WarmupFlag,
                   p.EnvironmentType,
                   rd.Value,
                   rdd.IsMeter,
                   rdd.Type,
                   rdd.IndexGroup,
                   rdd.TimestepType,
                   rdd.KeyValue,
                   rdd.Name,
                   rdd.ReportingFrequency,
                   rdd.ScheduleName,
                   rdd.Units
            FROM ReportData As rd
                    INNER JOIN ReportDataDictionary As rdd ON rd.ReportDataDictionaryIndex = rdd.ReportDataDictionaryIndex
                    LEFT OUTER JOIN ReportExtendedData As red ON rd.ReportDataIndex = red.ReportDataIndex
                    INNER JOIN Time As t ON rd.TimeIndex = t.TimeIndex
                    JOIN EnvironmentPeriods as p ON t.EnvironmentPeriodIndex = p.EnvironmentPeriodIndex
            WHERE (IFNULL(t.WarmupFlag, 0) = @warmup_flag);
            """
            params = {"warmup_flag": warmup_flag}
            if table_name:
                conditions, table_name = cls.multiple_conditions(
                    "table_name", table_name, "Name"
                )
                sql_query = sql_query.replace(";", """ AND (%s);""" % conditions)
                params.update(table_name)
            if environment_type:
                conditions, env_name = cls.multiple_conditions(
                    "env_name", environment_type, "EnvironmentType"
                )
                sql_query = sql_query.replace(";", """ AND (%s);""" % conditions)
                params.update(env_name)
            if reporting_frequency:
                conditions, reporting_frequency = cls.multiple_conditions(
                    "reporting_frequency", reporting_frequency, "ReportingFrequency"
                )
                sql_query = sql_query.replace(";", """ AND (%s);""" % conditions)
                params.update(reporting_frequency)
            df = cls.execute(conn, sql_query, params)
            return cls(df)

    @staticmethod
    def multiple_conditions(basename, cond_names, var_name):
        if not isinstance(cond_names, (list, tuple)):
            cond_names = [cond_names]
        cond_names = set(cond_names)
        cond_names = {
            "%s_%s" % (basename, i): name for i, name in enumerate(cond_names)
        }
        conditions = " OR ".join(
            ["%s = @%s" % (var_name, cond_name) for cond_name in cond_names]
        )
        return conditions, cond_names

    @staticmethod
    def execute(conn, sql_query, params):
        try:
            # Try regular str read, could fail if wrong encoding
            conn.text_factory = str
            df = read_sql_query(sql_query, conn, params=params, coerce_float=True)
        except OperationalError as e:
            # Wring encoding found, the load bytes and decode object
            # columns only
            raise e
        return df

    @property
    def _constructor(self):
        return ReportData

    @property
    def df(self):
        """Returns the DataFrame of the ReportData"""
        return DataFrame(self)

    def filter_report_data(
        self,
        archetype=None,
        reportdataindex=None,
        timeindex=None,
        reportdatadictionaryindex=None,
        value=None,
        ismeter=None,
        type=None,
        indexgroup=None,
        timesteptype=None,
        keyvalue=None,
        name=None,
        reportingfrequency=None,
        schedulename=None,
        units=None,
        inplace=False,
    ):
        """filter RaportData using specific keywords. Each keywords can be a
        tuple of strings (str1, str2, str3) which will return the logical_or
        on the specific column.

        Args:
            archetype (str or tuple):
            reportdataindex (str or tuple):
            timeindex (str or tuple):
            reportdatadictionaryindex (str or tuple):
            value (str or tuple):
            ismeter (str or tuple):
            type (str or tuple):
            indexgroup (str or tuple):
            timesteptype (str or tuple):
            keyvalue (str or tuple):
            name (str or tuple):
            reportingfrequency (str or tuple):
            schedulename (str or tuple):
            units (str or tuple):
            inplace (str or tuple):

        Returns:
            pandas.DataFrame
        """
        start_time = time.time()
        c_n = []

        if archetype:
            c_1 = (
                conjunction(
                    *[self[self.ARCHETYPE] == archetype for archetype in archetype],
                    logical=np.logical_or,
                )
                if isinstance(archetype, tuple)
                else self[self.ARCHETYPE] == archetype
            )
            c_n.append(c_1)
        if reportdataindex:
            c_2 = (
                conjunction(
                    *[
                        self[self.REPORTDATAINDEX] == reportdataindex
                        for reportdataindex in reportdataindex
                    ],
                    logical=np.logical_or,
                )
                if isinstance(reportdataindex, tuple)
                else self[self.REPORTDATAINDEX] == reportdataindex
            )
            c_n.append(c_2)
        if timeindex:
            c_3 = (
                conjunction(
                    *[self[self.TIMEINDEX] == timeindex for timeindex in timeindex],
                    logical=np.logical_or,
                )
                if isinstance(timeindex, tuple)
                else self[self.TIMEINDEX] == timeindex
            )
            c_n.append(c_3)
        if reportdatadictionaryindex:
            c_4 = (
                conjunction(
                    *[
                        self[self.REPORTDATADICTIONARYINDEX]
                        == reportdatadictionaryindex
                        for reportdatadictionaryindex in reportdatadictionaryindex
                    ],
                    logical=np.logical_or,
                )
                if isinstance(reportdatadictionaryindex, tuple)
                else self[self.REPORTDATADICTIONARYINDEX] == reportdatadictionaryindex
            )
            c_n.append(c_4)
        if value:
            c_5 = (
                conjunction(
                    *[self[self.VALUE] == value for value in value],
                    logical=np.logical_or,
                )
                if isinstance(value, tuple)
                else self[self.VALUE] == value
            )
            c_n.append(c_5)
        if ismeter:
            c_6 = (
                conjunction(
                    *[self[self.ISMETER] == ismeter for ismeter in ismeter],
                    logical=np.logical_or,
                )
                if isinstance(ismeter, tuple)
                else self[self.ISMETER] == ismeter
            )
            c_n.append(c_6)
        if type:
            c_7 = (
                conjunction(
                    *[self[self.TYPE] == type for type in type], logical=np.logical_or
                )
                if isinstance(type, tuple)
                else self[self.TYPE] == type
            )
            c_n.append(c_7)
        if indexgroup:
            c_8 = (
                conjunction(
                    *[self[self.INDEXGROUP] == indexgroup for indexgroup in indexgroup],
                    logical=np.logical_or,
                )
                if isinstance(indexgroup, tuple)
                else self[self.INDEXGROUP] == indexgroup
            )
            c_n.append(c_8)
        if timesteptype:
            c_9 = (
                conjunction(
                    *[
                        self[self.TIMESTEPTYPE] == timesteptype
                        for timesteptype in timesteptype
                    ],
                    logical=np.logical_or,
                )
                if isinstance(timesteptype, tuple)
                else self[self.TIMESTEPTYPE] == timesteptype
            )
            c_n.append(c_9)
        if keyvalue:
            c_10 = (
                conjunction(
                    *[self[self.KEYVALUE] == keyvalue for keyvalue in keyvalue],
                    logical=np.logical_or,
                )
                if isinstance(keyvalue, tuple)
                else self[self.KEYVALUE] == keyvalue
            )
            c_n.append(c_10)
        if name:
            c_11 = (
                conjunction(
                    *[self[self.NAME] == name for name in name], logical=np.logical_or
                )
                if isinstance(name, tuple)
                else self[self.NAME] == name
            )
            c_n.append(c_11)
        if reportingfrequency:
            c_12 = (
                conjunction(
                    *[
                        self[self.REPORTINGFREQUENCY] == reportingfrequency
                        for reportingfrequency in reportingfrequency
                    ],
                    logical=np.logical_or,
                )
                if isinstance(reportingfrequency, tuple)
                else self[self.REPORTINGFREQUENCY] == reportingfrequency
            )
            c_n.append(c_12)
        if schedulename:
            c_13 = (
                conjunction(
                    *[
                        self[self.SCHEDULENAME] == schedulename
                        for schedulename in schedulename
                    ],
                    logical=np.logical_or,
                )
                if isinstance(schedulename, tuple)
                else self[self.SCHEDULENAME] == schedulename
            )
            c_n.append(c_13)
        if units:
            c_14 = (
                conjunction(
                    *[self[self.UNITS] == units for units in units],
                    logical=np.logical_or,
                )
                if isinstance(units, tuple)
                else self[self.UNITS] == units
            )
            c_n.append(c_14)

        filtered_df = self.loc[conjunction(*c_n, logical=np.logical_and)]
        log("filtered ReportData in {:,.2f} seconds".format(time.time() - start_time))
        if inplace:
            return filtered_df._update_inplace(filtered_df)
        else:
            return filtered_df.__finalize__(self)


def conjunction(*conditions, logical=np.logical_and):
    """Apply a logical function on n conditions."""
    return functools.reduce(logical, conditions)
