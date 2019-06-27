################################################################################
# Module: idfclass.py
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
import time
from subprocess import CalledProcessError, check_call

import eppy
import eppy.modeleditor
import pandas as pd
from eppy.EPlusInterfaceFunctions import parse_idd
from eppy.easyopen import getiddfile
from eppy.runner.run_functions import run

from archetypal import log, settings, EnergyPlusProcessError, cd


class IDF(eppy.modeleditor.IDF):
    """Wrapper over the eppy.modeleditor.IDF class

    """

    def __init__(self, *args, **kwargs):
        super(IDF, self).__init__(*args, **kwargs)
        self.schedules_dict = self.get_all_schedules()
        self.sql = None

    def run_eplus(self, weather_file=None, output_folder=None, ep_version=None,
                  output_report='sql', prep_outputs=True, **kwargs):
        """wrapper around the :func:`archetypal.run_eplus()` method.

        If weather file is defined in the IDF object, then this field is
        optional. By default, will load the sql in self.sql.

        Args:
            weather_file (str, optional): path to the EPW weather file.
            output_folder (str, optional): path to the output folder. Will
                default to the settings.cache_folder.
            ep_version (str, optional): EnergyPlus version to use for the
                simulation, eg: 8-9-0. If the idf file's version is lower than
                the chosen simulation version, then the file will be upgraded
                using :func:`archetypal.perform_transition`.
            output_report (str): 'htm' or 'sql' or None. If None, EnergyPlus
                runs but nothing is returned in the return statement.
            prep_outputs (bool or list, optional): if True, default meters and
                variables outputs are appended to the idf file. see
                :func:`prepare_outputs` for more details.
            **kwargs:

        Returns:
            The output report or the sql file loaded as a dict of DataFrames.
        """

        if not weather_file:
            weather_file = self.epw
        if not ep_version:
            ep_version = '-'.join(map(str, self.idd_version))
        eplus_file = self.idfname
        results = run_eplus(eplus_file, weather_file, output_folder, ep_version,
                            output_report, prep_outputs, **kwargs)
        if output_report != 'sql':
            # user wants something more than the sql
            return results
        else:
            # user simply wants the sql
            self.sql = results
            return results

    def add_object(self, ep_object, save=True, **kwargs):
        """Add a new object to an idf file. The function will test if the
        object exists to prevent duplicates.

        Args:
            ep_object (str): the object name to add, eg. 'OUTPUT:METER' (Must
                be in all_caps)
            **kwargs: keyword arguments to pass to other functions.

        Returns:
            eppy.modeleditor.IDF: the IDF object
        """
        # get list of objects
        objs = self.idfobjects[ep_object]  # a list
        # create new object
        new_object = self.newidfobject(ep_object, **kwargs)
        # Check if new object exists in previous list
        # If True, delete the object
        if sum([str(obj).upper() == str(new_object).upper() for obj in
                objs]) > 1:
            log('object "{}" already exists in idf file'.format(ep_object),
                lg.WARNING)
            # Remove the newly created object since the function
            # `idf.newidfobject()` automatically adds it
            self.removeidfobject(new_object)
            if not save:
                return []
        else:
            if save:
                log('object "{}" added to the idf file'.format(ep_object))
                self.save()
            else:
                # return the ep_object
                return new_object

    def get_schedule_type_limits_data_by_name(self, schedule_limit_name):
        """Returns the data for a particular 'ScheduleTypeLimits' object"""
        schedule = self.getobject('ScheduleTypeLimits'.upper(),
                                  schedule_limit_name)

        if schedule is not None:
            lower_limit = schedule['Lower_Limit_Value']
            upper_limit = schedule['Upper_Limit_Value']
            numeric_type = schedule['Numeric_Type']
            unit_type = schedule['Unit_Type']

            if schedule['Unit_Type'] == '':
                unit_type = numeric_type

            return lower_limit, upper_limit, numeric_type, unit_type
        else:
            return '', '', '', ''

    def get_schedule_data_by_name(self, sch_name, sch_type=None):
        """Returns the epbunch of a particular schedule name

        Args:
            sch_type:
        """
        if sch_type is None:
            try:
                return self.schedules_dict[sch_name]
            except:
                try:
                    schedules_dict = self.get_all_schedules()
                    return schedules_dict[sch_name]
                except KeyError:
                    raise KeyError('Unable to find schedule "{}" of type "{}" '
                                   'in idf file "{}"'.format(
                        sch_name, sch_type, self.idfname))
        else:
            return self.getobject(sch_type, sch_name)

    def get_all_schedules(self, yearly_only=False):
        """Returns all schedule ep_objects in a dict with their name as a key

        Args:
            yearly_only (bool): If True, return only yearly schedules

        Returns:
            (dict of eppy.bunch_subclass.EpBunch): the schedules with their
                name as a key
        """
        schedule_types = ['Schedule:Day:Hourly'.upper(),
                          'Schedule:Day:Interval'.upper(),
                          'Schedule:Day:List'.upper(),
                          'Schedule:Week:Daily'.upper(),
                          'Schedule:Year'.upper(),
                          'Schedule:Week:Compact'.upper(),
                          'Schedule:Compact'.upper(),
                          'Schedule:Constant'.upper(),
                          'Schedule:File'.upper()]
        if yearly_only:
            schedule_types = ['Schedule:Year'.upper(),
                              'Schedule:Compact'.upper(),
                              'Schedule:Constant'.upper(),
                              'Schedule:File'.upper()]
        scheds = {}
        for sched_type in schedule_types:
            for sched in self.idfobjects[sched_type]:
                try:
                    if sched.key.upper() in schedule_types:
                        scheds[sched.Name] = sched
                except:
                    pass
        return scheds

    def get_used_schedules(self, yearly_only=False):
        """Returns all used schedules

        Args:
            yearly_only (bool): If True, return only yearly schedules

        Returns:
            (list): the schedules names

        """
        schedule_types = ['Schedule:Day:Hourly'.upper(),
                          'Schedule:Day:Interval'.upper(),
                          'Schedule:Day:List'.upper(),
                          'Schedule:Week:Daily'.upper(),
                          'Schedule:Year'.upper(),
                          'Schedule:Week:Compact'.upper(),
                          'Schedule:Compact'.upper(),
                          'Schedule:Constant'.upper(),
                          'Schedule:File'.upper()]

        used_schedules = []
        all_schedules = self.get_all_schedules(yearly_only=yearly_only)
        for object_name in self.idfobjects:
            for object in self.idfobjects[object_name]:
                if object.key.upper() not in schedule_types:
                    for fieldvalue in object.fieldvalues:
                        try:
                            if fieldvalue in all_schedules and fieldvalue not \
                                    in used_schedules:
                                used_schedules.append(fieldvalue)
                        except:
                            pass
        return used_schedules

    @property
    def day_of_week_for_start_day(self):
        """Get day of week for start day for the first found RUNPERIOD"""
        import calendar
        day = self.idfobjects["RUNPERIOD"][0]["Day_of_Week_for_Start_Day"]

        if day.lower() == "sunday":
            return calendar.SUNDAY
        elif day.lower() == "monday":
            return calendar.MONDAY
        elif day.lower() == "tuesday":
            return calendar.TUESDAY
        elif day.lower() == "wednesday":
            return calendar.WEDNESDAY
        elif day.lower() == "thursday":
            return calendar.THURSDAY
        elif day.lower() == "friday":
            return calendar.FRIDAY
        elif day.lower() == "saturday":
            return calendar.SATURDAY
        else:
            return 0

    def building_name(self, use_idfname=False):
        if use_idfname:
            return os.path.basename(self.idfname)
        else:
            bld = self.idfobjects["BUILDING"]
            if bld is not None:
                return bld[0].Name
            else:
                return os.path.basename(self.idfname)

    def rename(self, objkey, objname, newname):
        """rename all the references to this objname

        Function comes from eppy.modeleditor and was modify to compare
        the name to rename as a lower string
        (see idfobject[idfobject.objls[findex]].lower() == objname.lower())

        Args:
            objkey (EpBunch): EpBunch we want to rename and rename all the
                occurrences where this object is in the IDF file
            objname (str): The name of the EpBunch to rename
            newname (str): New name used to rename the EpBunch

        Returns:
            theobject (EpBunch): The IDF objects renameds

        """

        refnames = eppy.modeleditor.getrefnames(self, objkey)
        for refname in refnames:
            objlists = eppy.modeleditor.getallobjlists(self, refname)
            # [('OBJKEY', refname, fieldindexlist), ...]
            for robjkey, refname, fieldindexlist in objlists:
                idfobjects = self.idfobjects[robjkey]
                for idfobject in idfobjects:
                    for findex in fieldindexlist:  # for each field
                        if idfobject[idfobject.objls[findex]].lower() == \
                                objname.lower():
                            idfobject[idfobject.objls[findex]] = newname
        theobject = self.getobject(objkey, objname)
        fieldname = [item for item in theobject.objls if item.endswith('Name')][
            0]
        theobject[fieldname] = newname
        return theobject


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


def load_idf(eplus_file, idd_filename=None):
    """Returns a parsed IDF object from file. If
    *archetypal.settings.use_cache* is true, then the idf object is loaded
    from cache.

    Args:
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
        idf = eppy_load(eplus_file, idd_filename)
        return idf


def eppy_load(file, idd_filename):
    """Uses package eppy to parse an idf file. Will also try to upgrade the
    idf file using the EnergyPlus Transition
    executables.

    Args:
        file (str): path of the idf file
        idd_filename: path of the EnergyPlus IDD file

    Returns:
        eppy.modeleditor.IDF: IDF object

    """
    cache_filename = hash_file(file)
    # Initiate an eppy.modeleditor.IDF object
    idf_object = None
    IDF.setiddname(idd_filename, testing=True)
    while idf_object is None:
        try:
            idf_object = IDF(file)
            # Check version of IDF file against version of IDD file
            idf_version = idf_object.idfobjects['VERSION'][
                0].Version_Identifier
            idd_version = '{}.{}'.format(idf_object.idd_version[0],
                                         idf_object.idd_version[1])

            if idf_version == idd_version:
                # if the versions fit, great!
                log('The version of the IDF file "{}",\n\t'
                    'version "{}", matched the version of EnergyPlus {},'
                    '\n\tversion "{}", used to parse it.'.format(
                    os.path.basename(file),
                    idf_version,
                    idf_object.getiddname(),
                    idd_version),
                    level=lg.DEBUG)
            else:
                # if they don't fit, upgrade file
                upgrade_idf(file)
                idd_filename = getiddfile(get_idf_version(file))
                IDF.iddname = idd_filename
        # An error could occur if the iddname is not found on the system. Try
        # to upgrade the idf file
        except Exception as e:
            log('{}'.format(e))
            log('Trying to upgrade the file instead...')
            # Try to upgrade the file
            upgrade_idf(file)
            # Get idd file for newly created and upgraded idf file
            idd_filename = getiddfile(get_idf_version(file))
            IDF.iddname = idd_filename
        else:
            # when parsing is complete, save it to disk, then return object
            save_idf_object_to_cache(idf_object, idf_object.idfname,
                                     cache_filename)
    return idf_object


def save_idf_object_to_cache(idf_object, idf_file, cache_filename=None,
                             how=None):
    """Saves the object to disk. Essentially uses the pickling functions of
    python.

    Args:
        cache_filename:
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
        if cache_filename is None:
            cache_filename = hash_file(idf_file)
        cache_dir = os.path.join(settings.cache_folder, cache_filename)

        # create the folder on the disk if it doesn't already exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        if how.upper() == 'JSON':
            cache_fullpath_filename = os.path.join(settings.cache_folder,
                                                   cache_filename,
                                                   os.extsep.join([
                                                       cache_filename + 'idfs',
                                                       'json']))
            import gzip, json
            with open(cache_fullpath_filename, 'w') as file_handle:
                json.dump({key: value.__dict__ for key, value in
                           idf_object.idfobjects.items()},
                          file_handle,
                          sort_keys=True, indent=4, check_circular=True)

        elif how.upper() == 'PICKLE':
            # create pickle and dump
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
            with gzip.GzipFile(cache_fullpath_filename, 'wb') as file_handle:
                pickle.dump(idf_object, file_handle, protocol=0)
            log('Saved pickle to file in {:,.2f} seconds'.format(
                time.time() - start_time))

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


def prepare_outputs(eplus_file, outputs=None, idd_filename=None):
    """Add additional epobjects to the idf file. Users can pass in an outputs

    Args:
        eplus_file:
        outputs (bool or list):

    Examples:
        >>> objects = [{'ep_object':'OUTPUT:DIAGNOSTICS',
        >>>             'kwargs':{'Key_1':'DisplayUnusedSchedules'}}]
        >>> prepare_outputs(eplus_file, outputs=objects)

    """

    log('first, loading the idf file')
    idf = load_idf(eplus_file, idd_filename=idd_filename)
    eplus_finename = os.path.basename(eplus_file)
    idf = {eplus_finename: idf}

    if isinstance(outputs, list):
        for output in outputs:
            idf[eplus_finename].add_object(output['ep_object'], **output[
                'kwargs'])

    # SummaryReports
    idf[eplus_finename].add_object('Output:Table:SummaryReports'.upper(),
                                   Report_1_Name='AllSummary')

    # SQL output
    idf[eplus_finename].add_object('Output:SQLite'.upper(),
                                   Option_Type='SimpleAndTabular')

    # Output variables
    idf[eplus_finename].add_object('Output:Variable'.upper(),
                                   Variable_Name='Air System Total Heating '
                                                 'Energy',
                                   Reporting_Frequency='hourly')
    idf[eplus_finename].add_object('Output:Variable'.upper(),
                                   Variable_Name='Air System Total Cooling '
                                                 'Energy',
                                   Reporting_Frequency='hourly')

    # Output meters
    idf[eplus_finename].add_object('OUTPUT:METER',
                                   Key_Name='HeatRejection:EnergyTransfer',
                                   Reporting_Frequency='hourly')
    idf[eplus_finename].add_object('OUTPUT:METER',
                                   Key_Name='Heating:EnergyTransfer',
                                   Reporting_Frequency='hourly')
    idf[eplus_finename].add_object('OUTPUT:METER',
                                   Key_Name='Cooling:EnergyTransfer',
                                   Reporting_Frequency='hourly')
    idf[eplus_finename].add_object('OUTPUT:METER',
                                   Key_Name='Heating:DistrictHeating',
                                   Reporting_Frequency='hourly')
    idf[eplus_finename].add_object('OUTPUT:METER',
                                   Key_Name='Heating:Electricity',
                                   Reporting_Frequency='hourly')
    idf[eplus_finename].add_object('OUTPUT:METER',
                                   Key_Name='Heating:Gas',
                                   Reporting_Frequency='hourly')
    idf[eplus_finename].add_object('OUTPUT:METER',
                                   Key_Name='Cooling:DistrictCooling',
                                   Reporting_Frequency='hourly')
    idf[eplus_finename].add_object('OUTPUT:METER',
                                   Key_Name='Cooling:Electricity',
                                   Reporting_Frequency='hourly')
    idf[eplus_finename].add_object('OUTPUT:METER',
                                   Key_Name='Cooling:Gas',
                                   Reporting_Frequency='hourly')


def cache_runargs(eplus_file, runargs):
    import json
    output_directory = runargs['output_directory']

    runargs.update({'run_time': datetime.datetime.now().isoformat()})
    runargs.update({'idf_file': eplus_file})
    with open(os.path.join(output_directory, 'runargs.json'), 'w') as fp:
        json.dump(runargs, fp, sort_keys=True, indent=4)


def run_eplus(eplus_file, weather_file, output_folder=None, ep_version=None,
              output_report=None, prep_outputs=False, **kwargs):
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
    if os.path.isfile(weather_file):
        pass
    else:
        raise FileNotFoundError('Could not find weather file: {}'.format(
            weather_file))

    # use absolute paths
    eplus_file = os.path.abspath(eplus_file)

    # <editor-fold desc="Try to get cached results">
    try:
        start_time = time.time()
        cached_run_results = get_from_cache(eplus_file, output_report,
                                            **kwargs)
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

    output_prefix = hash_file(eplus_file, kwargs)

    # <editor-fold desc="Upgrade the file version if needed">
    try:
        if ep_version:
            # replace the dots with "-"
            ep_version = ep_version.replace(".", "-")
        perform_transition(eplus_file, to_version=ep_version)
    except KeyError as e:
        log('file already upgraded to latest version "{}"'.format(e))

    # update the versionid of the file
    versionid = get_idf_version(eplus_file, doted=False)
    idd_filename = getiddfile(get_idf_version(eplus_file, doted=True))
    # </editor-fold>

    # Output folder check
    if not output_folder:
        output_folder = os.path.abspath(settings.cache_folder)
    # create the folder on the disk if it doesn't already exist
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    log('Output folder set to {}'.format(output_folder))

    # Prepare outputs e.g. sql table
    if prep_outputs:
        # Check if idf file has necessary objects (eg specific outputs)
        prepare_outputs(eplus_file, prep_outputs, idd_filename)

    if runs_not_found:
        # continue with simulation of other files
        log('no cached run for {}. Running EnergyPlus...'.format(
            os.path.basename(eplus_file)))

        start_time = time.time()
        from shutil import copyfile
        processed_runs = {}

        # used the hash of the original file (unmodified)
        filename_prefix = kwargs.get('output_prefix', output_prefix)
        epw = os.path.abspath(weather_file)
        runargs = {'idf': eplus_file,
                   'weather': epw,
                   'verbose': 'q',
                   'output_directory': os.path.join(output_folder,
                                                    filename_prefix),
                   'ep_version': versionid,
                   'output_prefix': filename_prefix,
                   'idd': idd_filename}
        runargs.update(kwargs)

        # Put a copy of the file in its cache folder and save runargs
        if not os.path.isfile(os.path.join(runargs['output_directory'],
                                           os.path.basename(eplus_file))):
            if not os.path.isdir(os.path.join(runargs['output_directory'])):
                os.mkdir(runargs['output_directory'])
            copyfile(eplus_file, os.path.join(runargs['output_directory'],
                                              os.path.basename(eplus_file)))
            cache_runargs(eplus_file, runargs.copy())

        # run the EnergyPlus Simulation
        multirunner(**runargs)

        log('Completed EnergyPlus in {:,.2f} seconds'.format(
            time.time() - start_time))

        # Return summary DataFrames
        cacheargs = {'eplus_file': eplus_file,
                     'output_folder': output_folder,
                     'output_report': output_report,
                     'filename_prefix': output_prefix,
                     **kwargs}
        cached_run_results = get_report(**cacheargs)
        return cached_run_results


def multirunner(**kwargs):
    """Wrapper for :func:`eppy.runner.run_functions.run` to be used when
    running IDF and EPW runs in parallel.

    Args:
        kwargs (dict): A dict made up of run() arguments.

    """
    try:
        run(**kwargs)
    except TypeError as e:
        log('{}'.format(e), lg.ERROR)
        raise TypeError('{}'.format(e))
    except CalledProcessError as e:
        # Get error file
        log('{}'.format(e), lg.ERROR)

        error_filename = os.path.join(kwargs['output_directory'],
                                      kwargs['output_prefix'] + 'out.err')
        if os.path.isfile(error_filename):
            with open(error_filename, 'r') as fin:
                log('\nError File for "{}" begins here...\n'.format(
                    os.path.basename(kwargs['idf'])), lg.ERROR)
                log(fin.read(), lg.ERROR)
                log('Error File for "{}" ends here...\n'.format(
                    os.path.basename(kwargs['idf'])), lg.ERROR)
            with open(error_filename, 'r') as stderr:
                raise EnergyPlusProcessError(cmd=e.cmd,
                                             idf=os.path.basename(
                                                 kwargs['idf']),
                                             stderr=stderr.read())
        else:
            log('Could not find error file', lg.ERROR)


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
        fullpath_filename = os.path.join(output_folder, filename_prefix,
                                         os.extsep.join(
                                             [filename_prefix + 'out', 'sql']))
        if os.path.isfile(fullpath_filename):
            return get_sqlite_report(fullpath_filename)
        else:
            raise FileNotFoundError(
                'File "{}" does not exist'.format(fullpath_filename))
    else:
        return None


def get_from_cache(eplus_file, output_report='sql', **kwargs):
    """Retrieve a EPlus Tabulated Summary run result from the cache

    Args:
        eplus_file (str): the path of the eplus file
        output_report: 'html' or 'sql'
        **kwargs: keyword arguments to pass to other functions.

    Returns:
        dict: dict of DataFrames
    """
    if settings.use_cache:
        # determine the filename by hashing the eplus_file
        cache_filename_prefix = hash_file(eplus_file, kwargs)
        if output_report is None:
            return None
        elif 'htm' in output_report.lower():
            # Get the html report
            cache_fullpath_filename = os.path.join(settings.cache_folder,
                                                   cache_filename_prefix,
                                                   os.extsep.join([
                                                       cache_filename_prefix
                                                       + 'tbl',
                                                       'htm']))
            if os.path.isfile(cache_fullpath_filename):
                return get_html_report(cache_fullpath_filename)

        elif 'sql' in output_report.lower():
            # get the SQL report
            cache_fullpath_filename = os.path.join(settings.cache_folder,
                                                   cache_filename_prefix,
                                                   os.extsep.join([
                                                       cache_filename_prefix
                                                       + 'out',
                                                       'sql']))
            if os.path.isfile(cache_fullpath_filename):
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


def upgrade_idf(files):
    """upgrades the idf file to the latest version. Implements the
    :func:`perform_transition` function.

    Args:
        files (str or list): path or list of paths to the idf file(s)

    Returns:

    """
    # Check if files is a str and put in a list
    if isinstance(files, str):
        files = [files]

    for file in files:
        try:
            perform_transition(file, to_version=None)
        except KeyError as e:
            log('file already upgraded to latest version "{}"'.format(e))


def perform_transition(file, to_version=None):
    """Transition program for idf version 1-0-0 to version 8-9-0.

    Args:
        file (str): path of idf file
        to_version (str): EnergyPlus version in the form "X-X-X".

    Returns:

    """
    versionid = get_idf_version(file, doted=False)[0:5]
    doted_version = get_idf_version(file, doted=True)
    iddfile = getiddfile(doted_version)
    if os.path.exists(iddfile):
        # if a E+ exists, pass
        pass
        # might be an old version of E+
    elif tuple(map(int, doted_version.split('.'))) < (8, 0):
        # else if the version is an old E+ version (< 8.0)
        iddfile = getoldiddfile(doted_version)
    vupdater_path, _ = iddfile.split('Energy+')
    # use to_version
    if to_version is None:
        # What is the latest E+ installed version
        to_version = find_eplus_installs(vupdater_path)
    if tuple(versionid.split('-')) > tuple(to_version.split('-')):
        log(
            'The version of the idf file "{}: v{}" is higher than any version '
            'of EnergyPlus installed on this machine. Please install '
            'EnergyPlus version "{}" or higher. Latest version found: '
            '{}'.format(os.path.basename(file), versionid, versionid,
                        to_version), lg.WARNING)
        return None
    ep_installation_name = os.path.abspath(os.path.dirname(getiddfile(
        to_version.replace('-', '.'))))
    vupdater_path = os.path.join(ep_installation_name, 'PreProcess',
                                 'IDFVersionUpdater')
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
    file = os.path.abspath(file)
    # store the directory we start in
    cwd = os.getcwd()
    run_dir = os.path.abspath(os.path.dirname(trans_exec[versionid]))

    # build a list of command line arguments
    if versionid == to_version:
        raise KeyError
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
                cmd = [trans_exec[trans], file]
                try:
                    check_call(cmd)
                except CalledProcessError as e:
                    # potentially catch contents of std out and put it in the
                    # error log
                    log('{}'.format(e), lg.ERROR)
                    raise

    log('Transition completed\n')
    # Clean 'idfnew' and 'idfold' files created by the transition porgram
    files_to_delete = glob.glob(os.path.dirname(file) + '/*.idfnew')
    files_to_delete.extend(glob.glob(os.path.dirname(file) + '/*.idfold'))
    files_to_delete.extend(glob.glob(os.path.dirname(
        file) + '/*.VCpErr'))  # Remove error files since logged to console
    for file in files_to_delete:
        if os.path.isfile(file):
            os.remove(file)


def find_eplus_installs(vupdater_path):
    """Finds all installed versions of EnergyPlus in the default location and
    returns the latest version number

    Args:
        vupdater_path (str): path of the current EnergyPlus install file

    Returns:
        (str): The version number of the latest E+ install

    """
    path_to_eplus, _ = vupdater_path.split('EnergyPlus')

    # Find all EnergyPlus folders
    list_eplus_dir = glob.glob(os.path.join(path_to_eplus, 'EnergyPlus*'))

    # check if any EnergyPlus install exists
    if not list_eplus_dir:
        raise Exception('No EnergyPlus installation found. Make sure '
                        'you have EnergyPlus installed. Go to '
                        'https://energyplus.net/downloads to download the '
                        'latest version of EnergyPlus.')

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
