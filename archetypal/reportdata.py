import functools
import logging as lg
import time
from sqlite3 import OperationalError

import numpy as np
import pandas as pd
from path import Path

from archetypal import log, EnergySeries


class ReportData(pd.DataFrame):
    """This class serves as a subclass of a pandas DataFrame allowing to add
    additional functionnality"""

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
        report_data = sql_dict["ReportData"]
        report_data["ReportDataDictionaryIndex"] = pd.to_numeric(
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
        table_name="WaterSystems:EnergyTransfer",
        warmup_flag=0,
        environment_type=3,
    ):
        """Reads an EnergyPlus eplusout.sql file and returns a :class:`ReportData`
        which is a subclass of :class:`DataFrame`.

        Args:
            environment_type (str): An enumeration of the environment type. (1 = Design
                Day, 2 = Design Run Period, 3 = Weather Run Period) See the various
                SizingPeriod objects and the RunPeriod object for details.
            sqlite_file (str):

        Returns:
            (ReportData): The ReportData object.
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
            df = cls.execute(conn, sql_query, params)
            return cls(df)

    @classmethod
    def multiple_conditions(cls, basename, cond_names, var_name):
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
            df = pd.read_sql_query(sql_query, conn, params=params, coerce_float=True)
        except OperationalError as e:
            # Wring encoding found, the load bytes and decode object
            # columns only
            raise e
        return df

    @property
    def _constructor(self):
        return ReportData

    @property
    def schedules(self):
        return self.sorted_values(key_value="Schedule Value")

    @property
    def df(self):
        """Returns the DataFrame of the ReportData"""
        return pd.DataFrame(self)

    def heating_load(
        self, normalize=False, sort=False, ascending=False, concurrent_sort=False
    ):
        """Returns the aggragated 'Heating:Electricity', 'Heating:Gas' and
        'Heating:DistrictHeating' of each archetype

        Args:
            normalize (bool): if True, returns a normalize Series.
                Normalization is done with respect to each Archetype
            sort (bool): if True, sorts the values. Usefull when a load
                duration curve is needed.
            ascending (bool): if True, sorts value in ascending order. If a
                Load Duration Curve is needed, use ascending=False.

        Returns:
            EnergySeries: the Value series of the Heating Load with a Archetype,
                TimeIndex as MultiIndex.
        """
        hl = self.filter_report_data(
            name=("Heating:Electricity", "Heating:Gas", "Heating:DistrictHeating")
        )
        freq = list(set(hl.ReportingFrequency))
        units = list(set(hl.Units))
        freq_map = dict(Hourly="H", Daily="D", Monthly="M")
        if len(units) > 1:
            raise MixedUnitsError()

        hl = hl.groupby(["Archetype", "TimeIndex"]).Value.sum()
        log("Returned Heating Load in units of {}".format(str(units)), lg.DEBUG)
        return EnergySeries(
            hl,
            frequency=freq_map[freq[0]],
            units=units[0],
            normalize=normalize,
            sort_values=sort,
            ascending=ascending,
            to_units="kWh",
            concurrent_sort=concurrent_sort,
        )

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

    def sorted_values(self, key_value=None, name=None, by="TimeIndex", ascending=True):
        """Returns sorted values by filtering key_value and name

        Args:
            self: The ReporatData DataFrame
            key_value (str): key_value column filter
            name (str): name column filter
            by (str): sorting by this column name
            ascending (bool):

        Returns:
            ReportData
        """
        if key_value and name:
            return (
                self.filter_report_data(name=name, keyvalue=key_value)
                .sort_values(by=by, ascending=ascending)
                .reset_index(drop=True)
                .rename_axis("TimeStep")
                .set_index(["Archetype"], append=True)
                .swaplevel(i=-2, j=-1, axis=0)
            )
        else:
            return self.sort_values(by=by, inplace=False)


def conjunction(*conditions, logical=np.logical_and):
    """Applies a logical function on n conditons"""
    return functools.reduce(logical, conditions)


def or_conjunction(*conditions):
    return functools.reduce(np.logical_or, conditions)
