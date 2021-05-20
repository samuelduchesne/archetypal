"""Slab module"""

import logging as lg
import shutil
import subprocess
import time
from threading import Thread

from eppy.runner.run_functions import paths_from_version
from path import Path
from tqdm import tqdm

from archetypal.eplus_interface.exceptions import (
    EnergyPlusProcessError,
    EnergyPlusVersionError,
)
from archetypal.eplus_interface.version import EnergyPlusVersion
from archetypal.utils import log


class SlabThread(Thread):
    """Slab program manager.

    The slab program used to calculate the results is included with the
    EnergyPlus distribution. It requires an input file named GHTin.idf in
    input data file format. The needed corresponding idd file is
    SlabGHT.idd. An EnergyPlus weather file for the location is also needed.
    """

    def __init__(self, idf, tmp):
        """Constructor."""
        super(SlabThread, self).__init__()
        self.p = None
        self.std_out = None
        self.std_err = None
        self.idf = idf
        self.cancelled = False
        self.run_dir = Path(tmp).expand()
        self.exception = None
        self.name = "RunSlab_" + self.idf.name
        self.include = None

    @property
    def cmd(self):
        """Get the command."""
        cmd_path = Path(shutil.which("Slab", path=self.run_dir))
        return [cmd_path.relpath(self.run_dir)]

    def run(self):
        """Wrapper around the EnergyPlus command line interface."""
        self.cancelled = False
        # get version from IDF object or by parsing the IDF file for it

        # Move files into place
        self.epw = self.idf.epw.copy(self.run_dir / "in.epw").expand()
        self.idfname = Path(self.idf.savecopy(self.run_dir / "in.idf")).expand()
        self.idd = self.idf.iddname.copy(self.run_dir).expand()

        # Get executable using shutil.which (determines the extension based on
        # the platform, eg: .exe. And copy the executable to tmp
        self.slabexe = Path(
            shutil.which("Slab", path=self.eplus_home / "PreProcess" / "GrndTempCalc")
        ).copy(self.run_dir)
        self.slabidd = (
            self.eplus_home / "PreProcess" / "GrndTempCalc" / "SlabGHT.idd"
        ).copy(self.run_dir)

        # The GHTin.idf file is copied from the self.include list (added by
        # ExpandObjects. If self.include is empty, no need to run Slab.
        self.include = [Path(file).copy(self.run_dir) for file in self.idf.include]
        if not self.include:
            self.cleanup_callback()
            return

        # Run Slab Program
        with tqdm(
            unit_scale=True,
            miniters=1,
            desc=f"RunSlab #{self.idf.position}-{self.idf.name}",
            position=self.idf.position,
        ) as progress:

            self.p = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=True,  # can use shell
                cwd=self.run_dir.abspath(),
            )
            start_time = time.time()
            self.msg_callback("Begin Slab Temperature Calculation processing . . .")
            for line in self.p.stdout:
                self.msg_callback(line.decode("utf-8").strip("\n"))
                progress.update()

            # We explicitly close stdout
            self.p.stdout.close()

            # Wait for process to complete
            self.p.wait()

            # Communicate callbacks
            if self.cancelled:
                self.msg_callback("RunSlab cancelled")
                # self.cancelled_callback(self.std_out, self.std_err)
            else:
                if self.p.returncode == 0:
                    self.msg_callback(
                        "RunSlab completed in {:,.2f} seconds".format(
                            time.time() - start_time
                        )
                    )
                    self.success_callback()
                    for line in self.p.stderr:
                        self.msg_callback(line.decode("utf-8"))
                else:
                    self.msg_callback("RunSlab failed")
                    self.failure_callback()

    def msg_callback(self, *args, **kwargs):
        """Pass message to logger."""
        log(*args, name=self.idf.name, **kwargs)

    def success_callback(self):
        """Parse surface temperature and append to IDF file."""
        temp_schedule = self.run_dir / "SLABSurfaceTemps.txt"
        if temp_schedule.exists():
            with open(self.idf.idfname, "a") as outfile:
                with open(temp_schedule) as infile:
                    next(infile)  # Skipping first line
                    next(infile)  # Skipping second line
                    for line in infile:
                        outfile.write(line)
            # invalidate attributes dependant on idfname, since it has changed
            self.idf._reset_dependant_vars("idfname")
        self.cleanup_callback()

    def cleanup_callback(self):
        """clean up temp files, directories and variables that need cleanup."""

        # Remove from include
        ghtin = self.idf.output_directory / "GHTIn.idf"
        if ghtin.exists():
            try:
                self.idf.include.remove(ghtin)
                ghtin.remove()
            except ValueError:
                log("nothing to remove", lg.DEBUG)

    def failure_callback(self):
        """Parse error file and log"""
        error_filename = self.run_dir / "eplusout.err"
        if error_filename.exists():
            with open(error_filename, "r") as stderr:
                stderr_r = stderr.read()
                self.exception = EnergyPlusProcessError(
                    cmd=self.cmd, stderr=stderr_r, idf=self.idf
                )
        self.cleanup_callback()

    def cancelled_callback(self, stdin, stdout):
        """Call on cancelled."""
        self.cleanup_callback()

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
