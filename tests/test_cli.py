from click.testing import CliRunner

from archetypal import get_eplus_dirs, settings, copy_file, log
from archetypal.settings import ep_version
from archetypal.cli import cli
from path import Path


class TestCli:
    """Defines tests for usage of the archetypal Command Line Interface"""

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
                "--ep_version",
                settings.ep_version,
                "reduce",
                "-w",
                "tests/input_data/CAN_PQ_Montreal.Intl.AP.716270_CWEC.epw",
                "-p",
                *test_file_list,
                "tests/.temp/retail.json",
            ],
            catch_exceptions=False,
        )
        print(result.stdout)
        assert result.exit_code == 0

    def test_transition(self, config):
        """Tests the transition method for the CLI"""
        file = copy_file(
            "tests/input_data/problematic/ASHRAE90.1_ApartmentHighRise_STD2016_Buffalo.idf"
        )
        runner = CliRunner()
        result = runner.invoke(cli, ["transition", file], catch_exceptions=False)
        log(result.stdout)
        assert result.exit_code == 0
