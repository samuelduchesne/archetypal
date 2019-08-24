################################################################################
# Module: utils.py
# Description: Utility functions for configuration, logging
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################
# OSMnx
#
# Copyright (c) 2019 Geoff Boeing https://geoffboeing.com/
#
# Part of the following code is a derivative work of the code from the OSMnx
# project, which is licensed MIT License. This code therefore is also
# licensed under the terms of the The MIT License (MIT).
################################################################################

import datetime as dt
import json
import logging as lg
import os
import re
import sys
import time
import unicodedata
import warnings
from collections import OrderedDict
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from archetypal import settings
from pandas.io.json import json_normalize
from path import Path


def config(
    data_folder=settings.data_folder,
    logs_folder=settings.logs_folder,
    imgs_folder=settings.imgs_folder,
    cache_folder=settings.cache_folder,
    use_cache=settings.use_cache,
    log_file=settings.log_file,
    log_console=settings.log_console,
    log_level=settings.log_level,
    log_name=settings.log_name,
    log_filename=settings.log_filename,
    useful_idf_objects=settings.useful_idf_objects,
    umitemplate=settings.umitemplate,
    trnsys_default_folder=settings.trnsys_default_folder,
    default_weight_factor="area",
):
    """Configurations

    Args:
        data_folder (str): where to save and load data files
        logs_folder (str): where to write the log files
        imgs_folder (str): where to save figures
        cache_folder (str): where to save the simluation results
        use_cache (bool): if True, use a local cache to save/retrieve many of
            archetypal outputs such as EnergyPlus simulation results. This can
            save a lot of time by not calling the simulation and dataportal APIs
            repetitively for the same requests.
        log_file (bool): if true, save log output to a log file in logs_folder
        log_console (bool): if true, print log output to the console
        log_level (int): one of the logger.level constants
        log_name (str): name of the logger
        log_filename (str): name of the log file
        useful_idf_objects (list): a list of useful idf objects
        umitemplate (str): where the umitemplate is located
        trnsys_default_folder (str): root folder of TRNSYS install

    Returns:
        None
    """
    # set each global variable to the passed-in parameter value
    settings.use_cache = use_cache
    settings.cache_folder = Path(cache_folder).makedirs_p()
    settings.data_folder = Path(data_folder).makedirs_p()
    settings.imgs_folder = Path(imgs_folder).makedirs_p()
    settings.logs_folder = Path(logs_folder).makedirs_p()
    settings.log_console = log_console
    settings.log_file = log_file
    settings.log_level = log_level
    settings.log_name = log_name
    settings.log_filename = log_filename
    settings.useful_idf_objects = useful_idf_objects
    settings.umitemplate = umitemplate
    settings.trnsys_default_folder = validate_trnsys_folder(trnsys_default_folder)
    settings.zone_weight.set_weigth_attr(default_weight_factor)

    # if logging is turned on, log that we are configured
    if settings.log_file or settings.log_console:
        log("Configured archetypal")


def validate_trnsys_folder(trnsys_default_folder):
    """
    Args:
        trnsys_default_folder:
    """
    if sys.platform == "win32":
        if os.path.isdir(trnsys_default_folder):
            return trnsys_default_folder
        else:
            raise ValueError(
                "The provided TRNSYS path does not exist. Path={"
                ". Please set the TRNSYS path with the "
                '"--trnsys-default-folder" option}'.format(trnsys_default_folder)
            )
    else:
        return trnsys_default_folder


def log(
    message, level=None, name=None, filename=None, avoid_console=False, log_dir=None
):
    """Write a message to the log file and/or print to the the console.

    Args:
        message (str): the content of the message to log
        level (int): one of the logger.level constants
        name (str): name of the logger
        filename (str): name of the log file
        avoid_console (bool): If True, don't print to console for this message
            only
        log_dir (str, optional): directory of log file. Defaults to
            settings.log_folder
    """
    if level is None:
        level = settings.log_level
    if name is None:
        name = settings.log_name
    if filename is None:
        filename = settings.log_filename
    logger = None
    # if logging to file is turned on
    if settings.log_file:
        # get the current logger (or create a new one, if none), then log
        # message at requested level
        logger = get_logger(level=level, name=name, filename=filename, log_dir=log_dir)
        if level == lg.DEBUG:
            logger.debug(message)
        elif level == lg.INFO:
            logger.info(message)
        elif level == lg.WARNING:
            logger.warning(message)
        elif level == lg.ERROR:
            logger.error(message)

    # if logging to console is turned on, convert message to ascii and print to
    # the console
    if settings.log_console and not avoid_console:
        # capture current stdout, then switch it to the console, print the
        # message, then switch back to what had been the stdout. this prevents
        # logging to notebook - instead, it goes to console
        standard_out = sys.stdout
        sys.stdout = sys.__stdout__

        # convert message to ascii for console display so it doesn't break
        # windows terminals
        message = (
            unicodedata.normalize("NFKD", make_str(message))
            .encode("ascii", errors="replace")
            .decode()
        )
        print(message)
        sys.stdout = standard_out

        if level == lg.WARNING:
            warnings.warn(message)

    return logger


def get_logger(level=None, name=None, filename=None, log_dir=None):
    """Create a logger or return the current one if already instantiated.

    Args:
        level (int): one of the logger.level constants.
        name (str): name of the logger.
        filename (str): name of the log file.
        log_dir (str, optional): directory of the log file. Defaults to
            settings.log_folder.

    Returns:
        logging.Logger: a Logger
    """

    if level is None:
        level = settings.log_level
    if name is None:
        name = settings.log_name
    if filename is None:
        filename = settings.log_filename

    logger = lg.getLogger(name)

    # if a logger with this name is not already set up
    if not getattr(logger, "handler_set", None):

        # get today's date and construct a log filename
        todays_date = dt.datetime.today().strftime("%Y_%m_%d")

        if not log_dir:
            log_dir = settings.logs_folder

        log_filename = os.path.join(log_dir, "{}_{}.log".format(filename, todays_date))

        # if the logs folder does not already exist, create it
        if not os.path.exists(settings.logs_folder):
            os.makedirs(settings.logs_folder)

        # create file handler and log formatter and set them up
        handler = lg.FileHandler(log_filename, encoding="utf-8")
        formatter = lg.Formatter(
            "%(asctime)s [%(process)d]  %(levelname)s - %(name)s - %(" "message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.handler_set = True

    return logger


def close_logger(logger=None, level=None, name=None, filename=None, log_dir=None):
    if not logger:
        # try get logger by name
        logger = get_logger(level=level, name=name, filename=filename, log_dir=log_dir)
    handlers = logger.handlers[:]
    for handler in handlers:
        handler.close()
        logger.removeHandler(handler)


def make_str(value):
    """Convert a passed-in value to unicode if Python 2, or string if Python 3.

    Args:
        value (any): the value to convert to unicode/string

    Returns:
        unicode or string
    """
    try:
        # for python 2.x compatibility, use unicode
        return np.unicode(value)
    except NameError:
        # python 3.x has no unicode type, so if error, use str type
        return str(value)


def load_umi_template_objects(filename):
    """Reads

    Args:
        filename (str): path of template file

    Returns:
        dict: Dict of umi_objects
    """
    with open(filename) as f:
        umi_objects = json.load(f)
    return umi_objects


def umi_template_object_to_dataframe(umi_dict, umi_object):
    """Returns flattened DataFrame of umi_objects

    Args:
        umi_dict (dict): dict of umi objects
        umi_object (str): umi_object name

    Returns:
        pandas.DataFrame: flattened DataFrame of umi_objects
    """
    return json_normalize(umi_dict[umi_object])


def get_list_of_common_umi_objects(filename):
    """Returns list of common umi objects

    Args:
        filename (str): path to umi template file

    Returns:
        dict: Dict of common umi objects
    """
    umi_objects = load_umi_template(filename)
    components = OrderedDict()
    for umi_dict in umi_objects:
        for x in umi_dict:
            components[x] = umi_dict[x].columns.tolist()
    return components


def newrange(previous, following):
    """Takes the previous DataFrame and calculates a new Index range. Returns a
    DataFrame with a new index

    Args:
        previous (pandas.DataFrame): previous DataFrame
        following (pandas.DataFrame): follwoing DataFrame

    Returns:
        pandas.DataFrame: DataFrame with an incremented new index
    """
    if not previous.empty:
        from_index = previous.iloc[[-1]].index.values + 1
        to_index = from_index + len(following)

        following.index = np.arange(from_index, to_index)
        following.rename_axis("$id", inplace=True)
        return following
    else:
        # If previous dataframe is empty, return the orginal DataFrame
        return following


def type_surface(row):
    """Takes a boundary and returns its corresponding umi-type

    Args:
        row:

    Returns:
        str: The umi-type of boundary
    """

    # Floors
    if row["Surface_Type"] == "Floor":
        if row["Outside_Boundary_Condition"] == "Surface":
            return 3
        if row["Outside_Boundary_Condition"] == "Ground":
            return 2
        if row["Outside_Boundary_Condition"] == "Outdoors":
            return 4
        else:
            return np.NaN

    # Roofs & Ceilings
    if row["Surface_Type"] == "Roof":
        return 1
    if row["Surface_Type"] == "Ceiling":
        return 3
    # Walls
    if row["Surface_Type"] == "Wall":
        if row["Outside_Boundary_Condition"] == "Surface":
            return 5
        if row["Outside_Boundary_Condition"] == "Outdoors":
            return 0
    return np.NaN


def label_surface(row):
    """Takes a boundary and returns its corresponding umi-Category

    Args:
        row:
    """
    # Floors
    if row["Surface_Type"] == "Floor":
        if row["Outside_Boundary_Condition"] == "Surface":
            return "Interior Floor"
        if row["Outside_Boundary_Condition"] == "Ground":
            return "Ground Floor"
        if row["Outside_Boundary_Condition"] == "Outdoors":
            return "Exterior Floor"
        else:
            return "Other"

    # Roofs & Ceilings
    if row["Surface_Type"] == "Roof":
        return "Roof"
    if row["Surface_Type"] == "Ceiling":
        return "Interior Floor"
    # Walls
    if row["Surface_Type"] == "Wall":
        if row["Outside_Boundary_Condition"] == "Surface":
            return "Partition"
        if row["Outside_Boundary_Condition"] == "Outdoors":
            return "Facade"
    return "Other"


def layer_composition(row):
    """Takes in a series with $id and thickness values and return an array of
    dict of the form {'Material': {'$ref': ref}, 'thickness': thickness} If
    thickness is 'nan', it returns None.

    Returns (list): List of dicts

    Args:
        row (pandas.Series): a row
    """
    array = []
    ref = row["$id", "Outside_Layer"]
    thickness = row["Thickness", "Outside_Layer"]
    if np.isnan(ref):
        pass
    else:
        array.append({"Material": {"$ref": str(int(ref))}, "Thickness": thickness})
        for i in range(2, len(row["$id"]) + 1):
            ref = row["$id", "Layer_{}".format(i)]
            if np.isnan(ref):
                pass
            else:
                thickness = row["Thickness", "Layer_{}".format(i)]
                array.append(
                    {"Material": {"$ref": str(int(ref))}, "Thickness": thickness}
                )
        return array


def schedule_composition(row):
    """Takes in a series with $id and \*_ScheduleDay_Name values and return an
    array of dict of the form {'$ref': ref}

    Args:
        row (pandas.Series): a row

    Returns:
        list: list of dicts
    """
    # Assumes 7 days
    day_schedules = []
    days = [
        "Monday_ScheduleDay_Name",
        "Tuesday_ScheduleDay_Name",
        "Wednesday_ScheduleDay_Name",
        "Thursday_ScheduleDay_Name",
        "Friday_ScheduleDay_Name",
        "Saturday_ScheduleDay_Name",
        "Sunday_ScheduleDay_Name",
    ]  # With weekends last (as defined in
    # umi-template)
    # Let's start with the `Outside_Layer`
    for day in days:
        try:
            ref = row["$id", day]
        except:
            pass
        else:
            day_schedules.append({"$ref": str(int(ref))})
    return day_schedules


def year_composition(row):
    """Takes in a series with $id and ScheduleWeek_Name_{} values and return an
    array of dict of the form {'FromDay': fromday, 'FromMonth': frommonth,
    'Schedule': {'$ref': int( ref)}, 'ToDay': today, 'ToMonth': tomonth}

    Args:
        row (pandas.Series): a row

    Returns:
        list: list of dicts
    """
    parts = []
    for i in range(1, 26 + 1):
        try:
            ref = row["$id", "ScheduleWeek_Name_{}".format(i)]
        except:
            pass
        else:
            if ~np.isnan(ref):
                fromday = row["Schedules", "Start_Day_{}".format(i)]
                frommonth = row["Schedules", "Start_Month_{}".format(i)]
                today = row["Schedules", "End_Day_{}".format(i)]
                tomonth = row["Schedules", "End_Month_{}".format(i)]

                parts.append(
                    {
                        "FromDay": fromday,
                        "FromMonth": frommonth,
                        "Schedule": {"$ref": str(int(ref))},
                        "ToDay": today,
                        "ToMonth": tomonth,
                    }
                )
    return parts


def date_transform(date_str):
    """Simple function transforming one-based hours (1->24) into zero-based
    hours (0->23)

    Args:
        date_str (str): a date string of the form 'HH:MM'

    Returns:
        datetime.datetime: datetime object
    """
    if date_str[0:2] != "24":
        return datetime.strptime(date_str, "%H:%M") - timedelta(hours=1)
    return datetime.strptime("23:00", "%H:%M")


def weighted_mean(series, df, weighting_variable):
    """Compute the weighted average while ignoring NaNs. Implements
    :func:`numpy.average`.

    Args:
        series (pandas.Series):
        df (pandas.DataFrame):
        weighting_variable (str or list or tuple): Weight name to use in

    Returns:
        numpy.ndarray: the weighted average
    """
    # get non-nan values
    index = ~np.isnan(series.values.astype("float"))

    # Returns weights. If multiple `weighting_variable`, df.prod will take care
    # of multipling them together.
    if not isinstance(weighting_variable, list):
        weighting_variable = [weighting_variable]
    try:
        weights = df.loc[series.index, weighting_variable].astype("float").prod(axis=1)
    except Exception:
        raise

    # Try to average
    try:
        wa = np.average(series[index].astype("float"), weights=weights[index])
    except ZeroDivisionError:
        log("Cannot aggregate empty series {}".format(series.name), lg.WARNING)
        return np.NaN
    except Exception:
        raise
    else:
        return wa


def top(series, df, weighting_variable):
    """Compute the highest ranked value weighted by some other variable.
    Implements
        :func:`pandas.DataFrame.nlargest`.

    Args:
        series (pandas.Series): the *series* on which to compute the ranking.
        df (pandas.DataFrame): the *df* containing weighting variables.
        weighting_variable (str or list or tuple): Name of weights to use in
            *df*. If multiple values given, the values are multiplied together.

    Returns:
        numpy.ndarray: the weighted top ranked variable
    """
    # Returns weights. If multiple `weighting_variable`, df.prod will take care
    # of multipling them together.
    if not isinstance(series, pd.Series):
        raise TypeError(
            '"top()" only works on Series, ' "not DataFrames\n{}".format(series)
        )

    if not isinstance(weighting_variable, list):
        weighting_variable = [weighting_variable]

    try:
        idx_ = (
            df.loc[series.index]
            .groupby(series.name)
            .apply(lambda x: safe_prod(x, df, weighting_variable))
        )
        if not idx_.empty:
            idx = idx_.nlargest(1).index
        else:
            log('No such names "{}"'.format(series.name))
            return np.NaN
    except KeyError:
        log("Cannot aggregate empty series {}".format(series.name), lg.WARNING)
        return np.NaN
    except Exception:
        raise
    else:
        if idx.isnull().any():
            return np.NaN
        else:
            return pd.to_numeric(idx, errors="ignore").values[0]


def safe_prod(x, df, weighting_variable):
    """
    Args:
        x:
        df:
        weighting_variable:
    """
    df_ = df.loc[x.index, weighting_variable]
    if not df_.empty:
        return df_.astype("float").prod(axis=1).sum()
    else:
        return 0


def copy_file(files, where=None):
    """Handles a copy of test idf files

    Args:
        files:
        where:
    """
    import shutil, os

    if isinstance(files, str):
        files = [files]
    files = {os.path.basename(k): k for k in files}

    # defaults to cache folder
    if where is None:
        where = settings.cache_folder

    for file in files:
        dst = os.path.join(where, file)
        output_folder = where
        if not os.path.isdir(output_folder):
            os.makedirs(output_folder)
        shutil.copyfile(files[file], dst)
        files[file] = dst

    return _unpack_tuple(list(files.values()))


class Error(Exception):
    """Base class for exceptions in this module."""

    pass


class EnergyPlusProcessError(Error):
    """EnergyPlus Process call error"""

    def __init__(self, cmd, stderr, idf=None):
        """
        Args:
            cmd:
            stderr:
            idf:
        """
        self.cmd = cmd
        self.idf = idf
        self.stderr = stderr

    def __str__(self):
        """Override that only returns the stderr"""
        msg = ":\n".join([self.idf, self.stderr])
        return msg


class cd:
    """Context manager for changing the current working directory"""

    def __init__(self, new_path):
        """
        Args:
            new_path:
        """
        self.newPath = os.path.expanduser(new_path)

    def __enter__(self):
        self.savedPath = os.getcwd()
        if os.path.isdir(self.newPath):
            os.chdir(self.newPath)
        else:
            os.mkdir(self.newPath)
            os.chdir(self.newPath)

    def __exit__(self, etype, value, traceback):
        """
        Args:
            etype:
            value:
            traceback:
        """
        os.chdir(self.savedPath)


def rmse(data, targets):
    """calculate rmse with target values

    Args:
        data:
        targets:
    """
    y = piecewise(data)
    predictions = y
    error = np.sqrt(np.mean((predictions - targets) ** 2))
    return error


def piecewise(data):
    """returns a piecewise function from an array of the form [hour1, hour2,
    ..., value1, value2, ...]

    Args:
        data:
    """
    nb = int(len(data) / 2)
    bins = data[0:nb]
    sf = data[nb:]
    x = np.linspace(0, 8760, 8760)
    # build condition array
    conds = [x < bins[0]]
    conds.extend([np.logical_and(x >= i, x < j) for i, j in zip(bins[0:], bins[1:])])
    # build function array. This is the value of y when the condition is met.
    funcs = sf
    y = np.piecewise(x, conds, funcs)
    return y


def checkStr(datafile, string):
    """Find the last occurrence of a string and return its line number

    Returns: the list index containing the string

    Args:
        datafile (list-like): a list-like object
        string (str): the string to find in the txt file
    """
    value = []
    count = 0
    for line in datafile:
        count = count + 1
        match = re.search(string, str(line))
        if match:
            return count
            break


def write_lines(file_path, lines):
    """Delete file if exists, then write lines in it

    Args:
        file_path (str): path of the file
        lines (list of str): lines to be written in file
    """
    # Delete temp file if exists
    if os.path.exists(file_path):
        os.remove(file_path)
    # Save lines in temp file
    temp_idf_file = open(file_path, "w+")
    for line in lines:
        temp_idf_file.write("%s" % line)
    temp_idf_file.close()


def load_umi_template(json_template):
    """
    Args:
        json_template: Absolute or relative filepath to an umi json_template

    Returns:
        pandas.DataFrame: 17 DataFrames, one for each component groups
    """
    if os.path.isfile(json_template):
        with open(json_template) as f:
            dicts = json.load(f, object_pairs_hook=OrderedDict)

            return [{key: json_normalize(value)} for key, value in dicts.items()]
    else:
        raise ValueError("File {} does not exist".format(json_template))


def check_unique_name(first_letters, count, name, unique_list, suffix=False):
    """Making sure new_name does not already exist

    Args:
        first_letters (str): string at the beginning of the name, giving a hint
            on what the variable is.
        count (int): increment to create a unique id in the name.
        name (str): name that was just created. To be verified that it is unique
            in this function.
        unique_list (list): list where unique names are stored.
        suffix (bool):

    Returns:
        new_name (str): name that is unique
    """
    if suffix:
        while name in unique_list:
            count += 1
            end_count = "%03d" % count
            name = name[:-3] + end_count
    else:
        while name in unique_list:
            count += 1
            end_count = "%06d" % count
            name = first_letters + "_" + end_count

    return name, count


def angle(v1, v2, acute=True):
    """Calculate the angle between 2 vectors

    Args:
        v1 (Vector3D): vector 1
        v2 (Vector3D): vector 2
        acute (bool): If True, give the acute angle, else gives the obtuse one.

    Returns:
        angle (float): angle between the 2 vectors in degree
    """
    angle = np.arccos(np.dot(v1, v2) / (np.linalg.norm(v1) * np.linalg.norm(v2)))
    if acute == True:
        return angle
    else:
        return 2 * np.pi - angle


def float_round(num, n):
    """Makes sure a variable is a float and round it at "n" decimals

    Args:
        num (str, int, float): number we want to make sure is a float
        n (int): number of decimals

    Returns:
        num (float): a float rounded number

    """
    num = float(num)
    num = round(num, n)
    return num


def get_eplus_dire():
    from eppy.runner.run_functions import install_paths

    eplus_exe, eplus_weather = install_paths("8-9-0")
    eplusdir = Path(eplus_exe).dirname()
    return Path(eplusdir)


def timeit(method):
    """Use this method as a decorator on a function to calculate the time it
    take to complete. Uses the :func:`log` method.

    Examples:
        >>> @timeit
        >>> def myfunc():
        >>>     return 'is a function'

    Args:
        method (function): A function.
    """

    def timed(*args, **kwargs):
        ts = time.time()
        log("Executing %r..." % method.__qualname__)
        result = method(*args, **kwargs)
        te = time.time()

        tt = te - ts
        try:
            try:
                name = result.Name
            except:
                name = result.__qualname__
        except:
            name = str(result)
        if tt > 0.001:
            log("Completed %r for %r in %.3f s" % (method.__qualname__, name, tt))
        else:
            log(
                "Completed %r for %r in %.3f ms"
                % (method.__qualname__, name, tt * 1000)
            )
        return result

    return timed


def lcm(x, y):
    """This function takes two
   integers and returns the L.C.M."""

    # choose the greater number
    if x > y:
        greater = x
    else:
        greater = y

    while True:
        if (greater % x == 0) and (greater % y == 0):
            lcm = greater
            break
        greater += 1

    return lcm


def reduce(function, iterable, **attr):
    """
    Args:
        function:
        iterable:
        **attr:
    """
    it = iter(iterable)
    value = next(it)
    for element in it:
        value = function(value, element, **attr)
    return value


def _unpack_tuple(x):
    """Unpacks one-element tuples for use as return values

    Args:
        x:
    """
    if len(x) == 1:
        return x[0]
    else:
        return x
