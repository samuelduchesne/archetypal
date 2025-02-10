"""ExpandObjects module"""

import logging as lg
import shutil
import subprocess
import time
from io import StringIO
from subprocess import CalledProcessError
from threading import Thread

from packaging.version import Version
from path import Path
from tqdm.contrib.logging import tqdm_logging_redirect

from archetypal.eplus_interface.energy_plus import EnergyPlusProgram
from archetypal.utils import log


class ExpandObjectsExe(EnergyPlusProgram):
    """ExpandObject Wrapper"""

    def __init__(self, idf, tmp_dir):
        """Constructor."""
        super().__init__(idf)
        self.running_directory = tmp_dir

    @property
    def cmd(self):
        """Get the command line to run ExpandObjects."""
        return shutil.which("ExpandObjects", path=self.eplus_home)


class ExpandObjectsThread(Thread):
    """ExpandObjects program manager."""

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
        self.name = "ExpandObjects_" + self.idf.name
        self.tmp = tmp

    def run(self):
        """Wrapper around the ExpandObject command line interface."""

        # Move files into place
        self.epw = self.idf.epw.copy(self.run_dir / "in.epw").expand() if self.idf.epw else None
        self.idfname = Path(self.idf.savecopy(self.run_dir / "in.idf")).expand()
        self.idd = self.idf.iddname.copy(self.run_dir / "Energy+.idd").expand()

        # Run ExpandObjects Program
        self.p = subprocess.Popen(
            args=ExpandObjectsExe(self.idf, self.run_dir).cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            shell=False,  # can use shell
            cwd=self.run_dir,
        )
        start_time = time.time()
        self.msg_callback("Begin ExpandObjects")

        # Read stdout line by line
        loggers = [lg.getLogger("archetypal")]
        with tqdm_logging_redirect(desc=f"{self.p.args} {self.idf.name}", loggers=loggers) as pbar:
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
            self.msg_callback("ExpandObjects cancelled")
        else:
            if self.p.returncode == 0:
                self.msg_callback(f"ExpandObjects completed in {time.time() - start_time:,.2f} seconds")
                self.success_callback()
                for line in stderr_lines:
                    self.msg_callback(line, level=lg.ERROR)
            else:
                self.msg_callback("Transition failed")
                self.msg_callback("\n".join(stderr_lines), level=lg.ERROR)
                self.failure_callback()

    def msg_callback(self, *args, **kwargs):
        """Pass message to logger."""
        log(*args, **kwargs)

    def success_callback(self):
        """Replace idf with expanded.idf."""
        expanded_idf = self.run_dir / "expanded.idf"
        if expanded_idf.exists():
            self.idf.idfname = StringIO(expanded_idf.read_text())

        for filename in ["GHTIn.idf", "BasementGHTIn.idf"]:
            file_path = self.run_dir / filename
            if file_path.exists():
                dest_path = self.idf.output_directory.makedirs_p() / filename
                self.idf.include.append(file_path.copy(dest_path))

    def failure_callback(self):
        """Read stderr and pass to logger."""
        for line in self.p.stderr:
            self.msg_callback(line.decode("utf-8"), level=lg.ERROR)
        self.exception = CalledProcessError(self.p.returncode, cmd=self.cmd, stderr=self.p.stderr)

    def cancelled_callback(self, stdin, stdout):
        """Call on cancelled."""
        pass

    @property
    def eplus_home(self):
        """Get the version-dependant directory where executables are installed."""
        if self.idf.file_version <= Version("7.2"):
            install_dir = self.idf.file_version.current_install_dir / "bin"
        else:
            install_dir = self.idf.file_version.current_install_dir
        return install_dir

    def stop(self):
        self.msg_callback("Attempting to cancel simulation ...")
        self.cancelled = True
        self.p.terminate()
        self.cancelled_callback(self.std_out, self.std_err)
