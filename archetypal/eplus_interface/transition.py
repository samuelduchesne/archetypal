import os
import re
import shutil
import subprocess
import time
from subprocess import CalledProcessError
from threading import Thread
import logging as lg

from eppy.runner.run_functions import paths_from_version
from path import Path
from tqdm import tqdm

from archetypal.eplus_interface.exceptions import (
    EnergyPlusProcessError,
    EnergyPlusVersionError,
)
from archetypal.eplus_interface.version import EnergyPlusVersion
from archetypal.utils import log


class TransitionExe:
    """Transition Program Generator.

    Examples:
        >>> for transition in TransitionExe(IDF(), tmp_dir=os.getcwd()):
        >>>     print(transition.cmd())
    """

    def __init__(self, idf, tmp_dir):
        """
        Args:
            idf (IDF): The idf filename
        """
        self.idf = idf
        self.trans = None  # Set by __next__()
        self.running_directory = tmp_dir

        self._trans_exec = None

    def __next__(self):
        self.trans = next(self.transitions)
        return self

    def __iter__(self):
        return self

    def get_exe_path(self):
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
        """Copies self.idf to the output directory"""
        return Path(self.idf.idfname.copy(self.running_directory)).abspath()

    @property
    def trans_exec(self):
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
    def transitions(self):
        transitions = [
            key
            for key in self.trans_exec
            if self.idf.as_version >= key > self.idf.idf_version
        ]
        transitions.sort()
        for transition in transitions:
            yield transition

    def __str__(self):
        return " ".join(self.__repr__())

    def __repr__(self):
        _which = Path(shutil.which(self.get_exe_path()))
        cmd = ["./" + _which.basename(), self.idfname.basename()]
        return cmd

    def cmd(self):
        return self.__repr__()


class TransitionThread(Thread):
    def __init__(self, idf, tmp, overwrite=False):
        """

        Args:
            idf (IDF):
        """
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

    def run(self):
        """Wrapper around the EnergyPlus command line interface.

        Adapted from :func:`eppy.runner.runfunctions.run`.
        """
        self.cancelled = False
        # get version from IDF object or by parsing the IDF file for it

        tmp = self.tmp
        self.idfname = Path(self.idf.idfname.copy(tmp)).expand()
        self.idd = self.idf.iddname.copy(tmp).expand()

        for trans in tqdm(
            TransitionExe(self.idf, tmp_dir=tmp),
            position=self.idf.position,
            desc=f"Transition #{self.idf.position}-{self.idf.name}",
        ):
            # Get executable using shutil.which (determines the extension
            # based on the platform, eg: .exe. And copy the executable to tmp
            self.run_dir = Path(tmp).expand()
            self.transitionexe = trans

            # Run Transition Program
            self.cmd = self.transitionexe.cmd()
            self.p = subprocess.Popen(
                self.cmd,
                cwd=self.run_dir,
                shell=False,  # cannot use shell
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
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
    def trans_exec(self):
        return {
            EnergyPlusVersion(
                re.search(r"to-V(([\d])-([\d])-([\d]))", exec).group(1)
            ): exec
            for exec in self.idf.idfversionupdater_dir.files("Transition-V*")
        }

    @property
    def transitions(self):
        transitions = [
            key
            for key in self.trans_exec
            if self.idf.as_version >= key > self.idf.idf_version
        ]
        transitions.sort()
        return transitions

    def msg_callback(self, *args, **kwargs):
        log(*args, **kwargs)

    def success_callback(self):
        # retrieve transitioned file
        for f in Path(self.run_dir).files("*.idfnew"):
            if self.overwrite:
                file = f.copy(self.idf.output_directory / self.idf.name)
            else:
                file = f.copy(self.idf.output_directory)
            try:
                self.idf.idfname = file
            except (NameError, UnboundLocalError):
                raise EnergyPlusProcessError(
                    cmd="IDF.upgrade",
                    stderr=f"An error occurred during transitioning",
                    idf=self.idf,
                )
            else:
                self.idf._reset_dependant_vars("idfname")

    def failure_callback(self):
        for line in self.p.stderr:
            self.msg_callback(line.decode("utf-8"), level=lg.ERROR)
        raise CalledProcessError(self.p.returncode, cmd=self.cmd, stderr=self.p.stderr)

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
