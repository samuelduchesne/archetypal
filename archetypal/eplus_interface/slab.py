"""Slab module"""

import logging as lg
import shutil
import subprocess
import time
from io import StringIO
from threading import Thread

from packaging.version import Version
from path import Path
from tqdm.auto import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

from archetypal.eplus_interface.exceptions import EnergyPlusProcessError
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
        # if platform is windows
        return [self.slabexe]

    def run(self):
        """Wrapper around the Slab command line interface."""
        self.cancelled = False

        # Move files into place
        self.epw = self.idf.epw.copy(self.run_dir / "in.epw").expand()
        self.idfname = Path(self.idf.savecopy(self.run_dir / "in.idf")).expand()
        self.idd = self.idf.iddname.copy(self.run_dir).expand()

        # Get executable using shutil.which
        slab_exe = shutil.which("Slab", path=self.eplus_home)
        if slab_exe is None:
            log(
                f"The Slab program could not be found at '{self.eplus_home}'",
                lg.WARNING,
            )
            return
        else:
            slab_exe = (self.eplus_home / slab_exe).expand()
        self.slabexe = slab_exe
        self.slabidd = (self.eplus_home / "SlabGHT.idd").copy(self.run_dir)
        self.outfile = self.idf.name

        # The GHTin.idf file is copied from the self.include list
        self.include = [Path(file).copy(self.run_dir) for file in self.idf.include]
        if not self.include:
            self.cleanup_callback()
            return

        # Run Slab Program
        with logging_redirect_tqdm(loggers=[lg.getLogger("archetypal")]):
            with tqdm(
                unit_scale=True,
                miniters=1,
                desc=f"{self.slabexe} #{self.idf.position}-{self.idf.name}",
                position=self.idf.position,
            ) as progress:
                self.p = subprocess.Popen(
                    self.cmd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    shell=False,
                    cwd=self.run_dir,
                )
                start_time = time.time()
                self.msg_callback("Begin Slab Temperature Calculation processing . . .")

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
                    self.msg_callback("Slab cancelled")
                else:
                    if self.p.returncode == 0:
                        self.msg_callback(f"Slab completed in {time.time() - start_time:,.2f} seconds")
                        self.success_callback()
                        for line in stderr_lines:
                            self.msg_callback(line)
                    else:
                        self.msg_callback("Slab failed", level=lg.ERROR)
                        self.msg_callback("\n".join(stderr_lines), level=lg.ERROR)
                        self.failure_callback()

    def msg_callback(self, *args, **kwargs):
        """Pass message to logger."""
        log(*args, name=self.idf.name, **kwargs)

    def success_callback(self):
        """Parse surface temperature and append to IDF file."""
        for temp_schedule in self.run_dir.glob("SLABSurfaceTemps*"):
            if temp_schedule.exists():
                slab_models = self.idf.__class__(
                    StringIO(open(temp_schedule).read()),
                    file_version=self.idf.file_version,
                    as_version=self.idf.as_version,
                    prep_outputs=False,
                )
                # Loop on all objects and using self.newidfobject
                added_objects = []
                for sequence in slab_models.idfobjects.values():
                    if sequence:
                        for obj in sequence:
                            data = obj.to_dict()
                            key = data.pop("key")
                            added_objects.append(self.idf.newidfobject(key=key.upper(), **data))
                del slab_models  # remove loaded_string model
            else:
                self.msg_callback("No SLABSurfaceTemps.txt file found.", level=lg.ERROR)
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
