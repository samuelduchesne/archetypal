"""EnergyPlusVersion module handles finding idd paths and valid versions."""

import platform
import re
import warnings
from itertools import chain

from packaging.version import Version
from path import Path

from archetypal import settings
from archetypal.eplus_interface.exceptions import (
    EnergyPlusVersionError,
    InvalidEnergyPlusVersion,
)


class EnergyPlusVersion(Version):
    """EnergyPlusVersion class.

    This class subclasses the :class:`packaging.version.Version` class. It is usuful
    to compare version numbers together.

    Any EnergyPlusVersion numbers are checked against valid versions before they can
    be initialized.

    Examples:
        To create a version number:

        >>> from archetypal.eplus_interface.version import EnergyPlusVersion
        >>> EnergyPlusVersion("9.2.0")
        <EnergyPlusVersion('9.2.0')>

        An invalid version number raises an exception:

        >>> from archetypal.eplus_interface.version import EnergyPlusVersion
        >>> EnergyPlusVersion("3.2.0")  # "3.2.0" was never released.
        archetypal.eplus_interface.exceptions.InvalidEnergyPlusVersion

    """

    __slots__ = ("_valid_paths", "_install_locations")

    def __init__(self, version):
        """Initialize an EnergyPlusVersion from a version number.

        Args:
            version (str, EnergyPlusVersion): The version number to create. Can be a
                string a tuple or another EnergyPlusVersion object.

        Raises:
            InvalidEnergyPlusVersion: If the version is not a valid version number.
        """
        self.install_locations = {}
        self.valid_idd_paths = {}

        if isinstance(version, tuple):
            version = ".".join(map(str, version[0:3]))
        if isinstance(version, Version):
            version = ".".join(map(str, (version.major, version.minor, version.micro)))
        if isinstance(version, str) and "-" in version:
            version = version.replace("-", ".")
        super(EnergyPlusVersion, self).__init__(version)
        if self.dash not in self.valid_versions:
            raise InvalidEnergyPlusVersion

    @classmethod
    def latest(cls):
        """Initialize an EnergyPlusVersion with the latest version installed."""
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
        version = next(
            iter(
                sorted(
                    (
                        Version(
                            re.search(r"\d+(-\d+)+", home.stem)
                            .group()
                            .replace("-", ".")
                        )
                        for home in eplus_homes
                    ),
                    reverse=True,
                )
            )
        )
        return cls(version)

    @property
    def dash(self) -> str:
        """Return the version number as a dash-separated string: "major-minor-micro"."""
        return "-".join(map(str, (self.major, self.minor, self.micro)))

    @property
    def dot(self) -> str:
        """Return the version number as a dot-separated string: "major.minor.micro"."""
        return ".".join(map(str, (self.major, self.minor, self.micro)))

    @property
    def current_idd_path(self):
        """Get the current Idd file path for this version."""
        return self.valid_idd_paths[self.dash]

    @property
    def current_install_dir(self):
        """Get the current installation directory for this EnergyPlus version."""
        try:
            return self.install_locations[self.dash]
        except KeyError:
            raise EnergyPlusVersionError(
                f"EnergyPlusVersion {self.dash} is not installed."
            )

    @property
    def tuple(self) -> tuple:
        """Return the version number as a tuple: (major, minor, micro)."""
        return self.major, self.minor, self.micro

    @property
    def valid_versions(self) -> set:
        """List the idd file version found on this machine."""
        if not self.valid_idd_paths:
            # Little hack in case E+ is not installed
            _choices = {
                settings.ep_version,
            }
        else:
            _choices = set(self.valid_idd_paths.keys())

        return _choices

    @property
    def install_locations(self) -> dict:
        """Get or set the available EnergyPlus root folders keyed by version number.

        Installation folders are detected automatically at the default location for
        all platforms.
        """
        return self._install_locations

    @install_locations.setter
    def install_locations(self, value):
        if not value:
            value = {}
            for basedir in get_eplus_basedirs():
                # match the Idd file contained in basedir
                match = re.search(r"\d+(-\d+)+", basedir)
                version = match.group()
                value[version] = basedir.expand()
        self._install_locations = value

    @property
    def valid_idd_paths(self) -> dict:
        """Get or set the idd paths as a dict with version numbers as keys."""
        return self._valid_paths

    @valid_idd_paths.setter
    def valid_idd_paths(self, value):
        assert isinstance(value, dict)
        if not value:
            try:
                basedirs_ = []
                for version, basedir in self.install_locations.items():
                    updater_ = basedir / "PreProcess" / "IDFVersionUpdater"
                    if updater_.exists():
                        basedirs_.append(updater_.files("*.idd"))
                    else:
                        # The IDFVersionUpdate folder could be removed in some
                        # installation (eg Docker container).
                        # Add the idd contained in the basedir instead.
                        basedirs_.append(basedir.files("*.idd"))
                iddnames = set(chain.from_iterable(basedirs_))
            except FileNotFoundError:
                _valid_paths = {}
            else:
                _valid_paths = {}
                for iddname in iddnames:
                    match = re.search("\d+(-\d+)+", iddname.stem)
                    if match is None:
                        # match the Idd file contained in basedir
                        match = re.search(r"\d+(-\d+)+", iddname.stem)
                        version = match.group()
                    else:
                        version = match.group()

                    _valid_paths[version] = iddname
        self._valid_paths = dict(sorted(_valid_paths.items()))

    @classmethod
    def current(cls):
        """Initialize an EnergyPlusVersion object for the specified module version.

        Notes:
            Specified by :ref:`archetypal.settings.ep_version` which looks for the
            `"ENERGYPLUS_VERSION` environment variable.
        """
        version = settings.ep_version
        return cls(version)

    @property
    def current_install_location(self):
        return self.install_locations[self.dash]

    def duplicate(self):
        """Get a copy of this object."""
        return self.__copy__()

    def __copy__(self):
        """Return a copy of self."""
        return EnergyPlusVersion(self)

    def __repr__(self) -> str:
        """Return a representation of self."""
        return f"<EnergyPlusVersion('{str(self)}')>"


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
