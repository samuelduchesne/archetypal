import pytest

from archetypal.eplus_interface.exceptions import InvalidEnergyPlusVersion
from archetypal.eplus_interface.version import EnergyPlusVersion


class TestEnergyPlusVersion:
    """"""

    def test_eplusversion_version_init(self):
        """Test the initialization of VersionIdd and basic properties"""
        eplus_version = EnergyPlusVersion("9.2")
        str(eplus_version)  # test the string representation
        assert repr(eplus_version) == "<EnergyPlusVersion('9.2')>"  # test the repr

        assert eplus_version.dash == "9-2-0"
        assert eplus_version.tuple == (9, 2, 0)
        assert isinstance(eplus_version.valid_versions, set)

        # initialized 3 different ways, should return equivalent objects.
        assert (
            EnergyPlusVersion("9.2.0")
            == EnergyPlusVersion((9, 2, 0))
            == EnergyPlusVersion("9-2-0")
        )

        copy_of_idd_version = eplus_version.duplicate()
        assert copy_of_idd_version == eplus_version

        # initialize current module version
        eplus_version = EnergyPlusVersion.current()
        str(eplus_version)  # test the string representation

        # initialize current version
        eplus_version = EnergyPlusVersion.latest()
        str(eplus_version)  # test the string representation

        assert isinstance(eplus_version.current_idd_path, str)

    def test_eplusversion_err_init(self):
        """Test initialization of VersionIDd which produces an error."""
        with pytest.raises(InvalidEnergyPlusVersion):
            idd_version = EnergyPlusVersion("3.2.0")

    def test_idd_on_missing_install(self):
        idd_version = EnergyPlusVersion("9.2")
        idd_version._valid_paths = {}  # fakes not finding any versions on machine.

        assert idd_version.valid_versions == {"9-2-0",}
