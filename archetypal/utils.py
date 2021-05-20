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
import contextlib
import datetime as dt
import json
import logging as lg
import multiprocessing
import os
import sys
import time
import unicodedata
import warnings
from collections import OrderedDict
from concurrent.futures._base import as_completed

import numpy as np
import pandas as pd
from pandas.io.json import json_normalize
from path import Path
from tqdm import tqdm

from archetypal import __version__, settings
from archetypal.eplus_interface.version import EnergyPlusVersion


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
    default_weight_factor="area",
    ep_version=settings.ep_version,
    debug=settings.debug,
):
    """Package configurations. Call this method at the beginning of script or at the
    top of an interactive python environment to set package-wide settings.

    Args:
        data_folder (str): where to save and load data files.
        logs_folder (str): where to write the log files.
        imgs_folder (str): where to save figures.
        cache_folder (str): where to save the simulation results.
        use_cache (bool): if True, use a local cache to save/retrieve DataPortal API
            calls for the same requests.
        log_file (bool): if true, save log output to a log file in logs_folder.
        log_console (bool): if true, print log output to the console.
        log_level (int): one of the logger.level constants.
        log_name (str): name of the logger.
        log_filename (str): name of the log file.
        useful_idf_objects (list): a list of useful idf objects.
        umitemplate (str): where the umitemplate is located.
        default_weight_factor:
        ep_version (str): EnergyPlus version to use. eg. "9-2-0".
        debug (bool): Use debug behavior in various part of code base.

    Returns:
        None
    """
    # set each global variable to the passed-in parameter value
    settings.use_cache = use_cache
    settings.cache_folder = Path(cache_folder).expand().makedirs_p()
    settings.data_folder = Path(data_folder).expand().makedirs_p()
    settings.imgs_folder = Path(imgs_folder).expand().makedirs_p()
    settings.logs_folder = Path(logs_folder).expand().makedirs_p()
    settings.log_console = log_console
    settings.log_file = log_file
    settings.log_level = log_level
    settings.log_name = log_name
    settings.log_filename = log_filename
    settings.useful_idf_objects = useful_idf_objects
    settings.umitemplate = umitemplate
    settings.zone_weight.set_weigth_attr(default_weight_factor)
    settings.ep_version = EnergyPlusVersion(ep_version).dash
    settings.debug = debug

    # if logging is turned on, log that we are configured
    if settings.log_file or settings.log_console:
        log("Configured archetypal")


def log(
    message,
    level=None,
    name=None,
    filename=None,
    avoid_console=False,
    log_dir=None,
    verbose=False,
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
        verbose: If True, settings.log_console is overridden.
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
    if settings.log_console or verbose or level == lg.ERROR and not avoid_console:
        # capture current stdout, then switch it to the console, print the
        # message, then switch back to what had been the stdout. this prevents
        # logging to notebook - instead, it goes to console
        standard_out = sys.stdout
        sys.stdout = sys.__stdout__

        # convert message to ascii for console display so it doesn't break
        # windows terminals
        message = (
            unicodedata.normalize("NFKD", str(message))
            .encode("ascii", errors="replace")
            .decode()
        )
        tqdm.write(message)
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
    if isinstance(log_dir, str):
        log_dir = Path(log_dir)
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

        log_filename = log_dir / "{}_{}.log".format(filename, todays_date)

        # if the logs folder does not already exist, create it
        if not log_dir.exists():
            log_dir.makedirs_p()
        # create file handler and log formatter and set them up
        try:
            handler = lg.FileHandler(log_filename, encoding="utf-8")
        except:
            handler = lg.StreamHandler()
        formatter = lg.Formatter(
            "%(asctime)s [%(process)d]  %(levelname)s - %(name)s - %(" "message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.handler_set = True

    return logger


def close_logger(logger=None, level=None, name=None, filename=None, log_dir=None):
    """
    Args:
        logger:
        level:
        name:
        filename:
        log_dir:
    """
    if not logger:
        # try get logger by name
        logger = get_logger(level=level, name=name, filename=filename, log_dir=log_dir)
    handlers = logger.handlers[:]
    for handler in handlers:
        handler.close()
        logger.removeHandler(handler)


def weighted_mean(series, df, weighting_variable):
    """Compute the weighted average while ignoring NaNs. Implements
    :func:`numpy.average`.

    Args:
        series (pandas.Series): the *series* on which to compute the mean.
        df (pandas.DataFrame): the *df* containing weighting variables.
        weighting_variable (str or list or tuple): Name of weights to use in
            *df*. If multiple values given, the values are multiplied together.

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
        files (str or list): path(s) of the file(s) to copy
        where (str): path where to save the copy(ies)
    """
    import os
    import shutil

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


@contextlib.contextmanager
def cd(path):
    """
    Args:
        path:
    """
    log("initially inside {0}".format(os.getcwd()))
    CWD = os.getcwd()

    os.chdir(path)
    log("inside {0}".format(os.getcwd()))
    try:
        yield
    finally:
        os.chdir(CWD)
        log("finally inside {0}".format(os.getcwd()))


def load_umi_template(json_template):
    """Load umi template file to list of dict.

    Args:
        json_template (str): filepath to an umi json_template.

    Returns:
        list: list of dict.
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
    """This function takes two integers and returns the least common multiple."""

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
    if iterable:
        it = iter(iterable)
        value = next(it)
        for element in it:
            value = function(value, element, **attr)
        return value
    else:
        return None


def _unpack_tuple(x):
    """Unpacks one-element tuples for use as return values

    Args:
        x:
    """
    if len(x) == 1:
        return x[0]
    else:
        return x


def recursive_len(item):
    """Calculate the number of elements in nested list

    Args:
        item (list): list of lists (i.e. nested list)

    Returns:
        Total number of elements in nested list
    """
    if type(item) == list:
        return sum(recursive_len(subitem) for subitem in item)
    else:
        return 1


def rotate(l, n):
    """Shift list elements to the left

    Args:
        l (list): list to rotate
        n (int): number to shift list to the left

    Returns:
        list: shifted list.
    """
    return l[n:] + l[:n]


def parallel_process(
    in_dict,
    function,
    processors=-1,
    use_kwargs=True,
    show_progress=True,
    position=0,
    debug=False,
    executor=None,
):
    """A parallel version of the map function with a progress b

    Examples:
        >>> from archetypal import IDF
        >>> files = ['tests/input_data/problematic/nat_ventilation_SAMPLE0.idf',
        >>>          'tests/input_data/regular/5ZoneNightVent1.idf']
        >>> wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
        >>> rundict = {file: dict(idfname=file, epw=wf,
        >>>                      as_version="9-2-0", annual=True,
        >>>                      prep_outputs=True, expandobjects=True,
        >>>                      verbose='q')
        >>>           for file in files}
        >>> result = parallel_process(rundict, IDF, use_kwargs=True)

    Args:
        in_dict (dict): A dictionary to iterate over. `function` is applied to value
            and key is used as an identifier.
        function (callable): A python function to apply to the elements of
            in_dict
        processors (int): The number of cores to use.
        use_kwargs (bool): If True, pass the kwargs as arguments to `function`.
        debug (bool): If True, will raise any error on any process.
        position: Specify the line offset to print the tqdm bar (starting from 0)
            Automatic if unspecified. Useful to manage multiple bars at once
            (eg, from threads).
        executor (Executor)

    Returns:
        [function(array[0]), function(array[1]), ...]
    """
    if executor is None:
        from concurrent.futures import ThreadPoolExecutor

        _executor_factory = ThreadPoolExecutor
    else:
        _executor_factory = executor

    from tqdm import tqdm

    if processors == -1:
        processors = min(len(in_dict), multiprocessing.cpu_count())

    kwargs = {
        "desc": function.__name__,
        "total": len(in_dict),
        "unit": "runs",
        "unit_scale": True,
        "position": position,
        "disable": not show_progress,
    }

    if processors == 1:
        futures = []
        out = []
        for a in tqdm(in_dict, **kwargs):
            if use_kwargs:
                futures.append(submit(function, **in_dict[a]))
            else:
                futures.append(submit(function, in_dict[a]))
        for job in futures:
            out.append(job)
    else:
        with _executor_factory(
            max_workers=processors,
            initializer=config,
            initargs=(
                settings.data_folder,
                settings.logs_folder,
                settings.imgs_folder,
                settings.cache_folder,
                settings.use_cache,
                settings.log_file,
                settings.log_console,
                settings.log_level,
                settings.log_name,
                settings.log_filename,
                settings.useful_idf_objects,
                settings.umitemplate,
                "area",
                settings.ep_version,
                settings.debug,
            ),
        ) as executor:
            out = []
            futures = []

            if use_kwargs:
                for a in in_dict:
                    future = executor.submit(function, **in_dict[a])
                    futures.append(future)
            else:
                for a in in_dict:
                    future = executor.submit(function, in_dict[a])
                    futures.append(future)

            # Print out the progress as tasks complete
            for job in tqdm(as_completed(futures), **kwargs):
                # Read result from future
                try:
                    result_done = job.result()
                except Exception as e:
                    if debug:
                        lg.warning(str(e))
                        raise e
                    result_done = e
                # Append to the list of results
                out.append(result_done)
    return out


def submit(fn, *args, **kwargs):
    """return fn or Exception"""
    try:
        return fn(*args, **kwargs)
    except Exception as e:
        return e


def is_referenced(name, epbunch, fieldname="Zone_or_ZoneList_Name"):
    """bool: Returns True if name is in referenced object fieldname"""
    refobj = epbunch.get_referenced_object(fieldname)
    if not refobj:
        refobj = epbunch.get_referenced_object("Zone_Name")  # Backwards Compatibility
    if not refobj:
        pass
    elif refobj.key.upper() == "ZONE":
        return name in refobj.Name
    elif refobj.key.upper() == "ZONELIST":
        raise NotImplementedError(
            f"Checking against a ZoneList is "
            f"not yet supported in archetypal "
            f"v{__version__}"
        )
    raise ValueError(
        f"Invalid referring object returned while "
        f"referencing object name: Looking for '{name}' in "
        f"object {refobj}"
    )


def docstring_parameter(*args, **kwargs):
    """Replaces variables in foo.__doc__ by calling obj.__doc__ =
    obj.__doc__.format(* args, ** kwargs)
    """

    def dec(obj):
        obj.__doc__ = obj.__doc__.format(*args, **kwargs)
        return obj

    return dec


def extend_class(cls):
    """Given class cls, apply decorator @extend_class to function f so
    that f becomes a regular method of cls:

    Example:
        >>> class cls: pass
        >>> @extend_class(cls)
        ... def f(self):
        ...   pass

    Extending class has several usages:
        1. There are classes A, B, ... Z, all defining methods foo and b
           Though the usual approach is to group the code around class
           definitions in files A.py, B.py, ..., Z.py, it is sometimes more
           convenient to group all definitions of A.foo(), B.foo(), ... up
           to Z.foo(), in one file "foo.py", and all definitions of bar in
           file "bpy".
        2. Another usage of @extend_class is building a class step-by-step
           --- first creating an empty class, and later populating it with
           methods.
        3. Finally, it is possible to @extend several classes
           simultaneously with the same method, as in the example below,
           where classes A and B share method foo.

    Example:
        >>> class A: pass  # empty class
        ...
        >>> class B: pass  # empty class
        ...
        >>> @extend_class(A)
        ... @extend_class(B)
        ... def foo(self,s):
        ...     print s
        ...
        >>> a = A()
        >>> a.foo('hello')
        hello
        >>> b = B()
        >>> b.foo('world')
        world

    Limitations:
        1. @extend_class won't work on builtin classes, such as int.
        2. Not tested on python 3.
    Author:
        victorlei@gmail.com
    """
    return lambda f: (setattr(cls, f.__name__, f) or f)


class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, np.bool_):
            return bool(obj)

        return obj
