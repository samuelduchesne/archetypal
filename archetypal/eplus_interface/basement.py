"""Slab module"""

import logging as lg
import shutil
import subprocess
import time
from io import StringIO
from threading import Thread

from packaging.version import Version
from path import Path
from tqdm.contrib.logging import tqdm_logging_redirect

from ..eplus_interface.exceptions import EnergyPlusProcessError
from ..utils import log


class BasementThread(Thread):
    """Basement program manager.

    The basement program used to calculate the results is included with the
    EnergyPlus distribution. It requires an input file named GHTin.idf in
    input data file format. The needed corresponding idd file is
    SlabGHT.idd. An EnergyPlus weather file for the location is also needed.
    """

    def __init__(self, idf, tmp):
        """Constructor."""
        super().__init__()
        self.p: subprocess.Popen
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
        return [str(cmd_path.name)]

    def run(self):
        """Wrapper around the Basement command line interface."""

        # Move files into place
        self.epw = self.idf.epw.copy(self.run_dir / "in.epw").expand()
        self.idfname = Path(self.idf.savecopy(self.run_dir / "in.idf")).expand()
        self.idd = self.idf.iddname.copy(self.run_dir).expand()

        # Get executable using shutil.which
        basement_exe = shutil.which("Basement", path=self.eplus_home)
        self.basement_exe = Path(basement_exe).copy(self.run_dir)
        self.basement_idd = (self.eplus_home / "BasementGHT.idd").copy(self.run_dir)
        self.outfile = self.idf.name

        # The BasementGHTin.idf file is copied from the self.include list
        self.include = [Path(file).copy(self.run_dir) for file in self.idf.include]
        if "BasementGHTIn.idf" not in [p.basename() for p in self.include]:
            self.cleanup_callback()
            return

        # Run Basement Program
        self.p = subprocess.Popen(
            self.cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,  # can use shell
            cwd=self.run_dir,
        )
        start_time = time.time()
        self.msg_callback("Begin Basement Temperature Calculation processing . . .")

        # Read stdout line by line
        loggers = [lg.getLogger("archetypal")]
        with tqdm_logging_redirect(desc=f"{basement_exe} {self.idf.name}", loggers=loggers) as pbar:
            for line in iter(self.p.stdout.readline, b""):
                decoded_line = line.decode("utf-8").strip()
                self.msg_callback(decoded_line)
                pbar.update()

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
                    self.msg_callback(line, level=lg.ERROR)
            else:
                self.msg_callback("Basement failed")
                self.msg_callback("\n".join(stderr_lines), level=lg.ERROR)
                self.failure_callback()

    def msg_callback(self, *args, **kwargs):
        """Pass message to logger."""
        log(*args, **kwargs)

    def success_callback(self):
        """Parse surface temperature and append to IDF file."""
        for ep_objects in self.run_dir.glob("EPObjects*"):
            if ep_objects.exists():
                with open(ep_objects) as f:
                    basement_models = self.idf.__class__(
                        StringIO(f.read()),
                        file_version=self.idf.file_version,
                        as_version=self.idf.as_version,
                        prep_outputs=False,
                    )
                # Loop on all objects and using self.newidfobject
                added_objects = []
                for sequence in basement_models.idfobjects.values():
                    for obj in sequence:
                        data = obj.to_dict()
                        key = data.pop("key")
                        added_objects.append(self.idf.newidfobject(key=key.upper(), **data))
                del basement_models  # remove loaded_string model
            else:
                self.msg_callback("No EPObjects file found", level=lg.WARNING)
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
                self.msg_callback("nothing to remove", lg.DEBUG)

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
        self.msg_callback("Attempting to cancel Basement...")
        self.p.terminate()
        self.cancelled = True
        self.cancelled_callback(self.std_out, self.std_err)
