"""Transition module."""

import logging as lg
import os
import platform
import re
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
from archetypal.eplus_interface.exceptions import (
    EnergyPlusProcessError,
    EnergyPlusVersionError,
)
from archetypal.eplus_interface.version import EnergyPlusVersion
from archetypal.utils import log


class TransitionExe(EnergyPlusProgram):
    """Transition Program Generator.

    Examples:
        >>> from archetypal import IDF
        >>> for transition in TransitionExe(IDF(), tmp_dir=os.getcwd()):
        >>>     print(transition.cmd())
    """

    def __init__(self, idf, tmp_dir):
        """Initialize Transition Executable."""
        super().__init__(idf)
        self.idf = idf
        self.trans = None  # Set by __next__()
        self.running_directory = tmp_dir

        self._trans_exec = None

    def __next__(self):
        """Return next transition."""
        self.trans = next(self.transitions_generator)
        return self

    def __iter__(self):
        """Iterate over transitions."""
        return self

    def get_exe_path(self):
        """Return the path containing the next transition."""
        if not self.trans_exec[self.trans].exists():
            raise EnergyPlusProcessError(
                cmd=self.trans_exec[self.trans],
                stderr="The specified EnergyPlus version (v{}) does not have"
                " the required transition program '{}' in the "
                "PreProcess folder. See the documentation "
                "(archetypal.readthedocs.io/troubleshooting.html#missing"
                "-transition-programs) "
                "to solve this issue".format(
                    self.idf.as_version, self.trans_exec[self.trans]
                ),
                idf=self.idf,
            )
        return self.trans_exec[self.trans]

    @property
    def idfname(self):
        """Copy and return self.idf to the output directory and expand."""
        return Path(self.idf.savecopy(self.running_directory / "in.idf")).expand()

    @property
    def trans_exec(self) -> dict:
        """Return dict of {EnergyPlusVersion: executable} for each transitions."""

        def copytree(src, dst, symlinks=False, ignore=None):
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(dst, item)
                try:
                    if os.path.isdir(s):
                        shutil.copytree(s, d, symlinks, ignore)
                    else:
                        shutil.copy2(s, d)
                except FileNotFoundError as e:
                    time.sleep(60)
                    log(f"{e}")

        if self._trans_exec is None:
            copytree(self.idf.idfversionupdater_dir, self.running_directory)
            self._trans_exec = {
                EnergyPlusVersion(
                    re.search(r"to-V(([\d])-([\d])-([\d]))", exec).group(1)
                ): exec
                for exec in self.running_directory.files("Transition-V*")
            }
        return self._trans_exec

    @property
    def transitions(self) -> list:
        """Return a sorted list of necessary transitions."""
        transitions = [
            key
            for key in self.trans_exec
            if self.idf.as_version >= key > self.idf.file_version
        ]
        transitions.sort()
        return transitions

    @property
    def transitions_generator(self):
        """Generate transitions."""
        for transition in self.transitions:
            yield transition

    def __str__(self):
        """Return string representation."""
        return " ".join(self.__repr__())

    def __repr__(self):
        """Return the command as a string."""
        return self.cmd()

    def cmd(self):
        """Get the platform-specific command."""
        _which = Path(shutil.which(self.get_exe_path()))
        if platform.system() == "Windows":
            cmd = [_which.relpath(), self.idfname.basename()]
        else:
            # must specify current dir on Unix
            cmd = ["./" + _which.basename(), self.idfname.basename()]
        return cmd


class TransitionThread(Thread):
    """Transition program manager."""

    def __init__(self, idf, tmp, overwrite=False):
        """Initialize Thread."""
        super(TransitionThread, self).__init__()
        self.overwrite = overwrite
        self.p = None
        self.std_out = None
        self.std_err = None
        self.idf = idf
        self.cancelled = False
        self.run_dir = Path("")
        self.exception = None
        self.name = "Transition_" + self.idf.name
        self.tmp = tmp
        self.idfname = None
        self.idd = None
        self.cmd = None

    def run(self):
        """Run.

        Wrapper around the EnergyPlus command line interface.
        """
        self.cancelled = False
        # get version from IDF object or by parsing the IDF file for it

        # Move files into place
        tmp = self.tmp
        self.idfname = Path(self.idf.savecopy(tmp / "in.idf")).expand()
        self.idd = self.idf.iddname.copy(tmp).expand()

        generator = TransitionExe(self.idf, tmp_dir=tmp)

        for trans in tqdm(
            generator,
            total=len(generator.transitions),
            unit_scale=True,
            miniters=1,
            position=self.idf.position,
            desc=f"Transition #{self.idf.position}-{self.idf.name}",
        ):
            # Get executable using shutil.which (determines the extension
            # based on the platform, eg: .exe. And copy the executable to tmp
            self.run_dir = Path(tmp).expand()

            # Run Transition Program
            self.cmd = trans.cmd()
            self.p = subprocess.Popen(
                self.cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                shell=False,  # cannot use shell
                cwd=self.run_dir,
            )
            start_time = time.time()
            self.msg_callback("Transition started")
            for line in self.p.stdout:
                self.msg_callback(line.decode("utf-8").strip("\n"))

            # We explicitly close stdout
            self.p.stdout.close()

            # Wait for process to complete
            self.p.wait()

            # Communicate callbacks
            if self.cancelled:
                self.msg_callback("Transition cancelled")
                # self.cancelled_callback(self.std_out, self.std_err)
            else:
                if self.p.returncode == 0:
                    self.msg_callback(
                        "Transition completed in {:,.2f} seconds".format(
                            time.time() - start_time
                        )
                    )
                    self.success_callback()
                    for line in self.p.stderr:
                        self.msg_callback(line.decode("utf-8"))
                else:
                    self.msg_callback("Transition failed")
                    self.failure_callback()

    @property
    def trans_exec(self) -> dict:
        """Return dict of {EnergyPlusVersion, executable} for each transitions."""
        return {
            EnergyPlusVersion(
                re.search(r"to-V(([\d])-([\d])-([\d]))", exec).group(1)
            ): exec
            for exec in self.idf.idfversionupdater_dir.files("Transition-V*")
        }

    @property
    def transitions(self):
        """Return a sorted list of necessary transitions."""
        transitions = [
            key
            for key in self.trans_exec
            if self.idf.as_version >= key > self.idf.file_version
        ]
        transitions.sort()
        return transitions

    def msg_callback(self, *args, **kwargs):
        """Pass message to logger."""
        log(*args, name=self.idf.name, **kwargs)

    def success_callback(self):
        """Retrieve the transitioned file.

        If self.overwrite is True, the transitioned file replaces the
        original file.
        """
        for f in Path(self.run_dir).files("*.idfnew"):
            if isinstance(self.idf.idfname, StringIO) or not self.overwrite:
                file = StringIO(f.read_text())
            else:
                file = f.copy(self.idf.idfname)

            # replace idfname with file
            try:
                self.idf.idfname = file
            except (NameError, UnboundLocalError):
                self.exception = EnergyPlusProcessError(
                    cmd="IDF.upgrade",
                    stderr="An error occurred during transitioning",
                    idf=self.idf,
                )
            else:
                self.idf._reset_dependant_vars("idfname")

    def failure_callback(self):
        """Read stderr and pass to logger."""
        for line in self.p.stderr:
            self.msg_callback(line.decode("utf-8"), level=lg.ERROR)
        raise CalledProcessError(self.p.returncode, cmd=self.cmd, stderr=self.p.stderr)

    def cancelled_callback(self, stdin, stdout):
        """Call on cancelled."""
        pass

    @property
    def eplus_home(self):
        """Return the location of the EnergyPlus directory."""
        eplus_exe, eplus_home = paths_from_version(self.idf.as_version.dash)
        if not Path(eplus_home).exists():
            raise EnergyPlusVersionError(
                msg=f"No EnergyPlus Executable found for version "
                f"{EnergyPlusVersion(self.idf.as_version)}"
            )
        else:
            return Path(eplus_home)
