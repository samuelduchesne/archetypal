import pytest
import os
from click.testing import CliRunner

from archetypal import get_eplus_dirs
from archetypal.settings import ep_version
from archetypal.cli import cli
from path import Path


class TestCli:
    """Defines tests for usage of the archetypal Command Line Interface"""

    @pytest.fixture(
        params=[
            [
                1,
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "convert",
                "--ep-version",
                "9-1-0",
                "tests/input_data/trnsys/simple_2_zone.idf",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "--trnsidf-exe",
                "docker/trnsidf/trnsidf.exe",
            ],
            [
                2,
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "convert",
                "--ep-version",
                "9-1-0",
                "-i",
                "-t",
                "-d",
                "tests/input_data/trnsys/simple_2_zone.idf",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "--trnsidf-exe",
                "docker/trnsidf/trnsidf.exe",
            ],
            [
                3,
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "convert",
                "--ep-version",
                "9-1-0",
                "--window-lib",
                "archetypal/ressources/W74-lib.dat",
                "tests/input_data/trnsys/simple_2_zone.idf",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "--trnsidf-exe",
                "docker/trnsidf/trnsidf.exe",
            ],
            [
                4,
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "convert",
                "--ep-version",
                "9-1-0",
                "--template",
                "archetypal/ressources/NewFileTemplate.d18",
                "tests/input_data/trnsys/simple_2_zone.idf",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "--trnsidf-exe",
                "docker/trnsidf/trnsidf.exe",
            ],
            [
                5,
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "convert",
                "--ep-version",
                "9-1-0",
                "--log-clear-names",
                "tests/input_data/trnsys/simple_2_zone.idf",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "--trnsidf-exe",
                "docker/trnsidf/trnsidf.exe",
            ],
            [
                6,
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "convert",
                "--ep-version",
                "9-1-0",
                "--window",
                1.5,
                0.6,
                0.81,
                0.1,
                0.13,
                5.6,
                "tests/input_data/trnsys/simple_2_zone.idf",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "--trnsidf-exe",
                "docker/trnsidf/trnsidf.exe",
            ],
            [
                7,
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "convert",
                "--ep-version",
                "9-1-0",
                "--ordered",
                "tests/input_data/trnsys/simple_2_zone.idf",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "--trnsidf-exe",
                "docker/trnsidf/trnsidf.exe",
            ],
            [
                8,
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "convert",
                "--ep-version",
                "9-1-0",
                "--nonum",
                "-N",
                "--geofloor",
                0.6,
                "--refarea",
                "--volume",
                "--capacitance",
                "tests/input_data/trnsys/simple_2_zone.idf",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "--trnsidf-exe",
                "docker/trnsidf/trnsidf.exe",
            ],
            [
                9,
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "convert",
                "--ep-version",
                "9-1-0",
                "--schedule-as-input",
                "tests/input_data/trnsys/simple_2_zone.idf",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "--trnsidf-exe",
                "docker/trnsidf/trnsidf.exe",
            ],
        ]
    )
    def cli_args(config, request):
        if request.param[0] == 1:
            print("Runs convert cli with EnergyPlus version 9-1-0")
        elif request.param[0] == 2:
            print(
                "Runs convert cli with EnergyPlus version 9-1-0 AND returns paths to "
                "modified IDF, T3D file and the DCK file"
            )
        elif request.param[0] == 3:
            print(
                "Runs convert cli with EnergyPlus version 9-1-0 AND a given window library"
            )
        elif request.param[0] == 4:
            print(
                "Runs convert cli with EnergyPlus version 9-1-0 AND a given d18 template"
            )
        elif request.param[0] == 5:
            print(
                "Runs convert cli with EnergyPlus version 9-1-0 AND without logging "
                "in console the equivalence between"
                " old and new names"
            )
        elif request.param[0] == 6:
            print(
                "Runs convert cli with EnergyPlus version 9-1-0 AND given window parameters "
                "(u-value, shgc, t_vis, etc.) to find in default window library"
            )
        elif request.param[0] == 7:
            print(
                "Runs convert cli with EnergyPlus version 9-1-0 AND the ordered option "
                "(sorting the idf object names)"
            )
        elif request.param[0] == 8:
            print(
                "Runs convert cli with EnergyPlus version 9-1-0 AND trnsidf.exe arguments:"
                "1) Will not renumber surfaces"
                "2) Does BatchJob Modus"
                "3) 60% of solar radiation is directed to the floor"
                "4) Updates floor reference area of airnodes"
                "5) Updates volume of airnodes"
                "6) Updates the capacitance of airnodes"
            )
        elif request.param[0] == 9:
            print(
                "Runs convert cli with EnergyPlus version 9-1-0 AND writing the "
                "schedules as SCHEDULES"
            )
        else:
            print("Runs convert cli with EnergyPlus version 9-1-0 AND other parameters")

        yield request.param[1:]

    @pytest.mark.xfail(
        "TRAVIS" in os.environ and os.environ["TRAVIS"] == "true",
        reason="Skipping this test on Travis CI.",
    )
    def test_convert(self, config, cli_args):
        """Tests the 'reduce' method"""
        runner = CliRunner()
        args = cli_args
        result = runner.invoke(cli, args, catch_exceptions=False)
        print(result.stdout)
        assert result.exit_code == 0

    def test_reduce(self, config):
        """Tests the 'reduce' method"""
        runner = CliRunner()
        test_file_list = [
            "tests/input_data/umi_samples/B_Off_0.idf",
            "tests/input_data/umi_samples/B_Res_0_Masonry.idf",
        ]
        result = runner.invoke(
            cli,
            [
                "--use-cache",
                "--cache-folder",
                "tests/.temp/cache",
                "--data-folder",
                "tests/.temp/data",
                "--imgs-folder",
                "tests/.temp/images",
                "--logs-folder",
                "tests/.temp/logs",
                "--log-console",
                "--ep_version",
                "8-9-0",
                "reduce",
                "-n",
                "Retail",
                "-w",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "-p",
                *test_file_list,
            ],
            catch_exceptions=False,
        )
        print(result.stdout)
        assert result.exit_code == 0
