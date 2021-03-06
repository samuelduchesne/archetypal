################################################################################
# Module: idf.py
# Description: Various functions for processing of EnergyPlus models and
#              retrieving results in different forms
# License: MIT, see full license in LICENSE.txt
# Web: https://github.com/samuelduchesne/archetypal
################################################################################

import itertools
import logging as lg
import os
import re
import sqlite3
import subprocess
import time
import uuid
import warnings
from collections import defaultdict
from io import StringIO
from itertools import chain
from math import isclose
from typing import Any

import eppy
import pandas as pd
from eppy.bunch_subclass import BadEPFieldError
from eppy.easyopen import getiddfile
from eppy.modeleditor import IDDNotSetError, namebunch, newrawobject
from geomeppy import IDF as geomIDF
from geomeppy.patches import EpBunch, idfreader1, obj2bunch
from pandas.errors import ParserError
from path import Path
from tqdm import tqdm

from archetypal import ReportData, log, settings
from archetypal.energypandas import EnergySeries
from archetypal.eplus_interface.basement import BasementThread
from archetypal.eplus_interface.energy_plus import EnergyPlusThread
from archetypal.eplus_interface.exceptions import (
    EnergyPlusProcessError,
    EnergyPlusVersionError,
    EnergyPlusWeatherError,
)
from archetypal.eplus_interface.expand_objects import ExpandObjectsThread
from archetypal.eplus_interface.slab import SlabThread
from archetypal.eplus_interface.transition import TransitionThread
from archetypal.eplus_interface.version import EnergyPlusVersion, get_eplus_dirs
from archetypal.idfclass.meters import Meters
from archetypal.idfclass.outputs import Outputs
from archetypal.idfclass.reports import get_report
from archetypal.idfclass.util import get_idf_version, hash_model
from archetypal.idfclass.variables import Variables
from archetypal.schedule import Schedule


class IDF(geomIDF):
    """Class for loading and parsing idf models and running simulations and
    retrieving results.

    Wrapper over the geomeppy.IDF class and subsequently the
    eppy.modeleditor.IDF class
    """

    # dependencies: dict of <dependant value: independent value>
    _dependencies = {
        "iddname": ["idfname", "as_version"],
        "file_version": ["idfname"],
        "idd_info": ["iddname", "idfname"],
        "idd_index": ["iddname", "idfname"],
        "idd_version": ["iddname", "idfname"],
        "idfobjects": ["iddname", "idfname"],
        "block": ["iddname", "idfname"],
        "model": ["iddname", "idfname"],
        "sql": [
            "as_version",
            "annual",
            "design_day",
            "epw",
            "idfname",
            "tmp_dir",
        ],
        "htm": [
            "as_version",
            "annual",
            "design_day",
            "epw",
            "idfname",
            "tmp_dir",
        ],
        "meters": [
            "idfobjects",
            "epw",
            "annual",
            "design_day",
            "readvars",
            "as_version",
        ],
        "variables": [
            "idfobjects",
            "epw",
            "annual",
            "design_day",
            "readvars",
            "as_version",
        ],
        "sim_id": [
            "idfobjects",
            "epw",
            "annual",
            "design_day",
            "readvars",
            "as_version",
        ],
        "schedules_dict": ["idfobjects"],
        "partition_ratio": ["idfobjects"],
        "net_conditioned_building_area": ["idfobjects"],
        "energyplus_its": ["annual", "design_day"],
        "tmp_dir": ["idfobjects"],
    }
    _independant_vars = set(chain(*list(_dependencies.values())))
    _dependant_vars = set(_dependencies.keys())

    _initial_postition = itertools.count(start=1)

    def _reset_dependant_vars(self, name):
        _reverse_dependencies = {}
        for k, v in self._dependencies.items():
            for x in v:
                _reverse_dependencies.setdefault(x, []).append(k)
        for var in _reverse_dependencies[name]:
            super().__setattr__(f"_{var}", None)

    def __setattr__(self, key, value):
        propobj = getattr(self.__class__, key, None)
        if isinstance(propobj, property):
            if propobj.fset is None:
                raise AttributeError("Cannot set attribute")
                # self.__set_on_dependencies(key.strip("_"), value)
            else:
                propobj.fset(self, value)
                self.__set_on_dependencies(key, value)
        else:
            self.__set_on_dependencies(key, value)

    def __set_on_dependencies(self, key, value):
        if key in self._dependant_vars:
            raise AttributeError("Cannot set this value.")
        if key in self._independant_vars:
            self._reset_dependant_vars(key)
            key = f"_{key}"
        super(IDF, self).__setattr__(key, value)

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
        output_suffix="L",
        epmacro=False,
        keep_data=True,
        keep_data_err=False,
        position=0,
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
        if include is None:
            include = []
        self.idfname = idfname
        self.epw = epw
        self.as_version = as_version if as_version else settings.ep_version
        self._custom_processes = custom_processes
        self._include = include
        self.keep_data_err = keep_data_err
        self._keep_data = keep_data
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

        self.outputtype = "standard"
        self.original_idfname = self.idfname  # Save original
        self._original_cache = hash_model(self)
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
                    self.idfname = self.savecopy(self.output_directory / self.name)

        try:
            # load the idf object by asserting self.idd_info
            assert self.idd_info
        except Exception as e:
            raise e
        else:
            if self.file_version < self.as_version:
                self.upgrade(to_version=self.as_version)
        finally:
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
        """Returns name of IDF model."""
        return self.name

    def setiddname(self, iddname, testing=False):
        """Set the path to the EnergyPlus IDD for the version of EnergyPlus
        which is to be used by eppy.

        Args:
            iddname (str): Path to the IDD file.
            testing (bool):
        """
        self.iddname = iddname
        self.idd_info = None
        self.block = None

    def read(self):
        """Read the IDF file and the IDD file.

        If the IDD file had already been read, it will not be read again.

        Read populates the following data structures:
            - idfobjects : list
            - model : list
            - idd_info : list
            - idd_index : dict
        """
        if self.getiddname() is None:
            errortxt = (
                "IDD file needed to read the idf file. "
                "Set it using IDF.setiddname(iddfile)"
            )
            raise IDDNotSetError(errortxt)
        readout = idfreader1(
            self.idfname, self.iddname, self, commdct=self.idd_info, block=self.block
        )
        (self.idfobjects, block, self.model, idd_info, idd_index, idd_version) = readout
        self.setidd(idd_info, idd_index, block, idd_version)

    def getiddname(self):
        """Get the name of the current IDD used by eppy."""
        return self.iddname

    def setidd(self, iddinfo, iddindex, block, idd_version):
        """Set the IDD to be used by eppy.

        Args:
            iddinfo (list): Comments and metadata about fields in the IDD.
            block (list): Field names in the IDD.
        """
        self.idd_info = iddinfo
        self.block = block
        self.idd_index = iddindex
        self.idd_version = idd_version

    @property
    def block(self):
        """EnergyPlus field ID names of the IDF from the IDD."""
        if self._block is None:
            bunchdt, block, data, commdct, idd_index, versiontuple = idfreader1(
                self.idfname, self.iddname, self, commdct=None, block=None
            )
            self._block = block
            self._idd_info = commdct
            self._idd_index = idd_index
            self._idfobjects = bunchdt
            self._model = data
            self._idd_version = versiontuple
        return self._block

    @property
    def idd_info(self):
        """Descriptions of IDF fields from the IDD."""
        if self._idd_info is None:
            bunchdt, block, data, commdct, idd_index, versiontuple = idfreader1(
                self.idfname, self.iddname, self, commdct=None, block=None
            )
            self._block = block
            self._idd_info = commdct
            self._idd_index = idd_index
            self._idfobjects = bunchdt
            self._model = data
            self._idd_version = versiontuple
        return self._idd_info

    @property
    def idd_index(self):
        """A pair of dicts used for fast lookups of names of groups of objects."""
        if self._idd_index is None:
            bunchdt, block, data, commdct, idd_index, versiontuple = idfreader1(
                self.idfname, self.iddname, self, commdct=None, block=None
            )
            self._block = block
            self._idd_info = commdct
            self._idd_index = idd_index
            self._idfobjects = bunchdt
            self._model = data
            self._idd_version = versiontuple
        return self._idd_index

    @property
    def idfobjects(self):
        """Dict of lists of idf_MSequence objects in the IDF."""
        if self._idfobjects is None:
            bunchdt, block, data, commdct, idd_index, versiontuple = idfreader1(
                self.idfname, self.iddname, self, commdct=None, block=None
            )
            self._block = block
            self._idd_info = commdct
            self._idd_index = idd_index
            self._idfobjects = bunchdt
            self._model = data
            self._idd_version = versiontuple
        return self._idfobjects

    @property
    def model(self):
        """Eplusdata object containing representions of IDF objects."""
        if self._model is None:
            bunchdt, block, data, commdct, idd_index, versiontuple = idfreader1(
                self.idfname, self.iddname, self, commdct=None, block=None
            )
            self._block = block
            self._idd_info = commdct
            self._idd_index = idd_index
            self._idfobjects = bunchdt
            self._model = data
            self._idd_version = versiontuple
        return self._model

    @property
    def idd_version(self):
        """tuple: The version of the iddname."""
        if self._idd_version is None:
            bunchdt, block, data, commdct, idd_index, versiontuple = idfreader1(
                self.idfname, self.iddname, self, commdct=None, block=None
            )
            self._block = block
            self._idd_info = commdct
            self._idd_index = idd_index
            self._idfobjects = bunchdt
            self._model = data
            self._idd_version = versiontuple
        return self._idd_version

    @property
    def iddname(self):
        """Path: The iddname used to parse the idf model."""
        if self._iddname is None:
            if self.file_version > self.as_version:
                raise EnergyPlusVersionError(
                    f"{self.as_version} cannot be lower then "
                    f"the version number set in the file: {self.file_version}"
                )
            idd_filename = Path(getiddfile(str(self.file_version))).expand()
            if not idd_filename.exists():
                # Try finding the one in IDFVersionsUpdater
                idd_filename = (
                    self.idfversionupdater_dir / f"V"
                    f"{self.file_version.dash}-Energy+.idd"
                ).expand()
            self._iddname = idd_filename
        return self._iddname

    @property
    def file_version(self):
        """The :class:`EnergyPlusVersion` of the idf text file."""
        if self._file_version is None:
            return EnergyPlusVersion(get_idf_version(self.idfname))

    @property
    def custom_processes(self):
        """list: List of callables. Called on the output files."""
        return self._custom_processes

    @property
    def include(self):
        """list: List of external files."""
        return self._include

    @property
    def keep_data_err(self):
        """bool: If True, error files are copied back into self.output_folder"""
        return self._keep_data_err

    @keep_data_err.setter
    def keep_data_err(self, value):
        if not isinstance(value, bool):
            raise TypeError("'keep_data_err' needs to be a bool")
        self._keep_data_err = value

    @property
    def keep_data(self):
        return self._keep_data

    # region User-Defined Properties (have setter)
    @property
    def output_suffix(self):
        """Suffix style for output file names (default: L)

        - L: Legacy (e.g., eplustbl.csv)
        - C: Capital (e.g., eplusTable.csv)
        - D: Dash (e.g., eplus-table.csv)
        """
        return self._output_suffix

    @output_suffix.setter
    def output_suffix(self, value):
        choices = ["L", "C", "D"]
        if value not in choices:
            raise ValueError(f"Choices of 'output_suffix' are {choices}")
        self._output_suffix = value

    @property
    def idfname(self):
        """The path of the active (parsed) idf model.

        If `settings.use_cache == True`, then this path will point to
        `settings.cache_folder`. See :meth:`~archetypal.utils.config`
        """
        if self._idfname is None:
            idfname = StringIO(f"VERSION, {self.as_version};")
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
        if not value:
            self._idfname = None
        elif not isinstance(value, str):
            raise ValueError(f"IDF path must be Path-Like, not {type(value)}")
        else:
            self._idfname = Path(value).expand()

    @property
    def epw(self):
        """The weather file path."""
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
        """bool: If True, print outputs to logging module.

        See Also:
            :ref:`archetypal.utils.config`
        """
        return self._verbose

    @verbose.setter
    def verbose(self, value):

        if not isinstance(value, bool):
            raise TypeError("'verbose' needs to be a bool")
        self._verbose = value

    @property
    def expandobjects(self):
        """bool: If True, run ExpandObjects prior to simulation."""
        return self._expandobjects

    @expandobjects.setter
    def expandobjects(self, value):
        if not isinstance(value, bool):
            raise TypeError("'expandobjects' needs to be a bool")
        self._expandobjects = value

    @property
    def readvars(self):
        """bool: If True, run ReadVarsESO after simulation."""
        return self._readvars

    @readvars.setter
    def readvars(self, value):
        if not isinstance(value, bool):
            raise TypeError("'readvars' needs to be a bool")
        self._readvars = value

    @property
    def epmacro(self):
        """bool: If True, run EPMacro prior to simulation."""
        return self._epmacro

    @epmacro.setter
    def epmacro(self, value):
        if not isinstance(value, bool):
            raise TypeError("'epmacro' needs to be a bool")
        self._epmacro = value

    @property
    def design_day(self):
        """bool: If True, force design-day-only simulation."""
        return self._design_day

    @design_day.setter
    def design_day(self, value):
        if not isinstance(value, bool):
            raise TypeError("'design_day' needs to be a bool")
        self._design_day = value

    @property
    def annual(self):
        """bool: If True, force annual simulation."""
        return self._annual

    @annual.setter
    def annual(self, value):
        if not isinstance(value, bool):
            raise TypeError("'annual' needs to be a bool")
        self._annual = value

    @property
    def convert(self):
        """bool: If True, only convert IDF->epJSON or epJSON->IDF.

        Dependent on input file type. No simulation.
        """
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
        """Specify the desired :class:`EnergyPlusVersion` for the IDF model."""
        if self._as_version is None:
            self._as_version = EnergyPlusVersion.current()
        return EnergyPlusVersion(self._as_version)

    @as_version.setter
    def as_version(self, value):
        # Parse value and check if above or bellow
        self._as_version = EnergyPlusVersion(value)

    @property
    def output_directory(self):
        """The output directory based on the hashing of the original file.

        Notes:
            The hashing is performed before transitions or modifications.
        """
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
        """Prefix for output file names (default: eplus)."""
        if self._output_prefix is None:
            self._output_prefix = "eplus"
        return self._output_prefix

    @output_prefix.setter
    def output_prefix(self, value):
        if value and not isinstance(value, str):
            raise TypeError("'output_prefix' needs to be a string")
        self._output_prefix = value

    @property
    def sim_id(self):
        """The unique Id of the simulation.

        Based on a subset of hashed variables:
            - The idf model itself.
            - epw
            - annual
            - design_day
            - readvars
            - as_version
        """
        if self._sim_id is None:
            self._sim_id = hash_model(
                self,
                epw=self.epw,
                annual=self.annual,
                design_day=self.design_day,
                readvars=self.readvars,
                ep_version=self.as_version,
                include=self.include,
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
                if sql_object not in self.idfobjects["Output:SQLite".upper()]:
                    self.addidfobject(sql_object)
                return self.simulate().sql()
            except Exception as e:
                raise e
            else:
                self._sql = sql_dict
        return self._sql

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
                return self.simulate().htm()
            else:
                self._htm = htm_dict
        return self._htm

    @property
    def energyplus_its(self):
        """Number of iterations needed to complete simulation"""
        if self._energyplus_its is None:
            self._energyplus_its = 0
        return self._energyplus_its

    def open_htm(self):
        """Open .htm file in browser"""
        import webbrowser

        html, *_ = self.simulation_dir.files("*.htm")

        webbrowser.open(html.abspath())

    def open_idf(self):
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

    def open_last_simulation(self):
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

    def open_mdd(self):
        """Open .mdd file in browser. This file shows all the report meters along
        with their “availability” for the current input file"""
        import webbrowser

        mdd, *_ = self.simulation_dir.files("*.mdd")

        webbrowser.open(mdd.abspath())

    def open_mtd(self):
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
    def mtd_file(self):
        """Get the mtd file path"""
        try:
            file, *_ = self.simulation_dir.files("*.mtd")
        except (FileNotFoundError, ValueError):
            return self.simulate().mtd_file
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
                zones = self.idfobjects["ZONE"]
                zone: EpBunch
                for zone in zones:
                    for surface in zone.zonesurfaces:
                        if hasattr(surface, "tilt"):
                            if surface.tilt == 180.0:
                                part_of = int(
                                    zone.Part_of_Total_Floor_Area.upper() != "NO"
                                )
                                multiplier = float(
                                    zone.Multiplier if zone.Multiplier != "" else 1
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
                zones = self.idfobjects["ZONE"]
                zone: EpBunch
                for zone in zones:
                    for surface in zone.zonesurfaces:
                        if hasattr(surface, "tilt"):
                            if surface.tilt == 180.0:
                                part_of = int(
                                    zone.Part_of_Total_Floor_Area.upper() == "NO"
                                )
                                multiplier = float(
                                    zone.Multiplier if zone.Multiplier != "" else 1
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
                zones = self.idfobjects["ZONE"]
                zone: EpBunch
                for zone in zones:
                    for surface in zone.zonesurfaces:
                        if hasattr(surface, "tilt"):
                            if surface.tilt == 180.0:
                                multiplier = float(
                                    zone.Multiplier if zone.Multiplier != "" else 1
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
            zones = self.idfobjects["ZONE"]
            zone: EpBunch
            for zone in zones:
                for surface in [
                    surf
                    for surf in zone.zonesurfaces
                    if surf.key.upper() not in ["INTERNALMASS", "WINDOWSHADINGCONTROL"]
                ]:
                    if hasattr(surface, "tilt"):
                        if (
                            surface.tilt == 90.0
                            and surface.Outside_Boundary_Condition != "Outdoors"
                        ):
                            multiplier = float(
                                zone.Multiplier if zone.Multiplier != "" else 1
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

        run_period = next(iter(self.idfobjects["RUNPERIOD"]), None)
        if run_period:
            day = run_period["Day_of_Week_for_Start_Day"]
        else:
            raise ValueError("model does not contain a 'RunPeriod'")

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
            # field is null
            return 6  # E+ default is Sunday

    @property
    def meters(self) -> Meters:
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
            Call `idf.meters.<output_group>.<meter_name>.values()` to retreive a
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
        """Execute EnergyPlus. Does not return anything.

        Keyword Args:
            eplus_file (str): path to the idf file.
            weather_file (str): path to the EPW weather file.
            output_directory (str, optional): path to the output folder.
            ep_version (str, optional): EnergyPlus executable version to use, eg: 9-2-0
            output_report: 'sql' or 'htm'
            prep_outputs (bool or list, optional): if True, meters and variable
                outputs will be appended to the idf files. Can also specify custom
                outputs as list of ep-object outputs.
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

        See Also:
            :meth:`simulation_files`, :meth:`processed_results` for simulation outputs.

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
        tmp = (
            self.output_directory / "expandobjects_run_" + str(uuid.uuid1())[0:8]
        ).mkdir()
        # Run the ExpandObjects preprocessor program
        expandobjects_thread = ExpandObjectsThread(self, tmp)
        expandobjects_thread.start()
        expandobjects_thread.join()
        while expandobjects_thread.is_alive():
            time.sleep(1)
        tmp.rmtree(ignore_errors=True)
        e = expandobjects_thread.exception
        if e is not None:
            raise e

        # Run the Basement preprocessor program if necessary
        tmp = (
            self.output_directory / "runBasement_run_" + str(uuid.uuid1())[0:8]
        ).mkdir()
        basement_thread = BasementThread(self, tmp)
        basement_thread.start()
        basement_thread.join()
        while basement_thread.is_alive():
            time.sleep(1)
        tmp.rmtree(ignore_errors=True)
        e = basement_thread.exception
        if e is not None:
            raise e

        # Run the Slab preprocessor program if necessary
        tmp = (self.output_directory / "runSlab_run_" + str(uuid.uuid1())[0:8]).mkdir()
        slab_thread = SlabThread(self, tmp)
        slab_thread.start()
        slab_thread.join()
        while slab_thread.is_alive():
            time.sleep(1)
        tmp.rmtree(ignore_errors=True)
        e = slab_thread.exception
        if e is not None:
            raise e

        # Run the energyplus program
        tmp = (self.output_directory / "eplus_run_" + str(uuid.uuid1())[0:8]).mkdir()
        running_simulation_thread = EnergyPlusThread(self, tmp)
        running_simulation_thread.start()
        running_simulation_thread.join()
        while running_simulation_thread.is_alive():
            time.sleep(1)
        tmp.rmtree(ignore_errors=True)
        e = running_simulation_thread.exception
        if e is not None:
            raise e
        return self

    def savecopy(self, filename, lineendings="default", encoding="latin-1"):
        """Save a copy of the file with the filename passed.

        Args:
            filename (str): Filepath to save the file.
            lineendings (str): Line endings to use in the saved file. Options are
            'default',
                'windows' and 'unix' the default is 'default' which uses the line
                endings for the current system.
            encoding (str): Encoding to use for the saved file. The default is
            'latin-1' which
                is compatible with the EnergyPlus IDFEditor.

        Returns:
            Path: The new file path.
        """
        super(IDF, self).save(filename, lineendings, encoding)
        return Path(filename)

    def save(self, lineendings="default", encoding="latin-1", **kwargs):
        """Write the IDF model to the text file. Uses
        :meth:`~eppy.modeleditor.IDF.saveas`

        Args:
            filename (str): Filepath to save the file. If None then use the IDF.idfname
                parameter. Also accepts a file handle.
            lineendings (str) : Line endings to use in the saved file. Options are
            'default',
                'windows' and 'unix' the default is 'default' which uses the line
                endings for the current system.
            encoding (str): Encoding to use for the saved file. The default is
                'latin-1' which is compatible with the EnergyPlus IDFEditor.
        Returns:
            IDF: The IDF model
        """
        super(IDF, self).save(
            filename=self.idfname, lineendings=lineendings, encoding=encoding
        )
        if not settings.use_cache:
            cache_filename = hash_model(self)
            output_directory = settings.cache_folder / cache_filename
            output_directory.makedirs_p()
            dst = output_directory / self.simulation_dir.basename()
            if dst.exists():
                dst.rmtree_p()
            self.simulation_dir.copytree(dst)
        log(f"saved '{self.name}' at '{self.idfname}'")
        return self

    def saveas(self, filename, lineendings="default", encoding="latin-1"):
        """Save the IDF model as. Writes a new text file and load a new instance of
        the IDF class (new object).

        Args:
            filename (str): Filepath to save the file. If None then use the IDF.idfname
                parameter. Also accepts a file handle.
            lineendings (str) : Line endings to use in the saved file. Options are
            'default',
                'windows' and 'unix' the default is 'default' which uses the line
                endings for the current system.
            encoding (str): Encoding to use for the saved file. The default is
                'latin-1' which is compatible with the EnergyPlus IDFEditor.

        Returns:
            IDF: A new IDF object based on the new location file.
        """
        super(IDF, self).save(
            filename=filename, lineendings=lineendings, encoding=encoding
        )

        import inspect

        sig = inspect.signature(IDF.__init__)
        kwargs = {
            key: getattr(self, key)
            for key in [a for a in sig.parameters]
            if key not in ["self", "idfname", "kwargs"]
        }

        as_idf = IDF(filename, **kwargs)
        # copy simulation_dir over to new location
        file: Path
        as_idf.simulation_dir.makedirs_p()
        for file in self.simulation_files:
            if self.output_prefix in file:
                name = file.replace(self.output_prefix, as_idf.output_prefix)
                name = Path(name).basename()
            else:
                name = file.basename()
            file.copy(as_idf.simulation_dir / name)
        return as_idf

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
            raise ValueError("No results to process. Have you called IDF.simulate()?")
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
            tmp = (
                self.output_directory / "Transition_run_" + str(uuid.uuid1())[0:8]
            ).mkdir()
            slab_thread = TransitionThread(self, tmp, overwrite=overwrite)
            slab_thread.start()
            slab_thread.join()
            while slab_thread.is_alive():
                time.sleep(1)
            tmp.rmtree(ignore_errors=True)
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

        zones = self.idfobjects["ZONE"]
        zone: EpBunch
        for zone in zones:
            multiplier = float(zone.Multiplier if zone.Multiplier != "" else 1)
            for surface in [
                surf
                for surf in zone.zonesurfaces
                if surf.key.upper() not in ["INTERNALMASS", "WINDOWSHADINGCONTROL"]
            ]:
                if isclose(surface.tilt, 90, abs_tol=10):
                    if surface.Outside_Boundary_Condition == "Outdoors":
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
            EpBunch: the object
        """
        # get list of objects
        existing_objs = self.idfobjects[key]  # a list

        # create new object
        try:
            new_object = self.anidfobject(key, **kwargs)
        except BadEPFieldError as e:
            if str(e) == "unknown field Key_Name":
                # Try backwards compatibility with EnergyPlus < 9.0.0
                name = kwargs.pop("Key_Name")
                kwargs["Name"] = name
            else:
                log(f"Could not add object {key} because of: {e}", lg.WARNING)
                return None
        else:
            new_object = self.anidfobject(key, **kwargs)
            # If object is supposed to be 'unique-object', deletes all objects to be
            # sure there is only one of them when creating new object
            # (see following line)
            if "unique-object" in set().union(
                *(d.objidd[0].keys() for d in existing_objs)
            ):
                for obj in existing_objs:
                    self.removeidfobject(obj)
                    self.addidfobject(new_object)
                    log(
                        f"{obj} is a 'unique-object'; Removed and replaced with"
                        f" {new_object}",
                        lg.DEBUG,
                    )
                return new_object
            if new_object in existing_objs:
                # If obj already exists, simply return
                log(
                    f"object '{new_object}' already exists in {self.name}. "
                    f"Skipping.",
                    lg.DEBUG,
                )
                return new_object
            elif new_object not in existing_objs and new_object.nameexists():
                obj = self.getobject(
                    key=new_object.key.upper(), name=new_object.Name.upper()
                )
                self.removeidfobject(obj)
                self.addidfobject(new_object)
                log(
                    f"{obj} exists but has different attributes; Removed and replaced "
                    f"with {new_object}",
                    lg.DEBUG,
                )
                return new_object
            else:
                # add to model and return
                self.addidfobject(new_object)
                log(f"object '{new_object}' added to '{self.name}'", lg.DEBUG)
                return new_object

    def addidfobject(self, new_object):
        """Add an IDF object to the IDF.

        Args:
            new_object (EpBunch): The IDF object to copy.

        Returns:
            EpBunch: object.
        """
        key = new_object.key.upper()
        self.idfobjects[key].append(new_object)
        self._reset_dependant_vars("idfobjects")

    def removeidfobject(self, idfobject):
        """Remove an IDF object from the IDF.

        Parameters
        ----------
        idfobject : EpBunch object
            The IDF object to remove.

        """
        key = idfobject.key.upper()
        self.idfobjects[key].remove(idfobject)
        self._reset_dependant_vars("idfobjects")

    def anidfobject(self, key, aname="", **kwargs):
        # type: (str, str, **Any) -> EpBunch
        """Create an object, but don't add to the model (See
        :func:`~archetypal.idfclass.idf.IDF.newidfobject`). If you don't specify a value
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
            EpBunch: object.
        """
        obj = newrawobject(self.model, self.idd_info, key)
        abunch = obj2bunch(self.model, self.idd_info, obj)
        if aname:
            warnings.warn(
                "The aname parameter should no longer be used (%s)." % aname,
                UserWarning,
            )
            namebunch(abunch, aname)
        for k, v in kwargs.items():
            try:
                abunch[k] = v
            except BadEPFieldError as e:
                # Backwards compatibility
                if str(e) == "unknown field Key_Name":
                    abunch["Name"] = v
                else:
                    raise e
        abunch.theidf = self
        return abunch

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
        for object_name in self.idfobjects:
            for object in self.idfobjects[object_name]:
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

    def rename(self, objkey, objname, newname):
        """rename all the references to this objname.

        Function comes from eppy.modeleditor and was modified to compare the
        name to rename with a lower string (see
        idfobject[idfobject.objls[findex]].lower() == objname.lower())

        Args:
            objkey (str): EpBunch we want to rename and rename all the
                occurrences where this object is in the IDF file
            objname (str): The name of the EpBunch to rename
            newname (str): New name used to rename the EpBunch

        Returns:
            theobject (EpBunch): The renamed idf object
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
            self.outputs.add_custom(prep_outputs).apply()
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
