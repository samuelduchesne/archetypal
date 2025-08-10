import logging as lg
import subprocess
import time
from pathlib import Path
from subprocess import CalledProcessError
from threading import Thread

import eppy
from eppy.runner.run_functions import paths_from_version
from packaging.version import Version
from tqdm.auto import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

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
        """Get the version-dependant directory where executables are installed."""
        if self.idf.file_version <= Version("7.2"):
            install_dir = self.idf.file_version.current_install_dir / "bin"
        else:
            install_dir = self.idf.file_version.current_install_dir
        return install_dir


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
        help=False,  # noqa: A002
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
        # Short option flags map to EnergyPlus CLI switches
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
        # Prefer internal object expansion; always enable -x for robustness.
        # Keep the expandobjects parameter for API compatibility, but ignore it
        # in favor of using EnergyPlus's internal preprocessor via -x.
        self.x = True

        self.idfname = idfname
        self.ep_version = ep_version

        self.get_exe_path()

    def get_exe_path(self):
        (eplus_exe_path, eplus_weather_path) = eppy.runner.run_functions.install_paths(self.ep_version.dash, self.i)
        if not Path(eplus_exe_path).exists():
            raise EnergyPlusVersionError(
                msg=f"No EnergyPlus Executable found for version {EnergyPlusVersion(self.ep_version)}"
            )
        self.eplus_exe_path = Path(eplus_exe_path).expand()
        self.eplus_weather_path = Path(eplus_weather_path).expand()

    def __str__(self):
        """Return string representation."""
        return " ".join(self.__repr__())

    def __repr__(self):
        """Return a representation of self."""
        cmd = [str(self.eplus_exe_path)]
        for key, value in self.__dict__.items():
            if key not in [
                "idfname",
                "ep_version",
                "eplus_exe_path",
                "eplus_weather_path",
            ]:
                if isinstance(value, bool):
                    if value:
                        cmd.append(f"-{key}")
                else:
                    if value is not None:
                        cmd.extend([f"-{key}", str(value)])
        cmd.append(str(self.idfname))
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
        super().__init__()
        self.p: subprocess.Popen = None
        self.std_out = None
        self.std_err = None
        self.idf = idf
        self.cancelled = False
        self.run_dir = Path("")
        self.exception = None
        self.name = "EnergyPlus_" + self.idf.name
        self.tmp = tmp

    def stop(self):
        self.msg_callback("Attempting to cancel simulation ...")
        self.cancelled = True
        self.p.kill()
        self.cancelled_callback(self.std_out, self.std_err)

    def run(self):
        """Wrapper around the EnergyPlus command line interface.

        Adapted from :func:`eppy.runner.runfunctions.run`.
        """
        # get version from IDF object or by parsing the IDF file for it
        tmp = self.tmp
        self.epw = Path(self.idf.epw.copy(tmp)).expand()
        self.idfname = Path(self.idf.savecopy(tmp / self.idf.name)).expand()
        # Let EnergyPlus use the default IDD from the installation; passing a copied
        # IDD via -i has been observed to cause instability on some systems.
        self.idd = None
        self.run_dir = Path(tmp).expand()
        self.include = [Path(file).copy(tmp) for file in self.idf.include]

        # build a list of command line arguments
        try:
            eplus_exe = EnergyPlusExe(
                idfname=self.idfname,
                epw=self.epw,
                output_directory=self.run_dir,
                ep_version=self.idf.file_version,
                annual=self.idf.annual,
                convert=self.idf.convert,
                design_day=self.idf.design_day,
                help=False,
                idd=self.idd,  # None => use default EnergyPlus IDD
                epmacro=self.idf.epmacro,
                output_prefix=self.idf.output_prefix,
                readvars=self.idf.readvars,
                output_sufix=self.idf.output_suffix,
                version=False,
                expandobjects=self.idf.expandobjects,
            )
            self.cmd = eplus_exe.cmd()
        except EnergyPlusVersionError as e:
            self.exception = e
            if self.p:
                self.p.terminate()  # terminate process to be sure
            return
        with (
            logging_redirect_tqdm(loggers=[lg.getLogger("archetypal")]),
            tqdm(
                unit_scale=False,
                total=self.idf.energyplus_its if self.idf.energyplus_its > 0 else None,
                miniters=1,
                desc=(
                    f"{eplus_exe.eplus_exe_path} #{self.idf.position}-{self.idf.name}"
                    if self.idf.position
                    else f"{eplus_exe.eplus_exe_path} {self.idf.name}"
                ),
                position=self.idf.position,
            ) as progress,
        ):
            # Start process with tqdm bar
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
                    self.msg_callback(f"EnergyPlus Completed in {time.time() - start_time:,.2f} seconds")
                    self.success_callback()
                else:
                    self.msg_callback("Simulation failed")
                    self.failure_callback()

    def msg_callback(self, *args, **kwargs):
        msg, *_ = args
        for m in msg.split("\r"):
            if m:
                log(m, name=self.idf.name, **kwargs)

    def success_callback(self):
        save_dir = self.idf.simulation_dir
        if self.idf.keep_data:
            try:
                save_dir.rmtree_p()  # purge target dir
                self.run_dir.copytree(save_dir)  # copy files
            except PermissionError:
                pass
            else:
                log(
                    "Files generated at the end of the simulation: {}".format(
                        "\n".join(str(p) for p in save_dir.files())
                    ),
                    lg.DEBUG,
                    name=self.name,
                )

    def failure_callback(self):
        error_filename = self.run_dir / f"{self.idf.output_prefix}out.err"
        try:
            with open(error_filename) as stderr:
                stderr_r = stderr.read()
            if self.idf.keep_data_err:
                failed_dir = self.idf.simulation_dir.mkdir_p()
                try:
                    failed_dir.rmtree_p()
                except PermissionError:
                    log(f"Could not remove {failed_dir}")
                else:
                    self.run_dir.copytree(failed_dir)  # no need to create folder before
            self.exception = EnergyPlusProcessError(cmd=self.cmd, stderr=stderr_r, idf=self.idf)
        except FileNotFoundError:
            self.exception = CalledProcessError(self.p.returncode, cmd=self.cmd, stderr=self.p.stderr)

    def cancelled_callback(self, stdin, stdout):
        pass

    @property
    def eplus_home(self):
        eplus_exe, eplus_home = paths_from_version(self.idf.as_version.dash)
        if not Path(eplus_home).exists():
            raise EnergyPlusVersionError(
                msg=f"No EnergyPlus Executable found for version {EnergyPlusVersion(self.idf.as_version)}"
            )
        else:
            return Path(eplus_home)
