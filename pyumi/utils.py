import datetime as dt
import json
import logging as lg
import os
import sys
import unicodedata
from pandas.io.json import json_normalize

import numpy as np

from . import settings


def config(data_folder=settings.data_folder,
           logs_folder=settings.logs_folder,
           imgs_folder=settings.imgs_folder,
           cache_folder=settings.cache_folder,
           use_cache=settings.use_cache,
           log_file=settings.log_file,
           log_console=settings.log_console,
           log_level=settings.log_level,
           log_name=settings.log_name,
           log_filename=settings.log_filename,
           useful_idf_objects=settings.useful_idf_objects):
    """
    Configure osmnx by setting the default global vars to desired values.

    Parameters
    ---------
    data_folder : string
        where to save and load data files
    logs_folder : string
        where to write the log files
    imgs_folder : string
        where to save figures
    cache_folder : string
        where to save the http response cache
    use_cache : bool
        if True, use a local cache to save/retrieve http responses instead of
        calling API repetitively for the same request URL
    log_file : bool
        if true, save log output to a log file in logs_folder
    log_console : bool
        if true, print log output to the console
    log_level : int
        one of the logger.level constants
    log_name : string
        name of the logger
    useful_idf_objects : list
        a list of useful idf objects

    Returns
    -------
    None
    """

    # set each global variable to the passed-in parameter value
    settings.use_cache = use_cache
    settings.cache_folder = cache_folder
    settings.data_folder = data_folder
    settings.imgs_folder = imgs_folder
    settings.logs_folder = logs_folder
    settings.log_console = log_console
    settings.log_file = log_file
    settings.log_level = log_level
    settings.log_name = log_name
    settings.log_filename = log_filename
    settings.useful_idf_objects = useful_idf_objects

    # if logging is turned on, log that we are configured
    if settings.log_file or settings.log_console:
        log('Configured pyumi')


def log(message, level=None, name=None, filename=None):
    """
    Write a message to the log file and/or print to the the console.

    Parameters
    ----------
    message : string
        the content of the message to log
    level : int
        one of the logger.level constants
    name : string
        name of the logger
    filename : string
        name of the log file

    Returns
    -------
    None
    """

    if level is None:
        level = settings.log_level
    if name is None:
        name = settings.log_name
    if filename is None:
        filename = settings.log_filename

    # if logging to file is turned on
    if settings.log_file:
        # get the current logger (or create a new one, if none), then log
        # message at requested level
        logger = get_logger(level=level, name=name, filename=filename)
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
    if settings.log_console:
        # capture current stdout, then switch it to the console, print the
        # message, then switch back to what had been the stdout. this prevents
        # logging to notebook - instead, it goes to console
        standard_out = sys.stdout
        sys.stdout = sys.__stdout__

        # convert message to ascii for console display so it doesn't break
        # windows terminals
        message = unicodedata.normalize('NFKD', make_str(message)).encode('ascii', errors='replace').decode()
        print(message)
        sys.stdout = standard_out


def get_logger(level=None, name=None, filename=None):
    """
    Create a logger or return the current one if already instantiated.

    Parameters
    ----------
    level : int
        one of the logger.level constants
    name : string
        name of the logger
    filename : string
        name of the log file

    Returns
    -------
    logger.logger
    """

    if level is None:
        level = settings.log_level
    if name is None:
        name = settings.log_name
    if filename is None:
        filename = settings.log_filename

    logger = lg.getLogger(name)

    # if a logger with this name is not already set up
    if not getattr(logger, 'handler_set', None):

        # get today's date and construct a log filename
        todays_date = dt.datetime.today().strftime('%Y_%m_%d')
        log_filename = os.path.join(settings.logs_folder, '{}_{}.log'.format(filename, todays_date))

        # if the logs folder does not already exist, create it
        if not os.path.exists(settings.logs_folder):
            os.makedirs(settings.logs_folder)

        # create file handler and log formatter and set them up
        handler = lg.FileHandler(log_filename, encoding='utf-8')
        formatter = lg.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(level)
        logger.handler_set = True

    return logger


def make_str(value):
    """
    Convert a passed-in value to unicode if Python 2, or string if Python 3.

    Parameters
    ----------
    value : any
        the value to convert to unicode/string

    Returns
    -------
    unicode or string
    """
    try:
        # for python 2.x compatibility, use unicode
        return unicode(value)
    except NameError:
        # python 3.x has no unicode type, so if error, use str type
        return str(value)


def load_umi_template_objects(filename):
    """
    Reads
    :param filename: string
        Path of template file
    :return: dict
        Dict of umi_objects
    """
    with open(filename) as f:
        umi_objects = json.load(f)
    return umi_objects


def umi_template_object_to_dataframe(umi_dict, umi_object):
    """
    Returns flattened DataFrame of umi_objects
    :param umi_dict: dict
        dict of umi objects
    :param umi_object: string
        umi_object name
    :return: DataFrame

    """
    return json_normalize(umi_dict[umi_object])


def get_list_of_common_umi_objects(filename):
    umi_objects = load_umi_template_objects(filename)


def newrange(previous, following):
    """
    Takes the previous data
    :param previous:
    :param following:
    :return:
    """
    from_index = previous.iloc[[-1]].index.values + 1
    to_index = from_index + len(following)
    return np.arange(from_index, to_index)
