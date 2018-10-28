import glob
import hashlib
import logging as lg
import os
import time

import pandas as pd
from eppy.runner.run_functions import run

from . import settings
from .utils import log

try:
    import multiprocessing as mp
except ImportError:
    pass


def object_from_idfs(idfs, ep_object, first_occurrence_only=False):
    """

    :param idfs: list or dict
        List of IDF objects
    :param ep_object: string
        EnergyPlus object eg. 'WINDOWMATERIAL:GAS' as a string
    :param keys: list
        List of names for each idf file. Becomes level-0 of a multi-index.
    :param first_occurrence_only: bool

    :return: DataFrame of all specified objects in idf files
    """
    container = []
    start_time = time.time()
    log('Parsing {1} objects for {0} idf files...'.format(len(idfs), ep_object))

    if isinstance(idfs, dict):
        try:
            raise ValueError()
            runs = [[idf, ep_object] for idfname, idf in idfs.items()]
            import concurrent.futures
            with concurrent.futures.ProcessPoolExecutor() as executor:
                container = {idfname:result for (idfname, idf), result in zip(idfs.items(), executor.map(
                    object_from_idf_pool, runs))}
        except Exception as e:
            # multiprocessing not present so pass the jobs one at a time
            container = {}
            for key, idf in idfs.items():
                # Load objects from IDF files and concatenate
                this_frame = object_from_idf(idf, ep_object)
                container[key]=this_frame

        # If keys given, construct hierarchical index using the passed keys as the outermost level
        this_frame = pd.concat(container, names=['Archetype', '$id'], sort=True)
        this_frame.reset_index(inplace=True)
        this_frame.drop(columns='$id', inplace=True)
    else:
        for idf in idfs:
            # Load objects from IDF files and concatenate
            this_frame = object_from_idf(idf, ep_object)
            this_frame = pd.concat(this_frame, ignore_index=True, sort=True)
            container.append(this_frame)
        # Concat the list of DataFrames
        this_frame = pd.concat(container)

    if first_occurrence_only:
        this_frame = this_frame.groupby('Name').first()
    this_frame.reset_index(inplace=True)
    this_frame.index.rename('$id', inplace=True)
    log('Parsed {} {} object(s) in {} idf file(s) in {:,.2f} seconds'.format(len(this_frame), ep_object, len(idfs), time.time() -
                                                                       start_time))
    return this_frame

def object_from_idf_pool(args):
    this_frame = object_from_idf(args[0], args[1])
    return this_frame


def object_from_idf(idf, ep_object):
    """

    :param idf: IDF
        IDF object
    :param ep_object:
    :return:
    """
    try:
        df = pd.concat([pd.DataFrame(obj.fieldvalues, index=obj.fieldnames[0:len(obj.fieldvalues)]).T for obj in idf.idfobjects[ep_object]],
            ignore_index=True, sort=False)
    except:
        raise ValueError('EP object "{}" does not exist in frame'.format(ep_object))
    else:
        return df

    # object_values = [get_values(frame) for frame in idf.idfobjects[ep_object]]
    # return object_values


def load_idf(files, idd_filename=None, energyplus_version=None, as_dict=False):
    """
    Returns a list of IDF objects using the eppy package.
    :param files: list
        List of file paths
    :param idd_filename: string
        IDD file name location (Energy+.idd)
    :return: list
        List of IDF objects
    """
    # Check weather to use MacOs or Windows location
    if idd_filename is None:
        from sys import platform

        if energyplus_version:
            # Specify version
            energyplus_folder = 'EnergyPlus-{}'.format(energyplus_version)
        else:
            # Don't specify version
            energyplus_folder = 'EnergyPlus*'  # Wildcard will find any version installed

        # Platform specific location of IDD file
        if platform == "darwin":
            # Assume MacOs file location in Applications Folder
            idd_filename = glob.glob("/Applications/{}/Energy+.idd".format(energyplus_folder))
            if len(idd_filename) > 1:
                log('More than one versions of EnergyPlus were found. First one is used')
                idd_filename = idd_filename[0]
            elif len(idd_filename) == 1:
                idd_filename = idd_filename[0]
            else:
                log('The necessary IDD file could not be found', level=lg.ERROR)
                raise ValueError('File Energy+.idd could not be found')
        elif platform == "win32":
            # Assume Windows file location in "C" Drive
            idd_filename = glob.glob("C:\{}\EnergyPlus\*.idd".format(energyplus_folder))
            if len(idd_filename) > 1:
                log('More than one versions of EnergyPlus were found. First one is used')
                idd_filename = idd_filename[0]
            elif len(idd_filename) == 1:
                idd_filename = idd_filename[0]
            else:
                log('The necessary IDD file could not be found', level=lg.ERROR)
                raise ValueError('File Energy+.idd could not be found')
        if idd_filename:
            log('Retrieved EnergyPlus IDD file at location: {}'.format(idd_filename))

    # Try loading IDF objects from pickled cache first
    dirnames = [os.path.dirname(path) for path in files]
    start_time = time.time()
    try:
        log('Parsing IDF Objects in parallel...')
        import concurrent.futures
        with concurrent.futures.ProcessPoolExecutor() as executor:
            idfs = {os.path.basename(file): result for file, result in zip(files, executor.map(
                load_idf_object_from_cache, files))}
    except Exception as e:
        # multiprocessing not present so pass the jobs one at a time
        log('Error with the following exception : {}\nCannot use parallel load'.format(e))
        log('Parsing IDF Objects...')
        idfs = {}
        for file in files:
            eplus_finename = os.path.basename(file)
            idfs[eplus_finename] = load_idf_object_from_cache(file)

    objects_found = {k: v for k, v in idfs.items() if v is not None}
    objects_not_found = [k for k, v in idfs.items() if v is None]
    if not objects_not_found:
        # if objects_not_found not empty, return the ones we actually did find and pass the other ones
        if not as_dict:
            log('Eppy load from cache completed in {:,.2f} seconds\n'.format(time.time() - start_time))
            return list(objects_found.values())
        else:
            log('Eppy load from cache completed in {:,.2f} seconds\n'.format(time.time() - start_time))
            return objects_found
    else:
        # Else, run eppy to load the idf objects
        files = [os.path.join(dir, run) for dir, run in zip(dirnames, objects_not_found)]
        runs=[]
        for file in files:
            runs.append([file, idd_filename])
        # Parallel load
        try:
            start_time = time.time()
            import concurrent.futures
            with concurrent.futures.ProcessPoolExecutor() as executor:
                idfs = [idf_object for idf_object in executor.map(eppy_load_pool, runs)] # TODO : Will probably break when dict is asked
                log('Parallel parsing of {} idf file(s) completed in {:,.2f} seconds'.format(len(files), time.time() -
                                                                                             start_time))
        except Exception as e:
            # multiprocessing not present so pass the jobs one at a time
            log('Error with the following exception : {}\nCannot use parallel load'.format(e))
            idfs = {}
            start_time = time.time()
            for file in files:
                eplus_finename = os.path.basename(file)
                idf_object = eppy_load(file, idd_filename)
                idfs[eplus_finename] = idf_object
            log('Parsed {} idf file(s) in {:,.2f} seconds'.format(len(files), time.time() - start_time))
        if not as_dict:
            return list(idfs.values)
        return idfs

def eppy_load_pool(args):
    return eppy_load(args[0], args[1])


def eppy_load(file, idd_filename):
    from eppy.modeleditor import IDF
    # Loading eppy
    IDF.setiddname(idd_filename)
    with IDF(file) as idf_object:
        # Check version of IDF file against version of IDD file
        idf_version = idf_object.idfobjects['VERSION'][0].Version_Identifier
        idd_version = '{}.{}'.format(idf_object.idd_version[0], idf_object.idd_version[1])
        building = idf_object.idfobjects['BUILDING'][0]
        if idf_version == idd_version:
            log('The version of the IDF file {} : version {}, matched the version of EnergyPlus {}, '
                'version {} used to parse it.'.format(building.Name, idf_version,
                                                      idf_object.getiddname(), idd_version),
                level=lg.DEBUG)
        else:
            log('The version of the IDF file {} : version {}, does not match the version of EnergyPlus {}, '
                'version {} used to parse it.'.format(idf_object.idfobjects['BUILDING'][0].Name, idf_version,
                                                      idf_object.getiddname(), idd_version),
                level=lg.WARNING)
        save_idf_object_to_cache(idf_object, idf_object.idfname)
    return idf_object


def save_idf_object_to_cache(idf_object, idf_file):
    """Save IDFS instance to a gzip'ed pickle file
    :param idfs: array
    :param folder: str
        location to save file
    """
    if settings.use_cache:
        cache_filename = hash_file(idf_file)
        cache_dir = os.path.join(settings.cache_folder, cache_filename)
        cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename, os.extsep.join([
            cache_filename + 'idfs', 'gzip']))

        # create the folder on the disk if it doesn't already exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)
        # create pickle and dump
        import gzip
        try:
            import cPickle as pickle
        except ImportError:
            import pickle
        start_time = time.time()
        with gzip.GzipFile(cache_fullpath_filename, 'wb') as file_handle:
            pickle.dump(idf_object, file_handle)
        log('Saved pickle to file in {:,.2f} seconds'.format(time.time() - start_time))


def load_idf_object_from_cache(idf_file):
    """
    Load an idf instance from a gzip'ed pickle file
    :param idfs:
    """
    if settings.use_cache:
        import gzip
        try:
            import cPickle as pickle
        except ImportError:
            import pickle
        start_time = time.time()
        cache_filename = hash_file(idf_file)
        cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename, os.extsep.join([
            cache_filename + 'idfs', 'gzip']))
        if os.path.isfile(cache_fullpath_filename):
            with gzip.GzipFile(cache_fullpath_filename, 'rb') as file_handle:
                idf = pickle.load(file_handle)
            log('Loaded "{}" from pickled file in {:,.2f} seconds'.format(os.path.basename(idf_file), time.time() -
                                                                          start_time))
            return idf


def get_values(frame):
    ncols = min(len(frame.fieldvalues), len(frame.fieldnames))
    return pd.DataFrame([frame.fieldvalues[0:ncols]], columns=frame.fieldnames[0:ncols])


def run_eplus(eplus_files, weather_file, output_folder=None, ep_version='8-9-0', output_report='htm', processors=6,
              **kwargs):
    """
    Run an energy plus file and returns the SummaryReports Tables in a return a list of [(title, table), .....]

    :param ep_version: str
        the EnergyPlus version to use eg: 8-9-0
    :param weather_file: str
        path to the WeatherFile
    :param eplus_file: str or list
        path to the idf file
    :param output_folder: str
        path to the output folder. Will default to the settings.cache_folder value.
    :return: dict
        a dict of {title : table <DataFrame>, .....}
    """

    # If python 2.7: `from __future__ import print_function`

    if not output_folder:
        output_folder = os.path.abspath(settings.cache_folder)
    # create the folder on the disk if it doesn't already exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    log('Output folder set to {}'.format(output_folder))
    if isinstance(eplus_files, str):
        # Treat str as an array
        eplus_files = [eplus_files]
    dirnames = [os.path.dirname(path) for path in eplus_files]

    # Try to get cached results
    processed_cache = []
    for eplus_file in eplus_files:
        processed_cache.append([eplus_file, output_report, kwargs])
    try:
        start_time = time.time()
        import concurrent.futures
        with concurrent.futures.ProcessPoolExecutor() as executor:
            cached_run_results = {os.path.basename(eplus_finename): result for eplus_finename, result in
                                  zip(eplus_files, executor.map(get_from_cache_pool, processed_cache))}
            log('Parallel parsing completed in {:,.2f} seconds'.format(time.time() - start_time))
    except NameError:
        # multiprocessing not present so pass the jobs one at a time
        cached_run_results = {}
        start_time = time.time()
        for eplus_file in eplus_files:
            eplus_finename = os.path.basename(eplus_file)
            cached_run_results[eplus_finename] = get_from_cache(eplus_file, output_report, **kwargs)
        log('Parsing completed in {:,.2f} seconds'.format(time.time() - start_time))

    runs_found = {k: v for k, v in cached_run_results.items() if v is not None}
    runs_not_found = [k for k, v in cached_run_results.items() if v is None]
    if not runs_not_found:
        # found these runs in the cache, just return them instead of making a
        # new eplus call
        return runs_found

        # continue
        # with simulation of other files
    else:
        # some runs not found
        log('None or some runs could could be found. Running Eplus for {} out of {} files'.format(len(runs_not_found),
                                                                                                  len(eplus_files)))
        eplus_files = [os.path.join(dir, run) for dir, run in zip(dirnames, runs_not_found)]

        start_time = time.time()
        if processors <= 0:
            processors = max(1, mp.cpu_count() - processors)

        # shutil.rmtree("multi_runs", ignore_errors=True)
        # os.mkdir("multi_runs")

        from shutil import copyfile
        processed_runs = []
        for i, eplus_file in enumerate(eplus_files):
            filename = os.path.basename(eplus_file)
            # hash the eplus_file name (to make shorter than the often extremely long name)
            filename_prefix = hash_file(eplus_file)
            epw = weather_file
            kwargs = {'output_directory': output_folder + '/{}'.format(filename_prefix),
                      'ep_version': ep_version,
                      'output_prefix': filename_prefix}
            idf_path = os.path.abspath(eplus_file)  # TODO Should copy idf somewhere else before running; [Partly Fixed]
            processed_runs.append([[idf_path, epw], kwargs])

            # Put a copy of the file in its cache folder
            if not os.path.isfile(os.path.join(kwargs['output_directory'], os.path.basename(eplus_file))):
                if not os.path.isdir(os.path.join(kwargs['output_directory'])):
                    os.mkdir(kwargs['output_directory'])
                copyfile(eplus_file, os.path.join(kwargs['output_directory'], os.path.basename(eplus_file)))

        log('Running EnergyPlus...')
        # We run the EnergyPlus Simulation
        try:
            pool = mp.Pool(processors)
            pool.map(multirunner, processed_runs)
            pool.close()
        except NameError:
            # multiprocessing not present so pass the jobs one at a time
            for job in processed_runs:
                multirunner([job])
        log('Completed EnergyPlus in {:,.2f} seconds'.format(time.time() - start_time))
        # Return summary DataFrames
        reports = {}
        for eplus_file in eplus_files:
            eplus_finename = os.path.basename(eplus_file)
            runs_found[eplus_finename] = get_report(eplus_file, output_folder, output_report, **kwargs)
        return runs_found

def multirunner(args):
    """Wrapper for run() to be used when running IDF and EPW runs in parallel.

    Parameters
    ----------
    args : list
        A list made up of a two-item list (IDF and EPW) and a kwargs dict.

    """
    try:
        run(*args[0], **args[1])
    except:
        # Get error file
        error_filename = os.path.join(args[1]['output_directory'], args[1]['output_prefix'] + 'out.err')
        if os.path.isfile(error_filename):
            with open(error_filename, 'r') as fin:
                log('\nError File for {} begins here...\n'.format(os.path.basename(args[0][0])), lg.ERROR)
                log(fin.read(), lg.ERROR)
                log('\nError File for {} ends here...\n'.format(os.path.basename(args[0][0])), lg.ERROR)
        else:
            log('Could not find error file', lg.ERROR)

def get_from_cache_pool(args):
    """Wrapper for get_from_cache() to be used when laoding in parallel.
    Parameters
    ----------
    args : list
        A list made up of arguments.
    """
    return get_from_cache(args[0], args[1])  # Todo: Settup arguments as Locals()


def hash_file(eplus_file):
    """
    Simple function to hash a file and return it as a string.
    :param eplus_file: str
        the path to the idf file
    :return: str
        hashed file string

    TODO: Hashing only the idf file can cause issues when external files are used (and have changed) because hashing will no capture this change
    """
    hasher = hashlib.md5()
    with open(eplus_file, 'rb') as afile:
        buf = afile.read()
        hasher.update(buf)
    return hasher.hexdigest()


def get_report(eplus_file, output_folder=None, output_report='htm', **kwargs):
    filename = os.path.basename(eplus_file)
    filename_prefix = hash_file(eplus_file)
    if 'htm' in output_report.lower():
        # Get the html report
        fullpath_filename = os.path.join(output_folder, filename_prefix,
                                         os.extsep.join([filename_prefix + 'tbl', 'htm']))
        if os.path.isfile(fullpath_filename):
            return get_html_report(fullpath_filename)

    elif 'sql' in output_report.lower():
        # Get the sql report
        fullpath_filename = os.path.join(output_folder, filename_prefix,
                                         os.extsep.join([filename_prefix + 'out', 'sql']))
        if os.path.isfile(fullpath_filename):
            try:
                if kwargs['report_tables']:
                    return get_sqlite_report(fullpath_filename, kwargs['report_tables'])
            except:
                return get_sqlite_report(fullpath_filename)


def get_from_cache(eplus_file, output_report='htm', **kwargs):
    """
    Retrieve a EPlus Tabulated Summary run result from the cache.
    :param output_report: str
        the eplus output file extension eg. 'htm' or 'sql'
    :param eplus_file: str
        the name of the eplus file
    :return: dict
        a dict of {title : table <DataFrame>, .....}

    """
    if settings.use_cache:
        # determine the filename by hashing the eplus_file
        cache_filename_prefix = hash_file(eplus_file)
        if 'htm' in output_report.lower():
            # Get the html report
            cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename_prefix,
                                                   os.extsep.join([cache_filename_prefix + 'tbl', 'htm']))
            if os.path.isfile(cache_fullpath_filename):
                return get_html_report(cache_fullpath_filename)

        elif 'sql' in output_report.lower():
            # get the SQL report
            cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename_prefix,
                                                   os.extsep.join([cache_filename_prefix + 'out', 'sql']))
            if os.path.isfile(cache_fullpath_filename):
                try:
                    if kwargs['report_tables']:
                        return get_sqlite_report(cache_fullpath_filename, kwargs['report_tables'])
                except:
                    return get_sqlite_report(cache_fullpath_filename)


def get_html_report(report_fullpath):
    """
    Parses the html Summary Report for each tables into a dictionary of DataFrames
    :param report_fullpath: string
        full path to the report file
    :return: dict
        a dict of {title : table <DataFrame>,...}
    """
    from eppy.results import readhtml  # the eppy module with functions to read the html
    with open(report_fullpath, 'r', encoding='utf-8') as cache_file:
        filehandle = cache_file.read()  # get a file handle to the html file

        cached_tbl = readhtml.titletable(filehandle)  # get a file handle to the html file

        log('Retrieved response from cache file "{}"'.format(
            report_fullpath))
        return summary_reports_to_dataframes(cached_tbl)


def summary_reports_to_dataframes(reports_list):
    """
    Converts a list of [(title, table),...] to a dict of {title: table <DataFrame>}. Makes sure that duplicate keys
    have their own unique names in the output dict.
    :param reports_list: list
        a list of [(title, table),...]
    :return: dict
        a dict of {title: table <DataFrame>}
    """
    results_dict = {}
    for table in reports_list:
        key = str(table[0])
        if key in results_dict:  # Check if key is already exists in dictionary and give it a new name
            key = key + '_'
        df = pd.DataFrame(table[1])
        df = df.rename(columns=df.iloc[0]).drop(df.index[0])
        results_dict[key] = df
    return results_dict


def get_sqlite_report(report_file, report_tables=None):
    # set list of report tables
    if not report_tables:
        report_tables = settings.available_sqlite_tables

    # if file exists, parse it with pandas' read_sql_query
    if os.path.isfile(report_file):
        import sqlite3
        # create database connection with sqlite3
        with sqlite3.connect(report_file) as conn:
            # empty dict to hold all DataFrames
            all_tables = {}
            # Iterate over all tables in the report_tables list
            for table in report_tables:
                try:
                    all_tables[table] = pd.read_sql_query("select * from {};".format(table), conn,
                                                          index_col=report_tables[table]['PrimaryKey'],
                                                          parse_dates=report_tables[table]['ParseDates'])
                except:
                    log('no such table: {}'.format(table), lg.WARNING)

            log('SQL query parsed {} tables as DataFrames from {}'.format(len(all_tables), report_file))
            return all_tables
