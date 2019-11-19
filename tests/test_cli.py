from click.testing import CliRunner

from archetypal import get_eplus_dirs
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
