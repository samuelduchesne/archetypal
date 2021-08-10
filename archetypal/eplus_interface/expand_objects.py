"""ExpandObjects module"""

import logging as lg
import shutil
import subprocess
import time
from io import StringIO
from subprocess import CalledProcessError
from threading import Thread

from eppy.runner.run_functions import paths_from_version
from path import Path
from tqdm import tqdm

from archetypal.eplus_interface.energy_plus import EnergyPlusProgram
from archetypal.eplus_interface.exceptions import EnergyPlusVersionError
from archetypal.eplus_interface.version import EnergyPlusVersion
from archetypal.utils import log


class ExpandObjectsExe(EnergyPlusProgram):
    """ExpandObject Wrapper"""

    def __init__(self, idf):
        """Constructor."""
        super().__init__(idf)

    @property
    def cmd(self):
        """Get the command."""
        return ["ExpandObjects"]


class ExpandObjectsThread(Thread):
    """ExpandObjects program manager."""

    def __init__(self, idf, tmp):
        """Constructor."""
        super(ExpandObjectsThread, self).__init__()
        self.p = None
        self.std_out = None
        self.std_err = None
        self.idf = idf
        self.cancelled = False
        self.run_dir = Path("")
        self.exception = None
        self.name = "ExpandObjects_" + self.idf.name
        self.tmp = tmp
        self.cmd = None

    def run(self):
        """Wrapper around the EnergyPlus command line interface."""
        try:
            self.cancelled = False
            # get version from IDF object or by parsing the IDF file for it

            # Move files into place
            tmp = self.tmp
            self.epw = self.idf.epw.copy(tmp / "in.epw").expand()
            self.idfname = Path(self.idf.savecopy(tmp / "in.idf")).expand()
            self.idd = self.idf.iddname.copy(tmp / "Energy+.idd").expand()
            self.expandobjectsexe = Path(
                shutil.which("ExpandObjects", path=self.eplus_home.expand())
            ).copy2(tmp)
            self.run_dir = Path(tmp).expand()

            # Run ExpandObjects Program
            self.cmd = ExpandObjectsExe(self.idf).cmd
            with tqdm(
                unit_scale=True,
                miniters=1,
                desc=f"ExpandObjects #{self.idf.position}-{self.idf.name}",
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
                # self.msg_callback("ExpandObjects started")
                for line in self.p.stdout:
                    self.msg_callback(line.decode("utf-8"))
                    progress.update()

                # We explicitly close stdout
                self.p.stdout.close()

                # Wait for process to complete
                self.p.wait()

                # Communicate callbacks
                if self.cancelled:
                    self.msg_callback("ExpandObjects cancelled")
                    # self.cancelled_callback(self.std_out, self.std_err)
                else:
                    if self.p.returncode == 0:
                        self.msg_callback(
                            f"ExpandObjects completed in "
                            f"{time.time() - start_time:,.2f} seconds"
                        )
                        self.success_callback()
                    else:
                        self.failure_callback()
        except Exception as e:
            self.exception = e
            if self.p is not None:
                self.p.kill()  # kill process to be sure
            return

    def msg_callback(self, *args, **kwargs):
        """Pass message to logger."""
        log(*args, name=self.idf.name, **kwargs)

    def success_callback(self):
        """Replace idf with expanded.idf."""
        if (self.run_dir / "expanded.idf").exists():
            if isinstance(self.idf.idfname, StringIO):
                file = StringIO((self.run_dir / "expanded.idf").read_text())
            else:
                file = (self.run_dir / "expanded.idf").copy(self.idf.idfname)
            self.idf.idfname = file
        if (Path(self.run_dir) / "GHTIn.idf").exists():
            self.idf.include.append(
                (Path(self.run_dir) / "GHTIn.idf").copy(
                    self.idf.output_directory.makedirs_p() / "GHTIn.idf"
                )
            )

        if (Path(self.run_dir) / "BasementGHTIn.idf").exists():
            self.idf.include.append(
                (Path(self.run_dir) / "BasementGHTIn.idf").copy(
                    self.idf.output_directory.makedirs_p() / "BasementGHTIn.idf"
                )
            )

    def failure_callback(self):
        """Read stderr and pass to logger."""
        for line in self.p.stderr:
            self.msg_callback(line.decode("utf-8"), level=lg.ERROR)
        self.exception = CalledProcessError(
            self.p.returncode, cmd=self.cmd, stderr=self.p.stderr
        )

    def cancelled_callback(self, stdin, stdout):
        """Call on cancelled."""
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
