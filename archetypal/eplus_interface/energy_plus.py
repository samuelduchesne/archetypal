import logging as lg
import subprocess
import time
from subprocess import CalledProcessError
from threading import Thread

import eppy
from eppy.runner.run_functions import paths_from_version
from path import Path
from tqdm import tqdm

from archetypal.eplus_interface.exceptions import (
    EnergyPlusProcessError,
    EnergyPlusVersionError,
)
from archetypal.eplus_interface.version import EnergyPlusVersion
from archetypal.utils import log


class EnergyPlusProgram:
    def __init__(self, idf):
        self.idf = idf

    @property
    def eplus_home(self):
        eplus_exe, eplus_home = paths_from_version(self.idf.as_version.dash)
        if not Path(eplus_home).exists():
            raise EnergyPlusVersionError(
                msg=f"No EnergyPlus Executable found for version "
                f"{EnergyPlusVersion(self.idf.as_version)}"
            )
        else:
            return Path(eplus_home)


class EnergyPlusExe:
    """Usage: energyplus [options] [input-file]"""

    def __init__(
        self,
        idfname,
        epw,
        output_directory,
        ep_version,
        annual=False,
        convert=False,
        design_day=False,
        help=False,
        idd=None,
        epmacro=False,
        output_prefix="eplus",
        readvars=True,
        output_sufix="L",
        version=False,
        expandobjects=True,
    ):
        """
        Args:
            idfname (str):
            epw (str): Weather file path (default: in.epw in current directory))
            output-directory (str): Output directory path (default: current directory)
            ep_version (archetypal.EnergyPlusVersion): The version of energyplus
                executable.
            annual (bool): Force annual simulation. (default: False)
            convert (bool): Output IDF->epJSON or epJSON->IDF, dependent on input
                file type. (default: False)
            design_day (bool): Force design-day-only simulation. (default: False)
            help (bool): Display help information
            idd (str) :Input data dictionary path (default: Energy+.idd in
                executable directory)
            epmacro (bool): Run EPMacro prior to simulation. (default: True)
            output_prefix (str): Prefix for output file names (default: eplus)
            readvars (bool): Run ReadVarsESO after simulation. (default: True)
            output_suffix (str): Suffix style for output file names (
                default: L)
                    -L: Legacy (e.g., eplustbl.csv)
                    -C: Capital (e.g., eplusTable.csv)
                    -D: Dash (e.g., eplus-table.csv)
            version (bool): Display version information (default: False)
            expandobjects (bool): Run ExpandObjects prior to simulation. (default: True)
        """
        self.a = annual
        self.c = convert
        self.d = output_directory
        self.D = design_day
        self.h = help
        self.i = idd
        self.m = epmacro
        self.p = output_prefix
        self.r = readvars
        self.s = output_sufix
        self.v = version
        self.w = epw
        self.x = expandobjects

        self.idfname = idfname
        self.ep_version = ep_version

        self.get_exe_path()

    def get_exe_path(self):
        (eplus_exe_path, eplus_weather_path) = eppy.runner.run_functions.install_paths(
            self.ep_version.dash, self.i
        )
        if not Path(eplus_exe_path).exists():
            raise EnergyPlusVersionError(
                msg=f"No EnergyPlus Executable found for version "
                f"{EnergyPlusVersion(self.ep_version)}"
            )
        self.eplus_exe_path = Path(eplus_exe_path).expand()
        self.eplus_weather_path = Path(eplus_weather_path).expand()

    def __str__(self):
        """Return string representation."""
        return " ".join(self.__repr__())

    def __repr__(self):
        """Return a representation of self."""
        cmd = [self.eplus_exe_path]
        for key, value in self.__dict__.items():
            if key not in [
                "idfname",
                "ep_version",
                "eplus_exe_path",
                "eplus_weather_path",
            ]:
                if isinstance(value, bool):
                    cmd.append(f"-{key}") if value else None
                else:
                    cmd.extend([f"-{key}", value]) if value is not None else None
        cmd.append(self.idfname)
        return cmd

    def cmd(self):
        return self.__repr__()


class EnergyPlusThread(Thread):
    def __init__(self, idf, tmp):
        """

        Args:
            idf (IDF): The idf model.
            tmp (str or Path): The directory in which the process will be launched.
        """
        super(EnergyPlusThread, self).__init__()
        self.p = None
        self.std_out = None
        self.std_err = None
        self.idf = idf
        self.cancelled = False
        self.run_dir = Path("")
        self.exception = None
        self.name = "EnergyPlus_" + self.idf.name
        self.tmp = tmp

    def stop(self):
        if self.p.poll() is None:
            self.msg_callback("Attempting to cancel simulation ...")
            self.cancelled = True
            self.p.kill()

    def run(self):
        """Wrapper around the EnergyPlus command line interface.

        Adapted from :func:`eppy.runner.runfunctions.run`.
        """
        self.cancelled = False
        # get version from IDF object or by parsing the IDF file for it

        tmp = self.tmp
        self.epw = self.idf.epw.copy(tmp).expand()
        self.idfname = Path(self.idf.savecopy(tmp / self.idf.name)).expand()
        self.idd = self.idf.iddname.copy(tmp).expand()
        self.run_dir = Path(tmp).expand()
        self.include = [Path(file).copy(tmp) for file in self.idf.include]

        # build a list of command line arguments
        try:
            self.cmd = EnergyPlusExe(
                idfname=self.idfname,
                epw=self.epw,
                output_directory=self.run_dir,
                ep_version=self.idf.as_version,
                annual=self.idf.annual,
                convert=self.idf.convert,
                design_day=self.idf.design_day,
                help=False,
                idd=self.idd,
                epmacro=self.idf.epmacro,
                output_prefix=self.idf.output_prefix,
                readvars=self.idf.readvars,
                output_sufix=self.idf.output_suffix,
                version=False,
                expandobjects=self.idf.expandobjects,
            ).cmd()
        except EnergyPlusVersionError as e:
            self.exception = e
            self.p.kill()  # kill process to be sure
            return

        # Start process with tqdm bar
        with tqdm(
            unit_scale=True,
            total=self.idf.energyplus_its if self.idf.energyplus_its > 0 else None,
            miniters=1,
            desc=f"EnergyPlus #{self.idf.position}-{self.idf.name}"
            if self.idf.position
            else f"EnergyPlus {self.idf.name}",
            position=self.idf.position,
        ) as progress:
            self.p = subprocess.Popen(
                self.cmd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            start_time = time.time()
            self.msg_callback("Simulation started")
            self.idf._energyplus_its = 0  # reset counter
            for line in self.p.stdout:
                self.msg_callback(line.decode("utf-8").strip("\n"))
                self.idf._energyplus_its += 1
                progress.update()

            # We explicitly close stdout
            self.p.stdout.close()

            # Wait for process to complete
            self.p.wait()

            # Communicate callbacks
            if self.cancelled:
                self.msg_callback("Simulation cancelled")
                self.cancelled_callback(self.std_out, self.std_err)
            else:
                if self.p.returncode == 0:
                    self.msg_callback(
                        "EnergyPlus Completed in {:,.2f} seconds".format(
                            time.time() - start_time
                        )
                    )
                    self.success_callback()
                else:
                    self.msg_callback("Simulation failed")
                    self.failure_callback()

    def msg_callback(self, *args, **kwargs):
        log(*args, name=self.idf.name, **kwargs)

    def success_callback(self):
        save_dir = self.idf.simulation_dir
        if self.idf.keep_data:
            try:
                save_dir.rmtree_p()  # purge target dir
                self.run_dir.copytree(save_dir)  # copy files
            except PermissionError as e:
                pass
            else:
                log(
                    "Files generated at the end of the simulation: %s"
                    % "\n".join(save_dir.files()),
                    lg.DEBUG,
                    name=self.name,
                )

    def failure_callback(self):
        error_filename = self.run_dir / self.idf.output_prefix + "out.err"
        try:
            with open(error_filename, "r") as stderr:
                stderr_r = stderr.read()
            if self.idf.keep_data_err:
                failed_dir = self.idf.simulation_dir.mkdir_p() / "failed"
                try:
                    failed_dir.rmtree_p()
                except PermissionError as e:
                    log(f"Could not remove {failed_dir}")
                else:
                    self.run_dir.copytree(failed_dir)  # no need to create folder before
            self.exception = EnergyPlusProcessError(
                cmd=self.cmd, stderr=stderr_r, idf=self.idf
            )
        except FileNotFoundError:
            self.exception = CalledProcessError(
                self.p.returncode, cmd=self.cmd, stderr=self.p.stderr
            )

    def cancelled_callback(self, stdin, stdout):
        pass

    @property
    def eplus_home(self):
        eplus_exe, eplus_home = paths_from_version(self.idf.as_version.dash)
        if not Path(eplus_home).exists():
            raise EnergyPlusVersionError(
                msg=f"No EnergyPlus Executable found for version "
                f"{EnergyPlusVersion(self.idf.as_version)}"
            )
        else:
            return Path(eplus_home)
