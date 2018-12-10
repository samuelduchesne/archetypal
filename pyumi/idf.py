import glob
import hashlib
import logging as lg
import os
import time
from subprocess import CalledProcessError
from subprocess import check_call

import eppy.modeleditor
import pandas as pd
from eppy.EPlusInterfaceFunctions import parse_idd
from eppy.easyopen import getiddfile
from eppy.runner.run_functions import run

from . import settings
from .utils import log

try:
    import multiprocessing as mp
except ImportError:
    pass


def object_from_idfs(idfs, ep_object, first_occurrence_only=False, processors=None):
    """

    :param list or dict idfs:  List of IDF objects
    :param str ep_object: EnergyPlus object eg. 'WINDOWMATERIAL:GAS' as a string
    :param list keys: List of names for each idf file. Becomes level-0 of a multi-index.
    :param bool first_occurrence_only:
    :return: DataFrame of all specified objects in idf files
    :rtype: pandas.DataFrame

    """
    container = []
    start_time = time.time()
    log('Parsing {1} objects for {0} idf files...'.format(len(idfs), ep_object))

    if isinstance(idfs, dict):
        try:
            # Loading objects in parallel is actually slower at the moment, so we raise an Exception
            raise Exception('Parallel takes more time at the moment')
            runs = [[idf, ep_object] for idfname, idf in idfs.items()]
            import concurrent.futures
            with concurrent.futures.ProcessPoolExecutor(max_workers=processors) as executor:
                container = {idfname: result for (idfname, idf), result in zip(idfs.items(), executor.map(
                    object_from_idf_pool, runs))}
        except Exception as e:
            # multiprocessing not present so pass the jobs one at a time
            log('Cannot use parallel load. Error with the following exception:\n{}'.format(e))
            container = {}
            for key, idf in idfs.items():
                # Load objects from IDF files and concatenate
                this_frame = object_from_idf(idf, ep_object)
                container[key] = this_frame

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
    log('Parsed {} {} object(s) in {} idf file(s) in {:,.2f} seconds'.format(len(this_frame), ep_object, len(idfs),
                                                                             time.time() -
                                                                             start_time))
    return this_frame


def object_from_idf_pool(args):
    """
    Wrapper for :py:func:`object_from_idf` to use in parallel calls

    :param list args: list of arguments to pass to :py:func:`object_from_idf`
    :return: the list of
    :rtype: pandas.DataFrame

    """
    return object_from_idf(args[0], args[1])


def object_from_idf(idf, ep_object):
    """

    :param eppy.IDF idf: IDF object
    :param str ep_object:
    :return: DataFrame
    :rtype: pandas.DataFrame

    """
    try:
        df = pd.concat([pd.DataFrame(obj.fieldvalues, index=obj.fieldnames[0:len(obj.fieldvalues)]).T for obj in
                        idf.idfobjects[ep_object]],
                       ignore_index=True, sort=False)
    except Exception as e:
        log('ValueError: EP object "{}" does not exist in frame for idf "{}"'.format(ep_object, idf.idfname))
    else:
        return df


def load_idf(files, idd_filename=None, as_dict=True, processors=None):
    """
    Returns a list of parsed IDF objects.

    :param str,list files: file path or list of file paths to the idf files
    :param str idd_filename: optional, the IDD file name location, eg.: './Energy+.idd'
    :param bool as_dict: return as dictionnary instead of list
    :param int processors: Wether or not to run in parallel
    :return: list of eppy.IDF objects
    :rtype: list
    """
    # Check weather to use MacOs or Windows location
    if isinstance(files, str):
        files = [files]

    # Determine version of idf file by reading the text file
    if idd_filename is None:
        idd_filename = {file: getiddfile(get_idf_version(file)) for file in files}

    # Try loading IDF objects from pickled cache first
    dirnames = [os.path.dirname(path) for path in files]
    start_time = time.time()
    try:
        if processors:
            log('Parsing IDF Objects using {} processors...'.format(processors))
            import concurrent.futures
            with concurrent.futures.ProcessPoolExecutor(max_workers=processors) as executor:
                idfs = {os.path.basename(file): result for file, result in zip(files, executor.map(
                    load_idf_object_from_cache, files))}
        else:
            raise Exception('User asked not to run in parallel')
    except Exception as e:
        # multiprocessing not present so pass the jobs one at a time
        log('Cannot use parallel load. Error with the following exception:\n{}'.format(e))
        log('Parsing IDF Objects sequentially...')
        idfs = {}
        for file in files:
            eplus_finename = os.path.basename(file)
            idfs[eplus_finename] = load_idf_object_from_cache(file)

    objects_found = {k: v for k, v in idfs.items() if v is not None}
    objects_not_found = [k for k, v in idfs.items() if v is None]
    if not objects_not_found:
        # if objects_not_found not empty, return the ones we actually did find and pass the other ones
        if as_dict:
            log('Eppy load from cache completed in {:,.2f} seconds\n'.format(time.time() - start_time))
            return objects_found
        else:
            log('Eppy load from cache completed in {:,.2f} seconds\n'.format(time.time() - start_time))
            return list(objects_found.values())
    else:
        # Else, run eppy to load the idf objects
        files = [os.path.join(dir, run) for dir, run in zip(dirnames, objects_not_found)]
        # runs = []
        runs = {os.path.basename(file): [file, idd_filename[file]] for file in files}
        # for file in files:
        #     runs.append([file, idd_filename[file]])
        # Parallel load
        try:
            if processors:
                start_time = time.time()
                import concurrent.futures
                with concurrent.futures.ProcessPoolExecutor(max_workers=processors) as executor:
                    idfs = {filename: idf_object for filename, idf_object in
                            zip(runs.keys(), executor.map(eppy_load_pool, runs.values()))}
                    # TODO : Will probably break when dict is asked
                    log('Parallel parsing of {} idf file(s) completed in {:,.2f} seconds'.format(len(files),
                                                                                                 time.time() -
                                                                                                 start_time))
            else:
                raise Exception('User asked not to run in parallel')
        except Exception as e:
            # multiprocessing not present so pass the jobs one at a time
            log('Cannot use parallel load. Error with the following exception:\n{}'.format(e))
            idfs = {}
            start_time = time.time()
            for file in files:
                eplus_finename = os.path.basename(file)
                idf_object = eppy_load(file, idd_filename[file])
                idfs[eplus_finename] = idf_object
            log('Parsed {} idf file(s) sequentially in {:,.2f} seconds'.format(len(files), time.time() - start_time))
        if as_dict:
            return idfs
        return list(idfs.values())


def eppy_load_pool(args):
    """
    Wrapper for :py:func:`eppy_load` to perform parallelization.

    :param list args: list of arguments to pass to :py:func:`eppy_load`
    :return: eppy.IDF object
    :rtype: eppy.IDF

    """
    return eppy_load(args[0], args[1])


def eppy_load(file, idd_filename):
    """
    Uses pacakge eppy to parse an idf file. Will also try to upgrade the idf file using the EnergyPlus Transition
    executables.

    :param str file: path to idf file
    :param str idd_filename: path the idd file
    :return: eppy.IDF object
    :rtype: eppy.IDF

    """
    # Initiate an eppy.IDF object
    idf_object = None
    while idf_object is None:
        IDF.setiddname(idd_filename, testing=True)
        try:
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
        # An error could occur if the iddname is not found on the system. Try to upgrade the idf file
        except Exception as e:
            log('{}'.format(e))
            log('Trying to upgrade the file instead...')
            # Try to upgrade the file
            try:
                upgrade_idf(file)
            except Exception as e:
                log(''.format(e))
            else:
                # Get idd file for newly created and upgraded idf file
                idd_filename = getiddfile(get_idf_version(file))
        else:
            # when parsing is complete, save it to disk, then return object
            save_idf_object_to_cache(idf_object, idf_object.idfname)
    return idf_object


def save_idf_object_to_cache(idf_object, idf_file, how='normal'):
    """
    Save IDF instance to a gzip'ed pickle file

    :param eppy.IDF idf_object: an eppy IDF object
    :param str idf_file: file path of idf file

    """
    if settings.use_cache:
        cache_filename = hash_file(idf_file)
        cache_dir = os.path.join(settings.cache_folder, cache_filename)

        # create the folder on the disk if it doesn't already exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        if how.upper() == 'JSON':
            cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename, os.extsep.join([
                cache_filename + 'idfs', 'json']))
            import gzip, json
            with open(cache_fullpath_filename, 'w') as file_handle:
                json.dump({key: value.__dict__ for key, value in idf_object.idfobjects.items()},
                          file_handle,
                          sort_keys=True, indent=4, check_circular=True)

        elif how.upper() == 'PICKLE':
            # create pickle and dump
            cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename, os.extsep.join([
                cache_filename + 'idfs', 'gzip']))
            import gzip
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            with gzip.GzipFile(cache_fullpath_filename, 'wb') as file_handle:
                pickle.dump(idf_object, file_handle, protocol=0)
            log('Saved pickle to file in {:,.2f} seconds'.format(time.time() - start_time))

        else:
            cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename, os.extsep.join([
                cache_filename + 'idfs', 'dat']))
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            with open(cache_fullpath_filename, 'wb') as file_handle:
                pickle.dump(idf_object, file_handle, protocol=-1)
            log('Saved pickle to file in {:,.2f} seconds'.format(time.time() - start_time))


def load_idf_object_from_cache(idf_file, how='normal'):
    """
    Load an idf instance from a gzip'ed pickle file

    :param str idf_file: Path of idf file
    :return: Returns eppy.IDF Object from cache
    :rtype: eppy.IDF

    """
    if settings.use_cache:
        cache_filename = hash_file(idf_file)
        if how.upper() == 'JSON':
            cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename, os.extsep.join([
                cache_filename + 'idfs', 'json']))
            import json
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            if os.path.isfile(cache_fullpath_filename):
                with open(cache_fullpath_filename, 'rb') as file_handle:
                    idf = json.load(file_handle)
                log('Loaded "{}" from pickled file in {:,.2f} seconds'.format(os.path.basename(idf_file), time.time() -
                                                                              start_time))
                return idf

        elif how.upper() == 'PICKLE':
            cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename, os.extsep.join([
                cache_filename + 'idfs', 'gzip']))
            import gzip
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            if os.path.isfile(cache_fullpath_filename):
                with gzip.GzipFile(cache_fullpath_filename, 'rb') as file_handle:
                    idf = pickle.load(file_handle)
                log('Loaded "{}" from pickled file in {:,.2f} seconds'.format(os.path.basename(idf_file), time.time() -
                                                                              start_time))
                return idf
        else:
            cache_fullpath_filename = os.path.join(settings.cache_folder, cache_filename, os.extsep.join([
                cache_filename + 'idfs', 'dat']))
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            if os.path.isfile(cache_fullpath_filename):
                with open(cache_fullpath_filename, 'rb') as file_handle:
                    idf = pickle.load(file_handle)
                idf.setiddname(getiddfile(get_idf_version(idf_file)))
                idf.read()
                log('Loaded "{}" from pickled file in {:,.2f} seconds'.format(os.path.basename(idf_file), time.time() -
                                                                              start_time))
                return idf


def prepare_outputs(eplus_file):
    """
    Adds necessary epobjects to the idf file.
    :param eplus_file:
    :return:
    """
    # todo: do we need to do this?
    idfs = load_idf(eplus_file)  # Returns a dict, evan if there is only one file

    eplus_finename = os.path.basename(eplus_file)

    # SQL output
    idfs[eplus_finename].add_object('Output:SQLite'.upper(),
                                    Option_Type='SimpleAndTabular')

    # Output variables
    idfs[eplus_finename].add_object('Output:Variable'.upper(),
                                    Variable_Name='Air System Total Heating Energy',
                                    Reporting_Frequency='hourly')
    idfs[eplus_finename].add_object('Output:Variable'.upper(),
                                    Variable_Name='Air System Total Cooling Energy',
                                    Reporting_Frequency='hourly')

    # Output meters
    idfs[eplus_finename].add_object('OUTPUT:METER',
                                    Key_Name='HeatRejection:EnergyTransfer',
                                    Reporting_Frequency='hourly')
    idfs[eplus_finename].add_object('OUTPUT:METER',
                                    Key_Name='Heating:EnergyTransfer',
                                    Reporting_Frequency='hourly')
    idfs[eplus_finename].add_object('OUTPUT:METER',
                                    Key_Name='Cooling:EnergyTransfer',
                                    Reporting_Frequency='hourly')
    idfs[eplus_finename].add_object('OUTPUT:METER',
                                    Key_Name='Heating:DistrictHeating',
                                    Reporting_Frequency='hourly')
    idfs[eplus_finename].add_object('OUTPUT:METER',
                                    Key_Name='Heating:Electricity',
                                    Reporting_Frequency='hourly')
    idfs[eplus_finename].add_object('OUTPUT:METER',
                                    Key_Name='Heating:Gas',
                                    Reporting_Frequency='hourly')
    idfs[eplus_finename].add_object('OUTPUT:METER',
                                    Key_Name='Cooling:DistrictCooling',
                                    Reporting_Frequency='hourly')
    idfs[eplus_finename].add_object('OUTPUT:METER',
                                    Key_Name='Cooling:Electricity',
                                    Reporting_Frequency='hourly')
    idfs[eplus_finename].add_object('OUTPUT:METER',
                                    Key_Name='Cooling:Gas',
                                    Reporting_Frequency='hourly')


def run_eplus(eplus_files, weather_file, output_folder=None, ep_version=None, output_report='htm', processors=None,
              **kwargs):
    """
    Run an energy plus file and returns the SummaryReports Tables in a return a list of [(title, table), .....]

    :param str,list eplus_files: path to the idf file(s). Can be a list of strings or simply a string
    :param str ep_version: optional, EnergyPlus version to use, eg: 8-9-0
    :param str output_report: 'htm' or 'sql'
    :param str weather_file: path to the weather file
    :param str output_folder: optional, path to the output folder. Will default to the settings.cache_folder value.
    :param int processors: number of processors to use. if > 1, then parallelization will occur
    :return: dict of {title : table <DataFrame>, ...}

    """

    if isinstance(eplus_files, str):
        # Treat str as an array
        eplus_files = [eplus_files]

    # Determine version of idf file by reading the text file
    if ep_version is None:
        versionids = {file: get_idf_version(file) for file in eplus_files}
        idd_filename = {file: getiddfile(get_idf_version(file)) for file in eplus_files}
    else:
        versionids = {eplus_file: str(ep_version) for eplus_file in eplus_files}
        idd_filename = {eplus_file: getiddfile(ep_version) for eplus_file in eplus_files}

    # Output folder check
    if not output_folder:
        output_folder = os.path.abspath(settings.cache_folder)
    # create the folder on the disk if it doesn't already exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    log('Output folder set to {}'.format(output_folder))

    # Create a {filename:dirname} dict
    dirnames = {os.path.basename(path): os.path.dirname(path) for path in eplus_files}

    # Check if idf file has necessary objects (eg specific outputs)
    for eplus_file in eplus_files:
        log('Preparing outputs...\n', lg.INFO)
        prepare_outputs(eplus_file)
        log('Preparing outputs completed', lg.INFO)
    # Try to get cached results
    processed_cache = []
    for eplus_file in eplus_files:
        processed_cache.append([eplus_file, output_report, kwargs])
    try:
        if processors:
            start_time = time.time()
            import concurrent.futures
            with concurrent.futures.ProcessPoolExecutor(max_workers=processors) as executor:
                cached_run_results = {os.path.basename(eplus_finename): result for eplus_finename, result in
                                      zip(eplus_files, executor.map(get_from_cache_pool, processed_cache))}
                log('Parallel parsing completed in {:,.2f} seconds'.format(time.time() - start_time))
        else:
            raise Exception('User asked not to run in parallel')
    except Exception as e:
        # multiprocessing not present so pass the jobs one at a time
        log('Cannot use parallel runs. Error with the following exception:\n{}'.format(e))
        cached_run_results = {}
        start_time = time.time()
        for eplus_file in eplus_files:
            eplus_finename = os.path.basename(eplus_file)
            cached_run_results[eplus_finename] = get_from_cache(eplus_file, output_report, **kwargs)
        log('Parsing completed in {:,.2f} seconds'.format(time.time() - start_time))

    # Check if retrieved cached results than run for other files with no cached results
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
        eplus_files = [os.path.join(dirnames[run], run) for run in runs_not_found]

        start_time = time.time()
        if processors <= 0:
            processors = max(1, mp.cpu_count() - processors)

        from shutil import copyfile
        processed_runs = []
        for eplus_file in eplus_files:
            # hash the eplus_file (to make shorter than the often extremely long name)
            filename_prefix = hash_file(eplus_file)
            epw = weather_file
            kwargs = {'output_directory': output_folder + '/{}'.format(filename_prefix),
                      'ep_version': versionids[eplus_file],
                      'output_prefix': filename_prefix,
                      'idd': idd_filename[eplus_file],
                      'annual': True}
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
            if processors > 1:
                pool = mp.Pool(processors)
                pool.map(multirunner, processed_runs)
                pool.close()
            else:
                raise Exception('User asked not to run in parallel')
        except Exception as e:
            # multiprocessing not present so pass the jobs one at a time
            log('Cannot use parallel runs. Error with the following exception:\n{}'.format(e))
            for job in processed_runs:
                multirunner(job)
        log('Completed EnergyPlus in {:,.2f} seconds'.format(time.time() - start_time))
        # Return summary DataFrames
        for eplus_file in eplus_files:
            eplus_finename = os.path.basename(eplus_file)
            runs_found[eplus_finename] = get_report(eplus_file, output_folder, output_report, **kwargs)
        return runs_found


def multirunner(args):
    """
    Wrapper for run() to be used when running IDF and EPW runs in parallel.

    :param list args: A list made up of a two-item list (IDF and EPW) and a kwargs dict.

    """
    try:
        run(*args[0], **args[1])
    except Exception as e:
        # Get error file
        log('Error: {}'.format(e))
        try:
            error_filename = os.path.join(args[1]['output_directory'], args[1]['output_prefix'] + 'out.err')
            if os.path.isfile(error_filename):
                with open(error_filename, 'r') as fin:
                    log('\nError File for {} begins here...\n'.format(os.path.basename(args[0][0])), lg.ERROR)
                    log(fin.read(), lg.ERROR)
                    log('\nError File for {} ends here...\n'.format(os.path.basename(args[0][0])), lg.ERROR)
        except:
            log('Could not find error file', lg.ERROR)


def get_from_cache_pool(args):
    """Wrapper for :py:func:`get_from_cache` to be used when loading in parallel.

    :param list args: A list made up of arguments.
    :return: dict of {title : table <DataFrame>, .....}
    :rtype: dict

    """
    return get_from_cache(args[0], args[1])  # Todo: Settup arguments as Locals()


def hash_file(eplus_file):
    """
    Simple function to hash a file and return it as a string.

    :param str eplus_file: the path to the idf file
    :return: hashed file string
    :rtype: str

    TODO: Hashing only the idf file can cause issues when external files are used (and have changed) because hashing will not capture this change

    """
    hasher = hashlib.md5()
    with open(eplus_file, 'rb') as afile:
        buf = afile.read()
        hasher.update(buf)
    return hasher.hexdigest()


def get_report(eplus_file, output_folder=None, output_report='htm', **kwargs):
    """
    returns the specified report format (html or sql)

    :param str eplus_file:
    :param str output_folder: optional,
    :param str output_report: 'htm' or 'sql'
    :param kwargs: keyword arguments to pass to other functions
    :return: the specified report format (html or sql)

    """
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

    :param str output_report: the eplus output file extension eg. 'htm' or 'sql'
    :param str eplus_file: the name of the eplus file
    :return: dict of {title : table <DataFrame>, .....}
    :rtype: dict

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

    :param str report_fullpath: full path to the report file
    :return: dict of {title : table <DataFrame>,...}
    :rtype: dict

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

    :param list reports_list: a list of [(title, table),...]
    :return: a dict of {title: table <DataFrame>}
    :rtype: dict

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
    """
    Connects to the EnergyPlus SQL output file and retreives all tables.

    :param report_file:
    :param report_tables:
    :return: dict of DataFrames
    :rtype: dict,pandas.DataFrame
    """
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


def upgrade_idf(files):
    """
    upgrade the idf file to the latest version

    :param str,list files: path or list of paths to the idf file(s)

    """
    # Check if files is a str and put in a list
    if isinstance(files, str):
        files = [files]

    for file in files:
        try:
            perform_transition(file)
        except Exception as e:
            log(''.format(e))


def perform_transition(file):
    versionid = get_idf_version(file, doted=False)

    trans_exec = {'1-0-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-0-0-to-V1-0-1',
                  '1-0-1': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-0-1-to-V1-0-2',
                  '1-0-2': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-0-2-to-V1-0-3',
                  '1-0-3': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-0-3-to-V1-1-0',
                  '1-1-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-1-0-to-V1-1-1',
                  '1-1-1': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-1-1-to-V1-2-0',
                  '1-2-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-2-0-to-V1-2-1',
                  '1-2-1': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-2-1-to-V1-2-2',
                  '1-2-2': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-2-2-to-V1-2-3',
                  '1-2-3': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-2-3-to-V1-3-0',
                  '1-3-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-3-0-to-V1-4-0',
                  '1-4-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V1-4-0-to-V2-0-0',
                  '2-0-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V2-0-0-to-V2-1-0',
                  '2-1-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V2-1-0-to-V2-2-0',
                  '2-2-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V2-2-0-to-V3-0-0',
                  '3-0-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V3-0-0-to-V3-1-0',
                  '3-1-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V3-1-0-to-V4-0-0',
                  '4-0-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V4-0-0-to-V5-0-0',
                  '5-0-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V5-0-0-to-V6-0-0',
                  '6-0-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V6-0-0-to-V7-0-0',
                  '7-0-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V7-0-0-to-V7-1-0',
                  '7-1-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V7-1-0-to-V7-2-0',
                  '7-2-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V7-2-0-to-V8-0-0',
                  '8-0-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V8-0-0-to-V8-1-0',
                  '8-1-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V8-1-0-to-V8-2-0',
                  '8-2-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V8-2-0-to-V8-3-0',
                  '8-3-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V8-3-0-to-V8-4-0',
                  '8-4-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V8-4-0-to-V8-5-0',
                  '8-5-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V8-5-0-to-V8-6-0',
                  '8-6-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V8-6-0-to-V8-7-0',
                  '8-7-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V8-7-0-to-V8-8-0',
                  '8-8-0': '/Applications/EnergyPlus-8-9-0/PreProcess/IDFVersionUpdater/Transition-V8-8-0-to-V8-9-0',
                  }
    file = os.path.abspath(file)
    # store the directory we start in
    cwd = os.getcwd()
    run_dir = os.path.abspath(os.path.dirname(trans_exec[versionid]))
    os.chdir(run_dir)

    # build a list of command line arguments

    #
    result = None
    while result is None:
        try:
            trans_exec[versionid]
        except Exception:
            result = 0
            os.chdir(cwd)  # Change back the directory
        else:
            cmd = [trans_exec[versionid], file]
            try:
                check_call(cmd)
            except CalledProcessError as e:
                # potentially catch contents of std out and put it in the error log
                log(''.format(e), lg.ERROR)
            else:
                # load new version id and continue loop
                versionid = get_idf_version(file, doted=False)

    log('Transition completed\n')
    # Clean 'idfnew' and 'idfold' files created by the transition porgram
    files_to_delete = glob.glob(os.path.dirname(file) + '/*.idfnew')
    files_to_delete.extend(glob.glob(os.path.dirname(file) + '/*.idfold'))
    files_to_delete.extend(glob.glob(os.path.dirname(file) + '/*.VCpErr'))  # Remove error files since logged to console
    for file in files_to_delete:
        if os.path.isfile(file):
            os.remove(file)


def get_idf_version(file, doted=True):
    """
    Get idf version quickly by reading first few lines of idf file containing the 'VERSION' identifier

    :param str file: Absolute or relative Path to the idf file
    :param bool doted: Wheter or not to return the version number with periods or dashes eg.: 8.9 vs 8-9-0. Doted=False
        appends -0 to the end of the version number
    :return: The version id
    :rtype: str

    """
    with open(file, 'r', encoding='latin-1') as fhandle:
        try:
            txt = fhandle.read()
            ntxt = parse_idd.nocomment(txt, '!')
            blocks = ntxt.split(';')
            blocks = [block.strip() for block in blocks]
            bblocks = [block.split(',') for block in blocks]
            bblocks1 = [[item.strip() for item in block] for block in bblocks]
            ver_blocks = [block for block in bblocks1
                          if block[0].upper() == 'VERSION']
            ver_block = ver_blocks[0]
            if doted:
                versionid = ver_block[1]
            else:
                versionid = ver_block[1].replace('.', '-') + '-0'
        except Exception as e:
            log('Version id for file "{}" cannot be found'.format(file))
            log(''.format(e))
            raise
        else:
            return versionid


class IDF(eppy.modeleditor.IDF):

    def add_object(self, ep_object, **kwargs):
        """
        Add a new object to an idf file. The function will test of the object exists to prevent duplicates.

        :param eppy.IDF self: the load idf object
        :param str ep_object: the object name to add, eg. 'OUTPUT:METER' (Must be in all_caps)
        """
        # get list of objects
        objs = self.idfobjects[ep_object]  # a list
        # create new object
        new_object = self.newidfobject(ep_object, **kwargs)
        # Check if new object exists in previous list
        # If True, delete the object
        if sum([obj == new_object for obj in objs]) > 1:
            log('object "{}" already exists in idf file'.format(ep_object), lg.WARNING)
            # Remove the newly created object since the function `idf.newidfobject()` automatically adds it
            self.removeidfobject(new_object)
        else:
            self.save()
