"""EnergyPlusVersion module."""

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
    """Return EnergyPlus root folder for a specific version.

    Args:
        version (str): Version number in the form "9-2-0" to search for.

    Returns:
        (Path): The folder path.
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
    """Find all EnergyPlus installs. and returns the latest version number.

    Only looks in default locations on all platforms.

    Returns:
        (EnergyPlusVersion): The version number of the latest E+ install
    """
    eplus_homes = get_eplus_basedirs()

    # check if any EnergyPlus install exists
    if not eplus_homes:
        raise Exception(
            "No EnergyPlus installation found. Make sure you have EnergyPlus "
            "installed. Go to https://energyplus.net/downloads to download the "
            "latest version of EnergyPlus."
        )

    # Find the most recent version of EnergyPlus installed from the version
    # number (at the end of the folder name)
    return sorted(
        (re.search(r"([\d])-([\d])-([\d])", home.stem).group() for home in eplus_homes),
        reverse=True,
    )[0]


def warn_if_not_compatible():
    """Check if an EnergyPlus install is detected.

    Warnings:
        If the latest version detected is higher than the one specified by
        archetypal, a warning is raised.
    """
    eplus_homes = get_eplus_basedirs()

    if not eplus_homes:
        warnings.warn(
            "No installation of EnergyPlus could be detected on this "
            "machine. Please install EnergyPlus from https://energyplus.net before "
            "using archetypal"
        )


class EnergyPlusVersion(Version):
    """EnergyPlusVersion class.

    This class subclasses the :class:`packaging.version.Version` class. It is usuful
    to compare version numbers together.

    Any EnergyPlusVersion numbers are checked against valid versions before they can
    be initialized.

    Examples:
        To create a version number:

        >>> from archetypal import EnergyPlusVersion
        >>> EnergyPlusVersion("9.2.0")
        <EnergyPlusVersion('9.2.0')>

        An invalid version number raises an exception:

        >>> from archetypal import EnergyPlusVersion
        >>> EnergyPlusVersion("3.2.0")  # "3.2.0" was never released.
        archetypal.eplus_interface.exceptions.InvalidEnergyPlusVersion

    """

    def __init__(self, version):
        """Initialize an EnergyPlusVersion from a version number.

        Args:
            version (str, EnergyPlusVersion): The version number to create. Can be a
                string a tuple or another EnergyPlusVersion object.

        Raises:
            InvalidEnergyPlusVersion: If the version is not a valid version number.
        """
        if isinstance(version, tuple):
            version = ".".join(map(str, version[0:3]))
        if isinstance(version, Version):
            version = ".".join(map(str, (version.major, version.minor, version.micro)))
        if isinstance(version, str) and "-" in version:
            version = version.replace("-", ".")
        super(EnergyPlusVersion, self).__init__(version)
        if self.dash not in self.valid_versions:
            raise InvalidEnergyPlusVersion

    def __repr__(self) -> str:
        """Return a representation of self."""
        return "<EnergyPlusVersion({0})>".format(repr(str(self)))

    @classmethod
    def latest(cls):
        """Return the latest EnergyPlus version installed."""
        version = _latest_energyplus_version()
        return cls(version)

    @classmethod
    def current(cls):
        """Return the current EnergyPlus version specified by the main module.

        Specified by :ref:`archetypal.settings.ep_version`
        """
        version = settings.ep_version
        return cls(version)

    @property
    def tuple(self) -> tuple:
        """Return the object as a tuple: (major, minor, micro)."""
        return self.major, self.minor, self.micro

    @property
    def dash(self) -> str:
        """Return the object as a dash-separated string: "major-minor-micro"."""
        return "-".join(map(str, (self.major, self.minor, self.micro)))

    @property
    def valid_versions(self) -> list:
        """List the idd versions installed on this machine."""
        try:
            basedirs_ = []
            for basedir in get_eplus_basedirs():
                updater_ = basedir / "PreProcess" / "IDFVersionUpdater"
                if updater_.exists():
                    basedirs_.append(updater_.files("*.idd"))
                else:
                    # The IDFVersionUpdate folder could be removed in some installation (eg Docker container).
                    # Add the idd contained in the basedir instead.
                    basedirs_.append(basedir.files("*.idd"))
            iddnames = set(chain.from_iterable(basedirs_))
        except FileNotFoundError:
            _choices = ["9-2-0"]  # Little hack in case E+ is not installed
        else:
            _choices = set(
                re.match(r"V(.*)-Energy\+", idd.stem).groups()[0] for idd in iddnames
            )
        return _choices
