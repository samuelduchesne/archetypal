import platform
import re
import warnings
from itertools import chain

from packaging.version import Version
from path import Path

from archetypal import settings
from archetypal.eplus_interface.exceptions import InvalidEnergyPlusVersion
from archetypal.settings import ep_version


def get_eplus_dirs(version=ep_version):
    """Returns EnergyPlus root folder for a specific version.

    Returns (Path): The folder path.

    Args:
        version (str): Version number in the form "9-2-0" to search for.
    """
    from eppy.runner.run_functions import install_paths

    eplus_exe, eplus_weather = install_paths(version)
    return Path(eplus_exe).dirname()


def get_eplus_basedirs():
    """Return a list of possible E+ install paths."""
    if platform.system() == "Windows":
        eplus_homes = Path("C:\\").dirs("EnergyPlus*")
        return eplus_homes
    elif platform.system() == "Linux":
        eplus_homes = Path("/usr/local/").dirs("EnergyPlus*")
        return eplus_homes
    elif platform.system() == "Darwin":
        eplus_homes = Path("/Applications").dirs("EnergyPlus*")
        return eplus_homes
    else:
        warnings.warn(
            "Archetypal is not compatible with %s. It is only compatible "
            "with Windows, Linux or MacOs" % platform.system()
        )


def _latest_energyplus_version():
    """Finds all installed versions of EnergyPlus in the default location and
    returns the latest version number.

    Returns:
        (archetypal.EnergyPlusVersion): The version number of the latest E+
        install
    """

    eplus_homes = get_eplus_basedirs()

    # check if any EnergyPlus install exists
    if not eplus_homes:
        raise Exception(
            "No EnergyPlus installation found. Make sure you have EnergyPlus "
            "installed.  Go to https://energyplus.net/downloads to download the "
            "latest version of EnergyPlus."
        )

    # Find the most recent version of EnergyPlus installed from the version
    # number (at the end of the folder name)
    return sorted(
        (re.search(r"([\d])-([\d])-([\d])", home.stem).group() for home in eplus_homes),
        reverse=True,
    )[0]


def warn_if_not_compatible():
    """Checks if an EnergyPlus install is detected. If the latest version
    detected is higher than the one specified by archetypal, a warning is also
    raised.
    """
    eplus_homes = get_eplus_basedirs()

    if not eplus_homes:
        warnings.warn(
            "No installation of EnergyPlus could be detected on this "
            "machine. Please install EnergyPlus from https://energyplus.net before "
            "using archetypal"
        )


class EnergyPlusVersion(Version):
    try:
        iddnames = set(
            chain.from_iterable(
                (
                    (basedir / "PreProcess" / "IDFVersionUpdater").files("*.idd")
                    for basedir in get_eplus_basedirs()
                )
            )
        )
    except FileNotFoundError:
        _choices = ["9-2-0"]  # Little hack in case E+ is not installed
    else:
        _choices = set(
            re.match("V(.*)-Energy\+", idd.stem).groups()[0] for idd in iddnames
        )

    @property
    def tuple(self):
        return self.major, self.minor, self.micro

    @property
    def dash(self):
        # type: () -> str
        return "-".join(map(str, (self.major, self.minor, self.micro)))

    def __repr__(self):
        # type: () -> str
        return "<EnergyPlusVersion({0})>".format(repr(str(self)))

    def __init__(self, version):
        """

        Args:
            version (str, EnergyPlusVersion):
        """
        if isinstance(version, tuple):
            version = ".".join(map(str, version[0:3]))
        if isinstance(version, Version):
            version = ".".join(map(str, (version.major, version.minor, version.micro)))
        if isinstance(version, str) and "-" in version:
            version = version.replace("-", ".")
        super(EnergyPlusVersion, self).__init__(version)
        if self.dash not in self._choices:
            raise InvalidEnergyPlusVersion
