from packaging.version import InvalidVersion
from tabulate import tabulate


class EnergyPlusProcessError(Exception):
    """EnergyPlus Process call error"""

    def __init__(self, cmd=None, stderr=None, idf=None):
        """
        Args:
            cmd:
            stderr:
            idf:
        """
        self.cmd = cmd
        self.idf = idf
        self.stderr = stderr
        super().__init__(self.stderr)

    def __str__(self):
        """Override that only returns the stderr"""
        try:
            name = self.idf.idfname.abspath()
        except Exception:
            name = self.idf.name
        msg = ":\n".join([name, self.stderr])
        return msg

    def write(self):
        # create and add headers
        invalid = [{"Filename": self.idf, "Error": self.stderr}]
        return tabulate(invalid, headers="keys")


class EnergyPlusVersionError(Exception):
    """EnergyPlus Version call error"""

    def __init__(self, msg=None, idf_file=None, idf_version=None, ep_version=None):
        super(EnergyPlusVersionError, self).__init__(None)
        self.msg = msg
        self.idf_file = idf_file
        self.idf_version = idf_version
        self.ep_version = ep_version

    def __str__(self):
        """Override that only returns the stderr"""
        if not self.msg:
            if self.idf_version > self.ep_version:
                compares_ = "higher"
                self.msg = (
                    f"The version of {self.idf_file.basename()} (v{self.idf_version}) "
                    f"is {compares_} than the specified EnergyPlus version "
                    f"(v{self.ep_version}). This file looks like it has already been "
                    f"transitioned to a newer version"
                )
            else:
                compares_ = "lower"
                self.msg = (
                    f"The version of {self.idf_file.basename()} (v{self.idf_version}) "
                    f"is {compares_} than the specified EnergyPlus version "
                    f"(v{self.ep_version})"
                )

        return self.msg


class EnergyPlusWeatherError(Exception):
    """Error for when weather file is not defined"""

    pass


class InvalidEnergyPlusVersion(InvalidVersion):
    """
    An invalid version was found, users should refer to EnergyPlus Documentation.
    """
