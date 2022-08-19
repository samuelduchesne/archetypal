"""IDF class module.

Various functions for processing EnergyPlus models and retrieving results in
different forms.
"""
import io
import itertools
import logging as lg
import math
import os
import re
import shutil
import sqlite3
import subprocess
import time
import uuid
import warnings
from collections import defaultdict
from io import IOBase, StringIO
from itertools import chain
from math import isclose
from typing import IO, Iterable, Optional, Tuple, Union

import eppy
import pandas as pd
from energy_pandas import EnergySeries
from eppy.bunch_subclass import BadEPFieldError
from eppy.EPlusInterfaceFunctions.eplusdata import Eplusdata
from eppy.idf_msequence import Idf_MSequence
from eppy.modeleditor import IDDNotSetError, namebunch, newrawobject
from geomeppy import IDF as GeomIDF
from geomeppy.geom.polygons import Polygon3D
from geomeppy.patches import EpBunch, idfreader1, obj2bunch
from geomeppy.recipes import _is_window, window_vertices_given_wall
from pandas import DataFrame, Series
from pandas.errors import ParserError
from path import Path
from tabulate import tabulate
from tqdm.auto import tqdm

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
from archetypal.eplus_interface.version import EnergyPlusVersion
from archetypal.idfclass.meters import Meters
from archetypal.idfclass.outputs import Outputs
from archetypal.idfclass.reports import get_report
from archetypal.idfclass.util import get_idf_version, hash_model
from archetypal.idfclass.variables import Variables
from archetypal.reportdata import ReportData
from archetypal.utils import log, settings


def find_and_launch(app_name, app_path_guess, file_path):
    app_path = shutil.which(app_name, path=app_path_guess)
    assert app_path is not None, f"Could not find {app_name} at '{app_path_guess}'"
    assert file_path.exists(), f"{file_path} does not exist."
    subprocess.Popen(
        (
            app_path,
            file_path,
        )
    )


class IDF(GeomIDF):
    """Class for loading and parsing idf models.

    This is the starting point to run simulations and retrieving results.

    Wrapper over the geomeppy.IDF class and subsequently the
    eppy.modeleditor.IDF class.
    """

    IDD = {}
    IDDINDEX = {}
    BLOCK = {}

    OUTPUTTYPES = ("standard", "nocomment1", "nocomment2", "compressed")

    # dependencies: dict of <dependant value: independent value>
    _dependencies = {
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
        """Set attribute."""
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
        idfname: Optional[Union[str, IO, Path]] = None,
        epw=None,
        as_version: Union[str, EnergyPlusVersion] = None,
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
        keep_data_err=True,
        position=0,
        name=None,
        output_directory=None,
        outputtype="standard",
        iddname: Optional[Union[str, IO, Path]] = None,
        **kwargs,
    ):
        """Initialize an IDF object.

        Args:
            output_directory:
            idfname (str or os.PathLike): The path of the idf file to read. If none,
                an in-memory IDF object is generated.
            epw (str or os.PathLike): The weather-file. If None, epw can be specified in
                IDF.simulate().
            as_version (str): Specify the target EnergyPlus version for the IDF model.
                If as_version is higher than the file version, the model will be
                transitioned to the target version. This will not overwrite the file
                unless IDF.save() is invoked. See :meth:`IDF.save`,
                :meth:`IDF.saveas` and :meth:`IDF.savecopy` for other IO operations
                on IDF objects.
            annual (bool): If True then force annual simulation (default: False).
            design_day (bool): Force design-day-only simulation (default: False).
            expandobjects (bool): Run ExpandObjects prior to simulation (default: True).
            convert (bool): If True, only convert IDF->epJSON or epJSON->IDF.
            outputtype (str): Specifies the idf string representation of the model.
                Choices are: "standard", "nocomment1", "nocomment2", "compressed".

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
        self.as_version = as_version
        self.file_version = kwargs.get("file_version", None)
        self._custom_processes = custom_processes
        self.include = include
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
        self._translated = False
        self._rotated = False
        self.output_prefix = None
        self.name = (
            name
            if name is not None
            else self.idfname.basename()
            if isinstance(self.idfname, Path)
            else None
        )
        self.output_directory = output_directory

        # Set dependants to None
        self._iddname = Path(iddname) if iddname is not None else None
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
        self._sim_timestamp = None

        self.outputtype = outputtype
        self.original_idfname = self.idfname  # Save original

        try:
            # load the idf object by asserting self.idd_info
            assert self.idd_info
        except Exception as e:
            raise e
        else:
            self._original_cache = hash_model(self)
            if self.as_version is not None:
                if self.file_version < self.as_version:
                    self.upgrade(to_version=self.as_version, overwrite=False)
        finally:
            # Set model outputs
            self._outputs = Outputs(idf=self, include_html=False, include_sqlite=False)
            if self.prep_outputs:
                self._outputs.include_html = True
                self._outputs.include_sqlite = True
                self._outputs.add_basics()
                if isinstance(self.prep_outputs, list):
                    self._outputs.add_custom(outputs=self.prep_outputs)
                self._outputs.add_profile_gas_elect_outputs()
                self._outputs.add_umi_template_outputs()
                self._outputs.apply()

    @property
    def outputtype(self):
        """Get or set the outputtype for the idf string representation of self."""
        return self._outputtype

    @outputtype.setter
    def outputtype(self, value):
        assert value in self.OUTPUTTYPES, (
            f'Invalid input "{value}" for output_type.'
            f"\nOutput type must be one of the following: {self.OUTPUTTYPES}"
        )
        self._outputtype = value

    def __str__(self):
        """Return the name of IDF model."""
        return self.name

    def __repr__(self):
        """Return a representation of self."""
        if self.sim_info is not None:
            sim_info = tabulate(self.sim_info.T, tablefmt="orgtbl")
            sim_info += f"\n\tFiles at '{self.simulation_dir}'"
        else:
            sim_info = "\tNot yet simulated"
        body = "\n".join([f"IDF object {self.name}", f"at {self.idfname}"])
        body += f"\n\tVersion {self.file_version}\nSimulation Info:\n"
        body += sim_info
        return f"<{body}>"

    def __copy__(self):
        """Get a copy of self."""
        return self.copy()

    @classmethod
    def from_example_files(cls, example_name, epw=None, **kwargs):
        """Load an IDF model from the ExampleFiles folder by name.

        Examples:
            idf = IDF.from_example_files(
                "minimal",
                "USA_IL_Chicago-OHare.Intl.AP.725300_TMY3.epw"
            )

        Args:
            example_name (str): The name of the example file to load.
            epw (str): The name of the weather file contained the WeatherData folder
                or the path to a specific weather file.
            **kwargs: keyword arguments passed to the IDF constructor.

        Returns:
            (IDF): An IDF model.
        """
        from pathlib import Path as Pathlib

        example_name = Path(example_name)
        example_files_dir: Path = (
            EnergyPlusVersion.current().current_install_dir / "ExampleFiles"
        )
        try:

            file = next(
                iter(Pathlib(example_files_dir).rglob(f"{example_name.stem}.idf"))
            )
        except StopIteration:
            full_list = list(
                map(lambda x: str(x.name), example_files_dir.files("*.idf"))
            )
            raise ValueError(f"Choose from: {sorted(full_list)}")
        if epw is not None:
            epw = Path(epw)

            if not epw.exists():
                dir_weather_data_ = (
                    EnergyPlusVersion.current().current_install_dir / "WeatherData"
                )
                try:
                    epw = next(
                        iter(Pathlib(dir_weather_data_).rglob(f"{epw.stem}.epw"))
                    )
                except StopIteration:
                    full_list = list(
                        map(lambda x: str(x.name), dir_weather_data_.files("*.epw"))
                    )
                    raise ValueError(f"Choose EPW from: {sorted(full_list)}")
        return cls(file, epw=epw, **kwargs)

    def setiddname(self, iddname, testing=False):
        """Set EnergyPlus IDD path for model.

        Sets the version of EnergyPlus which is to be used by eppy.

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
            iddindex:
            iddinfo (list): Comments and metadata about fields in the IDD.
            block (list): Field names in the IDD.
        """
        self.idd_info = iddinfo
        self.block = block
        self.idd_index = iddindex
        self.idd_version = idd_version

    def _read_idf(self):
        """Read idf file and return bunches."""
        self._idd_info = IDF.IDD.get(str(self.file_version), None)
        self._idd_index = IDF.IDDINDEX.get(str(self.file_version), None)
        self._block = IDF.BLOCK.get(str(self.file_version), None)
        bunchdt, block, data, commdct, idd_index, versiontuple = idfreader1(
            self.idfname, self.iddname, self, commdct=self._idd_info, block=self._block
        )
        self._block = IDF.BLOCK[str(self.file_version)] = block
        self._idd_info = IDF.IDD[str(self.file_version)] = commdct
        self._idd_index = IDF.IDDINDEX[str(self.file_version)] = idd_index
        self._idfobjects = bunchdt
        self._model = data
        self._idd_version = versiontuple

    @property
    def block(self) -> list:
        """Set EnergyPlus field ID names of the IDF from the IDD."""
        if self._block is None:
            self._read_idf()
        return self._block

    @property
    def idd_info(self) -> list:
        """Set comments and metadata about fields in the IDD."""
        if self._idd_info is None:
            self._read_idf()
        return self._idd_info

    @property
    def idd_index(self) -> dict:
        """Set pair of dicts used for fast lookups of names of groups of objects."""
        if self._idd_index is None:
            self._read_idf()
        return self._idd_index

    @property
    def idfobjects(self) -> dict:
        """Set dict of lists of idf_MSequence objects in the IDF."""
        if self._idfobjects is None:
            self._read_idf()
        return self._idfobjects

    @property
    def model(self) -> Eplusdata:
        """Set Eplusdata object containing representations of IDF objects."""
        if self._model is None:
            self._read_idf()
        return self._model

    @property
    def idd_version(self) -> tuple:
        """Return the version of the iddname as a tuple."""
        if self._idd_version is None:
            self._read_idf()
        return self._idd_version

    @property
    def iddname(self) -> Path:
        """Get or set the iddname path used to parse the idf model."""
        if self._iddname is None:
            if self.as_version is not None:
                if self.file_version > self.as_version:
                    raise EnergyPlusVersionError(
                        f"{self.as_version} cannot be lower then "
                        f"the version number set in the file: {self.file_version}"
                    )
            self._iddname = self.file_version.current_idd_path
        return self._iddname

    @iddname.setter
    def iddname(self, value):
        if value is not None:
            value = Path(value)
        self._iddname = value

    @property
    def file_version(self) -> EnergyPlusVersion:
        """Return the :class:`EnergyPlusVersion` of the idf text file."""
        if self._file_version is None:
            return EnergyPlusVersion(get_idf_version(self.idfname))
        else:
            return self._file_version

    @file_version.setter
    def file_version(self, value):
        if value is not None:
            value = EnergyPlusVersion(value)
        self._file_version = value

    @property
    def custom_processes(self) -> list:
        """Return list of callables. Called on the output files."""
        return self._custom_processes

    @property
    def include(self) -> list:
        """Return list of external files attached to model."""
        return self._include

    @include.setter
    def include(self, value):
        self._include = value

    @property
    def keep_data_err(self) -> bool:
        """bool: If True, error files are copied back into self.output_folder."""
        return self._keep_data_err

    @keep_data_err.setter
    def keep_data_err(self, value):
        if not isinstance(value, bool):
            raise TypeError("'keep_data_err' needs to be a bool")
        self._keep_data_err = value

    @property
    def keep_data(self) -> bool:
        """bool: If True, keep data folder."""
        return self._keep_data

    # region User-Defined Properties (have setter)
    @property
    def output_suffix(self) -> str:
        """str: The suffix style for output file names (default: L).

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
    def idfname(self) -> Union[Path, StringIO]:
        """Path: The path of the active (parsed) idf model."""
        if self._idfname is None:
            if self.as_version is None:
                self.as_version = settings.ep_version
            idfname = StringIO(f"VERSION, {self.as_version};")
            self._idfname = idfname
            self._reset_dependant_vars("idfname")
        else:
            if isinstance(self._idfname, StringIO):
                pass
            else:
                self._idfname = Path(self._idfname).expand()
        return self._idfname

    @idfname.setter
    def idfname(self, value):
        if not value:
            self._idfname = None
        elif not isinstance(value, (str, os.PathLike, StringIO, IOBase)):
            raise ValueError(f"IDF path must be Path-Like, not {type(value)}")
        elif isinstance(value, (str, os.PathLike)):
            self._idfname = Path(value).expand()
        else:
            self._idfname = value
        self._reset_dependant_vars("idfname")

    @property
    def epw(self) -> Path:
        """Path: The weather file path."""
        if self._epw is not None:
            return Path(self._epw).expand()

    @epw.setter
    def epw(self, value):
        """Set the epw file path."""
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
        """Set verbose status for simulation."""
        if not isinstance(value, bool):
            raise TypeError("'verbose' needs to be a bool")
        self._verbose = value

    @property
    def expandobjects(self) -> bool:
        """bool: If True, run ExpandObjects prior to simulation."""
        return self._expandobjects

    @expandobjects.setter
    def expandobjects(self, value):
        """Set expandobjects."""
        if not isinstance(value, bool):
            raise TypeError("'expandobjects' needs to be a bool")
        self._expandobjects = value

    @property
    def readvars(self) -> bool:
        """bool: If True, run ReadVarsESO after simulation."""
        return self._readvars

    @readvars.setter
    def readvars(self, value):
        """Set readvars."""
        if not isinstance(value, bool):
            raise TypeError("'readvars' needs to be a bool")
        self._readvars = value

    @property
    def epmacro(self) -> bool:
        """bool: If True, run EPMacro prior to simulation."""
        return self._epmacro

    @epmacro.setter
    def epmacro(self, value):
        """Set epmacro."""
        if not isinstance(value, bool):
            raise TypeError("'epmacro' needs to be a bool")
        self._epmacro = value

    @property
    def design_day(self) -> bool:
        """bool: If True, force design-day-only simulation."""
        return self._design_day

    @design_day.setter
    def design_day(self, value):
        """Set design_day."""
        if not isinstance(value, bool):
            raise TypeError("'design_day' needs to be a bool")
        self._design_day = value

    @property
    def annual(self) -> bool:
        """bool: If True, force annual simulation."""
        return self._annual

    @annual.setter
    def annual(self, value):
        """Set annual."""
        if not isinstance(value, bool):
            raise TypeError("'annual' needs to be a bool")
        self._annual = value

    @property
    def convert(self) -> bool:
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
        """Bool or set list of custom outputs."""
        return self._prep_outputs

    @prep_outputs.setter
    def prep_outputs(self, value):
        assert isinstance(value, (bool, list)), (
            f"Expected bool or list of dict for "
            f"SimulationOutput outputs. Got {type(value)}."
        )
        self._prep_outputs = value

    @property
    def as_version(self):
        """Specify the desired :class:`EnergyPlusVersion` for the IDF model."""
        if self._as_version is not None:
            return EnergyPlusVersion(self._as_version)
        else:
            return self._as_version

    @as_version.setter
    def as_version(self, value):
        # Parse value and check if above or bellow
        if value is None:
            self._as_version = None
        else:
            self._as_version = EnergyPlusVersion(value)

    @property
    def output_directory(self) -> Path:
        """Path: The output directory based on the hashing of the original file.

        Notes:
            The hashing is performed before transitions or modifications. The directory
            is not created! Use `self.output_directory.makedir_p()` to create it
            without an error if it exists.
        """
        if self._output_directory is None:
            cache_filename = self._original_cache
            output_directory = settings.cache_folder / cache_filename
            self._output_directory = output_directory.expand()
        return Path(self._output_directory)

    @output_directory.setter
    def output_directory(self, value):
        if value:
            value = Path(value)
        self._output_directory = value

    @property
    def output_prefix(self) -> str:
        """str: Prefix for output file names (default: eplus)."""
        if self._output_prefix is None:
            self._output_prefix = "eplus"
        return self._output_prefix

    @output_prefix.setter
    def output_prefix(self, value):
        if value and not isinstance(value, str):
            raise TypeError("'output_prefix' needs to be a string")
        self._output_prefix = value

    @property
    def sim_id(self) -> str:
        """str: The unique Id of the simulation.

        Based on a subset of hashed variables:
            - The idf model itself.
            - epw
            - annual
            - design_day
            - readvars
            - as_version
        """
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

    # endregion
    @property
    def sim_info(self) -> Optional[DataFrame]:
        """DataFrame: Unique number generated for a simulation."""
        if self.sql_file is not None:
            with sqlite3.connect(self.sql_file) as conn:
                sql_query = """select * from Simulations"""
                sim_info = pd.read_sql_query(sql_query, con=conn)
            return sim_info
        else:
            return None

    @property
    def sim_timestamp(self) -> Union[str, Series]:
        """Return the simulation timestamp or "Never" if not ran yet."""
        if self.sim_info is None:
            return "Never"
        else:
            return self.sim_info.TimeStamp

    @property
    def position(self) -> int:
        """int: Position for the progress bar."""
        return self._position

    @property
    def idfversionupdater_dir(self) -> Path:
        """Path: The path of the IDFVersionUpdater folder.

        Uses the current module's ep_version.
        """
        return (
            EnergyPlusVersion.latest().current_install_dir
            / "PreProcess"
            / "IDFVersionUpdater"
        ).expand()

    @property
    def name(self) -> str:
        """str: Name of the idf model.

        Can include the extension (.idf).
        """
        return self._name

    @name.setter
    def name(self, value):
        if value is None:
            value = f"{uuid.uuid1()}.idf"
        elif ".idf" not in value:
            value = Path(value).stem + ".idf"
        self._name = value

    def sql(self) -> dict:
        """Get the sql table report."""
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

    def htm(self) -> dict:
        """Get the htm table report."""
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
    def energyplus_its(self) -> int:
        """Return number of iterations needed to complete simulation."""
        if self._energyplus_its is None:
            self._energyplus_its = 0
        return self._energyplus_its

    def open_htm(self):
        """Open .htm file in browser."""
        import webbrowser

        html, *_ = self.simulation_dir.files("*.htm")

        webbrowser.open(html.abspath())

    def open_idf(self):
        """Open file in correct version of Ep-Launch."""
        if isinstance(self.idfname, StringIO):
            # make a temporary file if inmemery IDF.
            filepath = self.savecopy(self.output_directory.makedirs_p() / self.name)
        else:
            filepath = self.idfname

        app_path_guess = (
            self.file_version.current_install_dir / "PreProcess" / "IDFEditor"
        )
        find_and_launch("IDFEditor", app_path_guess, filepath.abspath())

    def open_last_simulation(self):
        """Open last simulation in Ep-Launch."""
        filepath, *_ = self.simulation_dir.files("*.idf")

        app_path_guess = self.file_version.current_install_dir
        find_and_launch("EP-Launch", app_path_guess, filepath.abspath())

    def open_err(self):
        """Open last simulation err file in texteditor."""
        import webbrowser

        filepath, *_ = self.simulation_dir.files("*.err")

        webbrowser.open(filepath.abspath())

    def open_mdd(self):
        """Open .mdd file in browser.

        This file shows all the report meters along with their “availability” for the
        current input file.
        """
        import webbrowser

        mdd, *_ = self.simulation_dir.files("*.mdd")

        webbrowser.open(mdd.abspath())

    def open_mtd(self):
        """Open .mtd file in browser.

        This file contains the “meter details” for the run. This shows what report
        variables are on which meters and vice versa – which meters contain what
        report variables.
        """
        import webbrowser

        mtd, *_ = self.simulation_dir.files("*.mtd")

        webbrowser.open(mtd.abspath())

    @property
    def sql_file(self):
        """Get the sql file path."""
        try:
            file, *_ = self.simulation_dir.files("*out.sql")
        except (FileNotFoundError, ValueError):
            return None
        return file.expand()

    @property
    def mtd_file(self) -> Path:
        """Get the mtd file path."""
        try:
            file, *_ = self.simulation_dir.files("*.mtd")
        except (FileNotFoundError, ValueError):
            return self.simulate().mtd_file
        return file.expand()

    @property
    def net_conditioned_building_area(self) -> float:
        """Return the total conditioned area of a building.

        Takes into account zone multipliers.
        """
        if self._area_conditioned is None:
            if self.simulation_dir.exists():
                with sqlite3.connect(self.sql_file) as conn:
                    sql_query = """
                    SELECT t.Value
                    FROM TabularDataWithStrings t
                    WHERE TableName == 'Building Area'
                        and ColumnName == 'Area'
                        and RowName == 'Net Conditioned Building Area';
                        """
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
    def unconditioned_building_area(self) -> float:
        """Return the Unconditioned Building Area."""
        if self._area_unconditioned is None:
            if self.simulation_dir.exists():
                with sqlite3.connect(self.sql_file) as conn:
                    sql_query = """
                    SELECT t.Value
                    FROM TabularDataWithStrings t
                    WHERE TableName == 'Building Area'
                        and ColumnName == 'Area'
                        and RowName == 'Unconditioned Building Area';
                        """
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
    def total_building_area(self) -> float:
        """Return the Total Building Area."""
        if self._area_total is None:
            if self.simulation_dir.exists():
                with sqlite3.connect(self.sql_file) as conn:
                    sql_query = """
                    SELECT t.Value
                    FROM TabularDataWithStrings t
                    WHERE TableName == 'Building Area'
                        and ColumnName == 'Area' and RowName == 'Total Building Area';
                        """
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
    def total_building_volume(self):
        return NotImplemented()

    @staticmethod
    def _get_volume_from_surfs(zone_surfs):
        """Calculate the volume of a zone only and only if the surfaces are such
        that you can find a point inside so that you can connect every vertex to
        the point without crossing a face.

        Adapted from: https://stackoverflow.com/a/19125446

        Args:
            zone_surfs (list): List of zone surfaces (EpBunch)
        """
        vol = 0
        for surf in zone_surfs:
            polygon_d = Polygon3D(surf.coords)  # create Polygon3D from surf
            n = len(polygon_d.vertices_list)
            v2 = polygon_d[0]
            x2 = v2.x
            y2 = v2.y
            z2 = v2.z

            for i in range(1, n - 1):
                v0 = polygon_d[i]
                x0 = v0.x
                y0 = v0.y
                z0 = v0.z
                v1 = polygon_d[i + 1]
                x1 = v1.x
                y1 = v1.y
                z1 = v1.z
                # Add volume of tetrahedron formed by triangle and origin
                vol += math.fabs(
                    x0 * y1 * z2
                    + x1 * y2 * z0
                    + x2 * y0 * z1
                    - x0 * y2 * z1
                    - x1 * y0 * z2
                    - x2 * y1 * z0
                )
        return vol / 6.0

    @property
    def partition_ratio(self) -> float:
        """float: Lineal meters of partitions per m2 of floor area."""
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
            self._partition_ratio = partition_lineal / max(
                self.net_conditioned_building_area, self.unconditioned_building_area
            )
        return self._partition_ratio

    @property
    def simulation_files(self) -> list:
        """list: The list of files generated by the simulation."""
        try:
            return self.simulation_dir.files()
        except FileNotFoundError:
            return []

    @property
    def simulation_dir(self) -> Path:
        """Path: The path where simulation results are stored."""
        try:
            return (self.output_directory / self.sim_id).expand()
        except AttributeError:
            return Path()

    @property
    def schedules_dict(self) -> dict:
        """Return the dict of {NAME: schedule} in the model."""
        if self._schedules_dict is None:
            self._schedules_dict = self._get_all_schedules()
        return self._schedules_dict

    @property
    def outputs(self) -> Outputs:
        """Return the Outputs class associated with the model."""
        return self._outputs

    @property
    def day_of_week_for_start_day(self):
        """Get day of week for start day for the first found RUNPERIOD.

        Monday = 0 .. Sunday = 6
        """
        import calendar

        run_period = next(iter(self.idfobjects["RUNPERIOD"]), None)
        if run_period:
            day = run_period["Day_of_Week_for_Start_Day"]
        else:
            log("model does not contain a 'RunPeriod'. Defaulting to Sunday.")
            day = "Sunday"

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
        output is appended to the :attr:`IDF.idfobjects` list, but will not overwrite
        the original idf file, unless :meth:`IDF.save` is called.

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

    def simulate(self, force=False, **kwargs):
        """Execute EnergyPlus.

        Specified kwargs overwrite IDF parameters. ExpandObjects, Basement and Slab
        preprocessors are ran before EnergyPlus.

        Does not return anything.

        Args:
            force (bool): Force simulation even though results exist in
                `self.simulation_dir`.

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
            :attr:`IDF.simulation_files`, :attr:`IDF.processed_results` for simulation
            outputs.

        """
        if (
            self.simulation_dir.exists() and not force
        ):  # don't simulate if results exists
            return self
        # First, update keys with new values
        for key, value in kwargs.items():
            if f"_{key}" in self.__dict__.keys():
                setattr(self, key, value)

        if self.as_version is not None:
            if self.as_version != EnergyPlusVersion(self.idd_version):
                raise EnergyPlusVersionError(
                    None,
                    self.idfname,
                    EnergyPlusVersion(self.idd_version),
                    self.as_version,
                )

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
            self.output_directory.makedirs_p() / "expandobjects_run_"
            + str(uuid.uuid1())[0:8]
        ).mkdir()
        # Run the ExpandObjects preprocessor program
        expandobjects_thread = ExpandObjectsThread(self, tmp)
        try:
            expandobjects_thread.start()
            expandobjects_thread.join()
            # Give time to the subprocess to finish completely
            while expandobjects_thread.is_alive():
                time.sleep(1)
        except (KeyboardInterrupt, SystemExit):
            expandobjects_thread.stop()
        finally:
            tmp.rmtree(ignore_errors=True)
            e = expandobjects_thread.exception
            if e is not None:
                raise e

        # Run the Basement preprocessor program if necessary
        tmp = (
            self.output_directory.makedirs_p() / "runBasement_run_"
            + str(uuid.uuid1())[0:8]
        ).mkdir()
        basement_thread = BasementThread(self, tmp)
        try:
            basement_thread.start()
            basement_thread.join()
            # Give time to the subprocess to finish completely
            while basement_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            basement_thread.stop()
        finally:
            tmp.rmtree(ignore_errors=True)
            e = basement_thread.exception
            if e is not None:
                raise e

        # Run the Slab preprocessor program if necessary
        tmp = (
            self.output_directory.makedirs_p() / "runSlab_run_" + str(uuid.uuid1())[0:8]
        ).mkdir()
        slab_thread = SlabThread(self, tmp)
        try:
            slab_thread.start()
            slab_thread.join()
            # Give time to the subprocess to finish completely
            while slab_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            slab_thread.stop()
        finally:
            tmp.rmtree(ignore_errors=True)
            e = slab_thread.exception
            if e is not None:
                raise e

        # Run the energyplus program
        tmp = (
            self.output_directory.makedirs_p() / "eplus_run_" + str(uuid.uuid1())[0:8]
        ).mkdir()
        running_simulation_thread = EnergyPlusThread(self, tmp)
        try:
            running_simulation_thread.start()
            running_simulation_thread.join()
            # Give time to the subprocess to finish completely
            while running_simulation_thread.is_alive():
                time.sleep(1)
        except KeyboardInterrupt:
            running_simulation_thread.stop()
        finally:
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
                'default', 'windows' and 'unix' the default is 'default' which uses
                the line endings for the current system.
            encoding (str): Encoding to use for the saved file. The default is
                'latin-1' which is compatible with the EnergyPlus IDFEditor.

        Returns:
            Path: The new file path.
        """
        super(IDF, self).save(filename, lineendings, encoding)
        return Path(filename)

    def copy(self):
        """Return a copy of self as an in memory IDF.

        The copy is a new IDF object with the same parameters and arguments as self
        but is not attached to an file. Use IDF.saveas("idfname.idf", inplace=True)
        to save the copy to a file inplace. self.idfname will now be idfname.idf
        """
        return self.saveas(io.StringIO(""))

    def save(self, lineendings="default", encoding="latin-1", **kwargs):
        """Write the IDF model to the text file.

        Uses :meth:`~eppy.modeleditor.IDF.save` but also brings over existing
        simulation results.

        Args:
            lineendings (str) : Line endings to use in the saved file. Options are
                'default', 'windows' and 'unix' the default is 'default' which uses
                the line endings for the current system.
            encoding (str): Encoding to use for the saved file. The default is
                'latin-1' which is compatible with the EnergyPlus IDFEditor.
        Returns:
            IDF: The IDF model
        """
        super(IDF, self).save(
            filename=self.idfname, lineendings=lineendings, encoding=encoding
        )
        log(f"saved '{self.name}' at '{self.idfname}'")
        return self

    def saveas(
        self, filename, lineendings="default", encoding="latin-1", inplace=False
    ):
        """Save the IDF model as.

        Writes a new text file and load a new instance of the IDF class (new object).

        Args:
            filename (str): Filepath to save the file. If None then use the IDF.idfname
                parameter. Also accepts a file handle.
            lineendings (str) : Line endings to use in the saved file. Options are
                'default', 'windows' and 'unix' the default is 'default' which uses
                the line endings for the current system.
            encoding (str): Encoding to use for the saved file. The default is
                'latin-1' which is compatible with the EnergyPlus IDFEditor.
            inplace (bool): If True, applies the new filename to self directly,
                else a new object is returned with the new filename.

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
        if self.simulation_files:
            # If simulation files exist in cache, copy to new cache location
            as_idf.simulation_dir.makedirs_p()
            for file in self.simulation_files:
                if self.output_prefix in file:
                    name = file.replace(self.output_prefix, as_idf.output_prefix)
                    name = Path(name).basename()
                else:
                    name = file.basename()
                try:
                    file.copy(as_idf.simulation_dir / name)
                except shutil.SameFileError:
                    # A copy of self would have the same files in the simdir and
                    # throw an error.
                    pass
        if inplace:
            # If inplace, replace content of self with content of as_idf.
            self.__dict__.update(as_idf.__dict__)
        else:
            # return the new object.
            return as_idf

    def process_results(self):
        """Return the list of processed results.

        Processes are defined by :attr:`custom_processes` as a list of tuple(file,
        result). A default process looks for csv files and tries to parse them into
        :class:`~pandas.DataFrame` objects.

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

    def add_idf_object_from_idf_string(self, idf_string):
        """Add an IDF object (or more than one) from an EnergyPlus text string.

        Args:
            idf_string (str): A text string fully describing an EnergyPlus object.
        """
        # Load the idf_string as a new model.
        loaded_string = IDF(
            StringIO(idf_string),
            file_version=self.file_version,
            as_version=self.as_version,
            prep_outputs=False,
        )

        # Loop on all objects and using self.newidfobject
        added_objects = []
        for sequence in loaded_string.idfobjects.values():
            if sequence:
                for obj in sequence:
                    data = obj.to_dict()
                    key = data.pop("key")
                    added_objects.append(self.newidfobject(key=key.upper(), **data))
        del loaded_string  # remove loaded_string model
        return added_objects

    def upgrade(self, to_version=None, overwrite=True):
        """`EnergyPlus` idf version updater using local transition program.

        Update the EnergyPlus simulation file (.idf) to the latest available
        EnergyPlus version installed on this machine. Optionally specify a version
        (eg.: "9-2-0") to aim for a specific version. The output will be the path of
        the updated file. The run is multiprocessing_safe.

        Hint:
            If attempting to upgrade an earlier version of EnergyPlus (pre-v7.2.0),
            specific binaries need to be downloaded and copied to the
            EnergyPlus*/PreProcess/IDFVersionUpdater folder. More info at
            `Converting older version files
            <http://energyplus.helpserve.com/Knowledgebase/List/Index/46
            /converting-older-version-files>`_.

        Args:
            to_version (str, optional): EnergyPlus version in the form "X-X-X".
            overwrite (bool): If True, original idf file is overwritten with new
                transitioned file.

        Raises:
            EnergyPlusProcessError: If version updater fails.
            EnergyPlusVersionError:
            CalledProcessError:
        """
        # First, set versions
        if to_version is None:
            to_version = EnergyPlusVersion.latest()
        elif isinstance(to_version, (str, tuple)):
            to_version = EnergyPlusVersion(to_version)

        # second check if upgrade needed
        if self.file_version == to_version:
            return
        elif self.file_version > to_version:
            raise EnergyPlusVersionError(self.name, self.file_version, to_version)
        else:
            self.as_version = to_version  # set version number
            # execute transitions
            tmp = (
                self.output_directory / "Transition_run_" + str(uuid.uuid1())[0:8]
            ).makedirs_p()
            transition_thread = TransitionThread(self, tmp, overwrite=overwrite)
            transition_thread.start()
            transition_thread.join()
            while transition_thread.is_alive():
                time.sleep(1)
            tmp.rmtree(ignore_errors=True)
            e = transition_thread.exception
            if e is not None:
                raise e

    def wwr(self, azimuth_threshold=10, round_to=10):
        """Return the Window-to-Wall Ratio by major orientation.

        Optionally round up the WWR value to nearest value (eg.: nearest 10 %).

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

        def roundto(x, to=10.0):
            """Round up to closest `to` number."""
            from builtins import round

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
                    if surface.Outside_Boundary_Condition.lower() == "outdoors":
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
        """Return space-heating time series.

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
        """Return space-cooling time series.

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
        """Return service water heating (domestic hot water) time series.

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
        """Return user-defined time series.

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

    def newidfobject(self, key, **kwargs) -> Optional[EpBunch]:
        """Define EpBunch object and add to model.

        The function will test if the object exists to prevent duplicates.

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
            EpBunch: the object, if successful
            None: If an error occured.
        """
        # get list of objects
        existing_objs = self.idfobjects[key]  # a list

        # create new object
        try:
            new_object = self.anidfobject(key, **kwargs)
        except BadEPFieldError as e:
            raise e
        else:
            # If object is supposed to be 'unique-object', delete all objects to be
            # sure there is only one of them when creating new object
            # (see following line)
            if "unique-object" in set().union(
                *(d.objidd[0].keys() for d in existing_objs)
            ):
                for obj in existing_objs:
                    self.removeidfobject(obj)
                    log(
                        f"{obj} is a 'unique-object'; Removed and replaced with"
                        f" {new_object}",
                        lg.DEBUG,
                    )
                self.addidfobject(new_object)
                return new_object
            if new_object in existing_objs:
                # If obj already exists, simply return the existing one.
                log(
                    f"object '{new_object}' already exists in {self.name}. "
                    f"Skipping.",
                    lg.DEBUG,
                )
                return next(x for x in existing_objs if x == new_object)
            elif new_object not in existing_objs and new_object.nameexists():
                # Object does not exist (because not equal) but Name exists.
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

    def addidfobject(self, new_object) -> EpBunch:
        """Add an IDF object to the model.

        Args:
            new_object (EpBunch): The IDF object to add.

        Returns:
            EpBunch: object.
        """
        key = new_object.key.upper()
        self.idfobjects[key].append(new_object)
        self._reset_dependant_vars("idfobjects")
        return new_object

    def addidfobjects(self, new_objects):
        """Add multiple IDF objects to the model.

        Resetting dependent variables will wait after all objects have been added.
        """
        for new_object in new_objects:
            key = new_object.key.upper()
            self.idfobjects[key].append(new_object)
        self._reset_dependant_vars("idfobjects")
        return new_objects

    def removeidfobject(self, idfobject):
        """Remove an IDF object from the model.

        Args:
            idfobject (EpBunch): The object to remove from the model.
        """
        key = idfobject.key.upper()
        self.idfobjects[key].remove(idfobject)
        self._reset_dependant_vars("idfobjects")

    def removeidfobjects(self, idfobjects: Iterable[EpBunch]):
        """Remove an IDF object from the model.

        Resetting dependent variables will wait after all objects have been removed.

        Args:
            idfobjects: The object to remove from the model.
        """
        for idfobject in idfobjects:
            key = idfobject.key.upper()
            self.idfobjects[key].remove(idfobject)
        self._reset_dependant_vars("idfobjects")

    def anidfobject(self, key: str, aname: str = "", **kwargs) -> EpBunch:
        """Define and create an object, but don't add it to the model.

        See :func:`~archetypal.idfclass.idf.IDF.newidfobject`). If you don't specify
        a value for a field, the default value will be set.

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
        """Return the data for a particular 'ScheduleTypeLimits' object.

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
        """Return the epbunch of a particular schedule name.

        If the schedule type is known, retrievess it quicker.

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

    def _get_all_schedules(self, yearly_only=False):
        """Return all schedule ep_objects in a dict with their name as a key.

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

    def _get_used_schedules(self, yearly_only=False):
        """Return all used schedules.

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
        all_schedules = self._get_all_schedules(yearly_only=yearly_only)
        for object_name in self.idfobjects:
            for obj in self.idfobjects[object_name]:
                if obj.key.upper() not in schedule_types:
                    for fieldvalue in obj.fieldvalues:
                        try:
                            if (
                                fieldvalue.upper() in all_schedules.keys()
                                and fieldvalue not in used_schedules
                            ):
                                used_schedules.append(fieldvalue)
                        except (KeyError, AttributeError):
                            pass
        return used_schedules

    @property
    def width(self):
        """Get the width of the building [m]."""
        bbox = self.bounding_box()
        return max(bbox.xs) - min(bbox.xs)

    @property
    def length(self):
        """Get the length of the building [m]."""
        bbox = self.bounding_box()
        return max(bbox.ys) - min(bbox.ys)

    def resize(self, width, length):
        """Resize the floor plate to x and y [meters].

        Args:
            width (float): The new width [m] of the building (x axis).
            length (float): The new length [m] of the building (y axis).
        """
        x_scale = width / self.width
        y_scale = length / self.length
        self.scale(x_scale, axes="x")
        self.scale(y_scale, axes="y")

    def rename(self, objkey, objname, newname):
        """Rename all the references to this objname.

        Function comes from eppy.modeleditor and was modified to compare the
        name to rename with a lower string (see
        idfobject[idfobject.objls[findex]].lower() == objname.lower()).

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

    def set_wwr(
        self,
        wwr: float = None,
        construction: Optional[str] = None,
        force: bool = False,
        wwr_map: Optional[dict] = None,
        surfaces: Optional[Iterable] = None,
    ):
        """Set Window-to-Wall Ratio of external walls.

        Different WWR can be applied to specific wall orientations using the
        `wwr_map` dictionary. This map is a dict of wwr values, keyed by
        `wall.azimuth`, which overrides the default passed as `wwr`. Note that
        `wall.azimuth` is rounded to the closest integer.

        They can also be applied to walls oriented to a compass point, e.g. north,
        which will apply to walls which have an azimuth within 45 degrees of due north.

        Args:
            wwr: The window to wall ratio to apply to all orientations. If wwr_map is
                specified, `wwr` is the default wwr for oreintations not defined in
                the mapping.
            construction: Name of a window construction to apply.
            force: True to create windows on walls that don't have any.
            wwr_map: Mapping from wall orientation (azimuth) to WWR, e.g.
                {180: 0.25, 90: 0.2}.
            surfaces: Iterable of surfaces to set the window to wall ratio of.
        """
        # Taken from `geomeppy.idf.IDF.set_wwr` since pull request is not being
        # reviewed as of 2021-11-10.

        try:
            ggr: Optional[Idf_MSequence] = self.idfobjects["GLOBALGEOMETRYRULES"][0]
        except IndexError:
            ggr = None

        wwr_map = wwr_map or {0: wwr, 90: wwr, 180: wwr, 270: wwr}

        # check orientation
        for degrees, wwr in wwr_map.items():
            external_walls = filter(
                lambda x: x.Outside_Boundary_Condition.lower() == "outdoors",
                surfaces or self.getsurfaces("wall"),
            )
            external_walls = filter(
                lambda x: closest_cardinal_angle(x.azimuth) == degrees, external_walls
            )
            subsurfaces = self.getsubsurfaces()
            for wall in external_walls:
                # get any subsurfaces on the wall
                wall_subsurfaces = list(
                    filter(lambda x: x.Building_Surface_Name == wall.Name, subsurfaces)
                )

                if wall_subsurfaces and not construction:
                    constructions = list(
                        {
                            wss.Construction_Name
                            for wss in wall_subsurfaces
                            if _is_window(wss)
                        }
                    )
                    if len(constructions) > 1:
                        raise ValueError(
                            'Not all subsurfaces on wall "{name}" have the same construction'.format(
                                name=wall.Name
                            )
                        )
                    construction = constructions[0]
                if len(wall_subsurfaces) == 0 and not force:
                    # Don't create windows on walls that don't have any windows already.
                    continue
                # remove all subsurfaces
                for ss in wall_subsurfaces:
                    self.rename(ss.key.upper(), ss.Name, "%s window" % wall.Name)
                    self.removeidfobject(ss)
                coords = window_vertices_given_wall(wall, wwr)
                window = self.newidfobject(
                    "FENESTRATIONSURFACE:DETAILED",
                    Name="%s window" % wall.Name,
                    Surface_Type="Window",
                    Construction_Name=construction or "",
                    Building_Surface_Name=wall.Name,
                    View_Factor_to_Ground="autocalculate",  # from the surface angle
                )
                window.setcoords(coords, ggr)

    def _energy_series(
        self,
        energy_out_variable_name,
        units,
        name,
        prep_outputs=None,
        EnergySeries_kwds=None,
    ) -> EnergySeries:
        """Query the report data and return an EnergySeries.

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
                re.search(r"to-V(([\d])-([\d])-([\d]))", executable).group(1)
            ): executable
            for executable in self.idfversionupdater_dir.files("Transition-V*")
        }

        transitions = [
            key for key in trans_exec if to_version >= key > self.file_version
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

    def to_world(self):
        """Translate surfaces and subsurfaces to 'World' coordinates.

        Notes:
            Shading surfaces are already specified in world coordinates. Daylighting
            reference points are also translated in this method.
        """
        from geomeppy.geom.vectors import Vector3D
        from geomeppy.recipes import translate, translate_coords

        if (
            "world"
            in [
                o.Coordinate_System.lower()
                for o in self.idfobjects["GLOBALGEOMETRYRULES"]
            ]
            or self.translated
        ):
            log("Model already set as World coordinates", level=lg.WARNING)
            return
        zone_angles = set(
            z.Direction_of_Relative_North or 0 for z in self.idfobjects["ZONE"]
        )
        # If Zones have Direction_of_Relative_North != 0, model needs to be rotated
        # before translation.
        if all(angle != 0 for angle in zone_angles):
            self.rotate(None, (0, 0, 0))

            from geomeppy.recipes import rotate

            # Since we rotated the building and the site, we need to rotate the site
            # back by angle
            anchor = Vector3D(*(0, 0, 0))
            shadingsurfaces = self.getsiteshadingsurfaces()
            self.translate(-anchor)
            rotate(shadingsurfaces, next(iter(zone_angles)))
            self.translate(anchor)

        zone_origin = {
            zone.Name.upper(): Vector3D(
                zone.X_Origin or 0, zone.Y_Origin or 0, zone.Z_Origin or 0
            )
            for zone in self.idfobjects["ZONE"]
        }
        surfaces = {s.Name.upper(): s for s in self.getsurfaces()}
        subsurfaces = self.getsubsurfaces()
        daylighting_refpoints = [
            p for p in self.idfobjects["DAYLIGHTING:REFERENCEPOINT"]
        ]
        attached_shading_surf_names = []
        for g in self.idd_index["ref2names"]["AttachedShadingSurfNames"]:
            for item in self.idfobjects[g]:
                attached_shading_surf_names.append(item)

        # Translate surfaces in the direction of their zone's origin vector.
        for subsurf in subsurfaces:
            zone_name = surfaces[subsurf.Building_Surface_Name.upper()].Zone_Name
            translate([subsurf], zone_origin[zone_name.upper()])
        for surf_name, surf in surfaces.items():
            translate([surf], zone_origin[surf.Zone_Name.upper()])
        for day in daylighting_refpoints:
            zone_name = day.Zone_or_Space_Name
            coords = translate_coords(day.coords, zone_origin[zone_name.upper()])
            (
                day.XCoordinate_of_Reference_Point,
                day.YCoordinate_of_Reference_Point,
                day.ZCoordinate_of_Reference_Point,
            ) = coords[0]
        for attached_surf in attached_shading_surf_names:
            parent_surface = attached_surf.get_referenced_object("Base_Surface_Name")
            zone_name = parent_surface.Zone_Name
            translate([attached_surf], zone_origin[zone_name.upper()])

        # Edit the `GLOBALGEOMETRYRULES` to "World"
        for obj in self.idfobjects["GLOBALGEOMETRYRULES"]:
            obj.Coordinate_System = "World"
            obj.Daylighting_Reference_Point_Coordinate_System = "World"
            obj.Rectangular_Surface_Coordinate_System = "World"

        # Set all zone origin vectors to (0,0,0)
        for zone in self.idfobjects["ZONE"]:
            zone.X_Origin, zone.Y_Origin, zone.Z_Origin = 0, 0, 0

        self.translated = True
        # Finally, rotate model if not already rotated.
        if not self.rotated:
            self.rotate(None, (0, 0, 0))

    def view_model(self, test=False):
        # type: (Optional[bool]) -> None
        """Show a zoomable, rotatable representation of the IDF."""
        from geomeppy.view_geometry import view_idf

        if (
            "relative"
            in [
                o.Coordinate_System.lower()
                for o in self.idfobjects["GLOBALGEOMETRYRULES"]
            ]
            and self.coords_are_truly_relative
        ):
            raise Exception(
                "Model is in relative coordinates and must be translated to world using "
                "IDF.to_world()."
            )
        view_idf(idf=self, test=test)

    @property
    def coords_are_truly_relative(self):
        """True if GlobalGeometryRules as `Relative` and Zone origins are not 0,0,0."""
        ggr_asks_for_relative = "relative" in [
            o.Coordinate_System.lower() for o in self.idfobjects["GLOBALGEOMETRYRULES"]
        ]
        all_zone_origin_at_0 = True
        for z in self.idfobjects["ZONE"]:
            xyz = (z.X_Origin, z.Y_Origin, z.Z_Origin)
            coord = tuple(pd.to_numeric(pd.Series(xyz)).fillna(0))
            if coord != (0, 0, 0):
                all_zone_origin_at_0 = False
        return ggr_asks_for_relative and not all_zone_origin_at_0

    def rotate(
        self, angle: Optional[float] = None, anchor: Tuple[float, float, float] = None
    ):
        """Rotate the IDF counterclockwise around `anchor` by the angle given (degrees).

        IF angle is None, rotates to Direction_of_Relative_North specified in Zone
        objects.
        """
        if not angle:
            bldg_angle = self.idfobjects["BUILDING"][0].North_Axis or 0
            log(f"Building North Axis = {bldg_angle}", level=lg.DEBUG)
            zone_angles = set(
                z.Direction_of_Relative_North for z in self.idfobjects["ZONE"]
            )
            assert (
                len(zone_angles) == 1
            ), "Not all zone have the same Direction_of_Relative_North"
            zone_angle, *_ = zone_angles
            zone_angle = zone_angle or 0
            log(f"Zone(s) North Axis = {zone_angle}", level=lg.DEBUG)
            angle = -(bldg_angle + zone_angle)
        if isinstance(anchor, tuple):
            from geomeppy.geom.vectors import Vector3D

            anchor = Vector3D(*anchor)
        # Rotate the building
        super(IDF, self).rotate(angle, anchor=anchor)
        log(
            f"Geometries rotated by {angle} degrees around "
            f"{anchor or 'building centroid'}"
        )

        # after building is rotate, change the north axis and zone direction to zero.
        self.idfobjects["BUILDING"][0].North_Axis = 0
        for z in self.idfobjects["ZONE"]:
            z.Direction_of_Relative_North = 0
        # Mark the model as rotated
        self.rotated = True

    def translate(self, vector: Tuple[float, float, float]):
        """Move the IDF in the direction given by a vector."""
        if isinstance(vector, tuple):
            from geomeppy.geom.vectors import Vector2D

            vector = Vector2D(*vector)

        super(IDF, self).translate(vector=vector)
        self.translated = True

    @property
    def translated(self):
        """Get or set if the model was translated (X, Y, Z)."""
        return self._translated

    @translated.setter
    def translated(self, value):
        self._translated = bool(value)

    @property
    def rotated(self):
        """Get or set if the model was rotated."""
        return self._rotated

    @rotated.setter
    def rotated(self, value):
        self._rotated = bool(value)

    def getsiteshadingsurfaces(self, surface_type=""):
        site_shading_types = self.idd_index["ref2names"][
            "AllShadingSurfNames"
        ].difference(self.idd_index["ref2names"]["AttachedShadingSurfNames"])
        surfaces = itertools.chain.from_iterable(
            [self.idfobjects[key.upper()] for key in site_shading_types]
        )
        if surface_type:
            surfaces = filter(
                lambda x: x.Surface_Type.lower() == surface_type.lower(), surfaces
            )
        return list(surfaces)


def _process_csv(file, working_dir, simulname):
    """Process csv file.

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


def closest_cardinal_angle(azimuth):
    """Returns the closest bearing angle to the given azimuth angle."""
    dirs = [0, 90, 180, 270]
    ix = int(round(azimuth / (360.0 / len(dirs))))
    return dirs[ix % len(dirs)]
