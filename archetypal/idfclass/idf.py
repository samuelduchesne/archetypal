################################################################################
# Module: idf.py
# Description: Various functions for processing of EnergyPlus models and
#              retrieving results in different forms
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import logging as lg
import os
import re
import sqlite3
import subprocess
import time
from collections import defaultdict
from io import StringIO
from math import isclose
from tempfile import TemporaryDirectory

import eppy
import pandas as pd
from deprecation import deprecated
from opyplus import Epm, Idd
from opyplus.epm.record import Record
from pandas.errors import ParserError
from path import Path
from tqdm import tqdm

from archetypal import ReportData, __version__, extend_class, log, settings
from archetypal.energypandas import EnergySeries
from archetypal.eplus_interface.energy_plus import EnergyPlusThread
from archetypal.eplus_interface.exceptions import (
    EnergyPlusProcessError,
    EnergyPlusVersionError,
    EnergyPlusWeatherError,
)
from archetypal.eplus_interface.expand_objects import ExpandObjectsThread
from archetypal.eplus_interface.slab import SlabThread
from archetypal.eplus_interface.transition import TransitionThread
from archetypal.eplus_interface.version import (
    EnergyPlusVersion,
    _latest_energyplus_version,
    get_eplus_dirs,
)
from archetypal.idfclass.meters import Meters
from archetypal.idfclass.outputs import Outputs
from archetypal.idfclass.reports import get_report
from archetypal.idfclass.util import get_idf_version, hash_model
from archetypal.idfclass.variables import Variables
from archetypal.schedule import Schedule


class IDF(object):
    """Class for loading and parsing idf models and running simulations and
    retrieving results.
    """

    def __init__(
        self,
        idfname=None,
        epw=None,
        as_version=settings.ep_version,
        annual=False,
        design_day=False,
        expandobjects=False,
        convert=False,
        verbose=settings.log_console,
        readvars=True,
        prep_outputs=True,
        include=None,
        custom_processes=None,
        simulname=None,
        output_suffix="L",
        epmacro=False,
        keep_data=True,
        keep_data_err=False,
        position=0,
        check_required=True,
        check_length=True,
        **kwargs,
    ):
        """
        Args:
            idfname (str _TemporaryFileWrapper): The idf model filename.
            epw (str or Path): The weather-file

        EnergyPlus args:
            tmp_dir=None,
            as_version=None,
            prep_outputs=True,
            include=None,
            keep_original=True,
        """
        # Set independents to there original values
        self.idfname = idfname
        self.epw = epw
        self.check_required = check_required
        self.check_length = check_length
        self.as_version = as_version if as_version else settings.ep_version
        self._custom_processes = custom_processes
        self._include = include or []
        self.keep_data_err = keep_data_err
        self._keep_data = keep_data
        self._simulname = simulname
        self.output_suffix = output_suffix
        self.verbose = verbose
        self.readvars = readvars
        self.expandobjects = expandobjects
        self.convert = convert
        self.epmacro = epmacro
        self.design_day = design_day
        self.annual = annual
        self.prep_outputs = prep_outputs
        self._position = position
        self.output_prefix = None

        # Set dependants to None
        self._output_directory = None
        self._file_version = None
        self._iddname = None
        self._idd_info = None
        self._idd_index = None
        self._idd_version = None
        self._idfobjects = None
        self._block = None
        self._model = None
        self._sql = None
        self._sql_file = None
        self._htm = None
        self._original_ep_version = None
        self._schedules_dict = None
        self._outputs = None
        self._partition_ratio = None
        self._area_conditioned = None
        self._area_unconditioned = None
        self._area_total = None
        self._schedules = None
        self._meters = None
        self._variables = None
        self._energyplus_its = 0
        self._sim_id = None

        self.load_kwargs = dict(epw=epw, **kwargs)
        self.original_idfname = self.idfname  # Save original
        self._original_cache = hash_model(self.idfname)
        # Move to tmp_dir, if we want to keep the original file intact.
        if settings.use_cache:
            previous_file = self.output_directory / (self.name or str(self.idfname))
            if previous_file.exists():
                # We have a transitioned or cached file here; Load this one.
                cache_file_version = EnergyPlusVersion(get_idf_version(previous_file))
                if cache_file_version <= self.as_version:
                    self.idfname = previous_file
            else:
                if not isinstance(self.idfname, StringIO):
                    self.output_directory.makedirs_p()
                    self.idfname = self.idfname.copy(self.output_directory / self.name)

        if self.file_version < self.as_version:
            self.upgrade(to_version=self.as_version)

        self._workspace = Epm.load(
            self.idfname,
            check_required=self.check_required,
            check_length=self.check_length,
            idd_or_version=self.as_version.tuple,
        )

        # Set model outputs
        self._outputs = Outputs(idf=self)
        if self.prep_outputs:
            (
                self._outputs.add_basics()
                .add_umi_template_outputs()
                .add_custom(outputs=self.prep_outputs)
                .add_profile_gas_elect_ouputs()
                .apply()
            )

    def __str__(self):
        return self.name

    def valid_idds(self):
        """Returns all valid idd version numbers found in IDFVersionUpdater folder"""
        return self.idf_version._choices

    def getiddname(self):
        """Get the name of the current IDD used by eppy.

        Returns
        -------
        str

        """
        return self.iddname

    @property
    def idfobjects(self):
        return self._workspace

    @property
    def idd_version(self):
        return self.idfobjects._dev_idd.version

    @property
    def iddname(self):
        if self._iddname is None:
            if self.file_version > self.as_version:
                raise EnergyPlusVersionError(
                    f"{self.as_version} cannot be lower then "
                    f"the version number set in the model"
                )
            try:
                idd_filename = Path(
                    Idd._dev_get_from_cache(self.file_version.tuple).path
                )
            except ValueError:
                # Try finding the one in IDFVersionsUpdater
                idd_filename = (
                    self.idfversionupdater_dir / f"V"
                    f"{self.file_version.dash}-Energy+.idd"
                ).expand()
            self._iddname = idd_filename
        return self._iddname

    def save(self):
        """Saves changes to idf file. Returns True is successful"""
        dst = self.idfname
        return self._workspace.save(dst, dump_external_files=True)

    def saveas(self, filename, dump_external_files=False):
        """Saves changes to another filename. Returns True is successful"""
        dst = filename
        return self._workspace.save(dst, dump_external_files=dump_external_files)

    def savecopy(self, filename, dump_external_files=True):
        """Saves changes to another filename. Returns True is successful.
        Same as :ref:`archetypal.idfclass.IDF.saveas`"""
        dst = Path(filename).expand()
        self._workspace.save(dst, dump_external_files=dump_external_files)
        return dst

    @property
    def idf_objects(self):
        """Retruns list of IDF objects"""
        return list(self._workspace.objects())

    @property
    def file_version(self):
        if self._file_version is None:
            return EnergyPlusVersion(get_idf_version(self.idfname))

    @property
    def custom_processes(self):
        return self._custom_processes

    @property
    def include(self):
        return self._include

    @property
    def keep_data_err(self):
        return self._keep_data_err

    @keep_data_err.setter
    def keep_data_err(self, value):
        if not isinstance(value, bool):
            raise TypeError("'keep_data_err' needs to be a bool")
        self._keep_data_err = value

    @property
    def keep_data(self):
        return self._keep_data

    @property
    def simulname(self):
        return self._simulname

    @property
    def output_suffix(self):
        return self._output_suffix

    @output_suffix.setter
    def output_suffix(self, value):
        choices = ["L", "C", "D"]
        if value not in choices:
            raise ValueError(f"Choices of 'output_suffix' are {choices}")
        self._output_suffix = value

    # region User-Defined Properties (have setter)
    @property
    def idfname(self):
        """The path of the active (parsed) idf model. If `settings.use_cache ==
        True`, then this path will point to `settings.cache_folder`. See
        :meth:`~archetypal.utils.config`"""
        if self._idfname is None:
            idfname = StringIO(f"VERSION, {_latest_energyplus_version()};")
            idfname.seek(0)
            self._idfname = idfname
        else:
            if isinstance(self._idfname, StringIO):
                self._idfname.seek(0)
            else:
                self._idfname = Path(self._idfname).expand()
        return self._idfname

    @idfname.setter
    def idfname(self, value):
        if value:
            self._idfname = Path(value).expand()
        else:
            self._idfname = None

    @property
    def epw(self):
        if self._epw is not None:
            return Path(self._epw).expand()

    @epw.setter
    def epw(self, value):
        if value:
            self._epw = Path(value).expand()
        else:
            self._epw = None

    @property
    def verbose(self):
        return self._verbose

    @verbose.setter
    def verbose(self, value):

        if not isinstance(value, bool):
            raise TypeError("'verbose' needs to be a bool")
        self._verbose = value

    @property
    def expandobjects(self):
        return self._expandobjects

    @expandobjects.setter
    def expandobjects(self, value):
        if not isinstance(value, bool):
            raise TypeError("'expandobjects' needs to be a bool")
        self._expandobjects = value

    @property
    def readvars(self):
        return self._readvars

    @readvars.setter
    def readvars(self, value):
        if not isinstance(value, bool):
            raise TypeError("'readvars' needs to be a bool")
        self._readvars = value

    @property
    def epmacro(self):
        return self._epmacro

    @epmacro.setter
    def epmacro(self, value):
        if not isinstance(value, bool):
            raise TypeError("'epmacro' needs to be a bool")
        self._epmacro = value

    @property
    def design_day(self):
        return self._design_day

    @design_day.setter
    def design_day(self, value):
        if not isinstance(value, bool):
            raise TypeError("'design_day' needs to be a bool")
        self._design_day = value

    @property
    def annual(self):
        return self._annual

    @annual.setter
    def annual(self, value):
        if not isinstance(value, bool):
            raise TypeError("'annual' needs to be a bool")
        self._annual = value

    @property
    def convert(self):
        return self._convert

    @convert.setter
    def convert(self, value):
        if not isinstance(value, bool):
            raise TypeError("'convert' needs to be a bool")
        self._convert = value

    @property
    def prep_outputs(self):
        """Bool or set list of custom outputs"""
        return self._prep_outputs

    @prep_outputs.setter
    def prep_outputs(self, value):
        self._prep_outputs = value

    @property
    def as_version(self):
        if self._as_version is None:
            self._as_version = _latest_energyplus_version()
        return EnergyPlusVersion(self._as_version)

    @as_version.setter
    def as_version(self, value):
        # Parse value and check if above or bellow
        self._as_version = EnergyPlusVersion(value)

    @property
    def output_directory(self):
        """Returns the output directory based on the hashing of the original file (
        before transitions or modifications)."""
        if self._output_directory is None:
            cache_filename = self._original_cache
            output_directory = settings.cache_folder / cache_filename
            output_directory.makedirs_p()
            self._output_directory = output_directory.expand()
        return Path(self._output_directory)

    @output_directory.setter
    def output_directory(self, value):
        if value and not Path(value).exists():
            raise ValueError(
                f"The tmp_dir '{value}' must be created before being assigned"
            )
        elif value:
            value = Path(value)
        self._output_directory = value

    @property
    def output_prefix(self):
        if self._output_prefix is None:
            self._output_prefix = self.name.stem
        return self._output_prefix

    @output_prefix.setter
    def output_prefix(self, value):
        if value and not isinstance(value, str):
            raise TypeError("'output_prefix' needs to be a string")
        self._output_prefix = value

    @property
    def sim_id(self):
        """Returns the hash of the model"""
        if self._sim_id is None:
            self._sim_id = hash_model(
                self,
                epw=self.epw,
                annual=self.annual,
                design_day=self.design_day,
                readvars=self.readvars,
                ep_version=self.as_version,
            )
        return self._sim_id

    @sim_id.setter
    def sim_id(self, value):
        if value and not isinstance(value, str):
            raise TypeError("'output_prefix' needs to be a string")
        self._sim_id = value

    # endregion

    @property
    def position(self):
        return self._position

    @property
    def idfversionupdater_dir(self):
        return (
            get_eplus_dirs(settings.ep_version) / "PreProcess" / "IDFVersionUpdater"
        ).expand()

    @property
    def idf_version(self):
        return self.file_version

    @property
    def name(self):
        if isinstance(self.idfname, StringIO):
            return None
        return self.idfname.basename()

    def sql(self):
        """Get the sql table report"""
        if self._sql is None:
            try:
                sql_dict = get_report(
                    self.idfname,
                    self.simulation_dir,
                    output_report="sql",
                    output_prefix=self.output_prefix,
                )
            except FileNotFoundError:
                # check if htm output is in file
                sql_object = self.anidfobject(
                    key="Output:SQLite".upper(), Option_Type="SimpleAndTabular"
                )
                if sql_object not in self.idfobjects.Output_SQLite:
                    self.addidfobject(sql_object)
                return self.simulate().sql()
            except Exception as e:
                raise e
            else:
                self._sql = sql_dict
        return self._sql

    @property
    def htm(self):
        """Get the htm table report"""
        if self._htm is None:
            try:
                htm_dict = get_report(
                    self.idfname,
                    self.simulation_dir,
                    output_report="htm",
                    output_prefix=self.output_prefix,
                )
            except FileNotFoundError:
                return self.simulate().htm
            else:
                self._htm = htm_dict
        return self._htm

    @property
    def energyplus_its(self):
        """Number of iterations needed to complete simulation"""
        if self._energyplus_its is None:
            self._energyplus_its = 0
        return self._energyplus_its

    def htm_open(self):
        """Open .htm file in browser"""
        import webbrowser

        html, *_ = self.simulation_dir.files("*.htm")

        webbrowser.open(html.abspath())

    def idf_open(self):
        """Open .idf file in Ep-Launch"""

        self.save()

        filepath = self.idfname

        import os
        import platform
        import subprocess

        if platform.system() == "Darwin":  # macOS
            subprocess.call(("open", filepath))
        elif platform.system() == "Windows":  # Windows
            os.startfile(filepath)
        else:  # linux variants
            subprocess.call(("xdg-open", filepath))

    def idf_open_last_sim(self):
        """Open last simulation in Ep-Launch"""

        filepath, *_ = self.simulation_dir.files("*.idf")

        import os
        import platform
        import subprocess

        if platform.system() == "Darwin":  # macOS
            subprocess.call(("open", filepath))
        elif platform.system() == "Windows":  # Windows
            os.startfile(filepath)
        else:  # linux variants
            subprocess.call(("xdg-open", filepath))

    def mdd_open(self):
        """Open .mdd file in browser. This file shows all the report meters along
        with their “availability” for the current input file"""
        import webbrowser

        mdd, *_ = self.simulation_dir.files("*.mdd")

        webbrowser.open(mdd.abspath())

    def mtd_open(self):
        """Open .mtd file in browser. This file contains the “meter details” for the
        run. This shows what report variables are on which meters and vice versa –
        which meters contain what report variables."""
        import webbrowser

        mtd, *_ = self.simulation_dir.files("*.mtd")

        webbrowser.open(mtd.abspath())

    @property
    def sql_file(self):
        """Get the sql file path"""
        try:
            file, *_ = self.simulation_dir.files("*out.sql")
        except (FileNotFoundError, ValueError):
            return self.simulate().sql_file
        return file.expand()

    @property
    def net_conditioned_building_area(self):
        """Returns the total conditioned area of a building (taking into account
        zone multipliers)
        """
        if self._area_conditioned is None:
            if self.simulation_dir.exists():
                with sqlite3.connect(self.sql_file) as conn:
                    sql_query = f"""
                            SELECT t.Value
                            FROM TabularDataWithStrings t
                            WHERE TableName == 'Building Area' and ColumnName == 'Area' and RowName == 'Net Conditioned Building Area';"""
                    (res,) = conn.execute(sql_query).fetchone()
                self._area_conditioned = float(res)
            else:
                area = 0
                zones = self.idfobjects.Zone
                zone: Record
                for zone in zones:
                    surface: Record
                    for surface in zone.zonesurfaces:
                        surface.set_defaults()
                        if hasattr(surface, "tilt"):
                            if surface.tilt == 180.0:
                                if zone.part_of_total_floor_area:
                                    part_of = int(
                                        zone.part_of_total_floor_area.upper() != "NO"
                                    )
                                else:
                                    part_of = 0
                                multiplier = float(
                                    zone.multiplier if zone.multiplier else 1
                                )

                                area += surface.area * multiplier * part_of
                self._area_conditioned = area
        return self._area_conditioned

    @property
    def unconditioned_building_area(self):
        """Returns the Unconditioned Building Area"""
        if self._area_unconditioned is None:
            if self.simulation_dir.exists():
                with sqlite3.connect(self.sql_file) as conn:
                    sql_query = f"""
                            SELECT t.Value
                            FROM TabularDataWithStrings t
                            WHERE TableName == 'Building Area' and 
                            ColumnName == 'Area' and RowName == 'Unconditioned Building Area';"""
                    (res,) = conn.execute(sql_query).fetchone()
                self._area_unconditioned = float(res)
            else:
                area = 0
                zones = self.idfobjects.Zone
                zone: Record
                for zone in zones:
                    for surface in zone.zonesurfaces:
                        if hasattr(surface, "tilt"):
                            if surface.tilt == 180.0:
                                part_of = int(
                                    zone.Part_of_Total_Floor_Area.upper() == "NO"
                                )
                                multiplier = float(
                                    zone.multiplier if zone.multiplier != "" else 1
                                )

                                area += surface.area * multiplier * part_of
                self._area_unconditioned = area
        return self._area_unconditioned

    @property
    def total_building_area(self):
        """"""
        if self._area_total is None:
            if self.simulation_dir.exists():
                with sqlite3.connect(self.sql_file) as conn:
                    sql_query = f"""
                            SELECT t.Value
                            FROM TabularDataWithStrings t
                            WHERE TableName == 'Building Area' and 
                            ColumnName == 'Area' and RowName == 'Total Building Area';"""
                    (res,) = conn.execute(sql_query).fetchone()
                self._area_total = float(res)
            else:
                area = 0
                zones = self.idfobjects.Zone
                zone: Record
                for zone in zones:
                    for surface in zone.zonesurfaces:
                        if hasattr(surface, "tilt"):
                            if surface.tilt == 180.0:
                                multiplier = float(
                                    zone.multiplier if zone.multiplier != "" else 1
                                )

                                area += surface.area * multiplier
                self._area_total = area
        return self._area_total

    @property
    def partition_ratio(self):
        """The number of lineal meters of partitions (Floor to ceiling) present
        in average in the building floor plan by m2.
        """
        if self._partition_ratio is None:
            partition_lineal = 0
            zones = self.idfobjects.Zone
            zone: Record
            for zone in zones:
                for surface in [
                    surf
                    for surf in zone.zonesurfaces
                    if surf.key.upper() not in ["INTERNALMASS", "WINDOWSHADINGCONTROL"]
                ]:
                    if hasattr(surface, "tilt"):
                        if (
                            surface.tilt == 90.0
                            and surface.outside_boundary_condition != "Outdoors"
                        ):
                            multiplier = float(
                                zone.multiplier if zone.multiplier else 1
                            )
                            partition_lineal += surface.width * multiplier
            self._partition_ratio = (
                partition_lineal / self.net_conditioned_building_area
            )
        return self._partition_ratio

    @property
    def simulation_files(self):
        try:
            return self.simulation_dir.files()
        except FileNotFoundError:
            return []

    @property
    def simulation_dir(self):
        """The path where simulation results are stored"""
        try:
            return (self.output_directory / self.sim_id).expand()
        except AttributeError:
            return Path()

    @property
    def schedules_dict(self):
        if self._schedules_dict is None:
            self._schedules_dict = self.get_all_schedules()
        return self._schedules_dict

    @property
    def schedules(self):
        if self._schedules is None:
            schedules = {}
            for schd in self.schedules_dict:
                schedules[schd] = Schedule(Name=schd, idf=self)
            self._umischedules = schedules
        return self._umischedules

    @property
    def outputs(self):
        return self._outputs

    @property
    def day_of_week_for_start_day(self):
        """Get day of week for start day for the first found RUNPERIOD"""
        import calendar

        day = self.idfobjects.Runperiod.one().Day_of_Week_for_Start_Day

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

    @property
    def meters(self):
        """List of available meters for the :class:`IDF` model.

        The :class:`IDF` model must be simulated once (to retrieve the .mdd file).

        The listed meters may or may not be included in the idf file. If they are
        not, the output is added to the file and the model is simulated again. The
        output is appended to the :attr:`IDF.idfobjects` list, but will not overwrite the
        original idf file, unless :meth:`IDF.save` is called.

        Hint:
            Call `idf.meters.<output_group>.<meter_name>.values()` to retreive a
            time-series based on the :class:`pandas.Series` class which can be plotted.

            See :class:`Meter` and :class:`EnergySeries` for more information.

        Example:
            The IDF.meters attribute is populated with meters categories
            (`Output:Meter` or `Output:Meter:Cumulative`) and each category is
            populated with all the available meters.

            .. code-block::

                >>> IDF.meters.OutputMeter.WaterSystems__MainsWater
                >>> IDF.meters.OutputMeterCumulative.WaterSystems__MainsWater
        """
        if self._meters is None:
            try:
                self.simulation_dir.files("*.mdd")
            except FileNotFoundError:
                raise Exception(
                    "call IDF.simulate() at least once to get a list of "
                    "possible meters"
                )
            else:
                self._meters = Meters(self)
        return self._meters

    @property
    def variables(self):
        """List of available meters for the :class:`IDF` model.

        The :class:`IDF` model must be simulated once (to retrieve the .mdd file).

        The listed meters may or may not be included in the idf file. If they are
        not, the output is added to the file and the model is simulated again. The
        output is appended to the :attr:`IDF.idfobjects` list, but will not overwrite
        the
        original idf file, unless :meth:`IDF.save` is called.

        Hint:
            Call `idf.vairables.<output_group>.<meter_name>.values()` to retreive a
            time-series based on the :class:`pandas.Series` class which can be plotted.

            See :class:`Meter` and :class:`EnergySeries` for more information.

        Example:
            The IDF.meters attribute is populated with meters categories
            (`Output:Meter` or `Output:Meter:Cumulative`) and each category is
            populated with all the available meters.

            .. code-block::

                >>> IDF.variables.OutputVariable
                >>> IDF.variables.OutputVariable
        """
        if self._variables is None:
            try:
                self.simulation_dir.files("*.rdd")
            except FileNotFoundError:
                return "call IDF.simulate() to get a list of possible variables"
            else:
                self._variables = Variables(self)
        return self._variables

    def simulate(self, **kwargs):
        """Execute EnergyPlus. Does not return anything. See
        :meth:`simulation_files`, :meth:`processed_results` for simulation outputs.

        Keyword Args:
            eplus_file (str): path to the idf file.
            weather_file (str): path to the EPW weather file.
            output_directory (str, optional): path to the output folder.
            ep_version (str, optional): EnergyPlus executable version to use, eg: 9-2-0
            output_report: 'sql' or 'htm'
            prep_outputs (bool or list, optional): if True, meters and variable
                outputs will be appended to the idf files. Can also specify custom
                outputs as list of ep-object outputs.
            simulname (str): The name of the simulation. (Todo: Currently not
            implemented).
            keep_data (bool): If True, files created by EnergyPlus are saved to the
                tmp_dir.
            annual (bool): If True then force annual simulation (default: False)
            design_day (bool): Force design-day-only simulation (default: False)
            epmacro (bool): Run EPMacro prior to simulation (default: False)
            expandobjects (bool): Run ExpandObjects prior to simulation (default:
                True)
            readvars (bool): Run ReadVarsESO after simulation (default: False)
            output_prefix (str, optional): Prefix for output file names.
            output_suffix (str, optional): Suffix style for output file names
                (default: L) Choices are:
                    - L: Legacy (e.g., eplustbl.csv)
                    - C: Capital (e.g., eplusTable.csv)
                    - D: Dash (e.g., eplus-table.csv)
            version (bool, optional): Display version information (default: False)
            verbose (str): Set verbosity of runtime messages (default: v) v: verbose
                q: quiet
            keep_data_err (bool): If True, errored directory where simulation
            occurred is
                kept.
            include (str, optional): List input files that need to be copied to the
                simulation directory. If a string is provided, it should be in a glob
                form (see :meth:`pathlib.Path.glob`).
            process_files (bool): If True, process the output files and load to a
                :class:`~pandas.DataFrame`. Custom processes can be passed using the
                :attr:`custom_processes` attribute.
            custom_processes (dict(Callback)): if provided, it has to be a
                dictionary with the keys being a glob (see
                :meth:`pathlib.Path.glob`), and
                the value a Callback taking as signature `callback(file: str,
                working_dir, simulname) -> Any` All the file matching this glob will
                be processed by this callback. Note: they will still be processed by
                pandas.read_csv (if they are csv files), resulting in duplicate. The
                only way to bypass this behavior is to add the key "*.csv" to that
                dictionary.
            return_idf (bool): If True, returns the :class:`IDF` object part of the
                return tuple.
            return_files (bool): It True, all files paths created by the EnergyPlus
                run are returned.

        Raises:
            EnergyPlusProcessError: If an issue occurs with the execution of the
                energyplus command.

        """
        # First, update keys with new values
        for key, value in kwargs.items():
            if f"_{key}" in self.__dict__.keys():
                setattr(self, key, value)

        if self.as_version != EnergyPlusVersion(self.idd_version):
            raise EnergyPlusVersionError(
                None, self.idfname, EnergyPlusVersion(self.idd_version), self.as_version
            )

        start_time = time.time()
        include = self.include
        if isinstance(include, str):
            include = Path().abspath().glob(include)
        elif include is not None:
            include = [Path(file) for file in include]

        # check if a weather file is defined
        if not getattr(self, "epw", None):
            raise EnergyPlusWeatherError(
                f"No weather file specified with {self}. Set 'epw' in IDF("
                f"filename, epw='weather.epw').simulate() or in IDF.simulate("
                f"epw='weather.epw')"
            )

        # Todo: Add EpMacro Thread -> if exist in.imf "%program_path%EPMacro"
        # Run the expandobjects program if necessary
        with TemporaryDirectory(
            prefix="expandobjects_run_",
            suffix=self.output_prefix,
            dir=self.output_directory,
        ) as tmp:
            # Run the ExpandObjects preprocessor program
            expandobjects_thread = ExpandObjectsThread(self, tmp)
            expandobjects_thread.start()
            expandobjects_thread.join()
            e = expandobjects_thread.exception
            if e is not None:
                raise e

        # Run the Basement preprocessor program if necessary
        # Todo: Add Basement.exe Thread -> https://github.com/NREL/EnergyPlus/blob/4836252ecffbaf63e98b62a8e6613510de0046a9/scripts/Epl-run.bat#L271

        # Run the Slab preprocessor program if necessary
        with TemporaryDirectory(
            prefix="RunSlab_run_",
            suffix=self.output_prefix,
            dir=self.output_directory,
        ) as tmp:
            slab_thread = SlabThread(self, tmp)
            slab_thread.start()
            slab_thread.join()
        e = slab_thread.exception
        if e is not None:
            raise e

        # Run the energyplus program
        with TemporaryDirectory(
            prefix="eplus_run_",
            suffix=None,
            dir=self.output_directory,
        ) as tmp:
            running_simulation_thread = EnergyPlusThread(self, tmp)
            running_simulation_thread.start()
            running_simulation_thread.join()
        e = running_simulation_thread.exception
        if e is not None:
            raise e
        return self

    def process_results(self):
        """Returns the list of processed results as defined by self.custom_processes
        as a list of tuple(file, result). A default process looks for csv files
        and tries to parse them into :class:`~pandas.DataFrame` objects.

        Returns:
            list: List of two-tuples.

        Info:
            For processed_results to work more consistently, it may be necessary to
            add the "readvars=True" parameter to :func:`IDF.simulate` as this one is
            set to false by default.

        """
        processes = {"*.csv": _process_csv}
        custom_processes = self.custom_processes
        if custom_processes:
            processes.update(custom_processes)

        try:
            results = []
            for glob, process in processes.items():
                results.extend(
                    [
                        (
                            file.basename(),
                            process(
                                file,
                                working_dir=os.getcwd(),
                                simulname=self.output_prefix,
                            ),
                        )
                        for file in self.simulation_dir.files(glob)
                    ]
                )
        except FileNotFoundError:
            self.simulate()
            return self.process_results()
        else:
            return results

    def upgrade(self, to_version, overwrite=True, **kwargs):
        """EnergyPlus idf version updater using local transition program.

        Update the EnergyPlus simulation file (.idf) to the latest available
        EnergyPlus version installed on this machine. Optionally specify a version
        (eg.: "9-2-0") to aim for a specific version. The output will be the path of
        the updated file. The run is multiprocessing_safe.

        Hint:
            If attempting to upgrade an earlier version of EnergyPlus ( pre-v7.2.0),
            specific binaries need to be downloaded and copied to the
            EnergyPlus*/PreProcess/IDFVersionUpdater folder. More info at
            `Converting older version files
            <http://energyplus.helpserve.com/Knowledgebase/List/Index/46
            /converting-older-version-files>`_ .

        Args:
            to_version (str, optional): EnergyPlus version in the form "X-X-X".
            overwrite (bool): If True, original idf file is overwritten with new
                transitioned file.

        Keyword Args:
            Same as :class:`IDF`

        Raises:
            EnergyPlusProcessError: If version updater fails.
            EnergyPlusVersionError:
            CalledProcessError:
        """
        if self.file_version == to_version:
            return
        if self.file_version > to_version:
            raise EnergyPlusVersionError(self.name, self.idf_version, to_version)
        else:
            # # execute transitions
            with TemporaryDirectory(
                prefix="Transition_run_",
                dir=self.output_directory,
            ) as tmp:
                slab_thread = TransitionThread(self, tmp, overwrite=overwrite)
                slab_thread.start()
                slab_thread.join()
            e = slab_thread.exception
            if e is not None:
                raise e

    def wwr(self, azimuth_threshold=10, round_to=10):
        """Returns the Window-to-Wall Ratio by major orientation for the IDF
        model. Optionally round up the WWR value to nearest value (eg.: nearest
        10).

        Args:
            azimuth_threshold (int): Defines the incremental major orientation
                azimuth angle. Due to possible rounding errors, some surface
                azimuth can be rounded to values different than the main
                directions (eg.: 89 degrees instead of 90 degrees). Defaults to
                increments of 10 degrees.
            round_to (float): Optionally round the WWR value to nearest value
                (eg.: nearest 10). If None, this is ignored and the float is
                returned.

        Returns:
            (pd.DataFrame): A DataFrame with the total wall area, total window
            area and WWR for each main orientation of the building.
        """
        import math
        from builtins import round

        def roundto(x, to=10.0):
            """Rounds up to closest `to` number"""
            if to and not math.isnan(x):
                return int(round(x / to)) * to
            else:
                return x

        total_surface_area = defaultdict(int)
        total_window_area = defaultdict(int)

        zones = self.idfobjects.Zone
        zone: Record
        for zone in zones:
            multiplier = float(zone.multiplier if zone.multiplier else 1)
            for surface in [
                surf
                for surf in zone.zonesurfaces
                if surf.key.upper() not in ["INTERNALMASS", "WINDOWSHADINGCONTROL"]
            ]:
                if isclose(surface.tilt, 90, abs_tol=10):
                    if surface.outside_boundary_condition == "Outdoors":
                        surf_azim = roundto(surface.azimuth, to=azimuth_threshold)
                        total_surface_area[surf_azim] += surface.area * multiplier
                for subsurface in surface.subsurfaces:
                    if hasattr(subsurface, "tilt"):
                        if isclose(subsurface.tilt, 90, abs_tol=10):
                            if subsurface.Surface_Type.lower() == "window":
                                surf_azim = roundto(
                                    subsurface.azimuth, to=azimuth_threshold
                                )
                                total_window_area[surf_azim] += (
                                    subsurface.area * multiplier
                                )
                        if isclose(subsurface.tilt, 180, abs_tol=80):
                            total_window_area["sky"] += subsurface.area * multiplier
        # Fix azimuth = 360 which is the same as azimuth 0
        total_surface_area[0] += total_surface_area.pop(360, 0)
        total_window_area[0] += total_window_area.pop(360, 0)

        # Create dataframe with wall_area, window_area and wwr as columns and azimuth
        # as indexes
        from sigfig import round

        df = (
            pd.DataFrame(
                {"wall_area": total_surface_area, "window_area": total_window_area}
            )
            .rename_axis("Azimuth")
            .fillna(0)
        )
        df.wall_area = df.wall_area.apply(round, decimals=1)
        df.window_area = df.window_area.apply(round, decimals=1)
        df["wwr"] = (df.window_area / df.wall_area).fillna(0).apply(round, 2)
        df["wwr_rounded_%"] = (
            (df.window_area / df.wall_area * 100)
            .fillna(0)
            .apply(lambda x: roundto(x, to=round_to))
        )
        return df

    def space_heating_profile(
        self,
        units="kWh",
        energy_out_variable_name=None,
        name="Space Heating",
        EnergySeries_kwds=None,
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
        if EnergySeries_kwds is None:
            EnergySeries_kwds = {}
        start_time = time.time()
        if energy_out_variable_name is None:
            energy_out_variable_name = (
                "Air System Total Heating Energy",
                "Zone Ideal Loads Zone Total Heating Energy",
            )
        series = self._energy_series(
            energy_out_variable_name, units, name, EnergySeries_kwds=EnergySeries_kwds
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
        EnergySeries_kwds=None,
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
        if EnergySeries_kwds is None:
            EnergySeries_kwds = {}
        start_time = time.time()
        if energy_out_variable_name is None:
            energy_out_variable_name = (
                "Air System Total Cooling Energy",
                "Zone Ideal Loads Zone Total Cooling Energy",
            )
        series = self._energy_series(
            energy_out_variable_name, units, name, EnergySeries_kwds=EnergySeries_kwds
        )
        log(
            "Retrieved Space Cooling Profile in {:,.2f} seconds".format(
                time.time() - start_time
            )
        )
        return series

    def service_water_heating_profile(
        self,
        units="kWh",
        energy_out_variable_name=None,
        name="Space Heating",
        EnergySeries_kwds=None,
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
        if EnergySeries_kwds is None:
            EnergySeries_kwds = {}
        start_time = time.time()
        if energy_out_variable_name is None:
            energy_out_variable_name = ("WaterSystems:EnergyTransfer",)
        series = self._energy_series(
            energy_out_variable_name, units, name, EnergySeries_kwds=EnergySeries_kwds
        )
        log(
            "Retrieved Service Water Heating Profile in {:,.2f} seconds".format(
                time.time() - start_time
            )
        )
        return series

    def custom_profile(
        self,
        energy_out_variable_name,
        name,
        units="kWh",
        prep_outputs=None,
        EnergySeries_kwds=None,
    ):
        """
        Args:
            energy_out_variable_name (list-like): a list of EnergyPlus
            name (str): Name given to the EnergySeries.
            units (str): Units to convert the energy profile to. Will detect the
                units of the EnergyPlus results.
            prep_outputs:
            EnergySeries_kwds (dict, optional): keywords passed to
                :func:`EnergySeries.from_sqlite`

        Returns:
            EnergySeries
        """
        if EnergySeries_kwds is None:
            EnergySeries_kwds = {}
        start_time = time.time()
        series = self._energy_series(
            energy_out_variable_name,
            units,
            name,
            prep_outputs,
            EnergySeries_kwds=EnergySeries_kwds,
        )
        log("Retrieved {} in {:,.2f} seconds".format(name, time.time() - start_time))
        return series

    def newidfobject(self, key, **kwargs):
        """Add a new object to an idf file. The function will test if the object
        exists to prevent duplicates.

        Args:
            key (str): The type of IDF object. This must be in ALL_CAPS.
            **kwargs: Keyword arguments in the format `field=value` used to set
                fields in the EnergyPlus object.

        Example:
            >>> from archetypal import IDF
            >>> IDF.newidfobject(
            >>>     key="Schedule:Constant".upper(),
            >>>     Name="AlwaysOn",
            >>>     Schedule_Type_Limits_Name="",
            >>>     Hourly_Value=1,
            >>> )

        Returns:
            Record: the object
        """
        key = key.replace(":", "_")
        existing_objs = getattr(self.idfobjects, key)
        # create new object
        try:
            new_object = self.anidfobject(key, **kwargs)
        except Exception as e:
            raise e
        else:
            # If object is supposed to be 'unique-object', delete all objects to be
            # sure there is only one of them when creating new object
            # (see following line)
            if "unique-object" in existing_objs._dev_descriptor.tags:
                existing_objs.delete()
                existing_objs.add(new_object.to_dict())
                return new_object
            elif new_object in existing_objs:
                return new_object
            # elif new_object not in existing_objs and existing_objs.one(lambda x: x.name == new_object.name):
            #     obj = existing_objs.one(lambda x: x.name == new_object.name)
            #     self.removeidfobject(obj)
            #     self.addidfobject(new_object)
            #     log(
            #         f"{obj} exists but has different attributes; Removed and replaced "
            #         f"with {new_object}",
            #         lg.DEBUG,
            #     )
            #     return new_object
            else:
                # add to model and return
                self.addidfobject(new_object)
                log(f"object '{new_object}' added to '{self.name}'", lg.DEBUG)
                return new_object

    def addidfobject(self, new_object):
        """Add an IDF object to the IDF.

        Args:
            new_object (Record): The IDF object to copy.

        Returns:
            WorkspaceObject: object.
        """
        return new_object.get_table().add(new_object.to_dict())

    def removeidfobject(self, idfobject):
        """Remove an IDF object from the IDF.

        Args:
            idfobject (Record):

        Returns:
            Record: The added record
        """
        idfobject.delete()

    def anidfobject(self, key, **kwargs):
        """Create an object, but don't add to the model (See
        :func:`~archetypal.idfclass.IDF.newidfobject`). If you don't specify a value
        for a field, the default value will be set.

        Example:
            >>> from archetypal import IDF
            >>> IDF.anidfobject("CONSTRUCTION")
            >>> IDF.anidfobject(
            >>>     key="CONSTRUCTION",
            >>>     Name='Interior Ceiling_class',
            >>>     Outside_Layer='LW Concrete',
            >>>     Layer_2='soundmat'
            >>> )

        Args:
            key (str): The type of IDF object. This must be in ALL_CAPS.
            aname (str): This parameter is not used. It is left there for backward
                compatibility.
            kwargs: Keyword arguments in the format `field=value` used to set
                fields in the EnergyPlus object.

        Returns:
            IdfObject: object.
        """
        # Record field keys are lower case with underscores instead of spaces
        key = key.replace(":", "_")
        kwargs = {k.replace(" ", "_").lower(): v for k, v in kwargs.items()}
        record = Record(getattr(self._workspace, key), kwargs)
        return record

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
        type is known,retrievess it quicker.

        Args:
            name (str): The name of the schedule to retreive in the IDF file.
            sch_type (str): The schedule type, e.g.: "SCHEDULE:YEAR".
        """
        if sch_type is None:
            try:
                return self.schedules_dict[name.upper()]
            except KeyError:
                raise KeyError(
                    'Unable to find schedule "{}" of type "{}" '
                    'in idf file "{}"'.format(name, sch_type, self.name)
                )
        else:
            return self.getobject(sch_type.upper(), name)

    def get_all_schedules(self, yearly_only=False):
        """Returns all schedule ep_objects in a dict with their name as a key

        Args:
            yearly_only (bool): If True, return only yearly schedules

        Returns:
            (dict of eppy.bunch_subclass.Record): the schedules with their
                name as a key
        """
        schedule_types = [
            "Schedule_Year",
            "Schedule_Compact",
            "Schedule_Constant",
            "Schedule_File",
        ]
        if yearly_only:
            schedule_types = [
                "Schedule_Year",
                "Schedule_Compact",
                "Schedule_Constant",
                "Schedule_File",
            ]
        scheds = {}
        for sched_type in schedule_types:
            for sched in getattr(self.idfobjects, sched_type):
                try:
                    if sched.key.upper() in schedule_types:
                        scheds[sched.Name.upper()] = sched
                except KeyError:
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
        for object in self.idfobjects:
            if object.key.upper() not in schedule_types:
                for fieldvalue in object.fieldvalues:
                    try:
                        if (
                            fieldvalue.upper() in all_schedules.keys()
                            and fieldvalue not in used_schedules
                        ):
                            used_schedules.append(fieldvalue)
                    except (KeyError, AttributeError):
                        pass
        return used_schedules

    @deprecated(
        deprecated_in="1.3.5",
        removed_in="1.4",
        current_version=__version__,
        details="Use IDF.name instead",
    )
    def building_name(self, use_idfname=False):
        """
        Args:
            use_idfname:
        """
        if use_idfname:
            return os.path.basename(self.idfname)
        else:
            bld = self.idfobjects.Building
            if bld is not None:
                return bld[0].Name
            else:
                return os.path.basename(self.idfname)

    def rename(self, objkey, objname, newname):
        """rename all the references to this objname.

        Function comes from eppy.modeleditor and was modified to compare the
        name to rename with a lower string (see
        idfobject[idfobject.objls[findex]].lower() == objname.lower())

        Args:
            objkey (str): Record we want to rename and rename all the
                occurrences where this object is in the IDF file
            objname (str): The name of the Record to rename
            newname (str): New name used to rename the Record

        Returns:
            theobject (Record): The renamed idf object
        """

        refnames = eppy.modeleditor.getrefnames(self, objkey)
        for refname in refnames:
            objlists = eppy.modeleditor.getallobjlists(self, refname)
            # [('OBJKEY', refname, fieldindexlist), ...]
            for robjkey, refname, fieldindexlist in objlists:
                idfobjects = getattr(self.idfobjects, robjkey)
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

    def _energy_series(
        self,
        energy_out_variable_name,
        units,
        name,
        prep_outputs=None,
        EnergySeries_kwds=None,
    ):
        """
        Args:
            energy_out_variable_name:
            units:
            name:
            prep_outputs (list):
            EnergySeries_kwds:
        """
        if prep_outputs:
            Outputs(self).add_custom(prep_outputs).apply()
            self.simulate()
        rd = ReportData.from_sqlite(self.sql_file, table_name=energy_out_variable_name)
        profile = EnergySeries.from_reportdata(
            rd, to_units=units, name=name, **EnergySeries_kwds
        )
        return profile

    def _execute_transitions(self, idf_file, to_version, **kwargs):
        trans_exec = {
            EnergyPlusVersion(
                re.search(r"to-V(([\d])-([\d])-([\d]))", exec).group(1)
            ): exec
            for exec in self.idfversionupdater_dir.files("Transition-V*")
        }

        transitions = [
            key for key in trans_exec if to_version >= key > self.idf_version
        ]
        transitions.sort()

        for trans in tqdm(
            transitions,
            position=self.position,
            desc=f"transition file #{self.position}-{self.name}",
        ):
            if not trans_exec[trans].exists():
                raise EnergyPlusProcessError(
                    cmd=trans_exec[trans],
                    stderr="The specified EnergyPlus version (v{}) does not have"
                    " the required transition program '{}' in the "
                    "PreProcess folder. See the documentation "
                    "(archetypal.readthedocs.io/troubleshooting.html#missing"
                    "-transition-programs) "
                    "to solve this issue".format(to_version, trans_exec[trans]),
                    idf=self,
                )
            else:
                cmd = [trans_exec[trans], idf_file]
                with subprocess.Popen(
                    cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd=self.idfversionupdater_dir,
                ) as process:
                    process_output, error_output = process.communicate()
                    log(
                        process_output.decode("utf-8"),
                        level=lg.DEBUG,
                        name="transition_" + self.name,
                        filename="transition_" + self.name,
                        log_dir=self.idfversionupdater_dir,
                    )
                    if error_output:
                        log(
                            error_output.decode("utf-8"),
                            level=lg.DEBUG,
                            name="transition_" + self.name,
                            filename="transition_" + self.name,
                            log_dir=self.idfversionupdater_dir,
                        )

    def idfstr(self):
        return self._workspace.__str__()


@extend_class(Record)
def __eq__(self, other):
    """Tests the equality of two Record objects using all attribute values"""
    if not isinstance(other, Record):
        return False
    return self.to_dict() == other.to_dict()


Record.key = property(lambda x: x._table.get_ref())


def _process_csv(file, working_dir, simulname):
    """
    Args:
        file:
        working_dir:
        simulname:
    """
    log("looking for csv output, return the csv files in DataFrames if any")
    if "table" in file.basename():
        tables_out = working_dir.abspath() / "tables"
        tables_out.makedirs_p()
        file.copy(tables_out / "%s_%s.csv" % (file.basename().stripext(), simulname))
        return
    log("try to store file %s in DataFrame" % file)
    try:
        df = pd.read_csv(file, sep=",", encoding="us-ascii")
    except ParserError:
        pass
    else:
        log("file %s stored" % file)
        return df
