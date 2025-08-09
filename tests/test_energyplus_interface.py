import pytest
from path import Path

from archetypal.eplus_interface.energy_plus import EnergyPlusExe, EnergyPlusProgram
from archetypal.eplus_interface.exceptions import EnergyPlusVersionError
from archetypal.eplus_interface.version import EnergyPlusVersion


def test_energyplus_exe_cmd(tmp_path, mocker):
    exe = Path(tmp_path / "energyplus")
    exe.write_text("")
    weather = Path(tmp_path / "weather")
    weather.write_text("")
    mocker.patch("eppy.runner.run_functions.install_paths", return_value=(str(exe), str(weather)))
    version = EnergyPlusVersion("9.2.0")
    ep = EnergyPlusExe("in.idf", "in.epw", Path(tmp_path), version, annual=True, readvars=False)
    cmd = ep.cmd()
    assert str(exe) in str(cmd[0])
    assert "-a" in cmd
    assert "-r" not in cmd
    assert "in.idf" in cmd[-1]


def test_energyplus_exe_missing(tmp_path, mocker):
    mocker.patch(
        "eppy.runner.run_functions.install_paths",
        return_value=(str(Path(tmp_path) / "missing"), str(tmp_path)),
    )
    version = EnergyPlusVersion("9.2.0")
    with pytest.raises(EnergyPlusVersionError):
        EnergyPlusExe("in.idf", "in.epw", Path(tmp_path), version)


def test_energyplus_program_home(tmp_path):
    version = EnergyPlusVersion("9.2.0")
    version.install_locations = {version.dash: Path(tmp_path)}
    idf = type("IDF", (), {"file_version": version})()
    program = EnergyPlusProgram(idf)
    assert program.eplus_home == Path(tmp_path)
