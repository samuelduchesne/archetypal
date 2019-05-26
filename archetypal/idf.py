################################################################################
# Module: idf.py
# Description: Various functions for processing of EnergyPlus models and
#              retrieving results in different forms
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import datetime
import glob
import hashlib
import logging as lg
import multiprocessing
import os
import subprocess
import tempfile
import time
from subprocess import CalledProcessError

import eppy
import eppy.runner.run_functions
import pandas as pd
from eppy.EPlusInterfaceFunctions import parse_idd
from eppy.easyopen import getiddfile
from path import Path, tempdir

from archetypal import IDF
from archetypal import settings
from archetypal.utils import log, cd, EnergyPlusProcessError

try:
    import multiprocessing as mp
except ImportError:
    pass

EPLUS_PATH = None


def object_from_idfs(idfs, ep_object, first_occurrence_only=False,
                     processors=1):
    """Takes a list of parsed IDF objects and a single ep_object and returns
    a DataFrame.

    Args:
        idfs (list of dict of IDF): List or Dict of IDF objects
        ep_object (str): EnergyPlus object eg. 'WINDOWMATERIAL:GAS' as a
            string. **Most be in all caps.**
        first_occurrence_only (bool, optional): if true, returns only the
            first occurence of the object
        processors (int, optional): specify how many processors to use for a
            parallel run

    Returns:
        pandas.DataFrame: A DataFrame

    """
    if not isinstance(idfs, (list, dict)):
        idfs = [idfs]
    container = []
    start_time = time.time()
    log('Parsing {1} objects for {0} idf files...'.format(len(idfs), ep_object))
    if isinstance(idfs, dict):
        try:
            if processors == 1:
                raise Exception('Loading objects sequentially...')
            log('Loading objects in parallel...')
            # Loading objects in parallel is actually slower at the moment,
            # so we raise an Exception
            runs = [[idf, ep_object] for idfname, idf in idfs.items()]
            import concurrent.futures
            with concurrent.futures.ProcessPoolExecutor(
                    max_workers=processors) as executor:
                container = {idfname: result for (idfname, idf), result in
                             zip(idfs.items(), executor.map(
                                 object_from_idf_pool, runs))}
        except Exception as e:
            # multiprocessing not present so pass the jobs one at a time
            log('{}'.format(e))
            container = {}
            for key, idf in idfs.items():
                # Load objects from IDF files and concatenate
                this_frame = object_from_idf(idf, ep_object)
                container[key] = this_frame

        # If keys given, construct hierarchical index using the passed keys
        # as the outermost level
        this_frame = pd.concat(container, names=['Archetype', '$id'], sort=True)
        this_frame.reset_index(inplace=True)
        this_frame.drop(columns='$id', inplace=True)
    else:
        for idf in idfs:
            # Load objects from IDF files and concatenate
            this_frame = object_from_idf(idf, ep_object)
            container.append(this_frame)
        # Concat the list of DataFrames
        this_frame = pd.concat(container)

    if first_occurrence_only:
        this_frame = this_frame.groupby('Name').first()
    this_frame.reset_index(inplace=True)
    this_frame.index.rename('$id', inplace=True)
    log('Parsed {} {} object(s) in {} idf file(s) in {:,.2f} seconds'.format(
        len(this_frame), ep_object, len(idfs),
        time.time() - start_time))
    return this_frame


def object_from_idf_pool(args):
    """Wrapper for :py:func:`object_from_idf` to use in parallel calls

    Args:
        args (list): List of arguments to pass to :func:`object_from_idf`

    Returns:
        list: A list of DataFrames

    """
    return object_from_idf(args[0], args[1])


def object_from_idf(idf, ep_object):
    """Takes one parsed IDF object and a single ep_object and returns a
    DataFrame.

    Args:
        idf (eppy.modeleditor.IDF): a parsed eppy object
        ep_object (str): EnergyPlus object eg. 'WINDOWMATERIAL:GAS' as a
            string. **Most be in all caps.**

    Returns:
        pandas.DataFrame: A DataFrame. Returns an empty DataFrame if
            ep_object is not found in file.

    """
    try:
        df = pd.concat(
            [pd.DataFrame(
                obj.fieldvalues, index=obj.fieldnames[0:len(obj.fieldvalues)]).T
             for obj in
             idf.idfobjects[ep_object]],
            ignore_index=True, sort=False)
    except ValueError:
        log(
            'ValueError: EP object "{}" does not exist in frame for idf "{}. '
            'Returning empty DataFrame"'.format(
                ep_object, idf.idfname), lg.WARNING)
        return pd.DataFrame({ep_object: []})
    else:
        return df


def load_idf(eplus_file, idd_filename=None, output_folder=None):
    """Returns a parsed IDF object from file. If
    *archetypal.settings.use_cache* is true, then the idf object is loaded
    from cache.

    Args:
        output_folder (Path):
        eplus_file (str): path of the idf file.
        idd_filename (str, optional): name of the EnergyPlus IDD file. If
            None, the function tries to find it.

    Returns:
        (IDF): The parsed IDF object
    """
    # Determine version of idf file by reading the text file
    if idd_filename is None:
        idd_filename = getiddfile(get_idf_version(eplus_file))

    idf = load_idf_object_from_cache(eplus_file)

    start_time = time.time()
    if idf:
        # if found in cache, return
        log('Eppy load from cache completed in {:,.2f} seconds\n'.format(
            time.time() - start_time))
        return idf
    else:
        # Else, run eppy to load the idf objects
        idf = eppy_load(eplus_file, idd_filename, output_folder=output_folder)
        log('Eppy load completed in {:,.2f} seconds\n'.format(
            time.time() - start_time))
        return idf


def eppy_load(file, idd_filename, output_folder=None):
    """Uses package eppy to parse an idf file. Will also try to upgrade the
    idf file using the EnergyPlus Transition executables if the version of
    EnergyPlus is not installed on the machine.

    Args:
        file (str): path of the idf file
        idd_filename: path of the EnergyPlus IDD file

    Returns:
        eppy.modeleditor.IDF: IDF object

    """
    file = Path(file)
    cache_filename = hash_file(file)

    # Initiate an eppy.modeleditor.IDF object
    IDF.setiddname(idd_filename, testing=True)
    if not output_folder:
        output_folder = settings.cache_folder / cache_filename
    output_folder.makedirs_p()

    try:
        # first copy the file
        try:
            file = file.copy(output_folder)
        except:
            # The file already exists at the location
            pass
        # load the idf object
        idf_object = IDF(file)
        # Check version of IDF file against version of IDD file
        idf_version = idf_object.idfobjects['VERSION'][0].Version_Identifier
        idd_version = '{}.{}'.format(idf_object.idd_version[0],
                                     idf_object.idd_version[1])
    except FileNotFoundError as exception:
        # Loading the idf object will raise a FileNotFoundError if the
        # version of EnergyPlus is not included
        log('Transitioning idf file {}'.format(file))
        # if they don't fit, upgrade file
        file = idf_version_updater(file, out_dir=output_folder)
        idd_filename = getiddfile(get_idf_version(file))
        IDF.iddname = idd_filename
        idf_object = IDF(file)
    else:
        # the versions fit, great!
        log('The version of the IDF file "{}", version "{}", matched the '
            'version of EnergyPlus {}, version "{}", used to parse it.'.format(
            file.basename(), idf_version, idf_object.getiddname(), idd_version),
            level=lg.DEBUG)
    # when parsing is complete, save it to disk, then return object
    save_idf_object_to_cache(idf_object, idf_object.idfname,
                             output_folder)
    return idf_object


def save_idf_object_to_cache(idf_object, idf_file, output_folder=None,
                             how=None):
    """Saves the object to disk. Essentially uses the pickling functions of
    python.

    Args:
        output_folder (Path): temporary output directory (default:
            settings.cache_folder)
        idf_object (eppy.modeleditor.IDF): an eppy IDF object
        idf_file (str): file path of idf file
        how (str, optional): How the pickling is done. Choices are 'json' or
            'pickle'. json dump doen't quite work yet. 'pickle' will save to a
            gzip'ed file instead of a regular binary file (.dat).

    Returns:
        None

    Todo:
        * Json dump does not work yet.
    """
    # upper() can't take NoneType as input.
    if how is None:
        how = ''
    # The main function
    if settings.use_cache:
        if output_folder is None:
            output_folder = hash_file(idf_file)
            cache_dir = os.path.join(settings.cache_folder, output_folder)
        cache_dir = output_folder

        # create the folder on the disk if it doesn't already exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        if how.upper() == 'JSON':
            cache_fullpath_filename = cache_dir / cache_dir.basename() + \
                                      'idfs.json'
            import gzip, json
            with open(cache_fullpath_filename, 'w') as file_handle:
                json.dump({key: value.__dict__ for key, value in
                           idf_object.idfobjects.items()},
                          file_handle,
                          sort_keys=True, indent=4, check_circular=True)

        elif how.upper() == 'PICKLE':
            # create pickle and dump
            cache_fullpath_filename = cache_dir / cache_dir.basename() + \
                                      'idfs.gzip'
            import gzip
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            with gzip.GzipFile(cache_fullpath_filename, 'wb') as file_handle:
                pickle.dump(idf_object, file_handle, protocol=0)
            log('Saved pickle to file in {:,.2f} seconds'.format(
                time.time() - start_time))

        else:
            cache_fullpath_filename = cache_dir / cache_dir.basename() + \
                                      'idfs.dat'
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            with open(cache_fullpath_filename, 'wb') as file_handle:
                pickle.dump(idf_object, file_handle, protocol=-1)
            log('Saved pickle to file in {:,.2f} seconds'.format(
                time.time() - start_time))


def load_idf_object_from_cache(idf_file, how=None):
    """Load an idf instance from cache

    Args:
        idf_file (str): path to the idf file
        how (str, optional): How the pickling is done. Choices are 'json' or
            'pickle' or 'idf'. json dump doen't quite work yet. 'pickle' will
            load from a gzip'ed file instead of a regular binary file (.dat).
            'idf' will load from idf file saved in cache.

    Returns:
        None
    """
    # upper() can't tahe NoneType as input.
    if how is None:
        how = ''
    # The main function
    if settings.use_cache:
        cache_filename = hash_file(idf_file)
        if how.upper() == 'JSON':
            cache_fullpath_filename = os.path.join(settings.cache_folder,
                                                   cache_filename,
                                                   os.extsep.join([
                                                       cache_filename + 'idfs',
                                                       'json']))
            import json
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            if os.path.isfile(cache_fullpath_filename):
                with open(cache_fullpath_filename, 'rb') as file_handle:
                    idf = json.load(file_handle)
                log('Loaded "{}" from pickled file in {:,.2f} seconds'.format(
                    os.path.basename(idf_file), time.time() -
                                                start_time))
                return idf

        elif how.upper() == 'PICKLE':
            cache_fullpath_filename = os.path.join(settings.cache_folder,
                                                   cache_filename,
                                                   os.extsep.join([
                                                       cache_filename + 'idfs',
                                                       'gzip']))
            import gzip
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            if os.path.isfile(cache_fullpath_filename):
                with gzip.GzipFile(cache_fullpath_filename,
                                   'rb') as file_handle:
                    idf = pickle.load(file_handle)
                if idf.iddname is None:
                    idf.setiddname(getiddfile(idf.model.dt['VERSION'][0][1]))
                    # idf.read()
                log('Loaded "{}" from pickled file in {:,.2f} seconds'.format(
                    os.path.basename(idf_file), time.time() -
                                                start_time))
                return idf
        elif how.upper() == 'IDF':
            cache_fullpath_filename = os.path.join(settings.cache_folder,
                                                   cache_filename,
                                                   os.extsep.join([
                                                       cache_filename,
                                                       'idf']))
            if os.path.isfile(cache_fullpath_filename):
                version = get_idf_version(cache_fullpath_filename, doted=True)
                iddfilename = getiddfile(version)
                idf = eppy_load(cache_fullpath_filename, iddfilename)
                return idf
        else:
            cache_fullpath_filename = os.path.join(settings.cache_folder,
                                                   cache_filename,
                                                   os.extsep.join([
                                                       cache_filename + 'idfs',
                                                       'dat']))
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            if os.path.isfile(cache_fullpath_filename):
                with open(cache_fullpath_filename, 'rb') as file_handle:
                    idf = pickle.load(file_handle)
                if idf.iddname is None:
                    idf.setiddname(getiddfile(idf.model.dt['VERSION'][0][1]))
                    idf.read()
                log('Loaded "{}" from pickled file in {:,.2f} seconds'.format(
                    os.path.basename(idf_file), time.time() - start_time))
                return idf


def prepare_outputs(eplus_file, outputs=None, idd_filename=None,
                    output_folder=None, save=True):
    """Add additional epobjects to the idf file. Users can pass in an outputs

    Args:
        save (bool): if True, saves the idf inplace to disk with added objects
        eplus_file (Path): the file describing the model (.idf)
        outputs (bool or list):

    Examples:
        >>> objects = [{'ep_object':'OUTPUT:DIAGNOSTICS',
        >>>             'kwargs':{'Key_1':'DisplayUnusedSchedules'}}]
        >>> prepare_outputs(eplus_file, outputs=objects)

    """

    log('first, loading the idf file')
    idf = load_idf(eplus_file, idd_filename=idd_filename,
                   output_folder=output_folder)

    if isinstance(outputs, list):
        for output in outputs:
            idf.add_object(output['ep_object'], **output[
                'kwargs'], save=save)

    # SummaryReports
    idf.add_object('Output:Table:SummaryReports'.upper(),
                   Report_1_Name='AllSummary', save=save)

    # SQL output
    idf.add_object('Output:SQLite'.upper(),
                   Option_Type='SimpleAndTabular', save=save)

    # Output variables
    idf.add_object('Output:Variable'.upper(),
                   Variable_Name='Air System Total Heating '
                                 'Energy',
                   Reporting_Frequency='hourly', save=save)
    idf.add_object('Output:Variable'.upper(),
                   Variable_Name='Air System Total Cooling '
                                 'Energy',
                   Reporting_Frequency='hourly', save=save)

    # Output meters
    idf.add_object('OUTPUT:METER',
                   Key_Name='HeatRejection:EnergyTransfer',
                   Reporting_Frequency='hourly', save=save)
    idf.add_object('OUTPUT:METER',
                   Key_Name='Heating:EnergyTransfer',
                   Reporting_Frequency='hourly', save=save)
    idf.add_object('OUTPUT:METER',
                   Key_Name='Cooling:EnergyTransfer',
                   Reporting_Frequency='hourly', save=save)
    idf.add_object('OUTPUT:METER',
                   Key_Name='Heating:DistrictHeating',
                   Reporting_Frequency='hourly', save=save)
    idf.add_object('OUTPUT:METER',
                   Key_Name='Heating:Electricity',
                   Reporting_Frequency='hourly', save=save)
    idf.add_object('OUTPUT:METER',
                   Key_Name='Heating:Gas',
                   Reporting_Frequency='hourly', save=save)
    idf.add_object('OUTPUT:METER',
                   Key_Name='Cooling:DistrictCooling',
                   Reporting_Frequency='hourly', save=save)
    idf.add_object('OUTPUT:METER',
                   Key_Name='Cooling:Electricity',
                   Reporting_Frequency='hourly', save=save)
    idf.add_object('OUTPUT:METER',
                   Key_Name='Cooling:Gas',
                   Reporting_Frequency='hourly', save=save)


def cache_runargs(eplus_file, runargs):
    import json
    output_directory = runargs['output_directory']

    runargs.update({'run_time': datetime.datetime.now().isoformat()})
    runargs.update({'idf_file': eplus_file})
    with open(os.path.join(output_directory, 'runargs.json'), 'w') as fp:
        json.dump(runargs, fp, sort_keys=True, indent=4)


def run_eplus(eplus_file, weather_file, output_folder=None,
              ep_version=None, output_report=None, prep_outputs=False,
              simulname=None, keep_data=True, **kwargs):
    """Run an energy plus file and return the SummaryReports Tables in a list
    of [(title, table), .....]

    Args:
        eplus_file (str): path to the idf file.
        weather_file (str): path to the EPW weather file
        output_folder (str, optional): path to the output folder. Will default
            to the settings.cache_folder.
        ep_version (str, optional): EnergyPlus version to use, eg: 8-9-0
        output_report: 'htm' or 'sql'.
        prep_outputs (bool or list, optional): if true, meters and variable
            outputs will be appended to the idf files. see
            :func:`prepare_outputs`
        **kwargs: keyword arguments to pass to other functions (see below)

    Returns:
        dict: dict of [(title, table), .....]

    Keyword Args:
        annual (bool): If True then force annual simulation (default: False)
        design_day (bool): Force design-day-only simulation (default: False)
        epmacro (bool): Run EPMacro prior to simulation (default: False)
        expandobjects (bool): Run ExpandObjects prior to simulation (default:
            False)
        readvars (bool): Run ReadVarsESO after simulation (default: False)
        output_prefix (str): Prefix for output file names
        verbose (str):
        idf : str
        output_suffix (str, optional): Suffix style for output file names
            (default: L)
                L: Legacy (e.g., eplustbl.csv)
                C: Capital (e.g., eplusTable.csv)
                D: Dash (e.g., eplus-table.csv)
        version (bool, optional): Display version information (default: False)
        verbose (str): Set verbosity of runtime messages (default: v)
            v: verbose
            q: quiet
    """
    eplus_file = Path(eplus_file)
    weather_file = Path(weather_file)
    if not simulname:
        cache_filename = hash_file(eplus_file, kwargs)
        simulname = cache_filename
    else:
        cache_filename = simulname
    if not output_folder:
        output_folder = settings.cache_folder / cache_filename
    else:
        output_folder = Path(output_folder)

    # <editor-fold desc="Try to get cached results">
    try:
        start_time = time.time()
        cached_run_results = get_from_cache(eplus_file, output_report,
                                            output_folder, **kwargs)
    except Exception as e:
        # catch other exceptions that could occur
        raise Exception('{}'.format(e))
    else:
        if cached_run_results:
            # if cached run found, simply return it
            log('Succesfully parsed cached idf run in {:,.2f} seconds'.format(
                time.time() - start_time))
            return cached_run_results

    runs_not_found = eplus_file
    # </editor-fold>

    # <editor-fold desc="Upgrade the file version if needed">
    if ep_version:
        # replace the dots with "-"
        ep_version = ep_version.replace(".", "-")
    eplus_file = idf_version_updater(eplus_file, to_version=ep_version,
                                     out_dir=output_folder)
    # In case the file has been updated, update the versionid of the file
    # and the idd_file
    versionid = get_idf_version(eplus_file, doted=False)
    idd_file = Path(getiddfile(get_idf_version(eplus_file, doted=True)))
    # </editor-fold>

    # Prepare outputs e.g. sql table
    if prep_outputs:
        # Check if idf file has necessary objects (eg specific outputs)
        prepare_outputs(eplus_file, prep_outputs, idd_file, output_folder)

    if runs_not_found:
        # continue with simulation of other files
        log('no cached run for {}. Running EnergyPlus...'.format(
            os.path.basename(eplus_file)))

        start_time = time.time()
        processed_runs = {}

        # used the hash of the original file (unmodified)
        filename_prefix = kwargs.get('output_prefix', cache_filename)
        runargs = {'idf': eplus_file.abspath(),
                   'weather': weather_file.abspath(),
                   'verbose': 'q',
                   'output_directory': output_folder.abspath(),
                   'ep_version': versionid,
                   'output_prefix': filename_prefix,
                   'idd': idd_file.abspath()}
        runargs.update(kwargs)

        # save runargs
        cache_runargs(eplus_file, runargs.copy())

        # run the EnergyPlus Simulation
        with tempdir(prefix="eplus_run_", suffix=simulname,
                     dir=output_folder) as tmp:
            runargs['idf'] = runargs['idf'].copy(tmp)
            runargs['output_directory'] = tmp

            _multirunner(**runargs)

            log('EnergyPlus Completed Successfully in {:,.2f} seconds'.format(
                time.time() - start_time))

            log(
                "Files generated at the end of the simulation: %s" % " ".join(
                    tmp.files()),
                lg.DEBUG
            )

            # Return summary DataFrames
            cacheargs = {'eplus_file': eplus_file,
                         'output_folder': tmp,
                         'output_report': output_report,
                         'filename_prefix': cache_filename,
                         **kwargs}

            cached_run_results = get_report(**cacheargs)

            if keep_data:
                (output_folder / "output_data").rmtree_p()
                tmp.copytree(output_folder / "output_data")

            return cached_run_results


def _multirunner(**kwargs):
    """Wrapper around the :func:`eppy.runner.run_functions.run` to be used when
    running EnergyPlus.
    """
    try:
        run(**kwargs)
    except TypeError as e:
        log('{}'.format(e), lg.ERROR)
        raise TypeError('{}'.format(e))
    except CalledProcessError as e:
        # Get error file
        log('{}'.format(e), lg.ERROR)

        output_dir = kwargs['output_directory']
        error_filename = output_dir / output_dir.basename() + 'out.err'
        if os.path.isfile(error_filename):
            idf_name = os.path.basename(kwargs['idf'])
            with open(error_filename, 'r') as fin:
                log('\nError File for "{}" begins here...\n'.format(
                    idf_name), lg.ERROR)
                log(fin.read(), lg.ERROR)
                log('Error File for "{}" ends here...\n'.format(
                    idf_name), lg.ERROR)
            with open(error_filename, 'r') as stderr:
                raise EnergyPlusProcessError(cmd=e.cmd,
                                             idf=idf_name,
                                             stderr=stderr.read())
        else:
            log('Could not find error file', lg.ERROR)


def run(idf=None, weather=None, output_directory='', annual=False,
        design_day=False, idd=None, epmacro=False, expandobjects=False,
        readvars=False, output_prefix=None, output_suffix=None, version=False,
        verbose='v', ep_version=None):
    """
    Wrapper around the EnergyPlus command line interface.

    Parameters
    ----------
    idf : str
        Full or relative path to the IDF file to be run, or an IDF object.

    weather : str
        Full or relative path to the weather file.

    output_directory : str, optional
        Full or relative path to an output directory (default: 'run_outputs)

    annual : bool, optional
        If True then force annual simulation (default: False)

    design_day : bool, optional
        Force design-day-only simulation (default: False)

    idd : str, optional
        Input data dictionary (default: Energy+.idd in EnergyPlus directory)

    epmacro : str, optional
        Run EPMacro prior to simulation (default: False).

    expandobjects : bool, optional
        Run ExpandObjects prior to simulation (default: False)

    readvars : bool, optional
        Run ReadVarsESO after simulation (default: False)

    output_prefix : str, optional
        Prefix for output file names (default: eplus)

    output_suffix : str, optional
        Suffix style for output file names (default: L)
            L: Legacy (e.g., eplustbl.csv)
            C: Capital (e.g., eplusTable.csv)
            D: Dash (e.g., eplus-table.csv)

    version : bool, optional
        Display version information (default: False)

    verbose: str
        Set verbosity of runtime messages (default: v)
            v: verbose
            q: quiet

    ep_version: str
        EnergyPlus version, used to find install directory. Required if run() is
        called with an IDF file path rather than an IDF object.

    Returns
    -------
    str : status

    Raises
    ------
    CalledProcessError

    AttributeError
        If no ep_version parameter is passed when calling with an IDF file path
        rather than an IDF object.


    """
    args = locals().copy()
    # get unneeded params out of args ready to pass the rest to energyplus.exe
    verbose = args.pop('verbose')
    idf = args.pop('idf')
    iddname = args.get('idd')
    try:
        idf_path = os.path.abspath(idf.idfname)
    except AttributeError:
        idf_path = os.path.abspath(idf)
    ep_version = args.pop('ep_version')
    # get version from IDF object or by parsing the IDF file for it
    if not ep_version:
        try:
            ep_version = '-'.join(str(x) for x in idf.idd_version[:3])
        except AttributeError:
            raise AttributeError(
                "The ep_version must be set when passing an IDF path. \
                Alternatively, use IDF.run()")

    eplus_exe_path, eplus_weather_path = \
        eppy.runner.run_functions.install_paths(ep_version, iddname)
    if version:
        # just get EnergyPlus version number and return
        cmd = [eplus_exe_path, '--version']
        subprocess.check_call(cmd)
        return

    # convert paths to absolute paths if required
    if os.path.isfile(args['weather']):
        args['weather'] = os.path.abspath(args['weather'])
    else:
        args['weather'] = os.path.join(eplus_weather_path, args['weather'])
    args['output_directory'] = os.path.abspath(args['output_directory'])

    # store the directory we start in
    cwd = os.getcwd()
    run_dir = os.path.abspath(tempfile.mkdtemp())
    os.chdir(run_dir)

    # build a list of command line arguments
    cmd = [eplus_exe_path]
    for arg in args:
        if args[arg]:
            if isinstance(args[arg], bool):
                args[arg] = ''
            cmd.extend(['--{}'.format(arg.replace('_', '-'))])
            if args[arg] != "":
                cmd.extend([args[arg]])
    cmd.extend([idf_path])

    try:
        if verbose == 'v':
            subprocess.check_call(cmd)
        elif verbose == 'q':
            subprocess.check_call(cmd, stdout=open(os.devnull, 'w'))
        os.chdir(cwd)
    except CalledProcessError:
        # potentially catch contents of std out and put it in the error
        raise
    return 'OK'


def parallel_process(in_dict, function, processors=-1, use_kwargs=True):
    """A parallel version of the map function with a progress bar.

    Args:
        in_dict (dict-like): A dictionary to iterate over.
        function (function): A python function to apply to the elements of
            in_dict
        processors (int): The number of cores to use
        use_kwargs (bool): If True, pass the kwargs as arguments to `function`.

    Returns:
        [function(array[0]), function(array[1]), ...]

    Examples:
        >>> import archetypal as ar
        >>> files = ['tests/input_data/problematic/nat_ventilation_SAMPLE0.idf',
        >>>          'tests/input_data/regular/5ZoneNightVent1.idf']
        >>> wf = 'tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw'
        >>> files = ar.copy_file(files)
        >>> rundict = {file: dict(eplus_file=file, weather_file=wf,
        >>>                      ep_version=ep_version, annual=True,
        >>>                      prep_outputs=True, expandobjects=True,
        >>>                      verbose='q', output_report='sql')
        >>>           for file in files}
        >>> result = {file: ar.run_eplus(**rundict[file]) for file in files}

    """
    from tqdm import tqdm
    from concurrent.futures import ProcessPoolExecutor, as_completed

    if processors == -1:
        processors = min(len(in_dict), multiprocessing.cpu_count())

    if processors == 1:
        kwargs = {
            'desc': function.__name__,
            'total': len(in_dict),
            'unit': 'runs',
            'unit_scale': True,
            'leave': True
        }
        if use_kwargs:
            futures = {a: function(**in_dict[a]) for a in tqdm(in_dict,
                                                               **kwargs)}
        else:
            futures = {a: function(in_dict[a]) for a in tqdm(in_dict,
                                                             **kwargs)}
    else:
        with ProcessPoolExecutor(max_workers=processors) as pool:
            if use_kwargs:
                futures = {pool.submit(function, **in_dict[a]): a for a in
                           in_dict}
            else:
                futures = {pool.submit(function, in_dict[a]): a for a in
                           in_dict}

            kwargs = {
                'desc': function.__name__,
                'total': len(futures),
                'unit': 'runs',
                'unit_scale': True,
                'leave': True
            }

            # Print out the progress as tasks complete
            for f in tqdm(as_completed(futures), **kwargs):
                pass
    out = {}
    # Get the results from the futures.
    for key in futures:
        try:
            if processors > 1:
                out[futures[key]] = key.result()
            else:
                out[key] = futures[key]
        except Exception as e:
            log(str(e), lg.ERROR)
            out[futures[key]] = e
    return out


def hash_file(eplus_file, kwargs=None):
    """Simple function to hash a file and return it as a string.
    Will also hash the :py:func:`eppy.runner.run_functions.run()` arguments
    so that correct results are returned
    when different run arguments are used

    Args:
        eplus_file (str): path of the idf file
        **kwargs: keywords to pass to the hasher

    Returns:
        str: The digest value as a string of hexadecimal digits

    Todo:
        Hashing should include the external files used an idf file. For
        example, if a model
        uses a csv file as an input and that file changes, the hashing will
        currently not pickup that change. This
        could result in loading old results without the user knowing.
    """
    hasher = hashlib.md5()
    with open(eplus_file, 'rb') as afile:
        buf = afile.read()
        hasher.update(buf)
        hasher.update(
            kwargs.__str__().encode('utf-8'))  # Hashing the kwargs as well
    return hasher.hexdigest()


def get_report(eplus_file, output_folder=None, output_report='sql',
               filename_prefix=None, **kwargs):
    """Returns the specified report format (html or sql)

    Args:
        filename_prefix:
        eplus_file (str): path of the idf file
        output_folder (str, optional): path to the output folder. Will
            default to the settings.cache_folder.
        output_report: 'html' or 'sql'
        **kwargs: keyword arguments to pass to hasher.

    Returns:
        dict: a dict of DataFrames

    """
    # Hash the idf file with any kwargs used in the function
    if filename_prefix is None:
        filename_prefix = hash_file(eplus_file, kwargs)
    if output_report is None:
        return None
    elif 'htm' in output_report.lower():
        # Get the html report
        fullpath_filename = os.path.join(output_folder, filename_prefix,
                                         os.extsep.join(
                                             [filename_prefix + 'tbl', 'htm']))
        if os.path.isfile(fullpath_filename):
            return get_html_report(fullpath_filename)
        else:
            raise FileNotFoundError(
                'File "{}" does not exist'.format(fullpath_filename))

    elif 'sql' in output_report.lower():
        # Get the sql report
        fullpath_filename = output_folder / filename_prefix + 'out.sql'
        if fullpath_filename.exists():
            return get_sqlite_report(fullpath_filename)
        else:
            raise FileNotFoundError(
                'File "{}" does not exist'.format(fullpath_filename))
    else:
        return None


def get_from_cache(eplus_file, output_report='sql', output_folder=None,
                   **kwargs):
    """Retrieve a EPlus Tabulated Summary run result from the cache

    Args:
        output_folder (str):
        eplus_file (str): the path of the eplus file
        output_report: 'html' or 'sql'
        **kwargs: keyword arguments to pass to other functions.

    Returns:
        dict: dict of DataFrames

    Todo:
        Complete docstring for this function
    """
    if output_folder:
        output_folder = Path(output_folder)

    if settings.use_cache:
        # determine the filename by hashing the eplus_file
        cache_filename_prefix = hash_file(eplus_file, kwargs)
        if output_report is None:
            return None

        elif 'htm' in output_report.lower():

            # Get the html report
            if not output_folder:
                output_folder = settings.cache_folder / cache_filename_prefix

            cache_fullpath_filename = output_folder / \
                                      "output_data" / \
                                      cache_filename_prefix + "tbl.html"
            if os.path.isfile(cache_fullpath_filename):
                return get_html_report(cache_fullpath_filename)

        elif 'sql' in output_report.lower():

            # get the SQL report
            if not output_folder:
                output_folder = settings.cache_folder / cache_filename_prefix

            cache_fullpath_filename = output_folder / \
                                      "output_data" / \
                                      cache_filename_prefix + "out.sql"

            if cache_fullpath_filename.exists():
                # get reports from passed-in report names or from
                # settings.available_sqlite_tables if None are given
                return get_sqlite_report(cache_fullpath_filename,
                                         kwargs.get('report_tables',
                                                    settings.available_sqlite_tables))


def get_html_report(report_fullpath):
    """Parses the html Summary Report for each tables into a dictionary of
    DataFrames

    Args:
        report_fullpath (str): full path to the report file

    Returns:
        dict: dict of {title : table <DataFrame>,...}

    """
    from eppy.results import \
        readhtml  # the eppy module with functions to read the html
    with open(report_fullpath, 'r', encoding='utf-8') as cache_file:
        filehandle = cache_file.read()  # get a file handle to the html file

        cached_tbl = readhtml.titletable(
            filehandle)  # get a file handle to the html file

        log('Retrieved response from cache file "{}"'.format(
            report_fullpath))
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
            key = key + '_'
        df = pd.DataFrame(table[1])
        df = df.rename(columns=df.iloc[0]).drop(df.index[0])
        results_dict[key] = df
    return results_dict


def get_sqlite_report(report_file, report_tables=None):
    """Connects to the EnergyPlus SQL output file and retreives all tables

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
        # create database connection with sqlite3
        with sqlite3.connect(report_file) as conn:
            # empty dict to hold all DataFrames
            all_tables = {}
            # Iterate over all tables in the report_tables list
            for table in report_tables:
                try:
                    all_tables[table] = pd.read_sql_query(
                        "select * from {};".format(table), conn,
                        index_col=report_tables[table]['PrimaryKey'],
                        parse_dates=report_tables[table]['ParseDates'])
                except Exception as e:
                    log('no such table: {}'.format(table), lg.WARNING)

            log('SQL query parsed {} tables as DataFrames from {}'.format(
                len(all_tables), report_file))
            return all_tables


def idf_version_updater(idf_file,
                        to_version=None,
                        out_dir=None,
                        simulname=None):
    """EnergyPlus idf version updater using local transition program.

    Update the EnergyPlus simulation file (.idf) to the latest available
    EnergyPlus version installed on this machine. Optionally specify a
    version (eg.: "8-9-0") to aim for a specific version. The output will be
    the path of the updated file. The run is multiprocessing_safe.

    Args:
        idf_file (Path): path of idf file
        out_dir (Path): path of the output_dir
        to_version (str, optional): EnergyPlus version in the form "X-X-X".
        simulname (str or None, optional): this name will be
            used for temp dir id and saved outputs. If not provided,
            uuid.uuid1() is used. Be careful to avoid naming
            collision : the run will alway be done in separated folders, but the
            output files can overwrite each other if the simulname is the same.
            (default: None)

    Returns:
        str: The path of the transitioned idf file.

    Hint:
        If attempting to upgrade an earlier version of EnergyPlus (
        pre-v7.2.0), specific binaries need to be downloaded and copied to the
        EnergyPlus*/PreProcess/IDFVersionUpdater folder. More info at
        `Converting older version files
        <http://energyplus.helpserve.com/Knowledgebase/List/Index/46
        /converting-older-version-files>`_.
    """
    if not out_dir.isdir():
        out_dir.makedirs_p()
    with tempdir(prefix="transition_run_", suffix=simulname, dir=out_dir) as \
            tmp:
        log("temporary dir (%s) created" % tmp, lg.DEBUG)
        idf_file = idf_file.copy(tmp).abspath()  # copy and return abspath

        versionid = get_idf_version(idf_file, doted=False)[0:5]
        doted_version = get_idf_version(idf_file, doted=True)
        iddfile = getiddfile(doted_version)
        if os.path.exists(iddfile):
            # if a E+ exists, pass
            pass
            # might be an old version of E+
        elif tuple(map(int, doted_version.split('.'))) < (8, 0):
            # else if the version is an old E+ version (< 8.0)
            iddfile = getoldiddfile(doted_version)
        # use to_version
        if to_version is None:
            # What is the latest E+ installed version
            to_version = find_eplus_installs(iddfile)
        if tuple(versionid.split('-')) > tuple(to_version.split('-')):
            log(
                'The version of the idf file "{}: v{}" is higher than any '
                'version of EnergyPlus installed on this machine. Please '
                'install EnergyPlus version "{}" or higher. Latest version '
                'found: {}'.format(
                    os.path.basename(idf_file), versionid, versionid,
                    to_version), lg.WARNING)
            return None
        to_iddfile = Path(getiddfile(to_version.replace('-', '.')))
        vupdater_path = to_iddfile.dirname() / 'PreProcess' / \
                        'IDFVersionUpdater'
        trans_exec = {
            '1-0-0': os.path.join(vupdater_path, 'Transition-V1-0-0-to-V1-0-1'),
            '1-0-1': os.path.join(vupdater_path, 'Transition-V1-0-1-to-V1-0-2'),
            '1-0-2': os.path.join(vupdater_path, 'Transition-V1-0-2-to-V1-0-3'),
            '1-0-3': os.path.join(vupdater_path, 'Transition-V1-0-3-to-V1-1-0'),
            '1-1-0': os.path.join(vupdater_path, 'Transition-V1-1-0-to-V1-1-1'),
            '1-1-1': os.path.join(vupdater_path, 'Transition-V1-1-1-to-V1-2-0'),
            '1-2-0': os.path.join(vupdater_path, 'Transition-V1-2-0-to-V1-2-1'),
            '1-2-1': os.path.join(vupdater_path, 'Transition-V1-2-1-to-V1-2-2'),
            '1-2-2': os.path.join(vupdater_path, 'Transition-V1-2-2-to-V1-2-3'),
            '1-2-3': os.path.join(vupdater_path, 'Transition-V1-2-3-to-V1-3-0'),
            '1-3-0': os.path.join(vupdater_path, 'Transition-V1-3-0-to-V1-4-0'),
            '1-4-0': os.path.join(vupdater_path, 'Transition-V1-4-0-to-V2-0-0'),
            '2-0-0': os.path.join(vupdater_path, 'Transition-V2-0-0-to-V2-1-0'),
            '2-1-0': os.path.join(vupdater_path, 'Transition-V2-1-0-to-V2-2-0'),
            '2-2-0': os.path.join(vupdater_path, 'Transition-V2-2-0-to-V3-0-0'),
            '3-0-0': os.path.join(vupdater_path, 'Transition-V3-0-0-to-V3-1-0'),
            '3-1-0': os.path.join(vupdater_path, 'Transition-V3-1-0-to-V4-0-0'),
            '4-0-0': os.path.join(vupdater_path, 'Transition-V4-0-0-to-V5-0-0'),
            '5-0-0': os.path.join(vupdater_path, 'Transition-V5-0-0-to-V6-0-0'),
            '6-0-0': os.path.join(vupdater_path, 'Transition-V6-0-0-to-V7-0-0'),
            '7-0-0': os.path.join(vupdater_path, 'Transition-V7-0-0-to-V7-1-0'),
            '7-1-0': os.path.join(vupdater_path, 'Transition-V7-1-0-to-V7-2-0'),
            '7-2-0': os.path.join(vupdater_path, 'Transition-V7-2-0-to-V8-0-0'),
            '8-0-0': os.path.join(vupdater_path, 'Transition-V8-0-0-to-V8-1-0'),
            '8-1-0': os.path.join(vupdater_path, 'Transition-V8-1-0-to-V8-2-0'),
            '8-2-0': os.path.join(vupdater_path, 'Transition-V8-2-0-to-V8-3-0'),
            '8-3-0': os.path.join(vupdater_path, 'Transition-V8-3-0-to-V8-4-0'),
            '8-4-0': os.path.join(vupdater_path, 'Transition-V8-4-0-to-V8-5-0'),
            '8-5-0': os.path.join(vupdater_path, 'Transition-V8-5-0-to-V8-6-0'),
            '8-6-0': os.path.join(vupdater_path, 'Transition-V8-6-0-to-V8-7-0'),
            '8-7-0': os.path.join(vupdater_path, 'Transition-V8-7-0-to-V8-8-0'),
            '8-8-0': os.path.join(vupdater_path, 'Transition-V8-8-0-to-V8-9-0'),
            '8-9-0': os.path.join(vupdater_path, 'Transition-V8-9-0-to-V9-0-0'),
            '9-0-0': os.path.join(vupdater_path, 'Transition-V9-0-0-to-V9-1-0'),
        }
        # store the directory we start in
        cwd = os.getcwd()
        run_dir = Path(os.path.dirname(trans_exec[versionid]))

        if versionid == to_version:
            # if file version and to_veersion are the same, we don't need to
            # perform transition
            log('file {} already upgraded to latest version "{}"'.format(
                idf_file, versionid))
            idf_file = idf_file.copy(out_dir)
            return idf_file

        # build a list of command line arguments
        with cd(run_dir):
            transitions = [key for key in trans_exec
                           if tuple(map(int, key.split('-'))) < \
                           tuple(map(int, to_version.split('-')))
                           and tuple(map(int, key.split('-'))) >= \
                           tuple(map(int, versionid.split('-')))]
            for trans in transitions:
                try:
                    trans_exec[trans]
                except KeyError:
                    # there is no more updates to perfrom
                    result = 0
                else:
                    cmd = [trans_exec[trans], idf_file]
                    try:
                        process = subprocess.Popen(
                            cmd,
                            stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT
                        )
                        process_output, error_output = process.communicate()
                        log(process_output.decode('utf-8'), lg.DEBUG)
                    except CalledProcessError as exception:
                        log('{} failed with error\n'.format(
                            idf_version_updater.__name__, str(exception)),
                            lg.ERROR)
        for f in tmp.files('*.idfnew'):
            f.copy(out_dir / idf_file.basename())
        return out_dir / idf_file.basename()


def find_eplus_installs(iddfile):
    """Finds all installed versions of EnergyPlus in the default location and
    returns the latest version number

    Args:
        vupdater_path (str): path of the current EnergyPlus install file

    Returns:
        (str): The version number of the latest E+ install

    """
    vupdater_path, _ = iddfile.split('Energy+')
    path_to_eplus, _ = vupdater_path.split('EnergyPlus')

    # Find all EnergyPlus folders
    list_eplus_dir = glob.glob(os.path.join(path_to_eplus, 'EnergyPlus*'))

    # Find the most recent version of EnergyPlus installed from the version
    # number (at the end of the folder name)
    v0 = (0, 0, 0)  # Initialize the version number
    # Find the most recent version in the different folders found
    for dir in list_eplus_dir:
        version = dir[-5:]
        ver = tuple(map(int, version.split('-')))
        if ver > v0:
            v0 = ver

    return '-'.join(tuple(map(str, v0)))


def get_idf_version(file, doted=True):
    """Get idf version quickly by reading first few lines of idf file
    containing the 'VERSION' identifier

    Args:
        file (str): Absolute or relative Path to the idf file
        doted (bool, optional): Wheter or not to return the version number
        with periods or dashes eg.: 8.9 vs 8-9-0.
            Doted=False appends -0 to the end of the version number

    Returns:
        str: the version id

    """
    with open(os.path.abspath(file), 'r', encoding='latin-1') as fhandle:
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
            log('{}'.format(e))
            raise
        else:
            return versionid


def getoldiddfile(versionid):
    """find the IDD file of the E+ installation
    E+ version 7 and earlier have the idd in
    /EnergyPlus-7-2-0/bin/Energy+.idd """
    vlist = versionid.split('.')
    if len(vlist) == 1:
        vlist = vlist + ['0', '0']
    elif len(vlist) == 2:
        vlist = vlist + ['0']
    ver_str = '-'.join(vlist)
    eplus_exe, _ = eppy.runner.run_functions.install_paths(ver_str)
    eplusfolder = os.path.dirname(eplus_exe)
    iddfile = '{}/bin/Energy+.idd'.format(eplusfolder, )
    return iddfile


schedule_types = ['Schedule:Day:Hourly'.upper(),
                  'Schedule:Day:Interval'.upper(), 'Schedule:Day:List'.upper(),
                  'Schedule:Week:Daily'.upper(), 'Schedule:Year'.upper(),
                  'Schedule:Week:Compact'.upper(), 'Schedule:Compact'.upper(),
                  'Schedule:Constant'.upper(), 'Schedule:File'.upper()]
