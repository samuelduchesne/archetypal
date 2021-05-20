"""EnergyPlus reports module."""

import os
from sqlite3.dbapi2 import OperationalError

import pandas as pd

from archetypal import settings
from archetypal.idfclass.util import hash_model
from archetypal.utils import log


def get_report(
    eplus_file, output_directory=None, output_report="sql", output_prefix=None, **kwargs
):
    """Returns the specified report format (html or sql)

    Args:
        eplus_file (str): path of the idf file
        output_directory (str, optional): path to the output folder. Will
            default to the settings.cache_folder.
        output_report: 'htm' or 'sql'
        output_prefix (str): Prefix name given to results files.
        **kwargs: keyword arguments to pass to hasher.

    Returns:
        dict: a dict of DataFrames
    """
    if not output_directory:
        output_directory = settings.cache_folder
    # Hash the idf file with any kwargs used in the function
    if output_prefix is None:
        output_prefix = hash_model(eplus_file)
    if output_report is None:
        return None
    elif "htm" in output_report.lower():
        # Get the html report
        fullpath_filename = output_directory / output_prefix + "tbl.htm"
        if fullpath_filename.exists():
            return get_html_report(fullpath_filename)
        else:
            raise FileNotFoundError(
                'File "{}" does not exist'.format(fullpath_filename)
            )

    elif "sql" == output_report.lower():
        # Get the sql report
        fullpath_filename = output_directory / output_prefix + "out.sql"
        if fullpath_filename.exists():
            return get_sqlite_report(fullpath_filename)
        else:
            raise FileNotFoundError(
                'File "{}" does not exist'.format(fullpath_filename)
            )
    else:
        return None


def get_html_report(report_fullpath):
    """Parses the html Summary Report for each tables into a dictionary of
    DataFrames

    Args:
        report_fullpath (str): full path to the report file

    Returns:
        dict: dict of {title : table <DataFrame>,...}
    """
    from eppy.results import readhtml  # the eppy module with functions to read the html

    with open(report_fullpath, "r", encoding="utf-8") as cache_file:
        filehandle = cache_file.read()  # get a file handle to the html file

        cached_tbl = readhtml.titletable(
            filehandle
        )  # get a file handle to the html file

        log('Retrieved response from cache file "{}"'.format(report_fullpath))
        return summary_reports_to_dataframes(cached_tbl)


def summary_reports_to_dataframes(reports_list):
    """Converts a list of [(title, table),...] to a dict of {title: table
    <DataFrame>}. Duplicate keys must have their own unique names in the output
    dict.

    Args:
        reports_list (list): a list of [(title, table),...]

    Returns:
        dict: a dict of {title: table <DataFrame>}
    """
    results_dict = {}
    for table in reports_list:
        key = str(table[0])
        if key in results_dict:  # Check if key is already exists in
            # dictionary and give it a new name
            key = key + "_"
        df = pd.DataFrame(table[1])
        df = df.rename(columns=df.iloc[0]).drop(df.index[0])
        results_dict[key] = df
    return results_dict


def get_sqlite_report(report_file, report_tables=None):
    """Connect to the EnergyPlus SQL output file and retrieves all tables

    Args:
        report_file (str): path of report file
        report_tables (list, optional): list of report table names to retreive.
            Defaults to settings.available_sqlite_tables

    Returns:
        dict: dict of DataFrames
    """
    # set list of report tables
    if not report_tables:
        report_tables = settings.available_sqlite_tables

    # if file exists, parse it with pandas' read_sql_query
    if os.path.isfile(report_file):
        import sqlite3

        import numpy as np

        # create database connection with sqlite3
        with sqlite3.connect(report_file) as conn:
            # empty dict to hold all DataFrames
            all_tables = {}
            # Iterate over all tables in the report_tables list
            for table in report_tables:
                try:
                    # Try regular str read, could fail if wrong encoding
                    conn.text_factory = str
                    df = pd.read_sql_query(
                        "select * from {};".format(table),
                        conn,
                        index_col=report_tables[table]["PrimaryKey"],
                        parse_dates=report_tables[table]["ParseDates"],
                        coerce_float=True,
                    )
                    all_tables[table] = df
                except OperationalError:
                    # Wring encoding found, the load bytes and ecode object
                    # columns only
                    conn.text_factory = bytes
                    df = pd.read_sql_query(
                        "select * from {};".format(table),
                        conn,
                        index_col=report_tables[table]["PrimaryKey"],
                        parse_dates=report_tables[table]["ParseDates"],
                        coerce_float=True,
                    )
                    str_df = df.select_dtypes([np.object])
                    str_df = str_df.stack().str.decode("8859").unstack()
                    for col in str_df:
                        df[col] = str_df[col]
                    all_tables[table] = df
            log(
                "SQL query parsed {} tables as DataFrames from {}".format(
                    len(all_tables), report_file
                )
            )
            return all_tables


def get_ideal_loads_summary(idf):
    """Get ideal loads report summary.

    Returns DataFrame with Cooling, Domestic Hot Water, Equipment, Heating and
    Lighting hourly time series.

    Returns:
        DataFrame: DataFrame of hourly time series.
    """
    res = {
        "SDL/Cooling": idf.meters.OutputMeter.Cooling__DistrictCooling.values("kWh"),
        "SDL/Domestic Hot Water": idf.meters.OutputMeter.WaterSystems__DistrictHeating.values(
            "kWh"
        ),
        "SDL/Equipment": idf.meters.OutputMeter.InteriorEquipment__Electricity.values(
            "kWh"
        ),
        "SDL/Heating": idf.meters.OutputMeter.Heating__DistrictHeating.values("kWh"),
        "SDL/Lighting": idf.meters.OutputMeter.InteriorLights__Electricity.values(
            "kWh"
        ),
    }
    return pd.DataFrame(res)
