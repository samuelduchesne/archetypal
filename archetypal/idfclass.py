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
import inspect
import logging as lg
import multiprocessing
import os
import subprocess
import time
from sqlite3 import OperationalError
from subprocess import CalledProcessError
from tempfile import tempdir

import eppy
import eppy.modeleditor
import geomeppy
import pandas as pd
from archetypal import (
    log,
    settings,
    EnergyPlusProcessError,
    cd,
    ReportData,
    EnergySeries,
    close_logger,
)
from archetypal.utils import _unpack_tuple
from eppy.EPlusInterfaceFunctions import parse_idd
from eppy.easyopen import getiddfile
from path import Path, tempdir


class IDF(geomeppy.IDF):
    """Wrapper over the geomeppy.IDF class and subsequently the
    eppy.modeleditor.IDF class
    """

    def __init__(self, *args, **kwargs):
        """
        Args:
            *args:
            **kwargs:
        """
        super(IDF, self).__init__(*args, **kwargs)
        self._sql_file = None
        self.schedules_dict = self.get_all_schedules()
        self._sql = None
        self.eplus_run_options = EnergyPlusOptions(
            eplus_file=self.idfname,
            weather_file=getattr(self, "epw", None),
            ep_version="-".join(map(str, self.idd_version)),
        )

    @property
    def name(self):
        return os.path.basename(self.idfname)

    @property
    def sql(self):
        if self._sql is None:
            self._sql = self.run_eplus(
                annual=True, prep_outputs=True, output_report="sql"
            )
            return self._sql
        else:
            return self._sql

    @property
    def sql_file(self):
        if self._sql_file is None:
            self._sql_file = self.run_eplus(
                annual=True, prep_outputs=True, output_report="sql_file"
            )
            return self._sql_file
        else:
            return self._sql_file

    @property
    def area_conditioned(self):
        """Returns the total conditioned area of a building (taking into account
        zone multipliers
        """
        area = 0
        zones = self.idfobjects["ZONE"]
        for zone in zones:
            for surface in zone.zonesurfaces:
                if hasattr(surface, "tilt"):
                    if surface.tilt == 180.0:
                        part_of = int(zone.Part_of_Total_Floor_Area.upper() != "NO")
                        multiplier = float(
                            zone.Multiplier if zone.Multiplier != "" else 1
                        )

                        area += surface.area * multiplier * part_of
        return area

    @property
    def partition_ratio(self):
        """The number of lineal meters of partitions (Floor to ceiling) present
        in average in the building floor plan by m2.
        """
        partition_lineal = 0
        zones = self.idfobjects["ZONE"]
        for zone in zones:
            for surface in zone.zonesurfaces:
                if hasattr(surface, "tilt"):
                    if (
                        surface.tilt == 90.0
                        and surface.Outside_Boundary_Condition != "Outdoors"
                    ):
                        multiplier = float(
                            zone.Multiplier if zone.Multiplier != "" else 1
                        )
                        partition_lineal += surface.width * multiplier

        return partition_lineal / self.area_conditioned

    def space_heating_profile(
        self,
        units="kWh",
        energy_out_variable_name=None,
        name="Space Heating",
        EnergySeries_kwds={},
    ):
        """
        Args:
            units (str): Units to convert the energy profile to. Will detect the
                units of the EnergyPlus results.
            energy_out_variable_name (list-like): a list of EnergyPlus Variable
                names.
            name (str): Name given to the EnergySeries.
            EnergySeries_kwds (dict, optional): keywords passed to
                :func:`EnergySeries.from_sqlite`

        Returns:
            EnergySeries
        """
        start_time = time.time()
        if energy_out_variable_name is None:
            energy_out_variable_name = (
                "Air System Total Heating Energy",
                "Zone Ideal Loads Zone Total Heating Energy",
            )
        series = self._energy_series(
            energy_out_variable_name, units, name, EnergySeries_kwds
        )
        log(
            "Retrieved Space Heating Profile in {:,.2f} seconds".format(
                time.time() - start_time
            )
        )
        return series

    def space_cooling_profile(
        self,
        units="kWh",
        energy_out_variable_name=None,
        name="Space Cooling",
        EnergySeries_kwds={},
    ):
        """
        Args:
            units (str): Units to convert the energy profile to. Will detect the
                units of the EnergyPlus results.
            energy_out_variable_name (list-like): a list of EnergyPlus
            name (str): Name given to the EnergySeries.
            EnergySeries_kwds (dict, optional): keywords passed to
                :func:`EnergySeries.from_sqlite`

        Returns:
            EnergySeries
        """
        start_time = time.time()
        if energy_out_variable_name is None:
            energy_out_variable_name = (
                "Air System Total Cooling Energy",
                "Zone Ideal Loads Zone Total Cooling Energy",
            )
        series = self._energy_series(
            energy_out_variable_name, units, name, EnergySeries_kwds
        )
        log(
            "Retrieved Space Cooling Profile in {:,.2f} seconds".format(
                time.time() - start_time
            )
        )
        return series

    def _energy_series(self, energy_out_variable_name, units, name, EnergySeries_kwds):
        """
        Args:
            energy_out_variable_name:
            units:
            name:
            EnergySeries_kwds:
        """
        rd = ReportData.from_sqlite(self.sql_file, table_name=energy_out_variable_name)
        profile = EnergySeries.from_sqlite(
            rd, to_units=units, name=name, **EnergySeries_kwds
        )
        return profile

    def run_eplus(self, **kwargs):
        """wrapper around the :func:`archetypal.run_eplus()` method.

        If weather file is defined in the IDF object, then this field is
        optional. By default, will load the sql in self.sql.

        Args:
            **kwargs:

        Returns:
            The output report or the sql file loaded as a dict of DataFrames.
        """
        self.eplus_run_options.__dict__.update(kwargs)
        results = run_eplus(**self.eplus_run_options.__dict__)
        if self.eplus_run_options.output_report == "sql":
            # user simply wants the sql
            self._sql = results
            return results
        elif self.eplus_run_options.output_report == "sql_file":
            self._sql_file = results
            return results
        else:
            # user wants something more than the sql
            return results

    def add_object(self, ep_object, save=True, **kwargs):
        """Add a new object to an idf file. The function will test if the object
        exists to prevent duplicates. By default, the idf with the new object is
        saved to disk (save=True)

        Args:
            ep_object (str): the object name to add, eg. 'OUTPUT:METER' (Must be
                in all_caps).
            save (bool): Save the IDF as a text file with the current idfname of
                the IDF.
            **kwargs: keyword arguments to pass to other functions.

        Returns:
            EpBunch: the object
        """
        # get list of objects
        objs = self.idfobjects[ep_object]  # a list
        # If object is supposed to be 'unique-object', deletes all objects to be
        # sure there is only one of them when creating new object
        # (see following line)
        for obj in objs:
            if "unique-object" in obj.objidd[0].keys():
                self.removeidfobject(obj)
        # create new object
        new_object = self.newidfobject(ep_object, **kwargs)
        # Check if new object exists in previous list
        # If True, delete the object
        if sum([str(obj).upper() == str(new_object).upper() for obj in objs]) > 1:
            log('object "{}" already exists in idf file'.format(ep_object), lg.WARNING)
            # Remove the newly created object since the function
            # `idf.newidfobject()` automatically adds it
            self.removeidfobject(new_object)
            if not save:
                return self.getobject(ep_object, kwargs["Name"])
        else:
            if save:
                log('object "{}" added to the idf file'.format(ep_object))
                self.save()
            # invalidate the sql statements
            self._sql = None
            self._sql_file = None
            # return the ep_object
            return new_object

    def get_schedule_type_limits_data_by_name(self, schedule_limit_name):
        """Returns the data for a particular 'ScheduleTypeLimits' object

        Args:
            schedule_limit_name:
        """
        schedule = self.getobject("ScheduleTypeLimits".upper(), schedule_limit_name)

        if schedule is not None:
            lower_limit = schedule["Lower_Limit_Value"]
            upper_limit = schedule["Upper_Limit_Value"]
            numeric_type = schedule["Numeric_Type"]
            unit_type = schedule["Unit_Type"]

            if schedule["Unit_Type"] == "":
                unit_type = numeric_type

            return lower_limit, upper_limit, numeric_type, unit_type
        else:
            return "", "", "", ""

    def get_schedule_epbunch(self, name, sch_type=None):
        """Returns the epbunch of a particular schedule name. If the schedule
        type is know, retreives it quicker.

        Args:
            name (str): The name of the schedule to retreive in the IDF file.
            sch_type (str): The schedule type, e.g.: "SCHEDULE:YEAR".
        """
        if sch_type is None:
            try:
                return self.schedules_dict[name.upper()]
            except:
                try:
                    schedules_dict = self.get_all_schedules()
                    return schedules_dict[name.upper()]
                except KeyError:
                    raise KeyError(
                        'Unable to find schedule "{}" of type "{}" '
                        'in idf file "{}"'.format(name, sch_type, self.idfname)
                    )
        else:
            return self.getobject(sch_type.upper(), name)

    def get_all_schedules(self, yearly_only=False):
        """Returns all schedule ep_objects in a dict with their name as a key

        Args:
            yearly_only (bool): If True, return only yearly schedules

        Returns:
            (dict of eppy.bunch_subclass.EpBunch): the schedules with their
                name as a key
        """
        schedule_types = list(map(str.upper, self.getiddgroupdict()["Schedules"]))
        if yearly_only:
            schedule_types = [
                "Schedule:Year".upper(),
                "Schedule:Compact".upper(),
                "Schedule:Constant".upper(),
                "Schedule:File".upper(),
            ]
        scheds = {}
        for sched_type in schedule_types:
            for sched in self.idfobjects[sched_type]:
                try:
                    if sched.key.upper() in schedule_types:
                        scheds[sched.Name.upper()] = sched
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
        schedule_types = [
            "Schedule:Day:Hourly".upper(),
            "Schedule:Day:Interval".upper(),
            "Schedule:Day:List".upper(),
            "Schedule:Week:Daily".upper(),
            "Schedule:Year".upper(),
            "Schedule:Week:Compact".upper(),
            "Schedule:Compact".upper(),
            "Schedule:Constant".upper(),
            "Schedule:File".upper(),
        ]

        used_schedules = []
        all_schedules = self.get_all_schedules(yearly_only=yearly_only)
        for object_name in self.idfobjects:
            for object in self.idfobjects[object_name]:
                if object.key.upper() not in schedule_types:
                    for fieldvalue in object.fieldvalues:
                        try:
                            if (
                                fieldvalue in all_schedules
                                and fieldvalue not in used_schedules
                            ):
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
        """
        Args:
            use_idfname:
        """
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

        Function comes from eppy.modeleditor and was modify to compare the
        name to rename as a lower string (see
        idfobject[idfobject.objls[findex]].lower() == objname.lower())

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
                        if (
                            idfobject[idfobject.objls[findex]].lower()
                            == objname.lower()
                        ):
                            idfobject[idfobject.objls[findex]] = newname
        theobject = self.getobject(objkey, objname)
        fieldname = [item for item in theobject.objls if item.endswith("Name")][0]
        theobject[fieldname] = newname
        return theobject


class EnergyPlusOptions:
    def __init__(
        self,
        eplus_file,
        weather_file,
        output_directory=None,
        ep_version=None,
        output_report=None,
        prep_outputs=False,
        simulname=None,
        keep_data=True,
        annual=False,
        design_day=False,
        epmacro=False,
        expandobjects=True,
        readvars=False,
        output_prefix=False,
        output_suffix="L",
        version=None,
        verbose="v",
        keep_data_err=False,
        include=None,
        process_files=False,
        custom_processes=None,
        return_idf=False,
        return_files=False,
    ):
        """
        Args:
            eplus_file:
            weather_file:
            output_directory:
            ep_version:
            output_report:
            prep_outputs:
            return_idf:
            annual:
            design_day:
            epmacro:
            expandobjects:
            readvars:
            output_prefix:
            verbose:
            output_suffix:
        """
        self.return_files = return_files
        self.custom_processes = custom_processes
        self.process_files = process_files
        self.include = include
        self.keep_data_err = keep_data_err
        self.version = version
        self.keep_data = keep_data
        self.simulname = simulname
        self.output_suffix = output_suffix
        self.verbose = verbose
        self.output_prefix = output_prefix
        self.readvars = readvars
        self.expandobjects = expandobjects
        self.epmacro = epmacro
        self.design_day = design_day
        self.annual = annual
        self.return_idf = return_idf
        self.prep_outputs = prep_outputs
        self.output_report = output_report
        self.ep_version = ep_version
        self.output_directory = output_directory
        self.weather_file = weather_file
        self.eplus_file = eplus_file


def load_idf(
    eplus_file, idd_filename=None, output_folder=None, include=None, weather_file=None
):
    """Returns a parsed IDF object from file. If *archetypal.settings.use_cache*
    is true, then the idf object is loaded from cache.

    Args:
        eplus_file (str): path of the idf file.
        idd_filename (str, optional): name of the EnergyPlus IDD file. If None,
            the function tries to find it.
        output_folder (Path):
        include (str, optional): List input files that need to be copied to the
            simulation directory. If a string is provided, it should be in a
            glob form (see pathlib.Path.glob).
        weather_file:

    Returns:
        (IDF): The parsed IDF object
    """

    idf = load_idf_object_from_cache(eplus_file)

    start_time = time.time()
    if idf:
        # if found in cache, return
        log(
            "Eppy load from cache completed in {:,.2f} seconds\n".format(
                time.time() - start_time
            )
        )
        return idf
    else:
        # Else, run eppy to load the idf objects
        idf = _eppy_load(
            eplus_file,
            idd_filename,
            output_folder=output_folder,
            include=include,
            epw=weather_file,
        )
        log("Eppy load completed in {:,.2f} seconds\n".format(time.time() - start_time))
        return idf


def _eppy_load(file, idd_filename, output_folder=None, include=None, epw=None):
    """Uses package eppy to parse an idf file. Will also try to upgrade the idf
    file using the EnergyPlus Transition executables if the version of
    EnergyPlus is not installed on the machine.

    Args:
        file (str): path of the idf file.
        idd_filename: path of the EnergyPlus IDD file.
        output_folder (str): path to the output folder. Will default to the
            settings.cache_folder.
        include (str, optional): List input files that need to be copied to the
            simulation directory.if a string is provided, it should be in a glob
            form (see pathlib.Path.glob).
        epw:

    Returns:
        eppy.modeleditor.IDF: IDF object
    """
    file = Path(file)
    cache_filename = hash_file(file)

    try:
        # first copy the file
        if not output_folder:
            output_folder = settings.cache_folder / cache_filename
        else:
            output_folder = Path(output_folder)

        output_folder.makedirs_p()
        try:
            file = Path(file.copy(output_folder))
        except:
            # The file already exists at the location. Use that file
            file = output_folder / file.basename()
        finally:
            # Determine version of idf file by reading the text file
            if idd_filename is None:
                idd_filename = getiddfile(get_idf_version(file))

            # Initiate an eppy.modeleditor.IDF object
            IDF.setiddname(idd_filename, testing=True)
            # load the idf object
            idf_object = IDF(file, epw=epw)
            # Check version of IDF file against version of IDD file
            idf_version = idf_object.idfobjects["VERSION"][0].Version_Identifier
            idd_version = "{}.{}".format(
                idf_object.idd_version[0], idf_object.idd_version[1]
            )
    except FileNotFoundError as exception:
        # Loading the idf object will raise a FileNotFoundError if the
        # version of EnergyPlus is not included
        log("Transitioning idf file {}".format(file))
        # if they don't fit, upgrade file
        file = idf_version_updater(file, out_dir=output_folder)
        idd_filename = getiddfile(get_idf_version(file))
        IDF.iddname = idd_filename
        idf_object = IDF(file, epw=epw)
    else:
        # the versions fit, great!
        log(
            'The version of the IDF file "{}", version "{}", matched the '
            'version of EnergyPlus {}, version "{}", used to parse it.'.format(
                file.basename(), idf_version, idf_object.getiddname(), idd_version
            ),
            level=lg.DEBUG,
        )
    # when parsing is complete, save it to disk, then return object
    save_idf_object_to_cache(idf_object, idf_object.idfname, output_folder)
    if isinstance(include, str):
        include = Path().abspath().glob(include)
    if include is not None:
        [Path(file).copy(output_folder) for file in include]
    return idf_object


def save_idf_object_to_cache(idf_object, idf_file, output_folder=None, how=None):
    """Saves the object to disk. Essentially uses the pickling functions of
    python.

    Todo:
        * Json dump does not work yet.

    Args:
        idf_object (eppy.modeleditor.IDF): an eppy IDF object
        idf_file (str): file path of idf file
        output_folder (Path): temporary output directory (default:
            settings.cache_folder)
        how (str, optional): How the pickling is done. Choices are 'json' or
            'pickle'. json dump doen't quite work yet. 'pickle' will save to a
            gzip'ed file instead of a regular binary file (.dat).

    Returns:
        None
    """
    # upper() can't take NoneType as input.
    if how is None:
        how = ""
    # The main function
    if settings.use_cache:
        if output_folder is None:
            output_folder = hash_file(idf_file)
            cache_dir = os.path.join(settings.cache_folder, output_folder)
        cache_dir = output_folder

        # create the folder on the disk if it doesn't already exist
        if not os.path.exists(cache_dir):
            os.makedirs(cache_dir)

        if how.upper() == "JSON":
            cache_fullpath_filename = cache_dir / cache_dir.basename() + "idfs.json"
            import gzip, json

            with open(cache_fullpath_filename, "w") as file_handle:
                json.dump(
                    {
                        key: value.__dict__
                        for key, value in idf_object.idfobjects.items()
                    },
                    file_handle,
                    sort_keys=True,
                    indent=4,
                    check_circular=True,
                )

        elif how.upper() == "PICKLE":
            # create pickle and dump
            cache_fullpath_filename = cache_dir / cache_dir.basename() + "idfs.gzip"
            import gzip

            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            with gzip.GzipFile(cache_fullpath_filename, "wb") as file_handle:
                pickle.dump(idf_object, file_handle, protocol=0)
            log(
                "Saved pickle to file in {:,.2f} seconds".format(
                    time.time() - start_time
                )
            )

        else:
            cache_fullpath_filename = cache_dir / cache_dir.basename() + "idfs.dat"
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            with open(cache_fullpath_filename, "wb") as file_handle:
                pickle.dump(idf_object, file_handle, protocol=-1)
            log(
                "Saved pickle to file in {:,.2f} seconds".format(
                    time.time() - start_time
                )
            )


def load_idf_object_from_cache(idf_file, how=None):
    """Load an idf instance from cache

    Args:
        idf_file (str): path to the idf file
        how (str, optional): How the pickling is done. Choices are 'json' or
            'pickle' or 'idf'. json dump doesn't quite work yet. 'pickle' will
            load from a gzip'ed file instead of a regular binary file (.dat).
            'idf' will load from idf file saved in cache.

    Returns:
        None
    """
    # upper() can't tahe NoneType as input.
    if how is None:
        how = ""
    # The main function
    if settings.use_cache:
        cache_filename = hash_file(idf_file)
        if how.upper() == "JSON":
            cache_fullpath_filename = os.path.join(
                settings.cache_folder,
                cache_filename,
                os.extsep.join([cache_filename + "idfs", "json"]),
            )
            import json

            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            if os.path.isfile(cache_fullpath_filename):
                with open(cache_fullpath_filename, "rb") as file_handle:
                    idf = json.load(file_handle)
                log(
                    'Loaded "{}" from pickled file in {:,.2f} seconds'.format(
                        os.path.basename(idf_file), time.time() - start_time
                    )
                )
                return idf

        elif how.upper() == "PICKLE":
            cache_fullpath_filename = os.path.join(
                settings.cache_folder,
                cache_filename,
                os.extsep.join([cache_filename + "idfs", "gzip"]),
            )
            import gzip

            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            if os.path.isfile(cache_fullpath_filename):
                with gzip.GzipFile(cache_fullpath_filename, "rb") as file_handle:
                    idf = pickle.load(file_handle)
                if idf.iddname is None:
                    idf.setiddname(getiddfile(idf.model.dt["VERSION"][0][1]))
                    # idf.read()
                log(
                    'Loaded "{}" from pickled file in {:,.2f} seconds'.format(
                        os.path.basename(idf_file), time.time() - start_time
                    )
                )
                return idf
        elif how.upper() == "IDF":
            cache_fullpath_filename = os.path.join(
                settings.cache_folder,
                cache_filename,
                os.extsep.join([cache_filename, "idf"]),
            )
            if os.path.isfile(cache_fullpath_filename):
                version = get_idf_version(cache_fullpath_filename, doted=True)
                iddfilename = getiddfile(version)
                idf = _eppy_load(cache_fullpath_filename, iddfilename)
                return idf
        else:
            cache_fullpath_filename = os.path.join(
                settings.cache_folder,
                cache_filename,
                os.extsep.join([cache_filename + "idfs", "dat"]),
            )
            try:
                import cPickle as pickle
            except ImportError:
                import pickle
            start_time = time.time()
            if os.path.isfile(cache_fullpath_filename):
                with open(cache_fullpath_filename, "rb") as file_handle:
                    idf = pickle.load(file_handle)
                if idf.iddname is None:
                    idf.setiddname(getiddfile(idf.model.dt["VERSION"][0][1]))
                    idf.read()
                log(
                    'Loaded "{}" from pickled file in {:,.2f} seconds'.format(
                        os.path.basename(idf_file), time.time() - start_time
                    )
                )
                return idf


def prepare_outputs(
    eplus_file,
    outputs=None,
    idd_filename=None,
    output_directory=None,
    save=True,
    epw=None,
):
    """Add additional epobjects to the idf file. Users can pass in an outputs

    Examples:
        >>> objects = [{'ep_object':'OUTPUT:DIAGNOSTICS',
        >>>             'kwargs':{'Key_1':'DisplayUnusedSchedules'}}]
        >>> prepare_outputs(eplus_file, outputs=objects)

    Args:
        eplus_file (Path): the file describing the model (.idf)
        outputs (bool or list):
        idd_filename:
        output_directory:
        save (bool): if True, saves the idf inplace to disk with added objects
        epw:
    """

    log("first, loading the idf file")
    idf = load_idf(
        eplus_file,
        idd_filename=idd_filename,
        output_folder=output_directory,
        weather_file=epw,
    )

    if isinstance(outputs, list):
        for output in outputs:
            idf.add_object(output["ep_object"], **output["kwargs"], save=save)

    # SummaryReports
    idf.add_object(
        "Output:Table:SummaryReports".upper(), Report_1_Name="AllSummary", save=save
    )

    # OutputControl:Table:Style
    idf.add_object(
        "OutputControl:Table:Style".upper(), Column_Separator="CommaAndHTML", save=save
    )

    # SQL output
    idf.add_object("Output:SQLite".upper(), Option_Type="SimpleAndTabular", save=save)

    # Output variables
    idf.add_object(
        "Output:Variable".upper(),
        Variable_Name="Air System Total Heating Energy",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "Output:Variable".upper(),
        Variable_Name="Zone Ideal Loads Zone Total Cooling Energy",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "Output:Variable".upper(),
        Variable_Name="Zone Thermostat Heating Setpoint Temperature",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "Output:Variable".upper(),
        Variable_Name="Zone Thermostat Cooling Setpoint Temperature",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "Output:Variable".upper(),
        Variable_Name="Heat Exchanger Total Heating Rate",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "Output:Variable".upper(),
        Variable_Name="Heat Exchanger Sensible Effectiveness",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "Output:Variable".upper(),
        Variable_Name="Heat Exchanger Latent Effectiveness",
        Reporting_Frequency="hourly",
        save=save,
    )

    # Output meters
    idf.add_object(
        "OUTPUT:METER",
        Key_Name="HeatRejection:EnergyTransfer",
        Reporting_Frequency="hourly",
    )
    idf.add_object(
        "OUTPUT:METER",
        Key_Name="Heating:EnergyTransfer",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "OUTPUT:METER",
        Key_Name="Cooling:EnergyTransfer",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "OUTPUT:METER",
        Key_Name="Heating:DistrictHeating",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "OUTPUT:METER",
        Key_Name="Heating:Electricity",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "OUTPUT:METER", Key_Name="Heating:Gas", Reporting_Frequency="hourly", save=save
    )
    idf.add_object(
        "OUTPUT:METER",
        Key_Name="Cooling:DistrictCooling",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "OUTPUT:METER",
        Key_Name="Cooling:Electricity",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "OUTPUT:METER", Key_Name="Cooling:Gas", Reporting_Frequency="hourly", save=save
    )
    idf.add_object(
        "OUTPUT:METER",
        Key_Name="WaterSystems:EnergyTransfer",
        Reporting_Frequency="hourly",
        save=save,
    )
    idf.add_object(
        "OUTPUT:METER", Key_Name="Cooling:Gas", Reporting_Frequency="hourly", save=save
    )


def cache_runargs(eplus_file, runargs):
    """
    Args:
        eplus_file:
        runargs:
    """
    import json

    output_directory = runargs["output_directory"] / runargs["output_prefix"]

    runargs.update({"run_time": datetime.datetime.now().isoformat()})
    runargs.update({"idf_file": eplus_file})
    with open(os.path.join(output_directory, "runargs.json"), "w") as fp:
        json.dump(runargs, fp, sort_keys=True, indent=4)


def run_eplus(
    eplus_file,
    weather_file,
    output_directory=None,
    ep_version=None,
    output_report=None,
    prep_outputs=False,
    simulname=None,
    keep_data=True,
    annual=False,
    design_day=False,
    epmacro=False,
    expandobjects=False,
    readvars=False,
    output_prefix=None,
    output_suffix=None,
    version=None,
    verbose="v",
    keep_data_err=False,
    include=None,
    process_files=False,
    custom_processes=None,
    return_idf=False,
    return_files=False,
):
    """Run an energy plus file and return the SummaryReports Tables in a list of
    [(title, table), .....]

    Args:
        return_files (bool): It True, all files paths created by the energyplus run
            are returned.
        eplus_file (str): path to the idf file.
        weather_file (str): path to the EPW weather file
        output_directory (str, optional): path to the output folder. Will
            default to the settings.cache_folder.
        ep_version (str, optional): EnergyPlus version to use, eg: 8-9-0
        output_report: 'htm' or 'sql'.
        prep_outputs (bool or list, optional): if true, meters and variable
            outputs will be appended to the idf files. see
            :func:`prepare_outputs`
        simulname (str):
        keep_data (bool): If True, files created by EnergyPlus are saved to the
            output_directory.
        annual (bool): If True then force annual simulation (default: False)
        design_day (bool): Force design-day-only simulation (default: False)
        epmacro (bool): Run EPMacro prior to simulation (default: False)
        expandobjects (bool): Run ExpandObjects prior to simulation (default:
            False)
        readvars (bool): Run ReadVarsESO after simulation (default: False)
        output_prefix (str, optional): Prefix for output file names.
        output_suffix (str, optional): Suffix style for output file names (default: L)
                Choices are:
                    - L: Legacy (e.g., eplustbl.csv)
                    - C: Capital (e.g., eplusTable.csv)
                    - D: Dash (e.g., eplus-table.csv)
        version (bool, optional): Display version information (default: False)
        verbose (str): Set verbosity of runtime messages (default: v) v: verbose
            q: quiet
        keep_data_err:
        include (str, optional): List input files that need to be copied to the
            simulation directory.if a string is provided, it should be in a glob
            form (see pathlib.Path.glob).
        process_files:
        custom_processes (dict(Callback), optional): if provided, it has to be a
            dictionnary with the keys beeing a glob (see pathlib.Path.glob), and
            the value a Callback taking as signature `callback(file: str,
            working_dir, simulname) -> Any` All the file matching this glob will
            be processed by this callback. Note: they still be processed by
            pandas.read_csv (if they are csv files), resulting in duplicate. The
            only way to bypass this behavior is to add the key "*.csv" to that
            dictionnary.
        return_idf (bool): If Truem returns the :class:`IDF` object part of the return
            tuple.

    Returns:
        2-tuple: a 1-tuple or a 2-tuple
            - dict: dict of [(title, table), .....]
            - IDF: The IDF object. Only provided if return_idf is True.

    Raises:
        EnergyPlusProcessError.
    """
    eplus_file = Path(eplus_file)
    weather_file = Path(weather_file)

    frame = inspect.currentframe()
    args, _, _, values = inspect.getargvalues(frame)
    args = {arg: values[arg] for arg in args}

    cache_filename = hash_file(eplus_file)
    if not output_prefix:
        output_prefix = cache_filename
    if not output_directory:
        output_directory = settings.cache_folder / cache_filename
    else:
        output_directory = Path(output_directory)
    args["output_directory"] = output_directory
    # <editor-fold desc="Try to get cached results">
    try:
        start_time = time.time()
        cached_run_results = get_from_cache(args)
    except Exception as e:
        # catch other exceptions that could occur
        raise Exception("{}".format(e))
    else:
        if cached_run_results:
            # if cached run found, simply return it
            log(
                "Succesfully parsed cached idf run in {:,.2f} seconds".format(
                    time.time() - start_time
                ),
                name=eplus_file.basename(),
            )
            # return_idf
            if return_idf:
                filepath = os.path.join(
                    output_directory,
                    hash_file(output_directory / eplus_file.basename(), args),
                    eplus_file.basename(),
                )
                idf = load_idf(
                    filepath, output_folder=output_directory, include=include
                )
            else:
                idf = None
            from itertools import compress

            return_elements = list(
                compress([cached_run_results, idf], [True, return_idf])
            )
            return _unpack_tuple(return_elements)

    runs_not_found = eplus_file
    # </editor-fold>

    # <editor-fold desc="Upgrade the file version if needed">
    if ep_version:
        # replace the dots with "-"
        ep_version = ep_version.replace(".", "-")
    eplus_file = idf_version_updater(
        upgraded_file(eplus_file, output_directory),
        to_version=ep_version,
        out_dir=output_directory,
    )
    # In case the file has been updated, update the versionid of the file
    # and the idd_file
    versionid = get_idf_version(eplus_file, doted=False)
    idd_file = Path(getiddfile(get_idf_version(eplus_file, doted=True)))
    # </editor-fold>

    # Prepare outputs e.g. sql table
    if prep_outputs:
        # Check if idf file has necessary objects (eg specific outputs)
        prepare_outputs(
            eplus_file, prep_outputs, idd_file, output_directory, epw=weather_file
        )

    if runs_not_found:
        # continue with simulation of other files
        log(
            "no cached run for {}. Running EnergyPlus...".format(
                os.path.basename(eplus_file)
            ),
            name=eplus_file.basename(),
        )

        start_time = time.time()
        if isinstance(include, str):
            include = Path().abspath().glob(include)
        elif include is not None:
            include = [Path(file) for file in include]
        # run the EnergyPlus Simulation
        with tempdir(
            prefix="eplus_run_", suffix=output_prefix, dir=output_directory
        ) as tmp:
            log(
                "temporary dir (%s) created" % tmp, lg.DEBUG, name=eplus_file.basename()
            )
            if include:
                include = [file.copy(tmp) for file in include]
            tmp_file = Path(eplus_file.copy(tmp))
            runargs = {
                "tmp": tmp,
                "eplus_file": tmp_file,
                "weather": Path(weather_file.copy(tmp)),
                "verbose": verbose,
                "output_directory": output_directory,
                "ep_version": versionid,
                "output_prefix": hash_file(tmp_file, args),
                "idd": Path(idd_file.copy(tmp)),
                "annual": annual,
                "epmacro": epmacro,
                "readvars": readvars,
                "output_suffix": output_suffix,
                "version": version,
                "expandobjects": expandobjects,
                "design_day": design_day,
                "keep_data_err": keep_data_err,
                "output_report": output_report,
                "include": include,
            }

            _run_exec(**runargs)

            log(
                "EnergyPlus Completed in {:,.2f} seconds".format(
                    time.time() - start_time
                ),
                name=eplus_file.basename(),
            )

            processes = {"*.csv": _process_csv}  # output_prefix +
            if custom_processes is not None:
                processes.update(custom_processes)

            results = []
            if process_files:

                for glob, process in processes.items():
                    results.extend(
                        [
                            (
                                file.basename(),
                                process(
                                    file,
                                    working_dir=os.getcwd(),
                                    simulname=output_prefix,
                                ),
                            )
                            for file in tmp.files(glob)
                        ]
                    )

            save_dir = output_directory / hash_file(eplus_file, args)
            if keep_data:
                (save_dir).rmtree_p()
                tmp.copytree(save_dir)

                log(
                    "Files generated at the end of the simulation: %s"
                    % "\n".join((save_dir).files()),
                    lg.DEBUG,
                    name=eplus_file.basename(),
                )
                if return_files:
                    results.extend((save_dir).files())

                # save runargs
                cache_runargs(tmp_file, runargs.copy())

            # Return summary DataFrames
            runargs["output_directory"] = save_dir
            cached_run_results = get_report(**runargs)
            if cached_run_results:
                results.extend([cached_run_results])
            if return_idf:
                idf = load_idf(
                    eplus_file, output_folder=output_directory, include=include
                )
                results.extend([idf])
        return _unpack_tuple(results)


def upgraded_file(eplus_file, output_directory):
    """returns the eplus_file path that would have been copied in the output
    directory if it exists"""
    eplus_file = next(iter(output_directory.glob("*.idf")), eplus_file)
    return eplus_file


def _process_csv(file, working_dir, simulname):
    """
    Args:
        file:
        working_dir:
        simulname:
    """
    try:
        log("looking for csv output, return the csv files " "in DataFrames if " "any")
        if "table" in file.basename():
            tables_out = working_dir.abspath() / "tables"
            tables_out.makedirs_p()
            file.copy(
                tables_out / "%s_%s.csv" % (file.basename().stripext(), simulname)
            )
            return
        log("try to store file %s in DataFrame" % (file))
        df = pd.read_csv(file, sep=",", encoding="us-ascii")
        log("file %s stored" % file)
        return df
    except Exception:
        pass


def _run_exec(
    tmp,
    eplus_file,
    weather,
    output_directory,
    annual,
    design_day,
    idd,
    epmacro,
    expandobjects,
    readvars,
    output_prefix,
    output_suffix,
    version,
    verbose,
    ep_version,
    keep_data_err,
    output_report,
    include,
):
    """Wrapper around the EnergyPlus command line interface.

    Adapted from :func:`eppy.runner.runfunctions.run`.

    Args:
        tmp:
        eplus_file:
        weather:
        output_directory:
        annual:
        design_day:
        idd:
        epmacro:
        expandobjects:
        readvars:
        output_prefix:
        output_suffix:
        version:
        verbose:
        ep_version:
        keep_data_err:
        output_report:
        include:
    """

    args = locals().copy()
    # get unneeded params out of args ready to pass the rest to energyplus.exe
    verbose = args.pop("verbose")
    eplus_file = args.pop("eplus_file")
    iddname = args.get("idd")
    tmp = args.pop("tmp")
    keep_data_err = args.pop("keep_data_err")
    output_directory = args.pop("output_directory")
    output_report = args.pop("output_report")
    idd = args.pop("idd")
    include = args.pop("include")
    try:
        idf_path = os.path.abspath(eplus_file.idfname)
    except AttributeError:
        idf_path = os.path.abspath(eplus_file)
    ep_version = args.pop("ep_version")
    # get version from IDF object or by parsing the IDF file for it
    if not ep_version:
        try:
            ep_version = "-".join(str(x) for x in eplus_file.idd_version[:3])
        except AttributeError:
            raise AttributeError(
                "The ep_version must be set when passing an IDF path. \
                Alternatively, use IDF.run()"
            )

    eplus_exe_path, eplus_weather_path = eppy.runner.run_functions.install_paths(
        ep_version, iddname
    )
    if version:
        # just get EnergyPlus version number and return
        cmd = [eplus_exe_path, "--version"]
        subprocess.check_call(cmd)
        return

    # convert paths to absolute paths if required
    if os.path.isfile(args["weather"]):
        args["weather"] = os.path.abspath(args["weather"])
    else:
        args["weather"] = os.path.join(eplus_weather_path, args["weather"])
    # args['output_directory'] = tmp.abspath()

    with tmp.abspath() as tmp:
        # build a list of command line arguments
        cmd = [eplus_exe_path]
        for arg in args:
            if args[arg]:
                if isinstance(args[arg], bool):
                    args[arg] = ""
                cmd.extend(["--{}".format(arg.replace("_", "-"))])
                if args[arg] != "":
                    cmd.extend([args[arg]])
        cmd.extend([idf_path])

        with subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        ) as process:
            _log_subprocess_output(
                process.stdout, name=eplus_file.basename(), verbose=verbose
            )
            if process.wait() != 0:
                error_filename = output_prefix + "out.err"
                with open(error_filename, "r") as stderr:
                    if keep_data_err:
                        failed_dir = output_directory / "failed"
                        failed_dir.mkdir_p()
                        tmp.copytree(failed_dir / output_prefix)
                    tmp.rmtree_p()
                    raise EnergyPlusProcessError(
                        cmd=cmd, idf=eplus_file.basename(), stderr=stderr.read()
                    )


def _log_subprocess_output(pipe, name, verbose):
    """
    Args:
        pipe:
        name:
        verbose:
    """
    logger = None
    for line in iter(pipe.readline, b""):
        if verbose == "v":
            logger = log(
                line.decode().strip("\n"),
                level=lg.DEBUG,
                name="eplus_run_" + name,
                filename="eplus_run_" + name,
                log_dir=os.getcwd(),
            )
    if logger:
        close_logger(logger)


def parallel_process(in_dict, function, processors=-1, use_kwargs=True):
    """A parallel version of the map function with a progress bar.

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
        >>> result = parallel_process(rundict, ar.run_eplus, use_kwargs=True)

    Args:
        in_dict (dict-like): A dictionary to iterate over.
        function (function): A python function to apply to the elements of
            in_dict
        processors (int): The number of cores to use
        use_kwargs (bool): If True, pass the kwargs as arguments to `function` .

    Returns:
        [function(array[0]), function(array[1]), ...]
    """
    from tqdm import tqdm
    from concurrent.futures import ProcessPoolExecutor, as_completed

    if processors == -1:
        processors = min(len(in_dict), multiprocessing.cpu_count())

    if processors == 1:
        kwargs = {
            "desc": function.__name__,
            "total": len(in_dict),
            "unit": "runs",
            "unit_scale": True,
            "leave": True,
        }
        if use_kwargs:
            futures = {a: function(**in_dict[a]) for a in tqdm(in_dict, **kwargs)}
        else:
            futures = {a: function(in_dict[a]) for a in tqdm(in_dict, **kwargs)}
    else:
        with ProcessPoolExecutor(max_workers=processors) as pool:
            if use_kwargs:
                futures = {pool.submit(function, **in_dict[a]): a for a in in_dict}
            else:
                futures = {pool.submit(function, in_dict[a]): a for a in in_dict}

            kwargs = {
                "desc": function.__name__,
                "total": len(futures),
                "unit": "runs",
                "unit_scale": True,
                "leave": True,
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
    """Simple function to hash a file and return it as a string. Will also hash
    the :py:func:`eppy.runner.run_functions.run()` arguments so that correct
    results are returned when different run arguments are used

    Todo:
        Hashing should include the external files used an idf file. For example,
        if a model uses a csv file as an input and that file changes, the
        hashing will currently not pickup that change. This could result in
        loading old results without the user knowing.

    Args:
        eplus_file (str): path of the idf file
        kwargs:

    Returns:
        str: The digest value as a string of hexadecimal digits
    """
    hasher = hashlib.md5()
    with open(eplus_file, "rb") as afile:
        buf = afile.read()
        hasher.update(buf)
        hasher.update(kwargs.__str__().encode("utf-8"))  # Hashing the kwargs as well
    return hasher.hexdigest()


def get_report(
    eplus_file, output_directory=None, output_report="sql", output_prefix=None, **kwargs
):
    """Returns the specified report format (html or sql)

    Args:
        eplus_file (str): path of the idf file
        output_directory (str, optional): path to the output folder. Will
            default to the settings.cache_folder.
        output_report: 'html' or 'sql'
        output_prefix:
        **kwargs: keyword arguments to pass to hasher.

    Returns:
        dict: a dict of DataFrames
    """
    # Hash the idf file with any kwargs used in the function
    if output_prefix is None:
        output_prefix = hash_file(eplus_file, kwargs)
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
    elif output_report.lower() == "sql_file":
        # Get the sql report
        fullpath_filename = output_directory / output_prefix + "out.sql"
        if fullpath_filename.exists():
            return fullpath_filename
        else:
            raise FileNotFoundError(
                'File "{}" does not exist'.format(fullpath_filename)
            )
    else:
        return None


def get_from_cache(kwargs):
    """Retrieve a EPlus Tabulated Summary run result from the cache

    Args:
        kwargs (dict): Args used to create the cache name.

    Returns:
        dict: dict of DataFrames
    """
    output_directory = Path(kwargs.get("output_directory"))
    output_report = kwargs.get("output_report")
    eplus_file = next(iter(output_directory.glob("*.idf")), None)
    if not eplus_file:
        return None
    if settings.use_cache:
        # determine the filename by hashing the eplus_file
        cache_filename_prefix = hash_file(eplus_file, kwargs)

        if output_report is None:
            return None
        elif "htm" in output_report.lower():
            # Get the html report

            cache_fullpath_filename = (
                output_directory / cache_filename_prefix / cache_filename_prefix
                + "tbl.htm"
            )
            if cache_fullpath_filename.exists():
                return get_html_report(cache_fullpath_filename)

        elif "sql" == output_report.lower():
            # get the SQL report
            if not output_directory:
                output_directory = settings.cache_folder / cache_filename_prefix

            cache_fullpath_filename = (
                output_directory / cache_filename_prefix / cache_filename_prefix
                + "out.sql"
            )

            if cache_fullpath_filename.exists():
                # get reports from passed-in report names or from
                # settings.available_sqlite_tables if None are given
                return get_sqlite_report(
                    cache_fullpath_filename,
                    kwargs.get("report_tables", settings.available_sqlite_tables),
                )
        elif "sql_file" == output_report.lower():
            # get the SQL report
            if not output_directory:
                output_directory = settings.cache_folder / cache_filename_prefix

            cache_fullpath_filename = (
                output_directory / cache_filename_prefix / cache_filename_prefix
                + "out.sql"
            )
            if cache_fullpath_filename.exists():
                return cache_fullpath_filename


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


def idf_version_updater(idf_file, to_version=None, out_dir=None, simulname=None):
    """EnergyPlus idf version updater using local transition program.

    Update the EnergyPlus simulation file (.idf) to the latest available
    EnergyPlus version installed on this machine. Optionally specify a version
    (eg.: "8-9-0") to aim for a specific version. The output will be the path of
    the updated file. The run is multiprocessing_safe.

    Hint:
        If attempting to upgrade an earlier version of EnergyPlus ( pre-v7.2.0),
        specific binaries need to be downloaded and copied to the
        EnergyPlus*/PreProcess/IDFVersionUpdater folder. More info at
        `Converting older version files
        <http://energyplus.helpserve.com/Knowledgebase/List/Index/46
        /converting-older-version-files>`_ .

    Args:
        idf_file (Path): path of idf file
        to_version (str, optional): EnergyPlus version in the form "X-X-X".
        out_dir (Path): path of the output_dir
        simulname (str or None, optional): this name will be used for temp dir
            id and saved outputs. If not provided, uuid.uuid1() is used. Be
            careful to avoid naming collision : the run will alway be done in
            separated folders, but the output files can overwrite each other if
            the simulname is the same. (default: None)

    Returns:
        Path: The path of the transitioned idf file.
    """
    if not out_dir.isdir():
        out_dir.makedirs_p()
    with tempdir(prefix="transition_run_", suffix=simulname, dir=out_dir) as tmp:
        log("temporary dir (%s) created" % tmp, lg.DEBUG)
        idf_file = Path(idf_file.copy(tmp)).abspath()  # copy and return abspath

        versionid = get_idf_version(idf_file, doted=False)[0:5]
        doted_version = get_idf_version(idf_file, doted=True)
        iddfile = getiddfile(doted_version)
        if os.path.exists(iddfile):
            # if a E+ exists, pass
            pass
            # might be an old version of E+
        elif tuple(map(int, doted_version.split("."))) < (8, 0):
            # else if the version is an old E+ version (< 8.0)
            iddfile = getoldiddfile(doted_version)
        # use to_version
        if to_version is None:
            # What is the latest E+ installed version
            to_version = find_eplus_installs(iddfile)
        if tuple(versionid.split("-")) > tuple(to_version.split("-")):
            log(
                'The version of the idf file "{}: v{}" is higher than any '
                "version of EnergyPlus installed on this machine. Please "
                'install EnergyPlus version "{}" or higher. Latest version '
                "found: {}".format(
                    os.path.basename(idf_file), versionid, versionid, to_version
                ),
                lg.WARNING,
            )
            return None
        to_iddfile = Path(getiddfile(to_version.replace("-", ".")))
        vupdater_path = to_iddfile.dirname() / "PreProcess" / "IDFVersionUpdater"
        trans_exec = {
            "1-0-0": os.path.join(vupdater_path, "Transition-V1-0-0-to-V1-0-1"),
            "1-0-1": os.path.join(vupdater_path, "Transition-V1-0-1-to-V1-0-2"),
            "1-0-2": os.path.join(vupdater_path, "Transition-V1-0-2-to-V1-0-3"),
            "1-0-3": os.path.join(vupdater_path, "Transition-V1-0-3-to-V1-1-0"),
            "1-1-0": os.path.join(vupdater_path, "Transition-V1-1-0-to-V1-1-1"),
            "1-1-1": os.path.join(vupdater_path, "Transition-V1-1-1-to-V1-2-0"),
            "1-2-0": os.path.join(vupdater_path, "Transition-V1-2-0-to-V1-2-1"),
            "1-2-1": os.path.join(vupdater_path, "Transition-V1-2-1-to-V1-2-2"),
            "1-2-2": os.path.join(vupdater_path, "Transition-V1-2-2-to-V1-2-3"),
            "1-2-3": os.path.join(vupdater_path, "Transition-V1-2-3-to-V1-3-0"),
            "1-3-0": os.path.join(vupdater_path, "Transition-V1-3-0-to-V1-4-0"),
            "1-4-0": os.path.join(vupdater_path, "Transition-V1-4-0-to-V2-0-0"),
            "2-0-0": os.path.join(vupdater_path, "Transition-V2-0-0-to-V2-1-0"),
            "2-1-0": os.path.join(vupdater_path, "Transition-V2-1-0-to-V2-2-0"),
            "2-2-0": os.path.join(vupdater_path, "Transition-V2-2-0-to-V3-0-0"),
            "3-0-0": os.path.join(vupdater_path, "Transition-V3-0-0-to-V3-1-0"),
            "3-1-0": os.path.join(vupdater_path, "Transition-V3-1-0-to-V4-0-0"),
            "4-0-0": os.path.join(vupdater_path, "Transition-V4-0-0-to-V5-0-0"),
            "5-0-0": os.path.join(vupdater_path, "Transition-V5-0-0-to-V6-0-0"),
            "6-0-0": os.path.join(vupdater_path, "Transition-V6-0-0-to-V7-0-0"),
            "7-0-0": os.path.join(vupdater_path, "Transition-V7-0-0-to-V7-1-0"),
            "7-1-0": os.path.join(vupdater_path, "Transition-V7-1-0-to-V7-2-0"),
            "7-2-0": os.path.join(vupdater_path, "Transition-V7-2-0-to-V8-0-0"),
            "8-0-0": os.path.join(vupdater_path, "Transition-V8-0-0-to-V8-1-0"),
            "8-1-0": os.path.join(vupdater_path, "Transition-V8-1-0-to-V8-2-0"),
            "8-2-0": os.path.join(vupdater_path, "Transition-V8-2-0-to-V8-3-0"),
            "8-3-0": os.path.join(vupdater_path, "Transition-V8-3-0-to-V8-4-0"),
            "8-4-0": os.path.join(vupdater_path, "Transition-V8-4-0-to-V8-5-0"),
            "8-5-0": os.path.join(vupdater_path, "Transition-V8-5-0-to-V8-6-0"),
            "8-6-0": os.path.join(vupdater_path, "Transition-V8-6-0-to-V8-7-0"),
            "8-7-0": os.path.join(vupdater_path, "Transition-V8-7-0-to-V8-8-0"),
            "8-8-0": os.path.join(vupdater_path, "Transition-V8-8-0-to-V8-9-0"),
            "8-9-0": os.path.join(vupdater_path, "Transition-V8-9-0-to-V9-0-0"),
            "9-0-0": os.path.join(vupdater_path, "Transition-V9-0-0-to-V9-1-0"),
        }
        # store the directory we start in
        cwd = os.getcwd()
        run_dir = Path(os.path.dirname(trans_exec[versionid]))

        if versionid == to_version:
            # if file version and to_veersion are the same, we don't need to
            # perform transition
            log(
                'file {} already upgraded to latest version "{}"'.format(
                    idf_file, versionid
                )
            )
            idf_file = Path(idf_file.copy(out_dir))
            return idf_file

        # build a list of command line arguments
        with cd(run_dir):
            transitions = [
                key
                for key in trans_exec
                if tuple(map(int, key.split("-")))
                < tuple(map(int, to_version.split("-")))
                and tuple(map(int, key.split("-")))
                >= tuple(map(int, versionid.split("-")))
            ]
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
                            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
                        )
                        process_output, error_output = process.communicate()
                        log(process_output.decode("utf-8"), lg.DEBUG)
                    except CalledProcessError as exception:
                        log(
                            "{} failed with error\n".format(
                                idf_version_updater.__name__, str(exception)
                            ),
                            lg.ERROR,
                        )
        for f in tmp.files("*.idfnew"):
            f.copy(out_dir / idf_file.basename())
        return Path(out_dir / idf_file.basename())


def find_eplus_installs(iddfile):
    """Finds all installed versions of EnergyPlus in the default location and
    returns the latest version number

    Args:
        iddfile:

    Returns:
        (str): The version number of the latest E+ install
    """
    vupdater_path, _ = iddfile.split("Energy+")
    path_to_eplus, _ = vupdater_path.split("EnergyPlus")

    # Find all EnergyPlus folders
    list_eplus_dir = glob.glob(os.path.join(path_to_eplus, "EnergyPlus*"))

    # check if any EnergyPlus install exists
    if not list_eplus_dir:
        raise Exception(
            "No EnergyPlus installation found. Make sure "
            "you have EnergyPlus installed. Go to "
            "https://energyplus.net/downloads to download the "
            "latest version of EnergyPlus."
        )

    # Find the most recent version of EnergyPlus installed from the version
    # number (at the end of the folder name)
    v0 = (0, 0, 0)  # Initialize the version number
    # Find the most recent version in the different folders found
    for dir in list_eplus_dir:
        version = dir[-5:]
        ver = tuple(map(int, version.split("-")))
        if ver > v0:
            v0 = ver

    return "-".join(tuple(map(str, v0)))


def get_idf_version(file, doted=True):
    """Get idf version quickly by reading first few lines of idf file containing
    the 'VERSION' identifier

    Args:
        file (str): Absolute or relative Path to the idf file
        doted (bool, optional): Wheter or not to return the version number

    Returns:
        str: the version id
    """
    with open(os.path.abspath(file), "r", encoding="latin-1") as fhandle:
        try:
            txt = fhandle.read()
            ntxt = parse_idd.nocomment(txt, "!")
            blocks = ntxt.split(";")
            blocks = [block.strip() for block in blocks]
            bblocks = [block.split(",") for block in blocks]
            bblocks1 = [[item.strip() for item in block] for block in bblocks]
            ver_blocks = [block for block in bblocks1 if block[0].upper() == "VERSION"]
            ver_block = ver_blocks[0]
            if doted:
                versionid = ver_block[1]
            else:
                versionid = ver_block[1].replace(".", "-") + "-0"
        except Exception as e:
            log('Version id for file "{}" cannot be found'.format(file))
            log("{}".format(e))
            raise
        else:
            return versionid


def getoldiddfile(versionid):
    """find the IDD file of the E+ installation E+ version 7 and earlier have
    the idd in /EnergyPlus-7-2-0/bin/Energy+.idd

    Args:
        versionid:
    """
    vlist = versionid.split(".")
    if len(vlist) == 1:
        vlist = vlist + ["0", "0"]
    elif len(vlist) == 2:
        vlist = vlist + ["0"]
    ver_str = "-".join(vlist)
    eplus_exe, _ = eppy.runner.run_functions.install_paths(ver_str)
    eplusfolder = os.path.dirname(eplus_exe)
    iddfile = "{}/bin/Energy+.idd".format(eplusfolder)
    return iddfile


if __name__ == "__main__":
    pass
