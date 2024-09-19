"""Slab module"""

import logging as lg
import shutil
import subprocess
import time
from threading import Thread

from packaging.version import Version
from path import Path
from tqdm.auto import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from archetypal.utils import log

from ..eplus_interface.exceptions import EnergyPlusProcessError


class BasementThread(Thread):
    """Basement program manager.

    The basement program used to calculate the results is included with the
    EnergyPlus distribution. It requires an input file named GHTin.idf in
    input data file format. The needed corresponding idd file is
    SlabGHT.idd. An EnergyPlus weather file for the location is also needed.
    """

    def __init__(self, idf, tmp):
        """Constructor."""
        super(BasementThread, self).__init__()
        self.p = None
        self.std_out = None
        self.std_err = None
        self.idf = idf
        self.cancelled = False
        self.run_dir = Path(tmp).expand()
        self.exception = None
        self.name = "RunBasement_" + self.idf.name
        self.include = None

    @property
    def cmd(self):
        """Get the command."""
        cmd_path = Path(shutil.which("Basement", path=self.run_dir))
        return [cmd_path]

    def run(self):
        """Wrapper around the Basement command line interface."""

        # Move files into place
        self.epw = self.idf.epw.copy(self.run_dir / "in.epw").expand()
        self.idfname = Path(self.idf.savecopy(self.run_dir / "in.idf")).expand()
        self.idd = self.idf.iddname.copy(self.run_dir).expand()

        # Get executable using shutil.which
        basemenet_exe = shutil.which("Basement", path=self.eplus_home)
        if basemenet_exe is None:
            log(
                f"The Basement program could not be found at '{self.eplus_home}'",
                lg.WARNING,
            )
            return
        else:
            basemenet_exe = (self.eplus_home / Path(basemenet_exe)).expand()
        self.basement_exe = Path(basemenet_exe).copy(self.run_dir)
        self.basement_idd = (self.eplus_home / "BasementGHT.idd").copy(self.run_dir)
        self.outfile = self.idf.name

        # The BasementGHTin.idf file is copied from the self.include list
        self.include = [Path(file).copy(self.run_dir) for file in self.idf.include]
        if "BasementGHTIn.idf" not in self.include:
            self.cleanup_callback()
            return

        self.msg_callback("===== (Run Basement Temperature Generation) ===== Start =====")
        self.msg_callback("Running Basement.exe")
        self.msg_callback(f"Input File  : {self.idfname}")
        self.msg_callback(
            f"Output Files: {self.outfile}_bsmt.csv " f"{self.outfile}_bsmt.audit {self.outfile}_bsmt.out"
        )
        self.msg_callback(f"Weather File: {self.epw}")

        # Run Slab Program
        with logging_redirect_tqdm(loggers=[lg.getLogger("archetypal")]):
            with tqdm(
                unit_scale=True,
                miniters=1,
                desc=f"RunBasement #{self.idf.position}-{self.idf.name}",
                position=self.idf.position,
            ) as progress:
                self.p = subprocess.Popen(
                    self.cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=True,  # can use shell
                    cwd=self.run_dir,
                )
                start_time = time.time()
                self.msg_callback("Begin Basement Temperature Calculation processing . . .")

                # Read stdout line by line
                for line in iter(self.p.stdout.readline, b""):
                    decoded_line = line.decode("utf-8").strip()
                    self.msg_callback(decoded_line)
                    progress.update()

                # Process stderr after stdout is fully read
                stderr = self.p.stderr.read()
                stderr_lines = stderr.decode("utf-8").splitlines()

                # We explicitly close stdout
                self.p.stdout.close()

                # Wait for process to complete
                self.p.wait()

                # Communicate callbacks
                if self.cancelled:
                    self.msg_callback("Basement cancelled")
                else:
                    if self.p.returncode == 0:
                        self.msg_callback(f"Basement completed in {time.time() - start_time:,.2f} seconds")
                        self.success_callback()
                        for line in stderr_lines:
                            self.msg_callback(line)
                    else:
                        self.msg_callback("Basement failed")
                        self.msg_callback("\n".join(stderr_lines), level=lg.ERROR)
                        self.failure_callback()

    def msg_callback(self, *args, **kwargs):
        """Pass message to logger."""
        log(*args, name=self.idf.name, **kwargs)

    def success_callback(self):
        """Parse surface temperature and append to IDF file."""
        csv_ = self.run_dir / "MonthlyResults.csv"
        if csv_.exists():
            csv_ = csv_.rename(self.idf.output_directory / f"{self.outfile}_bsmt.csv")

        input_ = self.run_dir / "RunINPUT.TXT"
        if input_.exists():
            input_ = input_.rename(self.idf.output_directory / f"{self.outfile}_bsmt.out")

        debug_ = self.run_dir / "RunDEBUGOUT.txt"
        if debug_.exists():
            debug_ = debug_.rename(self.idf.output_directory / "basementout.audit")

        err_ = self.run_dir / "eplusout.err"
        if err_.exists():
            with open(err_) as f:
                with open(debug_, "a") as f1:
                    for line in f:
                        f1.write(line)

        audit_ = self.run_dir / "audit.out"
        if audit_.exists():
            with open(audit_) as f:
                with open(debug_, "a") as f1:
                    for line in f:
                        f1.write(line)

        ep_objects = self.run_dir / "EPObjects.txt"
        if ep_objects.exists():
            with open(self.idf.idfname, "a") as outfile:
                with open(ep_objects) as infile:
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
        ghtin = self.idf.output_directory / "BasementGHTIn.idf"
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
            with open(error_filename) as stderr:
                stderr_r = stderr.read()
                self.exception = EnergyPlusProcessError(cmd=self.cmd, stderr=stderr_r, idf=self.idf)
        self.cleanup_callback()

    def cancelled_callback(self, stdin, stdout):
        """Call on cancelled."""
        self.cleanup_callback()

    @property
    def eplus_home(self):
        """Get the version-dependant directory where executables are installed."""
        if self.idf.file_version <= Version("7.2"):
            install_dir = self.idf.file_version.current_install_dir / "bin"
        else:
            install_dir = self.idf.file_version.current_install_dir / "PreProcess" / "GrndTempCalc"
        return install_dir.expand()

    def stop(self):
        if self.p.poll() is None:
            self.msg_callback("Attempting to cancel simulation ...")
            self.cancelled = True
            self.p.kill()
            self.cancelled_callback(self.std_out, self.std_err)
